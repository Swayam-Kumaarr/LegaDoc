"""
Unit and integration tests for AI Parser Worker:
- Entity extraction (PERSON, PHONE_NUMBER, AADHAAR, PAN, MEDICAL_CONDITION, EMAIL_ADDRESS)
- Document sensitivity tagging and role-based masking integration
- Confidence threshold evaluation (threshold 70 -> needs_review vs ready)
- Fail-closed security rule on empty text or error
- Audit trail integrity under pg_advisory_xact_lock
- Case diary entry processing
"""

import importlib.util
import os
import sys
from uuid import UUID, uuid4

import pytest

from app import models
from app.audit import verify_chain_intact
from tests.conftest import TestSessionLocal, auth_headers, login

# Load ai_parser_worker module safely without sys.modules collisions
_worker_path = (
    "/workers/ai_parser_worker"
    if os.path.exists("/workers/ai_parser_worker")
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "workers", "ai_parser_worker")
)
_worker_file = os.path.join(_worker_path, "worker.py")
spec = importlib.util.spec_from_file_location("ai_parser_worker_module", _worker_file)
ai_worker = importlib.util.module_from_spec(spec)
sys.modules["ai_parser_worker_module"] = ai_worker
spec.loader.exec_module(ai_worker)


@pytest.fixture(autouse=True)
def _patch_worker_session(monkeypatch):
    """Ensure worker functions use the in-memory SQLite TestSessionLocal."""
    monkeypatch.setattr(ai_worker, "SessionLocal", TestSessionLocal)


