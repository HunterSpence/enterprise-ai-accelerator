# Enterprise AI Accelerator vs. Consulting Firm Tools

## The Problem

Big 4 and top consulting firms charge $500K–$5M for cloud transformation engagements.
The bulk of that cost is in activities that can be substantially automated:

| Activity | Manual Consulting Time | This Platform |
|----------|----------------------|---------------|
| Architecture assessment | 2–4 weeks (team of 4) | ~2 hours |
| Workload classification | 1–2 weeks (workshops) | ~30 minutes |
| Compliance gap analysis | 2–3 weeks | ~1 hour |
| Cost optimization review | 1–2 weeks | ~1 hour |
| Executive report | 3–5 days (PM/MD time) | ~10 minutes |

**This platform handles the 80% that's pattern-matching.**
Human expertise still wins the 20% that's judgment, relationships, and change management.

---

## vs. Accenture Cloud Migration Factory

**Accenture's offering:**
- Proprietary methodology + tooling
- Integrated with Accenture's managed services
- Requires Accenture team to operate
- Pricing: typically $500K–$2M for assessment + planning phase

**This platform:**
- Open source — modify, extend, integrate
- Runs in your environment (no vendor lock-in)
- Can be operated by a 1–2 person team
- Cost: Anthropic API costs (~$0.30–$1.00 per full analysis)

**Feature comparison:**

| Feature | Accenture CMF | This Platform |
|---------|--------------|---------------|
| Workload discovery | Manual workshops | Automated via inventory upload |
| 6R classification | Manual assessment | AI-automated per workload |
| Complexity scoring | Proprietary rubric | Claude-powered, explainable |
| Migration roadmap | Manual creation | Auto-generated with phases |
| Cost estimate | Accenture-internal | Integrated CostAnalyzer |
| Compliance check | Manual review | PolicyGuard automated |
| Executive report | PM-created | Auto-generated from data |
| Audit trail | Internal systems | Logged JSON output |
| Multi-cloud | AWS/Azure/GCP | AWS/Azure/GCP |
| Customizable | No | Yes (open source) |
| Integration | Accenture ecosystem | Jira, Slack, ServiceNow |

---

## vs. Deloitte Cloud Migration Factory

**Deloitte's offering:**
- Automation + methodology + managed services
- Strong Microsoft Azure integration
- Typically $500K–$5M per engagement

**Key differentiator of this platform:** Deloitte's factory still requires significant human touchpoints for each assessment phase. This platform treats each assessment as a template-driven pipeline that scales horizontally — one engineer can run 20 assessments simultaneously.

---

## vs. PwC's ChatPwC / AI Advisory

**PwC's offering:**
- ChatPwC: internal Claude deployment for 16,000+ staff
- AI advisory: help clients deploy AI
- Anthropic reseller: sell Claude to clients

**This platform's angle:** PwC has the distribution and trust. This platform has the
technical depth. A natural partnership — PwC could white-label this for client delivery.

---

## Competitive Advantages

1. **Speed**: Assessments in hours, not weeks
2. **Cost**: $1 per assessment vs. $500K+ per engagement  
3. **Transparency**: Every Claude call logged, every decision explainable
4. **Open Source**: Clients can audit, modify, and run independently
5. **Integration-ready**: Connects to existing enterprise tooling
6. **Multi-framework**: NIST AI RMF, SOC2, HIPAA, PCI-DSS, CIS AWS in one tool
7. **AWS MAP aligned**: Output maps to AWS Migration Acceleration Program phases

---

## Framework Alignment

### AWS Migration Acceleration Program (MAP)
MigrationScout phases align to MAP:
- Assess → CloudIQ + MigrationScout complexity scoring
- Mobilize → MigrationScout roadmap + PolicyGuard baseline
- Migrate → Migration execution tracking (roadmap)

### NIST AI Risk Management Framework
PolicyGuard maps controls to NIST AI RMF categories:
- Govern → IAM, policy, access controls
- Map → Asset inventory, risk identification
- Measure → Compliance scoring, continuous monitoring
- Manage → Remediation tracking, drift detection

### Azure Cloud Adoption Framework (CAF)
Supports Azure CAF phases:
- Strategy & Plan → CloudIQ + MigrationScout
- Ready → PolicyGuard baseline
- Govern → Ongoing PolicyGuard scans
