"""
Integration & Unit Tests for Document Ingestion Pipeline & Endpoints (Phase 2).
Tests:
- POST /documents (MIME sniffing, size cap, SHA-256, MinIO storage, audit log)
- Parallel dispatch: Track A (chain_worker) and Track B (ocr_worker)
- Duplicate detection and atomic version sequencing
- GET /documents (IO assignment scoping, status filters)
- GET /documents/:id (Role-filtered view)
- GET /documents/:id/versions (Append-only version history)
- GET /documents/:id/chain-status (Polling endpoint)
- POST /documents/:id/retry-chain-write (Admin recovery, original idempotency key)
- POST /documents/:id/redact-tag (Assigned IO correction)
"""

import asyncio
import hashlib
import io
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.database import SessionLocal
from app.models import (
    Case,
    CaseAssignment,
    Document,
    DocumentExtraction,
    DocumentSensitivityTag,
    Organization,
    User,
)
from app.routers.documents import (
    correct_redaction_tag,
    get_chain_status,
    get_document,
    get_document_versions,
    list_documents,
    retry_chain_write,
    upload_document,
)
from app.schemas.documents import RedactTagRequest
from app.security import get_password_hash
from app.services.audit_service import verify_audit_chain


class TestDocumentUploadPipeline(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

        # Seed Organizations
        self.police_org = Organization(name=f"Police-{uuid4().hex[:6]}", org_type="police")
        self.court_org = Organization(name=f"Court-{uuid4().hex[:6]}", org_type="court")
        self.defense_org = Organization(name=f"Defense-{uuid4().hex[:6]}", org_type="defense")
        self.db.add_all([self.police_org, self.court_org, self.defense_org])
        self.db.commit()

        # Seed Users
        hashed = get_password_hash("Password123!")
        self.admin_user = User(
            name="Admin Officer",
            email=f"admin_{uuid4().hex[:6]}@police.gov.in",
            role="admin",
            org_id=self.police_org.id,
            hashed_password=hashed,
        )
        self.assigned_io = User(
            name="IO Raj",
            email=f"io_raj_{uuid4().hex[:6]}@police.gov.in",
            role="io",
            org_id=self.police_org.id,
            hashed_password=hashed,
        )
        self.unassigned_io = User(
            name="IO Vikram",
            email=f"io_vikram_{uuid4().hex[:6]}@police.gov.in",
            role="io",
            org_id=self.police_org.id,
            hashed_password=hashed,
        )
        self.sho_user = User(
            name="SHO Sharma",
            email=f"sho_{uuid4().hex[:6]}@police.gov.in",
            role="sho",
            org_id=self.police_org.id,
            hashed_password=hashed,
        )
        self.prosecutor_user = User(
            name="PP Mehra",
            email=f"pp_{uuid4().hex[:6]}@court.gov.in",
            role="prosecutor",
            org_id=self.court_org.id,
            hashed_password=hashed,
        )
        self.defense_user = User(
            name="Adv Verma",
            email=f"adv_{uuid4().hex[:6]}@defense.org",
            role="defense",
            org_id=self.defense_org.id,
            hashed_password=hashed,
        )
        self.counselor_user = User(
            name="Counselor Ananya",
            email=f"counselor_{uuid4().hex[:6]}@police.gov.in",
            role="counselor",
            org_id=self.police_org.id,
            hashed_password=hashed,
        )
        self.db.add_all([
            self.admin_user,
            self.assigned_io,
            self.unassigned_io,
            self.sho_user,
            self.prosecutor_user,
            self.defense_user,
            self.counselor_user,
        ])
        self.db.commit()

        # Seed Showcase Case
        self.case = Case(
            case_number=f"FIR-{uuid4().hex[:8].upper()}",
            crime_type="robbery",
            court_level="sessions",
            investigation_status="FIR_Registered",
        )
        self.db.add(self.case)
        self.db.commit()

        # Assign IO Raj to the case
        self.assignment = CaseAssignment(
            case_id=self.case.id,
            io_user_id=self.assigned_io.id,
        )
        self.db.add(self.assignment)
        self.db.commit()

        # Claims dicts
        self.claims_admin = {"sub": str(self.admin_user.id), "org_id": str(self.police_org.id), "role": "admin"}
        self.claims_assigned_io = {"sub": str(self.assigned_io.id), "org_id": str(self.police_org.id), "role": "io"}
        self.claims_unassigned_io = {"sub": str(self.unassigned_io.id), "org_id": str(self.police_org.id), "role": "io"}
        self.claims_sho = {"sub": str(self.sho_user.id), "org_id": str(self.police_org.id), "role": "sho"}
        self.claims_prosecutor = {"sub": str(self.prosecutor_user.id), "org_id": str(self.court_org.id), "role": "prosecutor"}
        self.claims_defense = {"sub": str(self.defense_user.id), "org_id": str(self.defense_org.id), "role": "defense"}
        self.claims_counselor = {"sub": str(self.counselor_user.id), "org_id": str(self.police_org.id), "role": "counselor"}

    def tearDown(self):
        self.db.close()

    def _create_upload_file(self, content: bytes, filename: str = "doc.pdf", content_type: str = "application/pdf") -> UploadFile:
        return UploadFile(
            file=io.BytesIO(content),
            size=len(content),
            filename=filename,
            headers=Headers({"content-type": content_type}),
        )

    def _sample_pdf_bytes(self, content="Sample FIR Report"):
        return (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
            b"4 0 obj\n<< /Length 44 >>\nstream\n"
            + content.encode("utf-8")
            + b"\nendstream\nendobj\nxref\n0 5\ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n307\n%%EOF"
        )

    # =========================================================================
    # Upload Tests
    # =========================================================================

    @patch("app.routers.documents.storage_service.upload_file")
    @patch("app.routers.documents.dispatch_chain_write")
    @patch("app.routers.documents.dispatch_ocr_extraction")
    def test_upload_pdf_success(self, mock_ocr, mock_chain, mock_storage):
        """Happy path: assigned IO uploads PDF, rows created, tasks dispatched."""
        pdf_bytes = self._sample_pdf_bytes("FIR Narrative Text 123")
        expected_hash = hashlib.sha256(pdf_bytes).hexdigest()
        upload_f = self._create_upload_file(pdf_bytes, filename="fir_complaint.pdf", content_type="application/pdf")

        res = asyncio.run(
            upload_document(
                case_id=self.case.id,
                doc_type="FIR_Report",
                file=upload_f,
                claims=self.claims_assigned_io,
                db=self.db,
            )
        )

        self.assertEqual(res.doc_type, "FIR_Report")
        self.assertEqual(res.version, 1)
        self.assertEqual(res.status, "processing")
        self.assertEqual(res.chain_status, "pending")
        self.assertEqual(res.doc_hash, expected_hash)
        self.assertEqual(res.original_filename, "fir_complaint.pdf")

        # Storage upload invoked
        mock_storage.assert_called_once()

        # Track A and Track B tasks dispatched
        mock_chain.assert_called_once_with(str(res.document_id), 1)
        mock_ocr.assert_called_once_with(str(res.document_id))

        # Check DB rows
        doc = self.db.query(Document).filter(Document.id == res.document_id).first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.doc_hash, expected_hash)

        extraction = self.db.query(DocumentExtraction).filter(DocumentExtraction.document_id == doc.id).first()
        self.assertIsNotNone(extraction)
        self.assertEqual(extraction.extraction_status, "pending")

        # Check audit trail integrity
        audit_res = verify_audit_chain(self.db)
        self.assertTrue(audit_res["valid"])

    def test_upload_rejects_executable_mime(self):
        """Upload disguised executable (.exe as .pdf) gets rejected with 415."""
        fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00This is malware"
        upload_f = self._create_upload_file(fake_pdf, filename="malware.pdf", content_type="application/pdf")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_document(
                    case_id=self.case.id,
                    doc_type="FIR_Report",
                    file=upload_f,
                    claims=self.claims_assigned_io,
                    db=self.db,
                )
            )
        self.assertEqual(ctx.exception.status_code, 415)
        self.assertIn("Unsupported file type", ctx.exception.detail)

    @patch("app.services.upload_validator.detect_mime_from_bytes", return_value="application/pdf")
    def test_upload_rejects_oversized_file(self, mock_mime):
        """Upload exceeding size cap gets rejected with 413."""
        # 1.1MB bytes with a 1MB limit
        oversized = b"%PDF-1.4\n" + (b"A" * (1024 * 1024 + 100 * 1024))
        upload_f = self._create_upload_file(oversized, filename="big_scan.pdf", content_type="application/pdf")

        with patch("app.routers.documents.settings.MAX_UPLOAD_SIZE_MB", 1):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    upload_document(
                        case_id=self.case.id,
                        doc_type="FIR_Report",
                        file=upload_f,
                        claims=self.claims_assigned_io,
                        db=self.db,
                    )
                )
            self.assertEqual(ctx.exception.status_code, 413)
            self.assertIn("File exceeds maximum allowed size", ctx.exception.detail)

    @patch("app.routers.documents.storage_service.upload_file")
    @patch("app.routers.documents.dispatch_chain_write")
    @patch("app.routers.documents.dispatch_ocr_extraction")
    def test_upload_binary_evidence_skips_ocr(self, mock_ocr, mock_chain, mock_storage):
        """Video/CCTV evidence skips OCR and is marked ready immediately."""
        mp4_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42\x00\x00\x00\x08free"
        upload_f = self._create_upload_file(mp4_bytes, filename="cctv_clip.mp4", content_type="video/mp4")

        res = asyncio.run(
            upload_document(
                case_id=self.case.id,
                doc_type="CCTV_Footage",
                file=upload_f,
                claims=self.claims_assigned_io,
                db=self.db,
            )
        )

        self.assertEqual(res.status, "ready")
        mock_chain.assert_called_once()
        mock_ocr.assert_not_called()

    def test_upload_unassigned_io_forbidden(self):
        """Unassigned IO is rejected with 403 on POST /documents."""
        pdf_bytes = self._sample_pdf_bytes("Another PDF")
        upload_f = self._create_upload_file(pdf_bytes, filename="doc.pdf", content_type="application/pdf")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_document(
                    case_id=self.case.id,
                    doc_type="FIR_Report",
                    file=upload_f,
                    claims=self.claims_unassigned_io,
                    db=self.db,
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("not the assigned", ctx.exception.detail)

    def test_upload_defense_forbidden(self):
        """Defense attorney is blocked from uploading investigation documents."""
        pdf_bytes = self._sample_pdf_bytes("Defense Doc")
        upload_f = self._create_upload_file(pdf_bytes, filename="doc.pdf", content_type="application/pdf")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_document(
                    case_id=self.case.id,
                    doc_type="FIR_Report",
                    file=upload_f,
                    claims=self.claims_defense,
                    db=self.db,
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_upload_specialist_role_blocked_by_default(self):
        """Role not in UPLOAD_ALLOWED_ROLES (e.g. counselor) is blocked with 403."""
        pdf_bytes = self._sample_pdf_bytes("Counselor Notes")
        upload_f = self._create_upload_file(pdf_bytes, filename="doc.pdf", content_type="application/pdf")

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                upload_document(
                    case_id=self.case.id,
                    doc_type="FIR_Report",
                    file=upload_f,
                    claims=self.claims_counselor,
                    db=self.db,
                )
            )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("not permitted to upload", ctx.exception.detail)

    @patch("app.routers.documents.storage_service.upload_file")
    @patch("app.routers.documents.dispatch_chain_write")
    @patch("app.routers.documents.dispatch_ocr_extraction")
    def test_upload_duplicate_hash_returns_existing(self, mock_ocr, mock_chain, mock_storage):
        """Re-uploading identical file for same case/doc_type returns existing document."""
        pdf_bytes = self._sample_pdf_bytes("Identical Content")
        upload_f1 = self._create_upload_file(pdf_bytes, filename="file1.pdf", content_type="application/pdf")

        res1 = asyncio.run(
            upload_document(
                case_id=self.case.id,
                doc_type="FIR_Report",
                file=upload_f1,
                claims=self.claims_assigned_io,
                db=self.db,
            )
        )

        upload_f2 = self._create_upload_file(pdf_bytes, filename="file2.pdf", content_type="application/pdf")
        res2 = asyncio.run(
            upload_document(
                case_id=self.case.id,
                doc_type="FIR_Report",
                file=upload_f2,
                claims=self.claims_assigned_io,
                db=self.db,
            )
        )

        # Must return the exact same document ID and version
        self.assertEqual(res1.document_id, res2.document_id)
        self.assertEqual(res1.version, res2.version)

    # =========================================================================
    # Versioning Tests
    # =========================================================================

    @patch("app.routers.documents.storage_service.upload_file")
    @patch("app.routers.documents.dispatch_chain_write")
    @patch("app.routers.documents.dispatch_ocr_extraction")
    def test_version_history_append_only(self, mock_ocr, mock_chain, mock_storage):
        """Different uploads for same doc_type increment version (v1, v2) without overwriting."""
        upload_f1 = self._create_upload_file(self._sample_pdf_bytes("V1 text"), filename="stmt_v1.pdf")
        res1 = asyncio.run(
            upload_document(
                case_id=self.case.id,
                doc_type="Witness_Statement",
                file=upload_f1,
                claims=self.claims_assigned_io,
                db=self.db,
            )
        )
        self.assertEqual(res1.version, 1)

        upload_f2 = self._create_upload_file(self._sample_pdf_bytes("V2 text updated"), filename="stmt_v2.pdf")
        res2 = asyncio.run(
            upload_document(
                case_id=self.case.id,
                doc_type="Witness_Statement",
                file=upload_f2,
                claims=self.claims_assigned_io,
                db=self.db,
            )
        )
        self.assertEqual(res2.version, 2)

        # Query version history
        versions = get_document_versions(
            document_id=res1.document_id,
            claims=self.claims_assigned_io,
            db=self.db,
        )
        self.assertGreaterEqual(len(versions), 2)
        self.assertEqual(versions[0].version, 2)
        self.assertEqual(versions[1].version, 1)

    # =========================================================================
    # Role-Filtered Document View Tests
    # =========================================================================

    def test_get_document_views_by_role(self):
        """Assigned IO sees tags; Prosecutor sees text without tags; Defense gets 403."""
        doc = Document(
            case_id=self.case.id,
            doc_type="Medical_Report",
            version=1,
            storage_path="test/path",
            doc_hash="hash123",
            status="ready",
            chain_status="confirmed",
            uploaded_by=self.assigned_io.id,
            original_filename="mlc.pdf",
        )
        self.db.add(doc)
        self.db.flush()

        extraction = DocumentExtraction(
            document_id=doc.id,
            version=1,
            raw_text="Patient Rahul was treated for injury.",
            extraction_status="ready",
        )
        tag = DocumentSensitivityTag(
            document_id=doc.id,
            entity_type="PERSON",
            span_start=8,
            span_end=13,
            confidence=95,
            source="ai_parser",
        )
        self.db.add_all([extraction, tag])
        self.db.commit()

        # 1. Assigned IO gets full view with tags
        view_io = get_document(document_id=doc.id, claims=self.claims_assigned_io, db=self.db)
        self.assertIsNotNone(view_io.tags)
        self.assertEqual(len(view_io.tags), 1)
        self.assertEqual(view_io.text, "Patient Rahul was treated for injury.")

        # 2. Prosecutor sees text, tags are omitted
        view_pp = get_document(document_id=doc.id, claims=self.claims_prosecutor, db=self.db)
        self.assertIsNone(view_pp.tags)
        self.assertEqual(view_pp.text, "Patient Rahul was treated for injury.")

        # 3. Defense attorney blocked from investigation document
        with self.assertRaises(HTTPException) as ctx:
            get_document(document_id=doc.id, claims=self.claims_defense, db=self.db)
        self.assertEqual(ctx.exception.status_code, 403)

    # =========================================================================
    # Chain Status & Recovery Tests
    # =========================================================================

    def test_chain_status_polling(self):
        """GET /documents/:id/chain-status returns chain confirmation state."""
        doc = Document(
            case_id=self.case.id,
            doc_type="Bail_Notice",
            version=1,
            storage_path="test/path2",
            doc_hash="abc456",
            status="ready",
            chain_status="pending",
            uploaded_by=self.assigned_io.id,
        )
        self.db.add(doc)
        self.db.commit()

        res = get_chain_status(document_id=doc.id, claims=self.claims_assigned_io, db=self.db)
        self.assertEqual(res.chain_status, "pending")
        self.assertEqual(res.doc_hash, "abc456")

    @patch("app.routers.documents.dispatch_chain_write")
    def test_retry_chain_write_admin_recovery(self, mock_chain):
        """Admin can retry stuck/failed chain write; non-admin is forbidden."""
        doc = Document(
            case_id=self.case.id,
            doc_type="Seizure_Memo",
            version=1,
            storage_path="test/path3",
            doc_hash="failhash",
            status="ready",
            chain_status="failed",
            uploaded_by=self.assigned_io.id,
        )
        self.db.add(doc)
        self.db.commit()

        # Non-admin IO cannot trigger retry
        with self.assertRaises(HTTPException) as ctx:
            retry_chain_write(document_id=doc.id, claims=self.claims_assigned_io, db=self.db)
        self.assertEqual(ctx.exception.status_code, 403)

        # Admin triggers retry
        res_admin = retry_chain_write(document_id=doc.id, claims=self.claims_admin, db=self.db)
        self.assertEqual(res_admin.chain_status, "pending")

        # Must reuse original idempotency key
        mock_chain.assert_called_once_with(str(doc.id), 1)

    # =========================================================================
    # Officer Sensitivity Tag Correction Tests
    # =========================================================================

    def test_redact_tag_correction(self):
        """Assigned IO can correct or add sensitivity tags; unassigned cannot."""
        doc = Document(
            case_id=self.case.id,
            doc_type="FIR_Report",
            version=1,
            storage_path="test/path4",
            doc_hash="taghash",
            status="ready",
            chain_status="confirmed",
            uploaded_by=self.assigned_io.id,
        )
        self.db.add(doc)
        self.db.commit()

        # Unassigned IO is forbidden
        with self.assertRaises(HTTPException) as ctx:
            correct_redaction_tag(
                document_id=doc.id,
                request=RedactTagRequest(entity_type="PHONE_NUMBER", span_start=10, span_end=20),
                claims=self.claims_unassigned_io,
                db=self.db,
            )
        self.assertEqual(ctx.exception.status_code, 403)

        # Assigned IO creates tag
        tag_res = correct_redaction_tag(
            document_id=doc.id,
            request=RedactTagRequest(entity_type="PHONE_NUMBER", span_start=10, span_end=20),
            claims=self.claims_assigned_io,
            db=self.db,
        )
        self.assertEqual(tag_res.entity_type, "PHONE_NUMBER")
        self.assertEqual(tag_res.source, "officer_correction")
        self.assertIsNone(tag_res.confidence)

        # Assigned IO updates existing tag
        update_res = correct_redaction_tag(
            document_id=doc.id,
            request=RedactTagRequest(
                entity_type="AADHAAR",
                span_start=10,
                span_end=22,
                tag_id=tag_res.id,
            ),
            claims=self.claims_assigned_io,
            db=self.db,
        )
        self.assertEqual(update_res.entity_type, "AADHAAR")

    # =========================================================================
    # Document Listing & Scoping Tests
    # =========================================================================

    def test_list_documents_io_scoped(self):
        """IO only sees documents for assigned cases in GET /documents."""
        # Doc in assigned case
        doc1 = Document(
            case_id=self.case.id,
            doc_type="FIR_Report",
            version=1,
            storage_path="path1",
            doc_hash="hash_case1",
            status="ready",
            chain_status="confirmed",
            uploaded_by=self.assigned_io.id,
        )

        # Another case not assigned to this IO
        other_case = Case(
            case_number=f"FIR-OTHER-{uuid4().hex[:6]}",
            crime_type="theft",
            investigation_status="FIR_Registered",
        )
        self.db.add(other_case)
        self.db.flush()

        doc2 = Document(
            case_id=other_case.id,
            doc_type="FIR_Report",
            version=1,
            storage_path="path2",
            doc_hash="hash_case2",
            status="ready",
            chain_status="confirmed",
            uploaded_by=self.unassigned_io.id,
        )
        self.db.add_all([doc1, doc2])
        self.db.commit()

        # Assigned IO lists documents
        res_io = list_documents(claims=self.claims_assigned_io, db=self.db)
        io_doc_ids = [str(item.id) for item in res_io.items]
        self.assertIn(str(doc1.id), io_doc_ids)
        self.assertNotIn(str(doc2.id), io_doc_ids)

        # Admin lists documents — can see all
        res_admin = list_documents(claims=self.claims_admin, db=self.db)
        admin_doc_ids = [str(item.id) for item in res_admin.items]
        self.assertIn(str(doc1.id), admin_doc_ids)
        self.assertIn(str(doc2.id), admin_doc_ids)


if __name__ == "__main__":
    unittest.main()
