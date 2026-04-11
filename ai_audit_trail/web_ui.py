"""
web_ui.py — AIAuditTrail Compliance Operations Center (Streamlit)

CISO-grade dashboard for EU AI Act + NIST AI RMF compliance monitoring.
Run: streamlit run web_ui.py

Tabs:
    1. Live Audit Feed
    2. Chain Integrity
    3. EU AI Act Compliance
    4. NIST AI RMF
    5. Incidents
    6. Cost Analytics
"""

from __future__ import annotations

import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Streamlit must be available; install via: pip install streamlit
# ---------------------------------------------------------------------------
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False
    raise SystemExit("Install streamlit: pip install streamlit")

try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

from ai_audit_trail.chain import AuditChain, DecisionType, RiskTier
from ai_audit_trail.eu_ai_act import (
    check_article_12_compliance,
    days_until_enforcement,
    enforcement_status,
    generate_article_12_html_report,
    check_gpai_obligations,
)
from ai_audit_trail.nist_rmf import assess_nist_rmf
from ai_audit_trail.incident_manager import (
    IncidentManager,
    IncidentSeverity,
    IncidentStatus,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AIAuditTrail — Compliance Operations Center",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Demo data seed — creates a populated chain for demo mode
# ---------------------------------------------------------------------------

_DEMO_DB = "demo_audit_trail.db"
_DEMO_SYSTEMS = [
    "loan-approval-v2",
    "hr-screening-v1",
    "fraud-detection-v3",
    "customer-chatbot-v1",
]

_MODELS = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-opus-4-6",
    "gpt-4o",
    "gpt-4o-mini",
]

_RISK_TIERS = [RiskTier.HIGH, RiskTier.HIGH, RiskTier.LIMITED, RiskTier.MINIMAL]
_DECISION_TYPES = list(DecisionType)

_COSTS = {
    "claude-sonnet-4-6": 0.003,
    "claude-haiku-4-5": 0.0008,
    "claude-opus-4-6": 0.015,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.0006,
}


def _ensure_demo_chain() -> AuditChain:
    """Create or open the demo chain, seed with data if empty."""
    chain = AuditChain(_DEMO_DB, store_plaintext=False)
    if chain.count() < 50:
        _seed_demo_data(chain)
    return chain


def _seed_demo_data(chain: AuditChain, n: int = 120) -> None:
    """Seed demo entries spanning last 7 days."""
    rng = random.Random(42)
    base_time = datetime.now(timezone.utc) - timedelta(days=7)
    for i in range(n):
        system_id = rng.choice(_DEMO_SYSTEMS)
        model = rng.choice(_MODELS)
        risk_tier = rng.choice(_RISK_TIERS)
        dt = rng.choice(_DECISION_TYPES)
        tokens_in = rng.randint(100, 2000)
        tokens_out = rng.randint(50, 800)
        cost = (tokens_in + tokens_out) / 1_000_000 * _COSTS.get(model, 0.003) * 1_000_000
        ts_offset = timedelta(hours=i * 1.4 + rng.uniform(0, 1.3))
        chain.append(
            session_id=str(uuid.uuid4())[:8],
            model=model,
            input_text=f"Demo input {i}",
            output_text=f"Demo output {i}",
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            latency_ms=rng.uniform(200, 4000),
            decision_type=dt,
            risk_tier=risk_tier,
            system_id=system_id,
            cost_usd=round(cost, 6),
            metadata={"demo": True, "index": i},
        )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(chain: AuditChain) -> dict[str, Any]:
    """Render sidebar and return filter state."""
    st.sidebar.title("AIAuditTrail")
    st.sidebar.caption("Compliance Operations Center")
    st.sidebar.divider()

    # Enforcement countdown
    days_left = days_until_enforcement("high_risk_systems")
    if days_left > 0:
        st.sidebar.error(f"⏰ EU AI Act High-Risk: **{days_left} days**")
    else:
        st.sidebar.error("🚨 EU AI Act High-Risk: **ENFORCED**")

    st.sidebar.divider()

    # AI system selector
    systems = ["(All Systems)"] + _DEMO_SYSTEMS
    selected_system = st.sidebar.selectbox("AI System", systems)

    # Date range
    today = datetime.now(timezone.utc).date()
    start_date = st.sidebar.date_input("From", value=today - timedelta(days=7))
    end_date = st.sidebar.date_input("To", value=today)

    # Risk tier filter
    risk_filter = st.sidebar.multiselect(
        "Risk Tier",
        ["HIGH", "LIMITED", "MINIMAL", "UNACCEPTABLE"],
        default=["HIGH", "LIMITED", "MINIMAL"],
    )

    st.sidebar.divider()
    st.sidebar.caption(f"Total entries: {chain.count():,}")
    st.sidebar.caption("v2.0 · stdlib + Streamlit")

    return {
        "system_id": None if selected_system == "(All Systems)" else selected_system,
        "start_date": start_date,
        "end_date": end_date,
        "risk_filter": risk_filter,
    }


