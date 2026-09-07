"""
Interactive Developer Test Harness (/demo).
Mounts a single-page HTML test cockpit for testing persona logins, case assignments,
document uploads, MinIO S3 storage, and blockchain chain status.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>LegaDoc — Developer Security & Upload Harness</title>
    <style>
        :root {
            --bg: #0d1117;
            --panel: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --text-muted: #8b949e;
            --accent: #58a6ff;
            --accent-green: #2ea043;
            --accent-red: #da3633;
            --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        body {
            background-color: var(--bg);
            color: var(--text);
            font-family: var(--font);
            margin: 0;
            padding: 24px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        h1 {
            color: #ffffff;
            font-size: 24px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .subtitle {
            color: var(--text-muted);
            margin-bottom: 24px;
            font-size: 14px;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        .panel {
            background-color: var(--panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
        }
        .panel h2 {
            font-size: 16px;
            margin-top: 0;
            margin-bottom: 16px;
            color: var(--accent);
            border-bottom: 1px solid var(--border);
            padding-bottom: 8px;
        }
        label {
            display: block;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
        select, input, button {
            width: 100%;
            box-sizing: border-box;
            background: #090d13;
            border: 1px solid var(--border);
            color: var(--text);
            padding: 8px 12px;
            border-radius: 6px;
            margin-bottom: 12px;
            font-size: 14px;
        }
        button {
            background-color: #238636;
            color: #ffffff;
            border: none;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.2s;
        }
        button:hover {
            background-color: var(--accent-green);
        }
        pre {
            background: #040d1a;
            border: 1px solid var(--border);
            padding: 12px;
            border-radius: 6px;
            font-size: 12px;
            overflow-x: auto;
            color: #79c0ff;
            max-height: 250px;
        }
        .badge {
            display: inline-block;
            padding: 2px 8px;
            font-size: 12px;
            border-radius: 12px;
            background: #21262d;
            color: var(--text-muted);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚖️ LegaDoc Testing Cockpit <span class="badge">v0.2.0 Baseline Upgrade</span></h1>
        <div class="subtitle">Interactive test harness for Auth, Multi-Tenant Scoping, MinIO S3 Object Uploads, and Chain Polling.</div>

        <div class="grid">
            <div class="panel">
                <h2>1. Persona & Authentication</h2>
                <label>Select Persona</label>
                <select id="persona" onchange="updateCredentials()">
                    <option value="officer.raj@police.gov.in|Password123!|io">Investigating Officer (Inspector Raj)</option>
                    <option value="sho.sharma@police.gov.in|Password123!|sho">Station House Officer (SHO Sharma)</option>
                    <option value="admin@legadoc.gov.in|Password123!|config_admin">Config Admin (System Admin)</option>
                    <option value="judge.iyer@court.gov.in|Password123!|court">Judge (Sessions Court)</option>
                    <option value="dr.verma@fsl.gov.in|Password123!|external_authority">FSL Doctor (Forensics)</option>
                    <option value="adv.kapoor@bar.in|Password123!|defense">Defense Lawyer (Kapoor)</option>
                </select>

                <label>Email</label>
                <input id="email" type="text" value="officer.raj@police.gov.in">

                <label>Password</label>
                <input id="password" type="password" value="Password123!">

                <button onclick="login()">Authenticate & Issue JWT</button>

                <label>Current JWT Token</label>
                <pre id="tokenDisplay">Not authenticated</pre>
            </div>

            <div class="panel">
                <h2>2. Secure Document Upload (MinIO S3)</h2>
                <label>Case ID (UUID)</label>
                <input id="caseId" type="text" placeholder="Enter case UUID or create one">

                <label>Document Type</label>
                <select id="docType">
                    <option value="FIR">FIR (First Information Report)</option>
                    <option value="CHARGE_SHEET">Charge Sheet</option>
                    <option value="POST_MORTEM_REPORT">Post Mortem Report</option>
                    <option value="SEIZURE_MEMO">Seizure Memo</option>
                    <option value="FORENSIC_REPORT">Forensic Report</option>
                    <option value="CCTV_FOOTAGE">CCTV Footage (Binary Evidence)</option>
                </select>

                <label>File to Upload (sniffed via libmagic, max 50MB)</label>
                <input id="fileUpload" type="file">

                <button onclick="uploadDocument()">Upload via Ingestion Pipeline</button>

                <label>Pipeline Response</label>
                <pre id="uploadResponse">No upload executed yet</pre>
            </div>
        </div>
    </div>

    <script>
        let currentToken = "";

        function updateCredentials() {
            const [email, pwd] = document.getElementById('persona').value.split('|');
            document.getElementById('email').value = email;
            document.getElementById('password').value = pwd;
        }

        async function login() {
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            try {
                const res = await fetch('/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email, password})
                });
                const data = await res.json();
                if (res.ok) {
                    currentToken = data.access_token;
                    document.getElementById('tokenDisplay').innerText = `Access Token: ${currentToken.substring(0, 30)}...\\nExpires in: 15 min\\nRefresh Token issued: Yes`;
                } else {
                    document.getElementById('tokenDisplay').innerText = `Error: ${JSON.stringify(data)}`;
                }
            } catch (err) {
                document.getElementById('tokenDisplay').innerText = `Error: ${err.message}`;
            }
        }

        async function uploadDocument() {
            if (!currentToken) {
                alert('Please authenticate first!');
                return;
            }
            const caseId = document.getElementById('caseId').value.trim();
            const docType = document.getElementById('docType').value;
            const fileInput = document.getElementById('fileUpload');
            if (!caseId) {
                alert('Please enter a Case UUID');
                return;
            }
            if (fileInput.files.length === 0) {
                alert('Please select a file');
                return;
            }

            const formData = new FormData();
            formData.append('case_id', caseId);
            formData.append('doc_type', docType);
            formData.append('file', fileInput.files[0]);

            try {
                const res = await fetch('/documents', {
                    method: 'POST',
                    headers: {'Authorization': `Bearer ${currentToken}`},
                    body: formData
                });
                const data = await res.json();
                document.getElementById('uploadResponse').innerText = JSON.stringify(data, null, 2);
            } catch (err) {
                document.getElementById('uploadResponse').innerText = `Error: ${err.message}`;
            }
        }
    </script>
</body>
</html>
"""

@router.get("", response_class=HTMLResponse)
def get_demo_cockpit():
    """Serves the interactive developer test cockpit."""
    return HTMLResponse(content=DEMO_HTML)
