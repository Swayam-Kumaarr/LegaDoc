import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';

export default function ChargeSheetFiling() {
  const { id: caseId } = useParams();
  const { user } = useAuth();

  const [currentCase, setCurrentCase] = useState(null);
  const [caseDocs, setCaseDocs] = useState([]);
  const [loadingCase, setLoadingCase] = useState(false);
  const [prosecutorNotes, setProsecutorNotes] = useState('');
  const [filingStatus, setFilingStatus] = useState(null);
  const [missingRequirements, setMissingRequirements] = useState(null);
  const [isAttempting, setIsAttempting] = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoadingCase(true);
    Promise.all([
      apiClient(`/cases/${caseId}`).catch(() => null),
      apiClient(`/documents?case_id=${caseId}`).catch(() => [])
    ]).then(([c, docs]) => {
      if (c) setCurrentCase(c);
      if (docs) setCaseDocs(docs);
    }).finally(() => {
      setLoadingCase(false);
    });
  }, [caseId]);

  const handleAttemptFiling = async (e) => {
    e.preventDefault();
    if (!caseId) {
      setFilingStatus({
        type: 'error',
        msg: 'No case ID specified. Please access this page from a specific case.'
      });
      return;
    }

    setIsAttempting(true);
    setFilingStatus(null);
    setMissingRequirements(null);

    try {
      const updatedCase = await apiClient(`/cases/${caseId}/file-charge-sheet`, {
        method: 'POST'
      });
      setCurrentCase(updatedCase);
      setFilingStatus({
        type: 'success',
        msg: 'Charge sheet admitted. All statutory requirements under Section 173 CrPC / BNSS verified. Transmitted to Magistrate Court docket.'
      });
    } catch (err) {
      const missing = err.data?.detail?.missing_items;
      if (missing && Array.isArray(missing)) {
        setMissingRequirements(missing.map((item, idx) => ({ id: `req-${idx}`, name: item })));
        setFilingStatus({
          type: 'error',
          msg: `HTTP 409 Conflict: ${err.data?.detail?.message || 'Charge sheet cannot be filed. Mandatory stage requirements remain incomplete.'}`
        });
      } else {
        setFilingStatus({
          type: 'error',
          msg: err.message || 'Charge sheet filing failed. Please check server logs.'
        });
      }
    } finally {
      setIsAttempting(false);
    }
  };

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <Link to="/cases">Cases</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Prosecutor Charge Sheet Review</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">Charge Sheet Filing (Section 173 CrPC / BNSS)</h1>
            <p className="page-desc">
              Prosecutorial validation against mandatory crime-specific Stage Requirements before court docketing.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <StatusChip status="neutral" label="Role: Public Prosecutor" />
            <StatusChip status="confirmed" label="Stage Requirements Engine: Active" />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Flow 3 (AND-Join Validation):</strong> Statutory filing requires completion of all parallel
          evidentiary requirements on the Fabric ledger. Premature filing is structurally rejected with HTTP 409.
        </div>

        {filingStatus && (
          <div className={`alert ${filingStatus.type === 'success' ? 'alert-success' : 'alert-error'}`}>
            {filingStatus.msg}
          </div>
        )}

        {missingRequirements && (
          <div className="card" style={{ borderLeft: '4px solid var(--status-danger-text)', marginBottom: '16px' }}>
            <h3 style={{ color: 'var(--status-danger-text)', fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
              Missing Mandatory Evidentiary Items (HTTP 409 Conflict)
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
              The following stage requirements must be fulfilled on the ledger before judicial filing can proceed:
            </p>
            <ul style={{ paddingLeft: '20px', fontSize: '13px', color: 'var(--text-primary)' }}>
              {missingRequirements.map(m => (
                <li key={m.id} style={{ marginBottom: '4px' }}>
                  <strong>{m.name}</strong> ({m.docType}) — Awaiting external authority report
                </li>
              ))}
            </ul>
          </div>
        )}

        {currentCase && (
          <div className="card" style={{ marginBottom: '16px', background: 'var(--surface-sunken)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong style={{ fontSize: '15px' }}>Case {currentCase.case_number || currentCase.id?.slice(0, 8)}</strong>
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Case Number: <span className="mono-text">{currentCase.case_number}</span> | Crime Type: <strong>{currentCase.crime_type}</strong> | Jurisdiction: {currentCase.court_level || 'Magistrate Court'}
                </div>
              </div>
              <StatusChip
                status={currentCase.investigation_status === 'Charge_Sheet_Filed' ? 'confirmed' : 'pending'}
                label={currentCase.investigation_status}
              />
            </div>
          </div>
        )}

        <div className="grid-2">
          {/* Live Evidentiary Dossier */}
          <div className="card">
            <h2 className="card-title">Case Evidentiary Dossier</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '12px' }}>
              Documents and evidence records attached to this case ledger:
            </p>

            {loadingCase ? (
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Loading case dossier...</p>
            ) : caseDocs.length === 0 ? (
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                No documents currently attached to this case. Mandatory stage requirements will fail AND-join validation.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {caseDocs.map(doc => (
                  <div
                    key={doc.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      background: 'var(--surface-sunken)',
                      borderRadius: '4px',
                      border: '1px solid var(--border-default)',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 500, fontSize: '13px' }}>{doc.file_name}</div>
                      <span className="mono-text" style={{ fontSize: '11px' }}>{doc.doc_type || 'Unclassified'}</span>
                    </div>
                    <StatusChip
                      status={doc.ocr_status === 'completed' ? 'confirmed' : 'pending'}
                      label={doc.ocr_status || 'uploaded'}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Form */}
          <div className="card">
            <h2 className="card-title">Submit Charge Sheet to Court</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
              Once all prerequisites pass, the digital dossier is transmitted to the Magistrate Court.
            </p>

            <form onSubmit={handleAttemptFiling}>
              <div className="form-group">
                <label className="form-label">Prosecution Submissions & Grounds</label>
                <textarea
                  className="form-textarea"
                  placeholder="State the statutory sections under Bharatiya Nyaya Sanhita (BNS) and evidentiary summary..."
                  value={prosecutorNotes}
                  onChange={(e) => setProsecutorNotes(e.target.value)}
                  rows={5}
                  required
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%' }}
                disabled={isAttempting || currentCase?.investigation_status === 'Charge_Sheet_Filed'}
              >
                {isAttempting
                  ? 'Verifying Stage Requirements...'
                  : currentCase?.investigation_status === 'Charge_Sheet_Filed'
                  ? 'Charge Sheet Already Filed'
                  : 'File Charge Sheet'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
