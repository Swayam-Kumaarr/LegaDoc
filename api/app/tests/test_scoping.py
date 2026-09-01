"""
Unit and Integration Tests for Case and Org Scoping.
Tests:
- IO case assignment access
- Unauthorized IO access to unassigned cases
- Defense blocked from active investigation materials
- External Authority evidence request org-scoping
"""

import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Case, CaseAssignment, EvidenceRequest, Organization, User
from app.security import verify_case_access, verify_evidence_request_org_access


class TestScopingAndAccess(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        # Create organizations
        self.police_org = Organization(name="District Police", org_type="police")
        self.fsl_org = Organization(name="State FSL", org_type="fsl")
        self.other_fsl_org = Organization(name="Other FSL", org_type="fsl")
        self.db.add_all([self.police_org, self.fsl_org, self.other_fsl_org])
        self.db.commit()

        # Create users
        self.assigned_io = User(
            org_id=self.police_org.id,
            role="io",
            name="Assigned IO",
            email=f"io_{uuid4().hex[:6]}@police.gov.in",
            hashed_password="hash",
        )
        self.unassigned_io = User(
            org_id=self.police_org.id,
            role="io",
            name="Unassigned IO",
            email=f"io_un_{uuid4().hex[:6]}@police.gov.in",
            hashed_password="hash",
        )
        self.db.add_all([self.assigned_io, self.unassigned_io])
        self.db.commit()

        # Create case
        self.case = Case(
            case_number=f"FIR-{uuid4().hex[:8].upper()}",
            crime_type="Cyber_Fraud",
            investigation_status="Evidence_Collection",
        )
        self.db.add(self.case)
        self.db.commit()

        # Assign case to assigned_io
        self.assignment = CaseAssignment(
            case_id=self.case.id,
            io_user_id=self.assigned_io.id,
        )
        self.db.add(self.assignment)
        self.db.commit()

        # Create evidence request routed to fsl_org
        self.evidence_req = EvidenceRequest(
            case_id=self.case.id,
            requested_org_id=self.fsl_org.id,
            doc_type_expected="Fingerprint_Report",
        )
        self.db.add(self.evidence_req)
        self.db.commit()

    def tearDown(self):
        self.db.query(EvidenceRequest).filter(EvidenceRequest.case_id == self.case.id).delete()
        self.db.query(CaseAssignment).filter(CaseAssignment.case_id == self.case.id).delete()
        self.db.query(Case).filter(Case.id == self.case.id).delete()
        self.db.query(User).filter(User.id.in_([self.assigned_io.id, self.unassigned_io.id])).delete()
        self.db.query(Organization).filter(
            Organization.id.in_([self.police_org.id, self.fsl_org.id, self.other_fsl_org.id])
        ).delete()
        self.db.commit()
        self.db.close()

    def test_assigned_io_can_access_case(self):
        claims = {"sub": str(self.assigned_io.id), "org_id": str(self.police_org.id), "role": "io"}
        case = verify_case_access(self.case.id, claims, self.db)
        self.assertEqual(case.id, self.case.id)

    def test_unassigned_io_forbidden(self):
        claims = {"sub": str(self.unassigned_io.id), "org_id": str(self.police_org.id), "role": "io"}
        with self.assertRaises(HTTPException) as ctx:
            verify_case_access(self.case.id, claims, self.db)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("not the assigned Investigating Officer", ctx.exception.detail)

    def test_admin_and_court_global_access(self):
        admin_claims = {"sub": str(uuid4()), "org_id": str(uuid4()), "role": "admin"}
        court_claims = {"sub": str(uuid4()), "org_id": str(uuid4()), "role": "court"}
        self.assertEqual(verify_case_access(self.case.id, admin_claims, self.db).id, self.case.id)
        self.assertEqual(verify_case_access(self.case.id, court_claims, self.db).id, self.case.id)

    def test_defense_blocked_from_investigation_materials(self):
        defense_claims = {"sub": str(uuid4()), "org_id": str(uuid4()), "role": "defense"}
        with self.assertRaises(HTTPException) as ctx:
            verify_case_access(self.case.id, defense_claims, self.db)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Defense access", ctx.exception.detail)

    def test_evidence_request_org_scoping(self):
        # Matching FSL org can access
        fsl_claims = {"sub": str(uuid4()), "org_id": str(self.fsl_org.id), "role": "authority_staff"}
        req = verify_evidence_request_org_access(self.evidence_req.id, fsl_claims, self.db)
        self.assertEqual(req.id, self.evidence_req.id)

        # Mismatched FSL org is forbidden
        other_claims = {"sub": str(uuid4()), "org_id": str(self.other_fsl_org.id), "role": "authority_staff"}
        with self.assertRaises(HTTPException) as ctx:
            verify_evidence_request_org_access(self.evidence_req.id, other_claims, self.db)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("routed to a different organization", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
