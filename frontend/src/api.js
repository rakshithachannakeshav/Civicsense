export const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

function firstFieldError(data) {
  for (const [field, messages] of Object.entries(data)) {
    if (Array.isArray(messages) && messages.length) return `${field}: ${messages[0]}`;
  }
  return "";
}

async function request(path, options) {
  const res = await fetch(`${API}${path}`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || firstFieldError(data) || `Request failed (${res.status})`);
  }
  return data;
}

export function submitComplaint({ text, location, photo }) {
  const body = new FormData();
  body.append("text", text);
  body.append("location", location);
  if (photo) body.append("photo", photo);
  return request("/api/complaints/", { method: "POST", body });
}

export const listComplaints = () => request("/api/complaints/");
export const getComplaint = (id) => request(`/api/complaints/${id}/`);
export const resolveComplaint = (id) =>
  request(`/api/complaints/${id}/resolve/`, { method: "POST" });