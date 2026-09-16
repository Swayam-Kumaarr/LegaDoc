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
    _HAS_PRESIDIO = True
except ImportError:
    _HAS_PRESIDIO = False


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
                # Separators are REQUIRED in this last alternative. It exists for
                # foreign/NANP-style numbers written 123-456-7890, but with the
                # separators optional it reduced to \d{10} and matched any bare
                # ten-digit run — Unix timestamps, case-file numbers, seized
                # amounts. Confirmed: "Recorded 1725432000" was masked as
                # PHONE_NUMBER. Bare Indian mobiles are already covered by the
                # [6-9]\d{9} alternative above, so nothing is lost by requiring
                # punctuation here.
                r"\b\d{3}[-.]\d{3}[-.]\d{4}\b"
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
                r"Officer|Witness|Suspect|Accused|Victim|Complainant)\b[\.\:\-\/]?\s+)+)([A-Z][a-z]+(?:\s+(?!\w+\s*[:\-])[A-Z][a-z]+)*)\b"
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
                r"(?i)\b(?:Name|Complainant|Informant|Accused|Suspect|Victim)[\s\:\-\/\.]+(?:(?:Shri|Smt|Mr|Dr)\.?\s+)?([A-Za-z]{3,}(?:\s+(?!\w+\s*[:\-])[A-Za-z]{2,}){1,4})\b"
            ),
            "confidence": 80,
            "capture_group": 1,
        },
        # 6d. Parent/Spouse names following s/o, w/o, d/o with optional honorifics (LT. Sh., Smt., etc.)
        {
            "entity_type": "PERSON",
            "regex": re.compile(
                r"(?i)\b(?:son\s+of|daughter\s+of|wife\s+of|s/o|w/o|d/o)[\s\:\-\.]*(?:LT\.?\s*)?(?:Sh\.?|Smt\.?|Mr\.?|Dr\.?)?\s*([A-Za-z]{3,}(?:\s+(?!\w+\s*[:\-])[A-Za-z]{2,}){1,4})\b"
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


class CredentialIDRecognizer:
    """Pattern recognizers for the government/institutional ID formats this
    system's onboarding flow expects — a POSITIVE-extraction counterpart to
    LegalPIIRecognizer above (that one finds PII to hide; this one finds an
    identifier to surface and compare against a claimed identity). Patterns
    are deliberately permissive — this is candidate extraction for a human
    reviewer to confirm, not a validator that rejects real IDs for not
    matching a guessed format exactly.
    """

    PATTERNS = [
        # Government service/badge ID — matches the shape already used
        # throughout seed_data.py: "DL-POL-4921", "MHA-ADM-001", "CFSL-DIR-91",
        # "DEL-JUD-082", "NCRB-STAT-21" — 2-3 hyphen-separated alphanumeric
        # groups, letters-heavy on the first two, digits on the last.
        {
            "entity_type": "GOVT_SERVICE_ID",
            "regex": re.compile(r"\b[A-Z]{2,6}-[A-Z]{2,6}-\d{2,6}\b"),
            "confidence": 80,
        },
        # Bar Council of India enrollment number — "<State Code>/<Number>/<Year>",
        # e.g. "D/1234/2015", "DL/4521/2018", "MAH/998/2011".
        {
            "entity_type": "BAR_ENROLLMENT_NUMBER",
            "regex": re.compile(r"\b[A-Z]{1,4}/\d{1,6}/(?:19|20)\d{2}\b"),
            "confidence": 85,
        },
    ]

    @classmethod
    def find_spans(cls, text: str) -> List[Dict[str, Any]]:
        if not text:
            return []
        findings: List[Dict[str, Any]] = []
        for p in cls.PATTERNS:
            for match in p["regex"].finditer(text):
                findings.append({
                    "entity_type": p["entity_type"],
                    "value": match.group(0),
                    "span_start": match.start(),
                    "span_end": match.end(),
                    "confidence": p["confidence"],
                })
        return findings


def _resolve_overlapping_spans(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolves overlapping matches in favour of the higher-confidence span,
    then returns the survivors in document order.

    The previous implementation sorted by (span_start, -length, -confidence)
    and walked forward with a cursor, which decided overlaps purely by which
    span started first — confidence was only ever consulted to break a tie
    between two spans starting at the same offset with the same length. A
    PERSON guess at confidence 60 therefore beat a PAN match at confidence 95
    whenever it happened to start one character earlier, and the entity was
    recorded under the wrong type. The docstring claimed confidence ordering
    that the code did not implement.

    Entity *type* accuracy matters even though both spans get masked either
    way: the type is what lands in the audit trail, and it is what any future
    per-type access rule would key on. Masking "ABCDE1234F" as a PERSON is
    not the same record as masking it as a PAN.

    Ranking by confidence first, then by length, means the strongest claim on
    a region wins and weaker overlapping claims are dropped. Ties fall back to
    document order so the result stays deterministic — important, because
    these spans feed a hash-chained audit trail.
    """
    if not spans:
        return []

    ranked = sorted(
        spans,
        key=lambda s: (
            -s["confidence"],
            -(s["span_end"] - s["span_start"]),
            s["span_start"],
        ),
    )

    kept: List[Dict[str, Any]] = []
    for cand in ranked:
        if any(
            cand["span_start"] < k["span_end"] and k["span_start"] < cand["span_end"]
            for k in kept
        ):
            continue
        kept.append(cand)

    # Masking walks the text in order, so hand back document order, not rank.
    return sorted(kept, key=lambda s: s["span_start"])


_analyzer_engine = None
_analyzer_engine_init_failed = False

# Presidio ships recognizers for many jurisdictions and enables all of them
# when `entities` is not passed to analyze(). On Indian legal text that
# produced confident nonsense — a recorded timestamp matched UK_NHS, and
# "Sec"/"CrPC" matched ORGANIZATION.
#
# ORGANIZATION and DATE_TIME are deliberately absent. Masking a statute
# reference or a seizure date does not protect anyone and actively destroys
# the document: "[REDACTED:ORGANIZATION] 161 [REDACTED:ORGANIZATION]" is not
# a usable record of a statement recorded under Sec 161 CrPC, and a panchnama
# whose date is masked is worth little as evidence.
#
# Indian identifiers (Aadhaar, PAN, and the rest) are not in this list
# because Presidio has no recognizer for them — LegalPIIRecognizer below
# handles those natively, and its spans are merged in separately.
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
# recognizer carries the identifiers we actually care about at full
# confidence regardless of this threshold.
PRESIDIO_SCORE_THRESHOLD = 0.5


def _get_analyzer_engine():
    """Lazily builds and caches ONE Presidio AnalyzerEngine, explicitly
    configured to use en_core_web_sm — the model the Dockerfile actually
    pre-downloads (`python -m spacy download en_core_web_sm`). A bare
    AnalyzerEngine() ignores that entirely: Presidio's own default reaches
    for en_core_web_lg (588MB) regardless of what's already on disk, so
    every fresh container was quietly trying to download the large model
    from scratch at the first real request — confirmed live: a single
    extraction task sat downloading a 587.7MB wheel before it could do
    anything, the same "en_core_web_lg downloaded instead of _sm" issue
    already fixed once for the Dockerfile's build step, but never actually
    wired into the code that decides which model to load at runtime.
    Cached at module level rather than rebuilt per call — spaCy pipeline
    construction has real, avoidable cost otherwise.

    Returns None (rather than raising) if construction fails, so a bad
    Presidio/spaCy environment degrades to the native LegalPIIRecognizer
    instead of losing the whole parse — this worker's real job is finding
    Aadhaar/PAN/CrPC references, which the native recognizer catches with
    or without Presidio."""
    global _analyzer_engine, _analyzer_engine_init_failed
    if _analyzer_engine_init_failed:
        return None
    if _analyzer_engine is None:
        try:
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            provider = NlpEngineProvider(nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            })
            _analyzer_engine = AnalyzerEngine(
                nlp_engine=provider.create_engine(),
                supported_languages=["en"],
            )
        except Exception as exc:
            # Deliberately no fallback to a bare AnalyzerEngine(): that is
            # the path that reaches for en_core_web_lg and downloads/OOMs.
            logger.warning(f"Presidio AnalyzerEngine initialisation failed: {exc}")
            _analyzer_engine_init_failed = True
            return None
    return _analyzer_engine


def parse_text_for_sensitive_spans(text: str, doc_type: str = "general") -> List[Dict[str, Any]]:
    """Runs entity detection over raw text:
    1. Runs Presidio Analyzer if available in environment.
    2. Runs native LegalPIIRecognizer for Indian domain-specific identifiers.
    3. Merges and resolves overlapping spans cleanly.
    """
    all_spans: List[Dict[str, Any]] = []

    # 1. Presidio extraction if engine is present. Restricted to
    # PRESIDIO_ENTITIES and PRESIDIO_SCORE_THRESHOLD — left unrestricted,
    # Presidio enables every jurisdiction's recognizers at once and
    # mislabels ordinary Indian legal text (see PRESIDIO_ENTITIES above).
    analyzer = _get_analyzer_engine() if _HAS_PRESIDIO else None
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


def _normalize_for_compare(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def _name_similarity(claimed: str, extracted: str) -> float:
    """0.0-1.0. difflib's SequenceMatcher, not a new dependency — good
    enough for "does this look like the same name", which is all this
    feeds into (a human still makes the actual approve/reject call)."""
    import difflib
    a, b = _normalize_for_compare(claimed), _normalize_for_compare(extracted)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def process_extract_credential_fields(credential_document_id: str, db: Optional[Any] = None) -> str:
    """Core orchestration for onboarding credential extraction:
    1. Reads CredentialDocument.raw_text (OCR output).
    2. Extracts a candidate PERSON name (Presidio) and a candidate ID number
       (CredentialIDRecognizer).
    3. Compares both against the parent UserApplication's claimed identity.
    4. Sets match_status — 'matched' only if both compare well; 'mismatch'
       if either clearly conflicts; 'needs_review' whenever extraction is
       incomplete or ambiguous. This NEVER approves an application by
       itself — match_status is input to a config_admin's decision, same
       fail-closed posture as document redaction elsewhere in this system.
    """
    session = db if db is not None else SessionLocal()
    try:
        doc_uuid = credential_document_id if isinstance(credential_document_id, UUID) else UUID(str(credential_document_id))
        cred_doc = session.get(models.CredentialDocument, doc_uuid)
        if cred_doc is None:
            raise ValueError(f"CredentialDocument {credential_document_id} not found")

        if not cred_doc.raw_text or not cred_doc.raw_text.strip():
            cred_doc.status = "needs_review"
            cred_doc.match_status = "needs_review"
            session.commit()
            return "needs_review"

        application = session.get(models.UserApplication, cred_doc.application_id)
        text = cred_doc.raw_text

        # Candidate name: highest-confidence PERSON span from the same
        # combined Presidio + LegalPIIRecognizer pass every other document
        # in this system uses (parse_text_for_sensitive_spans) — not a
        # Presidio-only call, since Presidio is an optional dependency and
        # LegalPIIRecognizer's Indian-honorific/police-rank patterns are
        # often the only thing that actually fires on this kind of text.
        candidate_name = None
        MIN_PLAUSIBLE_NAME_LEN = 5  # "Xu Li" is short but real; "Ra" or "Fnk" never is
        person_spans = [
            s for s in parse_text_for_sensitive_spans(text)
            if s["entity_type"] == "PERSON" and (s["span_end"] - s["span_start"]) >= MIN_PLAUSIBLE_NAME_LEN
        ]
        if person_spans:
            # Confirmed live: Presidio's statistical NER (spaCy, now actually
            # running after the en_core_web_sm fix above) confidently
            # mis-tagged 2-3 character OCR-garbled fragments as PERSON at a
            # HIGHER confidence (85) than the deterministic "Name:" regex
            # match found for the real name one line above it (fixed at 80)
            # — so sorting by confidence first picked the fragment. The
            # length filter above removes anything too short to plausibly be
            # a name in the first place; among what's left, prefer the
            # longer match, then confidence, since a longer structured-
            # pattern match is more trustworthy on this kind of labeled-form
            # text than a marginally higher NER confidence score.
            best = max(person_spans, key=lambda s: (s["span_end"] - s["span_start"], s["confidence"]))
            raw_match = text[best["span_start"]:best["span_end"]]
            # The capturing regex can run on past a line break onto the next
            # OCR line (e.g. "...Rao\nService ID") — a name never legitimately
            # spans a newline, so cut there.
            candidate_name = raw_match.split("\n")[0].strip()

        # Candidate ID number: first ID-shaped match found.
        id_spans = CredentialIDRecognizer.find_spans(text)
        candidate_id = id_spans[0]["value"] if id_spans else None

        extracted_fields = {
            "name": candidate_name,
            "id_number": candidate_id,
        }

        name_score = _name_similarity(application.name, candidate_name) if (application and candidate_name) else 0.0
        id_match = (
            bool(application and candidate_id and application.claimed_credential_id)
            and _normalize_for_compare(application.claimed_credential_id) == _normalize_for_compare(candidate_id)
        )
        extracted_fields["name_similarity"] = round(name_score, 2)
        extracted_fields["id_number_exact_match"] = id_match

        if candidate_name is None or candidate_id is None:
            match_status = "needs_review"  # incomplete extraction — never guess
        elif name_score >= 0.75 and id_match:
            match_status = "matched"
        elif name_score < 0.4 or (candidate_id and application and application.claimed_credential_id and not id_match):
            match_status = "mismatch"
        else:
            match_status = "needs_review"

        cred_doc.extracted_fields = extracted_fields
        cred_doc.match_status = match_status
        cred_doc.status = "ready"
        session.commit()
        session.refresh(cred_doc)

        write_audit_log(
            session,
            action="credential_fields_extracted",
            actor_user_id=cred_doc.uploaded_by,
            target_type="credential_document",
            target_id=cred_doc.id,
            metadata={
                "application_id": str(cred_doc.application_id),
                "match_status": match_status,
                "name_similarity": extracted_fields["name_similarity"],
                "id_number_exact_match": id_match,
                # deliberately no candidate_name/candidate_id here — same
                # rule as every other audit entry in this system: never put
                # raw extracted personal data into audit log metadata.
            },
        )

        return match_status

    except Exception as exc:
        logger.exception(f"AI Parser Worker failure on credential document {credential_document_id}: {exc}")
        try:
            if "cred_doc" in locals() and cred_doc is not None:
                cred_doc.status = "needs_review"
                cred_doc.match_status = "needs_review"
                session.commit()
        except Exception:
            session.rollback()
        return "needs_review"
    finally:
        if db is None:
            session.close()


@app.task(name="ai_parser_worker.extract_credential_fields", bind=True, max_retries=5)
def extract_credential_fields(self, credential_document_id: str):
    """Celery task entrypoint for onboarding credential field extraction."""
    return process_extract_credential_fields(credential_document_id)
