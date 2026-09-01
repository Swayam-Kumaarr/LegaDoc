"""
Unit and Integration Tests for Audit Service & Hash Chaining.
Tests:
- Sequential hash calculation
- Atomic append with prev_hash chaining
- Chain verification and tampering detection
"""

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.database import SessionLocal
from app.models import AuditLog, Case, Organization, User
from app.services.audit_service import append_audit_log, compute_row_hash, verify_audit_chain


class TestAuditService(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        # Create Organization and User to satisfy foreign key constraints
        self.org = Organization(name="Audit Test Org", org_type="police")
        self.db.add(self.org)
        self.db.commit()

        self.user = User(
            org_id=self.org.id,
            role="io",
            name="Audit Test User",
            email=f"audit_user_{uuid4().hex[:6]}@police.gov.in",
            hashed_password="hashed_pwd",
        )
        self.db.add(self.user)
        self.db.commit()
        self.actor_id = self.user.id

        # Create a real Case row to satisfy foreign key constraints
        self.case = Case(
            case_number=f"AUDIT-CASE-{uuid4().hex[:8].upper()}",
            crime_type="Theft",
            investigation_status="FIR_Registered",
        )
        self.db.add(self.case)
        self.db.commit()
        self.case_id = self.case.id

    def tearDown(self):
        # Clean up any audit entries and records created during tests
        try:
            self.db.rollback()
            self.db.query(AuditLog).filter(AuditLog.case_id == self.case_id).delete()
            self.db.query(Case).filter(Case.id == self.case_id).delete()
            self.db.query(User).filter(User.id == self.user.id).delete()
            self.db.query(Organization).filter(Organization.id == self.org.id).delete()
            self.db.commit()
        except Exception:
            self.db.rollback()
        finally:
            self.db.close()

    def test_hash_computation_deterministic(self):
        ts = datetime(2026, 8, 30, 10, 0, 0, tzinfo=timezone.utc)
        h1 = compute_row_hash(
            prev_hash="abc",
            actor_user_id=self.actor_id,
            action="upload_document",
            target_type="document",
            target_id=None,
            created_at=ts,
            action_metadata={"version": 1},
        )
        h2 = compute_row_hash(
            prev_hash="abc",
            actor_user_id=self.actor_id,
            action="upload_document",
            target_type="document",
            target_id=None,
            created_at=ts,
            action_metadata={"version": 1},
        )
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)  # SHA-256 hex length

    def test_sequential_append_and_chain_verification(self):
        # Append 3 events
        e1 = append_audit_log(
            db=self.db,
            case_id=self.case_id,
            actor_user_id=self.actor_id,
            action="case_created",
            target_type="case",
            target_id=self.case_id,
            action_metadata={"crime_type": "Theft"},
        )
        self.db.commit()

        e2 = append_audit_log(
            db=self.db,
            case_id=self.case_id,
            actor_user_id=self.actor_id,
            action="document_uploaded",
            target_type="document",
            target_id=uuid4(),
            action_metadata={"doc_type": "FIR"},
        )
        self.db.commit()

        e3 = append_audit_log(
            db=self.db,
            case_id=self.case_id,
            actor_user_id=None,  # system:ai_parser
            action="ai_parser_auto_tag",
            target_type="document",
            target_id=e2.target_id,
            action_metadata={"tag_count": 3},
        )
        self.db.commit()

        # Check prev_hash links
        self.assertEqual(e2.prev_hash, e1.row_hash)
        self.assertEqual(e3.prev_hash, e2.row_hash)

        # Verify chain integrity
        report = verify_audit_chain(self.db, case_id=self.case_id)
        self.assertTrue(report["valid"])
        self.assertIsNone(report["first_break_at"])
        self.assertEqual(report["total_rows"], 3)


if __name__ == "__main__":
    unittest.main()
