"""
Authoritative seed data for SIH26190 Secure Digital Document Management System.
Provisions canonical system permissions, authoritative system roles, and
pre-registered official government accounts.
"""

from app import models, security

CANONICAL_PERMISSIONS = [
    # Cases
    {"code": "cases:read", "name": "Read Cases", "category": "cases", "description": "View case dockets in jurisdiction"},
    {"code": "cases:create", "name": "Create FIR / Case", "category": "cases", "description": "Register First Information Report"},
    {"code": "cases:assign", "name": "Assign IO", "category": "cases", "description": "Assign investigating officer to case"},
    {"code": "cases:diary_write", "name": "Append Case Diary", "category": "cases", "description": "Append Section 172 case diary notes"},
    
    # Documents
    {"code": "documents:read", "name": "Read Documents", "category": "documents", "description": "Read role-scoped sanitized documents"},
    {"code": "documents:upload", "name": "Upload Documents", "category": "documents", "description": "Ingest evidentiary records with SHA-256 hash"},
    {"code": "documents:correct_redaction", "name": "Correct AI Redaction", "category": "documents", "description": "Submit officer correction tags"},

    # Evidence Requests
    {"code": "evidence:request_create", "name": "Create Section 91 Requisition", "category": "evidence_requests", "description": "Dispatch evidence requests to banks, labs, telecom"},
    {"code": "evidence:fulfill_submit", "name": "Fulfill Requisition", "category": "evidence_requests", "description": "Upload certified forensic/bank records"},

    # Bail & Defense
    {"code": "bail:apply", "name": "Apply for Bail", "category": "bail", "description": "Submit bail petition under Section 437/439 CrPC"},
    {"code": "bail:order", "name": "Issue Judicial Bail Order", "category": "bail", "description": "Pronounce bail grant, interim, or rejection orders"},
    {"code": "bail:surety_submit", "name": "Submit Surety Bond", "category": "bail", "description": "Register surety undertaking documentation"},

    # Judiciary & Prosecution
    {"code": "judiciary:hearings_schedule", "name": "Schedule Trial Hearing", "category": "judiciary", "description": "Publish hearing dates and issue summons"},
    {"code": "judiciary:unredacted_view", "name": "Unredacted Judicial Review", "category": "judiciary", "description": "Inspect unredacted documents with full audit trail"},
    {"code": "judiciary:charge_sheet_file", "name": "File Charge Sheet", "category": "judiciary", "description": "Prosecutor submit Section 173 charge sheet"},

    # Administration
    {"code": "admin:roles_manage", "name": "Manage Roles & Permissions", "category": "admin", "description": "Create roles, assign permissions, manage users"},
    {"code": "admin:schemas_manage", "name": "Manage Document Schemas", "category": "admin", "description": "Update sensitivity tiers and entity recognizers"},
    {"code": "admin:chain_recovery", "name": "Fabric Chain Recovery", "category": "admin", "description": "Execute manual blockchain retry with idempotency key"},

    # Analytics & Audit
    {"code": "reports:ncrb_read", "name": "Read NCRB Reports", "category": "reporting", "description": "Access de-identified crime statistics and analytics"},
    {"code": "audit:read_full", "name": "Audit Trail Inspection", "category": "reporting", "description": "Examine tamper-evident hash-chained audit log"}
]

