export const SINGLE_POINT_METRIC_TO_WINDOW = {
  entry_rate: "entry_only",
  range_midpoint_rate: "range_midpoint_only",
  capacity_rate: "capacity_only",
  service_year_3_rate: "y3_only",
};

export const METRIC_LABELS = {
  entry_rate: "Entry rate",
  range_midpoint_rate: "Range midpoint rate",
  capacity_rate: "Capacity rate",
  service_year_3_rate: "Y3 service-horizon rate",
};

export const HORIZON_STOPS = [
  { key: "entry", label: "Entry" },
  { key: "y1", label: "Y1" },
  { key: "y2", label: "Y2" },
  { key: "y3", label: "Y3" },
  { key: "y4", label: "Y4" },
  { key: "y5", label: "Y5" },
  { key: "y6", label: "Y6" },
  { key: "capacity", label: "Capacity" },
];

export function parseJsonField(value, fallback) {
  if (value === null || value === undefined || value === "") return fallback;
  if (Array.isArray(value) || (typeof value === "object" && value !== null)) return value;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

export function selectedPoints(row) {
  const points = parseJsonField(row?.selected_council_points_json, []);
  return Array.isArray(points) ? points : [];
}

export function comparatorEnvelope(row) {
  const envelope = parseJsonField(row?.comparator_envelope_json, {});
  return envelope && typeof envelope === "object" && !Array.isArray(envelope) ? envelope : {};
}

export function horizonEnvelopePoints(row) {
  const points = parseJsonField(row?.horizon_envelope_json, []);
  return Array.isArray(points) ? points : [];
}

export function includedMetrics(row) {
  const metrics = parseJsonField(row?.included_metric_points, []);
  return Array.isArray(metrics) ? metrics : [];
}

export function includedYears(row) {
  const years = parseJsonField(row?.included_service_horizon_years, []);
  return Array.isArray(years) ? years : [];
}

export function windowFromHorizonStops(start, end) {
  const pair = `${start}:${end}`;
  const map = {
    "entry:entry": "entry_only",
    "entry:y3": "entry_to_y3",
    "y3:y6": "y3_to_y6",
    "entry:y6": "entry_to_y6",
    "entry:capacity": "entry_to_capacity_profile",
    "capacity:capacity": "capacity_only",
  };
  return map[pair] || null;
}

export function titleIsSafe(title) {
  const lowered = String(title || "").toLowerCase();
  if (/^\s*band\s+\w+\s+distribution\s*$/.test(lowered)) return false;
  const safeTerms = ["entry", "midpoint", "capacity", "service-horizon", "year", "range", "profile"];
  const namesMetricUniverse = lowered.includes("distribution")
    || lowered.includes("profile")
    || lowered.includes("service-horizon");
  return namesMetricUniverse && safeTerms.some((term) => lowered.includes(term));
}

export function formatCurrency(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not available";
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0,
  }).format(number);
}

export function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not available";
  return new Intl.NumberFormat("en-AU", { maximumFractionDigits: 2 }).format(number);
}

export function pointTooltip(point) {
  return [
    point.display_label || point.comparison_metric || "Selected point",
    `Metric: ${point.comparison_metric || "unknown"}`,
    point.service_horizon_year !== null && point.service_horizon_year !== undefined
      ? `Service horizon: Y${point.service_horizon_year}`
      : null,
    `Weekly rate: ${formatCurrency(point.weekly_rate)}`,
    `Resolved level: ${point.resolved_level_label || "not applicable"}`,
    `Resolved mode: ${point.resolved_value_mode || "not applicable"}`,
    `Actual step count: ${point.actual_step_count ?? "not available"}`,
    `Capacity carry-forward: ${point.capacity_carry_forward === true ? "yes" : "no"}`,
    `Calculation status: ${point.calculation_status || "unknown"}`,
    `Report status: ${point.report_ready_status || "unknown"}`,
    point.metric_caveat ? `Caveat: ${point.metric_caveat}` : null,
  ].filter(Boolean).join("\n");
}

export function comparatorTooltip(row) {
  const envelope = comparatorEnvelope(row);
  return [
    row?.cohort_name || "Comparator cohort",
    `Included metrics: ${includedMetrics(row).join(", ") || "unknown"}`,
    `Weighting: ${row?.weighting_method || envelope.weighting_method || "unknown"}`,
    `Councils: ${row?.curve_council_count ?? envelope.curve_council_count ?? "unknown"}`,
    `Observations: ${row?.curve_sample_count ?? envelope.curve_sample_count ?? "unknown"}`,
    `Min: ${formatCurrency(row?.curve_min ?? envelope.min)}`,
    `P25: ${formatCurrency(row?.curve_p25 ?? envelope.p25)}`,
    `Median: ${formatCurrency(row?.curve_median ?? envelope.median)}`,
    `P75: ${formatCurrency(row?.curve_p75 ?? envelope.p75)}`,
    `Max: ${formatCurrency(row?.curve_max ?? envelope.max)}`,
    `Blocked/excluded: ${envelope.blocked_observation_count ?? 0}`,
  ].join("\n");
}

export function buildDraftManifest(row, state, generatedAt = new Date().toISOString()) {
  const viewMode = state.viewMode;
  return {
    chart_version: "pay_horizon_distribution_explorer.v2_prototype",
    view_mode: viewMode,
    comparison_metric: viewMode === "single_point" ? state.comparisonMetric : null,
    service_horizon_window_id: row?.service_horizon_window_id || null,
    service_horizon_window_label: row?.service_horizon_window_label || null,
    included_metric_points: includedMetrics(row),
    selected_council: {
      id: row?.selected_council_id || state.selectedCouncilId || null,
      name: row?.selected_council_name || null,
    },
    band: row?.standard_band || state.band || null,
    cohort: {
      id: row?.cohort_id || state.cohortId || null,
      name: row?.cohort_name || null,
    },
    comparator_cohort: {
      id: state.comparatorCohortId || row?.cohort_id || state.cohortId || null,
      name: state.comparatorCohortName || null,
    },
    effective_period: {
      effective_from: row?.effective_from || state.effectiveFrom || null,
      effective_to: row?.effective_to || null,
    },
    weighting_method: row?.weighting_method || "unknown",
    source_view: "pay_service_horizon_curve_view",
    source_view_version: "datamart_current",
    council_count: row?.curve_council_count || null,
    observation_count: row?.curve_sample_count || null,
    caveats: row?.metric_caveats || [],
    generated_at: generatedAt,
    report_ready_status: row?.report_ready_status || "unknown",
  };
}
