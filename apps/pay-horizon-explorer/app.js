import {
  comparatorTooltip,
  formatCurrency,
  selectedPoints,
  titleIsSafe,
} from "./pay-horizon-engine.js?v=governed-midpoint-v1";

const API_OPTIONS = "/api/analysis/pay-service-horizon-curve/options";
const API_ROWS = "/api/analysis/pay-service-horizon-curve";
const MIDPOINT_WINDOW_ID = "range_midpoint_only";

const BASIS_CURRENT = "selected_period";
const BASIS_FOUR_PERIOD_AVERAGE = "four_period_average";
const BASIS_DATE_SMOOTHED = "date_smoothed";
const RANGE_NONE = "none";
const RANGE_IQR = "iqr";
const RANGE_STD_DEV = "standard_deviation";

const RUNTIME_COHORT_IDS = new Set([
  "local_5",
  "local_12",
  "lgv_category",
  "regional_victoria",
  "lgprf_group",
  "seifa_peer",
]);

const state = {
  options: null,
  row: null,
  sourceRows: [],
  curveRows: [],
  comparatorRows: [],
  curveStats: null,
  comparatorStats: null,
  cohortAvailability: null,
  selectedCouncilId: "",
  band: "",
  cohortId: "",
  comparatorCohortId: "",
  effectiveFrom: "",
  basisMode: BASIS_CURRENT,
  rangeMode: RANGE_IQR,
  loading: false,
  message: "Initialising midpoint distribution.",
  messageTone: "",
  loadSeq: 0,
};

const root = document.getElementById("pay-horizon-root");
const manifestRoot = document.getElementById("manifest-root");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function safeNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function mean(values) {
  const clean = values.map(Number).filter(Number.isFinite);
  if (!clean.length) return null;
  return clean.reduce((sum, value) => sum + value, 0) / clean.length;
}

function formatCount(value, fallback = "0") {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat("en-AU").format(number) : fallback;
}

function displayCurrencyDelta(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not available";
  return `${number > 0 ? "+" : ""}${formatCurrency(number)}`;
}

function option(label, value, selectedValue) {
  return `<option value="${escapeHtml(value)}"${String(value) === String(selectedValue) ? " selected" : ""}>${escapeHtml(label)}</option>`;
}

function fetchJson(url) {
  return fetch(url, { headers: { Accept: "application/json" } }).then((response) => {
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  });
}

function selectedPoint(row = state.row) {
  return selectedPoints(row)[0] || null;
}

function selectedCouncilName(row = state.row) {
  return row?.selected_council_name
    || state.options?.councils?.find((item) => item.selected_council_id === state.selectedCouncilId)?.selected_council_name
    || state.selectedCouncilId
    || "Selected council";
}

function councilOptionLabel(item) {
  const name = item.selected_council_name || item.selected_council_id;
  return item.has_pay_horizon_data === false ? `${name} (blocked: no pay-horizon data)` : name;
}

