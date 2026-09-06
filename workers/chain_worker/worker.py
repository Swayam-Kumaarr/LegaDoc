"""
Blockchain Write Worker — Python / fabric-sdk-py, submitting signed hash
transactions to Hyperledger Fabric. See SYSTEM_DESIGN.md Flow 2 Track A and
the System Connections table, arrows #8/#13/#14.

This is the single highest-setup-risk component in the system (per the
Build Prompt Seed) — stand this up and confirm one signed transaction
end-to-end in isolation before wiring anything else to it. Nobody has been
able to do that yet in the environment this was written in (no Docker, no
Go, no Fabric network) — see fabric_client.py's honesty note before trusting
the Fabric-facing half of this file. The DB orchestration half (idempotency,
retry, chain_status transitions, audit logging) is ordinary Python and IS
tested — see tests/test_worker_logic.py.

Reuses the API's own app.models / app.database / app.audit / app.config
directly (via the sys.path adjustment below) rather than maintaining a
second copy of the schema that could silently drift from the real one. In
Docker, the worker's image copies api/app in alongside this file for the
same reason — see Dockerfile.
"""

import os
import sys
from uuid import UUID

# Reuse api/app's models/database/audit/config instead of duplicating them.
# Locally (no Docker) this resolves ../../api relative to this file. In the
# built container image, api/app is copied in as a sibling directory — see
# Dockerfile — so this same relative path still resolves correctly there.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "api"))

from celery import Celery

from app import models
from app.audit import write_audit_log
from app.config import settings
from app.database import SessionLocal

from fabric_client import FabricClient, FabricSubmissionError

app = Celery(
    "chain_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)


def _get_fabric_client() -> FabricClient:
    """Separate function, not module-level, so tests can monkeypatch this
    instead of needing a real Fabric network on disk.

    org="org1" is hardcoded to match the 2-org test-network this has
    actually been run against — see fabric_client.py's docstring. A real
    multi-org deployment should make this configurable per-deployment
    rather than hardcoded."""
    return FabricClient(
        channel_name="legadoc-channel",
        org="org1",
    )


def process_hash_write(document_id: str, idempotency_key: str = None) -> str:
    """
    The actual orchestration logic, factored out of the Celery task so it
    can be unit-tested directly (Celery task objects are awkward to call
    like plain functions in tests). Returns the resulting chain_status.

    Idempotency, per SYSTEM_DESIGN.md: if this document is already
    "confirmed", this is a no-op — covers both a legitimate retry and a
    duplicate delivery from the queue. The chaincode's own RecordHash is
    ALSO idempotent for a resubmission of the same hash (see hashledger.go)
    — two independent layers, neither relying solely on the other.
    idempotency_key itself isn't sent to Fabric; the real safety comes from
    those two checks, not from the key. It's accepted as a parameter so
    retry-chain-write's contract (SYSTEM_DESIGN.md: "reuse the original
    idempotency key, never mint a new one") has somewhere to go, and so it
    shows up in the audit trail for anyone debugging a retry later.
    """
    db = SessionLocal()
    try:
        document = db.get(models.Document, UUID(document_id))
        if document is None:
            raise ValueError(f"No document {document_id} to write a hash for")

        if document.chain_status == "confirmed":
            return "confirmed"  # already done — matches the idempotency rule above

        uploader = db.get(models.User, document.uploaded_by)
        org_id = str(uploader.org_id) if uploader else "unknown"

        try:
            client = _get_fabric_client()
            client.submit_hash(doc_id=str(document.id), doc_hash=document.doc_hash, org_id=org_id)
        except FabricSubmissionError as e:
            document.chain_status = "failed"
            db.commit()
            write_audit_log(
                db,
                action="chain_write_failed",
                case_id=document.case_id,
                target_type="document",
                target_id=document.id,
                metadata={"idempotency_key": idempotency_key, "error": str(e)},
            )
            raise

        document.chain_status = "confirmed"
        db.commit()
        write_audit_log(
            db,
            action="chain_write_confirmed",
            case_id=document.case_id,
            target_type="document",
            target_id=document.id,
            metadata={"idempotency_key": idempotency_key},
        )
        return "confirmed"
    finally:
        db.close()


@app.task(name="chain_worker.write_hash", bind=True, max_retries=5, default_retry_delay=30)
def write_hash(self, document_id: str, idempotency_key: str = None):
    """Celery entrypoint. On repeated endorsement failure (after Celery's
    own retry/backoff is exhausted), the document is left at
    chain_status="failed" for manual review via POST
    /documents/:id/retry-chain-write — see api/app/routers/documents.py.
    """
    try:
        return process_hash_write(document_id, idempotency_key)
    except FabricSubmissionError as exc:
        raise self.retry(exc=exc)
