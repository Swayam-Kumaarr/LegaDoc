import React, { useState, useEffect } from "react";
import { Routes, Route, NavLink, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext.jsx";
import { I18nProvider, useI18n } from "./contexts/I18nContext.jsx";
import StatusBanner from "./components/StatusBanner.jsx";
import Login from "./routes/Login.jsx";
import Dashboard from "./routes/Dashboard.jsx";

import PoliceInvestigation from "./routes/PoliceInvestigation.jsx";
import CaseDetail from "./routes/CaseDetail.jsx";
import DocumentViewer from "./routes/DocumentViewer.jsx";
import ChargeSheetFiling from "./routes/ChargeSheetFiling.jsx";
import NeedsReviewQueue from "./routes/NeedsReviewQueue.jsx";
import ExternalAuthority from "./routes/ExternalAuthority.jsx";
import Judiciary from "./routes/Judiciary.jsx";
import DefenseAccused from "./routes/DefenseAccused.jsx";
import RecordsReporting from "./routes/RecordsReporting.jsx";
import PlatformAdmin from "./routes/PlatformAdmin.jsx";

function PrivateRoute({ children, allowedRoles }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && allowedRoles.length > 0) {
    const role = user.role?.toLowerCase();
    const isAllowed = allowedRoles.some(r => r.toLowerCase() === role);
    if (!isAllowed) {
      return <Navigate to="/dashboard" replace />;
    }
  }

  return children;
}

