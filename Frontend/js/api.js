const API_BASE = "http://127.0.0.1:8000";

async function apiFetch(url, options = {}) {
  const token = localStorage.getItem("admin_token");
  const headers = { "Content-Type": "application/json", ...options.headers };

  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(API_BASE + url, { ...options, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}
