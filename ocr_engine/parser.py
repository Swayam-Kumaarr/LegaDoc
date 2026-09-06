import re

def parse_fir(raw_text: str):
    """
    Generic FIR parser
    Input  : Raw OCR text
    Output : Dictionary of extracted fields
    """

    parsed = {
        "fir_number": None,
        "district": None,
        "police_station": None,
        "year": None,
        "registration_date": None,
        "registration_time": None,
        "ipc_sections": [],
        "type_of_information": None,
    }

    # ---------- FIR Number ----------
    m = re.search(
        r"(?:FIR|F\.?I\.?R\.?)\s*(?:No\.?|Number)?[:\-\s]*([0-9]{1,4})/?(20\d{2})?",
        raw_text,
        re.IGNORECASE,
    )
    if m:
        parsed["fir_number"] = m.group(1).zfill(4)
        if m.group(2):
            parsed["year"] = m.group(2)

    # ---------- District ----------
    m = re.search(r"District\s*[:\-]?\s*([A-Za-z ]+)", raw_text, re.IGNORECASE)
    if m:
        parsed["district"] = m.group(1).strip()

    # ---------- Police Station ----------
    m = re.search(r"P\.?S\.?\s*[:\-]?\s*([A-Za-z ]+)", raw_text, re.IGNORECASE)
    if m:
        parsed["police_station"] = m.group(1).strip()

    # ---------- Registration Date ----------
    m = re.search(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b", raw_text)
    if m:
        parsed["registration_date"] = m.group()

    # ---------- Registration Time ----------
    m = re.search(r"\b\d{2}:\d{2}\b", raw_text)
    if m:
        parsed["registration_time"] = m.group()

    # ---------- IPC Sections ----------
    ipc_sections = set()

    matches = re.findall(
        r"(?:IPC\s*Sections?|Sections?|U/S|Under\s*Section)\s*[:\-]?\s*([\d,\s/]+)",
        raw_text,
        re.IGNORECASE,
    )

    for match in matches:
        nums = re.findall(r"\d{3}", match)
        ipc_sections.update(nums)

    parsed["ipc_sections"] = sorted(ipc_sections)

    # ---------- Type of Information ----------
    if re.search(r"Written", raw_text, re.IGNORECASE):
        parsed["type_of_information"] = "Written"
    elif re.search(r"Oral", raw_text, re.IGNORECASE):
        parsed["type_of_information"] = "Oral"

    return parsed