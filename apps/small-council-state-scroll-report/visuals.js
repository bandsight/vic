/* global document, fetch */
import {
  clamp,
  escapeHtml,
  formatCurrency,
  formatSignedCurrency,
} from "./data-adapter.js";

function linePath(points) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
}

function dateToDecimalYear(dateValue) {
  const [year, month = "1", day = "1"] = String(dateValue || "").split("-");
  const date = Date.UTC(Number(year), Number(month) - 1, Number(day));
  const yearStart = Date.UTC(Number(year), 0, 1);
  const yearEnd = Date.UTC(Number(year) + 1, 0, 1);
  if (![date, yearStart, yearEnd].every(Number.isFinite)) return Number.NaN;
  return Number(year) + ((date - yearStart) / (yearEnd - yearStart));
}

function chartDomain(values, step = 100) {
  const clean = values.map(Number).filter(Number.isFinite);
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  return [
    Math.floor((min - step * 0.6) / step) * step,
    Math.ceil((max + step * 0.6) / step) * step,
  ];
}

function chartDomainWithFloor(values, step = 100) {
  const [min, max] = chartDomain(values, step);
  return [Math.max(0, min), max];
}

function normaliseSpatialKey(value) {
  return String(value || "")
    .toUpperCase()
    .replaceAll("&", " AND ")
    .replace(/[^A-Z0-9]+/g, " ")
    .trim();
}

function buildProjection(bounds, width, height, pad) {
  const [minLon, minLat, maxLon, maxLat] = bounds;
  const lonSpan = maxLon - minLon;
  const latSpan = maxLat - minLat;
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const scale = Math.min(plotW / lonSpan, plotH / latSpan);
  const mapW = lonSpan * scale;
  const mapH = latSpan * scale;
  const offsetX = pad.left + ((plotW - mapW) / 2);
  const offsetY = pad.top + ((plotH - mapH) / 2);

  return ([lon, lat]) => ({
    x: offsetX + ((lon - minLon) * scale),
    y: offsetY + ((maxLat - lat) * scale),
  });
}

function geometryRings(geometry) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return geometry.coordinates || [];
  if (geometry.type === "MultiPolygon") return (geometry.coordinates || []).flat();
  return [];
}

