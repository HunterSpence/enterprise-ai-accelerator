# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x (current) | Yes |
| 0.2.x | Security fixes only |
| < 0.2.0 | No |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security vulnerabilities by emailing:

**hspence21190@gmail.com**

Include in your report:
- A description of the vulnerability and its potential impact
- The affected module(s) and version(s)
- Steps to reproduce, including any proof-of-concept code
- Any suggested remediation, if you have one

### Response SLA

| Milestone | Timeline |
|-----------|----------|
| Acknowledgment | Within 72 hours of receipt |
| Severity assessment | Within 5 business days |
| Patch release (critical) | Within 14 days of confirmation |
| Patch release (high) | Within 30 days of confirmation |
| Patch release (medium/low) | Next scheduled release |

## Coordinated Disclosure

This project follows coordinated disclosure. We ask that you:

1. Give us reasonable time to investigate and produce a fix before public
   disclosure (90 days maximum for critical issues; we aim for 14 days).
2. Avoid accessing, modifying, or deleting data that belongs to others.
3. Not exploit the vulnerability beyond what is necessary to demonstrate impact.

We will:
1. Acknowledge your report within 72 hours.
2. Keep you informed of our progress toward a fix.
3. Credit you in the security advisory if you wish, once the issue is resolved.

## Scope

The following are in scope for security reports:

- Vulnerabilities in any Python module under `core/`, `ai_audit_trail/`,
  `migration_scout/`, `app_portfolio/`, `iac_security/`, `finops_intelligence/`,
  `policy_guard/`, `compliance_citations/`, `executive_chat/`, `agent_ops/`,
  `integrations/`, `observability/`
- The MCP server (`mcp_server.py`) and its tool implementations
- The SHA-256 Merkle audit chain tamper-evidence guarantees (`ai_audit_trail/chain.py`)
- Prompt injection vulnerabilities affecting AI decision integrity
- Insecure defaults in the docker-compose deployment configuration

The following are out of scope:

- Vulnerabilities in third-party dependencies (report to the upstream maintainer;
  we will update our dependency pin once a fix is available)
- Denial-of-service via resource exhaustion on self-hosted deployments
  (self-hosted operators control their own resource limits)
- Social engineering attacks

## Security Notes for Operators

- The platform requires an `ANTHROPIC_API_KEY` in the environment. Never commit
  this key to source control. Use `.env` files excluded by `.gitignore`.
- The audit chain database (`~/.eaa_cache/` by default) stores SHA-256 hashes of
  AI prompts and responses. If `store_plaintext=True` is set on any `LogEntry`,
  prompt content is stored in plaintext. Treat the database file as sensitive.
- The MCP server (`mcp_server.py`) exposes all platform tools to any MCP client.
  Do not expose the MCP server port on a public network interface without
  authentication.
- Cloud adapter credentials (AWS IAM keys, Azure service principals, GCP service
  accounts) should have read-only permissions scoped to the minimum required for
  discovery. The platform does not write to cloud resources.