def _setup_case_and_doc(db_session, make_org, make_user, raw_text=""):
    org = make_org()
    io_user = make_user("io", email=f"io-{uuid4().hex[:8]}@example.com", password="pw", org=org)
    case = models.Case(
        case_number=f"CASE-{uuid4().hex[:6]}",
        crime_type="Theft",
        investigation_status="Under_Investigation",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    # Assign IO to case
    db_session.add(models.CaseAssignment(case_id=case.id, io_user_id=io_user.id))

    document = models.Document(
        case_id=case.id,
        doc_type="Witness Statement",
        version=1,
        storage_path="test/storage/path/v1",
        doc_hash="fakehash123",
        raw_text=raw_text,
        status="processing",
        chain_status="pending",
        uploaded_by=io_user.id,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return case, io_user, document


def test_ai_parser_extracts_phone_aadhaar_pan_person_medical():
    """Entity recognizer extracts standard Indian PII and forensic terms accurately."""
    sample_text = (
        "Witness Dr. Rajesh Sharma, contact +91 9876543210, Aadhaar 2345 6789 0123, "
        "PAN ABCDE1234F, email rajesh@hospital.gov.in. Patient sustained deep lacerated wound."
    )

    spans = ai_worker.parse_text_for_sensitive_spans(sample_text)
    assert len(spans) >= 5

    entity_types = {s["entity_type"] for s in spans}
    assert "PERSON" in entity_types
    assert "PHONE_NUMBER" in entity_types
    assert "AADHAAR" in entity_types
    assert "PAN" in entity_types
    assert "MEDICAL_CONDITION" in entity_types
    assert "EMAIL_ADDRESS" in entity_types

    # Verify span offsets match actual text substrings
    for s in spans:
        matched_text = sample_text[s["span_start"] : s["span_end"]]
        assert len(matched_text) > 0
        if s["entity_type"] == "PERSON":
            assert "Rajesh Sharma" in matched_text
        elif s["entity_type"] == "PHONE_NUMBER":
            assert "9876543210" in matched_text
        elif s["entity_type"] == "AADHAAR":
            assert "2345 6789 0123" in matched_text
        elif s["entity_type"] == "PAN":
            assert "ABCDE1234F" in matched_text
        elif s["entity_type"] == "MEDICAL_CONDITION":
            assert "lacerated wound" in matched_text.lower()


def test_ai_parser_document_tagging_and_masking_e2e(client, db_session, make_org, make_user):
    """End-to-end integration: AI Parser tags document and restricted role sees masked spans."""
    raw_text = "Complainant Shri Amit Verma, phone 9123456780, resident of Delhi."
    case, io_user, document = _setup_case_and_doc(db_session, make_org, make_user, raw_text=raw_text)

    # Execute parser orchestration
    res_status = ai_worker.process_tag_document(str(document.id), db=db_session)
    assert res_status == "ready"

    # Verify DocumentSensitivityTag rows exist in DB
    tags = db_session.query(models.DocumentSensitivityTag).filter_by(document_id=document.id).all()
    assert len(tags) >= 2

    # Assert tags NEVER store the raw text
    for t in tags:
        assert hasattr(t, "span_start") and hasattr(t, "span_end")
        assert not hasattr(t, "raw_text")  # table schema has no raw text column
        assert t.source == "ai_parser"
        assert t.confidence >= 70

    # Assigned IO sees unredacted text
    io_token = login(client, io_user.email, "pw").json()["access_token"]
    io_resp = client.get(f"/documents/{document.id}", headers=auth_headers(io_token))
    assert io_resp.status_code == 200
    assert "Amit Verma" in io_resp.json()["text"]
    assert "9123456780" in io_resp.json()["text"]

    # Restricted role on same case sees masked text
    specialist = make_user("cyber_cell", email="specialist@example.com", password="pw", org=io_user.organization)
    db_session.add(models.CaseAssignment(case_id=case.id, io_user_id=specialist.id))
    db_session.commit()
    spec_token = login(client, "specialist@example.com", "pw").json()["access_token"]

    spec_resp = client.get(f"/documents/{document.id}", headers=auth_headers(spec_token))
    assert spec_resp.status_code == 200
    masked_text = spec_resp.json()["text"]
    assert "[REDACTED:PERSON]" in masked_text
    assert "[REDACTED:PHONE_NUMBER]" in masked_text
    assert "Amit Verma" not in masked_text
    assert "9123456780" not in masked_text


def test_ai_parser_low_confidence_routes_to_needs_review(client, db_session, make_org, make_user, monkeypatch):
    """Low-confidence tag (< 70) automatically routes document to status='needs_review'."""
    raw_text = "Suspect Amit Kumar, contact 9988776655."
    case, io_user, document = _setup_case_and_doc(db_session, make_org, make_user, raw_text=raw_text)

    # Monkeypatch parser to return one low-confidence span (e.g. 55)
    def mock_parse(text, doc_type="general"):
        return [
            {"entity_type": "PERSON", "span_start": 8, "span_end": 18, "confidence": 55},
            {"entity_type": "PHONE_NUMBER", "span_start": 28, "span_end": 38, "confidence": 90},
        ]

    monkeypatch.setattr(ai_worker, "parse_text_for_sensitive_spans", mock_parse)

    res_status = ai_worker.process_tag_document(str(document.id), db=db_session)
    assert res_status == "needs_review"

    db_session.refresh(document)
    assert document.status == "needs_review"

    # Verify document appears in review queue
    admin = make_user("config_admin", email="admin_rev@example.com", password="pw", org=io_user.organization)
    admin_token = login(client, "admin_rev@example.com", "pw").json()["access_token"]
    queue_resp = client.get("/documents?status=needs_review", headers=auth_headers(admin_token))
    assert queue_resp.status_code == 200
    doc_ids = [d["id"] for d in queue_resp.json()]
    assert str(document.id) in doc_ids


def test_ai_parser_fail_closed_on_empty_text_or_exception(db_session, make_org, make_user):
    """Fail-closed rule: empty raw_text or parser exception marks document 'needs_review', never 'ready'."""
    # 1. Empty raw text
    case, io_user, doc_empty = _setup_case_and_doc(db_session, make_org, make_user, raw_text="")
    res_status = ai_worker.process_tag_document(str(doc_empty.id), db=db_session)
    assert res_status == "needs_review"
    db_session.refresh(doc_empty)
    assert doc_empty.status == "needs_review"

    # 2. Crash / Exception during processing
    case, io_user, doc_err = _setup_case_and_doc(db_session, make_org, make_user, raw_text="Valid text")

    def mock_failing_parse(text, doc_type="general"):
        raise RuntimeError("Simulated internal worker crash")

    original_parser = ai_worker.parse_text_for_sensitive_spans
    ai_worker.parse_text_for_sensitive_spans = mock_failing_parse
    try:
        res_status2 = ai_worker.process_tag_document(str(doc_err.id), db=db_session)
        assert res_status2 == "needs_review"
        db_session.refresh(doc_err)
        assert doc_err.status == "needs_review"
    finally:
        ai_worker.parse_text_for_sensitive_spans = original_parser


def test_ai_parser_audit_trail_integrity(db_session, make_org, make_user):
    """AI Parser execution writes to the audit trail and preserves the cryptographic hash chain."""
    raw_text = "Accused Rahul Sharma, PAN ABCDE5678G."
    case, io_user, document = _setup_case_and_doc(db_session, make_org, make_user, raw_text=raw_text)

    ai_worker.process_tag_document(str(document.id), db=db_session)

    # Verify audit log entry
    audit_entry = (
        db_session.query(models.AuditLog)
        .filter_by(action="document_sensitivity_tagged", target_id=document.id)
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.action_metadata["tag_count"] >= 1
    assert "status" in audit_entry.action_metadata

    # Verify the entire audit hash chain remains intact
    assert verify_chain_intact(db_session) is True


def test_ai_parser_case_diary_tagging(db_session, make_org, make_user):
    """Case diary text is parsed and transitioned to status='ready'."""
    case, io_user, _ = _setup_case_and_doc(db_session, make_org, make_user, raw_text="Sample")

    diary_entry = models.CaseDiaryEntry(
        case_id=case.id,
        author_user_id=io_user.id,
        text="Interrogated suspect Vikram Malhotra at 9876543210 regarding stolen vehicle.",
        status="processing",
    )
    db_session.add(diary_entry)
    db_session.commit()
    db_session.refresh(diary_entry)

    res_status = ai_worker.process_tag_case_diary_entry(str(diary_entry.id), db=db_session)
    assert res_status == "ready"

    db_session.refresh(diary_entry)
    assert diary_entry.status == "ready"

    # Verify audit log
    audit_entry = (
        db_session.query(models.AuditLog)
        .filter_by(action="case_diary_sensitivity_tagged", target_id=diary_entry.id)
        .first()
    )
    assert audit_entry is not None
    assert verify_chain_intact(db_session) is True


def test_ai_parser_low_quality_ocr_resilience_and_safety(db_session, make_org, make_user):
    """Verifies that the parser handles degraded / low-quality OCR text:
    1. Extracts spaced phone, Aadhaar, and prefixed names with OCR punctuation (: - . /).
    2. Flags OCR-confused characters (e.g. PAN with 'I'/'O') to confidence 65, triggering needs_review.
    3. Detects severe OCR noise/fragmentation and routes to needs_review (fail-closed).
    """
    # 1. OCR text with formatting artifacts (colons after titles, spaced numbers)
    noisy_text = (
        "Witness: Dr. Rajesh Sharma, Mob: 98765 43210, Aadhaar: 2345   6789   0123. "
        "Suspect - Vikram Malhotra was present at the scene."
    )
    spans = ai_worker.parse_text_for_sensitive_spans(noisy_text)
    entity_map = {s["entity_type"]: noisy_text[s["span_start"]:s["span_end"]] for s in spans}

    assert "PERSON" in entity_map
    assert "Rajesh Sharma" in entity_map["PERSON"] or "Vikram Malhotra" in entity_map["PERSON"]
    assert "PHONE_NUMBER" in entity_map
    assert "98765 43210" in entity_map["PHONE_NUMBER"]
    assert "AADHAAR" in entity_map
    assert "2345   6789   0123" in entity_map["AADHAAR"]

    # 2. Degraded PAN with OCR letter confusion (I instead of 1)
    ocr_corrupted_pan_text = "Complainant Shri Amit Kumar, PAN ABCDEI234F."
    case1, user1, doc_pan = _setup_case_and_doc(db_session, make_org, make_user, raw_text=ocr_corrupted_pan_text)
    status1 = ai_worker.process_tag_document(str(doc_pan.id), db=db_session)
    assert status1 == "needs_review"  # Fail-closed triggered by low confidence (65)
    db_session.refresh(doc_pan)
    assert doc_pan.status == "needs_review"

    # 3. Heavily garbled OCR garbage text (scan quality too low to decipher)
    garbled_ocr_text = "~!@#$%^&*()_+=-`~ <><><> ?/::;{}[]\\| 1234567890 !@#$%^&*()_+=-`~"
    case2, user2, doc_noise = _setup_case_and_doc(db_session, make_org, make_user, raw_text=garbled_ocr_text)
    status2 = ai_worker.process_tag_document(str(doc_noise.id), db=db_session)
    assert status2 == "needs_review"  # Fail-closed triggered by text quality assessment
    db_session.refresh(doc_noise)
    assert doc_noise.status == "needs_review"

