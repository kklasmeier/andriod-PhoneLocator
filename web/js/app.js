import { renderBarChart, renderStackedBarChart, formatTrendDistance } from "./charts.js";
import { apiGet, apiPost, apiPut, buildSetupUrl, consumeSetupParams, deviceParams, getDeviceId, getToken, saveSettings } from "./api.js";
import { destroyMap, fitTrail, getBasemapId, getBasemapOptions, heatmapSupported, initMap, refreshMapSize, renderHeatmap, renderPlace, renderTrail, setBasemapId, setHeatmapVisible, waitForLayout } from "./map.js";
import { getDashboardParams, getRange, initPeriodBar, localDateKey } from "./period.js";
import { APP_VERSION } from "./version.js";
import {
  escapeHtml,
  formatDaySeparator,
  formatDateShort,
  formatDistance,
  formatDuration,
  formatSpeed,
  formatTime,
  formatTimeShort,
  isNearM,
  maxDuration,
  relativeTime,
} from "./utils.js";

const appEl = document.getElementById("app");
const bannerEl = document.getElementById("banner");
const footerEl = document.getElementById("site-footer");
let autoNamePollTimer = null;

function formatAutoRenameStatus(status) {
  if (status.running) {
    const started = status.started_at ? formatTime(status.started_at) : "recently";
    return `Naming in progress (started ${started})…`;
  }
  if (status.last_result && status.finished_at) {
    const r = status.last_result;
    let text =
      `Last run ${formatTime(status.finished_at)}: geocoded ${r.places_geocoded}, ` +
      `inherited ${r.places_inherited} (${r.api_calls} API calls, ${r.cache_hits} cache hits).`;
    if (r.unnamed_skipped_short_stay) {
      text += ` ${r.unnamed_skipped_short_stay} unnamed place(s) skipped — under 5 min total stay.`;
    }
    if (r.errors?.length) {
      text += ` Errors: ${r.errors.join("; ")}`;
    }
    return text;
  }
  return "Idle — no naming run recorded yet.";
}

async function refreshAutoRenameStatus() {
  const msg = document.getElementById("auto-name-msg");
  const btn = document.getElementById("run-auto-name");
  if (!msg || !getToken() || !getDeviceId()) return;

  try {
    const status = await apiGet("/api/v1/places/auto-name/status", deviceParams());
    msg.textContent = formatAutoRenameStatus(status);
    if (btn) btn.disabled = !!status.running;
    if (status.running) {
      autoNamePollTimer = setTimeout(refreshAutoRenameStatus, 2000);
    }
  } catch (err) {
    msg.textContent = err.message;
  }
}

function stopAutoRenamePolling() {
  if (autoNamePollTimer) {
    clearTimeout(autoNamePollTimer);
    autoNamePollTimer = null;
  }
}

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

let ringPollTimer = null;
let activeRingCommandId = null;

const RING_DURATION_STORAGE = "phoneLocator.ringDurationSec";
const RING_DURATION_DEFAULT = 30;
const RING_DURATION_MIN = 5;
const RING_DURATION_MAX = 300;

function getRingDurationSec() {
  const raw = Number(localStorage.getItem(RING_DURATION_STORAGE));
  if (!Number.isFinite(raw)) return RING_DURATION_DEFAULT;
  return Math.min(RING_DURATION_MAX, Math.max(RING_DURATION_MIN, Math.round(raw)));
}

function setRingDurationSec(value) {
  const sec = Math.min(RING_DURATION_MAX, Math.max(RING_DURATION_MIN, Math.round(Number(value) || RING_DURATION_DEFAULT)));
  localStorage.setItem(RING_DURATION_STORAGE, String(sec));
  return sec;
}

function clearRingPoll() {
  if (ringPollTimer) {
    clearTimeout(ringPollTimer);
    ringPollTimer = null;
  }
  activeRingCommandId = null;
  const stopBtn = document.getElementById("stop-ring-btn");
  if (stopBtn) {
    stopBtn.disabled = true;
    stopBtn.hidden = true;
  }
}

function setStopRingVisible(visible) {
  const stopBtn = document.getElementById("stop-ring-btn");
  if (!stopBtn) return;
  stopBtn.hidden = !visible;
  stopBtn.disabled = !visible;
}

