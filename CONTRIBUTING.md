# Contributing

Thank you for your interest in contributing to enterprise-ai-accelerator.

## Local Development

Requirements: Python 3.11+

```bash
git clone https://github.com/HunterSpence/enterprise-ai-accelerator.git
cd enterprise-ai-accelerator
pip install -r requirements.txt
pytest
```

Run a specific test file:

```bash
pytest tests/test_audit_trail.py -v
```

## Pull Request Process

1. Fork the repository and create a feature branch from `main`.
2. Write tests for any new behavior. All tests must pass before review.
3. Ensure your branch is up to date with `main` before opening a PR.
4. Open a pull request with a clear description of the change and its motivation.
5. Address any review feedback promptly.

PRs that reduce test coverage will not be merged.

## Code Style

- All public functions and classes must have docstrings.
- Use type hints throughout. Untyped public APIs will be rejected.
- Follow PEP 8. Run `ruff check .` before submitting.
- Keep functions focused. Prefer small, composable units over monolithic helpers.

## Issue Reporting

Before opening an issue:

- Search existing issues to avoid duplicates.
- Include the Python version, OS, and full traceback if reporting a bug.
- For feature requests, describe the use case and expected behavior.

Label your issue appropriately: `bug`, `enhancement`, `documentation`, or `compliance`.

## EU AI Act Compliance

This project implements logging and audit trail logic under EU AI Act Article 12
and related obligations. Any contribution that touches compliance-critical paths
(audit trail generation, SARIF output, OTEL spans, risk classification) requires
a detailed description of the regulatory impact and will receive additional
scrutiny during review. When in doubt, open an issue first before writing code.

## Contact

For questions not suited to a GitHub issue: hunter@vantaweb.io
