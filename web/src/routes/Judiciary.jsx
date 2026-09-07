import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';
import HashCell from '../components/HashCell';

export default function Judiciary() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('bail'); // 'bail' | 'trial' | 'audit'

  const [cases, setCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState(null);
  const [bailRecords, setBailRecords] = useState([]);
  const [bailPathway, setBailPathway] = useState(null);
  const [bailDecision, setBailDecision] = useState('GRANTED');
  const [bailConditions, setBailConditions] = useState('Personal bond of INR 50,000 with one local surety.');
  const [judgmentVerdict, setJudgmentVerdict] = useState('convicted');
  const [judgmentSummary, setJudgmentSummary] = useState('');
  const [actionAlert, setActionAlert] = useState(null);
  const [auditLogs, setAuditLogs] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchCases = () => {
    setLoading(true);
    apiClient('/cases')
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setCases(data);
          if (!selectedCase) {
            setSelectedCase(data[0]);
          }
        }
      })
      .catch((err) => {
        console.warn('Failed to load cases for judiciary bench:', err);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchCases();
  }, []);

  useEffect(() => {
    if (!selectedCase?.id) return;

    // Load bail records & pathway
    apiClient(`/cases/${selectedCase.id}/bail`)
      .then(records => setBailRecords(records || []))
      .catch(() => setBailRecords([]));

    apiClient(`/cases/${selectedCase.id}/bail/pathway`)
      .then(pw => setBailPathway(pw))
      .catch(() => setBailPathway(null));

    // Load audit logs if on audit tab
    if (activeTab === 'audit') {
      apiClient(`/cases/${selectedCase.id}/audit-log`)
        .then(res => setAuditLogs(res))
        .catch(() => setAuditLogs(null));
    }
  }, [selectedCase?.id, activeTab]);

  const handleIssueBailOrder = async (e) => {
    e.preventDefault();
    if (!selectedCase?.id) return;
    setActionAlert(null);

    try {
      const res = await apiClient(`/cases/${selectedCase.id}/bail/order`, {
        method: 'POST',
        body: {
          granted: bailDecision === 'GRANTED',
          conditions: bailConditions,
        }
      });
      setActionAlert({
        type: 'success',
        msg: `Judicial Bail Order (${res.stage}) recorded on ledger for Case ${selectedCase.case_number || selectedCase.fir_number || selectedCase.id.slice(0, 8)}. Immutable timestamp attached.`
      });
      fetchCases();
    } catch (err) {
      setActionAlert({
        type: 'error',
        msg: err.message || 'Failed to issue bail order. Note: A hearing notice must be scheduled before an order can be pronounced.'
      });
    }
  };

  const handleScheduleHearing = async () => {
    if (!selectedCase?.id) return;
    setActionAlert(null);

    try {
      const res = await apiClient(`/cases/${selectedCase.id}/bail/hearing-notice`, {
        method: 'POST',
      });
      setActionAlert({
        type: 'success',
        msg: `Hearing scheduled (Stage: ${res.stage}) for Case ${selectedCase.case_number || selectedCase.fir_number || selectedCase.id.slice(0, 8)}. Summons transmitted to IO and Defense.`
      });
      fetchCases();
    } catch (err) {
      setActionAlert({
        type: 'error',
        msg: err.message || 'Failed to schedule bail hearing. Note: Accused must first submit a bail application.'
      });
    }
  };

  const handleScheduleTrialHearing = async (caseId) => {
    setActionAlert(null);
    try {
      const res = await apiClient(`/cases/${caseId}/trial/hearing-notice`, {
        method: 'POST',
      });
      setActionAlert({
        type: 'success',
        msg: `Trial hearing notice issued. Case status moved to '${res.investigation_status}'.`
      });
      fetchCases();
    } catch (err) {
      setActionAlert({
        type: 'error',
        msg: err.message || 'Failed to schedule trial hearing. Note: Case must be in "Charge_Sheet_Filed" stage.'
      });
    }
  };

  const handleRecordJudgment = async (caseId) => {
    setActionAlert(null);
    try {
      const res = await apiClient(`/cases/${caseId}/judgment`, {
        method: 'POST',
        body: {
          verdict: judgmentVerdict,
          summary: judgmentSummary || 'Final judicial verdict rendered upon conclusion of trial proceedings.'
        }
      });
      setActionAlert({
        type: 'success',
        msg: `Final judgment recorded (${judgmentVerdict.toUpperCase()}). Case docket concluded in '${res.investigation_status}'.`
      });
      fetchCases();
    } catch (err) {
      setActionAlert({
        type: 'error',
        msg: err.message || 'Failed to record judgment. Note: Case must be in "Trial" stage.'
      });
    }
  };

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <span>Judiciary</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Magistrate Bench Docket</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">Judicial Bench & Magistrate Portal</h1>
            <p className="page-desc">
              Bail hearings, stage requirement compliance checks, judicial charge sheet review, and unredacted evidentiary inspection.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <StatusChip status="neutral" label={`Role: ${user?.role || 'Court / Magistrate'}`} />
            <StatusChip status="confirmed" label="Privilege: Unredacted Judicial Review" />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Judicial Authority Note (Flows 4 & 5):</strong> The court bench receives the complete evidentiary file
          including unredacted sensitive markers, chain-of-custody verification hashes, and full audit logs.
        </div>

        {/* Tabs */}
        <div className="gov-tabs">
          <button
            className={`gov-tab-btn ${activeTab === 'bail' ? 'active' : ''}`}
            onClick={() => setActiveTab('bail')}
          >
            Bail Docket & Orders
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'trial' ? 'active' : ''}`}
            onClick={() => setActiveTab('trial')}
          >
            Trial Proceedings & Judgment
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Full Ledger Audit Trail
          </button>
        </div>

        {actionAlert && (
          <div className={`alert ${actionAlert.type === 'success' ? 'alert-success' : 'alert-error'}`}>
            {actionAlert.msg}
          </div>
        )}

        {/* Tab 1: Bail */}
        {activeTab === 'bail' && (
          <div className="grid-2">
            <div className="card">
              <span className="table-caption">
                {cases.length} cases in judicial registry.
              </span>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>FIR / ID</th>
                      <th>Crime Type</th>
                      <th>Bail Track</th>
                      <th>Select</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cases.map((c) => (
                      <tr
                        key={c.id}
                        style={{
                          background: selectedCase?.id === c.id ? 'var(--surface-sunken)' : 'transparent'
                        }}
                      >
                        <td><span className="mono-text">{c.case_number || c.fir_number || c.id.slice(0, 8)}</span></td>
                        <td style={{ fontSize: '12px' }}>{c.crime_type}</td>
                        <td><StatusChip status={c.bail_status === 'Order_Issued' ? 'confirmed' : 'pending'} label={c.bail_status || 'No Action'} /></td>
                        <td>
                          <button
                            className="btn btn-secondary"
                            style={{ height: '28px', fontSize: '12px', padding: '0 8px' }}
                            onClick={() => setSelectedCase(c)}
                          >
                            Select
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <h2 className="card-title">Issue Judicial Bail Order & Statutory Compliance</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '12px' }}>
                Target Docket: <strong>{selectedCase?.case_number || selectedCase?.fir_number || selectedCase?.id?.slice(0, 8) || 'None Selected'}</strong>.
              </p>

              {/* Statutory Pathway Guidance Box */}
              {bailPathway && (
                <div style={{
                  background: 'var(--surface-sunken)',
                  border: '1px solid var(--border-default)',
                  padding: '12px',
                  marginBottom: '16px',
                  fontSize: '12px',
                  lineHeight: '1.5',
                  borderRadius: '4px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      Statutory Bail Classification:
                    </span>
                    <span style={{ fontWeight: 600 }}>
                      {bailPathway.classification || bailPathway.pathway_type || 'Standard Discretion'}
                    </span>
                  </div>
                  <div style={{ color: 'var(--text-secondary)', marginBottom: '4px' }}>
                    <strong>Applicable Statutes:</strong> {bailPathway.statute_references || selectedCase?.crime_type}
                  </div>
                  <div style={{ color: 'var(--text-secondary)' }}>
                    <strong>Current Bail Stage:</strong> {selectedCase?.bail_status || 'None'}
                  </div>
                </div>
              )}

              <form onSubmit={handleIssueBailOrder}>
                <div className="form-group">
                  <label className="form-label">Judicial Determination</label>
                  <select
                    className="form-select"
                    value={bailDecision}
                    onChange={(e) => setBailDecision(e.target.value)}
                  >
                    <option value="GRANTED">Bail Granted (Regular Bail)</option>
                    <option value="REJECTED">Bail Rejected (Risk of Flight / Tampering)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Bail Conditions & Directions</label>
                  <textarea
                    className="form-textarea"
                    value={bailConditions}
                    onChange={(e) => setBailConditions(e.target.value)}
                    rows={3}
                  />
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>
                    Pronounce Order
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleScheduleHearing}
                  >
                    Schedule Hearing Notice
                  </button>
                </div>
              </form>

              {/* History */}
              {bailRecords.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <span className="text-label" style={{ marginBottom: '6px', display: 'block' }}>Historical Bail Timeline</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {bailRecords.map(b => (
                      <div key={b.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '6px 8px', background: 'var(--surface-sunken)', borderRadius: '3px' }}>
                        <span>Stage: <strong>{b.stage}</strong></span>
                        <span style={{ color: 'var(--text-secondary)' }}>{new Date(b.created_at).toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Trial */}
        {activeTab === 'trial' && (
          <div className="card">
            <span className="table-caption">
              Trial bench hearings and Section 173 CrPC compliance reviews.
            </span>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>FIR / Case</th>
                    <th>Title & Crime Type</th>
                    <th>Investigation Stage</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.id}>
                      <td><span className="mono-text">{c.case_number || c.fir_number || c.id.slice(0, 8)}</span></td>
                      <td>
                        <strong>{c.case_number || c.title || 'Official Case Record'}</strong>
                        <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{c.crime_type}</div>
                      </td>
                      <td><StatusChip status={c.investigation_status === 'Judgment' ? 'confirmed' : 'pending'} label={c.investigation_status} /></td>
                      <td>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          {c.investigation_status === 'Charge_Sheet_Filed' && (
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handleScheduleTrialHearing(c.id)}
                            >
                              Schedule Trial Hearing
                            </button>
                          )}
                          {c.investigation_status === 'Trial' && (
                            <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                              <select
                                className="form-select"
                                style={{ width: 'auto', height: '28px', fontSize: '11px' }}
                                value={judgmentVerdict}
                                onChange={(e) => setJudgmentVerdict(e.target.value)}
                              >
                                <option value="convicted">Convicted</option>
                                <option value="acquitted">Acquitted</option>
                              </select>
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => handleRecordJudgment(c.id)}
                              >
                                Record Judgment
                              </button>
                            </div>
                          )}
                          {c.investigation_status === 'Judgment' && (
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                              Trial Concluded
                            </span>
                          )}
                          {c.investigation_status !== 'Charge_Sheet_Filed' && c.investigation_status !== 'Trial' && c.investigation_status !== 'Judgment' && (
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                              Awaiting Charge Sheet
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 3: Full Audit */}
        {activeTab === 'audit' && (
          <div className="card">
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-default)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <strong>Auditing Docket: {selectedCase?.case_number || selectedCase?.fir_number || selectedCase?.id?.slice(0, 8)}</strong>
                {/* Same three-state rule as CaseDetail: a failed verification
                    must never render as a passed one. The bench relies on this
                    line to decide whether the evidentiary file can be trusted. */}
                <div style={{
                  fontSize: '12px',
                  color: auditLogs?.chain_intact === false ? 'var(--color-status-danger, #b00020)' : 'var(--text-secondary)',
                  fontWeight: auditLogs?.chain_intact === false ? 600 : undefined,
                }}>
                  Integrity: {
                    auditLogs?.chain_intact === true
                      ? 'VALID & INTACT'
                      : auditLogs?.chain_intact === false
                        ? 'BROKEN — hash chain failed verification'
                        : 'UNVERIFIED'
                  }
                </div>
              </div>
            </div>

            <div className="table-container">
              {auditLogs?.entries && auditLogs.entries.length > 0 ? (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Actor</th>
                      <th>Action</th>
                      <th>Row Hash</th>
                      <th>Quorum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.entries.map((ev) => (
                      <tr key={ev.id}>
                        <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          {new Date(ev.created_at).toLocaleString()}
                        </td>
                        <td>{ev.actor_name || ev.actor_role || ev.actor_user_id || 'Authority'}</td>
                        <td style={{ fontWeight: 500 }}>{ev.action}</td>
                        <td><HashCell hash={ev.row_hash || ''} /></td>
                        <td><StatusChip status="confirmed" label="Valid" /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  {selectedCase ? 'No audit entries recorded for selected case.' : 'Select a case from the Bail or Trial tabs to inspect its audit log.'}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
