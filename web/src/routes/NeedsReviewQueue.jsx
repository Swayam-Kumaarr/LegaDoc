import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import StatusChip from '../components/StatusChip';
import HashCell from '../components/HashCell';

export default function NeedsReviewQueue() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await apiClient('/documents?status=needs_review');
        if (isMounted) setItems(data || []);
      } catch (e) {
        if (isMounted) setError(e.message || 'Could not load the review queue.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    load();
    return () => { isMounted = false; };
  }, []);

  const ageHours = (createdAt) => Math.max(0, Math.round((Date.now() - new Date(createdAt).getTime()) / (1000 * 60 * 60)));

  // "456 hrs" is not a length of time anyone reads as nineteen days. Hours
  // stay for the first day, where they are what a reviewer is judging
  // against; past that the unit changes to days, then months.
  const ageLabel = (createdAt) => {
    const hrs = ageHours(createdAt);
    if (hrs < 24) return `${hrs} hr${hrs === 1 ? '' : 's'}`;
    const days = Math.floor(hrs / 24);
    if (days < 31) return `${days} day${days === 1 ? '' : 's'}`;
    const months = Math.floor(days / 30);
    const rem = days % 30;
    return rem ? `${months} mo ${rem}d` : `${months} month${months === 1 ? '' : 's'}`;
  };
  const oldestItem = items.length
    ? items.reduce((a, b) => (ageHours(a.created_at) >= ageHours(b.created_at) ? a : b))
    : null;

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
              Documents the AI Parser flagged with low-confidence tagging or couldn't process at
              all — held in fail-closed state until a human confirms them.
            </p>
          </div>
          {!loading && !error && (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <StatusChip status="pending" label={`Queue Depth: ${items.length}`} />
              {oldestItem && <StatusChip status="critical" label={`Oldest: ${ageLabel(oldestItem.created_at)}`} />}
            </div>
          )}
        </div>

        <div className="domain-notice">
          <strong>Fail-Closed Safety:</strong> Documents remain in this state (all sensitive spans
          masked) until an Investigating Officer or Config Admin reviews them — this queue is the
          only way to clear that state.
        </div>

        <div className="card">
          <span className="table-caption">
            {error ? '' : loading ? 'Loading…' : `${items.length} document${items.length === 1 ? '' : 's'} requiring review.`}
          </span>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Type</th>
                  <th>Chain Status</th>
                  <th>Doc Hash</th>
                  <th>Age</th>
                  <th style={{ textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {error ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '32px', color: 'var(--color-status-error, #b91c1c)' }}>
                      {error.includes('permission') || error.includes('403')
                        ? "Your role doesn't have access to the review queue — this is restricted to Investigating Officers and Config Admins."
                        : error}
                    </td>
                  </tr>
                ) : loading ? (
                  <tr><td colSpan="6" style={{ textAlign: 'center', padding: '32px', color: 'var(--color-text-secondary)' }}>Loading…</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan="6" style={{ textAlign: 'center', padding: '32px', color: 'var(--color-text-secondary)' }}>Nothing needs review right now.</td></tr>
                ) : (
                  items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <span className="mono-text" style={{ fontSize: '11px' }}>{item.id}</span>
                      </td>
                      <td>{item.doc_type}</td>
                      <td><StatusChip status={item.chain_status} label={item.chain_status.replace(/_/g, ' ')} /></td>
                      <td><HashCell hash={item.doc_hash} prefix="SHA256" /></td>
                      <td>
                        <StatusChip status={ageHours(item.created_at) >= 24 ? 'error' : 'neutral'} label={ageLabel(item.created_at)} />
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {/* Straight to the document, where it can be read and
                            released. "Inspect Case" landed on the case docket,
                            from which there was no way to clear the review. */}
                        <Link
                          to={`/cases/${item.case_id}/documents/${item.id}`}
                          className="btn btn-primary"
                          style={{ height: '28px', fontSize: '12px', padding: '0 8px' }}
                        >
                          Review Document
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
