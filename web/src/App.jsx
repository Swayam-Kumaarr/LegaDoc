import React, { useState, useEffect } from "react";
import {
  Routes,
  Route,
  NavLink,
  Navigate,
  useLocation,
} from "react-router-dom";
import emblemImg from "./assets/emblem.png";
import watermarkNavy from "./assets/emblem_watermark_navy.png";
import watermarkSilver from "./assets/emblem_watermark_silver.png";
import { AuthProvider, useAuth } from "./contexts/AuthContext.jsx";
import { I18nProvider, useI18n } from "./contexts/I18nContext.jsx";
import StatusBanner from "./components/StatusBanner.jsx";
import ForcedPasswordChange from "./components/ForcedPasswordChange.jsx";
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
import OfficerOnboarding from "./routes/OfficerOnboarding.jsx";
import CrawlerRoute from "./routes/CrawlerRoute.jsx";
// Dev-only quick-login helper — only imported/registered in the Vite dev
// server, never bundled into a production build. See routes/DevLogin.jsx.
const DevLogin = import.meta.env.DEV
  ? React.lazy(() => import("./routes/DevLogin.jsx"))
  : null;

function PrivateRoute({ children, allowedRoles }) {
  const { user } = useAuth();
  const location = useLocation();

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (allowedRoles && allowedRoles.length > 0) {
    const role = user.role?.toLowerCase();
    const isAllowed = allowedRoles.some((r) => r.toLowerCase() === role);
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
    return localStorage.getItem("legadoc-theme") || "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("legadoc-theme", theme);
  }, [theme]);

  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  const isLoginPage =
    location.pathname === "/login" || location.pathname === "/dev-login";
  const role = user?.role?.toLowerCase() || "";

  // Role-scoped navigation definition per Requirement 5
  const isPolice = [
    "duty_officer",
    "io",
    "sho",
    "police",
    "cyber_cell",
    "narcotics_police",
  ].includes(role);
  const isCourt = role === "court";
  const isProsecutor = role === "prosecutor";
  const isAuthority = role === "external_authority";
  const isDefense = role === "defense";
  const isAdmin = ["config_admin", "security_auditor", "admin"].includes(role);
  const isNCRB = role === "records_ncrb_analyst";

  return (
    <div className="app-layout">
      {/* Top Institutional Header */}
      <header className="gov-masthead">
        <div className="gov-masthead-left">
          {user && !isLoginPage && (
            <button
              type="button"
              className="gov-mobile-menu-btn"
              onClick={() => setSidebarOpen((prev) => !prev)}
              aria-label="Toggle navigation menu"
              title="Toggle Navigation Menu"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="3" y1="12" x2="21" y2="12"></line>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <line x1="3" y1="18" x2="21" y2="18"></line>
              </svg>
            </button>
          )}
          <img
            src={emblemImg}
            alt="State Emblem of India"
            className="gov-emblem-img"
          />
          <div className="gov-system-title">
            {t("gov_title", "Government of India · Secure Digital DMS")}
          </div>
        </div>

        <div className="gov-masthead-right">
          {/* Language Selector */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <label
              style={{
                fontSize: "11px",
                color: "#BAC2CC",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.03em",
              }}
            >
              {t("choose_language", "Lang")}:
            </label>
            <select
              className="form-select"
              style={{
                width: "auto",
                height: "28px",
                fontSize: "11px",
                padding: "2px 24px 2px 8px",
                background: "rgba(255,255,255,0.12)",
                color: "#ffffff",
                borderColor: "rgba(255,255,255,0.3)",
                borderRadius: "var(--radius)",
              }}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              aria-label="Select Official Interface Language"
            >
              {supportedLanguages.map((l) => (
                <option
                  key={l.code}
                  value={l.code}
                  style={{ background: "#0F294A", color: "#ffffff" }}
                >
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
            title={`Switch to ${theme === "light" ? "Dark" : "Light"} Mode`}
            aria-label="Toggle Theme"
          >
            {theme === "light" ? "Dark Theme" : "Light Theme"}
          </button>

          {/* User Profile & Sign Out */}
          {user ? (
            <>
              <div className="gov-user-id-box">
                <span className="gov-user-name">{user.name || user.email}</span>
                <span className="gov-user-badge">
                  {user.service_id || user.role?.toUpperCase()}
                </span>
              </div>
              <button
                className="gov-logout-btn"
                onClick={logout}
                title="Clear session and sign out"
              >
                {t("sign_out", "Sign Out")}
              </button>
            </>
          ) : (
            !isLoginPage && (
              <NavLink
                to="/login"
                className="gov-logout-btn"
                style={{ textDecoration: "none" }}
              >
                {t("sign_in", "Sign In")}
              </NavLink>
            )
          )}
        </div>
      </header>

      {/* Authentic Indian Government Tricolor Stripe */}
      <div className="gov-tricolor-stripe" aria-hidden="true" />

      {/* Network / Offline Health Monitor */}
      <StatusBanner />

      {/* Blocking gate for a freshly-onboarded account still on its
          one-time temporary password — see components/ForcedPasswordChange.jsx */}
      {user && user.must_change_password && !isLoginPage && (
        <ForcedPasswordChange />
      )}

      {/* Login Screen: Dedicated Full Viewport Split Panel */}
      {isLoginPage ? (
        <main style={{ flex: 1 }}>
          <Routes>
            <Route path="/login" element={<Login />} />
            {DevLogin && (
              <Route
                path="/dev-login"
                element={
                  <React.Suspense fallback={null}>
                    <DevLogin />
                  </React.Suspense>
                }
              />
            )}
          </Routes>
        </main>
      ) : (
        /* Authenticated Two-Panel Layout (Section 5: Left Sidebar + Full-width Content) */
        <div className="app-body">
          {user && (
            <>
              {sidebarOpen && (
                <div
                  className="gov-sidebar-backdrop"
                  onClick={() => setSidebarOpen(false)}
                  aria-hidden="true"
                />
              )}
              <aside
                className={`gov-sidebar ${sidebarOpen ? "open" : ""}`}
                aria-label="Official Navigation Sidebar"
              >
                <div className="sidebar-scrollable-content">
                  <div className="sidebar-section-title">
                    <span>मुख्य पृष्ठ • DASHBOARD</span>
                  </div>
                  <nav className="sidebar-nav-list">
                    <NavLink
                      to="/dashboard"
                      className={({ isActive }) =>
                        "sidebar-nav-item" + (isActive ? " active" : "")
                      }
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <rect x="3" y="3" width="7" height="7"></rect>
                        <rect x="14" y="3" width="7" height="7"></rect>
                        <rect x="14" y="14" width="7" height="7"></rect>
                        <rect x="3" y="14" width="7" height="7"></rect>
                      </svg>
                      <span>{t("nav_dashboard", "Dashboard Hub")}</span>
                    </NavLink>

                    {/* Police & Investigation Links */}
                    {(isPolice || isAdmin) && (
                      <div className="sidebar-group-divider">
                        <div className="sidebar-section-title">
                          <span>विधि प्रवर्तन • POLICE</span>
                        </div>
                        <NavLink
                          to="/cases"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                            <polyline points="14 2 14 8 20 8"></polyline>
                          </svg>
                          <span>{t("nav_cases", "Case Registry & FIR")}</span>
                          <span className="sidebar-badge sidebar-badge-slate">
                            14
                          </span>
                        </NavLink>
                        <NavLink
                          to="/review-queue"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path>
                            <rect
                              x="8"
                              y="2"
                              width="8"
                              height="4"
                              rx="1"
                              ry="1"
                            ></rect>
                          </svg>
                          <span>
                            {t("nav_review_queue", "Needs-Review Queue")}
                          </span>
                          <span className="sidebar-badge sidebar-badge-amber">
                            3
                          </span>
                        </NavLink>
                      </div>
                    )}

                    {/* Prosecution Links */}
                    {isProsecutor && (
                      <div className="sidebar-group-divider">
                        <div className="sidebar-section-title">
                          <span>अभियोजन • PROSECUTION</span>
                        </div>
                        <NavLink
                          to="/cases"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                          </svg>
                          <span>
                            {t("nav_cases", "Prosecutor Case Review")}
                          </span>
                        </NavLink>
                      </div>
                    )}

                    {/* Judicial Bench Links */}
                    {(isCourt || isAdmin || isProsecutor) && (
                      <div className="sidebar-group-divider">
                        <div className="sidebar-section-title">
                          <span>न्यायिक पीठ • JUDICIARY</span>
                        </div>
                        <NavLink
                          to="/judiciary"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
                            <polyline points="2 17 12 22 22 17"></polyline>
                            <polyline points="2 12 12 17 22 12"></polyline>
                          </svg>
                          <span>
                            {t("nav_judiciary", "Magistrate Court Portal")}
                          </span>
                        </NavLink>
                      </div>
                    )}

                    {/* External Requisitions */}
                    {(isAuthority || isAdmin) && (
                      <div className="sidebar-group-divider">
                        <div className="sidebar-section-title">
                          <span>नोडल प्राधिकरण • AGENCIES</span>
                        </div>
                        <NavLink
                          to="/authority"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="12" y1="8" x2="12" y2="12"></line>
                            <line x1="12" y1="16" x2="12.01" y2="16"></line>
                          </svg>
                          <span>
                            {t("nav_authority", "Section 91 Requisitions")}
                          </span>
                        </NavLink>
                      </div>
                    )}

                    {/* Defense Counsel */}
                    {(isDefense || isAdmin) && (
                      <div className="sidebar-group-divider">
                        <div className="sidebar-section-title">
                          <span>विधिक बचाव • COUNSEL</span>
                        </div>
                        <NavLink
                          to="/defense"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                          </svg>
                          <span>
                            {t("nav_defense", "Defense Counsel Gateway")}
                          </span>
                        </NavLink>
                      </div>
                    )}

                    {/* NCRB Reporting */}
                    {(isNCRB || isAdmin) && (
                      <div className="sidebar-group-divider">
                        <div className="sidebar-section-title">
                          <span>सांख्यिकी • INTELLIGENCE</span>
                        </div>
                        <NavLink
                          to="/reports"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <line x1="18" y1="20" x2="18" y2="10"></line>
                            <line x1="12" y1="20" x2="12" y2="4"></line>
                            <line x1="6" y1="20" x2="6" y2="14"></line>
                          </svg>
                          <span>
                            {t("nav_reports", "NCRB Statistical Analytics")}
                          </span>
                        </NavLink>
                        <NavLink
                          to="/crawler"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <circle cx="11" cy="11" r="8"></circle>
                            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                          </svg>
                          <span>
                            {t("nav_crawler", "Legal Records Crawler")}
                          </span>
                        </NavLink>
                      </div>
                    )}

                    {/* Platform Governance */}
                    {isAdmin && (
                      <div className="sidebar-group-divider">
                        <div className="sidebar-section-title">
                          <span>प्रणाली प्रबंधन • ADMIN</span>
                        </div>
                        <NavLink
                          to="/admin"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <circle cx="12" cy="12" r="3"></circle>
                            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                          </svg>
                          <span>
                            {t("nav_admin", "RBAC & Audit Governance")}
                          </span>
                        </NavLink>
                        <NavLink
                          to="/onboarding"
                          className={({ isActive }) =>
                            "sidebar-nav-item" + (isActive ? " active" : "")
                          }
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          >
                            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                            <path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                          </svg>
                          <span>Officer Onboarding</span>
                        </NavLink>
                      </div>
                    )}
                  </nav>
                </div>
              </aside>
            </>
          )}

          <div className="app-content-wrapper">
            {/* Authentic Sovereign Ashok Stambh Watermark for All Application Pages */}
            <div className="app-bg-watermark" aria-hidden="true">
              <img
                className="watermark-img watermark-light"
                src={watermarkNavy}
                alt=""
              />
              <img
                className="watermark-img watermark-dark"
                src={watermarkSilver}
                alt=""
              />
            </div>
            <main style={{ flex: 1, position: "relative", zIndex: 1 }}>
              <Routes>
                <Route
                  path="/"
                  element={<Navigate to="/dashboard" replace />}
                />

                <Route
                  path="/dashboard"
                  element={
                    <PrivateRoute>
                      <Dashboard />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/cases"
                  element={
                    <PrivateRoute
                      allowedRoles={[
                        "duty_officer",
                        "io",
                        "sho",
                        "police",
                        "cyber_cell",
                        "narcotics_police",
                        "prosecutor",
                        "config_admin",
                        "security_auditor",
                        "admin",
                      ]}
                    >
                      <PoliceInvestigation />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/cases/:id"
                  element={
                    <PrivateRoute>
                      <CaseDetail />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/cases/:id/documents/:docId"
                  element={
                    <PrivateRoute>
                      <DocumentViewer />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/cases/:id/charge-sheet"
                  element={
                    <PrivateRoute
                      allowedRoles={[
                        "io",
                        "sho",
                        "prosecutor",
                        "config_admin",
                        "admin",
                      ]}
                    >
                      <ChargeSheetFiling />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/review-queue"
                  element={
                    <PrivateRoute
                      allowedRoles={[
                        "duty_officer",
                        "io",
                        "sho",
                        "police",
                        "cyber_cell",
                        "narcotics_police",
                        "config_admin",
                        "admin",
                      ]}
                    >
                      <NeedsReviewQueue />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/authority"
                  element={
                    <PrivateRoute
                      allowedRoles={[
                        "external_authority",
                        "config_admin",
                        "admin",
                      ]}
                    >
                      <ExternalAuthority />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/judiciary"
                  element={
                    <PrivateRoute
                      allowedRoles={[
                        "court",
                        "prosecutor",
                        "config_admin",
                        "admin",
                      ]}
                    >
                      <Judiciary />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/defense"
                  element={
                    <PrivateRoute
                      allowedRoles={["defense", "config_admin", "admin"]}
                    >
                      <DefenseAccused />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/reports"
                  element={
                    <PrivateRoute
                      allowedRoles={[
                        "records_ncrb_analyst",
                        "config_admin",
                        "admin",
                      ]}
                    >
                      <RecordsReporting />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/admin"
                  element={
                    <PrivateRoute
                      allowedRoles={[
                        "config_admin",
                        "security_auditor",
                        "admin",
                      ]}
                    >
                      <PlatformAdmin />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/onboarding"
                  element={
                    <PrivateRoute allowedRoles={["config_admin", "admin"]}>
                      <OfficerOnboarding />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="/crawler"
                  element={
                    <PrivateRoute>
                      <CrawlerRoute />
                    </PrivateRoute>
                  }
                />

                <Route
                  path="*"
                  element={<Navigate to="/dashboard" replace />}
                />
              </Routes>
            </main>

            <footer className="gov-footer">
              <div className="gov-footer-content">
                <div>
                  <strong>
                    Ministry of Home Affairs & Department of Justice
                  </strong>{" "}
                  · Government of India
                </div>
                <div style={{ color: "#9AA4B2" }}>
                  SIH26190 · Cryptographically Bound Hash Ledger v2.4 · GIGW /
                  USWDS Accessible
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
