# integrations — Notification and Ticketing Hub

Routes platform findings to external systems via a pluggable adapter pattern. All adapters use free-tier / webhook-based endpoints. A `FindingRouter` maps finding type and severity to the correct adapter(s); `WebhookDispatcher` handles retry, circuit-breaking, and rate-limiting.

---

## Supported Adapters

| Adapter | Class | Transport | Auth |
|---|---|---|---|
| Slack | `SlackAdapter` | Incoming Webhook | Webhook URL |
| Jira Cloud | `JiraAdapter` | REST API | API token + email |
| ServiceNow | `ServiceNowAdapter` | REST API | Username + password |
| GitHub Issues | `GitHubIssueAdapter` | REST API | PAT or GitHub App token |
| GitHub App (PR check-runs) | `GitHubAppAdapter` | REST API | GitHub App private key + App ID |
| Microsoft Teams | `TeamsAdapter` | Incoming Webhook | Webhook URL |
| SMTP Email | `SMTPAdapter` | SMTP | Host + credentials |
| PagerDuty | `PagerDutyAdapter` | Events API v2 | Routing key |

---

## Routing Rules

`FindingRouter` applies rules in order. First match wins.

```python
# integrations/config.py (example)
ROUTING_RULES = [
    # CRITICAL severity → PagerDuty + Slack
    {"severity": "CRITICAL", "adapters": ["pagerduty", "slack"]},
    # HIGH IaC security findings → Jira + GitHub Issues
    {"severity": "HIGH", "source": "iac_security", "adapters": ["jira", "github_issue"]},
    # Compliance findings → ServiceNow + Slack
    {"source": "policy_guard", "adapters": ["servicenow", "slack"]},
    # Default → Slack only
    {"adapters": ["slack"]},
]
```

Rules support matching on: `severity` (CRITICAL/HIGH/MEDIUM/LOW), `source` (module name), `finding_type` (string match), `tags` (list intersection).

---

## Retry and Circuit-Breaker Semantics

`WebhookDispatcher` wraps all adapter calls with:

- **Retry:** exponential backoff, 3 attempts, jitter. Retries on HTTP 429, 5xx, and connection errors.
- **Circuit breaker:** opens after 5 consecutive failures. Half-open after 60 seconds. Resets on first success.
- **Rate limit:** per-adapter configurable (e.g. Slack free tier = 1 req/sec). Requests are queued rather than dropped.
- **Timeout:** 10 seconds per request (configurable per adapter).

Failed deliveries after all retries are written to a dead-letter log at `integrations/dead_letter.jsonl`.

---

## Env Vars by Adapter

### Slack
```
SLACK_WEBHOOK_URL
```

### Jira
```
JIRA_URL             # e.g. https://yourorg.atlassian.net
JIRA_USER_EMAIL
JIRA_API_TOKEN
JIRA_PROJECT_KEY
```

### ServiceNow
```
SERVICENOW_INSTANCE  # e.g. dev12345
SERVICENOW_USERNAME
SERVICENOW_PASSWORD
```

### GitHub Issues
```
GITHUB_TOKEN         # PAT with repo scope
GITHUB_OWNER
GITHUB_REPO
```

### GitHub App (PR check-runs + annotations)
```
GITHUB_APP_ID
GITHUB_APP_PRIVATE_KEY_PATH   # path to .pem file
GITHUB_APP_INSTALLATION_ID
```

The `GitHubAppAdapter` creates check-runs on pull requests and adds inline annotations for IaC policy violations and CVE findings. This integrates directly with GitHub's PR interface — reviewers see findings inline without leaving GitHub.

### Microsoft Teams
```
TEAMS_WEBHOOK_URL
```

### SMTP
```
SMTP_HOST
SMTP_PORT            # default 587
SMTP_USER
SMTP_PASSWORD
SMTP_FROM
SMTP_TO              # comma-separated recipient list
```

### PagerDuty
```
PAGERDUTY_ROUTING_KEY   # Events API v2 integration key
```

---

## Dry-Run Mode

All adapters support `dry_run=True`. In dry-run mode, payloads are serialized and logged but no outbound HTTP requests are made. Useful for testing routing rules without triggering alerts.

```python
from integrations.dispatcher import WebhookDispatcher

dispatcher = WebhookDispatcher(dry_run=True)
dispatcher.dispatch(finding)
# Output: [DRY RUN] Would send to slack: {...payload...}
```

---

## Adding a New Adapter

1. Create `integrations/<provider>.py`
2. Inherit from `integrations.base.BaseAdapter`
3. Implement `send(finding: Finding) -> bool`
4. Register in `integrations/config.py` adapter registry

```python
# integrations/myservice.py
from integrations.base import BaseAdapter, Finding

class MyServiceAdapter(BaseAdapter):
    def send(self, finding: Finding) -> bool:
        payload = self._build_payload(finding)
        resp = self.session.post(self.config["webhook_url"], json=payload, timeout=10)
        return resp.status_code == 200
```

---

## Programmatic Usage

```python
from integrations.dispatcher import WebhookDispatcher
from integrations.base import Finding

dispatcher = WebhookDispatcher()

finding = Finding(
    id="iac-001",
    severity="HIGH",
    source="iac_security",
    title="S3 bucket public read enabled",
    description="aws_s3_bucket.data has ACL=public-read (CIS AWS 2.1.5)",
    remediation="Set acl = private and enable bucket policy with explicit deny",
)

results = dispatcher.dispatch(finding)
# routes to Jira + GitHub Issues per routing rules
```
