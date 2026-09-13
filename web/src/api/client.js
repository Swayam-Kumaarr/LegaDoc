// Same-origin by default: '/api' is proxied to the FastAPI service by the dev
// server (see web/vite.config.js) or by whatever fronts the app in a real
// deployment. This must not be an absolute http://localhost URL — that
// resolves on the *viewer's* machine, so the app breaks for anyone not
// running the API themselves (a tunnelled demo, a teammate, a phone on the
// LAN). Set VITE_API_BASE only when the API genuinely lives on another origin.
const API_BASE = import.meta.env?.VITE_API_BASE ?? "/api";

let inMemoryToken = null;

export function setAuthToken(token) {
  inMemoryToken = token;
}

export function getAuthToken() {
  return inMemoryToken;
}

export function parseJwt(token) {
  try {
    const base64Url = token.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join(""),
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
  console.error(
    `API Error: ${response.status} ${response.statusText}`,
    bodyText,
  );
  let parsedDetail = bodyText;
  try {
    const parsed = JSON.parse(bodyText);
    parsedDetail = parsed.detail !== undefined ? parsed.detail : parsed;
  } catch {
    // Not JSON — keep the raw text as the detail.
  }
  const detailMessage =
    typeof parsedDetail === "string"
      ? parsedDetail
      : parsedDetail && typeof parsedDetail === "object" && parsedDetail.message
        ? parsedDetail.message
        : "An error occurred while communicating with the server. Please verify your credentials or permissions.";
  const err = new Error(detailMessage);
  err.status = response.status;
  err.detail = parsedDetail;
  return err;
}

export async function apiClient(endpoint, { body, ...customConfig } = {}) {
  const headers = {
    ...customConfig.headers,
  };

  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  if (inMemoryToken) {
    headers["Authorization"] = `Bearer ${inMemoryToken}`;
  }

  const csrfToken = sessionStorage.getItem("csrf_token");
  if (csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const config = {
    method: body ? "POST" : "GET",
    ...customConfig,
    headers,
    credentials: "include",
  };

  if (body) {
    config.body = body instanceof FormData ? body : JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, config);
  } catch (error) {
    console.error("Network error:", error);
    throw new Error(
      "Unable to connect to the server. Please check that the API service is running.",
    );
  }

  if (response.ok) {
    if (response.status === 204) return null;
    return await response.json();
  } else {
    let errDetail = "";
    try {
      errDetail = await response.text();
    } catch {
      // Ignore text decoding failure
    }

    // Only a 401 means the session itself is invalid — clear it and force
    // re-login. A 403 means the session is fine but this specific action
    // isn't permitted for this role; logging the user out on every
    // permission-denied response (e.g. a duty_officer hitting an
    // admin-only endpoint) was wiping out a perfectly valid session over
    // an action that was correctly rejected.
    if (response.status === 401) {
      window.dispatchEvent(new Event("auth-error"));
    }
    throw handleApiError(response, errDetail);
  }
}

export async function apiUpload(endpoint, formData) {
  return apiClient(endpoint, {
    method: "POST",
    body: formData,
  });
}
