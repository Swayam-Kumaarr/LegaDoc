import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import StatusChip from '../components/StatusChip';
import HashCell from '../components/HashCell';
import ChainOfCustodyVisualizer from '../components/ChainOfCustodyVisualizer';

function useCaseResource(caseId, endpoint) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!caseId) return;
    let isMounted = true;
    setLoading(true);
    setError(null);
    apiClient(endpoint)
      .then((d) => { if (isMounted) setData(d); })
      .catch((e) => { if (isMounted) setError(e.message || 'Could not load this data.'); })
      .finally(() => { if (isMounted) setLoading(false); });
    return () => { isMounted = false; };
  }, [caseId, endpoint]);

  return { data, loading, error };
}

export default function CaseDetail() {
  const { id: caseId } = useParams();
  const [activeTab, setActiveTab] = useState('documents');

  const caseRes = useCaseResource(caseId, `/cases/${caseId}`);
  const docsRes = useCaseResource(caseId, `/cases/${caseId}/documents`);
  const evidenceRes = useCaseResource(caseId, `/cases/${caseId}/evidence-requests`);
  const bailRes = useCaseResource(caseId, `/cases/${caseId}/bail`);
  const diaryRes = useCaseResource(caseId, `/cases/${caseId}/case-diary`);
  const auditRes = useCaseResource(caseId, `/cases/${caseId}/audit-log`);

  const caseData = caseRes.data;
  const documents = docsRes.data || [];
  const evidenceRequests = evidenceRes.data || [];
  const bailRecords = bailRes.data || [];
  const diaryEntries = diaryRes.data || [];
  const auditLog = auditRes.data;

  if (caseRes.loading) {
    return <div className="page-container"><p className="text-body">Loading case…</p></div>;
  }
  if (caseRes.error || !caseData) {
    return (
      <div className="page-container">
        <div className="alert alert-error">{caseRes.error || 'Case not found, or you do not have access to it.'}</div>
      </div>
    );
  }

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <Link to="/cases">Case Registry</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Case Docket: {caseData.case_number}</span>
      </div>

      <div className="page-container">
        <div className="page-header" style={{ marginBottom: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
              <h1 className="text-display">Case {caseData.case_number}</h1>
              <StatusChip status={caseData.investigation_status} label={caseData.investigation_status.replace(/_/g, ' ')} />
            </div>
            <p className="page-desc">
              {caseData.court_level ? `Court: ${caseData.court_level} · ` : ''}
              Registered: {new Date(caseData.created_at).toLocaleDateString()}
            </p>
          </div>
          <Link to={`/cases/${caseData.id}/charge-sheet`} className="btn btn-primary btn-sm">
            Prosecutor Validation & Charge Sheet
          </Link>
        </div>

        <div className="card" style={{ padding: '12px 16px', marginBottom: '16px' }}>
          <div className="grid-2" style={{ margin: 0, gap: '12px' }}>
            <div>
              <div className="text-label" style={{ marginBottom: '2px' }}>Crime Type Classification</div>
              <div className="text-body">{caseData.crime_type}</div>
            </div>
            <div>
              <div className="text-label" style={{ marginBottom: '2px' }}>Bail Status</div>
              <div className="text-body">{caseData.bail_status ? caseData.bail_status.replace(/_/g, ' ') : 'Not applicable'}</div>
            </div>
          </div>
        </div>

        <div className="gov-tabs">
          <button className={`gov-tab-btn ${activeTab === 'documents' ? 'active' : ''}`} onClick={() => setActiveTab('documents')}>
            Evidentiary Documents ({documents.length})
          </button>
          <button className={`gov-tab-btn ${activeTab === 'evidence' ? 'active' : ''}`} onClick={() => setActiveTab('evidence')}>
            Section 91 Requisitions ({evidenceRequests.length})
          </button>
          <button className={`gov-tab-btn ${activeTab === 'bail' ? 'active' : ''}`} onClick={() => setActiveTab('bail')}>
            Bail Docket
          </button>
          <button className={`gov-tab-btn ${activeTab === 'diary' ? 'active' : ''}`} onClick={() => setActiveTab('diary')}>
            Case Diary (Sec 172 CrPC)
          </button>
          <button className={`gov-tab-btn ${activeTab === 'audit' ? 'active' : ''}`} onClick={() => setActiveTab('audit')}>
            Audit Trail & Chain of Custody
          </button>
        </div>

        {activeTab === 'documents' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)' }}>
              <span className="text-label">Ingested Evidentiary Records</span>
            </div>
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Type</th><th>Version</th><th>SHA-256 Digest</th><th>Status</th><th>Ledger Status</th><th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {docsRes.error ? (
                    <tr><td colSpan="6" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-status-error, #b91c1c)' }}>{docsRes.error}</td></tr>
                  ) : documents.length === 0 ? (
                    <tr><td colSpan="6" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-secondary)' }}>No documents uploaded to this case yet.</td></tr>
                  ) : (
                    documents.map((d) => (
                      <tr key={d.id}>
                        <td>{d.doc_type} <span className="text-caption">v{d.version}</span></td>
                        <td>v{d.version}</td>
                        <td><HashCell hash={d.doc_hash} /></td>
                        <td><StatusChip status={d.status} label={d.status.replace(/_/g, ' ')} /></td>
                        <td><StatusChip status={d.chain_status} label={d.chain_status.replace(/_/g, ' ')} /></td>
                        <td><Link to={`/cases/${caseData.id}/documents/${d.id}`} className="btn btn-secondary btn-sm">Inspect & Verify</Link></td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'evidence' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)' }}>
              <span className="text-label">Section 91 CrPC Production Orders</span>
            </div>
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead>
                  <tr><th>Requested Material</th><th>Dispatched</th><th>Compliance Status</th></tr>
                </thead>
                <tbody>
                  {evidenceRes.error ? (
                    <tr><td colSpan="3" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-status-error, #b91c1c)' }}>{evidenceRes.error}</td></tr>
                  ) : evidenceRequests.length === 0 ? (
                    <tr><td colSpan="3" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-secondary)' }}>No evidence requests dispatched for this case yet.</td></tr>
                  ) : (
                    evidenceRequests.map((r) => (
                      <tr key={r.id}>
                        <td>{r.doc_type_expected || 'General'}</td>
                        <td>{new Date(r.created_at).toLocaleDateString()}</td>
                        <td><StatusChip status={r.status} label={r.status.replace(/_/g, ' ')} /></td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'bail' && (
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)' }}>
              <span className="text-label">Bail Track (Section 437/439 CrPC)</span>
            </div>
            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              <table className="data-table">
                <thead><tr><th>Stage</th><th>Recorded</th></tr></thead>
                <tbody>
                  {bailRes.error ? (
                    <tr><td colSpan="2" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-status-error, #b91c1c)' }}>{bailRes.error}</td></tr>
                  ) : bailRecords.length === 0 ? (
                    <tr><td colSpan="2" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-secondary)' }}>No bail activity recorded for this case.</td></tr>
                  ) : (
                    bailRecords.map((r) => (
                      <tr key={r.id}>
                        <td><StatusChip status={r.stage} label={r.stage.replace(/_/g, ' ')} /></td>
                        <td style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>{new Date(r.created_at).toLocaleString()}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'diary' && (
          <div className="card">
            <h3 className="card-title">Daily Police Diary of Proceedings (Section 172 CrPC)</h3>
            {diaryRes.error ? (
              <p className="text-body" style={{ color: 'var(--color-status-error, #b91c1c)' }}>{diaryRes.error}</p>
            ) : diaryEntries.length === 0 ? (
              <p className="text-body" style={{ color: 'var(--color-text-secondary)' }}>No diary entries recorded for this case yet.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {diaryEntries.map((entry) => (
                  <div key={entry.id} style={{ padding: '10px', background: 'var(--color-surface-subtle)', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>
                      <span>{new Date(entry.created_at).toLocaleString()}</span>
                      <StatusChip status={entry.status} label={entry.status.replace(/_/g, ' ')} />
                    </div>
                    <div className="text-body" style={{ fontSize: '13px' }}>
                      {entry.status === 'ready' ? entry.text : '[Pending AI Parser review — visible only to the assigned IO/SHO until cleared]'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'audit' && (
          <>
          <div className="card" style={{ padding: '16px' }}>
            <h3 className="card-title">Verify Chain of Custody</h3>
            <ChainOfCustodyVisualizer events={auditEvents} />
          </div>

          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--color-border)' }}>
              <h3 className="card-title" style={{ borderBottom: 'none', paddingBottom: 0, marginBottom: '4px' }}>
                Tamper-Evident Audit Trail
              </h3>
              <span className="text-caption">
                {auditRes.loading ? 'Loading…' : auditLog ? (
                  auditLog.chain_intact
                    ? `Chain verified intact — ${auditLog.total_entries} entries`
                    : `⚠ CHAIN INTEGRITY FAILURE — ${auditLog.total_entries} entries, tampering detected`
                ) : ''}
              </span>
            </div>

            <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
              {auditRes.error ? (
                <p style={{ padding: '24px', textAlign: 'center', color: 'var(--color-status-error, #b91c1c)' }}>{auditRes.error}</p>
              ) : auditLog && auditLog.view_type === 'full' ? (
                <table className="data-table">
                  <thead>
                    <tr><th>Timestamp</th><th>Action</th><th>Row Hash</th><th>Prev Hash</th></tr>
                  </thead>
                  <tbody>
                    {(auditLog.entries || []).map((ev) => (
                      <tr key={ev.id}>
                        <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>{new Date(ev.created_at).toLocaleString()}</td>
                        <td style={{ fontWeight: 500 }}>{ev.action}</td>
                        <td><HashCell hash={ev.row_hash} /></td>
                        <td><HashCell hash={ev.prev_hash} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : auditLog && auditLog.view_type === 'summary' ? (
                <div style={{ padding: '16px' }}>
                  <p className="text-body" style={{ marginBottom: '10px' }}>
                    {auditLog.total_entries} total events between{' '}
                    {auditLog.first_entry_at ? new Date(auditLog.first_entry_at).toLocaleDateString() : '—'} and{' '}
                    {auditLog.last_entry_at ? new Date(auditLog.last_entry_at).toLocaleDateString() : '—'}.
                  </p>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {Object.entries(auditLog.action_counts || {}).map(([action, count]) => (
                      <span key={action} className="status-chip status-chip-neutral">{action}: {count}</span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
          </>
        )}
      </div>
    </div>
  );
}
