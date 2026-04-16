"""
executive_chat — CTO / CIO unified chat over all six modules
============================================================

Gives executives a single conversational surface on top of every module's
output, with Opus 4.7's 1M-token context window so the entire enterprise
analysis (architecture findings, migration plan, compliance violations,
FinOps anomalies, AIAuditTrail entries) can be loaded into system context
and cached.

Because the compiled briefing is large (~50k-200k tokens), we rely on:
  - Opus 4.7 1M context (no chunking)
  - 1-hour prompt caching on the briefing (``cache_control: {"type": "1h"}``)
    so follow-up questions cost only the delta tokens
  - Forced tool-use structured answers so the UI can render citations,
    confidence, and next-best-action
"""

from executive_chat.chat import (
    ExecutiveChat,
    BriefingBundle,
    ExecutiveAnswer,
)

__all__ = ["ExecutiveChat", "BriefingBundle", "ExecutiveAnswer"]
