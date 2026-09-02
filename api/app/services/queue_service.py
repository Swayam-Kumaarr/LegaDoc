"""
Queue Service — Celery task dispatcher for async workers.
See SYSTEM_DESIGN.md:
- Flow 2 Track A: chain_worker.write_hash (idempotency_key = f"{document_id}:{version}")
- Flow 2 Track B: ocr_worker.extract_document (text-bearing documents only)
- Graceful degradation if Redis is temporarily unreachable
"""

import logging
from typing import Optional
from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

# Lightweight Celery client for API task dispatching
celery_client = Celery(
    "api_dispatcher",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)


def dispatch_chain_write(document_id: str, version: int) -> Optional[str]:
    """
    Dispatches the blockchain hash-write job to Chain Worker.
    Uses deterministic idempotency_key = f"{document_id}:{version}".
    """
    idempotency_key = f"{document_id}:{version}"
    try:
        async_result = celery_client.send_task(
            "chain_worker.write_hash",
            args=[document_id],
            kwargs={"idempotency_key": idempotency_key},
        )
        return async_result.id
    except Exception as e:
        logger.warning(
            "Failed to enqueue chain_worker.write_hash for document %s: %s",
            document_id,
            str(e),
        )
        return None


def dispatch_ocr_extraction(document_id: str) -> Optional[str]:
    """
    Dispatches the OCR extraction job to OCR Worker.
    Only dispatched for text-bearing document types.
    """
    try:
        async_result = celery_client.send_task(
            "ocr_worker.extract_document",
            args=[document_id],
        )
        return async_result.id
    except Exception as e:
        logger.warning(
            "Failed to enqueue ocr_worker.extract_document for document %s: %s",
            document_id,
            str(e),
        )
        return None