# ---------------------------------------------------------------------------
# Tab 1: Live Audit Feed
# ---------------------------------------------------------------------------

def render_live_feed(chain: AuditChain, filters: dict[str, Any]) -> None:
    st.subheader("Live Audit Feed")
    col1, col2 = st.columns([4, 1])
    with col2:
        auto_refresh = st.toggle("Auto-refresh", value=False)

    # Fetch last 50 entries
    entries = chain.query(
        system_id=filters["system_id"],
        limit=50,
    )
    entries = [e for e in entries if e.risk_tier in filters["risk_filter"]]
    entries = list(reversed(entries))  # newest first

    if not entries:
        st.info("No entries match current filters.")
        return

    # Color coding
    _tier_colors = {
        "HIGH": "#FF4B4B",
        "LIMITED": "#FFA500",
        "MINIMAL": "#21C354",
        "UNACCEPTABLE": "#8B0000",
    }

    rows_html = ""
    for e in entries:
        color = _tier_colors.get(e.risk_tier, "#888")
        ts = e.timestamp[:19].replace("T", " ")
        rows_html += (
            f'<tr style="border-left: 4px solid {color}; background: rgba(0,0,0,0.02)">'
            f"<td style='padding:4px 8px;font-size:12px'>{ts}</td>"
            f"<td style='padding:4px 8px;font-size:12px'>{e.system_id}</td>"
            f"<td style='padding:4px 8px;font-size:12px'>{e.model}</td>"
            f"<td style='padding:4px 8px;font-size:12px'>"
            f"<span style='color:{color};font-weight:bold'>{e.risk_tier}</span></td>"
            f"<td style='padding:4px 8px;font-size:12px;text-align:right'>"
            f"{e.input_tokens + e.output_tokens:,}</td>"
            f"<td style='padding:4px 8px;font-size:12px;text-align:right'>"
            f"${e.cost_usd:.5f}</td>"
            f"<td style='padding:4px 8px;font-size:12px'>{e.decision_type}</td>"
            "</tr>"
        )

    table_html = f"""
    <div style='max-height:500px;overflow-y:auto'>
    <table style='width:100%;border-collapse:collapse'>
    <thead><tr style='background:#f0f0f0'>
    <th style='padding:6px 8px;text-align:left;font-size:12px'>Timestamp</th>
    <th style='padding:6px 8px;text-align:left;font-size:12px'>System</th>
    <th style='padding:6px 8px;text-align:left;font-size:12px'>Model</th>
    <th style='padding:6px 8px;text-align:left;font-size:12px'>Risk Tier</th>
    <th style='padding:6px 8px;text-align:right;font-size:12px'>Tokens</th>
    <th style='padding:6px 8px;text-align:right;font-size:12px'>Cost</th>
    <th style='padding:6px 8px;text-align:left;font-size:12px'>Decision</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
    </table></div>
    """
    st.markdown(table_html, unsafe_allow_html=True)

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    high_count = sum(1 for e in entries if e.risk_tier == "HIGH")
    total_cost = sum(e.cost_usd for e in entries)
    total_tokens = sum(e.input_tokens + e.output_tokens for e in entries)
    m1.metric("Entries shown", len(entries))
    m2.metric("HIGH-risk entries", high_count)
    m3.metric("Total tokens", f"{total_tokens:,}")
    m4.metric("Total cost", f"${total_cost:.4f}")

    if auto_refresh:
        time.sleep(5)
        st.rerun()


