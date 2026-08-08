export function formatDuration(seconds) {
  if (seconds == null || seconds < 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${seconds}s`;
}

export function formatDistance(meters) {
  if (meters == null) return "—";
  const miles = meters / 1609.344;
  if (miles >= 0.1) return `${miles.toFixed(1)} mi`;
  return `${Math.round(meters)} m`;
}

export function formatSpeed(mps) {
  if (mps == null) return "—";
  const mph = mps * 2.23694;
  return `${mph.toFixed(0)} mph`;
}

const LOCALE = "en-US";
const TIME_OPTS = { hour: "numeric", minute: "2-digit", hour12: true };
const DATE_OPTS = { month: "short", day: "numeric" };

export function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const currentYear = new Date().getFullYear();
  const datePart = d.toLocaleDateString(LOCALE, {
    ...DATE_OPTS,
    ...(d.getFullYear() !== currentYear ? { year: "numeric" } : {}),
  });
  const timePart = d.toLocaleTimeString(LOCALE, TIME_OPTS);
  return `${datePart}, ${timePart}`;
}

export function formatTimeShort(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString(LOCALE, TIME_OPTS);
}

export function formatDaySeparator(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const currentYear = new Date().getFullYear();
  const weekday = d.toLocaleDateString(LOCALE, { weekday: "long" });
  const datePart = d.toLocaleDateString(LOCALE, {
    ...DATE_OPTS,
    ...(d.getFullYear() !== currentYear ? { year: "numeric" } : {}),
  });
  return `${weekday}, ${datePart}`;
}

export function relativeTime(iso) {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function maxDuration(items, key = "duration_sec") {
  return items.reduce((max, item) => Math.max(max, item[key] || 0), 1);
}

export function haversineM(lat1, lon1, lat2, lon2) {
  const earthRadiusM = 6371000;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return earthRadiusM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function isNearM(lat, lon, centerLat, centerLon, radiusM) {
  return haversineM(lat, lon, centerLat, centerLon) <= radiusM;
}
