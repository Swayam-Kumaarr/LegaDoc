import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import { apiClient } from '../api/client';
import StatusChip from '../components/StatusChip';

export default function Dashboard() {
  const { user } = useAuth();
  const { t } = useI18n();

  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    async function loadCases() {
      setLoading(true);
      setError(null);
      try {
        const data = await apiClient('/cases');
        if (isMounted) setCases(data || []);
      } catch (e) {
        if (isMounted) setError(e.message || 'Could not load cases.');
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    loadCases();
    return () => { isMounted = false; };
  }, []);

  const daysOpen = (createdAt) => Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / (1000 * 60 * 60 * 24)));

  // Real counts derived from the same list every role already sees via
  // GET /cases (server-side scoped: an IO gets only assigned cases, other
  // roles get everything they're permitted to see) — not separately
  // fabricated per role.
  const metrics = [
    { label: 'Total Cases', value: String(cases.length), sub: 'Visible under your current role' },
    { label: 'FIR Registered', value: String(cases.filter((c) => c.investigation_status === 'FIR_Registered').length), sub: 'Awaiting evidence collection' },
    { label: 'Charge Sheet Filed', value: String(cases.filter((c) => c.investigation_status === 'Charge_Sheet_Filed').length), sub: 'Section 173 CrPC / BNSS 2023' },
    { label: 'In Trial or Judgment', value: String(cases.filter((c) => ['Trial', 'Judgment'].includes(c.investigation_status)).length), sub: 'Before the court' },
  ];

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <span>{t('nav_dashboard', 'Dashboard Hub')}</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>{user?.name || 'Officer Identity'}</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">
              {user?.designation || 'Investigating Officer'} Worklist
            </h1>
            <p className="page-desc">
              Case dockets visible to this official identity, pulled live from the case registry.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <Link to="/cases" className="btn btn-primary">
              Register New Case / FIR
            </Link>
          </div>
        </div>

        <div className="grid-4">
          {metrics.map((m, idx) => (
            <div key={idx} className="stat-widget">
              <div className="stat-value">{loading ? '—' : m.value}</div>
              <span className="stat-label">{m.label}</span>
              <span className="stat-sub">{m.sub}</span>
            </div>
          ))}
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h2 className="text-heading" style={{ fontSize: '15px' }}>
                My Cases
              </h2>
              <span className="text-caption">
                Case dockets visible to this official identity under Section 156/157 CrPC
              </span>
            </div>
            <Link to="/cases" className="text-caption" style={{ color: 'var(--color-primary)', fontWeight: 600, textDecoration: 'none' }}>
              View All Case Records →
            </Link>
          </div>

          <div className="table-container" style={{ border: 'none', borderRadius: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Case Number</th>
                  <th>Crime Type</th>
                  <th>Court Level</th>
                  <th style={{ width: '100px' }}>Days Open</th>
                  <th style={{ width: '160px' }}>Status</th>
                  <th style={{ width: '120px', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {error ? (
                  <tr><td colSpan="6" style={{ textAlign: 'center', padding: '32px', color: 'var(--color-status-error, #b91c1c)' }}>{error}</td></tr>
                ) : loading ? (
                  <tr><td colSpan="6" style={{ textAlign: 'center', padding: '32px', color: 'var(--color-text-secondary)' }}>Loading…</td></tr>
                ) : cases.length === 0 ? (
                  <tr><td colSpan="6" style={{ textAlign: 'center', padding: '32px', color: 'var(--color-text-secondary)' }}>No cases yet. Register the first FIR to get started.</td></tr>
                ) : (
                  cases.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <Link
                          to={`/cases/${c.id}`}
                          style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--color-primary)', textDecoration: 'none' }}
                        >
                          {c.case_number}
                        </Link>
                      </td>
                      <td>{c.crime_type}</td>
                      <td>
                        <span className="text-caption" style={{ color: 'var(--color-text-primary)' }}>
                          {c.court_level || '—'}
                        </span>
                      </td>
                      <td>
                        <span className="mono-text" style={{ fontSize: '11px' }}>
                          {daysOpen(c.created_at)}d
                        </span>
                      </td>
                      <td>
                        <StatusChip status={c.investigation_status} label={c.investigation_status.replace(/_/g, ' ')} />
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link to={`/cases/${c.id}`} className="btn btn-secondary btn-sm">
                          Inspect Docket
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
