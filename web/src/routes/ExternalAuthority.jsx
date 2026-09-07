import React, { useState, useEffect } from 'react';
import { apiClient, apiUpload } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';

export default function ExternalAuthority() {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedReq, setSelectedReq] = useState(null);
  const [reportTitle, setReportTitle] = useState('');
  const [reportNotes, setReportNotes] = useState('');
  const [attachment, setAttachment] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sortOrder, setSortOrder] = useState('oldest');

  const fetchRequests = () => {
    setLoading(true);
    apiClient('/evidence-requests')
      .then((data) => {
        if (Array.isArray(data)) {
          setRequests(data);
        }
      })
      .catch((err) => {
        console.warn('Failed to load evidence requests:', err);
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchRequests();
  }, []);

  const sortedRequests = [...requests].sort((a, b) => {
    const dateA = new Date(a.created_at);
    const dateB = new Date(b.created_at);
    return sortOrder === 'oldest' ? dateA - dateB : dateB - dateA;
  });

  const handleSubmitReport = async (e) => {
    e.preventDefault();
    if (!selectedReq) return;
    if (!attachment) {
      setStatusMessage({
        type: 'error',
        msg: 'Please select a document file to attach.'
      });
      return;
    }

    setIsSubmitting(true);
    setStatusMessage(null);

    try {
      const formData = new FormData();
      formData.append('file', attachment);
      await apiUpload(`/evidence-requests/${selectedReq.id}/submit`, formData);

      setStatusMessage({
        type: 'success',
        msg: `Official report submitted against Requisition ${selectedReq.id}. Document signed and hashed directly to the Case ${selectedReq.case_id} ledger.`
      });
      setReportTitle('');
      setReportNotes('');
      setAttachment(null);
      setSelectedReq(null);
      fetchRequests();
    } catch (err) {
      setStatusMessage({
        type: 'error',
        msg: err.message || 'Failed to submit official report to backend.'
      });
    } finally {
      setIsSubmitting(false);
    }
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
            <StatusChip status="neutral" label={`Role: ${user?.role || 'Authority Staff'}`} />
            <StatusChip status="confirmed" label="Scoped Gateway: Active" />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Security Standard (Audit Section 1.8 & 2.0):</strong> Access is strictly restricted to the specific
          item requisitioned. External users have no access to the broader case docket. Inquiries are sorted
          <em> Oldest First</em> to eliminate operational bottlenecks.
        </div>

        {statusMessage && (
          <div className={`alert ${statusMessage.type === 'success' ? 'alert-success' : 'alert-error'}`}>
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
                  {sortedRequests.length} evidentiary requisitions assigned.
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

            {loading ? (
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>Loading assigned requisitions...</p>
            ) : sortedRequests.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                No open requisitions currently assigned.
              </div>
            ) : (
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
                      <span className="mono-text" style={{ fontSize: '11px' }}>{req.id?.slice(0, 8)}...</span>
                      <StatusChip status={req.status === 'completed' ? 'confirmed' : 'pending'} label={req.status} />
                    </div>
                    <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--color-text-primary)' }}>
                      {req.doc_type_expected}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                      Case ID: {req.case_id?.slice(0, 8)}... · Created: {new Date(req.created_at).toLocaleDateString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
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
                    {selectedReq.doc_type_expected}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    Case ID: {selectedReq.case_id} · Requisition ID: {selectedReq.id}
                  </div>
                  <div style={{ marginTop: '6px' }}>
                    <StatusChip status={selectedReq.status === 'completed' ? 'confirmed' : 'pending'} label={`Status: ${selectedReq.status}`} />
                  </div>
                </div>

                {selectedReq.status === 'completed' ? (
                  <div className="alert alert-success">
                    This requisition has already been fulfilled and sealed on the ledger.
                  </div>
                ) : (
                  <form onSubmit={handleSubmitReport}>
                    <div className="form-group">
                      <label className="form-label">Report Reference / Lab Docket Number</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="e.g. FSL-DL-2026-REPORT-941"
                        value={reportTitle}
                        onChange={(e) => setReportTitle(e.target.value)}
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Official Findings Summary (Section 293 CrPC)</label>
                      <textarea
                        className="form-textarea"
                        placeholder="Provide certified findings and methodology..."
                        value={reportNotes}
                        onChange={(e) => setReportNotes(e.target.value)}
                        rows={3}
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Signed Official Report Document (PDF/TIFF/JPEG)</label>
                      <input
                        type="file"
                        className="form-input"
                        onChange={(e) => setAttachment(e.target.files[0])}
                        required
                      />
                    </div>

                    <button
                      type="submit"
                      className="btn btn-primary"
                      style={{ width: '100%' }}
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? 'Submitting & Streaming to Vault...' : 'Submit Report & Commit to Chain of Custody'}
                    </button>
                  </form>
                )}
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
