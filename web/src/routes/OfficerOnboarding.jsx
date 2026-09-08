import React, { useState, useEffect } from 'react';
import { apiClient, apiUpload } from '../api/client';
import StatusChip from '../components/StatusChip';

function formatError(err) {
  const detail = err?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    try {
      return JSON.stringify(detail);
    } catch {
      // fall through
    }
  }
  return err?.message || 'Request failed.';
}

const CREDENTIAL_DOC_TYPES = [
  { value: 'police_service_id', label: 'Police Service ID Card' },
  { value: 'bar_enrollment_certificate', label: 'Bar Council Enrollment Certificate' },
  { value: 'judicial_appointment_order', label: 'Judicial Appointment Order' },
  { value: 'institutional_authorization_letter', label: 'Institutional Authorization Letter' },
  { value: 'nabl_accreditation_certificate', label: 'NABL Accreditation Certificate' },
  { value: 'government_employee_id', label: 'Government Employee ID' },
];

const MATCH_STATUS_LABEL = {
  matched: { status: 'confirmed', label: 'Matched' },
  mismatch: { status: 'critical', label: 'Mismatch' },
  needs_review: { status: 'pending', label: 'Needs Review' },
};

export default function OfficerOnboarding() {
  const [statusFilter, setStatusFilter] = useState('pending_review');
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  const [roles, setRoles] = useState([]);
  const [orgs, setOrgs] = useState([]);

  const [showNewForm, setShowNewForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState('');
  const [newOrgId, setNewOrgId] = useState('');
  const [newDesignation, setNewDesignation] = useState('');
  const [newCredentialId, setNewCredentialId] = useState('');
  const [createAlert, setCreateAlert] = useState(null);

  const [docType, setDocType] = useState(CREDENTIAL_DOC_TYPES[0].value);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadAlert, setUploadAlert] = useState(null);
  const [uploading, setUploading] = useState(false);

  const [decisionAlert, setDecisionAlert] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const [approvedCredential, setApprovedCredential] = useState(null); // { email, temporary_password }

  const fetchApplications = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await apiClient(`/admin/applications?status_filter=${statusFilter}`);
      setApplications(Array.isArray(data) ? data : []);
    } catch (err) {
      setApplications([]);
      setLoadError(formatError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchApplications();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  useEffect(() => {
    apiClient('/admin/roles').then(setRoles).catch(() => setRoles([]));
    apiClient('/admin/orgs').then(setOrgs).catch(() => setOrgs([]));
  }, []);

  const selected = applications.find((a) => a.id === selectedId) || null;

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreateAlert(null);
    try {
      const created = await apiClient('/admin/applications', {
        body: {
          name: newName,
          email: newEmail,
          claimed_role: newRole,
          org_id: newOrgId,
          designation: newDesignation || null,
          claimed_credential_id: newCredentialId || null,
        },
      });
      setCreateAlert({ type: 'success', msg: `Application opened for ${created.name}. Now attach their credential document(s).` });
      setNewName('');
      setNewEmail('');
      setNewRole('');
      setNewOrgId('');
      setNewDesignation('');
      setNewCredentialId('');
      setShowNewForm(false);
      fetchApplications();
      setSelectedId(created.id);
    } catch (err) {
      setCreateAlert({ type: 'error', msg: `Could not open application: ${formatError(err)}` });
    }
  };

  const handleUploadDocument = async (e) => {
    e.preventDefault();
    if (!selected || !uploadFile) return;
    setUploading(true);
    setUploadAlert(null);
    const formData = new FormData();
    formData.append('doc_type', docType);
    formData.append('file', uploadFile);
    try {
      await apiUpload(`/admin/applications/${selected.id}/credential-documents`, formData);
      setUploadAlert({ type: 'success', msg: 'Document uploaded. OCR and field extraction are running — refresh in a few seconds to see the comparison.' });
      setUploadFile(null);
      fetchApplications();
    } catch (err) {
      setUploadAlert({ type: 'error', msg: `Upload failed: ${formatError(err)}` });
    } finally {
      setUploading(false);
    }
  };

  const handleApprove = async () => {
    if (!selected) return;
    setDecisionAlert(null);
    try {
      const res = await apiClient(`/admin/applications/${selected.id}/approve`, { method: 'POST' });
      setApprovedCredential(res);
      fetchApplications();
    } catch (err) {
      setDecisionAlert({ type: 'error', msg: `Could not approve: ${formatError(err)}` });
    }
  };

  const handleReject = async (e) => {
    e.preventDefault();
    if (!selected || !rejectReason.trim()) return;
    setDecisionAlert(null);
    try {
      await apiClient(`/admin/applications/${selected.id}/reject`, { body: { reason: rejectReason } });
      setDecisionAlert({ type: 'success', msg: 'Application rejected.' });
      setRejectReason('');
      setSelectedId(null);
      fetchApplications();
    } catch (err) {
      setDecisionAlert({ type: 'error', msg: `Could not reject: ${formatError(err)}` });
    }
  };

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <span>System Administration</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Officer & Authority Onboarding</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">Officer & Authority Onboarding</h1>
            <p className="page-desc">
              Verify credentials before provisioning an account. Every claimed identity is
              cross-checked against an uploaded proof document (OCR + extraction) — but the match
              result is advisory only; approval is always an explicit decision, never automatic.
            </p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowNewForm((v) => !v)}>
            {showNewForm ? 'Cancel' : '+ New Application'}
          </button>
        </div>

        <div className="domain-notice">
          <strong>Honest scope note:</strong> There is no accessible government API to verify a Bar
          Council enrollment number or a police service ID against a real registry. This flow
          documents and cross-checks a submitted credential scan — it does not claim official
          government verification.
        </div>

        {showNewForm && (
          <div className="card">
            <h2 className="card-title">Open New Application</h2>
            {createAlert && (
              <div className={`alert ${createAlert.type === 'success' ? 'alert-success' : 'alert-error'}`}>{createAlert.msg}</div>
            )}
            <form onSubmit={handleCreate}>
              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Full Name</label>
                  <input className="form-input" value={newName} onChange={(e) => setNewName(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Email</label>
                  <input type="email" className="form-input" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label className="form-label">Claimed Role</label>
                  <select className="form-select" value={newRole} onChange={(e) => setNewRole(e.target.value)} required>
                    <option value="">Select role...</option>
                    {roles.map((r) => (
                      <option key={r.code} value={r.code}>{r.name} ({r.code})</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Organization</label>
                  <select className="form-select" value={newOrgId} onChange={(e) => setNewOrgId(e.target.value)} required>
                    <option value="">Select organization...</option>
                    {orgs.map((o) => (
                      <option key={o.id} value={o.id}>{o.name}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Designation</label>
                  <input className="form-input" value={newDesignation} onChange={(e) => setNewDesignation(e.target.value)} placeholder="e.g. Inspector of Police" />
                </div>
                <div className="form-group">
                  <label className="form-label">Claimed Credential / Service ID</label>
                  <input
                    className="form-input"
                    value={newCredentialId}
                    onChange={(e) => setNewCredentialId(e.target.value)}
                    placeholder="e.g. DL-POL-4921 or Bar enrollment DL/1234/2015"
                  />
                </div>
              </div>
              <button type="submit" className="btn btn-primary">Open Application</button>
            </form>
          </div>
        )}

        <div className="gov-tabs">
          {['pending_review', 'approved', 'rejected'].map((s) => (
            <button
              key={s}
              className={`gov-tab-btn ${statusFilter === s ? 'active' : ''}`}
              onClick={() => { setStatusFilter(s); setSelectedId(null); }}
            >
              {s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())}
            </button>
          ))}
        </div>

        <div className="grid-2">
          <div className="card">
            <span className="table-caption">
              {loading ? 'Loading...' : `${applications.length} application${applications.length === 1 ? '' : 's'}.`}
            </span>
            {loadError && <div className="alert alert-error" style={{ marginTop: '8px' }}>{loadError}</div>}
            {!loadError && !loading && applications.length === 0 && (
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginTop: '8px' }}>Nothing here.</p>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '10px' }}>
              {applications.map((a) => (
                <div
                  key={a.id}
                  onClick={() => { setSelectedId(a.id); setApprovedCredential(null); setDecisionAlert(null); setUploadAlert(null); }}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '4px',
                    border: `1px solid ${selectedId === a.id ? 'var(--ink-900)' : 'var(--border-default)'}`,
                    background: selectedId === a.id ? 'var(--surface-sunken)' : 'var(--surface-panel)',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{a.name}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{a.email} · claiming {a.claimed_role}</div>
                  <div style={{ marginTop: '4px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {a.documents.length === 0 && <StatusChip status="neutral" label="No documents yet" />}
                    {a.documents.map((d) => (
                      <StatusChip
                        key={d.id}
                        status={(MATCH_STATUS_LABEL[d.match_status] || { status: 'neutral' }).status}
                        label={d.match_status ? (MATCH_STATUS_LABEL[d.match_status] || {}).label : d.status}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            {!selected ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Select an application to review.</p>
            ) : approvedCredential ? (
              <div>
                <StatusChip status="confirmed" label="Approved" />
                <h2 className="card-title" style={{ marginTop: '10px' }}>Account Created</h2>
                <div className="alert alert-warning">
                  This temporary password is shown <strong>exactly once</strong>. Communicate it to{' '}
                  {approvedCredential.email} out-of-band now — it cannot be retrieved again. They must
                  change it on first login.
                </div>
                <div style={{ background: 'var(--surface-sunken)', padding: '12px', borderRadius: '4px', fontFamily: 'var(--font-mono)', fontSize: '13px' }}>
                  <div>Email: {approvedCredential.email}</div>
                  <div>Temporary Password: <strong>{approvedCredential.temporary_password}</strong></div>
                </div>
              </div>
            ) : (
              <div>
                <h2 className="card-title">{selected.name}</h2>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                  {selected.email} · claiming <strong>{selected.claimed_role}</strong>
                  {selected.designation && <> · {selected.designation}</>}
                  <br />
                  Claimed credential ID: <span className="mono-text">{selected.claimed_credential_id || '—'}</span>
                </div>

                {selected.documents.length > 0 && (
                  <div style={{ marginBottom: '16px' }}>
                    <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: '6px' }}>Uploaded Documents</div>
                    {selected.documents.map((d) => (
                      <div key={d.id} style={{ border: '1px solid var(--border-default)', borderRadius: '4px', padding: '10px', marginBottom: '8px', fontSize: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <strong>{CREDENTIAL_DOC_TYPES.find((t) => t.value === d.doc_type)?.label || d.doc_type}</strong>
                          <StatusChip
                            status={(MATCH_STATUS_LABEL[d.match_status] || { status: 'neutral' }).status}
                            label={d.match_status ? (MATCH_STATUS_LABEL[d.match_status] || {}).label : d.status}
                          />
                        </div>
                        {d.extracted_fields && (
                          <div style={{ marginTop: '6px', color: 'var(--text-secondary)' }}>
                            <div>Extracted name: {d.extracted_fields.name || '(none found)'}</div>
                            <div>Extracted ID: {d.extracted_fields.id_number || '(none found)'}</div>
                            <div>Name similarity to claim: {Math.round((d.extracted_fields.name_similarity || 0) * 100)}%</div>
                          </div>
                        )}
                        {!d.extracted_fields && d.status === 'processing' && (
                          <div style={{ marginTop: '6px', color: 'var(--text-secondary)' }}>Still processing — refresh shortly.</div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {selected.status === 'pending_review' && (
                  <>
                    <form onSubmit={handleUploadDocument} style={{ marginBottom: '16px', borderTop: '1px solid var(--border-default)', paddingTop: '12px' }}>
                      <div style={{ fontWeight: 600, fontSize: '13px', marginBottom: '6px' }}>Attach Credential Document</div>
                      {uploadAlert && (
                        <div className={`alert ${uploadAlert.type === 'success' ? 'alert-success' : 'alert-error'}`} style={{ fontSize: '12px' }}>{uploadAlert.msg}</div>
                      )}
                      <div className="form-group">
                        <select className="form-select" value={docType} onChange={(e) => setDocType(e.target.value)}>
                          {CREDENTIAL_DOC_TYPES.map((t) => (
                            <option key={t.value} value={t.value}>{t.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="form-group">
                        <input type="file" className="form-input" onChange={(e) => setUploadFile(e.target.files[0])} required />
                      </div>
                      <button type="submit" className="btn btn-secondary" disabled={uploading}>
                        {uploading ? 'Uploading...' : 'Upload Document'}
                      </button>
                    </form>

                    {decisionAlert && (
                      <div className={`alert ${decisionAlert.type === 'success' ? 'alert-success' : 'alert-error'}`}>{decisionAlert.msg}</div>
                    )}

                    <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                      <button className="btn btn-primary" onClick={handleApprove} style={{ flex: 1 }}>
                        Approve & Create Account
                      </button>
                    </div>

                    <form onSubmit={handleReject} style={{ display: 'flex', gap: '8px' }}>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="Rejection reason..."
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                        style={{ flex: 1 }}
                      />
                      <button type="submit" className="btn btn-secondary" style={{ color: 'var(--status-rejected-text)' }}>
                        Reject
                      </button>
                    </form>
                  </>
                )}

                {selected.status === 'rejected' && selected.rejection_reason && (
                  <div className="alert alert-warning">Rejected: {selected.rejection_reason}</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
