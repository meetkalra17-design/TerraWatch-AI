import { Fragment, useEffect, useState } from "react";
import { CircleMarker, MapContainer, Marker, Polygon, Popup, Polyline, ScaleControl, TileLayer, Tooltip, ZoomControl, useMap } from "react-leaflet";
import { DivIcon } from "leaflet";
import "leaflet/dist/leaflet.css";
import { appConfig } from "./config";
import RescueAssistant from "./RescueAssistant";

export type FloodZone = {
  name: string;
  place: string;
  lat: number;
  lng: number;
  severity: "Critical" | "High" | "Moderate";
  area: string;
  population: string;
  waterLevel: string;
  depth: number;
  footprint: [number, number][];
};

const footprint = (lat: number, lng: number, width: number, height: number): [number, number][] => [
  [lat + height, lng - width * .35], [lat + height * .45, lng + width * .8],
  [lat + height * .05, lng + width], [lat - height * .65, lng + width * .5],
  [lat - height, lng + width * .05], [lat - height * .8, lng - width * .75],
  [lat - height * .15, lng - width], [lat + height * .55, lng - width * .8],
];

export const ZONES: FloodZone[] = [
  { name: "Sutlej floodplain", place: "Ludhiana", lat: 30.901, lng: 75.857, severity: "Critical", area: "42.8 km²", population: "18,420 affected", waterLevel: "2.8 m", depth: 2.8, footprint: [[30.98, 75.61], [31.01, 75.74], [30.97, 75.87], [30.91, 75.98], [30.83, 75.94], [30.78, 75.81], [30.82, 75.68], [30.89, 75.58]] },
  { name: "Ghaggar basin", place: "Patiala", lat: 30.339, lng: 76.386, severity: "High", area: "28.4 km²", population: "11,760 affected", waterLevel: "1.9 m", depth: 1.9, footprint: [[30.43, 76.18], [30.47, 76.31], [30.42, 76.45], [30.35, 76.55], [30.25, 76.49], [30.21, 76.36], [30.25, 76.22], [30.34, 76.14]] },
  { name: "Beas river corridor", place: "Kapurthala", lat: 31.38, lng: 75.38, severity: "Moderate", area: "16.7 km²", population: "6,980 affected", waterLevel: "1.1 m", depth: 1.1, footprint: [[31.47, 75.22], [31.53, 75.34], [31.47, 75.48], [31.40, 75.57], [31.31, 75.50], [31.26, 75.37], [31.31, 75.25], [31.39, 75.18]] },
  { name: "Brahmaputra lowlands", place: "Guwahati", lat: 26.14, lng: 91.74, severity: "Critical", area: "54.2 km²", population: "32,100 affected", waterLevel: "3.2 m", depth: 3.2, footprint: footprint(26.14, 91.74, .55, .4) },
  { name: "Mithi urban corridor", place: "Mumbai", lat: 19.08, lng: 72.88, severity: "High", area: "31.6 km²", population: "26,500 affected", waterLevel: "1.6 m", depth: 1.6, footprint: footprint(19.08, 72.88, .3, .22) },
  { name: "Kochi backwater belt", place: "Kochi", lat: 9.97, lng: 76.28, severity: "Moderate", area: "19.8 km²", population: "9,100 affected", waterLevel: "1.2 m", depth: 1.2, footprint: footprint(9.97, 76.28, .3, .2) },
  { name: "Hooghly delta edge", place: "Kolkata", lat: 22.57, lng: 88.36, severity: "High", area: "37.5 km²", population: "20,400 affected", waterLevel: "1.8 m", depth: 1.8, footprint: footprint(22.57, 88.36, .35, .25) },
  { name: "Adyar basin", place: "Chennai", lat: 13.04, lng: 80.24, severity: "High", area: "24.9 km²", population: "15,600 affected", waterLevel: "1.5 m", depth: 1.5, footprint: footprint(13.04, 80.24, .3, .22) },
  { name: "Musi urban reach", place: "Hyderabad", lat: 17.39, lng: 78.47, severity: "Moderate", area: "13.4 km²", population: "7,300 affected", waterLevel: ".9 m", depth: .9, footprint: footprint(17.39, 78.47, .28, .2) },
  { name: "Rispana foothills", place: "Dehradun", lat: 30.32, lng: 78.03, severity: "High", area: "21.3 km²", population: "8,400 affected", waterLevel: "1.4 m", depth: 1.4, footprint: footprint(30.32, 78.03, .3, .25) },
];

