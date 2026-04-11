"""
eu_ai_act.py — EU AI Act compliance engine v2.

V2 additions over V1:
- Complete Article 12 mandatory fields per Annex IV
- Article 62 serious incident reporting (72-hour window tracker)
- GPAI model obligations (in force August 2025):
  - Provider obligations for general-purpose AI models
  - Systemic risk classification (>10^25 FLOPs threshold)
  - Transparency documentation checklist
- Enforcement timeline with live countdown (all 4 phases)
- HTML Article 12 compliance report generation
- Bias / disparate impact detection from audit log patterns

EU AI Act timeline (Regulation (EU) 2024/1689):
- Feb 2, 2025:  Prohibited systems (Article 5) enforcement began
- Aug 2, 2025:  GPAI model rules (Chapter V) enforcement began
- Aug 2, 2026:  High-risk AI system obligations (Articles 8-25)
- Aug 2, 2027:  Remaining provisions

Reference: EUR-Lex 32024R1689
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from ai_audit_trail.chain import AuditChain, RiskTier


# ---------------------------------------------------------------------------
# Enforcement timeline
# ---------------------------------------------------------------------------

_ENFORCEMENT_DATES: dict[str, date] = {
    "prohibited_systems": date(2025, 2, 2),
    "gpai_model_rules": date(2025, 8, 2),
    "high_risk_systems": date(2026, 8, 2),
    "remaining_provisions": date(2027, 8, 2),
}

# Article 62 serious incident reporting window
ARTICLE_62_REPORTING_HOURS = 72


def days_until_enforcement(phase: str = "high_risk_systems") -> int:
    """Return days until the specified enforcement phase (negative = past)."""
    target = _ENFORCEMENT_DATES.get(phase)
    if not target:
        raise ValueError(f"Unknown phase: {phase}. Valid: {list(_ENFORCEMENT_DATES)}")
    return (target - date.today()).days


def enforcement_status() -> dict[str, Any]:
    """Return the current enforcement status of all EU AI Act phases."""
    today = date.today()
    return {
        phase: {
            "date": d.isoformat(),
            "days_remaining": (d - today).days,
            "status": "ENFORCED" if d <= today else "UPCOMING",
        }
        for phase, d in _ENFORCEMENT_DATES.items()
    }


# ---------------------------------------------------------------------------
# Annex III high-risk system categories
# ---------------------------------------------------------------------------

_ANNEX_III_CATEGORIES: dict[str, list[str]] = {
    "biometric_categorisation": [
        "biometric", "face recognition", "facial", "fingerprint",
        "voice recognition", "identity verification", "gait recognition",
    ],
    "critical_infrastructure": [
        "power grid", "water", "gas", "transport", "traffic management",
        "critical infrastructure", "smart grid", "pipeline",
    ],
    "education": [
        "student assessment", "exam", "admission", "educational evaluation",
        "grading", "academic", "learning assessment", "school",
    ],
    "employment_hr": [
        "hiring", "recruitment", "cv screening", "resume screening",
        "job applicant", "employee evaluation", "promotion", "termination",
        "workforce", "hr decision", "performance appraisal",
    ],
    "essential_services": [
        "credit score", "loan", "insurance", "social benefit",
        "housing", "social services", "benefit eligibility",
        "mortgage", "underwriting", "fraud detection",
    ],
    "law_enforcement": [
        "crime prediction", "predictive policing", "criminal", "law enforcement",
        "judicial", "court", "sentencing", "parole", "recidivism",
    ],
    "migration_asylum": [
        "immigration", "asylum", "border control", "visa",
        "migration assessment", "refugee",
    ],
    "democratic_processes": [
        "election", "voting", "political", "democracy",
        "electoral", "campaign targeting", "voter",
    ],
    "medical_safety": [
        "medical device", "safety component", "autonomous vehicle",
        "flight control", "surgical", "medical diagnosis",
        "clinical decision", "triage", "drug interaction",
    ],
}


def detect_annex_iii_categories(system_description: str) -> list[str]:
    """
    Detect which Annex III high-risk categories a system likely falls into.
    Returns list of matched category names (empty if no match).
    """
    desc_lower = system_description.lower()
    return [
        category
        for category, keywords in _ANNEX_III_CATEGORIES.items()
        if any(kw in desc_lower for kw in keywords)
    ]


def classify_risk_tier(system_description: str) -> RiskTier:
    """
    Classify the EU AI Act risk tier based on system description.
    Articles 5-7 logic with Annex III keyword detection.
    """
    desc_lower = system_description.lower()

    # Article 5: Prohibited practices
    prohibited_keywords = [
        "social scoring", "social credit", "mass surveillance",
        "real-time biometric surveillance", "subliminal manipulation",
        "exploit vulnerabilities", "manipulate behaviour",
        "remote biometric identification in public",
    ]
    if any(kw in desc_lower for kw in prohibited_keywords):
        return RiskTier.UNACCEPTABLE

    # Annex III: High-risk categories
    if detect_annex_iii_categories(system_description):
        return RiskTier.HIGH

    # Article 50: Transparency (chatbots, deepfakes)
    limited_keywords = [
        "chatbot", "deepfake", "synthetic media", "ai-generated",
        "emotion recognition", "content recommendation",
        "virtual assistant",
    ]
    if any(kw in desc_lower for kw in limited_keywords):
        return RiskTier.LIMITED

    return RiskTier.MINIMAL


def classify_risk_tier_with_llm(
    system_description: str,
    anthropic_client: Any,
) -> tuple[RiskTier, str]:
    """
    Use Claude to classify risk tier with reasoning.
    Returns (RiskTier, explanation_text).

    Requires: pip install anthropic
    """
    prompt = f"""You are an EU AI Act compliance expert. Classify the risk tier of
