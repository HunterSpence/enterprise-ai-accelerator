# app_portfolio — Repository Intelligence + 6R Scoring

Scans one or more code repositories and produces a structured intelligence report: language composition, dependency inventory, CVE findings, containerization readiness, CI maturity, test coverage, and an Opus 4.7 extended-thinking 6R cloud migration recommendation per repo.

---

## Architecture

```
CLI (python -m app_portfolio.cli <path>)
        |
        v
Analyzer.run(path)
        |
        ├── LanguageDetector        (11 languages)
        ├── DependencyScanner       (9 manifest formats)
        ├── CVEScanner              (OSV.dev batch API)
        ├── ContainerizationScorer  (Dockerfile / k8s)
        ├── CIMaturityScorer        (GitHub Actions / GitLab / Jenkins)
        ├── TestCoverageScanner     (pytest / jest / go test)
        └── SixRScorer              (Opus 4.7 extended thinking)
                |
                v
        PortfolioReport (JSON + console output)
```

All scorers are independent and run in parallel where possible. `SixRScorer` is the only step that calls the Anthropic API; all others are static analysis.

---

## Scan Pipeline

### Step 1 — Language Detection

`LanguageDetector` walks the repository tree and classifies files by extension and content heuristics. Supported languages:

Python, JavaScript, TypeScript, Java, Go, Rust, C#, Ruby, PHP, C/C++, Kotlin

Output: `{language: file_count, ...}` + primary language + LoC estimate.

### Step 2 — Dependency Scanning

`DependencyScanner` reads the following manifest formats:

| Manifest | Language |
|---|---|
| `requirements.txt` / `pyproject.toml` | Python |
| `package.json` | JavaScript / TypeScript |
| `go.mod` | Go |
| `Gemfile` | Ruby |
| `pom.xml` | Java (Maven) |
| `build.gradle` | Java / Kotlin (Gradle) |
| `Cargo.toml` | Rust |
| `composer.json` | PHP |

Output: flat list of `{name, version, ecosystem}` tuples.

### Step 3 — CVE Scanning

`CVEScanner` submits all detected packages to the [OSV.dev](https://osv.dev) batch API. Results are bucketed by severity (CRITICAL / HIGH / MEDIUM / LOW). No API key required — OSV.dev is free.

Output: `{critical: [...], high: [...], medium: [...], low: [...]}` with CVE IDs and descriptions.

### Step 4 — Containerization Score

`ContainerizationScorer` checks for:
- `Dockerfile` presence and quality (multi-stage, non-root user, HEALTHCHECK)
- `.dockerignore`
- Kubernetes manifests (`*.yaml` with `kind: Deployment/StatefulSet/DaemonSet`)
- Helm chart (`Chart.yaml`)
- Docker Compose file

Score: 0–100. Thresholds: `<40` = Not containerized, `40–70` = Partial, `>70` = Container-native.

### Step 5 — CI Maturity Score

`CIMaturityScorer` detects CI platform and evaluates:
- Pipeline file presence (GitHub Actions `.github/workflows/`, GitLab `.gitlab-ci.yml`, etc.)
- Test stage present
- Build stage present
- Linting / security scanning stage present
- Deployment stage present

Score: 0–100 by feature count.

### Step 6 — Test Coverage

`TestCoverageScanner` looks for coverage report artifacts:
- `coverage.xml`, `.coverage`, `htmlcov/` (pytest)
- `lcov.info`, `coverage/` (jest / istanbul)
- `coverage.out` (go test)

Extracts line coverage percentage where parseable.

### Step 7 — 6R Recommendation (Opus 4.7 Extended Thinking)

`SixRScorer` assembles the outputs of steps 1–6 into a structured prompt and calls Opus 4.7 with extended thinking enabled (up to 16k reasoning tokens). The model returns:

- Primary 6R strategy: Rehost / Replatform / Repurchase / Refactor / Retire / Retain
- Confidence score (0–1)
- Key rationale (3–5 bullet points)
- Top blockers for migration
- Recommended first action

The reasoning trace is optionally persisted to `ai_audit_trail` as Annex IV evidence.

---

## CLI Usage

```bash
# Scan current directory
python -m app_portfolio.cli .

# Scan a specific repo
python -m app_portfolio.cli /path/to/repo

# Scan without calling Anthropic API (skip 6R scoring)
python -m app_portfolio.cli . --no-ai

# Output as JSON
python -m app_portfolio.cli . --format json

# Output to file
python -m app_portfolio.cli . --output report.json
```

---

## Sample Output

```
App Portfolio Report — /path/to/my-service
============================================
Primary language:     Python (1,247 files, ~38k LoC)
Dependencies:         42 packages (requirements.txt + pyproject.toml)
CVEs found:           3 CRITICAL, 7 HIGH, 12 MEDIUM
Containerization:     72/100 (Container-native — multi-stage Dockerfile + K8s manifests)
CI maturity:          85/100 (GitHub Actions — test + build + deploy stages)
Test coverage:        68% line coverage (pytest coverage.xml)

6R Recommendation:    REPLATFORM (confidence: 0.84)
Rationale:
  - Python-native codebase maps well to managed container services
  - Existing Dockerfile reduces containerization effort
  - 3 CRITICAL CVEs in pinned dependencies — remediation is pre-req
  - CI pipeline is mature; deployment stage needs cloud target update
First action:         Update pinned deps to resolve CRITICAL CVEs, then migrate to ECS/Cloud Run
```

---

## Environment Variables

```
ANTHROPIC_API_KEY    # Required for SixRScorer (step 7). All other steps run without it.
```

---

## Programmatic Usage

```python
from app_portfolio.analyzer import PortfolioAnalyzer

analyzer = PortfolioAnalyzer(use_ai=True)
report = analyzer.run("/path/to/repo")

print(report.six_r_recommendation.strategy)   # e.g. "REPLATFORM"
print(report.cve_findings.critical)            # list of CVE dicts
print(report.containerization_score)           # 0–100
```
