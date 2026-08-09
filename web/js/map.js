let _map = null;
let _mapGeneration = 0;
let _resizeTimers = [];
let _layers = { trail: null, markers: null, accuracy: null, heatmap: null };

function waitForLayout() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

export { waitForLayout };

function boundsForCircle(lat, lon, radiusM) {
  const radius = Math.max(radiusM, 1);
  const dLat = radius / 111320;
  const cosLat = Math.cos((lat * Math.PI) / 180);
  const dLon = radius / (111320 * (Math.abs(cosLat) > 0.01 ? cosLat : 1));
  return L.latLngBounds([lat - dLat, lon - dLon], [lat + dLat, lon + dLon]);
}

export function refreshMapSize() {
  if (!_map) return;
  const gen = _mapGeneration;
  const resize = () => {
    if (!_map || gen !== _mapGeneration) return;
    _map.invalidateSize({ pan: false });
  };
  requestAnimationFrame(() => requestAnimationFrame(resize));
  _resizeTimers.push(setTimeout(resize, 100));
  _resizeTimers.push(setTimeout(resize, 300));
}

export function destroyMap() {
  _mapGeneration += 1;
  _resizeTimers.forEach(clearTimeout);
  _resizeTimers = [];
  if (_map) {
    _map.remove();
    _map = null;
    _layers = { trail: null, markers: null, accuracy: null, heatmap: null };
  }
}

export function initMap(container, { tall = false } = {}) {
  destroyMap();
  const el = typeof container === "string" ? document.getElementById(container) : container;
  if (!el) return null;

  el.innerHTML = "";
  delete el._leaflet_id;

  const panel = el.closest(".map-panel");
  if (panel && tall) panel.classList.add("tall");

  _map = L.map(el, { zoomControl: true });
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
    attribution:
      "Tiles &copy; Esri &mdash; Esri, TomTom, Garmin, FAO, NOAA, USGS, &copy; OpenStreetMap",
    maxZoom: 19,
  }).addTo(_map);

  _layers.trail = L.layerGroup().addTo(_map);
  _layers.markers = L.layerGroup().addTo(_map);
  _layers.accuracy = L.layerGroup().addTo(_map);

  const gen = _mapGeneration;
  _map.whenReady(() => {
    if (gen === _mapGeneration) refreshMapSize();
  });

  return _map;
}

export function renderTrail(points, latest) {
  if (!_map) return;

  _layers.trail.clearLayers();
  _layers.markers.clearLayers();
  _layers.accuracy.clearLayers();

  const latlngs = points.map((p) => [p.latitude, p.longitude]);
  if (latlngs.length > 1) {
    const line = L.polyline(latlngs, { color: "#3b82f6", weight: 4, opacity: 0.85 });
    _layers.trail.addLayer(line);
  }

  points.forEach((p) => {
    const marker = L.circleMarker([p.latitude, p.longitude], {
      radius: 3,
      color: "#60a5fa",
      fillColor: "#93c5fd",
      fillOpacity: 0.8,
      weight: 1,
    });
    marker.bindPopup(
      `<strong>${new Date(p.recorded_at).toLocaleString()}</strong><br/>` +
        `±${Math.round(p.accuracy_m || 0)} m` +
        (p.battery_pct != null ? `<br/>Battery ${p.battery_pct}%` : "")
    );
    _layers.markers.addLayer(marker);
  });

  if (latest) {
    const pin = L.marker([latest.latitude, latest.longitude]);
    pin.bindPopup(
      `<strong>Latest</strong><br/>${new Date(latest.recorded_at).toLocaleString()}`
    );
    _layers.markers.addLayer(pin);

    if (latest.accuracy_m) {
      const circle = L.circle([latest.latitude, latest.longitude], {
        radius: latest.accuracy_m,
        color: "#22c55e",
        fillColor: "#22c55e",
        fillOpacity: 0.12,
        weight: 1,
      });
      _layers.accuracy.addLayer(circle);
    }
  }

  if (latlngs.length > 0) {
    const bounds = L.latLngBounds(latlngs);
    _map.fitBounds(bounds.pad(0.12));
  } else if (latest) {
    _map.setView([latest.latitude, latest.longitude], 15);
  } else {
    _map.setView([39.36, -84.34], 12);
  }

  refreshMapSize();
}