function MainLayout() {
  const { user, logout } = useAuth();
  const { language, setLanguage, t, supportedLanguages } = useI18n();
  const location = useLocation();

  // Dark Mode Theme Management (PRD Section 3.3)
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('legadoc-theme') || 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('legadoc-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => (prev === 'light' ? 'dark' : 'light'));
  };

  const isLoginPage = location.pathname === "/login";
  const role = user?.role?.toLowerCase() || '';

  // Role-scoped navigation definition per Requirement 5
  const isPolice = ['duty_officer', 'io', 'sho', 'police', 'cyber_cell', 'narcotics_police'].includes(role);
  const isCourt = role === 'court';
  const isProsecutor = role === 'prosecutor';
  const isAuthority = role === 'external_authority';
  const isDefense = role === 'defense';
  const isAdmin = ['config_admin', 'security_auditor', 'admin'].includes(role);
  const isNCRB = role === 'records_ncrb_analyst';

  return (
    <div className="app-layout">
      {/* Top Institutional Header (PRD Section 3.1 & 8) */}
      <header className="gov-masthead">
        <div className="gov-masthead-left">
          <span className="gov-emblem-badge">[{t('official_system', 'Official System')}]</span>
          <div>
            <div className="gov-system-title">{t('gov_title', 'Government of India · Secure Digital DMS')}</div>
            <span className="gov-system-subtitle">{t('gov_subtitle', 'SIH26190 · Hyperledger Fabric Cryptographic Ledger')}</span>
          </div>
        </div>

        <div className="gov-masthead-right">
          {/* Language Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <label style={{ fontSize: '11px', color: '#BAC2CC', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.03em' }}>
              {t('choose_language', 'Lang')}:
            </label>
            <select
              className="form-select"
              style={{
                width: 'auto',
                height: '28px',
                fontSize: '11px',
                padding: '2px 24px 2px 8px',
                background: 'rgba(255,255,255,0.12)',
                color: '#ffffff',
                borderColor: 'rgba(255,255,255,0.3)',
                borderRadius: 'var(--radius)'
              }}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              aria-label="Select Official Interface Language"
            >
              {supportedLanguages.map(l => (
                <option key={l.code} value={l.code} style={{ background: '#0B2547', color: '#ffffff' }}>
                  {l.native} ({l.label})
                </option>
              ))}
            </select>
          </div>

          {/* Theme Toggle Button (Section 3.3) */}
          <button
            type="button"
            className="theme-toggle-btn"
            onClick={toggleTheme}
            title={`Switch to ${theme === 'light' ? 'Dark' : 'Light'} Mode`}
            aria-label="Toggle Theme"
          >
            {theme === 'light' ? 'Dark Theme' : 'Light Theme'}
          </button>

          {/* User Profile & Sign Out */}
          {user ? (
            <>
              <div className="gov-user-id-box">
                <span className="gov-user-name">
                  {user.name || user.email}
                </span>
                <span className="gov-user-badge">
                  {user.service_id || user.role?.toUpperCase()}
                </span>
              </div>
              <button className="gov-logout-btn" onClick={logout} title="Clear session and sign out">
                {t('sign_out', 'Sign Out')}
              </button>
            </>
          ) : (
            !isLoginPage && (
              <NavLink to="/login" className="gov-logout-btn" style={{ textDecoration: 'none' }}>
                {t('sign_in', 'Sign In')}
              </NavLink>
            )
          )}
        </div>
      </header>

      {/* Network / Offline Health Monitor */}
      <StatusBanner />

      {/* Login Screen: Dedicated Full Viewport Split Panel */}
      {isLoginPage ? (
        <main style={{ flex: 1 }}>
          <Routes>
            <Route path="/login" element={<Login />} />
          </Routes>
        </main>
      ) : (
        /* Authenticated Two-Panel Layout (Section 5: Left Sidebar + Full-width Content) */
        <div className="app-body">
          {user && (
            <aside className="gov-sidebar" aria-label="Official Navigation Sidebar">
              <div className="sidebar-section-title">Navigation Hub</div>
              <nav className="sidebar-nav-list">
                <NavLink to="/dashboard" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="3" y="3" width="7" height="7"></rect>
                    <rect x="14" y="3" width="7" height="7"></rect>
                    <rect x="14" y="14" width="7" height="7"></rect>
                    <rect x="3" y="14" width="7" height="7"></rect>
                  </svg>
                  <span>{t('nav_dashboard', 'Dashboard Hub')}</span>
                </NavLink>

                {/* Police & Investigation Links */}
                {(isPolice || isAdmin) && (
                  <>
                    <div className="sidebar-section-title">Law Enforcement</div>
                    <NavLink to="/cases" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                      </svg>
                      <span>{t('nav_cases', 'Case Registry & FIR')}</span>
                    </NavLink>
                    <NavLink to="/review-queue" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
                        <rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect>
                      </svg>
                      <span>{t('nav_review_queue', 'Needs-Review Queue')}</span>
                    </NavLink>
                  </>
                )}

                {/* Prosecution Links */}
                {isProsecutor && (
                  <>
                    <div className="sidebar-section-title">Prosecution</div>
                    <NavLink to="/cases" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                      </svg>
                      <span>{t('nav_cases', 'Prosecutor Case Review')}</span>
                    </NavLink>
                  </>
                )}

                {/* Judicial Bench Links */}
                {(isCourt || isAdmin || isProsecutor) && (
                  <>
                    <div className="sidebar-section-title">Judicial Bench</div>
                    <NavLink to="/judiciary" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                        <polyline points="2 17 12 22 22 17"></polyline>
                        <polyline points="2 12 12 17 22 12"></polyline>
                      </svg>
                      <span>{t('nav_judiciary', 'Magistrate Court Portal')}</span>
                    </NavLink>
                  </>
                )}

                {/* External Requisitions */}
                {(isAuthority || isAdmin) && (
                  <>
                    <div className="sidebar-section-title">Nodal Authorities</div>
                    <NavLink to="/authority" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                      </svg>
                      <span>{t('nav_authority', 'Section 91 Requisitions')}</span>
                    </NavLink>
                  </>
                )}

                {/* Defense Counsel */}
                {(isDefense || isAdmin) && (
                  <>
                    <div className="sidebar-section-title">Defense Counsel</div>
                    <NavLink to="/defense" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="9" cy="7" r="4"></circle>
                      </svg>
                      <span>{t('nav_defense', 'Defense Counsel Gateway')}</span>
                    </NavLink>
                  </>
                )}

                {/* NCRB Reporting */}
                {(isNCRB || isAdmin) && (
                  <>
                    <div className="sidebar-section-title">Reporting & Intelligence</div>
                    <NavLink to="/reports" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="20" x2="18" y2="10"></line>
                        <line x1="12" y1="20" x2="12" y2="4"></line>
                        <line x1="6" y1="20" x2="6" y2="14"></line>
                      </svg>
                      <span>{t('nav_reports', 'NCRB Statistical Analytics')}</span>
                    </NavLink>
                  </>
                )}

                {/* Platform Governance */}
                {isAdmin && (
                  <>
                    <div className="sidebar-section-title">System Administration</div>
                    <NavLink to="/admin" className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="3"></circle>
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                      </svg>
                      <span>{t('nav_admin', 'RBAC & Audit Governance')}</span>
                    </NavLink>
                  </>
                )}
              </nav>
            </aside>
          )}

          <div className="app-content-wrapper">
            <main style={{ flex: 1 }}>
              <Routes>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                
                <Route path="/dashboard" element={
                  <PrivateRoute>
                    <Dashboard />
                  </PrivateRoute>
                } />

                <Route path="/cases" element={
                  <PrivateRoute allowedRoles={['duty_officer', 'io', 'sho', 'police', 'cyber_cell', 'narcotics_police', 'prosecutor', 'config_admin', 'security_auditor', 'admin']}>
                    <PoliceInvestigation />
                  </PrivateRoute>
                } />

                <Route path="/cases/:id" element={
                  <PrivateRoute>
                    <CaseDetail />
                  </PrivateRoute>
                } />

                <Route path="/cases/:id/documents/:docId" element={
                  <PrivateRoute>
                    <DocumentViewer />
                  </PrivateRoute>
                } />

                <Route path="/cases/:id/charge-sheet" element={
                  <PrivateRoute allowedRoles={['io', 'sho', 'prosecutor', 'config_admin', 'admin']}>
                    <ChargeSheetFiling />
                  </PrivateRoute>
                } />

                <Route path="/review-queue" element={
                  <PrivateRoute allowedRoles={['duty_officer', 'io', 'sho', 'police', 'cyber_cell', 'narcotics_police', 'config_admin', 'admin']}>
                    <NeedsReviewQueue />
                  </PrivateRoute>
                } />

                <Route path="/authority" element={
                  <PrivateRoute allowedRoles={['external_authority', 'config_admin', 'admin']}>
                    <ExternalAuthority />
                  </PrivateRoute>
                } />

                <Route path="/judiciary" element={
                  <PrivateRoute allowedRoles={['court', 'prosecutor', 'config_admin', 'admin']}>
                    <Judiciary />
                  </PrivateRoute>
                } />

                <Route path="/defense" element={
                  <PrivateRoute allowedRoles={['defense', 'config_admin', 'admin']}>
                    <DefenseAccused />
                  </PrivateRoute>
                } />

                <Route path="/reports" element={
                  <PrivateRoute allowedRoles={['records_ncrb_analyst', 'config_admin', 'admin']}>
                    <RecordsReporting />
                  </PrivateRoute>
                } />

                <Route path="/admin" element={
                  <PrivateRoute allowedRoles={['config_admin', 'security_auditor', 'admin']}>
                    <PlatformAdmin />
                  </PrivateRoute>
                } />

                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </main>

            <footer className="gov-footer">
              <div className="gov-footer-content">
                <div>
                  <strong>Ministry of Home Affairs & Department of Justice</strong> · Government of India
                </div>
                <div style={{ color: '#9AA4B2' }}>
                  SIH26190 · Cryptographically Bound Hash Ledger v2.4 · GIGW / USWDS Accessible
                </div>
              </div>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <I18nProvider>
        <MainLayout />
      </I18nProvider>
    </AuthProvider>
  );
}
