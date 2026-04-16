"""
app_portfolio/language_detector.py
===================================

File-extension + shebang heuristic language detector.

Returns a dict mapping language name -> non-blank, non-comment LoC.
Supports: Python, JavaScript, TypeScript, Go, Java, C#, Ruby, PHP,
          Rust, Kotlin, Scala.

Design notes:
- Never raises to caller — returns empty dict on any error.
- Single-pass line counter strips blank lines and comment-only lines
  via language-specific prefix rules (no AST/regex — fast on large repos).
- Shebang detection handles extensionless scripts (#!/usr/bin/env python3 etc).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extension → language mapping
# ---------------------------------------------------------------------------

_EXT_MAP: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".phtml": "php",
    ".rs": "rust",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".sc": "scala",
}

# ---------------------------------------------------------------------------
# Comment prefix rules per language (single-line comment markers)
# Note: block comments (/* */) handled by checking stripped line starts.
# ---------------------------------------------------------------------------

_COMMENT_PREFIXES: dict[str, tuple[str, ...]] = {
    "python": ("#",),
    "javascript": ("//", "/*", "*", "*/"),
    "typescript": ("//", "/*", "*", "*/"),
    "go": ("//", "/*", "*", "*/"),
    "java": ("//", "/*", "*", "*/"),
    "csharp": ("//", "/*", "*", "*/"),
    "ruby": ("#",),
    "php": ("//", "#", "/*", "*", "*/"),
    "rust": ("//", "/*", "*", "*/"),
    "kotlin": ("//", "/*", "*", "*/"),
    "scala": ("//", "/*", "*", "*/"),
}

# ---------------------------------------------------------------------------
# Shebang → language
# ---------------------------------------------------------------------------

_SHEBANG_MAP: list[tuple[str, str]] = [
    ("python3", "python"),
    ("python2", "python"),
    ("python", "python"),
    ("node", "javascript"),
    ("ruby", "ruby"),
    ("php", "php"),
    ("perl", "perl"),
]


def _detect_from_shebang(first_line: str) -> str | None:
    """Return language if first_line is a recognisable shebang, else None."""
    stripped = first_line.strip()
    if not stripped.startswith("#!"):
        return None
    for token, lang in _SHEBANG_MAP:
        if token in stripped:
            return lang
    return None


def _count_code_lines(path: Path, language: str) -> int:
    """Count non-blank, non-comment lines in *path* for *language*.

    Gracefully returns 0 on any read/decode error.
    """
    prefixes = _COMMENT_PREFIXES.get(language, ())
    count = 0
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                stripped = raw_line.strip()
                if not stripped:
                    continue  # blank
                if prefixes and any(stripped.startswith(p) for p in prefixes):
                    continue  # comment
                count += 1
    except Exception as exc:  # noqa: BLE001
        logger.debug("language_detector: skipping %s — %s", path, exc)
    return count


def detect_languages(
    file_paths: list[Path],
) -> dict[str, int]:
    """Scan *file_paths* and return {language: code_loc}.

    Files whose extension is not in the known map are checked for a shebang
    on the first line.  Unrecognised files are ignored.

    Args:
        file_paths: Pre-filtered list of paths to inspect (no .gitignore
                    logic here — caller is responsible for filtering).

    Returns:
        Dict mapping lower-case language name to integer LoC count
        (blank + comment lines excluded).  Never raises.
    """
    result: dict[str, int] = {}

    for path in file_paths:
        try:
            ext = path.suffix.lower()
            language = _EXT_MAP.get(ext)

            if language is None:
                # Try shebang only for extensionless files or .sh
                if ext in ("", ".sh"):
                    try:
                        with path.open(encoding="utf-8", errors="replace") as fh:
                            first = fh.readline()
                        language = _detect_from_shebang(first)
                    except Exception:  # noqa: BLE001
                        pass

            if language is None:
                continue

            loc = _count_code_lines(path, language)
            result[language] = result.get(language, 0) + loc

        except Exception as exc:  # noqa: BLE001
            logger.debug("language_detector: error on %s — %s", path, exc)

    return result
