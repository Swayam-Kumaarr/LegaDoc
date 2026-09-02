"""
==============================================================================
DEVELOPER TESTING & DEMO HARNESS (TEMPORARY BACKEND TEST INTERFACE)
==============================================================================

NOTE FOR WEB/FRONTEND TEAM (Abhinav & Bhavya):
This route provides a lightweight single-page HTML test interface served at /demo
purely for backend developers to visually verify Auth, RBAC, Multi-Tenant Scoping,
and Audit Hash-Chaining during development.

It lives solely in api/ and does NOT interfere with, replace, or modify anything
in the web/ React frontend directory. When the React frontend is ready, this route
can either be retained as an internal debug console or unmounted.
==============================================================================
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/demo", tags=["demo-ui"], include_in_schema=False)

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LegaDoc — Dev Security & RBAC Test Harness</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0b0f19;
            --surface: #111827;
            --surface-card: rgba(17, 24, 39, 0.85);
            --border: #1f293d;
            --border-hover: #374151;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --primary: #3b82f6;
            --primary-glow: rgba(59, 130, 246, 0.25);
            --accent-green: #10b981;
            --accent-green-bg: rgba(16, 185, 129, 0.15);
            --accent-red: #ef4444;
            --accent-red-bg: rgba(239, 68, 68, 0.15);
            --accent-amber: #f59e0b;
            --accent-purple: #8b5cf6;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg);
            color: var(--text-main);
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            min-height: 100vh;
            padding: 2rem 1.5rem;
            line-height: 1.5;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 0.875rem;
        }

        .logo-icon {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #2563eb, #7c3aed);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.35rem;
            box-shadow: 0 0 20px var(--primary-glow);
        }

        .title {
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(to right, #ffffff, #93c5fd);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .subtitle {
            font-size: 0.82rem;
            color: var(--text-muted);
        }

        .team-banner {
            background: rgba(59, 130, 246, 0.08);
            border: 1px dashed rgba(59, 130, 246, 0.35);
            padding: 0.75rem 1.25rem;
            border-radius: 10px;
            font-size: 0.82rem;
            color: #93c5fd;
            margin-bottom: 2rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        @media (max-width: 900px) {
            .grid {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: var(--surface-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3);
        }

        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1.25rem;
        }

        .card-title {
            font-size: 1rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .persona-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.75rem;
        }

        @media (max-width: 600px) {
            .persona-grid {
                grid-template-columns: 1fr;
            }
        }

        .persona-btn {
            background: rgba(31, 41, 61, 0.5);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 0.875rem 1rem;
            color: var(--text-main);
            cursor: pointer;
            text-align: left;
            transition: all 0.2s ease;
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .persona-btn:hover {
            border-color: var(--primary);
            background: rgba(59, 130, 246, 0.1);
            transform: translateY(-2px);
        }

        .persona-btn.active {
            border-color: var(--primary);
            background: rgba(59, 130, 246, 0.18);
            box-shadow: 0 0 16px var(--primary-glow);
        }

        .persona-name {
            font-size: 0.88rem;
            font-weight: 700;
        }

        .persona-role-badge {
            display: inline-block;
            font-size: 0.7rem;
            font-family: 'JetBrains Mono', monospace;
            padding: 0.15rem 0.5rem;
            border-radius: 6px;
            background: rgba(255,255,255,0.06);
            color: #60a5fa;
            width: fit-content;
        }

        .badge-admin { color: #f472b6; background: rgba(244, 114, 182, 0.12); }
        .badge-court { color: #c084fc; background: rgba(192, 132, 252, 0.12); }
        .badge-fsl { color: #34d399; background: rgba(52, 211, 153, 0.12); }
        .badge-defense { color: #fbbf24; background: rgba(251, 191, 36, 0.12); }

        .session-info {
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
            color: #d1d5db;
            overflow-x: auto;
            max-height: 220px;
        }

        .tester-btn-group {
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }

        .action-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.75rem 1rem;
            background: rgba(31, 41, 61, 0.35);
            border: 1px solid var(--border);
            border-radius: 10px;
            gap: 1rem;
        }

        .action-label {
            font-size: 0.85rem;
            font-weight: 600;
        }

        .action-endpoint {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        .btn-test {
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.45rem 1rem;
            border-radius: 8px;
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            white-space: nowrap;
        }

        .btn-test:hover {
            background: #2563eb;
            box-shadow: 0 0 12px var(--primary-glow);
        }

        .status-badge {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-weight: 700;
        }

        .status-200 { background: var(--accent-green-bg); color: var(--accent-green); }
        .status-403 { background: var(--accent-red-bg); color: var(--accent-red); }
        .status-401 { background: rgba(245, 158, 11, 0.15); color: var(--accent-amber); }
        .status-501 { background: rgba(139, 92, 246, 0.15); color: var(--accent-purple); }

        .terminal-output {
            background: #060911;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.25rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
            color: #93c5fd;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 240px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="brand">
                <div class="logo-icon">⚖️</div>
                <div>
                    <h1 class="title">LegaDoc Developer Security Harness</h1>
                    <p class="subtitle">Phase 1 Substrate Verification & Live RBAC Inspector</p>
                </div>
            </div>
            <div style="text-align: right;">
                <span class="status-badge status-200">API STACK ONLINE</span>
            </div>
        </header>

        <div class="team-banner">
            <span>ℹ️</span>
            <div><strong>Developer Note:</strong> This test harness runs on <code>/demo</code> inside the API to verify Auth & RBAC logic. It does not replace the upcoming React frontend in <code>web/</code>.</div>
        </div>

        <div class="grid">
            <!-- Left Card: Persona Switcher -->
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">🎭 Quick-Login Personas</h2>
                    <span style="font-size: 0.75rem; color: var(--text-muted);">One-click authentication</span>
                </div>
                <div class="persona-grid">
                    <button class="persona-btn active" onclick="loginPersona('officer.raj@police.gov.in')">
                        <span class="persona-name">👮 Officer Rajesh Kumar</span>
                        <span class="persona-role-badge">Role: IO (Assigned)</span>
                    </button>
                    <button class="persona-btn" onclick="loginPersona('sho.vikram@police.gov.in')">
                        <span class="persona-name">🛡️ SHO Vikram Singh</span>
                        <span class="persona-role-badge">Role: SHO (Police)</span>
                    </button>
                    <button class="persona-btn" onclick="loginPersona('admin@legadoc.gov.in')">
                        <span class="persona-name">👑 System Administrator</span>
                        <span class="persona-role-badge badge-admin">Role: Admin</span>
                    </button>
                    <button class="persona-btn" onclick="loginPersona('court.magistrate@judiciary.gov.in')">
                        <span class="persona-name">⚖️ Judge Bhagwati</span>
                        <span class="persona-role-badge badge-court">Role: Court</span>
                    </button>
                    <button class="persona-btn" onclick="loginPersona('dr.sunita@fsl.gov.in')">
                        <span class="persona-name">🧪 Dr. Sunita Sharma</span>
                        <span class="persona-role-badge badge-fsl">Role: FSL Authority</span>
                    </button>
                    <button class="persona-btn" onclick="loginPersona('kapoor.defense@legalbar.in')">
                        <span class="persona-name">🏛️ Adv. Kapoor</span>
                        <span class="persona-role-badge badge-defense">Role: Defense</span>
                    </button>
                </div>
            </div>

            <!-- Right Card: Live Token & Session Inspector -->
            <div class="card">
                <div class="card-header">
                    <h2 class="card-title">🔐 Active JWT Session Claims</h2>
                    <span id="sessionStatus" class="status-badge status-200">LOGGED IN</span>
                </div>
                <div class="session-info" id="claimsDisplay">
Loading session...
                </div>
            </div>
        </div>

        <!-- Security & Route Tester -->
        <div class="card">
            <div class="card-header">
                <h2 class="card-title">🛡️ Multi-Tenant RBAC Endpoint Permission Tester</h2>
                <span style="font-size: 0.75rem; color: var(--text-muted);">Tests backend permission gating for the active role</span>
            </div>
            <div class="tester-btn-group">
                <div class="action-row">
                    <div>
                        <div class="action-label">1. My Profile Verification</div>
                        <div class="action-endpoint">GET /auth/me &bull; Any authenticated user</div>
                    </div>
                    <button class="btn-test" onclick="testEndpoint('/auth/me', 'GET')">Test Access</button>
                </div>

                <div class="action-row">
                    <div>
                        <div class="action-label">2. Document Schema Registry Config</div>
                        <div class="action-endpoint">GET /admin/document-schemas &bull; Admin Only</div>
                    </div>
                    <button class="btn-test" onclick="testEndpoint('/admin/document-schemas', 'GET')">Test Access</button>
                </div>

                <div class="action-row">
                    <div>
                        <div class="action-label">3. Case Investigation Materials</div>
                        <div class="action-endpoint">GET /cases &bull; Role & Assignment Gated (Defense Blocked)</div>
                    </div>
                    <button class="btn-test" onclick="testEndpoint('/cases', 'GET')">Test Access</button>
                </div>

                <div class="action-row">
                    <div>
                        <div class="action-label">4. De-Identified NCRB Metadata View</div>
                        <div class="action-endpoint">GET /reports/case-metadata &bull; NCRB Analyst Only</div>
                    </div>
                    <button class="btn-test" onclick="testEndpoint('/reports/case-metadata', 'GET')">Test Access</button>
                </div>
            </div>

            <!-- Phase 2: Document Upload & Pipeline Tester -->
            <div class="card" style="margin-top: 1.5rem;">
                <div class="card-title">
                    <span>📤 Phase 2 — Document Upload & Chain Poll</span>
                    <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: normal;">Max 50MB &bull; MIME Magic-Sniffed</span>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                    <div>
                        <label style="font-size: 0.75rem; color: var(--text-muted); display: block; margin-bottom: 0.3rem;">CASE ID (Default: FIR-2026-DEL-0042)</label>
                        <input id="docCaseId" type="text" value="41403d8b-54fc-417d-9268-147af0d71577" style="width: 100%; background: #060911; border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 0.6rem; color: var(--text-main); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
                    </div>
                    <div>
                        <label style="font-size: 0.75rem; color: var(--text-muted); display: block; margin-bottom: 0.3rem;">DOCUMENT TYPE</label>
                        <select id="docTypeSelect" style="width: 100%; background: #060911; border: 1px solid var(--border); border-radius: 6px; padding: 0.4rem 0.6rem; color: var(--text-main); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
                            <option value="FIR_Report">FIR_Report (Text/PDF)</option>
                            <option value="Medical_Legal_Certificate">Medical_Legal_Certificate (Tier 1)</option>
                            <option value="Witness_Statement">Witness_Statement (Tier 1)</option>
                            <option value="CCTV_Footage">CCTV_Footage (Binary Evidence)</option>
                        </select>
                    </div>
                </div>

                <div style="display: flex; gap: 0.75rem; align-items: center; margin-bottom: 1rem;">
                    <input id="docFileInput" type="file" style="font-size: 0.75rem; color: var(--text-muted); flex: 1;">
                    <button class="btn-test" style="background: var(--accent-green);" onclick="uploadDemoDocument()">Upload Document</button>
                    <button class="btn-test" style="background: #374151;" onclick="createSampleAndUpload()">Upload Test PDF</button>
                </div>

                <div id="uploadResultBanner" style="display: none; padding: 0.75rem; border-radius: 8px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.78rem; font-family: 'JetBrains Mono', monospace;">
                        <span>Uploaded Doc ID: <strong id="lastDocId" style="color: #60a5fa;">-</strong></span>
                        <span id="lastChainStatus" class="status-badge status-401">PENDING</span>
                    </div>
                    <div style="display: flex; gap: 0.5rem; margin-top: 0.6rem;">
                        <button class="btn-test" style="font-size: 0.7rem; padding: 0.25rem 0.6rem;" onclick="pollLastDocChain()">Poll Chain Status</button>
                        <button class="btn-test" style="font-size: 0.7rem; padding: 0.25rem 0.6rem; background: #4b5563;" onclick="viewLastDoc()">View Document</button>
                        <button class="btn-test" style="font-size: 0.7rem; padding: 0.25rem 0.6rem; background: #b45309;" onclick="retryLastDocChain()">Retry Chain Write (Admin)</button>
                    </div>
                </div>
            </div>

            <div style="margin-top: 1.5rem;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="font-size: 0.8rem; font-weight: 700; color: var(--text-muted);">LIVE SERVER RESPONSE</span>
                    <span id="responseStatus" class="status-badge" style="display:none;"></span>
                </div>
                <div class="terminal-output" id="responseOutput">Click any "Test Access" button above to inspect server response...</div>
            </div>
        </div>
    </div>

    <script>
        let currentToken = "";
        let currentClaims = {};

        async function loginPersona(email) {
            document.querySelectorAll('.persona-btn').forEach(btn => btn.classList.remove('active'));
            event.currentTarget.classList.add('active');

            try {
                const res = await fetch('/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: email, password: 'Password123!' })
                });

                if (!res.ok) {
                    throw new Error('Login failed: ' + res.statusText);
                }

                const data = await res.json();
                currentToken = data.access_token;

                // Decode claims
                const payloadBase64 = currentToken.split('.')[1];
                currentClaims = JSON.parse(atob(payloadBase64.replace(/-/g, '+').replace(/_/g, '/')));

                document.getElementById('claimsDisplay').textContent = JSON.stringify({
                    user: data.name,
                    role: data.role,
                    user_id: data.user_id,
                    org_id: data.org_id,
                    token_type: data.token_type,
                    expires: new Date(currentClaims.exp * 1000).toLocaleTimeString()
                }, null, 2);

                document.getElementById('sessionStatus').textContent = 'ROLE: ' + data.role.toUpperCase();
                document.getElementById('responseOutput').textContent = '✅ Switched to ' + data.name + ' (' + data.role + '). Ready to test routes.';
                document.getElementById('responseStatus').style.display = 'none';

                // Pre-populate showcase case ID if empty
                if (!document.getElementById('docCaseId').value) {
                    loadDefaultCase();
                }
            } catch (err) {
                document.getElementById('claimsDisplay').textContent = 'Error: ' + err.message;
            }
        }

        async function loadDefaultCase() {
            try {
                const res = await fetch('/cases', {
                    headers: { 'Authorization': 'Bearer ' + currentToken }
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.items && data.items.length > 0) {
                        document.getElementById('docCaseId').value = data.items[0].id;
                    }
                }
            } catch (e) {}
        }

        let lastUploadedDocId = "";

        async function uploadDemoDocument() {
            const caseId = document.getElementById('docCaseId').value;
            const docType = document.getElementById('docTypeSelect').value;
            const fileInput = document.getElementById('docFileInput');

            if (!caseId) {
                alert('Please enter a valid Case ID');
                return;
            }
            if (!fileInput.files || fileInput.files.length === 0) {
                alert('Please select a file or click "Upload Test PDF"');
                return;
            }

            const formData = new FormData();
            formData.append('case_id', caseId);
            formData.append('doc_type', docType);
            formData.append('file', fileInput.files[0]);

            executeUpload(formData);
        }

        async function createSampleAndUpload() {
            const caseId = document.getElementById('docCaseId').value;
            const docType = document.getElementById('docTypeSelect').value;
            if (!caseId) {
                alert('Please enter a valid Case ID');
                return;
            }

            // Minimal valid PDF binary
            const samplePdf = "%PDF-1.4\\n1 0 obj\\n<< /Type /Catalog /Pages 2 0 R >>\\nendobj\\n2 0 obj\\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\\nendobj\\n3 0 obj\\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\\nendobj\\n4 0 obj\\n<< /Length 44 >>\\nstream\\nBT /F1 12 Tf 72 712 Td (LegaDoc Test FIR) Tj ET\\nendstream\\nendobj\\nxref\\n0 5\\n0000000000 65535 f\\n0000000009 00000 n\\n0000000058 00000 n\\n0000000115 00000 n\\n0000000214 00000 n\\ntrailer\\n<< /Size 5 /Root 1 0 R >>\\nstartxref\\n307\\n%%EOF";
            const blob = new Blob([samplePdf], { type: 'application/pdf' });
            const testFile = new File([blob], 'demo_fir_' + Date.now() + '.pdf', { type: 'application/pdf' });

            const formData = new FormData();
            formData.append('case_id', caseId);
            formData.append('doc_type', docType);
            formData.append('file', testFile);

            executeUpload(formData);
        }

        async function executeUpload(formData) {
            const out = document.getElementById('responseOutput');
            const statusBadge = document.getElementById('responseStatus');
            out.textContent = 'Uploading document via POST /documents...';
            statusBadge.style.display = 'inline-block';

            try {
                const res = await fetch('/documents', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + currentToken },
                    body: formData
                });

                statusBadge.textContent = 'HTTP ' + res.status + ' ' + res.statusText;
                statusBadge.className = 'status-badge ' + (res.status < 300 ? 'status-200' : (res.status === 403 ? 'status-403' : 'status-401'));

                const json = await res.json();
                out.textContent = 'Request: POST /documents\\n' +
                                  'Status:  ' + res.status + ' ' + res.statusText + '\\n' +
                                  'Auth:    Bearer (' + currentClaims.role + ' / ' + currentClaims.sub + ')\\n\\n' +
                                  JSON.stringify(json, null, 2);

                if (res.ok && json.document_id) {
                    lastUploadedDocId = json.document_id;
                    document.getElementById('lastDocId').textContent = json.document_id.slice(0, 18) + '...';
                    document.getElementById('lastChainStatus').textContent = (json.chain_status || 'PENDING').toUpperCase();
                    document.getElementById('uploadResultBanner').style.display = 'block';
                }
            } catch (err) {
                statusBadge.textContent = 'ERROR';
                statusBadge.className = 'status-badge status-403';
                out.textContent = 'Upload Error: ' + err.message;
            }
        }

        async function pollLastDocChain() {
            if (!lastUploadedDocId) return;
            testEndpoint('/documents/' + lastUploadedDocId + '/chain-status', 'GET');
        }

        async function viewLastDoc() {
            if (!lastUploadedDocId) return;
            testEndpoint('/documents/' + lastUploadedDocId, 'GET');
        }

        async function retryLastDocChain() {
            if (!lastUploadedDocId) return;
            testEndpoint('/documents/' + lastUploadedDocId + '/retry-chain-write', 'POST');
        }

        async function testEndpoint(path, method) {
            const out = document.getElementById('responseOutput');
            const statusBadge = document.getElementById('responseStatus');
            out.textContent = 'Executing ' + method + ' ' + path + ' with active Bearer token...';
            statusBadge.style.display = 'inline-block';

            try {
                const res = await fetch(path, {
                    method: method,
                    headers: {
                        'Authorization': 'Bearer ' + currentToken,
                        'Content-Type': 'application/json'
                    }
                });

                statusBadge.textContent = 'HTTP ' + res.status + ' ' + res.statusText;
                statusBadge.className = 'status-badge ' + (res.status < 300 ? 'status-200' : (res.status === 403 ? 'status-403' : (res.status === 501 ? 'status-501' : 'status-401')));

                let bodyText;
                try {
                    const json = await res.json();
                    bodyText = JSON.stringify(json, null, 2);
                    if (json.chain_status) {
                        document.getElementById('lastChainStatus').textContent = json.chain_status.toUpperCase();
                    }
                } catch {
                    bodyText = await res.text();
                }

                out.textContent = 'Request: ' + method + ' ' + path + '\\n' +
                                  'Status:  ' + res.status + ' ' + res.statusText + '\\n' +
                                  'Auth:    Bearer (' + currentClaims.role + ' / ' + currentClaims.sub + ')\\n\\n' +
                                  bodyText;
            } catch (err) {
                statusBadge.textContent = 'ERROR';
                statusBadge.className = 'status-badge status-403';
                out.textContent = 'Network Error: ' + err.message;
            }
        }

        // Auto-login default persona on load
        window.addEventListener('DOMContentLoaded', () => {
            loginPersona('officer.raj@police.gov.in');
        });
    </script>
</body>
</html>
"""


@router.get("", response_class=HTMLResponse)
def get_demo_dashboard():
    """GET /demo — Serves the developer security test harness."""
    return HTML_CONTENT
