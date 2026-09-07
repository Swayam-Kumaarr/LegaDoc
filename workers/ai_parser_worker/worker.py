"""
AI Parser Worker — self-hosted Presidio + spaCy NER & Indian Legal Domain Recognizers.
See SYSTEM_DESIGN.md Flow 2 Track B, Flow 6 (audit trail), and the "Security"
section's fail-closed rule.

Handles both Document text (post-OCR) and Case Diary entries (see "Case Diary
now routes through the redaction pipeline") — same task, same rule either way.

DB access pattern matches workers/chain_worker/worker.py — reuse api/app's
models/database/audit/config directly rather than duplicating the schema.
"""

import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional
from uuid import UUID

# Adjust sys.path to locate api/app as a package
_api_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "api")
if _api_path not in sys.path:
    sys.path.insert(0, _api_path)

from celery import Celery

from app import models
from app.audit import write_audit_log
from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)

app = Celery(
    "ai_parser_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

CONFIDENCE_REVIEW_THRESHOLD = 70  # 0-100; below this, auto-flag even on "success"

# Optional Presidio Analyzer import
try:
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    _HAS_PRESIDIO = True
except ImportError:
    _HAS_PRESIDIO = False

# The spaCy model this worker is built around. The Dockerfile installs exactly
# this one (~15MB). A bare AnalyzerEngine() ignores it and defaults to
# en_core_web_lg (~588MB), which is not in the image — so Presidio downloads it
# over the network on first use and then loads it, which pip-installs at
# runtime and gets the container OOM-killed (exit 137). Naming the model keeps
# the worker on what was actually built into it.
SPACY_MODEL = "en_core_web_sm"


# Presidio ships recognizers for many jurisdictions and enables all of them
# when `entities` is not passed. On Indian legal text that produced confident
# nonsense — a recorded timestamp matched UK_NHS, and "Sec" and "CrPC" matched
# ORGANIZATION.
#
# ORGANIZATION and DATE_TIME are deliberately absent. Masking a statute
# reference or a seizure date does not protect anyone and actively destroys the
# document: "[REDACTED:ORGANIZATION] 161 [REDACTED:ORGANIZATION]" is not a
# usable record of a statement recorded under Sec 161 CrPC, and a panchnama
# whose date is masked is worth little as evidence.
#
# Indian identifiers (Aadhaar, PAN, and the rest) are not in this list because
# Presidio has no recognizer for them — LegalPIIRecognizer below handles those
# natively, and its spans are merged in separately.
PRESIDIO_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "LOCATION",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
]

# Presidio scores 0.0-1.0. Below this a match is weak enough that masking it
# costs more in destroyed text than it saves in protected PII; the native
# recognizer carries the identifiers we actually care about at full confidence.
PRESIDIO_SCORE_THRESHOLD = 0.5

# Built once, not per document. AnalyzerEngine loads a spaCy pipeline on
# construction, so instantiating it inside the per-document path made every
# document pay the model load again.
_analyzer_engine = None


def _get_analyzer():
    """Lazily builds the shared AnalyzerEngine. Returns None if Presidio is
    unavailable or fails to initialise, so callers fall back to the native
    recognizer instead of losing the whole parse."""
    global _analyzer_engine
    if not _HAS_PRESIDIO:
        return None
    if _analyzer_engine is None:
        try:
            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
            })
            _analyzer_engine = AnalyzerEngine(
                nlp_engine=provider.create_engine(),
                supported_languages=["en"],
            )
        except Exception as exc:
            # Deliberately no fallback to a bare AnalyzerEngine(): that is the
            # path that reaches for en_core_web_lg and OOM-kills the worker.
            # Returning None drops to the native recognizer, which still
            # catches the Indian identifiers that matter most here.
            logger.warning(f"Presidio AnalyzerEngine initialisation failed: {exc}")
            return None
    return _analyzer_engine


