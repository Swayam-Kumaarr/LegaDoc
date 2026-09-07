import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';

// A low-opacity background motif combining a courthouse silhouette, the
// scales of justice, and an Ashoka Chakra ring — original geometry drawn
// from scratch (not a reproduction of any photograph, artwork, or the
// State Emblem of India), in the spirit of the faint national-symbol
// watermarks most Indian government portals (eCourts, DigiLocker, MyGov)
// place behind their login copy.
function JusticeEmblemWatermark() {
  const spokes = Array.from({ length: 24 }, (_, i) => {
    const angle = (i * 360) / 24;
    const rad = (angle * Math.PI) / 180;
    const x1 = 200 + 178 * Math.cos(rad);
    const y1 = 200 + 178 * Math.sin(rad);
    const x2 = 200 + 194 * Math.cos(rad);
    const y2 = 200 + 194 * Math.sin(rad);
    return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} />;
  });

  return (
    <svg
      className="login-watermark-svg"
      viewBox="0 0 400 400"
      aria-hidden="true"
      focusable="false"
    >
      {/* Outer chakra ring, kept faint — a frame, not the focal element */}
      <g stroke="currentColor" strokeWidth="1.5" fill="none">
        <circle cx="200" cy="200" r="186" />
        <circle cx="200" cy="200" r="170" />
        {spokes}
      </g>

      {/* Courthouse: dome, entablature, columns, base steps */}
      <g fill="currentColor">
        <path d="M108 168 A92 74 0 0 1 292 168 Z" />
        <circle cx="200" cy="90" r="7" />
        <rect x="197" y="97" width="6" height="18" />
        <rect x="112" y="168" width="176" height="14" />
        {[128, 158, 188, 218, 248, 278].map((x) => (
          <rect key={x} x={x - 6} y="182" width="12" height="88" />
        ))}
        <rect x="100" y="270" width="200" height="16" />
        <rect x="84" y="286" width="232" height="14" />
        <rect x="68" y="300" width="264" height="14" />
      </g>

      {/* Scales of justice, overlapping the courthouse in front — the same
          compositional idea as the Devi Nyay statue: the scale held up in
          front of the court building behind it. */}
      <g fill="currentColor">
        <rect x="196" y="150" width="8" height="150" />
        <ellipse cx="200" cy="305" rx="26" ry="7" />
        <circle cx="200" cy="146" r="8" />
        <rect x="140" y="176" width="120" height="6" />
      </g>
      <g stroke="currentColor" strokeWidth="3" fill="none">
        <path d="M140 179 L118 224 L162 224 Z" />
        <path d="M260 179 L238 224 L282 224 Z" />
        <path d="M110 224 A30 14 0 0 0 170 224" />
        <path d="M230 224 A30 14 0 0 0 290 224" />
      </g>
    </svg>
  );
}

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const { language, setLanguage, t, supportedLanguages } = useI18n();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

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

  return (
    <div className="login-split-page">
      {/* Left Panel: Deep Navy, Serif Wordmark, Institutional Context (PRD Section 8) */}
      <div className="login-left-panel">
        <JusticeEmblemWatermark />
        <div className="login-left-branding">
          <div style={{ display: 'inline-block', marginBottom: '16px' }}>
            <span className="gov-emblem-badge">[NATIONAL LAW ENFORCEMENT PORTAL]</span>
          </div>
          <h1>Secure Digital DMS</h1>
          <p>
            Cryptographically audited electronic records, forensic evidence chain-of-custody,
            and inter-agency case docketing for state law enforcement and judicial authorities.
          </p>
        </div>

        <p className="login-legal-notice">
          Unauthorized access to this system is prohibited under the Information Technology Act, 2000.
        </p>
      </div>

      {/* Right Panel: Clean Government Form on Warm Off-White (PRD Section 8) */}
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

          <h2 className="text-heading" style={{ fontSize: '20px', marginBottom: '4px' }}>
            Sign In to Officer Portal
          </h2>
          <p className="text-caption" style={{ marginBottom: '18px' }}>
            Enter your authoritative badge number or official department email address.
          </p>

          {error && <div className="alert alert-error" role="alert">{error}</div>}

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
                placeholder="e.g. officer.rao@police.gov.in"
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
              style={{ width: '100%', marginTop: '8px' }}
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
        </div>
      </div>
    </div>
  );
}
