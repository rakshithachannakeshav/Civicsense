export const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

const TOKEN_KEY = "civicsense_token";

// Storage can be blocked (private windows, site settings), so never let it throw.
export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

// App registers a handler so any 401 sends the user back to the login screen.
let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

function firstFieldError(data) {
  for (const [field, messages] of Object.entries(data)) {
    if (Array.isArray(messages) && messages.length) return `${field}: ${messages[0]}`;
  }
  return "";
}

async function request(path, options = {}) {
  const headers = { ...(options.headers ?? {}) };
  const token = getToken();
  if (token) headers.Authorization = `Token ${token}`;

  const res = await fetch(`${API}${path}`, { ...options, headers });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && token) onUnauthorized();
  if (!res.ok) {
    throw new Error(data.detail || firstFieldError(data) || `Request failed (${res.status})`);
  }
  return data;
}

const json = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// Accounts
export const login = (username, password) => request("/api/auth/login/", json({ username, password }));
export const register = (username, email, password) =>
  request("/api/auth/register/", json({ username, email, password }));
export const logout = () => request("/api/auth/logout/", { method: "POST" });
export const getMe = () => request("/api/auth/me/");

// Complaints
export function submitComplaint({ text, location, photo, coords }) {
  const body = new FormData();
  body.append("text", text);
  body.append("location", location);
  if (photo) body.append("photo", photo);
  if (coords) {
    body.append("device_lat", coords.lat);
    body.append("device_lng", coords.lng);
  }
  return request("/api/complaints/", { method: "POST", body });
}

export const listComplaints = () => request("/api/complaints/");
export const getComplaint = (id) => request(`/api/complaints/${id}/`);
export const resolveComplaint = (id) =>
  request(`/api/complaints/${id}/resolve/`, { method: "POST" });