class LegalPIIRecognizer:
    """Deterministic, high-precision pattern and vocabulary recognizers for
    Indian legal, police, forensic, and medical documents.
    Detects PERSON, PHONE_NUMBER, AADHAAR, PAN, EMAIL_ADDRESS, and MEDICAL_CONDITION.
    """

    PATTERNS = [
        # 1. Aadhaar Number (12 digits, doesn't start with 0 or 1, flexible space or dash)
        {
            "entity_type": "AADHAAR",
            "regex": re.compile(r"\b[2-9]\d{3}[ -]*\d{4}[ -]*\d{4}\b"),
            "confidence": 85,
        },
        # 2. PAN Card Number (Standard: 5 letters, 4 digits, 1 letter)
        {
            "entity_type": "PAN",
            "regex": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
            "confidence": 90,
        },
        # 2b. PAN Card with OCR character confusion (e.g. 'O'/'0' or 'I'/'1' in 4-digit block)
        # Sets lower confidence (65) so it safely auto-flags for human review (fail-closed)
        {
            "entity_type": "PAN",
            "regex": re.compile(r"\b[A-Z]{5}[ -]?[0-9OI]{4}[ -]?[A-Z]\b"),
            "confidence": 65,
        },
        # 3. Indian Phone Number (10 digits starting with 6-9, flexible grouping/spaces/hyphens or +91 prefix)
        {
            "entity_type": "PHONE_NUMBER",
            "regex": re.compile(
                r"(?:\+91[\-\s]?)?[6-9]\d{9}\b|"
                r"(?:\+91[\-\s]?)?[6-9]\d{4}[\s\-]?[0-9]{5}\b|"
                r"(?:\+91[\-\s]?)?[6-9]\d{2}[\s\-]?[0-9]{3}[\s\-]?[0-9]{4}\b|"
                r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"
            ),
            "confidence": 85,
        },
        # 4. Email Address
        {
            "entity_type": "EMAIL_ADDRESS",
            "regex": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
            "confidence": 95,
        },
        # 5. Medical Conditions / Forensic Injuries (MLC reports)
        {
            "entity_type": "MEDICAL_CONDITION",
            "regex": re.compile(
                r"(?i)\b(?:gunshot\s+wound|lacerated\s+wound|incised\s+wound|contusion|abrasion|"
                r"fracture|haemorrhage|poisoning|asphyxia|stab\s+wound|burn\s+injury|grievous\s+hurt|"
                r"head\s+injury|strangulation|rigor\s+mortis|post-mortem|traumatic\s+shock|"
                r"subdural\s+haematoma|acute\s+trauma|blunt\s+force\s+trauma)\b"
            ),
            "confidence": 85,
        },
        # 6. Person Names with Indian Police/Court prefixes, tolerant of OCR punctuation (: - . /) and spacing
        {
            "entity_type": "PERSON",
            "regex": re.compile(
                r"(?i:(?:\b(?:Mr|Mrs|Ms|Miss|Shri|Smt|Dr|Prof|Advocate|Adv|Inspector|Sub-Inspector|SI|ASI|HC|Constable|"
                r"Officer|Witness|Suspect|Accused|Victim|Complainant)\b[\.\:\-\/]?\s+)+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
            ),
            "confidence": 80,
            "capture_group": 1,
        },
        {
            "entity_type": "PERSON",
            "regex": re.compile(
                r"(?i)\b(?:named|alias|identified\s+as|son\s+of|daughter\s+of|w/o|s/o|d/o)[\s\:\-]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b"
            ),
            "confidence": 80,
            "capture_group": 1,
        },
        # 6c. Complainant / Informant / Accused names in FIR headers (tolerant of OCR mixed case)
        {
            "entity_type": "PERSON",
            "regex": re.compile(
                r"(?i)\b(?:Name|Complainant|Informant|Accused|Suspect|Victim)[\s\:\-\/\.]+(?:(?:Shri|Smt|Mr|Dr)\.?\s+)?([A-Za-z]{3,}(?:\s+[A-Za-z]{2,}){1,4})\b"
            ),
            "confidence": 80,
            "capture_group": 1,
        },
        # 6d. Parent/Spouse names following s/o, w/o, d/o with optional honorifics (LT. Sh., Smt., etc.)
        {
            "entity_type": "PERSON",
            "regex": re.compile(
                r"(?i)\b(?:son\s+of|daughter\s+of|wife\s+of|s/o|w/o|d/o)[\s\:\-\.]*(?:LT\.?\s*)?(?:Sh\.?|Smt\.?|Mr\.?|Dr\.?)?\s*([A-Za-z]{3,}(?:\s+[A-Za-z]{2,}){1,4})\b"
            ),
            "confidence": 80,
            "capture_group": 1,
        },
    ]

    @classmethod
    def find_spans(cls, text: str) -> List[Dict[str, Any]]:
        if not text:
            return []

        findings: List[Dict[str, Any]] = []

        for p in cls.PATTERNS:
            for match in p["regex"].finditer(text):
                if p.get("capture_group"):
                    start = match.start(p["capture_group"])
                    end = match.end(p["capture_group"])
                else:
                    start = match.start()
                    end = match.end()

                findings.append({
                    "entity_type": p["entity_type"],
                    "span_start": start,
                    "span_end": end,
                    "confidence": p["confidence"],
                })

        return findings