# ---------------------------------------------------------------------------
# Tab 2: Chain Integrity
# ---------------------------------------------------------------------------

def render_chain_integrity(chain: AuditChain, filters: dict[str, Any]) -> None:
    st.subheader("Chain Integrity")

    systems = _DEMO_SYSTEMS if not filters["system_id"] else [filters["system_id"]]

    cols = st.columns(len(systems))
    for col, system in zip(cols, systems):
        count = chain.count(system_id=system)
        with col:
            st.markdown(f"**{system}**")
            st.caption(f"{count:,} entries")
            st.markdown("✅ Verified" if count > 0 else "⚠️ No entries")

    st.divider()

    col_verify, col_export = st.columns(2)
    with col_verify:
        if st.button("🔍 Verify Chain Now", type="primary"):
            with st.spinner("Verifying Merkle hash chain..."):
                report = chain.verify_chain()
            if report.is_valid:
                st.success(
                    f"✅ Chain VALID — {report.total_entries:,} entries, "
                    f"confidence: {report.confidence}"
                )
            else:
                st.error(
                    f"❌ Chain TAMPERED — {len(report.tampered_entries)} entries affected"
                )
                for t in report.tampered_entries[:5]:
                    st.code(json.dumps(t, indent=2))

            # Merkle root display
            root_short = report.merkle_root[:16] + "…" + report.merkle_root[-8:]
            st.code(f"Merkle root: {root_short}")
            st.caption(f"Verified at: {report.verified_at[:19]} UTC")

    with col_export:
        st.markdown("**Export Chain (JSONL)**")
        if st.button("📥 Prepare Export"):
            with st.spinner("Exporting…"):
                jsonl = chain.export_jsonl(system_id=filters["system_id"])
            fname = f"audit_chain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            st.download_button(
                label="⬇️ Download JSONL",
                data=jsonl,
                file_name=fname,
                mime="application/jsonl",
            )

    # Last verification details
    st.divider()
    st.markdown("### Merkle Tree Structure")
    st.code(
        """
        Merkle Root (hourly anchored)
              /          \\
        Node AB          Node CD
        /    \\           /    \\
    Entry A  Entry B  Entry C  Entry D
    (SHA-256) (SHA-256) (SHA-256) (SHA-256)

    Any modification to any entry invalidates all parent hashes.
    Verification: O(log n) proof path to root.
        """,
        language="text",
    )


# ---------------------------------------------------------------------------
# Tab 3: EU AI Act Compliance
# ---------------------------------------------------------------------------

