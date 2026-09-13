// Development-only offline mock store for testing when FastAPI backend is not running
const STORAGE_KEY = "legadoc_dev_cases";

function getStoredCases() {
  const existing = sessionStorage.getItem(STORAGE_KEY);
  if (existing) {
    try {
      return JSON.parse(existing);
    } catch {
      // ignore
    }
  }
  const defaults = [
    {
      id: "case-2026-001",
      case_number: "FIR-2026-ND-0104",
      crime_type: "Cyber Financial Fraud (Sec 420 IPC / 318 BNS)",
      investigation_status: "under_investigation",
      bail_status: "opposed_by_prosecution",
      court_level: "Chief Metropolitan Magistrate, Patiala House",
      created_at: new Date(Date.now() - 3 * 86400000).toISOString(),
      complaint_text:
        "Unauthorized debit of funds through compromised OTP and remote access trojan.",
    },
    {
      id: "case-2026-002",
      case_number: "FIR-2026-ND-0108",
      crime_type: "Digital Identity Theft & Forgery (Sec 468 IPC / 336 BNS)",
      investigation_status: "registered",
      bail_status: "not_applied",
      court_level: "Metropolitan Magistrate Court 03, New Delhi",
      created_at: new Date(Date.now() - 1 * 86400000).toISOString(),
      complaint_text:
        "Fabricated digital stamp and signature discovered on forged sale deed.",
    },
    {
      id: "case-2026-003",
      case_number: "FIR-2026-ND-0112",
      crime_type: "NDPS Contraband Trafficking (Sec 20 NDPS Act)",
      investigation_status: "charge_sheet_filed",
      bail_status: "rejected",
      court_level: "Special NDPS Court, Saket",
      created_at: new Date(Date.now() - 7 * 86400000).toISOString(),
      complaint_text:
        "Commercial quantity contraband intercepted with digital GPS trail evidence.",
    },
  ];
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(defaults));
  return defaults;
}

export function handleDevMockRequest(endpoint, config = {}) {
  const method = (config.method || "GET").toUpperCase();

  // /health check
  if (endpoint === "/health") {
    return { status: "operational", service: "legadoc-api", mode: "dev-mock" };
  }

  // /cases
  if (endpoint === "/cases") {
    if (method === "GET") {
      return getStoredCases();
    }
    if (method === "POST") {
      let body = config.body;
      if (typeof body === "string") {
        try {
          body = JSON.parse(body);
        } catch {
          body = {};
        }
      }
      const cases = getStoredCases();
      const num = Math.floor(100 + Math.random() * 900);
      const newCase = {
        id: `case-dev-${Date.now()}`,
        case_number: `FIR-2026-ND-0${num}`,
        crime_type: body?.crime_type || "Unspecified Cognizable Offense",
        complaint_text: body?.complaint_text || "",
        investigation_status: "registered",
        bail_status: "not_applied",
        court_level: "Metropolitan Magistrate Court, New Delhi",
        created_at: new Date().toISOString(),
      };
      cases.unshift(newCase);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(cases));
      return newCase;
    }
  }

  // /cases/:id
  const caseIdMatch = endpoint.match(/^\/cases\/([^/]+)$/);
  if (caseIdMatch && method === "GET") {
    const caseId = caseIdMatch[1];
    const cases = getStoredCases();
    const found = cases.find(
      (c) => c.id === caseId || c.case_number === caseId,
    );
    return found || cases[0];
  }

  // /cases/:id/documents
  if (endpoint.includes("/documents") && method === "GET") {
    return [
      {
        id: "doc-101",
        title: "Signed First Information Report (FIR.pdf)",
        document_type: "fir",
        hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        status: "verified_on_chain",
        created_at: new Date().toISOString(),
      },
      {
        id: "doc-102",
        title: "Digital Seizure Memo & Mobile Hash Extraction",
        document_type: "panchnama",
        hash: "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
        status: "verified_on_chain",
        created_at: new Date().toISOString(),
      },
    ];
  }

  // /cases/:id/audit-log
  if (endpoint.includes("/audit-log") && method === "GET") {
    return {
      chain_intact: true,
      total_entries: 3,
      view_type: "full",
      entries: [
        {
          id: "ev-1",
          action: "FIR Registered & Encrypted Ingest",
          created_at: new Date(Date.now() - 3600000).toISOString(),
          row_hash:
            "3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
          prev_hash:
            "0000000000000000000000000000000000000000000000000000000000000000",
        },
        {
          id: "ev-2",
          action: "Digital Hash Committed to Hyperledger Fabric",
          created_at: new Date(Date.now() - 1800000).toISOString(),
          row_hash:
            "7d8e4f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e",
          prev_hash:
            "3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
      ],
    };
  }

  // /cases/:id/bail
  if (endpoint.includes("/bail") && method === "GET") {
    return [];
  }

  // /review-queue
  if (endpoint.includes("/review-queue") || endpoint === "/needs-review") {
    return [
      {
        id: "rev-01",
        case_id: "case-2026-001",
        case_number: "FIR-2026-ND-0104",
        reason: "Low OCR confidence on handwritten panchnama stamp (68%)",
        status: "pending_review",
        created_at: new Date().toISOString(),
      },
    ];
  }

  // /reports
  if (endpoint.includes("/reports")) {
    return {
      total_cases: 14,
      under_investigation: 8,
      charge_sheets_filed: 4,
      disposed: 2,
    };
  }

  // Default fallback
  return { status: "success", endpoint, mode: "dev-offline-mock" };
}
