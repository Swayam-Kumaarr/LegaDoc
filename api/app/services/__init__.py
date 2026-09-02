"""
Services package for LegaDoc.
"""

from app.services.audit_service import append_audit_log, compute_row_hash, verify_audit_chain
from app.services.queue_service import dispatch_chain_write, dispatch_ocr_extraction
from app.services.storage_service import StorageService, storage_service
from app.services.upload_validator import UploadValidationResult, validate_upload

__all__ = [
    "append_audit_log",
    "compute_row_hash",
    "verify_audit_chain",
    "storage_service",
    "StorageService",
    "validate_upload",
    "UploadValidationResult",
    "dispatch_chain_write",
    "dispatch_ocr_extraction",
]