CANONICAL_ROLES = [
    {
        "code": "duty_officer",
        "name": "Duty Officer (Station Intake)",
        "description": "Station desk officer handling FIR intake, initial docket registration, and panchnama ingestion.",
        "is_system": True,
        "permissions": ["cases:create", "cases:read", "documents:upload", "documents:read"]
    },
    {
        "code": "io",
        "name": "Investigating Officer (IO)",
        "description": "Assigned police investigator with full case docket, evidence collection, and diary logging permissions.",
        "is_system": True,
        "permissions": [
            "cases:read", "cases:diary_write", "documents:upload", "documents:read",
            "documents:correct_redaction", "evidence:request_create"
        ]
    },
    {
        "code": "sho",
        "name": "Station House Officer (SHO)",
        "description": "Precinct commander supervising all cases, assigning IOs, and reviewing station investigation workflows.",
        "is_system": True,
        "permissions": [
            "cases:read", "cases:create", "cases:assign", "cases:diary_write",
            "documents:upload", "documents:read", "evidence:request_create"
        ]
    },
    {
        "code": "court",
        "name": "Judicial Bench (Magistrate / Judge)",
        "description": "Presiding judicial officer with bail determination, hearing scheduling, and unredacted evidence review powers.",
        "is_system": True,
        "permissions": [
            "cases:read", "documents:read", "bail:order", "judiciary:hearings_schedule",
            "judiciary:unredacted_view", "audit:read_full"
        ]
    },
    {
        "code": "prosecutor",
        "name": "Public Prosecutor",
        "description": "State prosecutor reviewing case dossiers against statutory stage requirements and filing charge sheets.",
        "is_system": True,
        "permissions": ["cases:read", "documents:read", "judiciary:charge_sheet_file"]
    },
    {
        "code": "external_authority",
        "name": "External Authority (FSL / Bank / Telecom)",
        "description": "Certified laboratory or institutional authority fulfilling Section 91 evidentiary requisitions.",
        "is_system": True,
        "permissions": ["evidence:fulfill_submit"]
    },
    {
        "code": "defense",
        "name": "Defense Counsel / Accused",
        "description": "Submission-only access portal for filing bail petitions, medical grounds, and surety undertakings.",
        "is_system": True,
        "permissions": ["bail:apply", "bail:surety_submit"]
    },
    {
        "code": "config_admin",
        "name": "Configuration & Platform Administrator",
        "description": "System administrator managing dynamic roles, organizational onboarding, and sensitivity schemas.",
        "is_system": True,
        "permissions": [
            "admin:roles_manage", "admin:schemas_manage", "admin:chain_recovery",
            "cases:read", "documents:read"
        ]
    },
    {
        "code": "security_auditor",
        "name": "Independent Security Auditor",
        "description": "Oversight authority inspecting hash-chained audit trails and AI redaction decisions.",
        "is_system": True,
        "permissions": ["audit:read_full"]
    },
    {
        "code": "records_ncrb_analyst",
        "name": "NCRB Records Analyst",
        "description": "National Crime Records Bureau analyst querying de-identified statistical views.",
        "is_system": True,
        "permissions": ["reports:ncrb_read"]
    }
]

OFFICIAL_TEST_USERS = [
    {
        "email": "admin.sharma@legadoc.gov.in",
        "name": "Vikram Sharma",
        "service_id": "MHA-ADM-001",
        "designation": "Director (Information Systems)",
        "role": "config_admin",
        "org_name": "Ministry of Home Affairs / NIC",
        "org_type": "admin"
    },
    {
        "email": "officer.rao@police.gov.in",
        "name": "Inspector S. Rao",
        "service_id": "DL-POL-4921",
        "designation": "Inspector of Police (Cyber Cell)",
        "role": "io",
        "org_name": "Delhi Police Cyber Cell",
        "org_type": "police"
    },
    {
        "email": "duty.verma@police.gov.in",
        "name": "Sub-Inspector A. Verma",
        "service_id": "DL-POL-1084",
        "designation": "Duty Officer (Station Intake)",
        "role": "duty_officer",
        "org_name": "Delhi Police (Central Precinct)",
        "org_type": "police"
    },
    {
        "email": "sho.singh@police.gov.in",
        "name": "Harjeet Singh",
        "service_id": "DL-POL-0312",
        "designation": "Station House Officer",
        "role": "sho",
        "org_name": "Delhi Police (North Zone)",
        "org_type": "police"
    },
    {
        "email": "magistrate.iyer@court.gov.in",
        "name": "Hon. Justice R. S. Iyer",
        "service_id": "DEL-JUD-082",
        "designation": "Chief Judicial Magistrate",
        "role": "court",
        "org_name": "Patiala House District Courts",
        "org_type": "court"
    },
    {
        "email": "prosecutor.sen@court.gov.in",
        "name": "Adv. Meenakshi Sen",
        "service_id": "DL-PROS-044",
        "designation": "Senior Public Prosecutor",
        "role": "prosecutor",
        "org_name": "Directorate of Prosecution",
        "org_type": "court"
    },
    {
        "email": "fsl.director@fsl.gov.in",
        "name": "Dr. Pradeep Nair",
        "service_id": "CFSL-DIR-91",
        "designation": "Senior Scientific Officer",
        "role": "external_authority",
        "org_name": "Central Forensic Science Laboratory",
        "org_type": "fsl"
    },
    {
        "email": "defense.advocate@bar.in",
        "name": "Adv. K. L. Mehta",
        "service_id": "DHC-BAR-5920",
        "designation": "Advocate-on-Record",
        "role": "defense",
        "org_name": "Delhi High Court Bar Association",
        "org_type": "defense"
    },
    {
        "email": "analyst.ncrb@nic.in",
        "name": "S. K. Murthy",
        "service_id": "NCRB-STAT-21",
        "designation": "Senior Statistical Officer",
        "role": "records_ncrb_analyst",
        "org_name": "National Crime Records Bureau",
        "org_type": "ncrb"
    },
    # The role carries audit:read_full, unrestricted case access, and
    # unredacted PII — the widest privilege in the system. Until this
    # persona existed no account held it, so none of that was ever
    # exercised by a test or reachable in a demo (see issue #72).
    {
        "email": "auditor.rajan@vigilance.gov.in",
        "name": "K. Rajan",
        "service_id": "CVC-AUD-07",
        "designation": "Chief Vigilance Officer (Systems Audit)",
        "role": "security_auditor",
        "org_name": "Central Vigilance Commission",
        "org_type": "audit"
    }
]

