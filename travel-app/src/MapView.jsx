import { useEffect, useRef } from "react";
import L from "leaflet";

// Imperative Leaflet wrapper. We avoid react-leaflet to dodge version coupling;
// the map is created once and the selected team's journey layer is swapped on change.
export default function MapView({ venues, team }) {
  const elRef = useRef(null);
  const mapRef = useRef(null);
  const journeyRef = useRef(null);
  const baseRef = useRef(null);

  // one-time init: base map + faint dots for all 16 venues
  useEffect(() => {
    const map = L.map(elRef.current, { scrollWheelZoom: false, attributionControl: true });
    map.setView([38, -97], 3);
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      { attribution: "&copy; OpenStreetMap &copy; CARTO", subdomains: "abcd", maxZoom: 19 }
    ).addTo(map);

    const base = L.layerGroup().addTo(map);
    Object.values(venues).forEach((v) => {
      L.circleMarker([v.lat, v.lon], {
        radius: 3, color: "#b9ab97", weight: 1, fillColor: "#cdbfa9", fillOpacity: 0.7,
      }).addTo(base).bindTooltip(`${v.city}`, { direction: "top" });
    });
    mapRef.current = map;
    baseRef.current = base;
    return () => map.remove();
  }, [venues]);

  // redraw journey when the selected team changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !team) return;
    if (journeyRef.current) journeyRef.current.remove();
    const layer = L.layerGroup().addTo(map);
    journeyRef.current = layer;

    // Draw each leg as a gentle arc, bowing alternate directions. A round trip
    // (e.g. Kansas City → SF → Kansas City) then reads as a visible loop rather
    // than a line drawn back over itself.
    const bounds = L.latLngBounds([]);
    for (let i = 1; i < team.legs.length; i++) {
      const a = [team.legs[i - 1].lat, team.legs[i - 1].lon];
      const b = [team.legs[i].lat, team.legs[i].lon];
      const pts = arc(a, b, i % 2 === 0 ? -0.18 : 0.18);
      const line = L.polyline(pts, { color: "#b06a16", weight: 3, opacity: 0.9 }).addTo(layer);
      pts.forEach((p) => bounds.extend(p));
      const el = line.getElement();
      if (el) {
        el.style.setProperty("--len", el.getTotalLength());
        el.style.animationDelay = `${(i - 1) * 0.5}s`;
        el.classList.add("journey-path");
      }
    }

    // Collapse repeated venues into one pin, labelled with every leg-number it
    // hosts ("1·3") and flagged as a return so the back-and-forth is intentional.
    const stops = new Map();
    team.legs.forEach((l, i) => {
      if (!stops.has(l.venue))
        stops.set(l.venue, { lat: l.lat, lon: l.lon, city: l.city, alt: l.alt, visits: [] });
      stops.get(l.venue).visits.push({ order: i + 1, date: l.date, opponent: l.opponent });
    });

    stops.forEach((s) => {
      const isAlt = s.alt >= 1500;
      const isReturn = s.visits.length > 1;
      const label = s.visits.map((v) => v.order).join("·");
      const cls = `venue-pin ${isAlt ? "alt" : ""} ${isReturn ? "multi" : ""}`;
      const icon = L.divIcon({
        className: "",
        html: `<div class="${cls}">${label}</div>`,
        iconSize: [0, 0], iconAnchor: [0, 0],
      });
      const altLine = isAlt ? `<br><span style="color:#c0533b">▲ ${s.alt} m</span>` : "";
      const visitLines = s.visits.map((v) => `${v.date} · vs ${v.opponent}`).join("<br>");
      const returnTag = isReturn ? `<br><span style="color:#b06a16">↻ returns here (matches ${label})</span>` : "";
      L.marker([s.lat, s.lon], { icon })
        .addTo(layer)
        .bindTooltip(`<b>${s.city}</b><br>${visitLines}${altLine}${returnTag}`,
          { direction: "top", offset: [0, -16] });
    });

    map.fitBounds(bounds, { padding: [55, 55], maxZoom: 6, animate: true });
  }, [team]);

  return <div id="map" ref={elRef} />;
}

// Sample a quadratic bezier whose control point is offset perpendicular to the
// leg by `bow` (fraction of leg length). Positive/negative bow = opposite sides.
function arc(a, b, bow) {
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const cx = mx - dy * bow, cy = my + dx * bow; // perpendicular offset
  const out = [];
  for (let t = 0; t <= 1.0001; t += 0.05) {
    const u = 1 - t;
    out.push([
      u * u * a[0] + 2 * u * t * cx + t * t * b[0],
      u * u * a[1] + 2 * u * t * cy + t * t * b[1],
    ]);
  }
  return out;
}
