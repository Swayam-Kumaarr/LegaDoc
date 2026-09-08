import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import StatusChip from '../components/StatusChip';

export default function DefenseAccused() {
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState('');
  const [suretyName, setSuretyName] = useState('');
  const [suretyAmount, setSuretyAmount] = useState('');
  const [submissionAlert, setSubmissionAlert] = useState(null);
  const [bailRecords, setBailRecords] = useState([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [isSubmittingApplication, setIsSubmittingApplication] = useState(false);
  const [isSubmittingSurety, setIsSubmittingSurety] = useState(false);

  useEffect(() => {
    let isMounted = true;
    apiClient('/cases')
      .then((data) => { if (isMounted) setCases(data || []); })
      .catch(() => { if (isMounted) setCases([]); })
      .finally(() => { if (isMounted) setLoadingCases(false); });
    return () => { isMounted = false; };
  }, []);

  useEffect(() => {
    if (!selectedCaseId) { setBailRecords([]); return; }
    let isMounted = true;
    apiClient(`/cases/${selectedCaseId}/bail`)
      .then((data) => { if (isMounted) setBailRecords(data || []); })
      .catch(() => { if (isMounted) setBailRecords([]); });
    return () => { isMounted = false; };
  }, [selectedCaseId]);

  const refreshBailRecords = () => {
    if (!selectedCaseId) return;
    apiClient(`/cases/${selectedCaseId}/bail`).then(setBailRecords).catch(() => {});
  };

  const handleBailApplication = async (e) => {
    e.preventDefault();
    if (!selectedCaseId) return;
    setIsSubmittingApplication(true);
    setSubmissionAlert(null);
    try {
      await apiClient(`/cases/${selectedCaseId}/bail/application`, { body: {} });
      setSubmissionAlert({ type: 'success', msg: 'Bail application filed for this case.' });
      refreshBailRecords();
    } catch (err) {
      setSubmissionAlert({ type: 'error', msg: err.message || 'Could not file the bail application.' });
    } finally {
      setIsSubmittingApplication(false);
    }
  };

  const handleSuretySubmission = async (e) => {
    e.preventDefault();
    if (!selectedCaseId) return;
    setIsSubmittingSurety(true);
    setSubmissionAlert(null);
    try {
      await apiClient(`/cases/${selectedCaseId}/bail/surety`, {
        body: { surety_name: suretyName, bond_amount: Number(suretyAmount) },
      });
      setSubmissionAlert({ type: 'success', msg: `Surety undertaking by ${suretyName} registered for this case.` });
      setSuretyName('');
      setSuretyAmount('');
      refreshBailRecords();
    } catch (err) {
      setSubmissionAlert({ type: 'error', msg: err.message || 'Could not register the surety undertaking.' });
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
              Electronic submission gateway for bail petitions and surety undertakings, applied
              directly to the selected case's bail track.
            </p>
          </div>
          <StatusChip status="neutral" label="Role: Defense Counsel" />
        </div>

        <div className="domain-notice">
          <strong>Privacy Boundary:</strong> Defense counsel accounts have submission-only
          privileges. Prosecution investigative dossiers, confidential witness statements, and
          internal diaries are not accessible.
        </div>

        <div className="card" style={{ marginBottom: '16px' }}>
          <label className="form-label">Case</label>
          <select
            className="form-select"
            value={selectedCaseId}
            onChange={(e) => { setSelectedCaseId(e.target.value); setSubmissionAlert(null); }}
            disabled={loadingCases}
          >
            <option value="">{loadingCases ? 'Loading cases…' : 'Select a case…'}</option>
            {cases.map((c) => (
              <option key={c.id} value={c.id}>{c.case_number} — {c.crime_type}</option>
            ))}
          </select>
        </div>

        {submissionAlert && (
          <div className={`alert ${submissionAlert.type === 'success' ? 'alert-success' : 'alert-error'}`}>
            {submissionAlert.msg}
          </div>
        )}

        {selectedCaseId && (
          <>
            <div className="grid-2">
              <div className="card">
                <h2 className="card-title">File Bail Petition</h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
                  Moves this case's bail track from "Arrested" to "Application Filed" — only valid
                  once the accused has actually been arrested on this case.
                </p>
                <button
                  onClick={handleBailApplication}
                  className="btn btn-primary"
                  style={{ width: '100%' }}
                  disabled={isSubmittingApplication}
                >
                  {isSubmittingApplication ? 'Submitting…' : 'Submit Petition to Bench'}
                </button>
              </div>

              <div className="card">
                <h2 className="card-title">Register Surety Undertaking</h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
                  Only valid once the court has actually issued a bail order on this case.
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
                  <button type="submit" className="btn btn-secondary" style={{ width: '100%' }} disabled={isSubmittingSurety}>
                    {isSubmittingSurety ? 'Submitting…' : 'Submit Surety Undertaking'}
                  </button>
                </form>
              </div>
            </div>

            <div className="card" style={{ marginTop: '16px' }}>
              <span className="table-caption">Bail track history for this case.</span>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr><th>Stage</th><th>Recorded</th></tr>
                  </thead>
                  <tbody>
                    {bailRecords.length === 0 ? (
                      <tr><td colSpan="2" style={{ textAlign: 'center', padding: '24px', color: 'var(--color-text-secondary)' }}>No bail activity recorded for this case yet.</td></tr>
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
          </>
        )}
      </div>
    </div>
  );
}
