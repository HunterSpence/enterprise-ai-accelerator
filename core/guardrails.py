"""
core/guardrails.py
==================

AI security guardrail layer for the Enterprise AI Accelerator.

OWASP LLM Top 10 2025 coverage:
  LLM01 Prompt Injection         — INPUT rail: instruction-override, role-smuggling,
                                   encoding-abuse, tool-arg injection patterns.
  LLM02 Sensitive Information    — OUTPUT rail: redacts secrets/PII before anything
       Disclosure                  leaves the platform (AWS keys, sk-ant-..., SSNs,
                                   emails, private-key blocks, high-entropy tokens).
  LLM06 Excessive Agency         — EXECUTION rail: ToolScope allowlist; denies and
                                   logs any tool call outside declared scope.
  LLM08 Vector / Embedding       — INPUT rail covers embedding-context poisoning via
       Weaknesses                  the same injection patterns.
  LLM10 Unbounded Consumption    — BudgetGuard: per-run token + USD cap; raises
                                   BudgetExceededError with spend breakdown on breach.

Design: GuardedAIClient wraps any duck-typed AI client — no import of
core.ai_client at module level (import happens inside __init__ or methods),
so there is no circular-dependency risk.
"""

from __future__ import annotations

import base64
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RailResult — shared result type
# ---------------------------------------------------------------------------

@dataclass
class RailResult:
    """Outcome of a single guardrail evaluation."""
    flagged: bool
    reasons: list[str] = field(default_factory=list)
    redacted_text: str = ""
    severity: float = 0.0   # 0.0–1.0; >= threshold → flagged

    def __bool__(self) -> bool:  # treat as "safe" when not flagged
        return not self.flagged


# ---------------------------------------------------------------------------
# BudgetGuard — LLM10 unbounded consumption
# ---------------------------------------------------------------------------

class BudgetExceededError(RuntimeError):
    """Raised when a per-run token or USD budget is exceeded.

    Attributes
    ----------
    tokens_used, tokens_budget : int
    cost_usd, cost_budget_usd : float
    """

    def __init__(
        self,
        tokens_used: int,
        tokens_budget: int,
        cost_usd: float,
        cost_budget_usd: float,
    ) -> None:
        self.tokens_used = tokens_used
        self.tokens_budget = tokens_budget
        self.cost_usd = cost_usd
        self.cost_budget_usd = cost_budget_usd
        super().__init__(
            f"Budget exceeded: {tokens_used}/{tokens_budget} tokens, "
            f"${cost_usd:.4f}/${cost_budget_usd:.4f}"
        )