function updateRingStatus(statusEl, btn, status) {
  const terminalSuccess = ["acked", "stopped", "completed"].includes(status.status);
  if (terminalSuccess) {
    if (status.status === "stopped") {
      const who = status.stopped_by === "phone" ? "on phone" : "from website";
      statusEl.textContent = `Ring stopped ${who} — location updated`;
    } else if (status.status === "completed") {
      statusEl.textContent = "Ring finished — location updated";
    } else {
      statusEl.textContent = "Phone responded — location updated";
    }
    statusEl.className = "ring-status ok";
    btn.disabled = false;
    setStopRingVisible(false);
    return true;
  }
  if (status.status === "ringing") {
    statusEl.textContent = "Phone is ringing…";
    statusEl.className = "ring-status pending";
    setStopRingVisible(true);
    return false;
  }
  if (status.status === "delivered") {
    statusEl.textContent = "Delivered to phone — starting ring…";
    statusEl.className = "ring-status pending";
    setStopRingVisible(true);
    return false;
  }
  if (status.status === "pending") {
    statusEl.textContent = "Queued — waiting for phone sync…";
    statusEl.className = "ring-status pending";
    setStopRingVisible(true);
    return false;
  }
  if (status.status === "expired") {
    statusEl.textContent = "Command expired before phone responded";
    statusEl.className = "ring-status error";
    btn.disabled = false;
    setStopRingVisible(false);
    return true;
  }
  if (status.status === "timeout") {
    statusEl.textContent = "Timed out — phone may be offline";
    statusEl.className = "ring-status error";
    btn.disabled = false;
    setStopRingVisible(false);
    return true;
  }
  statusEl.textContent = status.message || "Ring failed";
  statusEl.className = "ring-status error";
  btn.disabled = false;
  setStopRingVisible(false);
  return true;
}

async function stopRingFromWeb() {
  const commandId = activeRingCommandId;
  const statusEl = document.getElementById("ring-status");
  const stopBtn = document.getElementById("stop-ring-btn");
  if (!commandId || !statusEl || !stopBtn) return;
  stopBtn.disabled = true;
  statusEl.textContent = "Requesting stop…";
  try {
    const deviceId = getDeviceId();
    await apiPost(`/api/v1/devices/${deviceId}/commands/${commandId}/stop`, {});
    statusEl.textContent = "Stop requested — waiting for phone…";
  } catch (err) {
    statusEl.textContent = err?.message || String(err);
    statusEl.className = "ring-status error";
    stopBtn.disabled = false;
  }
}

async function pollRingCommand(commandId, statusEl, btn) {
  const deviceId = getDeviceId();
  activeRingCommandId = commandId;
  let attempt = 0;
  const poll = async () => {
    try {
      const status = await apiGet(`/api/v1/devices/${deviceId}/commands/${commandId}`);
      const done = updateRingStatus(statusEl, btn, status);
      if (done) {
        clearRingPoll();
        if (["acked", "stopped", "completed"].includes(status.status)) {
          const range = getRange();
          const [latest, history] = await Promise.all([
            apiGet("/api/v1/location/latest", deviceParams()),
            apiGet("/api/v1/location/history", deviceParams({
              from: range.from,
              to: range.to,
              limit: range.historyLimit,
            })),
          ]);
          renderTrail(history.points || [], latest.point);
          setBanner("Phone rang successfully", "info");
        }
        return;
      }
      attempt += 1;
      if (attempt >= 300) {
        updateRingStatus(statusEl, btn, { status: "timeout" });
        clearRingPoll();
        return;
      }
      ringPollTimer = setTimeout(poll, 2000);
    } catch (err) {
      updateRingStatus(statusEl, btn, { status: "error", message: err?.message });
      clearRingPoll();
    }
  };
  poll();
}

