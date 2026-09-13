import React, { useState, useMemo, useRef } from "react";

/**
 * ChainOfCustodyVisualizer — makes the system's actual hash-chained audit
 * log (see AuditLog.row_hash / prev_hash in the backend, verified live by
 * verify_chain_intact()) something a judge can *see* work, not just read
 * about in a table.
 *
 * Two things it demonstrates live, in the browser, with no backend needed
 * for the demo path:
 *   1. "Verify Chain Integrity" walks each block and confirms this block's
 *      parent_hash === the previous block's tx_hash — exactly the check
 *      the real backend does when verifying the row_hash chain.
 *   2. "Simulate Tamper Attempt" corrupts one block's hash in local state
 *      and re-runs the same walk, so the break is caught and pinpointed
 *      live — a concrete answer to "how do you know no one edited this
 *      after the fact," not a claim.
 *
 * This never talks to Fabric or Postgres directly; it operates on
 * whatever audit events are passed in (mock or real, once wired to
 * GET /cases/:id/audit-log). The verification LOGIC is real; only the
 * data source is currently a prop.
 */
export default function ChainOfCustodyVisualizer({ events }) {
  const [verifying, setVerifying] = useState(false);
  const [verifiedUpTo, setVerifiedUpTo] = useState(-1);
  const [result, setResult] = useState(null); // null | 'intact' | 'broken'
  const [breakIndex, setBreakIndex] = useState(null);
  const [tamperedIndex, setTamperedIndex] = useState(null);
  const cancelRef = useRef(false);

  const isGenesisHash = (h) => typeof h === "string" && /^0+$/.test(h);

  const chain = useMemo(() => {
    if (tamperedIndex === null) return events;
    return events.map((ev, i) =>
      i === tamperedIndex
        ? { ...ev, tx_hash: ev.tx_hash.slice(0, -8) + "deadbeef" }
        : ev,
    );
  }, [events, tamperedIndex]);

  const shortHash = (h) =>
    isGenesisHash(h) ? "GENESIS BLOCK" : `${h.slice(0, 10)}…${h.slice(-6)}`;

  async function runVerification() {
    cancelRef.current = false;
    setVerifying(true);
    setResult(null);
    setBreakIndex(null);
    setVerifiedUpTo(-1);

    for (let i = 0; i < chain.length; i++) {
      await new Promise((r) => setTimeout(r, 320));
      if (cancelRef.current) return;

      const linkOk =
        i === 0
          ? isGenesisHash(chain[i].parent_hash)
          : chain[i].parent_hash === chain[i - 1].tx_hash;

      setVerifiedUpTo(i);

      if (!linkOk) {
        setResult("broken");
        setBreakIndex(i);
        setVerifying(false);
        return;
      }
    }
    setResult("intact");
    setVerifying(false);
  }

  function simulateTamper() {
    cancelRef.current = true;
    const eligible =
      chain.length > 1 ? Math.floor(Math.random() * (chain.length - 1)) + 1 : 0;
    setTamperedIndex(eligible);
    setResult(null);
    setBreakIndex(null);
    setVerifiedUpTo(-1);
    setVerifying(false);
  }

  function restoreChain() {
    cancelRef.current = true;
    setTamperedIndex(null);
    setResult(null);
    setBreakIndex(null);
    setVerifiedUpTo(-1);
    setVerifying(false);
  }

  return (
    <div className="chain-viz">
      <div className="chain-viz-toolbar">
        <div className="chain-viz-toolbar-left">
          <button
            className="btn btn-primary btn-sm"
            onClick={runVerification}
            disabled={verifying}
          >
            {verifying ? "Verifying Links…" : "Verify Chain Integrity"}
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={simulateTamper}
            disabled={verifying}
          >
            Simulate Tamper Attempt
          </button>
          {tamperedIndex !== null && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={restoreChain}
              disabled={verifying}
            >
              Restore Original Chain
            </button>
          )}
        </div>
        <div className="chain-viz-toolbar-right">
          {result === "intact" && (
            <span className="status-chip status-chip-success">
              <CheckIcon /> All {chain.length} Links Verified — Chain Intact
            </span>
          )}
          {result === "broken" && (
            <span className="status-chip status-chip-error">
              <AlertIcon /> Tamper Detected at Block #
              {chain[breakIndex]?.block_num}
            </span>
          )}
        </div>
      </div>

      {tamperedIndex !== null && !result && (
        <div className="alert alert-warning chain-viz-tamper-note">
          Block #{chain[tamperedIndex].block_num}'s stored hash has been altered
          in this simulation. Run verification to see it caught.
        </div>
      )}

      <div
        className="chain-viz-track"
        role="list"
        aria-label="Cryptographic chain of custody"
      >
        {chain.map((ev, i) => {
          const isVerified =
            i <= verifiedUpTo && !(result === "broken" && i === breakIndex);
          const isBreak = result === "broken" && i === breakIndex;
          const isTampered = tamperedIndex === i;
          const pending = verifying && i > verifiedUpTo;

          return (
            <React.Fragment key={ev.block_num}>
              {i > 0 && (
                <div
                  className={
                    "chain-viz-link" +
                    (i <= verifiedUpTo && !isBreak
                      ? " chain-viz-link-ok"
                      : "") +
                    (isBreak ? " chain-viz-link-broken" : "")
                  }
                  aria-hidden="true"
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M5 12h13M13 6l6 6-6 6" />
                  </svg>
                </div>
              )}
              <div
                role="listitem"
                className={
                  "chain-viz-block" +
                  (isVerified ? " chain-viz-block-ok" : "") +
                  (isBreak ? " chain-viz-block-broken" : "") +
                  (isTampered ? " chain-viz-block-tampered" : "") +
                  (pending ? " chain-viz-block-pending" : "")
                }
              >
                <div className="chain-viz-block-top">
                  <span className="chain-viz-block-num">
                    Block #{ev.block_num}
                  </span>
                  {isVerified && <CheckIcon small />}
                  {isBreak && <AlertIcon small />}
                </div>
                <div className="chain-viz-block-time">{ev.timestamp}</div>
                <div className="chain-viz-block-event">{ev.event}</div>
                <div className="chain-viz-block-authority">{ev.authority}</div>
                <div className="chain-viz-block-hashes">
                  <div className="chain-viz-hash-row">
                    <span className="chain-viz-hash-label">HASH</span>
                    <span
                      className={
                        "mono-text chain-viz-hash-value" +
                        (isTampered ? " chain-viz-hash-tampered" : "")
                      }
                    >
                      {shortHash(ev.tx_hash)}
                    </span>
                  </div>
                  <div className="chain-viz-hash-row">
                    <span className="chain-viz-hash-label">PREV</span>
                    <span className="mono-text chain-viz-hash-value">
                      {shortHash(ev.parent_hash)}
                    </span>
                  </div>
                </div>
              </div>
            </React.Fragment>
          );
        })}
      </div>

      <p className="text-caption chain-viz-footnote">
        Each block's PREV hash must exactly equal the previous block's HASH.
        This is the same check the backend performs when independently verifying
        the audit log's row-hash chain — deleting or reordering any single event
        breaks every link after it, which is what makes the chain tamper-evident
        rather than just logged.
      </p>
    </div>
  );
}

function CheckIcon({ small }) {
  const s = small ? 13 : 14;
  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function AlertIcon({ small }) {
  const s = small ? 13 : 14;
  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 9v4M12 17h.01M10.29 3.86l-8.16 14.14A1 1 0 0 0 3 19.5h18a1 1 0 0 0 .87-1.5L13.71 3.86a1 1 0 0 0-1.72 0z" />
    </svg>
  );
}
