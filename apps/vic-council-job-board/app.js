const GEOJSON_URL = "../../static/data/victoria-lga-boundaries.geojson";
const BOARD_DATA_URL = "./data/job-board-data.json";
const WIDTH = 1200;
const HEIGHT = 860;
const METRO_WIDTH = 420;
const METRO_HEIGHT = 300;
const MAP_ZOOM_MIN = 0.78;
const MAP_ZOOM_MAX = 2.6;

const els = {
  mapSvg: document.getElementById("victoria-map"),
  mapFrame: document.getElementById("map-frame"),
  mapPaths: document.getElementById("map-paths"),
  mapMarkers: document.getElementById("map-markers"),
  metroSvg: document.getElementById("metro-map"),
  metroPaths: document.getElementById("metro-paths"),
  metroMarkers: document.getElementById("metro-markers"),
  tooltip: document.getElementById("map-tooltip"),
  search: document.getElementById("job-search"),
  list: document.getElementById("job-list"),
  snapshotNote: document.getElementById("snapshot-note"),
  resultCount: document.getElementById("result-count"),
  resultContext: document.getElementById("result-context"),
  selectedCouncil: document.getElementById("selected-council"),
  selectedCouncilLabel: document.getElementById("selected-council-label"),
  clearCouncil: document.getElementById("clear-council"),
  metricJobs: document.getElementById("metric-jobs"),
  metricLgas: document.getElementById("metric-lgas"),
  metricBand: document.getElementById("metric-band"),
  spotlightTitle: document.getElementById("spotlight-title"),
  spotlightBody: document.getElementById("spotlight-body"),
  spotlightJobs: document.getElementById("spotlight-jobs"),
  spotlightBand: document.getElementById("spotlight-band"),
  spotlightReview: document.getElementById("spotlight-review"),
  evidenceFlow: document.getElementById("evidence-flow"),
  bandChart: document.getElementById("band-chart"),
  bandChartTitle: document.getElementById("band-chart-title"),
  salaryChart: document.getElementById("salary-chart"),
  salaryChartTitle: document.getElementById("salary-chart-title"),
  monthChart: document.getElementById("month-chart"),
  sourceChart: document.getElementById("source-chart"),
};

const state = {
  geojson: null,
  snapshot: null,
  councils: [],
  councilLookup: new Map(),
  groups: new Map(),
  jobs: [],
  query: "",
  selectedCouncilKey: "",
  selectedBand: "",
  projectionBounds: null,
  metroProjectionBounds: null,
  currentViewBox: [0, 0, WIDTH, HEIGHT],
  viewAnimation: 0,
  mapPan: { x: 0, y: 0 },
  mapZoom: 1,
  panStart: null,
  suppressSelectUntil: 0,
  asOfDate: new Date(),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normaliseKey(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/&/g, " AND ")
    .replace(/[^A-Z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function formatCount(value, fallback = "0") {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-AU") : fallback;
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString("en-AU", { day: "2-digit", month: "short", year: "numeric" });
}

function daysUntil(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return Number.POSITIVE_INFINITY;
  return Math.ceil((parsed.getTime() - state.asOfDate.getTime()) / 86400000);
}

function isClassifiedJob(job) {
  return Boolean(job?.is_standard_band_1_to_8);
}

function closingSoonCount(jobs) {
  return jobs.filter((job) => job.closesSoon).length;
}

function publicBoardCount(jobs) {
  return jobs.filter((job) => job.publicBoardSignal).length;
}

function currentCount(jobs) {
  return jobs.filter((job) => job.boardStatus === "current").length;
}

function historicalCount(jobs) {
  return jobs.filter((job) => job.boardStatus === "historical").length;
}

function inferredCount(jobs) {
  return jobs.filter((job) => job.classification_confidence === "inferred").length;
}

function externalHost(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function formatSalary(job) {
  const text = job.advertised_salary_text || job.salary_text;
  if (text) return text;
  const eaMin = finiteNumber(job.enterprise_agreement_salary_min);
  const eaMax = finiteNumber(job.enterprise_agreement_salary_max);
  if (eaMin !== null) {
    const same = eaMax !== null && Math.abs(eaMax - eaMin) < 0.01;
    return same || eaMax === null
      ? `${formatMoney(eaMin)}/year`
      : `${formatMoney(eaMin)}-${formatMoney(eaMax)}/year`;
  }
  const min = finiteNumber(job.advertised_salary_min ?? job.salary_min);
  const max = finiteNumber(job.advertised_salary_max ?? job.salary_max);
  const period = job.advertised_salary_period || job.salary_period || "";
  if (min === null) return "";
  const range = max !== null && Math.abs(max - min) > 0.01
    ? `${formatMoney(min)}-${formatMoney(max)}`
    : formatMoney(min);
  return period ? `${range}/${period}` : range;
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: value < 1000 ? 2 : 0,
  }).format(value);
}

function formatCompactMoney(value) {
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    notation: "compact",
    maximumFractionDigits: 0,
  }).format(value);
}

function councilDisplayName(job) {
  return job.short_name || job.council_name || "Council";
}

function buildCouncilLookup(rows) {
  const lookup = new Map();
  for (const row of rows || []) {
    const key = normaliseKey(row.spatial_key || row.map_join_key || row.short_name || row.long_name);
    const normalized = { ...row, _key: key };
    [
      row.short_name,
      row.long_name,
      row.official_name,
      row.spatial_name,
      row.spatial_key,
      row.map_join_key,
    ].forEach((value) => {
      const candidate = normaliseKey(value);
      if (candidate && !lookup.has(candidate)) lookup.set(candidate, normalized);
    });
  }
  return lookup;
}

function enrichJobs(rows) {
  return (rows || []).map((job) => {
    const council = state.councilLookup.get(normaliseKey(job.short_name))
      || state.councilLookup.get(normaliseKey(job.council_name))
      || state.councilLookup.get(normaliseKey(job.council_key))
      || {};
    const councilKey = normaliseKey(job.council_key || council.spatial_key || council.map_join_key || job.short_name || job.council_name);
    const band = job.standard_band_number || job.inferred_standard_band_number || "";
    const salary = formatSalary(job);
    const closingDate = formatDate(job.closing_at || job.closing_at_text);
    const searchText = [
      job.job_title,
      job.short_name,
      job.council_name,
      council.council_category,
      council.council_type,
      job.classification_band,
      band ? `band ${band}` : "",
      salary,
      job.location_text,
      job.work_type,
      job.department,
      job.source_family,
      job.source_name,
      job.governance_status,
      job.board_status,
      job.public_board_signal ? "public board" : "",
      job.classification_confidence,
      job.completion_action_label,
    ].filter(Boolean).join(" ").toLowerCase();
    return {
      ...job,
      councilKey,
      councilCategory: council.council_category || "",
      councilType: council.council_type || "",
      displayCouncil: council.short_name || job.short_name || job.council_name || "Council",
      bandLabel: band ? `Band ${band}` : "Classified",
      salaryLabel: salary,
      closingDate,
      closesSoon: daysUntil(job.closing_at || job.closing_at_text) <= 10,
      boardStatus: job.board_status || "current",
      publicBoardSignal: Boolean(job.public_board_signal),
      searchText,
    };
  }).filter((job) => job.job_title && job.councilKey);
}

