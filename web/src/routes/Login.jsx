import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';

// Famous GeeksforGeeks Run-Length Encoded India Map String
// Reference: https://www.geeksforgeeks.org/cpp/code-to-generate-the-map-of-india-with-explanation/
const GFG_ENCODED_STR =
  "TFy!QJu ROo TNn(ROo)SLq SLq ULo+UHs UJq " +
  "TNn*RPn/QPbEWS_JSWQAIJO^NBELPeHBFHT}TnALVlBL" +
  "OFAkHFOuFETpHCStHAUFAgcEAelclcn^r^r\\tZvYxXyT|S~Pn SPm " +
  "SOn TNn ULo0ULo#ULo-WHq!WFs XDt!";

function decodeGfgIndiaMap() {
  let a = 10, b = 0, c = 10;
  const dots = [];
  let row = 0;
  let col = 0;

  while (b < GFG_ENCODED_STR.length) {
    a = GFG_ENCODED_STR.charCodeAt(b++);
    while (a-- > 64) {
      if (++c === 90) {
        c = 10;
        row++;
        col = 0;
      } else {
        if (b % 2 === 0) {
          // '!' represents land mass in the GfG C algorithm
          // Scale to SVG viewBox (0 0 380 430)
          const cx = col * 4.6 + 18;
          const cy = row * 8.6 + 16;
          const r = (col + row) % 7 === 0 ? 1.5 : 1.1;
          dots.push({
            cx: Number(cx.toFixed(1)),
            cy: Number(cy.toFixed(1)),
            r
          });
        }
        col++;
      }
    }
  }
  return dots;
}

// Precompute India Map dot coordinates once at module load time
const GFG_DOTS = decodeGfgIndiaMap();

// Regional judicial nodes (Delhi, Mumbai, Kolkata, Chennai) mapped on GfG grid
const REGIONAL_NODES = [
  { name: 'DEL (North)', x: 165, y: 128 },
  { name: 'BOM (West)',  x: 110, y: 231 },
  { name: 'CCU (East)',  x: 257, y: 205 },
  { name: 'MAA (South)', x: 165, y: 334 },
];

