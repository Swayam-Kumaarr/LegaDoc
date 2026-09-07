import React, { useState } from 'react';
import { apiClient } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

function formatError(err) {
  const detail = err?.detail;
  if (typeof detail === 'string') return detail;
  return err?.message || 'Request failed.';
}

// Blocking overlay shown when the logged-in account has
// must_change_password === true (set on every onboarding-approved account,
// which starts on a temporary password only the approving admin has seen).
// Nothing else in the app is reachable until this clears.
export default function ForcedPasswordChange() {
  const { user, logout, refreshProfile } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError('New password and confirmation do not match.');
      return;
    }
    setSubmitting(true);
    try {
      await apiClient('/auth/change-password', {
        body: { current_password: currentPassword, new_password: newPassword },
      });
      await refreshProfile();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(11, 37, 71, 0.7)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 2000, padding: '20px',
      }}
    >
      <div className="card" style={{ maxWidth: '440px', width: '100%', padding: '28px' }}>
        <h2 style={{ marginTop: 0 }}>Set a New Password</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '16px' }}>
          {user?.name ? `${user.name}, your` : 'Your'} account was just provisioned with a temporary
          password. You must set your own before continuing.
        </p>

        {error && <div className="alert alert-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Temporary Password</label>
            <input
              type="password"
              className="form-input"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">New Password</label>
            <input
              type="password"
              className="form-input"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Confirm New Password</label>
            <input
              type="password"
              className="form-input"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={submitting}>
              {submitting ? 'Updating...' : 'Set Password'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={logout}>
              Sign Out
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
