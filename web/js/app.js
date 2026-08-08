import { apiGet, apiPost, apiPut, buildSetupUrl, consumeSetupParams, deviceParams, getDeviceId, getToken, saveSettings } from "./api.js";
import { destroyMap, fitTrail, initMap, renderTrail } from "./map.js";
import { getDashboardParams, getRange, initPeriodBar, localDateKey } from "./period.js";
import { APP_VERSION } from "./version.js";
import {
  escapeHtml,
  formatDaySeparator,
  formatDistance,
  formatDuration,
  formatSpeed,
  formatTime,
  formatTimeShort,
  maxDuration,
  relativeTime,
} from "./utils.js";

const appEl = document.getElementById("app");
const bannerEl = document.getElementById("banner");
const footerEl = document.getElementById("site-footer");

function setFooter(text) {
  if (footerEl) footerEl.textContent = text;
}

function setFooterStatus(extra = "") {
  const tokenOk = getToken() ? "token ✓" : "no token";
  const deviceOk = getDeviceId() ? "device ✓" : "no device";
  const suffix = extra ? ` · ${extra}` : "";
  setFooter(`Phone Locator v${APP_VERSION} · ${tokenOk} · ${deviceOk}${suffix}`);
}

setFooter(`Phone Locator v${APP_VERSION} · starting…`);

initPeriodBar(() => navigate());

function setBanner(message, kind = "info") {
  if (!message) {
    bannerEl.className = "banner hidden";
    bannerEl.textContent = "";
    return;
  }
  bannerEl.className = `banner ${kind}`;
  bannerEl.textContent = message;
}

function setActiveNav(route) {
  document.querySelectorAll("#main-nav a").forEach((link) => {
    link.classList.toggle("active", link.dataset.route === route);
  });
}

function showError(err) {
  const msg = err?.message || String(err);
  setBanner(null);
  if (msg.includes("Settings")) {
    appEl.innerHTML = `<div class="empty">${escapeHtml(msg)}<br/><br/><a href="#/settings">Open Settings</a></div>`;
  } else {
    appEl.innerHTML = `
      <div class="empty">
        <p><strong>Could not load this page</strong></p>
        <p>${escapeHtml(msg)}</p>
        <p style="margin-top:1rem"><a href="#/settings">Open Settings</a> · <button type="button" id="retry-load">Retry</button></p>
      </div>`;
    document.getElementById("retry-load")?.addEventListener("click", () => navigate());
  }
}

async function renderHome() {
  setActiveNav("/");
  appEl.innerHTML = `<div class="loading">Loading dashboard…</div>`;

  const data = await apiGet("/api/v1/stats/dashboard", deviceParams(getDashboardParams()));
  const { latest, summary, status, stale_minutes: staleMinutes } = data;

  if (status === "stale") {
    setBanner(`Stale — last reading ${staleMinutes} min ago`, "warn");
  } else if (status === "no_data") {
    setBanner("No recent location data", "error");
  } else {
    setBanner(null);
  }

  const statusClass = status === "ok" ? "ok" : status === "stale" ? "warn" : "error";
  const topPlace = summary.top_places?.[0]?.name || "Unknown";
  const battery = latest?.battery_pct != null ? `${latest.battery_pct}%` : "—";
  const batterySub = latest?.battery_charging ? "charging" : "not charging";
  const accuracy = latest?.accuracy_m != null ? `±${Math.round(latest.accuracy_m)} m` : "—";

  const maxBar = maxDuration(summary.top_places || []);
  const bars = (summary.top_places || [])
    .map(
      (p) => `
      <div class="bar-row">
        <span>${escapeHtml(p.name)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.round((p.duration_sec / maxBar) * 100)}%"></div></div>
        <span>${formatDuration(p.duration_sec)}</span>
      </div>`
    )
    .join("");

  appEl.innerHTML = `
    <div class="cards">
      <div class="card ${statusClass}">
        <div class="card-label">Last seen</div>
        <div class="card-value">${latest ? relativeTime(latest.recorded_at) : "—"}</div>
        <div class="card-sub">${latest ? formatTime(latest.recorded_at) : "No data"}</div>
      </div>
      <div class="card">
        <div class="card-label">Top place</div>
        <div class="card-value">${escapeHtml(topPlace)}</div>
        <div class="card-sub">${summary.places_count} places</div>
      </div>
      <div class="card">
        <div class="card-label">Battery</div>
        <div class="card-value">${battery}</div>
        <div class="card-sub">${batterySub}</div>
      </div>
      <div class="card">
        <div class="card-label">Travel</div>
        <div class="card-value">${formatDuration(summary.travel_duration_sec)}</div>
        <div class="card-sub">this period</div>
      </div>
      <div class="card">
        <div class="card-label">Stationary</div>
        <div class="card-value">${formatDuration(summary.stationary_duration_sec)}</div>
        <div class="card-sub">at places</div>
      </div>
      <div class="card">
        <div class="card-label">Accuracy</div>
        <div class="card-value">${accuracy}</div>
        <div class="card-sub">${latest?.location_provider || "—"}</div>
      </div>
    </div>
    <div class="home-map-section">
      <div class="map-panel home">
        <div class="map-controls">
          <button type="button" class="secondary" id="fit-trail-btn">Fit trail</button>
        </div>
        <div id="home-map" class="map-container"></div>
      </div>
      <div class="panel home-places">
        <h3>Top places</h3>
        ${bars || '<div class="empty">No visits in period</div>'}
        ${summary.week_teaser ? `<p style="font-size:0.85rem;color:var(--muted);margin-top:1rem">This week: ${summary.week_teaser.places_count} places · ${formatDuration(summary.week_teaser.travel_duration_sec)} travel</p>` : ""}
      </div>
    </div>
    <p style="margin-top:1rem"><a href="#/timeline">View full timeline →</a></p>
  `;

  initMap("home-map");
  document.getElementById("fit-trail-btn")?.addEventListener("click", fitTrail);

  const history = await apiGet("/api/v1/location/history", deviceParams({
    from: data.from,
    to: data.to,
    limit: 2000,
  }));
  renderTrail(history.points || [], latest);
}

