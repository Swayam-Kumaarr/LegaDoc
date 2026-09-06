import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';

export default function DefenseAccused() {
  const { user } = useAuth();
  const [caseNumber, setCaseNumber] = useState('CYB-2026-482910');
  const [accusedName, setAccusedName] = useState('Vikram Sharma');
  const [bailGrounds, setBailGrounds] = useState('');
  const [suretyName, setSuretyName] = useState('');
  const [suretyAmount, setSuretyAmount] = useState('50000');
  const [suretyProof, setSuretyProof] = useState(null);
  const [submissionAlert, setSubmissionAlert] = useState(null);

  const [mySubmissions, setMySubmissions] = useState([
    {
      id: 'PET-2026-091',
      type: 'Regular Bail Application (Section 437/439 CrPC)',
      case_number: 'CYB-2026-482910',
      filed_on: '2026-09-02',
      status: 'HEARING_SCHEDULED',
      next_action: 'Hearing scheduled before Court No. 3 on 10 September 2026'
    }
  ]);

  const handleBailApplication = (e) => {
    e.preventDefault();
    const newSub = {
      id: `PET-2026-${Math.floor(100 + Math.random() * 900)}`,
      type: 'Bail Petition',
      case_number: caseNumber,
      filed_on: new Date().toISOString().split('T')[0],
      status: 'SUBMITTED_TO_COURT',
      next_action: 'Awaiting Court Docketing'
    };
    setMySubmissions([newSub, ...mySubmissions]);
    setSubmissionAlert({
      type: 'success',
      msg: `Bail petition filed for Case ${caseNumber}. Filing receipt generated.`
    });
    setBailGrounds('');
  };

  const handleSuretySubmission = (e) => {
    e.preventDefault();
    setSubmissionAlert({
      type: 'success',
      msg: `Surety Bond undertaking of INR ${suretyAmount} by ${suretyName} submitted for court verification.`
    });
    setSuretyName('');
  };

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <span>Defense Portal</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Submission Gateway</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">Defense Counsel & Accused Portal</h1>
            <p className="page-desc">
              Electronic submission gateway for bail petitions, surety undertakings, and appearance compliance.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <StatusChip status="neutral" label="Role: Defense Counsel" />
            <StatusChip status="neutral" label="Access: Submission-Only" />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Privacy Boundary (Audit Section 1.8 & Domain 6):</strong> Defense counsel accounts have submission-only
          privileges. Prosecution investigative dossiers, confidential witness statements, and internal diaries are not accessible.
        </div>

        {submissionAlert && (
          <div className={`alert ${submissionAlert.type === 'success' ? 'alert-success' : 'alert-warning'}`}>
            {submissionAlert.msg}
          </div>
        )}

        <div className="grid-2">
          {/* Bail Application */}
          <div className="card">
            <h2 className="card-title">File Bail Petition (Section 437 / 439 CrPC)</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
              Submit a formal application directly to the assigned court registry.
            </p>

            <form onSubmit={handleBailApplication}>
              <div className="form-group">
                <label className="form-label">Case Identifier / FIR Reference</label>
                <input
                  type="text"
                  className="form-input"
                  value={caseNumber}
                  onChange={(e) => setCaseNumber(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Statutory Petition Category</label>
                <select className="form-select" defaultValue="regular">
                  <option value="regular">Regular Bail Petition — Section 437/439 CrPC (Sec 480/483 BNSS)</option>
                  <option value="anticipatory">Anticipatory Bail Application — Section 438 CrPC (Sec 482 BNSS)</option>
                  <option value="interim">Interim Medical / Humanitarian Bail Application</option>
                  <option value="ndps">Special Bail Petition under NDPS Act § 37 (Commercial Contraband)</option>
                  <option value="pmla">Special Bail Petition under PMLA § 45 (Economic Offenses)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Accused Full Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={accusedName}
                  onChange={(e) => setAccusedName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Legal Grounds & Medical / Humanitarian Plea</label>
                <textarea
                  className="form-textarea"
                  placeholder="State the legal merits, lack of flight risk, cooperation with investigation, or medical grounds..."
                  value={bailGrounds}
                  onChange={(e) => setBailGrounds(e.target.value)}
                  required
                  rows={4}
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Submit Petition to Bench
              </button>
            </form>
          </div>

          {/* Surety Bond */}
          <div className="card">
            <h2 className="card-title">Register Surety Undertaking</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
              Submit surety documentation following a judicial bail grant order.
            </p>

            <form onSubmit={handleSuretySubmission}>
              <div className="form-group">
                <label className="form-label">Surety Guarantor Full Name</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Ramesh Chandra Sharma"
                  value={suretyName}
                  onChange={(e) => setSuretyName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Bond Amount (INR)</label>
                <input
                  type="number"
                  className="form-input"
                  value={suretyAmount}
                  onChange={(e) => setSuretyAmount(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Solvency Proof / Property Document PDF</label>
                <input
                  type="file"
                  className="form-input"
                  onChange={(e) => setSuretyProof(e.target.files[0])}
                  required
                />
              </div>

              <button type="submit" className="btn btn-secondary" style={{ width: '100%' }}>
                Submit Surety Undertaking
              </button>
            </form>
          </div>
        </div>

        {/* Submissions Docket */}
        <div className="card" style={{ marginTop: '16px' }}>
          <span className="table-caption">
            Electronic receipts of petitions filed from this defense account.
          </span>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Receipt ID</th>
                  <th>Petition Type</th>
                  <th>Case Docket</th>
                  <th>Date Filed</th>
                  <th>Status</th>
                  <th>Bench Directive</th>
                </tr>
              </thead>
              <tbody>
                {mySubmissions.map((sub) => (
                  <tr key={sub.id}>
                    <td><span className="mono-text">{sub.id}</span></td>
                    <td style={{ fontWeight: 500 }}>{sub.type}</td>
                    <td><span className="mono-text">{sub.case_number}</span></td>
                    <td>{sub.filed_on}</td>
                    <td><StatusChip status={sub.status} /></td>
                    <td style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>{sub.next_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