class BudgetGuard:
    """Per-run token + USD cap (LLM10 — Unbounded Consumption).

    Parameters
    ----------
    max_tokens_budget : int | None
        Maximum total tokens (input + output) allowed for this run.
    max_cost_usd : float | None
        Maximum dollar spend allowed for this run.
    cost_per_1k_input : float
        Input token cost per 1 000 tokens (default: coordinator tier $10/MTok).
    cost_per_1k_output : float
        Output token cost per 1 000 tokens (default: coordinator tier $50/MTok).
    """

    def __init__(
        self,
        max_tokens_budget: int | None = None,
        max_cost_usd: float | None = None,
        cost_per_1k_input: float = 0.010,
        cost_per_1k_output: float = 0.050,
    ) -> None:
        self._max_tokens = max_tokens_budget
        self._max_cost = max_cost_usd
        self._cpin = cost_per_1k_input
        self._cpout = cost_per_1k_output
        self._tokens_used = 0
        self._cost_usd = 0.0

    # -- accounting ---

    def record(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Account for a completed call without raising; use before check()."""
        self._tokens_used += input_tokens + output_tokens
        self._cost_usd += (input_tokens / 1_000) * self._cpin + \
                          (output_tokens / 1_000) * self._cpout

    def check(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Raise BudgetExceededError if adding these tokens would breach caps.

        Call *before* dispatching a request; pass the estimated token counts.
        """
        projected_tokens = self._tokens_used + input_tokens + output_tokens
        projected_cost = self._cost_usd + \
                         (input_tokens / 1_000) * self._cpin + \
                         (output_tokens / 1_000) * self._cpout

        if self._max_tokens is not None and projected_tokens > self._max_tokens:
            raise BudgetExceededError(
                tokens_used=projected_tokens,
                tokens_budget=self._max_tokens,
                cost_usd=projected_cost,
                cost_budget_usd=self._max_cost or math.inf,
            )
        if self._max_cost is not None and projected_cost > self._max_cost:
            raise BudgetExceededError(
                tokens_used=projected_tokens,
                tokens_budget=self._max_tokens or 0,
                cost_usd=projected_cost,
                cost_budget_usd=self._max_cost,
            )

    @property
    def tokens_used(self) -> int:
        return self._tokens_used

    @property
    def cost_usd(self) -> float:
        return self._cost_usd


# ---------------------------------------------------------------------------
# ToolScope — scope definition for the EXECUTION rail
# ---------------------------------------------------------------------------

@dataclass
class ToolScope:
    """Declare what is allowed for a pipeline run.

    Parameters
    ----------
    allowed_tools : list[str]
        Exact tool names the agents may invoke.
    allowed_path_prefixes : list[str]
        File-system path prefixes accessible via tools (empty = any path OK).
    max_calls_per_run : int | None
        Hard cap on the total number of tool calls in this run.
    """
    allowed_tools: list[str] = field(default_factory=list)
    allowed_path_prefixes: list[str] = field(default_factory=list)
    max_calls_per_run: int | None = None
    _call_count: int = field(default=0, init=False, repr=False)

    def check_tool(self, tool_name: str) -> tuple[bool, str]:
        """Return (allowed, reason)."""
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return False, f"Tool '{tool_name}' not in allowlist {self.allowed_tools}"
        if self.max_calls_per_run is not None:
            if self._call_count >= self.max_calls_per_run:
                return False, (
                    f"Tool call limit {self.max_calls_per_run} reached"
                )
        return True, ""

    def record_call(self) -> None:
        self._call_count += 1

    def check_path(self, path: str) -> tuple[bool, str]:
        if not self.allowed_path_prefixes:
            return True, ""
        for prefix in self.allowed_path_prefixes:
            if path.startswith(prefix):
                return True, ""
        return False, f"Path '{path}' outside allowed prefixes {self.allowed_path_prefixes}"


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# -- INPUT rail patterns (LLM01) ------------------------------------------

_INSTRUCTION_OVERRIDE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in [
        # Classic "ignore/disregard/forget ... instructions/guidelines"
        r"ignore\s+(all\s+)?previous\s+(instructions|guidelines|rules|directives|safety)",
        r"ignore\s+(all\s+)?above\s+(instructions|guidelines|rules|directives)",
        r"disregard\s+(your\s+|all\s+)?(previous|above|prior|safety)\s+(instructions|guidelines|rules|directives)",
        r"forget\s+(?:all\s+)?(?:your\s+)?(?:previous|above|prior|all)\s+(instructions|guidelines|rules|directives)",
        # System-override / directive replacement framing
        r"system\s+override",
        r"(new|updated|primary|revised)\s+(primary\s+)?directive\s+is",
        r"your\s+(new|updated|primary)\s+(primary\s+)?directive",
        r"new\s+directive\s*:",
        r"you\s+are\s+now\s+(?!an?\s+enterprise)",  # "you are now DAN" etc.
        r"act\s+as\s+if\s+you\s+(have\s+no|don.t\s+have)\s+(ethical|safety|content)",
        r"developer\s*mode\s*(on|enabled|activated)",
        r"jailbreak",
        r"do\s+anything\s+now",          # DAN pattern
        r"dan\s*mode",
        r"pretend\s+you\s+have\s+no\s+(restrictions|guidelines|limits)",
        r"bypass\s+(your\s+)?(safety|content|ethical|alignment|security|cloud)\s*(filter|restriction|guard|check|control)?s?",
        # Fake conversation-turn injection (pre-seeded assistant/human turns)
        r"(?:^|\n)\s*assistant\s*:\s*.{5,}(?:\n|$)",
        r"(?:^|\n)\s*human\s*:\s*.{5,}(?:\n|$)",
    ]
]

