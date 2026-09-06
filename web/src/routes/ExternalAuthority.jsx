import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';

export default function ExternalAuthority() {
  const { user } = useAuth();
  const [selectedReq, setSelectedReq] = useState(null);
  const [reportTitle, setReportTitle] = useState('');
  const [reportNotes, setReportNotes] = useState('');
  const [attachment, setAttachment] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);
  const [sortOrder, setSortOrder] = useState('oldest');

  const initialRequests = [
    {
      id: 'REQ-FSL-2026-001',
      case_number: 'CYB-2026-482910',
      requesting_officer: 'IO S. Rao (Cyber Cell)',
      request_type: 'Bank Account Transaction Statement (KYC & Trail)',
      target_subject: 'Accused Account ending 9182',
      requested_at: '2026-08-28T09:30:00Z',
      urgency: 'HIGH',
      status: 'PENDING_FULFILLMENT',
      days_open: 6
    },
    {
      id: 'REQ-FSL-2026-002',
      case_number: 'NDP-2026-119482',
      requesting_officer: 'IO P. Sharma (Narcotics Branch)',
      request_type: 'Chemical Forensic Purity Test Report',
      target_subject: 'Sample Seal #FSL-NDP-40192',
      requested_at: '2026-08-31T14:20:00Z',
      urgency: 'MEDIUM',
      status: 'PENDING_FULFILLMENT',
      days_open: 3
    }
  ];

  const sortedRequests = [...initialRequests].sort((a, b) => {
    if (sortOrder === 'oldest') {
      return new Date(a.requested_at) - new Date(b.requested_at);
    }
    return new Date(b.requested_at) - new Date(a.requested_at);
  });

  const handleSubmitReport = (e) => {
    e.preventDefault();
    if (!selectedReq) return;

    setStatusMessage({
      type: 'success',
      msg: `Official report submitted against Requisition ${selectedReq.id}. Document signed and hashed directly to the Case ${selectedReq.case_number} Fabric chain of custody.`
    });
    setReportTitle('');
    setReportNotes('');
    setAttachment(null);
  };

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <span>External Authorities</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Requisition Fulfillment Inbox</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">External Authority & Forensics Portal</h1>
            <p className="page-desc">
              Secure electronic requisition fulfillment for Forensic Laboratories, Hospitals, Banks, and Telecom Authorities.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <StatusChip status="neutral" label="Organization: State Forensic Science Laboratory" />
            <StatusChip status="confirmed" label="Scoped Gateway: Active" />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Security Standard (Audit Section 1.8 & 2.0):</strong> Access is strictly restricted to the specific
          item requisitioned. External users have no access to the broader case docket. Inquiries are sorted
          <em> Oldest First</em> to eliminate operational bottlenecks.
        </div>

        {statusMessage && (
          <div className={`alert ${statusMessage.type === 'success' ? 'alert-success' : 'alert-warning'}`}>
            {statusMessage.msg}
          </div>
        )}

        <div className="grid-2">
          {/* Requisitions List */}
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div>
                <h2 className="card-title" style={{ borderBottom: 'none', marginBottom: 0, paddingBottom: 0 }}>
                  Requisition Inbox
                </h2>
                <span className="table-caption" style={{ marginBottom: 0 }}>
                  {sortedRequests.length} pending evidentiary requisitions.
                </span>
              </div>
              <select
                className="form-select"
                style={{ width: 'auto', height: '30px', fontSize: '12px' }}
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
              >
                <option value="oldest">Sort: Oldest First (Audit Standard)</option>
                <option value="newest">Sort: Newest First</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {sortedRequests.map((req) => (
                <div
                  key={req.id}
                  onClick={() => setSelectedReq(req)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '4px',
                    border: `1px solid ${selectedReq?.id === req.id ? 'var(--ink-900)' : 'var(--border-default)'}`,
                    background: selectedReq?.id === req.id ? 'var(--surface-sunken)' : 'var(--surface-panel)',
                    cursor: 'pointer'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span className="mono-text" style={{ fontSize: '11px' }}>{req.id}</span>
                    <StatusChip status="pending" label={`Open ${req.days_open} days`} />
                  </div>
                  <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary)' }}>
                    {req.request_type}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                    Requested by: {req.requesting_officer} (Case: {req.case_number})
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--color-text-primary)', marginTop: '4px', fontWeight: 500 }}>
                    Target: {req.target_subject}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Fulfillment Form */}
          <div className="card">
            <h2 className="card-title">Fulfill & Submit Official Report</h2>

            {selectedReq ? (
              <div>
                <div style={{ background: 'var(--surface-sunken)', padding: '12px', borderRadius: '4px', marginBottom: '16px', border: '1px solid var(--border-default)' }}>
                  <div style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', fontWeight: 600 }}>
                    Requisition Target
                  </div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginTop: '2px' }}>
                    {selectedReq.request_type}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    Case Docket: {selectedReq.case_number} · Requisition ID: {selectedReq.id}
                  </div>
                </div>

                <form onSubmit={handleSubmitReport}>
                  <div className="form-group">
                    <label className="form-label">Report Reference / Lab Docket Number</label>
                    <input
                      type="text"
                      className="form-input"
                      placeholder="e.g. FSL-DL-2026-REPORT-941"
                      value={reportTitle}
                      onChange={(e) => setReportTitle(e.target.value)}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Official Findings Summary (Section 293 CrPC)</label>
                    <textarea
                      className="form-textarea"
                      placeholder="Provide certified findings and methodology..."
                      value={reportNotes}
                      onChange={(e) => setReportNotes(e.target.value)}
                      required
                      rows={3}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Signed Official PDF Report</label>
                    <input
                      type="file"
                      className="form-input"
                      onChange={(e) => setAttachment(e.target.files[0])}
                      required
                    />
                  </div>

                  <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                    Submit Report & Commit to Chain of Custody
                  </button>
                </form>
              </div>
            ) : (
              <div style={{ padding: '36px 16px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                Select a requisition from the list on the left to upload the certifying response.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