const COLORS = { Critical: "#ff6d66", High: "#ffbd5b", Moderate: "#65cbe7" };
const THERMAL_COLORS = { Critical: "#ff3b30", High: "#ff9f0a", Moderate: "#ffe45e" };
const populationValue = (population: string) => Number(population.replace(/[^\d]/g, ""));
const RIVER_LINES: [number, number][][] = [
  [[32.1, 75.4], [31.7, 75.45], [31.3, 75.54], [30.9, 75.85], [30.35, 75.77]],
  [[29.2, 91.1], [27.8, 90.5], [26.14, 91.74], [25.2, 92.4]],
  [[23.4, 88.2], [22.57, 88.36], [21.7, 87.9]],
  [[12.4, 80.2], [13.04, 80.24], [13.6, 80.1]],
];
const MAP_CENTER: [number, number] = [22.8, 79.2];
const PLACE_LABELS = [
  { name: "Ludhiana", position: [30.901, 75.857] as [number, number] },
  { name: "Dehradun", position: [30.32, 78.03] as [number, number] },
  { name: "Guwahati", position: [26.14, 91.74] as [number, number] },
  { name: "Kolkata", position: [22.57, 88.36] as [number, number] },
  { name: "Mumbai", position: [19.08, 72.88] as [number, number] },
  { name: "Hyderabad", position: [17.39, 78.47] as [number, number] },
  { name: "Chennai", position: [13.04, 80.24] as [number, number] },
  { name: "Kochi", position: [9.97, 76.28] as [number, number] },
];

function MapPerspective({ zoom }: { zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView(MAP_CENTER, zoom, { animate: false });
    map.invalidateSize();
  }, [map, zoom]);
  return null;
}