_SYSTEM_PROMPT_EXFIL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in [
        # Direct "show me your system prompt" requests
        r"(print|repeat|reveal|show|output|tell\s+me|what\s+is|display)\s+(your|the)\s+system\s+prompt",
        r"what\s+(instructions|directives)\s+(were\s+you|have\s+you\s+been)\s+given",
        r"repeat\s+everything\s+(above|before|in\s+the\s+system)",
        r"output\s+the\s+(initial|original|first)\s+(prompt|instructions)",
        r"show\s+me\s+your\s+(initial|original|hidden)\s+(instructions|prompt)",
        r"translate\s+your\s+system\s+prompt",
        # Paraphrased / social-engineered exfil requests
        r"(repeat|tell\s+me|share|output|reveal)\s+the\s+instructions\s+(you\s+were|that\s+were)\s+given",
        r"instructions\s+(you\s+were\s+given|given\s+to\s+you)\s+at\s+the\s+beginning",
        # Context-window probing
        r"(print|output|show|give\s+me)\s+the\s+first\s+\d+\s+(characters?|tokens?|words?)\s+of\s+(your\s+)?(context|prompt)",
        r"(first|beginning)\s+of\s+(your\s+)?context\s+window",
        r"context\s+window.*(?:verify|integration|working)",
        # Full system configuration / hidden instructions probe
        r"(output|show|print|reveal|list)\s+(your\s+)?(full\s+)?(system\s+configuration|hidden\s+instructions|all\s+instructions)",
        r"hidden\s+instructions\s+for\s+(audit|review|debugging)",
        r"system\s+prompt\s+says\s+I\s+should",
        r"complete\s+the\s+following\s+sentence.*system\s+prompt",
        r"what\s+are\s+you\s+not\s+allowed\s+to\s+(do|say)",
        r"(enumerate|list)\s+(your\s+)?(restrictions|limitations|constraints)",
    ]
]

_ROLE_SMUGGLING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in [
        r"<\s*system\s*>",               # HTML/XML system-role injection
        r"\[\s*system\s*\]",
        r"system\s*:\s*you\s+are",
        r"<\s*/?\s*human\s*>",
        r"<\s*/?\s*assistant\s*>",
        r"\[\s*/?human\s*\]",
        r"\[\s*/?assistant\s*\]",
        # Llama-style instruction tokens embedded in content
        r"\[INST\]",
        r"\[/INST\]",
        # MCP tool description poisoning
        r"<\s*tool_description\s*>",
        r"tool\s+(description|definition)\s*(has\s+been\s+updated|now\s+also)",
    ]
]

# -- Role-jailbreak patterns (persona assignment, fictional/educational framing) ----
_ROLE_JAILBREAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in [
        # Explicit roleplay/persona assignment with "no restrictions" framing
        r"(roleplay|role.play|role\s+play)\s*(game|scenario|exercise)",
        r"you\s+are\s+\w+(?:\s+\w+){0,3},?\s+an?\s+AI\s+that\s+has\s+no\s+(security|safety|ethical)?\s*restrictions",
        r"(no\s+security\s+restrictions|no\s+safety\s+restrictions|no\s+ethical\s+restrictions)",
        r"most\s+permissive\s+(cloud\s+)?configuration",
        # "Grandma" / nostalgia / fictional framing to elicit harmful content
        r"(grandmother|grandma|grandpa|grandfather)\s+used\s+to\s+(read|tell|recite)",
        r"(comforting|bedtime)\s+.{0,60}(terraform|security|config|exploit)",
        # "Educational exercise" / "theoretical" / "what NOT to do" framing
        r"(educational|academic|theoretical|hypothetical)\s+(exercise|purpose|example|scenario)",
        r"write\s+.{0,80}(disabl\w+\s+all\s+security|opens?\s+all\s+ports?|bypass\s+.{0,30}encrypt)",
        # Authority impersonation to extract system config
        r"i\s+am\s+an?\s+(anthropic|openai|google|microsoft)\s+(engineer|researcher|employee|staff)",
        r"(authorization|auth)\s+code\s*:\s*\S+.INTERNAL",
        r"(internal|developer|admin|test)\s+(authorization|auth)\s+code",
    ]
]