export function renderPlace({
  lat,
  lon,
  name,
  radiusM = 50,
  pinLat,
  pinLon,
  accuracyM,
  pinLabel,
}) {
  if (!_map) return;

  _layers.trail.clearLayers();
  _layers.markers.clearLayers();
  _layers.accuracy.clearLayers();

  const markerLat = pinLat ?? lat;
  const markerLon = pinLon ?? lon;
  const safeName = String(name || "Place").replace(/[<>&"]/g, (ch) => (
    { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[ch]
  ));
  const safePinLabel = String(pinLabel || safeName).replace(/[<>&"]/g, (ch) => (
    { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[ch]
  ));

  const radius = radiusM > 0 ? radiusM : 50;
  const placeCircle = L.circle([lat, lon], {
    radius,
    color: "#3b82f6",
    fillColor: "#3b82f6",
    fillOpacity: 0.15,
    weight: 2,
  });
  _layers.accuracy.addLayer(placeCircle);

  const marker = L.marker([markerLat, markerLon]);
  marker.bindPopup(`<strong>${safePinLabel}</strong>`);
  _layers.markers.addLayer(marker);

  if (accuracyM > 0) {
    const accuracyCircle = L.circle([markerLat, markerLon], {
      radius: accuracyM,
      color: "#22c55e",
      fillColor: "#22c55e",
      fillOpacity: 0.12,
      weight: 1,
    });
    _layers.accuracy.addLayer(accuracyCircle);
  }

  const bounds = boundsForCircle(lat, lon, radius);
  bounds.extend([markerLat, markerLon]);
  if (accuracyM > 0) {
    bounds.extend(boundsForCircle(markerLat, markerLon, accuracyM));
  }
  const padded = bounds.pad(0.18);
  _map.fitBounds(padded);
  refreshMapSize();
  const gen = _mapGeneration;
  setTimeout(() => {
    if (!_map || gen !== _mapGeneration) return;
    _map.invalidateSize({ pan: false });
    _map.fitBounds(padded);
  }, 150);
}

export function fitTrail() {
  if (!_map || !_layers.trail.getLayers().length) return;
  const group = L.featureGroup(_layers.trail.getLayers());
  _map.fitBounds(group.getBounds().pad(0.12));
}

function bringTrailLayersToFront() {
  if (!_map) return;
  for (const layer of [_layers.trail, _layers.markers, _layers.accuracy]) {
    try {
      layer?.bringToFront?.();
    } catch {
      // Best-effort stacking above the heatmap canvas.
    }
  }
}

export function clearHeatmap() {
  if (_layers.heatmap && _map) {
    _map.removeLayer(_layers.heatmap);
  }
  _layers.heatmap = null;
}

export function renderHeatmap(bins) {
  if (!_map) return;
  clearHeatmap();
  if (!bins?.length || typeof L.heatLayer !== "function") return;

  const max = bins.reduce((peak, bin) => Math.max(peak, bin.point_count || 0), 1);
  const points = bins.map((bin) => [
    bin.center_lat,
    bin.center_lon,
    bin.point_count / max,
  ]);

  _layers.heatmap = L.heatLayer(points, {
    radius: 24,
    blur: 20,
    maxZoom: 17,
    minOpacity: 0.3,
    gradient: {
      0.15: "#312e81",
      0.35: "#3b82f6",
      0.55: "#8b5cf6",
      0.75: "#f59e0b",
      1.0: "#ef4444",
    },
  });
  _layers.heatmap.addTo(_map);
  bringTrailLayersToFront();
}

export function setHeatmapVisible(visible) {
  if (!_map || !_layers.heatmap) return;
  if (visible) {
    if (!_map.hasLayer(_layers.heatmap)) {
      _layers.heatmap.addTo(_map);
    }
    bringTrailLayersToFront();
  } else {
    _map.removeLayer(_layers.heatmap);
  }
}

export function heatmapSupported() {
  return typeof L !== "undefined" && typeof L.heatLayer === "function";
}
