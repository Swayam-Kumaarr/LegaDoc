"""
Demo Seed Script — populates organizations and persona user accounts
for interactive testing and hackathon demo evaluation.

Run via:
  docker compose exec api python -m app.seed_demo_users
"""

from uuid import uuid4
from app.database import SessionLocal
from app.models import Case, CaseAssignment, Organization, User
from app.security import get_password_hash

DEFAULT_PASSWORD = "Password123!"

DEMO_ORGS = [
    {"name": "Central Police District", "org_type": "police"},
    {"name": "State Forensic Science Laboratory", "org_type": "fsl"},
    {"name": "City Civil & Sessions Court", "org_type": "court"},
    {"name": "National Crime Records Bureau", "org_type": "ncrb"},
    {"name": "City General Hospital", "org_type": "hospital"},
    {"name": "LegaDoc System Administration", "org_type": "admin"},
]

DEMO_USERS = [
    {
        "name": "Rajesh Kumar",
        "email": "officer.raj@police.gov.in",
        "role": "io",
        "org_type": "police",
    },
    {
        "name": "Vikram Singh",
        "email": "sho.vikram@police.gov.in",
        "role": "sho",
        "org_type": "police",
    },
    {
        "name": "System Administrator",
        "email": "admin@legadoc.gov.in",
        "role": "admin",
        "org_type": "admin",
    },
    {
        "name": "Judge P. N. Bhagwati",
        "email": "court.magistrate@judiciary.gov.in",
        "role": "court",
        "org_type": "court",
    },
    {
        "name": "Dr. Sunita Sharma",
        "email": "dr.sunita@fsl.gov.in",
        "role": "authority_staff",
        "org_type": "fsl",
    },
    {
        "name": "Advocate Kapoor",
        "email": "kapoor.defense@legalbar.in",
        "role": "defense",
        "org_type": "court",
    },
    {
        "name": "Amit Verma",
        "email": "analyst.verma@ncrb.gov.in",
        "role": "records_ncrb_analyst",
        "org_type": "ncrb",
    },
]


def seed_all():
    db = SessionLocal()
    org_map = {}

    print("--- Seeding Organizations ---")
    for org_data in DEMO_ORGS:
        org = db.query(Organization).filter(Organization.name == org_data["name"]).first()
        if not org:
            org = Organization(name=org_data["name"], org_type=org_data["org_type"])
            db.add(org)
            db.commit()
            db.refresh(org)
            print(f"Created Org: {org.name} ({org.org_type})")
        org_map[org_data["org_type"]] = org

    print("\n--- Seeding Persona Users ---")
    created_users = {}
    for udata in DEMO_USERS:
        user = db.query(User).filter(User.email == udata["email"]).first()
        org = org_map[udata["org_type"]]
        if not user:
            user = User(
                org_id=org.id,
                role=udata["role"],
                name=udata["name"],
                email=udata["email"],
                hashed_password=get_password_hash(DEFAULT_PASSWORD),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created User: {user.name} | Role: {user.role} | Email: {user.email}")
        else:
            user.hashed_password = get_password_hash(DEFAULT_PASSWORD)
            db.commit()
            print(f"Reset Password for: {user.name} | Role: {user.role} | Email: {user.email}")
        created_users[udata["role"]] = user

    print("\n--- Seeding Showcase Case ---")
    case = db.query(Case).filter(Case.case_number == "FIR-2026-DEL-0042").first()
    if not case:
        case = Case(
            case_number="FIR-2026-DEL-0042",
            crime_type="Domestic_Violence",
            investigation_status="Evidence_Collection",
            court_level="magistrate",
            bail_status="Arrested",
        )
        db.add(case)
        db.commit()
        db.refresh(case)

        # Assign case to IO Rajesh Kumar
        io_user = created_users.get("io")
        if io_user:
            assignment = CaseAssignment(case_id=case.id, io_user_id=io_user.id)
            db.add(assignment)
            db.commit()
            print(f"Assigned Case {case.case_number} to IO {io_user.name}")

    db.close()
    print("\n✅ Demo seed complete! Default password for all users: Password123!")


if __name__ == "__main__":
    seed_all()