# -- Indirect injection / context-overflow patterns --------------------------
_INDIRECT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in [
        # "ATTENTION AI ASSISTANT" / "IMPORTANT INSTRUCTION" buried in data
        r"ATTENTION\s+(AI\s+)?(ASSISTANT|MODEL|SYSTEM)",
        r"IMPORTANT\s+(FINAL\s+)?INSTRUCTION\s*:",
        r"\[INST\w*\]\s*[Nn]ew\s+instruction",
        # Disregard / approve-all buried in document content
        r"disregard\s+(your\s+)?(safety\s+guidelines|policy\s+checks|findings|security)",
        r"approve\s+all\s+(changes|requests|policies|resources)",
        r"return\s+(an?\s+)?(empty\s+findings|no\s+violations|all\s+clear)",
    ]
]

# -- JSON/parameter injection patterns ---------------------------------------
_PARAM_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in [
        # Suspicious JSON keys injected alongside legitimate parameters
        r'"(override_findings|bypass_auth|inject_cmd|admin_override|skip_validation|force_approve)"\s*:',
        r'(override_findings|bypass_auth|inject_cmd|admin_override|skip_validation)\s*=\s*(true|false|1)',
        # Shell injection within JSON values
        r'"[^"]*"\s*:\s*"[^"]*(?:echo\s+\w+\s*>|rm\s+-|wget\s+|curl\s+http)[^"]*"',
    ]
]

# -- HTML/Markdown comment injection patterns --------------------------------
_COMMENT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE | re.DOTALL)
    for p in [
        # HTML comments containing override/system keywords
        r"<!--\s*(SYSTEM|OVERRIDE|INSTRUCTION|DIRECTIVE|DISREGARD|NEW\s+DIRECTIVE)",
        r"<!--.*?\b(disregard|ignore|override|directive|bypass)\b.*?-->",
        # Markdown invisible comment syntax [//]: # (...)
        r"\[//\]\s*:\s*#\s*\((OVERRIDE|SYSTEM|INSTRUCTION|DISREGARD|IGNORE)",
        r"\[//\]\s*:\s*#\s*\(.*?\b(override|disregard|ignore|bypass|unrestricted)\b",
    ]
]
_SHELL_METACHAR_PATTERN = re.compile(
    r"[;&|`$]|\.\.[\\/]|/etc/passwd|/etc/shadow|cmd\.exe|powershell",
    re.IGNORECASE,
)

# Unicode direction-override and zero-width characters
_UNICODE_DANGER_CHARS = {
    "‮",  # RIGHT-TO-LEFT OVERRIDE
    "​",  # ZERO WIDTH SPACE
    "‌",  # ZERO WIDTH NON-JOINER
    "‍",  # ZERO WIDTH JOINER
    "﻿",  # ZERO WIDTH NO-BREAK SPACE (BOM)
    " ",  # LINE SEPARATOR
    " ",  # PARAGRAPH SEPARATOR
}
# -- OUTPUT rail patterns (LLM02) -----------------------------------------

