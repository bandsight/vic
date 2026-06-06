import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = dirname(fileURLToPath(import.meta.url));
const WIDTH = 1200;
const HEIGHT = 860;
const METRO_WIDTH = 420;
const METRO_HEIGHT = 300;

function readLocal(path) {
  return readFileSync(resolve(appDir, path), "utf8");
}

function readJson(path) {
  return JSON.parse(readFileSync(resolve(appDir, path), "utf8"));
}

function safeInlineScript(source) {
  return source.replaceAll("</script", "<\\/script");
}

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

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
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

function projectForBounds([lon, lat], bounds, width, height) {
  const [minLon, minLat, maxLon, maxLat] = bounds;
  return [
    ((lon - minLon) / (maxLon - minLon)) * width,
    ((maxLat - lat) / (maxLat - minLat)) * height,
  ];
}

function ringPath(ring, projector) {
  return `${ring.map((coord, index) => {
    const [x, y] = projector(coord);
    return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ")} Z`;
}

function geometryPath(geometry, projector) {
  if (geometry?.type === "Polygon") {
    return geometry.coordinates.map((ring) => ringPath(ring, projector)).join(" ");
  }
  if (geometry?.type === "MultiPolygon") {
    return geometry.coordinates.flatMap((polygon) => polygon.map((ring) => ringPath(ring, projector))).join(" ");
  }
  return "";
}

function councilLookup(councils) {
  const lookup = new Map();
  for (const council of councils || []) {
    const normalized = { ...council, _key: normaliseKey(council.map_join_key || council.spatial_key || council.short_name) };
    [
      council.short_name,
      council.long_name,
      council.official_name,
      council.spatial_name,
      council.spatial_key,
      council.map_join_key,
    ].forEach((value) => {
      const key = normaliseKey(value);
      if (key && !lookup.has(key)) lookup.set(key, normalized);
    });
  }
  return lookup;
}

