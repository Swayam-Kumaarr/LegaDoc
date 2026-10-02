"""Regression test for a real bug found while reviewing PR #20: multiple
write_audit_log() calls issued back-to-back can land with an IDENTICAL
created_at (proven in practice on this stack — not a hypothetical clock-
resolution worry). Ordering/linking the chain by created_at silently
corrupted prev_hash for every write after the first tied one. The fix is
models.AuditLog.seq — a plain monotonic counter assigned inside the same
locked critical section, independent of wall-clock resolution.

This test forces the exact failure condition (identical created_at across
several writes) rather than hoping the real clock ties on its own, so it
stays a reliable regression check regardless of the machine running it.
"""

from unittest.mock import patch
from datetime import datetime, timezone

from app.audit import write_audit_log, verify_chain_intact


def test_chain_survives_identical_timestamps_across_writes(db_session, make_org, make_user):
    """Five audit-log writes that would all share one frozen timestamp must
    still chain correctly via seq, not silently corrupt via created_at ties."""
    org = make_org()
    user = make_user("io", org=org)

    frozen = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch("app.audit.datetime") as mock_dt:
        mock_dt.now.return_value = frozen
        for i in range(5):
            write_audit_log(
                db_session,
                action=f"test_action_{i}",
                actor_user_id=user.id,
                target_type="case",
                target_id=user.id,
                metadata={"i": i},
            )

    assert verify_chain_intact(db_session) is True


def test_seq_is_strictly_increasing_and_never_ties(db_session, make_org, make_user):
    org = make_org()
    user = make_user("io", org=org)

    frozen = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entries = []
    with patch("app.audit.datetime") as mock_dt:
        mock_dt.now.return_value = frozen
        for i in range(4):
            entries.append(
                write_audit_log(db_session, action=f"a{i}", actor_user_id=user.id)
            )

    seqs = [e.seq for e in entries]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)  # no ties, unlike created_at above
    # And the chain actually links seq N to seq N-1's row_hash, not to
    # whatever the DB happened to return first under a timestamp tie.
    for prev_e, e in zip(entries, entries[1:]):
        assert e.prev_hash == prev_e.row_hash


# The chain checks stream audit_log in batches (app.audit._CHAIN_BATCH_ROWS)
# instead of loading it whole — GET /cases/:id/audit-log runs one on every
# request, and at 300k rows .all() alone took +739 MiB. A batch size of 2
# here makes every walk below cross several batch boundaries.

def _case(db_session):
    from app import models
    case = models.Case(case_number="CASE-CHAIN", crime_type="Theft", investigation_status="Under_Investigation")
    db_session.add(case)
    db_session.commit()
    return case


def test_streamed_chain_checks_match_across_batch_boundaries(db_session, make_org, make_user, monkeypatch):
    from app import audit
    monkeypatch.setattr(audit, "_CHAIN_BATCH_ROWS", 2)
    user = make_user("io", org=make_org())
    case = _case(db_session)

    written = [
        write_audit_log(db_session, action=f"a{i}", actor_user_id=user.id,
                        case_id=case.id if i % 3 == 0 else None, metadata={"i": i})
        for i in range(9)
    ]
    case_rows = [e for e in written if e.case_id == case.id]

    assert verify_chain_intact(db_session) is True
    result = audit.verify_case_chain_integrity(db_session, case.id)
    assert result["chain_intact"] is True
    assert result["total_entries"] == len(case_rows) == 3
    assert result["latest_hash"] == case_rows[-1].row_hash


def test_streamed_chain_check_still_stops_at_a_tampered_row(db_session, make_org, make_user, monkeypatch):
    from app import audit, models
    monkeypatch.setattr(audit, "_CHAIN_BATCH_ROWS", 2)
    user = make_user("io", org=make_org())
    case = _case(db_session)
    for i in range(9):
        write_audit_log(db_session, action=f"a{i}", actor_user_id=user.id, case_id=case.id, metadata={"i": i})

    victim = db_session.query(models.AuditLog).filter(models.AuditLog.action == "a5").one()
    victim.action_metadata = {"i": 999}
    db_session.commit()

    assert verify_chain_intact(db_session) is False
    # Stopping mid-stream must leave the session usable: the case check
    # counts the case's rows with a fresh query after the break.
    result = audit.verify_case_chain_integrity(db_session, case.id)
    assert result["chain_intact"] is False
    assert result["total_entries"] == 9
    assert result["latest_hash"] is None
