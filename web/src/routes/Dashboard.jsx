import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import StatusChip from '../components/StatusChip';

export default function Dashboard() {
  const { user } = useAuth();
  const { t } = useI18n();

  const role = user?.role || 'duty_officer';
  // Mirrors _UNRESTRICTED_CASE_ROLES in api/app/security.py — the roles for
  // which GET /cases returns the whole registry rather than a scoped set.
  const isOversightRole = ['config_admin', 'security_auditor', 'court', 'prosecutor', 'sho'].includes(role);

  // Live domain cases fetched from API
  const [assignedCases, setAssignedCases] = useState([]);
  const [loadingCases, setLoadingCases] = useState(true);

  useEffect(() => {
    let isMounted = true;
    apiClient('/cases')
      .then((data) => {
        if (!isMounted) return;
        if (Array.isArray(data) && data.length > 0) {
          const formatted = data.map((c) => {
            const created = new Date(c.created_at || Date.now());
            const daysOpen = Math.max(0, Math.floor((Date.now() - created.getTime()) / (1000 * 60 * 60 * 24)));
            const statusVal = c.investigation_status || 'FIR_Registered';
            return {
              id: c.id,
              case_number: c.case_number,
              crime_type: c.crime_type,
              stage: statusVal.replace(/_/g, ' '),
              days_open: daysOpen,
              status: statusVal === 'FIR_Registered' ? 'REGISTERED' : statusVal,
              status_label: statusVal.replace(/_/g, ' '),
            };
          });
          setAssignedCases(formatted);
        } else {
          setAssignedCases([]);
        }
      })
      .catch((err) => {
        console.error('Failed to load dashboard cases:', err);
        if (isMounted) setAssignedCases([]);
      })
      .finally(() => {
        if (isMounted) setLoadingCases(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Placeholder for a metric with no data source behind it yet.
  //
  // Integrity and security figures were previously hardcoded: "100%
  // cryptographic integrity", "Audit Chain Serial Hash: Valid / Zero forks
  // detected", "Failed Decryption Attempts: 0". None was read from anything.
  // On the running stack verify_chain_intact() returns false, so the dashboard
  // was asserting a clean ledger while the chain did not verify — the one
  // claim this product cannot afford to fake. A dash is worth more than a
  // number nobody computed.
  //
  // Per-case chain state is real and comes from GET /cases/:id/audit-log;
  // see the Audit Trail tab in CaseDetail and Judiciary.
  const UNWIRED = (label, sub) => ({ label, value: '—', sub, unwired: true });

  // Operational metrics (density over whitespace per PRD Section 2)
  const getRoleMetrics = () => {
    switch (role) {
      case 'court':
        return [
          { label: 'Pending Bail Petitions', value: '4', sub: 'Sample figure' },
          { label: 'Active Trial Proceedings', value: '12', sub: 'Sample figure' },
          UNWIRED('Immutable Ledger Events', 'Per-case integrity: Audit Trail tab'),
          { label: 'Avg Judicial Turnaround', value: '3.2d', sub: 'Sample figure' }
        ];
      case 'prosecutor':
        return [
          { label: 'Cases Pending Charge Sheet', value: '8', sub: 'Evidence nearing 60/90 days' },
          { label: 'Stage Compliance Verified', value: '5', sub: 'Ready for court filing' },
          { label: 'Section 409 Inconsistencies', value: '3', sub: 'Supplementary required' },
          { label: 'FSL Certificate Clearance', value: '94%', sub: 'Forensic science division' }
        ];
      case 'external_authority':
        return [
          { label: 'Pending Requisitions', value: '6', sub: 'Sample figure' },
          { label: 'Oldest Requisition SLA', value: '48h', sub: 'Sample figure' },
          UNWIRED('Certified Submissions', 'Ledger commit not yet reported'),
          UNWIRED('Cryptographic MSP Status', 'Fabric MSP state not yet reported')
        ];
      case 'defense':
        return [
          { label: 'Active Bail Applications', value: '2', sub: 'Under Section 437/439 CrPC' },
          { label: 'Next Scheduled Hearing', value: '10 Sept', sub: 'Court No. 3 Patiala House' },
          { label: 'Surety Undertakings', value: '1', sub: 'Guarantor verified' },
          { label: 'Accessible Case Files', value: '8', sub: 'Sanitized redacted dockets' }
        ];
      case 'config_admin':
      case 'security_auditor':
        return [
          { label: 'Active RBAC Role Matrix', value: '10', sub: 'Authoritative mappings' },
          { label: 'Fabric MSP Tenants', value: '4', sub: 'Sample figure' },
          // These two were the most dangerous strings in the app: an oversight
          // role was shown "Valid / Zero forks detected" and "0 failed
          // decryption attempts" as static text, which is exactly the
          // assurance a Security Auditor is there to check rather than assume.
          UNWIRED('Audit Chain Serial Hash', 'Verify per case in the Audit Trail tab'),
          UNWIRED('Failed Decryption Attempts', 'Security telemetry not yet wired')
        ];
      case 'records_ncrb_analyst':
      case 'duty_officer':
      case 'io':
      case 'sho':
      default:
        return [
          { label: 'Active Assigned Cases', value: loadingCases ? '...' : String(assignedCases.length), sub: 'Cases linked to this identity' },
          UNWIRED('Fabric Ledger Integrity', 'Verify per case in the Audit Trail tab'),
          { label: 'Oldest Requisition SLA', value: '48h', sub: 'Sample figure' },
          { label: 'Pending Redaction Verifications', value: '3', sub: 'Sample figure' }
        ];
    }
  };

  const metrics = getRoleMetrics();

  return (
    <div>
      {/* Breadcrumb Row */}
      <div className="gov-breadcrumb-bar">
        <span>{t('nav_dashboard', 'Dashboard Hub')}</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>{user?.name || 'Officer Identity'}</span>
      </div>

      <div className="page-container">
        {/* Page Header (No generic hero banner - straight to business per Section 8) */}
        <div className="page-header">
          <div>
            <h1 className="page-title">
              {user?.designation || 'Investigating Officer'} Worklist
            </h1>
            <p className="page-desc">
              Authoritative case dockets, evidence verification queue, and immutable audit ledger status.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            {/* POST /cases is duty_officer-only server-side. Offering this to a
                forensic lab, a judge or a defense advocate rendered a button
                whose only possible outcome was a 403 — an action the role is
                not permitted to take should not be presented as available. */}
            {role === 'duty_officer' && (
              <Link to="/cases" className="btn btn-primary">
                Register New Case / FIR
              </Link>
            )}
          </div>
        </div>

        {/* Operational Metrics (Dense 4-column row per Section 2 & 5) */}
        <div className="grid-4">
          {metrics.map((m, idx) => (
            <div key={idx} className="stat-widget">
              <div className="stat-value">{m.value}</div>
              <span className="stat-label">{m.label}</span>
              <span className="stat-sub">{m.sub}</span>
            </div>
          ))}
        </div>

        {/* Dense Table: My Assigned Cases (PRD Section 8) */}
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              {/* GET /cases returns the whole registry to oversight roles and
                  a scoped set to everyone else. Labelling both "My Assigned
                  Cases … assigned to this official identity" described only
                  the second, and made a cross-case view look like a personal
                  worklist — which is how a Duty Officer seeing all 105 cases
                  read as normal rather than as the access bug it was. */}
              <h2 className="text-heading" style={{ fontSize: '15px' }}>
                {isOversightRole ? 'Case Registry' : 'My Assigned Cases'}
              </h2>
              <span className="text-caption">
                {isOversightRole
                  ? 'All cases visible to this role across the registry'
                  : 'Matters linked to this official identity under Section 156/157 CrPC'}
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
                  <th>Investigation Stage</th>
                  <th style={{ width: '100px' }}>Days Open</th>
                  <th style={{ width: '140px' }}>Status</th>
                  <th style={{ width: '120px', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {loadingCases ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '32px 16px', color: 'var(--color-text-muted)' }}>
                      Loading jurisdiction case dockets...
                    </td>
                  </tr>
                ) : assignedCases.length === 0 ? (
                  <tr>
                    <td colSpan="6" style={{ textAlign: 'center', padding: '36px 16px', color: 'var(--color-text-muted)' }}>
                      <p style={{ margin: '0 0 10px 0', fontSize: '14px', fontWeight: 500 }}>
                        No active cases registered in this precinct yet.
                      </p>
                      <Link to="/cases" className="btn btn-primary btn-sm">
                        Register First Case / FIR →
                      </Link>
                    </td>
                  </tr>
                ) : (
                  assignedCases.map((c) => (
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
                          {c.stage}
                        </span>
                      </td>
                      <td>
                        <span className="mono-text" style={{ fontSize: '11px' }}>
                          {c.days_open}d
                        </span>
                      </td>
                      <td>
                        <StatusChip status={c.status} label={c.status_label} />
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

        {/* Statutory Compliance Notice */}
        <div className="domain-notice" style={{ marginTop: '16px' }}>
          <strong>Statutory Compliance Requirement:</strong> All documentary evidence ingested must have an accompanying
          Section 65B Electronic Certificate committed to the Hyperledger Fabric ledger prior to final Charge Sheet dispatch.
        </div>
      </div>
    </div>
  );
}
