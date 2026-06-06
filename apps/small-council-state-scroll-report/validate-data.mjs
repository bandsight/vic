import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const fileName = process.argv[2] || "workspace-small-council-state.json";
const dataPath = join(here, "data", fileName);

const requiredTopLevel = [
  "metadata",
  "reportManifest",
  "cohort",
  "heroMetrics",
  "payPointGalaxy",
  "evidenceChain",
  "payByBand",
  "distribution",
  "classificationContext",
  "upliftTimeline",
  "entitlements",
  "executiveTakeaways",
  "narrativeSteps",
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const payload = JSON.parse(await readFile(dataPath, "utf8"));

for (const key of requiredTopLevel) {
  assert(Object.hasOwn(payload, key), `Missing top-level key: ${key}`);
}

assert(
  ["illustrative_placeholder", "workspace_snapshot_mixed_governance", "draft_governed", "report_ready"].includes(payload.metadata.dataStatus),
  "metadata.dataStatus must clearly mark the data governance state.",
);
assert(
  String(payload.metadata.decisionUse || "").includes("not_for_decision_making")
    || String(payload.metadata.decisionUse || "").includes("not_for_decision"),
  "metadata.decisionUse must block unsupported decision use.",
);
assert(Array.isArray(payload.heroMetrics) && payload.heroMetrics.length >= 4, "Expected at least four hero metrics.");
assert(Array.isArray(payload.payPointGalaxy?.observations) && payload.payPointGalaxy.observations.length > 0, "Expected pay point galaxy observations.");
assert(Array.isArray(payload.evidenceChain) && payload.evidenceChain.length >= 5, "Expected a complete evidence chain.");
assert(Array.isArray(payload.payByBand.bands) && payload.payByBand.bands.length === 8, "Expected exactly eight pay bands.");

const bands = payload.payByBand.bands.map((row) => Number(row.band)).sort((a, b) => a - b);
assert(bands.every((band, index) => band === index + 1), "Pay bands must be numbered 1 to 8.");

const visualStates = new Set(Object.keys(payload.payByBand.states || {}));
for (const step of payload.narrativeSteps) {
  assert(visualStates.has(step.visualState), `Narrative step references unknown visual state: ${step.visualState}`);
}

assert(Array.isArray(payload.upliftTimeline.phases) && payload.upliftTimeline.phases.length >= 3, "Expected uplift phases.");
assert(Array.isArray(payload.upliftTimeline.series) && payload.upliftTimeline.series.length >= 3, "Expected uplift series.");
assert(Array.isArray(payload.entitlements.columns) && payload.entitlements.columns.length === 5, "Expected five entitlement columns.");
assert(Array.isArray(payload.executiveTakeaways) && payload.executiveTakeaways.length === 3, "Expected three executive takeaways.");

if (payload.distribution?.snapshotRule && Array.isArray(payload.distribution?.prototypeStyle?.observations)) {
  const asOf = new Date(`${payload.distribution.snapshotRule.asOfDate}T00:00:00Z`);
  assert(!Number.isNaN(asOf.valueOf()), "distribution.snapshotRule.asOfDate must be a valid ISO date.");

  const profiles = payload.distribution.prototypeStyle.profiles || {
    raw: payload.distribution.prototypeStyle,
  };
  for (const [profileKey, profile] of Object.entries(profiles)) {
    assert(Array.isArray(profile.observations) && profile.observations.length > 0, `Distribution profile has no observations: ${profileKey}`);
    assert(Array.isArray(profile.densityBins) && profile.densityBins.length > 0, `Distribution profile has no density bins: ${profileKey}`);
    for (const peak of profile.shapeDiagnostics?.primaryPeaks || []) {
      assert(typeof peak.label === "string" && peak.label.length > 0, `Distribution peak is missing a dynamic label: ${profileKey}`);
    }
    for (const row of profile.observations) {
      const from = new Date(`${row.effectiveFrom}T00:00:00Z`);
      const operativeEndRaw = row.effectiveTo || row.operativeEnd;
      const to = new Date(`${operativeEndRaw}T00:00:00Z`);
      assert(!Number.isNaN(from.valueOf()), `Distribution row missing valid effectiveFrom: ${row.councilName || row.councilKey}`);
      assert(!Number.isNaN(to.valueOf()), `Distribution row missing valid operative end: ${row.councilName || row.councilKey}`);
      assert(from <= asOf && asOf <= to, `Distribution row is outside the report operative window: ${row.councilName || row.councilKey}`);
    }
  }
}

console.log(`small-council-state-scroll-report data validation passed: ${fileName}`);