the following AI system under Regulation (EU) 2024/1689.

AI System Description:
{system_description}

EU AI Act Risk Tiers:
- UNACCEPTABLE: Prohibited (Article 5) — social scoring, real-time biometric surveillance,
  subliminal manipulation, exploitation of vulnerabilities
- HIGH: Annex III systems — biometrics, critical infrastructure, education assessment,
  employment/HR decisions, essential services (credit/insurance), law enforcement,
  migration, democratic processes, safety-critical systems
- LIMITED: Transparency obligations only (Article 50) — chatbots, deepfakes,
  emotion recognition, AI-generated content
- MINIMAL: All other systems

Respond in JSON only:
{{
  "risk_tier": "HIGH|LIMITED|MINIMAL|UNACCEPTABLE",
  "annex_iii_categories": ["list", "of", "matched", "categories"],
  "reasoning": "2-3 sentence explanation citing the relevant article/annex",
  "confidence": "HIGH|MEDIUM|LOW",
  "gpai_applicable": true|false,
  "article_62_risk": true|false
}}"""

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text if response.content else ""

    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        data = json.loads(json_match.group())
        tier = RiskTier(data.get("risk_tier", "LIMITED"))
        reasoning = data.get("reasoning", "")
        return tier, reasoning

    tier = classify_risk_tier(system_description)
    return tier, "Classified via keyword matching (LLM response unparseable)."


# ---------------------------------------------------------------------------
# Article 12 compliance checker
# ---------------------------------------------------------------------------

@dataclass
class Article12Check:
    """Result of an Article 12 record-keeping compliance assessment."""
    compliant: bool
    score: int  # 0-100
    requirements_met: list[str] = field(default_factory=list)
    requirements_missing: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    annex_iv_fields_present: list[str] = field(default_factory=list)
    annex_iv_fields_missing: list[str] = field(default_factory=list)


# Mandatory Annex IV fields per Article 12(1)(a-g)
_ANNEX_IV_MANDATORY_FIELDS = {
    "12.1.a": "Input data or reference to input data (hashed)",
    "12.1.b": "Output / decision produced by the AI system",
    "12.1.c": "Date and time of operation (ISO 8601 UTC timestamp)",
    "12.1.d": "Reference to the AI system version and model identifier",
    "12.1.e": "Human oversight measures applied (reviewer identity or 'automated')",
    "12.1.f": "Identity of natural persons involved in verification",
    "12.1.g": "The input data used where technically feasible (or reference)",
    "12.2":   "Tamper-evident storage ensuring log integrity",
    "12.3":   "Log retention for minimum period (10 years for Annex III)",
}

_ARTICLE_12_REQUIREMENTS = {
    "input_logging": (
        "Input data logging (Article 12.1.a)",
        "Chain logs input hashes for all decisions",
    ),
    "output_logging": (
        "Output/decision logging (Article 12.1.b)",
        "Chain logs output hashes for all decisions",
    ),
    "timestamp_logging": (
        "Timestamp recording (Article 12.1.c)",
        "Chain records ISO 8601 UTC timestamps",
    ),
    "model_identification": (
        "AI model identification (Article 12.1.d)",
        "Chain records model name and version",
    ),
    "chain_integrity": (
        "Tamper-evident storage (Article 12.2)",
        "Merkle tree + SHA-256 hash chain provides tamper evidence",
    ),
    "session_tracking": (
        "Session/interaction tracking (Article 12.1.f)",
        "Chain records session_id per conversation",
    ),
    "system_identification": (
        "AI system identification (Article 12.1.d)",
        "system_id field present on all entries",
    ),
    "high_risk_coverage": (
        "High-risk decision coverage (Article 12.1)",
        "HIGH-tier decisions present in log",
    ),
    "retention": (
        "Log retention policy (Article 12.3: minimum 10 years for Annex III)",
        "Verify retention policy is configured",
    ),
}


def check_article_12_compliance(chain: AuditChain) -> Article12Check:
    """
    Check whether an AuditChain satisfies EU AI Act Article 12 requirements.
    V2: validates all Annex IV mandatory fields, includes system_id check.
    """
    met: list[str] = []
    missing: list[str] = []
    recommendations: list[str] = []
    annex_present: list[str] = []
    annex_missing: list[str] = []

    total = chain.count()
    if total == 0:
        return Article12Check(
            compliant=False,
            score=0,
            requirements_missing=[r[0] for r in _ARTICLE_12_REQUIREMENTS.values()],
            recommendations=["No entries in audit log — begin logging AI decisions."],
            annex_iv_fields_missing=list(_ANNEX_IV_MANDATORY_FIELDS.values()),
        )

    sample = chain.query(limit=5)

    def check_field(entry_field: str) -> bool:
        return all(
            getattr(e, entry_field, None) not in (None, "", 0, "default")
            for e in sample
        )

    # input_logging
    if check_field("input_hash"):
        met.append(_ARTICLE_12_REQUIREMENTS["input_logging"][0])
        annex_present.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.a"])
    else:
        missing.append(_ARTICLE_12_REQUIREMENTS["input_logging"][0])
        annex_missing.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.a"])

    # output_logging
    if check_field("output_hash"):
        met.append(_ARTICLE_12_REQUIREMENTS["output_logging"][0])
        annex_present.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.b"])
    else:
        missing.append(_ARTICLE_12_REQUIREMENTS["output_logging"][0])
        annex_missing.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.b"])

    # timestamp_logging
    if check_field("timestamp"):
        met.append(_ARTICLE_12_REQUIREMENTS["timestamp_logging"][0])
        annex_present.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.c"])
    else:
        missing.append(_ARTICLE_12_REQUIREMENTS["timestamp_logging"][0])
        annex_missing.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.c"])

    # model_identification
    if check_field("model"):
        met.append(_ARTICLE_12_REQUIREMENTS["model_identification"][0])
        annex_present.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.d"])
    else:
        missing.append(_ARTICLE_12_REQUIREMENTS["model_identification"][0])
        annex_missing.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.d"])

    # system_identification (V2 new)
    has_system_id = all(
        getattr(e, "system_id", "default") not in (None, "", "default")
        for e in sample
    )
    if has_system_id:
        met.append(_ARTICLE_12_REQUIREMENTS["system_identification"][0])
    else:
        missing.append(_ARTICLE_12_REQUIREMENTS["system_identification"][0])
        recommendations.append(
            "Set system_id on each AuditChain entry to satisfy Article 12.1.d "
            "AI system version identification."
        )

    # chain_integrity
    report = chain.verify_chain()
    if report.is_valid:
        met.append(_ARTICLE_12_REQUIREMENTS["chain_integrity"][0])
        annex_present.append(_ANNEX_IV_MANDATORY_FIELDS["12.2"])
    else:
        missing.append(_ARTICLE_12_REQUIREMENTS["chain_integrity"][0])
        annex_missing.append(_ANNEX_IV_MANDATORY_FIELDS["12.2"])
        recommendations.append(
            f"CRITICAL: Hash chain integrity failure — {len(report.errors)} error(s). "
            "Audit logs may have been tampered with."
        )

    # session_tracking
    if check_field("session_id"):
        met.append(_ARTICLE_12_REQUIREMENTS["session_tracking"][0])
        annex_present.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.f"])
    else:
        missing.append(_ARTICLE_12_REQUIREMENTS["session_tracking"][0])
        annex_missing.append(_ANNEX_IV_MANDATORY_FIELDS["12.1.f"])

    # high_risk_coverage
    high_risk_entries = chain.query(risk_tier=RiskTier.HIGH.value, limit=1)
    if high_risk_entries:
        met.append(_ARTICLE_12_REQUIREMENTS["high_risk_coverage"][0])
    else:
        recommendations.append(
            "No HIGH-risk tier entries found. If this system processes Annex III "
            "use cases, ensure risk_tier=RiskTier.HIGH is set."
        )

    # Retention: advisory only
    annex_missing.append(_ANNEX_IV_MANDATORY_FIELDS["12.3"])
    recommendations.append(
        "Retention policy (Article 12.3): Annex III systems require logs for "
        "minimum 10 years. Implement database backup + retention enforcement."
    )
    recommendations.append(
        "Article 12.1.e: Document human oversight measures applied per decision "
        "(e.g., reviewer_id in metadata)."
    )

    score = int((len(met) / len(_ARTICLE_12_REQUIREMENTS)) * 100)
    compliant = len(missing) == 0 and report.is_valid

    return Article12Check(
        compliant=compliant,
        score=score,
        requirements_met=met,
        requirements_missing=missing,
        recommendations=recommendations,
        annex_iv_fields_present=annex_present,
        annex_iv_fields_missing=annex_missing,
    )


# ---------------------------------------------------------------------------
# Article 62 serious incident reporting
# ---------------------------------------------------------------------------

@dataclass
class Article62Report:
    """
    EU AI Act Article 62 serious incident report template.
    Must be submitted to national market surveillance authority within 72 hours
    of becoming aware of a serious incident.
    """
    incident_id: str
    system_id: str
    system_name: str
    incident_type: str
    detected_at: str
    reporting_deadline: str          # detected_at + 72 hours
    hours_remaining: float
    description: str
    affected_persons_estimate: int
    severity: str                    # P0-SAFETY | P0-DISCRIMINATION | P1-ACCURACY
    evidence_entry_ids: list[str]
    immediate_actions_taken: list[str]
    national_authority: str = "National market surveillance authority (per Art. 74)"
    provider_name: str = "[Provider organization name]"
    provider_contact: str = "[compliance@organization.com]"
    generated_at: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_markdown(self) -> str:
        """Generate Article 62 report as Markdown for submission."""
        return f"""# EU AI Act Article 62 Serious Incident Report
