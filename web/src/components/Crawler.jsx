import React, { useState } from "react";
import { startCrawlJob } from "../api/crawler";
import HashCell from "./HashCell";

/**
 * Crawler component – Legal Evidence & Public Records Crawler
 * Crawls e-Courts, CCTNS notices, ICJS dockets and statutory registries for case corroboration.
 */
export default function Crawler() {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("ecourts");
  const [status, setStatus] = useState("idle"); // idle | loading | success | error
  const [data, setData] = useState([]);
  const [error, setError] = useState(null);

  const handleStartCrawl = async (e) => {
    if (e) e.preventDefault();
    setStatus("loading");
    setError(null);
    try {
      const response = await startCrawlJob({ query, source });
      setData(response?.results ?? []);
      setStatus("success");
    } catch (err) {
      setError(
        err?.message ||
          "Crawling operation failed. Please check network connectivity.",
      );
      setStatus("error");
    }
  };

  return (
    <div className="card" style={{ padding: "20px" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: "16px",
        }}
      >
        <div>
          <h2
            className="card-title"
            style={{ margin: 0, padding: 0, border: "none" }}
          >
            Public Legal Gazette & e-Courts Evidence Crawler
          </h2>
          <p className="text-caption" style={{ marginTop: "4px" }}>
            Automated intelligence retrieval across CCTNS, e-Courts, ICJS
            repository, and gazette cause lists.
          </p>
        </div>
        <span
          className="gov-status-chip"
          style={{
            background: "rgba(15, 41, 74, 0.08)",
            color: "var(--color-brand)",
          }}
        >
          CRAWLER MODULE ACTIVE
        </span>
      </div>

      <form
        onSubmit={handleStartCrawl}
        style={{
          display: "flex",
          gap: "12px",
          flexWrap: "wrap",
          marginBottom: "20px",
        }}
      >
        <div style={{ flex: "1 1 280px" }}>
          <label className="text-label" htmlFor="crawler-query-input">
            Search Term / FIR / Case Citation
          </label>
          <input
            id="crawler-query-input"
            type="text"
            className="form-input"
            placeholder="e.g. State vs. Kumar, Section 420, CrPC 173..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={status === "loading"}
          />
        </div>

        <div style={{ width: "200px" }}>
          <label className="text-label" htmlFor="crawler-source-select">
            Target Legal Source
          </label>
          <select
            id="crawler-source-select"
            className="form-select"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            disabled={status === "loading"}
          >
            <option value="ecourts">e-Courts National Portal</option>
            <option value="gazette">Judicial Gazette / Cause List</option>
            <option value="icjs">ICJS Integrated Records</option>
            <option value="mca21">MCA21 Corporate Registry</option>
          </select>
        </div>

        <div style={{ display: "flex", alignItems: "flex-end" }}>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={status === "loading"}
            style={{ height: "38px" }}
          >
            {status === "loading"
              ? "Querying Judicial Dockets..."
              : "Search Docket Index"}
          </button>
        </div>
      </form>

      {status === "loading" && (
        <div
          style={{
            padding: "30px",
            textAlign: "center",
            background: "var(--color-surface-subtle)",
            borderRadius: "var(--radius)",
          }}
        >
          <div className="spinner" style={{ margin: "0 auto 12px" }} />
          <div className="text-body" style={{ fontWeight: 600 }}>
            Querying national judicial dockets and gazette databases...
          </div>
          <div className="text-caption">
            Retrieving digitally signed case records and verified electronic
            court orders
          </div>
        </div>
      )}

      {status === "error" && (
        <div className="alert alert-error" style={{ marginBottom: "16px" }}>
          <strong>Crawl Error:</strong> {error}
        </div>
      )}

      {status === "success" && data.length === 0 && (
        <div
          style={{
            padding: "24px",
            textAlign: "center",
            color: "var(--color-text-secondary)",
          }}
        >
          No records or matching gazette dockets found for query: &quot;{query}
          &quot;
        </div>
      )}

      {status === "success" && data.length > 0 && (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Record ID</th>
                <th>Source Portal</th>
                <th>Case Reference / Title</th>
                <th>Filing Date</th>
                <th>Relevant Section</th>
                <th>Integrity Hash</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.id}>
                  <td
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "12px",
                      fontWeight: 600,
                    }}
                  >
                    {item.id}
                  </td>
                  <td>{item.source}</td>
                  <td style={{ fontWeight: 500 }}>{item.title}</td>
                  <td
                    style={{
                      fontSize: "12px",
                      color: "var(--color-text-secondary)",
                    }}
                  >
                    {item.filing_date}
                  </td>
                  <td>
                    <span
                      className="gov-status-chip"
                      style={{ fontSize: "11px" }}
                    >
                      {item.matched_section}
                    </span>
                  </td>
                  <td>
                    <HashCell hash={item.hash} />
                  </td>
                  <td>
                    <span
                      style={{
                        display: "inline-block",
                        padding: "2px 8px",
                        borderRadius: "12px",
                        fontSize: "11px",
                        fontWeight: 600,
                        background: "rgba(16, 185, 129, 0.12)",
                        color: "#065f46",
                      }}
                    >
                      {item.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