async function ringPhone() {
  const durationSec = getRingDurationSec();
  if (!confirm(`Ring this phone for up to ${durationSec} seconds? It will sound on the next sync (usually within a few minutes).`)) {
    return;
  }
  const btn = document.getElementById("ring-phone-btn");
  const statusEl = document.getElementById("ring-status");
  if (!btn || !statusEl) return;

  clearRingPoll();
  btn.disabled = true;
  statusEl.textContent = "Sending ring command…";
  statusEl.className = "ring-status pending";

  try {
    const deviceId = getDeviceId();
    const created = await apiPost(`/api/v1/devices/${deviceId}/commands`, {
      type: "ring",
      duration_sec: durationSec,
    });
    activeRingCommandId = created.id;
    setStopRingVisible(true);
    statusEl.textContent = "Waiting for phone to respond…";
    pollRingCommand(created.id, statusEl, btn);
  } catch (err) {
    const msg = err?.message || String(err);
    if (msg.includes("429") || msg.toLowerCase().includes("rate limit")) {
      statusEl.textContent = "Please wait 30 seconds between rings";
    } else {
      statusEl.textContent = msg;
    }
    statusEl.className = "ring-status error";
    btn.disabled = false;
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
          <button type="button" class="ring-phone" id="ring-phone-btn">Ring phone</button>
          <button type="button" class="secondary stop-ring" id="stop-ring-btn" hidden disabled>Stop ringing</button>
          <button type="button" class="secondary" id="fit-trail-btn">Fit trail</button>
          <span id="ring-status" class="ring-status" aria-live="polite"></span>
        </div>
        <div id="home-map" class="map-container"></div>
      </div>
      <div class="panel home-places">
        <h3>Top places</h3>
        ${bars || '<div class="empty">No visits in period</div>'}
        ${summary.week_teaser ? `<p style="font-size:0.85rem;color:var(--muted);margin-top:1rem">This week: ${summary.week_teaser.places_count} places · ${formatDuration(summary.week_teaser.travel_duration_sec)} travel</p>` : ""}
      </div>
    </div>
    <p style="margin-top:1rem"><a href="#/timeline">View full timeline →</a> · <a href="#/reports">Reports →</a></p>
  `;

  initMap("home-map");
  document.getElementById("fit-trail-btn")?.addEventListener("click", fitTrail);
  document.getElementById("ring-phone-btn")?.addEventListener("click", ringPhone);
  document.getElementById("stop-ring-btn")?.addEventListener("click", stopRingFromWeb);

  const range = getRange();
  const history = await apiGet("/api/v1/location/history", deviceParams({
    from: range.from,
    to: range.to,
    limit: range.historyLimit,
  }));
  if (history.sampled && status === "ok") {
    setBanner(
      `Map shows ${history.count.toLocaleString()} sampled points from ${history.total_count.toLocaleString()} in this period`,
      "info"
    );
  }
  renderTrail(history.points || [], latest);
}

function buildPlaceBars(places, lifetimeStyle = false) {
  const max = maxDuration(places || []);
  return (places || [])
    .map(
      (p) => `
      <div class="bar-row">
        <span>${escapeHtml(p.name)}</span>
        <div class="bar-track"><div class="bar-fill${lifetimeStyle ? " lifetime" : ""}" style="width:${max ? Math.round((p.duration_sec / max) * 100) : 0}%"></div></div>
        <span>${formatDuration(p.duration_sec)}</span>
      </div>`
    )
    .join("");
}

function buildFrequentRoutesHtml(routes) {
  if (!routes?.length) {
    return '<div class="empty">No trips yet</div>';
  }
  const rows = routes
    .map(
      (route) => `
      <tr>
        <td>${escapeHtml(route.route_label || `${route.from_place_name} → ${route.to_place_name}`)}</td>
        <td>${route.trip_count}</td>
        <td>${formatDuration(route.avg_duration_sec)}</td>
        <td>${formatDistance(route.total_distance_m)}</td>
      </tr>`
    )
    .join("");
  return `
    <div class="table-wrap reports-travel-table">
      <table>
        <thead><tr><th>Route</th><th>Trips</th><th>Avg time</th><th>Total distance</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildTravelSection(travel) {
  return `
    <section class="reports-travel-section">
      <h3>Travel <span class="section-count">(${travel.trip_count} trips · ${formatDistance(travel.distance_m)})</span></h3>
      <h4>Frequent routes</h4>
      ${buildFrequentRoutesHtml(travel.frequent_routes)}
    </section>`;
}

function trendsRangeDays(rangeDays) {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - (rangeDays - 1));
  return {
    from: localDateKey(start.toISOString()),
    to: localDateKey(end.toISOString()),
  };
}

function renderTrendCharts(buckets) {
  renderStackedBarChart(document.getElementById("chart-time-split"), {
    buckets,
    series: [
      { key: "stationary_duration_sec", label: "Stationary", color: "var(--chart-stationary)" },
      { key: "travel_duration_sec", label: "Travel", color: "var(--chart-travel)" },
    ],
    emptyLabel: "No activity in this range",
  });
  renderBarChart(document.getElementById("chart-travel-distance"), {
    buckets,
    valueKey: "travel_distance_m",
    color: "var(--chart-distance)",
    formatValue: formatTrendDistance,
    label: "Distance",
    emptyLabel: "No travel distance in this range",
  });
  renderBarChart(document.getElementById("chart-travel-trips"), {
    buckets,
    valueKey: "travel_trips",
    color: "var(--chart-trips)",
    formatValue: (value) => `${Math.round(value)}`,
    label: "Trips",
    emptyLabel: "No trips in this range",
  });
}

async function loadTrends({ rangeDays = 90, granularity = null } = {}) {
  const range = trendsRangeDays(rangeDays);
  const params = deviceParams({ from: range.from, to: range.to });
  if (granularity) params.granularity = granularity;
  const trends = await apiGet("/api/v1/stats/trends", params);
  renderTrendCharts(trends.buckets || []);
  const hint = document.getElementById("trends-range-hint");
  if (hint) {
    hint.textContent = `${trends.from} → ${trends.to} · ${trends.granularity} buckets`;
  }
  return trends;
}

async function renderReports() {
  setActiveNav("/reports");
  setBanner(null);
  appEl.innerHTML = `<div class="loading">Loading reports…</div>`;

  const data = await apiGet("/api/v1/stats/reports", deviceParams());
  const { lifetime, lifetime_travel: lifetimeTravel } = data;

  const sinceLine = lifetime.first_point_at
    ? `Tracking since ${formatDateShort(lifetime.first_point_at)} · ${lifetime.days_with_data.toLocaleString()} days with data · ${lifetime.days_without_data.toLocaleString()} days without`
    : "No tracking data yet";

  const topPlaceLine = lifetime.top_place
    ? `Mostly at <strong>${escapeHtml(lifetime.top_place.name)}</strong> (${lifetime.top_place.share_pct}% of stationary time)`
    : "";

  const placesSub =
    lifetime.places_visited_count > 0 && lifetime.places_visited_count !== lifetime.places_count
      ? `${lifetime.places_visited_count.toLocaleString()} visited`
      : `${lifetime.visits_count.toLocaleString()} visits`;

  const lifetimeBars = buildPlaceBars(lifetime.top_places, true);

  appEl.innerHTML = `
    <h1 class="page-title">Reports</h1>
    <section class="reports-panel panel lifetime-band">
      <p class="lifetime-since">${sinceLine}</p>
      <div class="cards lifetime-cards">
        <div class="card">
          <div class="card-label">Places</div>
          <div class="card-value">${lifetime.places_count}</div>
          <div class="card-sub">${placesSub}</div>
        </div>
        <div class="card">
          <div class="card-label">Travel time</div>
          <div class="card-value">${formatDuration(lifetime.travel_duration_sec)}</div>
          <div class="card-sub">${lifetime.travel_trips.toLocaleString()} trips</div>
        </div>
        <div class="card">
          <div class="card-label">Stationary</div>
          <div class="card-value">${formatDuration(lifetime.stationary_duration_sec)}</div>
          <div class="card-sub">at named places</div>
        </div>
        <div class="card">
          <div class="card-label">Distance</div>
          <div class="card-value">${formatDistance(lifetime.travel_distance_m)}</div>
          <div class="card-sub">lifetime travel</div>
        </div>
      </div>
      ${topPlaceLine ? `<p class="lifetime-highlight">${topPlaceLine}</p>` : ""}
      <h3>Top places</h3>
      ${lifetimeBars || '<div class="empty">No place visits yet</div>'}
      ${buildTravelSection(lifetimeTravel)}
    </section>
    <section class="reports-panel panel trends-panel">
      <div class="trends-header">
        <h2>Trends</h2>
        <p id="trends-range-hint" class="trends-range-hint muted-hint">Loading…</p>
      </div>
      <div class="trends-controls" role="group" aria-label="Trend range">
        <button type="button" class="secondary" data-range-days="30">30 days</button>
        <button type="button" class="secondary active" data-range-days="90">90 days</button>
        <button type="button" class="secondary" data-range-days="365">1 year</button>
        <span class="trends-controls-divider"></span>
        <button type="button" class="secondary" data-granularity="day">Daily</button>
        <button type="button" class="secondary" data-granularity="week">Weekly</button>
        <button type="button" class="secondary" data-granularity="month">Monthly</button>
      </div>
      <div class="trends-charts">
        <div class="chart-card">
          <h3>Time at places vs travel</h3>
          <div id="chart-time-split" class="chart-host"></div>
        </div>
        <div class="chart-card">
          <h3>Travel distance</h3>
          <div id="chart-travel-distance" class="chart-host"></div>
        </div>
        <div class="chart-card">
          <h3>Trips</h3>
          <div id="chart-travel-trips" class="chart-host"></div>
        </div>
      </div>
    </section>
  `;

  let rangeDays = 90;
  let granularity = null;

  const load = () => loadTrends({ rangeDays, granularity });
  await load();

  document.querySelectorAll(".trends-controls [data-range-days]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      rangeDays = Number(btn.dataset.rangeDays);
      document.querySelectorAll(".trends-controls [data-range-days]").forEach((el) => {
        el.classList.toggle("active", el === btn);
      });
      await load();
    });
  });

  document.querySelectorAll(".trends-controls [data-granularity]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const selected = btn.dataset.granularity;
      if (granularity === selected) {
        granularity = null;
        btn.classList.remove("active");
      } else {
        granularity = selected;
        document.querySelectorAll(".trends-controls [data-granularity]").forEach((el) => {
          el.classList.toggle("active", el === btn);
        });
      }
      await load();
    });
  });
}

