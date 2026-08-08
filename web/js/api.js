const STORAGE_TOKEN = "phoneLocator.token";
const STORAGE_DEVICE = "phoneLocator.deviceId";
const STORAGE_API_BASE = "phoneLocator.apiBase";

function pathFromLocation() {
  const path = window.location.pathname.replace(/\/$/, "");
  if (path.endsWith("/index.html")) {
    return path.slice(0, -"/index.html".length) || "";
  }
  return path;
}

function resolveApiBase() {
  const stored = (localStorage.getItem(STORAGE_API_BASE) || "").trim().replace(/\/$/, "");
  const fromPage = pathFromLocation();

  if (!stored) return fromPage;

  // Always prefer a relative base so another device uses its own host/port.
  if (stored.startsWith("/")) return stored;

  try {
    const parsed = new URL(stored);
    if (parsed.origin === window.location.origin) {
      return parsed.pathname.replace(/\/$/, "") || fromPage;
    }
  } catch {
    // ignore invalid stored value
  }

  return fromPage;
}

export function apiBase() {
  return resolveApiBase();
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
  if (base !== undefined) {
    const trimmed = base.trim().replace(/\/$/, "");
    if (trimmed) localStorage.setItem(STORAGE_API_BASE, trimmed);
    else localStorage.removeItem(STORAGE_API_BASE);
  }
}

function dashboardPath() {
  const path = pathFromLocation();
  return path || "/";
}

export function buildSetupUrl() {
  const token = getToken();
  const deviceId = getDeviceId();
  if (!token || !deviceId) return null;

  const params = new URLSearchParams();
  params.set("token", token);
  params.set("device", deviceId);

  return `${window.location.origin}${dashboardPath()}/#/setup?${params.toString()}`;
}

/** Apply credentials from a one-time #/setup?... link, then strip them from the URL. */
export function consumeSetupParams() {
  const hash = window.location.hash.replace(/^#/, "");
  const qIndex = hash.indexOf("?");
  if (qIndex === -1) return false;

  const route = hash.slice(0, qIndex);
  if (route !== "/setup") return false;

  const params = new URLSearchParams(hash.slice(qIndex + 1));
  const token = params.get("token");
  const device = params.get("device");
  if (!token || !device) return false;

  saveSettings({
    token,
    deviceId: device,
    apiBase: "",
  });

  const cleanPath = window.location.pathname + window.location.search;
  window.history.replaceState(null, "", `${cleanPath}#/`);
  return true;
}

function buildApiUrl(path, params = {}) {
  const base = apiBase();
  const url = new URL(`${base}${path}`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, value);
    }
  });
  return url;
}

async function request(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);

  try {
    return await fetch(url.toString(), { ...options, signal: controller.signal });
  } catch (err) {
    const reason = err?.name === "AbortError" ? "timed out" : err?.message || "network error";
    throw new Error(
      `Cannot reach API (${reason}). Check VPN/Wi‑Fi, iOS Local Network access for Safari, then Settings → Test connection.`
    );
  } finally {
    clearTimeout(timeout);
  }
}

export async function apiGet(path, params = {}) {
  const token = getToken();
  if (!token) throw new Error("API token not configured — open Settings");

  const url = buildApiUrl(path, params);
  const response = await request(url, {
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

  const url = buildApiUrl(path, params);
  const response = await request(url, {
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

export async function apiPost(path, body = {}, params = {}) {
  const token = getToken();
  if (!token) throw new Error("API token not configured — open Settings");

  const url = buildApiUrl(path, params);
  const response = await request(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
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

export function deviceParams(extra = {}) {
  const deviceId = getDeviceId();
  if (!deviceId) throw new Error("Device ID not configured — open Settings");
  return { device_id: deviceId, ...extra };
}
