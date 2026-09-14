"""WebP scans — the format phones and messaging apps export — are accepted,
routed to OCR like any other scan, and still get pixel-bomb protection."""

import struct

from tests.conftest import auth_headers, login


def _webp_header(width: int, height: int, kind: str = "VP8 ") -> bytes:
    """Smallest byte layout the validator reads: RIFF container, WEBP form,
    then one bitstream chunk carrying the canvas size. The payload after the
    header is padding — upload validation never decodes the image."""
    if kind == "VP8 ":
        # frame tag (3) + start code 9d 01 2a + 14-bit width/height (little-endian)
        chunk = b"\x00\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", width & 0x3FFF, height & 0x3FFF)
    elif kind == "VP8X":
        # flags (1) + reserved (3) + canvas width-1 and height-1 as 24-bit little-endian
        chunk = b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    else:
        raise ValueError(kind)
    body = b"WEBP" + kind.encode() + struct.pack("<I", len(chunk)) + chunk + b"\x00" * 64
    return b"RIFF" + struct.pack("<I", len(body)) + body


def _case_with_io(client, make_user):
    duty = make_user("duty_officer", email="duty_webp@example.com", password="pw")
    make_user("sho", email="sho_webp@example.com", password="pw", org=duty.organization)
    io = make_user("io", email="io_webp@example.com", password="pw", org=duty.organization)
    duty_token = login(client, "duty_webp@example.com", "pw").json()["access_token"]
    case = client.post(
        "/cases", json={"crime_type": "Theft", "complaint_text": "Phone snatched."}, headers=auth_headers(duty_token)
    ).json()
    sho_token = login(client, "sho_webp@example.com", "pw").json()["access_token"]
    client.post(f"/cases/{case['id']}/assign-io", json={"io_user_id": str(io.id)}, headers=auth_headers(sho_token))
    return case, login(client, "io_webp@example.com", "pw").json()["access_token"]


def test_webp_scan_is_accepted_and_sent_to_ocr(client, make_user, fake_queue):
    case, io_token = _case_with_io(client, make_user)

    resp = client.post(
        "/documents",
        data={"case_id": case["id"], "doc_type": "FIR_Scan"},
        # Declared as JPEG on purpose: the committed fixture haryana_fir.jpg is
        # really WebP. Detection must follow the bytes, not the extension.
        files={"file": ("fir_photo.jpg", _webp_header(768, 1024), "image/jpeg")},
        headers=auth_headers(io_token),
    )

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "processing"
    tasks = {j["task_name"] for j in fake_queue.enqueued if j["kwargs"].get("document_id") == resp.json()["id"]}
    assert "ocr_worker.extract_document" in tasks


def test_oversized_webp_canvas_is_rejected_as_a_pixel_bomb(client, make_user):
    case, io_token = _case_with_io(client, make_user)

    resp = client.post(
        "/documents",
        data={"case_id": case["id"], "doc_type": "FIR_Scan"},
        files={"file": ("bomb.webp", _webp_header(15000, 15000, kind="VP8X"), "image/webp")},
        headers=auth_headers(io_token),
    )

    assert resp.status_code == 400, resp.text
    assert "pixel decompression bomb" in resp.json()["detail"]


def test_unsupported_type_message_lists_what_is_actually_allowed(client, make_user):
    case, io_token = _case_with_io(client, make_user)

    resp = client.post(
        "/documents",
        data={"case_id": case["id"], "doc_type": "Other"},
        files={"file": ("archive.zip", b"PK\x03\x04" + b"\x00" * 64, "application/zip")},
        headers=auth_headers(io_token),
    )

    assert resp.status_code == 415, resp.text
    assert "WebP" in resp.json()["detail"]
    assert "images, audio, and video" not in resp.json()["detail"]