async function renderMapPage() {
  setActiveNav("/map");
  setBanner(null);
  appEl.innerHTML = `
    <h1 class="page-title">Map</h1>
    <div class="map-panel tall">
      <div class="map-controls">
        <button type="button" class="secondary" id="fit-trail-btn">Fit trail</button>
        <label class="map-layer-toggle">
          <input type="checkbox" id="heatmap-toggle" ${heatmapSupported() ? "" : "disabled"} />
          Lifetime heatmap
        </label>
        <span id="heatmap-status" class="map-layer-status muted-hint"></span>
      </div>
      <div id="full-map" class="map-container"></div>
    </div>
  `;

  const dash = await apiGet("/api/v1/stats/dashboard", deviceParams(getDashboardParams()));
  const range = getRange();
  const history = await apiGet("/api/v1/location/history", deviceParams({
    from: range.from,
    to: range.to,
    limit: range.historyLimit,
  }));

  if (history.sampled) {
    setBanner(
      `Map shows ${history.count.toLocaleString()} sampled points from ${history.total_count.toLocaleString()} in this period`,
      "info"
    );
  }

  initMap("full-map", { tall: true });
  document.getElementById("fit-trail-btn")?.addEventListener("click", fitTrail);
  renderTrail(history.points || [], dash.latest);

  const heatmapToggle = document.getElementById("heatmap-toggle");
  const heatmapStatus = document.getElementById("heatmap-status");
  let heatmapLoaded = false;

  if (!heatmapSupported()) {
    if (heatmapStatus) heatmapStatus.textContent = "Heatmap plugin unavailable";
  }

  function formatHeatmapStatus(data) {
    const cells = Number(data?.bin_count ?? data?.bins?.length ?? 0);
    const points = Number(data?.total_points ?? 0);
    if (!cells) return "No lifetime data yet";
    const shown = Array.isArray(data?.bins) ? data.bins.length : cells;
    const suffix = shown < cells ? ` (showing top ${shown.toLocaleString()})` : "";
    return `${cells.toLocaleString()} cells · ${points.toLocaleString()} points${suffix}`;
  }

  async function ensureHeatmapLoaded() {
    if (heatmapLoaded) return true;
    if (heatmapStatus) heatmapStatus.textContent = "Loading heatmap…";
    let data;
    try {
      data = await apiGet("/api/v1/location/heatmap", deviceParams(), { timeoutMs: 120000 });
    } catch (err) {
      if (!heatmapLoaded && heatmapStatus) heatmapStatus.textContent = "Could not load heatmap";
      throw err;
    }

    try {
      renderHeatmap(data.bins || []);
    } catch (err) {
      if (heatmapStatus) heatmapStatus.textContent = "Could not render heatmap";
      throw err;
    }

    heatmapLoaded = true;
    if (heatmapStatus) heatmapStatus.textContent = formatHeatmapStatus(data);
    return (data.bins || []).length > 0;
  }

  heatmapToggle?.addEventListener("change", async () => {
    const wantVisible = heatmapToggle.checked;
    try {
      if (wantVisible) {
        const hasBins = await ensureHeatmapLoaded();
        if (!hasBins) {
          heatmapToggle.checked = false;
          if (heatmapStatus) heatmapStatus.textContent = "No lifetime data yet";
          return;
        }
        setHeatmapVisible(true);
      } else {
        setHeatmapVisible(false);
      }
    } catch {
      if (!heatmapLoaded) heatmapToggle.checked = false;
    }
  });
}

