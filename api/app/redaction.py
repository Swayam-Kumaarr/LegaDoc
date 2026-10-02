"""
Applies already-computed DocumentSensitivityTag spans to raw text. This is
deliberately NOT the AI Parser — it doesn't detect anything, it just masks
whatever spans already exist in the DB. Real tag generation needs Presidio +
spaCy (ai_parser_worker). This function is what the redaction filter actually
runs at read time regardless of whether a tag came from the AI Parser or an
officer's manual correction — same masking logic either way, see
SYSTEM_DESIGN.md's Access Model.

What a restricted role sees is decided by the redaction policy (see
models.RedactionPolicy): per role, per document type, per entity type. With
no policy rows loaded every tagged span is masked, which is what this module
did before the policy existed.
"""

from typing import Iterable, Optional

from app import models

# Used when no policy row matches. Masking is the default because the failure
# we can afford is a reader seeing less than they needed; the other direction
# puts a witness's phone number in front of someone with no right to it.
DEFAULT_ACTION = "mask"


def load_policies(db) -> list:
    """Every policy row. Small by construction — one row per role/doc-type/
    entity combination an administrator has actually configured — so it is
    read per request rather than cached, and an edit takes effect on the next
    read instead of whenever a cache happened to expire."""
    return db.query(models.RedactionPolicy).all()


def _rule_for(policies: Iterable, role: str, doc_type: Optional[str], entity_type: str):
    """The rule that governs this entity, most specific first.

    Specificity is (exact role, exact doc_type, exact entity) > wildcards, so
    a blanket "mask everything for duty_officer" can be kept while carving out
    one entity type, rather than having to restate the whole matrix.
    """
    if not policies:
        return None

    def score(p):
        if p.role not in (role, "*"):
            return None
        if p.doc_type not in (doc_type, "*"):
            return None
        if p.entity_type not in (entity_type, "*"):
            return None
        return (
            2 if p.role == role else 0,
            2 if p.doc_type == doc_type else 0,
            2 if p.entity_type == entity_type else 0,
        )

    scored = [(s, p) for p in policies if (s := score(p)) is not None]
    if not scored:
        return None
    return max(scored, key=lambda sp: sp[0])[1]


def apply_redaction(raw_text: str, tags: list, policies: Optional[list] = None,
                    role: str = "", doc_type: Optional[str] = None) -> str:
    """tags: DocumentSensitivityTag rows for this document. Overlapping tags
    are resolved by first-span-wins (sorted by span_start) — a real
    implementation would want tag validation to prevent overlaps from ever
    being written in the first place; not enforced at this baseline.

    policies: RedactionPolicy rows. Omitted (the default) means mask every
    span, which is what this function did before policies existed, so every
    caller that has not been taught about them stays fail-closed.
    """
    if not raw_text:
        return raw_text
    sorted_tags = sorted(tags, key=lambda t: t.span_start)
    out = []
    cursor = 0
    for tag in sorted_tags:
        if tag.span_start < cursor:
            continue  # overlaps an already-masked span — skip rather than corrupt output
        if tag.span_start > len(raw_text) or tag.span_end > len(raw_text):
            continue  # a stale tag from a shorter previous version of the text — don't crash

        rule = _rule_for(policies, role, doc_type, tag.entity_type) if policies else None
        action = rule.action if rule else DEFAULT_ACTION

        # A "show" rule is written with confident detections in mind. Applying
        # it to a weak guess would reveal text on the strength of a decision
        # nobody made about that span, so anything under the rule's floor
        # falls back to masking.
        confidence = getattr(tag, "confidence", 0) or 0
        if action in ("show", "flag") and rule and confidence < rule.min_confidence:
            action = "mask"

        out.append(raw_text[cursor:tag.span_start])
        original = raw_text[tag.span_start:tag.span_end]
        if action == "show":
            out.append(original)
        elif action == "flag":
            # Visible, but the reader is told the parser flagged it and no
            # human has confirmed it — the honest state for an unreviewed guess.
            out.append(f"{original} [UNCONFIRMED:{tag.entity_type}]")
        else:
            out.append(f"[REDACTED:{tag.entity_type}]")
        cursor = tag.span_end
    out.append(raw_text[cursor:])
    return "".join(out)


def get_document_view(document: "models.Document", tags: list, role: str, full_access_roles: set,
                      policies: Optional[list] = None) -> dict:
    """The single function every read path for a document's content should
    call — never build a "redacted vs full" branch ad hoc per endpoint.

    A document in needs_review is withheld from restricted roles only. Review
    status means the parser was not confident it found every piece of
    personal data, which matters to a reader who would see the redacted copy:
    a missed name would reach them. It does not matter to a full-text role,
    who sees the raw text once the document is released anyway. Withholding it
    from them as well protected nothing, and left the investigating officer
    unable to read the document they were the one expected to review — so
    nothing in review could ever be reviewed.
    """
    if document.status == "needs_review" and role in full_access_roles:
        return {"status": document.status, "text": document.raw_text}
    if document.status != "ready":
        return {"status": document.status, "text": None}
    if role in full_access_roles:
        return {"status": document.status, "text": document.raw_text}
    return {
        "status": document.status,
        "text": apply_redaction(
            document.raw_text, tags, policies=policies, role=role, doc_type=document.doc_type
        ),
    }
