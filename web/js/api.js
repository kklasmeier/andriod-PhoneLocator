const STORAGE_TOKEN = "phoneLocator.token";
const STORAGE_DEVICE = "phoneLocator.deviceId";
const STORAGE_API_BASE = "phoneLocator.apiBase";

export function apiBase() {
  const stored = localStorage.getItem(STORAGE_API_BASE);
  if (stored) return stored.replace(/\/$/, "");
  const path = window.location.pathname.replace(/\/$/, "");
  if (path.endsWith("/index.html")) {
    return path.slice(0, -"/index.html".length);
  }
  return path || "";
}

export function getToken() {
  return localStorage.getItem(STORAGE_TOKEN) || "";
}

export function getDeviceId() {
  return localStorage.getItem(STORAGE_DEVICE) || "";
}

export function saveSettings({ token, deviceId, apiBase: base }) {
  if (token !== undefined) localStorage.setItem(STORAGE_TOKEN, token.trim());
  if (deviceId !== undefined) localStorage.setItem(STORAGE_DEVICE, deviceId.trim());
  if (base !== undefined) localStorage.setItem(STORAGE_API_BASE, base.trim());
}

export async function apiGet(path, params = {}) {
  const token = getToken();
  if (!token) throw new Error("API token not configured — open Settings");

  const url = new URL(apiBase() + path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });

  const response = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (response.status === 401) {
    throw new Error("Unauthorized — check API token in Settings");
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return response.json();
}

export async function apiPut(path, body, params = {}) {
  const token = getToken();
  if (!token) throw new Error("API token not configured — open Settings");

  const url = new URL(apiBase() + path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });

  const response = await fetch(url.toString(), {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }
  return response.json();
}

export function deviceParams(extra = {}) {
  const deviceId = getDeviceId();
  if (!deviceId) throw new Error("Device ID not configured — open Settings");
  return { device_id: deviceId, ...extra };
}