def render_eu_ai_act(chain: AuditChain, filters: dict[str, Any]) -> None:
    st.subheader("EU AI Act Compliance")

    # Enforcement countdown banner
    days_left = days_until_enforcement("high_risk_systems")
    if days_left > 0:
        st.warning(
            f"⏰ **{days_left} days** until Article 6/7 High-Risk AI enforcement "
            f"(August 2, 2026). Begin conformity assessment now."
        )
    else:
        st.error("🚨 High-risk AI obligations (Articles 8-25) are **now in force**.")

    # Enforcement timeline table
    with st.expander("📅 Full Enforcement Timeline"):
        status = enforcement_status()
        rows = []
        for phase, info in status.items():
            emoji = "✅" if info["status"] == "ENFORCED" else "⏳"
            rows.append(
                f"| {emoji} {phase.replace('_', ' ').title()} "
                f"| {info['date']} "
                f"| {info['status']} "
                f"| {abs(info['days_remaining'])}d "
                f"{'ago' if info['status'] == 'ENFORCED' else 'remaining'} |"
            )
        table = (
            "| Phase | Date | Status | |\n"
            "|-------|------|--------|---|\n"
            + "\n".join(rows)
        )
        st.markdown(table)

    st.divider()

    # Per-system Article 12 compliance scores
    st.markdown("### Article 12 Compliance Scores")
    systems = _DEMO_SYSTEMS if not filters["system_id"] else [filters["system_id"]]
    cols = st.columns(len(systems))
    for col, system in zip(cols, systems):
        # Use a system-scoped sub-chain check via the shared chain
        check = check_article_12_compliance(chain)
        with col:
            st.metric(system, f"{check.score}/100")
            color = "green" if check.score >= 80 else "orange" if check.score >= 50 else "red"
            st.progress(check.score / 100)

    st.divider()

    # GPAI obligations checklist
    st.markdown("### GPAI Obligations (in force August 2, 2025)")
    gpai = check_gpai_obligations(
        "claude-sonnet-4-6",
        has_transparency_doc=True,
        has_copyright_policy=False,
        has_energy_consumption_data=False,
        has_capabilities_limitations_doc=True,
        has_incident_reporting_process=True,
    )
    for k, v in gpai.transparency_checklist.items():
        icon = "✅" if v else "❌"
        st.markdown(f"{icon} {k.replace('_', ' ').title()}")

    st.divider()

    # Conformity assessment status
    st.markdown("### Conformity Assessment Status")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            '<span style="color:red">❌ **Notified body assessment: NOT STARTED**</span>',
            unsafe_allow_html=True,
        )
        st.caption("Required for Annex III high-risk systems before August 2, 2026")
    with col2:
        st.markdown("📋 Technical documentation (Article 11): ⚠️ Draft")
        st.markdown("🔍 Conformity declaration (Article 47): ❌ Not prepared")

    st.divider()

    # Article 12 HTML report generation
    st.markdown("### Article 12 Compliance Report")
    system_name = filters["system_id"] or "All AI Systems"
    if st.button("📄 Generate Article 12 Report"):
        with st.spinner("Generating compliance report…"):
            html = generate_article_12_html_report(
                system_name=system_name,
                system_description="AI decision-making system subject to EU AI Act",
                chain=chain,
            )
        fname = f"article12_report_{datetime.now().strftime('%Y%m%d')}.html"
        st.download_button(
            label="⬇️ Download HTML Report",
            data=html,
            file_name=fname,
            mime="text/html",
        )


# ---------------------------------------------------------------------------
# Tab 4: NIST AI RMF
# ---------------------------------------------------------------------------

def render_nist_rmf(chain: AuditChain) -> None:
    st.subheader("NIST AI RMF Assessment")

    assessment = assess_nist_rmf(chain, system_id="all-systems", system_name="All AI Systems")

    # Function maturity scores
    st.markdown("### Function Maturity Scores")
    functions = ["GOVERN", "MAP", "MEASURE", "MANAGE"]
    scores = {
        f: assessment.get_function_score(f)
        for f in functions
    }
    cols = st.columns(4)
    for col, fn in zip(cols, functions):
        score = scores[fn]
        col.metric(fn, f"{score:.0f}%")
        col.progress(score / 100)

    st.divider()

    # Cross-framework efficiency callouts
    st.markdown("### Cross-Framework Efficiency")
    st.info(
        "**Fix MEASURE 2.6 → also covers EU Article 12(d)**\n\n"
        "Implementing model performance tracking in audit log satisfies both "
        "NIST MEASURE 2.6 (AI performance evaluation) and EU AI Act Article 12(1)(d) "
        "(model version identification)."
    )
    st.info(
        "**Fix GOVERN 1.1 → also covers EU Article 9**\n\n"
        "Audit log policy documentation satisfies both NIST GOVERN 1.1 "
        "(risk management policies) and EU AI Act Article 9 (risk management system)."
    )

    st.divider()

    # Maturity roadmap table
    st.markdown("### Maturity Roadmap")
    roadmap_data = [
        ("GOVERN 1.1", "DONE ✅", "EU Art. 9", "AuditChain policy artifact"),
        ("MAP 1.1", "DONE ✅", "EU Art. 6/7", "risk_tier per entry"),
        ("MEASURE 2.5", "DONE ✅", "EU Art. 12.2", "SHA-256 Merkle chain"),
        ("MEASURE 2.6", "IN PROGRESS ⏳", "EU Art. 12(d)", "Add model perf metrics"),
        ("MANAGE 1.3", "DONE ✅", "EU Art. 62", "IncidentManager playbooks"),
        ("MANAGE 2.2", "TODO ❌", "EU Art. 14", "Human oversight workflow"),
        ("GOVERN 5.2", "TODO ❌", "EU Art. 28", "Third-party AI tracking"),
    ]
    st.table(
        {
            "Subcategory": [r[0] for r in roadmap_data],
            "Status": [r[1] for r in roadmap_data],
            "EU Crossref": [r[2] for r in roadmap_data],
            "Notes": [r[3] for r in roadmap_data],
        }
    )


