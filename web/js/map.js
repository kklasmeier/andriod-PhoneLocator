let _map = null;
let _layers = { trail: null, markers: null, accuracy: null };

export function destroyMap() {
  if (_map) {
    _map.remove();
    _map = null;
    _layers = { trail: null, markers: null, accuracy: null };
  }
}

export function initMap(container, { tall = false } = {}) {
  destroyMap();
  const el = typeof container === "string" ? document.getElementById(container) : container;
  if (!el) return null;

  const panel = el.closest(".map-panel");
  if (panel && tall) panel.classList.add("tall");

  _map = L.map(el, { zoomControl: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
    maxZoom: 19,
  }).addTo(_map);

  _layers.trail = L.layerGroup().addTo(_map);
  _layers.markers = L.layerGroup().addTo(_map);
  _layers.accuracy = L.layerGroup().addTo(_map);

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

  setTimeout(() => _map.invalidateSize(), 100);
}

export function renderPlace({ lat, lon, name, radiusM = 50 }) {
  if (!_map) return;

  _layers.trail.clearLayers();
  _layers.markers.clearLayers();
  _layers.accuracy.clearLayers();

  const marker = L.marker([lat, lon]);
  const safeName = String(name || "Place").replace(/[<>&"]/g, (ch) => (
    { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[ch]
  ));
  marker.bindPopup(`<strong>${safeName}</strong>`);
  _layers.markers.addLayer(marker);

  const radius = radiusM > 0 ? radiusM : 50;
  const circle = L.circle([lat, lon], {
    radius,
    color: "#3b82f6",
    fillColor: "#3b82f6",
    fillOpacity: 0.15,
    weight: 2,
  });
  _layers.accuracy.addLayer(circle);

  _map.setView([lat, lon], 16);
  setTimeout(() => _map.invalidateSize(), 100);
}

export function fitTrail() {
  if (!_map || !_layers.trail.getLayers().length) return;
  const group = L.featureGroup(_layers.trail.getLayers());
  _map.fitBounds(group.getBounds().pad(0.12));
}
