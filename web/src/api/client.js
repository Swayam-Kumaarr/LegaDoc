const API_BASE = (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_URL) || 'http://localhost:8000';


let inMemoryToken = null;

export function setAuthToken(token) {
  inMemoryToken = token;
}

export function getAuthToken() {
  return inMemoryToken;
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

// Global error handler for generic messages (Audit Fix #7)
function handleApiError(response, bodyText) {
  console.error(`API Error: ${response.status} ${response.statusText}`, bodyText);
  return new Error("An error occurred while communicating with the server. Please verify your credentials or permissions.");
}

export async function apiClient(endpoint, { body, ...customConfig } = {}) {
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

    if (response.status === 401 || response.status === 403) {
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
