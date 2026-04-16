"""
integrations — Enterprise integration layer for enterprise-ai-accelerator.

Re-exports all public adapter classes, Finding, FindingRouter,
WebhookDispatcher, and IntegrationsConfig for convenience.

Quick start::

    from integrations import IntegrationsConfig, Finding

    config = IntegrationsConfig.from_env()

    finding = Finding(
        title="Overly permissive IAM policy",
        description="IAM role grants s3:* on all resources.",
        severity="high",
        module="cloud_iq",
        resource_id="arn:aws:iam::123456789012:role/my-role",
        remediation="Scope policy to specific S3 buckets required by the workload.",
        tags=["iam", "s3", "least-privilege"],
    )

    results = await config.dispatcher.dispatch(finding)

    # PR compliance check (GitHub App):
    if config.github_app:
        result = await config.github_app.run_check(
            owner="myorg", repo="my-repo", sha="abc123...", findings=[finding]
        )
"""

from integrations.base import (
    Finding,
    FindingRouter,
    IntegrationAdapter,
    IntegrationResult,
    RoutingRule,
)
from integrations.config import IntegrationsConfig
from integrations.dispatcher import WebhookDispatcher
from integrations.github_app import GitHubAppCheckRun
from integrations.github_issue import GitHubIssueAdapter
from integrations.jira import JiraAdapter
from integrations.pagerduty import PagerDutyEventsAdapter
from integrations.servicenow import ServiceNowAdapter
from integrations.slack import SlackWebhookAdapter
from integrations.smtp_email import SmtpEmailAdapter
from integrations.teams import TeamsWebhookAdapter

__all__ = [
    # Core primitives
    "Finding",
    "IntegrationAdapter",
    "IntegrationResult",
    "RoutingRule",
    "FindingRouter",
    # Dispatcher
    "WebhookDispatcher",
    # Config (env-driven factory)
    "IntegrationsConfig",
    # Adapters
    "SlackWebhookAdapter",
    "JiraAdapter",
    "ServiceNowAdapter",
    "GitHubIssueAdapter",
    "GitHubAppCheckRun",
    "TeamsWebhookAdapter",
    "SmtpEmailAdapter",
    "PagerDutyEventsAdapter",
]
