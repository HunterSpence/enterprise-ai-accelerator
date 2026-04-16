"""Tests for app_portfolio/ — language_detector, dependency_scanner, containerization_scorer, ci_maturity."""

from pathlib import Path

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
