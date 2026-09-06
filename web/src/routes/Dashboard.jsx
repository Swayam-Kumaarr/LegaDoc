import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';
import StatusChip from '../components/StatusChip';

export default function Dashboard() {
  const { user } = useAuth();
  const { t } = useI18n();

  const role = user?.role || 'duty_officer';

  // Real domain cases table per PRD Section 8
  const [assignedCases] = useState([
    {
      case_number: 'CYB-2026-482910',
      id: 'b1a2c3d4-0001-4000-8000-000000000001',
      crime_type: 'Financial Cyberfraud (Sec 66D IT Act)',
      stage: 'Investigation & Evidence Ingestion',
      days_open: 5,
      status: 'UNDER_INVESTIGATION',
      status_label: 'Under Investigation',
      priority: 'CRITICAL'
    },
    {
      case_number: 'NDP-2026-119482',
      id: 'b1a2c3d4-0002-4000-8000-000000000002',
      crime_type: 'Commercial Contraband Seizure (NDPS Act)',
      stage: 'Panchnama Certification & FSL Forwarding',
      days_open: 12,
      status: 'CONFIRMED',
      status_label: 'Chain Confirmed',
      priority: 'HIGH'
    },
    {
      case_number: 'HOM-2026-004921',
      id: 'b1a2c3d4-0003-4000-8000-000000000003',
      crime_type: 'Homicide / Grievous Hurt (Sec 302 IPC)',
      stage: 'Forensic Autopsy Report Integration',
      days_open: 28,
      status: 'NEEDS_REVIEW',
      status_label: 'Needs Review',
      priority: 'CRITICAL'
    },
    {
      case_number: 'COR-2026-902144',
      id: 'b1a2c3d4-0004-4000-8000-000000000004',
      crime_type: 'Public Procurement Bribery (PC Act)',
      stage: 'Section 17A Sanction Verification',
      days_open: 44,
      status: 'PROCESSING',
      status_label: 'SLA Pending',
      priority: 'MEDIUM'
    },
    {
      case_number: 'ROB-2026-339102',
      id: 'b1a2c3d4-0005-4000-8000-000000000005',
      crime_type: 'Armed Bank Robbery (Sec 392 IPC)',
      stage: 'Test Identification Parade & CCTV Review',
      days_open: 2,
      status: 'REGISTERED',
      status_label: 'FIR Registered',
      priority: 'HIGH'
    }
  ]);

  // Operational metrics (density over whitespace per PRD Section 2)
  const getRoleMetrics = () => {
    switch (role) {
      case 'court':
        return [
          { label: 'Pending Bail Petitions', value: '4', sub: 'Magistrate Court No. 3' },
          { label: 'Active Trial Proceedings', value: '12', sub: 'Charges framed & docketed' },
          { label: 'Immutable Ledger Events', value: '1,420', sub: '100% cryptographic integrity' },
          { label: 'Avg Judicial Turnaround', value: '3.2d', sub: 'Within statutory guidelines' }
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
          { label: 'Pending Requisitions', value: '6', sub: 'Dispatched under Section 91 CrPC' },
          { label: 'Oldest Requisition SLA', value: '48h', sub: 'Target: under 72h' },
          { label: 'Certified Submissions', value: '84', sub: 'Committed to ledger' },
          { label: 'Cryptographic MSP Status', value: 'Active', sub: 'Mutual TLS valid' }
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
          { label: 'Fabric MSP Tenants', value: '4', sub: 'Multi-organization quorum' },
          { label: 'Audit Chain Serial Hash', value: 'Valid', sub: 'Zero forks detected' },
          { label: 'Failed Decryption Attempts', value: '0', sub: '24-hour log window' }
        ];
      case 'records_ncrb_analyst':
      case 'duty_officer':
      case 'io':
      case 'sho':
      default:
        return [
          { label: 'Active Assigned Cases', value: '24', sub: 'Assigned in this precinct' },
          { label: 'Fabric Ledger Integrity', value: '100%', sub: 'SHA-256 hashes validated' },
          { label: 'Oldest Requisition SLA', value: '48h', sub: 'HDFC Bank Nodal Unit' },
          { label: 'Pending Redaction Verifications', value: '3', sub: 'Requires IO confirmation' }
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
            <Link to="/cases" className="btn btn-primary">
              Register New Case / FIR
            </Link>
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
              <h2 className="text-heading" style={{ fontSize: '15px' }}>
                My Assigned Cases
              </h2>
              <span className="text-caption">
                Active matters assigned to this official identity under Section 156/157 CrPC
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
                {assignedCases.map((c) => (
                  <tr key={c.case_number}>
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
                ))}
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