function displayCodeLabel(value) {
  return String(value || "")
    .replaceAll("__", " ")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normaliseReferenceKey(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/&/g, " AND ")
    .replace(/[^A-Z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function referenceRows() {
  return state.options?.council_reference || [];
}

function referenceLookup() {
  const lookup = new Map();
  for (const row of referenceRows()) {
    [
      row.council_key,
      row.spatial_key,
      row.map_join_key,
      row.short_name,
      row.council_name,
    ].forEach((value) => {
      const key = normaliseReferenceKey(value);
      if (key && !lookup.has(key)) lookup.set(key, row);
    });
  }
  return lookup;
}

function referenceForCouncilId(councilId, lookup = referenceLookup()) {
  return lookup.get(normaliseReferenceKey(councilId)) || null;
}

function referenceForRow(row, lookup = referenceLookup()) {
  return referenceForCouncilId(rowCouncilId(row), lookup) || lookup.get(normaliseReferenceKey(row?.selected_council_name)) || null;
}

function selectedReferenceRow(lookup = referenceLookup()) {
  return referenceForCouncilId(state.selectedCouncilId, lookup)
    || lookup.get(normaliseReferenceKey(selectedCouncilName()))
    || null;
}

function numericReferenceValue(row, key) {
  const value = Number(row?.[key]);
  return Number.isFinite(value) ? value : null;
}

function distanceKm(left, right) {
  const lat1 = numericReferenceValue(left, "office_lat");
  const lon1 = numericReferenceValue(left, "office_lon");
  const lat2 = numericReferenceValue(right, "office_lat");
  const lon2 = numericReferenceValue(right, "office_lon");
  if ([lat1, lon1, lat2, lon2].some((value) => value === null)) return Number.POSITIVE_INFINITY;
  const toRad = (value) => (value * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * (Math.sin(dLon / 2) ** 2);
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function referenceSeifaScore(row) {
  return numericReferenceValue(row, "vgccc_seifa_dis_score")
    ?? numericReferenceValue(row, "lgprf_relative_socioeconomic_disadvantage");
}

function seifaPeerBand(row) {
  const score = referenceSeifaScore(row);
  if (score === null) return null;
  const scores = referenceRows()
    .map(referenceSeifaScore)
    .filter((value) => value !== null)
    .sort((a, b) => a - b);
  if (!scores.length) return null;
  const index = scores.filter((value) => value <= score).length - 1;
  const quintile = Math.max(1, Math.min(5, Math.floor((index / Math.max(1, scores.length)) * 5) + 1));
  const labels = [
    "SEIFA Q1 most disadvantaged",
    "SEIFA Q2 lower",
    "SEIFA Q3 middle",
    "SEIFA Q4 higher",
    "SEIFA Q5 least disadvantaged",
  ];
  return { key: `seifa_q${quintile}`, label: labels[quintile - 1] };
}

function isRegionalVictoriaCouncil(row) {
  const category = String(row?.council_category || "").toLowerCase();
  if (category.includes("metropolitan") || category.includes("interface")) return false;
  return Boolean(
    row?.vif_regional_partnership
    || String(row?.vgccc_region || "").toLowerCase() === "country"
    || category.includes("regional")
    || category.includes("shire")
  );
}

function baseObservationRows(rows) {
  return rows.filter((row) => row?.selected_council_included_in_curve_sample !== false);
}

function rowsMatchingReference(rows, matcher, { excludeSelected = true } = {}) {
  const lookup = referenceLookup();
  const selectedId = String(state.selectedCouncilId || "").toLowerCase();
  return baseObservationRows(rows).filter((row) => {
    if (excludeSelected && rowCouncilId(row).toLowerCase() === selectedId) return false;
    const ref = referenceForRow(row, lookup);
    return Boolean(ref && matcher(ref, row));
  });
}

function localRowsByDistance(rows, count) {
  const lookup = referenceLookup();
  const selectedRef = selectedReferenceRow(lookup);
  if (!selectedRef) return [];
  const selectedId = String(state.selectedCouncilId || "").toLowerCase();
  return baseObservationRows(rows)
    .map((row) => ({ row, ref: referenceForRow(row, lookup) }))
    .filter((item) => item.ref && rowCouncilId(item.row).toLowerCase() !== selectedId)
    .map((item) => ({ row: item.row, distance: distanceKm(selectedRef, item.ref) }))
    .filter((item) => Number.isFinite(item.distance))
    .sort((a, b) => a.distance - b.distance || distributionRowCouncilLabel(a.row).localeCompare(distributionRowCouncilLabel(b.row)))
    .slice(0, count)
    .map((item) => item.row);
}

function runtimeCohortDefinition(cohortId, rows) {
  const lookup = referenceLookup();
  const selectedRef = selectedReferenceRow(lookup);
  const selectedCategory = selectedRef?.council_category || "";
  const selectedLgprfGroup = selectedRef?.lgprf_group || "";
  const selectedSeifaBand = seifaPeerBand(selectedRef);
  const definitions = {
    local_5: {
      cohort_id: "local_5",
      cohort_name: "Local 5 nearest councils",
      cohort_note: "nearest by council office reference point",
      rows: localRowsByDistance(rows, 5),
    },
    local_12: {
      cohort_id: "local_12",
      cohort_name: "Local 12 nearest councils",
      cohort_note: "extended nearest-council lens",
      rows: localRowsByDistance(rows, 12),
    },
    lgv_category: {
      cohort_id: "lgv_category",
      cohort_name: selectedCategory ? `LGV ${selectedCategory} councils` : "LGV category peers",
      cohort_note: "same Local Government Victoria category",
      rows: selectedCategory ? rowsMatchingReference(rows, (ref) => ref.council_category === selectedCategory) : [],
    },
    regional_victoria: {
      cohort_id: "regional_victoria",
      cohort_name: "Regional Victoria councils",
      cohort_note: "regional and rural Victorian councils",
      rows: rowsMatchingReference(rows, (ref) => isRegionalVictoriaCouncil(ref)),
    },
    lgprf_group: {
      cohort_id: "lgprf_group",
      cohort_name: selectedLgprfGroup ? `LGPRF ${selectedLgprfGroup} councils` : "LGPRF group peers",
      cohort_note: "same LGPRF group",
      rows: selectedLgprfGroup ? rowsMatchingReference(rows, (ref) => ref.lgprf_group === selectedLgprfGroup) : [],
    },
    seifa_peer: {
      cohort_id: "seifa_peer",
      cohort_name: selectedSeifaBand?.label || "SEIFA peer band",
      cohort_note: "same SEIFA disadvantage quintile",
      rows: selectedSeifaBand
        ? rowsMatchingReference(rows, (ref) => seifaPeerBand(ref)?.key === selectedSeifaBand.key)
        : [],
    },
  };
  return definitions[cohortId] || null;
}

function runtimeCohortOptions(rows) {
  return [...RUNTIME_COHORT_IDS]
    .map((cohortId) => runtimeCohortDefinition(cohortId, rows))
    .filter((definition) => definition && definition.rows.length)
    .map((definition) => ({
      cohort_id: definition.cohort_id,
      cohort_name: definition.cohort_name,
      cohort_note: definition.cohort_note,
      cohort_council_count: new Set(definition.rows.map(rowCouncilId).filter(Boolean)).size,
      runtime_derived: true,
    }));
}

function friendlyCohortName(item) {
  const id = String(item?.cohort_id || "");
  const rawName = item?.cohort_name || id;
  if (id === "all_governed") return "Statewide";
  if (id === "benchmark_lane__standard_band_core") return "Standard band core";
  if (id === "vgccc_region__country") return "Country councils";
  if (id === "vgccc_region__metro") return "Metro councils";
  if (id.startsWith("council_type__")) return `${displayCodeLabel(id.slice("council_type__".length))} councils`;
  if (id.startsWith("council_category__")) return `LGV ${displayCodeLabel(id.slice("council_category__".length))} councils`;
  if (id.startsWith("lgprf_group__")) return `LGPRF ${displayCodeLabel(id.slice("lgprf_group__".length))} councils`;
  if (id.startsWith("vif_regional_partnership__")) return `${displayCodeLabel(id.slice("vif_regional_partnership__".length))} partnership`;
  if (id.startsWith("vif_metropolitan_region__")) return `${displayCodeLabel(id.slice("vif_metropolitan_region__".length))} metro region`;
  return rawName;
}

function friendlyCohort(item) {
  return { ...item, cohort_name: friendlyCohortName(item) };
}

function mergeCohortOptions(options) {
  const byId = new Map();
  for (const item of options.filter(Boolean).map(friendlyCohort)) {
    const id = item.cohort_id;
    if (!id) continue;
    const previous = byId.get(id);
    if (!previous || Number(item.cohort_council_count || 0) > Number(previous.cohort_council_count || 0)) {
      byId.set(id, item);
    }
  }
  return [...byId.values()].sort((a, b) => String(a.cohort_name).localeCompare(String(b.cohort_name)));
}

function cohortName(row = state.row) {
  return row?.cohort_name
    || state.options?.cohorts?.find((item) => item.cohort_id === state.cohortId)?.cohort_name
    || state.cohortId
    || "Selected cohort";
}

function cohortNameById(cohortId) {
  const item = state.cohortAvailability?.find((cohort) => cohort.cohort_id === cohortId)
    || state.options?.cohorts?.find((cohort) => cohort.cohort_id === cohortId)
    || (cohortId ? { cohort_id: cohortId, cohort_name: cohortId } : null);
  return item ? friendlyCohortName(item) : "Selected cohort";
}

function curveCohortName(row = state.row) {
  return row?.cohort_id === state.cohortId ? row?.cohort_name || cohortNameById(state.cohortId) : cohortNameById(state.cohortId);
}

function comparatorCohortName() {
  return cohortNameById(state.comparatorCohortId);
}

function cohortOptionLabel(item) {
  const name = item.cohort_name || item.cohort_id;
  return item.cohort_council_count ? `${name} (n=${item.cohort_council_count})` : name;
}

function visibleCohorts() {
  const cohorts = state.cohortAvailability?.length ? state.cohortAvailability : (state.options?.cohorts || []);
  if (cohorts.some((item) => item.cohort_id === state.cohortId)) return cohorts;
  const selected = state.options?.cohorts?.find((item) => item.cohort_id === state.cohortId);
  return selected ? [selected, ...cohorts] : cohorts;
}

function visibleComparatorCohorts() {
  const cohorts = state.cohortAvailability?.length ? state.cohortAvailability : (state.options?.cohorts || []);
  if (cohorts.some((item) => item.cohort_id === state.comparatorCohortId)) return cohorts;
  const selected = state.options?.cohorts?.find((item) => item.cohort_id === state.comparatorCohortId);
  return selected ? [selected, ...cohorts] : cohorts;
}

function basisLabel(mode = state.basisMode) {
  if (mode === BASIS_FOUR_PERIOD_AVERAGE) return "4-period average";
  if (mode === BASIS_DATE_SMOOTHED) return "Date-smoothed";
  return "Selected period";
}

function rangeLabel() {
  if (state.basisMode === BASIS_FOUR_PERIOD_AVERAGE) return `Trailing four quarters to ${state.effectiveFrom}`;
  if (state.basisMode === BASIS_DATE_SMOOTHED) return `${state.effectiveFrom} trajectory point`;
  return state.effectiveFrom || "No quarter selected";
}

function rowStats(row) {
  if (!row) return null;
  const values = [row.curve_min, row.curve_p25, row.curve_median, row.curve_p75, row.curve_max]
    .map(Number)
    .filter(Number.isFinite);
  if (!values.length) return null;
  const avg = mean(values);
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / values.length;
  return {
    count: Number(row.curve_sample_count) || values.length,
    councilCount: Number(row.curve_council_count) || 0,
    min: safeNumber(row.curve_min),
    p25: safeNumber(row.curve_p25),
    median: safeNumber(row.curve_median),
    p75: safeNumber(row.curve_p75),
    max: safeNumber(row.curve_max),
    mean: safeNumber(row.curve_median) ?? avg,
    stdDev: Math.sqrt(variance),
  };
}

function rowValue(row) {
  return safeNumber(selectedPoint(row)?.weekly_rate ?? row?.selected_council_min);
}

function rowCouncilId(row) {
  return String(row?.selected_council_id || "");
}

function rowRangeKey(row) {
  return [
    rowCouncilId(row),
    row?.selected_range_group_id || "",
    row?.selected_classification_family || "",
  ].join("::");
}

function statsFromRows(rows) {
  const includedRows = rows.filter((row) => row?.selected_council_included_in_curve_sample !== false);
  const values = includedRows.map(rowValue).filter((value) => value !== null).sort((a, b) => a - b);
  if (!values.length) return null;
  const avg = mean(values);
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / values.length;
  return {
    count: values.length,
    councilCount: new Set(includedRows.map(rowCouncilId).filter(Boolean)).size,
    min: values[0],
    p25: percentile(values, 0.25),
    median: percentile(values, 0.5),
    p75: percentile(values, 0.75),
    max: values[values.length - 1],
    mean: avg,
    stdDev: Math.sqrt(variance),
    values,
  };
}

function percentile(sortedValues, p) {
  if (!sortedValues.length) return null;
  if (sortedValues.length === 1) return sortedValues[0];
  const index = (sortedValues.length - 1) * p;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sortedValues[lower];
  return sortedValues[lower] + ((sortedValues[upper] - sortedValues[lower]) * (index - lower));
}

function materializeRowsForBasis(rows) {
  if (state.basisMode !== BASIS_FOUR_PERIOD_AVERAGE) return rows;
  const byCouncil = new Map();
  for (const row of rows) {
    const value = rowValue(row);
    if (value === null) continue;
    const key = rowCouncilId(row) || rowRangeKey(row);
    const existing = byCouncil.get(key) || {
      latest: row,
      values: [],
      quarterStarts: [],
      sourceRangeKeys: new Set(),
    };
    existing.values.push(value);
    existing.quarterStarts.push(row.quarter_start || row.effective_from);
    existing.sourceRangeKeys.add(rowRangeKey(row));
    if (compareIso(row.effective_from, existing.latest.effective_from) > 0) existing.latest = row;
    byCouncil.set(key, existing);
  }
  return [...byCouncil.values()].map((item) => {
    const averagedValue = mean(item.values);
    const point = {
      ...(selectedPoint(item.latest) || {}),
      weekly_rate: averagedValue,
      metric_caveat: "Displayed marker is one council-level average from midpoint rows across the trailing four selected quarters.",
    };
    return {
      ...item.latest,
      effective_from: state.effectiveFrom,
      quarter_start: state.effectiveFrom,
      selected_council_min: averagedValue,
      selected_council_max: averagedValue,
      selected_council_points_json: JSON.stringify([point]),
      chart_quarter_count: item.values.length,
      chart_quarter_starts: item.quarterStarts,
      chart_source_range_count: item.sourceRangeKeys.size,
    };
  });
}

function quarterNumberFromIso(date) {
  const month = Number(String(date || "").slice(5, 7));
  if (!Number.isFinite(month) || month < 1) return 1;
  return Math.floor((month - 1) / 3) + 1;
}

function quarterStartFromYearQuarter(year, quarter) {
  const month = ((Number(quarter) - 1) * 3) + 1;
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

function availableYears() {
  return [...new Set(((state.options?.quarter_periods || state.options?.effective_periods) || []).map((date) => String(date).slice(0, 4)).filter(Boolean))];
}

function availableQuartersForYear(year) {
  return [...new Set(((state.options?.quarter_periods || state.options?.effective_periods) || [])
    .filter((date) => String(date).startsWith(`${year}-`))
    .map(quarterNumberFromIso))]
    .sort((a, b) => a - b);
}

function compareIso(a, b) {
  return String(a || "").localeCompare(String(b || ""));
}

function latestRowsForBasis(rows) {
  const sorted = [...rows].filter((row) => row.effective_from).sort((a, b) => compareIso(a.effective_from, b.effective_from));
  if (state.basisMode === BASIS_CURRENT) return sorted.filter((row) => row.effective_from === state.effectiveFrom);
  const beforeOrEqual = sorted.filter((row) => compareIso(row.effective_from, state.effectiveFrom) <= 0);
  if (state.basisMode === BASIS_FOUR_PERIOD_AVERAGE) return beforeOrEqual.slice(-4);
  return sorted;
}

function combineAverageRows(rows) {
  if (!rows.length) return null;
  if (rows.length === 1) return rows[0];
  const latest = rows[rows.length - 1];
  const selectedValues = rows
    .map((row) => safeNumber(selectedPoint(row)?.weekly_rate))
    .filter((value) => value !== null);
  const averagedPoint = {
    ...(selectedPoint(latest) || {}),
    weekly_rate: mean(selectedValues),
    metric_caveat: "Displayed selected marker is averaged from materialised midpoint rows.",
  };
  return {
    ...latest,
    curve_sample_count: rows.reduce((sum, row) => sum + (Number(row.curve_sample_count) || 0), 0),
    curve_council_count: Math.max(...rows.map((row) => Number(row.curve_council_count) || 0)),
    curve_min: mean(rows.map((row) => row.curve_min)),
    curve_p25: mean(rows.map((row) => row.curve_p25)),
    curve_median: mean(rows.map((row) => row.curve_median)),
    curve_p75: mean(rows.map((row) => row.curve_p75)),
    curve_max: mean(rows.map((row) => row.curve_max)),
    selected_council_points_json: JSON.stringify([averagedPoint]),
    chart_title: `Band ${latest.standard_band} range midpoint distribution - ${latest.cohort_name} (${basisLabel(BASIS_FOUR_PERIOD_AVERAGE)})`,
  };
}

function dateMs(date) {
  const value = Date.parse(`${date}T00:00:00Z`);
  return Number.isFinite(value) ? value : null;
}

function interpolateValue(a, b, fraction, field) {
  const left = safeNumber(a?.[field]);
  const right = safeNumber(b?.[field]);
  if (left === null && right === null) return null;
  if (left === null) return right;
  if (right === null) return left;
  return left + ((right - left) * fraction);
}

function dateSmoothedRow(rows) {
  const sorted = rows.filter((row) => row.effective_from).sort((a, b) => compareIso(a.effective_from, b.effective_from));
  const exact = sorted.find((row) => row.effective_from === state.effectiveFrom);
  if (exact) return exact;
  const target = dateMs(state.effectiveFrom);
  if (target === null || !sorted.length) return null;
  const before = [...sorted].reverse().find((row) => dateMs(row.effective_from) <= target);
  const after = sorted.find((row) => dateMs(row.effective_from) >= target);
  const fromRow = before || after;
  const toRow = after || before;
  if (!fromRow || !toRow) return null;
  const fromMs = dateMs(fromRow.effective_from);
  const toMs = dateMs(toRow.effective_from);
  const fraction = fromMs === toMs ? 0 : Math.max(0, Math.min(1, (target - fromMs) / (toMs - fromMs)));
  const fromPoint = selectedPoint(fromRow);
  const toPoint = selectedPoint(toRow);
  const weeklyRate = interpolateValue({ value: fromPoint?.weekly_rate }, { value: toPoint?.weekly_rate }, fraction, "value");
  const smoothedPoint = {
    ...(toPoint || fromPoint || {}),
    weekly_rate: weeklyRate,
    metric_caveat: `Displayed selected marker is interpolated from materialised midpoint rows between ${fromRow.effective_from} and ${toRow.effective_from}.`,
  };
  return {
    ...toRow,
    effective_from: state.effectiveFrom,
    curve_min: interpolateValue(fromRow, toRow, fraction, "curve_min"),
    curve_p25: interpolateValue(fromRow, toRow, fraction, "curve_p25"),
    curve_median: interpolateValue(fromRow, toRow, fraction, "curve_median"),
    curve_p75: interpolateValue(fromRow, toRow, fraction, "curve_p75"),
    curve_max: interpolateValue(fromRow, toRow, fraction, "curve_max"),
    selected_council_points_json: JSON.stringify([smoothedPoint]),
    chart_title: `Band ${toRow.standard_band} range midpoint distribution - ${toRow.cohort_name} (${basisLabel(BASIS_DATE_SMOOTHED)})`,
  };
}

function materializeBasisRow(rows) {
  const basisRows = latestRowsForBasis(rows);
  return state.basisMode === BASIS_FOUR_PERIOD_AVERAGE
    ? combineAverageRows(basisRows)
    : state.basisMode === BASIS_DATE_SMOOTHED
      ? dateSmoothedRow(rows)
      : basisRows[0] || null;
}

function buildQuery({
  quarterStart = state.effectiveFrom,
  cohortId = state.cohortId,
  selectedCouncilId,
  limit = 5000,
} = {}) {
  const params = new URLSearchParams({
    standard_band: state.band,
    cohort_id: cohortId,
    service_horizon_window_id: MIDPOINT_WINDOW_ID,
    limit: String(limit),
  });
  if (selectedCouncilId) params.set("selected_council_id", selectedCouncilId);
  if (quarterStart) params.set("quarter_start", quarterStart);
  return params;
}

async function loadAvailableCohortsForCurrentPeriod() {
  if (!state.band || !state.effectiveFrom) return state.options?.cohorts || [];
  const params = new URLSearchParams({
    standard_band: state.band,
    quarter_start: state.effectiveFrom,
    service_horizon_window_id: MIDPOINT_WINDOW_ID,
    limit: "5000",
  });
  const allGovernedParams = new URLSearchParams(params);
  allGovernedParams.set("cohort_id", "all_governed");
  const [payload, allGovernedPayload] = await Promise.all([
    fetchJson(`${API_ROWS}?${params.toString()}`),
    fetchJson(`${API_ROWS}?${allGovernedParams.toString()}`),
  ]);
  const byCohort = new Map();
  for (const row of payload.rows || []) {
    const cohortId = row.cohort_id;
    const councilCount = Number(row.curve_council_count) || 0;
    if (!cohortId || councilCount < 16) continue;
    const previous = byCohort.get(cohortId);
    if (!previous || councilCount > previous.cohort_council_count) {
      byCohort.set(cohortId, {
        cohort_id: cohortId,
        cohort_name: row.cohort_name || cohortId,
        cohort_council_count: councilCount,
      });
    }
  }
  return mergeCohortOptions([
    ...byCohort.values(),
    ...runtimeCohortOptions(allGovernedPayload.rows || []),
  ]);
}

function quarterStartsForBasis() {
  const periods = (state.options?.quarter_periods || state.options?.effective_periods || [])
    .filter((date) => compareIso(date, state.effectiveFrom) <= 0)
    .sort(compareIso);
  if (state.basisMode === BASIS_FOUR_PERIOD_AVERAGE) return periods.slice(-4);
  return [state.effectiveFrom].filter(Boolean);
}

async function loadRowsForCohort(cohortId, { selectedCouncilId = null } = {}) {
  const quarterStarts = quarterStartsForBasis();
  const sourceCohortId = RUNTIME_COHORT_IDS.has(cohortId) ? "all_governed" : cohortId;
  const payloads = await Promise.all(
    quarterStarts.map((quarterStart) => fetchJson(`${API_ROWS}?${buildQuery({
      quarterStart,
      cohortId: sourceCohortId,
      selectedCouncilId,
      limit: 5000,
    }).toString()}`)),
  );
  const materializedRows = materializeRowsForBasis(payloads.flatMap((payload) => payload.rows || []));
  if (!RUNTIME_COHORT_IDS.has(cohortId)) return materializedRows.map((row) => ({ ...row, cohort_name: cohortNameById(row.cohort_id) }));
  const definition = runtimeCohortDefinition(cohortId, materializedRows);
  if (!definition) return [];
  const councilCount = new Set(definition.rows.map(rowCouncilId).filter(Boolean)).size;
  return definition.rows.map((row) => ({
    ...row,
    cohort_id: definition.cohort_id,
    cohort_name: definition.cohort_name,
    curve_council_count: councilCount,
    curve_sample_count: definition.rows.length,
    selected_council_included_in_curve_sample: true,
    metric_caveats: [
      ...(Array.isArray(row.metric_caveats) ? row.metric_caveats : []),
      "Runtime V1-style cohort filter over midpoint observations.",
    ],
  }));
}

function updateMessage(message, tone = "") {
  state.message = message;
  state.messageTone = tone;
}

async function loadRow() {
  const loadSeq = ++state.loadSeq;
  state.loading = true;
  render();
  try {
    const previousCohortId = state.cohortId;
    const cohortAvailability = await loadAvailableCohortsForCurrentPeriod();
    if (loadSeq !== state.loadSeq) return;
    state.cohortAvailability = cohortAvailability;
    if (state.cohortAvailability.length && !state.cohortAvailability.some((item) => item.cohort_id === state.cohortId)) {
      const allGoverned = state.cohortAvailability.find((item) => item.cohort_id === "all_governed");
      state.cohortId = (allGoverned || state.cohortAvailability[0]).cohort_id;
    }
    if (!state.comparatorCohortId) state.comparatorCohortId = state.cohortId;
    if (state.cohortAvailability.length && !state.cohortAvailability.some((item) => item.cohort_id === state.comparatorCohortId)) {
      state.comparatorCohortId = state.cohortId;
    }
    const [curveRows, comparatorRows, selectedRows] = await Promise.all([
      loadRowsForCohort(state.cohortId),
      loadRowsForCohort(state.comparatorCohortId),
      loadRowsForCohort("all_governed", { selectedCouncilId: state.selectedCouncilId }),
    ]);
    if (loadSeq !== state.loadSeq) return;
    state.curveRows = curveRows;
    state.comparatorRows = comparatorRows;
    state.sourceRows = selectedRows.length ? selectedRows : curveRows;
    state.curveStats = statsFromRows(curveRows);
    state.comparatorStats = statsFromRows(comparatorRows);
    state.row = selectedRows[0]
      || curveRows.find((row) => rowCouncilId(row).toLowerCase() === String(state.selectedCouncilId).toLowerCase())
      || null;
    const cohortReset = previousCohortId !== state.cohortId;
    updateMessage(
      state.curveStats
        ? `${formatCount(state.curveStats.count)} midpoint row(s) loaded for the curve and ${formatCount(state.comparatorStats?.count)} for the comparator.${cohortReset ? " Cohort reset to the nearest available peer lens." : ""}`
        : "No midpoint row exists for this council/band/cohort/period.",
      state.curveStats ? "ok" : "warn",
    );
  } catch (error) {
    if (loadSeq !== state.loadSeq) return;
    state.row = null;
    state.sourceRows = [];
    state.curveRows = [];
    state.comparatorRows = [];
    state.curveStats = null;
    state.comparatorStats = null;
    updateMessage(`Could not load midpoint distribution: ${error.message || String(error)}`, "error");
  } finally {
    if (loadSeq === state.loadSeq) {
      state.loading = false;
      render();
    }
  }
}

function initialiseDefaults(options) {
  const defaults = options.default_selection || {};
  state.band = defaults.standard_band || (options.bands?.includes("5") ? "5" : options.bands?.[0] || "");
  state.cohortId = defaults.cohort_id || options.cohorts?.[0]?.cohort_id || "all_governed";
  state.comparatorCohortId = state.cohortId;
  state.effectiveFrom = defaults.quarter_start || defaults.effective_from || options.quarter_periods?.[options.quarter_periods.length - 1] || options.effective_periods?.[options.effective_periods.length - 1] || "";
  state.selectedCouncilId = defaults.selected_council_id || options.councils?.find((item) => item.has_pay_horizon_data !== false)?.selected_council_id || options.councils?.[0]?.selected_council_id || "";
}

function setYearQuarter(year, quarter) {
  const next = quarterStartFromYearQuarter(year, quarter);
  const available = state.options?.quarter_periods || state.options?.effective_periods || [];
  state.effectiveFrom = available.includes(next)
    ? next
    : available.find((date) => String(date).startsWith(`${year}-`)) || state.effectiveFrom;
}

function densityY(stats, value) {
  if (!stats || stats.max <= stats.min) return 0.48;
  const spread = Math.max(1, stats.max - stats.min);
  const centre = stats.mean ?? stats.median ?? ((stats.min + stats.max) / 2);
  const z = (Number(value) - centre) / spread;
  return Math.max(0.06, Math.exp(-5 * z * z));
}

function distributionRangeOverlay(stats) {
  if (!stats || state.rangeMode === RANGE_NONE) return null;
  if (state.rangeMode === RANGE_IQR && stats.p25 !== null && stats.p75 !== null) {
    return {
      key: RANGE_IQR,
      min: stats.p25,
      max: stats.p75,
      shortLabel: "IQR",
      title: `Interquartile range: ${formatCurrency(stats.p25)} to ${formatCurrency(stats.p75)}`,
    };
  }
  if (state.rangeMode === RANGE_STD_DEV && stats.mean !== null && stats.stdDev !== null) {
    return {
      key: RANGE_STD_DEV,
      min: stats.mean - stats.stdDev,
      max: stats.mean + stats.stdDev,
      shortLabel: "1 SD",
      title: `One standard deviation around the midpoint median estimate`,
    };
  }
  return null;
}

function markerTooltip(row) {
  const point = selectedPoint(row);
  return [
    selectedCouncilName(row),
    "Metric: range_midpoint_rate",
    `Weekly midpoint: ${formatCurrency(point?.weekly_rate)}`,
    `Cohort: ${cohortName(row)}`,
    `Governance: ${point?.calculation_status || row?.report_ready_status || "unknown"}`,
    point?.metric_caveat ? `Caveat: ${point.metric_caveat}` : null,
  ].filter(Boolean).join("\n");
}

function distributionRowCouncilLabel(row) {
  return row?.selected_council_name || row?.canonical_council_name || row?.selected_council_id || "Council";
}

function comparatorExtremeRows(rows = state.comparatorRows) {
  const sorted = rows
    .filter((row) => row?.selected_council_included_in_curve_sample !== false)
    .map((row) => ({ row, value: rowValue(row) }))
    .filter((item) => Number.isFinite(item.value))
    .sort((a, b) => a.value - b.value);
  if (!sorted.length) return [];
  const lowest = sorted[0];
  const highest = sorted[sorted.length - 1];
  if (lowest.row === highest.row || lowest.value === highest.value) {
    return [{ key: "low-high", label: "Comparator low/high", row: lowest.row, value: lowest.value }];
  }
  return [
    { key: "low", label: "Comparator low", row: lowest.row, value: lowest.value },
    { key: "high", label: "Comparator high", row: highest.row, value: highest.value },
  ];
}

function comparatorObservationRows(rows = state.comparatorRows, extremeRows = []) {
  const selectedId = String(state.selectedCouncilId || "").toLowerCase();
  const extremeKeys = new Set(
    extremeRows.map((item) => `${rowCouncilId(item.row)}::${Number(item.value).toFixed(4)}`),
  );
  return rows
    .filter((row) => row?.selected_council_included_in_curve_sample !== false)
    .map((row) => ({ row, value: rowValue(row), councilId: rowCouncilId(row).toLowerCase() }))
    .filter((item) => Number.isFinite(item.value)
      && item.councilId !== selectedId
      && !extremeKeys.has(`${rowCouncilId(item.row)}::${Number(item.value).toFixed(4)}`))
    .sort((a, b) => a.value - b.value);
}

function estimateSvgLabelWidth(label) {
  return Math.max(72, Math.min(210, String(label || "").length * 5.8));
}

function clampSvgLabelX(preferredX, label, width, pad, anchor = "start") {
  const labelWidth = estimateSvgLabelWidth(label);
  if (anchor === "end") {
    return Math.max(pad.left + labelWidth, Math.min(width - pad.right - 4, preferredX));
  }
  if (anchor === "middle") {
    return Math.max(pad.left + (labelWidth / 2), Math.min(width - pad.right - (labelWidth / 2), preferredX));
  }
  return Math.max(pad.left + 4, Math.min(width - pad.right - labelWidth, preferredX));
}

function svgLabelBox(label, x, y, anchor = "start") {
  const labelWidth = estimateSvgLabelWidth(label);
  const x1 = anchor === "end" ? x - labelWidth : anchor === "middle" ? x - (labelWidth / 2) : x;
  return {
    x1,
    x2: x1 + labelWidth,
    y1: y - 12,
    y2: y + 4,
  };
}

function svgBoxesIntersect(left, right) {
  return left.x1 < right.x2 && left.x2 > right.x1 && left.y1 < right.y2 && left.y2 > right.y1;
}

function chooseSvgLabelY({ candidates, label, x, anchor, placedBoxes, minY, maxY }) {
  for (const candidate of candidates) {
    const y = Math.max(minY, Math.min(maxY, candidate));
    const box = svgLabelBox(label, x, y, anchor);
    if (!placedBoxes.some((placed) => svgBoxesIntersect(box, placed))) return y;
  }
  return Math.max(minY, Math.min(maxY, candidates[0] ?? minY));
}

function renderDistributionSvg(row) {
  const stats = state.curveStats || rowStats(row);
  const comparatorStats = state.comparatorStats;
  const extremes = comparatorExtremeRows();
  const comparatorObservations = comparatorObservationRows(state.comparatorRows, extremes);
  const point = selectedPoint(row);
  const selectedValue = safeNumber(point?.weekly_rate);
  if (!stats) return `<div class="distribution-card-empty"><p>No numeric midpoint values are available.</p></div>`;
  const width = 920;
  const height = 310;
  const pad = { left: 54, right: 26, top: 58, bottom: 42 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const axisY = pad.top + chartH;
  const comparatorValues = [
    comparatorStats?.mean,
    comparatorStats?.min,
    comparatorStats?.max,
    ...extremes.map((item) => item.value),
  ];
  const domainValues = [stats.min, stats.p25, stats.median, stats.p75, stats.max, selectedValue, ...comparatorValues].filter(Number.isFinite);
  const domainMin = Math.min(...domainValues);
  const domainMax = Math.max(...domainValues);
  const spread = Math.max(domainMax - domainMin, 120);
  const xMin = Math.max(0, Math.floor((domainMin - spread * 0.04) / 25) * 25);
  const xMax = Math.ceil((domainMax + spread * 0.04) / 25) * 25;
  const xScale = (value) => pad.left + ((value - xMin) / Math.max(1, xMax - xMin)) * chartW;
  const yScale = (value) => pad.top + chartH - (densityY(stats, value) * chartH);
  const samples = Array.from({ length: 88 }, (_, index) => stats.min + ((stats.max - stats.min) * index / 87));
  const curvePath = stats.max > stats.min
    ? samples.map((value, index) => `${index === 0 ? "M" : "L"} ${xScale(value).toFixed(1)} ${yScale(value).toFixed(1)}`).join(" ")
    : "";
  const rangeOverlay = distributionRangeOverlay(stats);
  const rangeOverlayMarkup = rangeOverlay ? (() => {
    const rawX1 = xScale(rangeOverlay.min);
    const rawX2 = xScale(rangeOverlay.max);
    const boundedX1 = Math.max(pad.left, Math.min(width - pad.right, Math.min(rawX1, rawX2)));
    const boundedX2 = Math.max(pad.left, Math.min(width - pad.right, Math.max(rawX1, rawX2)));
    const overlayWidth = Math.max(6, boundedX2 - boundedX1);
    const labelX = Math.max(pad.left + 34, Math.min(width - pad.right - 34, (boundedX1 + boundedX2) / 2));
    return `
      <g class="distribution-range-overlay distribution-range-${escapeHtml(rangeOverlay.key)}">
        <title>${escapeHtml(rangeOverlay.title)}</title>
        <rect x="${boundedX1.toFixed(1)}" y="${(pad.top + 8).toFixed(1)}" width="${overlayWidth.toFixed(1)}" height="${(chartH - 8).toFixed(1)}"></rect>
        <line x1="${boundedX1.toFixed(1)}" x2="${boundedX1.toFixed(1)}" y1="${(pad.top + 8).toFixed(1)}" y2="${axisY.toFixed(1)}"></line>
        <line x1="${boundedX2.toFixed(1)}" x2="${boundedX2.toFixed(1)}" y1="${(pad.top + 8).toFixed(1)}" y2="${axisY.toFixed(1)}"></line>
        <text x="${labelX.toFixed(1)}" y="${(pad.top + 18).toFixed(1)}">${escapeHtml(rangeOverlay.shortLabel)}</text>
      </g>
    `;
  })() : "";
  const percentileMarkers = [
    ["P0", stats.min, true],
    ["P25", stats.p25, false],
    ["P50", stats.median, false],
    ["P75", stats.p75, false],
    ["P100", stats.max, true],
  ].filter(([, value]) => Number.isFinite(Number(value))).map(([label, value, boundary]) => {
    const x = xScale(value);
    const y = yScale(value);
    return `
      <g class="distribution-percentile-line${boundary ? " distribution-percentile-boundary" : ""}">
        <title>${escapeHtml(`${label}: ${formatCurrency(value)}`)}</title>
        <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y.toFixed(1)}" y2="${axisY.toFixed(1)}"></line>
        <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${boundary ? "4.2" : "3.1"}"></circle>
        <text x="${x.toFixed(1)}" y="${height - 12}">${escapeHtml(label)}</text>
      </g>
    `;
  }).join("");
  const placedLabelBoxes = [];
  const comparatorExtremeLayouts = extremes.map((item) => {
    const x = xScale(item.value);
    const y = yScale(item.value);
    const councilLabel = distributionRowCouncilLabel(item.row);
    const visibleLabel = `${item.key === "high" ? "High" : item.key === "low" ? "Low" : "Low/high"} ${councilLabel}`;
    const anchor = item.key === "high" ? "end" : "start";
    const preferredX = item.key === "high" ? x - 14 : x + 14;
    const labelX = clampSvgLabelX(preferredX, visibleLabel, width, pad, anchor);
    const labelY = Math.max(pad.top + 10, Math.min(axisY - 10, y + 4));
    placedLabelBoxes.push(svgLabelBox(visibleLabel, labelX, labelY, anchor));
    return { ...item, x, y, councilLabel, visibleLabel, anchor, labelX, labelY };
  });
  const comparatorAverageMarker = comparatorStats?.mean !== null && Number.isFinite(comparatorStats?.mean) ? (() => {
    const x = xScale(comparatorStats.mean);
    const y = yScale(comparatorStats.mean);
    const visibleLabel = `${comparatorCohortName()} avg`;
    const anchor = "middle";
    const labelX = clampSvgLabelX(x, visibleLabel, width, pad, anchor);
    const labelY = chooseSvgLabelY({
      candidates: [y + 20, y + 34, y - 20, y - 34],
      label: visibleLabel,
      x: labelX,
      anchor,
      placedBoxes: placedLabelBoxes,
      minY: pad.top + 12,
      maxY: axisY - 12,
    });
    placedLabelBoxes.push(svgLabelBox(visibleLabel, labelX, labelY, anchor));
    const leaderEndY = y < labelY ? labelY - 10 : labelY + 8;
    return `
      <g class="distribution-selected-cohort-average-marker">
        <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y.toFixed(1)}" y2="${leaderEndY.toFixed(1)}"></line>
        <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.4"></circle>
        <text x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="${anchor}">${escapeHtml(visibleLabel)}</text>
        <title>${escapeHtml(`${comparatorCohortName()} average: ${formatCurrency(comparatorStats.mean)} across ${formatCount(comparatorStats.count)} midpoint values`)}</title>
      </g>
    `;
  })() : "";
  const selectedComparatorBridge = Number.isFinite(selectedValue) && Number.isFinite(comparatorStats?.mean) ? (() => {
    const selectedX = xScale(selectedValue);
    const selectedY = yScale(selectedValue);
    const comparatorX = xScale(comparatorStats.mean);
    const comparatorY = yScale(comparatorStats.mean);
    const bridgeY = pad.top - 22;
    const bridgeStartX = Math.min(selectedX, comparatorX);
    const bridgeEndX = Math.max(selectedX, comparatorX);
    const bridgeWidth = bridgeEndX - bridgeStartX;
    const dotCount = Math.max(2, Math.min(22, Math.round(bridgeWidth / 16) + 1));
    const bridgeDots = Array.from({ length: dotCount }, (_, index) => {
      const dotX = dotCount === 1 ? bridgeStartX : bridgeStartX + ((bridgeWidth * index) / Math.max(1, dotCount - 1));
      const endpointClass = index === 0 || index === dotCount - 1 ? " distribution-selected-comparator-bridge-endpoint" : "";
      return `<circle class="distribution-selected-comparator-bridge-dot${endpointClass}" cx="${dotX.toFixed(1)}" cy="${bridgeY.toFixed(1)}" r="${endpointClass ? "2.5" : "1.8"}"></circle>`;
    }).join("");
    return `
      <g class="distribution-selected-comparator-bridge" aria-hidden="true">
        <line x1="${selectedX.toFixed(1)}" x2="${selectedX.toFixed(1)}" y1="${selectedY.toFixed(1)}" y2="${bridgeY.toFixed(1)}"></line>
        <line x1="${comparatorX.toFixed(1)}" x2="${comparatorX.toFixed(1)}" y1="${comparatorY.toFixed(1)}" y2="${bridgeY.toFixed(1)}"></line>
        ${bridgeDots}
        <title>${escapeHtml(`${selectedCouncilName(row)} to ${comparatorCohortName()} average bridge: ${formatCurrency(selectedValue)} vs ${formatCurrency(comparatorStats.mean)}`)}</title>
      </g>
    `;
  })() : "";
  const curveWatermark = `
    <g class="distribution-curve-watermark" aria-hidden="true">
      <text x="${(pad.left + (chartW / 2)).toFixed(1)}" y="${(pad.top + (chartH * 0.46)).toFixed(1)}">${escapeHtml(curveCohortName(row))}</text>
    </g>
  `;
  const comparatorExtremeMarkers = comparatorExtremeLayouts.map((item) => {
    const leaderEndX = item.anchor === "end" ? item.labelX + 4 : item.labelX - 4;
    return `
      <g class="distribution-comparator-extreme-marker distribution-comparator-extreme-${escapeHtml(item.key)}">
        <line x1="${item.x.toFixed(1)}" x2="${leaderEndX.toFixed(1)}" y1="${item.y.toFixed(1)}" y2="${item.y.toFixed(1)}"></line>
        <circle cx="${item.x.toFixed(1)}" cy="${item.y.toFixed(1)}" r="4.1"></circle>
        <text x="${item.labelX.toFixed(1)}" y="${item.labelY.toFixed(1)}" text-anchor="${item.anchor}">${escapeHtml(item.visibleLabel)}</text>
        <title>${escapeHtml(`${item.label}: ${item.councilLabel} ${formatCurrency(item.value)} in ${comparatorCohortName()}`)}</title>
      </g>
    `;
  }).join("");
  const comparatorObservationMarkers = comparatorObservations.map((item) => {
    const x = xScale(item.value);
    const y = yScale(item.value);
    const councilLabel = distributionRowCouncilLabel(item.row);
    return `
      <circle
        class="distribution-comparator-observation-marker"
        cx="${x.toFixed(1)}"
        cy="${y.toFixed(1)}"
        r="3"
      >
        <title>${escapeHtml(`${comparatorCohortName()} member: ${councilLabel} ${formatCurrency(item.value)}`)}</title>
      </circle>
    `;
  }).join("");
  const selectedMarker = Number.isFinite(selectedValue) ? (() => {
    const x = xScale(selectedValue);
    const y = yScale(selectedValue);
    const label = selectedCouncilName(row);
    const anchor = "middle";
    const labelX = clampSvgLabelX(x, label, width, pad, anchor);
    const labelY = chooseSvgLabelY({
      candidates: [y - 20, y - 34, y + 20, y + 34],
      label,
      x: labelX,
      anchor,
      placedBoxes: placedLabelBoxes,
      minY: pad.top + 12,
      maxY: axisY - 12,
    });
    const leaderEndY = y < labelY ? labelY - 10 : labelY + 8;
    return `
      <g class="distribution-current-marker">
        <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${y.toFixed(1)}" y2="${leaderEndY.toFixed(1)}"></line>
        <circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="5.2"></circle>
        <text x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="${anchor}">${escapeHtml(label)}</text>
        <title>${escapeHtml(markerTooltip(row))}</title>
      </g>
    `;
  })() : "";
  const ticks = [xMin, stats.p25, stats.median, stats.p75, xMax]
    .filter((value, index, arr) => Number.isFinite(value) && arr.findIndex((other) => Math.round(other) === Math.round(value)) === index)
    .map((value) => `
      <g class="distribution-tick">
        <line x1="${xScale(value).toFixed(1)}" x2="${xScale(value).toFixed(1)}" y1="${axisY.toFixed(1)}" y2="${(axisY + 6).toFixed(1)}"></line>
        <text x="${xScale(value).toFixed(1)}" y="${height - 12}">${escapeHtml(formatCurrency(value).replace("A$", "$"))}</text>
      </g>
    `).join("");
  return `
    <svg id="pay-horizon-svg" class="distribution-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(chartTitle(row))}">
      <line class="distribution-axis" x1="${pad.left}" x2="${width - pad.right}" y1="${axisY.toFixed(1)}" y2="${axisY.toFixed(1)}"></line>
      ${curveWatermark}
      ${rangeOverlayMarkup}
      <g class="distribution-percentile-lines">${percentileMarkers}</g>
      ${curvePath ? `<path class="distribution-curve" d="${curvePath}"><title>${escapeHtml(row ? comparatorTooltip(row) : `${curveCohortName(row)} midpoint curve`)}</title></path>` : ""}
      <g class="distribution-comparator-observation-markers">${comparatorObservationMarkers}</g>
      ${selectedComparatorBridge}
      ${comparatorExtremeMarkers}
      ${comparatorAverageMarker}
      ${selectedMarker}
      ${ticks}
    </svg>
  `;
}

function renderInlineMeta(items) {
  return `<div class="distribution-card-meta workbench-inline-meta">${items.filter(Boolean).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`;
}

function renderSelectorControls() {
  const years = availableYears();
  const selectedYear = String(state.effectiveFrom || "").slice(0, 4) || years[0] || "";
  const selectedQuarter = quarterNumberFromIso(state.effectiveFrom);
  const quarters = availableQuartersForYear(selectedYear);
  return `
    <div class="distribution-picker-grid pay-horizon-picker-grid" aria-label="Midpoint chart controls">
      <label>
        <span>Council</span>
        <select data-v1-control="selectedCouncilId">
          ${(state.options?.councils || []).map((item) => option(councilOptionLabel(item), item.selected_council_id, state.selectedCouncilId)).join("")}
        </select>
      </label>
      <label>
        <span>Year</span>
        <select data-v1-year>
          ${years.map((year) => option(year, year, selectedYear)).join("")}
        </select>
      </label>
      <label>
        <span>Quarter</span>
        <select data-v1-quarter>
          ${(quarters.length ? quarters : [1, 2, 3, 4]).map((quarter) => option(`Q${quarter}`, quarter, selectedQuarter)).join("")}
        </select>
      </label>
      <label>
        <span>Band</span>
        <select data-v1-control="band">
          ${(state.options?.bands || []).map((band) => option(`Band ${band}`, band, state.band)).join("")}
        </select>
      </label>
    </div>
    <div class="distribution-picker-grid pay-horizon-picker-grid" aria-label="Midpoint cohort controls">
      <label>
        <span>Curve cohort</span>
        <select data-v1-control="cohortId">
          ${visibleCohorts().map((item) => option(cohortOptionLabel(item), item.cohort_id, state.cohortId)).join("")}
        </select>
      </label>
      <label>
        <span>Comparator</span>
        <select data-v1-control="comparatorCohortId">
          ${visibleComparatorCohorts().map((item) => option(cohortOptionLabel(item), item.cohort_id, state.comparatorCohortId)).join("")}
        </select>
      </label>
      <div class="distribution-level-span">
        <span>Metric</span>
        <strong>Range midpoint</strong>
      </div>
      <div class="distribution-level-span">
        <span>Source</span>
        <strong>Datamart</strong>
      </div>
    </div>
  `;
}

function renderBasisToggle() {
  return `
    <div class="pay-horizon-mode-toggle" role="group" aria-label="Chart basis mode">
      ${[
    [BASIS_CURRENT, "Selected period"],
    [BASIS_FOUR_PERIOD_AVERAGE, "4-period avg"],
    [BASIS_DATE_SMOOTHED, "Date-smoothed"],
  ].map(([value, label]) => `
        <button type="button" class="${state.basisMode === value ? "is-active" : ""}" data-v1-basis="${value}" aria-pressed="${state.basisMode === value ? "true" : "false"}">${escapeHtml(label)}</button>
      `).join("")}
    </div>
  `;
}

function renderRangeToggle() {
  return `
    <div class="distribution-range-toggle" role="group" aria-label="Chart range overlay">
      ${[
    [RANGE_NONE, "No range"],
    [RANGE_IQR, "IQR"],
    [RANGE_STD_DEV, "1 SD"],
  ].map(([value, label]) => `
        <button type="button" class="${state.rangeMode === value ? "is-active" : ""}" data-v1-range="${value}" aria-pressed="${state.rangeMode === value ? "true" : "false"}">${escapeHtml(label)}</button>
      `).join("")}
    </div>
  `;
}

function chartTitle(row = state.row) {
  return `Band ${state.band} range midpoint distribution - ${curveCohortName(row)} / ${comparatorCohortName()} comparator`;
}

function renderSidePanel(row) {
  const stats = state.curveStats || rowStats(row);
  const comparatorStats = state.comparatorStats;
  const point = selectedPoint(row);
  const selectedValue = safeNumber(point?.weekly_rate);
  const comparatorGap = selectedValue !== null && comparatorStats?.mean !== null ? selectedValue - comparatorStats.mean : null;
  return `
    <aside class="distribution-band-delta-panel" aria-label="Midpoint detail">
      <div class="distribution-band-delta-head">
        <span>Selected council</span>
        <strong>${escapeHtml(selectedCouncilName(row))}</strong>
      </div>
      <div class="pay-horizon-selected-path-list">
        <div class="pay-horizon-selected-point">
          <span>Range midpoint</span>
          <strong>${escapeHtml(formatCurrency(point?.weekly_rate))}</strong>
          <small>${escapeHtml(`${curveCohortName(row)} curve / ${rangeLabel()}`)}</small>
        </div>
        <div class="pay-horizon-selected-point">
          <span>Curve median</span>
          <strong>${escapeHtml(formatCurrency(stats?.median))}</strong>
          <small>${escapeHtml(`${formatCount(stats?.councilCount)} councils / ${formatCount(stats?.count)} observations`)}</small>
        </div>
        <div class="pay-horizon-selected-point">
          <span>Comparator average</span>
          <strong>${escapeHtml(formatCurrency(comparatorStats?.mean))}</strong>
          <small>${escapeHtml(`${comparatorCohortName()} / delta ${comparatorGap !== null ? displayCurrencyDelta(comparatorGap) : "not available"}`)}</small>
        </div>
      </div>
    </aside>
  `;
}

function renderFoot(row) {
  if (!row) return "";
  const stats = state.curveStats || rowStats(row);
  const comparatorStats = state.comparatorStats;
  return `
    <div class="distribution-foot">
      <span>Curve ${escapeHtml(curveCohortName(row))}</span>
      <span>Comparator ${escapeHtml(comparatorCohortName())}</span>
      <span>${escapeHtml(formatCount(stats?.count))} curve midpoint observations</span>
      <span>${escapeHtml(formatCount(comparatorStats?.count))} comparator midpoint observations</span>
      <span>${escapeHtml(formatCount(stats?.councilCount))} councils</span>
      <span>Metric range_midpoint_rate</span>
      <span>Basis ${escapeHtml(rangeLabel())}</span>
      <span class="pay-horizon-status" data-tone="${escapeHtml(state.messageTone)}">${escapeHtml(state.message)}</span>
    </div>
  `;
}

function renderSourcePanel(row) {
  manifestRoot.innerHTML = row ? `
    <div class="report-export-card">
      <div>
        <span class="distribution-eyebrow">Chart source</span>
        <h3>V1 midpoint replica</h3>
        <p>This panel reads range_midpoint_only rows from pay_service_horizon_curve_view and its SQLite companion. Service-horizon features remain in the datamart/API, but are hidden from this working chart.</p>
      </div>
    </div>
  ` : "";
}

function render() {
  if (!state.options) {
    root.innerHTML = `<div class="distribution-card workbench-card-scaffold distribution-card-empty"><p>Loading midpoint distribution.</p></div>`;
    return;
  }
  const row = state.row;
  const stats = state.curveStats || rowStats(row);
  const comparatorStats = state.comparatorStats;
  const point = selectedPoint(row);
  const selectedValue = safeNumber(point?.weekly_rate);
  const comparatorGap = selectedValue !== null && comparatorStats?.mean !== null ? selectedValue - comparatorStats.mean : null;
  const title = chartTitle(row);
  root.innerHTML = `
    <div class="distribution-card workbench-card-scaffold">
      <div class="distribution-card-head">
        <div>
          <span class="distribution-eyebrow">Midpoint distribution</span>
          <h3>${escapeHtml(title)}</h3>
          ${renderInlineMeta([
    basisLabel(),
    rangeLabel(),
    `Council ${selectedCouncilName(row)}`,
    `Curve ${curveCohortName(row)}`,
    `Comparator ${comparatorCohortName()}`,
    "Metric range_midpoint_rate",
    titleIsSafe(title) ? "Metric-safe title" : "Needs metric label",
  ])}
        </div>
        <div class="distribution-head-actions">
          ${renderSelectorControls()}
          ${renderBasisToggle()}
          ${renderRangeToggle()}
          <div class="distribution-stat-grid">
            <div><span>Curve median</span><strong>${escapeHtml(stats ? formatCurrency(stats.median) : "Not available")}</strong></div>
            <div><span>Comparator avg</span><strong>${escapeHtml(comparatorStats ? formatCurrency(comparatorStats.mean) : "Not available")}</strong></div>
            <div><span>${escapeHtml(selectedCouncilName(row))}</span><strong>${escapeHtml(selectedValue !== null ? formatCurrency(selectedValue) : "Not available")}</strong></div>
            <div><span>Delta to comparator</span><strong>${escapeHtml(comparatorGap !== null ? displayCurrencyDelta(comparatorGap) : "Not available")}</strong></div>
            <div><span>Observations</span><strong>${escapeHtml(formatCount(stats?.count))}</strong></div>
          </div>
        </div>
      </div>
      <div class="distribution-chart-grid">
        <div class="distribution-curve-panel">
          ${state.loading ? `<div class="distribution-card-empty"><p>Loading midpoint curve.</p></div>` : renderDistributionSvg(row)}
        </div>
        ${renderSidePanel(row || {})}
      </div>
      ${renderFoot(row)}
    </div>
  `;
  renderSourcePanel(row);
}

function bindEvents() {
  document.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) return;
    const control = target.dataset.v1Control;
    if (control && control in state) {
      state[control] = target.value;
      loadRow();
      return;
    }
    if (target.dataset.v1Year !== undefined) {
      setYearQuarter(target.value, quarterNumberFromIso(state.effectiveFrom));
      loadRow();
      return;
    }
    if (target.dataset.v1Quarter !== undefined) {
      const year = String(state.effectiveFrom || "").slice(0, 4);
      setYearQuarter(year, Number(target.value));
      loadRow();
    }
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.v1Basis) {
      state.basisMode = button.dataset.v1Basis;
      loadRow();
      return;
    }
    if (button.dataset.v1Range) {
      state.rangeMode = button.dataset.v1Range;
      render();
    }
  });
}

async function init() {
  bindEvents();
  try {
    const payload = await fetchJson(API_OPTIONS);
    state.options = payload.options || {};
    initialiseDefaults(state.options);
    await loadRow();
  } catch (error) {
    root.innerHTML = `<div class="distribution-card workbench-card-scaffold distribution-card-empty"><p>Could not initialise midpoint chart: ${escapeHtml(error.message || String(error))}</p></div>`;
  }
}

init();
