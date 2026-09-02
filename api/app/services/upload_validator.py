"""
Upload Validation Service — Streaming MIME detection, SHA-256 computation, and size capping.
See SYSTEM_DESIGN.md:
- Section 1.6 & 1.7 (File Upload Security)
- Magic-byte detection via python-magic (prevents extension spoofing like .exe-as-.pdf)
- Incremental streaming SHA-256 computation
- SpooledTemporaryFile buffering (5MB memory threshold)
- Early abort on oversized streams (configurable size cap)
"""

import hashlib
import os
import re
import tempfile
from typing import BinaryIO, NamedTuple, Set
from fastapi import HTTPException, UploadFile, status

try:
    import magic
    HAS_MAGIC = True
except (ImportError, Exception):
    HAS_MAGIC = False

# Allowed text-bearing MIME types (routed to PaddleOCR)
TEXT_BEARING_MIME_TYPES: Set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "text/plain",
    "text/csv",
}

# Allowed binary evidence MIME types (bypasses OCR, marked ready immediately)
BINARY_EVIDENCE_MIME_TYPES: Set[str] = {
    "video/mp4",
    "video/mpeg",
    "audio/mpeg",
    "audio/wav",
    "application/octet-stream",
}

ALL_ALLOWED_MIME_TYPES = TEXT_BEARING_MIME_TYPES | BINARY_EVIDENCE_MIME_TYPES


class UploadValidationResult(NamedTuple):
    file_obj: BinaryIO
    sha256_hash: str
    detected_mime: str
    file_size: int
    is_binary_evidence: bool
    original_filename: str


def sanitize_filename(filename: str) -> str:
    """Sanitizes filename against path traversal and dangerous characters."""
    if not filename:
        return "unnamed_upload"
    # Take basename only
    base = os.path.basename(filename)
    # Strip dangerous characters
    cleaned = re.sub(r"[^\w\.\-\_]", "_", base)
    # Limit length
    return cleaned[:255] if cleaned else "unnamed_upload"


def detect_mime_from_bytes(header_bytes: bytes, fallback_content_type: str = "") -> str:
    """Detects MIME type from raw magic bytes."""
    if HAS_MAGIC and header_bytes:
        try:
            detected = magic.from_buffer(header_bytes, mime=True)
            if detected:
                return detected.lower()
        except Exception:
            pass

    # Simple magic-byte fallbacks if libmagic is not loaded
    if header_bytes.startswith(b"%PDF"):
        return "application/pdf"
    elif header_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif header_bytes.startswith(b"II*\x00") or header_bytes.startswith(b"MM\x00*"):
        return "image/tiff"
    elif header_bytes[4:8] == b"ftyp":
        return "video/mp4"

    return fallback_content_type.lower() if fallback_content_type else "application/octet-stream"


async def validate_upload(
    upload_file: UploadFile,
    max_size_mb: int = 50,
) -> UploadValidationResult:
    """
    Performs streaming validation on an incoming multipart file upload:
    1. Sanitizes the original filename.
    2. Reads initial header chunk (8KB) to sniff magic bytes.
    3. Validates MIME type against allowlist.
    4. Streams rest of content into SpooledTemporaryFile (5MB threshold).
    5. Computes SHA-256 incrementally.
    6. Aborts immediately if size exceeds max_size_mb.
    """
    sanitized_name = sanitize_filename(upload_file.filename or "")
    max_bytes = max_size_mb * 1024 * 1024
    chunk_size = 64 * 1024  # 64KB chunks

    spooled_file = tempfile.SpooledTemporaryFile(max_size=5 * 1024 * 1024)
    sha256 = hashlib.sha256()
    total_bytes = 0

    # 1. Read header chunk (8KB)
    header_chunk = await upload_file.read(8192)
    if not header_chunk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # 2. Sniff MIME type
    detected_mime = detect_mime_from_bytes(
        header_chunk,
        fallback_content_type=upload_file.content_type or "",
    )

    if detected_mime not in ALL_ALLOWED_MIME_TYPES:
        spooled_file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{detected_mime}'. Allowed types include PDF, images, audio, and video.",
        )

    # 3. Write header to spooled file and update hash
    spooled_file.write(header_chunk)
    sha256.update(header_chunk)
    total_bytes += len(header_chunk)

    if total_bytes > max_bytes:
        spooled_file.close()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {max_size_mb}MB",
        )

    # 4. Stream remaining chunks
    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break

        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            spooled_file.close()
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {max_size_mb}MB",
            )

        spooled_file.write(chunk)
        sha256.update(chunk)

    spooled_file.seek(0)
    is_binary = detected_mime in BINARY_EVIDENCE_MIME_TYPES

    return UploadValidationResult(
        file_obj=spooled_file,
        sha256_hash=sha256.hexdigest(),
        detected_mime=detected_mime,
        file_size=total_bytes,
        is_binary_evidence=is_binary,
        original_filename=sanitized_name,
    )
