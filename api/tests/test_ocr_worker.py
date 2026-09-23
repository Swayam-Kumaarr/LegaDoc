"""
Unit and integration tests for OCR Worker & Layout Reconstruction Pipeline:
- Spatial IoU Non-Maximum Suppression (cross-lingual ghost box elimination)
- Adaptive row clustering & column-aware reading order reconstruction
- Bilingual FIR extraction (Delhi & Haryana formats)
- Fallback mechanics (Tesseract fallback on PaddleOCR exception)
- Fail-closed security on empty text or corrupted scan
- End-to-end handoff to AI Parser Worker
"""

import importlib.util
import json
import os
import sys
from uuid import UUID, uuid4

import fitz  # PyMuPDF — also used directly by worker.py for PDF handling
import pytest

from app import models
from app.audit import verify_chain_intact
from tests.conftest import TestSessionLocal, auth_headers, login

# Dynamically load ocr_worker and layout_reconstruction
_ocr_worker_dir = (
    "/workers/ocr_worker"
    if os.path.exists("/workers/ocr_worker")
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "workers", "ocr_worker")
)

# Load layout_reconstruction
_layout_path = os.path.join(_ocr_worker_dir, "layout_reconstruction.py")
layout_spec = importlib.util.spec_from_file_location("layout_reconstruction", _layout_path)
layout_mod = importlib.util.module_from_spec(layout_spec)
sys.modules["layout_reconstruction"] = layout_mod
layout_spec.loader.exec_module(layout_mod)

# Load ocr worker
_worker_path = os.path.join(_ocr_worker_dir, "worker.py")
ocr_spec = importlib.util.spec_from_file_location("ocr_worker_module", _worker_path)
ocr_worker = importlib.util.module_from_spec(ocr_spec)
sys.modules["ocr_worker_module"] = ocr_worker
ocr_spec.loader.exec_module(ocr_worker)

# Load ai_parser worker for end-to-end handoff
_ai_worker_dir = (
    "/workers/ai_parser_worker"
    if os.path.exists("/workers/ai_parser_worker")
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "workers", "ai_parser_worker")
)
_ai_worker_path = os.path.join(_ai_worker_dir, "worker.py")
ai_spec = importlib.util.spec_from_file_location("ai_parser_worker_module", _ai_worker_path)
ai_worker = importlib.util.module_from_spec(ai_spec)
sys.modules["ai_parser_worker_module"] = ai_worker
ai_spec.loader.exec_module(ai_worker)


