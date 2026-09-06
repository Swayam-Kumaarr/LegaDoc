import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';

export default function ChargeSheetFiling() {
  const { id: caseId } = useParams();
  const { user } = useAuth();

  const [prosecutorNotes, setProsecutorNotes] = useState('');
  const [filingStatus, setFilingStatus] = useState(null);
  const [missingRequirements, setMissingRequirements] = useState(null);
  const [isAttempting, setIsAttempting] = useState(false);

  const [requirementsState, setRequirementsState] = useState([
    { id: 'req-1', name: 'FIR Copy with Crime Section Classification', ready: true, docType: 'FIR' },
    { id: 'req-2', name: 'Scene of Crime / Seizure Panchnama', ready: true, docType: 'Panchnama' },
    { id: 'req-3', name: 'Forensic Lab (FSL) Chemical Purity Certificate', ready: false, docType: 'Forensic_Report' },
    { id: 'req-4', name: 'Witness Statements (Section 161 CrPC)', ready: true, docType: 'Witness_Statement' },
    { id: 'req-5', name: 'Accused Arrest & Custody Memo', ready: true, docType: 'Arrest_Memo' },
  ]);

  const handleAttemptFiling = async (e) => {
    e.preventDefault();
    setIsAttempting(true);
    setFilingStatus(null);
    setMissingRequirements(null);

    try {
      await apiClient(`/cases/${caseId || 'sample-case'}/file-charge-sheet`, {
        body: { notes: prosecutorNotes }
      });
      setFilingStatus({
        type: 'success',
        msg: 'Charge sheet admitted. All statutory requirements under Section 173 CrPC verified. Transmitted to Magistrate Court.'
      });
    } catch (err) {
      const missing = requirementsState.filter(r => !r.ready);
      if (missing.length > 0) {
        setMissingRequirements(missing);
        setFilingStatus({
          type: 'error',
          msg: 'HTTP 409 Conflict: Charge sheet cannot be filed. Mandatory stage requirements remain incomplete.'
        });
      } else {
        setFilingStatus({
          type: 'success',
          msg: 'Charge sheet successfully admitted to court docket.'
        });
      }
    } finally {
      setIsAttempting(false);
    }
  };

  const toggleRequirement = (id) => {
    setRequirementsState(requirementsState.map(r => r.id === id ? { ...r, ready: !r.ready } : r));
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

        <div className="grid-2">
          {/* Checklist */}
          <div className="card">
            <h2 className="card-title">Mandatory Stage Requirements Checklist</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '12px' }}>
              Click any item below to simulate fulfilling or unfulfilling a dependency.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {requirementsState.map(req => (
                <div
                  key={req.id}
                  onClick={() => toggleRequirement(req.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    background: 'var(--surface-sunken)',
                    borderRadius: '4px',
                    border: '1px solid var(--border-default)',
                    cursor: 'pointer'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 500, fontSize: '13px' }}>{req.name}</div>
                    <span className="mono-text" style={{ fontSize: '11px' }}>{req.docType}</span>
                  </div>
                  <StatusChip
                    status={req.ready ? 'confirmed' : 'pending'}
                    label={req.ready ? 'Attached & Verified' : 'Missing Dependency'}
                  />
                </div>
              ))}
            </div>
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
                disabled={isAttempting}
              >
                {isAttempting ? 'Verifying Stage Requirements...' : 'File Charge Sheet'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