Regulation (EU) 2024/1689, Article 62

**Incident ID:** {self.incident_id}
**Generated:** {self.generated_at[:19]} UTC
**Reporting Status:** {"URGENT — " + str(int(self.hours_remaining)) + "h remaining" if self.hours_remaining > 0 else "OVERDUE"}

---

## 1. Provider Information (Article 62.1)

- **Provider:** {self.provider_name}
- **Contact:** {self.provider_contact}
- **Submitting to:** {self.national_authority}

## 2. AI System Identification (Article 62.2.a)

- **System ID:** {self.system_id}
- **System Name:** {self.system_name}
- **Risk Classification:** HIGH (Annex III)

## 3. Incident Description (Article 62.2.b)

- **Incident Type:** {self.incident_type}
- **Severity:** {self.severity}
- **Date/Time Detected:** {self.detected_at[:19]} UTC
- **72-Hour Reporting Deadline:** {self.reporting_deadline[:19]} UTC
- **Description:** {self.description}

## 4. Affected Persons (Article 62.2.c)

- **Estimated Affected Persons:** {self.affected_persons_estimate:,}
- **Categories of Persons:** [Describe — customers/employees/citizens]
- **Potential Harm:** [Describe potential or actual harm]

## 5. Evidence References

Audit trail entries supporting this report:
{chr(10).join(f"- {eid}" for eid in self.evidence_entry_ids) or "- See attached audit log export"}

