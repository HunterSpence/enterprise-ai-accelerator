"""
integrations/config.py — Environment-driven configuration.

Reads env vars, constructs all adapters that are fully configured,
and returns a wired FindingRouter + WebhookDispatcher.

Missing env vars = adapter silently absent (never an error).

Usage::

    from integrations.config import IntegrationsConfig

    config = IntegrationsConfig.from_env()
    dispatcher = config.dispatcher
    results = await dispatcher.dispatch(finding)

    # Or for PR compliance checks:
    if config.github_app:
        result = await config.github_app.run_check(owner, repo, sha, findings)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from integrations.base import FindingRouter, IntegrationAdapter, RoutingRule
from integrations.dispatcher import WebhookDispatcher

logger = logging.getLogger(__name__)


def _env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def _env_required(keys: list[str]) -> bool:
    """Return True only if ALL given env vars are set and non-empty."""
    return all(bool(os.environ.get(k)) for k in keys)


def _env_list(key: str) -> list[str]:
    """Parse comma-separated env var into a list of stripped strings."""
    val = os.environ.get(key, "")
    return [v.strip() for v in val.split(",") if v.strip()]


@dataclass
class IntegrationsConfig:
    """
    Fully-wired integration configuration built from environment variables.

    Attributes:
        adapters:     Dict of configured adapters keyed by name.
        router:       FindingRouter with default routing rules.
        dispatcher:   WebhookDispatcher wrapping the router.
        github_app:   GitHubAppCheckRun instance if GH App env vars are set, else None.
        dry_run:      Whether all adapters are in dry_run mode.
    """

    adapters: dict[str, IntegrationAdapter] = field(default_factory=dict)
    router: FindingRouter = field(init=False)
    dispatcher: WebhookDispatcher = field(init=False)
    github_app: object | None = None  # GitHubAppCheckRun | None
    dry_run: bool = False

    def __post_init__(self) -> None:
        rules = self._default_rules()
        self.router = FindingRouter(rules=rules, adapters=self.adapters)
        self.dispatcher = WebhookDispatcher(router=self.router)

    def _default_rules(self) -> list[RoutingRule]:
        """
        Default routing rules:
        - critical + high → all adapters that are configured
        - medium          → slack + jira + teams + smtp_email (no paging)
        - low + info      → jira + github_issue only
        """
        all_names = list(self.adapters.keys())
        # Exclude github_issue + teams from paging-class destinations for lower severities
        non_paging = [n for n in all_names if n not in ("pagerduty",)]
        low_info = [n for n in all_names if n in ("jira", "github_issue", "smtp_email")]

        rules = []
        if all_names:
            rules.append(RoutingRule(
                match_severity={"critical", "high"},
                adapters=all_names,
            ))
        if non_paging:
            rules.append(RoutingRule(
                match_severity={"medium"},
                adapters=non_paging,
            ))
        if low_info:
            rules.append(RoutingRule(
                match_severity={"low", "info"},
                adapters=low_info,
            ))
        return rules

    @classmethod
    def from_env(cls, dry_run: bool | None = None) -> IntegrationsConfig:
        """
        Construct from environment variables. Safe to call at startup — any
        unconfigured adapter is simply absent.

        Set EAA_DRY_RUN=true to force dry_run on all adapters.
        """
        _dry = (
            dry_run
            if dry_run is not None
            else os.environ.get("EAA_DRY_RUN", "").lower() in ("1", "true", "yes")
        )

        adapters: dict[str, IntegrationAdapter] = {}

        # ------------------------------------------------------------------ Slack
        if _env_required(["EAA_SLACK_WEBHOOK_URL"]):
            from integrations.slack import SlackWebhookAdapter
            adapters["slack"] = SlackWebhookAdapter(
                webhook_url=os.environ["EAA_SLACK_WEBHOOK_URL"],
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: slack adapter configured")

        # ------------------------------------------------------------------ Jira
        if _env_required(["EAA_JIRA_BASE_URL", "EAA_JIRA_EMAIL",
                           "EAA_JIRA_API_TOKEN", "EAA_JIRA_PROJECT"]):
            from integrations.jira import JiraAdapter
            adapters["jira"] = JiraAdapter(
                base_url=os.environ["EAA_JIRA_BASE_URL"],
                email=os.environ["EAA_JIRA_EMAIL"],
                api_token=os.environ["EAA_JIRA_API_TOKEN"],
                project_key=os.environ["EAA_JIRA_PROJECT"],
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: jira adapter configured")

        # ------------------------------------------------------------ ServiceNow
        if _env_required(["EAA_SNOW_INSTANCE_URL", "EAA_SNOW_USER", "EAA_SNOW_PASSWORD"]):
            from integrations.servicenow import ServiceNowAdapter
            adapters["servicenow"] = ServiceNowAdapter(
                instance_url=os.environ["EAA_SNOW_INSTANCE_URL"],
                user=os.environ["EAA_SNOW_USER"],
                password=os.environ["EAA_SNOW_PASSWORD"],
                assignment_group=_env("EAA_SNOW_ASSIGNMENT_GROUP"),
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: servicenow adapter configured")

        # --------------------------------------------------------------- GitHub Issues
        if _env_required(["EAA_GITHUB_ISSUE_REPO", "EAA_GITHUB_ISSUE_TOKEN"]):
            from integrations.github_issue import GitHubIssueAdapter
            adapters["github_issue"] = GitHubIssueAdapter(
                repo=os.environ["EAA_GITHUB_ISSUE_REPO"],
                token=os.environ["EAA_GITHUB_ISSUE_TOKEN"],
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: github_issue adapter configured")

        # ------------------------------------------------------------------ Teams
        if _env_required(["EAA_TEAMS_WEBHOOK_URL"]):
            from integrations.teams import TeamsWebhookAdapter
            adapters["teams"] = TeamsWebhookAdapter(
                webhook_url=os.environ["EAA_TEAMS_WEBHOOK_URL"],
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: teams adapter configured")

        # ----------------------------------------------------------------- SMTP
        if _env_required(["EAA_SMTP_HOST", "EAA_SMTP_USER", "EAA_SMTP_PASSWORD",
                           "EAA_SMTP_FROM", "EAA_SMTP_TO"]):
            from integrations.smtp_email import SmtpEmailAdapter
            adapters["smtp_email"] = SmtpEmailAdapter(
                host=os.environ["EAA_SMTP_HOST"],
                port=int(os.environ.get("EAA_SMTP_PORT", "587")),
                user=os.environ["EAA_SMTP_USER"],
                password=os.environ["EAA_SMTP_PASSWORD"],
                from_addr=os.environ["EAA_SMTP_FROM"],
                to_addrs=_env_list("EAA_SMTP_TO"),
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: smtp_email adapter configured")

        # --------------------------------------------------------------- PagerDuty
        if _env_required(["EAA_PAGERDUTY_ROUTING_KEY"]):
            from integrations.pagerduty import PagerDutyEventsAdapter
            fire_on_raw = _env("EAA_PAGERDUTY_FIRE_ON", "critical")
            fire_on = {s.strip() for s in fire_on_raw.split(",") if s.strip()}
            adapters["pagerduty"] = PagerDutyEventsAdapter(
                routing_key=os.environ["EAA_PAGERDUTY_ROUTING_KEY"],
                fire_on=fire_on,
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: pagerduty adapter configured (fire_on=%s)", fire_on)

        # ---------------------------------------------------------------- GitHub App (Check Runs)
        github_app = None
        if _env_required(["EAA_GH_APP_ID", "EAA_GH_APP_PRIVATE_KEY_PEM",
                           "EAA_GH_APP_INSTALLATION_ID"]):
            from integrations.github_app import GitHubAppCheckRun
            pem = os.environ["EAA_GH_APP_PRIVATE_KEY_PEM"].replace("\\n", "\n")
            github_app = GitHubAppCheckRun(
                app_id=int(os.environ["EAA_GH_APP_ID"]),
                private_key_pem=pem,
                installation_id=int(os.environ["EAA_GH_APP_INSTALLATION_ID"]),
                dry_run=_dry,
            )
            logger.info("IntegrationsConfig: github_app (check runs) configured")

        config = cls(adapters=adapters, dry_run=_dry)
        config.github_app = github_app

        if not adapters and not github_app:
            logger.info(
                "IntegrationsConfig: no adapters configured "
                "(set EAA_SLACK_WEBHOOK_URL etc. to enable)"
            )

        return config
