function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function initTripMap(el) {
  if (!el || typeof L === "undefined") return;

  let pins = [];
  try {
    pins = JSON.parse(el.dataset.pins || "[]");
  } catch (_) {}

  if (!pins.length) {
    if (el.dataset.mapState !== "map") {
      el.innerHTML = '<p class="trip-map-empty">Add locations to confirmed activities to see them on the map.</p>';
      el.dataset.mapState = "empty";
    }
    return;
  }

  if (el.dataset.mapState === "empty") {
    el.innerHTML = "";
    el.dataset.mapState = "";
  }

  if (el._leafletMap) {
    setTimeout(() => el._leafletMap.invalidateSize(), 100);
    return;
  }

  const map = L.map(el, { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
  }).addTo(map);

  const bounds = [];
  pins.forEach((pin, idx) => {
    const marker = L.marker([pin.lat, pin.lng]).addTo(map);
    marker.bindPopup(`<strong>${idx + 1}. ${escapeHtml(pin.title)}</strong>`);
    bounds.push([pin.lat, pin.lng]);
  });
  map.fitBounds(bounds, { padding: [24, 24] });
  el._leafletMap = map;
  el.dataset.mapState = "map";
  setTimeout(() => map.invalidateSize(), 100);
}

window.initTripMap = initTripMap;
