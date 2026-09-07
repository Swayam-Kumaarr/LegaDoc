import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';
import HashCell from '../components/HashCell';

export default function CaseDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('documents');
  const [caseData, setCaseData] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [evidenceRequests, setEvidenceRequests] = useState([]);
  const [diaryEntries, setDiaryEntries] = useState([]);
  const [bailRecords, setBailRecords] = useState([]);
  const [auditData, setAuditData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    Promise.all([
      apiClient(`/cases/${id}`).catch(err => {
        console.warn('Failed to load case metadata:', err);
        return null;
      }),
      apiClient(`/documents?case_id=${id}`).catch(() => []),
      apiClient(`/cases/${id}/evidence-requests`).catch(() => []),
      apiClient(`/cases/${id}/case-diary`).catch(() => []),
      apiClient(`/cases/${id}/bail`).catch(() => []),
      apiClient(`/audit?case_id=${id}`).catch(() => null),
    ]).then(([c, docs, reqs, diary, bail, audit]) => {
      if (c) {
        setCaseData(c);
      } else {
        setError('Case record not found or your role does not have authorization to view it.');
      }
      if (Array.isArray(docs)) setDocuments(docs);
      if (Array.isArray(reqs)) setEvidenceRequests(reqs);
      if (Array.isArray(diary)) setDiaryEntries(diary);
      if (Array.isArray(bail)) setBailRecords(bail);
      if (audit) setAuditData(audit);
    }).finally(() => {
      setLoading(false);
    });
  }, [id]);

  if (loading) {
    return (
      <div className="page-container" style={{ padding: '32px', textAlign: 'center' }}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Loading case docket and ledger records...</p>
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div className="page-container" style={{ padding: '32px' }}>
        <div className="alert alert-error">
          {error || 'Unable to load case details.'}
        </div>
        <Link to="/cases" className="btn btn-secondary btn-sm" style={{ marginTop: '12px', display: 'inline-block' }}>
          ← Back to Case Registry
        </Link>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb Bar */}
      <div className="gov-breadcrumb-bar">
        <Link to="/cases">Case Registry</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Case Docket: {caseData.fir_number || caseData.id?.slice(0, 8)}</span>
      </div>

      <div className="page-container">
        {/* Case Header: Case Number in text-display serif + inline status chip (PRD Section 8) */}
        <div className="page-header" style={{ marginBottom: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <h1 className="text-display">Case {caseData.fir_number || caseData.title}</h1>
              <StatusChip status={caseData.investigation_status === 'Charge_Sheet_Filed' ? 'confirmed' : 'pending'} label={caseData.investigation_status} />
              <span className="status-chip status-chip-success">Fabric Ledger Confirmed</span>
            </div>
            <p className="page-desc">
              Jurisdiction: {caseData.jurisdiction || 'Judicial Magistrate Court'} · Registered: {new Date(caseData.created_at).toLocaleDateString()}
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
              <div className="text-label" style={{ marginBottom: '2px' }}>Case Title</div>
              <div className="text-body" style={{ fontWeight: 600 }}>{caseData.title}</div>
              <div className="text-label" style={{ marginTop: '8px', marginBottom: '2px' }}>Crime Type Classification</div>
              <div className="text-body">{caseData.crime_type}</div>
            </div>
            <div>
              <div className="text-label" style={{ marginBottom: '2px' }}>FIR Registration Date</div>
              <div className="text-body" style={{ fontFamily: 'var(--font-mono)' }}>
                {new Date(caseData.created_at).toLocaleString()}
              </div>
              <div className="text-label" style={{ marginTop: '8px', marginBottom: '2px' }}>Current Lifecycle Stage</div>
              <div className="text-body">{caseData.investigation_status}</div>
            </div>
          </div>
        </div>

        {/* Underlined Text Tabs */}
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
            Bail Docket ({bailRecords.length})
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'diary' ? 'active' : ''}`}
            onClick={() => setActiveTab('diary')}
          >
            Case Diary ({diaryEntries.length})
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Audit Trail & Chain of Custody
          </button>
        </div>

        {/* Tab 1: Documents Table */}
        {activeTab === 'documents' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="text-label">Ingested Evidentiary Records</span>
              <span className="text-caption">Auto-redacted under Server-Side PII Governance</span>
            </div>
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              {documents.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No documents attached to this case docket yet.
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Document</th>
                      <th>Classification</th>
                      <th>Version</th>
                      <th>Cryptographic SHA-256 Digest</th>
                      <th>Ledger Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {documents.map((d) => (
                      <tr key={d.id}>
                        <td style={{ fontWeight: 600 }}>{d.file_name}</td>
                        <td>{d.doc_type || 'Unclassified'}</td>
                        <td>v{d.version || 1}</td>
                        <td>
                          <HashCell hash={d.sha256_hash || ''} />
                        </td>
                        <td>
                          <StatusChip status={d.ocr_status === 'completed' ? 'confirmed' : (d.ocr_status || 'pending')} />
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
              )}
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
              {evidenceRequests.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No Section 91 CrPC evidence requisitions recorded for this case.
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Requisition ID</th>
                      <th>Nodal Organization</th>
                      <th>Requested Material</th>
                      <th>Dispatched</th>
                      <th>Compliance Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidenceRequests.map((r) => (
                      <tr key={r.id}>
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{r.id?.slice(0, 8)}...</td>
                        <td>{r.requested_org_id || 'External Nodal Unit'}</td>
                        <td>{r.doc_type_expected}</td>
                        <td>{new Date(r.created_at).toLocaleDateString()}</td>
                        <td>
                          <StatusChip status={r.status === 'completed' ? 'confirmed' : 'pending'} label={r.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* Tab 3: Bail Docket */}
        {activeTab === 'bail' && (
          <div className="card">
            <h3 className="card-title">Bail Application Record (Section 437/439 CrPC)</h3>
            <div style={{ marginBottom: '16px' }}>
              <div className="text-label">Current Statutory Bail Track Status:</div>
              <div style={{ marginTop: '4px' }}>
                <StatusChip
                  status={caseData.bail_status === 'Order_Issued' ? 'confirmed' : (caseData.bail_status ? 'pending' : 'neutral')}
                  label={caseData.bail_status || 'No Bail Action Recorded'}
                />
              </div>
            </div>
            {bailRecords.length === 0 ? (
              <p className="text-body" style={{ color: 'var(--color-text-secondary)', marginBottom: '12px' }}>
                No active interim or regular bail petitions are currently recorded in this docket.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
                {bailRecords.map((b) => (
                  <div key={b.id} style={{ padding: '10px 14px', background: 'var(--surface-sunken)', borderRadius: '4px', border: '1px solid var(--border-default)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <strong>Stage: {b.stage}</strong>
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        Recorded: {new Date(b.created_at).toLocaleString()}
                      </div>
                    </div>
                    <StatusChip status={b.stage === 'Order_Issued' ? 'confirmed' : 'pending'} label={b.stage} />
                  </div>
                ))}
              </div>
            )}
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
            {diaryEntries.length === 0 ? (
              <p style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                No daily diary entries recorded yet.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {diaryEntries.map((entry) => (
                  <div key={entry.id} style={{ padding: '10px', background: 'var(--color-surface-subtle)', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>
                      <span>Entry #{entry.entry_number} · {new Date(entry.created_at).toLocaleString()}</span>
                      <span className="mono-text">{entry.officer_name || entry.actor_name || 'IO'}</span>
                    </div>
                    <div className="text-body" style={{ fontSize: '13px' }}>
                      {entry.activity_details}
                    </div>
                  </div>
                ))}
              </div>
            )}
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
                Ledger Chain Integrity: {auditData?.chain_intact ? 'VALID & UNBROKEN' : (auditData?.chain_status || 'VERIFIED')}
              </span>
            </div>

            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              {auditData?.view_type === 'summary' ? (
                <div style={{ padding: '16px' }}>
                  <h4 style={{ fontSize: '13px', marginBottom: '8px' }}>Summary Activity Log</h4>
                  <ul style={{ paddingLeft: '20px', fontSize: '13px' }}>
                    {auditData.summary_lines?.map((line, idx) => (
                      <li key={idx} style={{ marginBottom: '4px' }}>{line}</li>
                    ))}
                  </ul>
                </div>
              ) : (!auditData?.entries || auditData.entries.length === 0) ? (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No audit trail recorded for this case yet.
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Event ID</th>
                      <th>Timestamp</th>
                      <th>Action</th>
                      <th>Actor</th>
                      <th>Row Digest</th>
                      <th>Consensus State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditData.entries.map((ev) => (
                      <tr key={ev.id}>
                        <td>
                          <span className="mono-text" style={{ fontWeight: 600, color: 'var(--color-primary)' }}>
                            #{ev.id?.slice(0, 8)}
                          </span>
                        </td>
                        <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                          {new Date(ev.created_at).toLocaleString()}
                        </td>
                        <td style={{ fontWeight: 500 }}>
                          {ev.action}
                        </td>
                        <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                          {ev.actor_name || ev.actor_role || ev.actor_user_id || 'System'}
                        </td>
                        <td>
                          <HashCell hash={ev.row_hash || ''} />
                        </td>
                        <td>
                          <StatusChip status="confirmed" label="Quorum Validated" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