function geometryToPath(geometry, project) {
  return geometryRings(geometry).map((ring) => {
    const commands = ring.map((coordinate, index) => {
      const point = project(coordinate);
      return `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    });
    return `${commands.join(" ")} Z`;
  }).join(" ");
}

function collectProjectedBounds(feature, project) {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  geometryRings(feature.geometry).forEach((ring) => {
    ring.forEach((coordinate) => {
      const point = project(coordinate);
      minX = Math.min(minX, point.x);
      minY = Math.min(minY, point.y);
      maxX = Math.max(maxX, point.x);
      maxY = Math.max(maxY, point.y);
    });
  });
  if (!Number.isFinite(minX)) return null;
  return { minX, minY, maxX, maxY };
}

function mergeBounds(bounds, next) {
  if (!next) return bounds;
  if (!bounds) return { ...next };
  return {
    minX: Math.min(bounds.minX, next.minX),
    minY: Math.min(bounds.minY, next.minY),
    maxX: Math.max(bounds.maxX, next.maxX),
    maxY: Math.max(bounds.maxY, next.maxY),
  };
}

export function renderPayChart(payByBand, visualState = "state_only") {
  const bands = payByBand.bands;
  const width = 860;
  const height = 560;
  const pad = { top: 62, right: 44, bottom: 72, left: 74 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const allValues = bands.flatMap((row) => [
    row.stateMedian,
    row.smallMedian,
    ...(row.statewideRange || []),
    ...(row.smallRange || []),
  ]);
  const [yMin, yMax] = chartDomain(allValues, 100);
  const x = (index) => pad.left + (chartW * index) / Math.max(1, bands.length - 1);
  const y = (value) => pad.top + ((yMax - value) / (yMax - yMin)) * chartH;
  const showSmall = visualState !== "state_only";
  const showGap = ["gap_highlight", "timing_sensitive", "takeaway"].includes(visualState);
  const stateInfo = payByBand.states?.[visualState] || payByBand.states?.state_only || {};

  const statePoints = bands.map((row, index) => ({ x: x(index), y: y(row.stateMedian), row }));
  const smallPoints = bands.map((row, index) => ({ x: x(index), y: y(row.smallMedian), row }));

  function highlightClass(row) {
    if (visualState === "gap_highlight" && row.focus === "large_gap") return " is-highlight";
    if (visualState === "band_focus" && row.focus === "narrow_gap") return " is-highlight";
    if (visualState === "timing_sensitive" && row.timingSensitive) return " is-highlight is-timing";
    if (visualState === "takeaway" && (row.focus === "large_gap" || row.timingSensitive)) return " is-highlight";
    return "";
  }

  const yTicks = [yMin, Math.round((yMin + yMax) / 2 / 50) * 50, yMax];
  const grid = yTicks.map((tick) => `
    <g class="pay-chart-tick">
      <line x1="${pad.left}" x2="${width - pad.right}" y1="${y(tick).toFixed(1)}" y2="${y(tick).toFixed(1)}"></line>
      <text x="${pad.left - 14}" y="${(y(tick) + 4).toFixed(1)}">${escapeHtml(formatCurrency(tick).replace("A", ""))}</text>
    </g>
  `).join("");

  const ranges = bands.map((row, index) => {
    const stateRange = row.statewideRange || [row.stateMedian, row.stateMedian];
    const smallRange = row.smallRange || [row.smallMedian, row.smallMedian];
    const px = x(index);
    return `
      <g class="pay-band-range${highlightClass(row)}" data-band="${row.band}">
        <line class="state-range" x1="${px.toFixed(1)}" x2="${px.toFixed(1)}" y1="${y(stateRange[0]).toFixed(1)}" y2="${y(stateRange[1]).toFixed(1)}"></line>
        ${showSmall ? `<line class="small-range" x1="${(px + 8).toFixed(1)}" x2="${(px + 8).toFixed(1)}" y1="${y(smallRange[0]).toFixed(1)}" y2="${y(smallRange[1]).toFixed(1)}"></line>` : ""}
      </g>
    `;
  }).join("");

  const gapLines = showSmall ? bands.map((row, index) => {
    const px = x(index);
    return `
      <g class="pay-gap-line${showGap ? " is-visible" : ""}${highlightClass(row)}">
        <line x1="${px.toFixed(1)}" x2="${px.toFixed(1)}" y1="${y(row.stateMedian).toFixed(1)}" y2="${y(row.smallMedian).toFixed(1)}"></line>
        <text x="${(px + 10).toFixed(1)}" y="${(Math.min(y(row.stateMedian), y(row.smallMedian)) + 18).toFixed(1)}">${escapeHtml(formatSignedCurrency(row.gap))}</text>
      </g>
    `;
  }).join("") : "";

  const stateMarkers = statePoints.map((point) => `
    <g class="pay-point state-point${highlightClass(point.row)}">
      <circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="5.5"></circle>
      <title>${escapeHtml(`${point.row.label} statewide median ${formatCurrency(point.row.stateMedian)}`)}</title>
    </g>
  `).join("");

  const smallMarkers = showSmall ? smallPoints.map((point) => `
    <g class="pay-point small-point${highlightClass(point.row)}">
      <circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="6.4"></circle>
      <title>${escapeHtml(`${point.row.label} small-council median ${formatCurrency(point.row.smallMedian)}; gap ${formatSignedCurrency(point.row.gap)}`)}</title>
    </g>
  `).join("") : "";

  const bandLabels = bands.map((row, index) => `
    <g class="pay-band-label${highlightClass(row)}">
      <text x="${x(index).toFixed(1)}" y="${height - 34}">${escapeHtml(String(row.band))}</text>
    </g>
  `).join("");

  const callouts = bands.filter((row) => highlightClass(row)).map((row, calloutIndex) => {
    const index = bands.findIndex((item) => item.band === row.band);
    const topY = Math.min(y(row.stateMedian), y(row.smallMedian));
    const labelY = clamp(topY - 26 - (calloutIndex % 2) * 16, pad.top + 16, height - pad.bottom - 32);
    return `
      <g class="pay-callout">
        <line x1="${x(index).toFixed(1)}" x2="${x(index).toFixed(1)}" y1="${(topY - 8).toFixed(1)}" y2="${labelY.toFixed(1)}"></line>
        <text x="${x(index).toFixed(1)}" y="${(labelY - 7).toFixed(1)}">${escapeHtml(row.timingSensitive ? "timing" : formatSignedCurrency(row.gap))}</text>
      </g>
    `;
  }).join("");

  return `
    <div class="visual-caption">
      <span>${escapeHtml(stateInfo.label || "Pay position")}</span>
      <strong>${escapeHtml(stateInfo.summary || "")}</strong>
    </div>
    <svg class="pay-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(payByBand.question)}" data-pay-visual-state="${escapeHtml(visualState)}">
      <defs>
        <linearGradient id="smallCouncilGlow" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stop-color="#8ab4ff"></stop>
          <stop offset="100%" stop-color="#bba7ff"></stop>
        </linearGradient>
      </defs>
      <rect class="chart-plane" x="${pad.left}" y="${pad.top}" width="${chartW}" height="${chartH}" rx="8"></rect>
      ${grid}
      ${ranges}
      <path class="state-line" d="${linePath(statePoints)}"></path>
      ${showSmall ? `<path class="small-line" d="${linePath(smallPoints)}"></path>` : ""}
      ${gapLines}
      ${stateMarkers}
      ${smallMarkers}
      ${callouts}
      ${bandLabels}
      <text class="axis-title" x="${pad.left + chartW / 2}" y="${height - 10}">Standard band</text>
      <text class="axis-title axis-title-y" x="18" y="${pad.top + chartH / 2}" transform="rotate(-90 18 ${pad.top + chartH / 2})">Weekly midpoint</text>
      <g class="chart-legend" aria-hidden="true">
        <line class="state-line" x1="${width - 245}" x2="${width - 205}" y1="30" y2="30"></line>
        <text x="${width - 196}" y="34">Statewide median</text>
        ${showSmall ? `<line class="small-line" x1="${width - 245}" x2="${width - 205}" y1="52" y2="52"></line><text x="${width - 196}" y="56">Small council median</text>` : ""}
      </g>
    </svg>
  `;
}

export function renderPayPointGalaxy(galaxy) {
  const observations = (galaxy.observations || []).filter((item) => (
    Number.isFinite(Number(item.averageWeekly)) && Number.isFinite(dateToDecimalYear(item.date))
  ));
  const width = 1180;
  const height = 650;
  const pad = { top: 86, right: 64, bottom: 76, left: 82 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const years = observations.map((item) => dateToDecimalYear(item.date));
  const values = observations.map((item) => Number(item.averageWeekly));
  const yearMin = Math.floor(Math.min(...years));
  const yearMax = Math.ceil(Math.max(...years));
  const [yMin, yMax] = chartDomainWithFloor(values, 100);
  const maxRows = Math.max(...observations.map((item) => Number(item.rowCount) || 1));
  const x = (decimalYear) => pad.left + ((decimalYear - yearMin) / (yearMax - yearMin)) * chartW;
  const y = (value) => pad.top + ((yMax - value) / (yMax - yMin)) * chartH;
  const radius = (rowCount) => 3.2 + (Math.sqrt(Math.max(1, Number(rowCount))) / Math.sqrt(maxRows)) * 8.8;
  const xTicks = Array.from({ length: yearMax - yearMin + 1 }, (_, index) => yearMin + index)
    .filter((year) => year === yearMin || year === yearMax || year % 2 === 0);
  const yTicks = Array.from(new Set([
    yMin,
    Math.round((yMin + ((yMax - yMin) * 0.25)) / 100) * 100,
    Math.round((yMin + ((yMax - yMin) * 0.5)) / 100) * 100,
    Math.round((yMin + ((yMax - yMin) * 0.75)) / 100) * 100,
    yMax,
  ]));
  const bandGuideValues = [1, 3, 5, 7, 8].map((band) => {
    const bandValues = observations
      .filter((item) => Number(item.band) === band)
      .map((item) => Number(item.averageWeekly));
    if (!bandValues.length) return null;
    return {
      band,
      value: bandValues.reduce((sum, value) => sum + value, 0) / bandValues.length,
    };
  }).filter(Boolean);

  const grid = [
    ...xTicks.map((tick) => `
      <g class="galaxy-tick galaxy-x-tick">
        <line x1="${x(tick).toFixed(1)}" x2="${x(tick).toFixed(1)}" y1="${pad.top}" y2="${height - pad.bottom}"></line>
        <text x="${x(tick).toFixed(1)}" y="${height - 32}">${tick}</text>
      </g>
    `),
    ...yTicks.map((tick) => `
      <g class="galaxy-tick galaxy-y-tick">
        <line x1="${pad.left}" x2="${width - pad.right}" y1="${y(tick).toFixed(1)}" y2="${y(tick).toFixed(1)}"></line>
        <text x="${pad.left - 14}" y="${(y(tick) + 4).toFixed(1)}">${escapeHtml(formatCurrency(tick).replace("A", ""))}</text>
      </g>
    `),
  ].join("");

  const bandGuides = bandGuideValues.map((item) => `
    <g class="galaxy-band-guide">
      <line x1="${pad.left}" x2="${width - pad.right}" y1="${y(item.value).toFixed(1)}" y2="${y(item.value).toFixed(1)}"></line>
      <text x="${width - pad.right + 8}" y="${(y(item.value) + 4).toFixed(1)}">B${item.band}</text>
    </g>
  `).join("");

  const points = observations.map((item, index) => {
    const decimalYear = dateToDecimalYear(item.date);
    const cohort = item.cohort === "small_shire" ? "small" : "statewide";
    const bandJitter = ((Number(item.band) - 4.5) * 1.6);
    const cohortJitter = cohort === "small" ? 3.2 : -3.2;
    const wave = ((index % 5) - 2) * 0.9;
    const px = x(decimalYear) + cohortJitter + wave;
    const py = y(Number(item.averageWeekly)) + bandJitter;
    return `
      <circle
        class="galaxy-point is-${cohort} band-${escapeHtml(item.band)}"
        cx="${px.toFixed(1)}"
        cy="${py.toFixed(1)}"
        r="${radius(item.rowCount).toFixed(1)}"
      >
        <title>${escapeHtml(`${item.cohortLabel} ${item.levelLabel}, ${item.date}: ${formatCurrency(item.averageWeekly)} average weekly (${item.rowCount} rows, ${item.councilCount} councils)`)}</title>
      </circle>
    `;
  }).join("");

  const metrics = (galaxy.summaryMetrics || []).map((item) => `
    <article>
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
      <small>${escapeHtml(item.detail)}</small>
    </article>
  `).join("");

  return `
    <div class="galaxy-panel">
      <div class="galaxy-panel-header">
        <div>
          <span>${escapeHtml(galaxy.title || "Pay point galaxy")}</span>
          <strong>${escapeHtml(galaxy.question || "")}</strong>
        </div>
        <p>${escapeHtml(galaxy.metric || "")}</p>
      </div>
      <div class="galaxy-metrics" aria-label="Pay point galaxy coverage metrics">
        ${metrics}
      </div>
      <svg class="pay-galaxy-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(galaxy.question || "Temporal pay scatter plot")}">
        <defs>
          <radialGradient id="galaxyStateGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#8ab4ff" stop-opacity="0.82"></stop>
            <stop offset="100%" stop-color="#8ab4ff" stop-opacity="0.1"></stop>
          </radialGradient>
          <radialGradient id="galaxySmallGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stop-color="#bba7ff" stop-opacity="0.95"></stop>
            <stop offset="100%" stop-color="#bba7ff" stop-opacity="0.14"></stop>
          </radialGradient>
        </defs>
        <rect class="galaxy-plane" x="${pad.left}" y="${pad.top}" width="${chartW}" height="${chartH}" rx="10"></rect>
        ${grid}
        ${bandGuides}
        <g class="galaxy-points">
          ${points}
        </g>
        <text class="axis-title" x="${pad.left + chartW / 2}" y="${height - 10}">Effective date</text>
        <text class="axis-title axis-title-y" x="20" y="${pad.top + chartH / 2}" transform="rotate(-90 20 ${pad.top + chartH / 2})">Average weekly dollars</text>
        <g class="galaxy-legend" aria-hidden="true">
          <circle class="galaxy-point is-statewide" cx="${width - 288}" cy="42" r="7"></circle>
          <text x="${width - 272}" y="46">Statewide average</text>
          <circle class="galaxy-point is-small" cx="${width - 142}" cy="42" r="7"></circle>
          <text x="${width - 126}" y="46">Small shire average</text>
        </g>
      </svg>
      <p class="galaxy-caveat">${escapeHtml(galaxy.caveat || "")}</p>
    </div>
  `;
}

export function renderDistributionChart(distribution, mode = "raw") {
  const profiles = distribution.prototypeStyle?.profiles || {};
  const selectedProfile = mode === "smoothed" ? profiles.smoothed : profiles.raw;
  const fallbackProfile = distribution.prototypeStyle;
  const profile = selectedProfile || fallbackProfile;
  if (profile?.observations?.length) {
    const observations = profile.observations;
    const width = 900;
    const cohortRows = profile.cohortStats?.length ? profile.cohortStats : [];
    const height = Math.max(710, 430 + (cohortRows.length + 1) * 52);
    const pad = { top: 74, right: 58, bottom: 86, left: 84 };
    const chartW = width - pad.left - pad.right;
    const values = observations.map((item) => Number(item.value)).filter(Number.isFinite);
    const [xMin, xMax] = chartDomain(values, 50);
    const x = (value) => pad.left + ((value - xMin) / (xMax - xMin)) * chartW;
    const baseY = 242;
    const bins = (profile.densityBins?.length ? profile.densityBins : []).map((bin) => {
      const count = Number(bin.count) || 0;
      const center = (Number(bin.start) + Number(bin.end)) / 2;
      return {
        x: x(center),
        y: baseY - (count * 13),
        count,
      };
    });
    const densityBins = bins.length ? bins : Array.from({ length: 14 }, (_, index) => {
      const binMin = xMin + ((xMax - xMin) * index) / 14;
      const binMax = xMin + ((xMax - xMin) * (index + 1)) / 14;
      const count = values.filter((value) => value >= binMin && (index === 13 ? value <= binMax : value < binMax)).length;
      return {
        x: x((binMin + binMax) / 2),
        y: baseY - (count * 13),
        count,
      };
    });
    const densityPoints = [
      { x: pad.left, y: baseY },
      ...densityBins.map((bin) => ({ x: bin.x, y: bin.y })),
      { x: width - pad.right, y: baseY },
    ];
    const sortedObs = [...observations].sort((a, b) => Number(a.value) - Number(b.value));
    const ticks = [xMin, profile.stateStats?.p25, profile.stateStats?.median, profile.stateStats?.p75, xMax]
      .filter((value, index, list) => Number.isFinite(Number(value)) && list.findIndex((other) => Math.round(Number(other)) === Math.round(Number(value))) === index)
      .map((tick) => `
        <g class="dist-tick">
          <line x1="${x(tick).toFixed(1)}" x2="${x(tick).toFixed(1)}" y1="${pad.top + 40}" y2="${height - pad.bottom + 10}"></line>
          <text x="${x(tick).toFixed(1)}" y="${height - 30}">${escapeHtml(formatCurrency(tick).replace("A", ""))}</text>
        </g>
      `).join("");
    const percentileLines = [
      ["P25", profile.stateStats?.p25],
      ["Median", profile.stateStats?.median],
      ["P75", profile.stateStats?.p75],
    ].filter(([, value]) => Number.isFinite(Number(value))).map(([label, value]) => `
      <g class="prototype-percentile ${label === "Median" ? "is-median" : ""}">
        <line x1="${x(value).toFixed(1)}" x2="${x(value).toFixed(1)}" y1="${(baseY - 145).toFixed(1)}" y2="${(baseY + 104).toFixed(1)}"></line>
        <text x="${x(value).toFixed(1)}" y="${(baseY - 156).toFixed(1)}">${escapeHtml(label)}</text>
      </g>
    `).join("");
    const stateMedian = profile.stateStats?.median;
    const categoryClass = (category) => `category-${String(category || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
    const profileDiagnostics = profile.shapeDiagnostics || distribution.shapeDiagnostics;
    const cohortLaneOrder = cohortRows.length
      ? cohortRows
      : Array.from(new Set(sortedObs.map((item) => item.category))).map((category) => ({
        category,
        count: sortedObs.filter((item) => item.category === category).length,
        stats: { median: null },
      }));
    const allLaneY = 326;
    const laneStartY = 390;
    const laneGap = 48;
    const laneYByCategory = new Map(cohortLaneOrder.map((item, index) => [item.category, laneStartY + index * laneGap]));
    const lanePointRadius = 2.6;
    const allLanePointY = (index) => allLaneY + (((index % 9) - 4) * 2.1);
    const cohortLanePointY = (item, index) => (laneYByCategory.get(item.category) || laneStartY) + (((index % 7) - 3) * 2.7);
    const allLaneDots = sortedObs.map((item, index) => {
      return `
        <circle class="prototype-observation statewide-lane-observation" cx="${x(item.value).toFixed(1)}" cy="${allLanePointY(index).toFixed(1)}" r="${lanePointRadius}"></circle>
      `;
    }).join("");
    const observationsMarkup = sortedObs.map((item, index) => {
      const y = cohortLanePointY(item, index);
      return `
        <circle class="prototype-observation cohort-lane-observation" cx="${x(item.value).toFixed(1)}" cy="${y.toFixed(1)}" r="${lanePointRadius}"></circle>
      `;
    }).join("");
    const allLane = `
      <g class="statewide-lane">
        <line class="cohort-lane-rule statewide-lane-rule" x1="${pad.left}" x2="${width - pad.right}" y1="${allLaneY.toFixed(1)}" y2="${allLaneY.toFixed(1)}"></line>
        <text class="cohort-lane-label statewide-lane-label" x="${pad.left}" y="${(allLaneY - 13).toFixed(1)}">All active councils (${escapeHtml(sortedObs.length)})</text>
      </g>
    `;
    const cohortLanes = cohortLaneOrder.map((item) => {
      const laneY = laneYByCategory.get(item.category);
      const medianValue = item.stats?.median;
      const count = item.count || item.stats?.count || 0;
      const className = `cohort-lane ${categoryClass(item.category)} ${item.category === "Small shire" ? "is-small" : ""}`;
      return `
        <g class="${className}">
          <line class="cohort-lane-rule" x1="${pad.left}" x2="${width - pad.right}" y1="${laneY.toFixed(1)}" y2="${laneY.toFixed(1)}"></line>
          <text class="cohort-lane-label" x="${pad.left}" y="${(laneY - 11).toFixed(1)}">${escapeHtml(item.category)} (${escapeHtml(count)})</text>
          ${Number.isFinite(Number(medianValue)) ? `
            <line class="cohort-lane-median" x1="${x(medianValue).toFixed(1)}" x2="${x(medianValue).toFixed(1)}" y1="${(laneY - 16).toFixed(1)}" y2="${(laneY + 16).toFixed(1)}"></line>
          ` : ""}
        </g>
      `;
    }).join("");
    const stateMedianMarkup = Number.isFinite(Number(stateMedian)) ? `
      <g class="prototype-state-median">
        <circle cx="${x(stateMedian).toFixed(1)}" cy="${baseY.toFixed(1)}" r="5.5"></circle>
        <text x="${x(stateMedian).toFixed(1)}" y="${(baseY + 28).toFixed(1)}">State median</text>
      </g>
    ` : "";
    const highlightMarkup = "";
    const peakLabels = (profileDiagnostics?.primaryPeaks || []).map((peak, index) => {
      const [start, end] = peak.range || [];
      if (!Number.isFinite(Number(start)) || !Number.isFinite(Number(end))) return "";
      const peakX = x((Number(start) + Number(end)) / 2);
      const labelX = clamp(peakX, pad.left + 102, width - pad.right - 102);
      const peakY = Math.max(88 + (index % 2) * 24, baseY - (Number(peak.count || 0) * 13) - 18);
      const fallbackLabel = `${peak.count || 0} councils`;
      return `
        <g class="prototype-peak-label">
          <line x1="${peakX.toFixed(1)}" x2="${labelX.toFixed(1)}" y1="${(baseY - 4).toFixed(1)}" y2="${(peakY + 8).toFixed(1)}"></line>
          <text x="${labelX.toFixed(1)}" y="${peakY.toFixed(1)}">${escapeHtml(peak.label || fallbackLabel)}</text>
        </g>
      `;
    }).join("");
    const diagnostics = profileDiagnostics ? `
      <div class="distribution-diagnostic">
        <span>${escapeHtml(profileDiagnostics.reading)}</span>
        <p>${escapeHtml(profileDiagnostics.interpretation)}</p>
      </div>
    ` : "";
    return `
      ${diagnostics}
      <svg class="distribution-chart prototype-distribution-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(distribution.question)}">
        <text class="prototype-title" x="${pad.left}" y="34">${escapeHtml(profile.title || `Band ${distribution.focusBand} distribution`)}</text>
        <text class="prototype-subtitle" x="${pad.left}" y="55">${escapeHtml(`${profile.stateStats?.count || observations.length} active statewide ${String(profile.valueBasisLabel || "midpoint").toLowerCase()} observations across ${cohortLaneOrder.length} council cohorts as at ${distribution.asOfDate || "snapshot date"}`)}</text>
        ${ticks}
        <path class="prototype-density-fill" d="${linePath(densityPoints)} Z"></path>
        <path class="prototype-density-line" d="${linePath(densityPoints)}"></path>
        ${percentileLines}
        ${peakLabels}
        <line class="prototype-axis" x1="${pad.left}" x2="${width - pad.right}" y1="${baseY}" y2="${baseY}"></line>
        ${allLane}
        ${allLaneDots}
        ${cohortLanes}
        ${observationsMarkup}
        ${highlightMarkup}
        ${stateMedianMarkup}
        <g class="distribution-legend prototype-legend">
          <circle class="prototype-observation statewide-lane-observation" cx="${width - 216}" cy="34" r="${lanePointRadius}"></circle>
          <text x="${width - 202}" y="38">Statewide</text>
          <circle class="prototype-observation cohort-lane-observation" cx="${width - 108}" cy="34" r="${lanePointRadius}"></circle>
          <text x="${width - 94}" y="38">Cohort lanes</text>
        </g>
      </svg>
    `;
  }

  const rows = distribution.rangeRibbons || [];
  const width = 840;
  const height = 112 + rows.length * 102;
  const pad = { top: 58, right: 42, bottom: 58, left: 92 };
  const values = rows.flatMap((row) => [
    row.stateP10,
    row.stateP25,
    row.stateMedian,
    row.stateP75,
    row.stateP90,
    row.smallP25,
    row.smallMedian,
    row.smallP75,
  ]);
  const [xMin, xMax] = chartDomain(values, 100);
  const chartW = width - pad.left - pad.right;
  const x = (value) => pad.left + ((value - xMin) / (xMax - xMin)) * chartW;

  const ticks = [xMin, Math.round((xMin + xMax) / 2 / 50) * 50, xMax].map((tick) => `
    <g class="dist-tick">
      <line x1="${x(tick).toFixed(1)}" x2="${x(tick).toFixed(1)}" y1="${pad.top - 12}" y2="${height - pad.bottom + 8}"></line>
      <text x="${x(tick).toFixed(1)}" y="${height - 24}">${escapeHtml(formatCurrency(tick).replace("A", ""))}</text>
    </g>
  `).join("");

  const ribbons = rows.map((row, index) => {
    const y = pad.top + index * 102 + 44;
    return `
      <g class="distribution-row">
        <text class="distribution-band-name" x="24" y="${(y + 5).toFixed(1)}">Band ${escapeHtml(row.band)}</text>
        <line class="distribution-whisker" x1="${x(row.stateP10).toFixed(1)}" x2="${x(row.stateP90).toFixed(1)}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line>
        <line class="distribution-iqr" x1="${x(row.stateP25).toFixed(1)}" x2="${x(row.stateP75).toFixed(1)}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line>
        <line class="distribution-median" x1="${x(row.stateMedian).toFixed(1)}" x2="${x(row.stateMedian).toFixed(1)}" y1="${(y - 21).toFixed(1)}" y2="${(y + 21).toFixed(1)}"></line>
        <line class="distribution-small-range" x1="${x(row.smallP25).toFixed(1)}" x2="${x(row.smallP75).toFixed(1)}" y1="${(y + 24).toFixed(1)}" y2="${(y + 24).toFixed(1)}"></line>
        <circle class="distribution-small-median" cx="${x(row.smallMedian).toFixed(1)}" cy="${(y + 24).toFixed(1)}" r="7"></circle>
        <text class="distribution-row-note" x="${x(row.smallMedian).toFixed(1)}" y="${(y + 48).toFixed(1)}">small median</text>
        <title>${escapeHtml(`Band ${row.band}: statewide median ${formatCurrency(row.stateMedian)}, small median ${formatCurrency(row.smallMedian)}`)}</title>
      </g>
    `;
  }).join("");

  return `
    <svg class="distribution-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(distribution.question)}">
      ${ticks}
      ${ribbons}
      <g class="distribution-legend">
        <line class="distribution-iqr" x1="92" x2="152" y1="27" y2="27"></line>
        <text x="162" y="31">Statewide middle range</text>
        <line class="distribution-small-range" x1="360" x2="420" y1="27" y2="27"></line>
        <circle class="distribution-small-median" cx="390" cy="27" r="6"></circle>
        <text x="434" y="31">Small-council cohort</text>
      </g>
    </svg>
  `;
}

export function renderUpliftVisual(upliftTimeline, phase = "current") {
  const width = 860;
  const height = 430;
  const pad = { top: 64, right: 48, bottom: 62, left: 182 };
  const series = upliftTimeline.series || [];
  const values = series.flatMap((row) => [row.currentWeekly, row.horizonWeekly]);
  const [xMin, xMax] = chartDomain(values, 100);
  const chartW = width - pad.left - pad.right;
  const x = (value) => pad.left + ((value - xMin) / (xMax - xMin)) * chartW;
  const rowGap = 74;
  const visibleHorizon = phase === "horizon";
  const visibleUplifts = phase === "uplifts" || phase === "horizon";
  const phaseLabel = (upliftTimeline.phases || []).find((item) => item.id === phase)?.label || "Current snapshot";

  const ticks = [xMin, Math.round((xMin + xMax) / 2 / 50) * 50, xMax].map((tick) => `
    <g class="uplift-tick">
      <line x1="${x(tick).toFixed(1)}" x2="${x(tick).toFixed(1)}" y1="${pad.top - 18}" y2="${height - pad.bottom + 8}"></line>
      <text x="${x(tick).toFixed(1)}" y="${height - 24}">${escapeHtml(formatCurrency(tick).replace("A", ""))}</text>
    </g>
  `).join("");

  const rows = series.map((row, index) => {
    const y = pad.top + index * rowGap + 32;
    let rollingRate = Number(row.currentWeekly);
    const upliftMarkers = (row.uplifts || []).map((uplift) => {
      if (Number.isFinite(Number(uplift.projectedWeekly))) {
        rollingRate = Number(uplift.projectedWeekly);
      } else {
        rollingRate *= 1 + (Number(uplift.pct || 0) / 100);
      }
      const markerX = x(clamp(rollingRate, xMin, xMax));
      return `
        <g class="uplift-marker">
          <line x1="${markerX.toFixed(1)}" x2="${markerX.toFixed(1)}" y1="${(y - 17).toFixed(1)}" y2="${(y + 17).toFixed(1)}"></line>
        <text x="${markerX.toFixed(1)}" y="${(y - 24).toFixed(1)}">${escapeHtml(uplift.display || `${uplift.pct}%`)}</text>
          <title>${escapeHtml(`${row.name}: ${uplift.label} on ${uplift.date}`)}</title>
        </g>
      `;
    }).join("");

    return `
      <g class="uplift-row">
        <text class="uplift-name" x="24" y="${(y + 5).toFixed(1)}">${escapeHtml(row.name)}</text>
        <text class="uplift-cycle" x="24" y="${(y + 24).toFixed(1)}">${escapeHtml(row.cycleStatus)}</text>
        <line class="uplift-lane" x1="${pad.left}" x2="${width - pad.right}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line>
        <line class="uplift-change${visibleHorizon ? " is-visible" : ""}" x1="${x(row.currentWeekly).toFixed(1)}" x2="${x(row.horizonWeekly).toFixed(1)}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line>
        <circle class="uplift-current" cx="${x(row.currentWeekly).toFixed(1)}" cy="${y.toFixed(1)}" r="7"></circle>
        <text class="uplift-value current-value" x="${(x(row.currentWeekly) + 12).toFixed(1)}" y="${(y - 10).toFixed(1)}">${escapeHtml(formatCurrency(row.currentWeekly))}</text>
        ${visibleUplifts ? upliftMarkers : ""}
        ${visibleHorizon ? `<circle class="uplift-horizon" cx="${x(row.horizonWeekly).toFixed(1)}" cy="${y.toFixed(1)}" r="7"></circle><text class="uplift-value horizon-value" x="${(x(row.horizonWeekly) + 12).toFixed(1)}" y="${(y + 24).toFixed(1)}">${escapeHtml(formatCurrency(row.horizonWeekly))}</text>` : ""}
      </g>
    `;
  }).join("");

  return `
    <div class="visual-caption">
      <span>${escapeHtml(phaseLabel)}</span>
      <strong>${escapeHtml(upliftTimeline.summary)}</strong>
    </div>
    <svg class="uplift-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(upliftTimeline.question)}" data-uplift-phase="${escapeHtml(phase)}">
      <text class="uplift-axis-label" x="${pad.left}" y="28">${escapeHtml(upliftTimeline.snapshotDate)} snapshot</text>
      <text class="uplift-axis-label" x="${width - pad.right}" y="28" text-anchor="end">${escapeHtml(upliftTimeline.horizonDate)} horizon</text>
      ${ticks}
      ${rows}
    </svg>
  `;
}

export function renderEvidenceChain(chain) {
  return `
    <div class="evidence-chain" role="list">
      ${chain.map((item, index) => `
        <article class="evidence-node" role="listitem" style="--node-index: ${index}">
          <span>${String(index + 1).padStart(2, "0")}</span>
          <h3>${escapeHtml(item.stage)}</h3>
          <p>${escapeHtml(item.description)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

export function renderCohortConstellation(cohort) {
  const examples = cohort.smallCouncilExamples || [];
  return `
    <div class="cohort-constellation" aria-label="Illustrative small council cohort">
      <div class="cohort-orbit statewide-node">
        <span>All Victorian councils</span>
        <strong>${escapeHtml(cohort.comparisonUniverse?.statewideCouncilCount || "")}</strong>
      </div>
      <div class="cohort-core-node">
        <span>Small councils</span>
        <strong>${escapeHtml(cohort.comparisonUniverse?.smallCouncilCount || examples.length)}</strong>
      </div>
      <div class="cohort-member-grid">
        ${examples.map((item) => `
          <article class="cohort-member">
            <span>${escapeHtml(item.type)}</span>
            <strong>${escapeHtml(item.name)}</strong>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

export function renderCohortMapShell(cohort) {
  const map = cohort.map || {};
  const universe = cohort.comparisonUniverse || {};
  const councilList = map.allSmallShireCouncils || [];

  if (!map.boundaryGeojsonUrl || !councilList.length) {
    return renderCohortConstellation(cohort);
  }

  return `
    <div class="cohort-map-card" aria-label="Controlled Small shire cohort map">
      <div class="cohort-map-header">
        <div>
          <span>Controlled metadata map</span>
          <strong>${escapeHtml(map.title || "Victoria LGA context")}</strong>
        </div>
        <p>${escapeHtml(map.categoryField || "council_category")} = ${escapeHtml(map.categoryValue || "Small shire")}</p>
      </div>
      <div class="cohort-map-stats" aria-label="Cohort coverage metrics">
        <article>
          <span>Small shire profile members</span>
          <strong>${escapeHtml(universe.smallCouncilCount || councilList.length)}</strong>
        </article>
        <article>
          <span>With active pay rows</span>
          <strong>${escapeHtml(universe.smallCouncilPayCoverage || map.activePaySpatialKeys?.length || 0)}</strong>
        </article>
        <article>
          <span>Statewide council universe</span>
          <strong>${escapeHtml(universe.statewideCouncilCount || "")}</strong>
        </article>
      </div>
      <div id="cohort-map-root" class="cohort-map-shell" data-boundary-url="${escapeHtml(map.boundaryGeojsonUrl)}">
        <div class="cohort-map-loading">Loading governed geography asset...</div>
      </div>
      <div class="cohort-map-footer">
        <div class="cohort-map-legend" aria-label="Map legend">
          <span><i class="legend-swatch statewide"></i>Statewide context</span>
          <span><i class="legend-swatch controlled"></i>Small shire profile member</span>
          <span><i class="legend-swatch active"></i>Active pay coverage</span>
        </div>
        <p>${escapeHtml(map.caveat || cohort.productionCaveat || "")}</p>
      </div>
      <div class="cohort-map-list" aria-label="Small shire controlled cohort members">
        ${councilList.map((council) => `
          <article class="${council.hasActivePayCoverage ? "has-coverage" : "needs-coverage"}">
            <span>${escapeHtml(council.regionalPartnership || "Regional metadata")}</span>
            <strong>${escapeHtml(council.shortName || council.name)}</strong>
            <small>${escapeHtml(council.hasActivePayCoverage ? "active pay rows" : "profile member only")}</small>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderCohortBoundaryMap(cohort, geojson) {
  const map = cohort.map || {};
  const width = 960;
  const height = 660;
  const pad = { top: 26, right: 26, bottom: 34, left: 26 };
  const features = (geojson.features || []).filter((feature) => feature.properties?.is_reference_council !== false);
  const bounds = geojson.bbox || [
    140.95,
    -39.15,
    150.0,
    -33.95,
  ];
  const project = buildProjection(bounds, width, height, pad);
  const smallKeys = new Set((map.smallSpatialKeys || []).map(normaliseSpatialKey));
  const activeKeys = new Set((map.activePaySpatialKeys || []).map(normaliseSpatialKey));
  const labelKeys = new Set((map.labelSpatialKeys || []).map(normaliseSpatialKey));
  const councilsByKey = new Map((map.allSmallShireCouncils || []).map((council) => [
    normaliseSpatialKey(council.spatialKey || council.spatialName || council.shortName),
    council,
  ]));
  const projectedBoundsByKey = new Map();

  const boundaryPaths = features.map((feature) => {
    const key = normaliseSpatialKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
    const isSmall = smallKeys.has(key);
    const hasCoverage = activeKeys.has(key);
    const path = geometryToPath(feature.geometry, project);
    projectedBoundsByKey.set(key, mergeBounds(projectedBoundsByKey.get(key), collectProjectedBounds(feature, project)));
    const className = [
      "lga-boundary",
      isSmall ? "is-small-shire" : "",
      hasCoverage ? "has-pay-coverage" : "",
      isSmall && !hasCoverage ? "needs-pay-coverage" : "",
    ].filter(Boolean).join(" ");
    const council = councilsByKey.get(key);
    const coverageLabel = isSmall
      ? `${hasCoverage ? "active pay coverage" : "profile member only"}`
      : "statewide context";

    return `
      <path class="${className}" d="${escapeHtml(path)}" fill-rule="evenodd">
        <title>${escapeHtml(`${feature.properties?.spatial_name || key}: ${council?.category || coverageLabel}`)}</title>
      </path>
    `;
  }).join("");

  const markers = [...activeKeys].map((key) => {
    const boundsForKey = projectedBoundsByKey.get(key);
    if (!boundsForKey) return "";
    const council = councilsByKey.get(key);
    const x = (boundsForKey.minX + boundsForKey.maxX) / 2;
    const y = (boundsForKey.minY + boundsForKey.maxY) / 2;
    return `
      <circle class="cohort-map-marker" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.8">
        <title>${escapeHtml(`${council?.name || key}: active pay rows in snapshot`)}</title>
      </circle>
    `;
  }).join("");

  const labels = [...labelKeys].map((key) => {
    const boundsForKey = projectedBoundsByKey.get(key);
    const council = councilsByKey.get(key);
    if (!boundsForKey || !council) return "";
    const x = (boundsForKey.minX + boundsForKey.maxX) / 2;
    const y = (boundsForKey.minY + boundsForKey.maxY) / 2;
    const label = council.shortName || council.name || key;
    const labelWidth = Math.max(58, Math.min(142, label.length * 7 + 18));
    const labelX = clamp(x, pad.left + labelWidth / 2, width - pad.right - labelWidth / 2);
    const labelY = clamp(y - 10, pad.top + 16, height - pad.bottom - 18);
    return `
      <g class="cohort-map-label" transform="translate(${labelX.toFixed(1)} ${labelY.toFixed(1)})">
        <rect x="${(-labelWidth / 2).toFixed(1)}" y="-15" width="${labelWidth.toFixed(1)}" height="22" rx="5"></rect>
        <text y="0">${escapeHtml(label)}</text>
      </g>
    `;
  }).join("");

  return `
    <svg class="cohort-map-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Map of Victorian councils highlighting the controlled Small shire cohort">
      <defs>
        <radialGradient id="mapFocusGlow" cx="50%" cy="48%" r="62%">
          <stop offset="0%" stop-color="#8ab4ff" stop-opacity="0.22"></stop>
          <stop offset="72%" stop-color="#8ab4ff" stop-opacity="0.04"></stop>
          <stop offset="100%" stop-color="#8ab4ff" stop-opacity="0"></stop>
        </radialGradient>
      </defs>
      <rect class="cohort-map-plane" x="0" y="0" width="${width}" height="${height}"></rect>
      <rect class="cohort-map-glow" x="0" y="0" width="${width}" height="${height}"></rect>
      <g class="cohort-map-boundaries">
        ${boundaryPaths}
      </g>
      <g class="cohort-map-markers">
        ${markers}
      </g>
      <g class="cohort-map-labels">
        ${labels}
      </g>
    </svg>
  `;
}

export async function hydrateCohortMap(cohort) {
  const target = document.getElementById("cohort-map-root");
  const url = cohort.map?.boundaryGeojsonUrl;
  if (!target || !url) return;

  try {
    const response = await fetch(url, { headers: { Accept: "application/geo+json, application/json" } });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    const geojson = await response.json();
    target.innerHTML = renderCohortBoundaryMap(cohort, geojson);
  } catch (error) {
    target.innerHTML = `
      <div class="cohort-map-error">
        <strong>Boundary map unavailable.</strong>
        <span>${escapeHtml(error.message || String(error))}</span>
      </div>
    `;
  }
}

export function renderClassificationLadder(context) {
  return `
    <div class="classification-ladder">
      ${(context.bands || []).map((item) => `
        <article class="classification-rung${item.band >= 5 && item.band <= 6 ? " is-pressure" : ""}">
          <span>Band ${escapeHtml(item.band)}</span>
          <strong>${escapeHtml(item.workforceSignal)}</strong>
        </article>
      `).join("")}
    </div>
  `;
}

export function renderEntitlementMatrix(entitlements) {
  const columns = entitlements.columns || [];
  const rows = entitlements.rows || [];
  return `
    <div class="entitlement-matrix" role="table" aria-label="${escapeHtml(entitlements.question)}">
      <div class="entitlement-row entitlement-head" role="row">
        <div role="columnheader">Position</div>
        ${columns.map((column) => `<div role="columnheader">${escapeHtml(column)}</div>`).join("")}
      </div>
      ${rows.map((row) => `
        <div class="entitlement-row" role="row">
          <div class="entitlement-segment" role="rowheader">${escapeHtml(row.segment)}</div>
          ${columns.map((column) => {
            const cell = row.scores?.[column] || {};
            return `
              <div class="entitlement-cell" role="cell" data-rating="${escapeHtml(cell.rating || "unknown")}">
                <strong>${escapeHtml(cell.label || "Not assessed")}</strong>
                <span>${escapeHtml(cell.note || "")}</span>
              </div>
            `;
          }).join("")}
        </div>
      `).join("")}
    </div>
  `;
}