function eachCoordinate(coords, callback) {
  if (!Array.isArray(coords)) return;
  if (typeof coords[0] === "number" && typeof coords[1] === "number") {
    callback(coords);
    return;
  }
  coords.forEach((item) => eachCoordinate(item, callback));
}

function geometryBounds(geometry) {
  const bounds = [Infinity, Infinity, -Infinity, -Infinity];
  eachCoordinate(geometry?.coordinates, ([lon, lat]) => {
    bounds[0] = Math.min(bounds[0], lon);
    bounds[1] = Math.min(bounds[1], lat);
    bounds[2] = Math.max(bounds[2], lon);
    bounds[3] = Math.max(bounds[3], lat);
  });
  return bounds.every(Number.isFinite) ? bounds : null;
}

function combineBounds(boundsList) {
  const valid = boundsList.filter(Boolean);
  if (!valid.length) return null;
  return valid.reduce((acc, item) => [
    Math.min(acc[0], item[0]),
    Math.min(acc[1], item[1]),
    Math.max(acc[2], item[2]),
    Math.max(acc[3], item[3]),
  ], [Infinity, Infinity, -Infinity, -Infinity]);
}

function paddedBounds(bounds, width, height, padding = 0.06) {
  const [minLon, minLat, maxLon, maxLat] = bounds;
  const centerLon = (minLon + maxLon) / 2;
  const centerLat = (minLat + maxLat) / 2;
  const targetAspect = width / height;
  let lonSpan = Math.max(maxLon - minLon, 0.1);
  let latSpan = Math.max(maxLat - minLat, 0.1);
  if (lonSpan / latSpan > targetAspect) {
    latSpan = lonSpan / targetAspect;
  } else {
    lonSpan = latSpan * targetAspect;
  }
  lonSpan *= 1 + padding * 2;
  latSpan *= 1 + padding * 2;
  return [
    centerLon - lonSpan / 2,
    centerLat - latSpan / 2,
    centerLon + lonSpan / 2,
    centerLat + latSpan / 2,
  ];
}

function project([lon, lat]) {
  return projectForBounds([lon, lat], state.projectionBounds, WIDTH, HEIGHT);
}

function projectForBounds([lon, lat], bounds, width, height) {
  const [minLon, minLat, maxLon, maxLat] = bounds;
  return [
    ((lon - minLon) / (maxLon - minLon)) * width,
    ((maxLat - lat) / (maxLat - minLat)) * height,
  ];
}