function groupedCounts(jobs) {
  const counts = new Map();
  for (const job of jobs || []) {
    const key = normaliseKey(job.council_key || job.short_name || job.council_name);
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
  }
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
  if (!count) return null;
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

function jobStyle(count, domain) {
  const colour = jobColour(count, domain);
  if (!colour) return "";
  return [
    `--job-scale:${colour.scale.toFixed(3)}`,
    `--job-fill-alpha:${colour.fillAlpha.toFixed(3)}`,
    `--job-stroke-alpha:${colour.strokeAlpha.toFixed(3)}`,
    `--job-r:${colour.rgb[0]}`,
    `--job-g:${colour.rgb[1]}`,
    `--job-b:${colour.rgb[2]}`,
    `--job-stroke-r:${colour.strokeRgb[0]}`,
    `--job-stroke-g:${colour.strokeRgb[1]}`,
    `--job-stroke-b:${colour.strokeRgb[2]}`,
  ].join(";");
}

function fragmentId(key) {
  return `jobs-${normaliseKey(key).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
}

function buildFeatureGroups(features, lookup) {
  const groups = new Map();
  for (const feature of features || []) {
    const key = normaliseKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
    if (!key) continue;
    const bounds = geometryBounds(feature.geometry);
    const council = lookup.get(key) || {};
    const group = groups.get(key) || {
      key,
      name: feature.properties?.spatial_name || council.short_name || key,
      category: council.council_category || "",
      bounds: null,
      features: [],
    };
    group.features.push(feature);
    group.bounds = combineBounds([group.bounds, bounds]);
    groups.set(key, group);
  }
  return groups;
}

function isMetroCouncilKey(key, lookup) {
  return lookup.get(normaliseKey(key))?.council_category === "Metropolitan";
}

function staticPath(feature, projectionBounds, counts, countDomain, lookup, { metro = false, metroBounds = null } = {}) {
  const key = normaliseKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
  const count = counts.get(key) || 0;
  const classes = [
    "lga-boundary",
    metro ? "metro-boundary" : "",
    !metro && isMetroCouncilKey(key, lookup) ? "is-metro-main" : "",
    feature.properties?.is_reference_council === false ? "is-non-reference" : "",
    count ? "has-jobs" : "",
    count >= 4 ? "is-heavy" : "",
  ].filter(Boolean).join(" ");
  const bounds = metro ? metroBounds : projectionBounds;
  const width = metro ? METRO_WIDTH : WIDTH;
  const height = metro ? METRO_HEIGHT : HEIGHT;
  const d = geometryPath(feature.geometry, (coord) => projectForBounds(coord, bounds, width, height));
  const style = jobStyle(count, countDomain);
  const path = `<path d="${d}" data-key="${escapeHtml(key)}" class="${classes}"${style ? ` style="${style}"` : ""}></path>`;
  if (!count) return path;
  const label = `${feature.properties?.spatial_name || key}: ${count} job${count === 1 ? "" : "s"}`;
  return `<a href="#${fragmentId(key)}" aria-label="${escapeHtml(label)}">${path}</a>`;
}

function mapCenter(bounds, projectionBounds, width, height) {
  if (!bounds) return [0, 0];
  return projectForBounds([(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2], projectionBounds, width, height);
}

function staticMarker(group, counts, countDomain, { metro = false, projectionBounds }) {
  const count = counts.get(group.key) || 0;
  if (!count) return "";
  const [x, y] = mapCenter(group.bounds, projectionBounds, metro ? METRO_WIDTH : WIDTH, metro ? METRO_HEIGHT : HEIGHT);
  const classes = ["count-marker", metro ? "metro-count-marker" : "", "is-visible"].filter(Boolean).join(" ");
  const style = jobStyle(count, countDomain);
  const label = metro ? "" : `<text class="count-label" x="21" y="4" text-anchor="start" style="opacity:0.28">${escapeHtml(group.name)}</text>`;
  return `
    <g class="${classes}" data-key="${escapeHtml(group.key)}" transform="translate(${x.toFixed(2)} ${y.toFixed(2)})"${style ? ` style="${style}"` : ""}>
      <circle r="${metro ? 10 : 15}"></circle>
      <text y="0">${count}</text>
      ${label}
    </g>
  `;
}

function buildStaticMapHtml(boundaries, boardData) {
  const features = boundaries.features || [];
  const lookup = councilLookup(boardData.councils || []);
  const counts = groupedCounts(boardData.jobs || []);
  const countDomain = Math.max(2, quantile([...counts.values()], 0.9));
  const allBounds = combineBounds(features.map((feature) => geometryBounds(feature.geometry)));
  const projectionBounds = paddedBounds(allBounds, WIDTH, HEIGHT, 0.045);
  const groups = buildFeatureGroups(features, lookup);
  const metroFeatures = features.filter((feature) => isMetroCouncilKey(feature.properties?.spatial_key || feature.properties?.spatial_name, lookup));
  const metroBounds = paddedBounds(
    combineBounds(metroFeatures.map((feature) => geometryBounds(feature.geometry))),
    METRO_WIDTH,
    METRO_HEIGHT,
    0.08,
  );

  return {
    mapPaths: features.map((feature) => staticPath(feature, projectionBounds, counts, countDomain, lookup)).join("\n"),
    mapMarkers: [...groups.values()]
      .filter((group) => !isMetroCouncilKey(group.key, lookup))
      .map((group) => staticMarker(group, counts, countDomain, { projectionBounds }))
      .join("\n"),
    metroPaths: metroFeatures.map((feature) => staticPath(feature, projectionBounds, counts, countDomain, lookup, { metro: true, metroBounds })).join("\n"),
    metroMarkers: [...groups.values()]
      .filter((group) => isMetroCouncilKey(group.key, lookup))
      .map((group) => staticMarker(group, counts, countDomain, { metro: true, projectionBounds: metroBounds }))
      .join("\n"),
  };
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString("en-AU", { day: "2-digit", month: "short", year: "numeric" });
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

function fallbackSalary(job) {
  if (job.advertised_salary_text || job.salary_text) return job.advertised_salary_text || job.salary_text;
  const min = finiteNumber(job.advertised_salary_min ?? job.salary_min ?? job.annual_salary_min);
  const max = finiteNumber(job.advertised_salary_max ?? job.salary_max ?? job.annual_salary_max);
  if (min === null) return "Not listed";
  return max !== null && Math.abs(max - min) > 0.01
    ? `${formatMoney(min)}-${formatMoney(max)}`
    : formatMoney(min);
}

function fallbackSourceLabel(value) {
  const labels = {
    bigredsky: "Careers portal",
    pulse: "Careers portal",
    pageup: "Careers portal",
    smartrecruiters: "Careers portal",
    elmo_talent: "Careers portal",
    jora: "Jora",
    councildirect: "Council Direct",
    localgovernmentjobs: "Local Government Jobs",
    native_council: "Council website",
  };
  return labels[value] || String(value || "Council careers").replace(/_/g, " ");
}

function fallbackExternalHost(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function buildFallbackJobList(boardData) {
  const jobs = [...(boardData.jobs || [])].sort((a, b) => (
    String(a.short_name || a.council_name || "").localeCompare(String(b.short_name || b.council_name || ""))
    || Number(a.standard_band_number || 0) - Number(b.standard_band_number || 0)
    || String(a.job_title || "").localeCompare(String(b.job_title || ""))
  ));
  const groups = new Map();
  for (const job of jobs) {
    const key = normaliseKey(job.council_key || job.short_name || job.council_name);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(job);
  }
  return [...groups.entries()].map(([key, councilJobs]) => {
    const first = councilJobs[0] || {};
    const council = first.short_name || first.council_name || key;
    const cards = councilJobs.map((job) => {
      const links = Array.isArray(job.external_links) ? job.external_links.filter(Boolean) : [job.job_url].filter(Boolean);
      const host = fallbackExternalHost(job.job_url || links[0]);
      const closing = formatDate(job.closing_at || job.closing_at_text);
      const seen = formatDate(job.last_seen_at || job.first_seen_at);
      const details = [
        ["Council", job.council_name || council],
        ["Classification", job.classification_band || `Band ${job.standard_band_number}`],
        ["Salary", fallbackSalary(job)],
        ["Location", job.location_text || "Not listed"],
        ["Work type", job.work_type || "Not listed"],
        ["Source", fallbackSourceLabel(job.source_family)],
        ["Reference", job.canonical_reference_month || "Not listed"],
        ["Seen", seen || "Not listed"],
      ];
      const meta = [
        council,
        job.standard_band_number ? `Band ${job.standard_band_number}` : "",
        closing ? `Closes ${closing}` : "",
      ].filter(Boolean);
      return `
        <article class="job-card fallback-job-card">
          <div class="job-meta">${meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
          <h2>${escapeHtml(job.job_title || "Council role")}</h2>
          <dl class="job-details">
            ${details.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}
          </dl>
          ${links[0] ? `<a class="external-link" href="${escapeHtml(job.job_url || links[0])}" target="_blank" rel="noopener noreferrer">View external listing${host ? ` <span>${escapeHtml(host)}</span>` : ""}</a>` : ""}
        </article>
      `;
    }).join("");
    return `
      <section class="fallback-council-section" id="${fragmentId(key)}">
        <h2>${escapeHtml(council)} <span>${councilJobs.length} role${councilJobs.length === 1 ? "" : "s"}</span></h2>
        ${cards}
      </section>
    `;
  }).join("");
}

const indexHtml = readLocal("index.html");
const styles = readLocal("styles.css");
const embeddedData = readLocal("data/embedded-data.js");
const appJs = readLocal("app.js");
const boundaries = readJson("../../static/data/victoria-lga-boundaries.geojson");
const boardData = readJson("data/job-board-data.json");
const staticMap = buildStaticMapHtml(boundaries, boardData);
const fallbackJobList = buildFallbackJobList(boardData);

const standalone = indexHtml
  .replace('<g id="map-paths" aria-hidden="true"></g>', `<g id="map-paths" aria-hidden="true">${staticMap.mapPaths}</g>`)
  .replace('<g id="map-markers" aria-hidden="true"></g>', `<g id="map-markers" aria-hidden="true">${staticMap.mapMarkers}</g>`)
  .replace('<g id="metro-paths" aria-hidden="true"></g>', `<g id="metro-paths" aria-hidden="true">${staticMap.metroPaths}</g>`)
  .replace('<g id="metro-markers" aria-hidden="true"></g>', `<g id="metro-markers" aria-hidden="true">${staticMap.metroMarkers}</g>`)
  .replace('<strong id="result-count">Loading...</strong>', `<strong id="result-count">${(boardData.jobs || []).length.toLocaleString("en-AU")} roles</strong>`)
  .replace('<span id="result-context">Preparing map</span>', `<span id="result-context">${countsText(boardData.jobs)} council areas highlighted</span>`)
  .replace('<section id="job-list" class="job-list" aria-live="polite"></section>', `<section id="job-list" class="job-list" aria-live="polite">${fallbackJobList}</section>`)
  .replace(
    /<link rel="stylesheet" href="\.\/styles\.css\?v=[^"]+">/,
    `<style>\n${styles}\n</style>`,
  )
  .replace(
    /<script src="\.\/data\/embedded-data\.js\?v=[^"]+"><\/script>/,
    `<script>\n${safeInlineScript(embeddedData)}\n</script>`,
  )
  .replace(
    /<script type="module" src="\.\/app\.js\?v=[^"]+"><\/script>/,
    `<script>\n${safeInlineScript(appJs)}\n</script>`,
  )
  .replace(
    "<!doctype html>",
    "<!doctype html>\n<!-- Generated by apps/vic-council-job-board/build-standalone.mjs. Open directly in a browser. -->",
  );

writeFileSync(
  resolve(appDir, "vic-council-job-board-standalone.html"),
  standalone,
  "utf8",
);

console.log(JSON.stringify({
  output: "apps/vic-council-job-board/vic-council-job-board-standalone.html",
  bytes: Buffer.byteLength(standalone, "utf8"),
  static_map_paths: (boundaries.features || []).length,
  static_map_markers: groupedCounts(boardData.jobs || []).size,
}, null, 2));

function countsText(jobs) {
  return groupedCounts(jobs || []).size.toLocaleString("en-AU");
}
