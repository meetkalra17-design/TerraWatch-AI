import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { createUserWithEmailAndPassword, onAuthStateChanged, signInWithEmailAndPassword, signOut, type User } from "firebase/auth";
import { doc, getDoc, setDoc } from "firebase/firestore";
import { jsPDF } from "jspdf";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getFloodPredictions, getStatus, type FloodPrediction } from "./api";
import { auth, getDb } from "./firebase";
import { appConfig } from "./config";
import FloodMap from "./FloodMap";
import { ALL_CITIES, INDIA_STATES } from "./locations";
import { FLOOD_ZONES, type FloodZone, type Severity } from "./domain";

type SortMode = "relevance" | "newest" | "popular" | "rating";
type Page = "overview" | "explore" | "map" | "reports" | "predictions" | "profile";
type Filters = { state: string; city: string; severity: Severity | "All"; category: string; date: string; sort: SortMode };
const DEFAULT_FILTERS: Filters = { state: "All India", city: "All cities", severity: "All", category: "All categories", date: "Any date", sort: "relevance" };
const formatNumber = (value: number) => new Intl.NumberFormat("en-IN").format(value);
const chartColors = { Critical: "#fb7185", High: "#fbbf24", Moderate: "#67e8f9" } as const;
const downloadFile = (content: BlobPart, filename: string, type: string) => {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
};

