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


def has_devanagari_letters(text: str) -> bool:
    """True only for Devanagari *letters* \u2014 the block minus its numerals
    (U+0966-U+096F).

    This is the signal that a detection is genuinely Devanagari rather than
    the Hindi pass hallucinating Indic numerals over Latin digits. Both look
    identical to has_devanagari, but they mean opposite things during NMS:
    "\u0925\u093e\u0928\u093e" is authentic Hindi that must outrank a Latin ghost box, while the
    "\u096a\u0967" the Devanagari pass returned for a printed "41" on an English FIR is
    the ghost and must lose. Devanagari digits alone are never evidence that
    the underlying text is Hindi \u2014 a genuine Hindi line carries letters too.
    """
    return any(
        "\u0900" <= ch <= "\u097f" and not ("\u0966" <= ch <= "\u096f")
        for ch in text
    )


def normalize_devanagari_digits(text: str) -> str:
    """Normalizes Devanagari numerals (०-९) to standard ASCII digits (0-9)."""
    return text.translate(DEVANAGARI_DIGITS)


# Devanagari letters and signs, excluding the numerals (U+0966-U+096F), which
# the Hindi pass hallucinates over printed Latin digits — see
# has_devanagari_letters.
_DEVANAGARI_LETTER_RE = re.compile(r"[ऀ-॥॰-ॿ]")

# How much of a page must read as Devanagari before the Tesseract pass is
# worth fusing in. An English-only FIR produces a handful of spurious
# Devanagari detections (4 of 371 boxes on the real Delhi fixture), and
# fusing on that evidence only lets Tesseract's own Latin-as-Devanagari
# garbage ("हार" over "Act(s)") into a page that was reading correctly.
_BILINGUAL_MIN_BOXES = 8
_BILINGUAL_MIN_RATIO = 0.10


def page_is_bilingual(boxes: List[Dict[str, Any]]) -> bool:
    """True when enough of the page reads as Devanagari to be worth a second,
    Devanagari-specialist OCR pass. See _BILINGUAL_MIN_RATIO."""
    if not boxes:
        return False
    dev = sum(1 for b in boxes if has_devanagari_letters(b.get("text", "")))
    return dev >= _BILINGUAL_MIN_BOXES and dev / len(boxes) >= _BILINGUAL_MIN_RATIO


def strip_devanagari(text: str) -> str:
    """Removes the Devanagari words from a mixed-script detection, keeping
    the Latin ones.

    Used on PaddleOCR boxes once a Tesseract Devanagari reading is available
    for the same page. Dropping such a box wholesale loses the Latin half —
    Paddle reads the label "P.S. थाना:" as "P.S. धानn:", and discarding it
    took the "P.S." with it, which is what the police-station field matches
    on. Only the untrusted half is removed.

    The unit removed is the whole word, not just its Devanagari letters. A
    word mixing both scripts is the Hindi model misreading a Hindi word, and
    its Latin letters are part of that misreading: stripping only the
    Devanagari left "धानn:" as "n:" and "fज़:" as "f:", which ended up in the
    extracted fields as "n: SHAHABAD" and "f: KURUKSHETRA" (issue #107).
    """
    return " ".join(
        w for w in text.split()
        if not _DEVANAGARI_LETTER_RE.search(w) and w.strip(".,:;()[]|-")
    )


def is_devanagari_word(text: str) -> bool:
    """True for a detection that is genuinely Devanagari rather than Latin
    text mis-read as Devanagari.

    Tesseract's Hindi model transliterates Latin words it cannot place —
    "HARYANA" comes back as "#88१%8॥4&" and "IPC" as "॥?ए९". Those carry one
    or two Devanagari glyphs among symbols and digits; real Hindi words are
    almost entirely Devanagari letters. Requiring both a minimum count and a
    clear majority separates the two.
    """
    alnum = [ch for ch in text if ch.isalnum() or _DEVANAGARI_LETTER_RE.match(ch)]
    dev = [ch for ch in alnum if _DEVANAGARI_LETTER_RE.match(ch)]
    return len(dev) >= 2 and bool(alnum) and len(dev) / len(alnum) >= 0.6


