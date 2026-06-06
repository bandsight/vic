/* global fetch */
const REQUIRED_TOP_LEVEL = [
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

export async function loadReportData(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`Could not load report data: ${response.status} ${response.statusText}`);
  }
  const payload = await response.json();
  validateReportData(payload);
  return normaliseReportData(payload);
}

export function validateReportData(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Report data must be a JSON object.");
  }
  for (const key of REQUIRED_TOP_LEVEL) {
    if (!(key in payload)) throw new Error(`Report data missing required object: ${key}`);
  }
  if (!Array.isArray(payload.heroMetrics) || payload.heroMetrics.length < 4) {
    throw new Error("Report data requires at least four hero metrics.");
  }
  if (!Array.isArray(payload.payByBand?.bands) || payload.payByBand.bands.length < 8) {
    throw new Error("Report data requires payByBand.bands for Bands 1 to 8.");
  }
  if (!Array.isArray(payload.narrativeSteps) || payload.narrativeSteps.length < 5) {
    throw new Error("Report data requires pay narrative steps.");
  }
  if (!Array.isArray(payload.upliftTimeline?.series) || payload.upliftTimeline.series.length < 2) {
    throw new Error("Report data requires uplift timeline series.");
  }
  return true;
}

export function normaliseReportData(payload) {
  const payBands = payload.payByBand.bands.map((row) => ({
    ...row,
    band: Number(row.band),
    stateMedian: Number(row.stateMedian),
    smallMedian: Number(row.smallMedian),
    gap: Number(row.smallMedian) - Number(row.stateMedian),
    gapPct: Number(row.gapPct),
    timingSensitive: Boolean(row.timingSensitive),
  }));

  return {
    ...payload,
    payByBand: {
      ...payload.payByBand,
      bands: payBands,
      largestGap: payBands.reduce((winner, row) => (
        Math.abs(row.gap) > Math.abs(winner.gap) ? row : winner
      ), payBands[0]),
      narrowGapBands: payBands.filter((row) => Math.abs(row.gap) <= 40),
      timingSensitiveBands: payBands.filter((row) => row.timingSensitive),
    },
  };
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

export function formatSignedCurrency(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not available";
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatCurrency(number)}`;
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
