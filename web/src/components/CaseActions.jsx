import React, { useEffect, useState } from 'react';
import { apiClient } from '../api/client';

// The three case actions the demo story depends on that had no screen, and
// could only be driven with curl or Swagger (issue #89):
//   - SHO assigns an Investigating Officer    POST /cases/:id/assign-io
//   - IO / SHO raises a Section 91 requisition POST /cases/:id/evidence-requests
//   - IO / Duty Officer / SHO records an arrest POST /cases/:id/bail/arrest
//
// Each block is shown only to the roles its endpoint accepts, so the screen
// never offers a button that is guaranteed to come back 403.

const ACTIVE_BAIL_STAGES = new Set([
  'Arrested', 'Application_Filed', 'Hearing_Scheduled', 'Order_Issued', 'Surety_Registered',
]);

function errorText(err, fallback) {
  const d = err?.detail;
  if (typeof d === 'string') return d;
  return err?.message || fallback;
}

export default function CaseActions({ caseData, role, onChanged }) {
  const canAssign = role === 'sho';
  const canRequisition = role === 'io' || role === 'sho';
  const canArrest = role === 'io' || role === 'duty_officer' || role === 'sho';

  const [alert, setAlert] = useState(null);
  const [busy, setBusy] = useState(null);

  const [officers, setOfficers] = useState([]);
  const [officerId, setOfficerId] = useState('');

  const [targets, setTargets] = useState([]);
  const [targetId, setTargetId] = useState('');
  const [docType, setDocType] = useState('FSL Report');

  useEffect(() => {
    if (!canAssign) return;
    apiClient(`/cases/${caseData.id}/assignable-officers`)
      .then((list) => setOfficers(Array.isArray(list) ? list : []))
      .catch(() => setOfficers([]));
  }, [canAssign, caseData.id]);

  useEffect(() => {
    if (!canRequisition) return;
    apiClient('/evidence-requests/requisition-targets')
      .then((list) => setTargets(Array.isArray(list) ? list : []))
      .catch(() => setTargets([]));
  }, [canRequisition]);

  if (!canAssign && !canRequisition && !canArrest) return null;

  const run = async (key, fn, successMsg) => {
    setBusy(key);
    setAlert(null);
    try {
      await fn();
      setAlert({ type: 'success', msg: successMsg });
      onChanged?.();
    } catch (err) {
      setAlert({ type: 'error', msg: errorText(err, 'The action could not be completed.') });
    } finally {
      setBusy(null);
    }
  };

  const assignableOfficers = officers.filter((o) => !o.already_assigned);
  const arrestBlocked = ACTIVE_BAIL_STAGES.has(caseData.bail_status);

  const handleAssign = (e) => {
    e.preventDefault();
    const officer = officers.find((o) => o.id === officerId);
    run(
      'assign',
      () => apiClient(`/cases/${caseData.id}/assign-io`, { body: { io_user_id: officerId } }),
      `${officer ? officer.name : 'Officer'} assigned to investigate this case.`,
    ).then(() => {
      setOfficerId('');
      apiClient(`/cases/${caseData.id}/assignable-officers`).then(setOfficers).catch(() => {});
    });
  };

  const handleRequisition = (e) => {
    e.preventDefault();
    const target = targets.find((t) => t.id === targetId);
    run(
      'requisition',
      () => apiClient(`/cases/${caseData.id}/evidence-requests`, {
        body: { requested_org_id: targetId, doc_type_expected: docType.trim() || null },
      }),
      `Section 91 requisition sent to ${target ? target.name : 'the organisation'}.`,
    );
  };

  const handleArrest = () =>
    run(
      'arrest',
      () => apiClient(`/cases/${caseData.id}/bail/arrest`, { method: 'POST' }),
      'Arrest recorded. The bail track is now open for this case.',
    );

  return (
    <div className="card" style={{ padding: '14px 16px', marginBottom: '16px' }}>
      <div className="text-label" style={{ marginBottom: '10px' }}>Case Actions</div>

      {alert && (
        <div className={`alert ${alert.type === 'success' ? 'alert-success' : 'alert-error'}`} role="status">
          {alert.msg}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px' }}>
        {canAssign && (
          <form onSubmit={handleAssign}>
            <label className="form-label" htmlFor="assign-officer">Assign Investigating Officer</label>
            <select
              id="assign-officer"
              className="form-select"
              value={officerId}
              onChange={(e) => setOfficerId(e.target.value)}
            >
              <option value="">
                {assignableOfficers.length ? 'Select an officer…' : 'No unassigned officers available'}
              </option>
              {assignableOfficers.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}{o.designation ? ` — ${o.designation}` : ''}{o.org_name ? ` (${o.org_name})` : ''}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="btn btn-secondary"
              style={{ width: '100%', marginTop: '8px' }}
              disabled={!officerId || busy === 'assign'}
            >
              {busy === 'assign' ? 'Assigning…' : 'Assign Officer'}
            </button>
          </form>
        )}

        {canRequisition && (
          <form onSubmit={handleRequisition}>
            <label className="form-label" htmlFor="requisition-target">Raise Section 91 Requisition</label>
            <select
              id="requisition-target"
              className="form-select"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
            >
              <option value="">
                {targets.length ? 'Select an authority…' : 'No authorities registered'}
              </option>
              {targets.map((t) => (
                <option key={t.id} value={t.id}>{t.name} ({t.org_type.toUpperCase()})</option>
              ))}
            </select>
            <input
              type="text"
              className="form-input"
              style={{ marginTop: '8px' }}
              placeholder="Material required, e.g. FSL Report"
              aria-label="Material required"
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
            />
            <button
              type="submit"
              className="btn btn-secondary"
              style={{ width: '100%', marginTop: '8px' }}
              disabled={!targetId || busy === 'requisition'}
            >
              {busy === 'requisition' ? 'Sending…' : 'Send Requisition'}
            </button>
          </form>
        )}

        {canArrest && (
          <div>
            <div className="form-label">Record Arrest</div>
            <p className="text-caption" style={{ margin: '0 0 8px' }}>
              {arrestBlocked
                ? `Bail track already active (${caseData.bail_status.replace(/_/g, ' ')}).`
                : 'Opens the bail track so defence counsel can file an application.'}
            </p>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ width: '100%' }}
              onClick={handleArrest}
              disabled={arrestBlocked || busy === 'arrest'}
            >
              {busy === 'arrest' ? 'Recording…' : 'Record Arrest'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
