"""
Statutory Bail Pathways Reference Matrix — SIH26190 LegaDoc
Formal statutory taxonomy confirming the bail pathways across the 15 canonical crime types.
Adheres to the Code of Criminal Procedure (CrPC) / Bharatiya Nagarik Suraksha Sanhita (BNSS)
and special acts (NDPS, PMLA, POCSO).
"""

from typing import Dict, Any, List

BAIL_PATHWAYS_TAXONOMY: Dict[str, Dict[str, Any]] = {
    # 1. Domestic Violence (Showcase Case)
    "Domestic Violence": {
        "bailable_status": "Non-Bailable",
        "primary_statute": "Protection of Women from Domestic Violence Act, 2005 / Sec 498A IPC / Sec 85, 86 BNS",
        "jurisdiction_court": "Magistrate Court / Sessions Court (Fast Track Mahila Court)",
        "applicable_sections": "Sec 437 / 439 CrPC (Sec 480 / 483 BNSS)",
        "statutory_pathway": [
            "Arrest / Custody Surrender",
            "Bail Petition under Sec 437/439 CrPC with counseling report verification",
            "Judicial Hearing (Notice to Protection Officer & Complainant)",
            "Order Pronouncement (Grant with Non-Molestation/Restraining Conditions or Deny)",
            "Execution of Personal Bond & Verification of Local Surety"
        ],
        "special_conditions": "Mandatory residence prohibition orders; weapon surrender; protection order compliance."
    },

    # 2. Financial Cyberfraud / Cybercrime
    "Cybercrime": {
        "bailable_status": "Bailable / Non-Bailable based on quantum & Sec 66D IT Act / Sec 420 IPC / Sec 318 BNS",
        "primary_statute": "Information Technology Act, 2000 (Sec 43, 66, 66C, 66D) & Sec 420 IPC",
        "jurisdiction_court": "Chief Metropolitan Magistrate / Special Cyber Magistrate Court",
        "applicable_sections": "Sec 436 CrPC (if bailable offences < 3 yrs) or Sec 437 CrPC",
        "statutory_pathway": [
            "Arrest / Notice of Appearance under Sec 41A CrPC",
            "Bail Application with forensic device seizure proof",
            "Hearing with Bank/Intermediary Lien Status Report",
            "Bail Order (Grant subject to escrow deposit / device surrender)",
            "Surety Verification and Bank Guarantee Execution"
        ],
        "special_conditions": "Surrender of digital passports/passwords; restriction from electronic communication networks; asset lien maintenance."
    },

    # 3. Commercial Contraband Seizure (NDPS Act) - High Statutory Scrutiny
    "NDPS": {
        "bailable_status": "Strictly Non-Bailable (Stringent Statutory Bar)",
        "primary_statute": "Narcotic Drugs and Psychotropic Substances Act, 1985 (Sec 20(b)(ii)(C), 21, 27A, 29)",
        "jurisdiction_court": "Special Court (NDPS Act) / Sessions Court",
        "applicable_sections": "Sec 439 CrPC read with Mandatory Negative Twin Conditions under Section 37 NDPS Act",
        "statutory_pathway": [
            "Arrest with inventory panchnama under Sec 50 & 52A NDPS",
            "Bail Petition moved exclusively before Special NDPS Judge",
            "Mandatory Public Prosecutor Hearing Notice & Forensic FSL Chemical Report Review",
            "Judicial Satisfaction on Twin Conditions: (i) Reasonable grounds accused is not guilty, (ii) Unlikely to commit offence while on bail",
            "Pronouncement: Rejection (default for commercial quantity) or Rare Conditional Grant with substantial solvent sureties"
        ],
        "special_conditions": "Section 37 twin conditions satisfaction; bi-weekly reporting to NCB/Special Cell; strict travel ban."
    },

    # 4. Homicide / Grievous Hurt
    "Homicide": {
        "bailable_status": "Non-Bailable",
        "primary_statute": "Sec 302 / 304 / 307 IPC (Sec 103, 105, 109 BNS)",
        "jurisdiction_court": "Court of Session",
        "applicable_sections": "Sec 439 CrPC (High Court / Sessions Court inherent jurisdiction)",
        "statutory_pathway": [
            "Arrest & Judicial Remand",
            "Bail Petition filed in Court of Session under Sec 439 CrPC",
            "Formal Public Prosecutor Hearing with Case Diary & Post-Mortem / MLC Examination",
            "Judicial Determination considering gravity, weapon recovery (Sec 27 Evidence Act), and witness intimidation risk",
            "Bail Order Pronouncement & High-Value Solvency Surety Execution"
        ],
        "special_conditions": "No entry into victim's jurisdiction; daily/weekly police station reporting; passport surrender."
    },

    # 5. Financial Fraud & Money Laundering (PMLA)
    "Financial Fraud": {
        "bailable_status": "Non-Bailable (Twin Statutory Conditions under PMLA)",
        "primary_statute": "Sec 409, 420, 467, 471 IPC & Prevention of Money Laundering Act, 2002 (Sec 3/4)",
        "jurisdiction_court": "Special PMLA Court / Sessions Court",
        "applicable_sections": "Sec 439 CrPC read with Section 45(1) PMLA",
        "statutory_pathway": [
            "Arrest by Investigating Agency (ED / EOW)",
            "Special Bail Petition under Section 439 CrPC r/w Sec 45 PMLA",
            "Notice to Special Public Prosecutor & Enforcement Directorate",
            "Rigorous Evaluation of twin conditions (innocence test + no propensity to reoffend)",
            "Bail Order subject to heavy financial undertaking & ED appearance schedule",
            "Surety and Bank Guarantee Registration"
        ],
        "special_conditions": "Look-Out Circular (LOC) retention; freezing of all offshore and linked benami accounts; continuous IT attendance."
    },

    # 6. Theft & Burglary
    "Theft": {
        "bailable_status": "Bailable (Simple Theft Sec 379 IPC) / Non-Bailable (Dwelling House Sec 380 IPC / BNS 305)",
        "primary_statute": "Sec 379, 380, 457 IPC (Sec 303, 305 BNS)",
        "jurisdiction_court": "Judicial Magistrate First Class (JMFC) / Metropolitan Magistrate",
        "applicable_sections": "Sec 436 CrPC (if bailable) / Sec 437 CrPC (if non-bailable)",
        "statutory_pathway": [
            "Arrest & Property Recovery Panchnama",
            "Bail Petition under Sec 437 CrPC before Magistrate",
            "Verification of prior convictions / history sheet",
            "Bail Order (Usually granted upon satisfactory recovery of stolen property)",
            "Submission of Personal Bond and single local surety"
        ],
        "special_conditions": "Appearance on all trial dates; no alteration of property condition."
    },

    # 7. Armed Robbery & Dacoity
    "Robbery": {
        "bailable_status": "Non-Bailable",
        "primary_statute": "Sec 392, 395, 397 IPC (Sec 309, 310, 311 BNS)",
        "jurisdiction_court": "Court of Session",
        "applicable_sections": "Sec 437(1) / 439 CrPC",
        "statutory_pathway": [
            "Arrest & Test Identification Parade (TIP) initiation",
            "Bail Petition deferred until completion of TIP",
            "Judicial Hearing assessing violent weapon use and weapon seizure under Sec 27",
            "Bail Order (Strict evaluation; typically rejected prior to charge sheet filing)",
            "Execution of dual solvent sureties upon grant"
        ],
        "special_conditions": "Strict surveillance; exclusion from complainant commercial vicinity."
    },

    # 8. Sexual Assault & Rape
    "Sexual Assault": {
        "bailable_status": "Non-Bailable",
        "primary_statute": "Sec 376 IPC / Sec 64 BNS / POCSO Act (where applicable)",
        "jurisdiction_court": "Special Fast Track Court / Sessions Court",
        "applicable_sections": "Sec 437 / 439 CrPC (Mandatory victim intimation under Sec 439(1A) CrPC)",
        "statutory_pathway": [
            "Arrest & Accused/Victim Medical Examination (Sec 53A CrPC)",
            "Bail Petition under Sec 439 CrPC",
            "Mandatory statutory notice served to victim/informant under Sec 439(1A) CrPC",
            "Hearing with in-camera proceedings / victim legal aid representation",
            "Order Pronouncement with rigorous anti-intimidation stipulations",
            "Surety bond execution"
        ],
        "special_conditions": "Complete gag on victim identity; restraining radius (minimum 500 meters); electronic surveillance."
    },

    # 9. Acid Attack
    "Acid Attack": {
        "bailable_status": "Non-Bailable",
        "primary_statute": "Sec 326A, 326B IPC (Sec 124 BNS)",
        "jurisdiction_court": "Court of Session",
        "applicable_sections": "Sec 439 CrPC",
        "statutory_pathway": [
            "Arrest & Immediate Seizure of Corrosive Substance Chemical Logs",
            "Bail Petition filed in Court of Session",
            "Review of victim medical condition, burn percentages, and rehabilitative cost awards",
            "Order Pronouncement (Extremely stringent scrutiny; grant rare pre-trial)",
            "Execution of high monetary surety plus medical restitution guarantee"
        ],
        "special_conditions": "Monthly interim compensation payments to victim medical trust; prohibition from procuring regulated chemicals."
    },

    # 10. Road Accident / Rash Driving (Fatal / Non-Fatal)
    "Road Accident": {
        "bailable_status": "Bailable (Sec 279, 304A IPC / Sec 106(1) BNS)",
        "primary_statute": "Sec 279, 337, 304A IPC & Motor Vehicles Act (Sec 134, 184, 185)",
        "jurisdiction_court": "Judicial Magistrate / Traffic Court",
        "applicable_sections": "Sec 436 CrPC (Bail as a matter of right upon furnishing bond)",
        "statutory_pathway": [
            "Arrest / Station Bail appearance",
            "Submission of Personal Bail Bond under Sec 436 CrPC at Station or before Magistrate",
            "Mechanical Inspection Report (MIR) & Driving License/Insurance verification",
            "Immediate Release on furnishing statutory personal bond and insurance surety"
        ],
        "special_conditions": "Temporary suspension of driving license; compliance with Motor Accident Claims Tribunal (MACT) summons."
    },

    # 11. Public Corruption & Bribery
    "Public Corruption": {
        "bailable_status": "Non-Bailable",
        "primary_statute": "Prevention of Corruption Act, 1988 (Sec 7, 13) & Sec 120B IPC",
        "jurisdiction_court": "Special Judge (CBI / State Anti-Corruption Bureau)",
        "applicable_sections": "Sec 437 / 439 CrPC",
        "statutory_pathway": [
            "Trap arrest / Surrender with recovery of tainted currency (Phenolphthalein test)",
            "Bail Application before Special CBI/ACB Court",
            "Prosecution objection on sanction for prosecution (Sec 19 PC Act) and evidence tampering",
            "Bail Order considering public office suspension and document custody",
            "Surety submission with service record verification"
        ],
        "special_conditions": "Suspension from administrative posting; surrender of official files/devices; bar on accessing departmental premises."
    },

    # 12. Cyber Identity Theft
    "Cyber Identity Theft": {
        "bailable_status": "Bailable / Non-Bailable based on Sec 66C IT Act & Sec 419 IPC",
        "primary_statute": "Information Technology Act, 2000 (Sec 66C) & Sec 419 IPC",
        "jurisdiction_court": "Magistrate Court",
        "applicable_sections": "Sec 436 / 437 CrPC",
        "statutory_pathway": [
            "Arrest & Digital KYC Spoof Seizure",
            "Bail Petition with proof of non-commercial personal usage",
            "Review of telecom SIM issuance & IP login traces",
            "Bail Order with biometric verification conditions",
            "Surety Registration"
        ],
        "special_conditions": "Submission of authentic Aadhaar/PAN; bi-monthly biometric confirmation."
    },

    # 13. Organized Crime & Extortion
    "Organized Crime": {
        "bailable_status": "Strictly Non-Bailable (Statutory Bar under MCOCA / KCOCA / IPC 384, 386)",
        "primary_statute": "Special State Organized Crime Acts / Sec 384, 386, 120B IPC",
        "jurisdiction_court": "Special Designated Court",
        "applicable_sections": "Sec 439 CrPC read with Special Act Bail Bars (e.g. Sec 21 MCOCA)",
        "statutory_pathway": [
            "Arrest with prior approval of DIG/Commissioner rank officer",
            "Bail Application subjected to statutory bar (twin conditions & mandatory 180-day charge sheet leeway)",
            "Public Prosecutor in-camera objection on syndicated crime linkages",
            "Bail Determination (Grant strictly exceptional)",
            "High-security solvent surety registration"
        ],
        "special_conditions": "Round-the-clock GPS electronic tagging where available; complete prohibition from syndicate associates."
    },

    # 14. Kidnapping & Abduction
    "Kidnapping": {
        "bailable_status": "Non-Bailable",
        "primary_statute": "Sec 363, 364A, 365 IPC (Sec 137, 140 BNS)",
        "jurisdiction_court": "Court of Session",
        "applicable_sections": "Sec 437 / 439 CrPC",
        "statutory_pathway": [
            "Arrest & Victim Safe Rescue Panchnama",
            "Bail Petition under Sec 439 CrPC",
            "Judicial Hearing verifying statement of victim recorded under Sec 164 CrPC",
            "Bail Order (Evaluated on ransom demands and trauma risk)",
            "Execution of solvent family sureties"
        ],
        "special_conditions": "Absolute prohibition on approaching victim family or domicile; travel interdiction."
    },

    # 15. General Cognizable Offense
    "General Cognizable Offense": {
        "bailable_status": "Determined by First Schedule CrPC",
        "primary_statute": "Indian Penal Code / Bharatiya Nyaya Sanhita",
        "jurisdiction_court": "Jurisdictional Magistrate Court",
        "applicable_sections": "Sec 436 (Bailable) / Sec 437 (Non-Bailable) CrPC",
        "statutory_pathway": [
            "Arrest or Appearance under Sec 41A CrPC",
            "Bail Application before Magistrate",
            "Prosecution verification of criminal antecedents",
            "Bail Order pronounced",
            "Furnishing of Personal Bond and Surety"
        ],
        "special_conditions": "Standard trial attendance undertaking; peaceful conduct bond."
    }
}
