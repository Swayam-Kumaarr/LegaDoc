import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../contexts/I18nContext';

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
      {/* Left Panel: Deep Navy, Serif Wordmark, Institutional Context (PRD Section 8) */}
      <div className="login-left-panel">
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

        <div className="login-institutional-docket">
          <div className="login-docket-row">
            <span>Statutory Authority</span>
            <strong>Section 173 CrPC / BNSS 2023</strong>
          </div>
          <div className="login-docket-row">
            <span>Cryptographic Proof Engine</span>
            <strong>SHA-256 Fabric Ledger</strong>
          </div>
          <div className="login-docket-row">
            <span>Access Control Model</span>
            <strong>Authoritative RBAC Level-4</strong>
          </div>
          <div className="login-docket-row">
            <span>Verification Standard</span>
            <strong>Section 65B Indian Evidence Act</strong>
          </div>
        </div>
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

          {/* Official Pre-Registered Identities Drawer (Section 6.4) */}
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