let _openMapAccordion = null;

function closeMapAccordion() {
  if (!_openMapAccordion) return;
  const { accordion, trigger } = _openMapAccordion;
  accordion.classList.add("hidden");
  trigger?.classList.remove("place-row-selected", "selected");
  _openMapAccordion = null;
  _openMapAccordionToken += 1;
  destroyMap();
}

let _openMapAccordionToken = 0;

async function resolvePrecisePin({
  lat,
  lon,
  radiusM = 50,
  startedAt,
  endedAt,
  lastSeenAt,
}) {
  const fallback = { pinLat: lat, pinLon: lon, accuracyM: null, pinLabel: null };

  try {
    const latest = await apiGet("/api/v1/location/latest", deviceParams());
    if (
      latest?.latitude != null &&
      latest?.longitude != null &&
      isNearM(latest.latitude, latest.longitude, lat, lon, radiusM)
    ) {
      return {
        pinLat: latest.latitude,
        pinLon: latest.longitude,
        accuracyM: latest.accuracy_m ?? null,
        pinLabel: "Current phone location",
      };
    }
  } catch {
    // fall through to history lookup
  }

  if (startedAt && endedAt) {
    try {
      const history = await apiGet("/api/v1/location/history", deviceParams({
        from: startedAt,
        to: endedAt,
        limit: 500,
      }));
      const points = history.points || [];
      if (points.length > 0) {
        const last = points[points.length - 1];
        return {
          pinLat: last.latitude,
          pinLon: last.longitude,
          accuracyM: last.accuracy_m ?? null,
          pinLabel: "Last reading this visit",
        };
      }
    } catch {
      // fall through
    }
  }

  if (lastSeenAt) {
    try {
      const from = new Date(new Date(lastSeenAt).getTime() - 6 * 3600 * 1000).toISOString();
      const history = await apiGet("/api/v1/location/history", deviceParams({
        from,
        to: lastSeenAt,
        limit: 500,
      }));
      const points = (history.points || []).filter((p) =>
        isNearM(p.latitude, p.longitude, lat, lon, radiusM * 1.5)
      );
      if (points.length > 0) {
        const last = points[points.length - 1];
        return {
          pinLat: last.latitude,
          pinLon: last.longitude,
          accuracyM: last.accuracy_m ?? null,
          pinLabel: "Last reading here",
        };
      }
    } catch {
      // fall through
    }
  }

  return fallback;
}