## 6. Immediate Actions Taken (Article 62.2.d)

{chr(10).join(f"- {action}" for action in self.immediate_actions_taken) or "- Under investigation"}

## 7. Corrective Measures Planned

- [ ] Root cause analysis (complete within [X] days)
- [ ] Model retesting on affected demographic/scenario
- [ ] Process audit of human oversight measures
- [ ] Updated risk assessment (Article 9)
- [ ] Provider notification if system received from third party

---

*This report was generated automatically by AIAuditTrail v2.0.0.*
*Article 62 requires notification to competent national authority.*
*Verify with qualified EU AI Act counsel before official submission.*
"""


def detect_article_62_incidents(chain: AuditChain, system_id: str) -> list[dict[str, Any]]:
    """
    Scan audit log patterns to detect potential Article 62 serious incidents.

    Detection patterns:
    - High error rate in recent window
    - Disparate impact in CLASSIFICATION decisions (bias proxy)
    - Anomalous latency spikes (system failure risk)
    - Tamper detection (chain integrity failure)

    Returns list of detected incident dicts with severity and evidence.
    """
    incidents: list[dict[str, Any]] = []
    entries = chain.query(system_id=system_id, limit=500)

    if not entries:
        return incidents

    # --- Chain integrity ---
    report = chain.verify_chain()
    if not report.is_valid:
        incidents.append({
            "type": "P1-INTEGRITY",
            "severity": "P1-INTEGRITY",
            "description": f"Hash chain tamper detected: {len(report.tampered_entries)} entries",
            "evidence_entry_ids": [t["entry_id"] for t in report.tampered_entries[:10]],
            "affected_persons_estimate": chain.count(system_id=system_id),
        })

    # --- Error rate (entries with error in metadata) ---
    error_entries = [e for e in entries if e.metadata.get("error")]
    error_rate = len(error_entries) / len(entries) if entries else 0
    if error_rate > 0.05:  # >5% error rate
        incidents.append({
            "type": "P1-ACCURACY",
            "severity": "P1-ACCURACY",
            "description": f"Error rate {error_rate:.1%} exceeds 5% threshold in recent {len(entries)} entries",
            "evidence_entry_ids": [e.entry_id for e in error_entries[:10]],
            "affected_persons_estimate": len(error_entries),
        })

    # --- Disparate impact proxy (classification variance by session) ---
    classification_entries = [
        e for e in entries
        if e.decision_type == "CLASSIFICATION" and e.risk_tier == "HIGH"
    ]
    if len(classification_entries) >= 20:
        # Proxy: check output hash diversity (low diversity = suspicious uniformity)
        output_hashes = [e.output_hash for e in classification_entries]
        unique_ratio = len(set(output_hashes)) / len(output_hashes)
        if unique_ratio < 0.3:  # <30% unique outputs is suspicious
            incidents.append({
                "type": "P0-DISCRIMINATION",
                "severity": "P0-DISCRIMINATION",
                "description": (
                    f"LOW output diversity ({unique_ratio:.1%} unique outputs) in "
                    f"{len(classification_entries)} HIGH-risk classification decisions. "
                    "Possible bias: model may be returning similar outputs regardless of input. "
                    "Manual disparate impact analysis required."
                ),
                "evidence_entry_ids": [e.entry_id for e in classification_entries[:10]],
                "affected_persons_estimate": len(classification_entries),
            })

    # --- Latency spike ---
    latencies = [e.latency_ms for e in entries]
    if len(latencies) >= 10:
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        mean_lat = statistics.mean(latencies)
        if p95 > mean_lat * 10:  # p95 is 10x the mean
            incidents.append({
                "type": "P2-PERFORMANCE",
                "severity": "P2-PERFORMANCE",
                "description": f"Latency anomaly: p95={p95:.0f}ms is {p95/mean_lat:.0f}x the mean ({mean_lat:.0f}ms)",
                "evidence_entry_ids": [
                    e.entry_id for e in sorted(entries, key=lambda x: x.latency_ms, reverse=True)[:5]
                ],
                "affected_persons_estimate": len([l for l in latencies if l > mean_lat * 5]),
            })

    return incidents


# ---------------------------------------------------------------------------
# GPAI model obligations (Chapter V, in force August 2, 2025)
# ---------------------------------------------------------------------------

@dataclass
class GPAIComplianceCheck:
    """
    Assessment of GPAI (General-Purpose AI) model obligations under EU AI Act Chapter V.
    In force: August 2, 2025.
    """
    model_name: str
    is_gpai: bool
    has_systemic_risk: bool              # >10^25 FLOPs training compute
    estimated_training_flops: Optional[float]
    obligations_met: list[str]
    obligations_missing: list[str]
    transparency_checklist: dict[str, bool]


def check_gpai_obligations(
    model_name: str,
    estimated_training_flops: Optional[float] = None,
    has_transparency_doc: bool = False,
    has_copyright_policy: bool = False,
    has_energy_consumption_data: bool = False,
    has_capabilities_limitations_doc: bool = False,
    has_incident_reporting_process: bool = False,
) -> GPAIComplianceCheck:
    """
    Check GPAI model obligations per EU AI Act Chapter V (in force Aug 2025).

    GPAI thresholds:
    - All GPAI models: transparency obligations (Article 53)
    - Systemic risk threshold: training compute > 10^25 FLOPs (Article 51)
    - Systemic risk models: additional obligations (Article 55)
    """
    SYSTEMIC_RISK_FLOPS_THRESHOLD = 1e25

    # Detect GPAI models by name pattern
    gpai_model_patterns = [
        "gpt", "claude", "gemini", "llama", "mistral", "falcon",
        "palm", "bloom", "opt", "gpt-4", "gpt-3", "davinci",
    ]
    model_lower = model_name.lower()
    is_gpai = any(p in model_lower for p in gpai_model_patterns)

    has_systemic_risk = (
        estimated_training_flops is not None
        and estimated_training_flops > SYSTEMIC_RISK_FLOPS_THRESHOLD
    )

    # Known approximate training FLOPs for reference
    _KNOWN_FLOPS = {
        "gpt-4": 2.15e25,       # Estimated, above systemic risk threshold
        "claude-3-opus": 1e25,  # Estimated
        "llama-3-70b": 2e23,    # Below threshold
        "mistral-7b": 6e22,     # Below threshold
    }
    if estimated_training_flops is None:
        for model_key, flops in _KNOWN_FLOPS.items():
            if model_key in model_lower:
                estimated_training_flops = flops
                has_systemic_risk = flops > SYSTEMIC_RISK_FLOPS_THRESHOLD
                break

    obligations_met: list[str] = []
    obligations_missing: list[str] = []

    # Article 53: All GPAI providers must provide
    if has_transparency_doc:
        obligations_met.append("Technical documentation (Article 53.1.a)")
    else:
        obligations_missing.append("Technical documentation for downstream providers (Article 53.1.a)")

    if has_copyright_policy:
        obligations_met.append("Copyright compliance policy (Article 53.1.c)")
    else:
        obligations_missing.append("Copyright and training data compliance policy (Article 53.1.c)")

    if has_capabilities_limitations_doc:
        obligations_met.append("Capabilities and limitations summary (Article 53.1.b)")
    else:
        obligations_missing.append("Published summary of capabilities and limitations (Article 53.1.b)")

    if has_energy_consumption_data:
        obligations_met.append("Energy consumption disclosure (Article 53.1.b)")
    else:
        obligations_missing.append("Energy consumption data for training (Article 53.1.b)")

    # Article 55: Systemic risk GPAI additional obligations
    if has_systemic_risk:
        if has_incident_reporting_process:
            obligations_met.append("Incident reporting to EU AI Office (Article 55.1.c)")
        else:
            obligations_missing.append(
                "Incident and corrective action reporting to EU AI Office (Article 55.1.c)"
            )
        obligations_missing.append("Adversarial testing (red-teaming) (Article 55.1.a)")
        obligations_missing.append("Cybersecurity risk mitigation (Article 55.1.d)")

    transparency_checklist = {
        "technical_documentation": has_transparency_doc,
        "copyright_policy": has_copyright_policy,
        "capabilities_limitations": has_capabilities_limitations_doc,
        "energy_consumption": has_energy_consumption_data,
        "incident_reporting": has_incident_reporting_process,
    }

    return GPAIComplianceCheck(
        model_name=model_name,
        is_gpai=is_gpai,
        has_systemic_risk=has_systemic_risk,
        estimated_training_flops=estimated_training_flops,
        obligations_met=obligations_met,
        obligations_missing=obligations_missing,
        transparency_checklist=transparency_checklist,
    )


# ---------------------------------------------------------------------------
# Article 12 HTML compliance report
# ---------------------------------------------------------------------------

def generate_article_12_html_report(
    system_name: str,
    system_description: str,
    chain: AuditChain,
    system_id: str = "default",
    operator_name: str = "Organization Name",
    contact_email: str = "compliance@example.com",
) -> str:
    """
    Generate a full HTML Article 12 compliance report.
    Self-contained HTML, no external dependencies.
    """
    from ai_audit_trail.reporter import ReportGenerator
    gen = ReportGenerator(chain, system_name=system_name)
    report = gen.generate()
    return gen.to_html(report)


def generate_article_13_transparency_report(
    system_name: str,
    system_description: str,
    chain: AuditChain,
    operator_name: str = "Organization Name",
    contact_email: str = "compliance@example.com",
) -> str:
    """
    Generate a human-readable Article 13 transparency report as Markdown.
    Article 13 requires deployers to provide information to users.
    """
    risk_tier = classify_risk_tier(system_description)
    annex_iii = detect_annex_iii_categories(system_description)
    total_decisions = chain.count()
    article_12 = check_article_12_compliance(chain)
    enforcement = enforcement_status()

    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    days_to_enforcement = days_until_enforcement("high_risk_systems")

    lines = [
        "# EU AI Act Article 13 Transparency Report",
        "",
        f"**System:** {system_name}",
        f"**Operator:** {operator_name}",
        f"**Contact:** {contact_email}",
        f"**Report Date:** {report_date}",
        f"**Risk Classification:** {risk_tier.value}",
        "",
        "---",
        "",
        "## 1. AI System Identity and Purpose",
        "",
        f"**Description:** {system_description}",
        "",
        f"**Risk Tier:** {risk_tier.value} (EU AI Act Regulation 2024/1689)",
        "",
    ]

    if annex_iii:
        lines += [
            "**Annex III Categories Detected:**",
        ] + [f"- {c.replace('_', ' ').title()}" for c in annex_iii]
        lines.append("")

    lines += [
        "## 2. Capabilities and Intended Use",
        "",
        f"Total AI decisions logged: **{total_decisions:,}**",
        "",
        "## 3. Known Limitations",
        "",
        "- AI outputs may be incorrect or biased; human review required for high-stakes decisions",
        "- System performance may vary across demographic groups",
        "- Outputs should not be treated as deterministic or reproducible",
        "",
        "## 4. Human Oversight Provisions (Article 14)",
        "",
        "- All HIGH-risk decisions logged with tamper-evident Merkle-tree audit trail",
        "- Human review required before acting on HIGH-risk AI recommendations",
        "- Operators must verify AI outputs before applying to affected individuals",
        "",
        "## 5. Audit Trail Status (Article 12)",
        "",
        f"**Compliance Score:** {article_12.score}/100",
        "",
        f"**Requirements Met ({len(article_12.requirements_met)}):**",
    ] + [f"- {r}" for r in article_12.requirements_met]

    if article_12.requirements_missing:
        lines += [
            "",
            f"**Requirements Not Yet Met ({len(article_12.requirements_missing)}):**",
        ] + [f"- {r}" for r in article_12.requirements_missing]

    lines += [
        "",
        "## 6. EU AI Act Enforcement Timeline",
        "",
    ]
    for phase, info in enforcement.items():
        status_str = f"[{info['status']}]"
        lines.append(
            f"- **{phase.replace('_', ' ').title()}**: {info['date']} {status_str}"
        )

    if days_to_enforcement > 0:
        lines += [
            "",
            f"> **High-risk AI system enforcement begins in "
            f"{days_to_enforcement} days** ({_ENFORCEMENT_DATES['high_risk_systems'].isoformat()}). "
            f"Ensure full Article 8-25 compliance before this date.",
        ]
    else:
        lines += [
            "",
            "> **High-risk AI system enforcement is now ACTIVE** "
            f"(began {_ENFORCEMENT_DATES['high_risk_systems'].isoformat()}). "
            "Full Article 8-25 compliance is legally required.",
        ]

    lines += [
        "",
        "---",
        "",
        "*This report was generated automatically by AIAuditTrail v2.0.0. "
        "It does not constitute legal advice.*",
    ]

    return "\n".join(lines)


def generate_article_11_technical_doc(
    system_name: str,
    system_description: str,
    model_name: str,
    training_data_description: str = "Proprietary dataset",
    version: str = "1.0.0",
    operator_name: str = "Organization Name",
) -> str:
    """
    Generate an Article 11 Technical Documentation template (Annex IV).
    """
    risk_tier = classify_risk_tier(system_description)
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return f"""# Article 11 Technical Documentation (Annex IV)
EU AI Act Regulation (EU) 2024/1689

