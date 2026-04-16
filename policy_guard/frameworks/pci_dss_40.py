"""
PCI DSS 4.0 — Payment Card Industry Data Security Standard
===========================================================
Source: PCI DSS v4.0 (March 2022); mandatory as of 31 March 2025
        PCI Security Standards Council (PCI SSC)

PCI DSS 4.0 introduces two implementation approaches:
  - Defined Approach: prescriptive requirements identical to PCI DSS 3.2.1 philosophy
  - Customized Approach: organizations can meet the Objective of each requirement
    using controls that differ from the defined approach

Structure: 12 Principal Requirements + sub-requirements
  Req 1:  Install and maintain network security controls
  Req 2:  Apply secure configurations to all system components
  Req 3:  Protect stored account data
  Req 4:  Protect cardholder data with strong cryptography during transmission
  Req 5:  Protect all systems and networks from malicious software
  Req 6:  Develop and maintain secure systems and software
  Req 7:  Restrict access to system components and cardholder data by business need to know
  Req 8:  Identify users and authenticate access to system components
  Req 9:  Restrict physical access to cardholder data
  Req 10: Log and monitor all access to system components and cardholder data
  Req 11: Test security of systems and networks regularly
  Req 12: Support information security with organizational policies and programs

Total controls catalogued: 83 sub-requirements
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional


# Approach constants
DEFINED = "Defined"
CUSTOMIZED = "Customized"
BOTH = "Both"


@dataclass
class PCIControl:
    """A PCI DSS 4.0 sub-requirement."""
    req_id: str              # e.g. "1.1.1"
    title: str
    description: str
    approach: str            # "Defined" | "Customized" | "Both"
    evidence_needed: list[str]
    weight: str              # critical / high / medium / low
    new_in_v4: bool = False  # True if requirement is new or significantly changed in v4.0


# ---------------------------------------------------------------------------
# Requirement 1: Network Security Controls
# ---------------------------------------------------------------------------

REQ1_CONTROLS: list[PCIControl] = [
    PCIControl("1.1.1", "Processes for network security controls are defined and understood",
        "Operational procedures and responsibilities for managing network security controls are documented, in use, and known to all affected parties.",
        BOTH, ["Network security management procedure", "Responsibility assignment records", "Staff acknowledgment"],
        "high"),
    PCIControl("1.2.1", "Configuration standards for network security controls",
        "Configuration standards are developed, implemented, and maintained to cover all network security control components.",
        BOTH, ["Network device configuration standards", "CIS Benchmark alignment evidence"],
        "high"),
    PCIControl("1.2.2", "Configuration management for network security controls",
        "All changes to network connections and to configurations of network security controls are approved by authorized personnel.",
        BOTH, ["Change approval records", "Change management procedure for network"],
        "medium"),
    PCIControl("1.2.3", "Network access control list between trusted and untrusted networks",
        "An accurate network diagram is maintained that shows all connections between the CDE and other networks.",
        BOTH, ["Current network diagram", "CDE boundary documentation"],
        "critical"),
    PCIControl("1.2.4", "Network diagram", "Current network diagram shows all connections and identifies all systems in-scope.",
        BOTH, ["Network diagram dated within 12 months", "CDE highlighted diagram"],
        "high"),
    PCIControl("1.2.5", "All services, protocols, and ports are identified and approved",
        "All allowed services, protocols, and ports are identified, approved, and have a defined business need.",
        BOTH, ["Approved services/ports list", "Business justification for each"],
        "high"),
    PCIControl("1.3.1", "Inbound traffic to CDE restricted",
        "Inbound traffic to the CDE is restricted to only that which is necessary.",
        BOTH, ["Firewall rule documentation", "Inbound traffic restriction evidence"],
        "critical"),
    PCIControl("1.3.2", "Outbound traffic from CDE restricted",
        "Outbound traffic from the CDE is restricted to only that which is necessary.",
        BOTH, ["Outbound firewall rule documentation", "Egress restriction evidence"],
        "critical"),
    PCIControl("1.3.3", "NSC between CDE and DMZ",
        "Network security controls are implemented between all networks.",
        BOTH, ["DMZ configuration", "NSC between network zones documentation"],
        "high"),
    PCIControl("1.4.1", "Wireless networks separated from CDE",
        "If wireless networks are connected to or can access the CDE, security controls are implemented.",
        BOTH, ["Wireless network segmentation documentation", "Wireless isolation evidence"],
        "high"),
    PCIControl("1.4.2", "Wireless network packet filtering",
        "Wireless networks use traffic filtering between wireless networks and the CDE.",
        BOTH, ["Wireless traffic filtering configuration"],
        "medium"),
    PCIControl("1.5.1", "Protect against threats from personal devices",
        "Security controls are implemented on any computing devices that connect to both untrusted networks and the CDE.",
        DEFINED, ["Personal device policy", "MDM/endpoint controls for personal devices"],
        "high", new_in_v4=True),
]

# ---------------------------------------------------------------------------
# Requirement 2: Secure Configurations
# ---------------------------------------------------------------------------

REQ2_CONTROLS: list[PCIControl] = [
    PCIControl("2.1.1", "Configuration management processes documented",
        "Processes and mechanisms for applying secure configurations are defined and understood.",
        BOTH, ["Configuration management procedure", "Secure configuration standard"],
        "high"),
    PCIControl("2.2.1", "Vendor default passwords changed",
        "All vendor-supplied defaults are changed before system components are installed on the network.",
        BOTH, ["Default password change records", "System hardening checklist"],
        "critical"),
    PCIControl("2.2.2", "Unnecessary services/protocols/functions disabled",
        "Vendor default accounts that are not used are either removed or disabled.",
        BOTH, ["Unused account removal records", "Service inventory with disabled status"],
        "high"),
    PCIControl("2.2.3", "Wireless environments configured securely",
        "All wireless vendor defaults are changed where applicable.",
        BOTH, ["Wireless hardening checklist", "Wireless default change records"],
        "high"),
    PCIControl("2.2.4", "Only necessary services enabled",
        "All unnecessary services, functions, ports, protocols, and components are disabled.",
        BOTH, ["Enabled services justification", "Hardening benchmark alignment"],
        "high"),
    PCIControl("2.2.5", "Insecure protocols documented with business justification",
        "If any insecure services, protocols, or ports are present, the business need is documented and security features implemented.",
        BOTH, ["Insecure protocol register with justification", "Compensating controls documentation"],
        "medium"),
    PCIControl("2.2.6", "System security parameters prevent misuse",
        "System configuration standards address prevention of known security vulnerabilities.",
        BOTH, ["Hardening standards", "Known vulnerability mitigation evidence"],
        "high"),
    PCIControl("2.2.7", "Non-console administrative access encrypted",
        "All non-console administrative access is encrypted using strong cryptography.",
        BOTH, ["SSH/TLS for admin access configuration", "No telnet/unencrypted admin access"],
        "critical"),
    PCIControl("2.3.1", "Wireless environment encryption",
        "Wireless environments transmit cardholder data using strong cryptography.",
        BOTH, ["WPA3 or WPA2-Enterprise configuration", "Wireless encryption audit"],
        "critical"),
    PCIControl("2.3.2", "Wireless environment default settings changed",
        "For wireless environments connected to the CDE or transmitting account data, wireless encryption keys are changed when anyone with knowledge of the keys leaves.",
        BOTH, ["Key rotation procedure for wireless", "Key rotation records on personnel change"],
        "high", new_in_v4=True),
]

# ---------------------------------------------------------------------------
# Requirement 3: Protect Stored Account Data
# ---------------------------------------------------------------------------

REQ3_CONTROLS: list[PCIControl] = [
    PCIControl("3.1.1", "Stored data retention policies defined",
        "Processes for protection of stored account data are defined and understood.",
        BOTH, ["Data retention and disposal policy", "Account data inventory"],
        "high"),
    PCIControl("3.2.1", "SAD not stored after authorization",
        "Account data storage is kept to a minimum. Sensitive authentication data (SAD) is not stored after authorization.",
        BOTH, ["SAD storage prohibition controls", "Data scan results confirming no SAD"],
        "critical"),
    PCIControl("3.3.1", "SAD elements not retained after authorization",
        "Full track data, card verification codes, and PINs are not retained after authorization.",
        BOTH, ["Log review showing no SAD", "Application SAD scrubbing evidence"],
        "critical"),
    PCIControl("3.3.2", "Issuers may store SAD with protection",
        "SAD stored by issuers is encrypted with strong cryptography.",
        BOTH, ["SAD encryption for issuers", "Encryption key management records"],
        "critical"),
    PCIControl("3.3.3", "Encryption of stored SAD",
        "Any SAD stored is encrypted with strong cryptography.",
        BOTH, ["SAD encryption configuration", "Encryption key management"],
        "critical", new_in_v4=True),
    PCIControl("3.4.1", "PAN masked when displayed",
        "PAN is masked when displayed so that only personnel with a legitimate business need can see more than first six/last four digits.",
        BOTH, ["PAN masking configuration", "Screen capture of masked display"],
        "high"),
    PCIControl("3.4.2", "No copy/move of PAN without authorization",
        "When used in remote-access technologies, copy and/or relocation of PAN is prevented.",
        BOTH, ["Copy prevention controls", "Remote access PAN protection evidence"],
        "high", new_in_v4=True),
    PCIControl("3.5.1", "PAN secured with strong cryptography",
        "PAN is secured with strong cryptography wherever stored.",
        BOTH, ["PAN encryption configuration", "Encryption algorithm documentation (AES-256 etc.)"],
        "critical"),
    PCIControl("3.5.1.2", "Disk/partition encryption for PAN",
        "Disk-level or partition-level encryption for PAN storage with key management per 3.7.",
        DEFINED, ["Disk encryption configuration", "Key management for disk encryption"],
        "critical", new_in_v4=True),
    PCIControl("3.6.1", "Cryptographic keys for PAN protection managed",
        "Key management procedures and processes for cryptographic keys include generation, distribution, storage, and retirement.",
        BOTH, ["Key management policy", "Key lifecycle documentation"],
        "critical"),
    PCIControl("3.7.1", "Key management policies implemented",
        "Key management policies cover key generation using approved technology.",
        BOTH, ["Key generation procedure using FIPS-validated RNG", "Key management lifecycle records"],
        "critical"),
]

# ---------------------------------------------------------------------------
# Requirement 4: Protect Transmission of Cardholder Data
# ---------------------------------------------------------------------------

REQ4_CONTROLS: list[PCIControl] = [
    PCIControl("4.1.1", "Processes for secure transmission documented",
        "Processes for protection of PAN during transmission are defined and understood.",
        BOTH, ["Transmission security policy", "Encryption in transit standards"],
        "high"),
    PCIControl("4.2.1", "Strong cryptography for PAN transmission",
        "Strong cryptography is used to safeguard PAN during transmission over open, public networks.",
        BOTH, ["TLS 1.2+ configuration", "Cipher suite documentation", "No weak protocols (SSL/early TLS)"],
        "critical"),
    PCIControl("4.2.1.1", "Inventory of trusted keys/certificates",
        "An inventory of trusted keys and certificates used to protect PAN during transmission is maintained.",
        BOTH, ["Certificate inventory", "Certificate management records"],
        "medium", new_in_v4=True),
    PCIControl("4.2.2", "PAN secured in transit via end-user messaging",
        "PAN is secured when sent via end-user messaging technologies.",
        BOTH, ["Messaging encryption controls", "Policy prohibiting unencrypted PAN in email/messaging"],
        "high"),
]

# ---------------------------------------------------------------------------
# Requirement 5: Protect Against Malicious Software
# ---------------------------------------------------------------------------

REQ5_CONTROLS: list[PCIControl] = [
    PCIControl("5.1.1", "Processes for malware protection documented",
        "Processes for malware protection are defined and understood.",
        BOTH, ["Malware protection policy", "AV management procedure"],
        "high"),
    PCIControl("5.2.1", "Antimalware deployed on all applicable components",
        "Antimalware solution is deployed on all system components except those identified as not at risk.",
        BOTH, ["Antimalware deployment inventory", "Coverage verification"],
        "critical"),
    PCIControl("5.2.2", "Antimalware solution detects all known types of malware",
        "The deployed antimalware solution detects all known types of malicious software.",
        BOTH, ["AV capability documentation", "Malware detection test results"],
        "high"),
    PCIControl("5.2.3", "Systems not at risk assessed periodically",
        "For systems considered not at risk for malware, periodic evaluation determines if they remain not at risk.",
        BOTH, ["Risk assessment for malware exclusions", "Periodic evaluation records"],
        "medium", new_in_v4=True),
    PCIControl("5.3.1", "Antimalware solution kept current",
        "Antimalware solution is kept current via automatic updates.",
        BOTH, ["AV update configuration", "Update frequency evidence"],
        "critical"),
    PCIControl("5.3.2", "Antimalware performs periodic scans",
        "Antimalware mechanism performs scans and generates audit logs.",
        BOTH, ["Scheduled scan configuration", "Scan log evidence"],
        "high"),
    PCIControl("5.4.1", "Phishing protection mechanisms in use",
        "Processes are in place to detect and protect personnel against phishing attacks.",
        BOTH, ["Anti-phishing controls", "Security awareness training covering phishing"],
        "high", new_in_v4=True),
]

# ---------------------------------------------------------------------------
# Requirement 6: Develop and Maintain Secure Systems and Software
# ---------------------------------------------------------------------------

REQ6_CONTROLS: list[PCIControl] = [
    PCIControl("6.1.1", "Secure development processes documented",
        "Processes for bespoke and custom software are defined and understood.",
        BOTH, ["Secure SDLC policy", "Developer training records"],
        "high"),
    PCIControl("6.2.1", "Bespoke software developed securely",
        "Bespoke and custom software are developed securely per secure coding guidelines.",
        BOTH, ["Secure coding standards", "Code review records", "OWASP alignment evidence"],
        "high"),
    PCIControl("6.2.2", "Software developers receive training",
        "Software development personnel receive training on secure coding at least annually.",
        BOTH, ["Annual secure coding training completion records"],
        "medium"),
    PCIControl("6.2.3", "Code review for bespoke software",
        "All bespoke and custom software are reviewed to identify and remediate vulnerabilities before production.",
        BOTH, ["Code review process", "Pre-production code review records"],
        "high"),
    PCIControl("6.2.4", "Software engineering techniques for attack prevention",
        "Software engineering techniques or other methods are defined and in use to prevent or mitigate common software attacks.",
        BOTH, ["SAST/DAST tool usage", "Vulnerability prevention evidence"],
        "high", new_in_v4=True),
    PCIControl("6.3.1", "Security vulnerabilities identified and managed",
        "Security vulnerabilities are identified and managed.",
        BOTH, ["Vulnerability management program", "Vulnerability tracking records"],
        "critical"),
    PCIControl("6.3.2", "Inventory of bespoke and third-party software",
        "An inventory of bespoke and custom software and third-party software components is maintained.",
        BOTH, ["Software component inventory (SBOM)", "Third-party library inventory"],
        "high", new_in_v4=True),
    PCIControl("6.3.3", "All components protected from known vulnerabilities",
        "All system components are protected from known vulnerabilities by installing applicable security patches/updates.",
        BOTH, ["Patch management SLA", "Critical patch timeline compliance"],
        "critical"),
    PCIControl("6.4.1", "Web-facing applications protected against attacks",
        "For public-facing web applications, web application attacks are prevented.",
        BOTH, ["WAF deployment and configuration", "Web app pen test results"],
        "critical"),
    PCIControl("6.4.2", "Automated solution detects web application attacks",
        "For public-facing web applications, an automated technical solution detects and prevents web-based attacks.",
        BOTH, ["WAF in prevention mode configuration", "Alert monitoring records"],
        "high"),
    PCIControl("6.4.3", "Payment page scripts managed and authorized",
        "All payment page scripts that are loaded and executed in the consumer browser are managed.",
        BOTH, ["Payment page script inventory", "Script authorization records"],
        "critical", new_in_v4=True),
    PCIControl("6.5.1", "Changes to system components managed securely",
        "Changes to all system components are managed securely.",
        BOTH, ["Change management procedure", "Pre- and post-change testing records"],
        "high"),
]

# ---------------------------------------------------------------------------
# Requirement 7: Restrict Access to System Components and Cardholder Data
# ---------------------------------------------------------------------------

REQ7_CONTROLS: list[PCIControl] = [
    PCIControl("7.1.1", "Access control model defined",
        "Processes for restricting access are defined and understood.",
        BOTH, ["Access control policy", "Role-based access model documentation"],
        "high"),
    PCIControl("7.2.1", "Access control model implemented",
        "Access to system components and data is appropriately defined and assigned to individuals.",
        BOTH, ["RBAC implementation evidence", "Access rights matrix"],
        "critical"),
    PCIControl("7.2.2", "Access assigned with least privilege",
        "Access is assigned to users, including privileged users, based on least privilege.",
        BOTH, ["Least privilege access reviews", "Privilege escalation justification records"],
        "critical"),
    PCIControl("7.2.3", "Required privileges approved by authorized personnel",
        "Required privilege levels are approved by authorized personnel.",
        BOTH, ["Privilege approval records", "Access authorization workflow"],
        "high"),
    PCIControl("7.2.4", "All user accounts managed",
        "All user accounts and related access privileges are reviewed at least once every six months.",
        BOTH, ["Semi-annual access review records", "Terminated/transferred user access records"],
        "high"),
    PCIControl("7.2.5", "Accounts for system and application components managed",
        "All application and system accounts and related access privileges are assigned and managed.",
        BOTH, ["Service account inventory", "Service account access reviews"],
        "high", new_in_v4=True),
    PCIControl("7.3.1", "Access control system in place",
        "An access control system is in place that restricts access based on a user's need to know.",
        BOTH, ["IAM system documentation", "Need-to-know enforcement evidence"],
        "critical"),
]

# ---------------------------------------------------------------------------
# Requirement 8: Identify Users and Authenticate Access
# ---------------------------------------------------------------------------

REQ8_CONTROLS: list[PCIControl] = [
    PCIControl("8.1.1", "Processes for identification and authentication documented",
        "Processes for identification and authentication are defined and understood.",
        BOTH, ["IAM policy", "Authentication standards documentation"],
        "high"),
    PCIControl("8.2.1", "All user IDs and credentials are managed",
        "All users are assigned a unique ID before allowing them to access system components or cardholder data.",
        BOTH, ["Unique ID assignment procedure", "Shared account prohibition evidence"],
        "critical"),
    PCIControl("8.2.2", "Group/shared accounts managed with exceptions",
        "Group, shared, or generic accounts or other shared authentication credentials are only used when necessary.",
        BOTH, ["Shared account exception process", "Shared account inventory"],
        "high"),
    PCIControl("8.3.1", "Authenticate all users",
        "All user access to system components is authenticated.",
        BOTH, ["Authentication configuration", "No unauthenticated access evidence"],
        "critical"),
    PCIControl("8.3.6", "Password complexity requirements",
        "If passwords are used as authentication factors, they meet minimum complexity requirements.",
        BOTH, ["Password policy with complexity requirements", "Technical enforcement configuration"],
        "high"),
    PCIControl("8.3.9", "Passwords changed at least every 90 days",
        "If passwords are used as authentication factors for users, passwords are changed at least once every 90 days.",
        DEFINED, ["Password expiry configuration", "90-day rotation enforcement"],
        "medium"),
    PCIControl("8.4.1", "MFA for administrator access to CDE",
        "MFA is implemented for all non-console access into the CDE for personnel with administrative access.",
        BOTH, ["MFA configuration for admins", "Admin MFA enrollment records"],
        "critical"),
    PCIControl("8.4.2", "MFA for all non-console CDE access",
        "MFA is implemented for all access into the CDE.",
        BOTH, ["MFA for all CDE users", "MFA enforcement configuration"],
        "critical", new_in_v4=True),
    PCIControl("8.5.1", "MFA systems implemented securely",
        "MFA systems are implemented securely.",
        BOTH, ["MFA solution security documentation", "MFA implementation review"],
        "high", new_in_v4=True),
    PCIControl("8.6.1", "Accounts used by systems managed securely",
        "If accounts used by systems or applications can be used for interactive login, they are managed.",
        BOTH, ["Interactive login restriction for service accounts", "Service account controls"],
        "high", new_in_v4=True),
]

# ---------------------------------------------------------------------------
# Requirement 9: Restrict Physical Access to Cardholder Data
# ---------------------------------------------------------------------------

REQ9_CONTROLS: list[PCIControl] = [
    PCIControl("9.1.1", "Physical access control processes documented",
        "Processes for physical access are defined and understood.",
        BOTH, ["Physical access policy", "CDE physical security standards"],
        "high"),
    PCIControl("9.2.1", "Appropriate physical access controls",
        "Controls are implemented to restrict physical access to the CDE.",
        BOTH, ["Physical access control system", "Badge access records for CDE"],
        "critical"),
    PCIControl("9.3.1", "Physical access procedures for personnel",
        "Physical access to the CDE is authorized based on individual job function.",
        BOTH, ["Physical access authorization list", "Access review records"],
        "high"),
    PCIControl("9.4.1", "Media with cardholder data secured",
        "All media with cardholder data is physically secured.",
        BOTH, ["Secure media storage documentation", "Media access log"],
        "high"),
    PCIControl("9.4.2", "Media containing cardholder data classified",
        "All media with cardholder data is classified.",
        BOTH, ["Media classification procedure", "Labeled media inventory"],
        "medium"),
    PCIControl("9.4.5", "Inventory logs of all electronic media maintained",
        "Inventory logs of electronic media containing cardholder data are maintained.",
        BOTH, ["Electronic media inventory log", "Annual media inventory results"],
        "medium"),
    PCIControl("9.5.1", "POI devices protected from tampering",
        "Physical security controls are implemented to protect point-of-interaction (POI) devices.",
        BOTH, ["POI device inspection records", "Anti-tampering procedure"],
        "critical"),
]

# ---------------------------------------------------------------------------
# Requirement 10: Log and Monitor All Access
# ---------------------------------------------------------------------------

REQ10_CONTROLS: list[PCIControl] = [
    PCIControl("10.1.1", "Logging processes documented",
        "Processes for logging and monitoring are defined and understood.",
        BOTH, ["Log management policy", "Monitoring procedure"],
        "high"),
    PCIControl("10.2.1", "Audit logs capture all required events",
        "Audit logs are enabled and active for all system components in the CDE.",
        BOTH, ["Audit log enablement evidence", "Event types logged per PCI DSS"],
        "critical"),
    PCIControl("10.2.1.1", "All individual user access to cardholder data logged",
        "Individual user access to cardholder data is logged.",
        BOTH, ["User access logging for CDE", "Sample log evidence"],
        "critical"),
    PCIControl("10.2.1.7", "All access of all system components by root or admin logged",
        "Root or administrator access to system components is logged.",
        BOTH, ["Privileged access logging", "Admin action audit trail"],
        "critical"),
    PCIControl("10.3.1", "Audit log files protected from destruction",
        "Read access to audit log files is limited to those with a job-related need.",
        BOTH, ["Log file access restriction", "Log integrity protection evidence"],
        "high"),
    PCIControl("10.3.2", "Audit log files protected from modifications",
        "Audit log files are protected to prevent modifications by individuals.",
        BOTH, ["Log tamper protection", "WORM storage or log signing evidence"],
        "critical"),
    PCIControl("10.4.1", "Audit logs reviewed to identify anomalies",
        "The following audit logs are reviewed at least once daily.",
        BOTH, ["Daily log review records", "SIEM alert configuration", "SOC review evidence"],
        "critical"),
    PCIControl("10.5.1", "Audit log history retained 12 months",
        "Retain audit log history for at least 12 months, with at least three months available for immediate analysis.",
        BOTH, ["Log retention configuration (12 months)", "90-day online availability evidence"],
        "critical"),
    PCIControl("10.6.1", "Time synchronization mechanisms in use",
        "System clocks and time are synchronized using time-synchronization technology.",
        BOTH, ["NTP configuration", "Time synchronization evidence"],
        "medium"),
    PCIControl("10.7.1", "Failures of critical security controls detected and reported",
        "Failures of critical security controls are detected and responded to promptly.",
        BOTH, ["Security control failure alerting", "Response procedure"],
        "high", new_in_v4=True),
]

# ---------------------------------------------------------------------------
# Requirement 11: Test Security of Systems and Networks
# ---------------------------------------------------------------------------

REQ11_CONTROLS: list[PCIControl] = [
    PCIControl("11.1.1", "Security testing processes documented",
        "Processes for security testing are defined and understood.",
        BOTH, ["Security testing policy", "Test plan template"],
        "high"),
    PCIControl("11.2.1", "Authorized and unauthorized wireless access points managed",
        "Authorized and unauthorized wireless access points are managed.",
        BOTH, ["Wireless AP inventory", "Rogue AP detection evidence"],
        "high"),
    PCIControl("11.3.1", "Internal vulnerability scans performed quarterly",
        "Internal vulnerability scans are performed via authenticated scanning at least quarterly.",
        BOTH, ["Quarterly internal scan results", "Authenticated scan configuration"],
        "critical"),
    PCIControl("11.3.2", "External vulnerability scans performed quarterly by ASV",
        "External vulnerability scans are performed at least quarterly by a PCI SSC Approved Scanning Vendor (ASV).",
        BOTH, ["Quarterly ASV scan reports", "Passing ASV scan certificates"],
        "critical"),
    PCIControl("11.4.1", "Penetration testing methodology defined",
        "A penetration testing methodology is defined, documented, and implemented.",
        BOTH, ["Pen test methodology document", "Scope definition"],
        "high"),
    PCIControl("11.4.2", "Internal penetration testing performed",
        "Internal penetration testing is performed at least annually and after significant changes.",
        BOTH, ["Annual internal pen test results", "Post-change pen test evidence"],
        "critical"),
    PCIControl("11.4.3", "External penetration testing performed",
        "External penetration testing is performed at least annually.",
        BOTH, ["Annual external pen test results", "Findings remediation records"],
        "critical"),
    PCIControl("11.5.1", "Network intrusion detection in use",
        "Intrusion-detection and/or intrusion-prevention techniques are used to detect and/or prevent intrusions into the network.",
        BOTH, ["IDS/IPS deployment evidence", "Alert tuning records"],
        "critical"),
    PCIControl("11.6.1", "Change and tamper detection mechanism for payment pages",
        "A change- and tamper-detection mechanism is deployed to alert personnel to unauthorized modification of payment pages.",
        BOTH, ["SRI or CSP deployment", "Payment page integrity monitoring"],
        "critical", new_in_v4=True),
]

# ---------------------------------------------------------------------------
# Requirement 12: Support Information Security with Organizational Policies
# ---------------------------------------------------------------------------

REQ12_CONTROLS: list[PCIControl] = [
    PCIControl("12.1.1", "Information security policy documented",
        "An overall information security policy is established, published, maintained, and distributed.",
        BOTH, ["Information security policy", "Annual review records", "Distribution evidence"],
        "critical"),
    PCIControl("12.1.2", "Information security roles and responsibilities defined",
        "Information security roles and responsibilities are defined and understood.",
        BOTH, ["Security roles and responsibilities documentation", "RACI for security"],
        "high"),
    PCIControl("12.2.1", "Acceptable use policies defined for end-user technologies",
        "Acceptable use policies for end-user technologies are documented and implemented.",
        BOTH, ["Acceptable use policy", "User acknowledgment records"],
        "medium"),
    PCIControl("12.3.1", "Risk assessment process defined",
        "Each targeted risk analysis required by PCI DSS is documented to include: identified threats, likelihood, impact.",
        BOTH, ["Annual risk assessment", "Risk methodology documentation"],
        "high", new_in_v4=True),
    PCIControl("12.4.1", "PCI DSS compliance managed",
        "Responsibilities for managing PCI DSS activities are assigned to an executive leadership role.",
        BOTH, ["Executive PCI owner designation", "Compliance management records"],
        "high"),
    PCIControl("12.5.1", "Inventory of system components in scope",
        "An inventory of all in-scope system components is maintained.",
        BOTH, ["In-scope component inventory", "CDE scope documentation"],
        "critical"),
    PCIControl("12.5.2", "PCI DSS scope documented and confirmed",
        "PCI DSS scope is documented and confirmed at least once every 12 months and after significant changes.",
        BOTH, ["Annual scope review records", "Scope confirmation documentation"],
        "high"),
    PCIControl("12.6.1", "Security awareness program in place",
        "A security awareness program is implemented for all personnel.",
        BOTH, ["Security awareness program materials", "Annual training completion records"],
        "high"),
    PCIControl("12.7.1", "Personnel screened prior to hire",
        "Personnel are screened before hire to minimize the risk of attacks from internal sources.",
        BOTH, ["Background check policy", "Pre-hire screening records"],
        "high"),
    PCIControl("12.8.1", "Policies for third-party service providers documented",
        "Policies and procedures are maintained to manage the risks from TPSPs.",
        BOTH, ["TPSP risk management policy", "TPSP inventory"],
        "critical"),
    PCIControl("12.8.2", "Written agreements with TPSPs acknowledging PCI responsibility",
        "Written agreements with all TPSPs acknowledge that they are responsible for security of data.",
        BOTH, ["TPSP agreement template", "Signed TPSP agreements"],
        "critical"),
    PCIControl("12.8.4", "Program to monitor TPSP compliance status",
        "A program is in place to monitor the PCI DSS compliance status of TPSPs at least annually.",
        BOTH, ["TPSP compliance monitoring procedure", "Annual TPSP AOC collection records"],
        "critical"),
    PCIControl("12.9.1", "TPSPs provide written acknowledgment of cardholder data responsibility",
        "TPSPs provide written acknowledgment that they are responsible for the security of cardholder data.",
        BOTH, ["TPSP responsibility acknowledgment records"],
        "high"),
    PCIControl("12.10.1", "Incident response plan in place and tested",
        "An incident response plan exists and is ready to be activated in the event of a cardholder data breach.",
        BOTH, ["PCI incident response plan", "Annual IRP test records"],
        "critical"),
    PCIControl("12.10.4", "Personnel handling incidents trained",
        "Personnel involved in incident response are periodically trained.",
        BOTH, ["IRP training records", "Tabletop exercise completion evidence"],
        "high"),
]


# ---------------------------------------------------------------------------
# Unified catalog
# ---------------------------------------------------------------------------

ALL_CONTROLS: list[PCIControl] = (
    REQ1_CONTROLS + REQ2_CONTROLS + REQ3_CONTROLS + REQ4_CONTROLS +
    REQ5_CONTROLS + REQ6_CONTROLS + REQ7_CONTROLS + REQ8_CONTROLS +
    REQ9_CONTROLS + REQ10_CONTROLS + REQ11_CONTROLS + REQ12_CONTROLS
)

CONTROL_INDEX: dict[str, PCIControl] = {c.req_id: c for c in ALL_CONTROLS}

NEW_IN_V4_CONTROLS: list[PCIControl] = [c for c in ALL_CONTROLS if c.new_in_v4]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PCIFinding:
    req_id: str
    title: str
    status: str
    severity: str
    approach: str
    new_in_v4: bool
    details: str
    remediation: str


@dataclass
class PCIReport:
    controls_total: int
    controls_passing: int
    controls_failing: int
    new_v4_controls_failing: int
    findings: list[PCIFinding]
    compliance_score: float = 0.0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    def compute(self) -> None:
        self.total_findings = len([f for f in self.findings if f.status == "FAIL"])
        self.critical_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "CRITICAL"])
        self.high_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "HIGH"])
        self.medium_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "MEDIUM"])
        self.low_count = len([f for f in self.findings if f.status == "FAIL" and f.severity == "LOW"])
        total = self.controls_passing + self.controls_failing
        self.compliance_score = (self.controls_passing / total * 100) if total > 0 else 0.0


def _severity_for_weight(weight: str) -> str:
    return {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(weight, "MEDIUM")


# ---------------------------------------------------------------------------
# Mock state — simulate a card processor with partial compliance
# ---------------------------------------------------------------------------

MOCK_PCI_STATE: dict[str, bool] = {}
for _ctrl in ALL_CONTROLS:
    # Simulate established controls for basic requirements; gaps in newer v4 and crypto
    _MOCK_PASS = (
        _ctrl.req_id in {
            "1.2.3", "1.2.4", "2.2.1", "3.2.1", "4.2.1", "5.2.1", "5.3.1",
            "8.2.1", "8.3.1", "9.2.1", "10.2.1", "10.5.1", "11.3.1", "11.3.2",
            "12.1.1", "12.6.1", "12.10.1",
        } and not _ctrl.new_in_v4
    )
    MOCK_PCI_STATE[_ctrl.req_id] = _MOCK_PASS


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class PCIScanner:
    """PCI DSS 4.0 scanner — 12 principal requirements, 83 sub-requirements."""

    def __init__(self, mock: bool = True) -> None:
        self.mock = mock

    async def scan(self) -> PCIReport:
        await asyncio.sleep(0)
        state = MOCK_PCI_STATE if self.mock else {}
        findings: list[PCIFinding] = []
        passing = 0
        failing = 0
        new_v4_failing = 0

        for ctrl in ALL_CONTROLS:
            passed = state.get(ctrl.req_id, False)
            severity = _severity_for_weight(ctrl.weight)

            if passed:
                passing += 1
            else:
                failing += 1
                if ctrl.new_in_v4:
                    new_v4_failing += 1
                findings.append(PCIFinding(
                    req_id=ctrl.req_id,
                    title=ctrl.title,
                    status="FAIL",
                    severity=severity,
                    approach=ctrl.approach,
                    new_in_v4=ctrl.new_in_v4,
                    details=(
                        f"[PCI DSS 4.0 Req {ctrl.req_id}] {ctrl.title} — Not implemented. "
                        f"{'[NEW IN v4.0] ' if ctrl.new_in_v4 else ''}"
                        f"Missing: {', '.join(ctrl.evidence_needed)}"
                    ),
                    remediation=(
                        f"To satisfy PCI DSS 4.0 Req {ctrl.req_id} ({ctrl.approach} Approach), create:\n"
                        + "\n".join(f"  - {e}" for e in ctrl.evidence_needed)
                    ),
                ))

        report = PCIReport(
            controls_total=len(ALL_CONTROLS),
            controls_passing=passing,
            controls_failing=failing,
            new_v4_controls_failing=new_v4_failing,
            findings=findings,
        )
        report.compute()
        return report


class PCIFramework:
    """Sync wrapper for test compatibility."""

    def run_assessment(self) -> PCIReport:
        scanner = PCIScanner(mock=True)
        return asyncio.run(scanner.scan())