def _resolve_overlapping_spans(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sorts spans by start offset and resolves overlapping matches by higher confidence."""
    if not spans:
        return []

    sorted_spans = sorted(
        spans,
        key=lambda s: (s["span_start"], -(s["span_end"] - s["span_start"]), -s["confidence"]),
    )

    resolved: List[Dict[str, Any]] = []
    current_cursor = -1

    for s in sorted_spans:
        if s["span_start"] < current_cursor:
            continue
        resolved.append(s)
        current_cursor = s["span_end"]

    return resolved


def parse_text_for_sensitive_spans(text: str, doc_type: str = "general") -> List[Dict[str, Any]]:
    """Runs entity detection over raw text:
    1. Runs Presidio Analyzer if available in environment.
    2. Runs native LegalPIIRecognizer for Indian domain-specific identifiers.
    3. Merges and resolves overlapping spans cleanly.
    """
    all_spans: List[Dict[str, Any]] = []

    # 1. Presidio extraction if engine is present. Restricted to
    # PRESIDIO_ENTITIES — left unrestricted it enables every jurisdiction's
    # recognizers at once and mislabels ordinary legal text.
    analyzer = _get_analyzer()
    if analyzer is not None:
        try:
            results = analyzer.analyze(
                text=text,
                language="en",
                entities=PRESIDIO_ENTITIES,
                score_threshold=PRESIDIO_SCORE_THRESHOLD,
            )
            for res in results:
                ent_type = res.entity_type
                if ent_type == "US_PHONE_NUMBER":
                    ent_type = "PHONE_NUMBER"
                all_spans.append({
                    "entity_type": ent_type,
                    "span_start": res.start,
                    "span_end": res.end,
                    "confidence": int(round(res.score * 100)),
                })
        except Exception as exc:
            logger.warning(f"Presidio Analyzer execution skipped or failed: {exc}")

    # 2. Native Indian Legal / Medical Domain extraction
    native_spans = LegalPIIRecognizer.find_spans(text)
    all_spans.extend(native_spans)

    # 3. Resolve overlaps
    return _resolve_overlapping_spans(all_spans)


def assess_text_quality(text: str) -> tuple[bool, Optional[str]]:
    """Evaluates whether the raw text exhibits severe OCR degradation:
    - High non-alphanumeric noise / garbage characters.
    - Low alphanumeric ratio (< 50% on substantial text).
    - Unusually high proportion of isolated single-character tokens (OCR fragmentation).
    """
    if not text or len(text.strip()) < 30:
        return True, None

    cleaned = text.strip()
    non_ws = [c for c in cleaned if not c.isspace()]
    if not non_ws:
        return True, None

    alnum_count = sum(1 for c in non_ws if c.isalnum())
    alnum_ratio = alnum_count / len(non_ws)

    # If alphanumeric content is under 50% in a text with > 40 chars, it is garbled OCR
    if len(non_ws) > 40 and alnum_ratio < 0.50:
        return False, f"Low alphanumeric ratio ({alnum_ratio:.1%}): severe OCR noise"

    # Check for heavy token fragmentation (e.g. "t h e   f i r   n o")
    tokens = cleaned.split()
    if len(tokens) >= 10:
        single_char_tokens = sum(1 for t in tokens if len(t) == 1 and t.isalnum())
        single_ratio = single_char_tokens / len(tokens)
        if single_ratio > 0.45:
            return False, f"Excessive character fragmentation ({single_ratio:.1%}): degraded scan"

    return True, None


def process_tag_document(document_id: str, db: Optional[Any] = None) -> str:
    """Core orchestration for auto-tagging a document:
    1. Fetches Document and reads Document.raw_text.
    2. Checks OCR text quality for degradation / noise.
    3. Extracts sensitive spans.
    4. Writes DocumentSensitivityTag rows (never raw text).
    5. Evaluates confidence threshold (70) and quality: routes to 'ready' or 'needs_review'.
    6. Writes tamper-evident audit log under pg_advisory_xact_lock.
    7. Enforces FAIL-CLOSED rule on any exception or low-confidence tag.
    """
    session = db if db is not None else SessionLocal()
    try:
        doc_uuid = document_id if isinstance(document_id, UUID) else UUID(str(document_id))
        document = session.get(models.Document, doc_uuid)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        # Fail-closed check: if raw_text is missing/empty, route to needs_review
        if not document.raw_text or not document.raw_text.strip():
            document.status = "needs_review"
            session.commit()
            return "needs_review"

        # Check OCR quality / degradation
        is_quality_ok, quality_reason = assess_text_quality(document.raw_text)

        spans = parse_text_for_sensitive_spans(document.raw_text, doc_type=document.doc_type)

        # Clear prior auto-tags for this document to allow clean retries
        session.query(models.DocumentSensitivityTag).filter(
            models.DocumentSensitivityTag.document_id == document.id,
            models.DocumentSensitivityTag.source == "ai_parser",
        ).delete()

        # Insert sensitivity tags (coordinates + metadata only, NEVER raw text)
        for s in spans:
            tag = models.DocumentSensitivityTag(
                document_id=document.id,
                entity_type=s["entity_type"],
                span_start=s["span_start"],
                span_end=s["span_end"],
                confidence=s["confidence"],
                source="ai_parser",
            )
            session.add(tag)

        # Confidence review threshold (default: 70) and text quality gate
        has_low_confidence = any(s["confidence"] < CONFIDENCE_REVIEW_THRESHOLD for s in spans)
        if has_low_confidence or not is_quality_ok:
            document.status = "needs_review"
        else:
            document.status = "ready"

        session.commit()
        session.refresh(document)

        # Append to audit trail
        write_audit_log(
            session,
            action="document_sensitivity_tagged",
            case_id=document.case_id,
            actor_user_id=document.uploaded_by,
            target_type="document",
            target_id=document.id,
            metadata={
                "tag_count": len(spans),
                "status": document.status,
                "entity_types": sorted(list(set(s["entity_type"] for s in spans))),
                "min_confidence": min((s["confidence"] for s in spans), default=100),
                "ocr_quality_ok": is_quality_ok,
                "ocr_quality_reason": quality_reason,
            },
        )

        return document.status

    except Exception as exc:
        logger.exception(f"AI Parser Worker failure on document {document_id}: {exc}")
        # FAIL-CLOSED: On error, default to unreviewed full redaction
        try:
            if "document" in locals() and document is not None:
                document.status = "needs_review"
                session.commit()
        except Exception:
            session.rollback()
        return "needs_review"
    finally:
        if db is None:
            session.close()


def process_tag_case_diary_entry(case_diary_entry_id: str, db: Optional[Any] = None) -> str:
    """Core orchestration for auto-tagging a case diary entry:
    Runs sensitivity detection on entry.text, updates status to 'ready',
    and logs audit entry. Fails closed on error.
    """
    session = db if db is not None else SessionLocal()
    try:
        entry_uuid = case_diary_entry_id if isinstance(case_diary_entry_id, UUID) else UUID(str(case_diary_entry_id))
        entry = session.get(models.CaseDiaryEntry, entry_uuid)
        if entry is None:
            raise ValueError(f"CaseDiaryEntry {case_diary_entry_id} not found")

        # Analyze text
        spans = parse_text_for_sensitive_spans(entry.text)

        # Mark ready
        entry.status = "ready"
        session.commit()
        session.refresh(entry)

        write_audit_log(
            session,
            action="case_diary_sensitivity_tagged",
            case_id=entry.case_id,
            actor_user_id=entry.author_user_id,
            target_type="case_diary_entry",
            target_id=entry.id,
            metadata={"status": entry.status, "detected_entities": len(spans)},
        )

        return entry.status

    except Exception as exc:
        logger.exception(f"AI Parser Worker failure on diary entry {case_diary_entry_id}: {exc}")
        return "processing"
    finally:
        if db is None:
            session.close()


@app.task(name="ai_parser_worker.tag_document", bind=True, max_retries=5)
def tag_document(self, document_id: str):
    """Celery task entrypoint for document auto-tagging."""
    return process_tag_document(document_id)


@app.task(name="ai_parser_worker.tag_case_diary_entry", bind=True, max_retries=5)
def tag_case_diary_entry(self, case_diary_entry_id: str):
    """Celery task entrypoint for case diary auto-tagging."""
    return process_tag_case_diary_entry(case_diary_entry_id)
