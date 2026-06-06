import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./pay-horizon-engine.js", import.meta.url), "utf8");
const engine = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
const {
  SINGLE_POINT_METRIC_TO_WINDOW,
  buildDraftManifest,
  horizonEnvelopePoints,
  selectedPoints,
  titleIsSafe,
  windowFromHorizonStops,
} = engine;

test("single-point midpoint maps to explicit midpoint window", () => {
  assert.equal(SINGLE_POINT_METRIC_TO_WINDOW.range_midpoint_rate, "range_midpoint_only");
});

test("service-window controls resolve only materialised windows", () => {
  assert.equal(windowFromHorizonStops("entry", "y3"), "entry_to_y3");
  assert.equal(windowFromHorizonStops("y3", "y6"), "y3_to_y6");
  assert.equal(windowFromHorizonStops("entry", "y6"), "entry_to_y6");
  assert.equal(windowFromHorizonStops("entry", "capacity"), "entry_to_capacity_profile");
  assert.equal(windowFromHorizonStops("entry", "y5"), null);
});

test("safe title validation rejects generic distribution language", () => {
  assert.equal(titleIsSafe("Band 5 distribution"), false);
  assert.equal(titleIsSafe("Band 5 range midpoint distribution"), true);
  assert.equal(titleIsSafe("Band 5 Entry-to-Year-3 service-horizon distribution"), true);
  assert.equal(titleIsSafe("Band 5 Entry-to-capacity service-horizon profile"), true);
});

test("draft manifest preserves V2 chart state", () => {
  const row = {
    service_horizon_window_id: "entry_to_y3",
    service_horizon_window_label: "Entry-to-Year-3 service-horizon distribution",
    included_metric_points: ["entry_rate", "service_year_1_rate", "service_year_2_rate", "service_year_3_rate"],
    selected_council_points_json: JSON.stringify([{ comparison_metric: "entry_rate", weekly_rate: 1000 }]),
    selected_council_id: "ALPHA",
    selected_council_name: "Alpha Shire Council",
    standard_band: "5",
    cohort_id: "all_governed",
    cohort_name: "All governed comparable rows",
    effective_from: "2026-07-01",
    weighting_method: "observation_weighted",
    curve_council_count: 3,
    curve_sample_count: 12,
    metric_caveats: ["same metric universe"],
    report_ready_status: "ready",
  };
  const manifest = buildDraftManifest(
    row,
    {
      viewMode: "service_window",
      comparatorCohortId: "council_type__shire",
      comparatorCohortName: "Council Type: shire",
    },
    "2026-05-08T00:00:00Z",
  );

  assert.equal(manifest.chart_version, "pay_horizon_distribution_explorer.v2_prototype");
  assert.equal(manifest.service_horizon_window_id, "entry_to_y3");
  assert.deepEqual(manifest.included_metric_points, [
    "entry_rate",
    "service_year_1_rate",
    "service_year_2_rate",
    "service_year_3_rate",
  ]);
  assert.equal(manifest.observation_count, 12);
  assert.deepEqual(manifest.comparator_cohort, {
    id: "council_type__shire",
    name: "Council Type: shire",
  });
});

test("service-window rows expose horizon-aligned envelope points", () => {
  const row = {
    horizon_envelope_json: JSON.stringify([
      { comparison_metric: "entry_rate", display_label: "Entry", median: 1000, sample_count: 3 },
      { comparison_metric: "service_year_3_rate", display_label: "Y3 service-horizon", median: 1300, sample_count: 3 },
    ]),
  };
  const envelope = horizonEnvelopePoints(row);

  assert.equal(envelope.length, 2);
  assert.deepEqual(envelope.map((point) => point.comparison_metric), ["entry_rate", "service_year_3_rate"]);
});

test("carry-forward selected point label does not imply Level 6", () => {
  const row = {
    selected_council_points_json: JSON.stringify([
      {
        comparison_metric: "service_year_6_rate",
        display_label: "Y6 service-horizon, capacity carried forward from Level C",
        resolved_level_label: "C",
        resolved_value_mode: "capacity_carry_forward",
        actual_step_count: 3,
        capacity_carry_forward: true,
      },
    ]),
  };
  const [point] = selectedPoints(row);

  assert.equal(point.resolved_value_mode, "capacity_carry_forward");
  assert.equal(point.resolved_level_label, "C");
  assert.equal(point.display_label.includes("Level 6"), false);
});
