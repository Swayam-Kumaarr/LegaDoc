import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';
import HashCell from '../components/HashCell';

export default function CaseDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('documents'); // 'overview' | 'documents' | 'evidence' | 'bail' | 'diary' | 'audit'

  const caseData = {
    id: id || 'b1a2c3d4-0001-4000-8000-000000000001',
    case_number: 'CYB-2026-482910',
    crime_type: 'Financial Cyberfraud (Sec 66D IT Act)',
    status: 'UNDER_INVESTIGATION',
    status_label: 'Under Investigation',
    registered_at: '2026-09-01T10:30:00Z',
    assigned_io: 'Inspector S. Rao, Badge #POL-4921',
    investigation_stage: 'Forensic Ingestion & Witness Deposition',
    court: 'Patiala House Chief Judicial Magistrate Court #3',
    oldest_pending_item_hours: 48,
  };

  const documents = [
    { id: 'DOC-CYB-2026-001', type: 'FIR Initial Evidentiary Statement', version: 1, hash: '8f92a11b6c73e04812f86419bd39c29804bba28198fcd890141eab1490214811', status: 'READY', chain_status: 'CONFIRMED' },
    { id: 'DOC-CYB-2026-002', type: 'Panchnama (Physical Hardware Seizure)', version: 1, hash: '44aa9011e8271109a1284bb1928371827419ba8201aeb4819208471192837482', status: 'READY', chain_status: 'CONFIRMED' },
    { id: 'DOC-CYB-2026-003', type: 'Complainant Deposition (Section 161 CrPC)', version: 1, hash: '77bc5512e0912781290384aa8192837491028374019284719283748291028471', status: 'NEEDS_REVIEW', chain_status: 'PROCESSING' }
  ];

  const evidenceRequests = [
    { id: 'REQ-2026-01', authority: 'HDFC Bank Nodal Unit', req_type: 'Certified Account Transaction Ledger', status: 'PENDING', requested_days_ago: 2, is_slow: true },
    { id: 'REQ-2026-02', authority: 'Airtel Telecom Nodal Cell', req_type: 'CDR / IPDR Timestamp Records', status: 'FULFILLED', requested_days_ago: 3, is_slow: false },
  ];

  const auditEvents = [
    {
      block_num: 89012,
      timestamp: '2026-09-01 10:30:14 IST',
      event: 'Case Inception & FIR Genesis Registration',
      authority: 'DO-9011 (Cyber Crime PS Central)',
      tx_hash: '44aa9011e8271109a1284bb1928371827419ba8201aeb4819208471192837482',
      parent_hash: '0000000000000000000000000000000000000000000000000000000000000000',
      status: 'CONFIRMED'
    },
    {
      block_num: 89045,
      timestamp: '2026-09-01 11:15:22 IST',
      event: 'Primary FIR Statement Ingested & Hashed',
      authority: 'IO-S-RAO-4921 (Investigating Officer)',
      tx_hash: '8f92a11b6c73e04812f86419bd39c29804bba28198fcd890141eab1490214811',
      parent_hash: '44aa9011e8271109a1284bb1928371827419ba8201aeb4819208471192837482',
      status: 'CONFIRMED'
    },
    {
      block_num: 89063,
      timestamp: '2026-09-01 14:02:49 IST',
      event: 'Hardware Seizure Panchnama Committed',
      authority: 'IO-S-RAO-4921 (Investigating Officer)',
      tx_hash: '77bc5512e0912781290384aa8192837491028374019284719283748291028471',
      parent_hash: '8f92a11b6c73e04812f86419bd39c29804bba28198fcd890141eab1490214811',
      status: 'CONFIRMED'
    },
    {
      block_num: 89088,
      timestamp: '2026-09-02 09:45:10 IST',
      event: 'Section 91 CrPC Production Notice Dispatched',
      authority: 'IO-S-RAO-4921 (Investigating Officer)',
      tx_hash: '2c9e78f102938475610293847561029384756102938475610293847561029384',
      parent_hash: '77bc5512e0912781290384aa8192837491028374019284719283748291028471',
      status: 'CONFIRMED'
    }
  ];

  return (
    <div>
      {/* Breadcrumb Bar */}
      <div className="gov-breadcrumb-bar">
        <Link to="/cases">Case Registry</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Case Docket: {caseData.case_number}</span>
      </div>

      <div className="page-container">
        {/* Case Header: Case Number in text-display serif + inline status chip (PRD Section 8) */}
        <div className="page-header" style={{ marginBottom: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <h1 className="text-display">Case {caseData.case_number}</h1>
              <StatusChip status={caseData.status} label={caseData.status_label} />
              <span className="status-chip status-chip-success">Fabric Ledger Confirmed</span>
            </div>
            <p className="page-desc">
              Jurisdiction: {caseData.court} · Registered: {new Date(caseData.registered_at).toLocaleDateString()}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <Link to={`/cases/${caseData.id}/charge-sheet`} className="btn btn-primary btn-sm">
              Prosecutor Validation & Charge Sheet
            </Link>
          </div>
        </div>

        {/* Dense Two-Column Metadata Block (PRD Section 8) */}
        <div className="card" style={{ padding: '12px 16px', marginBottom: '16px' }}>
          <div className="grid-2" style={{ margin: 0, gap: '12px' }}>
            <div>
              <div className="text-label" style={{ marginBottom: '2px' }}>Investigating Officer</div>
              <div className="text-body" style={{ fontWeight: 600 }}>{caseData.assigned_io}</div>
              <div className="text-label" style={{ marginTop: '8px', marginBottom: '2px' }}>Crime Type Classification</div>
              <div className="text-body">{caseData.crime_type}</div>
            </div>
            <div>
              <div className="text-label" style={{ marginBottom: '2px' }}>FIR Registration Date</div>
              <div className="text-body" style={{ fontFamily: 'var(--font-mono)' }}>
                {caseData.registered_at} (Day 5 of statutory 60-day period)
              </div>
              <div className="text-label" style={{ marginTop: '8px', marginBottom: '2px' }}>Current Lifecycle Stage</div>
              <div className="text-body">{caseData.investigation_stage}</div>
            </div>
          </div>
        </div>

        {/* Bottleneck Notice */}
        <div className="alert alert-warning" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <strong>Requisition SLA Warning:</strong> Evidence request to <strong>HDFC Bank Nodal Unit</strong> has been open for 48 hours. Target SLA is 72 hours.
          </div>
          <span className="status-chip status-chip-pending">Pending SLA</span>
        </div>

        {/* Underlined Text Tabs (PRD Section 8: Underlined tabs, NOT pill/rounded) */}
        <div className="gov-tabs">
          <button
            className={`gov-tab-btn ${activeTab === 'documents' ? 'active' : ''}`}
            onClick={() => setActiveTab('documents')}
          >
            Evidentiary Documents ({documents.length})
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'evidence' ? 'active' : ''}`}
            onClick={() => setActiveTab('evidence')}
          >
            Section 91 Requisitions ({evidenceRequests.length})
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'bail' ? 'active' : ''}`}
            onClick={() => setActiveTab('bail')}
          >
            Bail Docket
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'diary' ? 'active' : ''}`}
            onClick={() => setActiveTab('diary')}
          >
            Case Diary (Sec 172 CrPC)
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Audit Trail & Chain of Custody
          </button>
        </div>

        {/* Tab 1: Documents Table (40px row height) */}
        {activeTab === 'documents' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="text-label">Ingested Evidentiary Records</span>
              <span className="text-caption">Auto-redacted under Server-Side PII Governance</span>
            </div>
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Document ID</th>
                    <th>Record Classification</th>
                    <th>Version</th>
                    <th>Cryptographic SHA-256 Digest</th>
                    <th>Ledger Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((d) => (
                    <tr key={d.id}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{d.id}</td>
                      <td>{d.type}</td>
                      <td>v{d.version}</td>
                      <td>
                        <HashCell hash={d.hash} />
                      </td>
                      <td>
                        <StatusChip status={d.chain_status} />
                      </td>
                      <td>
                        <Link to={`/cases/${caseData.id}/documents/${d.id}`} className="btn btn-secondary btn-sm">
                          Inspect & Verify
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: Evidence Requisitions */}
        {activeTab === 'evidence' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)' }}>
              <span className="text-label">Section 91 CrPC Production Orders</span>
            </div>
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Requisition ID</th>
                    <th>Nodal Authority</th>
                    <th>Requested Material</th>
                    <th>Dispatched</th>
                    <th>Compliance Status</th>
                  </tr>
                </thead>
                <tbody>
                  {evidenceRequests.map((r) => (
                    <tr key={r.id}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{r.id}</td>
                      <td>{r.authority}</td>
                      <td>{r.req_type}</td>
                      <td>{r.requested_days_ago} days ago</td>
                      <td>
                        <StatusChip status={r.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 3: Bail Docket */}
        {activeTab === 'bail' && (
          <div className="card">
            <h3 className="card-title">Bail Application Record (Section 437/439 CrPC)</h3>
            <p className="text-body" style={{ color: 'var(--color-text-secondary)', marginBottom: '12px' }}>
              No active interim or regular bail petitions are currently marked as contested in this court docket.
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Link to="/defense" className="btn btn-secondary btn-sm">
                File Defense Application
              </Link>
            </div>
          </div>
        )}

        {/* Tab 4: Case Diary */}
        {activeTab === 'diary' && (
          <div className="card">
            <h3 className="card-title">Daily Police Diary of Proceedings (Section 172 CrPC)</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ padding: '10px', background: 'var(--color-surface-subtle)', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>
                  <span>Entry #14 · 02 September 2026, 14:15 IST</span>
                  <span className="mono-text">IO-S-RAO-4921</span>
                </div>
                <div className="text-body" style={{ fontSize: '13px' }}>
                  Examined witness at Cyber Crime Unit headquarters. Audio-visual recording executed and hash committed to ledger.
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Tab 5: Audit Trail */}
        {activeTab === 'audit' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--color-border)' }}>
              <h3 className="card-title" style={{ borderBottom: 'none', paddingBottom: 0, marginBottom: '4px' }}>
                Immutable Cryptographic Chain of Custody
              </h3>
              <span className="text-caption">
                Every access event, redaction check, and document version commit is cryptographically anchored via Hyperledger Fabric consensus quorum.
              </span>
            </div>

            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Block Height</th>
                    <th>Timestamp (IST)</th>
                    <th>Action / Event Classification</th>
                    <th>Submitting Authority</th>
                    <th>Transaction Hash</th>
                    <th>Consensus State</th>
                  </tr>
                </thead>
                <tbody>
                  {auditEvents.map((ev) => (
                    <tr key={ev.block_num}>
                      <td>
                        <span className="mono-text" style={{ fontWeight: 600, color: 'var(--color-primary)' }}>
                          #{ev.block_num}
                        </span>
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                        {ev.timestamp}
                      </td>
                      <td style={{ fontWeight: 500 }}>
                        {ev.event}
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                        {ev.authority}
                      </td>
                      <td>
                        <HashCell hash={ev.tx_hash} />
                      </td>
                      <td>
                        <StatusChip status="confirmed" label="Quorum Validated" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