export default function App() {
  const [page, setPage] = useState<Page>(() => {
    const value = window.location.hash.slice(1);
    return ["overview", "explore", "map", "reports", "predictions", "profile"].includes(value) ? value as Page : "overview";
  });
  const [user, setUser] = useState<User | null>(null);
  const [email, setEmail] = useState("operator@terrawatch.ai");
  const [password, setPassword] = useState("Terra@2026");
  const [authMode, setAuthMode] = useState<"signIn" | "register">("signIn");
  const [error, setError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [mobileFilters, setMobileFilters] = useState(false);
  const [selectedZone, setSelectedZone] = useState<FloodZone>(FLOOD_ZONES[0]);
  const [favorites, setFavorites] = useState<string[]>(() => JSON.parse(localStorage.getItem("terrawatch:favorites") || "[]") as string[]);
  const [recent, setRecent] = useState<string[]>(() => JSON.parse(localStorage.getItem("terrawatch:recent") || "[]") as string[]);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileName, setProfileName] = useState(() => localStorage.getItem("terrawatch:profile-name") || "");
  const [geoMessage, setGeoMessage] = useState("");
  const status = useQuery({ queryKey: ["status"], queryFn: getStatus, retry: 1 });
  const predictions = useQuery({ queryKey: ["flood-predictions"], queryFn: getFloodPredictions, enabled: Boolean(user), retry: 1, staleTime: 10 * 60 * 1000 });

  useEffect(() => onAuthStateChanged(auth, setUser), []);
  useEffect(() => {
    const onHashChange = () => {
      const value = window.location.hash.slice(1);
      setPage(["overview", "explore", "map", "reports", "predictions", "profile"].includes(value) ? value as Page : "overview");
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [page]);
  useEffect(() => {
    if (page === "profile") setProfileOpen(true);
  }, [page]);
  useEffect(() => {
    if (!user || !appConfig.firestoreEnabled) return;
    try {
      void getDoc(doc(getDb(), "users", user.uid)).then((snapshot) => {
        const data = snapshot.data();
        if (!data) return;
        if (typeof data.displayName === "string") setProfileName(data.displayName);
        if (Array.isArray(data.favoriteZoneIds)) setFavorites(data.favoriteZoneIds.filter((id): id is string => typeof id === "string"));
        if (Array.isArray(data.recentZoneIds)) setRecent(data.recentZoneIds.filter((id): id is string => typeof id === "string"));
      }).catch(() => setGeoMessage("Using local preferences until Firestore is enabled."));
    } catch {
      setGeoMessage("Using local preferences until Firestore is enabled.");
    }
  }, [user]);
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 280);
    return () => window.clearTimeout(timer);
  }, [searchInput]);
  useEffect(() => localStorage.setItem("terrawatch:favorites", JSON.stringify(favorites)), [favorites]);
  useEffect(() => localStorage.setItem("terrawatch:recent", JSON.stringify(recent)), [recent]);

  const stateCities = useMemo(() => filters.state === "All India" ? Array.from(new Set(ALL_CITIES.map(({ city }) => city))) : INDIA_STATES.find(({ name }) => name === filters.state)?.cities || [], [filters.state]);
  const filteredZones = useMemo(() => {
    const query = search.toLowerCase();
    return FLOOD_ZONES.filter((zone) =>
      (!query || `${zone.region} ${zone.city} ${zone.state} ${zone.category}`.toLowerCase().includes(query)) &&
      (filters.state === "All India" || zone.state === filters.state) &&
      (filters.city === "All cities" || zone.city === filters.city) &&
      (filters.severity === "All" || zone.severity === filters.severity) &&
      (filters.category === "All categories" || zone.category === filters.category) &&
      (filters.date === "Any date" || (filters.date === "Last 7 days" ? zone.updatedAt >= "2025-08-18" : zone.updatedAt >= "2025-08-01")),
    ).sort((a, b) => filters.sort === "newest" ? b.updatedAt.localeCompare(a.updatedAt) : filters.sort === "popular" ? b.population - a.population : filters.sort === "rating" ? b.rating - a.rating : b.change - a.change);
  }, [filters, search]);
  const reportSummary = useMemo(() => ({
    area: filteredZones.reduce((sum, zone) => sum + zone.area, 0),
    population: filteredZones.reduce((sum, zone) => sum + zone.population, 0),
    averageDepth: filteredZones.length ? filteredZones.reduce((sum, zone) => sum + zone.depth, 0) / filteredZones.length : 0,
    critical: filteredZones.filter((zone) => zone.severity === "Critical").length,
    categories: Array.from(new Set(filteredZones.map((zone) => zone.category))).map((category) => ({
      category,
      count: filteredZones.filter((zone) => zone.category === category).length,
    })).sort((a, b) => b.count - a.count),
  }), [filteredZones]);

  function updateFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value, ...(key === "state" ? { city: "All cities" } : {}) }));
  }
  function chooseZone(zone: FloodZone) {
    setSelectedZone(zone);
    setRecent((items) => [zone.id, ...items.filter((id) => id !== zone.id)].slice(0, 5));
  }
  function detectLocation() {
    if (!navigator.geolocation) { setGeoMessage("Location detection is not supported by this browser."); return; }
    setGeoMessage("Requesting location permission…");
    navigator.geolocation.getCurrentPosition(() => setGeoMessage("Location detected. Nearby alerts are ready for review."), () => setGeoMessage("Location permission was denied. You can still browse all India."));
  }
  function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true); setError("");
    const action = authMode === "signIn" ? signInWithEmailAndPassword(auth, email, password) : createUserWithEmailAndPassword(auth, email, password);
    void action.catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Authentication failed. Check your Firebase Auth provider.")).finally(() => setAuthBusy(false));
  }
  function clearFilters() { setFilters(DEFAULT_FILTERS); setSearchInput(""); }
  function toggleFavorite(id: string) { setFavorites((items) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]); }
  async function savePreferences() {
    localStorage.setItem("terrawatch:profile-name", profileName);
    if (user && appConfig.firestoreEnabled) {
      try {
        await setDoc(doc(getDb(), "users", user.uid), { displayName: profileName, favoriteZoneIds: favorites, recentZoneIds: recent, updatedAt: new Date().toISOString() }, { merge: true });
        setGeoMessage("Profile preferences synced to Firestore.");
      } catch {
        setGeoMessage("Saved locally. Firestore is not enabled yet for this project.");
      }
    }
    setProfileOpen(false);
  }

  if (!user) {
    return <main className="shell"><section><p className="eyebrow">INDIA-WIDE FLOOD INTELLIGENCE</p><h1>See risk before it reaches the doorstep.</h1><p className="lede">TerraWatch turns satellite change detection into clear, location-aware decisions for every state and union territory in India.</p><div className="login-highlights"><span>◈ 36 regions covered</span><span>◉ 10 m satellite context</span><span>⌁ Response-ready insights</span></div></section><form className="panel auth-panel" onSubmit={submitAuth}><p className="eyebrow">{authMode === "signIn" ? "MISSION CONTROL ACCESS" : "CREATE OPERATOR ACCOUNT"}</p><h2>{authMode === "signIn" ? "Welcome back" : "Join TerraWatch"}</h2><label>Email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} required /></label>{error && <p className="error">{error}</p>}<button disabled={authBusy}>{authBusy ? "Connecting…" : authMode === "signIn" ? "Sign in securely" : "Create account"}</button><button className="link-button" type="button" onClick={() => { setAuthMode(authMode === "signIn" ? "register" : "signIn"); setError(""); }}>{authMode === "signIn" ? "Need an account? Register" : "Already registered? Sign in"}</button><div className="status"><i className={`dot ${status.isSuccess ? "online" : ""}`} /> API {status.isSuccess ? "connected" : status.isLoading ? "checking…" : "offline"}</div></form></main>;
  }

  const activeFilters = Object.entries(filters).filter(([key, value]) => value !== DEFAULT_FILTERS[key as keyof Filters] && key !== "sort");
  const recommendations = FLOOD_ZONES.filter((zone) => zone.state === filters.state || filters.state === "All India").slice(0, 3);
  const recentZones = recent.map((id) => FLOOD_ZONES.find((zone) => zone.id === id)).filter((zone): zone is FloodZone => Boolean(zone));
  const severityChartData = (["Critical", "High", "Moderate"] as const).map((severity) => ({
    name: severity,
    value: filteredZones.filter((zone) => zone.severity === severity).length,
  }));
  const stateChartData = Array.from(new Set(filteredZones.map((zone) => zone.state))).map((state) => ({
    state: state.replace("Andaman and Nicobar Islands", "A&N").replace("West Bengal", "W. Bengal"),
    population: filteredZones.filter((zone) => zone.state === state).reduce((sum, zone) => sum + zone.population, 0),
  })).sort((a, b) => b.population - a.population).slice(0, 6);
  const trendChartData = Array.from(new Set(filteredZones.map((zone) => zone.updatedAt))).sort().map((date) => ({
    date: new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(`${date}T00:00:00`)),
    area: Number(filteredZones.filter((zone) => zone.updatedAt === date).reduce((sum, zone) => sum + zone.area, 0).toFixed(1)),
  }));
  const topPredictions = predictions.data?.predictions.slice(0, 6) || [];
  const predictionLevelClass = (prediction: FloodPrediction) => `severity ${prediction.level}`;
  const pageTitles: Record<Page, string> = {
    overview: "Mission overview",
    explore: "Explore intelligence",
    map: "Flood map",
    predictions: "Upcoming predictions",
    reports: "Situation reports",
    profile: "Operator profile",
  };
  const pageDescriptions: Record<Page, string> = {
    overview: "A quick read of active signals, exposure, and response priorities.",
    explore: "Search and filter detected flood intelligence by place, severity, and category.",
    map: "Inspect affected areas, imagery layers, and rescue priorities on the operational map.",
    predictions: "Review the next seven days of model-scored rainfall and river risk.",
    reports: "Create a concise situation report for briefing and coordinated response.",
    profile: "Manage your operator identity, saved alerts, and viewing preferences.",
  };
  function exportCsv() {
    const header = ["Region", "City", "State", "Severity", "Category", "Flooded area (km2)", "Affected population", "Depth (m)", "Change (%)", "Updated"];
    const rows = filteredZones.map((zone) => [zone.region, zone.city, zone.state, zone.severity, zone.category, zone.area, zone.population, zone.depth, zone.change, zone.updatedAt]);
    downloadFile([header, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n"), `terrawatch-report-${new Date().toISOString().slice(0, 10)}.csv`, "text/csv;charset=utf-8");
  }
  function exportPdf() {
    const pdf = new jsPDF();
    pdf.setFontSize(18); pdf.text("TerraWatch AI — Flood Intelligence Report", 18, 20);
    pdf.setFontSize(9); pdf.setTextColor(100); pdf.text(`Scope: ${filters.state} / ${filters.city} · Generated ${new Date().toLocaleString("en-IN")}`, 18, 28);
    pdf.setTextColor(25); pdf.setFontSize(11);
    pdf.text(`Alerts: ${filteredZones.length}   Flooded area: ${reportSummary.area.toFixed(1)} km²   Affected population: ${formatNumber(reportSummary.population)}`, 18, 42);
    pdf.text(`Critical zones: ${reportSummary.critical}   Average depth: ${reportSummary.averageDepth.toFixed(1)} m`, 18, 50);
    pdf.setFontSize(10); pdf.text("Priority incidents", 18, 64);
    filteredZones.slice(0, 12).forEach((zone, index) => pdf.text(`${index + 1}. ${zone.city}, ${zone.state} — ${zone.severity} — ${zone.area} km² — ${formatNumber(zone.population)} people — ${zone.depth} m`, 18, 73 + index * 8));
    pdf.setFontSize(8); pdf.setTextColor(100); pdf.text("Data note: flood extents, depths, populations, and confidence values are modeled/demo intelligence unless connected to a live analysis pipeline.", 18, 180);
    pdf.save(`terrawatch-report-${new Date().toISOString().slice(0, 10)}.pdf`);
  }

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">T</span><span>TerraWatch <b>AI</b></span></div><p className="nav-label">MISSION CONTROL</p><nav><a className={`nav-item ${page === "overview" ? "active" : ""}`} href="#overview">◈ <span>Overview</span></a><a className={`nav-item ${page === "explore" ? "active" : ""}`} href="#explore">⌕ <span>Explore intelligence</span></a><a className={`nav-item ${page === "map" ? "active" : ""}`} href="#map">⌖ <span>Flood map</span></a><a className={`nav-item ${page === "predictions" ? "active" : ""}`} href="#predictions">⌁ <span>Predictions</span></a>    <a className={`nav-item ${page === "reports" ? "active" : ""}`} href="#reports">▤ <span>Reports</span></a><a className={`nav-item mobile-profile-link ${page === "profile" ? "active" : ""}`} href="#profile">⚙ <span>Profile</span></a></nav><div className="coverage-card"><p className="eyebrow">INDIA COVERAGE</p><strong>36 regions</strong><small>28 states · 8 UTs</small><div className="coverage-progress"><i /></div></div><div className="sidebar-bottom"><a className={`profile-button ${page === "profile" ? "active" : ""}`} href="#profile"><span className="avatar">{(user.email || "O").slice(0, 1).toUpperCase()}</span><span><strong>{profileName || user.email}</strong><small>Operator profile</small></span><b>⚙</b></a><button className="signout" type="button" onClick={() => void signOut(auth)}>Sign out</button></div></aside>
    <main className={`dashboard page-${page}`} id={page}>
      <header className="topbar"><div><p className="eyebrow">SATELLITE FLOOD INTELLIGENCE</p><h1>{pageTitles[page]}</h1></div><div className="top-actions"><span className="live"><i /> Live system</span><button className="primary" type="button" onClick={() => { window.location.hash = "map"; }}>+ New analysis</button></div></header>
      <section className="page-context"><div><span className="breadcrumb">Mission control <b>/</b> {pageTitles[page]}</span><p>{pageDescriptions[page]}</p></div><span className="context-scope">India · IST</span></section>
      <section className="welcome overview-hero"><div><p className="eyebrow">LOCATION-AWARE OPERATIONS</p><h2>Monitor India with clarity.</h2><p>Search alerts, compare flood footprints, and coordinate response from one workspace.</p></div><div className="date-chip">{new Date().toLocaleDateString("en-IN", { weekday: "short", month: "short", day: "numeric" })}<small>India Standard Time</small></div></section>
      <section className="location-toolbar card overview-search"><div className="search-wrap"><span>⌕</span><input aria-label="Search India flood intelligence" placeholder="Search city, state, basin or alert…" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />{searchInput && <button className="clear-search" type="button" onClick={() => setSearchInput("")}>×</button>}</div><button className="nearby-button" type="button" onClick={detectLocation}>◎ Use my location</button><button className="filter-toggle" type="button" onClick={() => setMobileFilters(true)}>☷ Filters {activeFilters.length > 0 && <b>{activeFilters.length}</b>}</button></section>
      {geoMessage && <div className="notice success-notice">◉ {geoMessage}</div>}
      <section className="metrics overview-metrics"><article><span>Signals monitored</span><strong>{filteredZones.length ? formatNumber(filteredZones.length * 18 + 74) : "—"}</strong><small className="up">↑ 12.5% this month</small></article><article><span>Flooded area</span><strong>{filteredZones.length ? `${filteredZones.reduce((sum, zone) => sum + zone.area, 0).toFixed(1)} km²` : "0 km²"}</strong><small className="up">Across selected scope</small></article><article><span>Critical zones</span><strong>{filteredZones.filter((zone) => zone.severity === "Critical").length.toString().padStart(2, "0")}</strong><small>Require immediate action</small></article><article><span>API status</span><strong className={status.isSuccess ? "green" : ""}>{status.isSuccess ? "Online" : status.isLoading ? "…" : "Offline"}</strong><small>{status.isSuccess ? "All systems operational" : "Check backend service"}</small></article></section>
      <section className="visualizations"><div className="visualization-heading"><div><p className="eyebrow">DATA PERSPECTIVE</p><h3>Flood signal breakdown</h3></div><span className="result-meta">{filteredZones.length} filtered alerts</span></div><div className="visualization-grid"><article className="chart-panel"><div className="chart-panel-heading"><div><h4>Risk distribution</h4><p>Alerts by severity level</p></div><span className="chart-total">{filteredZones.length}</span></div>{filteredZones.length ? <div className="donut-layout"><div className="donut-chart"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={severityChartData} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="84%" paddingAngle={3} stroke="none">{severityChartData.map((entry) => <Cell key={entry.name} fill={chartColors[entry.name]} />)}</Pie><Tooltip contentStyle={{ background: "#0b1728", border: "1px solid #29455f", borderRadius: "4px", color: "#e8f3fa" }} /></PieChart></ResponsiveContainer><strong>{filteredZones.length}</strong><small>alerts</small></div><div className="chart-legend">{severityChartData.map((entry) => <div key={entry.name}><i style={{ background: chartColors[entry.name] }} /><span>{entry.name}</span><b>{entry.value}</b></div>)}</div></div> : <div className="chart-empty-state">No severity data in this view.</div>}</article><article className="chart-panel chart-wide"><div className="chart-panel-heading"><div><h4>Population exposure</h4><p>Estimated affected population by state</p></div><span className="chart-unit">people</span></div>{stateChartData.length ? <ResponsiveContainer width="100%" height={185}><BarChart data={stateChartData} layout="vertical" margin={{ top: 4, right: 12, left: 0, bottom: 4 }}><CartesianGrid horizontal={false} stroke="#20344a" /><XAxis type="number" hide /><YAxis type="category" dataKey="state" width={72} tick={{ fill: "#8295a9", fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip cursor={{ fill: "#10243a" }} contentStyle={{ background: "#0b1728", border: "1px solid #29455f", borderRadius: "4px", color: "#e8f3fa" }} /><Bar dataKey="population" fill="#67e8f9" radius={[0, 3, 3, 0]} barSize={13} /></BarChart></ResponsiveContainer> : <div className="chart-empty-state">No population data in this view.</div>}</article><article className="chart-panel chart-wide"><div className="chart-panel-heading"><div><h4>Flooded area trend</h4><p>Detected footprint across capture dates</p></div><span className="chart-unit">km²</span></div>{trendChartData.length ? <ResponsiveContainer width="100%" height={185}><AreaChart data={trendChartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}><defs><linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#22d3ee" stopOpacity={0.38} /><stop offset="100%" stopColor="#22d3ee" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#20344a" vertical={false} /><XAxis dataKey="date" tick={{ fill: "#8295a9", fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: "#8295a9", fontSize: 10 }} axisLine={false} tickLine={false} width={34} /><Tooltip contentStyle={{ background: "#0b1728", border: "1px solid #29455f", borderRadius: "4px", color: "#e8f3fa" }} /><Area type="monotone" dataKey="area" stroke="#67e8f9" strokeWidth={2} fill="url(#areaFill)" /></AreaChart></ResponsiveContainer> : <div className="chart-empty-state">No trend data in this view.</div>}</article></div></section>
      <section className="reports-section" id="reports"><div className="reports-heading"><div><p className="eyebrow">OPERATIONS REPORTING</p><h3>Situation report</h3><p>Export the current filtered intelligence for briefing, dispatch, and response coordination.</p></div><div className="report-actions"><button type="button" onClick={exportCsv}>↓ CSV</button><button type="button" onClick={exportPdf}>↓ PDF report</button></div></div><div className="report-summary"><div><span>Signals</span><strong>{filteredZones.length}</strong></div><div><span>Flooded area</span><strong>{reportSummary.area.toFixed(1)} <small>km²</small></strong></div><div><span>People exposed</span><strong>{formatNumber(reportSummary.population)}</strong></div><div><span>Average depth</span><strong>{reportSummary.averageDepth.toFixed(1)} <small>m</small></strong></div></div><div className="report-body"><div><h4>Coverage by category</h4>{reportSummary.categories.map((item) => <div className="report-bar" key={item.category}><span>{item.category}</span><b>{item.count}</b><i><u style={{ width: `${filteredZones.length ? item.count / filteredZones.length * 100 : 0}%` }} /></i></div>)}</div><div><h4>Priority incidents</h4>{filteredZones.slice(0, 4).map((zone) => <div className="report-incident" key={zone.id}><span className={`severity ${zone.severity.toLowerCase()}`}>{zone.severity}</span><div><strong>{zone.city}, {zone.state}</strong><small>{zone.area} km² · {formatNumber(zone.population)} people · {zone.depth} m</small></div></div>)}</div></div><p className="report-disclaimer">Operational note: this report contains modeled/demo flood intelligence. Confirm with current field observations and official emergency channels before dispatch.</p></section>
      <section className="reports-section prediction-section" id="predictions"><div className="reports-heading"><div><p className="eyebrow">MODEL FORECAST · 7 DAYS</p><h3>Upcoming flood risk across India</h3><p>Seven-day risk outlook powered by rainfall and river forecasts.</p></div><button className="report-refresh" type="button" onClick={() => void predictions.refetch()} disabled={predictions.isFetching}>{predictions.isFetching ? "Refreshing…" : "Refresh forecast"}</button></div>{predictions.isLoading && <p className="notice">Loading forecast inputs across India…</p>}{predictions.isError && <p className="notice error">Forecast unavailable: {predictions.error instanceof Error ? predictions.error.message : "Check the backend connection and Open-Meteo availability."}</p>}{topPredictions.length > 0 && <><div className="report-summary"><div><span>Locations scored</span><strong>{predictions.data?.predictions.length}</strong></div><div><span>High or critical</span><strong>{predictions.data?.predictions.filter((item) => item.level === "high" || item.level === "critical").length}</strong></div><div><span>Peak risk</span><strong>{topPredictions[0].risk.toFixed(1)}<small>%</small></strong></div><div><span>Horizon</span><strong>{predictions.data?.horizonDays}<small> days</small></strong></div></div><div className="report-body prediction-list"><div><h4>Ranked locations</h4>{topPredictions.map((prediction) => <div className="report-incident" key={`${prediction.city}-${prediction.state}`}><span className={predictionLevelClass(prediction)}>{prediction.level}</span><div><strong>{prediction.city}, {prediction.state}</strong><small>{prediction.risk.toFixed(1)}% risk · {prediction.forecastRain7mm} mm rain · {prediction.forecastRiverRatio}× river baseline · {prediction.coverage}</small></div></div>)}</div><div><h4>Model context</h4><p className="report-disclaimer">{predictions.data?.warning}</p><p className="report-disclaimer">Scope: {predictions.data?.scope}. Sikkim and other non-Punjab locations are currently exploratory until India-wide training is completed.</p></div></div></>}</section>
      <section className="explorer-layout"><aside className={`filter-panel ${mobileFilters ? "open" : ""}`}><div className="filter-heading"><div><p className="eyebrow">EXPLORE INDIA</p><h3>Filter alerts</h3></div><button className="panel-close" type="button" onClick={() => setMobileFilters(false)}>×</button></div><label>State / union territory<select value={filters.state} onChange={(event) => updateFilter("state", event.target.value)}><option>All India</option>{INDIA_STATES.map((state) => <option key={state.code}>{state.name}</option>)}</select></label><label>City / district<select value={filters.city} onChange={(event) => updateFilter("city", event.target.value)}><option>All cities</option>{stateCities.map((city) => <option key={city}>{city}</option>)}</select></label><label>Risk level<select value={filters.severity} onChange={(event) => updateFilter("severity", event.target.value as Filters["severity"])}><option>All</option><option>Critical</option><option>High</option><option>Moderate</option></select></label><label>Category<select value={filters.category} onChange={(event) => updateFilter("category", event.target.value)}><option>All categories</option><option>River basin</option><option>Urban flooding</option><option>Coastal risk</option><option>Mountain runoff</option></select></label><label>Time window<select value={filters.date} onChange={(event) => updateFilter("date", event.target.value)}><option>Any date</option><option>Last 7 days</option><option>This season</option></select></label><label>Sort by<select value={filters.sort} onChange={(event) => updateFilter("sort", event.target.value as SortMode)}><option value="relevance">Relevance</option><option value="newest">Newest first</option><option value="popular">Most impacted</option><option value="rating">Highest confidence</option></select></label><button className="reset-button" type="button" onClick={clearFilters}>Clear all filters</button></aside>
        <div className="results-column"><div className="results-heading"><div><p className="eyebrow">ALERT EXPLORER · {filters.state}</p><h3>{filteredZones.length} intelligence signals</h3></div><span className="result-meta">INR-ready · India format</span></div>{activeFilters.length > 0 && <div className="filter-tags">{activeFilters.map(([key, value]) => <button key={key} type="button" onClick={() => updateFilter(key as keyof Filters, DEFAULT_FILTERS[key as keyof Filters])}>{value} ×</button>)}</div>}{filteredZones.length === 0 ? <div className="empty-state"><span>⌁</span><h3>No alerts match these filters</h3><p>Try broadening your location or clearing a filter.</p><button className="secondary-button" type="button" onClick={clearFilters}>Reset view</button></div> : <div className="zone-list">{filteredZones.map((zone) => <button className="zone-row enhanced-zone" type="button" key={zone.id} onClick={() => chooseZone(zone)}><img src={zone.image} alt="" /><span className="zone-copy"><strong>{zone.region}</strong><small>{zone.city}, {zone.state} · {zone.category}</small></span><span className={`severity ${zone.severity.toLowerCase()}`}>{zone.severity}</span><span className="zone-stat"><strong>{zone.area} km²</strong><small>{zone.rating} confidence</small></span><span className={`favorite ${favorites.includes(zone.id) ? "saved" : ""}`} onClick={(event) => { event.stopPropagation(); toggleFavorite(zone.id); }}>{favorites.includes(zone.id) ? "★" : "☆"}</span></button>)}</div>}</div></section>
      <section className="recommendation-row"><article className="card recommendation-card"><p className="eyebrow">RECOMMENDED FOR YOU</p><h3>Priority alerts near {filters.state === "All India" ? "your watchlist" : filters.state}</h3><div className="mini-recommendations">{recommendations.map((zone) => <button type="button" key={zone.id} onClick={() => chooseZone(zone)}><span className={`severity ${zone.severity.toLowerCase()}`}>{zone.severity}</span><strong>{zone.city}</strong><small>{zone.area} km² · {zone.change}% change</small></button>)}</div></article>{recentZones.length > 0 && <article className="card recent-card"><p className="eyebrow">RECENTLY VIEWED</p><h3>Continue monitoring</h3>{recentZones.slice(0, 3).map((zone) => <button className="recent-item" type="button" key={zone.id} onClick={() => chooseZone(zone)}><span>{zone.city}, {zone.state}</span><b>{zone.severity}</b></button>)}</article>}</section>
      <section className="card map-card" id="map"><div className="card-heading"><div><p className="eyebrow">REGIONAL MONITOR</p><h3>{filters.state === "All India" ? "India flood overview" : `${filters.state} flood overview`}</h3><span className="subheading">Sentinel-2 composite · 10 m resolution · 24 Aug 2025</span></div><span className="map-status"><i /> Imagery synced</span></div><FloodMap /></section>
      <section className="insight-grid"><article className="card zone-detail"><div className="card-heading"><div><p className="eyebrow">SELECTED ZONE</p><h3>{selectedZone.region}</h3><span className="subheading">{selectedZone.city}, {selectedZone.state}</span></div><span className={`severity ${selectedZone.severity.toLowerCase()}`}>{selectedZone.severity}</span></div><div className="zone-detail-main"><div className="depth-readout"><span className="depth-value">{selectedZone.depth}m</span><span>estimated water depth</span></div><div className="confidence-readout"><strong>{selectedZone.rating * 20}%</strong><span>model confidence</span></div></div><div className="detail-bars"><span><label>Flood extent <em>{selectedZone.area} km²</em></label><i><u style={{ width: `${Math.min(selectedZone.area * 1.7, 100)}%` }} /></i></span><span><label>Affected population <em>{formatNumber(selectedZone.population)}</em></label><i><u style={{ width: `${Math.min(selectedZone.population / 300, 100)}%` }} /></i></span></div></article><article className="card response-card"><p className="eyebrow">RESPONSE PRIORITY</p><h3>Recommended actions</h3><div className="action-item"><span className="action-icon red">!</span><div><strong>Deploy field team</strong><small>Critical inundation near {selectedZone.city}</small></div><span className="action-time">Now</span></div><div className="action-item"><span className="action-icon amber">↗</span><div><strong>Review evacuation routes</strong><small>{Math.ceil(selectedZone.area / 9)} road segments at risk</small></div><span className="action-time">1h</span></div></article></section>
      {profileOpen && <div className="modal-backdrop" onClick={() => setProfileOpen(false)}><section className="profile-modal" onClick={(event) => event.stopPropagation()}><button className="modal-close" type="button" onClick={() => setProfileOpen(false)}>×</button><p className="eyebrow">OPERATOR SETTINGS</p><h2>Your profile</h2><label>Display name<input value={profileName} placeholder="Mission operator" onChange={(event) => setProfileName(event.target.value)} /></label><div className="preference-block"><strong>Saved coverage</strong><p>{favorites.length} saved alerts · {recent.length} recently viewed</p></div><button className="primary wide" type="button" onClick={() => void savePreferences()}>Save preferences</button></section></div>}
    </main>
  </div>;
}