async function toggleMapAccordion(trigger, accordion, placeData) {
  const { lat, lon, name, radiusM = 50, startedAt, endedAt, lastSeenAt } = placeData;
  if (lat == null || lon == null) return;

  if (_openMapAccordion?.accordion === accordion) {
    closeMapAccordion();
    return;
  }

  closeMapAccordion();

  const mapEl = accordion.querySelector(".inline-place-map");
  if (!mapEl) return;

  accordion.classList.remove("hidden");
  trigger.classList.add(trigger.matches("tr") ? "place-row-selected" : "selected");
  _openMapAccordion = { accordion, trigger };

  await waitForLayout();
  if (_openMapAccordion?.accordion !== accordion) return;

  const token = ++_openMapAccordionToken;
  initMap(mapEl);
  renderPlace({ lat, lon, name, radiusM });

  const precise = await resolvePrecisePin({
    lat,
    lon,
    radiusM,
    startedAt,
    endedAt,
    lastSeenAt,
  });
  if (token !== _openMapAccordionToken || _openMapAccordion?.accordion !== accordion) return;

  renderPlace({
    lat,
    lon,
    name,
    radiusM,
    pinLat: precise.pinLat,
    pinLon: precise.pinLon,
    accuracyM: precise.accuracyM,
    pinLabel: precise.pinLabel,
  });
  refreshMapSize();
}

function wirePlaceMapRow(row, place) {
  const accordion = row.nextElementSibling;
  if (!accordion?.classList.contains("place-map-accordion-row")) return;

  row.classList.add("place-row-clickable");
  row.addEventListener("click", (event) => {
    if (event.target.closest("button, input, .inline-rename")) return;
    toggleMapAccordion(row, accordion, {
      lat: place.center_lat,
      lon: place.center_lon,
      name: place.name || `Place ${place.id}`,
      radiusM: place.radius_m,
      lastSeenAt: place.last_seen_at,
    });
  });
}