function ringPath(ring, projector = project) {
  return ring.map((coord, index) => {
    const [x, y] = projector(coord);
    return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ") + " Z";
}

function geometryPath(geometry, projector = project) {
  if (geometry?.type === "Polygon") {
    return geometry.coordinates.map((ring) => ringPath(ring, projector)).join(" ");
  }
  if (geometry?.type === "MultiPolygon") {
    return geometry.coordinates.flatMap((polygon) => polygon.map((ring) => ringPath(ring, projector))).join(" ");
  }
  return "";
}

function geometryPathForBounds(geometry, bounds, width, height) {
  return geometryPath(geometry, (coord) => projectForBounds(coord, bounds, width, height));
}

function buildFeatureGroups(features) {
  const groups = new Map();
  for (const feature of features || []) {
    const key = normaliseKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
    if (!key) continue;
    const bounds = geometryBounds(feature.geometry);
    const council = state.councilLookup.get(key) || {};
    const group = groups.get(key) || {
      key,
      name: feature.properties?.spatial_name || key,
      officialName: feature.properties?.official_name || "",
      category: council.council_category || "",
      bounds: null,
      features: [],
      paths: [],
      metroPaths: [],
    };
    group.features.push(feature);
    group.bounds = combineBounds([group.bounds, bounds]);
    groups.set(key, group);
  }
  return groups;
}

function mapCenter(bounds) {
  if (!bounds) return [0, 0];
  return project([(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2]);
}

function mapCenterForBounds(bounds, projectionBounds, width, height) {
  if (!bounds || !projectionBounds) return [0, 0];
  return projectForBounds([(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2], projectionBounds, width, height);
}

function projectedBounds(bounds) {
  if (!bounds) return [0, 0, WIDTH, HEIGHT];
  const points = [
    project([bounds[0], bounds[1]]),
    project([bounds[0], bounds[3]]),
    project([bounds[2], bounds[1]]),
    project([bounds[2], bounds[3]]),
  ];
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function maxPanForZoom(zoom) {
  const extra = Math.max(0, zoom - 1);
  return {
    x: 360 + extra * 520,
    y: 260 + extra * 390,
  };
}

function setMapTransform({ x = state.mapPan.x, y = state.mapPan.y, zoom = state.mapZoom } = {}) {
  const nextZoom = clamp(zoom, MAP_ZOOM_MIN, MAP_ZOOM_MAX);
  const bounds = maxPanForZoom(nextZoom);
  state.mapZoom = nextZoom;
  state.mapPan = {
    x: clamp(x, -bounds.x, bounds.x),
    y: clamp(y, -bounds.y, bounds.y),
  };
  els.mapFrame.style.setProperty("--map-pan-x", `${state.mapPan.x.toFixed(1)}px`);
  els.mapFrame.style.setProperty("--map-pan-y", `${state.mapPan.y.toFixed(1)}px`);
  els.mapFrame.style.setProperty("--map-user-scale", state.mapZoom.toFixed(3));
}

function mapTargetKey(target) {
  const node = target?.closest?.("[data-key]");
  return node?.dataset?.key || "";
}

function beginMapPan(event) {
  if (event.button !== 0) return;
  event.preventDefault();
  state.panStart = {
    pointerId: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    panX: state.mapPan.x,
    panY: state.mapPan.y,
    targetKey: mapTargetKey(event.target),
    moved: false,
  };
  hideTooltip();
  els.mapFrame.classList.add("is-panning");
  els.mapFrame.setPointerCapture?.(event.pointerId);
}

function moveMapPan(event) {
  if (!state.panStart || state.panStart.pointerId !== event.pointerId) return;
  event.preventDefault();
  const dx = event.clientX - state.panStart.x;
  const dy = event.clientY - state.panStart.y;
  if (Math.hypot(dx, dy) > 4) state.panStart.moved = true;
  setMapTransform({ x: state.panStart.panX + dx, y: state.panStart.panY + dy });
  hideTooltip();
}

function endMapPan(event) {
  if (!state.panStart || state.panStart.pointerId !== event.pointerId) return;
  const targetKey = state.panStart.targetKey;
  const moved = state.panStart.moved;
  if (state.panStart.moved) {
    state.suppressSelectUntil = performance.now() + 180;
  }
  state.panStart = null;
  els.mapFrame.classList.remove("is-panning");
  els.mapFrame.releasePointerCapture?.(event.pointerId);
  if (!moved && targetKey) {
    state.suppressSelectUntil = performance.now() + 180;
    selectCouncil(targetKey, { force: true });
  }
}

function zoomMap(event) {
  event.preventDefault();
  const previousZoom = state.mapZoom;
  const nextZoom = clamp(previousZoom * Math.exp(-event.deltaY * 0.0012), MAP_ZOOM_MIN, MAP_ZOOM_MAX);
  if (Math.abs(nextZoom - previousZoom) < 0.001) return;

  const rect = els.mapFrame.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const ratio = nextZoom / previousZoom;
  const anchorX = event.clientX - centerX;
  const anchorY = event.clientY - centerY;

  setMapTransform({
    zoom: nextZoom,
    x: state.mapPan.x - anchorX * (ratio - 1),
    y: state.mapPan.y - anchorY * (ratio - 1),
  });
}

function focusViewBox(bounds) {
  const [minX, minY, maxX, maxY] = projectedBounds(bounds);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const aspect = WIDTH / HEIGHT;
  let width = Math.max(maxX - minX, 34) * 3.25;
  let height = Math.max(maxY - minY, 34) * 3.25;

  width = Math.max(width, 330);
  height = Math.max(height, 236);
  if (width / height > aspect) {
    height = width / aspect;
  } else {
    width = height * aspect;
  }
  width = Math.min(width, WIDTH);
  height = Math.min(height, HEIGHT);

  return [
    clamp(centerX - width / 2, 0, WIDTH - width),
    clamp(centerY - height / 2, 0, HEIGHT - height),
    width,
    height,
  ];
}

function animateViewBox(target) {
  cancelAnimationFrame(state.viewAnimation);
  const start = state.currentViewBox || [0, 0, WIDTH, HEIGHT];
  const duration = 620;
  const startedAt = performance.now();

  function step(now) {
    const progress = clamp((now - startedAt) / duration, 0, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const next = start.map((value, index) => value + (target[index] - value) * eased);
    els.mapSvg.setAttribute("viewBox", next.map((value) => value.toFixed(2)).join(" "));
    state.currentViewBox = next;
    if (progress < 1) state.viewAnimation = requestAnimationFrame(step);
  }

  state.viewAnimation = requestAnimationFrame(step);
}

function updateMapView() {
  const selected = state.selectedCouncilKey ? state.groups.get(state.selectedCouncilKey) : null;
  const target = selected ? focusViewBox(selected.bounds) : [0, 0, WIDTH, HEIGHT];
  animateViewBox(target);
}

function selectCouncil(key, { force = false } = {}) {
  if (!force && performance.now() < state.suppressSelectUntil) return;
  const hasJobs = jobsForKey(filteredJobsWithoutCouncil(), key).length > 0 || jobsForKey(state.jobs, key).length > 0;
  if (!hasJobs) return;
  hideTooltip();
  state.selectedCouncilKey = state.selectedCouncilKey === key ? "" : key;
  render();
}

function selectBand(band) {
  const nextBand = String(band || "");
  state.selectedBand = state.selectedBand === nextBand ? "" : nextBand;
  hideTooltip();
  render();
}

function isMetroCouncilKey(key) {
  const council = state.councilLookup.get(normaliseKey(key));
  return council?.council_category === "Metropolitan";
}

function swapSvgChildren(root, fragment) {
  if (!root) return;
  while (root.firstChild) root.removeChild(root.firstChild);
  root.appendChild(fragment);
}

function wireMapPath(path, key) {
  path.addEventListener("mouseenter", (event) => showTooltip(event, key));
  path.addEventListener("mousemove", moveTooltip);
  path.addEventListener("mouseleave", hideTooltip);
  path.addEventListener("click", (event) => {
    event.preventDefault();
    selectCouncil(key);
  });
}

function wireMapMarker(marker, key) {
  marker.addEventListener("click", (event) => {
    event.preventDefault();
    selectCouncil(key);
  });
}

function hydrateStaticMap() {
  const mainPaths = [...els.mapPaths.querySelectorAll(".lga-boundary")];
  if (!mainPaths.length) return false;

  for (const path of mainPaths) {
    const key = path.dataset.key || "";
    if (!key) continue;
    wireMapPath(path, key);
    state.groups.get(key)?.paths.push(path);
  }

  if (els.metroPaths) {
    for (const path of els.metroPaths.querySelectorAll(".lga-boundary")) {
      const key = path.dataset.key || "";
      if (!key) continue;
      wireMapPath(path, key);
      state.groups.get(key)?.metroPaths.push(path);
    }
  }

  for (const marker of els.mapMarkers.querySelectorAll(".count-marker")) {
    const key = marker.dataset.key || "";
    if (key) wireMapMarker(marker, key);
  }
  if (els.metroMarkers) {
    for (const marker of els.metroMarkers.querySelectorAll(".count-marker")) {
      const key = marker.dataset.key || "";
      if (key) wireMapMarker(marker, key);
    }
  }
  return true;
}

function renderMap() {
  const features = state.geojson.features || [];
  const allBounds = combineBounds(features.map((feature) => geometryBounds(feature.geometry)));
  const nextProjectionBounds = paddedBounds(allBounds, WIDTH, HEIGHT, 0.045);
  const previousProjectionBounds = state.projectionBounds;
  state.projectionBounds = nextProjectionBounds;
  const nextGroups = buildFeatureGroups(features);
  state.groups = nextGroups;
  const metroFeatures = features.filter((feature) => {
    const key = normaliseKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
    return isMetroCouncilKey(key);
  });
  const metroBounds = combineBounds(metroFeatures.map((feature) => geometryBounds(feature.geometry)));
  const nextMetroProjectionBounds = metroBounds ? paddedBounds(metroBounds, METRO_WIDTH, METRO_HEIGHT, 0.08) : null;
  state.metroProjectionBounds = nextMetroProjectionBounds;
  if (hydrateStaticMap()) {
    state.projectionBounds = nextProjectionBounds || previousProjectionBounds;
    return;
  }

  const mapPathFragment = document.createDocumentFragment();
  const mapMarkerFragment = document.createDocumentFragment();
  const metroPathFragment = document.createDocumentFragment();
  const metroMarkerFragment = document.createDocumentFragment();

  for (const feature of features) {
    const key = normaliseKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", geometryPath(feature.geometry));
    path.dataset.key = key;
    path.classList.add("lga-boundary");
    if (isMetroCouncilKey(key)) path.classList.add("is-metro-main");
    if (feature.properties?.is_reference_council === false) path.classList.add("is-non-reference");
    wireMapPath(path, key);
    mapPathFragment.appendChild(path);
    nextGroups.get(key)?.paths.push(path);
  }

  if (els.metroPaths && nextMetroProjectionBounds) {
    for (const feature of metroFeatures) {
      const key = normaliseKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", geometryPathForBounds(feature.geometry, nextMetroProjectionBounds, METRO_WIDTH, METRO_HEIGHT));
      path.dataset.key = key;
      path.classList.add("lga-boundary", "metro-boundary");
      wireMapPath(path, key);
      metroPathFragment.appendChild(path);
      nextGroups.get(key)?.metroPaths.push(path);
    }
  }

  for (const group of nextGroups.values()) {
    if (isMetroCouncilKey(group.key)) continue;
    const [x, y] = mapCenter(group.bounds);
    const marker = document.createElementNS("http://www.w3.org/2000/svg", "g");
    marker.classList.add("count-marker");
    marker.dataset.key = group.key;
    marker.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
    marker.innerHTML = `
      <circle r="15"></circle>
      <text y="0">0</text>
      <text class="count-label" x="21" y="4" text-anchor="start">${escapeHtml(group.name)}</text>
    `;
    wireMapMarker(marker, group.key);
    mapMarkerFragment.appendChild(marker);
  }

  if (els.metroMarkers && nextMetroProjectionBounds) {
    for (const group of nextGroups.values()) {
      if (!isMetroCouncilKey(group.key)) continue;
      const [x, y] = mapCenterForBounds(group.bounds, nextMetroProjectionBounds, METRO_WIDTH, METRO_HEIGHT);
      const marker = document.createElementNS("http://www.w3.org/2000/svg", "g");
      marker.classList.add("count-marker", "metro-count-marker");
      marker.dataset.key = group.key;
      marker.setAttribute("transform", `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
      marker.innerHTML = `
        <circle r="10"></circle>
        <text y="0">0</text>
      `;
      wireMapMarker(marker, group.key);
      metroMarkerFragment.appendChild(marker);
    }
  }

  state.projectionBounds = nextProjectionBounds || previousProjectionBounds;
  state.metroProjectionBounds = nextMetroProjectionBounds;
  state.groups = nextGroups;
  swapSvgChildren(els.mapPaths, mapPathFragment);
  swapSvgChildren(els.mapMarkers, mapMarkerFragment);
  if (els.metroPaths) swapSvgChildren(els.metroPaths, metroPathFragment);
  if (els.metroMarkers) swapSvgChildren(els.metroMarkers, metroMarkerFragment);
}

function jobsForKey(jobs, key) {
  return jobs.filter((job) => job.councilKey === key);
}

function filteredJobsWithoutCouncil({ includeBand = true } = {}) {
  const tokens = state.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return state.jobs
    .filter((job) => !includeBand || !state.selectedBand || String(job.standard_band_number || "") === state.selectedBand)
    .filter((job) => !tokens.length || tokens.every((token) => job.searchText.includes(token)));
}

function filteredJobs() {
  return filteredJobsWithoutCouncil()
    .filter((job) => !state.selectedCouncilKey || job.councilKey === state.selectedCouncilKey)
    .sort((a, b) => {
      const closeDelta = daysUntil(a.closing_at || a.closing_at_text) - daysUntil(b.closing_at || b.closing_at_text);
      return String(a.displayCouncil).localeCompare(String(b.displayCouncil))
        || closeDelta
        || String(a.job_title).localeCompare(String(b.job_title));
    });
}

function groupedCounts(jobs) {
  const counts = new Map();
  for (const job of jobs) counts.set(job.councilKey, (counts.get(job.councilKey) || 0) + 1);
  return counts;
}

function quantile(values, percentile) {
  const sorted = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!sorted.length) return 1;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * percentile)));
  return sorted[index];
}

function lerp(start, end, amount) {
  return start + (end - start) * amount;
}

function mixRgb(start, end, amount) {
  return start.map((value, index) => Math.round(lerp(value, end[index], amount)));
}

function jobColour(count, domain) {
  if (!count) {
    return {
      scale: 0,
      fillAlpha: 0.17,
      strokeAlpha: 0.52,
      rgb: [24, 181, 178],
      strokeRgb: [114, 232, 220],
    };
  }
  const clipped = Math.min(count, domain);
  const scale = clamp(Math.log1p(clipped) / Math.log1p(domain), 0.12, 1);
  const warm = clamp((scale - 0.72) / 0.28, 0, 1);
  const tealToMint = mixRgb([24, 181, 178], [70, 208, 156], Math.min(1, scale / 0.72));
  const rgb = warm ? mixRgb(tealToMint, [231, 179, 79], warm) : tealToMint;
  const strokeRgb = rgb.map((value) => Math.min(255, Math.round(value + 58)));
  return {
    scale,
    fillAlpha: lerp(0.16, 0.44, scale),
    strokeAlpha: lerp(0.44, 0.92, scale),
    rgb,
    strokeRgb,
  };
}

function applyJobColour(element, count, domain) {
  const colour = jobColour(count, domain);
  element.style.setProperty("--job-scale", colour.scale.toFixed(3));
  element.style.setProperty("--job-fill-alpha", colour.fillAlpha.toFixed(3));
  element.style.setProperty("--job-stroke-alpha", colour.strokeAlpha.toFixed(3));
  element.style.setProperty("--job-r", String(colour.rgb[0]));
  element.style.setProperty("--job-g", String(colour.rgb[1]));
  element.style.setProperty("--job-b", String(colour.rgb[2]));
  element.style.setProperty("--job-stroke-r", String(colour.strokeRgb[0]));
  element.style.setProperty("--job-stroke-g", String(colour.strokeRgb[1]));
  element.style.setProperty("--job-stroke-b", String(colour.strokeRgb[2]));
}

function updateMap(visibleJobs) {
  const unscopedJobs = filteredJobsWithoutCouncil();
  const counts = groupedCounts(visibleJobs);
  const unscopedCounts = groupedCounts(unscopedJobs);
  const maxCount = Math.max(1, ...counts.values());
  const countDomain = Math.max(2, quantile([...counts.values()], 0.9));
  const hasQueryOrFilter = Boolean(state.query.trim()) || state.selectedBand || state.selectedCouncilKey;

  for (const group of state.groups.values()) {
    const count = counts.get(group.key) || 0;
    const unscopedCount = unscopedCounts.get(group.key) || 0;
    for (const path of [...group.paths, ...(group.metroPaths || [])]) {
      applyJobColour(path, count, countDomain);
      path.classList.toggle("has-jobs", count > 0);
      path.classList.toggle("is-heavy", count >= Math.max(4, maxCount * 0.5));
      path.classList.toggle("is-selected", state.selectedCouncilKey === group.key);
      path.classList.toggle("is-dimmed", hasQueryOrFilter && count === 0 && unscopedCount === 0);
      path.dataset.tooltip = tooltipText(group, count || unscopedCount);
    }
  }

  updateCountMarkers(els.mapMarkers, counts, countDomain);
  if (els.metroMarkers) updateCountMarkers(els.metroMarkers, counts, countDomain);

  els.mapFrame.classList.toggle("is-focused", Boolean(state.selectedCouncilKey || state.query.trim()));
  updateMapView();
}

function updateCountMarkers(root, counts, countDomain) {
  root.querySelectorAll(".count-marker").forEach((marker) => {
    const key = marker.dataset.key;
    const count = counts.get(key) || 0;
    applyJobColour(marker, count, countDomain);
    marker.style.display = count > 0 ? "" : "none";
    marker.classList.toggle("is-visible", count > 0);
    marker.classList.toggle("is-selected", state.selectedCouncilKey === key);
    marker.querySelector("text").textContent = String(count);
    const label = marker.querySelector(".count-label");
    if (label) label.style.opacity = state.selectedCouncilKey === key ? "0.92" : "0.28";
  });
}

function tooltipText(group, count) {
  const suffix = count === 1 ? "job" : "jobs";
  return `${group.name}\n${formatCount(count)} matching ${suffix}`;
}

function showTooltip(event, key) {
  if (state.selectedCouncilKey) return;
  const group = state.groups.get(key);
  if (!group) return;
  const count = jobsForKey(filteredJobs(), key).length || jobsForKey(filteredJobsWithoutCouncil(), key).length || jobsForKey(state.jobs, key).length;
  els.tooltip.innerHTML = escapeHtml(tooltipText(group, count)).replace("\n", "<br>");
  els.tooltip.classList.add("is-visible");
  els.tooltip.setAttribute("aria-hidden", "false");
  moveTooltip(event);
}

function moveTooltip(event) {
  els.tooltip.style.left = `${event.clientX}px`;
  els.tooltip.style.top = `${event.clientY}px`;
}

function hideTooltip() {
  els.tooltip.classList.remove("is-visible");
  els.tooltip.setAttribute("aria-hidden", "true");
}

function renderJobs(jobs) {
  if (!jobs.length) {
    els.list.innerHTML = '<div class="empty-note">No roles match the current filters.</div>';
    return;
  }
  els.list.innerHTML = jobs.map((job) => {
    const meta = [
      job.displayCouncil,
      job.bandLabel,
      hasSalaryBandMismatch(job) ? "Salary/EA gap" : "",
      job.closingDate ? `Closes ${job.closingDate}` : "",
    ].filter(Boolean);
    const details = [
      ["Council", job.council_name || job.displayCouncil],
      ["Classification", job.bandLabel],
      ["Salary", job.salaryLabel || "Not listed"],
      ["EA base", formatEaSalary(job) || "Not listed"],
      ["Location", job.location_text || "Not listed"],
      ["Work type", job.work_type || "Not listed"],
      ["Source", job.source_family ? sourceLabel(job.source_family) : "Council careers"],
      ["Reference", job.canonical_reference_month || "Not listed"],
      ["Seen", seenLabel(job)],
    ].filter(([, value]) => value);
    const description = String(job.description_text || "").trim();
    const host = externalHost(job.job_url);
    const links = Array.isArray(job.external_links) ? job.external_links.filter(Boolean) : [job.job_url].filter(Boolean);
    return `
      <article class="job-card job-card-${escapeHtml(job.boardStatus)} ${job.publicBoardSignal ? "has-public-signal" : ""} ${hasSalaryBandMismatch(job) ? "has-salary-mismatch" : ""}">
        <div class="job-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
        <h2>${escapeHtml(job.job_title)}</h2>
        ${description ? `<p>${escapeHtml(description.slice(0, 260))}${description.length > 260 ? "..." : ""}</p>` : ""}
        <dl class="job-details">
          ${details.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}
        </dl>
        ${links[0] ? `
          <a class="external-link" href="${escapeHtml(job.job_url)}" target="_blank" rel="noopener noreferrer">
            View external listing${host ? ` <span>${escapeHtml(host)}</span>` : ""}
          </a>
        ` : ""}
        ${links.length > 1 ? `<div class="job-link-row">${links.slice(1, 4).map((url) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(externalHost(url) || "alternate")}</a>`).join("")}</div>` : ""}
      </article>
    `;
  }).join("");
}

function seenLabel(job) {
  const first = formatDate(job.first_seen_at);
  const last = formatDate(job.last_seen_at);
  if (first && last && first !== last) return `${first} to ${last}`;
  return last || first || "Not listed";
}

function formatEaSalary(job) {
  const min = finiteNumber(job.enterprise_agreement_salary_min);
  const max = finiteNumber(job.enterprise_agreement_salary_max);
  if (min === null) {
    const inferredMin = finiteNumber(job.inferred_enterprise_agreement_salary_min);
    const inferredMax = finiteNumber(job.inferred_enterprise_agreement_salary_max);
    if (inferredMin !== null) {
      const range = inferredMax !== null && Math.abs(inferredMax - inferredMin) > 0.01
        ? `${formatMoney(inferredMin)}-${formatMoney(inferredMax)}/year`
        : `${formatMoney(inferredMin)}/year`;
      return `${range} candidate, pending band confirmation`;
    }
    return job.classification_confidence === "inferred" ? "Awaiting band confirmation" : "";
  }
  const range = max !== null && Math.abs(max - min) > 0.01
    ? `${formatMoney(min)}-${formatMoney(max)}/year`
    : `${formatMoney(min)}/year`;
  return hasSalaryBandMismatch(job) ? `${range} base range; ad outside governed range` : range;
}

function hasSalaryBandMismatch(job) {
  return job.salary_band_validation_status === "mismatch";
}

function sourceLabel(value) {
  const key = String(value || "").toLowerCase();
  const labels = {
    adlogic_martianlogic: "Careers portal",
    applynow: "Careers portal",
    aurion_selfservice: "Council website",
    bigredsky: "Careers portal",
    elmogov: "Careers portal",
    elmo_talent: "Careers portal",
    native_council: "Council website",
    native_council_custom: "Council website",
    pageup: "Careers portal",
    pulse: "Careers portal",
    recruitmenthub: "Careers portal",
    seek: "Seek",
    smartrecruiters: "Careers portal",
    springboard: "Careers portal",
    successfactors: "Careers portal",
    careersatcouncil: "Careers at Council",
    localgovernmentjobs: "Local Government Jobs",
  };
  if (labels[key]) return labels[key];
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function renderSelectedCouncil(visibleJobs) {
  const selected = state.selectedCouncilKey ? state.groups.get(state.selectedCouncilKey) : null;
  els.selectedCouncil.hidden = !selected;
  if (selected) {
    els.selectedCouncilLabel.textContent = `${selected.name} selected`;
  }

  if (!els.spotlightTitle) return;
  const focusJobs = selected ? visibleJobs : filteredJobsWithoutCouncil();
  const lgaCount = groupedCounts(focusJobs).size;
  els.spotlightTitle.textContent = selected ? selected.name : "All highlighted areas";
  els.spotlightBody.textContent = selected
    ? `${formatCount(visibleJobs.length)} classified roles in this council area, including ${formatCount(publicBoardCount(visibleJobs))} public-board signal${publicBoardCount(visibleJobs) === 1 ? "" : "s"}.`
    : `${formatCount(focusJobs.length)} classified roles across ${formatCount(lgaCount)} highlighted council areas.`;
  els.spotlightJobs.textContent = formatCount(focusJobs.length);
  els.spotlightBand.textContent = formatCount(lgaCount);
  els.spotlightReview.textContent = formatCount(publicBoardCount(focusJobs));
}

function render() {
  const visibleJobs = filteredJobs();
  const allFiltered = filteredJobsWithoutCouncil();
  const chartJobs = filteredJobsWithoutCouncil({ includeBand: false })
    .filter((job) => !state.selectedCouncilKey || job.councilKey === state.selectedCouncilKey);
  const lgaCount = groupedCounts(visibleJobs).size;
  updateMap(visibleJobs);
  renderJobs(visibleJobs);
  renderSelectedCouncil(visibleJobs);
  els.resultCount.textContent = `${formatCount(visibleJobs.length)} role${visibleJobs.length === 1 ? "" : "s"}`;
  els.resultContext.textContent = `${formatCount(lgaCount)} council area${lgaCount === 1 ? "" : "s"} highlighted${state.selectedBand ? `, Band ${state.selectedBand}` : ""}`;
  if (els.metricJobs) els.metricJobs.textContent = formatCount(state.jobs.length);
  if (els.metricLgas) els.metricLgas.textContent = formatCount(groupedCounts(state.jobs).size);
  if (els.metricBand) els.metricBand.textContent = formatCount(state.snapshot?.summary?.secondary_classified_jobs ?? publicBoardCount(state.jobs));
  renderVisuals(visibleJobs, allFiltered, chartJobs);
  if (state.selectedCouncilKey && !allFiltered.some((job) => job.councilKey === state.selectedCouncilKey)) {
    state.selectedCouncilKey = "";
    render();
  }
}

function countBy(rows, getter) {
  const counts = new Map();
  for (const row of rows) {
    const key = getter(row);
    if (!key) continue;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

function renderVisuals(visibleJobs, allFiltered, chartJobs = visibleJobs) {
  if (els.evidenceFlow) renderEvidenceFlow();
  if (els.bandChart) renderBandChart(chartJobs);
  if (els.salaryChart) renderSalaryChart(visibleJobs);
  if (els.monthChart) renderMonthChart(allFiltered);
  if (els.sourceChart) renderSourceChart(allFiltered);
}

function renderEvidenceFlow() {
  const rows = state.snapshot?.visuals?.evidence_flow || [];
  const max = Math.max(1, ...rows.map((row) => Number(row.value) || 0));
  els.evidenceFlow.innerHTML = rows.map((row, index) => `
    <div class="flow-node flow-node-${index + 1}" style="--pct:${Math.max(6, ((Number(row.value) || 0) / max) * 100).toFixed(2)}%">
      <span>${escapeHtml(row.label)}</span>
      <strong>${formatCount(row.value)}</strong>
      <small>${escapeHtml(row.detail || "")}</small>
      <i></i>
    </div>
  `).join("");
}

function renderBandChart(rows) {
  const counts = countBy(rows, (job) => String(job.standard_band_number || ""));
  const points = rows.map(salaryEvidence).filter(Boolean);
  const max = Math.max(1, ...counts.values());
  const salaryDomain = salaryMinimumAxisDomain(points);
  if (els.bandChartTitle) {
    els.bandChartTitle.textContent = state.selectedBand ? `Band ${state.selectedBand}` : `${formatCount(rows.length)} roles`;
  }

  const axis = `
    <div class="band-pay-axis">
      <span>${points.length ? formatCompactMoney(salaryDomain.min) : "No salary"}</span>
      <span>${points.length ? "minimum annual salary" : "count only"}</span>
      <span>${points.length ? formatCompactMoney(salaryDomain.max) : "signal"}</span>
    </div>
  `;
  const rowsHtml = Array.from({ length: 8 }, (_, index) => {
    const band = String(index + 1);
    const count = counts.get(band) || 0;
    const pct = (count / max) * 100;
    const bandPoints = points.filter((point) => String(point.band) === band);
    const bandSalaryLabel = salaryMinimumBandLabel(bandPoints);
    const averageMin = averageSalary(bandPoints.map((point) => point.low));
    const averageMarker = averageMin
      ? `<span class="band-pay-average" style="--avg-x:${salaryPercent(averageMin, salaryDomain.min, salaryDomain.max).toFixed(2)}%" title="Average minimum ${escapeHtml(formatMoney(averageMin))}/year"><i></i><b>${escapeHtml(formatCompactMoney(averageMin))}</b></span>`
      : "";
    const dots = bandPoints.map((point) => {
      const x = salaryPercent(point.low, salaryDomain.min, salaryDomain.max);
      return `<span class="salary-dot" style="--x:${x.toFixed(2)}%;--y:${salaryLaneY(point).toFixed(2)}%" title="${escapeHtml(salaryMinimumPointTitle(point))}"></span>`;
    }).join("");
    const active = state.selectedBand === band;
    return `
      <div class="band-pay-row${active ? " is-active" : ""}${count ? "" : " is-empty"}" style="--density:${pct.toFixed(2)}%" data-band="${band}" role="button" tabindex="0" aria-pressed="${active ? "true" : "false"}" title="Filter map to Band ${band}">
        <div class="band-pay-label">
          <span>Band ${band}</span>
          <strong>${formatCount(count)}</strong>
          <small>${bandSalaryLabel}</small>
        </div>
        <div class="band-pay-lane">
          <i class="band-pay-density"></i>
          ${averageMarker}
          ${dots}
        </div>
      </div>
    `;
  }).join("");
  els.bandChart.innerHTML = `
    ${axis}
    ${rowsHtml}
  `;
}

function averageSalary(values) {
  const numbers = values.filter(Number.isFinite);
  if (!numbers.length) return null;
  return numbers.reduce((total, value) => total + value, 0) / numbers.length;
}

function salaryMinimumBandLabel(points) {
  if (!points.length) return "no salary";
  const low = Math.min(...points.map((point) => point.low));
  const high = Math.max(...points.map((point) => point.low));
  if (Math.abs(high - low) < 1) return formatCompactMoney(high);
  return `min ${formatCompactMoney(low)}-${formatCompactMoney(high)}`;
}

function firstFinite(values) {
  for (const value of values) {
    const number = finiteNumber(value);
    if (number !== null) return number;
  }
  return null;
}

function salaryRange(values) {
  const min = firstFinite([values.min]);
  const max = firstFinite([values.max, values.min]);
  if (min === null && max === null) return null;
  return {
    low: min ?? max,
    high: max ?? min,
  };
}

function advertisedAnnualRange(job) {
  const range = salaryRange({
    min: job.advertised_salary_min ?? job.salary_min,
    max: job.advertised_salary_max ?? job.salary_max,
  });
  if (!range) return null;
  const high = Math.max(range.low, range.high);
  const low = Math.min(range.low, range.high);
  if (high < 30000) return null;
  return {
    low: low < 30000 ? high : low,
    high,
    source: "advertised",
  };
}

function storedAnnualRange(job) {
  if (job.annual_salary_source && job.annual_salary_source !== "advertised") return null;
  const range = salaryRange({ min: job.annual_salary_min, max: job.annual_salary_max });
  if (!range) return null;
  const high = Math.max(range.low, range.high);
  const low = Math.min(range.low, range.high);
  if (high < 30000) return null;
  return {
    low: low < 30000 ? high : low,
    high,
    source: job.annual_salary_source || "annual",
  };
}

function enterpriseAgreementRange(job) {
  const range = salaryRange({
    min: job.enterprise_agreement_salary_min ?? job.inferred_enterprise_agreement_salary_min,
    max: job.enterprise_agreement_salary_max ?? job.inferred_enterprise_agreement_salary_max,
  });
  return range ? { ...range, source: "enterprise_agreement" } : null;
}

function stableUnit(value) {
  let hash = 2166136261;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) % 10000) / 10000;
}

function salaryEvidence(job) {
  const range = advertisedAnnualRange(job) || storedAnnualRange(job) || enterpriseAgreementRange(job);
  if (!range) return null;
  const midpoint = (range.low + range.high) / 2;
  if (midpoint < 30000) return null;
  const band = Number(job.standard_band_number || job.inferred_standard_band_number);
  if (!Number.isFinite(band) || band < 1 || band > 8) return null;
  return {
    job,
    band,
    low: Math.min(range.low, range.high),
    high: Math.max(range.low, range.high),
    midpoint,
    source: range.source,
    jitter: stableUnit(job.job_uid || job.dedupe_key || `${job.displayCouncil}-${job.job_title}`),
  };
}

function salaryPercent(value, min, max) {
  if (max <= min) return 50;
  return clamp(((value - min) / (max - min)) * 100, 1.5, 98.5);
}

function salaryAxisDomain(points) {
  if (!points.length) return { min: 0, max: 1 };
  let minSalary = Math.min(...points.map((point) => point.low));
  let maxSalary = Math.max(...points.map((point) => point.high));
  minSalary = Math.floor(minSalary / 10000) * 10000;
  maxSalary = Math.ceil(maxSalary / 10000) * 10000;
  if (maxSalary - minSalary < 20000) {
    minSalary -= 10000;
    maxSalary += 10000;
  }
  return { min: minSalary, max: maxSalary };
}

function salaryMinimumAxisDomain(points) {
  if (!points.length) return { min: 0, max: 1 };
  let minSalary = Math.min(...points.map((point) => point.low));
  let maxSalary = Math.max(...points.map((point) => point.low));
  minSalary = Math.floor(minSalary / 10000) * 10000;
  maxSalary = Math.ceil(maxSalary / 10000) * 10000;
  if (maxSalary - minSalary < 20000) {
    minSalary -= 10000;
    maxSalary += 10000;
  }
  return { min: minSalary, max: maxSalary };
}

function salaryLaneY(point) {
  return clamp(50 + (point.jitter - 0.5) * 54, 18, 82);
}

function renderSalaryChart(rows) {
  const points = rows.map(salaryEvidence).filter(Boolean);
  if (els.salaryChartTitle) {
    els.salaryChartTitle.textContent = points.length ? `${formatCount(points.length)} salaries` : "no salary signal";
  }
  if (!points.length) {
    els.salaryChart.innerHTML = '<div class="salary-empty">No annual salary evidence in view.</div>';
    return;
  }

  const { min: minSalary, max: maxSalary } = salaryAxisDomain(points);

  const bandLines = Array.from({ length: 8 }, (_, index) => {
    const band = 8 - index;
    const y = salaryBandY(band);
    return `
      <span class="salary-band-line" style="--y:${y.toFixed(2)}%"></span>
      <span class="salary-band-label" style="--y:${y.toFixed(2)}%">B${band}</span>
    `;
  }).join("");

  const ranges = points.map((point) => {
    const x1 = salaryPercent(point.low, minSalary, maxSalary);
    const x2 = salaryPercent(point.high, minSalary, maxSalary);
    const y = salaryPointY(point);
    const title = salaryPointTitle(point);
    return `<span class="salary-range ${salaryPointClasses(point)}" style="--x:${x1.toFixed(2)}%;--w:${Math.max(1.2, x2 - x1).toFixed(2)}%;--y:${y.toFixed(2)}%" title="${escapeHtml(title)}"></span>`;
  }).join("");

  const dots = points.map((point) => {
    const x = salaryPercent(point.midpoint, minSalary, maxSalary);
    const y = salaryPointY(point);
    const title = salaryPointTitle(point);
    return `<span class="salary-dot ${salaryPointClasses(point)}" style="--x:${x.toFixed(2)}%;--y:${y.toFixed(2)}%" title="${escapeHtml(title)}"></span>`;
  }).join("");

  els.salaryChart.innerHTML = `
    <div class="salary-jitter">
      <div class="salary-axis-labels">
        <span>${formatCompactMoney(minSalary)}</span>
        <span>${formatCompactMoney(maxSalary)}</span>
      </div>
      <div class="salary-plot" aria-label="${escapeHtml(`${points.length} annual salary points by band`)}">
        ${bandLines}
        ${ranges}
        ${dots}
      </div>
    </div>
  `;
}

function salaryBandY(band) {
  return clamp(94 - ((band - 1) / 7) * 84, 8, 94);
}

function salaryPointY(point) {
  return clamp(salaryBandY(point.band) + (point.jitter - 0.5) * 7.2, 5, 97);
}

function salaryPointClasses(point) {
  return [
    point.job.classification_confidence === "inferred" ? "is-inferred" : "is-confirmed",
    point.job.publicBoardSignal ? "is-public" : "",
    hasSalaryBandMismatch(point.job) ? "is-salary-mismatch" : "",
    point.job.boardStatus === "historical" ? "is-historical" : "",
  ].filter(Boolean).join(" ");
}

function salaryPointTitle(point) {
  const range = Math.abs(point.high - point.low) > 0.01
    ? `${formatMoney(point.low)}-${formatMoney(point.high)}`
    : formatMoney(point.midpoint);
  return `${point.job.displayCouncil}: ${point.job.job_title} - Band ${point.band} - ${range}/year`;
}

function salaryMinimumPointTitle(point) {
  return `${point.job.displayCouncil}: ${point.job.job_title} - Band ${point.band} - minimum ${formatMoney(point.low)}/year`;
}

function renderMonthChart(rows) {
  const counts = countBy(rows, (job) => job.canonical_reference_month || "unknown");
  const months = state.snapshot?.visuals?.month_counts || [];
  const max = Math.max(1, ...months.map((row) => counts.get(row.month) || row.count || 0));
  els.monthChart.innerHTML = months.map((row) => {
    const value = counts.get(row.month) || 0;
    return `
      <div class="spark-bar" title="${escapeHtml(row.month)}: ${formatCount(value || row.count)}">
        <i style="height:${Math.max(8, (((value || row.count || 0) / max) * 100)).toFixed(2)}%"></i>
        <span>${escapeHtml(String(row.month).slice(5) || row.month)}</span>
      </div>
    `;
  }).join("");
}

function renderSourceChart(rows) {
  const counts = countBy(rows, (job) => job.source_family || "unknown");
  const sourceRows = [...counts.entries()]
    .map(([source, count]) => ({ source, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 7);
  const max = Math.max(1, ...sourceRows.map((row) => row.count));
  els.sourceChart.innerHTML = sourceRows.map((row) => `
    <div class="bar-row">
      <span>${escapeHtml(sourceLabel(row.source))}</span>
      <div class="bar-track cool"><i style="width:${((row.count / max) * 100).toFixed(2)}%"></i></div>
      <strong>${formatCount(row.count)}</strong>
    </div>
  `).join("");
}

async function loadJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function init() {
  try {
    const geojson = window.__VIC_LGA_BOUNDARIES__ || await loadJson(GEOJSON_URL);
    const boardData = window.__VIC_COUNCIL_JOB_BOARD_DATA__ || await loadJson(BOARD_DATA_URL);
    state.geojson = geojson;
    state.snapshot = boardData;
    state.asOfDate = new Date(boardData.as_of_date || boardData.saved_at || Date.now());
    state.councils = boardData.councils || [];
    state.councilLookup = buildCouncilLookup(state.councils);
    state.jobs = enrichJobs(boardData.jobs || []).filter(isClassifiedJob);
    renderMap();
    const savedAt = boardData.saved_at ? `Updated ${formatDate(boardData.saved_at)}` : "Current vacancy data";
    const coverage = boardData.summary?.coverage?.coverage_rate ?? Math.round((groupedCounts(state.jobs).size / 79) * 100);
    els.snapshotNote.textContent = `${savedAt}. ${formatCount(state.jobs.length)} classified roles across ${formatCount(groupedCounts(state.jobs).size)} councils, with ${formatCount(coverage)}% statewide coverage.`;
    render();
  } catch (error) {
    els.snapshotNote.textContent = "Vacancy data could not be loaded.";
    els.resultCount.textContent = "Data unavailable";
    els.resultContext.textContent = error.message;
    els.list.innerHTML = `<div class="empty-note">${escapeHtml(error.message)}</div>`;
  }
}

els.search.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

els.clearCouncil.addEventListener("click", () => {
  state.selectedCouncilKey = "";
  render();
});

els.bandChart?.addEventListener("click", (event) => {
  const row = event.target.closest?.("[data-band]");
  if (!row) return;
  selectBand(row.dataset.band);
});

els.bandChart?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest?.("[data-band]");
  if (!row) return;
  event.preventDefault();
  selectBand(row.dataset.band);
});

els.mapFrame.addEventListener("pointerdown", beginMapPan);
els.mapFrame.addEventListener("pointermove", moveMapPan);
els.mapFrame.addEventListener("pointerup", endMapPan);
els.mapFrame.addEventListener("pointercancel", endMapPan);
els.mapFrame.addEventListener("wheel", zoomMap, { passive: false });

init();