def _containment(inner: List[int], outer: List[int]) -> float:
    """Fraction of `inner`'s area that lies inside `outer`."""
    area = max(0, inner[2] - inner[0]) * max(0, inner[3] - inner[1])
    if area <= 0:
        return 0.0
    x_ov = max(0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
    y_ov = max(0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
    return (x_ov * y_ov) / area


def fuse_devanagari_boxes(
    paddle_boxes: List[Dict[str, Any]],
    tesseract_boxes: List[Dict[str, Any]],
    min_confidence: float = 0.5,
    latin_confidence: float = 0.85,
) -> List[Dict[str, Any]]:
    """Takes Devanagari from Tesseract and everything else from PaddleOCR.

    PaddleOCR's Hindi model drops conjuncts and reph and emits the ि matra in
    visual order, so "प्रथम सूचना रिपोर्ट" comes back as "पथम सूचना िरपोट" and
    "प्रक्रिया" as "पिकया" — issue #91. Tesseract's `hin` model reads the same
    lines correctly. It is not a replacement, though: it drops the digit 1
    from numbers ("Section 154" -> "54", "2017" -> "207"), which on an FIR
    corrupts exactly the statute and date values that matter most, while
    Paddle's English pass reads them perfectly.

    So each engine supplies what it is good at:
      - Devanagari words come from Tesseract, above a confidence floor and
        filtered by is_devanagari_word.
      - Latin text and all digits come from Paddle, with any Devanagari
        characters stripped out of mixed boxes.
      - A Tesseract box is dropped where Paddle read the same region as Latin
        with high confidence: a region a Latin model is sure about is Latin,
        and this is where Tesseract's transliterated garbage lands.

    Only called for pages that pass page_is_bilingual.
    """
    dev = [
        b for b in tesseract_boxes
        if is_devanagari_word(b.get("text", "")) and float(b.get("confidence", 0.0)) >= min_confidence
    ]

    latin: List[Dict[str, Any]] = []
    for box in paddle_boxes:
        text = box.get("text", "")
        if has_devanagari_letters(text):
            text = strip_devanagari(text)
        if not text.strip():
            continue
        kept = dict(box)
        kept["text"] = text
        latin.append(kept)

    weak = [
        b for b in tesseract_boxes
        if is_devanagari_word(b.get("text", "")) and float(b.get("confidence", 0.0)) < min_confidence
    ]
    latin, dev = resolve_latin_glosses(latin, dev, weak, latin_confidence=latin_confidence)

    dev = [
        d for d in dev
        if not any(
            float(p.get("confidence", 0.0)) >= latin_confidence
            and _containment(d["box"], p["box"]) >= 0.6
            for p in latin
        )
    ]

    return latin + dev


# How much of a Latin box's width, or of one bracketed gloss inside it, must
# lie under trusted Devanagari words before it is taken to be PaddleOCR's
# English pass transliterating that Hindi — issue #107.
_GLOSS_COVERAGE = 0.6

_PAREN_GROUP_RE = re.compile(r"\([^()]*\)")


def _same_line(a: List[int], b: List[int]) -> bool:
    """True when two boxes share most of their height, i.e. sit on one line."""
    y_ov = min(a[3], b[3]) - max(a[1], b[1])
    return y_ov > 0.5 * min(a[3] - a[1], b[3] - b[1])


def _x_coverage(x1: float, x2: float, spans: List[Tuple[int, int]]) -> float:
    """Fraction of [x1, x2] covered by the union of `spans`."""
    if x2 <= x1:
        return 0.0
    covered, cursor = 0.0, x1
    for s1, s2 in sorted(spans):
        s1, s2 = max(s1, cursor), min(s2, x2)
        if s2 > s1:
            covered += s2 - s1
            cursor = s2
    return covered / (x2 - x1)


def resolve_latin_glosses(
    latin_boxes: List[Dict[str, Any]],
    dev_boxes: List[Dict[str, Any]],
    weak_dev_boxes: Optional[List[Dict[str, Any]]] = None,
    latin_confidence: float = 0.85,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Removes PaddleOCR's English-pass reading of Hindi text — issue #107.

    The English model also detects the Devanagari on a bilingual FIR and
    transliterates it into Latin garbage: "(धारा 154 दंड प्रक्रिया संहिता के तहत)"
    comes back as "(4RT 154 zs afa4r afar a a6d)". It holds no Devanagari, so
    neither the fusion nor NMS sees it as a ghost, and it lands in the text
    beside the correct Hindi. It takes two shapes:

      - The whole box is the gloss. Paddle is unsure of it, and the trusted
        Tesseract words on that line cover it, so it is dropped whole.
      - The gloss is a bracket inside a real English box, the way these forms
        print labels: "P.S. (थाना): SHAHABAD" reads "P.S. (4I): SHAHABAD".
        Where trusted Tesseract words cover the bracket, it is replaced by
        them, giving back "P.S. (थाना): SHAHABAD"; those words are consumed so
        they are not emitted again as boxes of their own. Where only
        low-confidence Tesseract words cover it, and one of them opens with a
        bracket of its own — Tesseract saw "(" at that spot too — the bracket
        is deleted: Hindi goes there, but not Hindi we can vouch for.

    Trimming arbitrary words by an estimated x-position was tried and
    reverted: the estimate clipped "P.S." off "P.S. (4I): SHAHABAD" and the
    police-station field took a wrong value. The same proportional estimate
    locates the bracket here, but it can only ever rewrite text inside the
    brackets, so the label and the value around them are never touched.

    Returns the rewritten Latin boxes and the Devanagari boxes still unclaimed.
    """
    weak_dev_boxes = weak_dev_boxes or []
    consumed: set = set()
    kept: List[Dict[str, Any]] = []

    for box in latin_boxes:
        b = box.get("box")
        text = box.get("text", "")
        if not b or len(b) < 4 or b[2] <= b[0]:
            kept.append(box)
            continue
        line = [
            (i, d) for i, d in enumerate(dev_boxes)
            if i not in consumed and _same_line(b, d["box"])
        ]
        weak = [d for d in weak_dev_boxes if _same_line(b, d["box"])]
        if not line and not weak:
            kept.append(box)
            continue
        spans = [(d["box"][0], d["box"][2]) for _, d in line]

        if (
            float(box.get("confidence", 0.0)) < latin_confidence
            and _x_coverage(b[0], b[2], spans) >= _GLOSS_COVERAGE
        ):
            continue

        width, n = b[2] - b[0], max(len(text), 1)

        def under(d: Dict[str, Any], g1: float, g2: float) -> bool:
            return min(d["box"][2], g2) - max(d["box"][0], g1) > 0.5 * (d["box"][2] - d["box"][0])

        def replace(m: "re.Match[str]") -> str:
            g1 = b[0] + width * m.start() / n
            g2 = b[0] + width * m.end() / n
            if has_devanagari_letters(m.group(0)):
                return m.group(0)
            if _x_coverage(g1, g2, spans) >= _GLOSS_COVERAGE:
                words = sorted(
                    ((i, d) for i, d in line if i not in consumed and under(d, g1, g2)),
                    key=lambda w: w[1]["box"][0],
                )
                if words:
                    consumed.update(i for i, _ in words)
                    parts: List[str] = []
                    for _, d in words:
                        word = d["text"].replace("(", "").replace(")", "").strip(" :")
                        if word and (not parts or parts[-1] != word):
                            parts.append(word)
                    return "(" + " ".join(parts) + ")"
            nearby = [d for _, d in line if under(d, g1, g2)] + [d for d in weak if under(d, g1, g2)]
            if (
                any(d["text"].lstrip().startswith("(") for d in nearby)
                and _x_coverage(g1, g2, [(d["box"][0], d["box"][2]) for d in nearby]) >= _GLOSS_COVERAGE
            ):
                return ""
            return m.group(0)

        new_text = _PAREN_GROUP_RE.sub(replace, text)
        if new_text != text:
            new_text = re.sub(r"\s+([:.,])", r"\1", re.sub(r"\s{2,}", " ", new_text)).strip()
            box = dict(box)
            box["text"] = new_text
        if new_text.strip(".,:;()[]|- "):
            kept.append(box)

    return kept, [d for i, d in enumerate(dev_boxes) if i not in consumed]


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

    # Sort key — confidence first, Devanagari only as a tie-breaker.
    #
    # Devanagari presence used to rank ABOVE confidence, on the assumption that
    # a Devanagari reading is always the authentic one and the Latin box is the
    # hallucination. On a bilingual page that holds. On an English-only page it
    # inverts: the Devanagari pass hallucinates Indic numerals over Latin
    # digits, and that low-confidence guess then outranked the correct,
    # higher-confidence Latin reading of the same region. Confirmed live on an
    # English FIR — "Section 154" became "Section 15४" (0.89 beating 0.98),
    # "41 Jyotinagar" became "४१ Jyotinagar" (0.87 beating 0.99), and
    # "IPC 406" became "IPC ४०५" (0.73 beating 0.97). Silently corrupting a
    # statute number is materially worse than dropping a glyph.
    #
    # Ranking by the model's own confidence and using script only to break
    # ties keeps genuine Devanagari winning where it is actually read well —
    # on a real Hindi page the Devanagari pass scores high and the Latin pass
    # returns low-confidence garbage for the same box — without letting a weak
    # Indic guess overwrite confident Latin text.
    # Sort key, highest first: genuine Devanagari, then confidence, then area.
    #
    # The only change from the original ordering is that the script signal is
    # has_devanagari_LETTERS rather than has_devanagari. Indic numerals alone
    # are precisely what the Hindi pass hallucinates over printed Latin digits,
    # and counting those as authentic script let a weak guess outrank a
    # confident Latin read of the same region — turning "Section 154" into
    # "Section 15४" (0.89 beating 0.98) and "IPC 406" into "IPC ४०५" (0.73
    # beating 0.97) on an English FIR. Real Hindi text carries letters, so
    # keying on letters keeps "थाना" winning over its Latin ghost while
    # denying a bare numeral that same authority.
    #
    # Ranking area above confidence was tried and reverted: it cleaned up a
    # synthetic English page but destroyed the real Delhi FIR fixture, where
    # the correct content lives in the word-level boxes and the larger
    # competing box is garbage ("District: NORTH DIsTRIct/ Crme Branch, Delhi
    # P.S: KOTwALI" degraded to "District ! HIHON 12H1sI9 Srim? Branchi").
    # Confidence stays ahead of size.
    def sort_key(b: Dict[str, Any]) -> Tuple[int, float, int]:
        text = b.get("text", "")
        is_dev = 1 if has_devanagari_letters(text) else 0
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

            # Directional containment, measured against the candidate: "is
            # this candidate mostly inside something already kept?" That
            # direction is deliberate. It lets a high-ranking line box swallow
            # the word-level fragments detected under it, which is where most
            # of the suppression on a real scan comes from.
            #
            # Making it symmetric — min(area1, area2) — was tried and reverted.
            # It inverts that behaviour: a small fragment kept first then
            # suppresses the larger box containing it, so the line box dies and
            # all its other fragments survive. On the real Delhi FIR fixture
            # that took retention from 169 boxes to 246 and turned the header
            # "District: NORTH DIsTRIct/ Crme Branch, Delhi P.S: KOTwALI" into
            # "District ! HIHON 12H1sI9 Srim? Branchi" — the good line reads
            # were exactly the boxes it removed.
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


# The Hindi gloss these forms print after an English label — "P.S. (थाना):",
# "Date (दिनांक):" — which the field patterns step over to reach the value.
_GLOSS = r"(?:\s*\([^()\n]{0,40}\))?"

_TIME_VALUE = r"(?<![\d:])([0-2]?[0-9]:[0-5][0-9])(?![\d:])(\s*(?:hrs|nrs|am|pm|बजे))?"

# The row that records when the police station received the information —
# the FIR's registration time — and the rows that follow it on the form.
# Tolerant of the scan's misreads: "Informnation 'eccived" on the Haryana FIR.
_REGISTRATION_ROW_RE = re.compile(r"(?i)Info\w{0,8}\s+\S{0,3}c\w{0,3}ved|सूचना[^\n|]{0,15}प्राप्त")
_AFTER_REGISTRATION_RE = re.compile(
    r"(?i)Diary|रोजनामचा|Type\s+of\s+Information|सूचना\s+का\s+प्रकार|Place\s+of\s+Occurrence|घटना\s*स्थल"
)
# Labels of the occurrence period ("Time From", "समय से"), which sit above the
# registration row and are the times it was confused with.
_OCCURRENCE_TIME_RE = re.compile(r"(?i)Time\s*(?:From|To|Period)|Ti\w{1,2}\s+From|Perio?d|अवधि|समय\s*(?:से|तक)")


def _format_time(m: "re.Match[str]") -> str:
    return (m.group(1) + (m.group(2) or "")).replace("nrs", "hrs").strip()


def _registration_time(norm_text: str) -> Optional[str]:
    """When the FIR was registered — issue #107.

    Taking the first time on the page returned the occurrence time instead
    ("Time From 00:00" on the Haryana FIR, "Time From : 09:20" on Delhi),
    since the occurrence block is printed above the registration row. That is
    wrong data shown under the wrong label, which is worse than none.

    Where the form has an "Information received at P.S." row, the time is
    read from that row or the value row printed under it, and nowhere else:
    the search stops at the next section, so an empty field (as on the Delhi
    fixture) yields None rather than the Daily Diary time below it. Forms
    without that row (the UP template prints "दिनांक: ... समय: ..." on one
    line) fall back to a labelled time that is not an occurrence time.
    """
    lines = norm_text.split("\n")
    for i, line in enumerate(lines):
        if not _REGISTRATION_ROW_RE.search(line):
            continue
        for candidate in lines[i:i + 3]:
            if candidate is not line and _AFTER_REGISTRATION_RE.search(candidate):
                break
            m = re.search(_TIME_VALUE, candidate)
            if m:
                return _format_time(m)
        return None

    for line in lines:
        if _OCCURRENCE_TIME_RE.search(line):
            continue
        m = re.search(r"(?i)(?:Time|समय|वक्त)" + _GLOSS + r"[:\s]*" + _TIME_VALUE, line)
        if m:
            return _format_time(m)
    return None


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
        r"(?i)(?:FIR\s*N[oO0]\.?|एफ\.?आई\.?आर\.?\s*(?:सं\.?|संख्या|नं\.?)?|प्रथम\s*सूचना\s*रिपोर्ट(?:\s*(?:सं\.?|संख्या))?|मु\.?\s*अ\.?\s*सं\.?|मु०\s*अ०\s*सं०?|मुकदमा\s*अपराध\s*संख्या|अपराध\s*(?:सं\.?|संख्या))[^0-9\n]{0,40}([0-9]{1,12}(?:/[0-9]{2,4})?)",
        norm_text,
    )
    if m_fir:
        parsed["fir_number"] = m_fir.group(1).strip()

    # --- 2. District & 3. Police Station & 4. Year ---
    m_dist = re.search(
        r"(?i)(?:District|जिला|जनपद)" + _GLOSS + r"[:\s]*([^|\n]+?)(?=\s*\||\s*P\.?S\.?[:\s]|\s*Police\s+Station|\s*थाना|\s*कोतवाली|\s*Year|\s*वर्ष|\s*साल|$)",
        raw_text,
    )
    if m_dist:
        dist_val = m_dist.group(1).strip(" !:,-|")
        if dist_val:
            parsed["district"] = dist_val

    m_ps = re.search(
        r"(?i)(?:P\.?S\.?|Police\s+Station|थाना|कोतवाली)" + _GLOSS + r"[:\s]*([^|\n]+?)(?=\s*\||\s*Year|\s*वर्ष|\s*साल|\s*FIR|\s*मु\.?अ|\s*प्रथम|$)",
        raw_text,
    )
    if m_ps:
        ps_val = m_ps.group(1).strip(" !:,-|")
        if ps_val:
            parsed["police_station"] = ps_val

    m_year = re.search(r"(?i)(?:Year|वर्ष|साल)" + _GLOSS + r"[:\s]*([12][09][0-9]{2})", norm_text)
    if m_year:
        parsed["year"] = m_year.group(1).strip()
    elif parsed["fir_number"] and "/" in str(parsed["fir_number"]):
        parsed["year"] = parsed["fir_number"].split("/")[-1]

    # --- 5. Registration Date & 6. Registration Time ---
    m_date = re.search(r"(?i)(?:Date|दिनांक|तारीख)" + _GLOSS + r"[:\s]*([0-3]?[0-9][\/\-\.][01]?[0-9][\/\-\.][12][09][0-9]{2})", norm_text)
    if m_date:
        parsed["registration_date"] = m_date.group(1).strip()

    parsed["registration_time"] = _registration_time(norm_text)

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
    m_info = re.search(r"(?i)(?:Type\s+of\s+Information|सूचना\s+का\s+प्रकार)" + _GLOSS + r"[:\s]*([^|\n]+)", raw_text)
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


def drop_contained_duplicate_text(boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Removes a retained box whose text is already spelled out, verbatim, by a
    larger box overlapping the same region.

    Spatial NMS cannot catch this case. The English pass returns one box per
    line and the Devanagari pass one per word, so a line and its own fragments
    are all detections of the same text at different granularity. When a
    fragment outranks the line on confidence — common, since a single word
    scores 1.00 where the full line scores 0.97 — the fragment is retained
    first, and the line is then measured as overlap/area_of_line, a small
    fraction that clears neither the IoU nor the containment threshold. Both
    survive, and every such line lands in the output twice:

        "FIRST INFORMATION REPORT REPORT"
        "Complainant: Priya Menon Menon"
        "Accused: Kalyan Sarkar. Kalyan Sarkar"

    Widening the spatial test to fix this was tried and reverted — it destroys
    the line-swallows-fragments behaviour that does the real work on a scan
    (see deduplicate_boxes_nms). Comparing the decoded text instead is precise:
    a fragment is only dropped when a box it overlaps already contains that
    exact string, so nothing is removed on the strength of geometry alone.

    Case- and space-insensitive, since the two passes disagree on both
    ("NFORMATlON" vs "INFORMATION" is a different read and is deliberately
    NOT treated as a duplicate — only text that genuinely already appears is).
    """
    def norm(s: str) -> str:
        return "".join(s.split()).casefold()

    kept: List[Dict[str, Any]] = []
    for cand in boxes:
        c_txt = norm(cand.get("text", ""))
        c_box = cand.get("box")
        if not c_txt or not c_box or len(c_box) < 4:
            kept.append(cand)
            continue

        redundant = False
        for other in boxes:
            if other is cand:
                continue
            o_txt = norm(other.get("text", ""))
            o_box = other.get("box")
            if not o_box or len(o_box) < 4 or len(o_txt) <= len(c_txt):
                continue
            if c_txt not in o_txt:
                continue
            # Same region: the fragment must actually sit under the larger box.
            x_ov = max(0, min(c_box[2], o_box[2]) - max(c_box[0], o_box[0]))
            y_ov = max(0, min(c_box[3], o_box[3]) - max(c_box[1], o_box[1]))
            c_area = (c_box[2] - c_box[0]) * (c_box[3] - c_box[1])
            if c_area > 0 and (x_ov * y_ov) / c_area > 0.5:
                redundant = True
                break

        if not redundant:
            kept.append(cand)

    return kept


def process_ocr_boxes_to_layout(
    raw_boxes: List[Dict[str, Any]],
    devanagari_boxes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """End-to-end transformation:
    Raw OCR detections -> Devanagari fusion -> Spatial IoU NMS -> Row Clustering
    -> Bilingual Field Extraction.

    devanagari_boxes are Tesseract `hin` detections for the same page, used
    only on a page that passes page_is_bilingual — see fuse_devanagari_boxes.
    """
    if devanagari_boxes and page_is_bilingual(raw_boxes):
        raw_boxes = fuse_devanagari_boxes(raw_boxes, devanagari_boxes)

    filtered_boxes = drop_contained_duplicate_text(deduplicate_boxes_nms(raw_boxes))
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
