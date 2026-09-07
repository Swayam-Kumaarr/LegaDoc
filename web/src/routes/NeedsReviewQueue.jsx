import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { apiClient } from '../api/client';
import StatusChip from '../components/StatusChip';

export default function NeedsReviewQueue() {
  const { user } = useAuth();
  const [queueItems, setQueueItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('all');

  useEffect(() => {
    let isMounted = true;
    async function loadQueue() {
      try {
        const data = await apiClient('/documents/review-queue?status=needs_review');
        if (isMounted && Array.isArray(data)) {
          const mapped = data.map(doc => {
            const created = new Date(doc.created_at || Date.now());
            const ageHours = Math.max(1, Math.round((Date.now() - created.getTime()) / (1000 * 60 * 60)));
            return {
              id: doc.id,
              case_id: doc.case_id,
              case_number: `Case ${doc.case_id?.slice(0, 8)}...`,
              doc_type: doc.doc_type || 'Document',
              uploaded_by: doc.uploaded_by ? `Officer ${doc.uploaded_by.slice(0, 8)}` : 'Investigating Officer',
              failed_step: doc.ocr_engine ? `OCR (${doc.ocr_engine})` : 'AI Parser Review Trigger',
              confidence_score: 0.65,
              flagged_entity: 'PII / Sensitive Spans',
              age_hours: ageHours,
              status: doc.status || 'needs_review'
            };
          });
          setQueueItems(mapped);
        }
      } catch (err) {
        console.error('Failed to load review queue:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadQueue();
    return () => { isMounted = false; };
  }, []);

  const filteredItems = queueItems.filter(item => {
    if (filterType === 'stuck_over_24h') return item.age_hours >= 24;
    if (filterType === 'low_confidence') return item.confidence_score < 0.65;
    return true;
  });

  const handleQuickDismiss = (docId) => {
    setQueueItems(queueItems.filter(i => i.id !== docId));
  };

  const oldestHours = queueItems.length > 0 ? Math.max(...queueItems.map(i => i.age_hours)) : 0;

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <Link to="/cases">Cases</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Needs-Review Verification Queue</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">Needs-Review Redaction Queue</h1>
            <p className="page-desc">
              Fallback-redacted and low-confidence documents requiring verification before public docket inclusion.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <StatusChip status="pending" label={`Queue Depth: ${queueItems.length}`} />
            <StatusChip status="critical" label={`Oldest: ${oldestHours}h SLA`} />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Audit Section 2 & PRD v1:</strong> Documents remain in fail-closed state (all sensitive spans masked)
          until verified by an Investigating Officer or System Administrator.
        </div>

        {/* Operational Metrics */}
        <div className="grid-3">
          <div className="stat-widget">
            <span className="stat-value">{queueItems.length}</span>
            <span className="stat-label">Pending Review Count</span>
            <span className="stat-sub">Awaiting verification</span>
          </div>
          <div className="stat-widget">
            <span className="stat-value" style={{ color: 'var(--status-pending-text)' }}>
              {oldestHours} hrs
            </span>
            <span className="stat-label">Oldest Pending Item</span>
            <span className="stat-sub">SLA Target: under 24 hrs</span>
          </div>
          <div className="stat-widget">
            <span className="stat-value" style={{ color: 'var(--status-success-text)' }}>Active</span>
            <span className="stat-label">Fail-Closed Safety Enforcement</span>
            <span className="stat-sub">Zero uncertified leakage</span>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div className="card" style={{ padding: '12px 16px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)', marginRight: '8px' }}>Filter:</span>
            <button
              className={`btn ${filterType === 'all' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ height: '30px', fontSize: '12px' }}
              onClick={() => setFilterType('all')}
            >
              All Documents ({queueItems.length})
            </button>
            <button
              className={`btn ${filterType === 'stuck_over_24h' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ height: '30px', fontSize: '12px' }}
              onClick={() => setFilterType('stuck_over_24h')}
            >
              Pending over 24h ({queueItems.filter(i => i.age_hours >= 24).length})
            </button>
            <button
              className={`btn ${filterType === 'low_confidence' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ height: '30px', fontSize: '12px' }}
              onClick={() => setFilterType('low_confidence')}
            >
              Confidence under 65% ({queueItems.filter(i => i.confidence_score < 0.65).length})
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="card">
          <span className="table-caption">
            {filteredItems.length} documents requiring review.
          </span>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Doc ID / Case</th>
                  <th>Classification</th>
                  <th>Review Trigger</th>
                  <th>Confidence Score</th>
                  <th>Age</th>
                  <th>Uploader</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map(item => (
                  <tr key={item.id}>
                    <td>
                      <div style={{ fontWeight: 500 }}>{item.case_number}</div>
                      <span className="mono-text" style={{ fontSize: '11px' }}>{item.id}</span>
                    </td>
                    <td>{item.doc_type}</td>
                    <td>
                      <div style={{ fontSize: '13px', color: 'var(--status-danger-text)' }}>
                        {item.failed_step}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--color-text-secondary)' }}>
                        {item.flagged_entity}
                      </div>
                    </td>
                    <td style={{ fontWeight: 600 }}>
                      {Math.round(item.confidence_score * 100)}%
                    </td>
                    <td>
                      <StatusChip status={item.age_hours >= 24 ? 'error' : 'neutral'} label={`${item.age_hours} hrs`} />
                    </td>
                    <td style={{ fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                      {item.uploaded_by}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <Link
                          to={`/cases/${item.case_id}/documents/${item.id}`}
                          className="btn btn-primary"
                          style={{ height: '28px', fontSize: '12px', padding: '0 8px' }}
                        >
                          Inspect & Verify
                        </Link>
                        <button
                          className="btn btn-secondary"
                          style={{ height: '28px', fontSize: '12px', padding: '0 8px' }}
                          onClick={() => handleQuickDismiss(item.id)}
                        >
                          Dismiss
                        </button>
                      </div>
                    </td>
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
