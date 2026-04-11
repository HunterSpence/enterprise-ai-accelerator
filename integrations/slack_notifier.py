"""
Slack Integration — Send analysis findings to Slack channels.

Usage:
    from integrations.slack_notifier import SlackNotifier
    notifier = SlackNotifier(webhook_url=os.getenv("SLACK_WEBHOOK_URL"))
    notifier.send_cost_alert(cost_result, channel="#cloud-ops")
"""

import json
import os
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class SlackNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    
    def send_cost_alert(self, cost_result, channel: str = "#cloud-ops") -> bool:
        """Send cost analysis summary to Slack."""
        if not self.webhook_url or not REQUESTS_AVAILABLE:
            return False
        
        payload = {
            "channel": channel,
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Cloud Cost Analysis Complete"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Monthly Waste Identified:*\n${cost_result.total_waste_monthly:,.0f}"},
                        {"type": "mrkdwn", "text": f"*Annual Savings Potential:*\n${cost_result.total_savings_annual:,.0f}"},
                        {"type": "mrkdwn", "text": f"*Savings %:*\n{cost_result.savings_percentage:.1f}%"},
                        {"type": "mrkdwn", "text": f"*Quick Wins Available:*\n{len(cost_result.quick_wins)}"},
                    ]
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"_{cost_result.financial_narrative}_"}
                }
            ]
        }
        
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False
    
    def send_compliance_alert(self, compliance_result, channel: str = "#security") -> bool:
        """Send compliance violation summary to Slack."""
        if not self.webhook_url or not REQUESTS_AVAILABLE:
            return False
        
        critical_count = len(compliance_result.critical_violations)
        color = "danger" if critical_count > 0 else "warning"
        
        payload = {
            "channel": channel,
            "attachments": [{
                "color": color,
                "title": f"Compliance Scan: {compliance_result.compliance_score}/100",
                "text": compliance_result.executive_summary,
                "fields": [
                    {"title": "Critical Violations", "value": str(critical_count), "short": True},
                    {"title": "Frameworks", "value": ", ".join(compliance_result.frameworks_checked), "short": True},
                    {"title": "Remediation Est.", "value": f"{compliance_result.estimated_remediation_days} days", "short": True},
                ]
            }]
        }
        
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False
