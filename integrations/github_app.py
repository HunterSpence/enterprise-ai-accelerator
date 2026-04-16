"""
integrations/github_app.py — GitHub App Check Run adapter.

Creates GitHub Check Runs for PR compliance gating. Conclusion = failure if any
critical/high findings exist, otherwise success. Annotations map findings to
source files where metadata provides file + line info.

Uses GitHub App JWT auth → installation token exchange (no OAuth scopes needed
beyond the app's own `checks: write` permission).

Env vars:
    EAA_GH_APP_ID                GitHub App numeric ID
    EAA_GH_APP_PRIVATE_KEY_PEM   PEM content (replace literal \\n with newlines)
    EAA_GH_APP_INSTALLATION_ID   Installation ID for the target org/account
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from integrations.base import Finding, IntegrationResult

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"
_CHECK_NAME = "EAA Compliance"

# Severity → GitHub annotation level
_ANNOTATION_LEVEL: dict[str, str] = {
    "critical": "failure",
    "high":     "failure",
    "medium":   "warning",
    "low":      "notice",
    "info":     "notice",
}


def _make_jwt(app_id: int, private_key_pem: str) -> str:
    """
    Create a signed GitHub App JWT valid for 60 seconds.

    Requires: PyJWT>=2.8.0, cryptography>=42.0.0
    """
    try:
        import jwt  # PyJWT
    except ImportError as exc:
        raise RuntimeError(
            "PyJWT is required for GitHub App auth. "
            "Add PyJWT>=2.8.0 to requirements.txt."
        ) from exc

    now = int(time.time())
    payload = {
        "iat": now - 60,  # issued 60 s ago to account for clock skew
        "exp": now + (10 * 60),  # 10-minute expiry (GitHub max)
        "iss": str(app_id),
    }
    token: str = jwt.encode(payload, private_key_pem, algorithm="RS256")
    return token


async def _get_installation_token(
    client: httpx.AsyncClient,
    app_id: int,
    private_key_pem: str,
    installation_id: int,
) -> str:
    jwt_token = _make_jwt(app_id, private_key_pem)
    url = f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": _ACCEPT,
        "X-GitHub-Api-Version": _API_VERSION,
    }
    response = await client.post(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    token: str = data["token"]
    return token


def _build_annotations(findings: list[Finding]) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for f in findings:
        path = f.metadata.get("file") or f.metadata.get("path")
        if not path:
            continue  # Only annotate findings with file context
        start_line = int(f.metadata.get("line", f.metadata.get("start_line", 1)))
        end_line = int(f.metadata.get("end_line", start_line))
        annotation: dict[str, Any] = {
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
            "annotation_level": _ANNOTATION_LEVEL.get(f.severity, "notice"),
            "message": f"[{f.severity.upper()}] {f.title}",
            "title": f.title,
        }
        if f.remediation:
            annotation["raw_details"] = f.remediation[:65535]
        annotations.append(annotation)
        if len(annotations) >= 50:  # GitHub API limit per request
            break
    return annotations


def _build_summary(findings: list[Finding]) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    if not findings:
        return "No compliance findings detected. All checks passed."

    lines = [
        f"**{len(findings)} finding(s) detected**",
        "",
        "| Severity | Count |",
        "|----------|-------|",
    ]
    for sev in ("critical", "high", "medium", "low", "info"):
        if sev in counts:
            lines.append(f"| {sev.upper()} | {counts[sev]} |")

    lines.extend(["", "Findings by module:", ""])
    modules: dict[str, int] = {}
    for f in findings:
        modules[f.module] = modules.get(f.module, 0) + 1
    for mod, cnt in sorted(modules.items()):
        lines.append(f"- `{mod}`: {cnt}")

    return "\n".join(lines)


class GitHubAppCheckRun:
    """
    Creates GitHub Check Runs for PR compliance gating via GitHub App JWT auth.

    This is not an IntegrationAdapter (it operates on a batch of findings
    per-SHA rather than per-finding). The orchestrator calls run_check() directly.

    Args:
        app_id:           GitHub App numeric ID.
        private_key_pem:  RSA private key PEM string (from .pem file download).
        installation_id:  GitHub App installation ID for the target org.
        dry_run:          Return success without making HTTP calls.
        timeout:          HTTP timeout seconds.
    """

    def __init__(
        self,
        app_id: int,
        private_key_pem: str,
        installation_id: int,
        dry_run: bool = False,
        timeout: float = 20.0,
    ) -> None:
        self.app_id = app_id
        self.private_key_pem = private_key_pem
        self.installation_id = installation_id
        self.dry_run = dry_run
        self.timeout = timeout

    async def run_check(
        self,
        owner: str,
        repo: str,
        sha: str,
        findings: list[Finding],
    ) -> IntegrationResult:
        """
        Create or update a Check Run on the given SHA.

        Args:
            owner:    GitHub org or username.
            repo:     Repository name (no owner prefix).
            sha:      Full commit SHA to attach the check to.
            findings: List of Finding objects from any module.

        Returns:
            IntegrationResult with external_ref = check run HTML URL.
        """
        if self.dry_run:
            return IntegrationResult.dry(
                f"github-check:{owner}/{repo}@{sha[:8]}", adapter="github_app"
            )

        critical_or_high = any(f.severity in ("critical", "high") for f in findings)
        conclusion = "failure" if critical_or_high else "success"
        annotations = _build_annotations(findings)
        summary = _build_summary(findings)

        # GitHub API requires annotations in batches of ≤50; we already capped above.
        output: dict[str, Any] = {
            "title": f"EAA Compliance: {conclusion.upper()}",
            "summary": summary,
        }
        if annotations:
            output["annotations"] = annotations

        payload: dict[str, Any] = {
            "name": _CHECK_NAME,
            "head_sha": sha,
            "status": "completed",
            "conclusion": conclusion,
            "completed_at": _now_iso(),
            "output": output,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                token = await _get_installation_token(
                    client, self.app_id, self.private_key_pem, self.installation_id
                )
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": _ACCEPT,
                    "X-GitHub-Api-Version": _API_VERSION,
                }
                url = f"{_GITHUB_API}/repos/{owner}/{repo}/check-runs"
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:300]
            msg = f"GitHub App HTTP {exc.response.status_code}: {body}"
            logger.error("GitHubAppCheckRun: %s", msg)
            return IntegrationResult.failure(msg, adapter="github_app")
        except Exception as exc:
            logger.error("GitHubAppCheckRun unexpected error: %s", exc)
            return IntegrationResult.failure(str(exc), adapter="github_app")

        html_url = data.get("html_url", "")
        logger.info(
            "GitHubAppCheckRun: created check run %s (conclusion=%s)",
            data.get("id"), conclusion,
        )
        return IntegrationResult.success(html_url, adapter="github_app")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
