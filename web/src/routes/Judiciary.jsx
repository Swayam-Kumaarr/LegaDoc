import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';
import HashCell from '../components/HashCell';

export default function Judiciary() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('bail'); // 'bail' | 'trial' | 'audit'

  const [selectedCase, setSelectedCase] = useState('CYB-2026-482910');
  const [hearingDate, setHearingDate] = useState('2026-09-10T11:00');
  const [bailDecision, setBailDecision] = useState('GRANTED');
  const [bailConditions, setBailConditions] = useState('Personal bond of INR 50,000 with one local surety. Surrender passport to court registry.');
  const [actionAlert, setActionAlert] = useState(null);

  const bailApplications = [
    {
      id: 'BAIL-2026-001',
      case_number: 'CYB-2026-482910',
      accused: 'Vikram Sharma',
      sections: 'IT Act Sec 66D, IPC 420',
      filed_date: '2026-09-02',
      status: 'Hearing Scheduled',
      medical_summary: 'Hypertension reported (verified by Civil Hospital)'
    },
    {
      id: 'BAIL-2026-002',
      case_number: 'NDP-2026-119482',
      accused: 'Rahul M. Verma',
      sections: 'NDPS Act Sec 20(b)(ii)(B)',
      filed_date: '2026-09-01',
      status: 'Pending Review',
      medical_summary: 'No special medical grounds submitted'
    }
  ];

  const trialHearings = [
    {
      id: 'TR-2026-001',
      case_number: 'FIN-2026-881923',
      stage: 'Framing of Charges',
      prosecutor: 'Adv. R. S. Iyer (Public Prosecutor)',
      defense_counsel: 'Adv. M. K. Sen',
      next_hearing: '2026-09-15',
      charge_sheet_status: 'Validated Against Stage Requirements'
    }
  ];

  const handleIssueBailOrder = (e) => {
    e.preventDefault();
    setActionAlert({
      type: 'success',
      msg: `Judicial Bail Order (${bailDecision}) recorded on Hyperledger Fabric ledger for Case ${selectedCase}. Immutable timestamp attached.`
    });
  };

  const handleScheduleHearing = (e) => {
    e.preventDefault();
    setActionAlert({
      type: 'success',
      msg: `Hearing notice published for ${selectedCase} on ${hearingDate}. Summons transmitted to IO and Defense.`
    });
  };

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <span>Judiciary</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Magistrate Bench Docket</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">Judicial Bench & Magistrate Portal</h1>
            <p className="page-desc">
              Bail hearings, stage requirement compliance checks, judicial charge sheet review, and unredacted evidentiary inspection.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <StatusChip status="neutral" label="Role: Court / Magistrate" />
            <StatusChip status="success" label="Privilege: Unredacted Judicial Review" />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Judicial Authority Note (Flows 4 & 5):</strong> The court bench receives the complete evidentiary file
          including unredacted sensitive markers, chain-of-custody verification hashes, and full AI Parser audit logs.
        </div>

        {/* Tabs */}
        <div className="gov-tabs">
          <button
            className={`gov-tab-btn ${activeTab === 'bail' ? 'active' : ''}`}
            onClick={() => setActiveTab('bail')}
          >
            Bail Docket & Orders
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'trial' ? 'active' : ''}`}
            onClick={() => setActiveTab('trial')}
          >
            Trial Proceedings & Charge Sheets
          </button>
          <button
            className={`gov-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
          >
            Full Ledger Audit Trail
          </button>
        </div>

        {actionAlert && (
          <div className={`alert ${actionAlert.type === 'success' ? 'alert-success' : 'alert-warning'}`}>
            {actionAlert.msg}
          </div>
        )}

        {/* Tab 1: Bail */}
        {activeTab === 'bail' && (
          <div className="grid-2">
            <div className="card">
              <span className="table-caption">
                {bailApplications.length} active bail applications pending determination.
              </span>
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Case Number</th>
                      <th>Accused</th>
                      <th>Sections</th>
                      <th>Status</th>
                      <th>Select</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bailApplications.map((b) => (
                      <tr key={b.id}>
                        <td><span className="mono-text">{b.case_number}</span></td>
                        <td style={{ fontWeight: 500 }}>{b.accused}</td>
                        <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{b.sections}</td>
                        <td><StatusChip status={b.status} /></td>
                        <td>
                          <button
                            className="btn btn-secondary"
                            style={{ height: '28px', fontSize: '12px', padding: '0 8px' }}
                            onClick={() => setSelectedCase(b.case_number)}
                          >
                            Select
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <h2 className="card-title">Issue Judicial Bail Order & Statutory Compliance</h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '12px' }}>
                Target Docket: <strong>{selectedCase}</strong>. All determinations are signed and committed to the ledger.
              </p>

              {/* Statutory Pathway Guidance Box */}
              <div style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                padding: '12px',
                marginBottom: '16px',
                fontSize: '12px',
                lineHeight: '1.5'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                    Statutory Bail Classification:
                  </span>
                  <span style={{
                    fontWeight: 600,
                    color: selectedCase.startsWith('NDP') ? '#b91c1c' : '#0369a1'
                  }}>
                    {selectedCase.startsWith('NDP') 
                      ? 'Strictly Non-Bailable (NDPS Act § 37 Twin Conditions Apply)' 
                      : 'Non-Bailable (Sec 437/439 CrPC Judicial Discretion)'}
                  </span>
                </div>
                <div style={{ color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  <strong>Applicable Statute:</strong> {selectedCase.startsWith('NDP') 
                    ? 'Narcotic Drugs and Psychotropic Substances Act, 1985 (Sec 20/21/37)' 
                    : 'Information Technology Act, 2000 (Sec 66D) r/w IPC Sec 420 (Sec 318 BNS)'}
                </div>
                <div style={{ color: 'var(--text-secondary)' }}>
                  <strong>Mandatory Judicial Gate:</strong> {selectedCase.startsWith('NDP')
                    ? 'Court must record affirmative satisfaction that: (i) Accused is not guilty, and (ii) Unlikely to commit offense on bail.'
                    : 'Verification of digital asset lien, device seizure logs, and absence of flight risk.'}
                </div>
              </div>

              <form onSubmit={handleIssueBailOrder}>
                <div className="form-group">
                  <label className="form-label">Judicial Determination</label>
                  <select
                    className="form-select"
                    value={bailDecision}
                    onChange={(e) => setBailDecision(e.target.value)}
                  >
                    <option value="GRANTED">Bail Granted (Regular Bail)</option>
                    <option value="INTERIM">Interim Bail Pending Verification</option>
                    <option value="REJECTED">Bail Rejected (Risk of Flight / Tampering)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label className="form-label">Bail Conditions & Directions</label>
                  <textarea
                    className="form-textarea"
                    value={bailConditions}
                    onChange={(e) => setBailConditions(e.target.value)}
                    rows={3}
                  />
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }}>
                    Pronounce Order
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleScheduleHearing}
                  >
                    Schedule Hearing
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Tab 2: Trial */}
        {activeTab === 'trial' && (
          <div className="card">
            <span className="table-caption">
              Trial bench hearings and Section 173 CrPC compliance reviews.
            </span>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Case Identifier</th>
                    <th>Current Trial Stage</th>
                    <th>Public Prosecutor</th>
                    <th>Defense Counsel</th>
                    <th>Next Hearing Date</th>
                    <th>Compliance Check</th>
                  </tr>
                </thead>
                <tbody>
                  {trialHearings.map((t) => (
                    <tr key={t.id}>
                      <td><span className="mono-text">{t.case_number}</span></td>
                      <td style={{ fontWeight: 500 }}>{t.stage}</td>
                      <td>{t.prosecutor}</td>
                      <td>{t.defense_counsel}</td>
                      <td>{t.next_hearing}</td>
                      <td><StatusChip status="confirmed" label="Stage Validated" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 3: Full Audit */}
        {activeTab === 'audit' && (
          <div className="card">
            <span className="table-caption">
              Full unredacted judicial audit trail verified against Hyperledger Fabric channel quorum.
            </span>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Timestamp (IST)</th>
                    <th>Actor / Authority</th>
                    <th>Action Executed</th>
                    <th>Target Resource</th>
                    <th>Cryptographic Digest</th>
                    <th>Ledger Consensus</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>2026-09-02 10:30:14</td>
                    <td>Duty Officer (Kumar · PS Central)</td>
                    <td style={{ fontWeight: 500 }}>Case Inception & Genesis FIR Registration</td>
                    <td><span className="mono-text">CYB-2026-482910</span></td>
                    <td><HashCell hash="8a92b41c0981928475aeb90141eab14902148110912781290384aa8192837491" /></td>
                    <td><StatusChip status="confirmed" label="Chain Verified" /></td>
                  </tr>
                  <tr>
                    <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>2026-09-02 10:32:05</td>
                    <td>AI Pipeline (PaddleOCR Worker)</td>
                    <td style={{ fontWeight: 500 }}>Automated Redaction & Span Inspection</td>
                    <td><span className="mono-text">DOC-CYB-2026-001</span></td>
                    <td><HashCell hash="71e409aa81928374910283740192847192837482910284718f92a11b6c73e048" /></td>
                    <td><StatusChip status="neutral" label="4 Spans Redacted" /></td>
                  </tr>
                  <tr>
                    <td style={{ fontSize: '12px', color: 'var(--color-text-secondary)' }}>2026-09-02 11:15:30</td>
                    <td>Investigating Officer (IO S. Rao)</td>
                    <td style={{ fontWeight: 500 }}>Section 91 CrPC Evidentiary Requisition</td>
                    <td><span className="mono-text">HDFC-NODAL-REQ-01</span></td>
                    <td><HashCell hash="fe22890141eab14902148110912781290384aa81928374918f92a11b6c73e048" /></td>
                    <td><StatusChip status="confirmed" label="Chain Verified" /></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
