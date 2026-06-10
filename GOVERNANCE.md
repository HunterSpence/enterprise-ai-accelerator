# Governance — Enterprise AI Accelerator

## Maintainer Model

**Solo maintainer.** Hunter Spence (@HunterSpence) is the sole decision-maker for this project. There is no steering committee, foundation membership, or corporate sponsor. All release, roadmap, and architecture decisions are made by the maintainer.

## Decision Process

1. **Bug fixes and documentation** — merged by maintainer without public process.
2. **Non-breaking feature additions** — maintainer reviews open issues + community feedback, then decides unilaterally.
3. **Breaking API changes** — documented in CHANGELOG.md; a deprecation notice is added to the relevant module's docstring at least one minor version before removal.
4. **Dependency additions** — must be OSS (Apache 2.0 / MIT / BSD); no proprietary runtime dependencies introduced without explicit notice in the release notes.

## Release Cadence

There is no fixed release schedule. Releases are driven by meaningful capability additions, security patches, or model-refresh obligations (e.g., upstream API deprecations). Patch releases (x.x.N) are issued for security fixes without waiting for feature accumulation.

Version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Security Report Handling

See [SECURITY.md](SECURITY.md) for the full vulnerability disclosure policy. In brief: report privately via the GitHub Security Advisory form; maintainer acknowledges within 72 hours; critical issues patched within 14 days.

Security reports are never publicly disclosed until a patch is available or 90 days have elapsed, whichever comes first.

## Bus-Factor Mitigation

This project has a bus factor of 1. The following measures reduce the risk of abandonment blocking adopters:

| Measure | Details |
|---------|---------|
| **MIT License** | Any organization may fork, modify, and redistribute without restriction. No vendor lock-in. |
| **Documented architecture** | `docs/PLATFORM_ARCHITECTURE.md` describes module boundaries, data flows, and model-routing logic in sufficient detail to allow an informed engineer to take over maintenance. |
| **>50 offline tests** | `tests/` covers all core modules with no external service dependencies (Anthropic API calls are mocked). CI passes without credentials. |
| **No proprietary dependencies** | All 15+ runtime dependencies are Apache 2.0 / MIT. The Anthropic SDK is the only required external API; it can be swapped for any OpenAI-compatible endpoint with a one-file change to `core/models.py`. |
| **Public roadmap** | `ROADMAP.md` documents planned directions so the community can anticipate and participate. |
| **Public governance** | This file (`GOVERNANCE.md`) is checked into the repository so governance terms cannot be changed without a visible commit. |

## Contribution Acceptance Criteria

Contributions are welcome via pull request. A PR will be accepted when it meets **all** of the following:

1. **Tests pass.** All existing tests pass; new functionality includes tests that run offline (no live API calls).
2. **No new proprietary dependencies.** Any new dependency must be OSS (Apache 2.0, MIT, or BSD).
3. **Changelog entry.** A line describing the change is added to the `[Unreleased]` section of `CHANGELOG.md`.
4. **Consistent style.** Code follows the existing module structure; new modules include a `README.md` in the module directory.
5. **No AI-generated hallucinations in regulatory claims.** Any compliance claim (EU AI Act article numbers, NIST control identifiers, HIPAA citations) must include a source reference in the PR description.

The maintainer may decline PRs that add significant maintenance surface area without corresponding value to the core use case (enterprise AI governance + FinOps).

## Conflict of Interest

The maintainer has no financial relationship with Anthropic. The platform uses Anthropic APIs, but no affiliate or referral arrangement exists. The platform is model-agnostic at the transport layer; Bedrock/Vertex routing is on the roadmap.

## Amendment

This document may be updated by the maintainer at any time. Material changes (e.g., license change, introduction of a corporate sponsor, decision-making body changes) will be noted in the commit message and CHANGELOG.md.
