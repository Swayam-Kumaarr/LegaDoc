import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import { apiClient } from "../api/client";
import StatusChip from "../components/StatusChip";
import HashCell from "../components/HashCell";

function formatError(err) {
  const detail = err?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      // fall through
    }
  }
  return err?.message || "Request failed.";
}

export default function Judiciary() {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState("bail"); // 'bail' | 'trial' | 'audit'

  const [cases, setCases] = useState([]);
  const [loadingCases, setLoadingCases] = useState(false);
  const [casesError, setCasesError] = useState(null);

  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [bailRecords, setBailRecords] = useState([]);
  const [bailPathway, setBailPathway] = useState(null);
  const [bailAlert, setBailAlert] = useState(null);
  const [bailDecision, setBailDecision] = useState(true);
  const [bailConditions, setBailConditions] = useState("");

  const [trialCaseId, setTrialCaseId] = useState("");
  const [trialAlert, setTrialAlert] = useState(null);
  const [verdict, setVerdict] = useState("acquitted");
  const [verdictSummary, setVerdictSummary] = useState("");

  const [auditCaseId, setAuditCaseId] = useState("");
  const [auditLog, setAuditLog] = useState(null);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [auditError, setAuditError] = useState(null);

  const fetchCases = async () => {
    setLoadingCases(true);
    setCasesError(null);
    try {
      const data = await apiClient("/cases");
      const list = Array.isArray(data) ? data : [];
      setCases(list);
      setSelectedCaseId((prev) =>
        list.some((c) => c.id === prev) ? prev : list[0]?.id || "",
      );
      setTrialCaseId((prev) =>
        list.some((c) => c.id === prev) ? prev : list[0]?.id || "",
      );
      setAuditCaseId((prev) =>
        list.some((c) => c.id === prev) ? prev : list[0]?.id || "",
      );
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

  const selectedCase = cases.find((c) => c.id === selectedCaseId) || null;
  const trialCase = cases.find((c) => c.id === trialCaseId) || null;

  const fetchBailRecords = async (caseId) => {
    if (!caseId) return;
    try {
      const records = await apiClient(`/cases/${caseId}/bail`);
      setBailRecords(Array.isArray(records) ? records : []);
    } catch {
      setBailRecords([]);
    }
  };

  const fetchBailPathway = async (caseId) => {
    if (!caseId) return;
    try {
      const data = await apiClient(`/cases/${caseId}/bail/pathway`);
      setBailPathway(data?.statutory_pathway || null);
    } catch {
      setBailPathway(null);
    }
  };

  useEffect(() => {
    if (selectedCaseId) {
      fetchBailRecords(selectedCaseId);
      fetchBailPathway(selectedCaseId);
    } else {
      setBailPathway(null);
    }
  }, [selectedCaseId]);

  const handleScheduleHearing = async () => {
    if (!selectedCaseId) return;
    setBailAlert(null);
    try {
      await apiClient(`/cases/${selectedCaseId}/bail/hearing-notice`, {
        method: "POST",
      });
      setBailAlert({ type: "success", msg: "Bail hearing scheduled." });
      fetchCases();
      fetchBailRecords(selectedCaseId);
    } catch (err) {
      setBailAlert({
        type: "error",
        msg: `Could not schedule hearing: ${formatError(err)}`,
      });
    }
  };

  const handleIssueBailOrder = async (e) => {
    e.preventDefault();
    if (!selectedCaseId) return;
    setBailAlert(null);
    try {
      const record = await apiClient(`/cases/${selectedCaseId}/bail/order`, {
        body: { granted: bailDecision, conditions: bailConditions || null },
      });
      setBailAlert({
        type: "success",
        msg: `Bail order pronounced and uploaded to the judicial docket (Reference Stage: ${record.stage || "Official Record"}).`,
      });
      setBailConditions("");
      fetchCases();
      fetchBailRecords(selectedCaseId);
    } catch (err) {
      setBailAlert({
        type: "error",
        msg: `Could not issue bail order: ${formatError(err)}`,
      });
    }
  };

  const handleScheduleTrialHearing = async () => {
    if (!trialCaseId) return;
    setTrialAlert(null);
    try {
      await apiClient(`/cases/${trialCaseId}/trial/hearing-notice`, {
        method: "POST",
      });
      setTrialAlert({
        type: "success",
        msg: "Summons and Trial Hearing Notice officially issued to all parties on record.",
      });
      fetchCases();
    } catch (err) {
      setTrialAlert({
        type: "error",
        msg: `Could not schedule trial hearing: ${formatError(err)}`,
      });
    }
  };

  const handleRecordJudgment = async (e) => {
    e.preventDefault();
    if (!trialCaseId) return;
    setTrialAlert(null);
    try {
      const updated = await apiClient(`/cases/${trialCaseId}/judgment`, {
        body: { verdict, summary: verdictSummary || null },
      });
      setTrialAlert({
        type: "success",
        msg: `Final Judgment and Order signed and entered into the judicial register (Case Status: ${updated.investigation_status}).`,
      });
      setVerdictSummary("");
      fetchCases();
    } catch (err) {
      setTrialAlert({
        type: "error",
        msg: `Could not record judgment: ${formatError(err)}`,
      });
    }
  };

  const fetchAuditLog = async (caseId) => {
    if (!caseId) return;
    setLoadingAudit(true);
    setAuditError(null);
    try {
      const data = await apiClient(`/cases/${caseId}/audit-log`);
      setAuditLog(data);
    } catch (err) {
      setAuditLog(null);
      setAuditError(formatError(err));
    } finally {
      setLoadingAudit(false);
    }
  };

  useEffect(() => {
    if (activeTab === "audit" && auditCaseId) fetchAuditLog(auditCaseId);
  }, [activeTab, auditCaseId]);

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
              Bail hearings, trial proceedings, and full unredacted audit-trail
              inspection.
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <StatusChip
              status="neutral"
              label={`Role: ${user?.role ? user.role.replace(/_/g, " ").toUpperCase() : "COURT"}`}
            />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Judicial Bench Statutory Authority:</strong> Under the
          Bharatiya Sakshya Adhiniyam, 2023 and CrPC / BNSS, the judicial bench
          retains inherent jurisdiction to inspect the complete unredacted
          evidentiary record and the immutable audit trail of proceedings.
        </div>

        {casesError && (
          <div className="alert alert-error">
            Could not load cases: {casesError}
          </div>
        )}

        {/* Tabs */}
        <div className="gov-tabs">
          <button
            className={`gov-tab-btn ${activeTab === "bail" ? "active" : ""}`}
            onClick={() => setActiveTab("bail")}
          >
            Bail Docket & Orders
          </button>
          <button
            className={`gov-tab-btn ${activeTab === "trial" ? "active" : ""}`}
            onClick={() => setActiveTab("trial")}
          >
            Trial Proceedings
          </button>
          <button
            className={`gov-tab-btn ${activeTab === "audit" ? "active" : ""}`}
            onClick={() => setActiveTab("audit")}
          >
            Full Ledger Audit Trail
          </button>
        </div>

        {/* Tab 1: Bail */}
        {activeTab === "bail" && (
          <div className="grid-2">
            <div className="card">
              <span className="table-caption">
                {loadingCases
                  ? "Loading..."
                  : `${cases.length} case${cases.length === 1 ? "" : "s"} visible to this bench.`}
              </span>
              {cases.length === 0 && !loadingCases && (
                <p
                  style={{
                    color: "var(--text-secondary)",
                    fontSize: "13px",
                    marginTop: "8px",
                  }}
                >
                  No cases yet.
                </p>
              )}
              {cases.length > 0 && (
                <div className="table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Case Number</th>
                        <th>Crime Type</th>
                        <th>Bail Status</th>
                        <th>Select</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cases.map((c) => (
                        <tr key={c.id}>
                          <td>
                            <span className="mono-text">{c.case_number}</span>
                          </td>
                          <td
                            style={{
                              fontSize: "13px",
                              color: "var(--text-secondary)",
                            }}
                          >
                            {c.crime_type}
                          </td>
                          <td>
                            <StatusChip
                              status={c.bail_status || "neutral"}
                              label={(c.bail_status || "No Bail Track").replace(
                                /_/g,
                                " ",
                              )}
                            />
                          </td>
                          <td>
                            <button
                              className="btn btn-secondary"
                              style={{
                                height: "28px",
                                fontSize: "12px",
                                padding: "0 8px",
                              }}
                              onClick={() => setSelectedCaseId(c.id)}
                            >
                              {selectedCaseId === c.id ? "Selected" : "Select"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="card">
              <h2 className="card-title">Bail Track</h2>
              {selectedCase ? (
                <>
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "13px",
                      marginBottom: "12px",
                    }}
                  >
                    Target Docket: <strong>{selectedCase.case_number}</strong> ·
                    Current stage:{" "}
                    <strong>
                      {(selectedCase.bail_status || "No Bail Track").replace(
                        /_/g,
                        " ",
                      )}
                    </strong>
                  </p>

                  {/* Statutory Pathway Guidance Box — fetched live from
                      GET /cases/:id/bail/pathway, which matches the case's
                      real crime_type against the 15-crime-type statutory
                      taxonomy in bail_pathways.py. Falls back to the
                      "General Cognizable Offense" entry server-side if the
                      crime type has no dedicated statutory entry. */}
                  {bailPathway ? (
                    <div
                      style={{
                        background: "var(--surface-sunken)",
                        border: "1px solid var(--border-default)",
                        borderRadius: "4px",
                        padding: "12px",
                        marginBottom: "16px",
                        fontSize: "12px",
                        lineHeight: "1.5",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          marginBottom: "6px",
                          flexWrap: "wrap",
                          gap: "6px",
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 600,
                            color: "var(--text-primary)",
                          }}
                        >
                          Statutory Bail Classification (
                          {bailPathway.crime_type}):
                        </span>
                        <span
                          style={{
                            fontWeight: 600,
                            color: /non-bailable/i.test(
                              bailPathway.bailable_status || "",
                            )
                              ? "#b91c1c"
                              : "#0369a1",
                          }}
                        >
                          {bailPathway.bailable_status}
                        </span>
                      </div>
                      <div
                        style={{
                          color: "var(--text-secondary)",
                          marginBottom: "4px",
                        }}
                      >
                        <strong>Primary Statute:</strong>{" "}
                        {bailPathway.primary_statute}
                      </div>
                      <div
                        style={{
                          color: "var(--text-secondary)",
                          marginBottom: "4px",
                        }}
                      >
                        <strong>Applicable Sections:</strong>{" "}
                        {bailPathway.applicable_sections}
                      </div>
                      <div
                        style={{
                          color: "var(--text-secondary)",
                          marginBottom: "4px",
                        }}
                      >
                        <strong>Jurisdiction:</strong>{" "}
                        {bailPathway.jurisdiction_court}
                      </div>
                      {Array.isArray(bailPathway.statutory_pathway) &&
                        bailPathway.statutory_pathway.length > 0 && (
                          <div
                            style={{
                              color: "var(--text-secondary)",
                              marginBottom: "4px",
                            }}
                          >
                            <strong>Statutory Pathway:</strong>
                            <ol style={{ margin: "4px 0 0 18px", padding: 0 }}>
                              {bailPathway.statutory_pathway.map((step, i) => (
                                <li key={i}>{step}</li>
                              ))}
                            </ol>
                          </div>
                        )}
                      <div style={{ color: "var(--text-secondary)" }}>
                        <strong>Special Conditions:</strong>{" "}
                        {bailPathway.special_conditions}
                      </div>
                    </div>
                  ) : (
                    <p
                      style={{
                        color: "var(--text-secondary)",
                        fontSize: "12px",
                        marginBottom: "16px",
                      }}
                    >
                      Loading statutory bail pathway…
                    </p>
                  )}

                  {bailAlert && (
                    <div
                      className={`alert ${bailAlert.type === "success" ? "alert-success" : "alert-error"}`}
                    >
                      {bailAlert.msg}
                    </div>
                  )}

                  {bailRecords.length > 0 && (
                    <div style={{ marginBottom: "14px", fontSize: "12px" }}>
                      <div style={{ fontWeight: 600, marginBottom: "4px" }}>
                        Stage History
                      </div>
                      {bailRecords.map((r) => (
                        <div
                          key={r.id}
                          style={{ color: "var(--text-secondary)" }}
                        >
                          {new Date(r.created_at).toLocaleString()} —{" "}
                          {r.stage.replace(/_/g, " ")}
                        </div>
                      ))}
                    </div>
                  )}

                  <div
                    style={{
                      display: "flex",
                      gap: "8px",
                      marginBottom: "14px",
                    }}
                  >
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleScheduleHearing}
                      disabled={
                        selectedCase.bail_status !== "Application_Filed"
                      }
                    >
                      Schedule Hearing
                    </button>
                  </div>

                  <form onSubmit={handleIssueBailOrder}>
                    <div className="form-group">
                      <label className="form-label">
                        Judicial Determination
                      </label>
                      <select
                        className="form-select"
                        value={bailDecision ? "GRANTED" : "REJECTED"}
                        onChange={(e) =>
                          setBailDecision(e.target.value === "GRANTED")
                        }
                      >
                        <option value="GRANTED">Bail Granted</option>
                        <option value="REJECTED">Bail Rejected</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label className="form-label">
                        Bail Conditions & Directions
                      </label>
                      <textarea
                        className="form-textarea"
                        value={bailConditions}
                        onChange={(e) => setBailConditions(e.target.value)}
                        rows={3}
                        placeholder="e.g. Personal bond of INR 50,000 with one local surety."
                      />
                    </div>

                    <button
                      type="submit"
                      className="btn btn-primary"
                      style={{ width: "100%" }}
                      disabled={
                        selectedCase.bail_status !== "Hearing_Scheduled"
                      }
                    >
                      Pronounce Order
                    </button>
                    {selectedCase.bail_status !== "Hearing_Scheduled" && (
                      <p
                        style={{
                          fontSize: "11px",
                          color: "var(--text-secondary)",
                          marginTop: "6px",
                        }}
                      >
                        A hearing must be scheduled (application filed by
                        defense first) before an order can be issued.
                      </p>
                    )}
                  </form>
                </>
              ) : (
                <p style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
                  Select a case from the list to manage its bail track.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Trial */}
        {activeTab === "trial" && (
          <div className="grid-2">
            <div className="card">
              <span className="table-caption">
                Cases eligible for trial proceedings (Charge Sheet filed or
                later).
              </span>
              <div className="form-group" style={{ marginTop: "10px" }}>
                <label className="form-label">Select Case</label>
                <select
                  className="form-select"
                  value={trialCaseId}
                  onChange={(e) => setTrialCaseId(e.target.value)}
                >
                  {cases.length === 0 && (
                    <option value="">No cases available</option>
                  )}
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.case_number} —{" "}
                      {c.investigation_status?.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
              {trialCase && (
                <p style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
                  Current investigation status:{" "}
                  <strong>
                    {trialCase.investigation_status?.replace(/_/g, " ")}
                  </strong>
                </p>
              )}
            </div>

            <div className="card">
              <h2 className="card-title">Trial Actions</h2>
              {trialAlert && (
                <div
                  className={`alert ${trialAlert.type === "success" ? "alert-success" : "alert-error"}`}
                >
                  {trialAlert.msg}
                </div>
              )}

              {trialCase ? (
                <>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ width: "100%", marginBottom: "16px" }}
                    onClick={handleScheduleTrialHearing}
                    disabled={
                      trialCase.investigation_status !== "Charge_Sheet_Filed"
                    }
                  >
                    Schedule Trial Hearing
                  </button>

                  <form onSubmit={handleRecordJudgment}>
                    <div className="form-group">
                      <label className="form-label">Verdict</label>
                      <select
                        className="form-select"
                        value={verdict}
                        onChange={(e) => setVerdict(e.target.value)}
                      >
                        <option value="acquitted">Acquitted</option>
                        <option value="convicted">Convicted</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Judgment Summary</label>
                      <textarea
                        className="form-textarea"
                        rows={3}
                        value={verdictSummary}
                        onChange={(e) => setVerdictSummary(e.target.value)}
                      />
                    </div>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      style={{ width: "100%" }}
                      disabled={trialCase.investigation_status !== "Trial"}
                    >
                      Record Judgment
                    </button>
                    {trialCase.investigation_status !== "Trial" && (
                      <p
                        style={{
                          fontSize: "11px",
                          color: "var(--text-secondary)",
                          marginTop: "6px",
                        }}
                      >
                        A trial hearing must be scheduled first (case must be in
                        'Trial' stage).
                      </p>
                    )}
                  </form>
                </>
              ) : (
                <p style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
                  Select a case to manage trial proceedings.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Tab 3: Full Audit */}
        {activeTab === "audit" && (
          <div className="card">
            <div className="form-group" style={{ maxWidth: "360px" }}>
              <label className="form-label">Select Case</label>
              <select
                className="form-select"
                value={auditCaseId}
                onChange={(e) => setAuditCaseId(e.target.value)}
              >
                {cases.length === 0 && (
                  <option value="">No cases available</option>
                )}
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.case_number}
                  </option>
                ))}
              </select>
            </div>

            {auditError && (
              <div className="alert alert-error">{auditError}</div>
            )}
            {loadingAudit && (
              <p style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
                Loading audit trail...
              </p>
            )}

            {auditLog && auditLog.view_type === "summary" && (
              <div className="alert alert-warning">
                This role receives a summarized view for this case, not the full
                unredacted trail (chain intact:{" "}
                {auditLog.chain_intact ? "yes" : "NO — integrity check failed"}
                ).
              </div>
            )}

            {auditLog && auditLog.view_type === "full" && (
              <>
                <span className="table-caption">
                  {auditLog.total_entries} audit entries · Chain intact:{" "}
                  {auditLog.chain_intact ? "Yes" : "NO — INTEGRITY FAILURE"}
                </span>
                <div className="table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Timestamp</th>
                        <th>Actor</th>
                        <th>Action</th>
                        <th>Target</th>
                        <th>Row Hash</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLog.entries.length === 0 ? (
                        <tr>
                          <td
                            colSpan={5}
                            style={{
                              textAlign: "center",
                              color: "var(--text-secondary)",
                              padding: "20px",
                            }}
                          >
                            No audit entries yet.
                          </td>
                        </tr>
                      ) : (
                        auditLog.entries.map((entry) => (
                          <tr key={entry.id}>
                            <td
                              style={{
                                fontSize: "12px",
                                color: "var(--color-text-secondary)",
                              }}
                            >
                              {new Date(entry.created_at).toLocaleString()}
                            </td>
                            <td>
                              {entry.actor_name ||
                                entry.actor_email ||
                                "System"}
                            </td>
                            <td style={{ fontWeight: 500 }}>
                              {entry.action.replace(/_/g, " ")}
                            </td>
                            <td>
                              <span className="mono-text">
                                {entry.target_type || "—"}
                              </span>
                            </td>
                            <td>
                              <HashCell hash={entry.row_hash} />
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