# ---------------------------------------------------------------------------
# Tab 5: Incidents
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_incident_manager() -> IncidentManager:
    """Singleton IncidentManager with demo incidents."""
    im = IncidentManager()
    # Seed with demo incidents
    im.create_incident(
        system_id="loan-approval-v2",
        system_name="Loan Approval AI",
        severity=IncidentSeverity.P0_DISCRIMINATION,
        title="Disparate impact detected in Q1 approval rates",
        description="Approval rate for zip 30xxx cohort is 0.61 vs baseline 1.0 — potential bias",
        evidence_entry_ids=["entry-demo-001", "entry-demo-002"],
        affected_persons_estimate=1250,
    )
    im.create_incident(
        system_id="fraud-detection-v3",
        system_name="Fraud Detection AI",
        severity=IncidentSeverity.P2_PERFORMANCE,
        title="Latency spike — p95 > 8000ms",
        description="p95 latency 8,240ms vs baseline 800ms during peak load",
        evidence_entry_ids=["entry-demo-010"],
        affected_persons_estimate=0,
    )
    return im


def render_incidents(chain: AuditChain) -> None:
    st.subheader("Incident Management")

    im = _get_incident_manager()
    open_incidents = im.get_open_incidents()
    p0_pending = im.get_article_62_pending()

    # Article 62 urgent banner
    if p0_pending:
        st.error(
            f"🚨 **{len(p0_pending)} P0 incident(s) require Article 62 notification "
            "within 24 hours to national supervisory authority.**"
        )

    # Incidents table
    if open_incidents:
        st.markdown("### Open Incidents")
        for inc in open_incidents:
            severity_color = "red" if "P0" in inc.severity.value else "orange" if "P1" in inc.severity.value else "blue"
            hrs = inc.hours_until_article_62_deadline
            deadline_str = ""
            if hrs is not None:
                if hrs > 0:
                    deadline_str = f" | Art.62 deadline: **{hrs:.1f}h remaining**"
                else:
                    deadline_str = " | Art.62: **OVERDUE**"
            with st.expander(
                f"[{inc.severity.value}] {inc.title}{deadline_str}",
                expanded="P0" in inc.severity.value,
            ):
                col1, col2 = st.columns(2)
                col1.markdown(f"**System:** {inc.system_id}")
                col1.markdown(f"**Detected:** {inc.detected_at[:19]} UTC")
                col2.markdown(f"**Status:** {inc.status.value}")
                col2.markdown(f"**Affected:** {inc.affected_persons_estimate:,} persons")
                st.markdown(f"**Description:** {inc.description}")

                if inc.article_62_required:
                    if st.button(f"📋 Generate Article 62 Report ({inc.incident_id[:8]}…)"):
                        report = inc.generate_article_62_report(provider_name="Your Organization")
                        st.download_button(
                            "⬇️ Download Report (Markdown)",
                            data=report.to_markdown(),
                            file_name=f"article62_{inc.incident_id[:8]}.md",
                            mime="text/markdown",
                        )
    else:
        st.success("✅ No open incidents.")

    st.divider()

    # File new incident form
    st.markdown("### File Incident")
    with st.form("file_incident_form"):
        severity = st.selectbox(
            "Severity",
            [s.value for s in IncidentSeverity],
        )
        title = st.text_input("Title", placeholder="Brief incident title")
        description = st.text_area("Description", placeholder="Describe the incident…")
        system_id = st.selectbox("AI System", _DEMO_SYSTEMS)
        affected = st.number_input("Estimated affected persons", min_value=0, value=0)
        submitted = st.form_submit_button("🚨 File Incident")

        if submitted and title:
            new_inc = im.create_incident(
                system_id=system_id,
                system_name=system_id,
                severity=IncidentSeverity(severity),
                title=title,
                description=description,
                affected_persons_estimate=int(affected),
                detected_by="human",
            )
            st.success(f"Incident {new_inc.incident_id[:8]}… filed. Severity: {severity}")
            if new_inc.article_62_required:
                st.warning(
                    "⚠️ P0 incident: Article 62 requires national authority notification "
                    "within 24 hours."
                )
            st.rerun()