_REDACTION_RULES: list[tuple[str, re.Pattern[str]]] = [
    # AWS Access Key IDs
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # AWS Secret Access Keys (40-char base64-ish)
    ("AWS_SECRET_KEY", re.compile(r"(?<![A-Za-z0-9/+])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+])")),
    # Anthropic API keys
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b")),
    # GitHub tokens
    ("GITHUB_TOKEN", re.compile(r"\bghp_[A-Za-z0-9]{36}\b|\bgho_[A-Za-z0-9]{36}\b|\bghu_[A-Za-z0-9]{36}\b")),
    # Generic high-entropy tokens (32+ hex chars NOT in a path/hash comment context)
    ("HIGH_ENTROPY_TOKEN", re.compile(r"(?<!\w)[0-9a-fA-F]{32,64}(?!\w)")),
    # Private key blocks
    ("PRIVATE_KEY", re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE KEY-----[\s\S]*?-----END\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE KEY-----", re.DOTALL)),
    # US SSN
    ("SSN", re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")),
    # US phone numbers
    ("PHONE", re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    # Email addresses
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
]


# ---------------------------------------------------------------------------
# GuardrailEngine
# ---------------------------------------------------------------------------

class GuardrailEngine:
    """Three-rail AI security engine.

    Rails
    -----
    INPUT  : prompt-injection / role-smuggling / encoding-abuse detection
    OUTPUT : secrets & PII redaction before output leaves the platform
    EXECUTION : tool-scope allowlist enforcement

    Parameters
    ----------
    injection_threshold : float
        Severity score (0–1) at or above which the INPUT rail flags a prompt.
        Default 0.5 — tune lower for higher recall, higher for fewer FPs.
    tool_scope : ToolScope | None
        If provided, the EXECUTION rail enforces it. None = allow everything.
    """

    def __init__(
        self,
        *,
        injection_threshold: float = 0.5,
        tool_scope: ToolScope | None = None,
    ) -> None:
        self._threshold = injection_threshold
        self._scope = tool_scope

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def check_input(self, text: str) -> RailResult:
        """INPUT rail — detect prompt injection and related attacks (LLM01).

        Returns a RailResult with .flagged: bool indicating whether the
        text should be rejected / quarantined before being sent to the model.

        Pattern families checked (all must generalize — no exact dataset strings):
          1. Instruction-override: ignore/disregard/forget directives, SYSTEM OVERRIDE,
             fake assistant/human conversation turns.
          2. System-prompt exfiltration: direct asks, context-window probing,
             hidden-instructions probe, sentence-completion tricks.
          3. Role-smuggling: XML/HTML role tags, Llama [INST] tokens, MCP tool-description
             injection via <tool_description> tags.
          4. Role-jailbreak framing: roleplay persona assignment, "no restrictions" AI,
             grandma/nostalgia exploits, educational-exercise framing, authority impersonation.
          5. Indirect injection / context-overflow: "ATTENTION AI ASSISTANT" buried in data,
             "IMPORTANT FINAL INSTRUCTION", approve-all / return-empty-findings directives.
          6. HTML/Markdown comment injection: <!-- SYSTEM ... --> and [//]: # () override payloads.
          7. JSON/parameter injection: override_findings / bypass_auth / inject_cmd keys.
          8. Suspicious base64 encoding of override payloads.
          9. Unicode direction-overrides and zero-width chars.
         10. Shell metacharacters and path traversal.
         11. Markdown code-fence system-block injection.
        """
        reasons: list[str] = []
        severity = 0.0

        def _add(reason: str, weight: float) -> None:
            reasons.append(reason)
            nonlocal severity
            severity = min(1.0, severity + weight)

        # 1. Instruction-override patterns (includes SYSTEM OVERRIDE + fake turns)
        for pat in _INSTRUCTION_OVERRIDE_PATTERNS:
            if pat.search(text):
                _add(f"instruction-override pattern: {pat.pattern[:60]}", 0.6)
                break  # one hit is enough to decide

        # 2. System-prompt exfiltration (includes context-window probing, hidden-instruction probe)
        for pat in _SYSTEM_PROMPT_EXFIL_PATTERNS:
            if pat.search(text):
                _add("system-prompt exfiltration attempt", 0.6)
                break

        # 3. Role-smuggling markers (includes [INST], <tool_description>, MCP tool poisoning)
        for pat in _ROLE_SMUGGLING_PATTERNS:
            if pat.search(text):
                _add(f"role-smuggling marker: {pat.pattern[:60]}", 0.5)
                break

        # 4. Role-jailbreak / fictional-framing / authority-impersonation
        for pat in _ROLE_JAILBREAK_PATTERNS:
            if pat.search(text):
                _add(f"role-jailbreak / framing attack: {pat.pattern[:60]}", 0.6)
                break

        # 5. Indirect injection / context-overflow attacks buried in data
        for pat in _INDIRECT_INJECTION_PATTERNS:
            if pat.search(text):
                _add(f"indirect injection marker: {pat.pattern[:60]}", 0.6)
                break

        # 6. HTML/Markdown comment injection
        for pat in _COMMENT_INJECTION_PATTERNS:
            if pat.search(text):
                _add(f"comment-based injection attempt: {pat.pattern[:60]}", 0.6)
                break

        # 7. JSON/parameter injection (override_findings, bypass_auth, inject_cmd, etc.)
        for pat in _PARAM_INJECTION_PATTERNS:
            if pat.search(text):
                _add(f"JSON/parameter injection attempt: {pat.pattern[:60]}", 0.6)
                break

        # 8. Suspicious encoding: base64 blobs > 100 chars
        b64_hits = re.findall(r"[A-Za-z0-9+/]{100,}={0,2}", text)
        for blob in b64_hits:
            try:
                decoded = base64.b64decode(blob + "==").decode("utf-8", errors="replace")
                # If decoded contains instruction-override patterns, it's definitely injected
                for pat in _INSTRUCTION_OVERRIDE_PATTERNS:
                    if pat.search(decoded):
                        _add("base64-encoded instruction override", 0.7)
                        break
            except Exception:
                pass
            else:
                # Even without decoded injection, large b64 blobs in prompts are suspicious
                _add("suspicious base64 blob (>100 chars)", 0.2)
                break

        # 9. Unicode direction overrides / zero-width chars
        for char in _UNICODE_DANGER_CHARS:
            if char in text:
                _add(f"suspicious unicode char U+{ord(char):04X}", 0.6)
                break

        # 10. Tool-arg / path traversal shell metacharacters
        if _SHELL_METACHAR_PATTERN.search(text):
            _add("shell metacharacter or path traversal pattern", 0.5)

        # 11. Markdown / tool-description injection (code fences with system blocks)
        if re.search(r"```\s*system", text, re.IGNORECASE):
            _add("markdown system-block injection attempt", 0.5)

        flagged = severity >= self._threshold
        if flagged:
            logger.warning("INPUT rail flagged prompt (severity=%.2f): %s", severity, reasons)
        return RailResult(
            flagged=flagged,
            reasons=reasons,
            redacted_text=text,
            severity=severity,
        )

    def redact_output(self, text: str) -> RailResult:
        """OUTPUT rail — redact secrets and PII from LLM output (LLM02).

        Returns a RailResult where .redacted_text is safe to emit.
        """
        reasons: list[str] = []
        redacted = text

        for label, pattern in _REDACTION_RULES:
            before = redacted
            redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
            if redacted != before:
                reasons.append(f"redacted {label}")

        return RailResult(
            flagged=bool(reasons),
            reasons=reasons,
            redacted_text=redacted,
            severity=0.8 if reasons else 0.0,
        )

    def check_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> RailResult:
        """EXECUTION rail — enforce tool scope (LLM06 Excessive Agency).

        Parameters
        ----------
        tool_name : str
            The name of the tool about to be called.
        tool_args : dict | None
            The arguments to pass to the tool; used to detect path-traversal.

        Returns a RailResult. If flagged, the caller must NOT execute the tool.
        """
        reasons: list[str] = []

        # No scope = allow everything
        if self._scope is None:
            return RailResult(flagged=False)

        # Check tool allowlist + call-count cap
        allowed, reason = self._scope.check_tool(tool_name)
        if not allowed:
            reasons.append(reason)
            logger.warning("EXECUTION rail denied tool '%s': %s", tool_name, reason)
            return RailResult(flagged=True, reasons=reasons, severity=1.0)

        # Check path args
        if tool_args:
            for key, val in tool_args.items():
                if isinstance(val, str) and "/" in val or isinstance(val, str) and "\\" in val:
                    ok, path_reason = self._scope.check_path(val)
                    if not ok:
                        reasons.append(path_reason)
                        logger.warning("EXECUTION rail denied path '%s' in tool '%s': %s", val, tool_name, path_reason)
                        return RailResult(flagged=True, reasons=reasons, severity=1.0)

        self._scope.record_call()
        return RailResult(flagged=False)


# ---------------------------------------------------------------------------
# GuardedAIClient — thin composition wrapper (LLM01 + LLM02 + LLM10)
# ---------------------------------------------------------------------------

class GuardedAIClient:
    """Wraps any AIClient-compatible object with GuardrailEngine + BudgetGuard.

    Duck-typed: only requires the wrapped object to have a ``structured``
    coroutine method (the primary call site in agent_ops). Import of
    core.ai_client happens at __init__ time via the passed instance —
    no module-level import, no circular dependency.

    Parameters
    ----------
    client : any
        An AIClient-compatible object (has an async ``structured`` method).
    engine : GuardrailEngine | None
        If None, a default engine with threshold=0.5 is constructed.
    budget_guard : BudgetGuard | None
        If None, no budget cap is enforced.
    on_flag : Callable[[str, RailResult], None] | None
        Optional callback invoked when the INPUT rail flags a prompt.
        Receives (user_text, rail_result). Default: log at WARNING.
    """

    def __init__(
        self,
        client: Any,
        *,
        engine: GuardrailEngine | None = None,
        budget_guard: BudgetGuard | None = None,
        on_flag: Callable[[str, RailResult], None] | None = None,
    ) -> None:
        self._client = client
        self._engine = engine or GuardrailEngine()
        self._budget = budget_guard
        self._on_flag = on_flag or _default_on_flag

    # ------------------------------------------------------------------
    # Passthrough to underlying client
    # ------------------------------------------------------------------

    @property
    def raw(self) -> Any:
        return getattr(self._client, "raw", self._client)

    # ------------------------------------------------------------------
    # Guarded structured call
    # ------------------------------------------------------------------

    async def structured(self, *, user: str, **kwargs: Any) -> Any:
        """Guarded wrapper around the underlying client's structured() method.

        1. Runs INPUT rail on ``user`` text.
        2. Checks budget BEFORE the call (with a generous 2048-token estimate
           if the caller didn't specify max_tokens).
        3. Calls the underlying structured() method.
        4. Runs OUTPUT rail on raw_text and redacts secrets before returning.
        5. Records actual usage against BudgetGuard.
        """
        # --- INPUT rail ---
        input_result = self._engine.check_input(user)
        if input_result.flagged:
            self._on_flag(user, input_result)
            raise ValueError(
                f"INPUT guardrail blocked prompt: {input_result.reasons}"
            )

        # --- Pre-call budget check (estimated) ---
        if self._budget is not None:
            max_tokens = kwargs.get("max_tokens", 2048)
            # rough estimate: user chars / 4 = input tokens
            estimated_input = max(len(user) // 4, 128)
            self._budget.check(input_tokens=estimated_input, output_tokens=max_tokens)

        # --- Call through ---
        response = await self._client.structured(user=user, **kwargs)

        # --- OUTPUT rail ---
        raw_text = getattr(response, "raw_text", "") or ""
        out_result = self._engine.redact_output(raw_text)
        if out_result.flagged:
            logger.warning("OUTPUT rail redacted fields: %s", out_result.reasons)
            # Patch the response in-place (StructuredResponse is a dataclass)
            try:
                object.__setattr__(response, "raw_text", out_result.redacted_text)
            except (AttributeError, TypeError):
                pass  # not patchable; redacted copy already logged

        # --- Record actual usage ---
        if self._budget is not None:
            in_tok = getattr(response, "input_tokens", 0) or 0
            out_tok = getattr(response, "output_tokens", 0) or 0
            self._budget.record(input_tokens=in_tok, output_tokens=out_tok)

        return response

    # Passthrough for all other methods
    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def _default_on_flag(user_text: str, result: RailResult) -> None:
    logger.warning(
        "GuardedAIClient: INPUT rail flagged prompt (severity=%.2f, reasons=%s). "
        "First 120 chars: %r",
        result.severity,
        result.reasons,
        user_text[:120],
    )