const NODE_ARCS = [
  { from: 0, to: 1, d: 'M 165 128 Q 115 160 110 231', delay: '0s' },
  { from: 0, to: 2, d: 'M 165 128 Q 220 150 257 205', delay: '0.8s' },
  { from: 1, to: 3, d: 'M 110 231 Q 120 295 165 334', delay: '1.6s' },
  { from: 2, to: 3, d: 'M 257 205 Q 225 280 165 334', delay: '2.4s' },
];

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, testCredentials } = useAuth();
  const { language, setLanguage, t, supportedLanguages } = useI18n();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showTestDrawer, setShowTestDrawer] = useState(false);


  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = await login({ email: identifier, password });
    setLoading(false);

    if (result.success) {
      navigate('/dashboard', { replace: true });
    } else {
      setError(result.error || "Authentication failed. Please verify your government credentials.");
    }
  };

  const handleSelectTestAccount = (acc) => {
    setIdentifier(acc.email);
    setPassword('GovSecure@2026');
    setError(null);
  };

  return (
    <div className="login-split-page">
      {/* ================= LEFT PANEL (Institutional Sovereign Dark Theme) ================= */}
      <div className="left">
        <h1 className="title">
          Secure Digital Document<br />Management System
        </h1>

        <p className="desc">
          Cryptographically audited electronic case records, forensic evidence
          chain-of-custody, and inter-agency case docketing for state law
          enforcement and judicial authorities.
        </p>

        {/* Authentic India Dot Map via GeeksforGeeks C Run-Length Algorithm */}
        <div className="map-wrap">
            <svg className="india-map" viewBox="0 0 380 430" xmlns="http://www.w3.org/2000/svg">
              {/* GfG Algorithm Dot Layer */}
              <g id="dotLayer" fill="#334155">
                {GFG_DOTS.map((d, i) => (
                  <circle key={i} cx={d.cx} cy={d.cy} r={d.r} />
                ))}
              </g>

              {/* Regional Hub Nodes with Pulse Animation & Labels */}
              <g id="nodeLayer">
                {REGIONAL_NODES.map((n, i) => (
                  <g key={i}>
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={3.4}
                      fill="#38BDF8"
                      className="node-pulse"
                    />
                    <circle
                      cx={n.x}
                      cy={n.y}
                      r={7}
                      fill="none"
                      stroke="#38BDF8"
                      strokeWidth={0.8}
                      opacity={0.4}
                    />
                  </g>
                ))}
                {/* Node Geographical Labels matching reference */}
                <text x={152} y={124} textAnchor="end" fill="#93C5FD" fontSize="10" fontWeight="500" fontFamily="var(--font-sans)">
                  Delhi NCR
                </text>
                <text x={152} y={340} textAnchor="end" fill="#93C5FD" fontSize="10" fontWeight="500" fontFamily="var(--font-sans)">
                  Bengaluru
                </text>
              </g>

              {/* Inter-Node Ledger Sync Arcs */}
              <g id="arcLayer" fill="none" stroke="#38BDF8" strokeWidth={1}>
                {NODE_ARCS.map((arc, i) => (
                  <path
                    key={i}
                    d={arc.d}
                    className="arc-path"
                    style={{ animationDelay: arc.delay }}
                  />
                ))}
              </g>
            </svg>
          </div>

        {/* --- Statutory Slogans & Regulatory Chips --- */}
        <div className="mt-4 pt-4 border-t border-slate-700/60 flex flex-col items-center text-center space-y-3 max-w-lg mx-auto authority-slogan-section">
          {/* Judicial Slogan & Statutory Anchor */}
          <div className="space-y-1">
            <p className="text-base font-serif tracking-wide text-amber-200/90 font-medium">
              "यतो धर्मस्ततो जयः"
            </p>
            <p className="text-xs text-slate-400 max-w-sm leading-relaxed">
              Securing admissible judicial custody across State Police Directorates, Forensic Laboratories, and High Court registries.
            </p>
          </div>



        </div>
      </div>

      {/* ================= RIGHT PANEL (Restrained Government Authentication Form) ================= */}
      <div className="login-right-panel">
        <div className="login-card">
          {/* Header & Language Selection */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <span className="text-label" style={{ fontSize: '11px' }}>
              Official Identity Verification
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <label htmlFor="login-lang-select" className="text-caption" style={{ fontWeight: 600 }}>
                {t('choose_language', 'Lang')}:
              </label>
              <select
                id="login-lang-select"
                className="form-select"
                style={{ width: 'auto', height: '26px', fontSize: '11px', padding: '1px 22px 1px 6px' }}
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {supportedLanguages.map(l => (
                  <option key={l.code} value={l.code}>{l.native} ({l.label})</option>
                ))}
              </select>
            </div>
          </div>

          <h2 className="text-heading" style={{ fontSize: '22px', marginBottom: '6px' }}>
            Sign In to Officer Portal
          </h2>
          <p className="text-caption" style={{ marginBottom: '20px' }}>
            Enter your authoritative badge number or official department email address. Access is logged and audited.
          </p>

          {error && <div className="alert alert-error" role="alert">{error}</div>}

          {/* --- Security Clearance Advisory (Place above input fields) --- */}
          <div className="flex gap-2.5 p-3 mb-5 rounded-md border border-amber-200 bg-amber-50 text-amber-900 text-left">
            <svg className="h-4 w-4 text-amber-700 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <p className="text-[11px] leading-relaxed text-amber-800">
              <strong className="font-semibold text-amber-900">Official Access Only:</strong> All access attempts are cryptographically stamped and logged. Unauthorized access is punishable under <span className="font-medium">Sec. 66 IT Act</span>.
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="badge-identifier">
                Badge ID / Official Email <span className="form-required">*</span>
              </label>
              <input
                id="badge-identifier"
                type="text"
                className="form-input"
                placeholder="officer.rao@police.gov.in"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
                autoComplete="username"
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="auth-password">
                Authentication Secret <span className="form-required">*</span>
              </label>
              <input
                id="auth-password"
                type="password"
                className="form-input"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', marginTop: '14px', padding: '10px' }}
              disabled={loading}
            >
              {loading ? 'Verifying Authoritative Credentials...' : 'Sign In & Authorize'}
            </button>

            <div style={{ marginTop: '14px', textAlign: 'center' }}>
              <span className="text-caption">
                Credential issues? Contact your{' '}
                <span style={{ color: 'var(--color-text-secondary)', textDecoration: 'underline', cursor: 'pointer' }}>
                  Precinct Systems Administrator
                </span>
              </span>
            </div>
          </form>

          {/* Official Pre-Registered Identities Drawer */}
          <div style={{ marginTop: '20px', paddingTop: '14px', borderTop: '1px solid var(--color-border)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="text-label" style={{ fontSize: '11px', color: 'var(--color-text-primary)' }}>
                Pre-Registered Official Personas
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setShowTestDrawer(!showTestDrawer)}
              >
                {showTestDrawer ? 'Hide Personas' : 'Show Personas'}
              </button>
            </div>

            {showTestDrawer && (
              <div style={{ marginTop: '12px' }}>
                <p className="text-caption" style={{ marginBottom: '8px' }}>
                  Select an official role to populate authoritative credentials:
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '200px', overflowY: 'auto' }}>
                  {testCredentials.map((acc) => (
                    <div
                      key={acc.email}
                      onClick={() => handleSelectTestAccount(acc)}
                      style={{
                        padding: '6px 10px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--color-border)',
                        background: 'var(--color-surface-subtle)',
                        cursor: 'pointer',
                        fontSize: '11px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, color: 'var(--color-text-primary)' }}>
                          {acc.designation}
                        </div>
                        <div style={{ color: 'var(--color-text-secondary)', fontSize: '10px', fontFamily: 'var(--font-mono)' }}>
                          {acc.service_id} · {acc.email}
                        </div>
                      </div>
                      <span className="status-chip status-chip-neutral" style={{ fontSize: '9px', padding: '1px 5px' }}>
                        {acc.role_label}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>



        </div>
      </div>
    </div>
  );
}

