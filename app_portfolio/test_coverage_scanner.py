"""
app_portfolio/test_coverage_scanner.py
========================================

Heuristic test coverage scanner — no test runner required.

Counts test files vs source files by convention:
  Python  — test_*.py, *_test.py, tests/ directory, conftest.py
  JS/TS   — *.test.ts, *.test.js, *.spec.ts, *.spec.js, __tests__/
  Go      — *_test.go
  Java    — *Test.java, *Tests.java, *IT.java (src/test/java/)
  Ruby    — *_spec.rb, spec/, test/
  Rust    — tests/ module (files in tests/ directory)
  Generic — any path with /test/ or /tests/ or /spec/ in it

Also detects test framework config files:
  pytest.ini, setup.cfg [tool:pytest], pyproject.toml [tool.pytest],
  jest.config.{js,ts,mjs}, vitest.config.*, .mocharc*, karma.conf.*,
  testng.xml, phpunit.xml, RSpec (Gemfile with rspec)

Returns:
  test_file_count: int
  source_file_count: int
  test_ratio: float  (test_files / source_files, capped at 1.0)
  test_config_found: bool

Never raises — returns zeros on any error.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File patterns
# ---------------------------------------------------------------------------

# Extensions we consider "source" (mirrors language_detector)
_SOURCE_EXTENSIONS = {
    ".py", ".pyw",
    ".js", ".mjs", ".cjs", ".jsx",
    ".ts", ".tsx", ".mts", ".cts",
    ".go",
    ".java",
    ".cs",
    ".rb",
    ".php",
    ".rs",
    ".kt", ".kts",
    ".scala", ".sc",
}

# Test filename patterns (case-insensitive match against stem or full name)
_TEST_STEM_PREFIXES = ("test_", "tests_")
_TEST_STEM_SUFFIXES = ("_test", "_tests", "_spec", ".test", ".spec")
_TEST_EXACT_NAMES = {
    "conftest.py",
    "setup_test.py",
}

# Test directory name components
_TEST_DIR_PARTS = {"test", "tests", "spec", "specs", "__tests__", "test_suite"}

# Test config file names
_TEST_CONFIG_NAMES = {
    "pytest.ini",
    "setup.cfg",        # may contain [tool:pytest]
    "pyproject.toml",   # may contain [tool.pytest.ini_options]
    "jest.config.js",
    "jest.config.ts",
    "jest.config.mjs",
    "jest.config.cjs",
    "vitest.config.ts",
    "vitest.config.js",
    ".mocharc.js",
    ".mocharc.yml",
    ".mocharc.json",
    "karma.conf.js",
    "testng.xml",
    "phpunit.xml",
    "phpunit.xml.dist",
    "Gemfile",          # check content for rspec
}


def _is_test_file(path: Path) -> bool:
    """Return True if *path* looks like a test file by name or location."""
    if path.suffix not in _SOURCE_EXTENSIONS:
        return False

    name = path.name
    stem = path.stem

    # Exact names
    if name in _TEST_EXACT_NAMES:
        return True

    # Prefix / suffix patterns
    stem_lower = stem.lower()
    if any(stem_lower.startswith(p) for p in _TEST_STEM_PREFIXES):
        return True
    if any(stem_lower.endswith(s) for s in _TEST_STEM_SUFFIXES):
        return True

    # Java test conventions
    if path.suffix == ".java" and (
        stem.endswith("Test") or stem.endswith("Tests") or stem.endswith("IT")
    ):
        return True

    # Go test files
    if path.suffix == ".go" and stem.endswith("_test"):
        return True

    # Ruby spec files
    if path.suffix == ".rb" and stem.endswith("_spec"):
        return True

    # Directory-based detection
    parts_lower = {p.lower() for p in path.parts}
    if parts_lower & _TEST_DIR_PARTS:
        return True

    return False


def _is_test_config(path: Path, content_cache: dict[Path, str]) -> bool:
    """Return True if *path* is a recognised test config."""
    if path.name not in _TEST_CONFIG_NAMES:
        return False

    # setup.cfg — only counts if [tool:pytest] section present
    if path.name == "setup.cfg":
        content = content_cache.get(path, "")
        return "[tool:pytest]" in content

    # pyproject.toml — only if [tool.pytest.ini_options] present
    if path.name == "pyproject.toml":
        content = content_cache.get(path, "")
        return "tool.pytest.ini_options" in content or "[tool.pytest]" in content

    # Gemfile — only if rspec dependency present
    if path.name == "Gemfile":
        content = content_cache.get(path, "")
        return "rspec" in content.lower()

    return True


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def scan_test_coverage(
    all_files: list[Path],
) -> tuple[int, int, float, bool]:
    """Scan *all_files* for test coverage heuristics.

    Returns:
        (test_file_count, source_file_count, test_ratio, test_config_found)
        Never raises — returns (0, 0, 0.0, False) on error.
    """
    try:
        return _scan_inner(all_files)
    except Exception as exc:  # noqa: BLE001
        logger.warning("test_coverage_scanner failed: %s", exc)
        return 0, 0, 0.0, False


def _scan_inner(
    all_files: list[Path],
) -> tuple[int, int, float, bool]:
    # Lazy-read config files only
    config_candidates = [p for p in all_files if p.name in _TEST_CONFIG_NAMES]
    content_cache: dict[Path, str] = {p: _read_safe(p) for p in config_candidates}

    test_files: set[Path] = set()
    source_files: set[Path] = set()

    for path in all_files:
        if path.suffix not in _SOURCE_EXTENSIONS:
            continue

        if _is_test_file(path):
            test_files.add(path)
        else:
            source_files.add(path)

    test_config_found = any(
        _is_test_config(p, content_cache) for p in config_candidates
    )

    test_count = len(test_files)
    source_count = len(source_files)

    if source_count == 0:
        ratio = 0.0
    else:
        ratio = min(test_count / source_count, 1.0)

    return test_count, source_count, ratio, test_config_found