async function renderTimeline() {
  setActiveNav("/timeline");
  setBanner(null);
  _openMapAccordion = null;
  destroyMap();
  appEl.innerHTML = `<div class="loading">Loading timeline…</div>`;

  const range = getRange();
  const [items, placesData] = await Promise.all([
    apiGet("/api/v1/visits", deviceParams({ from: range.from, to: range.to, limit: range.visitsLimit })),
    apiGet("/api/v1/places", deviceParams()),
  ]);
  const placeById = Object.fromEntries((placesData.places || []).map((p) => [p.id, p]));
  const truncated = items.count >= range.visitsLimit;

  if (!items.items?.length) {
    appEl.innerHTML = `<h1 class="page-title">Timeline</h1><div class="empty">No visits or travel in this period</div>`;
    return;
  }

  let lastDay = null;
  const rows = items.items
    .map((item, index) => {
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
        <div class="timeline-visit-group">
          <div class="timeline-item visit-item" data-visit-index="${index}" data-place-id="${item.place_id ?? ""}" data-lat="${item.center_lat}" data-lon="${item.center_lon}" data-started-at="${item.started_at}" data-ended-at="${item.ended_at}">
            <div class="timeline-time">${formatTimeShort(item.started_at)}</div>
            <div>
              <div class="timeline-title">${escapeHtml(item.place_name || "Unknown place")}</div>
              <div class="timeline-meta">${formatDuration(item.duration_sec)} · tap to toggle map</div>
            </div>
            <div class="timeline-time">${formatTimeShort(item.ended_at)}</div>
          </div>
          <div class="timeline-map-accordion hidden" data-for-visit="${index}">
            <div class="inline-place-map"></div>
          </div>
        </div>`;
    })
    .join("");

  appEl.innerHTML = `
    <h1 class="page-title">Timeline</h1>
    ${truncated ? `<p class="page-hint">Showing the first ${range.visitsLimit} events in this period. Try a shorter range for full detail.</p>` : ""}
    <div class="timeline">${rows}</div>`;

  appEl.querySelectorAll(".timeline-item.visit-item").forEach((el) => {
    const accordion = el.nextElementSibling;
    if (!accordion?.classList.contains("timeline-map-accordion")) return;

    el.addEventListener("click", () => {
      const lat = Number(el.dataset.lat);
      const lon = Number(el.dataset.lon);
      const placeId = Number(el.dataset.placeId);
      const place = placeById[placeId];
      const name = el.querySelector(".timeline-title")?.textContent || "Place";

      toggleMapAccordion(el, accordion, {
        lat,
        lon,
        name,
        radiusM: place?.radius_m ?? 50,
        startedAt: el.dataset.startedAt,
        endedAt: el.dataset.endedAt,
      });
    });
  });
}

async function renderPlaces() {
  setActiveNav("/places");
  setBanner(null);
  _openMapAccordion = null;
  destroyMap();
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
      <tr data-place-id="${p.id}" class="place-row-clickable">
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
      </tr>
      <tr class="place-map-accordion-row hidden" data-for-place="${p.id}">
        <td colspan="5">
          <div class="inline-place-map"></div>
        </td>
      </tr>`
    )
    .join("");

  appEl.innerHTML = `
    <h1 class="page-title">Places <span style="color:var(--muted);font-size:0.9rem">(${places.length})</span></h1>
    <p class="page-hint">Click a place row to expand a map below it. Click again to collapse.</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Name</th><th>Visits</th><th>Last visit</th><th>Center</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;

  places.forEach((place) => {
    const row = appEl.querySelector(`tr[data-place-id="${place.id}"]`);
    if (row) wirePlaceMapRow(row, place);
  });

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
    deviceParams({ from: range.from, to: range.to, limit: range.visitsLimit })
  );
  const segments = [...(data.segments || [])].sort(
    (a, b) => new Date(b.started_at) - new Date(a.started_at)
  );

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
        <td>${escapeHtml(t.route_label || `${t.from_place_name || "Unknown"} → ${t.to_place_name || "Unknown"}`)}</td>
        <td>${formatDuration(t.duration_sec)}</td>
        <td>${formatDistance(t.distance_m)}</td>
        <td>${formatSpeed(t.avg_speed_mps)}</td>
      </tr>`
    )
    .join("");

  const cards = segments
    .map(
      (t) => `
      <div class="timeline-item travel">
        <div class="timeline-time">${formatTimeShort(t.started_at)}</div>
        <div>
          <div class="timeline-title">${escapeHtml(t.route_label || `${t.from_place_name || "Unknown"} → ${t.to_place_name || "Unknown"}`)}</div>
          <div class="timeline-meta">${formatDuration(t.duration_sec)} · ${formatDistance(t.distance_m)} · ${formatSpeed(t.avg_speed_mps)}</div>
        </div>
        <div class="timeline-time">${formatTimeShort(t.ended_at)}</div>
      </div>`
    )
    .join("");

  appEl.innerHTML = `
    <h1 class="page-title">Travel</h1>
    <div class="cards travel-summary" style="margin-bottom:1rem">
      <div class="card"><div class="card-label">Trips</div><div class="card-value">${segments.length}</div></div>
      <div class="card"><div class="card-label">Total time</div><div class="card-value">${formatDuration(totalSec)}</div></div>
      <div class="card"><div class="card-label">Total distance</div><div class="card-value">${formatDistance(totalDist)}</div></div>
    </div>
    <div class="travel-cards timeline">${cards}</div>
    <div class="table-wrap travel-table">
      <table>
        <thead><tr><th>Started</th><th>End</th><th>Route</th><th>Duration</th><th>Distance</th><th>Average speed</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

const HISTORY_PAGE_SIZE = 500;
let historyState = { points: [], total: 0 };

function historyRowsHtml(points) {
  return points
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
}

function exportHistoryCsv(points) {
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
}

function renderHistoryContent() {
  const { points, total } = historyState;
  const canLoadMore = points.length < total;
  const rows = historyRowsHtml(points);

  appEl.innerHTML = `
    <h1 class="page-title">History</h1>
    <p class="page-hint">
      Showing ${points.length.toLocaleString()} of ${total.toLocaleString()} points (newest first).
      Export CSV includes only the rows loaded below.
    </p>
    <div class="form-actions" style="margin-bottom:1rem">
      <button type="button" id="export-csv">Export CSV (${points.length})</button>
      ${canLoadMore ? `<button type="button" class="secondary" id="load-more-history">Load more</button>` : ""}
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Recorded</th><th>Lat</th><th>Lon</th><th>Acc (m)</th><th>Battery</th><th>Network</th></tr></thead>
        <tbody id="history-tbody">${rows || '<tr><td colspan="6">No points</td></tr>'}</tbody>
      </table>
    </div>
  `;

  document.getElementById("export-csv")?.addEventListener("click", () => {
    exportHistoryCsv(historyState.points);
  });

  document.getElementById("load-more-history")?.addEventListener("click", async () => {
    const btn = document.getElementById("load-more-history");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Loading…";
    }
    try {
      await loadMoreHistory();
    } catch (err) {
      showError(err);
    }
  });
}

async function loadHistoryPage({ reset = false } = {}) {
  if (reset) {
    historyState = { points: [], total: 0 };
  }

  const range = getRange();
  const data = await apiGet("/api/v1/location/history", deviceParams({
    from: range.from,
    to: range.to,
    limit: HISTORY_PAGE_SIZE,
    offset: historyState.points.length,
    order: "desc",
    sample: false,
  }));

  const page = data.points || [];
  historyState.points = reset ? page : [...historyState.points, ...page];
  historyState.total = data.total_count ?? historyState.points.length;
  return data;
}

async function loadMoreHistory() {
  await loadHistoryPage();
  renderHistoryContent();
}

async function renderHistory() {
  setActiveNav("/history");
  setBanner(null);
  appEl.innerHTML = `<div class="loading">Loading history…</div>`;

  await loadHistoryPage({ reset: true });
  renderHistoryContent();
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

  const basemapOptions = getBasemapOptions()
    .map(
      (basemap) =>
        `<option value="${basemap.id}" ${getBasemapId() === basemap.id ? "selected" : ""}>${escapeHtml(basemap.label)} — ${escapeHtml(basemap.description)}</option>`
    )
    .join("");

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
    <div class="panel form-grid">
      <h3>Ring phone</h3>
      <label>Max ring duration (seconds)
        <input id="cfg-ring-duration" type="number" min="${RING_DURATION_MIN}" max="${RING_DURATION_MAX}" value="${getRingDurationSec()}" />
      </label>
      <p class="setup-help">
        How long the phone rings if not stopped (${RING_DURATION_MIN}–${RING_DURATION_MAX} seconds). The phone still receives the ring command on its normal GPS sync (~every 3 minutes). While ringing, it checks every 5 seconds whether you pressed Stop on the website.
      </p>
    </div>
    <div class="panel form-grid">
      <h3>Map</h3>
      <label>Basemap
        <select id="cfg-basemap">${basemapOptions}</select>
      </label>
      <p class="setup-help">
        OpenStreetMap shows local-language labels (e.g. Deutsch in Germany). Esri uses English labels
        worldwide. Reopen a map page after changing.
      </p>
      <p id="basemap-msg" style="font-size:0.9rem;color:var(--muted)"></p>
    </div>
    <div class="panel form-grid place-naming-panel">
      <h3>Place names</h3>
      <label class="checkbox-row">
        <input type="checkbox" id="cfg-auto-rename" ${autoRename ? "checked" : ""} />
        Auto-name places from OpenStreetMap
      </label>
      <p class="setup-help">
        When enabled, naming runs automatically in the background after new location data is processed
        (you do not need to press the button each time). Names unnamed places with 5+ minutes total stay
        time. Prefers POI names, otherwise street and city (e.g. Oak St, Ann Arbor). Manual renames are
        never overwritten. Sends coordinates to OpenStreetMap Nominatim (~1 request/sec).
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
    const ringInput = document.getElementById("cfg-ring-duration");
    if (ringInput) setRingDurationSec(ringInput.value);
    document.getElementById("settings-msg").textContent = "Saved.";
  });

  document.getElementById("cfg-ring-duration")?.addEventListener("change", (event) => {
    setRingDurationSec(event.target.value);
    event.target.value = String(getRingDurationSec());
  });

  document.getElementById("cfg-basemap")?.addEventListener("change", (event) => {
    setBasemapId(event.target.value);
    const msg = document.getElementById("basemap-msg");
    if (msg) msg.textContent = "Basemap saved. Reopen Map or Home to apply.";
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
    msg.textContent = "Starting naming job…";
    try {
      const result = await apiPost("/api/v1/places/auto-name", {}, deviceParams());
      if (result.skipped && result.reason === "already_running") {
        msg.textContent = "Naming is already in progress.";
      } else {
        msg.textContent =
          `Done — inherited ${result.places_inherited}, geocoded ${result.places_geocoded} ` +
          `(${result.api_calls} API calls, ${result.cache_hits} cache hits).`;
        if (result.unnamed_skipped_short_stay) {
          msg.textContent += ` ${result.unnamed_skipped_short_stay} skipped (<5 min total stay).`;
        }
        if (result.errors?.length) {
          msg.textContent += ` Errors: ${result.errors.join("; ")}`;
        }
      }
    } catch (err) {
      msg.textContent = err.message;
    } finally {
      refreshAutoRenameStatus();
    }
  });

  if (getToken() && getDeviceId()) {
    refreshAutoRenameStatus();
  }

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
  "/reports": renderReports,
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
    stopAutoRenamePolling();
    consumeSetupParams();
    const route = parseRoute();
    normalizeRouteHash(route);
    destroyMap();
    document.getElementById("period-bar")?.classList.toggle("hidden", route === "/reports");

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
