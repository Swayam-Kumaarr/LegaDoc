import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  SEEDED_ACCOUNTS,
  SEEDED_ACCOUNT_PASSWORD,
} from "../dev/seededAccounts";

// Internal-only convenience page for demoing locally — never linked from the
// public /login screen. It still authenticates through AuthContext's real
// login(), which only succeeds via a genuine POST /auth/login; this page
// just saves typing the seeded demo password for each role. Registered only
// when running the Vite dev server (see App.jsx) so it never ships in a
// production build.
export default function DevLogin() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [pending, setPending] = useState(null);
  const [error, setError] = useState(null);

  const handleLogin = async (acc) => {
    setPending(acc.email);
    setError(null);
    const result = await login({
      email: acc.email,
      password: SEEDED_ACCOUNT_PASSWORD,
    });
    setPending(null);
    if (result.success) {
      navigate("/dashboard", { replace: true });
    } else {
      setError(`${acc.email}: ${result.error || "Login failed"}`);
    }
  };

  return (
    <div
      style={{
        maxWidth: "640px",
        margin: "48px auto",
        padding: "0 20px",
        fontFamily: "var(--font-mono, monospace)",
      }}
    >
      <div
        style={{
          background: "#7a1f1f",
          color: "white",
          padding: "10px 14px",
          borderRadius: "4px",
          marginBottom: "20px",
          fontSize: "13px",
        }}
      >
        DEV-ONLY TOOL — not part of the production login flow. Requires a
        running backend with seed data loaded (see scripts/setup.sh).
      </div>
      <h1 style={{ fontSize: "18px", marginBottom: "4px" }}>
        Quick Login — Seeded Demo Accounts
      </h1>
      <p style={{ fontSize: "13px", color: "#666", marginBottom: "16px" }}>
        Each entry submits the real login form against the backend using the
        shared seed password. This is a typing shortcut, not an authentication
        bypass.
      </p>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: "12px" }}>
          {error}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {SEEDED_ACCOUNTS.map((acc) => (
          <button
            key={acc.email}
            onClick={() => handleLogin(acc)}
            disabled={pending !== null}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "10px 12px",
              border: "1px solid #ccc",
              borderRadius: "4px",
              background: pending === acc.email ? "#eee" : "white",
              cursor: pending ? "default" : "pointer",
              fontSize: "12px",
              textAlign: "left",
            }}
          >
            <span>
              <strong>{acc.role_label}</strong>
              <br />
              <span style={{ color: "#666" }}>
                {acc.designation} · {acc.email}
              </span>
            </span>
            <span>{pending === acc.email ? "Signing in..." : "Sign In →"}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