async function renderMapPage() {
  setActiveNav("/map");
  setBanner(null);
  appEl.innerHTML = `
    <h1 class="page-title">Map</h1>
    <div class="map-panel tall">
      <div class="map-controls">
        <button type="button" class="secondary" id="fit-trail-btn">Fit trail</button>
      </div>
      <div id="full-map" class="map-container"></div>
    </div>
  `;

  const dash = await apiGet("/api/v1/stats/dashboard", deviceParams(getDashboardParams()));
  const history = await apiGet("/api/v1/location/history", deviceParams({
    from: dash.from,
    to: dash.to,
    limit: 5000,
  }));

  initMap("full-map", { tall: true });
  document.getElementById("fit-trail-btn")?.addEventListener("click", fitTrail);
  renderTrail(history.points || [], dash.latest);
}

async function renderTimeline() {
  setActiveNav("/timeline");
  setBanner(null);
  appEl.innerHTML = `<div class="loading">Loading timeline…</div>`;

  const range = getRange();
  const items = await apiGet(
    "/api/v1/visits",
    deviceParams({ from: range.from, to: range.to, limit: range.visitsLimit })
  );

  if (!items.items?.length) {
    appEl.innerHTML = `<h1 class="page-title">Timeline</h1><div class="empty">No visits or travel in this period</div>`;
    return;
  }

  let lastDay = null;
  const rows = items.items
    .map((item) => {
      const dayKey = localDateKey(item.started_at);
      let separator = "";
      if (dayKey !== lastDay) {
        lastDay = dayKey;
        separator = `<div class="timeline-day-separator">${escapeHtml(formatDaySeparator(item.started_at))}</div>`;
      }

      if (item.kind === "travel") {
        return `${separator}
          <div class="timeline-item travel">
            <div class="timeline-time">${formatTimeShort(item.started_at)}</div>
            <div>
              <div class="timeline-title">Travel</div>
              <div class="timeline-meta">${formatDuration(item.duration_sec)} · ${formatDistance(item.distance_m)} · ${formatSpeed(item.avg_speed_mps)}</div>
            </div>
            <div class="timeline-time">${formatTimeShort(item.ended_at)}</div>
          </div>`;
      }
      return `${separator}
        <div class="timeline-item">
          <div class="timeline-time">${formatTimeShort(item.started_at)}</div>
          <div>
            <div class="timeline-title">${escapeHtml(item.place_name || "Unknown place")}</div>
            <div class="timeline-meta">${formatDuration(item.duration_sec)}</div>
          </div>
          <div class="timeline-time">${formatTimeShort(item.ended_at)}</div>
        </div>`;
    })
    .join("");

  appEl.innerHTML = `<h1 class="page-title">Timeline</h1><div class="timeline">${rows}</div>`;
}

