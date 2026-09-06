import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';

export default function NeedsReviewQueue() {
  const { user } = useAuth();

  const [queueItems, setQueueItems] = useState([
    {
      id: 'DOC-REV-101',
      case_id: 'b1a2c3d4-0001-4000-8000-000000000001',
      case_number: 'CYB-2026-482910',
      doc_type: 'Witness Statement',
      uploaded_by: 'Officer Ramesh (IO)',
      failed_step: 'AI Confidence Below Threshold',
      confidence_score: 0.62,
      flagged_entity: 'PERSON (Suspect Co-Conspirator)',
      age_hours: 58,
      status: 'NEEDS_REVIEW'
    },
    {
      id: 'DOC-REV-102',
      case_id: 'b1a2c3d4-0002-4000-8000-000000000002',
      case_number: 'NDP-2026-119482',
      doc_type: 'Panchnama',
      uploaded_by: 'Duty Officer Verma',
      failed_step: 'OCR Handwritten Ambiguity',
      confidence_score: 0.54,
      flagged_entity: 'PHONE_NUMBER / AADHAAR',
      age_hours: 29,
      status: 'NEEDS_REVIEW'
    },
    {
      id: 'DOC-REV-103',
      case_id: 'b1a2c3d4-0001-4000-8000-000000000001',
      case_number: 'CYB-2026-482910',
      doc_type: 'Bank Statement',
      uploaded_by: 'HDFC Nodal Authority',
      failed_step: 'Complex Tabular PII',
      confidence_score: 0.71,
      flagged_entity: 'ACCOUNT_NUMBER',
      age_hours: 11,
      status: 'NEEDS_REVIEW'
    }
  ]);

  const [filterType, setFilterType] = useState('all');

  const filteredItems = queueItems.filter(item => {
    if (filterType === 'stuck_over_24h') return item.age_hours >= 24;
    if (filterType === 'low_confidence') return item.confidence_score < 0.65;
    return true;
  });

  const handleQuickDismiss = (docId) => {
    setQueueItems(queueItems.filter(i => i.id !== docId));
  };

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
            <StatusChip status="critical" label={`Oldest: ${Math.max(...queueItems.map(i => i.age_hours))}h SLA`} />
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
              {Math.max(...queueItems.map(i => i.age_hours))} hrs
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