export default function FloodMap() {
  const [satellite, setSatellite] = useState(true);
  const [thermal, setThermal] = useState(false);
  const [rescueMode, setRescueMode] = useState(true);
  const [compare, setCompare] = useState(false);
  const [waterOpacity, setWaterOpacity] = useState(0.42);
  const [perspective, setPerspective] = useState<"regional" | "detail">("regional");
  const mapZoom = perspective === "regional" ? 5.2 : 7.2;

  const mapTiles = (after: boolean) => (
    <TileLayer
      attribution={after ? "&copy; Esri, Maxar, Earthstar Geographics" : "&copy; OpenStreetMap contributors"}
      url={after ? appConfig.map.satelliteTiles : appConfig.map.streetTiles}
      className={`${thermal && after ? "thermal-tiles" : ""} ${rescueMode && after ? "rescue-tiles" : ""}`}
    />
  );

  const zoneLayers = (after: boolean) => ZONES.map((zone) => (
    <div key={`${after ? "after" : "before"}-${zone.name}`}>
      {after && <CircleMarker center={[zone.lat, zone.lng]} radius={rescueMode ? 13 : 10} pathOptions={{ color: "#ffffff", weight: rescueMode ? 3 : 2, fillColor: COLORS[zone.severity], fillOpacity: 0.95 }}>
        <Popup><strong>{zone.name}</strong><br />{zone.place}, India<br /><b>{zone.severity} risk</b> · {zone.area}<br />Water level: <b>{zone.waterLevel}</b><br />{zone.population}</Popup>
      </CircleMarker>}
      {after && <CircleMarker center={[zone.lat, zone.lng]} radius={18 + zone.depth * 5} pathOptions={{ color: "#55d7f0", fillColor: "#159bb5", fillOpacity: 0.18, weight: 2, opacity: 0.8 }}>
        <Tooltip direction="top" offset={[0, -8]}>{zone.waterLevel} water depth</Tooltip>
      </CircleMarker>}
      {after && <Polygon positions={zone.footprint} pathOptions={{ color: COLORS[zone.severity], fillColor: "#0787a5", fillOpacity: rescueMode ? Math.min(waterOpacity + .1, .8) : waterOpacity, weight: rescueMode ? 4 : 2, dashArray: rescueMode ? "8 5" : undefined }}><Tooltip sticky>{zone.name} · {zone.waterLevel} water depth</Tooltip></Polygon>}
    </div>
  ));
  const contextualLayers = (after: boolean) => <>
    {RIVER_LINES.map((line, index) => <Fragment key={index}><Polyline positions={line} pathOptions={{ color: "#0c7187", weight: 12, opacity: after ? .22 : .1, lineCap: "round" }} /><Polyline positions={line} pathOptions={{ color: "#64d9eb", weight: 2, opacity: after ? .9 : .35, dashArray: after ? undefined : "8 10" }} /></Fragment>)}
    {after && !rescueMode && PLACE_LABELS.map((place) => <Marker key={place.name} position={place.position} icon={new DivIcon({ className: "map-place-label", html: `<span>${place.name}</span>` })} />)}
  </>;
  const thermalLayers = ZONES.map((zone) => (
    <Fragment key={`thermal-${zone.name}`}>
      <CircleMarker center={[zone.lat, zone.lng]} radius={24 + zone.depth * 8} pathOptions={{ color: THERMAL_COLORS[zone.severity], fillColor: THERMAL_COLORS[zone.severity], fillOpacity: .1, weight: 3, opacity: .8 }}>
        <Tooltip sticky>{zone.name} · thermal proxy · {zone.depth} m depth</Tooltip>
      </CircleMarker>
      <CircleMarker center={[zone.lat, zone.lng]} radius={10 + zone.depth * 4} pathOptions={{ color: THERMAL_COLORS[zone.severity], fillColor: THERMAL_COLORS[zone.severity], fillOpacity: .52, weight: 1.5, opacity: .95 }}>
        <Popup><strong>{zone.name}</strong><br />{zone.place}, India<br /><b>{zone.severity} thermal proxy</b><br />Estimated water depth: {zone.waterLevel}</Popup>
      </CircleMarker>
    </Fragment>
  ));
  const rescueLayers = ZONES.map((zone, index) => (
    <Marker key={`rescue-${zone.name}`} position={[zone.lat, zone.lng]} icon={new DivIcon({
      className: "rescue-marker",
      html: `<span class="rescue-marker-rank">${index + 1}</span><span class="rescue-marker-label">${zone.place}</span>`,
    })}>
      <Tooltip direction="top" offset={[0, -18]}><b>Priority {index + 1}</b> · {zone.place}<br />{zone.area} · {zone.population}</Tooltip>
    </Marker>
  ));
  const priorityZones = [...ZONES].sort((a, b) => (b.depth - a.depth) || (populationValue(b.population) - populationValue(a.population))).slice(0, 4);

  return (
    <div className={`leaflet-map ${compare ? "compare-active" : ""} ${rescueMode ? "rescue-active" : ""}`}>
      {compare ? <div className="compare-layout">
        <div className="compare-maps">
          <div className="compare-panel"><span className="compare-label before-label">BEFORE · 08 AUG 2025</span><MapContainer center={MAP_CENTER} zoom={5.2} scrollWheelZoom={false} zoomControl={false}>{mapTiles(true)}<ScaleControl position="bottomleft" />{contextualLayers(false)}</MapContainer></div>
          <div className="compare-panel"><span className="compare-label after-label">AFTER · 24 AUG 2025</span><MapContainer center={MAP_CENTER} zoom={5.2} scrollWheelZoom={false} zoomControl={false}>{mapTiles(true)}<ScaleControl position="bottomleft" />{contextualLayers(true)}{zoneLayers(true)}</MapContainer></div>
          <div className="compare-split"><span>⇄</span><small>50%</small></div>
        </div>
        <aside className="compare-insight">
          <p className="eyebrow">SCENE INTELLIGENCE</p>
          <div className="compare-scene-title"><div><h3>Sutlej floodplain</h3><span>Ludhiana, Punjab · 30.901°N, 75.857°E</span></div><b>CRITICAL</b></div>
          <div className="compare-stats"><div><small>NEWLY FLOODED</small><strong className="amber-value">18.4%</strong></div><div><small>FLOOD EXTENT</small><strong>42.8 <em>km²</em></strong></div><div><small>WATER DEPTH</small><strong className="cyan-value">2.8 <em>m</em></strong></div><div><small>CONFIDENCE</small><strong className="green-value">94.2%</strong></div></div>
          <div className="compare-chart"><p>WATER COVERAGE SHIFT</p><div className="chart-bars"><i style={{ height: "48%" }} /><i style={{ height: "84%" }} /><i className="amber-bar" style={{ height: "34%" }} /></div><div><span>BEFORE</span><span>AFTER</span><span>NEW FLOOD</span></div></div>
          <div className="compare-note"><i /> Cyan overlay is modeled inundation extent derived from the image pair.</div>
        </aside>
      </div> : <MapContainer center={MAP_CENTER} zoom={5.2} minZoom={4} maxZoom={14} scrollWheelZoom={false} zoomControl={false}>{satellite || thermal ? mapTiles(true) : <TileLayer attribution="&copy; OpenStreetMap contributors" url={appConfig.map.streetTiles} />}<MapPerspective zoom={mapZoom} /><ZoomControl position="bottomright" /><ScaleControl position="bottomleft" />{contextualLayers(true)}{thermal ? thermalLayers : zoneLayers(true)}{rescueMode && rescueLayers}</MapContainer>}
      <div className="map-mode-toggle">
        <button className={compare ? "selected" : ""} type="button" onClick={() => setCompare(!compare)}>⇄ Compare</button>
        {!compare && <>
        <button className={satellite && !thermal ? "selected" : ""} type="button" onClick={() => { setSatellite(true); setThermal(false); }}>◎ Satellite</button>
        <button className={thermal ? "selected thermal-selected" : ""} type="button" onClick={() => { setSatellite(true); setThermal(true); }}>◉ Thermal</button>
        <button className={!satellite && !thermal ? "selected" : ""} type="button" onClick={() => { setSatellite(false); setThermal(false); }}>⌖ Streets</button>
        </>}
      </div>
      {!compare && <button className={`rescue-toggle ${rescueMode ? "selected" : ""}`} type="button" onClick={() => setRescueMode(!rescueMode)}>✚ {rescueMode ? "Rescue view on" : "Rescue view"}</button>}
      {!compare && <div className="map-perspective-toggle"><span>VIEW</span><button className={perspective === "regional" ? "selected" : ""} type="button" onClick={() => setPerspective("regional")}>Regional</button><button className={perspective === "detail" ? "selected" : ""} type="button" onClick={() => setPerspective("detail")}>Detail</button></div>}
      <label className="opacity-control">Flood overlay <input type="range" min="0.08" max="0.65" step="0.01" value={waterOpacity} onChange={(event) => setWaterOpacity(Number(event.target.value))} /><span>{Math.round(waterOpacity * 100)}%</span></label>
      <div className="imagery-badge"><span className="satellite-pulse" /> {compare ? "CHANGE DETECTION" : thermal ? "THERMAL PROXY VIEW" : "LIVE IMAGERY"} <small>{compare ? "Before vs after" : thermal ? "Modeled from flood depth · not sensor temperature" : "Esri World Imagery"}</small></div>
      <div className={thermal ? "thermal-level-key" : "water-level-key"}>{thermal ? <><span><i className="thermal-cool" /> Lower heat proxy</span><span><i className="thermal-hot" /> Higher heat proxy</span></> : <><span><i /> Water depth rings</span><span>1.1–2.8 m</span></>}</div>
      <div className="map-telemetry"><span><b>10 m</b><small>resolution</small></span><span><b>24 Aug 2025</b><small>capture date</small></span><span><b>94.2%</b><small>confidence</small></span></div>
      <div className="map-source"><i /> {thermal ? "SATELLITE CONTEXT + MODELED THERMAL PROXY" : "OBSERVED SATELLITE + MODELED EXTENT"}</div>
      <div className="map-coverage"><strong>9</strong><span>affected areas</span><small>8 states · 4 corridors</small></div>
      {!compare && rescueMode && <aside className="map-rescue-panel"><div className="rescue-panel-heading"><div><p>RESCUE PRIORITY</p><strong>Start with these areas</strong></div><span>LIVE ORDER</span></div>{priorityZones.map((zone, index) => <div className="rescue-row" key={zone.name}><b>{index + 1}</b><div><strong>{zone.place}</strong><small>{zone.severity} · {zone.area} · {zone.depth} m</small></div><span>{populationValue(zone.population).toLocaleString("en-IN")}<small>people</small></span></div>)}<p className="rescue-footnote">Priority combines estimated depth, severity, and affected population.</p></aside>}
      {!compare && rescueMode && <RescueAssistant zones={priorityZones} />}
      <div className="map-orientation"><strong>N</strong><span>↑</span><small>INDIA · AFFECTED AREAS</small></div>
      <div className="leaflet-legend"><span><i className="critical-dot" /> Critical</span><span><i className="high-dot" /> High</span><span><i className="moderate-dot" /> Moderate</span></div>
    </div>
  );
}