@pytest.fixture(autouse=True)
def _patch_worker_sessions(monkeypatch):
    """Ensure workers use in-memory SQLite TestSessionLocal."""
    monkeypatch.setattr(ocr_worker, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(ai_worker, "SessionLocal", TestSessionLocal)


def _load_delhi_test_boxes():
    fixture_path = os.path.join(_ocr_worker_dir, "test_firs", "delhi_ocr_boxes.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_fixture_boxes(name):
    """Real detections captured from the fixture scans by the worker's own
    engines, so these tests exercise the same input production sees."""
    with open(os.path.join(_ocr_worker_dir, "test_firs", name), "r", encoding="utf-8") as f:
        return json.load(f)


def _create_test_document(db_session, make_org, make_user):
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

    db_session.add(models.CaseAssignment(case_id=case.id, io_user_id=io_user.id))

    document = models.Document(
        case_id=case.id,
        doc_type="FIR",
        version=1,
        storage_path="mock/storage/fir.png",
        doc_hash="mockhash123",
        raw_text=None,
        status="processing",
        chain_status="pending",
        uploaded_by=io_user.id,
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return case, io_user, document


def test_spatial_iou_nms_eliminates_duplicate_boxes():
    """Verifies that spatial IoU Non-Maximum Suppression eliminates overlapping ghost boxes."""
    raw_boxes = _load_delhi_test_boxes()
    assert len(raw_boxes) > 300

    deduped = layout_mod.deduplicate_boxes_nms(raw_boxes, iou_thresh=0.35, containment_thresh=0.65)
    # Box count should be slashed by >50%
    assert len(deduped) < len(raw_boxes) * 0.60
    assert len(deduped) > 100

    # Ensure no remaining boxes have high spatial overlap
    for i, b1 in enumerate(deduped):
        for j, b2 in enumerate(deduped):
            if i != j:
                iou = layout_mod.compute_box_iou(b1["box"], b2["box"])
                assert iou <= 0.50


def test_layout_row_clustering_preserves_reading_order():
    """Verifies that bounding boxes on the same horizontal line assemble in natural reading order."""
    raw_boxes = _load_delhi_test_boxes()
    deduped = layout_mod.deduplicate_boxes_nms(raw_boxes)
    rows = layout_mod.reconstruct_layout_rows(deduped)

    assert len(rows) > 30

    # Locate the header row containing District and Police Station
    header_rows = [r for r in rows if "District" in r["text"] and ("P.S" in r["text"] or "KOTwALI" in r["text"])]
    assert len(header_rows) >= 1
    header_line = header_rows[0]["text"]

    # Verify column order: District appears before Police Station
    dist_idx = header_line.find("District")
    ps_idx = header_line.find("KOTwALI")
    assert dist_idx != -1
    assert ps_idx != -1
    assert dist_idx < ps_idx


def test_bilingual_fir_extraction_delhi():
    """Accurately extracts all canonical fields from real Delhi Police FIR OCR data."""
    raw_boxes = _load_delhi_test_boxes()
    res = layout_mod.process_ocr_boxes_to_layout(raw_boxes)

    assert res["template"] == "Delhi Police FIR"
    fields = res["fields"]

    # 1. FIR Number
    assert fields["fir_number"] == "80082511"
    # 2. District
    assert "NORTH" in fields["district"]
    # 3. Police Station
    assert "KOTwALI" in fields["police_station"]
    # 4. Year
    assert fields["year"] == "2025"
    # 5. Registration Date
    assert fields["registration_date"] == "03/09/2025"
    # 6. Registration Time — blank on this FIR: the "Information received at
    # P.S." row has a "Time :" label and no value. 09:20 is the occurrence
    # "Time From" and 21:49 the Daily Diary time (issue #107).
    assert fields["registration_time"] is None
    # 7. Sections (BNS 303(2))
    assert any("303" in s for s in fields["ipc_sections"])
    # 8. Type of Information
    assert "web" in fields["type_of_information"].lower()
    # 9. Complainant
    assert "sudhir" in fields["complainant"].lower()
    # 10. Address
    assert "ali pur road" in fields["address"].lower()
    # 11. Place of Occurrence
    assert "LAL QILA" in fields["place_of_occurrence"] or "JAIN PARV" in fields["place_of_occurrence"]


def test_bilingual_fir_extraction_haryana():
    """Accurately parses a bilingual Hindi/English Haryana Police FIR template."""
    haryana_text_lines = [
        {"box": [50, 20, 200, 40], "text": "District: Ambala / जिला: अम्बाला", "confidence": 0.95},
        {"box": [300, 20, 500, 40], "text": "P.S.: Kotwali / थाना: कोतवाली", "confidence": 0.95},
        {"box": [600, 20, 700, 40], "text": "Year: 2024 / वर्ष: 2024", "confidence": 0.95},
        {"box": [50, 50, 300, 70], "text": "FIR No: 151 / प्रथम सूचना रिपोर्ट: 151", "confidence": 0.95},
        {"box": [350, 50, 500, 70], "text": "Date: 12/05/2024 / दिनांक: 12/05/2024", "confidence": 0.95},
        {"box": [50, 80, 400, 100], "text": "Acts & Sections: भा.दं.सं (IPC) 379, 411", "confidence": 0.95},
        {"box": [50, 110, 350, 130], "text": "Complainant / शिकायतकर्ता: Ramesh Kumar s/o Sh. Ram Lal", "confidence": 0.95},
        {"box": [50, 140, 350, 160], "text": "Address / पता: Model Town Ambala City", "confidence": 0.95},
    ]

    res = layout_mod.process_ocr_boxes_to_layout(haryana_text_lines)
    fields = res["fields"]

    assert fields["fir_number"] == "151"
    assert "Ambala" in fields["district"]
    assert "Kotwali" in fields["police_station"]
    assert fields["year"] == "2024"
    assert fields["registration_date"] == "12/05/2024"
    assert any("379" in s for s in fields["ipc_sections"])
    assert "Ramesh Kumar" in fields["complainant"]
    assert "Model Town" in fields["address"]


def test_ocr_worker_tesseract_fallback_on_engine_error(db_session, make_org, make_user, monkeypatch):
    """When PaddleOCR throws an error, the worker falls back to Tesseract and records the engine used."""
    case, io_user, document = _create_test_document(db_session, make_org, make_user)

    # Mock storage to return dummy image bytes
    class DummyStorage:
        def get(self, path):
            return b"dummy_image_data"

    # Simulate PaddleOCR failing and Tesseract succeeding
    def mock_failing_paddle(bytes_):
        raise RuntimeError("PaddleOCR runtime model initialization failed")

    def mock_successful_tesseract(bytes_):
        return [
            {"text": "FIR No: 999", "confidence": 0.9, "box": [10, 10, 100, 30]},
            {"text": "District: Central", "confidence": 0.9, "box": [110, 10, 200, 30]},
        ]

    monkeypatch.setattr(ocr_worker, "run_paddle_ocr", mock_failing_paddle)
    monkeypatch.setattr(ocr_worker, "run_tesseract_fallback", mock_successful_tesseract)

    res = ocr_worker.process_extract_document(
        str(document.id),
        db=db_session,
        storage=DummyStorage(),
    )

    assert res["status"] == "success"
    assert res["ocr_engine"] == "tesseract_fallback"

    db_session.refresh(document)
    assert document.ocr_engine == "tesseract_fallback"
    assert "FIR No: 999" in document.raw_text


def test_ocr_worker_fail_closed_on_empty_text_or_engine_crash(db_session, make_org, make_user, monkeypatch):
    """Fail-closed rule: if all OCR engines fail or produce empty text, document is marked needs_review."""
    case, io_user, document = _create_test_document(db_session, make_org, make_user)

    class DummyStorage:
        def get(self, path):
            return b"empty_image"

    def mock_failing_both(bytes_):
        raise RuntimeError("All OCR engines crashed")

    monkeypatch.setattr(ocr_worker, "run_paddle_ocr", mock_failing_both)
    monkeypatch.setattr(ocr_worker, "run_tesseract_fallback", mock_failing_both)

    res = ocr_worker.process_extract_document(
        str(document.id),
        db=db_session,
        storage=DummyStorage(),
    )

    assert res["status"] == "needs_review"
    db_session.refresh(document)
    assert document.status == "needs_review"


def _make_pdf_with_text_layer(pages_text):
    """Builds a real, tiny PDF with a genuine embedded text layer (not a
    scanned image) — the same shape as a real government e-filing export,
    confirmed against an actual submitted FIR PDF during this feature's
    development: it had 4 pages of real extractable text, not raster
    scans. Built with PyMuPDF itself rather than depending on reportlab or
    any file outside the repo."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_ocr_worker_reads_pdf_native_text_layer_without_ocr(db_session, make_org, make_user, monkeypatch):
    """A PDF with a real text layer (government e-filing exports, not
    scanned paper) should be read directly — faster and far more accurate
    than rasterizing to an image and OCRing it. Neither OCR engine should
    even be called."""
    case, io_user, document = _create_test_document(db_session, make_org, make_user)

    pdf_bytes = _make_pdf_with_text_layer([
        "FIRST INFORMATION REPORT\nDistrict: Kolkata\nFIR No: RC2220 21E0011",
        "Complainant: Test Officer\nAddress: 570 KMs North of CBI EO-IV",
    ])

    class DummyStorage:
        def get(self, path):
            return pdf_bytes

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("OCR engine should not run when a PDF text layer is present")

    monkeypatch.setattr(ocr_worker, "run_paddle_ocr", _fail_if_called)
    monkeypatch.setattr(ocr_worker, "run_tesseract_fallback", _fail_if_called)

    res = ocr_worker.process_extract_document(str(document.id), db=db_session, storage=DummyStorage())

    assert res["status"] == "success"
    assert res["ocr_engine"] == "pdf_native_text"
    assert "Kolkata" in res["raw_text"]
    assert "RC2220 21E0011" in res["raw_text"]
    assert "Test Officer" in res["raw_text"]
    assert "--- Page Break ---" in res["raw_text"]

    db_session.refresh(document)
    assert document.ocr_engine == "pdf_native_text"
    assert document.status == "processing"  # OCR's job is raw_text only; AI Parser sets ready/needs_review


def test_ocr_worker_falls_back_to_ocr_for_image_only_pdf(db_session, make_org, make_user, monkeypatch):
    """A PDF with no usable text layer (a genuine paper scan saved as PDF)
    must still go through the real per-page OCR path, not silently return
    empty text."""
    case, io_user, document = _create_test_document(db_session, make_org, make_user)

    # A real one-page PDF with no text inserted — i.e. image-only in spirit
    # (this test doesn't embed an actual raster image; it only proves the
    # code path decides to OCR rather than accepting an empty native layer).
    blank_pdf = fitz.open()
    blank_pdf.new_page()
    pdf_bytes = blank_pdf.tobytes()
    blank_pdf.close()

    class DummyStorage:
        def get(self, path):
            return pdf_bytes

    def mock_paddle(bytes_):
        return [{"text": "Scanned FIR text", "confidence": 0.9, "box": [10, 10, 100, 30]}]

    monkeypatch.setattr(ocr_worker, "run_paddle_ocr", mock_paddle)

    res = ocr_worker.process_extract_document(str(document.id), db=db_session, storage=DummyStorage())

    assert res["status"] == "success"
    assert res["ocr_engine"] == "paddleocr"
    assert "Scanned FIR text" in res["raw_text"]


def test_ocr_worker_to_ai_parser_handoff_e2e(client, db_session, make_org, make_user):
    """End-to-end integration: OCR worker extracts layout text -> AI parser auto-tags PII ->
    Assigned IO sees unredacted text -> Restricted role sees masked [REDACTED:PERSON]."""
    case, io_user, document = _create_test_document(db_session, make_org, make_user)
    raw_boxes = _load_delhi_test_boxes()

    # 1. OCR Worker executes with real Delhi FIR OCR data
    ocr_res = ocr_worker.process_extract_document(
        str(document.id),
        db=db_session,
        mock_boxes=raw_boxes,
    )
    assert ocr_res["status"] == "success"
    db_session.refresh(document)
    assert document.raw_text is not None

    # Verify OCR audit log was written
    ocr_audit = (
        db_session.query(models.AuditLog)
        .filter_by(action="document_ocr_extracted", target_id=document.id)
        .first()
    )
    assert ocr_audit is not None
    assert ocr_audit.action_metadata["extracted_fields"]["fir_number"] == "80082511"

    # 2. AI Parser Worker executes on the newly populated raw_text
    ai_status = ai_worker.process_tag_document(str(document.id), db=db_session)
    assert ai_status in ("ready", "needs_review")

    db_session.refresh(document)
    tags = db_session.query(models.DocumentSensitivityTag).filter_by(document_id=document.id).all()
    assert len(tags) >= 1

    # 3. Assigned IO calls GET /documents/{id} -> sees full text
    io_token = login(client, io_user.email, "pw").json()["access_token"]
    io_resp = client.get(f"/documents/{document.id}", headers=auth_headers(io_token))
    assert io_resp.status_code == 200
    assert "80082511" in io_resp.json()["text"]

    # 4. Restricted role (cyber_cell) on same case -> sees masked text
    specialist = make_user("cyber_cell", email="cyber_spec@example.com", password="pw", org=io_user.organization)
    db_session.add(models.CaseAssignment(case_id=case.id, io_user_id=specialist.id))
    db_session.commit()

    spec_token = login(client, "cyber_spec@example.com", "pw").json()["access_token"]
    spec_resp = client.get(f"/documents/{document.id}", headers=auth_headers(spec_token))
    assert spec_resp.status_code == 200
    masked_text = spec_resp.json()["text"]
    assert "[REDACTED:PERSON]" in masked_text

    # Verify audit chain integrity remains unbroken after both worker writes
    assert verify_chain_intact(db_session) is True


def test_ocr_pipeline_with_multilingual_haryana_fir(client, db_session, make_org, make_user):
    """Verifies the complete flow with a bilingual Hindi/English FIR."""
    case, io_user, document = _create_test_document(db_session, make_org, make_user)

    haryana_boxes = [
        {"box": [50, 20, 200, 40], "text": "District: Ambala / जिला: अम्बाला", "confidence": 0.95},
        {"box": [300, 20, 500, 40], "text": "P.S.: Kotwali / थाना: कोतवाली", "confidence": 0.95},
        {"box": [600, 20, 700, 40], "text": "Year: 2024 / वर्ष: 2024", "confidence": 0.95},
        {"box": [50, 50, 300, 70], "text": "FIR No: 151 / प्रथम सूचना रिपोर्ट: 151", "confidence": 0.95},
        {"box": [350, 50, 500, 70], "text": "Date: 12/05/2024 / दिनांक: 12/05/2024", "confidence": 0.95},
        {"box": [50, 80, 400, 100], "text": "Acts & Sections: भा.दं.सं (IPC) 379, 411", "confidence": 0.95},
        {"box": [50, 110, 450, 130], "text": "Complainant / शिकायतकर्ता: Ramesh Kumar s/o Sh. Ram Lal", "confidence": 0.95},
        {"box": [50, 140, 350, 160], "text": "Address / पता: Model Town Ambala City", "confidence": 0.95},
        {"box": [50, 170, 350, 190], "text": "Contact / फोन: 9876543210 Aadhaar 2345 6789 0123", "confidence": 0.95},
    ]

    # Run OCR worker
    ocr_res = ocr_worker.process_extract_document(
        str(document.id),
        db=db_session,
        mock_boxes=haryana_boxes,
    )
    assert ocr_res["status"] == "success"
    assert ocr_res["fields"]["fir_number"] == "151"

    # Run AI Parser
    ai_status = ai_worker.process_tag_document(str(document.id), db=db_session)
    assert ai_status == "ready"

    # Verify tags created for phone, aadhaar, person
    tags = db_session.query(models.DocumentSensitivityTag).filter_by(document_id=document.id).all()
    entity_types = {t.entity_type for t in tags}
    assert "PHONE_NUMBER" in entity_types
    assert "AADHAAR" in entity_types

    assert verify_chain_intact(db_session) is True


def test_devanagari_numeral_normalization():
    """Verifies that Devanagari numerals (०-९) normalize accurately to ASCII digits."""
    raw_hindi_number = "०१४२/२०२४"
    norm = layout_mod.normalize_devanagari_digits(raw_hindi_number)
    assert norm == "0142/2024"

    hindi_date = "१५/०८/२०२४"
    assert layout_mod.normalize_devanagari_digits(hindi_date) == "15/08/2024"


def test_cross_lingual_devanagari_priority_nms():
    """Verifies that authentic Devanagari detections suppress overlapping Latin ASCII ghost boxes
    emitted by single-script English CTC decoders.
    """
    # Simulate an English CTC hallucination ('T1T 2llldl' at conf 0.89) overlapping authentic Hindi ('थाना कोतवाली' at conf 0.82)
    boxes = [
        {
            "box": [100, 50, 300, 80],
            "text": "T1T 2llldl",
            "confidence": 0.89,
            "lang": "en",
        },
        {
            "box": [100, 50, 295, 80],
            "text": "थाना कोतवाली",
            "confidence": 0.82,
            "lang": "hi",
        },
    ]

    deduped = layout_mod.deduplicate_boxes_nms(boxes, iou_thresh=0.35)
    assert len(deduped) == 1
    assert deduped[0]["text"] == "थाना कोतवाली"


def test_pure_hindi_fir_extraction_up_police():
    """Accurately extracts canonical FIR fields from a pure Hindi Uttar Pradesh Police FIR
    using Devanagari script and Devanagari numerals.
    """
    up_fir_boxes = [
        {"box": [50, 20, 200, 40], "text": "उत्तर प्रदेश पुलिस", "confidence": 0.95},
        {"box": [50, 50, 250, 70], "text": "जनपद: वाराणसी", "confidence": 0.94},
        {"box": [300, 50, 500, 70], "text": "थाना: सिगरा", "confidence": 0.94},
        {"box": [550, 50, 700, 70], "text": "वर्ष: २०२४", "confidence": 0.95},
        {"box": [50, 80, 350, 100], "text": "मु.अ.सं.: ०१४२/२०२४", "confidence": 0.96},
        {"box": [400, 80, 650, 100], "text": "दिनांक: १५/०८/२०२४ समय: १४:३० बजे", "confidence": 0.94},
        {"box": [50, 110, 450, 130], "text": "धाराएं: ३७९, ४११ भा.दं.सं.", "confidence": 0.95},
        {"box": [50, 140, 500, 160], "text": "वादी का नाम: सुरेश कुमार पुत्र श्री राम मनोहर", "confidence": 0.93},
        {"box": [50, 170, 450, 190], "text": "निवासी: संकट मोचन, वाराणसी", "confidence": 0.92},
        {"box": [50, 200, 500, 220], "text": "घटना स्थल: लंका चौराहा के पास, वाराणसी", "confidence": 0.93},
        {"box": [50, 230, 600, 250], "text": "घटना का विवरण: वादी का मोबाइल फोन अज्ञात चोर द्वारा चोरी कर लिया गया", "confidence": 0.92},
    ]

    res = layout_mod.process_ocr_boxes_to_layout(up_fir_boxes)
    assert res["template"] == "UP Police FIR"
    fields = res["fields"]

    assert fields["fir_number"] == "0142/2024"
    assert "वाराणसी" in fields["district"]
    assert "सिगरा" in fields["police_station"]
    assert fields["year"] == "2024"
    assert fields["registration_date"] == "15/08/2024"
    assert "14:30" in fields["registration_time"]
    assert any("379" in s for s in fields["ipc_sections"])
    assert "सुरेश कुमार" in fields["complainant"]
    assert "संकट मोचन" in fields["address"]
    assert "लंका चौराहा" in fields["place_of_occurrence"]
    assert "मोबाइल फोन" in fields["incident_description"]



def test_line_level_read_is_not_duplicated_by_its_own_word_fragments():
    """A line and the word boxes detected under it are the same text at two
    granularities, and spatial NMS cannot separate them: when a fragment wins
    on confidence it is kept first, and the containing line then measures as
    overlap/area_of_line — too small to trip either threshold — so both
    survive and the line is emitted twice ("Priya Menon Menon").

    Reproduces the geometry seen live from PaddleOCR's bilingual pass: the
    English engine returns one box per line, the Devanagari engine one per
    word, and the fragments score higher.
    """
    boxes = [
        {"text": "Complainant: Priya Menon", "confidence": 0.97, "box": [60, 280, 400, 310]},
        {"text": "Priya", "confidence": 1.00, "box": [240, 283, 306, 309]},
        {"text": "Menon", "confidence": 1.00, "box": [315, 283, 402, 309]},
    ]

    text = layout_mod.process_ocr_boxes_to_layout(boxes)["reconstructed_text"]

    assert "Priya Menon" in text
    assert text.count("Menon") == 1, f"fragment duplicated the line: {text!r}"
    assert text.count("Priya") == 1, f"fragment duplicated the line: {text!r}"


def test_devanagari_numerals_alone_do_not_outrank_a_confident_latin_read():
    """has_devanagari matches the whole block, numerals included, so the Hindi
    pass's Indic-numeral guess over printed Latin digits counted as authentic
    script and outranked a more confident Latin read of the same region.
    Only Devanagari *letters* are evidence the text is genuinely Hindi.
    """
    assert layout_mod.has_devanagari_letters("थाना")
    assert not layout_mod.has_devanagari_letters("४१")
    assert not layout_mod.has_devanagari_letters("15४")
    assert layout_mod.has_devanagari("४१"), "block-level check should still match numerals"

    latin = {"text": "Section 154", "confidence": 0.98, "box": [60, 100, 390, 128]}
    ghost = {"text": "15४", "confidence": 0.89, "box": [252, 104, 302, 127]}

    kept = layout_mod.deduplicate_boxes_nms([ghost, latin])
    assert [b["text"] for b in kept] == ["Section 154"]


def test_hindi_lines_of_a_real_bilingual_fir_are_readable(monkeypatch):
    """Issue #91. PaddleOCR's Hindi model drops conjuncts and reph and emits
    the ि matra in visual order, so the Haryana FIR's title came out as
    "पथम सूचना िरपोट" and "प्रक्रिया" as "पिकया" — garbage in front of a
    judge. Tesseract's hin model reads those same lines correctly, so the
    Devanagari is taken from it and everything else stays with Paddle."""
    paddle = _load_fixture_boxes("haryana_paddle_boxes.json")
    tess = _load_fixture_boxes("haryana_tesseract_hin_boxes.json")

    before = layout_mod.process_ocr_boxes_to_layout(paddle)["reconstructed_text"]
    after = layout_mod.process_ocr_boxes_to_layout(paddle, tess)["reconstructed_text"]

    # What the page actually says.
    for phrase in ("सूचना", "रिपोर्ट", "प्रक्रिया", "अधिनियम", "दिनांक", "अपराध की घटना"):
        assert phrase in after, phrase

    # What PaddleOCR made of it.
    for garbled in ("िरपोट", "पिकया", "सिंहंता", "धिनेयम"):
        assert garbled in before, garbled
        assert garbled not in after, garbled


def test_fusion_keeps_latin_and_digits_from_paddleocr():
    """Tesseract's hin model drops the digit 1 ("Section 154" -> "54",
    "2017" -> "207"), which on an FIR corrupts the statute and date values
    that matter most. Only the Devanagari comes from it."""
    paddle = _load_fixture_boxes("haryana_paddle_boxes.json")
    tess = _load_fixture_boxes("haryana_tesseract_hin_boxes.json")

    res = layout_mod.process_ocr_boxes_to_layout(paddle, tess)
    text, fields = res["reconstructed_text"], res["fields"]

    assert "KURUKSHETRA" in fields["district"]
    assert "SHAHABAD" in fields["police_station"]
    assert "2017" in text and "24/07/2017" in text
    assert "154" in text  # Section 154 Cr.P.C., the FIR's own statute
    # The label sits between "FIR No." and the number as a Devanagari gloss;
    # matching straight through it used to capture the wrong digit entirely.
    assert fields["fir_number"] == "0380"


def test_an_english_only_page_is_left_to_paddleocr_alone():
    """The Devanagari pass is a second opinion on Hindi, not a general
    improvement. On the real Delhi FIR — English, 4 spurious Devanagari
    detections out of 371 — Tesseract contributes only its own Latin-as-
    Devanagari garbage ("हार" over "Act(s)"), so the page must not be fused
    at all."""
    paddle = _load_delhi_test_boxes()
    tess = _load_fixture_boxes("delhi_tesseract_hin_boxes.json")

    assert layout_mod.page_is_bilingual(paddle) is False
    assert layout_mod.page_is_bilingual(_load_fixture_boxes("haryana_paddle_boxes.json")) is True

    unfused = layout_mod.process_ocr_boxes_to_layout(paddle)["reconstructed_text"]
    offered = layout_mod.process_ocr_boxes_to_layout(paddle, tess)["reconstructed_text"]
    assert offered == unfused


def test_latin_half_of_a_mixed_script_box_survives_fusion():
    """Paddle reads the label "P.S. थाना:" as "P.S. धानn:". Dropping such a
    box wholesale because it holds Devanagari took the "P.S." with it — and
    that Latin label is what the police-station field matches on. Only the
    untrusted words are stripped, and a word mixing both scripts is untrusted
    whole: keeping its Latin letters put "n: SHAHABAD" in the field (#107)."""
    assert layout_mod.strip_devanagari("P.S. धानn:") == "P.S."
    assert layout_mod.strip_devanagari("District fज़:") == "District"
    assert layout_mod.strip_devanagari("धारा") == ""

    # Tesseract's transliteration of Latin words carries a glyph or two among
    # symbols; real Hindi words are almost entirely Devanagari letters.
    assert layout_mod.is_devanagari_word("रिपोर्ट") is True
    assert layout_mod.is_devanagari_word("#88१%8॥4&") is False
    assert layout_mod.is_devanagari_word("ए.5.") is False


def _fused_haryana():
    return layout_mod.process_ocr_boxes_to_layout(
        _load_fixture_boxes("haryana_paddle_boxes.json"),
        _load_fixture_boxes("haryana_tesseract_hin_boxes.json"),
    )


def test_english_pass_transliteration_of_hindi_is_removed():
    """Issue #107. PaddleOCR's English pass reads the Hindi on a bilingual
    FIR as Latin garbage, with no Devanagari for the fusion or NMS to catch.
    Whole-box glosses are dropped; bracketed glosses inside a real label are
    replaced by Tesseract's reading of the same spot."""
    res = _fused_haryana()
    text = res["reconstructed_text"]

    for junk in ("(4RT 154", ">R4IuT", "(4I)", "(fai)", "(ul T aoR)", "(a$)", "(fam)", "(faftc a.)"):
        assert junk not in text, junk

    assert "HARYANA POLiCE CITIZEN SERVICES (हरियाणा पुलिस नागरिक)" in text
    assert "(धारा 15४ दंड प्रक्रिया सहिंता के तहत)" in text
    assert "P.S. (थाना): SHAHABAD" in text
    assert "Date (दिनांक): 24/07/2017" in text
    assert "FIR No. (प्र.सू.रि.): 0380" in text


def test_removing_glosses_does_not_cost_a_field():
    """The token-trimming attempt at #107 clipped "P.S." and the police
    station took a wrong value. Every header field on the real Haryana FIR
    must come out exactly — including the Latin leftovers of the Hindi pass
    ("f:", "n:") that used to prefix the district and police station."""
    fields = _fused_haryana()["fields"]

    assert fields["fir_number"] == "0380"
    assert fields["district"] == "KURUKSHETRA"
    assert fields["police_station"] == "SHAHABAD"
    assert fields["year"] == "2017"
    assert fields["registration_date"] == "24/07/2017"
    assert fields["type_of_information"].startswith("Written")


def test_real_english_brackets_are_not_treated_as_glosses():
    """Only a bracket that sits under Tesseract's Devanagari is rewritten.
    English brackets — the statute line, the "(b)"/"(c)" item markers — have
    no Hindi on top of them and must survive untouched."""
    text = _fused_haryana()["reconstructed_text"]
    assert "(Under Section 154 Cr.P.C.)" in text
    assert "(b)Information received" in text
    assert "(c) General Diary Reference" in text

    latin = [{"text": "Accused (unknown): 2", "confidence": 0.95, "box": [0, 0, 400, 30]}]
    kept, dev = layout_mod.resolve_latin_glosses(latin, [])
    assert [b["text"] for b in kept] == ["Accused (unknown): 2"]

    # Devanagari elsewhere on the line does not license touching the bracket.
    far = [{"text": "थाना", "confidence": 0.95, "box": [600, 0, 700, 30]}]
    kept, dev = layout_mod.resolve_latin_glosses(latin, far)
    assert [b["text"] for b in kept] == ["Accused (unknown): 2"]
    assert dev == far


def test_registration_time_comes_from_the_information_received_row():
    """Issue #107. The first time on the page is the occurrence "Time From",
    printed above the registration row — 00:00 on Haryana, 09:20 on Delhi.
    Returning it under registration_time is wrong data, not missing data."""
    assert _fused_haryana()["fields"]["registration_time"] == "16:43 hrs"
    # Also without the Tesseract pass, where the label reads "Informnation 'eccived".
    paddle_only = layout_mod.process_ocr_boxes_to_layout(_load_fixture_boxes("haryana_paddle_boxes.json"))
    assert paddle_only["fields"]["registration_time"] == "16:43 hrs"

    # Delhi leaves the field blank; the Daily Diary time below it is not it.
    delhi = layout_mod.process_ocr_boxes_to_layout(_load_delhi_test_boxes())
    assert delhi["fields"]["registration_time"] is None


def test_registration_time_fallback_skips_occurrence_times():
    """Forms without an "Information received" row fall back to a labelled
    time, but never one from the occurrence period."""
    def time_of(lines):
        boxes = [
            {"box": [50, 20 + 30 * i, 600, 40 + 30 * i], "text": t, "confidence": 0.95}
            for i, t in enumerate(lines)
        ]
        return layout_mod.process_ocr_boxes_to_layout(boxes)["fields"]["registration_time"]

    assert time_of(["Time Period: Time From: 22:23 hrs Time To: 06:23 hrs"]) is None
    assert time_of(["घटना का समय से: १०:०० समय तक: ११:००"]) is None
    assert time_of([
        "Time From: 22:23 hrs Time To: 06:23 hrs",
        "दिनांक: १३/११/२०२४ समय: १४:३० बजे",
    ]) == "14:30 बजे"


def test_act_year_is_not_reported_as_a_section_number():
    """Issue #107. These forms tabulate the Act and its sections in separate
    columns — "1 | IPC 1860 | 380" — and the old pattern took the first 1-3
    digit run after the Act name. That truncated the Act's own year and
    reported "IPC 186" as the offence, while the real sections (380, 457) in
    the next column were never picked up. A wrong statute number on a charge
    sheet is not a cosmetic defect."""
    fields = _fused_haryana()["fields"]

    assert fields["ipc_sections"] == ["IPC 380", "IPC 457"]
    assert not any("186" in s for s in fields["ipc_sections"])


def test_sections_are_read_per_line_and_per_act():
    """A section belongs to the Act on its own row: the number two rows down
    is a different offence, and 2023 after BNS is the year it was enacted."""
    def sections(lines):
        boxes = [
            {"box": [50, 20 + 30 * i, 600, 40 + 30 * i], "text": t, "confidence": 0.95}
            for i, t in enumerate(lines)
        ]
        return layout_mod.process_ocr_boxes_to_layout(boxes)["fields"]["ipc_sections"]

    assert sections(["1 IPC 1860 380", "2 IPC 1860 457"]) == ["IPC 380", "IPC 457"]
    assert sections(["The Bharatiya Nyaya Sanhita (BNS), 2023 303(2)"]) == ["BNS 303(2)"]
    # A number printed before the Act name is not one of its sections; the
    # Section/s heading fallback still catches it.
    assert sections(["धाराएं: 379, 411 भा.दं.सं."]) == ["379"]
