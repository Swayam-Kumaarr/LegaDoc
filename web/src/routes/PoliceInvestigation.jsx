import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient, apiUpload } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import StatusChip from '../components/StatusChip';
import SearchableSelect from '../components/SearchableSelect';

// Turns a thrown apiClient error into a readable string. err.detail comes
// straight from the backend's JSON body (see client.js handleApiError) —
// it's a plain string for most validation/permission errors here, but stay
// defensive in case a future endpoint returns a structured object.
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

export default function PoliceInvestigation() {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [casesError, setCasesError] = useState(null);

  // Worklist filters. The worklist used to sit above the action forms and
  // list every case flat, which stops working the moment a station has more
  // than a screenful: the thing an officer came here to do — register an FIR
  // — was pushed below an ever-growing table.
  const [worklistOpen, setWorklistOpen] = useState(false);
  const [filterDate, setFilterDate] = useState('');
  const [filterCrime, setFilterCrime] = useState('');
  const [filterQuery, setFilterQuery] = useState('');

  // FIR Form State
  const [crimeType, setCrimeType] = useState('Cybercrime');
  const [complaintText, setComplaintText] = useState('');
  const [firStatus, setFirStatus] = useState(null);

  // Upload Document State
  const [selectedCaseId, setSelectedCaseId] = useState('');
  const [docType, setDocType] = useState('FIR');
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);
  const [uploadedDoc, setUploadedDoc] = useState(null);

  // Case Diary State
  const [diaryCaseId, setDiaryCaseId] = useState('');
  const [diaryNote, setDiaryNote] = useState('');
  const [diaryStatus, setDiaryStatus] = useState(null);

  const fetchCases = async () => {
    setLoadingCases(true);
    setCasesError(null);
    try {
      const data = await apiClient('/cases');
      const list = Array.isArray(data) ? data : [];
      setCases(list);
      // Keep the form selectors pointed at a real case, but never invent one.
      setSelectedCaseId((prev) => (list.some((c) => c.id === prev) ? prev : (list[0]?.id || '')));
      setDiaryCaseId((prev) => (list.some((c) => c.id === prev) ? prev : (list[0]?.id || '')));
    } catch (err) {
      setCases([]);
      setCasesError(formatError(err));
    } finally {
      setLoadingCases(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, []);

  const handleRegisterFIR = async (e) => {
    e.preventDefault();
    setFirStatus({ type: 'pending', msg: 'Submitting FIR to the case registry...' });
    try {
      const res = await apiClient('/cases', {
        body: {
          crime_type: crimeType,
          complaint_text: complaintText,
        },
      });
      setFirStatus({
        type: 'success',
        msg: `FIR registered: Case ${res.case_number} (status: ${res.investigation_status}). The complaint narrative is stored as the case's first document, queued for redaction and ledger hash commit — no separate upload needed.`,
      });
      setComplaintText('');
      fetchCases();
    } catch (err) {
      setFirStatus({ type: 'error', msg: `FIR registration failed: ${formatError(err)}` });
    }
  };

  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadStatus({ type: 'error', msg: 'Select a file before ingesting.' });
      return;
    }
    if (!selectedCaseId) {
      setUploadStatus({ type: 'error', msg: 'No case selected — register or select a case first.' });
      return;
    }

    setUploadStatus({ type: 'pending', msg: 'Uploading document and enqueuing hash + OCR processing...' });

    const formData = new FormData();
    formData.append('case_id', selectedCaseId);
    formData.append('doc_type', docType);
    formData.append('file', uploadFile);

    try {
      const doc = await apiUpload('/documents', formData);
      setUploadedDoc(doc);
      setUploadStatus({
        type: 'success',
        msg: `Document accepted (v${doc.version}). Status: ${doc.status}, chain status: ${doc.chain_status}.`,
      });
      setUploadFile(null);
    } catch (err) {
      setUploadedDoc(null);
      setUploadStatus({ type: 'error', msg: `Upload failed: ${formatError(err)}` });
    }
  };

  const handleAddDiaryEntry = async (e) => {
    e.preventDefault();
    if (!diaryNote.trim()) return;
    if (!diaryCaseId) {
      setDiaryStatus({ type: 'error', msg: 'No case selected — register or select a case first.' });
      return;
    }
    setDiaryStatus({ type: 'pending', msg: 'Submitting case diary entry...' });
    try {
      const entry = await apiClient(`/cases/${diaryCaseId}/case-diary`, {
        body: { text: diaryNote },
      });
      setDiaryStatus({ type: 'success', msg: `Case diary entry recorded (status: ${entry.status}). It will route through redaction before becoming visible to other roles.` });
      setDiaryNote('');
    } catch (err) {
      setDiaryStatus({ type: 'error', msg: `Could not add case diary entry: ${formatError(err)}` });
    }
  };

  // Filtering and grouping for the worklist. Dates are compared on the local
  // calendar day, matching what the table prints, so a case registered at
  // 23:40 does not fall under the previous day for the officer reading it.
  const dayKey = (iso) => (iso ? new Date(iso).toLocaleDateString() : 'Unknown date');

  const crimeTypes = Array.from(new Set(cases.map((c) => c.crime_type).filter(Boolean))).sort();

  const filteredCases = cases.filter((c) => {
    if (filterCrime && c.crime_type !== filterCrime) return false;
    if (filterDate && dayKey(c.created_at) !== new Date(filterDate + 'T00:00:00').toLocaleDateString()) return false;
    if (filterQuery) {
      const q = filterQuery.trim().toLowerCase();
      const haystack = `${c.case_number || ''} ${c.crime_type || ''} ${c.investigation_status || ''}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  // Newest registration day first — an officer is looking for today's work,
  // not the oldest case on the station's books.
  const groupedCases = Object.entries(
    filteredCases.reduce((acc, c) => {
      const key = dayKey(c.created_at);
      (acc[key] = acc[key] || []).push(c);
      return acc;
    }, {})
  ).sort((a, b) => new Date(b[1][0].created_at || 0) - new Date(a[1][0].created_at || 0));

  const filtersActive = Boolean(filterDate || filterCrime || filterQuery);

  return (
    <div>
      <div className="gov-breadcrumb-bar">
        <span>Investigation & Cases</span>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Precinct Worklist</span>
      </div>

      <div className="page-container">
        <div className="page-header">
          <div>
            <h1 className="page-title">Police Investigation & Case Registry</h1>
            <p className="page-desc">
              First Information Report registration, evidentiary record ingestion, and case diary maintenance.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <StatusChip status="neutral" label={`Role: ${user?.role ? user.role.replace(/_/g, ' ').toUpperCase() : 'UNKNOWN'}`} />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Security Standard (Audit Section 1.2 & 1.5):</strong> Access control is verified server-side on every request.
          Sensitive fields (complainant identity, phone numbers, addresses) are redacted at the server boundary before transmission.
        </div>

        {/* Operational Metrics — both are real counts derived from the case
            list above, not static policy text dressed up as a metric. */}
        <div className="grid-2">
          <div className="stat-widget">
            <span className="stat-value">{cases.length}</span>
            <span className="stat-label">Assigned Investigation Cases</span>
            <span className="stat-sub">Visible to this account</span>
          </div>
          <div className="stat-widget">
            <span className="stat-value" style={{ color: 'var(--ink-900)' }}>
              {cases.filter((c) => c.investigation_status && c.investigation_status !== 'FIR_Registered').length}
            </span>
            <span className="stat-label">Cases Past Initial Registration</span>
            <span className="stat-sub">Beyond FIR-only stage</span>
          </div>
        </div>

        {/* Action Forms Grid */}
        <div className="grid-2">
          {/* Register FIR Form */}
          <div className="card">
            <h2 className="card-title">Register First Information Report (FIR)</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
              Creates the case record and stores this narrative as its first document in the same
              step — hashed and queued for redaction automatically. Restricted to the Duty Officer role.
            </p>

            {firStatus && (
              <div className={`alert ${firStatus.type === 'success' ? 'alert-success' : firStatus.type === 'error' ? 'alert-error' : 'alert-warning'}`}>
                {firStatus.msg}
              </div>
            )}

            <form onSubmit={handleRegisterFIR}>
              <div className="form-group">
                <label className="form-label">Crime Classification</label>
                <select
                  className="form-select"
                  value={crimeType}
                  onChange={(e) => setCrimeType(e.target.value)}
                >
                  <option value="Domestic Violence">Domestic Violence (Protection of Women / Sec 498A IPC)</option>
                  <option value="Cybercrime">Cybercrime (IT Act / Financial Cyberfraud)</option>
                  <option value="NDPS">NDPS (Narcotics & Psychotropic Substances)</option>
                  <option value="Homicide">Homicide (BNS / Sec 302 IPC)</option>
                  <option value="Financial Fraud">Financial Fraud & Money Laundering (PMLA)</option>
                  <option value="Theft">Theft & Burglary (Sec 379/380 IPC)</option>
                  <option value="Robbery">Armed Robbery & Dacoity (Sec 392 IPC)</option>
                  <option value="Sexual Assault">Sexual Assault & Rape (Sec 376 IPC / POCSO)</option>
                  <option value="Acid Attack">Acid Attack (Sec 326A IPC)</option>
                  <option value="Road Accident">Road Accident & Rash Driving (Sec 279/304A IPC)</option>
                  <option value="Public Corruption">Public Corruption & Bribery (PC Act)</option>
                  <option value="Cyber Identity Theft">Cyber Identity Theft (Sec 66C IT Act)</option>
                  <option value="Organized Crime">Organized Crime & Extortion (MCOCA / IPC 384)</option>
                  <option value="Kidnapping">Kidnapping & Abduction (Sec 363/364A IPC)</option>
                  <option value="General Cognizable Offense">General Cognizable Offense</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Complaint Narrative</label>
                <textarea
                  className="form-textarea"
                  placeholder="Enter complaint details. Sensitive informant identities will be redacted on ingest..."
                  value={complaintText}
                  onChange={(e) => setComplaintText(e.target.value)}
                  required
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Register FIR
              </button>
            </form>
          </div>

          {/* Upload Evidence Form */}
          <div className="card">
            <h2 className="card-title">Ingest Additional Evidence</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
              For anything beyond the FIR narrative itself — Panchnama, forensic reports, CCTV/media,
              witness statements. Hashing and OCR/redaction run asynchronously, same as the FIR document.
            </p>

            {uploadStatus && (
              <div className={`alert ${uploadStatus.type === 'success' ? 'alert-success' : uploadStatus.type === 'error' ? 'alert-error' : 'alert-warning'}`}>
                {uploadStatus.msg}
              </div>
            )}

            <form onSubmit={handleFileUpload}>
              <div className="form-group">
                <label className="form-label" htmlFor="ingest-case">Case Identifier</label>
                {/* Searchable: picking from a flat dropdown stops working
                    once a station has more cases than fit on screen. */}
                <SearchableSelect
                  id="ingest-case"
                  value={selectedCaseId}
                  onChange={setSelectedCaseId}
                  disabled={cases.length === 0}
                  placeholder={cases.length === 0 ? 'No cases available' : 'Type a case number or crime type'}
                  options={cases.map((c) => ({ value: c.id, label: c.case_number, hint: c.crime_type }))}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Document Classification</label>
                <select
                  className="form-select"
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                >
                  <option value="FIR">FIR Initial Record</option>
                  <option value="Panchnama">Panchnama (Seizure / Scene of Crime)</option>
                  <option value="Forensic_Report">Forensic Analysis Report</option>
                  <option value="CCTV_Footage">Binary Media (CCTV / Phone Dump)</option>
                  <option value="Witness_Statement">Witness Statement (Section 161)</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Evidence File</label>
                <input
                  type="file"
                  className="form-input"
                  onChange={(e) => setUploadFile(e.target.files[0])}
                  required
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={cases.length === 0}>
                Ingest Document
              </button>
            </form>

            {uploadedDoc && (
              <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Upload Result
                  </span>
                  <StatusChip status={uploadedDoc.chain_status} label={`Ledger: ${uploadedDoc.chain_status}`} />
                </div>
                <div style={{ background: 'var(--surface-sunken)', padding: '10px', borderRadius: '4px', fontSize: '12px', fontFamily: 'var(--font-mono)' }}>
                  <div>Document ID: {uploadedDoc.id}</div>
                  <div>SHA-256: {uploadedDoc.doc_hash || '(pending — hashing runs asynchronously)'}</div>
                  <div>Status: {uploadedDoc.status}</div>
                </div>
                <Link to={`/cases/${uploadedDoc.case_id}`} style={{ fontSize: '12px' }}>
                  View redacted preview in case docket &rarr;
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* Case Diary Section */}
        <div className="card">
          <h2 className="card-title">Append Case Diary Entry (Section 172 CrPC / BNSS)</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '12px' }}>
            Day-to-day chronological record of investigation. Append-only. Restricted to the assigned IO/SHO;
            routes through the redaction pipeline before other roles can view it.
          </p>

          {diaryStatus && (
            <div className={`alert ${diaryStatus.type === 'success' ? 'alert-success' : diaryStatus.type === 'error' ? 'alert-error' : 'alert-warning'}`}>
              {diaryStatus.msg}
            </div>
          )}

          <form onSubmit={handleAddDiaryEntry} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ minWidth: '240px' }}>
              <SearchableSelect
                id="diary-case"
                value={diaryCaseId}
                onChange={setDiaryCaseId}
                disabled={cases.length === 0}
                placeholder={cases.length === 0 ? 'No cases available' : 'Type a case number'}
                options={cases.map((c) => ({ value: c.id, label: c.case_number, hint: c.crime_type }))}
              />
            </div>
            <input
              type="text"
              className="form-input"
              style={{ flex: 1, minWidth: '280px' }}
              placeholder="Record daily entry (e.g. Conducted site inspection; seized physical exhibit)..."
              value={diaryNote}
              onChange={(e) => setDiaryNote(e.target.value)}
            />
            <button type="submit" className="btn btn-primary" disabled={cases.length === 0}>
              Append Entry
            </button>
          </form>
        </div>

        {/* Active Case Worklist — below the action forms, and collapsed by
            default. A station accumulates cases indefinitely; putting the
            table first buried the reason an officer opens this page. */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => setWorklistOpen((o) => !o)}
              aria-expanded={worklistOpen}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', color: 'inherit', font: 'inherit' }}
            >
              <h2 className="card-title" style={{ borderBottom: 'none', marginBottom: 0, paddingBottom: 0 }}>
                {worklistOpen ? '▾' : '▸'} Active Case Worklist
              </h2>
              <span className="table-caption" style={{ marginTop: '2px', marginBottom: 0 }}>
                {loadingCases
                  ? 'Loading…'
                  : `${cases.length} case${cases.length === 1 ? '' : 's'} visible to this account` +
                    (filtersActive ? ` — ${filteredCases.length} match the current filter` : '')}
              </span>
            </button>
            <button className="btn btn-secondary" onClick={fetchCases} disabled={loadingCases} style={{ height: '32px', fontSize: '12px' }}>
              {loadingCases ? 'Refreshing…' : 'Refresh Table'}
            </button>
          </div>

          {worklistOpen && (
            <>
              <div className="grid-3" style={{ marginTop: '14px', marginBottom: '14px' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label" htmlFor="worklist-query">Search case identifier</label>
                  <input
                    id="worklist-query"
                    className="form-input"
                    type="search"
                    placeholder="e.g. THE-2026-873593"
                    value={filterQuery}
                    onChange={(e) => setFilterQuery(e.target.value)}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label" htmlFor="worklist-crime">Crime classification</label>
                  <select
                    id="worklist-crime"
                    className="form-select"
                    value={filterCrime}
                    onChange={(e) => setFilterCrime(e.target.value)}
                  >
                    <option value="">All classifications</option>
                    {crimeTypes.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label className="form-label" htmlFor="worklist-date">Registration date</label>
                  <input
                    id="worklist-date"
                    className="form-input"
                    type="date"
                    value={filterDate}
                    onChange={(e) => setFilterDate(e.target.value)}
                  />
                </div>
              </div>

              {filtersActive && (
                <button
                  className="btn btn-secondary"
                  style={{ height: '28px', fontSize: '12px', marginBottom: '12px' }}
                  onClick={() => { setFilterQuery(''); setFilterCrime(''); setFilterDate(''); }}
                >
                  Clear filters
                </button>
              )}

              {casesError && (
                <div className="alert alert-warning" style={{ marginBottom: '12px' }}>
                  Could not load cases: {casesError}
                </div>
              )}

              {!casesError && !loadingCases && cases.length === 0 && (
                <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                  No cases yet. Register a FIR above to create the first one.
                </p>
              )}

              {!casesError && cases.length > 0 && filteredCases.length === 0 && (
                <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
                  No case matches these filters.
                </p>
              )}

              {groupedCases.map(([day, dayCases]) => (
                <div key={day} style={{ marginBottom: '18px' }}>
                  <h3 className="table-caption" style={{ marginBottom: '6px', fontWeight: 600 }}>
                    Registered {day} · {dayCases.length} case{dayCases.length === 1 ? '' : 's'}
                  </h3>
                  <div className="table-container">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Case Identifier</th>
                          <th>Crime Classification</th>
                          <th>Investigation Stage</th>
                          <th>Registration Date</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dayCases.map((c) => (
                          <tr key={c.id}>
                            <td><span className="mono-text">{c.case_number}</span></td>
                            <td>{c.crime_type}</td>
                            <td>
                              <StatusChip status={c.investigation_status} label={c.investigation_status ? c.investigation_status.replace(/_/g, ' ') : 'Registered'} />
                            </td>
                            <td style={{ color: 'var(--color-text-secondary)', fontSize: '13px' }}>
                              {c.created_at ? new Date(c.created_at).toLocaleDateString() : '—'}
                            </td>
                            <td>
                              <Link
                                to={`/cases/${c.id}`}
                                className="btn btn-secondary"
                                style={{ height: '28px', fontSize: '12px', padding: '0 8px' }}
                              >
                                Inspect Docket
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