DEFAULT_TEST_PASSWORD = "GovSecure@2026"


def seed_all(db):
    """Idempotently provisions all canonical permissions, roles, and official users."""
    # 1. Seed Permissions
    perm_map = {}
    for p_data in CANONICAL_PERMISSIONS:
        existing = db.query(models.Permission).filter(models.Permission.code == p_data["code"]).first()
        if not existing:
            perm = models.Permission(**p_data)
            db.add(perm)
            db.flush()
            perm_map[p_data["code"]] = perm
        else:
            perm_map[p_data["code"]] = existing

    # 2. Seed Roles
    role_map = {}
    for r_data in CANONICAL_ROLES:
        existing = db.query(models.Role).filter(models.Role.code == r_data["code"]).first()
        if not existing:
            role = models.Role(
                code=r_data["code"],
                name=r_data["name"],
                description=r_data["description"],
                is_system=r_data["is_system"]
            )
            for p_code in r_data["permissions"]:
                if p_code in perm_map:
                    role.permissions.append(perm_map[p_code])
            db.add(role)
            db.flush()
            role_map[r_data["code"]] = role
        else:
            role_map[r_data["code"]] = existing

    # 3. Seed Organizations & Users
    hashed_pwd = security.hash_password(DEFAULT_TEST_PASSWORD)
    org_cache = {}

    for u_data in OFFICIAL_TEST_USERS:
        # Resolve org
        org_name = u_data["org_name"]
        if org_name not in org_cache:
            org = db.query(models.Organization).filter(models.Organization.name == org_name).first()
            if not org:
                org = models.Organization(name=org_name, org_type=u_data["org_type"])
                db.add(org)
                db.flush()
            org_cache[org_name] = org
        else:
            org = org_cache[org_name]

        existing_user = db.query(models.User).filter(models.User.email == u_data["email"]).first()
        role_obj = role_map.get(u_data["role"])
        if not existing_user:
            user = models.User(
                name=u_data["name"],
                email=u_data["email"],
                service_id=u_data["service_id"],
                designation=u_data["designation"],
                role=u_data["role"],
                role_id=role_obj.id if role_obj else None,
                org_id=org.id,
                hashed_password=hashed_pwd
            )
            db.add(user)
        else:
            if not existing_user.service_id:
                existing_user.service_id = u_data["service_id"]
            if not existing_user.designation:
                existing_user.designation = u_data["designation"]
            if role_obj and not existing_user.role_id:
                existing_user.role_id = role_obj.id

    db.commit()
