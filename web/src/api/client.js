// Same-origin by default: '/api' is proxied to the FastAPI service by the dev
// server (see web/vite.config.js) or by whatever fronts the app in a real
// deployment. This must not be an absolute http://localhost URL — that
// resolves on the *viewer's* machine, so the app breaks for anyone not
// running the API themselves (a tunnelled demo, a teammate, a phone on the
// LAN). Set VITE_API_BASE only when the API genuinely lives on another origin.
const API_BASE = import.meta.env?.VITE_API_BASE ?? '/api';

let inMemoryToken = null;
let inMemoryRefreshToken = null;

export function setAuthToken(token) {
  inMemoryToken = token;
}

export function getAuthToken() {
  return inMemoryToken;
}

export function setRefreshToken(token) {
  inMemoryRefreshToken = token;
}

// Endpoints whose 401 means "these credentials are wrong", not "the session
// expired" — refreshing on them would be meaningless, and on /auth/refresh
// itself would recurse.
const NO_REFRESH_ENDPOINTS = new Set(['/auth/login', '/auth/refresh']);

// One refresh at a time. When a screen fires several requests together and
// they all 401 at once, every one of them awaits this same promise instead of
// each spending the refresh token separately.
let refreshInFlight = null;

// Exchanges the refresh token for a new access token. Resolves to the new
// token, or null when there is no refresh token or the server refuses it
// (expired after 7 days, or the user was removed).
function refreshAccessToken() {
  if (!inMemoryRefreshToken) return Promise.resolve(null);
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: inMemoryRefreshToken }),
          credentials: 'include',
        });
        if (!response.ok) return null;
        const data = await response.json();
        if (!data || !data.access_token) return null;
        inMemoryToken = data.access_token;
        // AuthContext hydrates from this key on reload, so a refreshed session
        // must survive a page refresh just like the original one did.
        try {
          sessionStorage.setItem('access_token', data.access_token);
        } catch {
          // Storage can be unavailable (private mode); the in-memory token
          // still carries this tab.
        }
        return data.access_token;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export function parseJwt(token) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

// Builds an Error that keeps the real backend response attached (status +
// parsed detail), instead of collapsing every failure into one generic
// string. Callers that need to react to a specific case — a 409's
// missing_items list, a 403's reason — read err.status / err.detail. The
// generic .message stays as a safe default for callers that just want
// something to display without checking status.
function handleApiError(response, bodyText) {
  console.error(`API Error: ${response.status} ${response.statusText}`, bodyText);
  let parsedDetail = bodyText;
  try {
    const parsed = JSON.parse(bodyText);
    parsedDetail = parsed.detail !== undefined ? parsed.detail : parsed;
  } catch {
    // Not JSON — keep the raw text as the detail.
  }
  const detailMessage = typeof parsedDetail === 'string'
    ? parsedDetail
    : (parsedDetail && typeof parsedDetail === 'object' && parsedDetail.message)
      ? parsedDetail.message
      : 'An error occurred while communicating with the server. Please verify your credentials or permissions.';
  const err = new Error(detailMessage);
  err.status = response.status;
  err.detail = parsedDetail;
  return err;
}

export async function apiClient(endpoint, options = {}) {
  return request(endpoint, options, false);
}

async function request(endpoint, options, isRetry) {
  const { body, ...customConfig } = options;
  const headers = {
    ...customConfig.headers,
  };

  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  if (inMemoryToken) {
    headers['Authorization'] = `Bearer ${inMemoryToken}`;
  }

  const csrfToken = sessionStorage.getItem('csrf_token');
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }

  const config = {
    method: body ? 'POST' : 'GET',
    ...customConfig,
    headers,
    credentials: 'include',
  };

  if (body) {
    config.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, config);
  } catch (error) {
    console.error("Network error:", error);
    throw new Error("Unable to connect to the server. Please check that the API service is running.");
  }

  if (response.ok) {
    if (response.status === 204) return null;
    return await response.json();
  } else {
    let errDetail = '';
    try {
      errDetail = await response.text();
    } catch (_) {}

    // A 401 on an ordinary request almost always means the 15-minute access
    // token expired, not that the user's session is over — the 7-day refresh
    // token is still good. Before this, the first request after 15 minutes
    // logged the user out mid-flow, which in a demo reads as a random crash
    // (issue #88). Refresh once, replay the original request with the new
    // token, and only end the session if the refresh itself is refused.
    //
    // isRetry caps this at one attempt, so a request that still 401s with a
    // fresh token (e.g. a revoked account) cannot loop.
    if (response.status === 401 && !isRetry && !NO_REFRESH_ENDPOINTS.has(endpoint)) {
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        return request(endpoint, options, true);
      }
    }

    // Only a 401 means the session itself is invalid — clear it and force
    // re-login. A 403 means the session is fine but this specific action
    // isn't permitted for this role; logging the user out on every
    // permission-denied response (e.g. a duty_officer hitting an
    // admin-only endpoint) was wiping out a perfectly valid session over
    // an action that was correctly rejected.
    //
    // Not dispatched for /auth/login: a wrong password is not a session to
    // end, and clearing state there would wipe the form's own context.
    if (response.status === 401 && endpoint !== '/auth/login') {
      window.dispatchEvent(new Event('auth-error'));
    }
    throw handleApiError(response, errDetail);
  }
}

export async function apiUpload(endpoint, formData) {
  return apiClient(endpoint, {
    method: 'POST',
    body: formData,
  });
}