async function renderPlaces() {
  setActiveNav("/places");
  setBanner(null);
  appEl.innerHTML = `<div class="loading">Loading places…</div>`;

  const data = await apiGet("/api/v1/places", deviceParams());
  const places = [...(data.places || [])].sort((a, b) => b.visit_count - a.visit_count);

  if (!places.length) {
    appEl.innerHTML = `<h1 class="page-title">Places</h1><div class="empty">No places detected yet</div>`;
    return;
  }

  const rows = places
    .map(
      (p) => `
      <tr data-place-id="${p.id}">
        <td>
          <span class="place-name">${escapeHtml(p.name || `Place ${p.id}`)}</span>
          <div class="inline-rename hidden">
            <input type="text" value="${escapeHtml(p.name || "")}" placeholder="Name" />
            <button type="button" class="save-name">Save</button>
          </div>
        </td>
        <td>${p.visit_count}</td>
        <td>${formatTime(p.last_seen_at)}</td>
        <td>${p.center_lat.toFixed(5)}, ${p.center_lon.toFixed(5)}</td>
        <td><button type="button" class="secondary rename-btn">Rename</button></td>
      </tr>`
    )
    .join("");

  appEl.innerHTML = `
    <h1 class="page-title">Places <span style="color:var(--muted);font-size:0.9rem">(${places.length})</span></h1>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Visits</th><th>Last visit</th><th>Center</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;

  appEl.querySelectorAll(".rename-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest("tr");
      row.querySelector(".place-name").classList.add("hidden");
      row.querySelector(".inline-rename").classList.remove("hidden");
    });
  });

  appEl.querySelectorAll(".save-name").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const row = btn.closest("tr");
      const placeId = row.dataset.placeId;
      const name = row.querySelector("input").value.trim();
      if (!name) return;
      try {
        await apiPut(`/api/v1/places/${placeId}`, { name }, deviceParams());
        renderPlaces();
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

async function renderTravel() {
  setActiveNav("/travel");
  setBanner(null);
  appEl.innerHTML = `<div class="loading">Loading travel…</div>`;

  const range = getRange();
  const data = await apiGet(
    "/api/v1/travel",
    deviceParams({ from: range.from, to: range.to, limit: 200 })
  );
  const segments = data.segments || [];

  if (!segments.length) {
    appEl.innerHTML = `<h1 class="page-title">Travel</h1><div class="empty">No travel segments in this period</div>`;
    return;
  }

  const totalSec = segments.reduce((s, t) => s + t.duration_sec, 0);
  const totalDist = segments.reduce((s, t) => s + t.distance_m, 0);

  const rows = segments
    .map(
      (t) => `
      <tr>
        <td>${formatTime(t.started_at)}</td>
        <td>${formatTime(t.ended_at)}</td>
        <td>${formatDuration(t.duration_sec)}</td>
        <td>${formatDistance(t.distance_m)}</td>
        <td>${formatSpeed(t.avg_speed_mps)}</td>
      </tr>`
    )
    .join("");

  appEl.innerHTML = `
    <h1 class="page-title">Travel</h1>
    <div class="cards" style="margin-bottom:1rem">
      <div class="card"><div class="card-label">Trips</div><div class="card-value">${segments.length}</div></div>
      <div class="card"><div class="card-label">Total time</div><div class="card-value">${formatDuration(totalSec)}</div></div>
      <div class="card"><div class="card-label">Total distance</div><div class="card-value">${formatDistance(totalDist)}</div></div>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Started</th><th>Ended</th><th>Duration</th><th>Distance</th><th>Avg speed</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

async function renderHistory() {
  setActiveNav("/history");
  setBanner(null);
  appEl.innerHTML = `<div class="loading">Loading history…</div>`;

  const dash = await apiGet("/api/v1/stats/dashboard", deviceParams(getDashboardParams()));
  const data = await apiGet("/api/v1/location/history", deviceParams({
    from: dash.from,
    to: dash.to,
    limit: 500,
  }));

  const points = data.points || [];
  const rows = points
    .map(
      (p) => `
      <tr>
        <td>${formatTime(p.recorded_at)}</td>
        <td>${p.latitude.toFixed(6)}</td>
        <td>${p.longitude.toFixed(6)}</td>
        <td>${p.accuracy_m != null ? Math.round(p.accuracy_m) : "—"}</td>
        <td>${p.battery_pct ?? "—"}</td>
        <td>${escapeHtml(p.network_type || "—")}</td>
      </tr>`
    )
    .join("");

  appEl.innerHTML = `
    <h1 class="page-title">History</h1>
    <p style="color:var(--muted);font-size:0.9rem;margin-bottom:1rem">Showing ${points.length} points (max 500 per page)</p>
    <div class="form-actions" style="margin-bottom:1rem">
      <button type="button" id="export-csv">Export CSV</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Recorded</th><th>Lat</th><th>Lon</th><th>Acc (m)</th><th>Battery</th><th>Network</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6">No points</td></tr>'}</tbody>
      </table>
    </div>
  `;

  document.getElementById("export-csv")?.addEventListener("click", () => {
    const header = "recorded_at,latitude,longitude,accuracy_m,battery_pct,network_type\n";
    const body = points
      .map((p) =>
        [p.recorded_at, p.latitude, p.longitude, p.accuracy_m ?? "", p.battery_pct ?? "", p.network_type ?? ""].join(",")
      )
      .join("\n");
    const blob = new Blob([header + body], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `phone-locator-history-${formatAnchorDateForExport()}.csv`;
    a.click();
  });
}

function formatAnchorDateForExport() {
  const range = getRange();
  const anchor = range.anchor;
  const y = anchor.getFullYear();
  const m = String(anchor.getMonth() + 1).padStart(2, "0");
  const d = String(anchor.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}-${range.granularity}`;
}

function renderSettings() {
  setActiveNav("/settings");
  setBanner(null);
  destroyMap();
  renderSettingsBody();
}

async function renderSettingsBody() {

  const setupUrl = buildSetupUrl();
  const setupSection = setupUrl
    ? `
    <div class="panel setup-panel">
      <h3>Set up phone or tablet</h3>
      <p class="setup-help">
        Scan the QR code or open the setup link on another device. Your token and device ID
        are saved locally on that device — the link is cleared from the browser immediately.
        Only use this on your home network or VPN.
      </p>
      <div class="setup-qr-wrap">
        <canvas id="setup-qr" width="220" height="220" aria-label="Setup QR code"></canvas>
      </div>
      <div class="form-actions">
        <button type="button" class="secondary" id="copy-setup-link">Copy setup link</button>
      </div>
      <p id="setup-msg" style="font-size:0.9rem;color:var(--muted)"></p>
    </div>`
    : "";

  let autoRename = true;
  if (getToken() && getDeviceId()) {
    try {
      const settings = await apiGet("/api/v1/settings", deviceParams());
      autoRename = settings.auto_rename_places;
    } catch {
      autoRename = true;
    }
  }

  appEl.innerHTML = `
    <h1 class="page-title">Settings</h1>
    <div class="panel form-grid">
      <label>API base URL <small>(leave blank for auto)</small>
        <input id="cfg-api-base" type="text" placeholder="/locator" value="${escapeHtml(localStorage.getItem("phoneLocator.apiBase") || "")}" />
      </label>
      <label>API token
        <input id="cfg-token" type="password" placeholder="Bearer token from piSensors" value="${escapeHtml(getToken())}" />
      </label>
      <label>Device ID
        <input id="cfg-device" type="text" placeholder="Phone device UUID" value="${escapeHtml(getDeviceId())}" />
      </label>
      <div class="form-actions">
        <button type="button" id="save-settings">Save</button>
        <button type="button" class="secondary" id="test-connection">Test connection</button>
      </div>
      <p id="settings-msg" style="font-size:0.9rem;color:var(--muted)"></p>
    </div>
    <div class="panel form-grid place-naming-panel">
      <h3>Place names</h3>
      <label class="checkbox-row">
        <input type="checkbox" id="cfg-auto-rename" ${autoRename ? "checked" : ""} />
        Auto-name places from OpenStreetMap
      </label>
      <p class="setup-help">
        Names unnamed places with a 5+ minute stay. Prefers POI names, otherwise street and city
        (e.g. Oak St, Ann Arbor). Manual renames are never overwritten. Sends coordinates to
        OpenStreetMap Nominatim (~1 request/sec).
      </p>
      <div class="form-actions">
        <button type="button" class="secondary" id="estimate-geocode">Estimate queries</button>
        <button type="button" id="run-auto-name">Name places now</button>
      </div>
      <p id="auto-name-msg" style="font-size:0.9rem;color:var(--muted)"></p>
    </div>
    ${setupSection}
  `;

  if (setupUrl) {
    import("https://cdn.jsdelivr.net/npm/qrcode@1.5.4/+esm")
      .then((QRCode) => QRCode.toCanvas(document.getElementById("setup-qr"), setupUrl, { width: 220, margin: 1 }))
      .catch(() => {
        const msg = document.getElementById("setup-msg");
        if (msg) msg.textContent = "QR code unavailable — use Copy setup link instead.";
      });

    document.getElementById("copy-setup-link")?.addEventListener("click", async () => {
      const msg = document.getElementById("setup-msg");
      try {
        await navigator.clipboard.writeText(setupUrl);
        if (msg) msg.textContent = "Setup link copied.";
      } catch {
        if (msg) msg.textContent = "Could not copy — select and copy the link from the address bar after saving.";
      }
    });
  }

  document.getElementById("save-settings").addEventListener("click", () => {
    saveSettings({
      token: document.getElementById("cfg-token").value,
      deviceId: document.getElementById("cfg-device").value,
      apiBase: document.getElementById("cfg-api-base").value,
    });
    document.getElementById("settings-msg").textContent = "Saved.";
  });

  document.getElementById("cfg-auto-rename")?.addEventListener("change", async (event) => {
    const msg = document.getElementById("auto-name-msg");
    msg.textContent = "Saving…";
    try {
      await apiPut(
        "/api/v1/settings",
        { auto_rename_places: event.target.checked },
        deviceParams()
      );
      msg.textContent = event.target.checked ? "Auto-naming enabled." : "Auto-naming disabled.";
    } catch (err) {
      msg.textContent = err.message;
    }
  });

  document.getElementById("estimate-geocode")?.addEventListener("click", async () => {
    const msg = document.getElementById("auto-name-msg");
    msg.textContent = "Estimating…";
    try {
      const result = await apiPost("/api/v1/places/auto-name", {}, deviceParams({ dry_run: true }));
      msg.textContent =
        `${result.geocode_queries_needed} geocode queries needed ` +
        `(${result.geocode_groups} clusters, ~${result.geocode_queries_needed}s first run).`;
    } catch (err) {
      msg.textContent = err.message;
    }
  });

  document.getElementById("run-auto-name")?.addEventListener("click", async () => {
    const msg = document.getElementById("auto-name-msg");
    const btn = document.getElementById("run-auto-name");
    btn.disabled = true;
    msg.textContent = "Naming places… this may take about a minute on first run.";
    try {
      const result = await apiPost("/api/v1/places/auto-name", {}, deviceParams());
      msg.textContent =
        `Done — inherited ${result.places_inherited}, geocoded ${result.places_geocoded} ` +
        `(${result.api_calls} API calls, ${result.cache_hits} cache hits).`;
      if (result.errors?.length) {
        msg.textContent += ` Errors: ${result.errors.join("; ")}`;
      }
    } catch (err) {
      msg.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById("test-connection").addEventListener("click", async () => {
    const msg = document.getElementById("settings-msg");
    msg.textContent = "Testing…";
    try {
      await apiGet("/api/v1/health");
      if (getDeviceId()) {
        await apiGet("/api/v1/stats/dashboard", deviceParams({ period: "today" }));
        msg.textContent = "Connected — API and device OK.";
      } else {
        msg.textContent = "API OK — set device ID to load data.";
      }
    } catch (err) {
      msg.textContent = err.message;
    }
  });
}

const routes = {
  "/": renderHome,
  "/map": renderMapPage,
  "/timeline": renderTimeline,
  "/places": renderPlaces,
  "/travel": renderTravel,
  "/history": renderHistory,
  "/settings": renderSettings,
};

function parseRoute() {
  const raw = window.location.hash.replace(/^#/, "");
  if (!raw) return "/";

  const path = raw.split("?")[0];
  if (!path || path === "/setup") return "/";

  return routes[path] ? path : "/";
}

function normalizeRouteHash(route) {
  const desired = `#${route}`;
  const current = window.location.hash.split("?")[0];
  if (current !== desired) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}${desired}`);
  }
}

async function navigate() {
  try {
    consumeSetupParams();
    const route = parseRoute();
    normalizeRouteHash(route);
    destroyMap();

    if (!getToken() && route !== "/settings") {
      setActiveNav("/settings");
      appEl.innerHTML = `<div class="empty">Configure API token and device ID in <a href="#/settings">Settings</a></div>`;
      setFooterStatus("needs setup");
      return;
    }

    try {
      await routes[route]();
      setFooterStatus(route);
    } catch (err) {
      showError(err);
      setFooterStatus(`error on ${route}`);
    }
  } catch (err) {
    showError(err);
    setFooterStatus("navigation error");
  }
}

window.addEventListener("hashchange", navigate);

if (!window.location.hash || window.location.hash === "#") {
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/`);
}
navigate();
