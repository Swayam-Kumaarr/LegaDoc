import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import { apiClient, apiUpload } from "../api/client";
import StatusChip from "../components/StatusChip";

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

export default function ExternalAuthority() {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [selectedReq, setSelectedReq] = useState(null);
  const [attachment, setAttachment] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [sortOrder, setSortOrder] = useState("oldest");

  const fetchRequests = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await apiClient("/evidence-requests");
      setRequests(Array.isArray(data) ? data : []);
    } catch (err) {
      setRequests([]);
      setLoadError(formatError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRequests();
  }, []);

  const pending = requests.filter((r) => r.status !== "completed");
  const sortedRequests = [...pending].sort((a, b) => {
    const diff = new Date(a.created_at) - new Date(b.created_at);
    return sortOrder === "oldest" ? diff : -diff;
  });

  const handleSubmitReport = async (e) => {
    e.preventDefault();
    if (!selectedReq || !attachment) return;

    setSubmitting(true);
    setStatusMessage(null);

    const formData = new FormData();
    formData.append("file", attachment);

    try {
      const updated = await apiUpload(
        `/evidence-requests/${selectedReq.id}/submit`,
        formData,
      );
      setStatusMessage({
        type: "success",
        msg: `Report submitted and hashed to Case ${selectedReq.case_number}'s chain of custody. Requisition status: ${updated.status}.`,
      });
      setAttachment(null);
      setSelectedReq(null);
      fetchRequests();
    } catch (err) {
      setStatusMessage({
        type: "error",
        msg: `Submission failed: ${formatError(err)}`,
      });
    } finally {
      setSubmitting(false);
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
            <h1 className="page-title">
              External Authority & Forensics Portal
            </h1>
            <p className="page-desc">
              Secure electronic requisition fulfillment for Forensic
              Laboratories, Hospitals, Banks, and Telecom Authorities.
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <StatusChip
              status="neutral"
              label={`Organization: ${user?.org_name || "Unknown"}`}
            />
          </div>
        </div>

        <div className="domain-notice">
          <strong>Security Standard (Audit Section 1.8 & 2.0):</strong> Access
          is strictly restricted to requisitions routed to your organization.
          You have no access to the broader case docket.
        </div>

        {statusMessage && (
          <div
            className={`alert ${statusMessage.type === "success" ? "alert-success" : "alert-error"}`}
          >
            {statusMessage.msg}
          </div>
        )}

        <div className="grid-2">
          {/* Requisitions List */}
          <div className="card">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "12px",
              }}
            >
              <div>
                <h2
                  className="card-title"
                  style={{
                    borderBottom: "none",
                    marginBottom: 0,
                    paddingBottom: 0,
                  }}
                >
                  Requisition Inbox
                </h2>
                <span className="table-caption" style={{ marginBottom: 0 }}>
                  {loading
                    ? "Loading..."
                    : `${sortedRequests.length} pending evidentiary requisition${sortedRequests.length === 1 ? "" : "s"}.`}
                </span>
              </div>
              <select
                className="form-select"
                style={{ width: "auto", height: "30px", fontSize: "12px" }}
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
              >
                <option value="oldest">
                  Sort: Oldest First (Audit Standard)
                </option>
                <option value="newest">Sort: Newest First</option>
              </select>
            </div>

            {loadError && (
              <div
                className="alert alert-error"
                style={{ marginBottom: "12px" }}
              >
                Could not load requisitions: {loadError}
              </div>
            )}

            {!loadError && !loading && sortedRequests.length === 0 && (
              <p style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
                No pending requisitions addressed to your organization.
              </p>
            )}

            <div
              style={{ display: "flex", flexDirection: "column", gap: "8px" }}
            >
              {sortedRequests.map((req) => (
                <div
                  key={req.id}
                  onClick={() => setSelectedReq(req)}
                  style={{
                    padding: "12px 14px",
                    borderRadius: "4px",
                    border: `1px solid ${selectedReq?.id === req.id ? "var(--ink-900)" : "var(--border-default)"}`,
                    background:
                      selectedReq?.id === req.id
                        ? "var(--surface-sunken)"
                        : "var(--surface-panel)",
                    cursor: "pointer",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginBottom: "4px",
                    }}
                  >
                    <span className="mono-text" style={{ fontSize: "11px" }}>
                      {req.case_number}
                    </span>
                    <StatusChip status="pending" label={req.status} />
                  </div>
                  <div
                    style={{
                      fontWeight: 600,
                      fontSize: "13px",
                      color: "var(--color-text-primary)",
                    }}
                  >
                    {req.doc_type_expected || "Evidence"}
                  </div>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "var(--color-text-secondary)",
                      marginTop: "4px",
                    }}
                  >
                    Requested {new Date(req.created_at).toLocaleDateString()}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Fulfillment Form */}
          <div className="card">
            <h2 className="card-title">Fulfill & Submit Official Report</h2>

            {selectedReq ? (
              <div>
                <div
                  style={{
                    background: "var(--surface-sunken)",
                    padding: "12px",
                    borderRadius: "4px",
                    marginBottom: "16px",
                    border: "1px solid var(--border-default)",
                  }}
                >
                  <div
                    style={{
                      fontSize: "11px",
                      textTransform: "uppercase",
                      color: "var(--text-secondary)",
                      fontWeight: 600,
                    }}
                  >
                    Requisition Target
                  </div>
                  <div
                    style={{
                      fontWeight: 600,
                      color: "var(--text-primary)",
                      marginTop: "2px",
                    }}
                  >
                    {selectedReq.doc_type_expected || "Evidence"}
                  </div>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "var(--text-secondary)",
                      marginTop: "2px",
                    }}
                  >
                    Case Docket: {selectedReq.case_number}
                  </div>
                </div>

                <form onSubmit={handleSubmitReport}>
                  <div className="form-group">
                    <label className="form-label">
                      Signed Official Report File
                    </label>
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
                    style={{ width: "100%" }}
                    disabled={submitting}
                  >
                    {submitting
                      ? "Submitting..."
                      : "Submit Report & Commit to Chain of Custody"}
                  </button>
                </form>
              </div>
            ) : (
              <div
                style={{
                  padding: "36px 16px",
                  textAlign: "center",
                  color: "var(--text-secondary)",
                }}
              >
                Select a requisition from the list on the left to upload the
                certifying response.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
