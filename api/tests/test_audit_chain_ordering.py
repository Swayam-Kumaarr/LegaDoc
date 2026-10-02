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


# --- The per-request check is incremental -----------------------------------
#
# chain_intact_for_request verifies the last row it vouched for plus every
# row since, and walks everything at most every AUDIT_FULL_VERIFY_SECONDS.

def _write(db_session, user, n, start=0):
    return [write_audit_log(db_session, action=f"inc{start + i}", actor_user_id=user.id, metadata={"i": start + i})
            for i in range(n)]


def test_incremental_check_agrees_with_the_full_walk_as_the_chain_grows(db_session, make_org, make_user):
    from app import audit
    user = make_user("io", org=make_org())
    _write(db_session, user, 5)
    assert audit.chain_intact_for_request(db_session) is True     # first call: full walk
    _write(db_session, user, 4, start=5)
    assert audit.chain_intact_for_request(db_session) is True     # only the 4 new rows
    assert verify_chain_intact(db_session) is True


def test_tampering_with_a_new_row_is_caught_on_the_next_request(db_session, make_org, make_user):
    from app import audit, models
    user = make_user("io", org=make_org())
    _write(db_session, user, 3)
    assert audit.chain_intact_for_request(db_session) is True
    new_rows = _write(db_session, user, 3, start=3)
    db_session.query(models.AuditLog).filter(models.AuditLog.id == new_rows[1].id).update({"action": "forged"})
    db_session.commit()

    assert audit.chain_intact_for_request(db_session) is False
    assert audit.chain_intact_for_request(db_session) is False, "a broken chain stays reported broken"


def test_tampering_with_the_checkpoint_row_is_caught_on_the_next_request(db_session, make_org, make_user):
    from app import audit, models
    user = make_user("io", org=make_org())
    rows = _write(db_session, user, 4)
    assert audit.chain_intact_for_request(db_session) is True
    db_session.query(models.AuditLog).filter(models.AuditLog.id == rows[-1].id).update({"action_metadata": {"i": 99}})
    db_session.commit()
    assert audit.chain_intact_for_request(db_session) is False


def test_a_deleted_new_row_is_caught_by_the_seq_gap(db_session, make_org, make_user):
    from app import audit, models
    user = make_user("io", org=make_org())
    _write(db_session, user, 2)
    assert audit.chain_intact_for_request(db_session) is True
    new_rows = _write(db_session, user, 3, start=2)
    db_session.query(models.AuditLog).filter(models.AuditLog.id == new_rows[1].id).delete()
    db_session.commit()
    assert audit.chain_intact_for_request(db_session) is False


def test_tampering_with_an_older_row_is_caught_by_the_next_full_walk(db_session, make_org, make_user, monkeypatch):
    """The trade this check makes: an edit behind the checkpoint is not seen
    until the next full walk — at most AUDIT_FULL_VERIFY_SECONDS later — while
    the full check (and the Config Admin chain-integrity endpoint) sees it at
    once."""
    from app import audit, models
    user = make_user("io", org=make_org())
    rows = _write(db_session, user, 6)
    assert audit.chain_intact_for_request(db_session) is True
    db_session.query(models.AuditLog).filter(models.AuditLog.id == rows[1].id).update({"action": "forged"})
    db_session.commit()

    assert verify_chain_intact(db_session) is False
    assert audit.chain_intact_for_request(db_session) is True          # inside the window

    monkeypatch.setattr(audit, "AUDIT_FULL_VERIFY_SECONDS", 0)          # window elapsed
    assert audit.chain_intact_for_request(db_session) is False
