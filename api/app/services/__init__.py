"""
Services package for LegaDoc.
"""

from app.services.audit_service import append_audit_log, compute_row_hash, verify_audit_chain

__all__ = ["append_audit_log", "compute_row_hash", "verify_audit_chain"]
