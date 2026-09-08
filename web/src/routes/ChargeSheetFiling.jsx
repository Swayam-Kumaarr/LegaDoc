import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import StatusChip from '../components/StatusChip';

export default function ChargeSheetFiling() {
  const { id: caseId } = useParams();

  const [prosecutorNotes, setProsecutorNotes] = useState('');
  const [filingStatus, setFilingStatus] = useState(null);
  const [missingItems, setMissingItems] = useState(null);
  const [isAttempting, setIsAttempting] = useState(false);

  const handleAttemptFiling = async (e) => {
    e.preventDefault();
    if (!caseId) {
      setFilingStatus({ type: 'error', msg: 'No case selected — open this page from a specific case.' });
      return;
    }
    setIsAttempting(true);
    setFilingStatus(null);
    setMissingItems(null);

    try {
      await apiClient(`/cases/${caseId}/file-charge-sheet`, {
        body: { notes: prosecutorNotes },
      });
      setFilingStatus({
        type: 'success',
        msg: 'Charge sheet filed. All mandatory stage requirements were verified against this case\'s actual documents and evidence requests.',
      });
    } catch (err) {
      if (err.status === 409 && err.detail && Array.isArray(err.detail.missing_items)) {
        setMissingItems(err.detail.missing_items);
        setFilingStatus({ type: 'error', msg: err.detail.message || 'Charge sheet cannot be filed: mandatory stage requirements remain incomplete.' });
      } else {
        setFilingStatus({ type: 'error', msg: err.message || 'Could not file the charge sheet.' });
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
              Filing is checked against this case's actual documents and evidence requests —
              the mandatory items for its crime type are defined server-side and verified live,
              not previewed here in advance.
            </p>
          </div>
          <StatusChip status="neutral" label="Role: Public Prosecutor" />
        </div>

        <div className="domain-notice">
          <strong>Flow 3 (AND-Join Validation):</strong> Filing requires every mandatory document
          and completed evidence request for this case's crime type. An incomplete case is
          rejected with the specific missing items listed below — not a guess made in the browser.
        </div>

        {filingStatus && (
          <div className={`alert ${filingStatus.type === 'success' ? 'alert-success' : 'alert-error'}`}>
            {filingStatus.msg}
          </div>
        )}

        {missingItems && missingItems.length > 0 && (
          <div className="card" style={{ borderLeft: '4px solid var(--status-danger-text)', marginBottom: '16px' }}>
            <h3 style={{ color: 'var(--status-danger-text)', fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
              Missing Mandatory Items (from the server, for this case)
            </h3>
            <ul style={{ paddingLeft: '20px', fontSize: '13px', color: 'var(--text-primary)' }}>
              {missingItems.map((m, idx) => (
                <li key={idx} style={{ marginBottom: '4px' }}>{m}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="card" style={{ maxWidth: '560px' }}>
          <h2 className="card-title">Submit Charge Sheet to Court</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
            If any mandatory requirement is missing, filing is rejected and the specific missing
            items are listed above — nothing is filed partially.
          </p>

          <form onSubmit={handleAttemptFiling}>
            <div className="form-group">
              <label className="form-label">Prosecution Submissions & Grounds</label>
              <textarea
                className="form-textarea"
                placeholder="State the statutory sections and evidentiary summary..."
                value={prosecutorNotes}
                onChange={(e) => setProsecutorNotes(e.target.value)}
                rows={5}
                required
              />
            </div>

            <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isAttempting}>
              {isAttempting ? 'Checking stage requirements…' : 'File Charge Sheet'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
