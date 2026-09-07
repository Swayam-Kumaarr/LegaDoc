import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiClient, setAuthToken, parseJwt } from '../api/client';

const AuthContext = createContext();

// Opt-in only, and never on by default. The offline path in `login` below
// issues a session without verifying a password, so it is a demo affordance
// for presenting with no backend — not a resilience feature. Set
// VITE_OFFLINE_DEMO_MODE=true in a local .env to enable it; leave it unset
// everywhere else.
const OFFLINE_DEMO_MODE = import.meta.env?.VITE_OFFLINE_DEMO_MODE === 'true';

export const OFFICIAL_TEST_CREDENTIALS = [
  {
    role_code: 'config_admin',
    role_label: 'Platform Administrator',
    email: 'admin.sharma@legadoc.gov.in',
    service_id: 'MHA-ADM-001',
    designation: 'Director (Information Systems)',
    department: 'Ministry of Home Affairs / NIC',
    defaultRoute: '/dashboard'
  },
  {
    role_code: 'io',
    role_label: 'Investigating Officer (IO)',
    email: 'officer.rao@police.gov.in',
    service_id: 'DL-POL-4921',
    designation: 'Inspector of Police (Cyber Cell)',
    department: 'Delhi Police Cyber Cell',
    defaultRoute: '/dashboard'
  },
  {
    role_code: 'duty_officer',
    role_label: 'Duty Officer (Station Intake)',
    email: 'duty.verma@police.gov.in',
    service_id: 'DL-POL-1084',
    designation: 'Sub-Inspector (Intake)',
    department: 'Delhi Police Central Precinct',
    defaultRoute: '/dashboard'
  },
  {
    role_code: 'court',
    role_label: 'Judicial Bench (Magistrate)',
    email: 'magistrate.iyer@court.gov.in',
    service_id: 'DEL-JUD-082',
    designation: 'Chief Judicial Magistrate',
    department: 'Patiala House District Courts',
    defaultRoute: '/dashboard'
  },
  {
    role_code: 'prosecutor',
    role_label: 'Public Prosecutor',
    email: 'prosecutor.sen@court.gov.in',
    service_id: 'DL-PROS-044',
    designation: 'Senior Public Prosecutor',
    department: 'Directorate of Prosecution',
    defaultRoute: '/dashboard'
  },
  {
    role_code: 'external_authority',
    role_label: 'Forensic Lab (FSL)',
    email: 'fsl.director@fsl.gov.in',
    service_id: 'CFSL-DIR-91',
    designation: 'Senior Scientific Officer',
    department: 'Central Forensic Science Laboratory',
    defaultRoute: '/dashboard'
  },
  {
    role_code: 'defense',
    role_label: 'Defense Counsel',
    email: 'defense.advocate@bar.in',
    service_id: 'DHC-BAR-5920',
    designation: 'Advocate-on-Record',
    department: 'Delhi High Court Bar Association',
    defaultRoute: '/dashboard'
  },
  {
    role_code: 'records_ncrb_analyst',
    role_label: 'NCRB Analyst',
    email: 'analyst.ncrb@nic.in',
    service_id: 'NCRB-STAT-21',
    designation: 'Senior Statistical Officer',
    department: 'National Crime Records Bureau',
    defaultRoute: '/dashboard'
  }
];

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Atomic state wipe on logout or authorization error (Audit Fix 4.1 #6)
  const clearAppState = () => {
    setUser(null);
    setAuthToken(null);
    localStorage.removeItem('auth_user');
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('auth_user');
  };

  useEffect(() => {
    const handleAuthError = () => {
      clearAppState();
    };
    window.addEventListener('auth-error', handleAuthError);

    // Hydrate active session
    const savedToken = sessionStorage.getItem('access_token');
    const savedUser = sessionStorage.getItem('auth_user');

    if (savedToken) {
      setAuthToken(savedToken);
      if (savedUser) {
        try {
          setUser(JSON.parse(savedUser));
        } catch (_) {}
      }
    }
    setLoading(false);

    return () => window.removeEventListener('auth-error', handleAuthError);
  }, []);

  // Authenticate against authoritative server endpoint
  const login = async ({ email, password }) => {
    try {
      const response = await apiClient('/auth/login', { body: { email, password } });
      if (response && response.access_token) {
        setAuthToken(response.access_token);
        sessionStorage.setItem('access_token', response.access_token);

        // Fetch authoritative profile and permission claims from /auth/me
        let profile = null;
        try {
          profile = await apiClient('/auth/me');
        } catch (_) {
          // Fallback to JWT claims if /auth/me temporarily degraded
          const claims = parseJwt(response.access_token) || {};
          profile = {
            id: claims.sub,
            name: email.split('@')[0],
            email,
            role: claims.role,
            org_id: claims.org_id,
            service_id: 'GOV-SEC-ID',
            designation: 'Officer',
            permissions: []
          };
        }

        const authoritativeUser = {
          id: profile.id,
          name: profile.name || email.split('@')[0],
          email: profile.email,
          service_id: profile.service_id || 'GOV-SEC-ID',
          designation: profile.designation || 'Authorized Officer',
          role: profile.role,
          org_id: profile.org_id,
          org_name: profile.org_name || 'Government Organization',
          org_type: profile.org_type || 'official',
          language_preference: profile.language_preference || 'en',
          permissions: profile.permissions || []
        };

        setUser(authoritativeUser);
        sessionStorage.setItem('auth_user', JSON.stringify(authoritativeUser));
        return { success: true, role: authoritativeUser.role };
      }
      throw new Error("Invalid authentication response");
    } catch (error) {
      // Offline demo mode. Two gates, both required — without either, this
      // block is an authentication bypass, not a fallback:
      //
      // 1. OFFLINE_DEMO_MODE must be explicitly opted into at build time. It
      //    is off by default, so no real deployment can reach this path.
      // 2. The failure must be a genuine transport failure. apiClient only
      //    attaches `.status` to errors built from an HTTP response
      //    (handleApiError); a fetch that never got a response throws a plain
      //    Error with no status. Without this check a 401 "Invalid email or
      //    password" also lands here — which meant any wrong password was
      //    silently upgraded into a session for whichever persona was typed.
      //
      // This path never verifies a password and grants a caller-chosen role,
      // so it must stay unreachable outside a deliberate offline demo build.
      const isTransportFailure = error?.status === undefined;
      if (!OFFLINE_DEMO_MODE || !isTransportFailure) {
        return { success: false, error: error.message || 'Authentication failed' };
      }

      const matched = OFFICIAL_TEST_CREDENTIALS.find(
        (c) => c.email.toLowerCase() === email.toLowerCase() || c.service_id.toLowerCase() === email.toLowerCase()
      );
      if (matched && password) {
        const offlineToken = `gov-auth-token-${matched.role_code}`;
        setAuthToken(offlineToken);
        sessionStorage.setItem('access_token', offlineToken);

        const authoritativeUser = {
          id: `usr-${matched.role_code}`,
          name: matched.designation.split('(')[0].trim(),
          email: matched.email,
          service_id: matched.service_id,
          designation: matched.designation,
          role: matched.role_code,
          org_id: `org-${matched.role_code}`,
          org_name: matched.department,
          org_type: 'official',
          language_preference: 'en',
          permissions: ['cases:read', 'documents:read']
        };

        setUser(authoritativeUser);
        sessionStorage.setItem('auth_user', JSON.stringify(authoritativeUser));
        return { success: true, role: authoritativeUser.role };
      }

      return { success: false, error: error.message || 'Authentication failed' };
    }
  };

  const logout = async () => {
    try {
      await apiClient('/auth/logout', { method: 'POST' });
    } catch (_) {
    } finally {
      clearAppState();
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', color: '#94a3b8' }}>
        Loading session...
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, testCredentials: OFFICIAL_TEST_CREDENTIALS }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
