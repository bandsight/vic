import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(new URL("../..", import.meta.url).pathname.slice(1));

function readJson(path) {
  return JSON.parse(readFileSync(resolve(root, path), "utf8"));
}

function writeJson(path, data) {
  writeFileSync(resolve(root, path), `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function normaliseKey(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/&/g, " AND ")
    .replace(/[^A-Z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "");
}

function numberOrNull(value) {
  if (value === undefined || value === null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function asDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function dateOnly(value) {
  const parsed = asDate(value);
  return parsed ? parsed.toISOString().slice(0, 10) : null;
}

function median(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function normaliseSalaryPeriod(value) {
  const text = String(value || "").toLowerCase();
  if (!text) return "";
  if (/\b(year|annual|annum|pa|p\/a|per annum)\b/.test(text)) return "year";
  if (/\b(hour|hourly|p\/h|per hour)\b/.test(text)) return "hour";
  if (/\b(fortnight|fortnightly)\b/.test(text)) return "fortnight";
  if (/\b(week|weekly|per week)\b/.test(text)) return "week";
  return text;
}

function salaryRangeFromValues(minValue, maxValue) {
  const min = numberOrNull(minValue);
  const max = numberOrNull(maxValue ?? min);
  if (min === null && max === null) return null;
  return {
    min: min ?? max,
    max: max ?? min,
  };
}

function advertisedAnnualSalaryRange(job) {
  const min = numberOrNull(firstPresent(
    job.advertised_salary_min,
    job.salary_min,
  ));
  const max = numberOrNull(firstPresent(
    job.advertised_salary_max,
    job.salary_max,
    min,
  ));
  const range = salaryRangeFromValues(min, max);
  if (!range) return null;
  const period = normaliseSalaryPeriod(firstPresent(job.advertised_salary_period, job.salary_period));
  const high = Math.max(range.min, range.max);
  const low = Math.min(range.min, range.max);
  if (high < 30000) return null;
  if (period && !["year", "annual", "annum", "pa", "hour"].includes(period)) return null;
  if (low < 30000) return { min: high, max: high, source: "advertised" };
  return { min: low, max: high, source: "advertised" };
}

function enterpriseAgreementAnnualSalaryRange(job) {
  const period = normaliseSalaryPeriod(firstPresent(
    job.enterprise_agreement_salary_period,
    job.canonical_salary_period,
  ));
  if (period && period !== "year") return null;
  const range = salaryRangeFromValues(
    firstPresent(job.enterprise_agreement_salary_min, job.canonical_salary_min),
    firstPresent(job.enterprise_agreement_salary_max, job.canonical_salary_max),
  );
  return range ? { ...range, source: "enterprise_agreement" } : null;
}

function annualSalaryRange(job, hasCouncilPayRows) {
  return advertisedAnnualSalaryRange(job) || (hasCouncilPayRows ? enterpriseAgreementAnnualSalaryRange(job) : null);
}

function bandInferenceEaRange(latest, bandNumber) {
  const candidates = Array.isArray(latest.band_inference_candidates)
    ? latest.band_inference_candidates
    : [];
  const match = candidates.find((candidate) => Number(candidate.standard_band_number) === bandNumber);
  const weeklyMin = numberOrNull(match?.comparator_weekly_min);
  const weeklyMax = numberOrNull(match?.comparator_weekly_max);
  if (weeklyMin === null && weeklyMax === null) return null;
  return {
    min: (weeklyMin ?? weeklyMax) * 52,
    max: (weeklyMax ?? weeklyMin) * 52,
    effective_from: match?.comparator_effective_from || null,
    comparator_rows: numberOrNull(match?.comparator_rows),
  };
}

function daysUntil(value, asOfDate) {
  const parsed = asDate(value);
  if (!parsed) return null;
  return Math.ceil((parsed.getTime() - asOfDate.getTime()) / 86400000);
}

function increment(map, key, amount = 1) {
  map.set(key, (map.get(key) || 0) + amount);
}

function sortedCountRows(map, labelKey = "label") {
  return [...map.entries()]
    .map(([label, count]) => ({ [labelKey]: label, count }))
    .sort((a, b) => b.count - a.count || String(a[labelKey]).localeCompare(String(b[labelKey])));
}

function councilLookup(councils) {
  const lookup = new Map();
  for (const council of councils) {
    [
      council.short_name,
      council.long_name,
      council.spatial_key,
      council.map_join_key,
    ].forEach((value) => {
      const key = normaliseKey(value);
      if (key && !lookup.has(key)) lookup.set(key, council);
    });
  }
  return lookup;
}

function payCouncilKeys(payRows) {
  const keys = new Set();
  for (const row of payRows || []) {
    [
      row.council_key,
      row.council_name,
      row.canonical_lga_short_name,
      row.lga_short_name,
    ].forEach((value) => {
      const key = normaliseKey(value);
      if (key) keys.add(key);
    });
  }
  return keys;
}

function hasPayRowsForCouncil(council, councilKey, payKeys) {
  return [
    councilKey,
    council.short_name,
    council.long_name,
    council.spatial_key,
    council.map_join_key,
  ].some((value) => payKeys.has(normaliseKey(value)));
}

function buildJob(row, lookup, payKeys) {
  const latest = row.latest_job || {};
  const council = lookup.get(normaliseKey(row.short_name))
    || lookup.get(normaliseKey(row.council_name))
    || {};
  const sourceKindsSeen = Array.isArray(row.source_kinds_seen) ? row.source_kinds_seen : [];
  const links = Array.isArray(row.job_urls_seen)
    ? row.job_urls_seen.filter(Boolean)
    : [row.job_url].filter(Boolean);
  const primaryUrl = firstPresent(row.canonical_url, row.job_url, latest.canonical_url, latest.job_url, links[0]);
  const bandNumber = Number(row.standard_band_number);
  const inferredBand = row.classification_confidence === "inferred";
  const status = row.observed_status === "historical_not_seen_latest"
    ? "historical"
    : (sourceKindsSeen.includes("secondary") && !sourceKindsSeen.includes("official") ? "public_board" : "current");
  const publicBoardSignal = sourceKindsSeen.includes("secondary") || row.observed_status === "secondary_signal";
  const councilKey = normaliseKey(council.map_join_key || council.spatial_key || row.short_name || row.council_name);
  const hasCouncilPayRows = hasPayRowsForCouncil(council, councilKey, payKeys);
  const annualSalary = annualSalaryRange({ ...latest, ...row }, hasCouncilPayRows);
  const inferredEa = inferredBand && hasCouncilPayRows ? bandInferenceEaRange(latest, bandNumber) : null;
  const salaryValidation = latest.salary_band_validation && typeof latest.salary_band_validation === "object"
    ? latest.salary_band_validation
    : null;
  const eaMin = hasCouncilPayRows ? numberOrNull(firstPresent(latest.enterprise_agreement_salary_min, latest.canonical_salary_min)) : null;
  const eaMax = hasCouncilPayRows ? numberOrNull(firstPresent(latest.enterprise_agreement_salary_max, latest.canonical_salary_max)) : null;
  return {
    dedupe_key: row.dedupe_key,
    job_uid: latest.job_uid || row.dedupe_key,
    job_title: row.job_title,
    job_url: primaryUrl,
    external_links: [...new Set([primaryUrl, ...links].filter(Boolean))],
    council_name: row.council_name,
    short_name: row.short_name,
    council_key: councilKey,
    source_family: firstPresent(row.source_family, latest.source_family),
    source_name: firstPresent(row.source_name, latest.source_name),
    source_kinds_seen: sourceKindsSeen,
    source_labels_seen: row.source_labels_seen || [],
    observed_status: row.observed_status,
    board_status: status,
    public_board_signal: publicBoardSignal,
    classification_band: row.classification_band,
    standard_band_number: bandNumber,
    inferred_standard_band_number: inferredBand ? bandNumber : null,
    classification_confidence: row.classification_confidence,
    is_standard_band_1_to_8: bandNumber >= 1 && bandNumber <= 8,
    canonical_reference_month: row.canonical_reference_month,
    canonical_reference_date: row.canonical_reference_date,
    first_seen_at: row.first_seen_at,
    last_seen_at: row.last_seen_at,
    last_seen_official_at: row.last_seen_official_at,
    last_seen_secondary_at: row.last_seen_secondary_at,
    sighting_count: row.sighting_count || 1,
    location_text: firstPresent(latest.location_text, row.location_text),
    work_type: firstPresent(latest.work_type, row.work_type),
    department: firstPresent(latest.department, row.department),
    closing_at: firstPresent(latest.closing_at, row.closing_at),
    closing_at_text: firstPresent(latest.closing_at_text, row.closing_at_text),
    advertised_salary_text: firstPresent(latest.advertised_salary_text, latest.salary_text),
    advertised_salary_min: numberOrNull(firstPresent(latest.advertised_salary_min, latest.salary_min)),
    advertised_salary_max: numberOrNull(firstPresent(latest.advertised_salary_max, latest.salary_max)),
    advertised_salary_period: firstPresent(latest.advertised_salary_period, latest.salary_period),
    enterprise_agreement_salary_min: eaMin,
    enterprise_agreement_salary_max: eaMax,
    enterprise_agreement_salary_period: hasCouncilPayRows ? firstPresent(latest.enterprise_agreement_salary_period, latest.canonical_salary_period) : null,
    enterprise_agreement_salary_effective_from: hasCouncilPayRows ? firstPresent(latest.enterprise_agreement_salary_effective_from, latest.canonical_salary_effective_from) : null,
    enterprise_agreement_salary_effective_to: hasCouncilPayRows ? firstPresent(latest.enterprise_agreement_salary_effective_to, latest.canonical_salary_effective_to) : null,
    inferred_enterprise_agreement_salary_min: inferredEa?.min ?? null,
    inferred_enterprise_agreement_salary_max: inferredEa?.max ?? null,
    inferred_enterprise_agreement_salary_period: inferredEa ? "year" : null,
    inferred_enterprise_agreement_salary_effective_from: inferredEa?.effective_from ?? null,
    inferred_enterprise_agreement_salary_comparator_rows: inferredEa?.comparator_rows ?? null,
    annual_salary_min: annualSalary?.min ?? null,
    annual_salary_max: annualSalary?.max ?? null,
    annual_salary_source: annualSalary?.source ?? null,
    salary_band_validation_status: hasCouncilPayRows ? (latest.salary_band_validation_status || salaryValidation?.status || null) : "no_comparator",
    salary_band_validation_notes: hasCouncilPayRows ? (salaryValidation?.notes || null) : "No governed pay-table rows are available for this council.",
    description_text: firstPresent(latest.description_text, latest.detail_text, ""),
    completion_action_label: latest.completion_action_label,
  };
}

function relaxedJobKey(job) {
  const council = normaliseKey(job.council_key || job.short_name || job.council_name);
  const title = normaliseKey(job.job_title);
  const month = String(job.canonical_reference_month || "");
  return council && title && month ? `${council}|${title}|${month}` : "";
}

function jobLinks(job) {
  return new Set([job.job_url, ...(job.external_links || [])].filter(Boolean));
}

function sourceKinds(job) {
  return new Set((job.source_kinds_seen || []).filter(Boolean));
}

function shouldMergeDuplicateJobs(left, right) {
  if (!relaxedJobKey(left) || relaxedJobKey(left) !== relaxedJobKey(right)) return false;
  const leftLinks = jobLinks(left);
  const rightLinks = jobLinks(right);
  if ([...leftLinks].some((link) => rightLinks.has(link))) return true;
  const kinds = new Set([...sourceKinds(left), ...sourceKinds(right)]);
  return kinds.has("secondary") || left.public_board_signal || right.public_board_signal;
}

function jobPreference(job) {
  const kinds = sourceKinds(job);
  const official = kinds.has("official");
  const status = job.board_status || job.observed_status || "";
  let sourceRank = 4;
  if (official && status === "current") sourceRank = 0;
  else if (official) sourceRank = 1;
  else if (status === "current") sourceRank = 2;
  else if (status === "historical") sourceRank = 3;
  const confidenceRank = job.classification_confidence === "confirmed" ? 0 : 1;
  return [sourceRank, confidenceRank, -jobLinks(job).size, String(job.last_seen_at || "")];
}

function preferredJob(left, right) {
  const leftRank = jobPreference(left);
  const rightRank = jobPreference(right);
  for (let index = 0; index < 3; index += 1) {
    if (leftRank[index] < rightRank[index]) return [left, right];
    if (rightRank[index] < leftRank[index]) return [right, left];
  }
  return rightRank[3] >= leftRank[3] ? [right, left] : [left, right];
}

function firstDateString(...values) {
  const dates = values.filter(Boolean).map(String).sort();
  return dates[0] || null;
}

function lastDateString(...values) {
  const dates = values.filter(Boolean).map(String).sort();
  return dates.at(-1) || null;
}

function mergeDuplicateJobs(left, right) {
  const [primary, secondaryJob] = preferredJob(left, right);
  const externalLinks = [...new Set([
    primary.job_url,
    secondaryJob.job_url,
    ...(primary.external_links || []),
    ...(secondaryJob.external_links || []),
  ].filter(Boolean))];
  const sourceKindsSeen = [...new Set([
    ...(primary.source_kinds_seen || []),
    ...(secondaryJob.source_kinds_seen || []),
  ].filter(Boolean))].sort();
  return {
    ...secondaryJob,
    ...primary,
    external_links: externalLinks,
    source_kinds_seen: sourceKindsSeen,
    source_labels_seen: [...new Set([
      ...(primary.source_labels_seen || []),
      ...(secondaryJob.source_labels_seen || []),
    ].filter(Boolean))].sort(),
    public_board_signal: primary.public_board_signal || secondaryJob.public_board_signal || sourceKindsSeen.includes("secondary"),
    first_seen_at: firstDateString(primary.first_seen_at, secondaryJob.first_seen_at),
    last_seen_at: lastDateString(primary.last_seen_at, secondaryJob.last_seen_at),
    last_seen_official_at: lastDateString(primary.last_seen_official_at, secondaryJob.last_seen_official_at),
    last_seen_secondary_at: lastDateString(primary.last_seen_secondary_at, secondaryJob.last_seen_secondary_at),
    sighting_count: Number(primary.sighting_count || 0) + Number(secondaryJob.sighting_count || 0),
  };
}

function collapseDuplicateJobRows(jobs) {
  const rowsByKey = new Map();
  const relaxedIndex = new Map();
  for (const job of jobs) {
    const key = job.dedupe_key || job.job_uid;
    const relaxedKey = relaxedJobKey(job);
    const existingKey = relaxedKey ? relaxedIndex.get(relaxedKey) : null;
    if (
      existingKey
      && existingKey !== key
      && rowsByKey.has(existingKey)
      && shouldMergeDuplicateJobs(rowsByKey.get(existingKey), job)
    ) {
      const merged = mergeDuplicateJobs(rowsByKey.get(existingKey), job);
      const mergedKey = merged.dedupe_key || merged.job_uid || existingKey;
      if (mergedKey !== existingKey) rowsByKey.delete(existingKey);
      rowsByKey.set(mergedKey, merged);
      relaxedIndex.set(relaxedKey, mergedKey);
      continue;
    }
    rowsByKey.set(key, job);
    if (relaxedKey && !relaxedIndex.has(relaxedKey)) relaxedIndex.set(relaxedKey, key);
  }
  return [...rowsByKey.values()];
}

function buildVisuals(jobs, councils, accumulator, secondary, wide, asOfDate) {
  const byBand = new Map();
  const bySource = new Map();
  const byMonth = new Map();
  const byCouncil = new Map();
  const closingBuckets = new Map([
    ["Past close", 0],
    ["0-7 days", 0],
    ["8-14 days", 0],
    ["15-30 days", 0],
    ["31+ days", 0],
    ["No close date", 0],
  ]);
  const salaryByBand = new Map();

  for (const job of jobs) {
    const band = String(job.standard_band_number);
    const bandRow = byBand.get(band) || {
      band: Number(band),
      count: 0,
      current: 0,
      historical: 0,
      public_board: 0,
      inferred: 0,
    };
    bandRow.count += 1;
    bandRow[job.board_status] = (bandRow[job.board_status] || 0) + 1;
    if (job.public_board_signal) bandRow.public_board += 1;
    if (job.classification_confidence === "inferred") bandRow.inferred += 1;
    byBand.set(band, bandRow);

    increment(bySource, job.source_family || "unknown");
    increment(byMonth, job.canonical_reference_month || "unknown");
    increment(byCouncil, job.council_key);

    const days = daysUntil(job.closing_at || job.closing_at_text, asOfDate);
    if (days === null) increment(closingBuckets, "No close date");
    else if (days < 0) increment(closingBuckets, "Past close");
    else if (days <= 7) increment(closingBuckets, "0-7 days");
    else if (days <= 14) increment(closingBuckets, "8-14 days");
    else if (days <= 30) increment(closingBuckets, "15-30 days");
    else increment(closingBuckets, "31+ days");

    if (job.annual_salary_min !== null || job.annual_salary_max !== null) {
      const salary = salaryByBand.get(band) || [];
      salary.push(job.annual_salary_min ?? job.annual_salary_max);
      if (job.annual_salary_max !== null && job.annual_salary_max !== job.annual_salary_min) {
        salary.push(job.annual_salary_max);
      }
      salaryByBand.set(band, salary);
    }
  }

  const coveredCouncils = new Set(jobs.map((job) => job.council_key));
  const categories = new Map();
  for (const council of councils) {
    const category = council.council_category || "Uncategorised";
    const key = normaliseKey(council.map_join_key || council.spatial_key || council.short_name);
    const row = categories.get(category) || { category, total: 0, covered: 0, jobs: 0 };
    row.total += 1;
    if (coveredCouncils.has(key)) row.covered += 1;
    row.jobs += byCouncil.get(key) || 0;
    categories.set(category, row);
  }

  const salary_spans = [...salaryByBand.entries()]
    .map(([band, values]) => ({
      band: Number(band),
      min: Math.min(...values),
      max: Math.max(...values),
      median: median(values),
      count: values.length,
    }))
    .sort((a, b) => a.band - b.band);

  return {
    evidence_flow: [
      { label: "Official wide fetch", value: wide.summary?.jobs || 0, detail: `${wide.summary?.sources_attempted || 0} sources checked` },
      { label: "Checked classified", value: accumulator.summary?.checked_classified_jobs || jobs.length, detail: `${accumulator.coverage?.coverage_rate || 0}% council coverage` },
      { label: "Public-board signals", value: secondary.summary?.classified_band_1_to_8_jobs || 0, detail: `${secondary.summary?.sources_attempted || 0} secondary pages checked` },
      { label: "Historical memory", value: accumulator.summary?.historical_jobs || 0, detail: `${accumulator.summary?.reference_months || 0} reference months retained` },
    ],
    band_counts: [...byBand.values()].sort((a, b) => a.band - b.band),
    source_mix: sortedCountRows(bySource, "source_family").slice(0, 9),
    month_counts: sortedCountRows(byMonth, "month").sort((a, b) => String(a.month).localeCompare(String(b.month))),
    council_category_coverage: [...categories.values()].sort((a, b) => b.jobs - a.jobs || a.category.localeCompare(b.category)),
    top_councils: sortedCountRows(byCouncil, "council_key").slice(0, 12).map((row) => {
      const council = councils.find((item) => normaliseKey(item.map_join_key || item.spatial_key || item.short_name) === row.council_key);
      return { ...row, label: council?.short_name || row.council_key };
    }),
    closing_buckets: sortedCountRows(closingBuckets, "bucket"),
    salary_spans,
  };
}

const accumulator = readJson("var/job_intake/checked_job_accumulator.json");
const secondary = readJson("var/job_intake/secondary_preview_snapshot.json");
const wide = readJson("var/job_intake/scrape_preview_snapshot.json");
const oldBoard = readJson("apps/vic-council-job-board/data/job-board-data.json");
const boundaries = readJson("static/data/victoria-lga-boundaries.geojson");
const governedPayRows = readJson("data/governed_canonical/pay_rows.json");
const councils = oldBoard.councils || [];
const lookup = councilLookup(councils);
const payKeys = payCouncilKeys(governedPayRows.rows || []);
const savedAt = accumulator.saved_at || new Date().toISOString();
const asOfDate = asDate(savedAt) || new Date();

const builtJobs = (accumulator.rows || [])
  .map((row) => buildJob(row, lookup, payKeys))
  .filter((job) => job.is_standard_band_1_to_8 && job.job_title && job.council_key);

const jobs = collapseDuplicateJobRows(builtJobs)
  .sort((a, b) => a.council_key.localeCompare(b.council_key)
    || Number(a.standard_band_number) - Number(b.standard_band_number)
    || a.job_title.localeCompare(b.job_title));

const data = {
  set_id: "vic_council_job_board_checked_history_v2",
  generated_from: {
    accumulator_path: "var/job_intake/checked_job_accumulator.json",
    secondary_snapshot_path: "var/job_intake/secondary_preview_snapshot.json",
    wide_snapshot_path: "var/job_intake/scrape_preview_snapshot.json",
    boundary_path: "static/data/victoria-lga-boundaries.geojson",
  },
  saved_at: savedAt,
  as_of_date: dateOnly(savedAt),
  summary: {
    ...(accumulator.summary || {}),
    coverage: accumulator.coverage || {},
    wide_fetch_jobs: wide.summary?.jobs || 0,
    wide_fetch_sources_attempted: wide.summary?.sources_attempted || 0,
    wide_fetch_generated_sources: wide.summary?.generated_candidate_sources || 0,
    secondary_jobs: secondary.summary?.jobs || 0,
    secondary_sources_attempted: secondary.summary?.sources_attempted || 0,
    secondary_classified_jobs: secondary.summary?.classified_band_1_to_8_jobs || 0,
    display_jobs: jobs.length,
    display_councils: new Set(jobs.map((job) => job.council_key)).size,
  },
  councils,
  jobs,
  visuals: buildVisuals(jobs, councils, accumulator, secondary, wide, asOfDate),
};

writeJson("apps/vic-council-job-board/data/job-board-data.json", data);
writeFileSync(
  resolve(root, "apps/vic-council-job-board/data/embedded-data.js"),
  `window.__VIC_LGA_BOUNDARIES__ = ${JSON.stringify(boundaries)};\nwindow.__VIC_COUNCIL_JOB_BOARD_DATA__ = ${JSON.stringify(data)};\n`,
  "utf8",
);

console.log(JSON.stringify({
  jobs: data.jobs.length,
  councils: data.summary.display_councils,
  publicBoard: data.summary.secondary_classified_jobs,
  wide: data.summary.wide_fetch_jobs,
}, null, 2));