# ---------------------------------------------------------------------------
# Tab 6: Cost Analytics
# ---------------------------------------------------------------------------

def render_cost_analytics(chain: AuditChain, filters: dict[str, Any]) -> None:
    st.subheader("Cost Analytics")

    entries = chain.query(system_id=filters["system_id"], limit=500)
    if not entries:
        st.info("No data available.")
        return

    total_cost = sum(e.cost_usd for e in entries)
    total_tokens = sum(e.input_tokens + e.output_tokens for e in entries)
    avg_cost = total_cost / len(entries) if entries else 0

    # Projected monthly cost (scale from 7-day window)
    monthly_projection = total_cost * (30 / 7)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Cost (window)", f"${total_cost:.4f}")
    m2.metric("Total Tokens", f"{total_tokens:,}")
    m3.metric("Avg Cost/Call", f"${avg_cost:.5f}")
    m4.metric("Monthly Projection", f"${monthly_projection:.2f}")

    st.divider()

    if HAS_PLOTLY:
        col1, col2 = st.columns(2)

        # Tokens by model — pie chart
        model_tokens: dict[str, int] = {}
        for e in entries:
            model_tokens[e.model] = model_tokens.get(e.model, 0) + (e.input_tokens + e.output_tokens)
        with col1:
            st.markdown("#### Tokens by Model")
            fig = px.pie(
                names=list(model_tokens.keys()),
                values=list(model_tokens.values()),
                hole=0.4,
            )
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

        # Cost by AI system — bar chart
        system_cost: dict[str, float] = {}
        for e in entries:
            system_cost[e.system_id] = system_cost.get(e.system_id, 0.0) + e.cost_usd
        with col2:
            st.markdown("#### Cost by AI System")
            fig2 = px.bar(
                x=list(system_cost.keys()),
                y=list(system_cost.values()),
                labels={"x": "System", "y": "Cost (USD)"},
                color=list(system_cost.values()),
                color_continuous_scale="Reds",
            )
            fig2.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

        # Daily cost trend — line chart
        st.markdown("#### Daily Cost Trend")
        daily_cost: dict[str, float] = {}
        for e in entries:
            day = e.timestamp[:10]
            daily_cost[day] = daily_cost.get(day, 0.0) + e.cost_usd
        days_sorted = sorted(daily_cost.keys())
        fig3 = px.line(
            x=days_sorted,
            y=[daily_cost[d] for d in days_sorted],
            labels={"x": "Date", "y": "Cost (USD)"},
            markers=True,
        )
        fig3.update_layout(margin=dict(t=0, b=20, l=0, r=0))
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Install plotly for charts: pip install plotly")

    # Top-10 most expensive calls
    st.markdown("#### Top 10 Most Expensive Calls")
    top10 = sorted(entries, key=lambda e: e.cost_usd, reverse=True)[:10]
    rows = []
    for e in top10:
        rows.append({
            "Entry ID": e.entry_id[:12] + "…",
            "System": e.system_id,
            "Model": e.model,
            "Tokens": e.input_tokens + e.output_tokens,
            "Cost (USD)": f"${e.cost_usd:.5f}",
            "Risk": e.risk_tier,
            "Time": e.timestamp[:19],
        })
    st.table(rows)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.title("🔒 AIAuditTrail — Compliance Operations Center")
    st.caption(
        "EU AI Act Article 12 · NIST AI RMF · Merkle-tree tamper detection · "
        "5 SDK integrations · Zero mandatory dependencies"
    )

    chain = _ensure_demo_chain()
    filters = render_sidebar(chain)

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📡 Live Audit Feed",
        "🔗 Chain Integrity",
        "🇪🇺 EU AI Act",
        "📊 NIST AI RMF",
        "🚨 Incidents",
        "💰 Cost Analytics",
    ])

    with tab1:
        render_live_feed(chain, filters)
    with tab2:
        render_chain_integrity(chain, filters)
    with tab3:
        render_eu_ai_act(chain, filters)
    with tab4:
        render_nist_rmf(chain)
    with tab5:
        render_incidents(chain)
    with tab6:
        render_cost_analytics(chain, filters)


if __name__ == "__main__":
    main()
