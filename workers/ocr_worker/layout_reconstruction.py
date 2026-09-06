"""
Layout Reconstruction & Bilingual FIR Extraction Engine.
Resolves OCR spatial disconnection and Hindi-language reading reliability (Issue #37) by:
1. Filtering overlapping detections via spatial IoU Non-Maximum Suppression (NMS) with
   Devanagari priority (suppressing hallucinated Latin ASCII ghost boxes emitted by single-script CTC).
2. Normalizing Devanagari numerals (०-९) to standard digits.
3. Clustering bounding boxes into discrete horizontal rows by adaptive vertical tolerance.
4. Sorting within each row left-to-right to preserve column structure and natural reading order.
5. Extracting the 12 canonical FIR header fields across bilingual and pure-Hindi templates
   (Delhi Police, Haryana Police, UP Police).

LANGUAGE SUPPORT MATRIX (Issue #37):
====================================
CONFIRMED WORKING:
- English (lang='en'): Full alphanumeric, police FIR headers, court orders, chargesheets.
- Hindi (lang='hi'): Devanagari script (U+0900-U+097F), Devanagari numerals (०-९),
  pure-Hindi and mixed Hindi-English templates across Delhi, Haryana, and UP Police.
- Cross-lingual NMS: Prioritizes Devanagari glyph detections over hallucinated Latin ASCII ghost boxes.

UNRELIABLE / FUTURE ROADMAP:
- Regional non-Devanagari Indian scripts (Tamil, Telugu, Bengali, Gujarati, Kannada,
  Malayalam, Odia, Gurmukhi/Punjabi) require dedicated per-script recognition dictionaries;
  currently trigger fallback or status='needs_review' under fail-closed safety policy.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def has_devanagari(text: str) -> bool:
    """Checks if text contains Devanagari script characters (U+0900 - U+097F)."""
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def normalize_devanagari_digits(text: str) -> str:
    """Normalizes Devanagari numerals (०-९) to standard ASCII digits (0-9)."""
    return text.translate(DEVANAGARI_DIGITS)


def compute_box_iou(b1: List[int], b2: List[int]) -> float:
    """Calculates Intersection over Union (IoU) of two bounding boxes [x1, y1, x2, y2]."""
    x_left = max(b1[0], b2[0])
    y_top = max(b1[1], b2[1])
    x_right = min(b1[2], b2[2])
    y_bottom = min(b1[3], b2[3])

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def deduplicate_boxes_nms(
    boxes: List[Dict[str, Any]],
    iou_thresh: float = 0.35,
    containment_thresh: float = 0.65,
) -> List[Dict[str, Any]]:
    """Suppresses redundant, overlapping, and cross-lingual ghost bounding boxes.
    Prioritizes Devanagari detections over hallucinated Latin ASCII ghost boxes
    when overlapping in the same spatial region.
    """
    if not boxes:
        return []

    # Sort key:
    # 1. Devanagari presence (gives priority to authentic Hindi script over Latin hallucinations)
    # 2. Confidence
    # 3. Box area
    def sort_key(b: Dict[str, Any]) -> Tuple[int, float, int]:
        text = b.get("text", "")
        is_dev = 1 if has_devanagari(text) else 0
        conf = float(b.get("confidence", 0.0))
        box = b.get("box", [0, 0, 0, 0])
        area = (box[2] - box[0]) * (box[3] - box[1])
        return (is_dev, conf, area)

    sorted_boxes = sorted(boxes, key=sort_key, reverse=True)
    retained: List[Dict[str, Any]] = []

    for cand in sorted_boxes:
        box1 = cand.get("box")
        if not box1 or len(box1) < 4:
            continue

        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        if area1 <= 0:
            continue

        dominated = False
        for kept in retained:
            box2 = kept["box"]
            iou = compute_box_iou(box1, box2)

            # Check directional containment (box1 inside box2)
            x_ov = max(0, min(box1[2], box2[2]) - max(box1[0], box2[0]))
            y_ov = max(0, min(box1[3], box2[3]) - max(box1[1], box2[1]))
            ov_area = x_ov * y_ov
            containment = ov_area / area1

            if iou > iou_thresh or containment > containment_thresh:
                dominated = True
                break

        if not dominated:
            retained.append(cand)

    return retained


def center_y(box: List[int]) -> float:
    return (box[1] + box[3]) / 2.0


def reconstruct_layout_rows(
    boxes: List[Dict[str, Any]],
    y_tol: float = 13.0,
    x_spacing_tol: int = 40,
) -> List[Dict[str, Any]]:
    """Groups spatially filtered bounding boxes into ordered horizontal rows.
    Each row maintains:
    - row_index: int (1-based)
    - center_y: float average vertical position
    - cells: list of box dicts ordered left-to-right (x1 asc)
    - text: clean reconstructed line with column separators
    """
    if not boxes:
        return []

    # Sort boxes top-to-bottom by vertical center
    sorted_by_y = sorted(boxes, key=lambda b: (center_y(b["box"]), b["box"][0]))

    row_clusters: List[Dict[str, Any]] = []

    for b in sorted_by_y:
        cy = center_y(b["box"])
        matched_row = None

        for r in row_clusters:
            if abs(r["center_y"] - cy) <= y_tol:
                matched_row = r
                break

        if matched_row is not None:
            matched_row["cells"].append(b)
            # Update moving average center_y
            total_y = sum(center_y(x["box"]) for x in matched_row["cells"])
            matched_row["center_y"] = total_y / len(matched_row["cells"])
        else:
            row_clusters.append({
                "center_y": cy,
                "cells": [b],
            })

    # Sort rows top-to-bottom
    row_clusters.sort(key=lambda r: r["center_y"])

    # Within each row, sort cells left-to-right and assemble row text
    reconstructed_rows: List[Dict[str, Any]] = []

    for idx, r in enumerate(row_clusters, start=1):
        sorted_cells = sorted(r["cells"], key=lambda c: c["box"][0])
        
        # Build line text preserving multi-column gaps
        line_parts = []
        last_x2 = None

        for cell in sorted_cells:
            text = cell.get("text", "").strip()
            if not text:
                continue

            x1 = cell["box"][0]
            if last_x2 is not None:
                gap = x1 - last_x2
                if gap > x_spacing_tol:
                    line_parts.append("   |   ")
                else:
                    line_parts.append(" ")
            line_parts.append(text)
            last_x2 = cell["box"][2]

        line_str = "".join(line_parts).strip()

        reconstructed_rows.append({
            "row_index": idx,
            "center_y": round(r["center_y"], 2),
            "cells": sorted_cells,
            "text": line_str,
        })

    return reconstructed_rows


def extract_bilingual_fir_fields(
    rows: List[Dict[str, Any]],
    raw_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Extracts the 12 canonical FIR fields across Delhi and Haryana bilingual formats:
    1. fir_number
    2. district
    3. police_station
    4. year
    5. registration_date
    6. registration_time
    7. type_of_information
    8. ipc_sections
    9. complainant
    10. address
    11. place_of_occurrence
    12. incident_description
    """
    if raw_text is None:
        raw_text = "\n".join(r["text"] for r in rows)

    parsed: Dict[str, Any] = {
        "fir_number": None,
        "district": None,
        "police_station": None,
        "year": None,
        "registration_date": None,
        "registration_time": None,
        "type_of_information": None,
        "ipc_sections": [],
        "complainant": None,
        "address": None,
        "place_of_occurrence": None,
        "incident_description": None,
    }

    # Detect template
    upper_full = raw_text.upper()
    if "DELHI" in upper_full or "BNS.S" in upper_full or "BHARATIYA NYAYA" in upper_full:
        template = "Delhi Police FIR"
    elif "HARYANA" in upper_full or "अम्बाला" in raw_text or "हिसार" in raw_text or "करनाल" in raw_text:
        template = "Haryana Police FIR"
    elif "UTTAR PRADESH" in upper_full or "उत्तर प्रदेश" in raw_text or "मु.अ.सं" in raw_text or "मु०अ०सं०" in raw_text or "जनपद" in raw_text:
        template = "UP Police FIR"
    else:
        template = "Standard Indian Police FIR"

    norm_text = normalize_devanagari_digits(raw_text)

    # --- 1. FIR Number ---
    m_fir = re.search(
        r"(?i)(?:FIR\s*N[oO0]\.?|एफ\.?आई\.?आर\.?\s*(?:सं\.?|संख्या|नं\.?)?|प्रथम\s*सूचना\s*रिपोर्ट(?:\s*(?:सं\.?|संख्या))?|मु\.?\s*अ\.?\s*सं\.?|मु०\s*अ०\s*सं०?|मुकदमा\s*अपराध\s*संख्या|अपराध\s*(?:सं\.?|संख्या))[:\s]*([0-9]{1,12}(?:/[0-9]{2,4})?)",
        norm_text,
    )
    if m_fir:
        parsed["fir_number"] = m_fir.group(1).strip()

    # --- 2. District & 3. Police Station & 4. Year ---
    m_dist = re.search(
        r"(?i)(?:District|जिला|जनपद)[:\s]*([^|\n]+?)(?=\s*\||\s*P\.?S\.?[:\s]|\s*Police\s+Station|\s*थाना|\s*कोतवाली|\s*Year|\s*वर्ष|\s*साल|$)",
        raw_text,
    )
    if m_dist:
        dist_val = m_dist.group(1).strip(" !:,-|")
        if dist_val:
            parsed["district"] = dist_val

    m_ps = re.search(
        r"(?i)(?:P\.?S\.?|Police\s+Station|थाना|कोतवाली)[:\s]*([^|\n]+?)(?=\s*\||\s*Year|\s*वर्ष|\s*साल|\s*FIR|\s*मु\.?अ|\s*प्रथम|$)",
        raw_text,
    )
    if m_ps:
        ps_val = m_ps.group(1).strip(" !:,-|")
        if ps_val:
            parsed["police_station"] = ps_val

    m_year = re.search(r"(?i)(?:Year|वर्ष|साल)[:\s]*([12][09][0-9]{2})", norm_text)
    if m_year:
        parsed["year"] = m_year.group(1).strip()
    elif parsed["fir_number"] and "/" in str(parsed["fir_number"]):
        parsed["year"] = parsed["fir_number"].split("/")[-1]

    # --- 5. Registration Date & 6. Registration Time ---
    m_date = re.search(r"(?i)(?:Date|दिनांक|तारीख)[:\s]*([0-3]?[0-9][\/\-\.][01]?[0-9][\/\-\.][12][09][0-9]{2})", norm_text)
    if m_date:
        parsed["registration_date"] = m_date.group(1).strip()

    m_time = re.search(
        r"(?i)(?:Time\s*(?:From)?|समय|वक्त)[:\s]*([0-2]?[0-9]:[0-5][0-9](?:\s*(?:hrs|nrs|am|pm|बजे))?)",
        norm_text,
    )
    if m_time:
        parsed["registration_time"] = m_time.group(1).replace("nrs", "hrs").strip()

    # --- 7. Sections (IPC / BNS) ---
    sections = []
    # Search for BNS sections (e.g. 303(2), 304, 379)
    for m in re.finditer(r"(?i)(?:BNS|Bharatiya\s+Nyaya\s+Sanhita|भारतीय\s*न्याय\s*संहिता|बी\.?एन\.?एस\.?).*?(?:2023\s*)?([1-9][0-9]{1,2}(?:\([0-9a-zA-Z]+\))?)", norm_text):
        sec = m.group(1).strip()
        if sec and f"BNS {sec}" not in sections:
            sections.append(f"BNS {sec}")
    # Search for IPC sections
    for m in re.finditer(r"(?i)(?:IPC|Indian\s+Penal\s+Code|भा\.?\s*दं\.?\s*(?:सं\.?|वि\.?)|भा०\s*दं०\s*(?:सं०|वि०)|भारतीय\s*दंड\s*संहिता).*?([1-9][0-9]{1,2}(?:\([0-9a-zA-Z]+\))?)", norm_text):
        sec = m.group(1).strip()
        if sec and f"IPC {sec}" not in sections:
            sections.append(f"IPC {sec}")
    # Section/s heading directly followed by digits
    if not sections:
        for m in re.finditer(r"(?i)(?:Section/s|Sections|धाराएं|धाराएँ|धारा)[:\s]*([1-9][0-9]{1,2}(?:\([0-9a-zA-Z]+\))?)", norm_text):
            sec = m.group(1).strip()
            if sec and sec not in sections:
                sections.append(sec)

    parsed["ipc_sections"] = sections

    # --- 8. Type of Information ---
    m_info = re.search(r"(?i)(?:Type\s+of\s+Information|सूचना\s+का\s+प्रकार)[:\s]*([^|\n]+)", raw_text)
    if m_info:
        parsed["type_of_information"] = m_info.group(1).strip(" !:,-|.")

    # --- 9. Complainant / Informant ---
    m_comp = re.search(
        r"(?i)(?:Complainant\s*/\s*Informant|शिकायतकर्ता|वादी|सूचक|प्रार्थी)[\s\S]*?(?:(?:\([a-zA-Z0-9]\)\s*)?(?:Name|(?:का\s*)?नाम))?[:\s]*([A-Z\u0900-\u097f][a-zA-Z\u0900-\u097f\s\.]+(?:s\/o|w\/o|d\/o|पुत्र|आत्मज|सुपुत्र|पत्नी|पुत्री|श्री|Sh\.|LT\.)?[^\n|,\(\)]+)",
        raw_text,
    )
    if m_comp:
        comp_clean = m_comp.group(1).strip(" !:,-|")
        comp_clean = re.sub(
            r"(?i)^(?:(?:\([a-zA-Z0-9]\)\s*)?Name|(?:का\s*)?नाम|वादी|शिकायतकर्ता|सूचक|प्रार्थी)\s*[:\s]*",
            "",
            comp_clean,
        ).strip()
        if len(comp_clean) > 3:
            parsed["complainant"] = comp_clean

    # --- 10. Address ---
    m_addr = re.search(r"(?i)(?:Address|पता|निवास|निवासी)[:\s]*([^|\n]+)", raw_text)
    if m_addr:
        parsed["address"] = m_addr.group(1).strip(" !:,-|")

    # --- 11. Place of Occurrence ---
    m_poc = re.search(
        r"(?i)(?:घटना\s*स्थल|घटनास्थल|घटना\s+का\s+स्थान|मौका\s+वारदात)[:\s]*([^|\n]+)",
        raw_text,
    )
    if not m_poc:
        m_poc = re.search(
            r"(?i)(?:Place\s+of\s+Occurrence)[\s\S]*?(?:Address[:\s]*|Addre[a-zA-Z\$]{1,3}[:\s]*)?([^|\n]+(?:PARK|ROAD|STATION|DELHI|HARYANA|PANDAL)[^|\n]*)",
            raw_text,
        )
    if m_poc:
        poc_clean = m_poc.group(1).strip(" !:,-|")
        poc_clean = re.sub(
            r"(?i)^(?:\([a-zA-Z0-9]\)\s*)?(?:Place\s+of\s+Occurrence|Direction\s+and\s+Distance|Address|Addre[a-zA-Z\$]{1,3}|घटना\s*स्थल|घटना\s+का\s+स्थान)[:\s]*",
            "",
            poc_clean,
        ).strip()
        if len(poc_clean) > 3:
            parsed["place_of_occurrence"] = poc_clean

    # --- 12. Incident Description / Stolen Property ---
    m_desc = re.search(
        r"(?i)(?:घटना\s+का\s+विवरण|अपराध\s+का\s+विवरण|संक्षिप्त\s+विवरण)[:\s]*([^|\n]+)",
        raw_text,
    )
    if not m_desc:
        m_desc = re.search(
            r"(?i)(?:Description\s+of\s+Property|Particulars\s+of\s+properties\s+stolen|घटना\s+का\s+विवरण)[\s\S]*?([A-Z0-9\s,]+(?:GOLD|JHARI|DIAMOND|CASH|MOBILE|VEHICLE)[^|\n]*)",
            raw_text,
        )
    if m_desc:
        desc_clean = m_desc.group(1).strip(" !:,-|")
        if len(desc_clean) > 3:
            parsed["incident_description"] = desc_clean

    return {
        "template": template,
        "fields": parsed,
    }


def process_ocr_boxes_to_layout(raw_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """End-to-end transformation:
    Raw OCR detections -> Spatial IoU NMS -> Row Clustering -> Bilingual Field Extraction.
    """
    filtered_boxes = deduplicate_boxes_nms(raw_boxes)
    rows = reconstruct_layout_rows(filtered_boxes)
    reconstructed_text = "\n".join(r["text"] for r in rows)
    extracted = extract_bilingual_fir_fields(rows, raw_text=reconstructed_text)

    return {
        "template": extracted["template"],
        "fields": extracted["fields"],
        "reconstructed_text": reconstructed_text,
        "rows": rows,
        "token_count": len(filtered_boxes),
        "row_count": len(rows),
    }