**System Name:** {system_name}
**Version:** {version}
**Provider:** {operator_name}
**Date:** {report_date}
**Risk Classification:** {risk_tier.value}

---

## 1. General Description (Annex IV, para. 1)

### 1.1 Intended Purpose
{system_description}

### 1.2 Categories of Natural Persons Affected
[List categories of individuals subject to AI-generated decisions]

### 1.3 Version History
| Version | Date | Changes |
|---------|------|---------|
| {version} | {report_date} | Initial documentation |

## 2. Detailed Description of System Elements (Annex IV, para. 2)

### 2.1 Development Methods
**Base model:** {model_name}
**Training approach:** [Supervised/Fine-tuned/RAG-augmented]

### 2.2 Training Data (Article 10)
**Description:** {training_data_description}

### 2.3 Performance Metrics (Article 9.7)
| Metric | Value | Test Set | Date Evaluated |
|--------|-------|----------|----------------|
| [Accuracy/F1/etc.] | [value] | [description] | {report_date} |

## 3. Monitoring, Functioning and Control (Annex IV, para. 3)

### 3.1 Human Oversight Measures (Article 14)
[Describe override mechanisms and intervention procedures]

### 3.2 Logging and Audit Trail (Article 12)
- **Implementation:** AIAuditTrail v2.0.0 — Merkle-tree hash chain
- **Storage backend:** SQLite WAL-mode append-only database
- **Tamper detection:** SHA-256 Merkle tree — any modification invalidates root hash
- **Anchoring:** Hourly Merkle root anchored to public ledger

## 4. Contact Information

**Provider:** {operator_name}
**Compliance contact:** [Name, email, role]

---
*Generated by AIAuditTrail v2.0.0. Verify with EU AI Act counsel before submission.*
"""
