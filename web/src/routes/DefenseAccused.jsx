import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';

export default function DefenseAccused() {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState('');
  const [accusedName, setAccusedName] = useState('');
  const [bailGrounds, setBailGrounds] = useState('');
  const [suretyName, setSuretyName] = useState('');
  const [suretyAmount, setSuretyAmount] = useState('50000');
  const [suretyProof, setSuretyProof] = useState(null);
  const [submissionAlert, setSubmissionAlert] = useState(null);
  const [isSubmittingBail, setIsSubmittingBail] = useState(false);
  const [isSubmittingSurety, setIsSubmittingSurety] = useState(false);
  const [mySubmissions, setMySubmissions] = useState([]);

  useEffect(() => {
    apiClient('/cases')
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setCases(data);
          setSelectedCaseId(data[0].id);
        }
      })
      .catch((err) => {
        console.warn('Failed to load cases:', err);
      });
  }, []);

  const handleBailApplication = async (e) => {
    e.preventDefault();
    if (!selectedCaseId) {
      setSubmissionAlert({
        type: 'error',
        msg: 'Please select a valid case to file the petition.'
      });
      return;
    }

    setIsSubmittingBail(true);
    setSubmissionAlert(null);

    try {
      const res = await apiClient(`/cases/${selectedCaseId}/bail/application`, {
        method: 'POST',
      });

      const newSub = {
        id: res.id ? res.id.slice(0, 8) : `BAIL-${Date.now()}`,
        type: 'Regular Bail Petition — Section 437/439 CrPC',
        case_id: selectedCaseId,
        filed_on: new Date().toISOString().split('T')[0],
        status: res.stage || 'Application_Filed',
        next_action: 'Awaiting judicial review and hearing notice from Bench'
      };
      setMySubmissions([newSub, ...mySubmissions]);
      setSubmissionAlert({
        type: 'success',
        msg: `Bail petition filed successfully for Case ID ${selectedCaseId}. Statutory filing receipt generated.`
      });
      setBailGrounds('');
    } catch (err) {
      setSubmissionAlert({
        type: 'error',
        msg: err.message || 'Failed to file bail application. Ensure accused is in "Arrested" status.'
      });
    } finally {
      setIsSubmittingBail(false);
    }
  };

  const handleSuretySubmission = async (e) => {
    e.preventDefault();
    if (!selectedCaseId) {
      setSubmissionAlert({
        type: 'error',
        msg: 'Please select a valid case to register surety.'
      });
      return;
    }

    setIsSubmittingSurety(true);
    setSubmissionAlert(null);

    try {
      const res = await apiClient(`/cases/${selectedCaseId}/bail/surety`, {
        method: 'POST',
        body: {
          surety_name: suretyName,
          bond_amount: parseFloat(suretyAmount) || 50000,
        }
      });

      setSubmissionAlert({
        type: 'success',
        msg: `Surety Bond undertaking of INR ${suretyAmount} by ${suretyName} submitted and committed to ledger. Stage: ${res.stage || 'Surety_Registered'}.`
      });
      setSuretyName('');
    } catch (err) {
      setSubmissionAlert({
        type: 'error',
        msg: err.message || 'Failed to register surety. Ensure bail has been granted ("Order_Issued").'
      });
    } finally {
      setIsSubmittingSurety(false);
    }
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
            <StatusChip status="neutral" label={`Role: ${user?.role || 'Defense Counsel'}`} />
            <StatusChip status="neutral" label="Access: Submission-Only" />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Privacy Boundary (Audit Section 1.8 & Domain 6):</strong> Defense counsel accounts have submission-only
          privileges. Prosecution investigative dossiers, confidential witness statements, and internal diaries are not accessible.
        </div>

        {submissionAlert && (
          <div className={`alert ${submissionAlert.type === 'success' ? 'alert-success' : 'alert-error'}`}>
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
                <label className="form-label">Case Identifier / Docket</label>
                {cases.length > 0 ? (
                  <select
                    className="form-select"
                    value={selectedCaseId}
                    onChange={(e) => setSelectedCaseId(e.target.value)}
                    required
                  >
                    {cases.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.fir_number || c.id?.slice(0, 8)} - {c.title} (Bail: {c.bail_status || 'None'})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Enter UUID of case"
                    value={selectedCaseId}
                    onChange={(e) => setSelectedCaseId(e.target.value)}
                    required
                  />
                )}
              </div>

              <div className="form-group">
                <label className="form-label">Statutory Petition Category</label>
                <select className="form-select" defaultValue="regular">
                  <option value="regular">Regular Bail Petition — Section 437/439 CrPC (Sec 480/483 BNSS)</option>
                  <option value="anticipatory">Anticipatory Bail Application — Section 438 CrPC (Sec 482 BNSS)</option>
                  <option value="interim">Interim Medical / Humanitarian Bail Application</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Accused Full Name</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Full legal name of accused"
                  value={accusedName}
                  onChange={(e) => setAccusedName(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Legal Grounds & Medical / Humanitarian Plea</label>
                <textarea
                  className="form-textarea"
                  placeholder="State legal merits, lack of flight risk, cooperation with investigation, or medical grounds..."
                  value={bailGrounds}
                  onChange={(e) => setBailGrounds(e.target.value)}
                  required
                  rows={4}
                />
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                style={{ width: '100%' }}
                disabled={isSubmittingBail}
              >
                {isSubmittingBail ? 'Submitting to Court Registry...' : 'Submit Petition to Bench'}
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
                <label className="form-label">Case Identifier / Docket</label>
                {cases.length > 0 ? (
                  <select
                    className="form-select"
                    value={selectedCaseId}
                    onChange={(e) => setSelectedCaseId(e.target.value)}
                    required
                  >
                    {cases.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.fir_number || c.id?.slice(0, 8)} - {c.title} (Bail: {c.bail_status || 'None'})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Enter UUID of case"
                    value={selectedCaseId}
                    onChange={(e) => setSelectedCaseId(e.target.value)}
                    required
                  />
                )}
              </div>

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
                />
              </div>

              <button
                type="submit"
                className="btn btn-secondary"
                style={{ width: '100%' }}
                disabled={isSubmittingSurety}
              >
                {isSubmittingSurety ? 'Registering Surety with Court...' : 'Submit Surety Undertaking'}
              </button>
            </form>
          </div>
        </div>

        {/* Submissions Docket */}
        {mySubmissions.length > 0 && (
          <div className="card" style={{ marginTop: '16px' }}>
            <span className="table-caption">
              Electronic receipts of petitions filed from this defense session.
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
                      <td><span className="mono-text">{sub.case_id?.slice(0, 8)}...</span></td>
                      <td>{sub.filed_on}</td>
                      <td><StatusChip status={sub.status} /></td>
                      <td style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>{sub.next_action}</td>
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
