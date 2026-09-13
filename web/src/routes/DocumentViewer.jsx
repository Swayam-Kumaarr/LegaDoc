import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { apiClient } from "../api/client";
import RedactedBlock from "../components/RedactedBlock";
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

export default function DocumentViewer() {
  const { id: caseId, docId } = useParams();

  const [documentData, setDocumentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  // Redaction Correction State (for the assigned IO)
  const [entityType, setEntityType] = useState("PERSON");
  const [spanStart, setSpanStart] = useState(0);
  const [spanEnd, setSpanEnd] = useState(0);
  const [correctionAlert, setCorrectionAlert] = useState(null);
  const [submittingCorrection, setSubmittingCorrection] = useState(false);

  const fetchDoc = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await apiClient(`/documents/${docId}`);
      setDocumentData(data);
    } catch (err) {
      setDocumentData(null);
      setLoadError(formatError(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDoc();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  const handleApplyCorrection = async (e) => {
    e.preventDefault();
    setSubmittingCorrection(true);
    setCorrectionAlert(null);
    try {
      const updated = await apiClient(`/documents/${docId}/redact-tag`, {
        body: {
          entity_type: entityType,
          span_start: Number(spanStart),
          span_end: Number(spanEnd),
        },
      });
      setDocumentData(updated);
      setCorrectionAlert({
        type: "success",
        msg: `Correction recorded: [${entityType}] at [${spanStart}:${spanEnd}]. Audit trail updated.`,
      });
    } catch (err) {
      setCorrectionAlert({
        type: "error",
        msg: `Correction failed: ${formatError(err)}`,
      });
    } finally {
      setSubmittingCorrection(false);
    }
  };

  // Render text replacing [Redacted · Entity] with strict Section 6.5 RedactedBlock
  const renderSanitizedContent = (text) => {
    if (!text) return null;
    const regex = /\[Redacted\s*[·—\-:]\s*([^\]]+)\]/gi;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }
      const entityLabel = match[1].trim();
      parts.push(
        <RedactedBlock
          key={match.index}
          entityType={entityLabel}
          width={entityLabel.length * 8}
        />,
      );
      lastIndex = regex.lastIndex;
    }

    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts;
  };

  if (loading) {
    return (
      <div className="page-container" style={{ padding: "40px 24px" }}>
        Loading document record...
      </div>
    );
  }

  if (loadError || !documentData) {
    return (
      <div className="page-container" style={{ padding: "40px 24px" }}>
        <div className="alert alert-error">
          {loadError || "Document not found."}
        </div>
        <Link to={`/cases/${caseId}`}>&larr; Back to case file</Link>
      </div>
    );
  }

  const doc = documentData;

  return (
    <div>
      {/* Breadcrumbs */}
      <div className="gov-breadcrumb-bar">
        <Link to="/cases">Case Registry</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <Link to={`/cases/${caseId}`}>Case File</Link>
        <span className="gov-breadcrumb-separator">›</span>
        <span>Document Record {doc.id}</span>
      </div>

      <div className="page-container">
        {/* Document Header */}
        <div className="page-header" style={{ marginBottom: "14px" }}>
          <div>
            <h1 className="page-title">{doc.doc_type}</h1>
            <p className="page-desc">
              Document Reference: <span className="mono-text">{doc.id}</span> ·
              Version: {doc.version}
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <StatusChip
              status={doc.chain_status}
              label={`Ledger: ${(doc.chain_status || "unknown").toUpperCase()}`}
            />
            <StatusChip status={doc.status} label={`Pipeline: ${doc.status}`} />
          </div>
        </div>

        {/* Security Rule Callout */}
        <div className="domain-notice">
          <strong>Security Requirement (Section 6.5):</strong> Redacted spans
          are enforced server-side. The browser renders solid unrevealed blocks
          with entity categorization. No underlying sensitive data is present in
          the DOM.
        </div>

        {/* Two-Column Grid: Document Render Area (left) + Metadata Sidebar (right) (PRD Section 8) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) 340px",
            gap: "20px",
            alignItems: "start",
          }}
        >
          {/* Main Document Content Area */}
          <div className="card" style={{ padding: "20px" }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "14px",
                borderBottom: "1px solid var(--color-border)",
                paddingBottom: "8px",
              }}
            >
              <h2 className="text-heading" style={{ fontSize: "15px" }}>
                Sanitized Evidentiary Document
              </h2>
              <span className="text-caption">Section 65B Certified Output</span>
            </div>

            {doc.text ? (
              <div
                style={{
                  backgroundColor: "var(--color-surface-subtle)",
                  padding: "20px",
                  borderRadius: "var(--radius)",
                  border: "1px solid var(--color-border)",
                  fontFamily: "var(--font-mono)",
                  fontSize: "13px",
                  lineHeight: "26px",
                  whiteSpace: "pre-wrap",
                  color: "var(--color-text-primary)",
                }}
              >
                {renderSanitizedContent(doc.text)}
              </div>
            ) : (
              <p style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
                {doc.status === "ready"
                  ? "No text available for this document."
                  : `Document is still processing (status: ${doc.status}). Text will appear once redaction completes.`}
              </p>
            )}

            {doc.download_url && (
              <div style={{ marginTop: "12px" }}>
                <a
                  href={doc.download_url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-secondary btn-sm"
                >
                  Download Original File
                </a>
              </div>
            )}
          </div>

          {/* Metadata Sidebar (PRD Section 8) */}
          <div
            style={{ display: "flex", flexDirection: "column", gap: "16px" }}
          >
            {/* Metadata Card */}
            <div className="card">
              <h3 className="card-title">Document Metadata</h3>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px",
                }}
              >
                <div>
                  <span className="text-label">Pipeline Ingestion Status</span>
                  <div style={{ marginTop: "4px" }}>
                    <StatusChip status={doc.status} />
                  </div>
                </div>

                <div>
                  <span className="text-label">Legal Hold</span>
                  <div style={{ marginTop: "4px" }}>
                    <StatusChip
                      status={doc.retention_legal_hold ? "critical" : "neutral"}
                      label={doc.retention_legal_hold ? "Active" : "None"}
                    />
                  </div>
                </div>

                <div>
                  <span className="text-label">Chain-of-Custody Hash</span>
                  <div style={{ marginTop: "4px" }}>
                    <HashCell hash={doc.doc_hash} />
                  </div>
                </div>
              </div>
            </div>

            {/* Officer Tag Correction (Section 6.6) — restricted to the assigned IO */}
            <div className="card">
              <h3 className="card-title">Officer Redaction Correction</h3>
              <p className="text-caption" style={{ marginBottom: "12px" }}>
                If an entity was omitted by the automated NLP pipeline, specify
                the offset range to enforce redaction. Restricted to the
                Investigating Officer assigned to this case.
              </p>

              {correctionAlert && (
                <div
                  className={`alert ${correctionAlert.type === "success" ? "alert-success" : "alert-error"}`}
                  style={{ padding: "8px 10px", fontSize: "11px" }}
                >
                  {correctionAlert.msg}
                </div>
              )}

              <form onSubmit={handleApplyCorrection}>
                <div className="form-group">
                  <label className="form-label">Entity Category</label>
                  <select
                    className="form-select"
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                  >
                    <option value="PERSON">PERSON (Victim / Witness)</option>
                    <option value="PHONE">PHONE / CONTACT</option>
                    <option value="BANK_ACCOUNT">FINANCIAL / ACCOUNT</option>
                    <option value="MEDICAL">MEDICAL RECORD</option>
                    <option value="ADDRESS">RESIDENTIAL ADDRESS</option>
                  </select>
                </div>

                <div
                  className="grid-2"
                  style={{ marginBottom: "10px", gap: "8px" }}
                >
                  <div>
                    <label className="form-label">Span Start</label>
                    <input
                      type="number"
                      className="form-input"
                      min={0}
                      value={spanStart}
                      onChange={(e) => setSpanStart(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="form-label">Span End</label>
                    <input
                      type="number"
                      className="form-input"
                      min={0}
                      value={spanEnd}
                      onChange={(e) => setSpanEnd(e.target.value)}
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  className="btn btn-secondary btn-sm"
                  style={{ width: "100%" }}
                  disabled={submittingCorrection}
                >
                  {submittingCorrection
                    ? "Submitting..."
                    : "Submit Officer Correction"}
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
