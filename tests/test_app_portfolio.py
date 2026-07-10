"""Tests for app_portfolio/ — language_detector, dependency_scanner, containerization_scorer, ci_maturity."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from app_portfolio.language_detector import detect_languages
from app_portfolio.containerization_scorer import score_containerization
from app_portfolio.ci_maturity_scorer import score_ci_maturity
from app_portfolio.report import Dependency, PortfolioReport, Vulnerability


class TestLanguageDetector:
    def test_detects_python(self, tmp_path):
        f = tmp_path / "main.py"
        f.write_text("def hello():\n    return 42\n")
        result = detect_languages([f])
        assert "python" in result
        assert result["python"] > 0

    def test_detects_javascript(self, tmp_path):
        f = tmp_path / "app.js"
        f.write_text("const x = 1;\nconsole.log(x);\n")
        result = detect_languages([f])
        assert "javascript" in result

    def test_detects_typescript(self, tmp_path):
        f = tmp_path / "index.ts"
        f.write_text("const x: number = 1;\n")
        result = detect_languages([f])
        assert "typescript" in result

    def test_detects_go(self, tmp_path):
        f = tmp_path / "main.go"
        f.write_text("package main\nfunc main() {}\n")
        result = detect_languages([f])
        assert "go" in result

    def test_skips_unknown_extension(self, tmp_path):
        f = tmp_path / "data.xyz"
        f.write_text("some data\n")
        result = detect_languages([f])
        assert "xyz" not in result

    def test_blank_and_comment_lines_excluded(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("# comment\n\ndef fn(): pass\n")
        result = detect_languages([f])
        # Only 1 non-blank non-comment line
        assert result.get("python", 0) == 1

    def test_empty_file_list(self):
        result = detect_languages([])
        assert result == {}


class TestContainerizationScorer:
    def test_no_dockerfile_low_score(self, tmp_path):
        score, issues = score_containerization(tmp_path, [])
        assert score < 20

    def test_with_dockerfile_boosts_score(self, tmp_path):
        df = tmp_path / "Dockerfile"
        df.write_text("FROM python:3.11-slim\nCMD python app.py\n")
        score, issues = score_containerization(tmp_path, [df])
        assert score >= 20

    def test_with_multistage_dockerfile(self, tmp_path):
        df = tmp_path / "Dockerfile"
        df.write_text(
            "FROM python:3.11 AS builder\nRUN pip install .\n"
            "FROM python:3.11-slim\nCOPY --from=builder /app /app\n"
            "USER nonroot\nHEALTHCHECK CMD curl -f http://localhost/ || exit 1\n"
            "EXPOSE 8080\n"
        )
        score, issues = score_containerization(tmp_path, [df])
        assert score >= 35

    def test_score_is_integer(self, tmp_path):
        score, issues = score_containerization(tmp_path, [])
        assert isinstance(score, int)

    def test_result_has_issues_list(self, tmp_path):
        score, issues = score_containerization(tmp_path, [])
        assert isinstance(issues, list)


class TestCIMaturityScorer:
    def test_no_ci_config_returns_zero_score(self, tmp_path):
        score, issues = score_ci_maturity(tmp_path, [])
        assert score == 0

    def test_github_actions_detected(self, tmp_path):
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        wf = wf_dir / "ci.yml"
        wf.write_text("name: CI\non: push\njobs:\n  test:\n    steps:\n      - run: pytest\n")
        score, issues = score_ci_maturity(tmp_path, [wf])
        assert score > 0

    def test_result_is_tuple(self, tmp_path):
        result = score_ci_maturity(tmp_path, [])
        assert isinstance(result, tuple)
        score, issues = result
        assert isinstance(score, int)
        assert isinstance(issues, list)


class TestPortfolioReport:
    def test_render_json_returns_str(self):
        report = PortfolioReport(
            repo_name="test-repo",
            repo_path=".",
            languages={},
            dependencies=[],
        )
        data = report.render_json()
        assert isinstance(data, str)
        import json
        parsed = json.loads(data)
        assert parsed["repo_name"] == "test-repo"

    def test_render_markdown_returns_string(self):
        report = PortfolioReport(
            repo_name="test-repo",
            repo_path=".",
            languages={"python": 500},
            dependencies=[],
        )
        md = report.render_markdown()
        assert isinstance(md, str)

    def test_dependency_dataclass(self):
        dep = Dependency(name="requests", version="2.31.0", ecosystem="pypi")
        assert dep.name == "requests"
        assert dep.is_stale is False  # days_since_latest is None

    def test_vulnerability_dataclass(self):
        vuln = Vulnerability(
            id="GHSA-xxxx", severity="HIGH", summary="test vuln", fix_version="2.32.0"
        )
        d = vuln.to_dict()
        assert d["id"] == "GHSA-xxxx"
        assert d["severity"] == "HIGH"

    def test_default_status_is_complete(self):
        report = PortfolioReport(repo_name="r", repo_path=".")
        assert report.status == "COMPLETE"
        assert report.partial_reasons == []

    def test_dependency_default_cve_scan_status_unscanned(self):
        dep = Dependency(name="requests", version="2.31.0", ecosystem="pypi")
        assert dep.cve_scan_status == "UNSCANNED"
        assert dep.to_dict()["cve_scan_status"] == "UNSCANNED"


class TestCVEScanOutageNotCachedClean:
    """P0-26: a failed OSV lookup must never be cached as (or reported as)
    a clean 0-vulnerability result."""

    def test_osv_failure_marks_failed_not_cached_clean(self, tmp_path):
        from app_portfolio.cve_scanner import scan_cves

        deps = [Dependency(name="requests", version="2.31.0", ecosystem="pypi")]

        async def _boom(*args, **kwargs):
            raise ConnectionError("simulated OSV outage")

        with patch("httpx.AsyncClient.post", side_effect=_boom):
            result = asyncio.run(scan_cves(deps, tmp_path))

        assert result[0].cve_scan_status == "FAILED"
        assert result[0].cves == []

        # The failure must not have been persisted to the 24h cache.
        cache_file = tmp_path / ".eaa_cache" / "osv_results.json"
        if cache_file.exists():
            import json
            cache = json.loads(cache_file.read_text())
            assert not cache, "a failed OSV lookup must never be cached as clean"

    def test_osv_success_with_zero_vulns_is_cached_and_ok(self, tmp_path, monkeypatch):
        from app_portfolio import cve_scanner

        deps = [Dependency(name="safe-pkg", version="1.0.0", ecosystem="pypi")]

        async def _fake_query(client, queries):
            return [{"vulns": []}] * len(queries), True

        monkeypatch.setattr(cve_scanner, "_query_osv_batch", _fake_query)
        result = asyncio.run(cve_scanner.scan_cves(deps, tmp_path))

        assert result[0].cve_scan_status == "OK"
        assert result[0].cves == []

        cache_file = tmp_path / ".eaa_cache" / "osv_results.json"
        assert cache_file.exists()

    def test_unsupported_ecosystem_not_marked_failed(self, tmp_path):
        from app_portfolio.cve_scanner import scan_cves

        deps = [Dependency(name="weird-pkg", version="1.0.0", ecosystem="not-a-real-ecosystem")]
        result = asyncio.run(scan_cves(deps, tmp_path))
        assert result[0].cve_scan_status == "UNSCANNED"


class TestRunStalenessDisabledMakesNoNetworkCalls:
    """MOD-014: run_staleness=False must make ZERO enrichment network calls."""

    def test_scan_dependencies_skips_enrichment_when_disabled(self, tmp_path, monkeypatch):
        from app_portfolio import dependency_scanner as ds

        (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")

        enrich_mock = AsyncMock()
        monkeypatch.setattr(ds, "_enrich_staleness", enrich_mock)

        deps = asyncio.run(ds.scan_dependencies(tmp_path, [tmp_path / "requirements.txt"], run_staleness=False))
        enrich_mock.assert_not_called()
        assert deps and deps[0].name == "requests"

    def test_scan_dependencies_calls_enrichment_when_enabled(self, tmp_path, monkeypatch):
        from app_portfolio import dependency_scanner as ds

        (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")

        enrich_mock = AsyncMock()
        monkeypatch.setattr(ds, "_enrich_staleness", enrich_mock)

        asyncio.run(ds.scan_dependencies(tmp_path, [tmp_path / "requirements.txt"], run_staleness=True))
        enrich_mock.assert_called_once()

    def test_analyzer_threads_run_staleness_false_through(self, tmp_path, monkeypatch):
        from app_portfolio.analyzer import RepoAnalyzer
        from app_portfolio import dependency_scanner as ds

        enrich_mock = AsyncMock()
        monkeypatch.setattr(ds, "_enrich_staleness", enrich_mock)

        analyzer = RepoAnalyzer(run_staleness=False, run_cve_scan=False)
        report = asyncio.run(analyzer.analyze(tmp_path))

        enrich_mock.assert_not_called()
        assert report.status == "COMPLETE"


class TestAnalyzerPartialStatus:
    """P0-26: truncation/skips must surface as report.status=PARTIAL with
    reasons, and a metadata error must not render as a clean empty report."""

    def test_file_limit_truncation_marks_partial(self, tmp_path, monkeypatch):
        from app_portfolio import analyzer as an

        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.py").write_text("y = 2\n")
        monkeypatch.setattr(an, "_MAX_FILES", 1)

        analyzer = an.RepoAnalyzer(run_staleness=False, run_cve_scan=False)
        report = asyncio.run(analyzer.analyze(tmp_path))

        assert report.status == "PARTIAL"
        assert any("file limit" in r for r in report.partial_reasons)

    def test_oversized_file_skip_marks_partial(self, tmp_path, monkeypatch):
        from app_portfolio import analyzer as an

        big = tmp_path / "big.py"
        big.write_bytes(b"x = 1\n")
        monkeypatch.setattr(an, "_MAX_FILE_SIZE_BYTES", 1)  # everything is "oversized"

        analyzer = an.RepoAnalyzer(run_staleness=False, run_cve_scan=False)
        report = asyncio.run(analyzer.analyze(tmp_path))

        assert report.status == "PARTIAL"
        assert any("skipped" in r for r in report.partial_reasons)

    def test_clean_small_repo_is_complete(self, tmp_path):
        from app_portfolio.analyzer import RepoAnalyzer

        (tmp_path / "a.py").write_text("x = 1\n")
        analyzer = RepoAnalyzer(run_staleness=False, run_cve_scan=False)
        report = asyncio.run(analyzer.analyze(tmp_path))
        assert report.status == "COMPLETE"
        assert report.partial_reasons == []

    def test_analyze_error_reports_failed_not_clean_empty(self, monkeypatch):
        from app_portfolio.analyzer import RepoAnalyzer

        analyzer = RepoAnalyzer(run_staleness=False, run_cve_scan=False)
        # A path that doesn't exist triggers the ValueError -> except branch.
        report = asyncio.run(analyzer.analyze(Path("Z:/definitely/does/not/exist/eaa-test")))
        assert report.status == "FAILED"
        assert "error" in report.metadata
