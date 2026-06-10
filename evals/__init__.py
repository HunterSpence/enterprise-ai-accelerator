"""
evals/__init__.py
=================

First-party evaluation harness for the Enterprise AI Accelerator.

Three suites:
  - six_r_classification   : golden 6R migration labels for workload descriptions
  - iac_policy_detection   : Terraform/Pulumi snippets vs the real policy engine
  - prompt_injection_redteam : adversarial inputs scored offline via core.guardrails
"""

from __future__ import annotations

__version__ = "0.1.0"
