import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiClient, setAuthToken, parseJwt } from '../api/client';

const AuthContext = createContext();

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
          permissions: profile.permissions || [],
          must_change_password: profile.must_change_password || false
        };

        setUser(authoritativeUser);
        sessionStorage.setItem('auth_user', JSON.stringify(authoritativeUser));
        return { success: true, role: authoritativeUser.role };
      }
      throw new Error("Invalid authentication response");
    } catch (error) {
      // Authentication is decided by the backend only — a network error, a
      // wrong password (401), or an unreachable API must always fail here.
      // This used to fall back to a client-side match against a hardcoded
      // credential list and mint a fake token for ANY non-empty password,
      // which was a real authentication bypass (any of the well-known demo
      // emails + garbage password succeeded whenever the backend call
      // failed for any reason, including a genuine wrong-password 401).
      return { success: false, error: error.detail || error.message || 'Authentication failed' };
    }
  };

  // Re-fetches the authoritative profile and updates local state — used
  // after a forced password change clears must_change_password, so the
  // gate lifts without requiring a full re-login.
  const refreshProfile = async () => {
    try {
      const profile = await apiClient('/auth/me');
      setUser((prev) => {
        const updated = { ...(prev || {}), ...profile };
        sessionStorage.setItem('auth_user', JSON.stringify(updated));
        return updated;
      });
    } catch (_) {
      // Leave existing state as-is on failure — this is a refresh, not a
      // login; a transient error here shouldn't clear a valid session.
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
    <AuthContext.Provider value={{ user, login, logout, refreshProfile }}>
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
