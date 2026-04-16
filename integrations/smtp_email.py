"""
integrations/smtp_email.py — SMTP email adapter.

Sends an HTML email digest via stdlib smtplib. Jinja2 for template rendering.
Works with Gmail (app password), Mailgun SMTP, AWS SES SMTP, etc.

Env vars:
    EAA_SMTP_HOST      e.g. smtp.gmail.com
    EAA_SMTP_PORT      e.g. 587
    EAA_SMTP_USER      SMTP username / email address
    EAA_SMTP_PASSWORD  SMTP password or app password
    EAA_SMTP_FROM      From address, e.g. alerts@myorg.com
    EAA_SMTP_TO        Comma-separated recipient list
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from jinja2 import Environment

from integrations.base import Finding, IntegrationAdapter, IntegrationResult

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f4f4f4; }
  .container { max-width: 640px; margin: 24px auto; background: #fff;
               border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.1); }
  .header { padding: 20px 24px; background: {{ header_bg }}; color: #fff; }
  .header h1 { margin: 0; font-size: 18px; }
  .header .badge { display: inline-block; background: rgba(255,255,255,.25);
                   border-radius: 4px; padding: 2px 8px; font-size: 12px; margin-top: 4px; }
  .body { padding: 24px; }
  table { width: 100%; border-collapse: collapse; margin: 12px 0; }
  th { text-align: left; background: #f0f0f0; padding: 8px 10px; font-size: 12px; color: #555; }
  td { padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 13px; }
  .remediation { background: #f8f9fa; border-left: 4px solid #007bff;
                  padding: 12px 16px; margin-top: 16px; border-radius: 0 4px 4px 0; }
  .footer { padding: 12px 24px; background: #f8f8f8; font-size: 11px; color: #999;
            border-top: 1px solid #eee; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{{ severity_label }} Finding: {{ title }}</h1>
    <span class="badge">{{ module }}</span>
  </div>
  <div class="body">
    <p>{{ description }}</p>
    <table>
      <tr><th>Field</th><th>Value</th></tr>
      <tr><td><strong>Severity</strong></td><td>{{ severity_label }}</td></tr>
      <tr><td><strong>Module</strong></td><td>{{ module }}</td></tr>
      {% if resource_id %}
      <tr><td><strong>Resource</strong></td><td>{{ resource_id }}</td></tr>
      {% endif %}
      {% if tags %}
      <tr><td><strong>Tags</strong></td><td>{{ tags | join(', ') }}</td></tr>
      {% endif %}
      <tr><td><strong>Finding ID</strong></td><td>{{ finding_id }}</td></tr>
      <tr><td><strong>Detected</strong></td><td>{{ detected_at }}</td></tr>
    </table>
    {% if remediation %}
    <div class="remediation">
      <strong>Remediation</strong>
      <p style="margin:8px 0 0">{{ remediation }}</p>
    </div>
    {% endif %}
  </div>
  <div class="footer">
    Sent by enterprise-ai-accelerator &middot; {{ detected_at }}
  </div>
</div>
</body>
</html>
""".strip()

_HEADER_BG: dict[str, str] = {
    "critical": "#CC0000",
    "high":     "#E03E2D",
    "medium":   "#E07B00",
    "low":      "#A08000",
    "info":     "#555555",
}

_jinja_env = Environment(autoescape=True)
_template = _jinja_env.from_string(_HTML_TEMPLATE)


def _render_html(finding: Finding) -> str:
    return _template.render(
        title=finding.title,
        description=finding.description,
        severity_label=finding.severity.upper(),
        module=finding.module,
        resource_id=finding.resource_id,
        tags=finding.tags,
        remediation=finding.remediation,
        finding_id=finding.id,
        detected_at=finding.created_at.strftime("%Y-%m-%d %H:%M UTC"),
        header_bg=_HEADER_BG.get(finding.severity, "#555555"),
    )


def _send_sync(
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    html_body: str,
) -> None:
    """Blocking SMTP send — runs in a thread executor."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(html_body, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(user, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())


class SmtpEmailAdapter(IntegrationAdapter):
    """
    Sends an HTML email for each finding via SMTP STARTTLS.

    Args:
        host:       SMTP server hostname.
        port:       SMTP port (typically 587 for STARTTLS).
        user:       SMTP auth username.
        password:   SMTP auth password or app password.
        from_addr:  Sender address.
        to_addrs:   List of recipient addresses.
        dry_run:    Return success without sending.
    """

    name = "smtp_email"

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        to_addrs: list[str],
        dry_run: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.dry_run = dry_run

    async def send(self, finding: Finding) -> IntegrationResult:
        if self.dry_run:
            return IntegrationResult.dry(f"smtp:{finding.id}", adapter=self.name)

        subject = f"[EAA] [{finding.severity.upper()}] {finding.title}"
        html_body = _render_html(finding)

        fn = partial(
            _send_sync,
            self.host,
            self.port,
            self.user,
            self.password,
            self.from_addr,
            self.to_addrs,
            subject,
            html_body,
        )

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, fn)
        except smtplib.SMTPException as exc:
            msg = f"SMTP error: {exc}"
            logger.error("SmtpEmailAdapter: %s", msg)
            return IntegrationResult.failure(msg, adapter=self.name)
        except Exception as exc:
            logger.error("SmtpEmailAdapter unexpected error: %s", exc)
            return IntegrationResult.failure(str(exc), adapter=self.name)

        logger.info("SmtpEmailAdapter: sent to %s", self.to_addrs)
        return IntegrationResult.success(
            f"smtp:{','.join(self.to_addrs)}", adapter=self.name
        )
