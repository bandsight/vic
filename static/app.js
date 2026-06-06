import { PdfViewer } from "/static/pdf-viewer.js";
import { api, apiErrorMessage } from "/static/api-client.js";
import {
  createReportExportState,
  ensureReportExportCatalog as ensureReportExportCatalogState,
  REPORT_EXPORT_ENDPOINT,
  reportExportAsset as reportExportAssetState,
  reportExportDownloadHref,
  resetReportExportState,
  updateReportAssetStatus as updateReportAssetStatusState,
} from "/static/report-export-state.js";
import {
  DISPLAY_EMPTY,
  displayCodeLabel,
  displayCurrency,
  displayCurrencyDelta,
  displayDate,
  displayDateRange,
  displayFileSize,
  displayFractionPercent,
  displayHtml,
  displayNumber,
  displayPages,
  displayPercent,
  displayPercentDelta,
  displayValue,
  isIsoDate,
} from "/static/display-values.js";
import {
  GOVERNANCE_STATUS_CHIPS,
  WORKBENCH_CAPABILITY_TREE,
} from "/static/workbench-tree.js?ui=eba-long-list-v1&nav=single-workspace-v1";

const SECTION_LABELS = {
  overview: "Overview",
  uplift_rules: "Uplift Rules",
  pay_tables: "Pay Tables",
  scenarios: "Scenarios",
  end_of_band_dollars: "End of Band Dollars",
  uplifts: "Governed Set",
};

const MATRIX_SECTION_LABELS = {
  overview: "Overview",
  uplift_rules: "Uplift",
  pay_tables: "Pay",
  scenarios: "Scenarios",
  end_of_band_dollars: "EOB",
  uplifts: "Governed",
};

const SECTION_GROUPS = [
  {
    label: "Extraction",
    sections: ["overview", "uplift_rules", "pay_tables"],
  },
  {
    label: "Validation",
    sections: ["scenarios", "end_of_band_dollars"],
  },
  {
    label: "Governance",
    sections: ["uplifts"],
  },
];

const SECTION_QA_WORKFLOW_ORDER = ["overview", "uplift_rules", "pay_tables", "scenarios", "end_of_band_dollars", "uplifts"];
const MATRIX_CORE_REVIEW_SECTIONS = ["overview", "uplift_rules", "pay_tables", "scenarios", "end_of_band_dollars", "uplifts"];
const PIPELINE_LED_SECTIONS = ["overview", "uplift_rules", "pay_tables", "scenarios", "end_of_band_dollars", "uplifts"];

const SECTION_DESCRIPTIONS = {
  overview: "Document map, FWC metadata and early risk signals.",
  uplift_rules: "Wage-increase rules extracted from the agreement evidence.",
  pay_tables: "Extract, validate and accept wage tables from source pages.",
  scenarios: "Compare pay tables against uplift rules before promotion.",
  end_of_band_dollars: "Resolve current cash end-of-band amounts by governed operative period and band.",
  uplifts: "Read-only governed outputs promoted from validated evidence.",
};

const LOCAL_GROUP_SIZE = 5;
const EXTENDED_LOCAL_GROUP_SIZE = 12;
const DEFAULT_ANALYSIS_CHART_COHORT_KEY = "local_12";
const DEFAULT_ANALYSIS_CHART_DISTRIBUTION_COHORT_KEY = "statewide";
const WIKI_DEFAULT_COHORT_KEY = "statewide";
const WIKI_COHORT_KEYS = ["statewide", "local_5", "local_12", "lgv_category", "regional_victoria", "lgprf_group", "seifa_peer"];
const DEFAULT_ANALYSIS_CHART_BAND = "5";
const CHART_BASE_CURRENT = "current";
const CHART_BASE_FOUR_QUARTER_AVERAGE = "four_quarter_average";
const CHART_BASE_DATE_SMOOTHED = "date_smoothed";
const CHART_RANGE_NONE = "none";
const CHART_RANGE_IQR = "interquartile_range";
const CHART_RANGE_STD_DEV = "standard_deviation";
const REPORT_EXPORT_FORMAT_LABELS = {
  csv: "CSV",
  svg: "SVG",
  png: "PNG",
  xlsx: "XLSX",
  docx: "DOCX",
  pptx: "PPTX",
};
const REPORT_ASSET_LIFECYCLE_STATUSES = ["draft", "reviewed", "report_ready"];
const REPORT_ASSET_STATUS_LABELS = {
  draft: "Draft",
  reviewed: "Reviewed",
  report_ready: "Report ready",
  superseded: "Superseded",
  rejected: "Rejected",
};
const REVIEW_BOARD_AUTOMATION_DETAILS_KEY = "municipal-benchmark.review-board-automation-details.v1";
const ENTITLEMENT_QA_ACCEPTED_KEY = "municipal-benchmark.entitlement-qa-accepted.v1";
const WIKI_ENDPOINTS = {
  status: "/api/wiki/status",
  runs: "/api/wiki/runs",
  latestRun: "/api/wiki/runs/latest",
  documentMaps: "/api/wiki/document-maps",
  referenceInputs: "/api/wiki/reference-inputs",
  clauseLibrary: "/api/wiki/clause-library",
  tagRegistry: "/api/wiki/tag-registry",
  taggedEvidence: "/api/wiki/tagged-evidence",
  goldComparatorTarget: "/api/wiki/gold-comparator-target",
  questions: "/api/wiki/questions",
  learningBacklog: "/api/wiki/learning-backlog",
  languageMap: "/api/wiki/language-map",
  artifacts: "/api/wiki/artifacts",
  clauseCards: "/api/wiki/clause-cards",
  clauseIntelligence: "/api/wiki/clause-intelligence",
  entitlementTestMatrix: "/api/wiki/entitlement-test-matrix",
};

function loadReviewBoardAutomationDetailsOpen() {
  if (typeof window === "undefined" || !window.localStorage) return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(REVIEW_BOARD_AUTOMATION_DETAILS_KEY) || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([, value]) => typeof value === "boolean")
        .map(([key, value]) => [String(key).toLowerCase(), value]),
    );
  } catch {
    return {};
  }
}

function loadEntitlementQaAccepted() {
  if (typeof window === "undefined" || !window.localStorage) return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(ENTITLEMENT_QA_ACCEPTED_KEY) || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([, value]) => value === true)
        .map(([key, value]) => [String(key), value]),
    );
  } catch {
    return {};
  }
}

const state = {
  councils: [],
  councilsLoading: null,
  intakeRows: [],
  jobSourceRegistry: null,
  jobSourceRegistryLoading: null,
  jobScrapePreview: null,
  jobScrapePreviewLoading: null,
  jobScrapePreviewStarted: false,
  jobScrapePreviewLinkedDocuments: false,
  jobPipelineStage1: null,
  jobPipelineStage1Loading: null,
  jobPipelineFilter: "",
  jobPipelineStatus: "all",
  jobSecondaryPreview: null,
  jobSecondaryPreviewLoading: null,
  jobSecondaryPreviewStarted: false,
  jobAccumulator: null,
  jobAccumulatorLoading: null,
  jobAccumulatorStarted: false,
  jobAccumulatorFilter: "",
  jobEndpointResolution: null,
  jobEndpointResolutionLoading: null,
  jobEndpointResolutionStarted: false,
  councilReference: null,
  canonicalCouncils: [],
  canonicalLgas: new Set(),
  canonicalLgaTotal: null,
  intakeQuality: null,
  currentCouncil: null,
  currentSection: "overview",
  currentCapabilityBranch: "source_custody",
  currentCapabilityNode: "",
  capabilitySelectedAgreementId: "",
  capabilityReviewEntitlementId: "",
  capabilityReviewCouncilId: "",
  capabilityReviewStageFilter: "",
  entitlementQaSelectedEntitlementId: "",
  entitlementQaValuesOnly: false,
  entitlementQaAccepted: loadEntitlementQaAccepted(),
  pdfViewer: null,
  pdfPaneMode: "normal",
  pipelineSort: "default",
  intakeSort: "effective_date",
  intakeFilter: "",
  intakeStatusFilter: "all",
  intakeQuickFilter: "all",
  jobIntakeFilter: "",
  jobIntakeTier: "all",
  jobIntakePlatform: "all",
  jobIntakeStatus: "all",
  jobIntakeTab: "jobs",
  jobObservedFilter: "",
  jobObservedGovernance: "all",
  jobObservedPlatform: "all",
  jobObservedBand: "all",
  currentDataSet: "uplift_rules",
  analysisData: null,
  analysisDataByKind: {},
  ...createReportExportState(),
  auditCouncil: "",
  auditReport: null,
  auditReportByCouncil: {},
  analysisChartCohortKey: DEFAULT_ANALYSIS_CHART_COHORT_KEY,
  analysisChartDistributionCohortKey: DEFAULT_ANALYSIS_CHART_DISTRIBUTION_COHORT_KEY,
  analysisChartBaseMode: CHART_BASE_CURRENT,
  analysisChartRangeMode: CHART_RANGE_NONE,
  analysisChartQuarterStart: "",
  analysisChartBand: DEFAULT_ANALYSIS_CHART_BAND,
  overviewPreparation: {},
  upliftSuggestionExclusions: {},
  syntheticHumanReview: {},
  reviewBoardAutomationActiveAeId: "",
  reviewBoardAutomationDetailsOpen: loadReviewBoardAutomationDetailsOpen(),
  rateCapStatus: null,
  rateCapStatusLoad: null,
  wikiStatus: null,
  wikiRuns: null,
  wikiLatestRun: null,
  wikiDocumentMaps: null,
  wikiDocumentMapsLoading: null,
  wikiDocumentMapDetails: {},
  wikiReferenceInputs: null,
  wikiClauseLibrary: null,
  wikiTagRegistry: null,
  wikiTaggedEvidence: null,
  wikiTaggedEvidenceRows: [],
  wikiTaggedEvidenceLoading: null,
  wikiTaggedEvidenceKey: "",
  wikiTagFilter: "",
  wikiTagSourceType: "all",
  wikiTagRecordType: "all",
  wikiTagRelevance: "all",
  wikiTagQuery: "",
  wikiGoldComparatorTarget: null,
  wikiSelectedGoldEntitlementId: "",
  wikiSelectedClauseId: "",
  wikiComparatorCouncilKey: "",
  wikiComparatorCohortKey: WIKI_DEFAULT_COHORT_KEY,
  wikiQuestions: null,
  wikiBacklog: null,
  wikiLanguageMap: null,
  wikiArtifacts: null,
  wikiClauseCards: null,
  wikiClauseCardsLoading: null,
  wikiClauseIntelligence: null,
  wikiClauseIntelligenceLoading: null,
  agentCatalog: null,
  agentCatalogLoading: null,
  wikiSelectedAeId: "",
  wikiLoading: null,
  analysisFilter: "",
  analysisSort: "effective_date",
  llmStatus: null,
  llmConnections: null,
  lgaBoundaryGeojson: null,
  lgaBoundaryPrepared: null,
  lgaBoundaryLoad: null,
  payDraft: {
    tables: [],
    sourceRef: "",
    notes: "",
    status: "in_progress",
    candidatePages: [],
    payTablePages: [],
    upliftRulePages: [],
    rangeExtraction: null,
    rangeStart: null,
    rangeEnd: null,
    validations: [],
    editingJsonIndex: new Set(),
    reviewHints: [],
  },
  dateSuggestions: null,
};

const scenarioOverrides = new Map(); // ae_id -> { [period]: { ["band:level"]: { action, weekly? } } }
let _scenarioSavedAt = null;
let _scenarioSavedNotes = null;
let _scenarioAuditEvents = [];
let suppressWorkbenchRouteSync = false;
const quickSwitchState = {
  open: false,
  activeIndex: 0,
  results: [],
};
const RECENT_WORKBENCH_DESTINATIONS_KEY = "municipal-benchmark.recent-destinations.v1";
const RECENT_WORKBENCH_DESTINATIONS_LIMIT = 8;
const RECENT_WORKBENCH_ROUTE_PREFIXES = [
  "#capability",
  "#incoming",
  "#intake",
  "#job-intake",
  "#job-pipeline",
  "#matrix",
  "#workspace",
  "#data",
  "#analysis",
  "#audit",
  "#wiki",
  "#admin",
];

function normaliseSpatialKey(value) {
  return String(value || "").toUpperCase().replace(/[^A-Z0-9]+/g, " ").trim();
}

function selectedCouncilSpatialKey() {
  return normaliseSpatialKey(
    state.currentCouncil?.geography?.spatial_key
    || state.currentCouncil?.canonical_lga_short_name
    || state.currentCouncil?.geography?.short_name
  );
}

function ensureLgaBoundaryData() {
  if (state.lgaBoundaryGeojson) return Promise.resolve(state.lgaBoundaryGeojson);
  if (!state.lgaBoundaryLoad) {
    state.lgaBoundaryLoad = fetch("/static/data/victoria-lga-boundaries.geojson")
      .then((response) => {
        if (!response.ok) throw new Error(`Boundary layer failed: ${response.status}`);
        return response.json();
      })
      .then((geojson) => {
        state.lgaBoundaryGeojson = geojson;
        state.lgaBoundaryPrepared = prepareLgaBoundaryData(geojson);
        return geojson;
      })
      .catch((error) => {
        console.warn(error);
        state.lgaBoundaryLoad = null;
        return null;
      });
  }
  return state.lgaBoundaryLoad;
}

function lgaMapProject(point, bounds, width, height) {
  const [minLon, minLat, maxLon, maxLat] = bounds;
  const [lon, lat] = point;
  const x = ((lon - minLon) / (maxLon - minLon || 1)) * width;
  const y = ((maxLat - lat) / (maxLat - minLat || 1)) * height;
  return [Number(x.toFixed(2)), Number(y.toFixed(2))];
}

function lgaRingToPath(ring, bounds, width, height) {
  if (!Array.isArray(ring) || ring.length === 0) return "";
  return `${ring.map((point, index) => {
    const [x, y] = lgaMapProject(point, bounds, width, height);
    return `${index === 0 ? "M" : "L"}${x} ${y}`;
  }).join(" ")} Z`;
}

function lgaFeatureToPath(feature, bounds, width, height) {
  const geometry = feature?.geometry || {};
  const coordinates = geometry.coordinates || [];
  if (geometry.type === "Polygon") {
    return coordinates.map((ring) => lgaRingToPath(ring, bounds, width, height)).join(" ");
  }
  if (geometry.type === "MultiPolygon") {
    return coordinates.flatMap((polygon) => polygon.map((ring) => lgaRingToPath(ring, bounds, width, height))).join(" ");
  }
  return "";
}

function lgaFeatureBounds(feature) {
  if (feature?._lgaBounds) return feature._lgaBounds;
  const geometry = feature?.geometry || {};
  const polygons = geometry.type === "Polygon"
    ? [geometry.coordinates || []]
    : geometry.type === "MultiPolygon"
      ? geometry.coordinates || []
      : [];
  const xs = [];
  const ys = [];
  polygons.forEach((polygon) => {
    polygon.forEach((ring) => {
      ring.forEach((point) => {
        if (Array.isArray(point) && point.length >= 2) {
          xs.push(Number(point[0]));
          ys.push(Number(point[1]));
        }
      });
    });
  });
  if (!xs.length || !ys.length) return null;
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function prepareLgaBoundaryData(geojson) {
  const features = geojson?.features || [];
  features.forEach((feature) => {
    feature._lgaBounds = lgaFeatureBounds(feature);
  });
  const groups = lgaFeatureGroups(features);
  const insetWidth = 58;
  const insetHeight = 42;
  const insetBounds = paddedLgaBounds(
    geojson?.bbox || combineLgaBounds(features.map((feature) => feature._lgaBounds)),
    insetWidth,
    insetHeight,
  );
  const victoriaInsetPaths = insetBounds
    ? features.map((feature) => {
      const path = lgaFeatureToPath(feature, insetBounds, insetWidth, insetHeight);
      return path ? `<path d="${path}"></path>` : "";
    }).join("")
    : "";
  return {
    features,
    groups,
    insetBounds,
    insetWidth,
    insetHeight,
    victoriaInsetPaths,
  };
}

function combineLgaBounds(boundsList) {
  const validBounds = boundsList.filter(Boolean);
  if (!validBounds.length) return null;
  return validBounds.reduce((combined, bounds) => [
    Math.min(combined[0], bounds[0]),
    Math.min(combined[1], bounds[1]),
    Math.max(combined[2], bounds[2]),
    Math.max(combined[3], bounds[3]),
  ]);
}

function lgaBoundsCenter(bounds) {
  if (!bounds) return null;
  return [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
}

function numericLgaPoint(lon, lat) {
  const x = Number(lon);
  const y = Number(lat);
  return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
}

function lgaDistanceKm(a, b) {
  if (!a || !b) return Number.POSITIVE_INFINITY;
  const meanLat = ((a[1] + b[1]) / 2) * Math.PI / 180;
  const kmPerDegreeLat = 111.32;
  const kmPerDegreeLon = Math.cos(meanLat) * kmPerDegreeLat;
  return Math.hypot((a[0] - b[0]) * kmPerDegreeLon, (a[1] - b[1]) * kmPerDegreeLat);
}

function councilOfficePointLookup() {
  const lookup = new Map();
  const rows = state.councilReference?.rows || state.canonicalCouncils || [];
  rows.forEach((row) => {
    const point = numericLgaPoint(row.office_lon, row.office_lat);
    if (!point) return;
    [
      row.spatial_key,
      row.map_join_key,
      row.spatial_name,
      row.short_name,
      row.long_name,
      row.official_name,
    ].forEach((value) => {
      const key = normaliseSpatialKey(value);
      if (key && !lookup.has(key)) lookup.set(key, point);
    });
  });
  const currentOffice = state.currentCouncil?.geography?.office;
  const currentPoint = numericLgaPoint(currentOffice?.lon, currentOffice?.lat);
  const currentKey = selectedCouncilSpatialKey();
  if (currentKey && currentPoint && !lookup.has(currentKey)) lookup.set(currentKey, currentPoint);
  return lookup;
}

function lgaFeatureGroups(features) {
  const groups = new Map();
  features.forEach((feature) => {
    const key = normaliseSpatialKey(feature.properties?.spatial_key || feature.properties?.spatial_name);
    if (!key) return;
    const existing = groups.get(key) || {
      key,
      name: feature.properties?.spatial_name,
      features: [],
      bounds: null,
    };
    existing.features.push(feature);
    existing.bounds = combineLgaBounds([existing.bounds, feature._lgaBounds || lgaFeatureBounds(feature)]);
    groups.set(key, existing);
  });
  return groups;
}

function lgaGroupDistancePoint(group, officeLookup) {
  return officeLookup?.get(group?.key) || lgaBoundsCenter(group?.bounds);
}

function closestCouncilReferenceKeys(selectedKey, count = EXTENDED_LOCAL_GROUP_SIZE) {
  if (!selectedKey) return new Set();
  const officeLookup = councilOfficePointLookup();
  const selectedPoint = officeLookup.get(selectedKey);
  if (!selectedPoint) return new Set([selectedKey]);
  const rows = state.councilReference?.rows || state.canonicalCouncils || [];
  const neighbours = rows
    .filter((row) => row?.status === "active")
    .map((row) => {
      const key = normaliseSpatialKey(row.spatial_key || row.map_join_key || row.spatial_name || row.short_name);
      const point = officeLookup.get(key);
      return key && key !== selectedKey && point
        ? { key, distanceKm: lgaDistanceKm(selectedPoint, point), name: row.short_name || row.long_name || key }
        : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.distanceKm - b.distanceKm || String(a.name || "").localeCompare(String(b.name || "")))
    .slice(0, count);
  return new Set([selectedKey, ...neighbours.map((row) => row.key)]);
}

function closestLgaGroups(groups, selectedKey, count = EXTENDED_LOCAL_GROUP_SIZE) {
  const selected = groups.get(selectedKey);
  const officeLookup = councilOfficePointLookup();
  const selectedPoint = lgaGroupDistancePoint(selected, officeLookup);
  if (!selectedPoint) return [];
  return [...groups.values()]
    .filter((group) => group.key !== selectedKey && group.features.some((feature) => feature.properties?.is_reference_council !== false))
    .map((group) => ({
      ...group,
      distanceKm: lgaDistanceKm(selectedPoint, lgaGroupDistancePoint(group, officeLookup)),
    }))
    .sort((a, b) => a.distanceKm - b.distanceKm || String(a.name || "").localeCompare(String(b.name || "")))
    .slice(0, count);
}

function selectedCohortKeys(count = EXTENDED_LOCAL_GROUP_SIZE) {
  const selectedKey = selectedCouncilSpatialKey();
  if (!selectedKey) return new Set();
  const prepared = state.lgaBoundaryPrepared;
  const groups = prepared?.groups;
  if (!groups?.get) return closestCouncilReferenceKeys(selectedKey, count);
  return new Set([
    selectedKey,
    ...closestLgaGroups(groups, selectedKey, count).map((group) => group.key),
  ]);
}

function selectedLocalCohortKeys() {
  return selectedCohortKeys(LOCAL_GROUP_SIZE);
}

function selectedExtendedLocalCohortKeys() {
  return selectedCohortKeys(EXTENDED_LOCAL_GROUP_SIZE);
}

function paddedLgaBounds(bounds, width, height) {
  if (!bounds) return null;
  const [minLon, minLat, maxLon, maxLat] = bounds;
  const centerLon = (minLon + maxLon) / 2;
  const centerLat = (minLat + maxLat) / 2;
  const targetAspect = width / height;
  let lonSpan = Math.max(maxLon - minLon, 0.08);
  let latSpan = Math.max(maxLat - minLat, 0.08);
  if (lonSpan / latSpan > targetAspect) {
    latSpan = lonSpan / targetAspect;
  } else {
    lonSpan = latSpan * targetAspect;
  }
  lonSpan *= 1.18;
  latSpan *= 1.18;
  return [
    centerLon - lonSpan / 2,
    centerLat - latSpan / 2,
    centerLon + lonSpan / 2,
    centerLat + latSpan / 2,
  ];
}

function setPdfPaneMode(mode) {
  const nextMode = ["normal", "collapsed", "expanded"].includes(mode) ? mode : "normal";
  state.pdfPaneMode = nextMode;
  const workspaceMain = document.getElementById("workspace-main");
  if (workspaceMain) {
    workspaceMain.classList.toggle("pdf-collapsed", nextMode === "collapsed");
    workspaceMain.classList.toggle("pdf-expanded", nextMode === "expanded");
  }
  const collapseButton = document.getElementById("pdf-pane-collapse");
  if (collapseButton) {
    collapseButton.textContent = nextMode === "collapsed" ? "PDF" : "Collapse PDF";
    collapseButton.setAttribute("aria-label", nextMode === "collapsed" ? "Expand PDF pane" : "Collapse PDF pane to rail");
    collapseButton.setAttribute("aria-expanded", nextMode === "collapsed" ? "false" : "true");
    collapseButton.setAttribute("title", nextMode === "collapsed" ? "Expand PDF pane" : "Collapse PDF pane to rail");
  }
  const expandButton = document.getElementById("pdf-pane-expand");
  if (expandButton) {
    expandButton.textContent = nextMode === "expanded" ? "Normal PDF" : "Wide PDF";
    expandButton.setAttribute("aria-label", nextMode === "expanded" ? "Restore normal PDF width" : "Expand PDF pane");
  }
}

function togglePdfPaneCollapsed() {
  setPdfPaneMode(state.pdfPaneMode === "collapsed" ? "normal" : "collapsed");
}

function togglePdfPaneExpanded() {
  setPdfPaneMode(state.pdfPaneMode === "expanded" ? "normal" : "expanded");
}

const DATA_SET_CONFIG = {
  uplift_rules: {
    endpoint: "/api/analysis/uplift-rules",
    label: "Uplift Rules",
    title: "Uplift Rules",
    description: "First-class governed uplift records standardised across agreements before comparison, rate-cap review or scenario analysis.",
    runId: "UPLIFT-RULES",
    runMeta: "Promoted rules from governed agreement periods.",
    tableTitle: "Uplift Rules Entity Set",
    tableDescription: "Rules only appear here after they have been promoted into the governed set for an agreement period.",
    filterPlaceholder: "Filter council, agreement, pattern",
    patternHeading: "Pattern Mix",
    primaryLabel: "Promoted rules",
    primaryNote: "governed uplift records",
    agreementNote: "with governed uplift rules",
    secondaryLabel: "Rate-cap rules",
    secondaryNote: "using cap-linked logic",
    firstFilterLabel: "Rate-cap",
    firstFilterValue: "rate cap",
    secondFilterLabel: "Floor",
    secondFilterValue: "floor",
    sortOptions: [
      ["effective_date", "Sort: effective date"],
      ["council", "Sort: council"],
      ["pattern", "Sort: pattern"],
    ],
  },
  pay_tables: {
    endpoint: "/api/analysis/pay-tables",
    label: "Pay Tables",
    title: "Pay Tables",
    description: "Flattened governed weekly pay-table rows standardised across agreements as a data asset.",
    runId: "PAY-TABLES",
    runMeta: "Promoted pay-table rows from governed agreement periods.",
    tableTitle: "Pay Tables Data Asset",
    tableDescription: "One governed weekly rate row per agreement period and classification point, promoted from accepted evidence.",
    filterPlaceholder: "Filter council, agreement, band, level, table",
    patternHeading: "Weekly Basis Mix",
    primaryLabel: "Pay rows",
    primaryNote: "flattened governed rows",
    agreementNote: "with governed pay tables",
    secondaryLabel: "Pay tables",
    secondaryNote: "promoted governed tables",
    firstFilterLabel: "Weekly",
    firstFilterValue: "weekly",
    secondFilterLabel: "Governed",
    secondFilterValue: "governed",
    hideSidePanel: true,
    showCandidateDiagnostics: false,
    sortOptions: [
      ["effective_date", "Sort: effective date"],
      ["council", "Sort: council"],
      ["classification", "Sort: band / level"],
      ["weekly_rate", "Sort: weekly rate"],
    ],
  },
  end_of_band_dollars: {
    endpoint: "/api/analysis/end-of-band-dollars",
    label: "End of Band Dollars",
    title: "End of Band Dollars",
    description: "Band-level cash premiums above the current band top, derived after governed scenarios with clause evidence and calculation status.",
    runId: "EOB-DOLLARS",
    runMeta: "Derived from governed periods plus cached agreement text.",
    tableTitle: "End of Band Dollars Data Asset",
    tableDescription: "One row per governed operative period and band where an in-scope cash end-of-band amount can be resolved; midpoint formulas follow adjacent-band gaps, so amounts are not expected to rise monotonically by band.",
    filterPlaceholder: "Filter council, agreement, band, clause, basis",
    patternHeading: "Rule Mix",
    primaryLabel: "EOB rows",
    primaryNote: "band-period amounts",
    agreementNote: "with cash EOB",
    secondaryLabel: "Bands",
    secondaryNote: "period-band rows",
    firstFilterLabel: "Fixed",
    firstFilterValue: "fixed",
    secondFilterLabel: "Computed",
    secondFilterValue: "computed",
    hideSidePanel: true,
    sortOptions: [
      ["effective_date", "Sort: effective date"],
      ["council", "Sort: council"],
      ["band", "Sort: band"],
      ["amount", "Sort: amount"],
    ],
  },
  charts: {
    endpoint: "/api/analysis/distribution-point-analysis",
    sourceDataKind: "distribution_point_analysis",
    label: "Charts",
    title: "Charts",
    description: "Chart-ready views built from governed benchmark data, with selectable quarter, band and cohort inputs.",
    runId: "CHARTS",
    runMeta: "Visual benchmark layer derived from distribution point analysis.",
    tableTitle: "Pay Distribution",
    tableDescription: "Weekly midpoint rates matched where the selected quarter falls inside each operative uplift period.",
    filterPlaceholder: "Filter chart context",
    patternHeading: "Comparator Cohort",
    primaryLabel: "Active values",
    primaryNote: "selected band midpoint",
    agreementLabel: "Cohorts",
    agreementNote: "reporting peer sets plus statewide",
    secondaryLabel: "Cohort values",
    secondaryNote: "selected cohort average",
    dateLabel: "Quarter",
    dateNote: "selected snapshot",
    sourceInput: "Distribution Point Analysis",
    sourceUse: "Charts and benchmark views",
    hideTableControls: true,
    firstFilterLabel: "Selected",
    firstFilterValue: "",
    secondFilterLabel: "Local",
    secondFilterValue: "",
    sortOptions: [
      ["weekly_rate", "Sort: weekly rate"],
      ["council", "Sort: council"],
    ],
  },
  councils: {
    endpoint: "/api/reference/council-master",
    label: "Council Master",
    title: "Council Master",
    description: "Mother reference table for Victoria's 79 councils, joining spatial identity, cohort geography, electoral structure, performance context and governance coverage.",
    runId: "COUNCILS",
    runMeta: "Canonical councils joined to official reference and statistical context sources.",
    tableTitle: "Council Dimension",
    tableDescription: "Authoritative council names with category, region, electoral, spatial, governance and socioeconomic attributes.",
    filterPlaceholder: "Filter council, category, region, ward, SEIFA, status, code",
    patternHeading: "Council Category",
    primaryLabel: "Councils",
    primaryNote: "canonical rows",
    agreementLabel: "Active",
    agreementNote: "available for agreement matching",
    secondaryLabel: "Exceptions",
    secondaryNote: "missing or excluded",
    dateLabel: "Categories",
    dateNote: "council category groups",
    sourceInput: "Council master",
    sourceUse: "Cohorts and mapping",
    firstFilterLabel: "Active",
    firstFilterValue: "active",
    secondFilterLabel: "Exceptions",
    secondFilterValue: "missing excluded",
    sortOptions: [
      ["council", "Sort: council"],
      ["category", "Sort: category"],
      ["region", "Sort: region"],
      ["electoral", "Sort: councillors"],
      ["status", "Sort: status"],
    ],
  },
};

function isIso(v) { return isIsoDate(v); }

function htmlDisplay(value, empty = DISPLAY_EMPTY) {
  return displayHtml(value, escapeHtml, empty);
}

function recalcToDates(tables, nominatedExpiry, upliftRuleDates) {
  const groups = {};
  tables.forEach((t) => {
    const ef = (t.effective_from || "").trim();
    const kind = (t.rate_kind || "").trim() || "__unknown__";
    if (isIso(ef)) {
      if (!groups[kind]) groups[kind] = [];
      groups[kind].push([ef, t]);
    }
  });
  const addOneYear = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    const newY = y + 1;
    const isLeap = (yr) => yr % 4 === 0 && (yr % 100 !== 0 || yr % 400 === 0);
    const maxDay = (m === 2 && d === 29 && !isLeap(newY)) ? 28 : d;
    return `${newY}-${String(m).padStart(2, "0")}-${String(maxDay).padStart(2, "0")}`;
  };
  const minusOneDay = (iso) => {
    const dt = new Date(iso + "T00:00:00Z");
    dt.setUTCDate(dt.getUTCDate() - 1);
    return dt.toISOString().slice(0, 10);
  };
  // Uplift rule dates are used to cap the last table's to_date when a future-period
  // rule exists but no table for it has been extracted yet. Matches backend behaviour
  // in recalc_to_dates / get_uplift_rule_dates.
  const ruleDatesSorted = Array.isArray(upliftRuleDates)
    ? [...new Set(upliftRuleDates.filter((d) => isIso(d)))].sort()
    : [];
  Object.values(groups).forEach((items) => {
    items.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    items.forEach(([ef, t], i) => {
      if (i < items.length - 1) {
        const nextEf = items[i + 1][0];
        t.to_date = (nextEf === ef) ? null : minusOneDay(nextEf);
      } else {
        // Last in group: prefer earliest rule date strictly after this ef.
        const futureRuleDate = ruleDatesSorted.find((d) => d > ef);
        if (futureRuleDate) {
          t.to_date = minusOneDay(futureRuleDate);
        } else {
          t.to_date = nominatedExpiry || addOneYear(ef);
        }
      }
    });
  });
  return tables;
}

function collectUpliftRuleDates(council) {
  // Mirror backend get_uplift_rule_dates: read effective_date from accepted/suggestion/rules
  // in that priority order, return ISO-valid dates.
  try {
    const data = council?.sections?.uplift_rules?.data || {};
    const rules =
      (data.accepted && Array.isArray(data.accepted.rules) && data.accepted.rules)
      || (data.suggestion && data.suggestion.document && Array.isArray(data.suggestion.document.rules) && data.suggestion.document.rules)
      || (Array.isArray(data.rules) && data.rules)
      || [];
    const out = [];
    for (const r of rules) {
      const ed = (r?.effective_date || "").trim();
      if (isIso(ed)) out.push(ed);
    }
    return out;
  } catch {
    return [];
  }
}

function sortDraftTablesByEffectiveFrom() {
  // Sort tables chronologically by effective_from. Nulls/undefineds/non-ISO values sink to the bottom.
  // Non-ISO tables are secondarily sorted by effective_from_note then table_title.
  state.payDraft.tables.sort((a, b) => {
    const aDate = isIso(a?.effective_from) ? a.effective_from : "";
    const bDate = isIso(b?.effective_from) ? b.effective_from : "";
    if (!aDate && !bDate) {
      const aNoteTitle = (a?.effective_from_note || "") + "\x00" + (a?.table_title || "");
      const bNoteTitle = (b?.effective_from_note || "") + "\x00" + (b?.table_title || "");
      return aNoteTitle.localeCompare(bNoteTitle);
    }
    if (!aDate) return 1;
    if (!bDate) return -1;
    if (aDate !== bDate) return aDate.localeCompare(bDate);
    return (a?.table_title || "").localeCompare(b?.table_title || "");
  });
}

function applyToDateRecalc() {
  const nominatedExpiry = state.currentCouncil?.sections?.front_matter?.data?.nominated_expiry || null;
  const upliftRuleDates = collectUpliftRuleDates(state.currentCouncil);
  sortDraftTablesByEffectiveFrom();
  recalcToDates(state.payDraft.tables, nominatedExpiry, upliftRuleDates);
  // Overview shows live earliest/latest from draft tables — refresh it whenever draft dates change.
  try { renderOverview(); } catch { /* overview element may not be mounted yet */ }
}

function toast(msg, level = "info") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = `show ${level}`;
  setTimeout(() => {
    t.className = "";
  }, 3000);
}

async function withBusyButton(buttonId, busyLabel, fn) {
  const btn = document.getElementById(buttonId);
  if (!btn) return fn();
  const originalLabel = btn.innerHTML;
  const originalDisabled = btn.disabled;
  const originalBusy = btn.getAttribute("aria-busy");
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  btn.innerHTML = `<span class="spinner-char">?</span> ${busyLabel}`;
  try {
    return await fn();
  } finally {
    btn.disabled = originalDisabled;
    if (originalBusy === null) btn.removeAttribute("aria-busy");
    else btn.setAttribute("aria-busy", originalBusy);
    btn.innerHTML = originalLabel;
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function ensureReportExportCatalog({ force = false } = {}) {
  return ensureReportExportCatalogState(state, { force });
}

async function ensureAgentCatalog({ force = false } = {}) {
  if (!force && state.agentCatalog) return state.agentCatalog;
  if (!force && state.agentCatalogLoading) return state.agentCatalogLoading;
  state.agentCatalogLoading = api("/api/agent/datasets")
    .then((payload) => {
      state.agentCatalog = payload;
      return payload;
    })
    .finally(() => {
      state.agentCatalogLoading = null;
    });
  return state.agentCatalogLoading;
}

async function ensureRateCapStatus({ force = false } = {}) {
  if (!force && state.rateCapStatus) return state.rateCapStatus;
  if (!force && state.rateCapStatusLoad) return state.rateCapStatusLoad;
  state.rateCapStatusLoad = api("/api/rate-caps/status")
    .then((data) => {
      state.rateCapStatus = data;
      return data;
    })
    .finally(() => {
      state.rateCapStatusLoad = null;
    });
  return state.rateCapStatusLoad;
}

async function ensureWikiData({ force = false } = {}) {
  const loaded = state.wikiStatus
    && state.wikiRuns
    && state.wikiLatestRun
    && state.wikiDocumentMaps
    && state.wikiReferenceInputs
    && state.wikiClauseLibrary
    && state.wikiTagRegistry
    && state.wikiGoldComparatorTarget
    && state.wikiQuestions
    && state.wikiBacklog
    && state.wikiLanguageMap
    && state.wikiArtifacts;
  if (!force && loaded) return state.wikiLatestRun;
  if (!force && state.wikiLoading) return state.wikiLoading;
  state.wikiLoading = Promise.all([
    api(WIKI_ENDPOINTS.status),
    api(WIKI_ENDPOINTS.runs),
    api(WIKI_ENDPOINTS.latestRun),
    api(WIKI_ENDPOINTS.documentMaps),
    api(WIKI_ENDPOINTS.referenceInputs),
    api(WIKI_ENDPOINTS.clauseLibrary),
    api(WIKI_ENDPOINTS.tagRegistry),
    api(WIKI_ENDPOINTS.goldComparatorTarget),
    api(WIKI_ENDPOINTS.questions),
    api(WIKI_ENDPOINTS.learningBacklog),
    api(WIKI_ENDPOINTS.languageMap),
    api(WIKI_ENDPOINTS.artifacts),
  ])
    .then(([status, runs, latestRun, documentMaps, referenceInputs, clauseLibrary, tagRegistry, goldComparatorTarget, questions, backlog, languageMap, artifacts]) => {
      state.wikiStatus = status;
      state.wikiRuns = runs;
      state.wikiLatestRun = latestRun;
      state.wikiDocumentMaps = documentMaps;
      state.wikiReferenceInputs = referenceInputs;
      state.wikiClauseLibrary = clauseLibrary;
      state.wikiTagRegistry = tagRegistry;
      state.wikiGoldComparatorTarget = goldComparatorTarget;
      state.wikiQuestions = questions;
      state.wikiBacklog = backlog;
      state.wikiLanguageMap = languageMap;
      state.wikiArtifacts = artifacts;
      const maps = wikiDocumentMapRows();
      if (!state.wikiSelectedAeId && maps.length) {
        state.wikiSelectedAeId = String(maps[0].agreement_id || "").toLowerCase();
      }
      const firstClause = wikiAsArray(clauseLibrary?.categories)
        .flatMap((category) => wikiAsArray(category.children))
        .find((child) => child?.id);
      if (!state.wikiSelectedClauseId && firstClause) {
        state.wikiSelectedClauseId = firstClause.id;
      }
      const firstTag = wikiTagRegistryRows()[0];
      if (!state.wikiTagFilter && firstTag) {
        state.wikiTagFilter = firstTag.tag;
      }
      const firstGoldEntitlement = wikiGoldEntitlementRows().find((item) => item?.entitlement_id);
      if (!state.wikiSelectedGoldEntitlementId && firstGoldEntitlement) {
        state.wikiSelectedGoldEntitlementId = firstGoldEntitlement.entitlement_id;
      }
      return latestRun;
    })
    .finally(() => {
      state.wikiLoading = null;
    });
  return state.wikiLoading;
}

async function ensureWikiDocumentMaps({ force = false } = {}) {
  if (!force && state.wikiDocumentMaps) return state.wikiDocumentMaps;
  if (!force && state.wikiDocumentMapsLoading) return state.wikiDocumentMapsLoading;
  state.wikiDocumentMapsLoading = api(WIKI_ENDPOINTS.documentMaps)
    .then((payload) => {
      state.wikiDocumentMaps = payload;
      const rows = wikiDocumentMapRows();
      if (!state.wikiSelectedAeId && rows.length) {
        state.wikiSelectedAeId = String(rows[0].agreement_id || "").toLowerCase();
      }
      return payload;
    })
    .finally(() => {
      state.wikiDocumentMapsLoading = null;
    });
  return state.wikiDocumentMapsLoading;
}

async function ensureWikiDocumentMapDetail(aeId = state.wikiSelectedAeId, { force = false } = {}) {
  const key = String(aeId || "").toLowerCase();
  if (!key) return null;
  if (!force && state.wikiDocumentMapDetails[key]) return state.wikiDocumentMapDetails[key];
  const detail = await api(`${WIKI_ENDPOINTS.documentMaps}/${encodeURIComponent(key)}`);
  state.wikiDocumentMapDetails[key] = detail;
  return detail;
}

async function ensureWikiClauseIntelligence({ force = false } = {}) {
  if (!force && state.wikiClauseIntelligence) return state.wikiClauseIntelligence;
  if (!force && state.wikiClauseIntelligenceLoading) return state.wikiClauseIntelligenceLoading;
  state.wikiClauseIntelligenceLoading = api(WIKI_ENDPOINTS.clauseIntelligence)
    .then((payload) => {
      state.wikiClauseIntelligence = payload;
      state.wikiClauseCards = payload?.clause_cards || state.wikiClauseCards;
      return payload;
    })
    .finally(() => {
      state.wikiClauseIntelligenceLoading = null;
    });
  return state.wikiClauseIntelligenceLoading;
}

async function ensureCouncilRows() {
  if (state.councils.length) return state.councils;
  if (state.councilsLoading) return state.councilsLoading;
  state.councilsLoading = api("/api/councils")
    .then((rows) => {
      state.councils = Array.isArray(rows) ? rows : [];
      return state.councils;
    })
    .finally(() => {
      state.councilsLoading = null;
    });
  return state.councilsLoading;
}

function currentDataSetConfig() {
  return DATA_SET_CONFIG[state.currentDataSet] || DATA_SET_CONFIG.uplift_rules;
}

function analysisDataForKind(kind) {
  const config = DATA_SET_CONFIG[kind] || null;
  const sourceKind = config?.sourceDataKind;
  return state.analysisDataByKind[kind] || (sourceKind ? state.analysisDataByKind[sourceKind] : null) || null;
}

function setCurrentDataSet(kind) {
  const next = DATA_SET_CONFIG[kind] ? kind : "uplift_rules";
  if (state.currentDataSet === next) return;
  state.currentDataSet = next;
  state.analysisData = analysisDataForKind(next);
  state.analysisFilter = "";
  state.analysisSort = "effective_date";
  if (document.body.dataset.view === "analysis") syncWorkbenchRoute("analysis");
}

function dataSetButtonShouldRefresh(kind) {
  return kind === "uplift_rules" || kind === "pay_tables" || kind === "end_of_band_dollars";
}

function rebuildableAnalysisDataSet(kind = state.currentDataSet) {
  return ["uplift_rules", "pay_tables", "end_of_band_dollars"].includes(kind) ? kind : null;
}

function setAnalysisDataForKind(kind, data) {
  state.analysisDataByKind[kind] = data;
  const sourceKind = DATA_SET_CONFIG[kind]?.sourceDataKind;
  if (sourceKind) state.analysisDataByKind[sourceKind] = data;
  const activeSourceKind = DATA_SET_CONFIG[state.currentDataSet]?.sourceDataKind;
  if (state.currentDataSet === kind || activeSourceKind === kind) {
    state.analysisData = data;
  }
}

async function rebuildAndRefreshCurrentAnalysisDataSet() {
  const rebuildKind = rebuildableAnalysisDataSet();
  if (!rebuildKind) {
    await renderAnalysisWorkspace({ force: true });
    return;
  }
  await withBusyButton("analysis-refresh", "Rebuilding...", async () => {
    const status = document.getElementById("analysis-status");
    const config = currentDataSetConfig();
    if (status) status.textContent = `Rebuilding ${config.label.toLowerCase()} data set...`;
    const result = await api(`/api/analysis/${encodeURIComponent(rebuildKind)}/rebuild`, {
      method: "POST",
    });
    if (result?.analysis) {
      setAnalysisDataForKind(rebuildKind, result.analysis);
    }
    if (rebuildKind === "pay_tables") {
      delete state.analysisDataByKind.charts;
      delete state.analysisDataByKind.distribution_point_analysis;
      resetReportExportState(state);
    }
    const promoted = result?.rebuild?.promoted ?? 0;
    const changed = result?.rebuild?.agreements_changed ?? 0;
    toast(`Rebuilt ${config.label}: ${formatCount(promoted, "0")} promoted item(s) across ${formatCount(changed, "0")} agreement(s)`, "success");
    await renderAnalysisWorkspace({ force: !result?.analysis });
  });
}

function governanceStatusDefinition(status) {
  return GOVERNANCE_STATUS_CHIPS.find((item) => item.id === status) || {
    id: status || "candidate",
    label: displayCodeLabel(status || "candidate"),
    description: "",
  };
}

function capabilityStatusChip(status, extraClass = "") {
  const definition = governanceStatusDefinition(status);
  return `<span class="capability-status-chip capability-status-${escapeHtml(definition.id)} ${extraClass}" title="${escapeHtml(definition.description || definition.label)}">${escapeHtml(definition.label)}</span>`;
}

function capabilityTreeBranches() {
  return Array.isArray(WORKBENCH_CAPABILITY_TREE) ? WORKBENCH_CAPABILITY_TREE : [];
}

function capabilityPrimaryChildren(branch) {
  return Array.isArray(branch?.children) ? branch.children : [];
}

function capabilitySecondarySurfaces(branch) {
  return Array.isArray(branch?.secondarySurfaces) ? branch.secondarySurfaces : [];
}

function capabilityBranchNodes(branch) {
  return [...capabilityPrimaryChildren(branch), ...capabilitySecondarySurfaces(branch)];
}

function normaliseSidebarRouteKey(route) {
  return String(route || "").replace(/^#\/?/, "#").replace(/\/+$/, "");
}

function sidebarCapabilityTreeBranches() {
  const cloneChildren = (children = []) => children.map((node) => ({
    ...node,
    children: cloneChildren(node.children || []),
  }));
  return capabilityTreeBranches().map((branch) => ({
    ...branch,
    children: cloneChildren(branch.children || []),
  }));
}

function sidebarCapabilityBranchById(id) {
  const branches = sidebarCapabilityTreeBranches();
  return branches.find((branch) => branch.id === id) || branches[0] || null;
}

function capabilityBranchById(id) {
  const branches = capabilityTreeBranches();
  return branches.find((branch) => branch.id === id) || branches[0] || null;
}

function capabilityChildById(branch, nodeId) {
  if (!branch || !nodeId) return null;
  return capabilityBranchNodes(branch).find((node) => node.id === nodeId) || null;
}

function flattenCapabilityNodes(nodes = capabilityTreeBranches(), parent = null, options = {}) {
  const includeSecondary = options.includeSecondary !== false;
  return nodes.flatMap((node) => {
    const withParent = { ...node, parentId: parent?.id || null, parentLabel: parent?.label || "" };
    const descendants = includeSecondary
      ? [...(node.children || []), ...(node.secondarySurfaces || [])]
      : (node.children || []);
    return [withParent, ...flattenCapabilityNodes(descendants, node, options)];
  });
}

function capabilityNodeRoute(node) {
  return node?.route || "";
}

function capabilityNodeView(route) {
  const clean = String(route || "").replace(/^#\/?/, "");
  const [area] = clean.split("/").filter(Boolean);
  if (area === "data" || area === "analysis") return "analysis";
  if (area === "workspace") return "workspace";
  if (area === "capability") return "capability";
  if (area === "audit") return "audit";
  return area || "";
}

function capabilityNodeMatchesCurrent(node) {
  const route = capabilityNodeRoute(node);
  if (!route) return false;
  const clean = route.replace(/^#\/?/, "");
  const [area, detail, extra] = clean.split("/").filter(Boolean);
  const activeView = document.body.dataset.view || "incoming";
  if (area === "capability") {
    if (activeView !== "capability" || (detail || "source_custody") !== state.currentCapabilityBranch) return false;
    return extra ? state.currentCapabilityNode === extra : !state.currentCapabilityNode;
  }
  if (area === "data" || area === "analysis") {
    return activeView === "analysis" && (!detail || detail === state.currentDataSet);
  }
  if (area === "workspace") {
    if (activeView !== "workspace") return false;
    if (detail && !SECTION_LABELS[detail]) return false;
    const activeSection = SECTION_LABELS[state.currentSection] ? state.currentSection : "overview";
    return activeSection === (detail || "overview");
  }
  if (area === "audit") return activeView === "audit";
  return activeView === area;
}

function capabilityBranchMatchesCurrent(branch) {
  if (!branch) return false;
  if (capabilityNodeMatchesCurrent(branch)) return true;
  return flattenCapabilityNodes(capabilityBranchNodes(branch), branch).some((node) => {
    const view = capabilityNodeView(node.route);
    if (document.body.dataset.view !== view) return false;
    if (view === "analysis" && node.dataAnalysisKind) return node.dataAnalysisKind === state.currentDataSet;
    return true;
  });
}

function capabilityNodeMetaHtml(node) {
  const bits = [];
  if (node.status) bits.push(capabilityStatusChip(node.status));
  if (node.countSummary) bits.push(`<span class="capability-count-chip">${escapeHtml(node.countSummary)}</span>`);
  return bits.length ? `<span class="capability-node-meta">${bits.join("")}</span>` : "";
}

function capabilityIconHtml(icon, extraClass = "") {
  const iconPaths = {
    funnel: `<path d="M4 5h16l-6.4 7.2v4.9l-3.2 1.9v-6.8L4 5Z"></path>`,
    chart: `
      <path d="M4 19h16"></path>
      <path d="M7 16V9"></path>
      <path d="M12 16V5"></path>
      <path d="M17 16v-6"></path>
    `,
    database: `
      <ellipse cx="12" cy="5.5" rx="7" ry="3"></ellipse>
      <path d="M5 5.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"></path>
      <path d="M5 11.5v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"></path>
    `,
    globe: `
      <circle cx="12" cy="12" r="8.4"></circle>
      <path d="M3.6 12h16.8"></path>
      <path d="M12 3.6c2.1 2.2 3.2 5 3.2 8.4s-1.1 6.2-3.2 8.4"></path>
      <path d="M12 3.6C9.9 5.8 8.8 8.6 8.8 12s1.1 6.2 3.2 8.4"></path>
      <path d="M5.4 7.7h13.2"></path>
      <path d="M5.4 16.3h13.2"></path>
    `,
    shield: `
      <path d="M12 3.5 19 6v5.4c0 4.1-2.6 7.7-7 9.1-4.4-1.4-7-5-7-9.1V6l7-2.5Z"></path>
      <path d="m9 12 2 2 4-4"></path>
    `,
  };
  const iconPath = iconPaths[icon];
  if (!iconPath) return "";
  const classes = ["capability-icon", `capability-icon-${icon}`, extraClass].filter(Boolean).join(" ");
  return `
    <span class="${escapeHtml(classes)}" aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false" stroke-linecap="round">
        ${iconPath}
      </svg>
    </span>
  `;
}

function sidebarCapabilityNodeLabel(node) {
  const labelsByRoute = {
    "#intake": "Intake",
    "#job-intake": "Job Intake",
    "#job-pipeline": "Job Pipeline",
    "#matrix": "Review Board",
    "#data/councils": "Council Master",
    "#data/pay_tables": "Pay Tables",
    "#data/uplift_rules": "Uplift Rules",
    "#data/charts": "Charts",
    "#audit": "Council Audit",
    "#admin": "Settings",
  };
  return labelsByRoute[normaliseSidebarRouteKey(node?.route)] || node?.label || "";
}

function capabilityNodeButtonHtml(node, depth = 1) {
  const route = capabilityNodeRoute(node);
  const label = sidebarCapabilityNodeLabel(node);
  const attrs = [
    `class="capability-node capability-node-depth-${depth}"`,
    `data-capability-node-id="${escapeHtml(node.id)}"`,
  ];
  if (node.navId) attrs.push(`id="${escapeHtml(node.navId)}"`);
  if (route) attrs.push(`data-workbench-route="${escapeHtml(route)}"`);
  if (node.dataAnalysisKind) attrs.push(`data-analysis-kind="${escapeHtml(node.dataAnalysisKind)}"`);
  const description = node.description ? `<span class="capability-node-description">${escapeHtml(node.description)}</span>` : "";
  const slot = node.slot === "workspace_sections"
    ? `<nav id="sections-tabbar" class="sidebar-section-tabs capability-workspace-sections" aria-label="Agreement workspace sections"></nav>`
    : "";
  return `
    <button type="button" ${attrs.join(" ")}>
      <span class="capability-node-main">
        <span class="capability-node-label">${escapeHtml(label)}</span>
        ${description}
      </span>
      ${capabilityNodeMetaHtml(node)}
    </button>
    ${slot}
  `;
}

function renderCapabilityBranch(branch) {
  const openAttr = capabilityBranchMatchesCurrent(branch) ? " open" : "";
  const iconHtml = capabilityIconHtml(branch.icon, "capability-branch-icon")
    || '<span class="capability-icon capability-branch-icon capability-icon-empty" aria-hidden="true"></span>';
  const branchOpen = branch.route && !branch.hideOverviewLink ? `
    <button type="button" class="capability-branch-open" data-workbench-route="${escapeHtml(branch.route)}" data-capability-node-id="${escapeHtml(branch.id)}">
      <span class="capability-node-main">
        <span class="capability-node-label">${escapeHtml(`${branch.label} Overview`)}</span>
        <span class="capability-node-description">${escapeHtml(branch.description || "Open this production lane dashboard.")}</span>
      </span>
    </button>
  ` : "";
  const children = (branch.children || []).map((node) => capabilityNodeButtonHtml(node)).join("");
  const summaryAttrs = [
    `class="capability-branch-summary"`,
    `data-capability-node-id="${escapeHtml(branch.id)}"`,
    `title="${escapeHtml(`Expand or collapse ${branch.label}`)}"`,
  ];
  return `
    <details class="sidebar-nav-group capability-branch" data-capability-branch-id="${escapeHtml(branch.id)}"${openAttr}>
      <summary ${summaryAttrs.join(" ")}>
        ${iconHtml}
        <span class="capability-branch-copy">
          <span class="capability-branch-title">${escapeHtml(branch.label)}</span>
          <span class="capability-branch-description">${escapeHtml(branch.countSummary || "Branch cockpit")}</span>
        </span>
        ${capabilityStatusChip(branch.status, "capability-branch-status")}
      </summary>
      <nav class="capability-branch-children" aria-label="${escapeHtml(branch.label)}">
        ${branchOpen}
        ${children}
      </nav>
    </details>
  `;
}

function renderCapabilityTree() {
  const root = document.getElementById("capability-tree");
  if (!root) return;
  root.innerHTML = sidebarCapabilityTreeBranches().map(renderCapabilityBranch).join("");
  updateCapabilityTreeActiveState();
}

function updateCapabilityTreeActiveState() {
  const root = document.getElementById("capability-tree");
  if (!root) return;
  const branches = sidebarCapabilityTreeBranches();
  const nodes = flattenCapabilityNodes(branches, null, { includeSecondary: false });
  root.querySelectorAll("[data-capability-node-id]").forEach((element) => {
    const nodeId = element.dataset.capabilityNodeId;
    const node = nodes.find((item) => item.id === nodeId);
    const active = node ? capabilityNodeMatchesCurrent(node) : nodeId === state.currentCapabilityBranch;
    element.classList.toggle("active", active);
    element.classList.toggle("is-active", active);
    if (active) element.setAttribute("aria-current", "page");
    else element.removeAttribute("aria-current");
  });
  root.querySelectorAll("[data-capability-branch-id]").forEach((element) => {
    const branch = sidebarCapabilityBranchById(element.dataset.capabilityBranchId);
    const activeBranch = capabilityBranchMatchesCurrent(branch);
    element.classList.toggle("has-active", activeBranch);
    element.open = activeBranch;
  });
}

function wireCapabilityTreeNavigation() {
  const root = document.getElementById("capability-tree");
  if (!root) return;
  root.addEventListener("click", (event) => {
    const target = event.target.closest("[data-workbench-route]");
    if (!target || !root.contains(target)) return;
    event.preventDefault();
    const route = target.dataset.workbenchRoute;
    if (!route) return;
    openWorkbenchRoute(route).catch((error) => toast(apiErrorMessage(error), "error"));
  });
}

function capabilityArtifactPaths(branch) {
  const paths = [];
  const visit = (node) => {
    (node.artifactPaths || []).forEach((path) => paths.push(path));
    (node.children || []).forEach(visit);
    (node.secondarySurfaces || []).forEach(visit);
  };
  if (branch) visit(branch);
  return [...new Set(paths)];
}

function renderCapabilityBranchList() {
  const container = document.getElementById("capability-dashboard-branch-list");
  if (!container) return;
  container.innerHTML = "";
  container.hidden = true;
}

function renderCapabilityChildCard(node, selectedNodeId = "") {
  const artifacts = (node.artifactPaths || []).map((path) => `<code>${escapeHtml(path)}</code>`).join("");
  const selected = node.id === selectedNodeId;
  const kicker = selected
    ? "selected node"
    : node.surfaceGroup
    ? `${node.surfaceGroup} surface`
    : node.countSummary || node.parentLabel || "work object";
  const route = node.route ? `
    <button type="button" class="capability-open-btn" data-workbench-route="${escapeHtml(node.route)}">
      Open
    </button>
  ` : "";
  return `
    <article class="capability-detail-card${selected ? " is-selected" : ""}" data-capability-card-id="${escapeHtml(node.id)}">
      <div class="capability-detail-card-head">
        <div>
          <span class="capability-card-kicker">${escapeHtml(kicker)}</span>
          <h3>${escapeHtml(node.label)}</h3>
        </div>
        ${capabilityStatusChip(node.status)}
      </div>
      <p>${escapeHtml(node.description || "")}</p>
      <div class="capability-card-note">${escapeHtml(node.ownershipNote || "")}</div>
      ${artifacts ? `<div class="capability-artifact-list">${artifacts}</div>` : ""}
      ${route}
    </article>
  `;
}

function renderCapabilitySecondarySurfaces(branch, selectedNodeId = "") {
  const surfaces = capabilitySecondarySurfaces(branch);
  if (!surfaces.length) return "";
  return `
    <section class="capability-secondary-surface-panel" aria-label="${escapeHtml(branch.label)} secondary surfaces">
      <div class="capability-pipeline-head">
        <div>
          <span class="capability-card-kicker">Secondary surfaces</span>
          <h2>Reports & Diagnostics</h2>
        </div>
        <span class="capability-count-chip">${escapeHtml(`${surfaces.length} demoted`)}</span>
      </div>
      <div class="capability-secondary-surface-grid">
        ${surfaces.map((surface) => renderCapabilityChildCard(surface, selectedNodeId)).join("")}
      </div>
    </section>
  `;
}

function renderCapabilityPipelineStage(stage, index, selectedNodeId = "") {
  const selected = stage.nodeId === selectedNodeId || stage.id === selectedNodeId;
  const artifacts = (stage.artifactPaths || []).map((path) => `<code>${escapeHtml(path)}</code>`).join("");
  const openButton = stage.route ? `
    <button type="button" class="capability-pipeline-open" data-workbench-route="${escapeHtml(stage.route)}" aria-label="Open ${escapeHtml(stage.label)}">
      Open
    </button>
  ` : "";
  return `
    <article class="capability-pipeline-stage${selected ? " is-selected" : ""}" data-capability-pipeline-stage="${escapeHtml(stage.id || "")}">
      <div class="capability-pipeline-stage-index" aria-hidden="true">${escapeHtml(String(index + 1).padStart(2, "0"))}</div>
      <div class="capability-pipeline-stage-body">
        <div class="capability-pipeline-stage-head">
          <div>
            <span class="capability-card-kicker">${escapeHtml(stage.countSummary || "pipeline stage")}</span>
            <h3>${escapeHtml(stage.label || "")}</h3>
          </div>
          ${capabilityStatusChip(stage.status)}
        </div>
        <p>${escapeHtml(stage.description || "")}</p>
        ${artifacts ? `<div class="capability-artifact-list">${artifacts}</div>` : ""}
        ${openButton}
      </div>
    </article>
  `;
}

function renderCapabilityPipeline(branch, selectedNodeId = "") {
  const stages = branch.pipelineStages || [];
  if (!stages.length) return "";
  return `
    <section class="capability-pipeline-panel" aria-label="${escapeHtml(branch.pipelineLabel || `${branch.label} pipeline`)}">
      <div class="capability-pipeline-head">
        <div>
          <span class="capability-card-kicker">Operational lane</span>
          <h2>${escapeHtml(branch.pipelineLabel || `${branch.label} Pipeline`)}</h2>
        </div>
        <span class="capability-count-chip">${escapeHtml(`${stages.length} stages`)}</span>
      </div>
      <div class="capability-pipeline-track">
        ${stages.map((stage, index) => renderCapabilityPipelineStage(stage, index, selectedNodeId)).join("")}
      </div>
    </section>
  `;
}

function capabilityEntitlementQaIsOpen() {
  return document.body.dataset.view === "capability"
    && state.currentCapabilityBranch === "clause_intelligence"
    && !state.currentCapabilityNode;
}

function capabilityEntitlementQaEntitlementId(row, intelligence) {
  const explicit = String(row?.entitlement_id || "").trim();
  if (explicit) return explicit;
  const label = String(row?.entitlement_label || "").trim().toLowerCase();
  if (!label) return "";
  const entitlements = wikiAsArray(intelligence?.entitlement_test_matrix?.entitlements);
  const matched = entitlements.find((item) => String(item.entitlement_label || "").trim().toLowerCase() === label);
  return String(matched?.entitlement_id || "").trim();
}

function capabilityEntitlementQaHasHumanDecision(row) {
  return [
    row?.human_review_decision,
    row?.human_governance_result,
    row?.human_review_notes,
  ].some((value) => String(value || "").trim());
}

function capabilityEntitlementQaLane(row) {
  if (capabilityEntitlementQaHasHumanDecision(row)) return "governed";
  const machineState = String(row?.machine_cell_status || "").toLowerCase();
  const suggested = String(row?.codex_suggested_review_decision || "").toLowerCase();
  const confidence = String(row?.codex_confidence || "").toLowerCase();
  const blockers = capabilityReviewListValue(row?.blocker_signals);
  const failure = String(row?.failure_reason || row?.machine_failure_reason || "").trim();
  const hasClause = String(row?.clause_card_id || "").trim();
  const hasFeature = String(row?.feature_card_id || "").trim();
  if (failure || blockers.length || machineState.includes("blocked") || machineState.includes("no_candidate") || !hasClause) {
    return "blocked";
  }
  if (suggested === "correct" && confidence === "high" && hasFeature) return "ready";
  return "decision";
}

function capabilityEntitlementQaLaneLabel(lane) {
  const labels = {
    ready: "Ready to accept",
    decision: "Needs human decision",
    blocked: "Blocked: missing evidence",
    governed: "Already governed",
  };
  return labels[lane] || "Needs review";
}

function capabilityEntitlementQaReason(row, lane) {
  const blockers = capabilityReviewListValue(row?.blocker_signals);
  const risks = capabilityReviewListValue(row?.codex_risk_flags);
  const failure = String(row?.failure_reason || row?.machine_failure_reason || "").trim();
  if (lane === "ready") return "High-confidence evidence and value are present. Human confirmation is the remaining gate.";
  if (failure) return wikiDisplayLabel(failure);
  if (blockers.length) return `Scope or adjacent-clause blocker: ${blockers.map((item) => wikiDisplayLabel(item)).join(", ")}.`;
  if (!String(row?.clause_card_id || "").trim()) return "The machine could not locate a source clause strong enough to support the entitlement.";
  if (!String(row?.feature_card_id || "").trim()) return "A source clause exists, but the benchmarkable value or scope has not been extracted cleanly.";
  if (risks.length) return `Review risk: ${risks.map((item) => wikiDisplayLabel(item)).join(", ")}.`;
  if (String(row?.codex_confidence || "").toLowerCase() !== "high") return "The advisory confidence is not high enough for automatic acceptance.";
  return "A human judgement is needed before this fact can become report-safe.";
}

function capabilityEntitlementQaProposedFact(row) {
  const value = [row?.codex_suggested_value, row?.codex_suggested_unit].filter((item) => String(item || "").trim()).join(" ");
  const presence = String(row?.codex_suggested_provision_present || "").trim();
  if (value) return `${row.entitlement_label || "Entitlement"} = ${value}`;
  if (presence) return `${row.entitlement_label || "Entitlement"} presence = ${wikiDisplayLabel(presence)}`;
  return `${row.entitlement_label || "Entitlement"} needs classification`;
}

function capabilityEntitlementQaEvidenceSnippet(row) {
  const text = String(row?.evidence_span_text || row?.review_text || row?.best_excerpt || "").replace(/\s+/g, " ").trim();
  if (!text) return "No evidence excerpt is attached to this review item yet.";
  return text.length > 260 ? `${text.slice(0, 260).trim()}...` : text;
}

function capabilityEntitlementQaItems(intelligence) {
  const worksheetRows = wikiAsArray(intelligence?.human_review_worksheet?.rows);
  return worksheetRows.map((row) => {
    const lane = capabilityEntitlementQaLane(row);
    return {
      row,
      lane,
      entitlementId: capabilityEntitlementQaEntitlementId(row, intelligence),
      agreementId: String(row?.agreement_id || "").toLowerCase(),
      reason: capabilityEntitlementQaReason(row, lane),
    };
  });
}

function capabilityEntitlementQaSummary(intelligence, items) {
  const counts = { ready: 0, decision: 0, blocked: 0, governed: 0 };
  items.forEach((item) => {
    counts[item.lane] = (counts[item.lane] || 0) + 1;
  });
  counts.governed = Math.max(
    counts.governed,
    Number(intelligence?.summary?.governed_entitlement_rows || 0),
  );
  return counts;
}

function capabilityEntitlementQaStateCard(key, value, detail) {
  return `
    <article class="entitlement-qa-state-card entitlement-qa-state-${escapeHtml(key)}">
      <span>${escapeHtml(capabilityEntitlementQaLaneLabel(key))}</span>
      <strong>${escapeHtml(formatCount(value, "0"))}</strong>
      <p>${escapeHtml(detail)}</p>
    </article>
  `;
}

function capabilityEntitlementQaChoiceChips(lane) {
  const choices = lane === "blocked"
    ? ["Open source evidence", "Mark not found", "Send back to Wiki Base"]
    : ["Accept", "Edit value", "Needs more evidence", "Not applicable", "Reject"];
  return `
    <div class="entitlement-qa-choice-row" aria-label="Available review choices">
      ${choices.map((choice) => `<span>${escapeHtml(choice)}</span>`).join("")}
    </div>
  `;
}

function renderCapabilityEntitlementQaCard(item) {
  const row = item.row || {};
  const lane = item.lane;
  const page = String(row.page || "").trim();
  const refs = Number(row.reference_link_count || 0);
  const meta = [
    page ? `p.${page}` : "",
    refs ? `${formatCount(refs, "0")} reference${refs === 1 ? "" : "s"}` : "",
    row.codex_confidence ? `${wikiDisplayLabel(row.codex_confidence)} advisory` : "",
  ].filter(Boolean).join(" / ");
  return `
    <article class="entitlement-qa-card entitlement-qa-card-${escapeHtml(lane)}">
      <div class="entitlement-qa-card-head">
        <div>
          <span>${escapeHtml(capabilityEntitlementQaLaneLabel(lane))}</span>
          <h3>${escapeHtml(row.council || "Council")} / ${escapeHtml(row.entitlement_label || "Entitlement")}</h3>
        </div>
        <strong>${escapeHtml(meta || String(row.agreement_id || "").toUpperCase())}</strong>
      </div>
      <div class="entitlement-qa-proposed-fact">
        <span>Proposed fact</span>
        <p>${escapeHtml(capabilityEntitlementQaProposedFact(row))}</p>
      </div>
      <div class="entitlement-qa-card-grid">
        <section>
          <span>Why review?</span>
          <p>${escapeHtml(item.reason)}</p>
        </section>
        <section>
          <span>Evidence</span>
          <p>${escapeHtml(capabilityEntitlementQaEvidenceSnippet(row))}</p>
        </section>
        <section>
          <span>Choices</span>
          ${capabilityEntitlementQaChoiceChips(lane)}
        </section>
      </div>
      <div class="entitlement-qa-card-actions">
        <button
          type="button"
          class="capability-open-btn"
          data-entitlement-qa-open-review="1"
          data-entitlement-qa-entitlement="${escapeHtml(item.entitlementId)}"
          data-entitlement-qa-agreement="${escapeHtml(item.agreementId)}"
        >Open review workspace</button>
      </div>
    </article>
  `;
}

function renderCapabilityEntitlementQaAdvancedLinks() {
  const branch = capabilityBranchById("clause_intelligence");
  const surfaces = capabilitySecondarySurfaces(branch);
  if (!surfaces.length) return "";
  return `
    <details class="entitlement-qa-advanced">
      <summary>
        <span>Advanced / Diagnostics</span>
        <strong>${escapeHtml(formatCount(surfaces.length, "0"))} surfaces</strong>
      </summary>
      <div class="entitlement-qa-advanced-grid">
        ${surfaces.map((surface) => `
          <button type="button" data-workbench-route="${escapeHtml(surface.route || "")}">
            <span>${escapeHtml(surface.surfaceGroup || "Advanced")}</span>
            <strong>${escapeHtml(surface.label || "Surface")}</strong>
            <small>${escapeHtml(surface.description || "")}</small>
          </button>
        `).join("")}
      </div>
    </details>
  `;
}

function saveEntitlementQaAccepted() {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(ENTITLEMENT_QA_ACCEPTED_KEY, JSON.stringify(state.entitlementQaAccepted || {}));
  } catch {
    // Local acceptance state is only a front-end review convenience until worksheet writeback exists.
  }
}

function entitlementQaAcceptanceKey(entitlementId, agreementId) {
  return `${String(entitlementId || "").toLowerCase()}::${String(agreementId || "").toLowerCase()}`;
}

function capabilityEntitlementQaSelectedEntitlement(intelligence) {
  const entitlements = wikiAsArray(intelligence?.entitlement_test_matrix?.entitlements);
  if (!entitlements.length) return null;
  const current = entitlements.find((item) => item.entitlement_id === state.entitlementQaSelectedEntitlementId);
  if (current) return current;
  const preferred = entitlements.find((item) => Number(item.feature_card_ready || 0) > 0)
    || entitlements.find((item) => Number(item.clause_card_ready || 0) > 0)
    || entitlements[0];
  state.entitlementQaSelectedEntitlementId = preferred.entitlement_id;
  return preferred;
}

function capabilityEntitlementQaWorksheetForCell(intelligence, entitlement, cell, target) {
  const rows = wikiAsArray(intelligence?.human_review_worksheet?.rows);
  const agreementId = String(cell?.agreement_id || target?.agreement_id || "").toLowerCase();
  const label = String(entitlement?.entitlement_label || cell?.entitlement_label || "").toLowerCase();
  return rows.find((row) => (
    String(row.agreement_id || "").toLowerCase() === agreementId
    && String(row.entitlement_label || "").toLowerCase() === label
  )) || null;
}

function capabilityEntitlementQaPrimaryValue(cell, worksheetRow) {
  const normalised = wikiAsArray(cell?.normalised_values).find((item) => item?.value || item?.unit) || null;
  if (normalised) {
    const text = [normalised.value, normalised.unit].filter((item) => String(item || "").trim()).join(" ");
    return {
      text,
      value: String(normalised.value || "").trim(),
      unit: String(normalised.unit || "").trim(),
      condition: normalised.condition || normalised.subclass_label || "",
    };
  }
  const suggestedValue = String(worksheetRow?.codex_suggested_value || "").trim();
  const suggestedUnit = String(worksheetRow?.codex_suggested_unit || "").trim();
  return {
    text: [suggestedValue, suggestedUnit].filter(Boolean).join(" "),
    value: suggestedValue,
    unit: suggestedUnit,
    condition: worksheetRow?.codex_suggested_scope || "",
  };
}

function capabilityEntitlementQaOutcome(item) {
  if (item.accepted) {
    return item.value.text ? `Accepted value: ${item.value.text}.` : "Accepted no reportable value for this council.";
  }
  const blockers = wikiAsArray(item.cell?.blocker_signals).length
    ? wikiAsArray(item.cell?.blocker_signals)
    : capabilityReviewListValue(item.worksheetRow?.blocker_signals);
  if (item.value.text) {
    const condition = item.value.condition ? ` (${wikiDisplayLabel(item.value.condition)})` : "";
    return `Value found: ${item.value.text}${condition}.`;
  }
  if (blockers.length) return `Blocked by ${blockers.map((value) => wikiDisplayLabel(value)).join(", ")}.`;
  if (item.cell?.clause_cards === "ready") return "Clause found; no normalised value yet.";
  if (item.cell?.document_spine !== "ready") return "Source map missing.";
  if (String(item.cell?.machine_state || "").includes("no_candidate")) return "No source clause located.";
  return wikiDisplayLabel(item.cell?.machine_state || "No value found");
}

function capabilityEntitlementQaRowState(item) {
  if (item.accepted) return "Accepted";
  if (item.value.text) return "Value";
  if (item.cell?.clause_cards === "ready") return "Needs value";
  if (wikiAsArray(item.cell?.blocker_signals).length || String(item.cell?.machine_state || "").includes("blocked")) return "Blocked";
  return "No value";
}

function capabilityEntitlementQaQuoteText(item) {
  const feature = wikiAsArray(item.cell?.feature_card_previews)[0] || {};
  const clause = wikiAsArray(item.cell?.clause_card_previews)[0] || {};
  return String(
    item.worksheetRow?.evidence_span_text
    || item.cell?.review_text
    || feature.evidence_text
    || feature.evidence_span
    || clause.text
    || item.cell?.best_excerpt
    || "",
  ).replace(/\s+/g, " ").trim();
}

function capabilityEntitlementQaHighlightValue(text, value) {
  const candidates = [
    value?.text,
    value?.value && value?.unit ? `${value.value} ${value.unit}` : "",
    String(value?.value || "").length >= 2 ? value.value : "",
  ].map((item) => String(item || "").trim()).filter(Boolean);
  const lower = text.toLowerCase();
  for (const candidate of [...new Set(candidates)].sort((a, b) => b.length - a.length)) {
    const index = lower.indexOf(candidate.toLowerCase());
    if (index < 0) continue;
    return `${escapeHtml(text.slice(0, index))}<mark>${escapeHtml(text.slice(index, index + candidate.length))}</mark>${escapeHtml(text.slice(index + candidate.length))}`;
  }
  return escapeHtml(text);
}

function capabilityEntitlementQaQuoteHtml(item) {
  const text = capabilityEntitlementQaQuoteText(item);
  const page = item.cell?.best_page || item.worksheetRow?.page || wikiAsArray(item.cell?.clause_card_previews)[0]?.page || "";
  if (!text) {
    return `<p class="entitlement-qa-row-quote is-empty">No clause quote attached.</p>`;
  }
  const clipped = text.length > 340 ? `${text.slice(0, 340).trim()}...` : text;
  return `
    <p class="entitlement-qa-row-quote">
      ${page ? `<span>p.${escapeHtml(page)}</span>` : ""}
      ${capabilityEntitlementQaHighlightValue(clipped, item.value)}
    </p>
  `;
}

function capabilityEntitlementQaCouncilItems(intelligence, selectedEntitlement) {
  const matrix = intelligence?.entitlement_test_matrix || {};
  const cells = capabilityReviewCells(matrix, selectedEntitlement?.entitlement_id);
  return capabilityReviewTargets(matrix).map((target) => {
    const cell = capabilityReviewCellForTarget(cells, target) || {
      agreement_id: target.agreement_id,
      council: target.council,
      entitlement_id: selectedEntitlement?.entitlement_id,
      entitlement_label: selectedEntitlement?.entitlement_label,
      document_spine: "missing",
      clause_cards: "missing",
      feature_cards: "missing",
      machine_state: "not_profiled",
    };
    const worksheetRow = capabilityEntitlementQaWorksheetForCell(intelligence, selectedEntitlement, cell, target);
    const value = capabilityEntitlementQaPrimaryValue(cell, worksheetRow);
    const agreementId = String(cell.agreement_id || target.agreement_id || "").toLowerCase();
    const accepted = Boolean(state.entitlementQaAccepted?.[entitlementQaAcceptanceKey(selectedEntitlement?.entitlement_id, agreementId)]);
    const item = { target, cell, worksheetRow, value, accepted, entitlement: selectedEntitlement, agreementId };
    item.outcome = capabilityEntitlementQaOutcome(item);
    item.state = capabilityEntitlementQaRowState(item);
    return item;
  }).sort((left, right) => String(left.target?.council || left.agreementId).localeCompare(String(right.target?.council || right.agreementId)));
}

function renderCapabilityEntitlementQaListRow(item) {
  return `
    <article class="entitlement-qa-list-row${item.accepted ? " is-accepted" : ""}${item.value.text ? " has-value" : ""}">
      <div class="entitlement-qa-council-cell">
        <strong>${escapeHtml(item.target?.council || item.cell?.council || item.agreementId.toUpperCase())}</strong>
        <span>${escapeHtml(item.agreementId.toUpperCase())}</span>
      </div>
      <div class="entitlement-qa-outcome-cell">
        <div class="entitlement-qa-outcome-line">
          <span>${escapeHtml(item.state)}</span>
          <p>${escapeHtml(item.outcome)}</p>
        </div>
        ${capabilityEntitlementQaQuoteHtml(item)}
      </div>
      <div class="entitlement-qa-row-actions">
        <button
          type="button"
          class="entitlement-qa-open-link"
          data-entitlement-qa-open-review="1"
          data-entitlement-qa-entitlement="${escapeHtml(item.entitlement?.entitlement_id || "")}"
          data-entitlement-qa-agreement="${escapeHtml(item.agreementId)}"
        >Open</button>
        <button
          type="button"
          class="entitlement-qa-accept-btn${item.accepted ? " is-accepted" : ""}"
          data-entitlement-qa-accept="1"
          data-entitlement-qa-entitlement="${escapeHtml(item.entitlement?.entitlement_id || "")}"
          data-entitlement-qa-agreement="${escapeHtml(item.agreementId)}"
          title="Prototype local acceptance; governed worksheet writeback is not wired yet."
        >${item.accepted ? "Accepted" : "Accept"}</button>
      </div>
    </article>
  `;
}

function renderCapabilityEntitlementQaInbox(intelligence) {
  const matrix = intelligence?.entitlement_test_matrix || {};
  const entitlements = wikiAsArray(matrix.entitlements);
  const selectedEntitlement = capabilityEntitlementQaSelectedEntitlement(intelligence);
  const rows = selectedEntitlement ? capabilityEntitlementQaCouncilItems(intelligence, selectedEntitlement) : [];
  const visibleRows = state.entitlementQaValuesOnly ? rows.filter((item) => item.value.text) : rows;
  const valueRows = rows.filter((item) => item.value.text);
  const acceptedRows = rows.filter((item) => item.accepted);
  const freshness = intelligence?.pipeline_freshness;
  const freshnessText = freshness?.status === "current"
    ? "Checks current"
    : `${formatCount(freshness?.stale_stages, "0")} check stage(s) need refresh.`;
  return `
    <section id="entitlement-qa-inbox" class="entitlement-qa-inbox" aria-label="Entitlement QA Inbox">
      <div class="entitlement-qa-compact-head">
        <div>
          <h2>Entitlement QA Inbox</h2>
          <p>${escapeHtml(formatCount(rows.length, "0"))} councils / ${escapeHtml(formatCount(valueRows.length, "0"))} with values / ${escapeHtml(formatCount(acceptedRows.length, "0"))} accepted</p>
        </div>
        <div class="entitlement-qa-run-panel">
          <button type="button" id="entitlement-qa-run-checks">Run available checks</button>
          <span>${escapeHtml(freshnessText)}</span>
        </div>
      </div>

      <div class="entitlement-qa-toolbar">
        <label>
          <span>Entitlement</span>
          <select data-entitlement-qa-entitlement aria-label="Entitlement">
            ${entitlements.map((item) => `
              <option value="${escapeHtml(item.entitlement_id)}"${item.entitlement_id === selectedEntitlement?.entitlement_id ? " selected" : ""}>
                ${escapeHtml(item.entitlement_label || item.entitlement_id)}
              </option>
            `).join("")}
          </select>
        </label>
        <label class="entitlement-qa-filter-toggle">
          <input type="checkbox" data-entitlement-qa-values-only ${state.entitlementQaValuesOnly ? "checked" : ""}>
          <span>With values only</span>
        </label>
        <div class="entitlement-qa-toolbar-note">
          <strong>${escapeHtml(formatCount(visibleRows.length, "0"))}</strong>
          <span>${state.entitlementQaValuesOnly ? "value rows shown" : "council rows shown"}</span>
        </div>
      </div>

      <section class="entitlement-qa-ledger">
        <div class="entitlement-qa-ledger-head" aria-hidden="true">
          <span>Council</span>
          <span>Human-readable outcome and source clause</span>
          <span>Action</span>
        </div>
        ${visibleRows.length ? visibleRows.map(renderCapabilityEntitlementQaListRow).join("") : renderEmptyState("No value rows", "This entitlement has no council rows with a normalised value yet.", { eyebrow: "Entitlement QA" })}
      </section>

      <section class="entitlement-qa-governed-band">
        <div>
          <span class="capability-card-kicker">Promotion posture</span>
          <h3>Governed evidence remains the reporting boundary</h3>
          <p>Accepted entitlement measures are still consumed through the governed entitlement output, not from the inbox itself.</p>
        </div>
        <button type="button" class="capability-open-btn" data-workbench-route="#capability/clause_intelligence/governed_entitlement_measures">Open governed measures</button>
      </section>

      ${renderCapabilityEntitlementQaAdvancedLinks()}
    </section>
  `;
}

function renderCapabilityEntitlementQaInboxLoading() {
  return `
    <section id="entitlement-qa-inbox" class="entitlement-qa-inbox">
      <div class="wiki-loading-row">Preparing entitlement QA inbox...</div>
    </section>
  `;
}

function wireCapabilityEntitlementQaInbox(root = document.getElementById("entitlement-qa-inbox")) {
  if (!root) return;
  const rerender = () => {
    const host = document.getElementById("entitlement-qa-inbox");
    if (!host || !state.wikiClauseIntelligence) return;
    host.outerHTML = renderCapabilityEntitlementQaInbox(state.wikiClauseIntelligence);
    wireCapabilityEntitlementQaInbox();
  };
  root.querySelectorAll("[data-workbench-route]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const route = button.dataset.workbenchRoute;
      if (!route) return;
      openWorkbenchRoute(route).catch((error) => toast(apiErrorMessage(error), "error"));
    });
  });
  root.querySelectorAll("[data-entitlement-qa-open-review]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const entitlementId = String(button.dataset.entitlementQaEntitlement || "");
      const agreementId = String(button.dataset.entitlementQaAgreement || "").toLowerCase();
      if (entitlementId) state.capabilityReviewEntitlementId = entitlementId;
      if (agreementId) state.capabilityReviewCouncilId = agreementId;
      state.capabilityReviewStageFilter = "all";
      openWorkbenchRoute("#capability/clause_intelligence/feature_cards").catch((error) => toast(apiErrorMessage(error), "error"));
    });
  });
  root.querySelector("[data-entitlement-qa-entitlement]")?.addEventListener("change", (event) => {
    state.entitlementQaSelectedEntitlementId = String(event.target.value || "");
    rerender();
  });
  root.querySelector("[data-entitlement-qa-values-only]")?.addEventListener("change", (event) => {
    state.entitlementQaValuesOnly = Boolean(event.target.checked);
    rerender();
  });
  root.querySelectorAll("[data-entitlement-qa-accept]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      const key = entitlementQaAcceptanceKey(button.dataset.entitlementQaEntitlement, button.dataset.entitlementQaAgreement);
      if (!key.replace(/:/g, "")) return;
      if (state.entitlementQaAccepted[key]) delete state.entitlementQaAccepted[key];
      else state.entitlementQaAccepted[key] = true;
      saveEntitlementQaAccepted();
      rerender();
      toast(state.entitlementQaAccepted[key] ? "Entitlement outcome accepted for this review session" : "Entitlement acceptance cleared", "success");
    });
  });
  const runButton = root.querySelector("#entitlement-qa-run-checks");
  runButton?.addEventListener("click", async () => {
    const originalLabel = runButton.innerHTML;
    runButton.disabled = true;
    runButton.setAttribute("aria-busy", "true");
    runButton.textContent = "Checking...";
    try {
      const intelligence = await ensureWikiClauseIntelligence({ force: true });
      if (!capabilityEntitlementQaIsOpen()) return;
      const host = document.getElementById("entitlement-qa-inbox");
      if (!host) return;
      host.outerHTML = renderCapabilityEntitlementQaInbox(intelligence);
      wireCapabilityEntitlementQaInbox();
      toast("Available entitlement checks refreshed", "success");
    } catch (error) {
      runButton.disabled = false;
      runButton.removeAttribute("aria-busy");
      runButton.innerHTML = originalLabel;
      toast(apiErrorMessage(error), "error");
    }
  });
}

async function hydrateCapabilityEntitlementQaInbox() {
  const host = document.getElementById("entitlement-qa-inbox");
  if (!host) return;
  try {
    await ensureCouncilRows();
    const intelligence = await ensureWikiClauseIntelligence();
    if (!capabilityEntitlementQaIsOpen()) return;
    const target = document.getElementById("entitlement-qa-inbox");
    if (!target) return;
    target.outerHTML = renderCapabilityEntitlementQaInbox(intelligence);
    wireCapabilityEntitlementQaInbox();
  } catch (error) {
    const target = document.getElementById("entitlement-qa-inbox");
    if (!target || !capabilityEntitlementQaIsOpen()) return;
    target.innerHTML = renderEmptyState("QA inbox failed to load", apiErrorMessage(error), { eyebrow: "Entitlement QA" });
  }
}

function payUpliftAgreementRows() {
  return [...(state.councils || [])]
    .filter((item) => item?.ae_id)
    .sort((a, b) => {
      const lgaA = (a.canonical_lga_short_name || "").toLowerCase();
      const lgaB = (b.canonical_lga_short_name || "").toLowerCase();
      return lgaA.localeCompare(lgaB)
        || String(a.source_name || a.ae_id).localeCompare(String(b.source_name || b.ae_id));
    });
}

function payUpliftNextAction(item) {
  const statuses = item?.section_statuses || {};
  const section = PIPELINE_LED_SECTIONS.find((key) => statuses[key] !== "done");
  if (!section) {
    return {
      section: "uplifts",
      label: "Open governed set",
      tone: "complete",
    };
  }
  const status = statuses[section] || "not_started";
  const verb = status === "not_started" ? "Start" : "Review";
  return {
    section,
    label: `${verb} ${MATRIX_SECTION_LABELS[section] || SECTION_LABELS[section] || section}`,
    tone: pipelineLedState(status).tone,
  };
}

function payUpliftHumanQaStatus(item, section) {
  const qaStatuses = item?.human_qa_statuses || {};
  const recorded = qaStatuses[section];
  if (typeof recorded === "string") return recorded;
  const status = (item?.section_statuses || {})[section] || "not_started";
  if (status === "not_started") return "not_started";
  if (status === "done") return "missing";
  return "open";
}

function payUpliftHumanQaAlertSections(item) {
  return PIPELINE_LED_SECTIONS.filter((section) => {
    const qaStatus = payUpliftHumanQaStatus(item, section);
    return qaStatus !== "accepted" && qaStatus !== "not_started";
  });
}

function payUpliftHumanQaAlertTitle(item, sections = payUpliftHumanQaAlertSections(item)) {
  if (!sections.length) return "Human QA accepted where work exists";
  const labels = sections.map((section) => MATRIX_SECTION_LABELS[section] || SECTION_LABELS[section] || section);
  return `Human QA not accepted: ${labels.join(", ")}`;
}

function payUpliftWorklistSummary(rows) {
  const allDone = rows.filter((row) => PIPELINE_LED_SECTIONS.every((section) => (row.section_statuses || {})[section] === "done")).length;
  const qaAlerts = rows.filter((row) => payUpliftHumanQaAlertSections(row).length).length;
  const untouched = rows.filter((row) => PIPELINE_LED_SECTIONS.every((section) => ((row.section_statuses || {})[section] || "not_started") === "not_started")).length;
  return { allDone, qaAlerts, untouched };
}

function renderPayUpliftWorklistRow(item) {
  const statuses = item.section_statuses || {};
  const action = payUpliftNextAction(item);
  const qaAlertSections = payUpliftHumanQaAlertSections(item);
  const qaAlertTitle = payUpliftHumanQaAlertTitle(item, qaAlertSections);
  const qaAlertSection = qaAlertSections[0] || action.section || "overview";
  const council = item.canonical_lga_short_name || item.fetch_metadata?.lga_short_name || "Unassigned council";
  const agreement = item.source_name || item.fetch_metadata?.["Agreement Title"] || item.ae_id || "Agreement";
  const aeId = String(item.ae_id || "").toUpperCase();
  return `
    <article class="pay-uplift-worklist-row" data-pay-uplift-row="${escapeHtml(item.ae_id || "")}">
      <div class="pay-uplift-agreement-cell">
        <strong>${escapeHtml(council)}</strong>
        <span>${escapeHtml(agreement)}</span>
        <code>${escapeHtml(aeId)}</code>
      </div>
      <div class="pay-uplift-qa-cell">
        ${qaAlertSections.length ? `
          <button
            type="button"
            class="pay-uplift-qa-alert"
            title="${escapeHtml(qaAlertTitle)}"
            aria-label="${escapeHtml(qaAlertTitle)}"
            data-pay-uplift-open="${escapeHtml(item.ae_id || "")}"
            data-pay-uplift-section="${escapeHtml(qaAlertSection)}"
          ><span aria-hidden="true">!</span></button>
        ` : `<span class="pay-uplift-qa-clear" title="${escapeHtml(qaAlertTitle)}" aria-label="${escapeHtml(qaAlertTitle)}"></span>`}
      </div>
      <div class="pay-uplift-led-cell">
        ${renderPipelineStatusLeds(statuses, "pay-uplift-row-leds")}
      </div>
      <div class="pay-uplift-action-cell">
        <button
          type="button"
          class="pay-uplift-open-btn pay-uplift-open-${escapeHtml(action.tone)}"
          data-pay-uplift-open="${escapeHtml(item.ae_id || "")}"
          data-pay-uplift-section="${escapeHtml(action.section)}"
        >${escapeHtml(action.label)}</button>
      </div>
    </article>
  `;
}

function renderPayUpliftWorklist() {
  const rows = payUpliftAgreementRows();
  const summary = payUpliftWorklistSummary(rows);
  const nextRow = rows.find((row) => firstOpenReviewSection(row)) || rows[0] || null;
  const nextAction = nextRow ? payUpliftNextAction(nextRow) : null;
  const nextButton = nextRow ? `
    <button
      type="button"
      class="pay-uplift-next-btn"
      data-pay-uplift-open="${escapeHtml(nextRow.ae_id || "")}"
      data-pay-uplift-section="${escapeHtml(nextAction.section)}"
    >Open next action</button>
  ` : "";
  return `
    <section class="pay-uplift-worklist" aria-label="Quantum and timing agreement worklist">
      <div class="pay-uplift-worklist-head">
        <div>
          <span class="capability-card-kicker">Agreement worklist</span>
          <h2>${capabilityIconHtml("funnel", "pay-uplift-title-icon")}<span>Quantum &amp; Timing Pipeline</span></h2>
          <p>Each agreement carries the same six-stage LED strip used inside the workspace. Green means the section status is complete, red needs human attention, black has not started.</p>
          <p class="pay-uplift-worklist-note">The amber alert marks stages where work exists but the Human QA gate is not accepted.</p>
        </div>
        <div class="pay-uplift-summary-panel">
          <div><span>Agreements</span><strong>${escapeHtml(formatCount(rows.length, "0"))}</strong></div>
          <div><span>Status complete</span><strong>${escapeHtml(formatCount(summary.allDone, "0"))}</strong></div>
          <div><span>QA alerts</span><strong>${escapeHtml(formatCount(summary.qaAlerts, "0"))}</strong></div>
          <div><span>Not started</span><strong>${escapeHtml(formatCount(summary.untouched, "0"))}</strong></div>
          ${nextButton}
        </div>
      </div>
      <div class="pay-uplift-worklist-legend" aria-label="Pipeline stage legend">
        ${PIPELINE_LED_SECTIONS.map((section) => `<span>${escapeHtml(MATRIX_SECTION_LABELS[section] || SECTION_LABELS[section] || section)}</span>`).join("")}
      </div>
      <div class="pay-uplift-worklist-table">
        <div class="pay-uplift-worklist-table-head" aria-hidden="true">
          <span>Agreement</span>
          <span>QA</span>
          <span>Pipeline status</span>
          <span>Call to action</span>
        </div>
        ${rows.length ? rows.map(renderPayUpliftWorklistRow).join("") : renderEmptyState("No agreements loaded", "No quantum and timing agreements are available in the current workspace.", { eyebrow: "Pipeline" })}
      </div>
    </section>
  `;
}

function wirePayUpliftWorklist(detail) {
  detail.querySelectorAll("[data-pay-uplift-open]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const aeId = button.dataset.payUpliftOpen;
      const section = button.dataset.payUpliftSection || "overview";
      if (!aeId) return;
      await openCouncil(aeId, section);
    });
  });
}

const CAPABILITY_NODE_PAGE_IDS = new Set([
  "datamart_inventory",
  "document_spine",
  "clause_evidence_graph",
  "clause_cards",
  "feature_cards",
  "entitlement_cards",
  "reference_edges",
  "entitlement_locator",
  "qa_review_pack",
  "gold_seed_rows",
  "codex_suggestions",
  "human_review_worksheet",
  "governed_entitlement_measures",
]);

function capabilityNodePageTitle(nodeId) {
  const titles = {
    datamart_inventory: "Data Mart Inventory",
    document_spine: "Wiki Base",
    clause_evidence_graph: "Clause Evidence Graph",
    clause_cards: "Clause",
    feature_cards: "Feature",
    entitlement_cards: "Entitlement",
    reference_edges: "Reference Edges",
    entitlement_locator: "Entitlement Locator",
    qa_review_pack: "QA Review Pack",
    gold_seed_rows: "Gold Seed Rows",
    codex_suggestions: "Codex Suggestions",
    human_review_worksheet: "Review",
    governed_entitlement_measures: "Governed Entitlement Measures",
  };
  return titles[nodeId] || "Clause Intelligence";
}

function renderCapabilityNodePageScaffold(node) {
  if (!node || !CAPABILITY_NODE_PAGE_IDS.has(node.id)) return "";
  const pageKicker = node.id === "document_spine"
    ? "Source & custody"
    : node.id === "datamart_inventory"
    ? "Data marts"
    : "Clause intelligence";
  const agreementSelectHtml = ["datamart_inventory", "feature_cards", "entitlement_cards"].includes(node.id) ? "" : `
        <label class="capability-node-page-select">
          <span>Agreement</span>
          <select id="capability-document-map-select" aria-label="Agreement"></select>
          <small id="capability-document-map-note" class="capability-document-map-note"></small>
        </label>
  `;
  return `
    <section class="capability-node-page" data-capability-node-page="${escapeHtml(node.id)}">
      <div class="capability-node-page-head">
        <div>
          <span class="capability-card-kicker">${escapeHtml(pageKicker)}</span>
          <h2>${escapeHtml(capabilityNodePageTitle(node.id))}</h2>
          <p>${escapeHtml(node.description || "")}</p>
        </div>
        ${agreementSelectHtml}
      </div>
      <div id="capability-node-page-body" class="capability-node-page-body">
        <div class="wiki-loading-row">Loading node content...</div>
      </div>
    </section>
  `;
}

function capabilityCurrentNodePageIs(nodeId) {
  return document.body.dataset.view === "capability" && state.currentCapabilityNode === nodeId;
}

function capabilityAgreementIdForRow(row) {
  return String(row?.ae_id || row?.agreement_id || "").toLowerCase();
}

function capabilityAgreementOptionLabel(row, documentMap = null) {
  const aeId = capabilityAgreementIdForRow(row) || String(documentMap?.agreement_id || "").toLowerCase();
  const councilName = row ? wikiAgreementDisplayName(row) : "";
  const title = row ? wikiAgreementTitle(row) : documentMap?.agreement_name || "Agreement map";
  const parts = [
    aeId ? aeId.toUpperCase() : "",
    councilName && councilName !== "Council" ? councilName : "",
    title && title !== councilName ? title : "",
  ].filter(Boolean);
  return parts.join(" - ") || "Agreement";
}

function capabilityAgreementOptions() {
  const mapRows = wikiDocumentMapRows();
  const mapsById = new Map(mapRows.map((row) => [String(row.agreement_id || "").toLowerCase(), row]));
  const options = [];
  const seen = new Set();
  state.councils.forEach((row) => {
    const aeId = capabilityAgreementIdForRow(row);
    if (!aeId || seen.has(aeId)) return;
    const documentMap = mapsById.get(aeId) || null;
    options.push({
      agreement_id: aeId,
      agreement_name: wikiAgreementTitle(row),
      hasDocumentMap: Boolean(documentMap),
      label: capabilityAgreementOptionLabel(row, documentMap),
      documentMap,
    });
    seen.add(aeId);
  });
  mapRows.forEach((row) => {
    const aeId = String(row.agreement_id || "").toLowerCase();
    if (!aeId || seen.has(aeId)) return;
    options.push({
      agreement_id: aeId,
      agreement_name: row.agreement_name || "Agreement map",
      hasDocumentMap: true,
      label: capabilityAgreementOptionLabel(null, row),
      documentMap: row,
    });
    seen.add(aeId);
  });
  return options.sort((left, right) => left.label.localeCompare(right.label));
}

function capabilityDocumentMapOptionsHtml(options) {
  const optionHtml = (option) =>
    `<option value="${escapeHtml(option.agreement_id)}">${escapeHtml(option.label)}</option>`;
  const mapped = options.filter((option) => option.hasDocumentMap);
  const pending = options.filter((option) => !option.hasDocumentMap);
  return [
    mapped.length ? `<optgroup label="Mapped agreements">${mapped.map(optionHtml).join("")}</optgroup>` : "",
    pending.length ? `<optgroup label="Agreements without document map">${pending.map(optionHtml).join("")}</optgroup>` : "",
  ].join("");
}

function capabilitySelectedDocumentMapId(options) {
  const selected = String(state.capabilitySelectedAgreementId || state.wikiSelectedAeId || "").toLowerCase();
  if (selected && options.some((option) => option.agreement_id === selected)) return selected;
  return String(options.find((option) => option.hasDocumentMap)?.agreement_id || options[0]?.agreement_id || "").toLowerCase();
}

function capabilityPlaceholderDocumentMap(option) {
  const aeId = String(option?.agreement_id || "").toLowerCase();
  return {
    agreement_id: aeId,
    agreement_name: option?.agreement_name || option?.label || aeId.toUpperCase(),
    review_state: "pending_document_map",
    scope_focus: "document_map_not_generated",
    summary: {
      pages_scanned: 0,
      headings_detected: 0,
      sections_detected: 0,
      language_candidates: 0,
    },
    pages: [],
    sections: [],
    questions: [],
  };
}

function capabilityPendingDocumentMapNoticeHtml(option) {
  const label = option?.label || String(option?.agreement_id || "").toUpperCase() || "the selected agreement";
  return `
    <div class="capability-document-map-warning" role="note">
      <strong>No document map has been generated for ${escapeHtml(label)} yet.</strong>
      <span>Showing the agreement in the selector now; source-spine details will appear once the wiki evidence job builds this map.</span>
    </div>
  `;
}

function capabilityMetricHtml(label, value, note = "") {
  return `
    <article class="capability-node-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value ?? DISPLAY_EMPTY))}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </article>
  `;
}

function capabilitySourceRefText(sourceRef) {
  if (!sourceRef || typeof sourceRef !== "object") return DISPLAY_EMPTY;
  const agreementId = String(sourceRef.agreement_id || sourceRef.source_id || "").toUpperCase();
  const page = sourceRef.page ? `p.${sourceRef.page}` : "";
  const line = sourceRef.line_index !== undefined ? `line ${sourceRef.line_index}` : "";
  return [agreementId, page, line].filter(Boolean).join(" / ") || DISPLAY_EMPTY;
}

function capabilityShortHash(value) {
  const raw = String(value || "").trim();
  return raw ? raw.slice(0, 12) : DISPLAY_EMPTY;
}

function capabilityCounterChipsHtml(counts, limit = 4) {
  const entries = Object.entries(counts || {}).slice(0, limit);
  if (!entries.length) return `<span class="wiki-muted">No statuses</span>`;
  return entries.map(([key, value]) => `
    <span class="capability-node-chip">
      ${escapeHtml(wikiDisplayLabel(key))}
      <strong>${formatCount(value, "0")}</strong>
    </span>
  `).join("");
}

function capabilityQuestionListHtml(questions) {
  const rows = wikiAsArray(questions).slice(0, 6);
  if (!rows.length) {
    return renderEmptyState("No open direction questions", "This map has no page-level clause-context questions in the current wiki run.", { eyebrow: "Questions" });
  }
  return rows.map((item) => `
    <article class="capability-node-question">
      <div>
        <span>${escapeHtml(wikiDisplayLabel(item.priority || "medium"))}</span>
        <strong>${escapeHtml(capabilitySourceRefText(item.source_ref))}</strong>
      </div>
      <p>${escapeHtml(item.prompt || item.code || "Review question")}</p>
    </article>
  `).join("");
}

function capabilityPageSpineRowsHtml(pages) {
  const rows = wikiAsArray(pages).slice(0, 24);
  if (!rows.length) {
    return renderEmptyState("No pages in document spine", "The selected document map has not captured page-level structure yet.", { eyebrow: "Spine" });
  }
  return `
    <div class="wiki-table-wrap capability-node-table-wrap">
      <table class="wiki-map-table capability-node-table">
        <thead>
          <tr>
            <th>Page</th>
            <th>Text</th>
            <th>Relevance</th>
            <th>Tags</th>
            <th>Headings</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((page) => {
            const relevance = wikiRecordRelevance(page);
            return `
              <tr>
                <td>p.${escapeHtml(page.page || "")}</td>
                <td>${formatCount(page.char_count, "0")} chars</td>
                <td><span class="wiki-relevance wiki-relevance-${escapeHtml(relevance)}">${escapeHtml(wikiDisplayLabel(relevance))}</span></td>
                <td><div class="wiki-tag-list">${wikiTagPills(page.tags, 3)}</div></td>
                <td>${formatCount(page.heading_count, "0")}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function capabilitySectionContainerCardsHtml(sections, { limit = 10 } = {}) {
  const rows = wikiAsArray(sections)
    .filter((section) => (section.clause_context_relevance || section.standard_band_relevance) !== "none")
    .slice(0, limit);
  if (!rows.length) {
    return renderEmptyState("No clause containers", "The selected map has no section-level containers tagged for clause review.", { eyebrow: "Containers" });
  }
  return `
    <div class="capability-clause-container-grid">
      ${rows.map((section) => {
        const relevance = wikiRecordRelevance(section);
        return `
          <article class="capability-clause-container-card">
            <div class="capability-clause-container-head">
              <div>
                <span>${escapeHtml(capabilitySourceRefText(section.source_ref))}</span>
                <h3>${escapeHtml(section.title || section.heading || "Detected section")}</h3>
              </div>
              <span class="wiki-relevance wiki-relevance-${escapeHtml(relevance)}">${escapeHtml(wikiDisplayLabel(relevance))}</span>
            </div>
            <p>${escapeHtml(section.evidence_excerpt || "No excerpt captured yet.")}</p>
            <div class="capability-clause-container-foot">
              <code>${escapeHtml(section.section_id || "section-id-pending")}</code>
              <span>${escapeHtml(wikiDisplayLabel(section.review_state || "proposed"))}</span>
            </div>
            <div class="wiki-tag-list">${wikiTagPills(section.tags, 4)}</div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderCapabilityDocumentSpineContent(detail) {
  const summary = detail?.summary || {};
  const pages = wikiAsArray(detail?.pages);
  const sections = wikiAsArray(detail?.sections);
  const questions = wikiAsArray(detail?.questions);
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Pages", formatCount(summary.pages_scanned ?? pages.length, "0"), "scanned units")}
      ${capabilityMetricHtml("Headings", formatCount(summary.headings_detected, "0"), "detected headings")}
      ${capabilityMetricHtml("Sections", formatCount(summary.sections_detected ?? sections.length, "0"), "containers")}
      ${capabilityMetricHtml("Language", formatCount(summary.language_candidates, "0"), "candidate terms")}
    </div>
    <div class="capability-node-contract-grid">
      <article>
        <span>Wiki base contract</span>
        <strong>Page -> heading -> section -> clause container</strong>
        <p>Keep document structure thin, reusable, and source-shaped before any specialised interpretation starts.</p>
      </article>
      <article>
        <span>Review role</span>
        <strong>Preserve structure, do not decide meaning</strong>
        <p>Relevance, tags, questions, and excerpts are review scaffolding for downstream evidence surfaces.</p>
      </article>
      <article>
        <span>Output state</span>
        <strong>${escapeHtml(wikiDisplayLabel(detail?.review_state, "Proposed"))}</strong>
        <p>${escapeHtml(wikiDisplayLabel(detail?.scope_focus || "entitlements_conditions_benefits"))}</p>
      </article>
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      <section>
        <h4>Clause Function Weight</h4>
        <div class="wiki-chip-cloud">${wikiTopClauseHtml(summary, 8)}</div>
      </section>
      <section>
        <h4>Clause/Context Relevance</h4>
        <div class="wiki-relevance-cloud">${wikiRelevanceCountsHtml(summary)}</div>
      </section>
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Page Map</h3>
        <span>${formatCount(pages.length, "0")} page records</span>
      </div>
      ${capabilityPageSpineRowsHtml(pages)}
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Section Containers</h3>
        <span>${formatCount(sections.length, "0")} detected sections</span>
      </div>
      ${capabilitySectionContainerCardsHtml(sections)}
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Direction Questions</h3>
        <span>${formatCount(questions.length, "0")} open prompts</span>
      </div>
      <div class="capability-node-question-list">${capabilityQuestionListHtml(questions)}</div>
    </section>
  `;
}

function capabilityClauseCardsForAgreement(payload, agreementId) {
  const selected = String(agreementId || "").toLowerCase();
  const cards = wikiAsArray(payload?.cards);
  const matching = cards.filter((card) => String(card.agreement_id || "").toLowerCase() === selected);
  return matching.length ? matching : cards;
}

function capabilityLocatorClauseCardsHtml(cards, selectedAgreementId) {
  const rows = wikiAsArray(cards).slice(0, 8);
  if (!rows.length) {
    return renderEmptyState("No locator clause cards", "The locator review file has not emitted clause cards yet.", { eyebrow: "Clause cards" });
  }
  const selected = String(selectedAgreementId || "").toUpperCase();
  const isFallback = rows.some((card) => String(card.agreement_id || "").toUpperCase() !== selected);
  return `
    ${isFallback ? `<p class="capability-node-page-note">No locator clause cards matched ${escapeHtml(selected || "the selected map")}; showing the current review sample instead.</p>` : ""}
    <div class="capability-locator-card-grid">
      ${rows.map((card) => {
        const entitlements = wikiAsArray(card.entitlements).slice(0, 4);
        const span = wikiAsArray(card.evidence_spans)[0] || {};
        const hashes = wikiAsArray(card.raw_clause_text_hashes);
        return `
          <article class="capability-locator-card">
            <div class="capability-locator-card-head">
              <div>
                <span>${escapeHtml(String(card.agreement_id || "").toUpperCase())}${card.pages?.length ? ` / p.${escapeHtml(card.pages.join(", "))}` : ""}</span>
                <h3>${escapeHtml(card.clause_card_id || "Clause card")}</h3>
              </div>
              <strong>${formatCount(card.reference_link_count, "0")} refs</strong>
            </div>
            <p>${escapeHtml(span.text || "No evidence span captured for this card.")}</p>
            <div class="capability-locator-card-tags">
              ${entitlements.map((item) => `<span>${escapeHtml(item.label || item.entitlement_id || "Entitlement")}</span>`).join("")}
            </div>
            <dl class="capability-locator-card-facts">
              <div><dt>Raw hash</dt><dd>${escapeHtml(capabilityShortHash(hashes[0]))}</dd></div>
              <div><dt>Feature cards</dt><dd>${formatCount(wikiAsArray(card.feature_card_ids).length, "0")}</dd></div>
              <div><dt>Machine</dt><dd>${capabilityCounterChipsHtml(card.machine_cell_statuses, 2)}</dd></div>
              <div><dt>Review</dt><dd>${capabilityCounterChipsHtml(card.review_statuses, 2)}</dd></div>
            </dl>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderCapabilityClauseCardsContent(detail, clausePayload) {
  const sections = wikiAsArray(detail?.sections);
  const sourceContainers = sections.filter((section) => (section.clause_context_relevance || section.standard_band_relevance) !== "none");
  const summary = clausePayload?.summary || {};
  const cards = capabilityClauseCardsForAgreement(clausePayload, detail?.agreement_id);
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Source containers", formatCount(sourceContainers.length, "0"), "from selected map")}
      ${capabilityMetricHtml("Locator cards", formatCount(summary.clause_cards, "0"), "review sample")}
      ${capabilityMetricHtml("Feature cards", formatCount(summary.feature_cards, "0"), "span facts")}
      ${capabilityMetricHtml("References", formatCount(summary.cards_with_reference_links, "0"), "cards with edges")}
    </div>
    <div class="capability-node-contract-grid">
      <article>
        <span>Clause card contract</span>
        <strong>Source window plus identifiers</strong>
        <p>Each card carries agreement, page, raw-text hash, feature-card links, reference edges, and review status.</p>
      </article>
      <article>
        <span>Governance boundary</span>
        <strong>Candidate evidence only</strong>
        <p>Cards can support review, but report-safe entitlement measures still require explicit human promotion.</p>
      </article>
      <article>
        <span>Review gap</span>
        <strong>${formatCount(summary.rows_without_clause_card, "0")} rows without a clause card</strong>
        <p>Those rows stay visible as absence or search-scope review targets.</p>
      </article>
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Selected Agreement Clause Containers</h3>
        <span>${escapeHtml(String(detail?.agreement_id || "").toUpperCase())}</span>
      </div>
      ${capabilitySectionContainerCardsHtml(sections, { limit: 8 })}
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Locator Clause Cards</h3>
        <span>${formatCount(cards.length, "0")} displayed source windows</span>
      </div>
      ${capabilityLocatorClauseCardsHtml(cards, detail?.agreement_id)}
    </section>
  `;
}

function capabilityRowsTableHtml(rows, columns, { emptyTitle = "No rows", emptyDetail = "No records are available for this node.", limit = 12 } = {}) {
  const visibleRows = wikiAsArray(rows).slice(0, limit);
  if (!visibleRows.length) {
    return renderEmptyState(emptyTitle, emptyDetail, { eyebrow: "Records" });
  }
  return `
    <div class="wiki-table-wrap capability-node-table-wrap">
      <table class="wiki-map-table capability-node-table">
        <thead>
          <tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${visibleRows.map((row) => `
            <tr>
              ${columns.map((column) => {
                const raw = typeof column.value === "function" ? column.value(row) : row[column.key];
                const html = column.html ? raw : escapeHtml(raw ?? DISPLAY_EMPTY);
                return `<td>${html || escapeHtml(DISPLAY_EMPTY)}</td>`;
              }).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function capabilitySummaryChipsPanel(title, counts) {
  return `
    <section>
      <h4>${escapeHtml(title)}</h4>
      <div class="wiki-chip-cloud">${capabilityCounterChipsHtml(counts, 8)}</div>
    </section>
  `;
}

function capabilityCatalogRows(catalog, kind) {
  return wikiAsArray(catalog?.datasets).filter((item) => item?.kind === kind);
}

function capabilityDatasetStatusCounts(rows) {
  return rows.reduce((acc, row) => {
    const key = row.status || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function capabilityDatasetOutputSummary(row) {
  const files = wikiAsArray(row.output_files);
  if (files.length) return files.join(", ");
  const file = row.file || row.status_file || {};
  if (file.exists) return displayFileSize(file.bytes, DISPLAY_EMPTY);
  return DISPLAY_EMPTY;
}

function capabilityEndpointHtml(endpoint) {
  return endpoint ? `<code>${escapeHtml(endpoint)}</code>` : escapeHtml(DISPLAY_EMPTY);
}

function renderCapabilityDatamartInventoryContent(catalog) {
  const governedRows = capabilityCatalogRows(catalog, "governed_canonical_dataset");
  const martRows = capabilityCatalogRows(catalog, "analytical_datamart");
  const appRows = wikiAsArray(catalog?.datasets)
    .filter((item) => ["governed_entity_set", "reference", "report_asset_source", "report_asset_manifest"].includes(item?.kind))
    .filter((item) => item.endpoint || item.file?.exists);
  const partialRows = [...governedRows, ...martRows].filter((row) => ["partial", "blocked", "staged_not_governed"].includes(row.status));
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Governed canonical", formatCount(governedRows.length, "0"), "source-shaped datasets")}
      ${capabilityMetricHtml("Analytical marts", formatCount(martRows.length, "0"), "derived data products")}
      ${capabilityMetricHtml("Partial/blocked", formatCount(partialRows.length, "0"), "visible work queues")}
      ${capabilityMetricHtml("App-facing", formatCount(appRows.length, "0"), "endpoints and assets")}
    </div>
    <div class="capability-node-contract-grid">
      <article>
        <span>Governed canonical</span>
        <strong>Lineage-preserving truth layer</strong>
        <p>Normalised source-shaped tables derived from governed, reviewed, promoted, or controlled reference records.</p>
      </article>
      <article>
        <span>Analytical datamarts</span>
        <strong>Report-facing derived structures</strong>
        <p>Marts can be built, partial, or blocked. Their status and caveats travel with the rowset.</p>
      </article>
      <article>
        <span>Report boundary</span>
        <strong>Visible does not mean report-ready</strong>
        <p>Draft report inputs, benchmark questions, entitlement taxonomy, and quality issues stay surfaced without being upgraded.</p>
      </article>
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Canonical Status", capabilityDatasetStatusCounts(governedRows))}
      ${capabilitySummaryChipsPanel("Mart Status", capabilityDatasetStatusCounts(martRows))}
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Governed Canonical Datasets</h3>
        <span>${formatCount(governedRows.length, "0")} datasets</span>
      </div>
      ${capabilityRowsTableHtml(governedRows, [
        { label: "Dataset", value: (row) => row.label || row.dataset_id || row.id },
        { label: "Status", value: (row) => wikiDisplayLabel(row.status || "unknown") },
        { label: "Rows", value: (row) => formatCount(row.row_count, "0") },
        { label: "Contract", value: (row) => row.contract || DISPLAY_EMPTY },
        { label: "Next", value: (row) => row.recommended_next_action || DISPLAY_EMPTY },
      ], { limit: 16 })}
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Analytical Datamarts</h3>
        <span>${formatCount(martRows.length, "0")} marts and views</span>
      </div>
      ${capabilityRowsTableHtml(martRows, [
        { label: "Mart", value: (row) => row.label || row.mart_id || row.id },
        { label: "Status", value: (row) => wikiDisplayLabel(row.status || "unknown") },
        { label: "Rows", value: (row) => formatCount(row.row_count, "0") },
        { label: "Outputs", value: capabilityDatasetOutputSummary },
        { label: "Caveat", value: (row) => wikiAsArray(row.caveats)[0] || DISPLAY_EMPTY },
      ], { limit: 24 })}
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>App-Facing Data Surfaces</h3>
        <span>${formatCount(appRows.length, "0")} exposed endpoints or assets</span>
      </div>
      ${capabilityRowsTableHtml(appRows, [
        { label: "Surface", value: (row) => row.label || row.id },
        { label: "Kind", value: (row) => wikiDisplayLabel(row.kind || "surface") },
        { label: "Endpoint", value: (row) => capabilityEndpointHtml(row.endpoint), html: true },
        { label: "Backing file", value: capabilityDatasetOutputSummary },
      ], { limit: 16 })}
    </section>
  `;
}

function capabilityArtifactSourceLine(source) {
  const path = source?.path || source?.relative_path || "";
  const size = source?.bytes ? displayFileSize(source.bytes, DISPLAY_EMPTY) : "";
  return [path, size].filter(Boolean).join(" / ");
}

function capabilityFreshnessStatusHtml(status) {
  const key = String(status || "unknown");
  return `<span class="capability-freshness-status capability-freshness-status-${escapeHtml(key)}">${escapeHtml(wikiDisplayLabel(key))}</span>`;
}

function capabilityFreshnessReasonsHtml(reasons) {
  const rows = wikiAsArray(reasons);
  if (!rows.length) return `<span class="wiki-muted">No blockers</span>`;
  return rows.slice(0, 5).map((reason) => `<span>${escapeHtml(wikiDisplayLabel(reason))}</span>`).join("");
}

function capabilityPipelineFreshnessHtml(freshness) {
  const checks = wikiAsArray(freshness?.checks);
  if (!checks.length) return "";
  const isCurrent = freshness?.status === "current";
  return `
    <section class="capability-freshness capability-freshness-${escapeHtml(freshness?.status || "unknown")}">
      <div class="capability-freshness-head">
        <div>
          <span>Pipeline freshness</span>
          <strong>${isCurrent ? "Artifacts are current" : `${formatCount(freshness?.stale_stages, "0")} stale stages`}</strong>
        </div>
        ${capabilityFreshnessStatusHtml(freshness?.status)}
      </div>
      <div class="capability-freshness-grid">
        ${checks.map((check) => {
          const coverage = check.answer_builder_coverage || {};
          const coverageText = coverage.feature_cards
            ? `Answer builder ${capabilityCoverageFraction(coverage.with_answer_builder_contract, coverage.feature_cards)}`
            : "";
          return `
            <article>
              <div class="capability-freshness-stage-head">
                <strong>${escapeHtml(check.label || check.stage || "Stage")}</strong>
                ${capabilityFreshnessStatusHtml(check.status)}
              </div>
              <small>${escapeHtml(displayDate(check.generated_at || check.effective_generated_at, DISPLAY_EMPTY))}${coverageText ? ` / ${escapeHtml(coverageText)}` : ""}</small>
              <div class="capability-freshness-reasons">${capabilityFreshnessReasonsHtml(check.reasons)}</div>
            </article>
          `;
        }).join("")}
      </div>
      ${!isCurrent ? `<p>Run stages in order before treating the blocker table as current: locator, entitlement cards, then repair loop.</p>` : ""}
    </section>
  `;
}

function capabilityCoverageFraction(numerator, denominator) {
  return `${formatCount(numerator, "0")}/${formatCount(denominator, "0")}`;
}

function capabilityCoverageStatusHtml(status) {
  const labels = {
    complete_to_feature_card: "Complete",
    partial_feature_cards: "Partial",
    clause_cards_only: "Clause cards",
    document_spine_only: "Spine only",
    not_profiled: "Not profiled",
  };
  const key = String(status || "not_profiled");
  return `<span class="capability-coverage-status capability-coverage-status-${escapeHtml(key)}">${escapeHtml(labels[key] || wikiDisplayLabel(key))}</span>`;
}

function capabilityReviewStageKey(cell) {
  if (cell?.feature_cards === "ready") return "feature";
  if (cell?.clause_cards === "ready") return "clause";
  if (cell?.document_spine === "ready") return "spine";
  return "missing";
}

function capabilityReviewStageLabel(cell) {
  const labels = {
    feature: "Feature card",
    clause: "Clause card",
    spine: "Spine only",
    missing: "Missing",
  };
  return labels[capabilityReviewStageKey(cell)] || "Missing";
}

function capabilityReviewEntitlements(matrix) {
  return wikiAsArray(matrix?.entitlements);
}

function capabilityReviewTargets(matrix) {
  return wikiAsArray(matrix?.targets).map((target) => ({
    ...target,
    agreement_id: String(target.agreement_id || "").toLowerCase(),
  }));
}

function capabilityReviewCells(matrix, entitlementId) {
  const selected = String(entitlementId || "").toLowerCase();
  return wikiAsArray(matrix?.cells).filter((cell) => String(cell.entitlement_id || "").toLowerCase() === selected);
}

function capabilityReviewSelectedEntitlement(matrix) {
  const entitlements = capabilityReviewEntitlements(matrix);
  if (!entitlements.length) return null;
  const current = entitlements.find((item) => item.entitlement_id === state.capabilityReviewEntitlementId);
  if (current) return current;
  const preferred = entitlements.find((item) => item.status !== "complete_to_feature_card") || entitlements[0];
  state.capabilityReviewEntitlementId = preferred.entitlement_id;
  return preferred;
}

function capabilityReviewSelectedCouncil(matrix, entitlementId) {
  const targets = capabilityReviewTargets(matrix);
  if (!targets.length) return null;
  const current = targets.find((item) => item.agreement_id === state.capabilityReviewCouncilId);
  if (current) return current;
  const cells = capabilityReviewCells(matrix, entitlementId);
  const preferredCell = cells.find((cell) => cell.clause_cards === "ready" && cell.feature_cards !== "ready")
    || cells.find((cell) => cell.feature_cards !== "ready")
    || cells.find((cell) => cell.feature_cards === "ready")
    || cells[0];
  const preferred = targets.find((item) => item.agreement_id === String(preferredCell?.agreement_id || "").toLowerCase()) || targets[0];
  state.capabilityReviewCouncilId = preferred.agreement_id;
  return preferred;
}

function capabilityReviewSelectedCell(matrix, entitlementId, agreementId) {
  const target = String(agreementId || "").toLowerCase();
  return capabilityReviewCells(matrix, entitlementId).find((cell) => String(cell.agreement_id || "").toLowerCase() === target) || null;
}

function capabilityReviewCellForTarget(cells, target) {
  const key = String(target?.agreement_id || "").toLowerCase();
  return cells.find((cell) => String(cell.agreement_id || "").toLowerCase() === key) || null;
}

function capabilityReviewStageFilter(matrix) {
  const targetCount = capabilityReviewTargets(matrix).length;
  const value = String(state.capabilityReviewStageFilter || "");
  const allowed = new Set(["all", "open", "feature", "clause", "spine", "missing"]);
  if (allowed.has(value)) return value;
  state.capabilityReviewStageFilter = targetCount > 12 ? "open" : "all";
  return state.capabilityReviewStageFilter;
}

function capabilityReviewStageFilterMatches(filter, stage) {
  if (filter === "all") return true;
  if (filter === "open") return stage !== "feature";
  return stage === filter;
}

function capabilityReviewStageFilterBar(matrix, entitlementId) {
  const targets = capabilityReviewTargets(matrix);
  const cells = capabilityReviewCells(matrix, entitlementId);
  const counts = {
    all: targets.length,
    open: 0,
    feature: 0,
    clause: 0,
    spine: 0,
    missing: 0,
  };
  for (const target of targets) {
    const stage = capabilityReviewStageKey(capabilityReviewCellForTarget(cells, target));
    counts[stage] += 1;
    if (stage !== "feature") counts.open += 1;
  }
  const selected = capabilityReviewStageFilter(matrix);
  const filters = [
    ["open", "Open"],
    ["all", "All"],
    ["feature", "Feature"],
    ["clause", "Clause"],
    ["spine", "Spine"],
    ["missing", "Missing"],
  ];
  return `
    <div class="capability-review-filter-row" aria-label="Council stage filter">
      ${filters.map(([key, label]) => `
        <button
          type="button"
          class="${key === selected ? "is-selected" : ""}"
          data-capability-review-stage-filter="${escapeHtml(key)}"
          aria-pressed="${key === selected ? "true" : "false"}"
        >
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(formatCount(counts[key], "0"))}</strong>
        </button>
      `).join("")}
    </div>
  `;
}

function capabilityReviewStageRail(cell) {
  const stage = capabilityReviewStageKey(cell);
  const items = [
    ["spine", "Spine", cell?.document_spine === "ready"],
    ["clause", "Clause", cell?.clause_cards === "ready"],
    ["feature", "Feature", cell?.feature_cards === "ready"],
    ["review", "Review", false],
  ];
  return `
    <div class="capability-review-stage-rail" aria-label="Selected cell pipeline stage">
      ${items.map(([key, label, ready]) => `
        <span class="${ready ? "is-ready" : ""} ${key === stage ? "is-current" : ""}">
          ${escapeHtml(label)}
        </span>
      `).join("")}
    </div>
  `;
}

function capabilityReviewCouncilGrid(matrix, entitlementId, selectedAgreementId) {
  const targets = capabilityReviewTargets(matrix);
  const cells = capabilityReviewCells(matrix, entitlementId);
  const selectedKey = String(selectedAgreementId || "").toLowerCase();
  const selectedFilter = capabilityReviewStageFilter(matrix);
  const visibleTargets = targets.filter((target) => {
    const stage = capabilityReviewStageKey(capabilityReviewCellForTarget(cells, target));
    return capabilityReviewStageFilterMatches(selectedFilter, stage) || target.agreement_id === selectedKey;
  });
  return `
    <div class="capability-review-council-grid" aria-label="Councils in selected entitlement test">
      ${visibleTargets.map((target) => {
    const cell = capabilityReviewCellForTarget(cells, target);
    const stage = capabilityReviewStageKey(cell);
    const selected = target.agreement_id === selectedAgreementId;
    return `
        <button
          type="button"
          class="capability-review-council-button capability-review-stage-${escapeHtml(stage)} ${selected ? "is-selected" : ""}"
          data-capability-review-council-key="${escapeHtml(target.agreement_id)}"
          aria-pressed="${selected ? "true" : "false"}"
        >
          <span>${escapeHtml(target.council || target.agreement_id.toUpperCase())}</span>
          <strong>${escapeHtml(capabilityReviewStageLabel(cell))}</strong>
        </button>
      `;
  }).join("")}
    </div>
  `;
}

function capabilityReviewValuesHtml(cell) {
  const rows = wikiAsArray(cell?.normalised_values);
  if (!rows.length) {
    return `<div class="capability-review-empty-line">No extracted value yet.</div>`;
  }
  return `
    <div class="capability-review-value-list">
      ${rows.slice(0, 4).map((value) => `
        <div>
          <strong>${escapeHtml([value.value, value.unit].filter(Boolean).join(" ") || "Value")}</strong>
          <span>${escapeHtml(value.condition || value.subclass_label || "Candidate value")}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function capabilityReviewEvidenceHtml(cell) {
  const feature = wikiAsArray(cell?.feature_card_previews)[0] || {};
  const clause = wikiAsArray(cell?.clause_card_previews)[0] || {};
  const excerpt = cell?.review_text || clause.review_text || feature.evidence_text || clause.text || feature.evidence_span || cell?.best_excerpt || "";
  if (!excerpt) {
    return `<div class="capability-review-empty-line">No evidence window has been promoted past the spine for this cell.</div>`;
  }
  const heading = cell?.best_heading || clause.heading || "Clause window";
  const page = cell?.best_page ? `Page ${cell.best_page}` : clause.page ? `Page ${clause.page}` : "Page not set";
  return `
    <div class="capability-review-evidence-card">
      <div class="capability-review-evidence-head">
        <span>${escapeHtml(heading)}</span>
        <strong>${escapeHtml(page)}</strong>
      </div>
      <div class="capability-review-evidence-text" tabindex="0" aria-label="Clause evidence text">${escapeHtml(excerpt)}</div>
    </div>
  `;
}

function capabilityReviewMetaGrid(cell) {
  const feature = wikiAsArray(cell?.feature_card_previews)[0] || {};
  const clause = wikiAsArray(cell?.clause_card_previews)[0] || {};
  return `
    <dl class="capability-review-meta-grid">
      <div><dt>Machine</dt><dd>${escapeHtml(wikiDisplayLabel(cell?.machine_state || "not profiled"))}</dd></div>
      <div><dt>Confidence</dt><dd>${escapeHtml(formatCount(cell?.locator_confidence, "0"))}</dd></div>
      <div><dt>Review</dt><dd>${escapeHtml(wikiDisplayLabel(feature.review_status || clause.review_status || "not reviewed"))}</dd></div>
      <div><dt>Refs</dt><dd>${escapeHtml(formatCount(cell?.reference_link_count, "0"))}</dd></div>
    </dl>
  `;
}

function capabilityReviewChecklist(cell) {
  const checks = [
    ["Source text", cell?.document_spine === "ready"],
    ["Clause window", cell?.clause_cards === "ready"],
    ["Feature fact", cell?.feature_cards === "ready"],
    ["Human decision", false],
  ];
  return `
    <div class="capability-review-checklist">
      ${checks.map(([label, ready]) => `
        <div class="${ready ? "is-ready" : ""}">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(ready ? "Ready" : "Open")}</strong>
        </div>
      `).join("")}
    </div>
  `;
}

function capabilityReviewListValue(value) {
  if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
  const text = String(value || "").trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) return parsed.map((item) => String(item || "").trim()).filter(Boolean);
  } catch {
    return text.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function capabilityReviewWorksheetRow(intelligence, selectedEntitlement, selectedCell, selectedCouncil) {
  const rows = wikiAsArray(intelligence?.human_review_worksheet?.rows);
  const agreementId = String(selectedCell?.agreement_id || selectedCouncil?.agreement_id || "").toLowerCase();
  const entitlementLabel = String(selectedEntitlement?.entitlement_label || selectedCell?.entitlement_label || "").toLowerCase();
  if (!agreementId || !entitlementLabel) return null;
  return rows.find((row) => (
    String(row.agreement_id || "").toLowerCase() === agreementId
    && String(row.entitlement_label || "").toLowerCase() === entitlementLabel
  )) || null;
}

function capabilityReviewProblemStatement(cell, worksheetRow) {
  const stage = capabilityReviewStageKey(cell);
  if (stage === "missing") {
    return "Source spine is missing for this agreement. The first review problem is source intake or cache repair, not entitlement judgement.";
  }
  if (stage === "spine") {
    return "The source spine exists, but no clause card has been accepted for this entitlement. Decide whether this is true absence or a locator miss.";
  }
  if (stage === "clause") {
    return "A clause window exists, but the feature fact is not ready. Decide whether the span contains the entitlement and whether a benchmarkable value can be normalised.";
  }
  if (worksheetRow?.codex_suggested_review_decision === "correct") {
    return "A feature card exists and the advisory pass thinks it is likely correct. Confirm clause, span, value, scope, and references before promotion.";
  }
  return "A feature card exists. Confirm the evidence span and value before treating it as report-safe.";
}

function capabilityReviewDecisionSteps(cell, worksheetRow) {
  const hasClause = cell?.clause_cards === "ready";
  const hasFeature = cell?.feature_cards === "ready";
  const hasValue = wikiAsArray(cell?.normalised_values).length > 0 || String(worksheetRow?.codex_suggested_value || "").trim();
  const refs = Number(cell?.reference_link_count || worksheetRow?.reference_link_count || 0);
  return [
    ["Clause", hasClause ? "Ready" : "Open", hasClause ? (cell?.best_heading || "Clause window located") : "Find or rule out the source clause"],
    ["Span", hasFeature ? "Ready" : hasClause ? "Review" : "Open", hasFeature ? "Evidence span attached" : "Pick the exact text span that carries the entitlement"],
    ["Presence", worksheetRow?.codex_suggested_provision_present || (hasClause ? "Candidate" : "Open"), worksheetRow?.machine_presence_status || wikiDisplayLabel(cell?.machine_state || "not profiled")],
    ["Value", hasValue ? "Candidate" : "Open", hasValue ? [worksheetRow?.codex_suggested_value, worksheetRow?.codex_suggested_unit].filter(Boolean).join(" ") || "Machine value found" : "Normalise value, unit, condition and scope"],
    ["References", refs ? "Review" : "None", refs ? `${formatCount(refs, "0")} linked reference${refs === 1 ? "" : "s"}` : "No reference edge flagged"],
    ["Governance", "Open", "Human decision needed before promotion"],
  ];
}

function capabilityReviewGuidanceHtml(intelligence, selectedEntitlement, selectedCell, selectedCouncil) {
  const worksheetRow = capabilityReviewWorksheetRow(intelligence, selectedEntitlement, selectedCell, selectedCouncil);
  const riskFlags = capabilityReviewListValue(worksheetRow?.codex_risk_flags);
  const blockers = capabilityReviewListValue(worksheetRow?.blocker_signals).length
    ? capabilityReviewListValue(worksheetRow?.blocker_signals)
    : wikiAsArray(selectedCell?.blocker_signals);
  const pendingHumanFields = [
    ["Clause", worksheetRow?.human_clause_locator_result],
    ["Span", worksheetRow?.human_span_result],
    ["Presence", worksheetRow?.human_presence_result],
    ["Value", worksheetRow?.human_value_result],
    ["Refs", worksheetRow?.human_cross_reference_result],
    ["Decision", worksheetRow?.human_review_decision],
  ].filter(([, value]) => !String(value || "").trim());
  const decisionSteps = capabilityReviewDecisionSteps(selectedCell, worksheetRow);
  return `
    <section class="capability-review-guidance">
      <div class="capability-review-guidance-head">
        <div>
          <span>${escapeHtml(worksheetRow ? worksheetRow.sample_reason || "selected cell" : "selected cell")}</span>
          <h4>Guided Problem</h4>
        </div>
        <strong>${escapeHtml(worksheetRow?.codex_confidence ? `${wikiDisplayLabel(worksheetRow.codex_confidence)} advisory` : "Live cell")}</strong>
      </div>
      <p>${escapeHtml(capabilityReviewProblemStatement(selectedCell, worksheetRow))}</p>
      <div class="capability-review-decision-grid">
        ${decisionSteps.map(([label, status, detail]) => `
          <article>
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(status)}</strong>
            <p>${escapeHtml(detail || DISPLAY_EMPTY)}</p>
          </article>
        `).join("")}
      </div>
      <div class="capability-review-guidance-facts">
        <div>
          <span>Advisory</span>
          <strong>${escapeHtml(wikiDisplayLabel(worksheetRow?.codex_suggested_review_decision || selectedCell?.machine_state || "not sampled"))}</strong>
        </div>
        <div>
          <span>Risks</span>
          <strong>${escapeHtml(riskFlags.length ? riskFlags.join(", ") : blockers.length ? blockers.join(", ") : "None flagged")}</strong>
        </div>
        <div>
          <span>Pending</span>
          <strong>${escapeHtml(worksheetRow ? pendingHumanFields.map(([label]) => label).join(", ") || "None" : "Not in review sample")}</strong>
        </div>
      </div>
      ${worksheetRow?.machine_failure_reason || worksheetRow?.failure_reason ? `
        <div class="capability-review-guidance-note">
          ${escapeHtml(worksheetRow.machine_failure_reason || worksheetRow.failure_reason)}
        </div>
      ` : ""}
    </section>
  `;
}

function capabilityReviewRuleListHtml(title, rows, emptyLabel) {
  const items = wikiAsArray(rows).map((item) => String(item || "").trim()).filter(Boolean);
  return `
    <section class="capability-review-rule-section">
      <h5>${escapeHtml(title)}</h5>
      ${items.length ? `
        <ul class="capability-review-rule-list">
          ${items.slice(0, 8).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      ` : `<p>${escapeHtml(emptyLabel)}</p>`}
    </section>
  `;
}

function capabilityReviewValueProfileHtml(valueProfile) {
  const commonValues = valueProfile?.common_values || {};
  const units = valueProfile?.units || {};
  const examples = wikiAsArray(valueProfile?.examples);
  const commonValueItems = Object.entries(commonValues).slice(0, 6);
  const unitItems = Object.keys(units).slice(0, 5);
  const exampleItems = examples.slice(0, 3).map((item) => [item.council, item.value, item.unit].filter(Boolean).join(": "));
  return `
    <div class="capability-review-value-profile">
      <section class="capability-review-rule-section">
        <h5>Observed Values</h5>
        ${commonValueItems.length ? `
          <ul class="capability-review-rule-list">
            ${commonValueItems.map(([label, count]) => `<li><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(count))}</strong></li>`).join("")}
          </ul>
        ` : "<p>No values yet.</p>"}
      </section>
      <section class="capability-review-rule-section">
        <h5>Units</h5>
        ${unitItems.length ? `
          <ul class="capability-review-rule-list">
            ${unitItems.map((label) => `<li>${escapeHtml(label)}</li>`).join("")}
          </ul>
        ` : "<p>No unit pattern yet.</p>"}
      </section>
      <section class="capability-review-rule-section">
        <h5>Examples</h5>
        ${exampleItems.length ? `
          <ul class="capability-review-rule-list">
            ${exampleItems.map((label) => `<li>${escapeHtml(label)}</li>`).join("")}
          </ul>
        ` : "<p>No feature examples yet.</p>"}
      </section>
    </div>
  `;
}

function capabilityReviewScopeLabel(value) {
  const label = wikiDisplayLabel(value || "standard employees");
  return label ? `${label.charAt(0).toUpperCase()}${label.slice(1)}` : "Standard employees";
}

function capabilityReviewRuleContractHtml(selectedEntitlement) {
  const contract = selectedEntitlement?.rule_contract || {};
  const boundary = contract.classification_boundary || {};
  const subclasses = wikiAsArray(contract.accepted_subclasses);
  const questions = wikiAsArray(contract.ai_improvement_questions);
  const definition = boundary.canonical_definition || contract.definition || selectedEntitlement?.definition || "";
  return `
    <section class="capability-review-rule-card">
      <div class="capability-review-rule-head">
        <div>
          <h4>Definition & Rules</h4>
          <span>${escapeHtml(capabilityReviewScopeLabel(contract.scope || selectedEntitlement?.category || "standard employees"))}</span>
        </div>
        <span>${escapeHtml(formatCount(selectedEntitlement?.value_profile?.feature_values, "0"))} feature values</span>
      </div>
      <section class="capability-review-rule-definition">
        <h5>Definition</h5>
        <p>${escapeHtml(definition || "No governed definition has been supplied yet.")}</p>
      </section>
      <div class="capability-review-rule-grid">
        ${capabilityReviewRuleListHtml("Include", boundary.included, "No inclusion rules yet.")}
        ${capabilityReviewRuleListHtml("Exclude", boundary.excluded, "No exclusion rules yet.")}
        ${capabilityReviewRuleListHtml("Review If", boundary.needs_review, "No ambiguity rules yet.")}
      </div>
      ${capabilityReviewValueProfileHtml(selectedEntitlement?.value_profile || {})}
      ${subclasses.length ? `
        <section class="capability-review-rule-section">
          <h5>Accepted Subclasses</h5>
          <ul class="capability-review-rule-list">
            ${subclasses.slice(0, 8).map((item) => `<li>${escapeHtml(item.label || item.subclass_id || "Subclass")}</li>`).join("")}
          </ul>
        </section>
      ` : ""}
      <div class="capability-review-ai-loop">
        <span>AI Improvement Loop</span>
        <ol>
          ${(questions.length ? questions : [
    "What is this entitlement really asking us to identify?",
    "Does this feature card fit the definition and observed council pattern?",
    "What definition, exclusion, expected value, or alias should be improved for the next run?",
  ]).slice(0, 6).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ol>
      </div>
    </section>
  `;
}

function capabilityReviewSelfImprovementRow(intelligence, selectedEntitlement) {
  const entitlementId = selectedEntitlement?.entitlement_id;
  if (!entitlementId) return null;
  const rowsByEntitlement = intelligence?.entitlement_self_improvement?.rows_by_entitlement || {};
  if (rowsByEntitlement[entitlementId]) return rowsByEntitlement[entitlementId];
  return wikiAsArray(intelligence?.entitlement_self_improvement?.rows)
    .find((row) => row?.entitlement_id === entitlementId) || null;
}

function capabilityReviewLoopIntelligenceRow(intelligence, selectedEntitlement) {
  const entitlementId = selectedEntitlement?.entitlement_id;
  if (!entitlementId) return null;
  const rowsByEntitlement = intelligence?.entitlement_loop_intelligence?.rows_by_entitlement || {};
  if (rowsByEntitlement[entitlementId]) return rowsByEntitlement[entitlementId];
  return wikiAsArray(intelligence?.entitlement_loop_intelligence?.rows)
    .find((row) => row?.entitlement_id === entitlementId) || null;
}

function capabilityReviewSelfImprovementHtml(intelligence, selectedEntitlement) {
  const row = capabilityReviewSelfImprovementRow(intelligence, selectedEntitlement);
  const loopRow = capabilityReviewLoopIntelligenceRow(intelligence, selectedEntitlement);
  if (!row && !loopRow) return "";
  const coverage = loopRow?.coverage || row?.coverage || {};
  const status = wikiDisplayLabel(loopRow?.loop_status || row?.status || "needs review");
  const answerShape = loopRow?.answer_shape || {};
  const ruleCandidates = loopRow?.rule_change_candidates || {};
  const valueRules = wikiAsArray(ruleCandidates.value_rules);
  const reviewRules = wikiAsArray(ruleCandidates.review_if);
  const validationQueue = wikiAsArray(loopRow?.validation_queue);
  const nextLoopSteps = wikiAsArray(loopRow?.next_loop_steps);
  const fallbackSuggestions = wikiAsArray(row?.improvement_suggestions);
  return `
    <section class="capability-review-improvement">
      <div class="capability-review-improvement-head">
        <div>
          <h4>Loop Intelligence</h4>
          <span>${escapeHtml(status)}</span>
        </div>
        <span>${escapeHtml(formatCount(coverage.green_feature_cells, "0"))} green cells</span>
      </div>
      <section class="capability-review-rule-section">
        <h5>Question</h5>
        <p>${escapeHtml(loopRow?.entitlement_question || "The entitlement question still needs to be made explicit.")}</p>
      </section>
      <section class="capability-review-rule-section">
        <h5>Expected Answer</h5>
        <p>${escapeHtml(answerShape.expectation || row?.normal_value_hypothesis || "No normal value hypothesis has been generated yet.")}</p>
      </section>
      <section class="capability-review-rule-section">
        <h5>Next Rule Changes</h5>
        ${(valueRules.length || reviewRules.length || fallbackSuggestions.length) ? `
          <ul class="capability-review-rule-list">
            ${valueRules.slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
            ${reviewRules.slice(0, Math.max(0, 3 - valueRules.length)).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
            ${(!valueRules.length && !reviewRules.length ? fallbackSuggestions.slice(0, 3).map((item) => `<li>${escapeHtml(item.message || item.type || "Review rule")}</li>`).join("") : "")}
          </ul>
        ` : "<p>No immediate rule change suggested by this loop.</p>"}
      </section>
      <section class="capability-review-rule-section">
        <h5>Validate Next</h5>
        ${validationQueue.length ? `
          <ul class="capability-review-rule-list">
            ${validationQueue.slice(0, 4).map((item) => `
              <li>
                <span>${escapeHtml([item.council, wikiAsArray(item.value_labels).join(", ")].filter(Boolean).join(": "))}</span>
                <strong>${escapeHtml(wikiAsArray(item.reasons).slice(0, 2).join(", ") || "sample")}</strong>
              </li>
            `).join("")}
          </ul>
        ` : nextLoopSteps.length ? `
          <ol class="capability-review-rule-list">
            ${nextLoopSteps.slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
          </ol>
        ` : "<p>No validation queue has been generated yet.</p>"}
      </section>
    </section>
  `;
}

function rerenderCapabilityReviewWorkspace() {
  const host = document.getElementById("capability-review-workspace");
  const matrix = state.wikiClauseIntelligence?.entitlement_test_matrix;
  if (!host || !matrix) return;
  host.outerHTML = renderCapabilityEntitlementTestMatrix(matrix, state.wikiClauseIntelligence);
}

function renderCapabilityEntitlementTestMatrix(matrix, intelligence = state.wikiClauseIntelligence) {
  const summary = matrix?.summary || {};
  const entitlements = wikiAsArray(matrix?.entitlements);
  if (!summary.test_cells) {
    return renderEmptyState("No entitlement matrix yet", "Run the 10-council locator experiment to fill the entitlement test matrix.", { eyebrow: "Entitlement tests" });
  }
  const selectedEntitlement = capabilityReviewSelectedEntitlement(matrix);
  const selectedCouncil = capabilityReviewSelectedCouncil(matrix, selectedEntitlement?.entitlement_id);
  const selectedCell = capabilityReviewSelectedCell(matrix, selectedEntitlement?.entitlement_id, selectedCouncil?.agreement_id);
  return `
    <section id="capability-review-workspace" class="capability-review-workspace">
      <div class="capability-review-toolbar">
        <label>
          <span>Entitlement</span>
          <select data-capability-review-entitlement aria-label="Entitlement">
            ${entitlements.map((item) => `
              <option value="${escapeHtml(item.entitlement_id)}"${item.entitlement_id === selectedEntitlement?.entitlement_id ? " selected" : ""}>
                ${escapeHtml(item.entitlement_label || item.entitlement_id)}
              </option>
            `).join("")}
          </select>
        </label>
        <label>
          <span>Council</span>
          <select data-capability-review-council aria-label="Council">
            ${capabilityReviewTargets(matrix).map((target) => `
              <option value="${escapeHtml(target.agreement_id)}"${target.agreement_id === selectedCouncil?.agreement_id ? " selected" : ""}>
                ${escapeHtml(target.council || target.agreement_id.toUpperCase())}
              </option>
            `).join("")}
          </select>
        </label>
        <div class="capability-review-toolbar-stat">
          <span>Feature-ready cells</span>
          <strong>${escapeHtml(capabilityCoverageFraction(summary.feature_card_ready, summary.test_cells))}</strong>
        </div>
      </div>

      <div class="capability-review-shell">
        <aside class="capability-review-side">
          <div class="capability-review-entitlement-card">
            <span>${escapeHtml(selectedEntitlement?.category || "Entitlement")}</span>
            <h3>${escapeHtml(selectedEntitlement?.entitlement_label || "Select an entitlement")}</h3>
            ${capabilityCoverageStatusHtml(selectedEntitlement?.status)}
            <p>${escapeHtml(selectedEntitlement?.definition || "")}</p>
            <dl>
              <div><dt>Spine</dt><dd>${escapeHtml(capabilityCoverageFraction(selectedEntitlement?.document_spine_ready, selectedEntitlement?.target_councils))}</dd></div>
              <div><dt>Clause</dt><dd>${escapeHtml(capabilityCoverageFraction(selectedEntitlement?.clause_card_ready, selectedEntitlement?.target_councils))}</dd></div>
              <div><dt>Feature</dt><dd>${escapeHtml(capabilityCoverageFraction(selectedEntitlement?.feature_card_ready, selectedEntitlement?.target_councils))}</dd></div>
            </dl>
          </div>
          ${capabilityReviewStageFilterBar(matrix, selectedEntitlement?.entitlement_id)}
          ${capabilityReviewCouncilGrid(matrix, selectedEntitlement?.entitlement_id, selectedCouncil?.agreement_id)}
        </aside>

        <main class="capability-review-main">
          <div class="capability-review-main-head">
            <div>
              <span>${escapeHtml(String(selectedCell?.agreement_id || selectedCouncil?.agreement_id || "").toUpperCase())}</span>
              <h3>${escapeHtml(selectedCouncil?.council || selectedCell?.council || "Council")}</h3>
            </div>
            <strong class="capability-review-stage-badge capability-review-stage-${escapeHtml(capabilityReviewStageKey(selectedCell))}">
              ${escapeHtml(capabilityReviewStageLabel(selectedCell))}
            </strong>
          </div>
          ${capabilityReviewStageRail(selectedCell)}
          ${capabilityReviewEvidenceHtml(selectedCell)}
          <section class="capability-review-subsection">
            <h4>Extracted Value</h4>
            ${capabilityReviewValuesHtml(selectedCell)}
          </section>
          ${capabilityReviewRuleContractHtml(selectedEntitlement)}
          ${capabilityReviewSelfImprovementHtml(intelligence, selectedEntitlement)}
          ${capabilityReviewGuidanceHtml(intelligence, selectedEntitlement, selectedCell, selectedCouncil)}
        </main>

        <aside class="capability-review-panel">
          <h3>Review State</h3>
          ${capabilityReviewMetaGrid(selectedCell)}
          ${capabilityReviewChecklist(selectedCell)}
        </aside>
      </div>
    </section>
  `;
}

function renderCapabilityEvidenceGraphContent(detail, intelligence) {
  const summary = intelligence?.summary || {};
  const graphStages = [
    ["Document spine", "Page, heading, section and clause-container map", detail?.summary?.sections_detected || wikiAsArray(detail?.sections).length],
    ["Clause cards", "Source windows with raw hashes and review state", summary.clause_cards],
    ["Feature cards", "Benchmarkable span facts attached to clauses", summary.feature_cards],
    ["Reference edges", "Dependencies on clauses, schedules, awards, statutes and definitions", summary.reference_edges],
    ["Review rows", "Gold seed, suggestions and worksheet adjudication records", summary.gold_seed_rows],
    ["Governed measures", "Report-safe entitlement rows after promotion", summary.governed_entitlement_rows],
  ];
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Document maps", formatCount(summary.document_maps, "0"), "source agreements")}
      ${capabilityMetricHtml("Clause cards", formatCount(summary.clause_cards, "0"), "source windows")}
      ${capabilityMetricHtml("Feature cards", formatCount(summary.feature_cards, "0"), "span facts")}
      ${capabilityMetricHtml("Reference edges", formatCount(summary.reference_edges, "0"), "dependencies")}
    </div>
    <div class="capability-node-contract-grid">
      <article>
        <span>Graph contract</span>
        <strong>Structure, evidence and review state</strong>
        <p>The graph connects source containers, clause cards, feature facts, reference edges, and governance rows.</p>
      </article>
      <article>
        <span>Truth boundary</span>
        <strong>Review before promotion</strong>
        <p>Machine locator output stays candidate evidence until human decisions and governed promotion are recorded.</p>
      </article>
      <article>
        <span>Current node</span>
        <strong>${formatCount(summary.locator_rows, "0")} locator rows</strong>
        <p>${formatCount(summary.human_review_rows, "0")} worksheet rows are waiting for semantic adjudication.</p>
      </article>
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Evidence Graph Lanes</h3>
        <span>${formatCount(graphStages.length, "0")} linked work objects</span>
      </div>
      <div class="capability-node-contract-grid capability-graph-lane-grid">
        ${graphStages.map(([label, description, count]) => `
          <article>
            <span>${escapeHtml(label)}</span>
            <strong>${formatCount(count, "0")}</strong>
            <p>${escapeHtml(description)}</p>
          </article>
        `).join("")}
      </div>
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Reference Edge Sample</h3>
        <span>${formatCount(intelligence?.reference_edges?.summary?.reference_edges, "0")} edges</span>
      </div>
      ${capabilityRowsTableHtml(intelligence?.reference_edges?.edges, [
        { label: "Relationship", value: (row) => wikiDisplayLabel(row.relationship) },
        { label: "From", key: "from_clause_id" },
        { label: "Target", value: (row) => row.to_clause || row.to_schedule || row.to_external },
        { label: "Entitlement", key: "entitlement_label" },
      ])}
    </section>
  `;
}

function renderCapabilityFeatureCardsContent(intelligence) {
  const matrix = intelligence?.entitlement_test_matrix || {};
  const matrixSummary = matrix.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Entitlements", formatCount(matrixSummary.final_entitlements, "0"), "final test list")}
      ${capabilityMetricHtml("Councils", formatCount(matrixSummary.target_councils, "0"), "test cohort")}
      ${capabilityMetricHtml("Test cells", formatCount(matrixSummary.test_cells, "0"), "entitlement x council")}
      ${capabilityMetricHtml("Feature ready", capabilityCoverageFraction(matrixSummary.feature_card_ready, matrixSummary.test_cells), "candidate cells")}
    </div>
    ${renderCapabilityEntitlementTestMatrix(matrix, intelligence)}
  `;
}

function entitlementCardPreviewText(value, limit = 180) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text || text.length <= limit) return text;
  return `${text.slice(0, limit).trim()}...`;
}

function entitlementCardClauseSummary(card) {
  const clauses = wikiAsArray(card?.source_clauses);
  const firstClause = clauses.find((clause) => clause?.raw_clause_text) || clauses[0] || {};
  const text = firstClause.raw_clause_text || wikiAsArray(card?.source_refs?.clause_card_ids).join(", ");
  return entitlementCardPreviewText(text || "No clause text captured yet.", 180);
}

function entitlementCardClauseEvidenceHtml(card) {
  const clauses = wikiAsArray(card?.source_clauses);
  if (!clauses.length) {
    const ids = wikiAsArray(card?.source_refs?.clause_card_ids);
    return `
      <div class="capability-entitlement-evidence-empty">
        <span>Clause evidence</span>
        <p>${escapeHtml(ids.length ? `Clause text was not projected. Source IDs: ${ids.join(", ")}` : "No clause evidence is attached to this card yet.")}</p>
      </div>
    `;
  }
  return clauses.map((clause, index) => {
    const heading = wikiAsArray(clause.heading_path).join(" / ");
    return `
      <article class="capability-entitlement-clause">
        <div class="capability-entitlement-evidence-head">
          <strong>${escapeHtml(heading || `Clause ${index + 1}`)}</strong>
          <span>${escapeHtml(clause.page ? `p.${clause.page}` : "page unknown")}</span>
        </div>
        <p>${escapeHtml(clause.raw_clause_text || "No clause text captured for this source clause.")}</p>
      </article>
    `;
  }).join("");
}

function entitlementCardFeatureEvidenceHtml(card) {
  const features = wikiAsArray(card?.source_features);
  if (!features.length) return "";
  return `
    <div class="capability-entitlement-feature-list">
      ${features.map((feature) => `
        <article class="capability-entitlement-feature">
          <div class="capability-entitlement-evidence-head">
            <strong>${escapeHtml([feature.value, feature.unit].filter(Boolean).join(" ") || "Feature value")}</strong>
            <span>${escapeHtml(feature.answer_builder_status || feature.review_status || "feature")}</span>
          </div>
          <p>${escapeHtml(feature.evidence_span_text || "No feature evidence span captured.")}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function entitlementCardRegisterHtml(cards) {
  const rows = wikiAsArray(cards);
  if (!rows.length) {
    return renderEmptyState("No entitlement cards", "No proposed governed Entitlement Cards are available yet.", { eyebrow: "Entitlement" });
  }
  return `
    <div class="capability-entitlement-register" aria-label="All Entitlement Cards">
      ${rows.map((card) => {
        const quantum = card.quantum || {};
        const clauseSummary = entitlementCardClauseSummary(card);
        return `
          <details class="capability-entitlement-card">
            <summary>
              <span>
                <b>${escapeHtml(card.entitlement_label || card.entitlement_id || "Entitlement")}</b>
                <small>${escapeHtml(card.council || "Council unknown")} · ${escapeHtml(String(card.agreement_id || "").toUpperCase())}</small>
              </span>
              <strong>${escapeHtml(quantum.value_text || card.simple_sentence || "Value not stated")}</strong>
            </summary>
            <div class="capability-entitlement-card-body">
              <dl class="capability-entitlement-card-facts">
                <div><dt>Sentence</dt><dd>${escapeHtml(card.simple_sentence || "No simple sentence.")}</dd></div>
                <div><dt>Timeframe</dt><dd>${escapeHtml(quantum.timeframe_or_basis || "Not stated")}</dd></div>
                <div><dt>Cohort</dt><dd>${escapeHtml(quantum.cohort || "Not stated")}</dd></div>
                <div><dt>Condition</dt><dd>${escapeHtml(quantum.condition || "Not stated")}</dd></div>
              </dl>
              <div class="capability-entitlement-definition">
                <span>Definition</span>
                <p>${escapeHtml(card.entitlement_definition || "No entitlement definition projected.")}</p>
              </div>
              <div class="capability-entitlement-definition">
                <span>Clause Summary</span>
                <p>${escapeHtml(clauseSummary)}</p>
              </div>
              <div class="capability-entitlement-evidence-grid">
                <section>
                  <h4>Clauses</h4>
                  ${entitlementCardClauseEvidenceHtml(card)}
                </section>
                <section>
                  <h4>Feature Evidence</h4>
                  ${entitlementCardFeatureEvidenceHtml(card) || "<p class=\"capability-entitlement-evidence-note\">No feature evidence spans projected.</p>"}
                </section>
              </div>
            </div>
          </details>
        `;
      }).join("")}
    </div>
  `;
}

function renderCapabilityEntitlementCardsContent(intelligence) {
  const payload = intelligence?.entitlement_cards || {};
  const repair = intelligence?.entitlement_card_repair_loop || {};
  const summary = payload.summary || {};
  const repairSummary = repair.summary || {};
  const cards = wikiAsArray(payload.cards);
  const blocked = wikiAsArray(payload.blocked_samples);
  const repairRows = wikiAsArray(repair.rows);
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Cards", formatCount(summary.entitlement_cards, "0"), "proposed governed")}
      ${capabilityMetricHtml("Value cells", formatCount(summary.value_extracted_cells, "0"), "source-backed")}
      ${capabilityMetricHtml("Blocked values", formatCount(summary.blocked_value_cells, "0"), "not promoted")}
      ${capabilityMetricHtml("Source", displayFileSize(payload.source?.bytes, DISPLAY_EMPTY), "entitlement cards")}
    </div>
    ${capabilityPipelineFreshnessHtml(intelligence?.pipeline_freshness)}
    <div class="capability-node-contract-grid">
      <article>
        <span>Doctrine</span>
        <strong>Only strong proposals get a card</strong>
        <p>${escapeHtml(payload.method?.doctrine || "If the row needs review, the entitlement card is not emitted.")}</p>
      </article>
      <article>
        <span>Gate</span>
        <strong>No review flags</strong>
        <p>Cards require a definition, source clause, feature value, strong review status, and no blocking process rule flags.</p>
      </article>
      <article>
        <span>Blocked</span>
        <strong>${formatCount(summary.blocked_cells, "0")} cells</strong>
        <p>Blocked cells remain diagnostics without becoming reportable entitlement cards.</p>
      </article>
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Card Status", summary.status_counts)}
      ${capabilitySummaryChipsPanel("Blocked Reasons", summary.gate_failure_counts)}
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Repair Loop</h3>
        <span>${formatCount(repairSummary.entitlements_reviewed, "0")} entitlements</span>
      </div>
      <div class="capability-node-metrics">
        ${capabilityMetricHtml("LLM parsed", formatCount(repairSummary.llm_statuses?.parsed, "0"), "repair reviews")}
        ${capabilityMetricHtml("Blocked rows", formatCount(repairSummary.blocked_rows_reviewed, "0"), "diagnosed")}
        ${capabilityMetricHtml("Blocked values", formatCount(repairSummary.blocked_value_rows_reviewed, "0"), "diagnosed")}
        ${capabilityMetricHtml("Source", displayFileSize(repair.source?.bytes, DISPLAY_EMPTY), "repair loop")}
      </div>
      <div class="wiki-detail-columns capability-node-columns">
        ${capabilitySummaryChipsPanel("Repair Decisions", repairSummary.sample_decisions)}
        ${capabilitySummaryChipsPanel("Repair Failures", repairSummary.failure_counts)}
      </div>
      ${capabilityRowsTableHtml(repairRows, [
        { label: "Entitlement", key: "label" },
        { label: "Blocked values", key: "blocked_value_rows" },
        { label: "Can repair", value: (row) => row.repair_review?.entitlement_card_standard_review?.can_any_blocked_rows_become_cards || "" },
        { label: "Dominant blocker", value: (row) => row.repair_review?.entitlement_card_standard_review?.dominant_blocker || "" },
      ], { limit: 14 })}
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Entitlement Cards</h3>
        <span>${formatCount(cards.length, "0")} available</span>
      </div>
      ${entitlementCardRegisterHtml(cards)}
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Blocked Samples</h3>
        <span>${formatCount(blocked.length, "0")} diagnostics</span>
      </div>
      ${capabilityRowsTableHtml(blocked, [
        { label: "Council", key: "council" },
        { label: "Entitlement", key: "entitlement_label" },
        { label: "State", key: "state" },
        { label: "Gate", value: (row) => wikiAsArray(row.gate_failures).join(", ") },
      ], { limit: 16 })}
    </section>
  `;
}

function renderCapabilityReferenceEdgesContent(intelligence) {
  const edgePayload = intelligence?.reference_edges || {};
  const summary = edgePayload.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Reference edges", formatCount(summary.reference_edges, "0"), "deduped links")}
      ${capabilityMetricHtml("Clause targets", formatCount(summary.clause_targets, "0"), "internal clauses")}
      ${capabilityMetricHtml("External targets", formatCount(summary.external_targets, "0"), "NES/Award/Act")}
      ${capabilityMetricHtml("Schedule targets", formatCount(summary.schedule_targets, "0"), "schedules")}
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Relationship Mix", summary.relationships)}
      <section>
        <h4>Reference Contract</h4>
        <p class="capability-node-page-note">Edges keep definitions, schedules, statutory floors and calculation dependencies explicit, so reviewers do not have to infer them from free text.</p>
      </section>
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Reference Edge Register</h3>
        <span>${formatCount(wikiAsArray(edgePayload.edges).length, "0")} loaded</span>
      </div>
      ${capabilityRowsTableHtml(edgePayload.edges, [
        { label: "Relationship", value: (row) => wikiDisplayLabel(row.relationship) },
        { label: "Agreement", value: (row) => String(row.agreement_id || "").toUpperCase() },
        { label: "From", key: "from_clause_id" },
        { label: "To", value: (row) => row.to_clause || row.to_schedule || row.to_external },
        { label: "Hash", value: (row) => capabilityShortHash(row.text_hash) },
      ], { limit: 16 })}
    </section>
  `;
}

function capabilityQaProfileCardsHtml(profiles) {
  const rows = wikiAsArray(profiles);
  if (!rows.length) {
    return renderEmptyState("No locator profiles", "The QA review pack has not produced entitlement locator profiles yet.", { eyebrow: "Locator" });
  }
  return `
    <div class="capability-locator-card-grid">
      ${rows.map((profile) => {
        const summary = profile.summary || {};
        return `
          <article class="capability-locator-card">
            <div class="capability-locator-card-head">
              <div>
                <span>${escapeHtml(profile.key || profile.entitlement_id || "profile")}</span>
                <h3>${escapeHtml(profile.label || profile.entitlement_id || "Locator profile")}</h3>
              </div>
              <strong>${formatCount(summary.councils, "0")} councils</strong>
            </div>
            <dl class="capability-locator-card-facts">
              <div><dt>Clause found</dt><dd>${formatCount(summary.clause_found, "0")}</dd></div>
              <div><dt>Value found</dt><dd>${formatCount(summary.value_found, "0")}</dd></div>
              <div><dt>Cell states</dt><dd>${capabilityCounterChipsHtml(summary.cell_status_counts, 3)}</dd></div>
              <div><dt>Samples</dt><dd>${formatCount(wikiAsArray(profile.details).length, "0")}</dd></div>
            </dl>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderCapabilityEntitlementLocatorContent(intelligence) {
  const qa = intelligence?.qa_review_pack || {};
  const summary = qa.summary || {};
  const matrixSummary = intelligence?.entitlement_test_matrix?.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Entitlements", formatCount(matrixSummary.final_entitlements ?? summary.profiles, "0"), "test list")}
      ${capabilityMetricHtml("Councils", formatCount(matrixSummary.target_councils, "0"), "current cohort")}
      ${capabilityMetricHtml("Clause cards", capabilityCoverageFraction(matrixSummary.clause_card_ready ?? summary.clause_found, matrixSummary.test_cells ?? summary.details), "candidate cells")}
      ${capabilityMetricHtml("Feature cards", capabilityCoverageFraction(matrixSummary.feature_card_ready ?? summary.value_found, matrixSummary.test_cells ?? summary.details), "candidate cells")}
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Cell Status", summary.cell_statuses)}
      ${capabilitySummaryChipsPanel("Row State", summary.row_states)}
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Locator Profiles</h3>
        <span>${formatCount(wikiAsArray(qa.profiles).length, "0")} profiles</span>
      </div>
      ${capabilityQaProfileCardsHtml(qa.profiles)}
    </section>
  `;
}

function renderCapabilityQaReviewPackContent(intelligence) {
  const qa = intelligence?.qa_review_pack || {};
  const summary = qa.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Profiles", formatCount(summary.profiles, "0"), "review profiles")}
      ${capabilityMetricHtml("Details", formatCount(summary.details, "0"), "locator cells")}
      ${capabilityMetricHtml("Clause found", formatCount(summary.clause_found, "0"), "machine positives")}
      ${capabilityMetricHtml("Value found", formatCount(summary.value_found, "0"), "value positives")}
    </div>
    <div class="capability-node-contract-grid">
      <article>
        <span>Doctrine</span>
        <strong>Review pack, not truth</strong>
        <p>${escapeHtml(qa.doctrine || "Machine locator outputs are review targets only.")}</p>
      </article>
      <article>
        <span>Source</span>
        <strong>${escapeHtml(qa.artifact_id || "QA pack")}</strong>
        <p>${escapeHtml(capabilityArtifactSourceLine(qa.source) || displayDate(qa.generated_at, DISPLAY_EMPTY))}</p>
      </article>
      <article>
        <span>Review Questions</span>
        <strong>${formatCount(wikiAsArray(qa.review_questions).length, "0")}</strong>
        <p>${escapeHtml(wikiAsArray(qa.review_questions).join(" "))}</p>
      </article>
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Guardrails</h3>
        <span>${formatCount(wikiAsArray(qa.guardrails).length, "0")} rules</span>
      </div>
      <div class="capability-node-question-list">
        ${wikiAsArray(qa.guardrails).map((item) => `<article class="capability-node-question"><p>${escapeHtml(item)}</p></article>`).join("")}
      </div>
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Profile Summary</h3>
        <span>${formatCount(wikiAsArray(qa.profiles).length, "0")} profiles</span>
      </div>
      ${capabilityQaProfileCardsHtml(qa.profiles)}
    </section>
  `;
}

function renderCapabilityGoldSeedRowsContent(intelligence) {
  const payload = intelligence?.gold_seed_rows || {};
  const summary = payload.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Gold rows", formatCount(summary.rows, "0"), "review targets")}
      ${capabilityMetricHtml("Follow up", formatCount(summary.follow_up_required, "0"), "requires human review")}
      ${capabilityMetricHtml("Eligible", formatCount(summary.eligible_for_governance, "0"), "currently promotable")}
      ${capabilityMetricHtml("Source", displayFileSize(payload.source?.bytes, DISPLAY_EMPTY), "JSONL")}
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Review Status", summary.review_statuses)}
      ${capabilitySummaryChipsPanel("Machine Cell Status", summary.machine_cell_statuses)}
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Gold Seed Rows</h3>
        <span>${formatCount(wikiAsArray(payload.rows).length, "0")} displayed</span>
      </div>
      ${capabilityRowsTableHtml(payload.rows, [
        { label: "Council", key: "council" },
        { label: "Entitlement", key: "entitlement_label" },
        { label: "Machine", key: "machine_cell_status" },
        { label: "Review", key: "review_status" },
        { label: "Clause", key: "clause_card_id" },
      ], { limit: 16 })}
    </section>
  `;
}

function renderCapabilityCodexSuggestionsContent(intelligence) {
  const payload = intelligence?.codex_suggestions || {};
  const summary = payload.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Suggestions", formatCount(summary.rows, "0"), "advisory rows")}
      ${capabilityMetricHtml("Human confirm", formatCount(summary.requires_human_confirmation, "0"), "required")}
      ${capabilityMetricHtml("Risk flags", formatCount(Object.keys(summary.risk_flags || {}).length, "0"), "flag types")}
      ${capabilityMetricHtml("Source", displayFileSize(payload.source?.bytes, DISPLAY_EMPTY), "JSONL")}
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Confidence", summary.confidence)}
      ${capabilitySummaryChipsPanel("Suggested Decision", summary.suggested_review_decisions)}
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Advisory Suggestions</h3>
        <span>${formatCount(wikiAsArray(payload.rows).length, "0")} displayed</span>
      </div>
      ${capabilityRowsTableHtml(payload.rows, [
        { label: "Gold row", key: "gold_review_id" },
        { label: "Confidence", key: "confidence" },
        { label: "Decision", key: "suggested_review_decision" },
        { label: "Scope", key: "suggested_scope" },
        { label: "Risks", value: (row) => wikiAsArray(row.risk_flags).join(", ") },
      ], { limit: 16 })}
    </section>
  `;
}

function renderCapabilityHumanReviewWorksheetContent(intelligence) {
  const payload = intelligence?.human_review_worksheet || {};
  const summary = payload.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Rows", formatCount(summary.rows, "0"), "worksheet lines")}
      ${capabilityMetricHtml("Columns", formatCount(wikiAsArray(payload.columns).length, "0"), "review fields")}
      ${capabilityMetricHtml("CSV", displayFileSize(payload.source?.bytes, DISPLAY_EMPTY), "worksheet")}
      ${capabilityMetricHtml("Markdown", displayFileSize(payload.markdown?.bytes, DISPLAY_EMPTY), "brief")}
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Machine Status", summary.machine_cell_statuses)}
      ${capabilitySummaryChipsPanel("Codex Confidence", summary.codex_confidence)}
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Blank Human Fields</h3>
        <span>semantic judgement still pending</span>
      </div>
      <div class="wiki-chip-cloud">${capabilityCounterChipsHtml(summary.blank_human_fields, 12)}</div>
    </section>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Worksheet Rows</h3>
        <span>${formatCount(wikiAsArray(payload.rows).length, "0")} displayed</span>
      </div>
      ${capabilityRowsTableHtml(payload.rows, [
        { label: "Council", key: "council" },
        { label: "Entitlement", key: "entitlement_label" },
        { label: "Machine", key: "machine_cell_status" },
        { label: "Codex", key: "codex_suggested_review_decision" },
        { label: "Human decision", key: "human_review_decision" },
      ], { limit: 14 })}
    </section>
  `;
}

function renderCapabilityGovernedEntitlementMeasuresContent(intelligence) {
  const payload = intelligence?.governed_entitlement_measures || {};
  const summary = payload.summary || {};
  return `
    <div class="capability-node-metrics">
      ${capabilityMetricHtml("Rows", formatCount(summary.rows, "0"), "canonical entitlement items")}
      ${capabilityMetricHtml("Mart rows", formatCount(summary.mart_rows, "0"), summary.mart_id || "summary mart")}
      ${capabilityMetricHtml("Source", displayFileSize(payload.source?.bytes, DISPLAY_EMPTY), "governed canonical")}
      ${capabilityMetricHtml("Datamart", displayFileSize(payload.summary_mart?.bytes, DISPLAY_EMPTY), "summary view")}
    </div>
    <div class="wiki-detail-columns capability-node-columns">
      ${capabilitySummaryChipsPanel("Governed Canonical Status", summary.governed_canonical_statuses)}
      ${capabilitySummaryChipsPanel("Value Status", summary.value_statuses)}
    </div>
    <section class="capability-node-section">
      <div class="capability-node-section-head">
        <h3>Governed Entitlement Rows</h3>
        <span>${formatCount(wikiAsArray(payload.rows).length, "0")} displayed</span>
      </div>
      ${capabilityRowsTableHtml(payload.rows, [
        { label: "Entitlement", key: "entitlement_label" },
        { label: "Category", key: "category" },
        { label: "Scope", key: "scope" },
        { label: "Governance", key: "governed_canonical_status" },
        { label: "Value", key: "value_status" },
      ], { limit: 18 })}
    </section>
  `;
}

function renderCapabilityNodeContent(nodeId, detail, intelligence) {
  if (nodeId === "document_spine") return renderCapabilityDocumentSpineContent(detail);
  if (nodeId === "clause_evidence_graph") return renderCapabilityEvidenceGraphContent(detail, intelligence);
  if (nodeId === "clause_cards") return renderCapabilityClauseCardsContent(detail, intelligence?.clause_cards || state.wikiClauseCards);
  if (nodeId === "feature_cards") return renderCapabilityFeatureCardsContent(intelligence);
  if (nodeId === "entitlement_cards") return renderCapabilityEntitlementCardsContent(intelligence);
  if (nodeId === "reference_edges") return renderCapabilityReferenceEdgesContent(intelligence);
  if (nodeId === "entitlement_locator") return renderCapabilityEntitlementLocatorContent(intelligence);
  if (nodeId === "qa_review_pack") return renderCapabilityQaReviewPackContent(intelligence);
  if (nodeId === "gold_seed_rows") return renderCapabilityGoldSeedRowsContent(intelligence);
  if (nodeId === "codex_suggestions") return renderCapabilityCodexSuggestionsContent(intelligence);
  if (nodeId === "human_review_worksheet") return renderCapabilityHumanReviewWorksheetContent(intelligence);
  if (nodeId === "governed_entitlement_measures") return renderCapabilityGovernedEntitlementMeasuresContent(intelligence);
  return renderEmptyState("No node renderer", "This capability node has no dedicated content surface yet.", { eyebrow: "Clause intelligence" });
}

async function hydrateCapabilityNodePage(nodeId) {
  if (!CAPABILITY_NODE_PAGE_IDS.has(nodeId)) return;
  const body = document.getElementById("capability-node-page-body");
  if (!body) return;
  body.innerHTML = `<div class="wiki-loading-row">Loading ${escapeHtml(capabilityNodePageTitle(nodeId).toLowerCase())}...</div>`;
  try {
    if (nodeId === "datamart_inventory") {
      const catalog = await ensureAgentCatalog();
      if (!capabilityCurrentNodePageIs(nodeId)) return;
      body.innerHTML = renderCapabilityDatamartInventoryContent(catalog);
      return;
    }
    await Promise.all([ensureWikiDocumentMaps(), ensureCouncilRows()]);
    if (!capabilityCurrentNodePageIs(nodeId)) return;
    const options = capabilityAgreementOptions();
    const selectedAeId = capabilitySelectedDocumentMapId(options);
    const selectedOption = options.find((option) => option.agreement_id === selectedAeId) || null;
    state.capabilitySelectedAgreementId = selectedAeId;
    const select = document.getElementById("capability-document-map-select");
    if (select) {
      select.innerHTML = capabilityDocumentMapOptionsHtml(options);
      select.value = selectedAeId;
      select.onchange = (event) => {
        state.capabilitySelectedAgreementId = String(event.target.value || "").toLowerCase();
        hydrateCapabilityNodePage(nodeId).catch((error) => toast(apiErrorMessage(error), "error"));
      };
    }
    const note = document.getElementById("capability-document-map-note");
    if (note) {
      const mapCount = options.filter((option) => option.hasDocumentMap).length;
      note.textContent = `${formatCount(options.length, "0")} agreements / ${formatCount(mapCount, "0")} document maps`;
    }
    if (!selectedAeId) {
      body.innerHTML = renderEmptyState("No agreements loaded", "Load the council register before opening this clause-intelligence node.", { eyebrow: "Clause intelligence" });
      return;
    }
    const detail = selectedOption?.hasDocumentMap
      ? await ensureWikiDocumentMapDetail(selectedAeId)
      : capabilityPlaceholderDocumentMap(selectedOption);
    if (!capabilityCurrentNodePageIs(nodeId)) return;
    const intelligence = nodeId === "document_spine"
      ? null
      : await ensureWikiClauseIntelligence();
    if (!capabilityCurrentNodePageIs(nodeId)) return;
    const pendingNotice = selectedOption?.hasDocumentMap ? "" : capabilityPendingDocumentMapNoticeHtml(selectedOption);
    body.innerHTML = `${pendingNotice}${renderCapabilityNodeContent(nodeId, detail, intelligence)}`;
  } catch (error) {
    if (!capabilityCurrentNodePageIs(nodeId)) return;
    body.innerHTML = renderEmptyState("Node content failed to load", apiErrorMessage(error), { eyebrow: capabilityNodePageTitle(nodeId) });
  }
}

function renderCapabilityDashboard() {
  const branch = capabilityBranchById(state.currentCapabilityBranch);
  if (!branch) return;
  const children = capabilityPrimaryChildren(branch);
  const selectedNode = capabilityChildById(branch, state.currentCapabilityNode);
  const focusNode = selectedNode || branch;
  const focusedNodePage = Boolean(selectedNode && CAPABILITY_NODE_PAGE_IDS.has(selectedNode.id));
  const artifactPaths = capabilityArtifactPaths(focusNode);
  const shell = document.querySelector(".capability-dashboard-shell");
  shell?.classList.toggle("is-focused-node", focusedNodePage);
  const title = document.getElementById("capability-dashboard-title");
  const description = document.getElementById("capability-dashboard-description");
  const branchCount = document.getElementById("capability-dashboard-branch-count");
  const nodeCount = document.getElementById("capability-dashboard-node-count");
  const status = document.getElementById("capability-dashboard-status");
  const artifactCount = document.getElementById("capability-dashboard-artifact-count");
  if (title) {
    const iconHtml = capabilityIconHtml(focusNode.icon || branch.icon, "capability-dashboard-title-icon");
    title.innerHTML = `${iconHtml}<span>${escapeHtml(focusNode.label)}</span>`;
  }
  if (description) description.textContent = selectedNode
    ? `${branch.label}: ${focusNode.description || ""}`
    : branch.description || "";
  if (branchCount) branchCount.textContent = String(capabilityTreeBranches().findIndex((item) => item.id === branch.id) + 1);
  if (nodeCount) nodeCount.textContent = String(children.length);
  if (status) status.textContent = governanceStatusDefinition(focusNode.status).label;
  if (artifactCount) artifactCount.textContent = String(artifactPaths.length);
  renderCapabilityBranchList();
  const detail = document.getElementById("capability-dashboard-detail");
  if (!detail) return;
  if (focusedNodePage) {
    detail.innerHTML = renderCapabilityNodePageScaffold(selectedNode);
    hydrateCapabilityNodePage(selectedNode.id).catch((error) => toast(apiErrorMessage(error), "error"));
    updateCapabilityTreeActiveState();
    return;
  }
  if (!selectedNode && branch.id === "clause_intelligence") {
    detail.innerHTML = renderCapabilityEntitlementQaInboxLoading();
    hydrateCapabilityEntitlementQaInbox().catch((error) => toast(apiErrorMessage(error), "error"));
    updateCapabilityTreeActiveState();
    return;
  }
  if (!selectedNode && branch.id === "pay_uplift") {
    detail.innerHTML = renderPayUpliftWorklist();
    wirePayUpliftWorklist(detail);
    updateCapabilityTreeActiveState();
    return;
  }
  const artifactHtml = artifactPaths.length
    ? `<div class="capability-artifact-list capability-artifact-list-wide">${artifactPaths.map((path) => `<code>${escapeHtml(path)}</code>`).join("")}</div>`
    : `<div class="capability-card-note">No branch-level artifact paths declared yet.</div>`;
  detail.innerHTML = `
    <section class="capability-ownership-band">
      <div>
        <span class="capability-card-kicker">${selectedNode ? "Node ownership" : "Ownership"}</span>
        <p>${escapeHtml(focusNode.ownershipNote || branch.ownershipNote || "")}</p>
      </div>
      <div>
        <span class="capability-card-kicker">Report safety</span>
        <p>${escapeHtml(branch.safeUse || "Use only according to node governance status.")}</p>
      </div>
      <div>
        <span class="capability-card-kicker">Governance state</span>
        ${capabilityStatusChip(focusNode.status)}
      </div>
    </section>
    ${renderCapabilityNodePageScaffold(selectedNode)}
    ${renderCapabilityPipeline(branch, selectedNode?.id || "")}
    <section class="capability-detail-grid">
      ${children.map((child) => renderCapabilityChildCard(child, selectedNode?.id || "")).join("")}
    </section>
    ${renderCapabilitySecondarySurfaces(branch, selectedNode?.id || "")}
    <section class="capability-artifact-section">
      <h2>Declared Artifacts</h2>
      ${artifactHtml}
    </section>
  `;
  detail.querySelectorAll("[data-workbench-route]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      openWorkbenchRoute(button.dataset.workbenchRoute).catch((error) => toast(apiErrorMessage(error), "error"));
    });
  });
  document.getElementById("capability-dashboard-branch-list")?.querySelectorAll("[data-workbench-route]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      openWorkbenchRoute(button.dataset.workbenchRoute).catch((error) => toast(apiErrorMessage(error), "error"));
    });
  });
  hydrateCapabilityNodePage(selectedNode?.id || "").catch((error) => toast(apiErrorMessage(error), "error"));
  updateCapabilityTreeActiveState();
}

function routeForWorkbenchView(view = document.body.dataset.view || "incoming") {
  if (view === "capability") {
    const branch = state.currentCapabilityBranch || "source_custody";
    return state.currentCapabilityNode ? `#capability/${branch}/${state.currentCapabilityNode}` : `#capability/${branch}`;
  }
  if (view === "analysis") return `#data/${state.currentDataSet || "uplift_rules"}`;
  if (view === "audit") {
    return state.auditCouncil ? `#audit/${encodeURIComponent(state.auditCouncil)}` : "#audit";
  }
  if (view === "workspace") {
    const currentSection = SECTION_LABELS[state.currentSection] ? state.currentSection : "overview";
    const section = encodeURIComponent(currentSection);
    const aeId = state.currentCouncil?.agreement_id;
    return aeId ? `#workspace/${encodeURIComponent(aeId)}/${section}` : `#workspace/${section}`;
  }
  return `#${view || "intake"}`;
}

function currentWorkbenchDestination(view = document.body.dataset.view || "incoming") {
  const route = routeForWorkbenchView(view);
  if (view === "capability") {
    const branch = capabilityBranchById(state.currentCapabilityBranch);
    const node = capabilityChildById(branch, state.currentCapabilityNode);
    return {
      route,
      label: node?.label || branch?.label || "Workbench Capability Tree",
      detail: node?.description || branch?.description || "Governed production system map",
      keywords: [branch?.label, branch?.id, node?.label, node?.id, "capability", "governance", "tree"],
    };
  }
  if (view === "analysis") {
    const config = currentDataSetConfig();
    return {
      route,
      label: config.title,
      detail: config.tableDescription || config.description,
      keywords: [config.label, config.runId, config.sourceInput, config.sourceUse],
    };
  }
  if (view === "workspace") {
    const section = SECTION_LABELS[state.currentSection] ? state.currentSection : "overview";
    const sectionLabel = SECTION_LABELS[section];
    const context = currentWorkspaceContext();
    const councilName = context.councilName === "Unknown council" ? "Workspace" : context.councilName;
    return {
      route,
      label: `${councilName} - ${sectionLabel}`,
      detail: context.aeId ? `${context.aeId} / ${context.agreementName}` : context.agreementName,
      keywords: [sectionLabel, section, context.councilName, context.agreementName, context.aeId],
    };
  }
  if (view === "audit") {
    const council = state.auditReport?.council?.short_name || state.auditCouncil || "Council";
    const latest = state.auditReport?.latest;
    return {
      route,
      label: `${council} audit`,
      detail: latest ? `${String(latest.ae_id || "").toUpperCase()} / ${latest.title || "latest agreement"}` : "Agreement lineage and process history",
      keywords: [council, "audit", "lineage", "report", latest?.ae_id, latest?.title],
    };
  }
  const defaults = {
    incoming: ["Incoming", "New registry candidates grouped by confidence", ["incoming", "source", "registry", "confidence"]],
    intake: ["Intake Processing", "Accepted source processing and PDF fetch queue", ["intake", "processing", "source", "pdf", "fetch"]],
    "job-intake": ["Job Intake", "Council job source registry and endpoint readiness", ["job", "jobs", "careers", "ats", "source", "registry"]],
    "job-pipeline": ["Job Pipeline", "Band-governed job field completion", ["job", "pipeline", "stage", "band", "field", "completion"]],
    matrix: ["Review Board", "Agreement pipeline and section progress", ["matrix", "review", "pipeline"]],
    wiki: ["Wiki", "Entitlement, condition, benefit and clause-context maps", ["wiki", "document map", "clause context", "language map"]],
    admin: ["Settings", "Provider status, rate caps and reference controls", ["admin", "settings", "rate cap", "llm"]],
  };
  const [label, detail, keywords] = defaults[view] || defaults.incoming;
  return { route, label, detail, keywords };
}

function readRecentWorkbenchDestinations() {
  if (typeof window === "undefined" || !window.localStorage) return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(RECENT_WORKBENCH_DESTINATIONS_KEY) || "[]");
    return Array.isArray(parsed)
      ? parsed
        .filter((item) => item?.route && item?.label)
        .filter((item) => RECENT_WORKBENCH_ROUTE_PREFIXES.some((prefix) => {
          const route = String(item.route);
          return route === prefix || route.startsWith(`${prefix}/`);
        }))
        .slice(0, RECENT_WORKBENCH_DESTINATIONS_LIMIT)
      : [];
  } catch {
    return [];
  }
}

function writeRecentWorkbenchDestinations(destinations) {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(
      RECENT_WORKBENCH_DESTINATIONS_KEY,
      JSON.stringify(destinations.slice(0, RECENT_WORKBENCH_DESTINATIONS_LIMIT)),
    );
  } catch {
    // Recent destinations are a convenience only.
  }
}

function saveReviewBoardAutomationDetailsOpen() {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(
      REVIEW_BOARD_AUTOMATION_DETAILS_KEY,
      JSON.stringify(state.reviewBoardAutomationDetailsOpen || {}),
    );
  } catch {
    // Disclosure persistence is a convenience; the UI still works without it.
  }
}

function reviewBoardAutomationKey(aeId) {
  return String(aeId || "").toLowerCase();
}

function hasReviewBoardAutomationOpenPreference(aeId) {
  const key = reviewBoardAutomationKey(aeId);
  return Boolean(key) && Object.prototype.hasOwnProperty.call(state.reviewBoardAutomationDetailsOpen, key);
}

function setReviewBoardAutomationDetailsOpen(aeId, open) {
  const key = reviewBoardAutomationKey(aeId);
  if (!key) return;
  state.reviewBoardAutomationDetailsOpen[key] = Boolean(open);
  saveReviewBoardAutomationDetailsOpen();
}

function matrixAutomationDetailsAeId(details) {
  return details?.dataset?.matrixAutomationAeId
    || details?.closest("[data-matrix-card-ae-id]")?.dataset?.matrixCardAeId
    || "";
}

function setMatrixAutomationDetailsOpen(details, open) {
  if (!details) return;
  details.open = Boolean(open);
  const aeId = matrixAutomationDetailsAeId(details);
  if (aeId) setReviewBoardAutomationDetailsOpen(aeId, details.open);
}

function toggleMatrixAutomationDetails(details) {
  setMatrixAutomationDetailsOpen(details, !details?.open);
}

function reviewBoardAutomationDetailsIsOpen(aeId) {
  const key = reviewBoardAutomationKey(aeId);
  if (!key) return false;
  if (hasReviewBoardAutomationOpenPreference(key)) {
    return Boolean(state.reviewBoardAutomationDetailsOpen[key]);
  }
  const prep = overviewPreparationState(key);
  const human = syntheticHumanReviewState(key);
  const prepJobs = Object.values(prep?.jobs || {});
  const humanJobs = Object.values(human?.jobs || {});
  return state.reviewBoardAutomationActiveAeId === key
    || Boolean(prep?.running || human?.running)
    || prepJobs.some((job) => job.status === "running")
    || humanJobs.some((job) => job.status === "running");
}

function captureMatrixAutomationDisclosureState(list) {
  list?.querySelectorAll(".matrix-auto-details").forEach((details) => {
    const aeId = matrixAutomationDetailsAeId(details);
    if (aeId) setReviewBoardAutomationDetailsOpen(aeId, details.open);
  });
}

function wireMatrixAutomationDisclosureState(list) {
  list?.querySelectorAll(".matrix-auto-details").forEach((details) => {
    details.addEventListener("toggle", () => {
      const aeId = matrixAutomationDetailsAeId(details);
      if (aeId) setReviewBoardAutomationDetailsOpen(aeId, details.open);
    });
    const summary = details.querySelector("summary");
    summary?.addEventListener("click", (event) => {
      event.preventDefault();
      toggleMatrixAutomationDetails(details);
    });
    summary?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      toggleMatrixAutomationDetails(details);
    });
  });
}

function recordRecentWorkbenchDestination(view = document.body.dataset.view || "incoming") {
  if (suppressWorkbenchRouteSync) return;
  const destination = {
    ...currentWorkbenchDestination(view),
    savedAt: new Date().toISOString(),
  };
  const existing = readRecentWorkbenchDestinations().filter((item) => item.route !== destination.route);
  writeRecentWorkbenchDestinations([destination, ...existing]);
}

function syncWorkbenchRoute(view = document.body.dataset.view || "incoming") {
  if (suppressWorkbenchRouteSync || typeof window === "undefined") return;
  const nextHash = routeForWorkbenchView(view);
  if (window.location.hash !== nextHash) {
    window.history.replaceState(null, "", nextHash);
  }
  recordRecentWorkbenchDestination(view);
}

function currentWorkbenchUrl() {
  if (typeof window === "undefined") return "";
  const view = document.body.dataset.view || "incoming";
  syncWorkbenchRoute(view);
  return `${window.location.origin}${window.location.pathname}${routeForWorkbenchView(view)}`;
}

async function writeClipboardText(text) {
  if (window.navigator?.clipboard?.writeText) {
    await window.navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    const copied = document.execCommand("copy");
    if (!copied) throw new Error("copy command failed");
  } finally {
    textarea.remove();
  }
}

async function copyCurrentWorkbenchLink() {
  const url = currentWorkbenchUrl();
  if (!url) {
    toast("No current view link available", "error");
    return;
  }
  try {
    await writeClipboardText(url);
    toast("Current view link copied", "success");
  } catch (error) {
    toast(`Copy failed: ${apiErrorMessage(error)}`, "error");
  }
}

function parseWorkbenchRoute() {
  if (typeof window === "undefined") return null;
  const rawHash = decodeURIComponent(window.location.hash || "").replace(/^#\/?/, "").trim();
  if (!rawHash) return null;
  const [area, detail, extra] = rawHash.split("/").filter(Boolean);
  if (area === "capability") {
    return { view: "capability", capabilityBranch: detail || "source_custody", capabilityNode: extra || "" };
  }
  if (area === "data" || area === "analysis") {
    return { view: "analysis", dataSet: DATA_SET_CONFIG[detail] ? detail : "uplift_rules" };
  }
  if (area === "workspace") {
    if (!detail) return { view: "workspace", section: "overview" };
    if (SECTION_LABELS[detail]) return { view: "workspace", section: detail };
    return {
      view: "workspace",
      aeId: detail,
      section: SECTION_LABELS[extra] ? extra : "overview",
    };
  }
  if (area === "audit") {
    return { view: "audit", council: detail || "" };
  }
  if (["incoming", "intake", "job-intake", "job-pipeline", "matrix", "wiki", "admin"].includes(area)) {
    return { view: area };
  }
  return null;
}

function applyInitialWorkbenchViewFromHash() {
  const route = parseWorkbenchRoute();
  if (!route) {
    switchView("capability");
    return;
  }
  if (route.view === "capability") {
    const branch = capabilityBranchById(route.capabilityBranch);
    state.currentCapabilityBranch = branch?.id || "source_custody";
    state.currentCapabilityNode = capabilityChildById(branch, route.capabilityNode)?.id || "";
    switchView("capability");
    return;
  }
  if (route.view === "analysis") {
    setCurrentDataSet(route.dataSet || "uplift_rules");
    switchView("analysis", { renderAnalysis: false });
    renderAnalysisWorkspace().catch((error) => toast(apiErrorMessage(error), "error"));
    return;
  }
  if (route.view === "audit") {
    switchView("audit", { renderAudit: false });
    return;
  }
  if (route.view === "workspace") {
    switchView("workspace");
    return;
  }
  switchView(route.view);
}

async function applyWorkbenchRouteFromHash() {
  const route = parseWorkbenchRoute();
  if (!route) return false;
  suppressWorkbenchRouteSync = true;
  let appliedView = null;
  try {
    if (route.view === "capability") {
      const branch = capabilityBranchById(route.capabilityBranch);
      state.currentCapabilityBranch = branch?.id || "source_custody";
      state.currentCapabilityNode = capabilityChildById(branch, route.capabilityNode)?.id || "";
      switchView("capability");
      appliedView = "capability";
      return true;
    }
    if (route.view === "analysis") {
      setCurrentDataSet(route.dataSet || "uplift_rules");
      switchView("analysis", { renderAnalysis: false });
      await renderAnalysisWorkspace();
      appliedView = "analysis";
      return true;
    }
    if (route.view === "workspace") {
      if (route.aeId) {
        await openCouncil(route.aeId, route.section || "overview");
      } else {
        await openDefaultWorkspaceAgreement(route.section || "overview");
      }
      appliedView = "workspace";
      return true;
    }
    if (route.view === "audit") {
      switchView("audit", { renderAudit: false });
      await renderCouncilAudit(route.council || defaultAuditCouncil());
      appliedView = "audit";
      return true;
    }
    switchView(route.view);
    if (route.view === "matrix") {
      renderMatrix();
      renderMatrixStats();
    } else if (route.view === "incoming") {
      renderIncoming();
    } else if (route.view === "intake") {
      renderIntake();
    } else if (route.view === "job-intake") {
      renderJobIntake();
    } else if (route.view === "job-pipeline") {
      renderJobPipeline();
    } else if (route.view === "wiki") {
      await renderWikiCockpit();
    } else if (route.view === "admin") {
      await renderLlmStatusPane();
      await renderRateCapAdminPane();
    }
    appliedView = route.view;
    return true;
  } finally {
    suppressWorkbenchRouteSync = false;
    if (appliedView) recordRecentWorkbenchDestination(appliedView);
  }
}

async function openWorkbenchRoute(route) {
  if (typeof window === "undefined" || !route) return;
  const target = String(route);
  if (/^https?:\/\//i.test(target) || target.startsWith("/")) {
    window.location.assign(target);
    return;
  }
  window.history.pushState(null, "", target);
  await applyWorkbenchRouteFromHash();
}

function updateDataSetNav() {
  document.querySelectorAll("[data-analysis-kind]").forEach((button) => {
    const active = document.body.dataset.view === "analysis" && button.dataset.analysisKind === state.currentDataSet;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function switchView(view, { renderAnalysis = true, renderAudit = true } = {}) {
  const views = ["capability", "incoming", "intake", "job-intake", "job-pipeline", "matrix", "workspace", "analysis", "audit", "wiki", "admin"];
  const target = views.includes(view) ? view : "capability";
  document.body.dataset.view = target;
  if (target !== "workspace") clearSectionFinalFloatingSlot();
  for (const v of views) {
    const active = v === target;
    const viewEl = document.getElementById(`view-${v}`);
    const navEl = document.getElementById(`nav-${v}`);
    const navActive = active || (target === "workspace" && v === "matrix");
    if (viewEl) viewEl.classList.toggle("active", active);
    if (viewEl) viewEl.setAttribute("aria-hidden", String(!active));
    if (navEl) {
      navEl.classList.toggle("active", navActive);
      if (navActive) navEl.setAttribute("aria-current", "page");
      else navEl.removeAttribute("aria-current");
    }
  }
  updateDataSetNav();
  updateCapabilityTreeActiveState();
  updateStageRail(target);
  updateHeaderForView(target);
  renderSectionsList();
  if (target === "capability") renderCapabilityDashboard();
  if (target === "incoming") renderIncoming();
  if (target === "job-intake") renderJobIntake();
  if (target === "job-pipeline") renderJobPipeline();
  if (target === "matrix") renderMatrix();
  if (target === "analysis" && renderAnalysis) renderAnalysisWorkspace();
  if (target === "audit" && renderAudit) renderCouncilAudit();
  if (target === "wiki") renderWikiCockpit().catch((error) => toast(apiErrorMessage(error), "error"));
  syncWorkbenchRoute(target);
}

function renderActiveLoadedWorkbenchView() {
  const activeView = document.body.dataset.view || "incoming";
  if (activeView === "capability") {
    renderCapabilityDashboard();
    return;
  }
  if (activeView === "incoming") {
    renderIncoming();
    return;
  }
  if (activeView === "matrix") {
    renderMatrix();
    renderMatrixStats();
    return;
  }
  if (activeView === "intake") {
    renderIntake();
    return;
  }
  if (activeView === "job-intake") {
    renderJobIntake();
    return;
  }
  if (activeView === "job-pipeline") {
    renderJobPipeline();
    return;
  }
  if (activeView === "wiki") {
    renderWikiCockpit().catch((error) => toast(apiErrorMessage(error), "error"));
  }
}

function updateHeaderForView(view) {
  const title = document.querySelector(".top-status-title");
  const subtitle = document.querySelector(".top-status-subtitle");
  const stats = document.getElementById("header-stats");
  const copy = {
    capability: ["Capability Tree", "Navigate the governed production system."],
    incoming: ["Incoming", "Review new source candidates before intake processing."],
    intake: ["", ""],
    "job-intake": ["Job Intake", "Monitor council job-source readiness and ATS coverage."],
    "job-pipeline": ["Job Pipeline", "Advance governed job records through field completion."],
    matrix: ["Review Board", "Track extraction, validation and governance by agreement."],
    workspace: ["Agreement Workspace", "Validate PDF evidence, extraction drafts and governed outputs."],
    analysis: ["Data Sets", "Inspect governed entities before analysis."],
    audit: ["Council Audit", "Trace lineage, intake, review and governed changes for one council."],
    wiki: ["Wiki", "Inspect agreement maps, language signals and the learning backlog."],
    admin: ["Settings", "Maintain shared reference data used by the workbench."],
  };
  const [heading, subheading] = copy[view] || copy.incoming;
  if (title) title.textContent = heading;
  if (subtitle) subtitle.textContent = subheading;
  document.title = `${heading} | Municipal Benchmark Workbench`;
  if (view === "incoming") renderIncoming();
  if (view === "matrix") renderMatrixStats();
  if (view === "intake") renderIntake();
  if (view === "job-intake") renderJobIntake();
  if (view === "job-pipeline") renderJobPipeline();
  if (view === "workspace" && stats && state.currentCouncil) stats.textContent = state.currentCouncil.agreement_id.toUpperCase();
  if (view === "capability" && stats) stats.textContent = "Tree";
  if (view === "job-intake" && stats) stats.textContent = "Jobs";
  if (view === "job-pipeline" && stats) stats.textContent = "Stage 1";
  if (view === "analysis" && stats) stats.textContent = currentDataSetConfig().label;
  if (view === "audit" && stats) stats.textContent = state.auditReport?.council?.short_name || state.auditCouncil || "Audit";
  if (view === "wiki" && stats) stats.textContent = "Knowledge";
  if (view === "admin" && stats) stats.textContent = "Settings";
  renderAgreementNavigator();
}

function updateStageRail(view) {
  const rail = document.getElementById("stage-rail");
  if (!rail) return;
  if (view === "capability") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-structure">Source</span>',
      '<span class="stage-badge stage-badge-evidence">Evidence</span>',
      '<span class="stage-badge stage-badge-review">Review</span>',
      '<span class="stage-badge stage-badge-success">Governed</span>',
    ].join("");
    return;
  }
  if (view === "incoming") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-structure">Registry</span>',
      '<span class="stage-badge stage-badge-evidence">Confidence</span>',
      '<span class="stage-badge stage-badge-review">Accept</span>',
    ].join("");
    return;
  }
  if (view === "intake") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-structure">Fetch</span>',
      '<span class="stage-badge stage-badge-evidence">Fetch PDF</span>',
      '<span class="stage-badge stage-badge-review">Scope QA</span>',
    ].join("");
    return;
  }
  if (view === "job-intake") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-structure">Registry</span>',
      '<span class="stage-badge stage-badge-evidence">Official URLs</span>',
      '<span class="stage-badge stage-badge-review">Compliance</span>',
    ].join("");
    return;
  }
  if (view === "job-pipeline") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-structure">Snapshot</span>',
      '<span class="stage-badge stage-badge-evidence">Band governed</span>',
      '<span class="stage-badge stage-badge-review">Stage 1 fields</span>',
    ].join("");
    return;
  }
  if (view === "matrix") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-structure">Source readiness</span>',
      '<span class="stage-badge stage-badge-evidence">Extraction</span>',
      '<span class="stage-badge stage-badge-review">Validation</span>',
      '<span class="stage-badge stage-badge-success">Governance</span>',
    ].join("");
    return;
  }
  if (view === "workspace") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-evidence">Extraction</span>',
      '<span class="stage-badge stage-badge-review">Validation</span>',
      '<span class="stage-badge stage-badge-success">Governance</span>',
    ].join("");
    return;
  }
  if (view === "analysis") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-success">Governed source</span>',
      '<span class="stage-badge stage-badge-evidence">Entity set</span>',
      `<span class="stage-badge stage-badge-review">${escapeHtml(currentDataSetConfig().label)}</span>`,
    ].join("");
    return;
  }
  if (view === "wiki") {
    rail.innerHTML = [
      '<span class="stage-badge stage-badge-structure">Document map</span>',
      '<span class="stage-badge stage-badge-evidence">Language map</span>',
      '<span class="stage-badge stage-badge-review">Questions</span>',
      '<span class="stage-badge stage-badge-success">Learning backlog</span>',
    ].join("");
    return;
  }
  rail.innerHTML = [
    '<span class="stage-badge stage-badge-structure">Settings</span>',
    '<span class="stage-badge stage-badge-warning">Reference data</span>',
  ].join("");
}

async function openDefaultWorkspaceAgreement(section = "overview") {
  const targetSection = SECTION_LABELS[section] ? section : "overview";
  if (state.currentCouncil) {
    state.currentSection = openableWorkspaceSection(targetSection, { notify: true });
    switchView("workspace");
    renderSectionPane();
    return;
  }
  const reviewRows = reviewBoardRows();
  const firstAvailable = reviewRows.find((item) => item.section_statuses?.pay_tables !== "done") || reviewRows[0];
  if (!firstAvailable) {
    switchView("workspace");
    toast("No agreements loaded for the workspace yet", "error");
    return;
  }
  await openCouncil(firstAvailable.ae_id, targetSection);
}

function statusDot(status) {
  return `<span class="status-dot dot dot-${status}" title="${status}"></span>`;
}

function statusPill(status) {
  const label = status === "qa_off"
    ? "QA off"
    : status === "blocked"
    ? "Blocked"
    : String(status || "not_started").replaceAll("_", " ");
  return `<span class="status-pill status-${escapeHtml(status)}">${escapeHtml(label)}</span>`;
}

function pipelineLedState(status) {
  if (status === "done") {
    return {
      tone: "complete",
      label: "Complete",
    };
  }
  if (status === "not_started" || !status) {
    return {
      tone: "not-started",
      label: "Not started",
    };
  }
  return {
    tone: "human-needed",
    label: "Human needed",
  };
}

function sectionRawStatus(section) {
  const status = state.currentCouncil?.sections?.[section]?.status
    || state.currentCouncil?.section_statuses?.[section]
    || "not_started";
  return typeof status === "string" ? status : "not_started";
}

function pipelineAutomationStatusForSection(section, aeId = state.currentCouncil?.agreement_id) {
  if (!aeId) return "";
  const prep = overviewPreparationState(aeId);
  const human = syntheticHumanReviewState(aeId);
  const prepSectionByJob = {
    overview: "overview",
    pay: "pay_tables",
    uplift: "uplift_rules",
    scenarios: "scenarios",
  };
  const syntheticSectionByJob = {
    overview: "overview",
    uplift_rules: "uplift_rules",
    pay_tables: "pay_tables",
    scenarios: "scenarios",
    uplifts: "uplifts",
  };
  const prepMatch = Object.entries(prep?.jobs || {}).find(([key]) => prepSectionByJob[key] === section);
  const humanMatch = Object.entries(human?.jobs || {}).find(([key]) => syntheticSectionByJob[key] === section);
  const humanStatus = humanMatch?.[1]?.status || "";
  const prepStatus = prepMatch?.[1]?.status || "";
  const status = humanStatus === "running" || humanStatus === "waiting" || humanStatus === "failed" || humanStatus === "done" || humanStatus === "skipped" || (humanStatus === "queued" && human?.running)
    ? humanStatus
    : prepStatus;
  if (status === "running") return "auto-running";
  if (status === "waiting") return "auto-waiting";
  if (status === "failed") return "auto-failed";
  if (status === "done" || status === "skipped") return "auto-done";
  if (status === "queued" && (prep?.running || human?.running)) return "auto-queued";
  return "";
}

function pipelineAutomationStatusLabel(status) {
  return {
    "auto-running": "agent running",
    "auto-waiting": "agent waiting",
    "auto-failed": "agent needs attention",
    "auto-done": "agent complete",
    "auto-queued": "agent queued",
  }[status] || "";
}

function renderPipelineStatusLeds(statusMap = null, extraClass = "") {
  if (!statusMap && !state.currentCouncil) return "";
  const classes = ["pipeline-led-strip", extraClass].filter(Boolean).join(" ");
  const interactive = !statusMap;
  return `
    <div class="${escapeHtml(classes)}" aria-label="Selected agreement pipeline status">
      ${PIPELINE_LED_SECTIONS.map((section) => {
        const rawStatus = statusMap ? (statusMap[section] || "not_started") : sectionRawStatus(section);
        const led = pipelineLedState(rawStatus);
        const sectionLabel = MATRIX_SECTION_LABELS[section] || SECTION_LABELS[section] || section;
        const automationStatus = statusMap ? "" : pipelineAutomationStatusForSection(section);
        const automationLabel = pipelineAutomationStatusLabel(automationStatus);
        const itemClasses = [
          "pipeline-led-item",
          `pipeline-led-${led.tone}`,
          automationStatus ? `pipeline-led-${automationStatus}` : "",
        ].filter(Boolean).join(" ");
        const title = `${sectionLabel}: ${led.label}${automationLabel ? `; ${automationLabel}` : ""}`;
        const tagName = interactive ? "button" : "div";
        const actionAttrs = interactive
          ? `type="button" data-pipeline-led-section="${escapeHtml(section)}" aria-label="${escapeHtml(`Open ${sectionLabel}`)}"`
          : "";
        return `
          <${tagName} class="${escapeHtml(itemClasses)}" title="${escapeHtml(title)}" ${actionAttrs}>
            <span class="pipeline-led-bulb" aria-hidden="true"></span>
            <span class="pipeline-led-label">${escapeHtml(sectionLabel)}</span>
            <span class="sr-only">${escapeHtml(title)}</span>
          </${tagName}>
        `;
      }).join("")}
    </div>
  `;
}

function pipelineAutomationSummary(aeId = state.currentCouncil?.agreement_id) {
  const prep = overviewPreparationState(aeId);
  const human = syntheticHumanReviewState(aeId);
  const prepJobs = Object.values(prep?.jobs || {});
  const humanJobs = Object.values(human?.jobs || {});
  const prepRunningJob = prepJobs.find((job) => job.status === "running") || null;
  const humanRunningJob = humanJobs.find((job) => job.status === "running") || null;
  const prepRunning = Boolean(prep?.running || prepJobs.some((job) => job.status === "running"));
  const humanRunning = Boolean(human?.running || humanJobs.some((job) => job.status === "running"));
  const waiting = Boolean(human?.awaitingSystemImprovement);
  const failed = prepJobs.some((job) => job.status === "failed") || humanJobs.some((job) => job.status === "failed");
  const prepComplete = Boolean(prep?.completed);
  const humanComplete = Boolean(human?.completed);
  const row = currentCouncilRow();
  const gated = row ? !isReviewBoardReady(row) : false;
  const tone = waiting
    ? "waiting"
    : humanRunning
    ? "human-running"
    : prepRunning
    ? "running"
    : failed
    ? "failed"
    : humanComplete
    ? "complete"
    : prepComplete
    ? "prep-complete"
    : gated
    ? "gated"
    : "ready";
  const label = {
    waiting: "Paused for system improvement",
    "human-running": "Automated reviewer running",
    running: "Computer prep running",
    failed: "Automation needs attention",
    complete: "Automated reviewer complete",
    "prep-complete": "Computer prep complete",
    gated: "Automation gated",
    ready: "Automation ready",
  }[tone];
  return {
    tone,
    label,
    prepRunning,
    humanRunning,
    prepRunningJob,
    humanRunningJob,
    waiting,
    gated,
    prepComplete,
    humanComplete,
  };
}

function renderPipelineAutomationCue(summary) {
  const active = summary.humanRunning
    ? {
        kind: "qa",
        label: "QA synthesis running",
        detail: summary.humanRunningJob?.detail || summary.label,
      }
    : summary.prepRunning
    ? {
        kind: "computer",
        label: "Computer process running",
        detail: summary.prepRunningJob?.detail || summary.label,
      }
    : null;
  if (!active) return "";
  const title = [active.label, active.detail].filter(Boolean).join(": ");
  const speech = `${active.kind === "qa" ? "QA" : "Computer"}: ${active.detail || active.label}`;
  return `
    <span class="pipeline-auto-cue pipeline-auto-cue-${escapeHtml(active.kind)}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}">
      <span class="pipeline-auto-avatar" aria-hidden="true"></span>
      <span class="pipeline-auto-speech" aria-hidden="true">
        <span class="pipeline-auto-speech-text">${escapeHtml(speech)}</span>
        <span class="pipeline-auto-speech-pulse"></span>
      </span>
    </span>
  `;
}

function renderPipelineAutomationControls() {
  const aeId = state.currentCouncil?.agreement_id;
  if (!aeId) return "";
  const summary = pipelineAutomationSummary(aeId);
  const prepDisabled = summary.prepRunning || summary.humanRunning;
  const qaDisabled = summary.prepRunning || summary.humanRunning || summary.gated;
  const prepTitle = summary.prepRunning
    ? "Computer prep is running"
    : summary.prepComplete
    ? "Run computer prep again"
    : "Run computer prep";
  const qaTitle = summary.humanRunning
    ? "Automated reviewer is running"
    : summary.waiting
    ? "Continue automated reviewer after system improvement"
    : summary.humanComplete
    ? "Run automated reviewer QA again"
    : summary.gated
    ? "Automation is gated until source and scope are ready"
    : "Run automated reviewer QA";
  return `
    <div class="pipeline-auto-mini pipeline-auto-${escapeHtml(summary.tone)}" title="${escapeHtml(summary.label)}" aria-label="Automation controls">
      <span class="pipeline-auto-lamp" aria-hidden="true"></span>
      <span class="pipeline-auto-label">AUTO</span>
      <button
        type="button"
        class="pipeline-auto-btn pipeline-auto-prep-btn"
        data-pipeline-auto-run="prep"
        title="${escapeHtml(prepTitle)}"
        aria-label="${escapeHtml(prepTitle)}"
        ${prepDisabled ? "disabled" : ""}
      >C</button>
      <button
        type="button"
        class="pipeline-auto-btn pipeline-auto-qa-btn"
        data-pipeline-auto-run="qa"
        ${summary.waiting ? 'data-resume-system-improvement="1"' : ""}
        title="${escapeHtml(qaTitle)}"
        aria-label="${escapeHtml(qaTitle)}"
        ${qaDisabled ? "disabled" : ""}
      >QA</button>
      ${renderPipelineAutomationCue(summary)}
      <span class="sr-only">${escapeHtml(summary.label)}</span>
    </div>
  `;
}

function humanQaStatusFromSectionData(sectionData) {
  if (!sectionData || typeof sectionData !== "object") return "not_started";
  const status = sectionData.status || "not_started";
  const qaRecord = sectionData.human_qa;
  if (qaRecord && typeof qaRecord === "object") {
    if (qaRecord.enabled === true && !qaRecord.invalidated_by) return "accepted";
    if (qaRecord.invalidated_by) return "invalidated";
    if (qaRecord.enabled === false) return "open";
  }
  return status === "not_started" ? "not_started" : "missing";
}

function workflowStateFromCanonical(canonical) {
  const sections = canonical?.sections || {};
  const reviewSections = [...new Set([...PIPELINE_LED_SECTIONS, "clauses"])];
  const sectionStatuses = {};
  const humanQaStatuses = {};
  reviewSections.forEach((section) => {
    const sectionData = sections[section] || {};
    sectionStatuses[section] = sectionData.status || "not_started";
    humanQaStatuses[section] = humanQaStatusFromSectionData(sectionData);
  });
  return {
    section_statuses: sectionStatuses,
    human_qa_statuses: humanQaStatuses,
    done_count: Object.values(sectionStatuses).filter((status) => status === "done").length,
  };
}

function syncCouncilRowWorkflowState(canonical) {
  const aeId = canonical?.agreement_id || canonical?.ae_id;
  if (!aeId || !Array.isArray(state.councils)) return;
  const target = String(aeId).toLowerCase();
  const index = state.councils.findIndex((row) => String(row?.ae_id || "").toLowerCase() === target);
  if (index < 0) return;
  state.councils[index] = {
    ...state.councils[index],
    ...workflowStateFromCanonical(canonical),
  };
}

function syncPayDraftFromCanonical() {
  if (!state.currentCouncil) return;
  const pay = state.currentCouncil.sections.pay_tables;
  state.payDraft.tables = JSON.parse(JSON.stringify(pay.tables || []));
  sortDraftTablesByEffectiveFrom();
  // Recompute to_date on load so stale/missing values from the stored canonical are refreshed
  // against the current effective_from chain within each rate_kind group.
  const nominatedExpiry = state.currentCouncil?.sections?.front_matter?.data?.nominated_expiry || null;
  const upliftRuleDates = collectUpliftRuleDates(state.currentCouncil);
  recalcToDates(state.payDraft.tables, nominatedExpiry, upliftRuleDates);
  state.payDraft.sourceRef = pay.source_ref || "";
  state.payDraft.notes = pay.notes || "";
  state.payDraft.status = pay.status || "in_progress";
  state.payDraft.validations = pay.validations || [];
  state.payDraft.rangeExtraction = null;
  state.payDraft.rangeStart = null;
  state.payDraft.rangeEnd = null;
  state.payDraft.editingJsonIndex = new Set();
  state.payDraft.reviewHints = [];
}

async function fetchCouncils() {
  const [councils, intakeRows, councilReference, intakeQuality] = await Promise.all([
    api("/api/councils"),
    api("/api/intake/candidates").catch(() => []),
    api("/api/reference/council-master"),
    api("/api/intake/quality").catch(() => null),
  ]);
  const canonicalCouncils = (councilReference.rows || []).filter((council) => council.status === "active");
  state.councils = councils;
  state.intakeRows = intakeRows;
  state.councilReference = councilReference;
  state.canonicalCouncils = canonicalCouncils;
  state.canonicalLgas = new Set(canonicalCouncils.map((c) => c.short_name));
  state.canonicalLgaTotal = councilReference.summary?.total || canonicalCouncils.length;
  state.intakeQuality = intakeQuality;
  await ensureDefaultAgreementContextForNavigator();
  renderCouncilSelect();
  renderAuditCouncilOptions();
  renderSectionsList();
  renderAgreementNavigator();
  renderActiveLoadedWorkbenchView();
}

function applyIntakeRunPayload(result) {
  if (Array.isArray(result?.candidates)) {
    state.intakeRows = result.candidates;
  }
  if (result?.quality) {
    state.intakeQuality = result.quality;
  }
  renderIntake();
  renderIncoming();
}

async function fetchFairWorkRegistryRun(buttonId = "incoming-run-fetch") {
  await withBusyButton(buttonId, "Fetching registry...", async () => {
    const result = await api("/api/intake/fetch-registry?force_refresh=true", {
      method: "POST",
    });
    applyIntakeRunPayload(result);
    const run = result?.run || {};
    const registryRows = formatCount(run.registry_rows, "0");
    const candidates = formatCount(run.candidate_agreements, formatCount(state.intakeRows.length, "0"));
    await fetchCouncils();
    toast(`Fetched Fair Work registry: ${registryRows} rows, ${candidates} candidates`, "success");
  });
}

function metadataPrimaryLabel(item) {
  return item.fetch_metadata?.["Agreement Title"] || item.source_name;
}

function currentCouncilRow() {
  const aeId = state.currentCouncil?.agreement_id;
  if (!aeId) return null;
  return state.councils.find((item) => item.ae_id === aeId) || null;
}

function currentWorkspaceContext() {
  const council = state.currentCouncil || {};
  const row = currentCouncilRow();
  const councilName =
    council.canonical_lga_short_name ||
    row?.canonical_lga_short_name ||
    council.fwc?.canonical_lga_short_name ||
    row?.fetch_metadata?.lga_short_name ||
    "Unknown council";
  const agreementName =
    row?.fetch_metadata?.["Agreement Title"] ||
    council.source_name ||
    row?.source_name ||
    council.agreement_id ||
    "No agreement selected";
  const aeId = (council.agreement_id || row?.ae_id || "").toUpperCase();
  return { councilName, agreementName, aeId };
}

function agreementNavigationItems() {
  return [...state.councils]
    .filter((item) => item?.ae_id)
    .sort((a, b) => {
      const labelA = (a.canonical_lga_short_name || a.source_name || a.ae_id).toLowerCase();
      const labelB = (b.canonical_lga_short_name || b.source_name || b.ae_id).toLowerCase();
      return labelA.localeCompare(labelB);
    });
}

function agreementNavigatorLabelForItem(item) {
  if (!item) return "";
  const councilName = item.canonical_lga_short_name
    || item.fetch_metadata?.lga_short_name
    || item.geography?.short_name
    || "Unknown council";
  const agreementName = item.fetch_metadata?.["Agreement Title"]
    || item.source_name
    || item.ae_id
    || "No agreement selected";
  return `${councilName} - ${agreementName}`;
}

function agreementNavigatorState() {
  const items = agreementNavigationItems();
  const currentAeId = String(state.currentCouncil?.agreement_id || "").toLowerCase();
  const currentIndex = currentAeId
    ? items.findIndex((item) => String(item.ae_id || "").toLowerCase() === currentAeId)
    : -1;
  const noCurrentTarget = currentIndex < 0;
  return {
    items,
    currentIndex,
    previous: noCurrentTarget ? items[items.length - 1] || null : items[currentIndex - 1] || null,
    next: noCurrentTarget ? items[0] || null : items[currentIndex + 1] || null,
  };
}

function ensureAgreementNavigatorElement() {
  let navigator = document.getElementById("agreement-context-navigator");
  const headerSlot = document.body.dataset.view === "workspace"
    ? document.getElementById("agreement-context-header-slot")
    : null;
  const host = headerSlot || document.querySelector(".app-shell-main") || document.body;
  if (!navigator) {
    navigator = document.createElement("div");
    navigator.id = "agreement-context-navigator";
    navigator.className = "agreement-context-navigator";
    navigator.setAttribute("aria-label", "Council agreement navigator");
  }
  if (navigator.parentElement !== host) host.appendChild(navigator);
  return navigator;
}

function renderAgreementNavigator() {
  if (typeof document === "undefined") return;
  if (document.body.dataset.view === "capability") {
    document.getElementById("agreement-context-navigator")?.remove();
    return;
  }
  const compactWorkspace = document.body.dataset.view === "workspace";
  const navigator = ensureAgreementNavigatorElement();
  navigator.classList.toggle("agreement-context-navigator-compact", compactWorkspace);
  const { items, currentIndex, previous, next } = agreementNavigatorState();
  const context = currentWorkspaceContext();
  const hasCurrent = Boolean(state.currentCouncil?.agreement_id);
  const title = hasCurrent
    ? `${context.councilName} - ${context.agreementName}`
    : "No council agreement selected";
  const position = hasCurrent && currentIndex >= 0
    ? `${currentIndex + 1} of ${items.length}`
    : items.length
      ? `${items.length} agreements`
      : "No agreements";
  const previousTitle = previous ? `Previous agreement: ${agreementNavigatorLabelForItem(previous)}` : "No previous agreement";
  const nextTitle = next ? `Next agreement: ${agreementNavigatorLabelForItem(next)}` : "No next agreement";
  const displayTitle = compactWorkspace && hasCurrent ? context.councilName : title;
  const displayMeta = compactWorkspace && hasCurrent
    ? [context.aeId, position].filter(Boolean).join(" / ")
    : position;
  navigator.innerHTML = `
    <div class="agreement-context-copy" title="${escapeHtml(title)}">
      <div id="agreement-context-title" class="agreement-context-title">${escapeHtml(displayTitle)}</div>
      <div class="agreement-context-meta">${escapeHtml(displayMeta)}</div>
    </div>
    <div class="agreement-context-controls">
      <button
        type="button"
        class="agreement-context-button"
        data-agreement-nav="previous"
        aria-label="Previous agreement"
        title="${escapeHtml(previousTitle)}"
        ${previous ? "" : "disabled"}
      ><span aria-hidden="true">&lt;</span></button>
      <button
        type="button"
        class="agreement-context-button"
        data-agreement-nav="next"
        aria-label="Next agreement"
        title="${escapeHtml(nextTitle)}"
        ${next ? "" : "disabled"}
      ><span aria-hidden="true">&gt;</span></button>
    </div>
  `;
  navigator.querySelectorAll("[data-agreement-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      navigateAgreementContext(button.dataset.agreementNav).catch((error) => {
        toast(`Agreement navigation failed: ${apiErrorMessage(error)}`, "error");
      });
    });
  });
}

function workspaceNavigationItems() {
  return [...reviewBoardRows()].sort((a, b) => {
    const labelA = (a.canonical_lga_short_name || a.source_name || a.ae_id).toLowerCase();
    const labelB = (b.canonical_lga_short_name || b.source_name || b.ae_id).toLowerCase();
    return labelA.localeCompare(labelB);
  });
}

function renderAnalysisChartsHeader() {
  const config = currentDataSetConfig();
  return `
    <div class="section-work-header analysis-chart-header app-page-header">
      <div class="section-work-title-shell">
        <div class="section-report-brand" aria-label="Municipal Benchmark">
          <span class="section-report-mark" aria-hidden="true"></span>
          <span>Municipal Benchmark</span>
        </div>
        <div class="section-work-title">
          <h2>Think &gt; ${escapeHtml(config.title)}</h2>
        </div>
      </div>
    </div>
  `;
}

function wireAnalysisChartsHeaderNavigation(header) {
  header.querySelectorAll("[data-analysis-dataset-nav-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.analysisDatasetNavTarget;
      if (!target) return;
      setCurrentDataSet(target);
      renderAnalysisWorkspace();
    });
  });
  header.querySelectorAll("[data-analysis-agreement-nav-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = button.dataset.analysisAgreementNavTarget;
      if (!target) return;
      await selectAnalysisCouncil(target);
    });
  });
}

function renderAnalysisBannerHeader() {
  const banner = document.getElementById("analysis-banner-header");
  const hero = document.querySelector("#view-analysis .analysis-hero");
  if (!banner || !hero) return;
  const isCharts = state.currentDataSet === "charts";
  banner.hidden = !isCharts;
  hero.hidden = isCharts;
  if (!isCharts) {
    banner.innerHTML = "";
    return;
  }
  banner.innerHTML = renderAnalysisChartsHeader();
  wireAnalysisChartsHeaderNavigation(banner);
  if (!state.lgaBoundaryGeojson) {
    ensureLgaBoundaryData().then((geojson) => {
      if (geojson && document.body.dataset.view === "analysis" && state.currentDataSet === "charts") {
        renderAnalysisBannerHeader();
      }
    });
  }
}

function workspaceSectionNavigation(section) {
  const sections = SECTION_GROUPS.flatMap((group) => group.sections);
  const index = sections.indexOf(section);
  return {
    previous: index > 0 ? sections[index - 1] : "",
    next: index >= 0 && index < sections.length - 1 ? sections[index + 1] : "",
  };
}

function openableWorkspaceSection(section, { notify = false } = {}) {
  const targetSection = SECTION_LABELS[section] ? section : "overview";
  const blocker = sectionQaGateBlocker(targetSection);
  if (!blocker) return targetSection;
  if (notify) {
    const targetLabel = SECTION_LABELS[targetSection] || targetSection;
    const blockerLabel = SECTION_LABELS[blocker] || blocker;
    toast(`${targetLabel} is locked until ${blockerLabel} is accepted.`, "error");
  }
  return blocker;
}

function renderSectionNavButton(target, direction) {
  const isPrevious = direction === "previous";
  const label = isPrevious ? "Previous section" : "Next section";
  const className = isPrevious ? "section-card-scroll-left" : "section-card-scroll-right";
  const glyph = isPrevious ? "&lsaquo;" : "&rsaquo;";
  const blocker = target ? sectionQaGateBlocker(target) : null;
  const blockedBy = blocker ? SECTION_LABELS[blocker] || blocker : "";
  const disabled = target && !blocker ? "" : " disabled";
  const title = blocker ? `${label}: accept ${blockedBy} first` : label;
  return `
    <button
      class="section-card-scroll ${className} section-work-nav-btn"
      type="button"
      data-section-nav-target="${escapeHtml(target)}"
      aria-label="${label}"
      title="${escapeHtml(title)}"
      ${disabled}
    ><span aria-hidden="true">${glyph}</span></button>
  `;
}

function renderSectionWorkHeader(section) {
  const label = SECTION_LABELS[section] || section;
  const sectionClass = String(section || "workspace").replace(/[^a-z0-9_-]/gi, "_");
  const context = currentWorkspaceContext();
  const description = SECTION_DESCRIPTIONS[section] || "Agreement workspace section.";
  const navigation = workspaceSectionNavigation(section);
  return `
    <div class="section-work-header section-work-${escapeHtml(sectionClass)} app-page-header">
      <div class="section-work-title-shell">
        ${renderSectionNavButton(navigation.previous, "previous")}
        ${renderSectionNavButton(navigation.next, "next")}
        <div class="section-report-brand" aria-label="Municipal Benchmark">
          <span class="section-report-mark" aria-hidden="true"></span>
          <span>Municipal Benchmark</span>
        </div>
        <div class="section-work-title">
          <h2>Process &gt; ${escapeHtml(label)}</h2>
          <div class="section-heading-led-row">
            ${renderPipelineStatusLeds()}
            ${renderPipelineAutomationControls()}
          </div>
          <p>${escapeHtml(description)}</p>
        </div>
      </div>
      <div class="section-work-panel">
        ${renderSectionNavButton(navigation.previous, "previous")}
        ${renderSectionNavButton(navigation.next, "next")}
        <div class="section-work-panel-copy">
          <div class="intake-kicker">Current evidence</div>
          <div class="section-work-council-line">
            <h3>${escapeHtml(context.councilName)}</h3>
          </div>
          <p>${escapeHtml(context.agreementName)}</p>
          <div class="section-context-line">${escapeHtml(context.aeId || "No AE selected")}</div>
        </div>
      </div>
      <div id="agreement-context-header-slot" class="agreement-context-header-slot" aria-label="Council agreement navigator"></div>
    </div>
  `;
}

function wirePipelineAutomationControls(root) {
  root?.querySelectorAll("[data-pipeline-auto-run]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      const aeId = state.currentCouncil?.agreement_id;
      if (!aeId) return;
      if (button.dataset.pipelineAutoRun === "prep") {
        setReviewBoardAutomationDetailsOpen(aeId, true);
        queueOverviewPreparation({ aeId, force: true, source: "workspace" });
        return;
      }
      if (button.dataset.pipelineAutoRun === "qa") {
        setReviewBoardAutomationDetailsOpen(aeId, true);
        queueSyntheticHumanReview({ aeId, force: button.dataset.resumeSystemImprovement !== "1" });
      }
    });
  });
}

function wirePipelineLedNavigation(root) {
  root?.querySelectorAll("[data-pipeline-led-section]").forEach((button) => {
    button.addEventListener("click", () => {
      const section = button.dataset.pipelineLedSection;
      if (!section) return;
      openWorkspaceSection(section);
    });
  });
}

function setWorkspaceModuleHeader(section) {
  const header = document.getElementById("workspace-module-header");
  if (!header) return;
  header.innerHTML = renderSectionWorkHeader(section);
  header.querySelectorAll("[data-section-nav-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.sectionNavTarget;
      if (!target) return;
      openWorkspaceSection(target);
    });
  });
  wirePipelineLedNavigation(header);
  wirePipelineAutomationControls(header);
  renderAgreementNavigator();
}

function sectionHumanQaRecord(section = state.currentSection) {
  const record = state.currentCouncil?.sections?.[section]?.human_qa;
  return record && typeof record === "object" ? record : null;
}

function sectionFinalActionAccepted(section = state.currentSection) {
  const qaRecord = sectionHumanQaRecord(section);
  return Boolean(qaRecord?.enabled === true && !qaRecord?.invalidated_by);
}

function sectionQaGateBlocker(section = state.currentSection) {
  if (!state.currentCouncil) return null;
  const targetIndex = SECTION_QA_WORKFLOW_ORDER.indexOf(section);
  if (targetIndex <= 0) return null;
  for (let index = 0; index < targetIndex; index += 1) {
    const upstream = SECTION_QA_WORKFLOW_ORDER[index];
    if (!sectionFinalActionAccepted(upstream)) return upstream;
  }
  return null;
}

function sectionQaIsGrey(section = state.currentSection) {
  return Boolean(sectionQaGateBlocker(section));
}

function sectionDisplayStatus(section = state.currentSection) {
  if (sectionQaGateBlocker(section)) return "blocked";
  return state.currentCouncil?.sections?.[section]?.status || "not_started";
}

function sectionQaDownstreamSections(section = state.currentSection) {
  const index = SECTION_QA_WORKFLOW_ORDER.indexOf(section);
  if (index < 0) return [];
  return SECTION_QA_WORKFLOW_ORDER.slice(index + 1);
}

function sectionLabelList(sections = []) {
  return sections.map((section) => SECTION_LABELS[section] || section).join(", ");
}

function ensureSectionFinalFloatingSlot() {
  let slot = document.getElementById("section-work-final-floating-slot");
  if (slot) return slot;
  slot = document.createElement("div");
  slot.id = "section-work-final-floating-slot";
  slot.className = "section-work-final-floating-slot";
  slot.setAttribute("aria-label", "Section completion");
  const host = document.querySelector(".app-shell-main") || document.body;
  host.appendChild(slot);
  return slot;
}

function clearSectionFinalFloatingSlot() {
  document.getElementById("section-work-final-floating-slot")?.remove();
}

function scheduleSectionFinalActionMount(buttonId, section = state.currentSection) {
  if (!buttonId || typeof window === "undefined") return;
  window.queueMicrotask(() => {
    if (section !== state.currentSection) return;
    if (document.body.dataset.view !== "workspace") return;
    if (!document.getElementById("view-workspace")?.classList.contains("active")) return;
    const slot = ensureSectionFinalFloatingSlot();
    const button = document.getElementById(buttonId);
    const card = button?.closest(".section-final-card");
    if (!slot || !card) return;
    slot.replaceChildren(card);
    card.hidden = false;
  });
}

function syncSectionFinalActionState(buttonId, section = state.currentSection) {
  const button = document.getElementById(buttonId);
  const card = button?.closest(".section-final-card");
  if (!button || !card) return;
  const accepted = sectionFinalActionAccepted(section);
  const qaOff = sectionQaIsGrey(section);
  button.classList.toggle("is-accepted", accepted);
  button.setAttribute("aria-pressed", accepted ? "true" : "false");
  button.setAttribute("data-qa-enabled", accepted ? "true" : "false");
  const label = button.querySelector(".section-toggle-label");
  if (label) label.textContent = accepted ? "Accepted" : "Edit mode";
  card.classList.toggle("is-accepted", accepted);
  card.classList.toggle("is-qa-off", qaOff);
}

function syncSectionPaneQaMode() {
  const pane = document.getElementById("section-pane");
  if (!pane) return;
  const accepted = sectionFinalActionAccepted(state.currentSection);
  pane.classList.toggle("section-pane-confirm-mode", accepted);
  pane.querySelectorAll("button, input, select, textarea").forEach((control) => {
    if (control.closest(".section-final-card") || control.matches("[data-section-qa-toggle]")) return;
    if (control.matches("[data-confirm-mode-action]")) return;
    control.disabled = accepted;
  });
}

function renderSectionFinalAction({
  eyebrow = "Human QA",
  title = "Preliminary final state",
  detail = "",
  buttonId,
  buttonText = "Save & Accept",
  buttonClass = "",
  buttonAttrs = "",
} = {}) {
  if (!buttonId) return "";
  const section = state.currentSection;
  const accepted = sectionFinalActionAccepted(section);
  const qaOff = sectionQaIsGrey(section);
  const disabled = /\bdisabled\b/i.test(buttonAttrs);
  const actionLabel = accepted ? "Accepted" : "Edit mode";
  const qaTitle = accepted ? "QA gate accepted" : qaOff ? "Blocked by an upstream QA gate" : title;
  const qaDetail = detail || (accepted ? "Open the QA note or switch back to edit mode." : "Open the QA note before accepting this gate.");
  scheduleSectionFinalActionMount(buttonId, section);
  return `
    <aside class="section-final-card section-final-toggle-card ${accepted ? "is-accepted" : ""} ${qaOff ? "is-qa-off" : ""}" data-section-final-id="${escapeHtml(buttonId)}" data-section="${escapeHtml(section)}" aria-label="Human QA" hidden>
      <div class="section-final-copy">
        <div class="section-final-label">Human QA</div>
        <strong>${escapeHtml(qaTitle)}</strong>
        ${qaDetail ? `<p>${escapeHtml(qaDetail)}</p>` : ""}
      </div>
      <button
        id="${escapeHtml(buttonId)}"
        class="section-final-action section-accept-action section-accept-toggle ${accepted ? "is-accepted" : ""} ${escapeHtml(buttonClass)}"
        type="button"
        aria-pressed="${accepted ? "true" : "false"}"
        title="${escapeHtml(qaDetail || qaTitle || eyebrow || buttonText)}"
        data-section-qa-toggle="1"
        data-section="${escapeHtml(section)}"
        data-qa-enabled="${accepted ? "true" : "false"}"
        ${buttonAttrs}
      >
        <span class="section-toggle-track" aria-hidden="true"><span class="section-toggle-thumb"></span></span>
        <span class="section-toggle-label">${escapeHtml(disabled && !accepted ? "Locked" : actionLabel)}</span>
      </button>
    </aside>
  `;
}

function renderSectionActionBar(actionsHtml = "", finalActionHtml = "") {
  if (!actionsHtml && !finalActionHtml) return "";
  return `
    <div class="section-pane-actions ${actionsHtml ? "" : "section-pane-actions-final-only"}">
      ${actionsHtml ? `<div class="section-utility-actions">${actionsHtml}</div>` : ""}
      ${finalActionHtml ? `<div class="section-final-staging">${finalActionHtml}</div>` : ""}
    </div>
  `;
}

function storedHumanNoteText(value) {
  const text = String(value || "");
  const marker = "\n---\n";
  const index = text.indexOf(marker);
  return index >= 0 ? text.slice(index + marker.length) : text;
}

function scenarioOverrideDecisionCount(aeId) {
  const overrides = scenarioOverrides.get(aeId) || {};
  return Object.values(overrides).reduce((total, cells) => total + Object.keys(cells || {}).length, 0);
}

function sectionQaProcessLines(section) {
  const council = state.currentCouncil || {};
  const sectionData = council.sections?.[section] || {};
  const data = sectionData.data && typeof sectionData.data === "object" ? sectionData.data : {};
  if (section === "overview") {
    const overview = council.overview || {};
    const pageCount = overview.page_count || data.page_count;
    return [
      pageCount ? `Computer: generated document map across ${pageCount} pages.` : "Computer: overview generation is not recorded yet.",
      `Computer: identified ${(overview.likely_pay_table_pages || data.likely_pay_table_pages || []).length} likely pay-table pages and ${(overview.likely_uplift_pages || data.likely_uplift_pages || []).length} likely uplift pages.`,
    ];
  }
  if (section === "uplift_rules") {
    const acceptedRules = data.accepted?.document?.rules || [];
    const suggestedRules = data.suggestion?.document?.rules || [];
    return [
      `Computer: extracted ${suggestedRules.length || acceptedRules.length} uplift rule candidate${(suggestedRules.length || acceptedRules.length) === 1 ? "" : "s"}.`,
      acceptedRules.length ? `Human: accepted ${acceptedRules.length} uplift rule${acceptedRules.length === 1 ? "" : "s"} for governed use.` : "Human: no accepted uplift rule set recorded yet.",
    ];
  }
  if (section === "pay_tables") {
    const tables = Array.isArray(state.payDraft.tables) && state.currentSection === "pay_tables"
      ? state.payDraft.tables
      : sectionData.tables || [];
    const validations = Array.isArray(state.payDraft.validations) && state.currentSection === "pay_tables"
      ? state.payDraft.validations
      : sectionData.validations || [];
    return [
      `Computer: prepared ${tables.length} pay table${tables.length === 1 ? "" : "s"} and ${validations.length} validation message${validations.length === 1 ? "" : "s"}.`,
      sectionData.source_ref ? `Human: source reference captured as ${sectionData.source_ref}.` : "Human: source reference is not recorded yet.",
    ];
  }
  if (section === "scenarios") {
    const summary = data.status_summary || {};
    const scenarioCount = Object.values(summary).reduce((total, count) => total + Number(count || 0), 0);
    const decisions = scenarioOverrideDecisionCount(council.agreement_id);
    return [
      `Computer: ran scenario checks across ${scenarioCount} period result${scenarioCount === 1 ? "" : "s"}.`,
      `Human: recorded ${decisions} scenario override decision${decisions === 1 ? "" : "s"} and ${_scenarioAuditEvents.length} QA event${_scenarioAuditEvents.length === 1 ? "" : "s"}.`,
    ];
  }
  if (section === "end_of_band_dollars") {
    const rows = Array.isArray(data.rows) ? data.rows : [];
    const periods = new Set(rows.map((row) => row.effective_from).filter(Boolean));
    const bands = new Set(rows.map((row) => row.band).filter(Boolean));
    return [
      `Computer: resolved ${rows.length} end-of-band cash row${rows.length === 1 ? "" : "s"} across ${periods.size} operative period${periods.size === 1 ? "" : "s"}.`,
      rows.length
        ? `Human: reviewing ${bands.size} band value${bands.size === 1 ? "" : "s"} and clause evidence before governed set acceptance.`
        : "Human: no current in-scope cash end-of-band amount is recorded for this agreement.",
    ];
  }
  if (section === "uplifts") {
    const periods = Array.isArray(data.periods) ? data.periods : [];
    const promoted = periods.filter((period) => period?.pay_table || period?.uplift_rule).length;
    return [
      `Computer: assembled ${periods.length} governed period${periods.length === 1 ? "" : "s"}.`,
      `Human: promoted governed evidence for ${promoted} period${promoted === 1 ? "" : "s"}.`,
    ];
  }
  return ["Computer: no recorded process summary is available yet.", "Human: no reviewer action is recorded yet."];
}

function sectionQaAlterationLines(section) {
  const council = state.currentCouncil || {};
  const sectionData = council.sections?.[section] || {};
  const lines = [];
  if (sectionData.human_qa?.invalidated_by) {
    lines.push(`Cleared because ${SECTION_LABELS[sectionData.human_qa.invalidated_by] || sectionData.human_qa.invalidated_by} was switched back to edit mode.`);
  }
  if (section === "scenarios") {
    const scenarioSummary = buildScenarioNoteSummary(council.agreement_id);
    if (scenarioSummary) lines.push(scenarioSummary);
  }
  if (section === "pay_tables" && Array.isArray(sectionData.qa_events) && sectionData.qa_events.length) {
    lines.push(`${sectionData.qa_events.length} pay-table review change${sectionData.qa_events.length === 1 ? "" : "s"} recorded.`);
  }
  if (sectionData.notes) lines.push(`Section notes: ${sectionData.notes}`);
  return lines.length ? lines : ["No alterations or override reasons are recorded yet."];
}

function buildSectionQaSummary(section, { enabled = !sectionFinalActionAccepted(section) } = {}) {
  const label = SECTION_LABELS[section] || section;
  const council = state.currentCouncil || {};
  const sectionData = council.sections?.[section] || {};
  const status = sectionData.status || "not_started";
  const completed = sectionData.completed_at ? displayDate(sectionData.completed_at) : "not completed";
  const downstream = sectionQaDownstreamSections(section);
  const lines = [
    `${label} Human QA`,
    `Agreement: ${council.source_name || council.agreement_id || "Current agreement"}`,
    `Current state: ${status.replaceAll("_", " ")}; ${completed}.`,
    "",
    "Processes run:",
    ...sectionQaProcessLines(section).map((line) => `- ${line}`),
    "",
    "Alterations and reasons:",
    ...sectionQaAlterationLines(section).map((line) => `- ${line}`),
    "",
  ];
  if (enabled) {
    lines.push("Accepted effect: records this note, saves the section where applicable, and opens downstream stages.");
  } else {
    lines.push(`Edit-mode effect: keeps this section editable and clears downstream data${downstream.length ? ` for ${sectionLabelList(downstream)}` : ""}.`);
  }
  return lines.join("\n");
}

function sectionQaDefaultNoteText(section) {
  const processLines = sectionQaProcessLines(section)
    .filter((line) => !/^Computer: no recorded process summary/.test(line) && !/^Human: no reviewer action/.test(line));
  const alterationLines = sectionQaAlterationLines(section)
    .filter((line) => !/^No alterations or override reasons/.test(line));
  const lines = [];
  if (processLines.length) {
    lines.push("Section actions:");
    lines.push(...processLines.map((line) => `- ${line}`));
  }
  if (alterationLines.length) {
    if (lines.length) lines.push("");
    lines.push("Section QA notes:");
    lines.push(...alterationLines.map((line) => `- ${line}`));
  }
  return lines.join("\n");
}

function closeSectionQaDialog() {
  const dialog = document.querySelector("dialog.section-qa-dialog");
  if (!dialog) return;
  dialog.close();
  dialog.remove();
}

function openSectionQaDialog(section = state.currentSection) {
  if (!state.currentCouncil || !SECTION_LABELS[section]) return;
  closeSectionQaDialog();
  const accepted = sectionFinalActionAccepted(section);
  const nextEnabled = !accepted;
  const qaRecord = sectionHumanQaRecord(section);
  const existingNotes = qaRecord?.notes || (section === "scenarios" ? storedHumanNoteText(_scenarioSavedNotes) : "");
  const noteText = String(existingNotes || "").trim() ? existingNotes : sectionQaDefaultNoteText(section);
  const downstream = sectionQaDownstreamSections(section);
  const label = SECTION_LABELS[section] || section;
  const summary = buildSectionQaSummary(section, { enabled: nextEnabled });
  const dialog = document.createElement("dialog");
  dialog.className = "scenario-note-dialog section-qa-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="section-qa-form stack-sm">
      <div class="section-qa-dialog-head">
        <span>Human QA</span>
        <h3>${escapeHtml(label)}</h3>
      </div>
      <div class="dialog-summary">${escapeHtml(summary)}</div>
      <label class="section-qa-note-label">Human notes
        <textarea id="section-qa-note-textarea" placeholder="Add reviewer notes, judgement calls, or follow-up needed.">${escapeHtml(noteText)}</textarea>
      </label>
      <div class="section-qa-impact ${nextEnabled ? "section-qa-impact-on" : "section-qa-impact-off"}">
        ${escapeHtml(nextEnabled
          ? "This will save the section where applicable, record the note, and accept this gate for downstream use."
          : `This will reopen editing for this section and clear downstream data${downstream.length ? ` for ${sectionLabelList(downstream)}` : ""}.`)}
      </div>
      <div class="toolbar dialog-actions">
        <button type="button" id="section-qa-confirm" class="${nextEnabled ? "primary" : "section-qa-danger"}" data-section="${escapeHtml(section)}" data-qa-enabled="${nextEnabled ? "true" : "false"}">${nextEnabled ? "Accept gate" : "Open edit mode"}</button>
        <button type="button" id="section-qa-cancel">Cancel</button>
      </div>
    </form>
  `;
  document.body.appendChild(dialog);
  dialog.showModal();
}

async function runSectionQaEnableAction(section) {
  const sectionData = state.currentCouncil?.sections?.[section] || {};
  if (section === "overview") {
    if (sectionData.status !== "done") await generateOverview();
    return;
  }
  if (section === "pay_tables") {
    await savePayTables();
    return;
  }
  if (section === "uplift_rules") {
    const data = sectionData.data && typeof sectionData.data === "object" ? sectionData.data : {};
    if (sectionData.status !== "done" && data.suggestion) await acceptUpliftSuggestion();
    return;
  }
  if (section === "uplifts") {
    await saveGovernedSet();
    return;
  }
  if (section === "end_of_band_dollars") {
    await saveEndOfBandDollarsSection();
    return;
  }
  if (!["scenarios", "overview", "pay_tables", "uplift_rules", "end_of_band_dollars", "uplifts"].includes(section)) {
    await api(`/api/councils/${state.currentCouncil.agreement_id}/sections/${section}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "done" }),
    });
    await refreshCurrentCouncil(section);
  }
}

async function persistScenarioHumanQaNote(aeId, summary, notes, enabled) {
  const currentOverrides = scenarioOverrides.get(aeId) || {};
  const fullNotes = `${summary}\n---\n${notes}`;
  const resp = await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/scenarios/note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      notes: fullNotes,
      overrides: currentOverrides,
      change_context: { scope: "human_qa", action: enabled ? "qa_on" : "qa_off" },
    }),
  });
  _scenarioSavedNotes = fullNotes;
  setScenarioAuditEvents(resp.audit_events || _scenarioAuditEvents);
  updateScenarioSavedBadge(aeId, resp.saved_at);
}

function applyHumanQaResponse(resp) {
  if (resp?.canonical) {
    state.currentCouncil = resp.canonical;
    syncCouncilRowWorkflowState(resp.canonical);
    syncPayDraftFromCanonical();
  }
  renderCouncilSelect();
  renderSectionsList();
  renderSectionPane();
}

async function saveSectionHumanQa(section, enabled, notes) {
  const aeId = state.currentCouncil?.agreement_id;
  if (!aeId) return;
  if (enabled) {
    await runSectionQaEnableAction(section);
  }
  const summary = buildSectionQaSummary(section, { enabled });
  if (section === "scenarios") {
    await persistScenarioHumanQaNote(aeId, summary, notes, enabled);
  }
  const resp = await api(`/api/councils/${encodeURIComponent(aeId)}/sections/${encodeURIComponent(section)}/human-qa`, {
    method: "PATCH",
    body: JSON.stringify({ enabled, notes, summary }),
  });
  if (!enabled && (resp.downstream_cleared || []).includes("scenarios")) {
    scenarioOverrides.delete(aeId);
    _scenarioSavedAt = null;
    _scenarioSavedNotes = null;
    setScenarioAuditEvents([]);
  }
  applyHumanQaResponse(resp);
  const downstream = resp.downstream_cleared || [];
  toast(
    enabled
      ? `${SECTION_LABELS[section] || section} Human QA on`
      : `${SECTION_LABELS[section] || section} Human QA off${downstream.length ? `; cleared ${sectionLabelList(downstream)}` : ""}`,
    enabled ? "success" : "error",
  );
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-section-qa-toggle]");
  if (!button || button.disabled) return;
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  openSectionQaDialog(button.getAttribute("data-section") || state.currentSection);
}, true);

document.addEventListener("click", async (event) => {
  if (event.target.closest("#section-qa-cancel")) {
    closeSectionQaDialog();
    return;
  }
  const confirmButton = event.target.closest("#section-qa-confirm");
  if (!confirmButton) return;
  const section = confirmButton.getAttribute("data-section") || state.currentSection;
  const enabled = confirmButton.getAttribute("data-qa-enabled") === "true";
  const textarea = document.getElementById("section-qa-note-textarea");
  confirmButton.disabled = true;
  confirmButton.textContent = enabled ? "Accepting..." : "Opening...";
  try {
    await saveSectionHumanQa(section, enabled, textarea?.value || "");
    closeSectionQaDialog();
  } catch (error) {
    confirmButton.disabled = false;
    confirmButton.textContent = enabled ? "Accept gate" : "Open edit mode";
    toast(`Human QA update failed: ${error.message}`, "error");
  }
});

function clearWorkspaceModuleHeader() {
  const header = document.getElementById("workspace-module-header");
  if (header) header.innerHTML = "";
}

function formatDateRange(meta) {
  if (!meta) return "Dates not stated";
  return displayDateRange(meta["Operative Date"], meta["Expiry Date"]);
}

function splitMatchedNames(meta) {
  const raw = meta?.matched_lga_names;
  if (Array.isArray(raw)) return raw.filter(Boolean);
  if (typeof raw === "string") {
    return raw.split("|").map((part) => part.trim()).filter(Boolean);
  }
  return [];
}

function getCouncilOptionsHtml(selected = "", includeBlank = true) {
  const options = state.canonicalCouncils.map((council) => {
    const selectedAttr = council.short_name === selected ? "selected" : "";
    return `<option value="${escapeHtml(council.short_name)}" ${selectedAttr}>${escapeHtml(council.short_name)}</option>`;
  }).join("");
  if (!includeBlank) return options;
  return `<option value="">Select council</option>${options}`;
}

function getSortedCouncils(items) {
  const sorted = [...items];
  if (state.pipelineSort === "lga") {
    sorted.sort((a, b) => {
      const lgaA = (a.canonical_lga_short_name || "").toLowerCase();
      const lgaB = (b.canonical_lga_short_name || "").toLowerCase();
      if (lgaA !== lgaB) return lgaA.localeCompare(lgaB);
      return (a.source_name || a.ae_id).toLowerCase().localeCompare((b.source_name || b.ae_id).toLowerCase());
    });
    return sorted;
  }
  sorted.sort((a, b) => (a.source_name || a.ae_id).toLowerCase().localeCompare((b.source_name || b.ae_id).toLowerCase()));
  return sorted;
}

function getSortedIntakeRows(items) {
  const sorted = [...items];
  const meta = (item) => item.fetch_metadata || {};
  const normalise = (value) => String(value || "").trim().toLowerCase();
  const effectiveDate = (item) =>
    meta(item)["Operative Date"] ||
    meta(item).operative_date ||
    item.fwc?.operative_date ||
    "9999-12-31";
  const agreementNumber = (item) =>
    meta(item).agreement_num_clean ||
    meta(item)["Agreement ID"] ||
    item.ae_id ||
    "";
  const lgaShort = (item) =>
    item.canonical_lga_short_name ||
    meta(item).lga_short_name ||
    splitMatchedNames(meta(item))[0] ||
    "";
  const tieBreak = (a, b) =>
    normalise(metadataPrimaryLabel(a)).localeCompare(normalise(metadataPrimaryLabel(b))) ||
    normalise(a.ae_id).localeCompare(normalise(b.ae_id));

  if (state.intakeSort === "effective_date") {
    sorted.sort((a, b) => effectiveDate(b).localeCompare(effectiveDate(a)) || tieBreak(a, b));
    return sorted;
  }
  if (state.intakeSort === "agreement_name") {
    sorted.sort((a, b) => tieBreak(a, b));
    return sorted;
  }
  if (state.intakeSort === "lga_short_name") {
    sorted.sort((a, b) => normalise(lgaShort(a)).localeCompare(normalise(lgaShort(b))) || tieBreak(a, b));
    return sorted;
  }
  if (state.intakeSort === "confidence") {
    sorted.sort((a, b) => (intakeConfidence(b).value - intakeConfidence(a).value) || tieBreak(a, b));
    return sorted;
  }
  if (state.intakeSort === "agreement_number") {
    sorted.sort((a, b) => normalise(agreementNumber(a)).localeCompare(normalise(agreementNumber(b))) || tieBreak(a, b));
    return sorted;
  }

  const acceptanceRank = {
    accepted: 0,
    needs_review: 1,
    candidate: 1,
    rejected: 3,
  };
  const statusRank = {
    active: 0,
    superseded_by_newer: 2,
    superseded_in_lineage: 3,
  };
  sorted.sort((a, b) => {
    const metaA = a.fetch_metadata || {};
    const metaB = b.fetch_metadata || {};
    const acceptanceA = acceptanceRank[a.acceptance_state] ?? 2;
    const acceptanceB = acceptanceRank[b.acceptance_state] ?? 2;
    if (acceptanceA !== acceptanceB) return acceptanceA - acceptanceB;
    const rankA = statusRank[metaA.pipeline_status] ?? 4;
    const rankB = statusRank[metaB.pipeline_status] ?? 4;
    if (rankA !== rankB) return rankA - rankB;
    if (Boolean(a.processing_gated) !== Boolean(b.processing_gated)) return a.processing_gated ? 1 : -1;
    const lgaA = (a.canonical_lga_short_name || "zzzz").toLowerCase();
    const lgaB = (b.canonical_lga_short_name || "zzzz").toLowerCase();
    if (lgaA !== lgaB) return lgaA.localeCompare(lgaB);
    return (a.source_name || a.ae_id).toLowerCase().localeCompare((b.source_name || b.ae_id).toLowerCase());
  });
  return sorted;
}

function intakeStatus(item) {
  const decision = item.multi_council_decision || {};
  const meta = item.fetch_metadata || {};
  if (item.acceptance_state === "accepted") return "accepted";
  if (item.acceptance_state === "rejected") return "rejected";
  if (item.acceptance_state === "needs_review") return "needs_review";
  if (item.in_working_set) return "accepted";
  if ((meta.pipeline_status || "").includes("superseded")) return "rejected";
  if (item.possible_multi_council_flag || item.matched_lga_count === 0) return "needs_review";
  if (item.pdf_frozen === false) return "needs_review";
  if (decision.decision_pending || item.processing_gated || !item.fetch_metadata) return "needs_review";
  if (hasUnresolvedScopeStatus(meta.scope_resolution_status)) return "needs_review";
  return "needs_review";
}

function isSourceReady(item) {
  return Boolean(item?.pdf_frozen && !item?.pdf_source?.suspect);
}

function sourceGateStatus(item) {
  if (item?.pdf_source?.suspect) return { key: "suspect", label: "Source retry", detail: "Fetched PDF under 500 KB" };
  if (!item?.pdf_frozen) return { key: "missing", label: "Source missing", detail: "Fetch PDF before QA" };
  return { key: "ready", label: "Source ready", detail: "Fetched source passed intake check" };
}

function normaliseScopeStatus(value) {
  const status = String(value || "").trim();
  return status === "title_only_unresolved" ? "" : status;
}

function hasUnresolvedScopeStatus(value) {
  return normaliseScopeStatus(value).includes("unresolved");
}

function hasScopeIssue(item) {
  const meta = item?.fetch_metadata || {};
  return Boolean(
    item?.multi_council_decision?.decision_pending
    || item?.possible_multi_council_flag
    || item?.matched_lga_count === 0
    || hasUnresolvedScopeStatus(meta.scope_resolution_status)
  );
}

function isSplitAgreementCandidate(item) {
  const meta = item?.fetch_metadata || {};
  const matchedNames = splitMatchedNames(meta);
  const matchedCount = Number(item?.matched_lga_count ?? meta.matched_lga_count ?? matchedNames.length);
  const lineageKey = String(meta.lineage_key || item?.lineage_key || "");
  return Boolean(
    item?.possible_multi_council_flag
    || item?.multi_council_decision?.decision_pending
    || matchedCount > 1
    || matchedNames.length > 1
    || lineageKey.includes("|")
  );
}

function isReviewBoardReady(item) {
  return Boolean(isSourceReady(item) && !item?.processing_gated && !isSplitAgreementCandidate(item));
}

function reviewBoardRecordFor(item) {
  const aeId = String(item?.ae_id || "").toLowerCase();
  if (!aeId) return null;
  return state.councils.find((row) => String(row.ae_id || "").toLowerCase() === aeId) || null;
}

function isReviewBoardItem(item) {
  const boardRecord = reviewBoardRecordFor(item);
  return Boolean(boardRecord && isReviewBoardReady(boardRecord));
}

function reviewBoardRows(rows = state.councils) {
  if (rows === state.councils) return rows.filter(isReviewBoardReady);
  return rows.filter(isReviewBoardItem);
}

function firstOpenReviewSection(item) {
  const statuses = item?.section_statuses || {};
  return MATRIX_CORE_REVIEW_SECTIONS.find((section) => statuses[section] !== "done") || null;
}

function matrixCoreProgress(item) {
  const statuses = item?.section_statuses || {};
  const total = MATRIX_CORE_REVIEW_SECTIONS.length;
  const done = MATRIX_CORE_REVIEW_SECTIONS.filter((section) => statuses[section] === "done").length;
  return {
    done,
    total,
    pct: total ? Math.round((done / total) * 100) : 0,
  };
}

function nextIntakeAction(item) {
  const meta = item?.fetch_metadata || {};
  const status = intakeStatus(item);
  const hasPdfUrl = Boolean(meta.pdf_url || item?.pdf_url);
  if (status === "rejected") {
    return { action: "none", kind: "muted", label: "Rejected", detail: "No QA action", disabled: true };
  }
  if (!item?.pdf_frozen) {
    return {
      action: "freeze",
      kind: hasPdfUrl ? "source" : "muted",
      label: hasPdfUrl ? "Fetch PDF" : "No PDF URL",
      detail: hasPdfUrl ? "Retrieve source PDF" : "Source link missing",
      disabled: !hasPdfUrl,
    };
  }
  if (item?.pdf_source?.suspect) {
    return { action: "retry", kind: "warning", label: "Retry source", detail: "PDF under 500 KB", disabled: false };
  }
  if (hasScopeIssue(item)) {
    return { action: "review_scope", kind: "review", label: "Resolve scope", detail: "Confirm council coverage", disabled: false };
  }
  if (status !== "accepted") {
    return { action: "accept", kind: "primary", label: "Accept source", detail: "Ready for governed QA", disabled: false };
  }
  return { action: "send_review", kind: "primary", label: "Send to Review", detail: "Open agreement workspace", disabled: false };
}

function nextMatrixAction(item) {
  const sourceGate = sourceGateStatus(item);
  if (!isSourceReady(item)) {
    return {
      action: "source",
      kind: sourceGate.key === "suspect" ? "warning" : "source",
      label: sourceGate.key === "suspect" ? "Fix source first" : "Fetch source first",
      detail: sourceGate.detail,
      disabled: false,
    };
  }
  if (hasScopeIssue(item) || item?.processing_gated) {
    return { action: "scope", kind: "review", label: "", detail: "", disabled: false };
  }
  const section = firstOpenReviewSection(item);
  if (!section) {
    return {
      action: "complete",
      kind: "review",
      label: "Core review complete",
      detail: "All core workspace sections reviewed",
      disabled: true,
    };
  }
  const label = SECTION_LABELS[section] || "Review";
  return {
    action: "section",
    kind: section === "uplifts" ? "review" : "primary",
    label: section === "uplifts" ? "Review governed set" : `Open ${label}`,
    detail: section === "uplifts" ? "Final governed output" : "Next incomplete section",
    section,
    disabled: false,
  };
}

function intakeStatusLabel(status) {
  if (status === "accepted") return "Accepted source";
  if (status === "rejected") return "Rejected";
  return "Needs intake review";
}

function intakeConfidence(item) {
  const meta = item.fetch_metadata || {};
  const status = intakeStatus(item);
  if (status === "accepted") return { label: "Accepted", value: 96 };
  if (status === "rejected") return { label: "Rejected", value: 38 };
  if (!item.fetch_metadata) return { label: "Missing metadata", value: 35 };
  if (item.matched_lga_count === 0) return { label: "Unmatched", value: 42 };
  if (item.pdf_frozen === false) return { label: "Needs fetch", value: 64 };
  if ((meta.match_strength || "").includes("civic_strong") && !item.processing_gated) {
    return { label: "High", value: 92 };
  }
  if ((meta.matched_lga_count || "0") !== "0") return { label: "Medium", value: 72 };
  return { label: "Low", value: 46 };
}

function allIntakeRows() {
  return state.intakeRows.length ? state.intakeRows : state.councils;
}

function intakeDateOrdinal(item) {
  const ranked = Number(item?.rank?.operative_ordinal);
  if (Number.isFinite(ranked)) return ranked;
  const meta = item?.fetch_metadata || {};
  const rawDate = meta["Operative Date"] || meta.operative_date || item?.fwc?.operative_date || "";
  const parsedDate = Date.parse(rawDate);
  if (Number.isFinite(parsedDate)) return parsedDate / 86400000;
  const year = Number(meta.published_year || item?.rank?.published_year);
  return Number.isFinite(year) ? year * 366 : Number.NEGATIVE_INFINITY;
}

function intakeAgreementNumberRank(item) {
  const raw = item?.rank?.agreement_num_clean || item?.fetch_metadata?.agreement_num_clean || item?.fetch_metadata?.["Agreement ID"];
  const numeric = Number(raw);
  return Number.isFinite(numeric) ? numeric : 0;
}

function intakeProcessingRows(rows = allIntakeRows()) {
  return rows.filter((item) => intakeStatus(item) === "accepted");
}

function incomingRows(rows = allIntakeRows()) {
  return rows
    .filter((item) => !["accepted", "rejected"].includes(intakeStatus(item)))
    .sort(sortIncomingNewestFirst);
}

function rejectedIncomingRows(rows = allIntakeRows()) {
  return rows
    .filter((item) => intakeStatus(item) === "rejected")
    .sort(sortIncomingNewestFirst);
}

function sortIncomingNewestFirst(a, b) {
  return intakeDateOrdinal(b) - intakeDateOrdinal(a)
    || intakeAgreementNumberRank(b) - intakeAgreementNumberRank(a)
    || String(metadataPrimaryLabel(a) || a.ae_id).localeCompare(String(metadataPrimaryLabel(b) || b.ae_id));
}

function incomingConfidenceBand(item) {
  const confidence = intakeConfidence(item);
  if (confidence.value >= 85) {
    return { key: "high", label: "High confidence", detail: "Strong evidence match", confidence };
  }
  if (confidence.value >= 65) {
    return { key: "medium", label: "Medium confidence", detail: "Usable evidence, light checks", confidence };
  }
  return { key: "low", label: "Low confidence", detail: "Needs attention before processing", confidence };
}

function groupedIncomingRows(rows) {
  const groups = [
    { key: "high", label: "High confidence", detail: "Strong evidence match", rows: [] },
    { key: "medium", label: "Medium confidence", detail: "Usable evidence, light checks", rows: [] },
    { key: "low", label: "Low confidence", detail: "Needs attention before processing", rows: [] },
  ];
  const byKey = new Map(groups.map((group) => [group.key, group]));
  rows.forEach((item) => {
    const band = incomingConfidenceBand(item);
    byKey.get(band.key)?.rows.push(item);
  });
  return groups.filter((group) => group.rows.length);
}

function findIntakeRow(aeId) {
  return state.intakeRows.find((item) => item.ae_id === aeId)
    || state.councils.find((item) => item.ae_id === aeId);
}

async function saveIntakeDecision(aeId, status, reason = "", notes = "") {
  const result = await api(`/api/intake/candidates/${encodeURIComponent(aeId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ status, reason, notes }),
  });
  const updated = result.candidate;
  if (updated) {
    const index = state.intakeRows.findIndex((item) => item.ae_id === updated.ae_id);
    if (index >= 0) state.intakeRows[index] = updated;
    else state.intakeRows.push(updated);
  }
  renderIntake();
  renderIncoming();
  return result;
}

async function freezeIntakeSource(aeId, { forceRefresh = false } = {}) {
  const suffix = forceRefresh ? "?force_refresh=true" : "";
  const result = await api(`/api/intake/candidates/${encodeURIComponent(aeId)}/freeze${suffix}`, {
    method: "POST",
  });
  const updated = result.candidate;
  if (updated) {
    const index = state.intakeRows.findIndex((item) => item.ae_id === updated.ae_id);
    if (index >= 0) state.intakeRows[index] = updated;
    else state.intakeRows.push(updated);
  }
  await fetchCouncils();
  renderIncoming();
  return result;
}

function formatBytes(value) {
  return displayFileSize(value, "");
}

function applyIntakeQuickFilter(kind) {
  state.intakeQuickFilter = kind;
  if (kind === "frozen") {
    state.intakeStatusFilter = "all";
    state.intakeFilter = "pdf fetched";
  } else if (kind === "source_retry") {
    state.intakeStatusFilter = "all";
    state.intakeFilter = "suspect pdf retry source";
  } else if (kind === "accepted") {
    state.intakeStatusFilter = "accepted";
    state.intakeFilter = "";
  } else if (kind === "decisions") {
    state.intakeStatusFilter = "all";
    state.intakeFilter = "scope check";
  } else {
    state.intakeQuickFilter = "all";
    state.intakeStatusFilter = "all";
    state.intakeFilter = "";
  }

  const filter = document.getElementById("intake-status-filter");
  const search = document.getElementById("intake-filter");
  const sort = document.getElementById("intake-sort");
  if (filter) filter.value = state.intakeStatusFilter;
  if (search) search.value = state.intakeFilter;
  if (sort) sort.value = state.intakeSort;
  renderIntake();
}

function defaultIntakeReason(item, status) {
  const meta = item?.fetch_metadata || {};
  if (status === "accepted") return item?.pdf_frozen ? "Source accepted for governed QA" : "Source accepted; PDF fetch required before QA";
  if (status === "rejected" && (meta.pipeline_status || "").includes("superseded")) {
    return `Superseded by ${meta.superseded_by_ae_id || "newer agreement"}`;
  }
  if (status === "rejected") return "Rejected at incoming source triage";
  return "Requires further scope review";
}

function focusIntakeRow(aeId) {
  state.intakeQuickFilter = "custom";
  state.intakeStatusFilter = "all";
  state.intakeFilter = aeId;
  const filter = document.getElementById("intake-status-filter");
  const search = document.getElementById("intake-filter");
  if (filter) filter.value = "all";
  if (search) search.value = aeId;
  switchView("intake");
  renderIntake();
}

function focusMatrixRow(aeId) {
  const filter = document.getElementById("matrix-filter");
  if (filter) filter.value = aeId;
  switchView("matrix");
  renderMatrix();
  renderMatrixStats();
}

function formatCount(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return number.toLocaleString("en-AU");
}

function renderInlineMeta(items, className = "workbench-inline-meta") {
  const cleanItems = items
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);
  if (!cleanItems.length) return "";
  return `
    <div class="${escapeHtml(className)}">
      ${cleanItems.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
    </div>
  `;
}

function compactStatusLabel(status) {
  return String(status || "not_started").replaceAll("_", " ");
}

function matrixPrimaryActionLabel(nextAction) {
  if (nextAction.action === "scope") return "Resolve scope";
  if (nextAction.action === "complete") return "Complete";
  return nextAction.label || "Open";
}

function matrixSectionStatusSummary(item) {
  const statuses = item?.section_statuses || {};
  return MATRIX_CORE_REVIEW_SECTIONS
    .map((section) => `${MATRIX_SECTION_LABELS[section] || SECTION_LABELS[section] || section} ${compactStatusLabel(statuses[section])}`)
    .join(" | ");
}

function matrixAutomationSummary(item) {
  const prep = overviewPreparationState(item.ae_id);
  const human = syntheticHumanReviewState(item.ae_id);
  const jobs = Object.values(prep?.jobs || {});
  const humanJobs = Object.values(human?.jobs || {});
  if (human?.awaitingSystemImprovement) return "Paused for system improvement";
  if (human?.running || humanJobs.some((job) => job.status === "running")) return "Automated reviewer running";
  if (prep?.running || jobs.some((job) => job.status === "running")) return "Computer running";
  if (humanJobs.some((job) => job.status === "failed") || jobs.some((job) => job.status === "failed")) return "Needs attention";
  if (human?.completed) return "Automated reviewer complete";
  if (prep?.completed) return "Computer complete";
  return isReviewBoardReady(item) ? "Ready" : "Gated";
}

function renderIntakeQuality(total, active) {
  const quality = state.intakeQuality;
  if (!quality) {
    setText("quality-state", "Unavailable");
    setText("quality-rule-summary", "Intake quality summary could not be loaded.");
    document.getElementById("quality-state")?.classList.add("quality-state-warning");
    setText("quality-candidates", formatCount(total));
    setText("quality-visible", formatCount(active));
    setText("quality-runner-ups", "-");
    setText("quality-unmatched", "-");
    const flags = document.getElementById("quality-flags");
    if (flags) flags.innerHTML = "";
    return;
  }

  const candidate = quality.candidate_records || {};
  const working = quality.working_set || {};
  const topTwo = quality.top_two_review || {};
  const rule = quality.selection_rule || {};
  const warnings = (quality.flags || []).filter((flag) => flag.severity !== "info").length;
  const stateEl = document.getElementById("quality-state");
  if (stateEl) stateEl.classList.toggle("quality-state-warning", warnings > 0);

  setText("quality-state", warnings ? `${warnings} checks` : "Clean");
  setText(
    "quality-rule-summary",
    [rule.promotion_policy, rule.top_two_note].filter(Boolean).join(" ") || "Selection rule available.",
  );
  setText("quality-candidates", formatCount(candidate.total, formatCount(total)));
  setText("quality-visible", formatCount(working.visible, formatCount(active)));
  setText("quality-runner-ups", formatCount(topTwo.unique_runner_up_candidates, "0"));
  setText("quality-unmatched", formatCount(candidate.active_unmatched, "0"));

  const flags = document.getElementById("quality-flags");
  if (!flags) return;
  const rows = (quality.flags || []).slice(0, 3);
  if (!rows.length) {
    flags.innerHTML = '<div class="quality-flag quality-flag-clean">No intake quality exceptions raised.</div>';
    return;
  }
  flags.innerHTML = rows.map((flag) => {
    const value = flag.value === undefined ? "" : `<strong>${escapeHtml(formatCount(flag.value))}</strong>`;
    return `
      <div class="quality-flag quality-flag-${escapeHtml(flag.severity || "info")}">
        ${value}
        <span>${escapeHtml(flag.label || "Quality check")}</span>
      </div>
    `;
  }).join("");
}

function renderIncoming() {
  const list = document.getElementById("incoming-list");
  if (!list) return;

  const rows = allIntakeRows();
  const incoming = incomingRows(rows);
  const rejected = rejectedIncomingRows(rows);
  const processing = intakeProcessingRows(rows);
  const highConfidence = incoming.filter((item) => incomingConfidenceBand(item).key === "high").length;

  setText("incoming-total", formatCount(incoming.length, "0"));
  setText("incoming-high", formatCount(highConfidence, "0"));
  setText("incoming-processing", formatCount(processing.length, "0"));
  if (document.body.dataset.view === "incoming") {
    setText("header-stats", `${formatCount(incoming.length, "0")} incoming | ${formatCount(processing.length, "0")} in processing | ${formatCount(rejected.length, "0")} rejected`);
  }

  const rejectedHtml = renderRejectedIncomingSection(rejected);

  if (!incoming.length) {
    const emptyHtml = renderEmptyState(
      "No incoming candidates",
      "Accepted source items are available in Intake Processing.",
      {
        eyebrow: "Incoming",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-open-intake-processing="1">Open intake processing</button>',
      },
    );
    list.innerHTML = emptyHtml + rejectedHtml;
    list.querySelector("[data-open-intake-processing]")?.addEventListener("click", () => switchView("intake"));
    return;
  }

  list.innerHTML = groupedIncomingRows(incoming).map((group) => `
    <section class="incoming-confidence-group incoming-confidence-${escapeHtml(group.key)}">
      <header class="incoming-group-header">
        <div>
          <h2>${escapeHtml(group.label)}</h2>
          <p>${escapeHtml(group.detail)}</p>
        </div>
        <strong>${escapeHtml(formatCount(group.rows.length, "0"))}</strong>
      </header>
      <div class="incoming-card-list">
        ${group.rows.map(renderIncomingCard).join("")}
      </div>
    </section>
  `).join("") + rejectedHtml;

  list.querySelectorAll("[data-incoming-accept]").forEach((button) => {
    button.addEventListener("click", async () => {
      const aeId = button.dataset.aeId;
      const item = findIntakeRow(aeId);
      if (!item || button.disabled) return;
      const originalText = button.textContent;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = "Adding...";
      try {
        await saveIntakeDecision(aeId, "accepted", defaultIntakeReason(item, "accepted"), "");
        toast(`Added ${aeId.toUpperCase()} to Intake Processing`, "success");
      } catch (error) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.textContent = originalText;
        toast(apiErrorMessage(error), "error");
      }
    });
  });
  list.querySelectorAll("[data-incoming-reject]").forEach((button) => {
    button.addEventListener("click", async () => {
      const aeId = button.dataset.aeId;
      const item = findIntakeRow(aeId);
      if (!item || button.disabled) return;
      const originalText = button.textContent;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = "Rejecting...";
      try {
        await saveIntakeDecision(aeId, "rejected", defaultIntakeReason(item, "rejected"), "");
        toast(`Rejected ${aeId.toUpperCase()} from Incoming`, "success");
      } catch (error) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.textContent = originalText;
        toast(apiErrorMessage(error), "error");
      }
    });
  });
}

function renderRejectedIncomingSection(rows) {
  if (!rows.length) return "";
  return `
    <details class="incoming-rejected-section">
      <summary>
        <span>Rejected</span>
        <strong>${escapeHtml(formatCount(rows.length, "0"))}</strong>
      </summary>
      <div class="incoming-card-list">
        ${rows.map((item) => renderIncomingCard(item, { rejected: true })).join("")}
      </div>
    </details>
  `;
}

function renderIncomingCard(item, { rejected = false } = {}) {
  const meta = item.fetch_metadata || {};
  const confidence = intakeConfidence(item);
  const band = rejected ? { key: "rejected" } : incomingConfidenceBand(item);
  const sourceGate = sourceGateStatus(item);
  const title = metadataPrimaryLabel(item) || item.ae_id;
  const matched = splitMatchedNames(meta).join(", ") || item.canonical_lga_short_name || "Unassigned";
  const dateRange = meta ? formatDateRange(meta) : "Dates not stated";
  const scopeLabel = hasScopeIssue(item) ? "Scope check" : "Scope clear";
  const metaItems = [
    dateRange,
    matched,
    sourceGate.label,
    scopeLabel,
    `${confidence.value}% ${confidence.label}`,
  ];
  const actionHtml = rejected
    ? '<div class="incoming-actions workbench-card-actions"><span class="incoming-rejected-note">Hidden from processing</span></div>'
    : `
      <div class="incoming-actions workbench-card-actions">
        <button class="incoming-add-btn" data-incoming-accept data-ae-id="${escapeHtml(item.ae_id)}">Add to processing</button>
        <button class="incoming-reject-btn" data-incoming-reject data-ae-id="${escapeHtml(item.ae_id)}">Reject</button>
      </div>
    `;
  return `
    <article class="incoming-card workbench-card-scaffold incoming-card-${escapeHtml(band.key)}">
      <div class="incoming-card-main workbench-card-main">
        <div class="incoming-card-title workbench-card-title">
          <span class="intake-ae-pill">${escapeHtml(item.ae_id.toUpperCase())}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
        ${renderInlineMeta(metaItems, "incoming-card-meta workbench-inline-meta")}
      </div>
      ${actionHtml}
    </article>
  `;
}

function ensureJobSourceRegistry({ force = false } = {}) {
  if (state.jobSourceRegistry && !force) return Promise.resolve(state.jobSourceRegistry);
  if (state.jobSourceRegistryLoading && !force) return state.jobSourceRegistryLoading;
  state.jobSourceRegistryLoading = api("/api/reference/council-job-sources")
    .then((payload) => {
      state.jobSourceRegistry = payload;
      return payload;
    })
    .finally(() => {
      state.jobSourceRegistryLoading = null;
    });
  return state.jobSourceRegistryLoading;
}

function ensureJobScrapePreview({ force = false, enrichAttachments = false } = {}) {
  if (state.jobScrapePreview && !force && state.jobScrapePreviewLinkedDocuments === enrichAttachments) {
    return Promise.resolve(state.jobScrapePreview);
  }
  if (state.jobScrapePreviewLoading && !force) return state.jobScrapePreviewLoading;
  if (!force) {
    state.jobScrapePreviewLoading = api("/api/job-intake/snapshot")
      .then((payload) => {
        state.jobScrapePreview = payload;
        state.jobScrapePreviewStarted = Boolean(payload?.snapshot_exists);
        state.jobScrapePreviewLinkedDocuments = Boolean(payload?.scope?.linked_document_enrichment === "all_linked_documents");
        return payload;
      })
      .finally(() => {
        state.jobScrapePreviewLoading = null;
      });
    return state.jobScrapePreviewLoading;
  }
  const params = new URLSearchParams({
    source_limit: "0",
    job_limit: "500",
    timeout: enrichAttachments ? "15" : "12",
    enrich_pay_tables: "true",
    enrich_details: "true",
    detail_job_limit: "500",
    enrich_attachments: enrichAttachments ? "true" : "false",
    attachment_job_limit: enrichAttachments ? "500" : "300",
    resolve_missing_documents: "true",
  });
  state.jobScrapePreviewLoading = api(`/api/job-intake/refresh?${params.toString()}`, { method: "POST" })
    .then((payload) => {
      state.jobScrapePreview = payload;
      state.jobScrapePreviewStarted = true;
      state.jobScrapePreviewLinkedDocuments = enrichAttachments;
      state.jobPipelineStage1 = null;
      return payload;
    })
    .finally(() => {
      state.jobScrapePreviewLoading = null;
    });
  return state.jobScrapePreviewLoading;
}

function ensureJobEndpointResolution({ force = false } = {}) {
  if (state.jobEndpointResolution && !force) return Promise.resolve(state.jobEndpointResolution);
  if (state.jobEndpointResolutionLoading && !force) return state.jobEndpointResolutionLoading;
  state.jobEndpointResolutionLoading = api("/api/job-intake/endpoint-resolution-preview?candidate_limit=500&job_limit=200&timeout=6")
    .then((payload) => {
      state.jobEndpointResolution = payload;
      state.jobEndpointResolutionStarted = true;
      return payload;
    })
    .finally(() => {
      state.jobEndpointResolutionLoading = null;
    });
  return state.jobEndpointResolutionLoading;
}

function ensureJobSecondaryPreview({ force = false } = {}) {
  if (state.jobSecondaryPreview && !force) return Promise.resolve(state.jobSecondaryPreview);
  if (state.jobSecondaryPreviewLoading && !force) return state.jobSecondaryPreviewLoading;
  state.jobSecondaryPreviewLoading = api("/api/job-intake/secondary-preview?source_limit=0&job_limit=5000&timeout=10&enrich_pay_tables=true&enrich_details=true&detail_job_limit=1000&expand_sector_board_council_pages=true")
    .then((payload) => {
      state.jobSecondaryPreview = payload;
      state.jobSecondaryPreviewStarted = true;
      return payload;
    })
    .finally(() => {
      state.jobSecondaryPreviewLoading = null;
    });
  return state.jobSecondaryPreviewLoading;
}

function ensureJobAccumulator({ force = false } = {}) {
  if (state.jobAccumulator && !force) return Promise.resolve(state.jobAccumulator);
  if (state.jobAccumulatorLoading && !force) return state.jobAccumulatorLoading;
  state.jobAccumulatorLoading = api("/api/job-intake/accumulator")
    .then((payload) => {
      state.jobAccumulator = payload;
      state.jobAccumulatorStarted = true;
      return payload;
    })
    .finally(() => {
      state.jobAccumulatorLoading = null;
    });
  return state.jobAccumulatorLoading;
}

function ensureJobPipelineStage1({ force = false } = {}) {
  if (state.jobPipelineStage1 && !force) return Promise.resolve(state.jobPipelineStage1);
  if (state.jobPipelineStage1Loading && !force) return state.jobPipelineStage1Loading;
  state.jobPipelineStage1Loading = api("/api/job-pipeline/stage1")
    .then((payload) => {
      state.jobPipelineStage1 = payload;
      return payload;
    })
    .finally(() => {
      state.jobPipelineStage1Loading = null;
    });
  return state.jobPipelineStage1Loading;
}

function jobIntakeRows() {
  return Array.isArray(state.jobSourceRegistry?.rows) ? state.jobSourceRegistry.rows : [];
}

function observedJobRows() {
  return Array.isArray(state.jobScrapePreview?.rows) ? state.jobScrapePreview.rows : [];
}

function secondaryJobRows() {
  return Array.isArray(state.jobSecondaryPreview?.rows) ? state.jobSecondaryPreview.rows : [];
}

function checkedJobRows() {
  return Array.isArray(state.jobAccumulator?.rows) ? state.jobAccumulator.rows : [];
}

function jobPipelineRows() {
  return Array.isArray(state.jobPipelineStage1?.rows) ? state.jobPipelineStage1.rows : [];
}

function jobObservedSearchText(job) {
  return [
    job.job_title,
    job.short_name,
    job.council_name,
    job.source_family,
    job.classification_band,
    job.inferred_classification_band,
    job.salary_text,
    job.advertised_salary_text,
    job.advertised_salary_basis,
    job.enterprise_agreement_salary_min,
    job.enterprise_agreement_salary_max,
    job.enterprise_agreement_salary_basis,
    job.canonical_reference_month,
    job.canonical_reference_date_source,
    job.work_type,
    job.location_text,
    job.department,
    job.governance_status,
    job.salary_band_validation_status,
    job.completion_action,
    job.completion_action_label,
    job.completion_reason,
    job.position_description_url,
    job.position_description_excerpt,
  ].filter(Boolean).join(" ").toLowerCase();
}

function jobObservedBandValue(job) {
  const band = job.standard_band_number || job.inferred_standard_band_number;
  return band ? String(band) : "unknown";
}

function filteredObservedJobRows() {
  const query = state.jobObservedFilter.trim().toLowerCase();
  const tokens = query.split(/\s+/).filter(Boolean);
  return observedJobRows()
    .filter((job) => state.jobObservedGovernance === "all" || job.governance_status === state.jobObservedGovernance)
    .filter((job) => state.jobObservedPlatform === "all" || job.source_family === state.jobObservedPlatform)
    .filter((job) => state.jobObservedBand === "all" || jobObservedBandValue(job) === state.jobObservedBand)
    .filter((job) => !tokens.length || tokens.every((token) => jobObservedSearchText(job).includes(token)))
    .sort((a, b) => jobGovernanceSort(a) - jobGovernanceSort(b)
      || String(a.council_name || a.short_name || "").localeCompare(String(b.council_name || b.short_name || ""))
      || String(a.job_title || "").localeCompare(String(b.job_title || "")));
}

function checkedJobSearchText(row) {
  const latest = row.latest_job || {};
  return [
    row.job_title,
    row.short_name,
    row.council_name,
    row.classification_band,
    row.standard_band_number ? `band ${row.standard_band_number}` : "",
    row.canonical_reference_month,
    row.classification_confidence,
    row.observed_status,
    row.source_family,
    row.source_name,
    latest.salary_text,
    latest.work_type,
    latest.location_text,
  ].filter(Boolean).join(" ").toLowerCase();
}

function filteredCheckedJobRows() {
  const query = state.jobAccumulatorFilter.trim().toLowerCase();
  const tokens = query.split(/\s+/).filter(Boolean);
  return checkedJobRows()
    .filter((row) => !tokens.length || tokens.every((token) => checkedJobSearchText(row).includes(token)))
    .sort((a, b) => String(b.canonical_reference_month || "").localeCompare(String(a.canonical_reference_month || ""))
      || String(a.council_name || a.short_name || "").localeCompare(String(b.council_name || b.short_name || ""))
      || String(a.job_title || "").localeCompare(String(b.job_title || "")));
}

function jobPipelineSearchText(row) {
  return [
    row.job_title,
    row.council_name,
    row.short_name,
    row.source_family,
    row.classification_band,
    row.standard_band_number ? `band ${row.standard_band_number}` : "",
    row.canonical_reference_month,
    row.canonical_reference_date_source,
    row.advertised_salary_text,
    row.advertised_salary_basis,
    row.enterprise_agreement_salary_min,
    row.enterprise_agreement_salary_basis,
    row.salary_band_validation_status,
    row.stage1_status,
    row.next_action,
    ...(row.missing_required_fields || []),
    ...(row.missing_optional_fields || []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function filteredJobPipelineRows() {
  const query = state.jobPipelineFilter.trim().toLowerCase();
  const tokens = query.split(/\s+/).filter(Boolean);
  return jobPipelineRows()
    .filter((row) => state.jobPipelineStatus === "all" || row.stage1_status === state.jobPipelineStatus)
    .filter((row) => !tokens.length || tokens.every((token) => jobPipelineSearchText(row).includes(token)))
    .sort((a, b) => {
      const aMissing = Array.isArray(a.missing_required_fields) ? a.missing_required_fields.length : 0;
      const bMissing = Array.isArray(b.missing_required_fields) ? b.missing_required_fields.length : 0;
      return (a.stage1_status === "stage1_fill_required" ? 0 : 1) - (b.stage1_status === "stage1_fill_required" ? 0 : 1)
        || bMissing - aMissing
        || String(a.council_name || a.short_name || "").localeCompare(String(b.council_name || b.short_name || ""))
        || String(a.job_title || "").localeCompare(String(b.job_title || ""));
    });
}

function jobGovernanceSort(job) {
  const order = {
    auto_included: 0,
    needs_band_confirmation: 1,
    needs_band_review: 2,
  };
  return order[job.governance_status] ?? 9;
}

function jobIntakeSearchText(row) {
  return [
    row.short_name,
    row.council_name,
    row.council_grouping,
    row.poll_tier,
    row.platform_family,
    row.adapter,
    row.monitoring_status,
    row.official_careers_entry_url,
    row.listing_url,
    row.notes,
  ].filter(Boolean).join(" ").toLowerCase();
}

function filteredJobIntakeRows() {
  const query = state.jobIntakeFilter.trim().toLowerCase();
  const tokens = query.split(/\s+/).filter(Boolean);
  return jobIntakeRows()
    .filter((row) => state.jobIntakeTier === "all" || row.poll_tier === state.jobIntakeTier)
    .filter((row) => state.jobIntakePlatform === "all" || row.platform_family === state.jobIntakePlatform)
    .filter((row) => state.jobIntakeStatus === "all" || row.monitoring_status === state.jobIntakeStatus)
    .filter((row) => !tokens.length || tokens.every((token) => jobIntakeSearchText(row).includes(token)))
    .sort((a, b) => String(a.poll_tier || "").localeCompare(String(b.poll_tier || ""))
      || String(a.council_name || a.short_name || "").localeCompare(String(b.council_name || b.short_name || "")));
}

function jobIntakeStatusLabel(status) {
  if (status === "ready") return "Ready";
  if (status === "needs_endpoint_discovery") return "Pattern queue";
  return displayCodeLabel(status || "unknown");
}

function jobIntakePlatformLabel(platform) {
  const labels = {
    adlogic_martianlogic: "Adlogic / Martian Logic",
    applynow: "ApplyNow",
    aurion_selfservice: "Aurion",
    bigredsky: "BigRedSky",
    native_council: "Native council",
    native_council_custom: "Custom council site",
    oracle_hcm: "Oracle HCM",
    pageup: "PageUp",
    pulse: "Pulse",
    recruitmenthub: "RecruitmentHub",
    employmenthero: "Employment Hero",
    successfactors: "SuccessFactors",
    t1cloud: "T1Cloud",
    unknown_official: "Official link",
  };
  return labels[platform] || displayCodeLabel(platform || "unknown");
}

function jobIntakeTierLabel(tier) {
  if (tier === "A") return "Tier A";
  if (tier === "B") return "Tier B";
  if (tier === "C") return "Tier C";
  return displayValue(tier);
}

function clearJobIntakeFilters() {
  state.jobIntakeFilter = "";
  state.jobIntakeTier = "all";
  state.jobIntakePlatform = "all";
  state.jobIntakeStatus = "all";
  state.jobObservedFilter = "";
  state.jobObservedGovernance = "all";
  state.jobObservedPlatform = "all";
  state.jobObservedBand = "all";
  state.jobAccumulatorFilter = "";
  const filter = document.getElementById("job-intake-filter");
  const tier = document.getElementById("job-intake-tier");
  const platform = document.getElementById("job-intake-platform");
  const statusSelect = document.getElementById("job-intake-status");
  const jobFilter = document.getElementById("job-observed-filter");
  const jobGovernance = document.getElementById("job-observed-governance");
  const jobPlatform = document.getElementById("job-observed-platform");
  const jobBand = document.getElementById("job-observed-band");
  const historyFilter = document.getElementById("job-history-filter");
  if (filter) filter.value = "";
  if (tier) tier.value = "all";
  if (platform) platform.value = "all";
  if (statusSelect) statusSelect.value = "all";
  if (jobFilter) jobFilter.value = "";
  if (jobGovernance) jobGovernance.value = "all";
  if (jobPlatform) jobPlatform.value = "all";
  if (jobBand) jobBand.value = "all";
  if (historyFilter) historyFilter.value = "";
}

function updateJobIntakePlatformSelect() {
  const select = document.getElementById("job-intake-platform");
  if (!select) return;
  const platforms = [...new Set(jobIntakeRows().map((row) => row.platform_family).filter(Boolean))]
    .sort((a, b) => jobIntakePlatformLabel(a).localeCompare(jobIntakePlatformLabel(b)));
  select.innerHTML = [
    '<option value="all">All platforms</option>',
    ...platforms.map((platform) => {
      const selected = state.jobIntakePlatform === platform ? " selected" : "";
      return `<option value="${escapeHtml(platform)}"${selected}>${escapeHtml(jobIntakePlatformLabel(platform))}</option>`;
    }),
  ].join("");
  if (!platforms.includes(state.jobIntakePlatform)) {
    state.jobIntakePlatform = "all";
    select.value = "all";
  }
}

function updateObservedJobFilterSelects() {
  const platformSelect = document.getElementById("job-observed-platform");
  const bandSelect = document.getElementById("job-observed-band");
  const rows = observedJobRows();
  if (platformSelect) {
    const platforms = [...new Set(rows.map((job) => job.source_family).filter(Boolean))]
      .sort((a, b) => jobIntakePlatformLabel(a).localeCompare(jobIntakePlatformLabel(b)));
    platformSelect.innerHTML = [
      '<option value="all">All platforms</option>',
      ...platforms.map((platform) => {
        const selected = state.jobObservedPlatform === platform ? " selected" : "";
        return `<option value="${escapeHtml(platform)}"${selected}>${escapeHtml(jobIntakePlatformLabel(platform))}</option>`;
      }),
    ].join("");
    if (!platforms.includes(state.jobObservedPlatform)) {
      state.jobObservedPlatform = "all";
      platformSelect.value = "all";
    }
  }
  if (bandSelect) {
    const bands = [...new Set(rows.map(jobObservedBandValue).filter(Boolean))]
      .sort((a, b) => {
        if (a === "unknown") return 1;
        if (b === "unknown") return -1;
        return Number(a) - Number(b);
      });
    bandSelect.innerHTML = [
      '<option value="all">All bands</option>',
      ...bands.map((band) => {
        const selected = state.jobObservedBand === band ? " selected" : "";
        const label = band === "unknown" ? "Band review" : `Band ${band}`;
        return `<option value="${escapeHtml(band)}"${selected}>${escapeHtml(label)}</option>`;
      }),
    ].join("");
    if (!bands.includes(state.jobObservedBand)) {
      state.jobObservedBand = "all";
      bandSelect.value = "all";
    }
  }
}

function renderJobIntakeMetrics() {
  const summary = state.jobSourceRegistry?.summary || {};
  const scrapeSummary = state.jobScrapePreview?.summary || {};
  setText("job-intake-observed-count", formatCount(scrapeSummary.jobs, state.jobScrapePreviewLoading ? "..." : "0"));
  setText("job-intake-council-count", formatCount(summary.councils, "0"));
  setText("job-intake-ready-count", formatCount(summary.ready_sources, "0"));
  setText("job-intake-discovery-count", formatCount(summary.needs_endpoint_discovery, "0"));
  setText("job-intake-restricted-count", formatCount(summary.restricted_sources, "0"));
  setText(
    "job-intake-status-note",
    state.jobScrapePreview?.snapshot_exists
      ? `${formatCount(scrapeSummary.jobs, "0")} saved roles across ${formatCount(scrapeSummary.councils_with_jobs ?? scrapeSummary.sources_with_jobs, "0")} council${scrapeSummary.councils_with_jobs === 1 ? "" : "s"}; ${formatCount(scrapeSummary.band_completion_rate, "0")}% band complete; saved ${formatJobDateTime(state.jobScrapePreview.saved_at)}; ${formatCount(summary.ready_sources, "0")} verified endpoints.`
      : `${formatCount(summary.ready_sources, "0")} verified endpoints. Refresh the intake snapshot when you want to fetch current jobs.`,
  );
  if (document.body.dataset.view === "job-intake") {
    setText(
      "header-stats",
      `${formatCount(scrapeSummary.jobs, "0")} observed | ${formatCount(scrapeSummary.councils_with_jobs ?? scrapeSummary.sources_with_jobs, "0")} with jobs | ${formatCount(summary.councils, "0")} councils`,
    );
  }
}

function renderJobIntakeTabs() {
  document.querySelectorAll("[data-job-intake-tab]").forEach((button) => {
    const isActive = button.dataset.jobIntakeTab === state.jobIntakeTab;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  document.querySelectorAll(".job-intake-tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `job-intake-tab-${state.jobIntakeTab}`);
  });
}

function renderJobIntakeTierExplainer() {
  const host = document.getElementById("job-intake-tier-list");
  if (!host) return;
  const tiers = state.jobSourceRegistry?.polling_policy?.tier_explainer
    || state.jobScrapePreview?.tier_explainer
    || [];
  if (!tiers.length) {
    host.innerHTML = '<div class="muted">Tier definitions will appear with the registry.</div>';
    return;
  }
  host.innerHTML = tiers.map((item) => `
    <button class="job-tier-explainer-row ${state.jobIntakeTier === item.tier ? "is-active" : ""}" type="button" data-job-tier="${escapeHtml(item.tier)}" aria-pressed="${state.jobIntakeTier === item.tier ? "true" : "false"}">
      <span class="job-tier-pill job-tier-${escapeHtml(item.tier)}">${escapeHtml(jobIntakeTierLabel(item.tier))}</span>
      <strong>${escapeHtml(item.cadence || "")}</strong>
      <small>${escapeHtml(item.meaning || "")}</small>
    </button>
  `).join("");
  host.querySelectorAll("[data-job-tier]").forEach((button) => {
    button.addEventListener("click", () => {
      state.jobIntakeTier = state.jobIntakeTier === button.dataset.jobTier ? "all" : button.dataset.jobTier;
      const select = document.getElementById("job-intake-tier");
      if (select) select.value = state.jobIntakeTier;
      renderJobIntake();
    });
  });
}

function renderJobIntakePlatformMix() {
  const host = document.getElementById("job-intake-platform-list");
  if (!host) return;
  const counts = state.jobSourceRegistry?.summary?.platform_families || {};
  const entries = Object.entries(counts).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0));
  if (!entries.length) {
    host.innerHTML = '<div class="muted">No platform counts loaded.</div>';
    return;
  }
  const max = Math.max(...entries.map(([, count]) => Number(count || 0)), 1);
  host.innerHTML = entries.map(([platform, count]) => {
    const selected = state.jobIntakePlatform === platform;
    const width = Math.max(8, Math.round((Number(count || 0) / max) * 100));
    return `
      <button class="job-intake-platform-row ${selected ? "is-active" : ""}" type="button" data-job-platform="${escapeHtml(platform)}" aria-pressed="${selected ? "true" : "false"}">
        <span>${escapeHtml(jobIntakePlatformLabel(platform))}</span>
        <strong>${escapeHtml(formatCount(count, "0"))}</strong>
        <i><b style="width:${width}%"></b></i>
      </button>
    `;
  }).join("");
  host.querySelectorAll("[data-job-platform]").forEach((button) => {
    button.addEventListener("click", () => {
      state.jobIntakePlatform = state.jobIntakePlatform === button.dataset.jobPlatform ? "all" : button.dataset.jobPlatform;
      const select = document.getElementById("job-intake-platform");
      if (select) select.value = state.jobIntakePlatform;
      renderJobIntake();
    });
  });
}

function renderJobIntakeSourceLists() {
  const secondary = document.getElementById("job-intake-secondary-list");
  const restricted = document.getElementById("job-intake-restricted-list");
  if (secondary) {
    const sources = state.jobSourceRegistry?.secondary_sources || [];
    secondary.innerHTML = sources.length ? sources.map((source) => `
      <a class="job-intake-source-card" href="${escapeHtml(source.url || "#")}" target="_blank" rel="noreferrer">
        <strong>${escapeHtml(source.source_name || source.source_id)}</strong>
        <span>${escapeHtml(source.best_use || source.monitoring_role || "")}</span>
      </a>
    `).join("") : '<div class="muted">No secondary sources loaded.</div>';
  }
  if (restricted) {
    const sources = state.jobSourceRegistry?.restricted_sources || [];
    restricted.innerHTML = sources.length ? sources.map((source) => `
      <article class="job-intake-source-card is-restricted">
        <strong>${escapeHtml(source.source_name || source.source_id)}</strong>
        <span>${escapeHtml(source.best_use || source.access_policy || "")}</span>
      </article>
    `).join("") : '<div class="muted">No restricted sources loaded.</div>';
  }
}

function renderObservedJobCard(job) {
  const posted = formatJobDate(job.posted_at || job.posted_at_text);
  const closes = formatJobDate(job.closing_at || job.closing_at_text);
  const salary = formatJobSalary(job);
  const enterpriseAgreementSalary = formatEnterpriseAgreementJobSalary(job);
  const governance = jobGovernanceLabel(job);
  const band = job.classification_band || job.inferred_classification_band || "Band review";
  const meta = [
    job.short_name || job.council_name,
    jobIntakePlatformLabel(job.source_family),
    band,
    salary,
    posted ? `Posted ${posted}` : "",
    closes ? `Closes ${closes}` : "",
  ];
  const detailMeta = [
    job.work_type,
    job.location_text,
    job.department,
    job.completion_action_label ? `Next ${job.completion_action_label}` : "",
    enterpriseAgreementSalary ? `EA ${enterpriseAgreementSalary}` : "",
    job.salary_band_validation_status ? `Salary check ${displayCodeLabel(job.salary_band_validation_status)}` : "",
    job.source_job_id ? `ID ${job.source_job_id}` : "",
  ];
  const evidence = [
    job.governance_notes,
    job.salary_band_validation?.notes,
    job.salary_enrichment_notes,
  ].filter(Boolean);
  const fieldSources = job.field_sources || {};
  const pdLink = job.position_description_url
    ? `<p class="job-observed-link-row"><a href="${escapeHtml(job.position_description_url)}" target="_blank" rel="noreferrer">Position description</a><span>${escapeHtml([
      fieldSources.classification_band ? `Band from ${displayCodeLabel(fieldSources.classification_band)}` : "",
      fieldSources.salary_text ? `Salary from ${displayCodeLabel(fieldSources.salary_text)}` : "",
    ].filter(Boolean).join(" / ") || "Linked evidence")}</span></p>`
    : "";
  return `
    <article class="job-observed-card job-observed-${escapeHtml(job.governance_status || "unknown")}">
      <div class="job-observed-row">
        <div class="job-observed-title">
          <span class="job-governance-chip">${escapeHtml(governance || "Review")}</span>
          <div>
            <h4>${escapeHtml(job.job_title || "Untitled job")}</h4>
            ${renderInlineMeta(meta, "job-intake-meta workbench-inline-meta")}
          </div>
        </div>
        <a href="${escapeHtml(job.job_url || "#")}" target="_blank" rel="noreferrer">Open</a>
      </div>
      <details class="job-observed-detail">
        <summary><span>Source detail</span><strong>${escapeHtml(detailMeta.filter(Boolean).join(" | ") || "No extra fields parsed")}</strong></summary>
        <div class="job-observed-detail-grid">
          ${renderJobFact("Posted", posted || "Not parsed")}
          ${renderJobFact("Closes", closes || "Not parsed")}
          ${renderJobFact("Reference month", job.canonical_reference_month || "Not parsed")}
          ${renderJobFact("Band", band)}
          ${renderJobFact("Advertised salary", salary || job.salary_text || "Not parsed")}
          ${renderJobFact("Enterprise Agreement salary", enterpriseAgreementSalary || "Not available")}
          ${renderJobFact("Advertised basis", job.advertised_salary_basis || job.salary_basis || "Not parsed")}
          ${renderJobFact("EA basis", job.enterprise_agreement_salary_basis || "Not available")}
          ${renderJobFact("Next action", job.completion_action_label || "Not classified")}
          ${renderJobFact("Salary validation", displayCodeLabel(job.salary_band_validation_status || "not_checked"))}
        </div>
        ${pdLink}
        ${evidence.length ? `<p>${escapeHtml(evidence.join(" "))}</p>` : ""}
      </details>
    </article>
  `;
}

function renderJobFact(label, value) {
  return `
    <div class="job-observed-fact">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "Not parsed")}</strong>
    </div>
  `;
}

function formatEnterpriseAgreementJobSalary(job) {
  const min = Number(job.enterprise_agreement_salary_min ?? job.canonical_salary_min);
  const max = Number(job.enterprise_agreement_salary_max ?? job.canonical_salary_max);
  if (!Number.isFinite(min)) return "";
  const same = Number.isFinite(max) && Math.abs(max - min) < 0.005;
  const period = job.enterprise_agreement_salary_period || job.canonical_salary_period || "year";
  return same || !Number.isFinite(max)
    ? `${formatMoney(min)}/${period}`
    : `${formatMoney(min)}-${formatMoney(max)}/${period}`;
}

function formatCanonicalJobSalary(job) {
  return formatEnterpriseAgreementJobSalary(job);
}

function formatJobDate(value) {
  if (!value) return "";
  const raw = String(value);
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleDateString("en-AU", { day: "2-digit", month: "short", year: "numeric" });
}

function formatJobDateTime(value) {
  if (!value) return "not saved";
  const raw = String(value);
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return raw;
  return parsed.toLocaleString("en-AU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatJobSalary(job) {
  const min = Number(job.advertised_salary_min ?? job.salary_min);
  const max = Number(job.advertised_salary_max ?? job.salary_max);
  const period = job.advertised_salary_period || job.salary_period || "";
  if (Number.isFinite(min)) {
    const same = Number.isFinite(max) && Math.abs(max - min) < 0.005;
    const range = same || !Number.isFinite(max)
      ? formatMoney(min)
      : `${formatMoney(min)}-${formatMoney(max)}`;
    return period ? `${range}/${period}` : range;
  }
  return "";
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: Number(value) < 1000 ? 2 : 0,
  }).format(value);
}

function jobGovernanceLabel(job) {
  if (job.governance_status === "auto_included") return "Band governed";
  if (job.governance_status === "needs_band_confirmation") return "Band inferred";
  if (job.governance_status === "needs_band_review") return "Band review";
  if (job.governance_status === "auto_excluded") return "Out of scope";
  return "";
}

function renderJobSourceResult(result) {
  const ok = result.status === "ok";
  const label = ok
    ? `${formatCount(result.parsed_jobs, "0")} parsed`
    : "needs action";
  return `
    <article class="job-source-result ${ok ? "is-ok" : "is-failed"}">
      <div>
        <strong>${escapeHtml(result.council_name || result.short_name || "Unknown source")}</strong>
        <span>${escapeHtml([
    jobIntakeTierLabel(result.poll_tier),
    jobIntakePlatformLabel(result.platform_family),
    label,
  ].filter(Boolean).join(" / "))}</span>
      </div>
    </article>
  `;
}

function renderObservedJobs() {
  const host = document.getElementById("job-observed-list");
  const status = document.getElementById("job-observed-status");
  const resultList = document.getElementById("job-source-result-list");
  const resultCount = document.getElementById("job-source-result-count");
  if (!host) return;
  updateObservedJobFilterSelects();
  const allRows = observedJobRows();
  const rows = filteredObservedJobRows();
  const summary = state.jobScrapePreview?.summary || {};
  if (state.jobScrapePreviewLoading) {
    if (status) status.textContent = state.jobScrapePreviewLinkedDocuments ? "Running linked-document enrichment..." : "Refreshing intake snapshot...";
    host.innerHTML = renderEmptyState("Running", "Fetching verified sources.", { eyebrow: "Observed jobs" });
  } else if (!state.jobScrapePreview?.snapshot_exists) {
    if (status) status.textContent = "Not run.";
    host.innerHTML = renderEmptyState(
      "No saved intake snapshot",
      "Refresh the intake snapshot to fetch current official jobs.",
      {
        eyebrow: "Observed jobs",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-run-job-preview="1">Refresh intake snapshot</button>',
      },
    );
    host.querySelector("[data-run-job-preview]")?.addEventListener("click", () => runJobScrapePreview());
  } else if (!allRows.length) {
    if (status) {
      status.textContent = `0 jobs parsed / ${formatCount(summary.sources_attempted, "0")} sources checked.`;
    }
    host.innerHTML = renderEmptyState(
      "0 parsed jobs",
      "Ready sources checked.",
      { eyebrow: "Observed jobs" },
    );
  } else if (!rows.length) {
    if (status) {
      status.textContent = `0 of ${formatCount(allRows.length, "0")} parsed jobs match the current filters.`;
    }
    host.innerHTML = renderEmptyState(
      "No jobs match",
      "Clear the job filters to return to the parsed roles.",
      {
        eyebrow: "Observed jobs",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-clear-observed-job-filters="1">Clear job filters</button>',
      },
    );
    host.querySelector("[data-clear-observed-job-filters]")?.addEventListener("click", () => {
      state.jobObservedFilter = "";
      state.jobObservedGovernance = "all";
      state.jobObservedPlatform = "all";
      state.jobObservedBand = "all";
      renderJobIntake();
    });
  } else {
    if (status) {
      status.textContent = `Showing ${formatCount(rows.length, "0")} of ${formatCount(allRows.length, "0")} saved roles across ${formatCount(summary.councils_with_jobs ?? summary.sources_with_jobs, "0")} councils; ${formatCount(summary.standard_band_1_to_8_jobs, "0")} confirmed Band 1-8, ${formatCount(summary.jobs_needing_band_review, "0")} needing band review.`;
    }
    host.innerHTML = rows.map(renderObservedJobCard).join("");
  }
  if (resultCount) {
    resultCount.textContent = state.jobScrapePreviewLoading
      ? "running"
      : `${formatCount(summary.sources_attempted, "0")} checked`;
  }
  if (resultList) {
    const sourceResults = state.jobScrapePreview?.source_results || [];
    resultList.innerHTML = sourceResults.length
      ? sourceResults.map(renderJobSourceResult).join("")
      : '<div class="muted">No source status yet.</div>';
  }
}

function renderJobHistoryPanel() {
  const host = document.getElementById("job-history-list");
  const status = document.getElementById("job-history-status");
  const metrics = document.getElementById("job-history-metrics");
  const missingCount = document.getElementById("job-history-missing-count");
  const missingList = document.getElementById("job-history-missing-list");
  if (!host) return;
  const summary = state.jobAccumulator?.summary || {};
  const coverage = state.jobAccumulator?.coverage || {};
  const rows = filteredCheckedJobRows();
  const total = checkedJobRows().length;
  if (metrics) {
    metrics.innerHTML = renderCheckedJobMetrics(summary, coverage);
  }
  if (missingCount) {
    missingCount.textContent = state.jobAccumulatorLoading
      ? "loading"
      : `${formatCount(coverage.councils_without_checked_jobs, "0")} missing`;
  }
  if (missingList) {
    const missing = Array.isArray(coverage.missing_councils) ? coverage.missing_councils : [];
    missingList.innerHTML = missing.length
      ? missing.slice(0, 79).map((row) => `
        <article class="job-source-result is-failed">
          <div>
            <strong>${escapeHtml(row.council_name || row.short_name || "Unknown council")}</strong>
            <span>${escapeHtml([jobIntakeTierLabel(row.poll_tier), "No checked classified job accumulated yet"].filter(Boolean).join(" / "))}</span>
          </div>
        </article>
      `).join("")
      : '<div class="muted">Every council has at least one checked classified job in the accumulator.</div>';
  }
  if (state.jobAccumulatorLoading) {
    if (status) status.textContent = "Loading checked job accumulator...";
    host.innerHTML = renderEmptyState("Loading checked jobs", "Reading the accumulated classified job ledger.", { eyebrow: "Checked jobs" });
    return;
  }
  if (!state.jobAccumulatorStarted && !state.jobAccumulator) {
    if (status) status.textContent = "Not loaded.";
    host.innerHTML = renderEmptyState(
      "Checked jobs not loaded",
      "Load the accumulator or run a broader refresh to begin building history.",
      {
        eyebrow: "Checked jobs",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-load-job-history="1">Load checked jobs</button>',
      },
    );
    host.querySelector("[data-load-job-history]")?.addEventListener("click", () => {
      state.jobAccumulatorStarted = true;
      ensureJobAccumulator({ force: true }).then(() => renderJobHistoryPanel());
    });
    return;
  }
  if (!total) {
    if (status) status.textContent = "0 checked classified jobs accumulated.";
    host.innerHTML = renderEmptyState(
      "No checked jobs accumulated",
      "Accumulate the saved snapshot or run an aggressive refresh to keep classified Band 1-8 jobs.",
      { eyebrow: "Checked jobs" },
    );
    return;
  }
  if (!rows.length) {
    if (status) status.textContent = `0 of ${formatCount(total, "0")} checked jobs match the filter.`;
    host.innerHTML = renderEmptyState(
      "No checked jobs match",
      "Clear the checked-job search to return to the accumulated ledger.",
      {
        eyebrow: "Checked jobs",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-clear-job-history-filter="1">Clear search</button>',
      },
    );
    host.querySelector("[data-clear-job-history-filter]")?.addEventListener("click", () => {
      state.jobAccumulatorFilter = "";
      const filter = document.getElementById("job-history-filter");
      if (filter) filter.value = "";
      renderJobHistoryPanel();
    });
    return;
  }
  if (status) {
    status.textContent = `Showing ${formatCount(rows.length, "0")} of ${formatCount(total, "0")} checked jobs; ${formatCount(coverage.councils_with_checked_jobs, "0")} of ${formatCount(coverage.target_councils, "0")} councils covered.`;
  }
  host.innerHTML = rows.map(renderCheckedJobCard).join("");
}

function renderCheckedJobMetrics(summary, coverage) {
  const items = [
    ["Checked jobs", formatCount(summary.checked_classified_jobs ?? summary.jobs, "0")],
    ["Council coverage", `${formatCount(coverage.councils_with_checked_jobs, "0")}/${formatCount(coverage.target_councils, "0")}`],
    ["Coverage rate", `${formatCount(coverage.coverage_rate, "0")}%`],
    ["Reference months", formatCount(summary.reference_months, "0")],
    ["Current official", formatCount(summary.current_official_jobs, "0")],
    ["Historical", formatCount(summary.historical_jobs, "0")],
  ];
  return items.map(([label, value]) => `
    <article class="job-history-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `).join("");
}

function renderCheckedJobCard(row) {
  const latest = row.latest_job || {};
  const posted = formatJobDate(latest.posted_at || latest.posted_at_text);
  const closes = formatJobDate(latest.closing_at || latest.closing_at_text);
  const salary = formatJobSalary(latest);
  const confidence = row.classification_confidence === "inferred" ? "Band inferred" : "Band confirmed";
  const status = row.observed_status === "historical_not_seen_latest" ? "Historical" : (row.observed_status === "secondary_signal" ? "Secondary" : "Current");
  const meta = [
    row.short_name || row.council_name,
    row.classification_band || (row.standard_band_number ? `Band ${row.standard_band_number}` : ""),
    row.canonical_reference_month,
    confidence,
    salary,
    closes ? `Closes ${closes}` : "",
    `${formatCount(row.sighting_count, "1")} sighting${Number(row.sighting_count || 1) === 1 ? "" : "s"}`,
  ];
  return `
    <article class="job-observed-card job-history-card job-history-${escapeHtml(row.observed_status || "current")}">
      <div class="job-observed-row">
        <div class="job-observed-title">
          <span class="job-governance-chip">${escapeHtml(status)}</span>
          <div>
            <h4>${escapeHtml(row.job_title || "Untitled checked job")}</h4>
            ${renderInlineMeta(meta, "job-intake-meta workbench-inline-meta")}
          </div>
        </div>
        <a href="${escapeHtml(row.job_url || latest.job_url || "#")}" target="_blank" rel="noreferrer">Open</a>
      </div>
      <details class="job-observed-detail">
        <summary><span>Accumulation detail</span><strong>${escapeHtml([row.council_name, row.canonical_reference_month, row.source_family].filter(Boolean).join(" | "))}</strong></summary>
        <div class="job-observed-detail-grid">
          ${renderJobFact("Council", row.council_name || row.short_name || "Not parsed")}
          ${renderJobFact("Band", row.classification_band || (row.standard_band_number ? `Band ${row.standard_band_number}` : "Not parsed"))}
          ${renderJobFact("Reference month", row.canonical_reference_month || "Not parsed")}
          ${renderJobFact("Classification", confidence)}
          ${renderJobFact("Posted", posted || "Not parsed")}
          ${renderJobFact("Closes", closes || "Not parsed")}
          ${renderJobFact("First seen", formatJobDateTime(row.first_seen_at))}
          ${renderJobFact("Last seen", formatJobDateTime(row.last_seen_at))}
          ${renderJobFact("Sources", (row.source_labels_seen || []).join(", ") || row.source_name || "Not parsed")}
          ${renderJobFact("Dedupe", "council + title + band + month")}
        </div>
      </details>
    </article>
  `;
}

function renderJobGovernancePanel() {
  const host = document.getElementById("job-governance-list");
  const status = document.getElementById("job-governance-status");
  if (!host) return;
  const rows = observedJobRows();
  const summary = state.jobScrapePreview?.summary || {};
  if (!rows.length) {
    if (status) status.textContent = "Run the preview scrape to populate governance groups.";
    host.innerHTML = renderEmptyState("No governance rows", "Parsed job governance appears after scraping.", { eyebrow: "Governance" });
    return;
  }
  if (status) {
    status.textContent = `${formatCount(summary.pay_table_rows_available, "0")} governed pay-table rows available for salary enrichment.`;
  }
  const groups = [
    {
      key: "auto_included",
      title: "Confirmed Band 1-8",
      note: "Band evidence was found in the job record.",
    },
    {
      key: "needs_band_confirmation",
      title: "Band Inferred",
      note: "Salary mapped to one governed band, but the source did not state the band.",
    },
    {
      key: "needs_band_review",
      title: "Needs Band Review",
      note: "The source did not expose enough band or salary evidence yet.",
    },
  ];
  host.innerHTML = groups.map((group) => {
    const count = rows.filter((job) => job.governance_status === group.key).length;
    return `
      <button class="job-governance-group" type="button" data-job-governance-group="${escapeHtml(group.key)}">
        <strong>${escapeHtml(formatCount(count, "0"))}</strong>
        <span>${escapeHtml(group.title)}</span>
        <small>${escapeHtml(group.note)}</small>
      </button>
    `;
  }).join("");
  host.querySelectorAll("[data-job-governance-group]").forEach((button) => {
    button.addEventListener("click", () => {
      state.jobObservedGovernance = button.dataset.jobGovernanceGroup || "all";
      state.jobIntakeTab = "jobs";
      renderJobIntake();
    });
  });
}

function renderJobCompletionPanel() {
  const host = document.getElementById("job-completion-list");
  const status = document.getElementById("job-completion-status");
  const button = document.getElementById("job-completion-enrich");
  if (!host) return;
  const rows = observedJobRows();
  const summary = state.jobScrapePreview?.summary || {};
  const actions = Array.isArray(state.jobScrapePreview?.completion_actions)
    ? state.jobScrapePreview.completion_actions
    : [];
  if (button) {
    button.disabled = state.jobScrapePreviewLoading;
    button.textContent = state.jobScrapePreviewLoading ? "Running..." : "Run document pass";
  }
  if (state.jobScrapePreviewLoading) {
    if (status) status.textContent = state.jobScrapePreviewLinkedDocuments ? "Mining linked documents..." : "Refreshing completion state...";
    host.innerHTML = renderEmptyState("Completion pass running", "Checking official sources and linked evidence.", { eyebrow: "Completion" });
    return;
  }
  if (!rows.length) {
    if (status) status.textContent = "Run the preview scrape to classify completion actions.";
    host.innerHTML = renderEmptyState("No completion actions yet", "Parsed jobs will be grouped by the next action that can make them governed.", { eyebrow: "Completion" });
    return;
  }
  if (status) {
    status.textContent = `${formatCount(summary.standard_band_1_to_8_jobs, "0")} governed / ${formatCount(summary.jobs, "0")} parsed roles; ${formatCount(summary.band_completion_rate, "0")}% band completion.`;
  }
  host.innerHTML = actions.length
    ? actions.map((action) => renderCompletionActionCard(action, rows)).join("")
    : renderEmptyState("No completion buckets", "The scrape payload did not include completion actions.", { eyebrow: "Completion" });
  host.querySelectorAll("[data-completion-open-action]").forEach((control) => {
    control.addEventListener("click", () => {
      state.jobObservedFilter = control.dataset.completionOpenAction || "";
      state.jobIntakeTab = "jobs";
      renderJobIntake();
    });
  });
  host.querySelectorAll("[data-completion-document-pass]").forEach((control) => {
    control.addEventListener("click", () => runJobScrapePreview({ enrichAttachments: true }));
  });
}

function renderCompletionActionCard(action, rows) {
  const actionId = action.action_id || "";
  const jobs = rows.filter((job) => job.completion_action === actionId);
  const examples = jobs.slice(0, 6);
  const actionButton = actionId === "parse_linked_documents"
    ? '<button type="button" data-completion-document-pass="1">Run document pass</button>'
    : `<button type="button" data-completion-open-action="${escapeHtml(actionId)}">Show jobs</button>`;
  return `
    <article class="job-observed-card job-completion-card">
      <div class="job-observed-row">
        <div class="job-observed-title">
          <span class="job-governance-chip">${escapeHtml(formatCount(action.count, "0"))}</span>
          <div>
            <h4>${escapeHtml(action.label || displayCodeLabel(actionId))}</h4>
            <p>${escapeHtml(action.description || "")}</p>
          </div>
        </div>
        ${actionButton}
      </div>
      <details class="job-observed-detail">
        <summary><span>Jobs in this bucket</span><strong>${escapeHtml(formatCount(jobs.length, "0"))}</strong></summary>
        <div class="job-source-result-list">
          ${examples.length ? examples.map(renderCompletionExample).join("") : '<div class="muted">No examples in the current row set.</div>'}
        </div>
      </details>
    </article>
  `;
}

function renderCompletionExample(job) {
  const meta = [
    job.council_name || job.short_name,
    job.classification_band || job.inferred_classification_band || "Band missing",
    formatJobSalary(job) || "Salary missing",
    job.completion_reason,
  ];
  return `
    <article class="job-source-result is-ok">
      <div>
        <strong>${escapeHtml(job.job_title || "Untitled job")}</strong>
        <span>${escapeHtml(meta.filter(Boolean).join(" / "))}</span>
      </div>
      <a href="${escapeHtml(job.job_url || "#")}" target="_blank" rel="noreferrer">Open</a>
    </article>
  `;
}

function renderJobSecondaryPanel() {
  const host = document.getElementById("job-secondary-list");
  const status = document.getElementById("job-secondary-status");
  const resultCount = document.getElementById("job-secondary-result-count");
  const sourceList = document.getElementById("job-secondary-source-list");
  if (!host) return;
  const summary = state.jobSecondaryPreview?.summary || {};
  if (state.jobSecondaryPreviewLoading) {
    if (status) status.textContent = "Checking secondary sources...";
    host.innerHTML = renderEmptyState("Checking secondary sources", "Fetching sector aggregator signals.", { eyebrow: "Secondary" });
  } else if (!state.jobSecondaryPreviewStarted && !state.jobSecondaryPreview) {
    if (status) status.textContent = "Not run.";
    host.innerHTML = renderEmptyState(
      "No secondary signals loaded",
      "Refresh secondary sources to compare aggregator listings against official council jobs.",
      {
        eyebrow: "Secondary",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-run-secondary-preview="1">Refresh secondary sources</button>',
      },
    );
    host.querySelector("[data-run-secondary-preview]")?.addEventListener("click", () => runJobSecondaryPreview());
  } else {
    const rows = secondaryJobRows();
  if (status) {
      const classified = summary.classified_band_1_to_8_jobs ?? summary.standard_band_1_to_8_jobs;
      status.textContent = `${formatCount(rows.length, "0")} secondary roles from ${formatCount(summary.sources_with_jobs, "0")} source${summary.sources_with_jobs === 1 ? "" : "s"}; ${formatCount(classified, "0")} classified Band 1-8.`;
  }
    host.innerHTML = rows.length
      ? rows.map(renderSecondaryJobCard).join("")
      : renderEmptyState("No secondary jobs parsed", "Secondary sources were checked but no job cards were extracted.", { eyebrow: "Secondary" });
  }
  if (resultCount) {
    resultCount.textContent = state.jobSecondaryPreviewLoading
      ? "running"
      : `${formatCount(summary.sources_attempted, "0")} checked`;
  }
  if (sourceList) {
    const sourceResults = state.jobSecondaryPreview?.source_results || [];
    sourceList.innerHTML = sourceResults.length
      ? sourceResults.map(renderJobSourceResult).join("")
      : '<div class="muted">No secondary source status yet.</div>';
  }
}

function renderSecondaryJobCard(job) {
  const match = secondaryOfficialMatch(job);
  const meta = [
    job.source_name,
    job.council_name || "Council not parsed",
    job.work_type,
    job.location_text,
    job.classification_band || (job.inferred_classification_band ? `${job.inferred_classification_band} inferred` : ""),
    formatJobSalary(job),
    job.closing_at ? `Closes ${formatJobDate(job.closing_at)}` : "",
  ].filter(Boolean);
  return `
    <article class="job-observed-card job-secondary-card">
      <div class="job-observed-row">
        <div class="job-observed-title">
          <span class="job-governance-chip">${escapeHtml(match.label)}</span>
          <div>
            <h4>${escapeHtml(job.job_title || "Untitled secondary role")}</h4>
            ${renderInlineMeta(meta, "job-intake-meta workbench-inline-meta")}
          </div>
        </div>
        <a href="${escapeHtml(job.job_url || "#")}" target="_blank" rel="noreferrer">Open</a>
      </div>
      <details class="job-observed-detail">
        <summary><span>Signal detail</span><strong>${escapeHtml(match.detail)}</strong></summary>
        <div class="job-observed-detail-grid">
          ${renderJobFact("Source", job.source_name || "Secondary")}
          ${renderJobFact("Council", job.council_name || "Not parsed")}
          ${renderJobFact("Posted", formatJobDate(job.posted_at || job.posted_at_text) || "Not parsed")}
          ${renderJobFact("Closes", formatJobDate(job.closing_at || job.closing_at_text) || "Not parsed")}
          ${renderJobFact("Band", job.classification_band || job.inferred_classification_band || "Not parsed")}
          ${renderJobFact("Advertised salary", formatJobSalary(job) || job.salary_text || "Not parsed")}
          ${renderJobFact("Official match", match.label)}
          ${renderJobFact("Role", job.source_role || "secondary_signal")}
        </div>
      </details>
    </article>
  `;
}

function secondaryOfficialMatch(job) {
  const secondaryTitle = normalizeJobMatchText(job.job_title);
  const secondaryCouncil = normalizeJobMatchText(job.council_name);
  if (!secondaryTitle) return { label: "Review", detail: "Secondary role title was not parsed." };
  const official = observedJobRows().find((row) => {
    const sameTitle = normalizeJobMatchText(row.job_title) === secondaryTitle;
    const officialCouncil = normalizeJobMatchText(row.council_name || row.short_name);
    const sameCouncil = secondaryCouncil && officialCouncil && (
      officialCouncil.includes(secondaryCouncil) || secondaryCouncil.includes(officialCouncil)
    );
    return sameTitle && sameCouncil;
  });
  if (official) {
    return { label: "Matched", detail: `Matches official ${official.short_name || official.council_name || "council"} record.` };
  }
  if (!secondaryCouncil) {
    return { label: "Review", detail: "Secondary source did not expose a council name for automatic matching." };
  }
  return { label: "Gap check", detail: "No same-title official record is currently visible in the parsed jobs list." };
}

function normalizeJobMatchText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\b(city|shire|rural|borough|council|city council|shire council)\b/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function renderJobResolutionCard(source) {
  const meta = [
    jobIntakeTierLabel(source.poll_tier),
    jobIntakePlatformLabel(source.platform_family),
    `${formatCount(source.parsed_jobs, "0")} parsed`,
    source.candidate_pattern_id ? displayCodeLabel(source.candidate_pattern_id) : "",
  ];
  return `
    <article class="job-resolution-card">
      <div>
        <strong>${escapeHtml(source.council_name || source.short_name || "Unknown source")}</strong>
        ${renderInlineMeta(meta, "job-intake-meta workbench-inline-meta")}
      </div>
      <a href="${escapeHtml(source.listing_url || "#")}" target="_blank" rel="noreferrer">Open</a>
    </article>
  `;
}

function renderJobEndpointResolution() {
  const host = document.getElementById("job-resolution-list");
  const status = document.getElementById("job-resolution-status");
  const button = document.getElementById("job-resolution-refresh");
  if (!host) return;
  const summary = state.jobEndpointResolution?.summary || {};
  const rows = state.jobEndpointResolution?.resolved_sources || [];
  const queueCount = Number(state.jobSourceRegistry?.summary?.needs_endpoint_discovery || 0);
  if (button) {
    button.disabled = queueCount === 0 || state.jobEndpointResolutionLoading;
    button.textContent = queueCount === 0 ? "All endpoints ready" : "Probe endpoint patterns";
  }
  if (queueCount === 0 && !state.jobEndpointResolutionLoading) {
    if (status) status.textContent = "All councils have verified endpoints.";
    host.innerHTML = renderEmptyState(
      "No endpoint queue",
      "Ready sources are feeding the scrape preview.",
      { eyebrow: "Endpoint resolution" },
    );
    return;
  }
  if (state.jobEndpointResolutionLoading) {
    if (status) status.textContent = "Probing generated endpoint patterns...";
    host.innerHTML = renderEmptyState("Probing patterns", "Checking generated official-source candidates.", { eyebrow: "Endpoint resolution" });
    return;
  }
  if (!state.jobEndpointResolutionStarted && !state.jobEndpointResolution) {
    if (status) status.textContent = "Pattern probe idle.";
    host.innerHTML = renderEmptyState(
      "Pattern probe ready",
      "Run the resolver to check generated official-source candidates.",
      {
        eyebrow: "Endpoint resolution",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-run-job-resolution="1">Probe endpoint patterns</button>',
      },
    );
    host.querySelector("[data-run-job-resolution]")?.addEventListener("click", () => runJobEndpointResolution());
    return;
  }
  if (status) {
    status.textContent = `${formatCount(summary.sources_resolved, "0")} source${summary.sources_resolved === 1 ? "" : "s"} resolved from ${formatCount(summary.candidates_checked, "0")} pattern probe${summary.candidates_checked === 1 ? "" : "s"}.`;
  }
  host.innerHTML = rows.length
    ? rows.map(renderJobResolutionCard).join("")
    : renderEmptyState("0 pattern matches", "Resolver checked the generated candidates.", { eyebrow: "Endpoint resolution" });
}

function runJobEndpointResolution() {
  state.jobEndpointResolutionStarted = true;
  renderJobEndpointResolution();
  return ensureJobEndpointResolution({ force: true })
    .then(() => renderJobEndpointResolution())
    .catch((error) => {
      const status = document.getElementById("job-resolution-status");
      if (status) status.textContent = `Resolution probe needs attention: ${apiErrorMessage(error)}`;
      toast(`Endpoint resolution needs attention: ${apiErrorMessage(error)}`, "error");
      renderJobEndpointResolution();
    });
}

function runJobScrapePreview({ enrichAttachments = false } = {}) {
  state.jobScrapePreviewStarted = true;
  state.jobScrapePreviewLinkedDocuments = enrichAttachments;
  renderObservedJobs();
  renderJobIntakeMetrics();
  return ensureJobScrapePreview({ force: true, enrichAttachments })
    .then(() => renderJobIntake())
    .catch((error) => {
      const status = document.getElementById("job-observed-status");
      if (status) status.textContent = `Preview needs attention: ${apiErrorMessage(error)}`;
      toast(`Job preview needs attention: ${apiErrorMessage(error)}`, "error");
      renderObservedJobs();
    });
}

function runJobSecondaryPreview() {
  state.jobSecondaryPreviewStarted = true;
  renderJobSecondaryPanel();
  return ensureJobSecondaryPreview({ force: true })
    .then(() => renderJobIntake())
    .catch((error) => {
      const status = document.getElementById("job-secondary-status");
      if (status) status.textContent = `Secondary preview needs attention: ${apiErrorMessage(error)}`;
      toast(`Secondary preview needs attention: ${apiErrorMessage(error)}`, "error");
      renderJobSecondaryPanel();
    });
}

function runJobAccumulatorIngest() {
  state.jobAccumulatorStarted = true;
  renderJobHistoryPanel();
  return api("/api/job-intake/accumulator/ingest-snapshot", { method: "POST" })
    .then((payload) => {
      state.jobAccumulator = payload;
      renderJobIntake();
      toast("Saved snapshot accumulated into checked jobs.", "success");
      return payload;
    })
    .catch((error) => {
      const status = document.getElementById("job-history-status");
      if (status) status.textContent = `Accumulator needs attention: ${apiErrorMessage(error)}`;
      toast(`Checked job accumulation failed: ${apiErrorMessage(error)}`, "error");
      renderJobHistoryPanel();
      throw error;
    });
}

function runJobAccumulatorRefresh() {
  state.jobAccumulatorStarted = true;
  state.jobAccumulatorLoading = Promise.resolve();
  renderJobHistoryPanel();
  const params = new URLSearchParams({
    source_limit: "0",
    job_limit: "0",
    timeout: "12",
    enrich_pay_tables: "true",
    enrich_details: "true",
    detail_job_limit: "1000",
    enrich_attachments: "false",
    attachment_job_limit: "1000",
    resolve_missing_documents: "true",
    include_secondary: "true",
    secondary_job_limit: "0",
    wide_fetch: "true",
    candidate_limit_per_council: "20",
    candidate_priority_limit: "3",
  });
  state.jobAccumulatorLoading = api(`/api/job-intake/accumulator/refresh?${params.toString()}`, { method: "POST" })
    .then((payload) => {
      state.jobAccumulator = payload;
      state.jobScrapePreview = null;
      state.jobPipelineStage1 = null;
      toast("Aggressive job refresh accumulated checked classified jobs.", "success");
      return ensureJobScrapePreview().catch(() => null).then(() => payload);
    })
    .then((payload) => {
      renderJobIntake();
      return payload;
    })
    .catch((error) => {
      const status = document.getElementById("job-history-status");
      if (status) status.textContent = `Aggressive refresh needs attention: ${apiErrorMessage(error)}`;
      toast(`Aggressive checked-job refresh failed: ${apiErrorMessage(error)}`, "error");
      renderJobHistoryPanel();
      throw error;
    })
    .finally(() => {
      state.jobAccumulatorLoading = null;
    });
  return state.jobAccumulatorLoading;
}

function renderJobIntakeRow(row) {
  const status = row.monitoring_status || "unknown";
  const url = row.listing_url || row.official_careers_entry_url || "";
  const endpointCandidates = Array.isArray(row.endpoint_candidates) ? row.endpoint_candidates : [];
  const meta = [
    jobIntakeTierLabel(row.poll_tier),
    row.suggested_cadence_label,
    jobIntakePlatformLabel(row.platform_family),
    row.adapter,
    row.listing_url_confidence === "verified_deep_endpoint" ? "Verified endpoint" : "Directory entry",
  ];
  const compliance = [
    `Robots ${displayCodeLabel(row.robots_status || "not_checked")}`,
    `Terms ${displayCodeLabel(row.terms_review_status || "not_checked")}`,
  ];
  return `
    <article class="job-intake-card job-intake-${escapeHtml(status)}">
      <div class="job-intake-card-main">
        <div class="job-intake-card-title">
          <span class="job-tier-pill job-tier-${escapeHtml(row.poll_tier || "C")}">${escapeHtml(jobIntakeTierLabel(row.poll_tier))}</span>
          <div>
            <h3>${escapeHtml(row.council_name || row.short_name)}</h3>
            ${renderInlineMeta(meta, "job-intake-meta workbench-inline-meta")}
          </div>
        </div>
        <div class="job-intake-endpoint">
          <span>${escapeHtml(url || "Endpoint missing")}</span>
          ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">Open</a>` : ""}
        </div>
        ${endpointCandidates.length ? `
          <div class="job-intake-endpoint-candidates">
            ${endpointCandidates.map((candidate) => `
              <a href="${escapeHtml(candidate.listing_url || "#")}" target="_blank" rel="noreferrer">
                ${escapeHtml(jobIntakePlatformLabel(candidate.platform_family))} pattern
              </a>
            `).join("")}
          </div>
        ` : ""}
        ${renderInlineMeta(compliance, "job-intake-compliance workbench-inline-meta")}
        ${row.notes ? `<p>${escapeHtml(row.notes)}</p>` : ""}
      </div>
      <div class="job-intake-status-cell">
        <strong>${escapeHtml(jobIntakeStatusLabel(status))}</strong>
        <span>${escapeHtml(displayCodeLabel(row.council_grouping || ""))}</span>
      </div>
    </article>
  `;
}

function renderJobIntakeList() {
  const list = document.getElementById("job-intake-list");
  const status = document.getElementById("job-intake-source-note");
  if (!list) return;
  const rows = filteredJobIntakeRows();
  const total = jobIntakeRows().length;
  if (status) {
    status.textContent = `Showing ${formatCount(rows.length, "0")} of ${formatCount(total, "0")} council job sources`;
  }
  if (!rows.length) {
    list.innerHTML = renderEmptyState(
      "No job sources match the current filters",
      "Clear the job-source filters to return to the full registry.",
      {
        eyebrow: "Job intake",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-job-intake-clear="1">Clear job filters</button>',
      },
    );
    list.querySelector("[data-job-intake-clear]")?.addEventListener("click", () => {
      clearJobIntakeFilters();
      renderJobIntake();
    });
    return;
  }
  list.innerHTML = rows.map(renderJobIntakeRow).join("");
}

function renderJobIntake({ force = false } = {}) {
  const list = document.getElementById("job-intake-list");
  if (!list) return;
  if (!state.jobSourceRegistry || force) {
    setText("job-intake-status-note", "Loading source registry...");
    if (force) state.jobSourceRegistry = null;
    list.innerHTML = renderEmptyState("Loading job sources", "Fetching council job-source registry.", { eyebrow: "Job intake" });
    ensureJobSourceRegistry({ force })
      .then(() => renderJobIntake())
      .catch((error) => {
        setText("job-intake-status-note", `Job source registry failed: ${apiErrorMessage(error)}`);
        list.innerHTML = renderEmptyState("Job source registry unavailable", apiErrorMessage(error), { eyebrow: "Job intake" });
      });
    return;
  }
  const filter = document.getElementById("job-intake-filter");
  const tier = document.getElementById("job-intake-tier");
  const statusSelect = document.getElementById("job-intake-status");
  const platformSelect = document.getElementById("job-intake-platform");
  const jobFilter = document.getElementById("job-observed-filter");
  const jobGovernance = document.getElementById("job-observed-governance");
  const jobPlatform = document.getElementById("job-observed-platform");
  const jobBand = document.getElementById("job-observed-band");
  const historyFilter = document.getElementById("job-history-filter");
  if (filter) filter.value = state.jobIntakeFilter;
  if (tier) tier.value = state.jobIntakeTier;
  if (statusSelect) statusSelect.value = state.jobIntakeStatus;
  if (platformSelect) platformSelect.value = state.jobIntakePlatform;
  if (jobFilter) jobFilter.value = state.jobObservedFilter;
  if (jobGovernance) jobGovernance.value = state.jobObservedGovernance;
  if (jobPlatform) jobPlatform.value = state.jobObservedPlatform;
  if (jobBand) jobBand.value = state.jobObservedBand;
  if (historyFilter) historyFilter.value = state.jobAccumulatorFilter;
  updateJobIntakePlatformSelect();
  renderJobIntakeTabs();
  renderJobIntakeMetrics();
  renderJobIntakeTierExplainer();
  renderJobIntakePlatformMix();
  renderJobIntakeSourceLists();
  renderObservedJobs();
  renderJobHistoryPanel();
  renderJobCompletionPanel();
  renderJobGovernancePanel();
  renderJobSecondaryPanel();
  renderJobEndpointResolution();
  renderJobIntakeList();
  if (!state.jobScrapePreview && !state.jobScrapePreviewLoading && !state.jobScrapePreviewStarted) {
    state.jobScrapePreviewStarted = true;
    ensureJobScrapePreview()
      .then(() => renderJobIntake())
      .catch((error) => {
        const status = document.getElementById("job-observed-status");
        if (status) status.textContent = `Scrape preview failed: ${apiErrorMessage(error)}`;
        renderObservedJobs();
      });
  }
  const hasEndpointQueue = Number(state.jobSourceRegistry?.summary?.needs_endpoint_discovery || 0) > 0;
  if (hasEndpointQueue && !state.jobEndpointResolution && !state.jobEndpointResolutionLoading && !state.jobEndpointResolutionStarted) {
    state.jobEndpointResolutionStarted = true;
    ensureJobEndpointResolution()
      .then(() => renderJobEndpointResolution())
      .catch((error) => {
        const status = document.getElementById("job-resolution-status");
        if (status) status.textContent = `Resolution probe needs attention: ${apiErrorMessage(error)}`;
        renderJobEndpointResolution();
      });
  }
  if (state.jobIntakeTab === "secondary" && !state.jobSecondaryPreview && !state.jobSecondaryPreviewLoading && !state.jobSecondaryPreviewStarted) {
    state.jobSecondaryPreviewStarted = true;
    ensureJobSecondaryPreview()
      .then(() => renderJobSecondaryPanel())
      .catch((error) => {
        const status = document.getElementById("job-secondary-status");
        if (status) status.textContent = `Secondary preview failed: ${apiErrorMessage(error)}`;
        renderJobSecondaryPanel();
      });
  }
  if (state.jobIntakeTab === "history" && !state.jobAccumulator && !state.jobAccumulatorLoading && !state.jobAccumulatorStarted) {
    state.jobAccumulatorStarted = true;
    ensureJobAccumulator()
      .then(() => renderJobHistoryPanel())
      .catch((error) => {
        const status = document.getElementById("job-history-status");
        if (status) status.textContent = `Checked jobs failed: ${apiErrorMessage(error)}`;
        renderJobHistoryPanel();
      });
  }
}

function renderJobPipeline() {
  const list = document.getElementById("job-pipeline-list");
  if (!list) return;
  if (!state.jobPipelineStage1 && !state.jobPipelineStage1Loading) {
    list.innerHTML = renderEmptyState("Loading Stage 1", "Reading the saved intake snapshot.", { eyebrow: "Job pipeline" });
    ensureJobPipelineStage1()
      .then(() => renderJobPipeline())
      .catch((error) => {
        setText("job-pipeline-status-note", `Stage 1 could not load: ${apiErrorMessage(error)}`);
        list.innerHTML = renderEmptyState("Stage 1 unavailable", apiErrorMessage(error), { eyebrow: "Job pipeline" });
      });
    return;
  }
  const filter = document.getElementById("job-pipeline-filter");
  const statusSelect = document.getElementById("job-pipeline-status");
  if (filter) filter.value = state.jobPipelineFilter;
  if (statusSelect) statusSelect.value = state.jobPipelineStatus;
  renderJobPipelineMetrics();
  renderJobPipelineRule();
  renderJobPipelineMissingFields();
  renderJobPipelineList();
}

function renderJobPipelineMetrics() {
  const summary = state.jobPipelineStage1?.summary || {};
  setText("job-pipeline-stage1-count", state.jobPipelineStage1Loading ? "..." : formatCount(summary.governed_input_jobs, "0"));
  setText("job-pipeline-ready-count", formatCount(summary.stage1_ready_jobs, "0"));
  setText("job-pipeline-fill-count", formatCount(summary.stage1_fill_required_jobs, "0"));
  setText("job-pipeline-required-rate", `${formatCount(summary.required_completion_rate, "0")}%`);
  setText("job-pipeline-optional-rate", `${formatCount(summary.optional_completion_rate, "0")}%`);
  if (document.body.dataset.view === "job-pipeline") {
    setText(
      "header-stats",
      `${formatCount(summary.governed_input_jobs, "0")} Stage 1 | ${formatCount(summary.stage1_ready_jobs, "0")} ready | ${formatCount(summary.stage1_fill_required_jobs, "0")} fill`,
    );
  }
}

function renderJobPipelineRule() {
  const host = document.getElementById("job-pipeline-rule");
  if (!host) return;
  const policy = state.jobPipelineStage1?.stage_policy || {};
  const savedAt = formatJobDateTime(state.jobPipelineStage1?.snapshot_saved_at);
  host.innerHTML = `
    <div class="job-pipeline-rule-row">
      <strong>Entry</strong>
      <span>${escapeHtml(policy.entry_rule || "Band-governed jobs only.")}</span>
    </div>
    <div class="job-pipeline-rule-row">
      <strong>Stage 1</strong>
      <span>${escapeHtml(policy.stage_1_goal || "Complete required and optional fields.")}</span>
    </div>
    <div class="job-pipeline-rule-row">
      <strong>Snapshot</strong>
      <span>${escapeHtml(state.jobPipelineStage1?.snapshot_exists ? savedAt : "No saved snapshot")}</span>
    </div>
  `;
}

function renderJobPipelineMissingFields() {
  const host = document.getElementById("job-pipeline-missing-list");
  if (!host) return;
  const fields = state.jobPipelineStage1?.summary?.top_missing_required_fields || [];
  if (!fields.length) {
    host.innerHTML = '<div class="muted">No compulsory field gaps in Stage 1.</div>';
    return;
  }
  host.innerHTML = fields.map((field) => `
    <button class="job-intake-source-card" type="button" data-job-pipeline-missing="${escapeHtml(field.field)}">
      <strong>${escapeHtml(pipelineFieldLabel(field.field))}</strong>
      <span>${escapeHtml(formatCount(field.count, "0"))} job${field.count === 1 ? "" : "s"}</span>
    </button>
  `).join("");
  host.querySelectorAll("[data-job-pipeline-missing]").forEach((button) => {
    button.addEventListener("click", () => {
      state.jobPipelineFilter = button.dataset.jobPipelineMissing || "";
      const filter = document.getElementById("job-pipeline-filter");
      if (filter) filter.value = state.jobPipelineFilter;
      renderJobPipeline();
    });
  });
}

function renderJobPipelineList() {
  const host = document.getElementById("job-pipeline-list");
  const status = document.getElementById("job-pipeline-status-note");
  if (!host) return;
  if (state.jobPipelineStage1Loading) {
    if (status) status.textContent = "Loading Stage 1 from the saved intake snapshot.";
    host.innerHTML = renderEmptyState("Loading Stage 1", "Reading governed job rows.", { eyebrow: "Job pipeline" });
    return;
  }
  if (!state.jobPipelineStage1?.snapshot_exists) {
    if (status) status.textContent = "No saved intake snapshot yet.";
    host.innerHTML = renderEmptyState(
      "No saved intake snapshot",
      "Refresh the intake snapshot first, then Stage 1 will admit Band-governed jobs.",
      {
        eyebrow: "Job pipeline",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-open-job-intake="1">Open job intake</button>',
      },
    );
    host.querySelector("[data-open-job-intake]")?.addEventListener("click", () => switchView("job-intake"));
    return;
  }
  const rows = filteredJobPipelineRows();
  const total = jobPipelineRows().length;
  if (!total) {
    if (status) status.textContent = "The saved snapshot has no Band-governed jobs ready for Stage 1.";
    host.innerHTML = renderEmptyState("No Stage 1 jobs", "Band-governed rows from intake will appear here.", { eyebrow: "Job pipeline" });
    return;
  }
  if (!rows.length) {
    if (status) status.textContent = `0 of ${formatCount(total, "0")} Stage 1 jobs match the current filters.`;
    host.innerHTML = renderEmptyState(
      "No Stage 1 jobs match",
      "Clear the pipeline filters to return to the governed jobs.",
      {
        eyebrow: "Job pipeline",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-clear-job-pipeline="1">Clear pipeline filters</button>',
      },
    );
    host.querySelector("[data-clear-job-pipeline]")?.addEventListener("click", () => {
      state.jobPipelineFilter = "";
      state.jobPipelineStatus = "all";
      renderJobPipeline();
    });
    return;
  }
  if (status) {
    const summary = state.jobPipelineStage1?.summary || {};
    status.textContent = `Showing ${formatCount(rows.length, "0")} of ${formatCount(total, "0")} Stage 1 jobs; ${formatCount(summary.required_completion_rate, "0")}% compulsory field completion.`;
  }
  host.innerHTML = rows.map(renderJobPipelineCard).join("");
}

function renderJobPipelineCard(row) {
  const status = row.stage1_status || "stage1_fill_required";
  const required = `${formatCount(row.required_fields_present, "0")}/${formatCount(row.required_fields_total, "0")} required`;
  const optional = `${formatCount(row.optional_fields_present, "0")}/${formatCount(row.optional_fields_total, "0")} optional`;
  const missingRequired = (row.missing_required_fields || []).map(pipelineFieldLabel);
  const missingOptional = (row.missing_optional_fields || []).map(pipelineFieldLabel);
  const meta = [
    row.council_name || row.short_name,
    row.source_family ? jobIntakePlatformLabel(row.source_family) : "",
    row.classification_band,
    row.canonical_reference_month ? `Ref ${row.canonical_reference_month}` : "",
    row.closing_at ? `Closes ${formatJobDate(row.closing_at)}` : "",
    formatJobSalary(row),
    formatEnterpriseAgreementJobSalary(row) ? `EA ${formatEnterpriseAgreementJobSalary(row)}` : "",
  ].filter(Boolean);
  return `
    <article class="job-pipeline-card job-pipeline-${escapeHtml(status)}">
      <div class="job-observed-row">
        <div class="job-observed-title">
          <span class="job-governance-chip">${escapeHtml(status === "stage1_ready" ? "Stage 1 ready" : "Fill fields")}</span>
          <div>
            <h4>${escapeHtml(row.job_title || "Untitled job")}</h4>
            ${renderInlineMeta(meta, "job-intake-meta workbench-inline-meta")}
          </div>
        </div>
        <a href="${escapeHtml(row.canonical_url || row.job_url || "#")}" target="_blank" rel="noreferrer">Open</a>
      </div>
      <details class="job-observed-detail" ${missingRequired.length ? "open" : ""}>
        <summary><span>Field completion</span><strong>${escapeHtml(`${required} | ${optional}`)}</strong></summary>
        <div class="job-observed-detail-grid">
          ${renderJobFact("Required completion", `${formatCount(row.required_completion_rate, "0")}%`)}
          ${renderJobFact("Optional completion", `${formatCount(row.optional_completion_rate, "0")}%`)}
          ${renderJobFact("Band", row.classification_band || "Not parsed")}
          ${renderJobFact("Reference month", row.canonical_reference_month || "Not parsed")}
          ${renderJobFact("Reference source", displayCodeLabel(row.canonical_reference_date_source || "not_parsed"))}
          ${renderJobFact("Source ID", row.source_job_id || "Not parsed")}
          ${renderJobFact("Posted", formatJobDate(row.posted_at) || "Not parsed")}
          ${renderJobFact("Fetched", formatJobDate(row.fetched_at) || "Not parsed")}
          ${renderJobFact("Work type", row.work_type || "Not parsed")}
          ${renderJobFact("Location", row.location_text || "Not parsed")}
          ${renderJobFact("Advertised salary", formatJobSalary(row) || row.salary_text || "Not parsed")}
          ${renderJobFact("Advertised basis", row.advertised_salary_basis || row.salary_basis || "Not parsed")}
          ${renderJobFact("Enterprise Agreement salary", formatEnterpriseAgreementJobSalary(row) || "Not available")}
          ${renderJobFact("EA effective", [row.enterprise_agreement_salary_effective_from, row.enterprise_agreement_salary_effective_to].filter(Boolean).join(" to ") || "Not available")}
          ${renderJobFact("Salary validation", displayCodeLabel(row.salary_band_validation_status || "not_checked"))}
        </div>
        ${missingRequired.length ? `<p><strong>Missing required:</strong> ${escapeHtml(missingRequired.join(", "))}</p>` : '<p>Compulsory fields are filled for Stage 1.</p>'}
        ${missingOptional.length ? `<p><strong>Optional gaps:</strong> ${escapeHtml(missingOptional.slice(0, 8).join(", "))}${missingOptional.length > 8 ? "..." : ""}</p>` : ""}
      </details>
    </article>
  `;
}

function pipelineFieldLabel(fieldId) {
  const fields = [
    ...(state.jobPipelineStage1?.stage_policy?.required_fields || []),
    ...(state.jobPipelineStage1?.stage_policy?.optional_fields || []),
  ];
  const match = fields.find((field) => field.id === fieldId);
  return match?.label || displayCodeLabel(fieldId || "");
}

function renderIntake() {
  const queue = document.getElementById("intake-queue");
  if (!queue) return;

  const intakeRows = intakeProcessingRows();
  const total = intakeRows.length;
  const active = intakeRows.length;
  const decisions = intakeRows.filter((item) => hasScopeIssue(item)).length;
  const pdfs = intakeRows.filter((item) => item.pdf_frozen).length;
  const weak = intakeRows.filter((item) => !item.fetch_metadata || intakeConfidence(item).value < 60).length;
  const suspectSources = intakeRows.filter((item) => item.pdf_source?.suspect).length;

  setText("intake-records", formatCount(total, "0"));
  setText("intake-pdfs", formatCount(pdfs, "0"));
  setText("intake-source-retry", formatCount(suspectSources, "0"));
  setText("intake-active", formatCount(active, "0"));
  setText("intake-decisions", formatCount(decisions, "0"));
  setText("lane-clean", formatCount(active, "0"));
  setText("lane-multi", formatCount(decisions, "0"));
  setText("lane-weak", formatCount(weak, "0"));
  setText("lane-source-retry", formatCount(suspectSources, "0"));
  if (document.body.dataset.view === "intake") {
    setText("header-stats", `${formatCount(total, "0")} processing | ${formatCount(decisions, "0")} scope checks | ${formatCount(suspectSources, "0")} suspect PDFs`);
  }
  document.querySelectorAll("[data-intake-quick-filter]").forEach((button) => {
    const isActive = button.dataset.intakeQuickFilter === state.intakeQuickFilter;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  renderIntakeQuality(total, active);

  const q = state.intakeFilter.trim().toLowerCase();
  const statusFilter = state.intakeStatusFilter;
  const filteredRows = getSortedIntakeRows(intakeRows)
    .filter((item) => {
      const status = intakeStatus(item);
      if (statusFilter !== "all" && status !== statusFilter) return false;
      if (!q) return true;
      const meta = item.fetch_metadata || {};
      const haystack = [
        item.ae_id,
        item.source_name,
        item.canonical_lga_short_name,
        meta["Agreement Title"],
        meta.matched_lga_names,
        meta.Industry,
        meta["Agreement ID"],
        meta["Matter Number"],
        item.acceptance_state,
        item.in_working_set ? "accepted working set review board" : "candidate",
        item.pdf_frozen ? "pdf fetched" : "pdf not fetched fetch source",
        item.pdf_source?.suspect ? "suspect pdf under 500kb retry source incomplete document" : "",
        hasScopeIssue(item) ? "scope check unresolved unmatched multi council" : "source ready scope clear",
        isSplitAgreementCandidate(item) ? "split agreement split council multi council matched councils" : "",
        item.possible_multi_council_flag ? "multi council" : "",
        item.matched_lga_count === 0 ? "unmatched unresolved scope" : "",
      ].join(" ").toLowerCase();
      return haystack.includes(q);
    });
  const rows = filteredRows;

  if (!rows.length) {
    queue.innerHTML = renderEmptyState(
      "No processing rows match the current filters",
      "Accepted items from Incoming will appear here for source checks and Review Board handoff.",
      {
        eyebrow: "Intake processing",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-intake-empty-clear="1">Clear intake filters</button>',
      },
    );
    queue.querySelector("[data-intake-empty-clear]")?.addEventListener("click", () => {
      state.intakeQuickFilter = "all";
      state.intakeStatusFilter = "all";
      state.intakeFilter = "";
      const statusSelect = document.getElementById("intake-status-filter");
      const filterInput = document.getElementById("intake-filter");
      if (statusSelect) statusSelect.value = "all";
      if (filterInput) filterInput.value = "";
      renderIntake();
    });
    return;
  }

  const countHtml = `
    <div class="intake-result-count">
      Showing ${escapeHtml(formatCount(rows.length))} real Fair Work candidate rows
    </div>
  `;
  const splitRows = [];
  const sourceRetryRows = [];
  const sourceMissingRows = [];
  const standardRows = [];
  rows.forEach((item) => {
    if (isSplitAgreementCandidate(item)) {
      splitRows.push(item);
    } else if (item?.pdf_source?.suspect) {
      sourceRetryRows.push(item);
    } else if (!item?.pdf_frozen) {
      sourceMissingRows.push(item);
    } else {
      standardRows.push(item);
    }
  });
  queue.innerHTML = countHtml
    + standardRows.map(renderIntakeRow).join("")
    + renderSourceRetrySection(sourceRetryRows)
    + renderSourceMissingSection(sourceMissingRows)
    + renderSplitAgreementSection(splitRows);
  queue.querySelectorAll("[data-intake-next-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.disabled) return;
      await handleIntakeNextAction(button);
    });
  });
  queue.querySelectorAll("[data-intake-state]").forEach((button) => {
    button.addEventListener("click", async () => {
      const aeId = button.dataset.aeId;
      const nextState = button.dataset.intakeState;
      const item = findIntakeRow(aeId);
      if (!item || !nextState || button.disabled) return;
      try {
        await saveIntakeDecision(aeId, nextState, defaultIntakeReason(item, nextState), "");
        toast(`${intakeStatusLabel(nextState)} saved for ${aeId.toUpperCase()}`, "success");
      } catch (error) {
        toast(apiErrorMessage(error), "error");
      }
    });
  });
  queue.querySelectorAll("[data-freeze-source]").forEach((button) => {
    button.addEventListener("click", async () => {
      const aeId = button.dataset.aeId;
      const forceRefresh = button.dataset.forceRefresh === "true";
      if (!aeId || button.disabled) return;
      const originalText = button.textContent;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      button.textContent = forceRefresh ? "Retrying..." : "Fetching...";
      try {
        const result = await freezeIntakeSource(aeId, { forceRefresh });
        const source = result.pdf_source || result.candidate?.pdf_source || {};
        const suffix = source.suspect ? " but still looks under 500 KB" : "";
        toast(`Fetched PDF registered for ${aeId.toUpperCase()}${suffix}`, source.suspect ? "warning" : "success");
      } catch (error) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
        button.textContent = originalText;
        toast(apiErrorMessage(error), "error");
      }
    });
  });
}

function renderSourceRetrySection(rows) {
  if (!rows.length) return "";
  return `
    <details class="intake-source-retry-section">
      <summary>
        <span>
          <strong>Source retry</strong>
          <small>Accepted records with fetched PDFs that look incomplete or under 500 KB</small>
        </span>
        <b>${escapeHtml(formatCount(rows.length, "0"))}</b>
      </summary>
      <div class="intake-collapsible-list">
        ${rows.map(renderIntakeRow).join("")}
      </div>
    </details>
  `;
}

function renderSourceMissingSection(rows) {
  if (!rows.length) return "";
  return `
    <details class="intake-source-missing-section">
      <summary>
        <span>
          <strong>Source missing</strong>
          <small>Accepted records waiting for the source PDF fetch before QA</small>
        </span>
        <b>${escapeHtml(formatCount(rows.length, "0"))}</b>
      </summary>
      <div class="intake-collapsible-list">
        ${rows.map(renderIntakeRow).join("")}
      </div>
    </details>
  `;
}

function renderSplitAgreementSection(rows) {
  if (!rows.length) return "";
  return `
    <details class="intake-split-section">
      <summary>
        <span>
          <strong>Split agreement originals</strong>
          <small>Original multi-council source records retained after split council cards are created</small>
        </span>
        <b>${escapeHtml(formatCount(rows.length, "0"))}</b>
      </summary>
      <div class="intake-collapsible-list">
        ${rows.map(renderIntakeRow).join("")}
      </div>
    </details>
  `;
}

async function handleIntakeNextAction(button) {
  const aeId = button.dataset.aeId;
  const action = button.dataset.intakeNextAction;
  const item = findIntakeRow(aeId);
  if (!item || !action) return;

  const setBusy = (label) => {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = label;
  };
  const clearBusy = (label) => {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.textContent = label;
  };

  if (action === "freeze" || action === "retry") {
    const originalText = button.textContent;
    const forceRefresh = action === "retry";
    setBusy(forceRefresh ? "Retrying..." : "Fetching...");
    try {
      const result = await freezeIntakeSource(aeId, { forceRefresh });
      const source = result.pdf_source || result.candidate?.pdf_source || {};
      const suffix = source.suspect ? " but still looks under 500 KB" : "";
      toast(`Fetched PDF registered for ${aeId.toUpperCase()}${suffix}`, source.suspect ? "warning" : "success");
    } catch (error) {
      clearBusy(originalText);
      toast(apiErrorMessage(error), "error");
    }
    return;
  }

  if (action === "accept") {
    const originalText = button.textContent;
    setBusy("Accepting...");
    try {
      await saveIntakeDecision(aeId, "accepted", defaultIntakeReason(item, "accepted"), "");
      toast(`Accepted source saved for ${aeId.toUpperCase()}`, "success");
    } catch (error) {
      clearBusy(originalText);
      toast(apiErrorMessage(error), "error");
    }
    return;
  }

  if (action === "review_scope") {
    focusMatrixRow(aeId);
    toast("Focused the Review Board card for scope decision", "success");
    return;
  }

  if (action === "send_review") {
    await openCouncil(aeId, "overview");
  }
}

function renderIntakeRow(item) {
  const meta = item.fetch_metadata || {};
  const pdfSource = item.pdf_source || {};
  const sourceGate = sourceGateStatus(item);
  const nextAction = nextIntakeAction(item);
  const pdfSizeLabel = formatBytes(pdfSource.file_size_bytes);
  const pdfSuspect = Boolean(pdfSource.suspect);
  const status = intakeStatus(item);
  const confidence = intakeConfidence(item);
  const title = metadataPrimaryLabel(item);
  const matched = splitMatchedNames(meta).join(", ") || item.canonical_lga_short_name || "Unassigned";
  const dateRange = meta ? formatDateRange(meta) : "Dates not stated";
  const statusClass = `intake-status-${status}`;
  const pipelineStatus = meta.pipeline_status || item.candidate_stage || "unknown";
  const riskNotes = [];
  if (pipelineStatus.includes("superseded")) {
    const supersededBy = meta.superseded_by_ae_id || item.superseded_by_ae_id;
    riskNotes.push(supersededBy ? `superseded by ${supersededBy.toUpperCase()}` : "superseded candidate");
  }
  if (item.pdf_frozen === false) riskNotes.push("PDF not fetched");
  if (pdfSuspect) riskNotes.push("PDF under 500 KB - retry source");
  if (item.matched_lga_count === 0) riskNotes.push("no Victorian LGA match");
  if (item.multi_council_decision?.decision_pending) riskNotes.push("multi-council decision");
  if (item.possible_multi_council_flag) riskNotes.push("multi-council candidate");
  if (item.processing_gated) riskNotes.push("processing gated");
  if (!item.fetch_metadata) riskNotes.push("missing fetch metadata");
  if (hasUnresolvedScopeStatus(meta.scope_resolution_status)) riskNotes.push("scope unresolved");
  if (item.pdf_frozen && item.in_working_set) riskNotes.push("fetched source available");
  if (status === "accepted") riskNotes.push("accepted into Intake Processing");
  if (!riskNotes.length) riskNotes.push("source checks clear");
  const stateButtons = [
    ["accepted", "Accepted"],
    ["needs_review", "Needs review"],
  ].map(([stateName, label]) => {
    const activeClass = status === stateName ? "is-active" : "";
    const pressed = status === stateName ? "true" : "false";
    return `<button class="intake-state-btn ${activeClass} intake-state-${stateName}" aria-pressed="${pressed}" data-intake-state="${stateName}" data-ae-id="${escapeHtml(item.ae_id)}">${escapeHtml(label)}</button>`;
  }).join("");
  const hasPdfUrl = Boolean(meta.pdf_url || item.pdf_url);
  const freezeButton = item.pdf_frozen
    ? pdfSuspect
      ? `<button class="intake-freeze-btn is-suspect" data-freeze-source data-force-refresh="true" data-ae-id="${escapeHtml(item.ae_id)}">Retry source</button>`
      : '<button class="intake-freeze-btn is-frozen" disabled>Fetched PDF</button>'
    : hasPdfUrl
      ? `<button class="intake-freeze-btn" data-freeze-source data-ae-id="${escapeHtml(item.ae_id)}">Fetch PDF</button>`
      : '<button class="intake-freeze-btn" disabled>No PDF URL</button>';
  const primaryRisk = riskNotes.find((note) => !note.includes("accepted into")) || riskNotes[0] || "checks clear";
  const scopeLabel = hasScopeIssue(item) ? "Check" : "Clear";
  const sourceLabel = sourceGate.key === "ready"
    ? (pdfSizeLabel || "Fetched")
    : sourceGate.detail;
  const intakeMetaItems = [
    matched,
    dateRange,
    sourceGate.key === "ready" ? `PDF ${sourceLabel}` : sourceGate.label,
    `Scope ${scopeLabel.toLowerCase()}`,
    `${confidence.value}% ${confidence.label}`,
    primaryRisk,
  ];

  return `
    <article class="intake-row intake-row-compact workbench-card-scaffold ${statusClass}">
      <div class="intake-row-main workbench-card-main">
        <div class="intake-row-title workbench-card-title">
          <span class="intake-ae-pill">${escapeHtml(item.ae_id.toUpperCase())}</span>
          <h3>${escapeHtml(title)}</h3>
        </div>
        ${renderInlineMeta(intakeMetaItems, "intake-inline-meta workbench-inline-meta")}
      </div>
      <div class="intake-actions workbench-card-actions">
        <button class="intake-next-btn next-action-${escapeHtml(nextAction.kind)}" data-intake-next-action="${escapeHtml(nextAction.action)}" data-ae-id="${escapeHtml(item.ae_id)}" ${nextAction.disabled ? "disabled" : ""}>
          <span>${escapeHtml(nextAction.label || "Open")}</span>
        </button>
        <details class="intake-more-actions">
          <summary>More</summary>
          <div class="intake-more-action-list">
            ${freezeButton}
            <div class="intake-state-buttons" role="group" aria-label="Set intake state">
              ${stateButtons}
            </div>
          </div>
        </details>
      </div>
    </article>
  `;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function renderEmptyState(title, detail, { eyebrow = "No results", actionHtml = "" } = {}) {
  return `
    <div class="workbench-empty-state">
      <span>${escapeHtml(eyebrow)}</span>
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(detail)}</p>
      ${actionHtml ? `<div class="workbench-empty-actions">${actionHtml}</div>` : ""}
    </div>
  `;
}

function wikiAsArray(value) {
  return Array.isArray(value) ? value : [];
}

function wikiDocumentMapRows() {
  return wikiAsArray(state.wikiDocumentMaps?.document_maps);
}

function wikiReferenceInputRows() {
  return wikiAsArray(state.wikiReferenceInputs?.reference_inputs);
}

function wikiQuestionRows() {
  return wikiAsArray(state.wikiQuestions?.questions);
}

function wikiBacklogRows() {
  return wikiAsArray(state.wikiBacklog?.items);
}

function wikiLanguageTerms() {
  return wikiAsArray(state.wikiLanguageMap?.terms);
}

function wikiTagRegistryFamilies() {
  return wikiAsArray(state.wikiTagRegistry?.families);
}

function wikiTagRegistryRows() {
  return wikiTagRegistryFamilies()
    .flatMap((family) => wikiAsArray(family.tags).map((tag) => ({
      ...tag,
      family: tag.family || family.family,
      family_label: family.label || wikiDisplayLabel(family.family),
    })))
    .sort((a, b) => Number(b.record_count || 0) - Number(a.record_count || 0) || String(a.tag || "").localeCompare(String(b.tag || "")));
}

function wikiTagDimensionValues(dimensionId) {
  const dimensions = wikiAsArray(state.wikiTagRegistry?.taggable_dimensions?.dimensions);
  return wikiAsArray(dimensions.find((dimension) => dimension.dimension === dimensionId)?.values);
}

function wikiTaggedEvidenceRows() {
  return wikiAsArray(state.wikiTaggedEvidenceRows);
}

function wikiArtifactRows() {
  return wikiAsArray(state.wikiArtifacts?.artifacts);
}

function wikiGoldCategories() {
  return wikiAsArray(state.wikiGoldComparatorTarget?.categories);
}

function wikiGoldEntitlementRows() {
  return wikiGoldCategories().flatMap((category) =>
    wikiAsArray(category.children).map((child) => ({
      ...child,
      category_label: category.label,
      category_id: category.category_id,
    })),
  );
}

function wikiSelectedGoldEntitlement() {
  const rows = wikiGoldEntitlementRows();
  return rows.find((item) => item.entitlement_id === state.wikiSelectedGoldEntitlementId) || rows[0] || null;
}

function wikiArtifactSummaryLine(item) {
  const summary = item?.summary || {};
  const goldTarget = item?.gold_comparator_target || {};
  const parts = [];
  if (goldTarget.accuracy_target !== undefined) parts.push(`${displayFractionPercent(goldTarget.accuracy_target, "0%")} recreate target`);
  if (summary.entitlements !== undefined) parts.push(`${formatCount(summary.entitlements, "0")} entitlement rows`);
  if (summary.categories !== undefined) parts.push(`${formatCount(summary.categories, "0")} categories`);
  if (summary.explicit_review_items !== undefined) parts.push(`${formatCount(summary.explicit_review_items, "0")} review flags`);
  if (summary.specialist_cohort_rows_excluded !== undefined) parts.push(`${formatCount(summary.specialist_cohort_rows_excluded, "0")} specialist excluded`);
  if (summary.language_candidates !== undefined) parts.push(`${formatCount(summary.language_candidates, "0")} language hits`);
  if (summary.pages_scanned !== undefined) parts.push(`${formatCount(summary.pages_scanned, "0")} units`);
  return parts.join(" / ");
}

function wikiClauseCategories() {
  return wikiAsArray(state.wikiClauseLibrary?.categories);
}

function wikiClauseChildren() {
  return wikiClauseCategories().flatMap((category) => wikiAsArray(category.children));
}

function wikiSelectedClauseNode() {
  const children = wikiClauseChildren();
  return children.find((child) => child.id === state.wikiSelectedClauseId) || children[0] || null;
}

function wikiCategoryForClause(clauseId) {
  return wikiClauseCategories().find((category) =>
    wikiAsArray(category.children).some((child) => child.id === clauseId),
  ) || null;
}

function wikiRunSummary() {
  return state.wikiLatestRun?.summary || {};
}

function wikiDisplayLabel(value, fallback = DISPLAY_EMPTY) {
  const raw = String(value || "").trim();
  return raw ? displayCodeLabel(raw) : fallback;
}

function wikiSourceRefLabel(sourceRef) {
  const agreementId = String(sourceRef?.agreement_id || "").toUpperCase();
  const sourceId = String(sourceRef?.source_id || "").trim();
  const page = sourceRef?.page ? `p.${sourceRef.page}` : "";
  return [agreementId || sourceId, page].filter(Boolean).join(" / ") || DISPLAY_EMPTY;
}

function wikiTagEntries(tags) {
  if (!tags || typeof tags !== "object") return [];
  return Object.entries(tags)
    .flatMap(([family, values]) => wikiAsArray(values).map((item) => ({ ...item, family: item?.family || family })))
    .filter((item) => item?.tag);
}

function wikiTagPills(tags, limit = 4) {
  const entries = wikiTagEntries(tags).slice(0, limit);
  if (!entries.length) return `<span class="wiki-muted">No tags</span>`;
  return entries.map((item) => `
    <span class="wiki-tag-pill" title="${escapeHtml(wikiAsArray(item.evidence_terms).join(", "))}">
      ${escapeHtml(wikiDisplayLabel(item.tag))}
      ${item.score ? `<small>${escapeHtml(item.score)}</small>` : ""}
    </span>
  `).join("");
}

function wikiRelevanceCountItems(summary) {
  const counts = summary?.clause_context_relevance_counts || summary?.standard_band_relevance_counts || {};
  const order = ["core_clause", "context", "needs_review", "exclusion", "direct", "indirect", "unclear", "none"];
  return order
    .filter((key) => counts[key] !== undefined)
    .map((key) => ({ key, value: Number(counts[key] || 0) }));
}

function wikiRecordRelevance(record) {
  return record?.clause_context_relevance || record?.standard_band_relevance || "needs_review";
}

function wikiRelevanceCountsHtml(summary) {
  const items = wikiRelevanceCountItems(summary);
  if (!items.length) return `<span class="wiki-muted">No relevance counts</span>`;
  return items.map((item) => `
    <span class="wiki-relevance wiki-relevance-${escapeHtml(item.key)}">
      ${escapeHtml(wikiDisplayLabel(item.key))}
      <strong>${formatCount(item.value, "0")}</strong>
    </span>
  `).join("");
}

function wikiTopClauseHtml(summary, limit = 6) {
  const rows = wikiAsArray(summary?.top_clause_functions).slice(0, limit);
  if (!rows.length) return `<span class="wiki-muted">No clause tags yet</span>`;
  return rows.map((item) => `
    <span class="wiki-clause-chip">
      ${escapeHtml(wikiDisplayLabel(item.tag))}
      <strong>${formatCount(item.score, "0")}</strong>
    </span>
  `).join("");
}

function setWikiStatus(message, tone = "info") {
  const el = document.getElementById("wiki-status");
  if (!el) return;
  el.textContent = message;
  el.className = `analysis-status wiki-status wiki-status-${tone}`;
}

function wikiTaggedEvidenceFilterKey() {
  return [
    state.wikiTagFilter || "all",
    state.wikiTagSourceType || "all",
    state.wikiTagRecordType || "all",
    state.wikiTagRelevance || "all",
    state.wikiTagQuery || "",
  ].join("|");
}

function wikiTaggedEvidenceParams(offset = 0) {
  const params = new URLSearchParams();
  if (state.wikiTagFilter && state.wikiTagFilter !== "all") params.set("tag", state.wikiTagFilter);
  if (state.wikiTagSourceType && state.wikiTagSourceType !== "all") params.set("source_type", state.wikiTagSourceType);
  if (state.wikiTagRecordType && state.wikiTagRecordType !== "all") params.set("record_type", state.wikiTagRecordType);
  if (state.wikiTagRelevance && state.wikiTagRelevance !== "all") params.set("relevance", state.wikiTagRelevance);
  if (state.wikiTagQuery) params.set("q", state.wikiTagQuery);
  params.set("limit", "180");
  params.set("offset", String(offset || 0));
  return params;
}

async function loadWikiTaggedEvidence({ force = false, append = false } = {}) {
  const key = wikiTaggedEvidenceFilterKey();
  const currentRows = append && state.wikiTaggedEvidenceKey === key ? wikiTaggedEvidenceRows() : [];
  if (!force && !append && state.wikiTaggedEvidence && state.wikiTaggedEvidenceKey === key) {
    return state.wikiTaggedEvidence;
  }
  if (!force && state.wikiTaggedEvidenceLoading) return state.wikiTaggedEvidenceLoading;
  const params = wikiTaggedEvidenceParams(currentRows.length);
  state.wikiTaggedEvidenceLoading = api(`${WIKI_ENDPOINTS.taggedEvidence}?${params.toString()}`)
    .then((payload) => {
      const incomingRows = wikiAsArray(payload?.rows);
      const rows = append ? [...currentRows, ...incomingRows] : incomingRows;
      state.wikiTaggedEvidenceRows = rows;
      state.wikiTaggedEvidence = { ...(payload || {}), rows };
      state.wikiTaggedEvidenceKey = key;
      return state.wikiTaggedEvidence;
    })
    .finally(() => {
      state.wikiTaggedEvidenceLoading = null;
    });
  return state.wikiTaggedEvidenceLoading;
}

function resetWikiTaggedEvidence() {
  state.wikiTaggedEvidence = null;
  state.wikiTaggedEvidenceRows = [];
  state.wikiTaggedEvidenceKey = "";
}

function renderWikiMetrics() {
  const summary = state.wikiClauseLibrary?.summary || {};
  const latestSummary = wikiRunSummary();
  const tagSummary = state.wikiTagRegistry?.summary || {};
  setText("wiki-agreements-count", formatCount(tagSummary.source_records ?? ((summary.agreement_sources || 0) + (summary.reference_sources || 0)), "0"));
  setText("wiki-pages-count", formatCount(tagSummary.tags ?? summary.subcategories, "0"));
  setText("wiki-questions-count", formatCount(tagSummary.tagged_records ?? latestSummary.sections_detected, "0"));
  setText("wiki-backlog-count", formatCount((summary.questions || 0) + (summary.learning_backlog_items || 0), "0"));
  const runId = state.wikiLatestRun?.run_id || state.wikiStatus?.latest_run_id || "No run loaded";
  const generated = displayDate(state.wikiLatestRun?.generated_at, DISPLAY_EMPTY);
  const scope = wikiDisplayLabel(state.wikiTagRegistry?.scope_role || state.wikiClauseLibrary?.scope_focus || state.wikiLatestRun?.scope_focus || state.wikiStatus?.scope_focus);
  setText("wiki-latest-run-note", `${scope} / refreshed ${generated || runId}`);
}

function renderWikiRunList() {
  const container = document.getElementById("wiki-run-list");
  if (!container) return;
  const runs = wikiAsArray(state.wikiRuns?.runs);
  if (!runs.length) {
    container.innerHTML = renderEmptyState("No wiki runs", "Run the pilot builder to create document maps and learning records.", { eyebrow: "Wiki" });
    return;
  }
  const latestId = state.wikiStatus?.latest_run_id || state.wikiLatestRun?.run_id;
  container.innerHTML = runs.slice(0, 8).map((run) => {
    const summary = run.summary || {};
    const active = run.run_id === latestId ? " is-active" : "";
    return `
      <article class="wiki-run-card${active}">
        <div>
          <strong>${escapeHtml(run.run_id || "wiki run")}</strong>
          <span>${escapeHtml(displayDate(run.generated_at, DISPLAY_EMPTY))}</span>
        </div>
        <dl>
          <div><dt>Agreements</dt><dd>${formatCount(summary.agreements_mapped, "0")}</dd></div>
          <div><dt>Pages</dt><dd>${formatCount(summary.pages_scanned, "0")}</dd></div>
          <div><dt>Sections</dt><dd>${formatCount(summary.sections_detected, "0")}</dd></div>
        </dl>
      </article>
    `;
  }).join("");
}

function renderWikiReferenceList() {
  const container = document.getElementById("wiki-reference-list");
  if (!container) return;
  const references = wikiReferenceInputRows();
  if (!references.length) {
    container.innerHTML = renderEmptyState("No reference inputs", "Add official policy, award, or interpretive material to strengthen clause context.", { eyebrow: "References" });
    return;
  }
  container.innerHTML = references.slice(0, 12).map((item) => {
    const summary = item.summary || {};
    const sourceUrl = String(item.source_url || "").trim();
    return `
      <article class="wiki-reference-card">
        <div class="wiki-reference-head">
          <strong>${escapeHtml(item.source_name || item.source_id || "Reference input")}</strong>
          <span>${escapeHtml(wikiDisplayLabel(item.source_kind || "reference_material"))}</span>
        </div>
        <div class="wiki-reference-meta">
          <span>${formatCount(summary.pages_scanned, "0")} units</span>
          <span>${formatCount(summary.sections_detected, "0")} sections</span>
          <span>${formatCount(summary.language_candidates, "0")} language hits</span>
        </div>
        ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Source page</a>` : ""}
      </article>
    `;
  }).join("");
}

function renderWikiLanguageList() {
  const container = document.getElementById("wiki-language-list");
  if (!container) return;
  const terms = wikiLanguageTerms();
  if (!terms.length) {
    container.innerHTML = renderEmptyState("No language map", "The wiki has not built a clause-context term map yet.", { eyebrow: "Language" });
    return;
  }
  container.innerHTML = terms.slice(0, 10).map((term) => {
    const observed = wikiAsArray(term.observed_terms).slice(0, 4);
    return `
      <article class="wiki-language-card">
        <div class="wiki-language-head">
          <strong>${escapeHtml(wikiDisplayLabel(term.canonical_term))}</strong>
          <span>${escapeHtml(wikiDisplayLabel(term.review_state, "Proposed"))}</span>
        </div>
        <div class="wiki-observed-terms">
          ${observed.map((item) => `
            <span>${escapeHtml(item.observed_term || "")}<strong>${formatCount(item.count, "0")}</strong></span>
          `).join("")}
        </div>
      </article>
    `;
  }).join("");
}

function renderWikiClauseTree() {
  const container = document.getElementById("wiki-clause-tree");
  if (!container) return;
  const categories = wikiClauseCategories();
  if (categories.length) {
    container.innerHTML = categories.map((category) => `
      <section class="wiki-tree-category">
        <div class="wiki-tree-category-head">
          <strong>${escapeHtml(category.label || category.id)}</strong>
          <span>${formatCount(category.evidence_count, "0")}</span>
        </div>
        <div class="wiki-tree-children">
          ${wikiAsArray(category.children).map((child) => {
            const active = child.id === state.wikiSelectedClauseId ? " is-active" : "";
            return `
              <button class="wiki-tree-node${active}" type="button" data-wiki-clause-id="${escapeHtml(child.id)}">
                <span>${escapeHtml(child.label || child.id)}</span>
                <strong>${formatCount(child.evidence_count, "0")}</strong>
              </button>
            `;
          }).join("")}
        </div>
      </section>
    `).join("");
    return;
  }
  const goldCategories = wikiGoldCategories();
  if (goldCategories.length) {
    container.innerHTML = goldCategories.map((category) => `
    <section class="wiki-tree-category">
      <div class="wiki-tree-category-head">
        <strong>${escapeHtml(category.label || category.category_id || "Knowledge family")}</strong>
        <span>${formatCount(category.row_count, "0")}</span>
      </div>
      <div class="wiki-tree-children">
        ${wikiAsArray(category.children).map((child) => {
          const active = child.entitlement_id === state.wikiSelectedGoldEntitlementId ? " is-active" : "";
          return `
            <button class="wiki-tree-node${active}" type="button" data-wiki-gold-entitlement-id="${escapeHtml(child.entitlement_id || "")}">
              <span>${escapeHtml(child.label || child.entitlement_id || "Knowledge item")}</span>
              <strong>${escapeHtml(wikiDisplayLabel(child.target?.comparator_posture, ""))}</strong>
            </button>
          `;
        }).join("")}
      </div>
    </section>
  `).join("");
    return;
  }
  container.innerHTML = renderEmptyState("No knowledge categories", "The wiki has not built a source knowledge library yet.", { eyebrow: "Knowledge" });
}

function wikiSourceListHtml(sources, limit = 8) {
  const rows = wikiAsArray(sources).slice(0, limit);
  if (!rows.length) return `<span class="wiki-muted">No source links yet</span>`;
  return rows.map((source) => {
    const pages = wikiAsArray(source.pages).slice(0, 5).map((page) => `p.${page}`).join(", ");
    return `
      <div class="wiki-source-row">
        <span>${escapeHtml(wikiDisplayLabel(source.source_type))}</span>
        <strong>${escapeHtml(source.source_name || source.source_id || "Source")}</strong>
        <small>${escapeHtml(pages || `${formatCount(source.page_count, "0")} pages`)}</small>
      </div>
    `;
  }).join("");
}

function wikiObservedTermsHtml(observedTerms) {
  const rows = wikiAsArray(observedTerms).slice(0, 6);
  if (!rows.length) return `<span class="wiki-muted">No mapped terms yet</span>`;
  return rows.map((item) => `
    <span>${escapeHtml(item.observed_term || item.canonical_term || "")}<strong>${formatCount(item.count, "0")}</strong></span>
  `).join("");
}

function wikiExamplesHtml(examples) {
  const rows = wikiAsArray(examples).slice(0, 4);
  if (!rows.length) return renderEmptyState("No examples yet", "As maps fill in, source-linked clause examples will collect here.", { eyebrow: "Evidence" });
  return rows.map((example) => `
    <article class="wiki-section-card">
      <div>
        <strong>${escapeHtml(example.title || "Clause example")}</strong>
        <span>${escapeHtml(wikiSourceRefLabel(example.source_ref))} / ${escapeHtml(wikiDisplayLabel(example.relevance, "Mapped"))}</span>
      </div>
      <p>${escapeHtml(example.excerpt || "")}</p>
    </article>
  `).join("");
}

function wikiEvidenceClauseTitle(record, fallback = "Clause evidence") {
  const subclass = record?.suggested_subclass || {};
  const sourceRef = record?.source_ref || {};
  return wikiDisplayLabel(
    record?.clause_label
      || record?.heading
      || sourceRef.clause_heading
      || subclass.label
      || subclass.subclass_id,
    fallback,
  );
}

function wikiEvidencePageLabel(record, fallbackSourceLabel = "") {
  const sourceRef = record?.source_ref || {};
  const page = record?.page || sourceRef.page;
  const agreementId = String(sourceRef.agreement_id || "").toUpperCase();
  return [agreementId, page ? `p.${page}` : "", fallbackSourceLabel && fallbackSourceLabel !== DISPLAY_EMPTY ? fallbackSourceLabel : ""]
    .filter(Boolean)
    .join(" / ");
}

function wikiEvidenceClauseCardHtml(record, fallbackSourceLabel, { candidate = false } = {}) {
  const title = wikiEvidenceClauseTitle(record, candidate ? "Candidate context" : "Clause evidence");
  const sourceLabel = wikiEvidencePageLabel(record, fallbackSourceLabel);
  const subclass = record?.suggested_subclass || {};
  const text = record?.clause_text || record?.excerpt || "";
  const segments = wikiAsArray(record?.clause_segments);
  const tags = [
    candidate ? wikiDisplayLabel(record?.candidate_type, "Candidate") : "Source-backed evidence",
    subclass.label || "",
    ...wikiAsArray(record?.matched_terms).slice(0, 3).map((term) => wikiDisplayLabel(term)),
  ].filter(Boolean);
  return `
    <article class="wiki-evidence-clause${candidate ? " wiki-evidence-clause-candidate" : ""}">
      <div class="wiki-evidence-clause-head">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(sourceLabel || DISPLAY_EMPTY)}</span>
        </div>
        ${record?.page ? `<b>p.${escapeHtml(record.page)}</b>` : ""}
      </div>
      ${segments.length ? `
        <div class="wiki-evidence-segment-list">
          ${segments.map((segment) => `
            <div class="wiki-evidence-segment">
              <span>${escapeHtml(segment.clause_number || segment.page_label || "Text")}</span>
              <p>${escapeHtml(segment.text || "")}</p>
            </div>
          `).join("")}
        </div>
      ` : `<p class="wiki-evidence-clause-text">${escapeHtml(text || "No clause text captured yet.")}</p>`}
      ${tags.length ? `
        <div class="wiki-evidence-clause-tags">
          ${tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}
        </div>
      ` : ""}
    </article>
  `;
}

function wikiEvidencePackHtml(sourceEvidence, item, sourceLabel) {
  const excerpts = wikiAsArray(sourceEvidence.source_excerpts || item.source_excerpts);
  const candidatePages = wikiAsArray(sourceEvidence.candidate_pages || item.candidate_pages).slice(0, 4);
  if (excerpts.length) {
    return `
      <details class="wiki-source-excerpts wiki-evidence-pack">
        <summary>
          <span>Evidence clauses</span>
          <strong>${formatCount(excerpts.length, "0")}</strong>
        </summary>
        <div class="wiki-evidence-clause-list">
          ${excerpts.map((excerpt) => wikiEvidenceClauseCardHtml(excerpt, sourceLabel)).join("")}
        </div>
      </details>
    `;
  }
  if (candidatePages.length) {
    return `
      <details class="wiki-source-excerpts wiki-evidence-pack wiki-candidate-context">
        <summary>
          <span>Candidate context</span>
          <strong>${formatCount(candidatePages.length, "0")}</strong>
        </summary>
        <div class="wiki-evidence-clause-list">
          ${candidatePages.map((candidate) => wikiEvidenceClauseCardHtml(candidate, sourceLabel, { candidate: true })).join("")}
        </div>
      </details>
    `;
  }
  return "";
}

function wikiEvidenceCandidatePageCount(item) {
  const explicit = Number(item?.candidate_page_count ?? item?.source_evidence?.candidate_page_count);
  if (Number.isFinite(explicit) && explicit > 0) return explicit;
  return wikiAsArray(item?.candidate_pages || item?.source_evidence?.candidate_pages).length;
}

function wikiEvidenceKind(item) {
  if (!item) return "missing";
  if (item.presence === "latest_agreement_not_searched" || item.support_status === "latest_agreement_pending_source_search") return "pending_latest";
  if (item.presence === "source_clause_observed" || item.support_status === "source_clause_supported") return "source_backed";
  return wikiEvidenceCandidatePageCount(item) > 0 ? "outside_boundary" : "no_candidate";
}

function wikiEvidenceKindClass(kind) {
  return String(kind || "missing").replaceAll("_", "-");
}

function wikiEvidenceKindLabel(kind) {
  const labels = {
    source_backed: "Included above baseline",
    outside_boundary: "Context only",
    no_candidate: "No candidate text",
    pending_latest: "Pending latest search",
    missing: "Not in set",
  };
  return labels[kind] || wikiDisplayLabel(kind, "Evidence");
}

function wikiEvidenceKindVisual(kind) {
  const visuals = {
    source_backed: { fill: "#0b7f7a", border: "#075f5b", image: "none" },
    outside_boundary: { fill: "#d69222", border: "#8d5c12", image: "none" },
    no_candidate: { fill: "#2f6f9f", border: "#1f4f73", image: "none" },
    pending_latest: {
      fill: "#ffffff",
      border: "#7c8795",
      image: "repeating-linear-gradient(135deg, #ffffff 0, #ffffff 2px, #7c8795 2px, #7c8795 4px)",
    },
    missing: { fill: "#c8d4df", border: "#94a3b8", image: "none" },
  };
  return visuals[kind] || visuals.missing;
}

function wikiEvidenceKindStyle(kind) {
  const visual = wikiEvidenceKindVisual(kind);
  return `--dot-fill:${visual.fill};--dot-border:${visual.border};--dot-image:${visual.image};`;
}

function wikiNormalisedValueText(value) {
  if (!value || typeof value !== "object") return "";
  return [value.value, value.unit, value.condition].filter(Boolean).join(" ");
}

function wikiEvidenceAgreementId(row) {
  const candidates = [
    row?.agreement_id,
    row?.ae_id,
    row?.source_ref?.agreement_id,
    row?.source_ref?.ae_id,
    row?.source_evidence?.agreement_id,
    row?.source_evidence?.ae_id,
    row?.source_evidence?.source_ref?.agreement_id,
    row?.latest_agreement?.agreement_id,
  ];
  const found = candidates.find((candidate) => String(candidate || "").trim());
  return String(found || "").toLowerCase();
}

function wikiCouncilRowKey(row) {
  return String(wikiEvidenceAgreementId(row) || row?.council || "").toLowerCase();
}

function wikiAgreementBaseId(value) {
  return String(value || "").toLowerCase().split("__")[0];
}

function wikiAgreementRowForEvidenceRow(row) {
  const agreementId = wikiEvidenceAgreementId(row);
  if (!agreementId) return null;
  const baseId = wikiAgreementBaseId(agreementId);
  const rows = state.councils.filter((item) => item?.ae_id || item?.agreement_id);
  const exact = rows.find((item) => String(item?.ae_id || item?.agreement_id || "").toLowerCase() === agreementId);
  if (exact) return exact;
  const base = rows.find((item) => String(item?.ae_id || item?.agreement_id || "").toLowerCase() === baseId);
  if (base) return base;
  return rows.find((item) => wikiAgreementBaseId(item?.ae_id || item?.agreement_id) === baseId) || null;
}

function wikiCouncilReferenceForEvidenceRow(row, lookup = councilReferenceLookup()) {
  const agreementRow = wikiAgreementRowForEvidenceRow(row);
  const candidates = [
    agreementRow?.canonical_lga_short_name,
    agreementRow?.geography?.spatial_key,
    agreementRow?.geography?.short_name,
    agreementRow?.fetch_metadata?.lga_short_name,
    row?.council,
    row?.agreement_name,
    row?.source_evidence?.council,
    row?.source_evidence?.agreement_name,
    row?.canonical_lga_short_name,
    row?.spatial_key,
    row?.map_join_key,
  ];
  for (const candidate of candidates) {
    const ref = lookup.get(normaliseSpatialKey(candidate));
    if (ref) return ref;
  }
  return null;
}

function wikiCouncilReferenceKey(value, lookup = councilReferenceLookup()) {
  const ref = lookup.get(normaliseSpatialKey(value));
  return normaliseSpatialKey(ref?.spatial_key || ref?.short_name || value);
}

function wikiEvidenceRowReferenceKey(row, lookup = councilReferenceLookup()) {
  const agreementRow = wikiAgreementRowForEvidenceRow(row);
  if (agreementRow) {
    return normaliseSpatialKey(
      agreementRow.geography?.spatial_key
      || agreementRow.canonical_lga_short_name
      || agreementRow.geography?.short_name
      || agreementRow.fetch_metadata?.lga_short_name,
    );
  }
  const ref = wikiCouncilReferenceForEvidenceRow(row, lookup);
  return normaliseSpatialKey(ref?.spatial_key || ref?.short_name || row?.council);
}

function wikiDateRank(value) {
  const raw = String(value || "").trim();
  if (!raw) return 0;
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function wikiAgreementNumberRank(value) {
  const raw = String(value || "").match(/\d+/)?.[0] || "";
  const number = Number(raw);
  return Number.isFinite(number) ? number : 0;
}

function wikiAgreementRecencyTuple(item) {
  const meta = item?.fetch_metadata || {};
  const fwc = item?.fwc || {};
  const report = item?.report_values || {};
  return [
    meta.likely_most_current === "likely_current" ? 1 : 0,
    meta.pipeline_status === "active" || !meta.superseded_by_ae_id ? 1 : 0,
    wikiDateRank(fwc.operative_date || meta["Operative Date"] || meta.operative_date || report.operative_date),
    wikiDateRank(fwc.expiry_date || meta["Expiry Date"] || meta.expiry_date || report.expiry_date),
    Number(meta.published_year || 0),
    wikiAgreementNumberRank(meta.agreement_num_clean || meta["Agreement ID"] || item?.ae_id),
    wikiDateRank(item?.landed_at),
  ];
}

function wikiCompareRecencyTuple(left, right) {
  const length = Math.max(left?.length || 0, right?.length || 0);
  for (let index = 0; index < length; index += 1) {
    const delta = Number(left?.[index] || 0) - Number(right?.[index] || 0);
    if (delta) return delta;
  }
  return 0;
}

function wikiLatestAgreementByCouncilKey(lookup = councilReferenceLookup()) {
  const latest = new Map();
  state.councils.forEach((item) => {
    const ref = selectedAgreementReferenceForRow(item, lookup);
    const key = normaliseSpatialKey(
      ref?.spatial_key
      || item?.geography?.spatial_key
      || item?.canonical_lga_short_name
      || item?.geography?.short_name
      || item?.fetch_metadata?.lga_short_name,
    );
    if (!key) return;
    const current = latest.get(key);
    if (!current || wikiCompareRecencyTuple(wikiAgreementRecencyTuple(item), wikiAgreementRecencyTuple(current)) > 0) {
      latest.set(key, item);
    }
  });
  return latest;
}

function selectedAgreementReferenceForRow(item, lookup = councilReferenceLookup()) {
  const candidates = [
    item?.geography?.spatial_key,
    item?.canonical_lga_short_name,
    item?.geography?.short_name,
    item?.fetch_metadata?.lga_short_name,
  ];
  for (const candidate of candidates) {
    const ref = lookup.get(normaliseSpatialKey(candidate));
    if (ref) return ref;
  }
  return null;
}

function wikiEvidenceRowMatchesAgreement(row, agreementRow) {
  if (!agreementRow) return false;
  const evidenceId = String(row?.agreement_id || row?.ae_id || "").toLowerCase();
  const agreementId = String(agreementRow.ae_id || agreementRow.agreement_id || "").toLowerCase();
  if (!evidenceId || !agreementId) return false;
  return evidenceId === agreementId || wikiAgreementBaseId(evidenceId) === wikiAgreementBaseId(agreementId);
}

function wikiEvidenceFallbackRecencyTuple(row) {
  const text = `${row?.agreement_name || ""} ${row?.council || ""}`;
  const years = [...text.matchAll(/\b(20\d{2}|19\d{2})\b/g)].map((match) => Number(match[1]));
  return [
    years.length ? Math.max(...years) : 0,
    wikiAgreementNumberRank(row?.agreement_id || row?.ae_id || row?.agreement_name),
  ];
}

function wikiLatestAvailableEvidenceRow(rows) {
  return [...wikiAsArray(rows)].sort((a, b) =>
    wikiCompareRecencyTuple(wikiEvidenceFallbackRecencyTuple(b), wikiEvidenceFallbackRecencyTuple(a)),
  )[0] || null;
}

function wikiAgreementDisplayName(item, ref = null) {
  return item?.canonical_lga_short_name
    || item?.geography?.short_name
    || item?.fetch_metadata?.lga_short_name
    || ref?.short_name
    || ref?.long_name
    || "Council";
}

function wikiAgreementTitle(item) {
  return item?.source_name
    || item?.fetch_metadata?.["Agreement Title"]
    || item?.agreement_name
    || item?.ae_id
    || "Latest agreement";
}

function wikiPendingLatestEvidenceRow(agreementRow, ref = null) {
  const aeId = String(agreementRow?.ae_id || agreementRow?.agreement_id || "").toLowerCase();
  const fwc = agreementRow?.fwc || {};
  const meta = agreementRow?.fetch_metadata || {};
  const operative = fwc.operative_date || meta["Operative Date"] || meta.operative_date || "";
  const expiry = fwc.expiry_date || meta["Expiry Date"] || meta.expiry_date || "";
  return {
    council: wikiAgreementDisplayName(agreementRow, ref),
    agreement_id: aeId,
    agreement_name: wikiAgreementTitle(agreementRow),
    page_count: 0,
    candidate_page_count: 0,
    source_clause_page_count: 0,
    out_of_scope_candidate_page_count: 0,
    observed_subclasses: [],
    presence: "latest_agreement_not_searched",
    finding: "Latest agreement is in the workbench register, but wiki evidence has not been generated for this entitlement yet.",
    quantum_signals: [],
    normalised_values: [],
    confidence: 0,
    support_status: "latest_agreement_pending_source_search",
    source_ref: {
      source_type: "agreement_register",
      agreement_id: aeId,
      evidence_state: "latest_agreement_not_searched",
    },
    source_excerpts: [],
    candidate_pages: [],
    latest_agreement: {
      agreement_id: aeId,
      agreement_name: wikiAgreementTitle(agreementRow),
      operative_date: operative,
      expiry_date: expiry,
    },
  };
}

function wikiFallbackLatestCouncilEvidenceRows(sourceRows, lookup = councilReferenceLookup()) {
  const grouped = new Map();
  sourceRows.forEach((row) => {
    const key = wikiEvidenceRowReferenceKey(row, lookup)
      || normaliseSpatialKey(row?.council || row?.agreement_name || row?.agreement_id)
      || wikiCouncilRowKey(row);
    if (!key) return;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(row);
  });
  const latestRows = [];
  grouped.forEach((groupRows) => {
    const fallback = wikiLatestAvailableEvidenceRow(groupRows);
    if (fallback) latestRows.push(fallback);
  });
  return latestRows.length ? latestRows : sourceRows;
}

function wikiLatestCouncilEvidenceRows(rows) {
  const sourceRows = wikiAsArray(rows);
  if (!sourceRows.length) return [];
  const lookup = councilReferenceLookup();
  const latestAgreements = wikiLatestAgreementByCouncilKey(lookup);
  if (!latestAgreements.size) return wikiFallbackLatestCouncilEvidenceRows(sourceRows, lookup);
  const grouped = new Map();
  sourceRows.forEach((row) => {
    const key = wikiEvidenceRowReferenceKey(row, lookup)
      || normaliseSpatialKey(row?.council || row?.agreement_name || row?.agreement_id)
      || wikiCouncilRowKey(row);
    if (!key) return;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(row);
  });
  const latestRows = [];
  latestAgreements.forEach((latestAgreement, key) => {
    const groupRows = grouped.get(key) || [];
    const matches = groupRows.filter((row) => wikiEvidenceRowMatchesAgreement(row, latestAgreement));
    if (matches.length) {
      latestRows.push(wikiLatestAvailableEvidenceRow(matches) || matches[0]);
      return;
    }
    const ref = selectedAgreementReferenceForRow(latestAgreement, lookup);
    latestRows.push(wikiPendingLatestEvidenceRow(latestAgreement, ref));
  });
  return latestRows
    .sort((a, b) => String(a.council || "").localeCompare(String(b.council || "")));
}

function wikiSameCouncilEvidenceRow(left, right) {
  if (!left || !right) return false;
  const leftKey = wikiCouncilRowKey(left);
  const rightKey = wikiCouncilRowKey(right);
  if (leftKey && rightKey) return leftKey === rightKey;
  return wikiEvidenceRowReferenceKey(left) === wikiEvidenceRowReferenceKey(right);
}

function wikiFindCouncilEvidenceRow(rows, candidate, lookup = councilReferenceLookup()) {
  const raw = String(candidate || "").trim();
  if (!raw) return null;
  const directKey = raw.toLowerCase();
  const refKey = wikiCouncilReferenceKey(raw, lookup);
  return rows.find((row) => {
    if (wikiCouncilRowKey(row) === directKey) return true;
    if (wikiEvidenceRowReferenceKey(row, lookup) === refKey) return true;
    return normaliseSpatialKey(row?.council) === normaliseSpatialKey(raw);
  }) || null;
}

function wikiComparatorCouncilRow(rows, entitlement = {}) {
  const lookup = councilReferenceLookup();
  const candidates = [
    state.currentCouncil?.agreement_id,
    state.currentCouncil?.canonical_lga_short_name,
    state.currentCouncil?.geography?.short_name,
    state.currentCouncil?.fwc?.canonical_lga_short_name,
    state.wikiComparatorCouncilKey,
    entitlement?.target?.council,
    "Ballarat",
  ];
  for (const candidate of candidates) {
    const row = wikiFindCouncilEvidenceRow(rows, candidate, lookup);
    if (row) {
      state.wikiComparatorCouncilKey = wikiCouncilRowKey(row);
      return row;
    }
  }
  const fallback = rows.find((row) => wikiEvidenceKind(row) === "source_backed") || rows[0] || null;
  if (fallback) state.wikiComparatorCouncilKey = wikiCouncilRowKey(fallback);
  return fallback;
}

function wikiComparatorCouncilSelectHtml(rows, selectedRow) {
  const selectedKey = wikiCouncilRowKey(selectedRow);
  const options = [...rows]
    .sort((a, b) => String(a.council || "").localeCompare(String(b.council || "")))
    .map((row) => {
      const key = wikiCouncilRowKey(row);
      return `<option value="${escapeHtml(key)}" ${key === selectedKey ? "selected" : ""}>${escapeHtml(row.council || row.agreement_name || "Council")}</option>`;
    }).join("");
  return `
    <label class="wiki-infographic-select">
      <span>Comparator</span>
      <select data-wiki-comparator-council aria-label="Comparator council">
        ${options}
      </select>
    </label>
  `;
}

function wikiRowsForReferenceKeys(rows, keys, selectedRow, lookup = councilReferenceLookup()) {
  if (!keys?.size) return [];
  return rows.filter((row) => !wikiSameCouncilEvidenceRow(row, selectedRow) && keys.has(wikiEvidenceRowReferenceKey(row, lookup)));
}

function wikiRowsMatchingReference(rows, selectedRow, matcher, lookup = councilReferenceLookup()) {
  return rows.filter((row) => {
    if (wikiSameCouncilEvidenceRow(row, selectedRow)) return false;
    const ref = wikiCouncilReferenceForEvidenceRow(row, lookup);
    return Boolean(ref && matcher(ref, row));
  });
}

function buildWikiEntitlementCohorts(rows, selectedRow) {
  const lookup = councilReferenceLookup();
  const selectedRef = wikiCouncilReferenceForEvidenceRow(selectedRow, lookup);
  const selectedKey = wikiEvidenceRowReferenceKey(selectedRow, lookup);
  const selectedCategory = selectedRef?.council_category;
  const selectedLgprfGroup = selectedRef?.lgprf_group;
  const selectedSeifaBand = seifaPeerBand(selectedRef);
  const statewideRows = rows.filter((row) => !wikiSameCouncilEvidenceRow(row, selectedRow));
  const cohorts = [
    {
      key: "statewide",
      label: "Statewide",
      note: "all evidence rows",
      rows: statewideRows,
      baseline: true,
    },
    {
      key: "local_5",
      label: "Local 5",
      note: "nearest councils",
      rows: wikiRowsForReferenceKeys(rows, closestCouncilReferenceKeys(selectedKey, LOCAL_GROUP_SIZE), selectedRow, lookup),
    },
    {
      key: "local_12",
      label: "Local 12",
      note: "extended neighbours",
      rows: wikiRowsForReferenceKeys(rows, closestCouncilReferenceKeys(selectedKey, EXTENDED_LOCAL_GROUP_SIZE), selectedRow, lookup),
    },
    {
      key: "lgv_category",
      label: selectedCategory ? `LGV ${selectedCategory}` : "LGV category",
      note: "same category",
      rows: selectedCategory
        ? wikiRowsMatchingReference(rows, selectedRow, (ref) => ref.council_category === selectedCategory, lookup)
        : [],
    },
    {
      key: "regional_victoria",
      label: "Regional Victoria",
      note: "non-metro set",
      rows: wikiRowsMatchingReference(rows, selectedRow, (ref) => isRegionalVictoriaCouncil(ref), lookup),
    },
    {
      key: "lgprf_group",
      label: selectedLgprfGroup ? `LGPRF ${selectedLgprfGroup}` : "LGPRF group",
      note: "performance peer",
      rows: selectedLgprfGroup
        ? wikiRowsMatchingReference(rows, selectedRow, (ref) => ref.lgprf_group === selectedLgprfGroup, lookup)
        : [],
    },
    {
      key: "seifa_peer",
      label: selectedSeifaBand?.label || "SEIFA peer band",
      note: "socioeconomic peer",
      rows: selectedSeifaBand
        ? wikiRowsMatchingReference(rows, selectedRow, (ref) => seifaPeerBand(ref)?.key === selectedSeifaBand.key, lookup)
        : [],
    },
  ];
  return WIKI_COHORT_KEYS.map((key) => cohorts.find((cohort) => cohort.key === key)).filter(Boolean);
}

function wikiSelectedEntitlementCohort(cohorts) {
  const selected = cohorts.find((cohort) => cohort.key === state.wikiComparatorCohortKey);
  if (selected) return selected;
  state.wikiComparatorCohortKey = WIKI_DEFAULT_COHORT_KEY;
  return cohorts.find((cohort) => cohort.key === WIKI_DEFAULT_COHORT_KEY) || cohorts[0] || null;
}

function wikiBenchmarkStats(rows) {
  const counts = rows.reduce((acc, row) => {
    acc[wikiEvidenceKind(row)] = (acc[wikiEvidenceKind(row)] || 0) + 1;
    acc.valueCount += wikiAsArray(row.normalised_values).length;
    wikiAsArray(row.observed_subclasses).forEach((subclass) => {
      const relationship = String(subclass.relationship || "");
      if (relationship && !relationship.includes("accepted")) return;
      const label = subclass.label || subclass.subclass_id;
      if (!label) return;
      acc.subclasses.set(label, (acc.subclasses.get(label) || 0) + 1);
    });
    return acc;
  }, {
    source_backed: 0,
    outside_boundary: 0,
    no_candidate: 0,
    pending_latest: 0,
    valueCount: 0,
    subclasses: new Map(),
  });
  const topSubclass = [...counts.subclasses.entries()]
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))[0];
  return {
    count: rows.length,
    sourceBacked: counts.source_backed || 0,
    outsideBoundary: counts.outside_boundary || 0,
    noCandidate: counts.no_candidate || 0,
    pendingLatest: counts.pending_latest || 0,
    valueCount: counts.valueCount || 0,
    sourceBackedPercent: rows.length ? ((counts.source_backed || 0) / rows.length) * 100 : 0,
    topSubclass: topSubclass ? { label: topSubclass[0], count: topSubclass[1] } : null,
  };
}

function wikiSourceEvidenceSummaryForRows(rows, baseSummary = {}) {
  const sourceRows = wikiAsArray(rows);
  const candidateSubclassCounts = {};
  let sourceBacked = 0;
  let noCandidate = 0;
  let outsideBoundary = 0;
  let pendingLatest = 0;
  let candidatePages = 0;
  let sourceClausePages = 0;
  let normalisedValues = 0;
  let pagesScanned = 0;
  sourceRows.forEach((row) => {
    const kind = wikiEvidenceKind(row);
    if (kind === "source_backed") sourceBacked += 1;
    if (kind === "no_candidate") noCandidate += 1;
    if (kind === "outside_boundary") outsideBoundary += 1;
    if (kind === "pending_latest") pendingLatest += 1;
    candidatePages += wikiEvidenceCandidatePageCount(row);
    sourceClausePages += Number(row?.source_clause_page_count || wikiAsArray(row?.source_excerpts || row?.source_evidence?.source_excerpts).length || 0);
    normalisedValues += wikiAsArray(row?.normalised_values).length;
    pagesScanned += Number(row?.page_count || 0);
    wikiAsArray(row?.observed_subclasses || row?.source_evidence?.observed_subclasses).forEach((subclass) => {
      const label = subclass.label || subclass.subclass_id;
      if (!label) return;
      candidateSubclassCounts[label] = (candidateSubclassCounts[label] || 0) + 1;
    });
  });
  const remaining = Math.max(0, sourceRows.length - sourceBacked);
  return {
    ...baseSummary,
    councils: sourceRows.length,
    total_pages_scanned: pagesScanned || baseSummary.total_pages_scanned,
    candidate_pages_found: candidatePages,
    source_clause_pages: sourceClausePages,
    positive_candidate_pages: sourceClausePages,
    normalised_values_extracted: normalisedValues,
    candidate_subclass_counts: candidateSubclassCounts,
    presence_counts: {
      source_clause_observed: sourceBacked,
      no_source_clause_match: remaining,
    },
    support_status_counts: {
      source_clause_supported: sourceBacked,
      source_search_no_positive_match: remaining,
    },
    source_clause_observed: sourceBacked,
    source_search_no_positive_match: remaining,
    rows_needing_absence_or_scope_automation: remaining,
    rows_with_no_candidate_pages: noCandidate,
    rows_with_only_out_of_scope_candidates: outsideBoundary,
    rows_with_pending_latest_search: pendingLatest,
    row_source_backed_percent: sourceRows.length ? (sourceBacked / sourceRows.length) * 100 : 0,
    row_remaining_automation_percent: sourceRows.length ? (remaining / sourceRows.length) * 100 : 0,
    candidate_page_positive_percent: candidatePages ? (sourceClausePages / candidatePages) * 100 : 0,
  };
}

function wikiLandscapeCoverageLabel(percent) {
  const value = Number(percent || 0);
  if (value <= 0) return "not yet observed";
  if (value < 10) return "rare";
  if (value < 25) return "narrow";
  if (value < 50) return "minority";
  if (value < 75) return "mixed";
  return "common";
}

function wikiSelectedCouncilConclusion(row, statewideStats, cohortStats, cohortLabel, entitlementLabel) {
  const council = row?.council || "The selected council";
  const kind = wikiEvidenceKind(row);
  const statewideLabel = wikiLandscapeCoverageLabel(statewideStats?.sourceBackedPercent);
  const cohortBacked = Number(cohortStats?.sourceBacked || 0);
  const cohortCount = Number(cohortStats?.count || 0);
  if (kind === "source_backed") {
    return `${council} has source-backed ${entitlementLabel} in its latest agreement. Against the statewide landscape this sits inside a ${statewideLabel} above-baseline pattern; in ${cohortLabel}, ${cohortBacked} of ${cohortCount} comparator councils are source-backed.`;
  }
  if (kind === "pending_latest") {
    return `${council}'s latest agreement is in the workbench register, but this entitlement has not been processed against that agreement yet. It should stay visible, but its relationship to the statewide and ${cohortLabel} benchmark is not decision-ready.`;
  }
  if (kind === "outside_boundary") {
    return `${council}'s latest processed material has related annual-leave language, but it is currently classified outside this entitlement boundary. That means the council does not yet have a supportable above-baseline ${entitlementLabel} result for comparison.`;
  }
  return `${council}'s latest processed material has no candidate text for this entitlement. On the current evidence, it aligns with the non-source-backed part of a ${statewideLabel} statewide pattern.`;
}

function wikiStatewideLandscapeConclusion(entitlementLabel, stats) {
  const count = Number(stats?.count || 0);
  const sourceBacked = Number(stats?.sourceBacked || 0);
  const pending = Number(stats?.pendingLatest || 0);
  const coverage = wikiLandscapeCoverageLabel(stats?.sourceBackedPercent);
  if (!count) return `No statewide landscape has been built for ${entitlementLabel} yet.`;
  const pendingLine = pending
    ? ` ${pending} latest agreement${pending === 1 ? " is" : "s are"} still pending entitlement processing, so the landscape is useful but not complete.`
    : " Every visible row has been reduced to a latest-agreement evidence state.";
  return `Statewide, ${sourceBacked} of ${count} current council agreements are source-backed for ${entitlementLabel}, making it a ${coverage} above-baseline condition rather than a universal entitlement.${pendingLine}`;
}

function wikiCohortLandscapeConclusion(entitlementLabel, cohort, stats) {
  const label = cohort?.label || "Selected cohort";
  const count = Number(stats?.count || 0);
  const sourceBacked = Number(stats?.sourceBacked || 0);
  const pending = Number(stats?.pendingLatest || 0);
  if (!count) return `${label} has no benchmark rows available for ${entitlementLabel} under the current council selection.`;
  const coverage = wikiLandscapeCoverageLabel(stats?.sourceBackedPercent);
  const pendingLine = pending ? ` ${pending} peer row${pending === 1 ? " is" : "s are"} pending latest-agreement processing.` : "";
  return `${label} has ${sourceBacked} of ${count} peer agreements source-backed for ${entitlementLabel}, so this pivot currently reads as a ${coverage} cohort signal.${pendingLine}`;
}

function wikiEntitlementLandscapeDataset(entitlement, baseSummary = {}) {
  const rows = wikiLatestCouncilEvidenceRows(entitlement?.council_evidence);
  const selectedRow = wikiComparatorCouncilRow(rows, entitlement);
  const cohorts = buildWikiEntitlementCohorts(rows, selectedRow);
  const selectedCohort = wikiSelectedEntitlementCohort(cohorts);
  const statewideSummary = wikiBenchmarkStats(rows);
  const selectedCohortSummary = wikiBenchmarkStats(selectedCohort?.rows || []);
  const sourceSummary = wikiSourceEvidenceSummaryForRows(rows, baseSummary);
  const label = entitlement?.label || "this entitlement";
  const conclusions = {
    statewide: wikiStatewideLandscapeConclusion(label, statewideSummary),
    selected_council: wikiSelectedCouncilConclusion(selectedRow, statewideSummary, selectedCohortSummary, selectedCohort?.label || "selected cohort", label),
    selected_cohort: wikiCohortLandscapeConclusion(label, selectedCohort, selectedCohortSummary),
  };
  return {
    schema_version: "wiki.entitlement_landscape_dataset.v1",
    entitlement,
    rows,
    selected_row: selectedRow,
    cohorts,
    selected_cohort: selectedCohort,
    statewide_summary: statewideSummary,
    selected_cohort_summary: selectedCohortSummary,
    source_summary: sourceSummary,
    plain_english_conclusions: conclusions,
  };
}

function wikiLandscapeConclusionHtml(landscape) {
  const conclusions = landscape?.plain_english_conclusions || {};
  const cards = [
    ["Statewide", conclusions.statewide],
    ["Selected council", conclusions.selected_council],
    ["Cohort lens", conclusions.selected_cohort],
  ].filter(([, text]) => text);
  if (!cards.length) return "";
  return `
    <div class="wiki-landscape-conclusions">
      ${cards.map(([label, text]) => `
        <article>
          <span>${escapeHtml(label)}</span>
          <p>${escapeHtml(text)}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function wikiBenchmarkDotFieldHtml(rows) {
  const order = { source_backed: 0, outside_boundary: 1, no_candidate: 2, pending_latest: 3, missing: 4 };
  const dots = [...rows]
    .sort((a, b) => (order[wikiEvidenceKind(a)] ?? 9) - (order[wikiEvidenceKind(b)] ?? 9)
      || String(a.council || "").localeCompare(String(b.council || "")))
    .slice(0, 140);
  if (!dots.length) {
    return `<div class="wiki-infographic-rail is-empty"><span>No benchmark rows in this cohort</span></div>`;
  }
  return `
    <div class="wiki-infographic-rail" aria-label="Benchmark cohort evidence state">
      ${dots.map((row) => {
    const kind = wikiEvidenceKind(row);
    return `<span class="wiki-benchmark-dot wiki-benchmark-dot-${escapeHtml(wikiEvidenceKindClass(kind))}" data-evidence-kind="${escapeHtml(kind)}" style="${escapeHtml(wikiEvidenceKindStyle(kind))}" title="${escapeHtml(`${row.council || "Council"}: ${wikiEvidenceKindLabel(kind)}`)}"></span>`;
  }).join("")}
    </div>
  `;
}

function wikiCohortSelectorHtml(cohorts, selectedKey) {
  return `
    <div class="wiki-cohort-selector" aria-label="Benchmark cohort">
      ${cohorts.map((cohort) => {
    const selected = cohort.key === selectedKey;
    return `
        <button type="button" class="wiki-cohort-option wiki-cohort-${escapeHtml(cohort.key)}${selected ? " is-active" : ""}" data-wiki-cohort-key="${escapeHtml(cohort.key)}" aria-pressed="${selected ? "true" : "false"}">
          <span>${escapeHtml(cohort.label)}</span>
          <strong>${formatCount(cohort.rows.length, "0")}</strong>
          <small>${escapeHtml(cohort.note)}</small>
        </button>
      `;
  }).join("")}
    </div>
  `;
}

function wikiComparatorInfographicHtml(landscape) {
  const entitlement = landscape?.entitlement || {};
  const rows = wikiAsArray(landscape?.rows);
  if (!rows.length) return "";
  const selectedRow = landscape?.selected_row || wikiComparatorCouncilRow(rows, entitlement);
  const cohorts = wikiAsArray(landscape?.cohorts);
  const selectedCohort = landscape?.selected_cohort || wikiSelectedEntitlementCohort(cohorts);
  const benchmarkRows = selectedCohort?.rows || [];
  const stats = landscape?.selected_cohort_summary || wikiBenchmarkStats(benchmarkRows);
  const selectedKind = wikiEvidenceKind(selectedRow);
  const selectedValues = wikiAsArray(selectedRow?.normalised_values).map(wikiNormalisedValueText).filter(Boolean).slice(0, 3);
  const selectedFinding = selectedRow?.finding || "No comparator row is available for this entitlement.";
  const topSubclassLine = stats.topSubclass
    ? `${stats.topSubclass.label} is the most common source-backed subclass in this cohort.`
    : "No source-backed subclass has emerged in this cohort yet.";
  return `
    <section class="wiki-comparator-infographic" aria-label="Comparator Lens">
      <div class="wiki-infographic-topline">
        <div>
          <span>Comparator Lens</span>
          <h4>${escapeHtml(selectedRow?.council || "Selected council")} against ${escapeHtml(selectedCohort?.label || "benchmark cohort")}</h4>
        </div>
        <div class="wiki-infographic-controls">
          ${wikiComparatorCouncilSelectHtml(rows, selectedRow)}
          ${wikiCohortSelectorHtml(cohorts, selectedCohort?.key)}
        </div>
      </div>
      <div class="wiki-infographic-body">
        <aside class="wiki-infographic-council">
          <span>Selected council</span>
          <strong>${escapeHtml(selectedRow?.council || DISPLAY_EMPTY)}</strong>
          <em class="wiki-infographic-status wiki-infographic-status-${escapeHtml(wikiEvidenceKindClass(selectedKind))}">${escapeHtml(wikiEvidenceKindLabel(selectedKind))}</em>
          <p>${escapeHtml(selectedFinding)}</p>
          ${selectedValues.length ? `
            <div class="wiki-infographic-value-list">
              ${selectedValues.map((value) => `<i>${escapeHtml(value)}</i>`).join("")}
            </div>
          ` : `<div class="wiki-infographic-value-list"><i>No source-backed value</i></div>`}
        </aside>
        <div class="wiki-infographic-benchmark">
          <div class="wiki-infographic-statline">
            <span>Source-backed in cohort</span>
            <strong>${formatCount(stats.sourceBacked, "0")}</strong>
            <small>of ${formatCount(stats.count, "0")} rows / ${escapeHtml(displayPercent(stats.sourceBackedPercent, "0%"))}</small>
          </div>
          ${wikiBenchmarkDotFieldHtml(benchmarkRows)}
          <div class="wiki-infographic-legend">
            <span><i class="wiki-benchmark-dot-source-backed"></i>Included above baseline</span>
            <span><i class="wiki-benchmark-dot-outside-boundary"></i>Context only</span>
            <span><i class="wiki-benchmark-dot-no-candidate"></i>No candidate text</span>
            <span><i class="wiki-benchmark-dot-pending-latest"></i>Pending latest search</span>
          </div>
          <div class="wiki-infographic-mini-stats">
            <div><span>Context only</span><strong>${formatCount(stats.outsideBoundary, "0")}</strong></div>
            <div><span>No candidate</span><strong>${formatCount(stats.noCandidate, "0")}</strong></div>
            <div><span>Pending</span><strong>${formatCount(stats.pendingLatest, "0")}</strong></div>
            <div><span>Values</span><strong>${formatCount(stats.valueCount, "0")}</strong></div>
            <div><span>Benchmark</span><strong>${formatCount(stats.count, "0")}</strong></div>
          </div>
          <p>${escapeHtml(topSubclassLine)} Benchmark rows exclude the selected comparator council.</p>
        </div>
      </div>
      ${wikiLandscapeConclusionHtml(landscape)}
    </section>
  `;
}

function wikiCouncilEvidenceHtml(evidence) {
  const rows = wikiAsArray(evidence).slice(0, 160);
  if (!rows.length) {
    return renderEmptyState("No council evidence", "Council evidence will appear when this entitlement is mapped to comparator agreements.", { eyebrow: "Evidence" });
  }
  return rows.map((item) => {
    const quantum = wikiAsArray(item.quantum_signals).slice(0, 4);
    const values = wikiAsArray(item.normalised_values).slice(0, 3);
    const sourceLabel = wikiSourceRefLabel(item.source_ref);
    const sourceEvidence = item.source_evidence || {};
    const subclasses = wikiAsArray(sourceEvidence.observed_subclasses || item.observed_subclasses).slice(0, 2);
    const scope = item.scope && item.scope !== "standard_employees" ? `<span>${escapeHtml(wikiDisplayLabel(item.scope))}</span>` : "";
    return `
      <article class="wiki-council-evidence-card">
        <div class="wiki-council-evidence-head">
          <strong>${escapeHtml(item.council || "Council")}</strong>
          <span>${escapeHtml(wikiDisplayLabel(item.presence, "Evidence"))}</span>
        </div>
        <p>${escapeHtml(item.finding || "")}</p>
        ${values.length ? `
          <div class="wiki-source-values">
            ${values.map((value) => `<span>${escapeHtml([value.value, value.unit, value.condition].filter(Boolean).join(" "))}</span>`).join("")}
          </div>
        ` : ""}
        ${wikiEvidencePackHtml(sourceEvidence, item, sourceLabel)}
        <footer>
          ${quantum.map((signal) => `<span>${escapeHtml(signal)}</span>`).join("")}
          ${subclasses.map((subclass) => `<span>${escapeHtml(subclass.label || subclass.subclass_id || "Subclass")}</span>`).join("")}
          ${sourceLabel && sourceLabel !== DISPLAY_EMPTY ? `<span>${escapeHtml(sourceLabel)}</span>` : ""}
          ${scope}
        </footer>
      </article>
    `;
  }).join("");
}

function wikiCouncilSummaryHtml(evidence) {
  const rows = wikiAsArray(evidence).slice(0, 160);
  if (!rows.length) {
    return renderEmptyState("No council summary", "Council summaries will appear when this entitlement is mapped across the comparator set.", { eyebrow: "Councils" });
  }
  return `
    <div class="wiki-council-summary-table">
      ${rows.map((item) => {
        const quantum = wikiAsArray(item.quantum_signals).slice(0, 2).join(", ");
        return `
          <div class="wiki-council-summary-row">
            <strong>${escapeHtml(item.council || "Council")}</strong>
            <span>${escapeHtml(wikiDisplayLabel(item.presence, "Evidence"))}</span>
            <p>${escapeHtml(item.finding || "")}</p>
            <small>${escapeHtml([quantum, wikiSourceRefLabel(item.source_ref)].filter((value) => value && value !== DISPLAY_EMPTY).join(" / ") || wikiDisplayLabel(item.scope || "standard_employees"))}</small>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function wikiAutomationMeasurementHtml(summary, abTest = {}) {
  if (!summary || typeof summary !== "object" || !Object.keys(summary).length) return "";
  const sourceBacked = Number(summary.source_clause_observed || 0);
  const remaining = Number(summary.rows_needing_absence_or_scope_automation || 0);
  const noCandidateRows = Number(summary.rows_with_no_candidate_pages || 0);
  const outOfScopeRows = Number(summary.rows_with_only_out_of_scope_candidates || 0);
  const pendingLatestRows = Number(summary.rows_with_pending_latest_search || 0);
  const needsReviewCandidates = Number(summary.candidate_subclass_counts?.["Needs Review"] || 0);
  const councils = Number(summary.councils || 0);
  const backedPct = summary.row_source_backed_percent ?? (councils ? (sourceBacked / councils) * 100 : 0);
  const remainingPct = summary.row_remaining_automation_percent ?? (councils ? (remaining / councils) * 100 : 0);
  const baseline = abTest && typeof abTest === "object" ? abTest.baseline || {} : {};
  const trainingVariant = abTest && typeof abTest === "object" ? abTest.training_variant || {} : {};
  const variant = abTest && typeof abTest === "object" ? abTest.variant || {} : {};
  const subclassCounts = summary.candidate_subclass_counts && typeof summary.candidate_subclass_counts === "object"
    ? Object.entries(summary.candidate_subclass_counts).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0)).slice(0, 4)
    : [];
  const abLine = Number(baseline.councils || 0) && Number(variant.councils || 0)
    ? `<p>${escapeHtml(abTest.baseline_label || "A baseline")}: ${formatCount(baseline.source_clause_observed, "0")}/${formatCount(baseline.councils, "0")} source-backed. ${Number(trainingVariant.councils || 0) ? `${escapeHtml(abTest.training_variant_label || "B training")}: ${formatCount(trainingVariant.source_clause_observed, "0")}/${formatCount(trainingVariant.councils, "0")}. ` : ""}${escapeHtml(abTest.variant_label || "Current variant")}: ${formatCount(variant.source_clause_observed, "0")}/${formatCount(variant.councils, "0")}.</p>`
    : "";
  const subclassLine = subclassCounts.length
    ? `<p>Held subclasses: ${subclassCounts.map(([label, count]) => `${escapeHtml(label)} (${formatCount(count, "0")})`).join(", ")}.</p>`
    : "";
  return `
    <section class="wiki-automation-measurement">
      <div class="wiki-entitlement-section-head">
        <h4>Automation Coverage</h4>
        <span>${escapeHtml(displayPercent(Number(backedPct || 0), "0"))} source backed</span>
      </div>
      <div class="wiki-automation-metrics">
        <div><span>Source backed</span><strong>${formatCount(sourceBacked, "0")}/${formatCount(councils, "0")}</strong></div>
        <div><span>Outside boundary</span><strong>${formatCount(outOfScopeRows, "0")}</strong></div>
        <div><span>No candidate text</span><strong>${formatCount(noCandidateRows, "0")}</strong></div>
        <div><span>Pending latest</span><strong>${formatCount(pendingLatestRows, "0")}</strong></div>
        <div><span>Needs review</span><strong>${formatCount(needsReviewCandidates, "0")}</strong></div>
        <div><span>Pages scanned</span><strong>${formatCount(summary.total_pages_scanned, "0")}</strong></div>
        <div><span>Candidate pages</span><strong>${formatCount(summary.candidate_pages_found, "0")}</strong></div>
      </div>
      <p>${escapeHtml(displayPercent(Number(remainingPct || 0), "0"))} are not source-backed for this entitlement: ${formatCount(outOfScopeRows, "0")} row${outOfScopeRows === 1 ? "" : "s"} classified outside the boundary, ${formatCount(noCandidateRows, "0")} with no candidate text, ${formatCount(pendingLatestRows, "0")} pending latest-agreement search, and ${formatCount(needsReviewCandidates, "0")} needing review.</p>
      ${abLine}
      ${subclassLine}
    </section>
  `;
}

function wikiEvidenceMethodHtml(methodology) {
  if (!methodology || typeof methodology !== "object" || !Object.keys(methodology).length) return "";
  const hitMethod = methodology.hit_discovery_method || {};
  const boundary = hitMethod.classification_boundary || methodology.classification_boundary || {};
  const terms = wikiAsArray(methodology.search_terms).slice(0, 12);
  const learnedPatterns = wikiAsArray(hitMethod.learned_hit_patterns).map((item) => item && typeof item === "object" ? item.label : item).filter(Boolean).slice(0, 10);
  const learnedRetest = methodology.learned_pattern_retest || {};
  const steps = wikiAsArray(hitMethod.pipeline).slice(0, 7);
  const acceptance = hitMethod.acceptance_rule || methodology.positive_match_rule;
  const reuse = hitMethod.reuse_rule || "";
  const boundaryGroups = [
    ["Included", wikiAsArray(boundary.included)],
    ["Excluded", wikiAsArray(boundary.excluded)],
    ["Needs Review", wikiAsArray(boundary.needs_review)],
  ].filter(([, rows]) => rows.length);
  return `
    <section class="wiki-evidence-method">
      <div class="wiki-entitlement-section-head">
        <h4>Evidence Method</h4>
        <span>${escapeHtml(wikiDisplayLabel(methodology.method, "Profiled search"))}</span>
      </div>
      ${boundary.canonical_definition ? `<p>${escapeHtml(boundary.canonical_definition)}</p>` : ""}
      ${boundaryGroups.length ? `
        <div class="wiki-boundary-grid">
          ${boundaryGroups.map(([label, rows]) => `
            <div>
              <strong>${escapeHtml(label)}</strong>
              <ul>${rows.slice(0, 6).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
            </div>
          `).join("")}
        </div>
      ` : ""}
      ${acceptance ? `<p>${escapeHtml(acceptance)}</p>` : ""}
      ${terms.length ? `<div class="wiki-method-chips">${terms.map((term) => `<span>${escapeHtml(term)}</span>`).join("")}</div>` : ""}
      ${learnedPatterns.length ? `
        <div class="wiki-method-subblock">
          <strong>Learned Patterns</strong>
          <div class="wiki-method-chips">${learnedPatterns.map((term) => `<span>${escapeHtml(wikiDisplayLabel(term))}</span>`).join("")}</div>
        </div>
      ` : ""}
      ${Number.isFinite(Number(learnedRetest.rows_retested)) ? `
        <p>${formatCount(learnedRetest.rows_with_learned_pattern_candidates, "0")} of ${formatCount(learnedRetest.rows_retested, "0")} non-converting row${Number(learnedRetest.rows_retested || 0) === 1 ? "" : "s"} had learned-pattern candidates on retest; ${formatCount(learnedRetest.current_rule_conversion_candidates, "0")} would convert under the current rule.</p>
      ` : ""}
      ${steps.length ? `
        <ol class="wiki-method-steps">
          ${steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}
        </ol>
      ` : ""}
      ${reuse ? `<p>${escapeHtml(reuse)}</p>` : ""}
    </section>
  `;
}

function renderWikiEntitlementDetail() {
  const container = document.getElementById("wiki-entitlement-detail");
  if (!container) return;
  const entitlement = wikiSelectedGoldEntitlement();
  if (!entitlement) {
    container.innerHTML = renderEmptyState("No entitlement selected", "Select an entitlement class to inspect definition, comparator evidence and quick takeaway.", { eyebrow: "Entitlement" });
    return;
  }
  state.wikiSelectedGoldEntitlementId = entitlement.entitlement_id;
  setText("wiki-entitlement-detail-title", entitlement.label || "Entitlement");
  setText("wiki-entitlement-detail-note", `${entitlement.category_label || entitlement.category || "Entitlement class"} / ${wikiDisplayLabel(entitlement.comparison_basis)}`);
  const quantification = entitlement.quantification || {};
  const target = entitlement.target || {};
  const supportability = entitlement.supportability || {};
  const analysis = entitlement.analysis || {};
  const landscape = wikiEntitlementLandscapeDataset(
    entitlement,
    analysis.source_evidence_summary || supportability.source_evidence_summary || {},
  );
  const councilEvidence = landscape.rows;
  const sourceSummary = landscape.source_summary;
  const sourceMethodology = analysis.source_evidence_methodology || supportability.source_evidence_methodology || {};
  const sourceAbTest = analysis.source_evidence_ab_test || supportability.source_evidence_ab_test || {};
  container.innerHTML = `
    <div class="wiki-entitlement-lede">
      <div>
        <span>${escapeHtml(wikiDisplayLabel(entitlement.category_label || entitlement.category, "Class"))}</span>
        <p>${escapeHtml(entitlement.definition || "No definition supplied yet.")}</p>
      </div>
      <div class="wiki-entitlement-status">
        <span>${escapeHtml(wikiDisplayLabel(target.comparator_posture, "Comparator posture"))}</span>
        <strong>${escapeHtml(wikiDisplayLabel(quantification.quantification_type, "Evidence"))}</strong>
      </div>
    </div>
    <section class="wiki-entitlement-summary-block">
      <div class="wiki-entitlement-section-head">
        <h4>Council Summary</h4>
        <span>${formatCount(councilEvidence.length, "0")} latest council agreements / ${escapeHtml(wikiDisplayLabel(target.presence))}</span>
      </div>
      ${wikiCouncilSummaryHtml(councilEvidence)}
    </section>
    <section class="wiki-entitlement-takeaway">
      <div class="wiki-entitlement-section-head">
        <h4>Global Takeaway</h4>
        <span>${escapeHtml(wikiDisplayLabel(target.comparator_posture, "Comparator posture"))}</span>
      </div>
      <p>${escapeHtml(landscape.plain_english_conclusions?.statewide || analysis.quick_takeaway || target.takeaway || "Analysis will appear once source-clause evidence is linked.")}</p>
    </section>
    ${wikiComparatorInfographicHtml(landscape)}
    ${wikiAutomationMeasurementHtml(sourceSummary, sourceAbTest)}
    ${wikiEvidenceMethodHtml(sourceMethodology)}
    <div class="wiki-detail-summary wiki-entitlement-summary">
      <div><span>Target</span><strong>${escapeHtml(target.council || DISPLAY_EMPTY)}</strong></div>
      <div><span>Quantification</span><strong>${escapeHtml(wikiDisplayLabel(quantification.quantification_type))}</strong></div>
      <div><span>Support</span><strong>${escapeHtml(wikiDisplayLabel(supportability.production_support_status || supportability.current_support_level))}</strong></div>
      <div><span>Next</span><strong>${escapeHtml(wikiDisplayLabel(analysis.next_state))}</strong></div>
    </div>
    <section>
      <h4>Evidence Details</h4>
      <div class="wiki-council-evidence-list">${wikiCouncilEvidenceHtml(councilEvidence)}</div>
    </section>
  `;
}

function renderWikiClauseDetail() {
  const container = document.getElementById("wiki-clause-detail");
  if (!container) return;
  const clause = wikiSelectedClauseNode();
  if (!clause) {
    container.innerHTML = renderEmptyState("No clause family selected", "Select a library category to inspect its source evidence and substructure.", { eyebrow: "Clause map" });
    return;
  }
  state.wikiSelectedClauseId = clause.id;
  const category = wikiCategoryForClause(clause.id);
  setText("wiki-clause-detail-title", clause.label || "Clause family");
  setText("wiki-clause-detail-note", category?.label || "Global clause library");
  container.innerHTML = `
    <div class="wiki-clause-detail-lede">
      <p>${escapeHtml(clause.description || "A global clause family collected from agreement maps and reference inputs.")}</p>
      <div class="wiki-detail-summary">
        <div><span>Evidence</span><strong>${formatCount(clause.evidence_count, "0")}</strong></div>
        <div><span>Sections</span><strong>${formatCount(clause.section_count, "0")}</strong></div>
        <div><span>Sources</span><strong>${formatCount(clause.source_count, "0")}</strong></div>
        <div><span>Language</span><strong>${formatCount(clause.language_term_count, "0")}</strong></div>
      </div>
    </div>
    <div class="wiki-detail-columns">
      <section>
        <h4>Subcategory Tags</h4>
        <div class="wiki-chip-cloud">
          ${wikiAsArray(clause.tags).length ? wikiAsArray(clause.tags).map((tag) => `<span class="wiki-clause-chip">${escapeHtml(wikiDisplayLabel(tag))}</span>`).join("") : `<span class="wiki-muted">No tags yet</span>`}
        </div>
      </section>
      <section>
        <h4>Observed Language</h4>
        <div class="wiki-observed-terms">${wikiObservedTermsHtml(clause.observed_terms)}</div>
      </section>
    </div>
    <div class="wiki-clause-library-grid">
      <section>
        <h4>Source Links</h4>
        <div class="wiki-source-list">${wikiSourceListHtml(clause.sources, 10)}</div>
      </section>
      <section>
        <h4>Evidence Examples</h4>
        <div class="wiki-section-strip">${wikiExamplesHtml(clause.examples)}</div>
      </section>
    </div>
  `;
}

function wikiFilterOptionHtml(value, label, selectedValue, count = null) {
  const selected = String(value) === String(selectedValue) ? "selected" : "";
  const countLabel = count === null || count === undefined ? "" : ` (${formatCount(count, "0")})`;
  return `<option value="${escapeHtml(value)}" ${selected}>${escapeHtml(label)}${escapeHtml(countLabel)}</option>`;
}

function renderWikiTagFilters() {
  const tagSelect = document.getElementById("wiki-tag-filter");
  const sourceTypeSelect = document.getElementById("wiki-tag-source-type");
  const recordTypeSelect = document.getElementById("wiki-tag-record-type");
  const relevanceSelect = document.getElementById("wiki-tag-relevance");
  const queryInput = document.getElementById("wiki-tag-query");
  const tags = wikiTagRegistryRows();
  if (!state.wikiTagFilter && tags.length) state.wikiTagFilter = tags[0].tag;
  if (tagSelect) {
    tagSelect.innerHTML = [
      wikiFilterOptionHtml("all", "All tags", state.wikiTagFilter, state.wikiTagRegistry?.summary?.tagged_records),
      ...tags.map((tag) => wikiFilterOptionHtml(tag.tag, `${wikiDisplayLabel(tag.tag)} / ${tag.family_label}`, state.wikiTagFilter, tag.record_count)),
    ].join("");
    tagSelect.value = state.wikiTagFilter || "all";
  }
  if (sourceTypeSelect) {
    sourceTypeSelect.innerHTML = [
      wikiFilterOptionHtml("all", "All sources", state.wikiTagSourceType, state.wikiTagRegistry?.summary?.tagged_records),
      ...wikiTagDimensionValues("source_type").map((item) => wikiFilterOptionHtml(item.value, item.label || wikiDisplayLabel(item.value), state.wikiTagSourceType, item.record_count)),
    ].join("");
    sourceTypeSelect.value = state.wikiTagSourceType || "all";
  }
  if (recordTypeSelect) {
    recordTypeSelect.innerHTML = [
      wikiFilterOptionHtml("all", "Pages and sections", state.wikiTagRecordType),
      ...wikiTagDimensionValues("record_type").map((item) => wikiFilterOptionHtml(item.value, item.label || wikiDisplayLabel(item.value), state.wikiTagRecordType, item.record_count)),
    ].join("");
    recordTypeSelect.value = state.wikiTagRecordType || "all";
  }
  if (relevanceSelect) {
    relevanceSelect.innerHTML = [
      wikiFilterOptionHtml("all", "All relevance", state.wikiTagRelevance),
      ...wikiTagDimensionValues("clause_context_relevance").map((item) => wikiFilterOptionHtml(item.value, item.label || wikiDisplayLabel(item.value), state.wikiTagRelevance, item.record_count)),
    ].join("");
    relevanceSelect.value = state.wikiTagRelevance || "all";
  }
  if (queryInput) queryInput.value = state.wikiTagQuery || "";
}

function renderWikiTagRegistrySummary() {
  const container = document.getElementById("wiki-tag-summary");
  if (!container) return;
  const summary = state.wikiTagRegistry?.summary || {};
  const topTags = wikiTagRegistryRows().slice(0, 10);
  const families = wikiTagRegistryFamilies();
  container.innerHTML = `
    <div class="wiki-detail-summary wiki-tag-summary-metrics">
      <div><span>Sources</span><strong>${formatCount(summary.source_records, "0")}</strong></div>
      <div><span>Tags</span><strong>${formatCount(summary.tags, "0")}</strong></div>
      <div><span>Records</span><strong>${formatCount(summary.tagged_records, "0")}</strong></div>
      <div><span>Proposals</span><strong>${formatCount(summary.discovery_proposals, "0")}</strong></div>
    </div>
    <div class="wiki-tag-family-strip">
      ${families.map((family) => `
        <span>${escapeHtml(family.label || wikiDisplayLabel(family.family))}<strong>${formatCount(family.tag_count, "0")}</strong></span>
      `).join("")}
    </div>
    <div class="wiki-chip-cloud">
      ${topTags.map((tag) => `
        <button type="button" class="wiki-tag-chip-button${tag.tag === state.wikiTagFilter ? " is-active" : ""}" data-wiki-tag-pick="${escapeHtml(tag.tag)}">
          ${escapeHtml(wikiDisplayLabel(tag.tag))}
          <strong>${formatCount(tag.record_count, "0")}</strong>
        </button>
      `).join("")}
    </div>
  `;
}

function wikiTaggedEvidenceCardHtml(row) {
  const title = row.title || row.heading || "Tagged source";
  const sourceLabel = [wikiDisplayLabel(row.source_type), row.source_name || row.source_id, row.page ? `p.${row.page}` : ""]
    .filter(Boolean)
    .join(" / ");
  const relevance = wikiRecordRelevance(row);
  return `
    <article class="wiki-tag-evidence-card">
      <div class="wiki-tag-evidence-head">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(sourceLabel || DISPLAY_EMPTY)}</span>
        </div>
        <em class="wiki-relevance wiki-relevance-${escapeHtml(relevance)}">${escapeHtml(wikiDisplayLabel(relevance))}</em>
      </div>
      ${row.evidence_excerpt ? `<p>${escapeHtml(row.evidence_excerpt)}</p>` : ""}
      <div class="wiki-tag-list">${wikiTagPills(row.tags, 8)}</div>
      <footer>
        <span>${escapeHtml(wikiDisplayLabel(row.record_type))}</span>
        ${row.page_role ? `<span>${escapeHtml(wikiDisplayLabel(row.page_role))}</span>` : ""}
        ${row.source_container_type ? `<span>${escapeHtml(wikiDisplayLabel(row.source_container_type))}</span>` : ""}
        ${row.review_state ? `<span>${escapeHtml(wikiDisplayLabel(row.review_state))}</span>` : ""}
      </footer>
    </article>
  `;
}

function renderWikiTaggedEvidenceList() {
  const container = document.getElementById("wiki-tag-evidence-list");
  if (!container) return;
  const payload = state.wikiTaggedEvidence || {};
  const rows = wikiTaggedEvidenceRows();
  const summary = payload.summary || {};
  const total = Number(summary.total || rows.length || 0);
  setText("wiki-tag-evidence-note", `${formatCount(rows.length, "0")} of ${formatCount(total, "0")} records`);
  if (!rows.length) {
    container.innerHTML = renderEmptyState("No tagged evidence", "No source records match the current tag filters.", { eyebrow: "Tags" });
    return;
  }
  const hasMore = Boolean(summary.has_more);
  container.innerHTML = `
    <div class="wiki-tag-evidence-scroll">
      ${rows.map((row) => wikiTaggedEvidenceCardHtml(row)).join("")}
    </div>
    ${hasMore ? `<button type="button" class="wiki-tag-more" data-wiki-tag-more>Load more</button>` : ""}
  `;
}

async function renderWikiTagExplorer({ force = false, append = false } = {}) {
  const container = document.getElementById("wiki-tag-evidence-list");
  if (!container) return;
  renderWikiTagFilters();
  renderWikiTagRegistrySummary();
  if (!append) {
    container.innerHTML = `<div class="wiki-loading-row">Loading tagged evidence...</div>`;
  }
  try {
    await loadWikiTaggedEvidence({ force, append });
    renderWikiTaggedEvidenceList();
  } catch (error) {
    setText("wiki-tag-evidence-note", "Tag load failed");
    container.innerHTML = renderEmptyState("Tagged evidence unavailable", apiErrorMessage(error), { eyebrow: "Tags" });
  }
}

function renderWikiMapSelect() {
  const select = document.getElementById("wiki-map-select");
  if (!select) return;
  const rows = wikiDocumentMapRows();
  if (!state.wikiSelectedAeId && rows.length) {
    state.wikiSelectedAeId = String(rows[0].agreement_id || "").toLowerCase();
  }
  select.innerHTML = rows.map((row) => {
    const aeId = String(row.agreement_id || "").toLowerCase();
    const label = `${String(row.agreement_id || "").toUpperCase()} - ${row.agreement_name || "Agreement map"}`;
    return `<option value="${escapeHtml(aeId)}">${escapeHtml(label)}</option>`;
  }).join("");
  select.value = state.wikiSelectedAeId;
}

function renderWikiDocumentMaps() {
  const container = document.getElementById("wiki-document-maps");
  if (!container) return;
  const rows = wikiDocumentMapRows();
  renderWikiMapSelect();
  if (!rows.length) {
    container.innerHTML = renderEmptyState("No agreement evidence", "Mapped council agreements will appear here as evidence sources for the global clause library.", { eyebrow: "Source evidence" });
    return;
  }
  container.innerHTML = rows.map((row) => {
    const aeId = String(row.agreement_id || "").toLowerCase();
    const summary = row.summary || {};
    const active = aeId === state.wikiSelectedAeId ? " is-active" : "";
    return `
      <article class="wiki-map-card${active}" data-wiki-open-map="${escapeHtml(aeId)}">
        <div class="wiki-map-card-head">
          <div>
            <span>${escapeHtml(String(row.agreement_id || "").toUpperCase())}</span>
            <h3>${escapeHtml(row.agreement_name || "Agreement map")}</h3>
          </div>
        </div>
        <div class="wiki-map-card-meta">
          <span>${formatCount(summary.pages_scanned, "0")} pages</span>
          <span>${formatCount(summary.sections_detected, "0")} sections</span>
          <span>${formatCount(summary.questions, "0")} questions</span>
        </div>
        <div class="wiki-map-card-tags">${wikiTopClauseHtml(summary, 4)}</div>
      </article>
    `;
  }).join("");
}

function renderWikiQuestionList() {
  const container = document.getElementById("wiki-question-list");
  if (!container) return;
  const rows = wikiQuestionRows();
  setText("wiki-question-note", `${formatCount(rows.length, "0")} open`);
  if (!rows.length) {
    container.innerHTML = renderEmptyState("No direction questions", "The latest wiki run did not raise operator questions.", { eyebrow: "Questions" });
    return;
  }
  container.innerHTML = rows.slice(0, 14).map((item) => `
    <article class="wiki-work-item wiki-work-item-${escapeHtml(item.priority || "medium")}">
      <div class="wiki-work-item-head">
        <span>${escapeHtml(wikiDisplayLabel(item.priority || "medium"))}</span>
        <small>${escapeHtml(wikiSourceRefLabel(item.source_ref))}</small>
      </div>
      <p>${escapeHtml(item.prompt || item.code || "Question requires review.")}</p>
      <footer>${escapeHtml(wikiDisplayLabel(item.code || item.question_type))}</footer>
    </article>
  `).join("");
}

function renderWikiBacklogList() {
  const container = document.getElementById("wiki-backlog-list");
  if (!container) return;
  const rows = wikiBacklogRows();
  setText("wiki-backlog-note", `${formatCount(rows.length, "0")} observed`);
  if (!rows.length) {
    container.innerHTML = renderEmptyState("No learning backlog", "The latest wiki run did not add learning items.", { eyebrow: "Backlog" });
    return;
  }
  container.innerHTML = rows.slice(0, 14).map((item) => `
    <article class="wiki-work-item wiki-work-item-${escapeHtml(item.priority || "medium")}">
      <div class="wiki-work-item-head">
        <span>${escapeHtml(wikiDisplayLabel(item.priority || "medium"))}</span>
        <small>${escapeHtml(wikiSourceRefLabel(item.source_ref))}</small>
      </div>
      <p>${escapeHtml(item.description || item.code || "Learning item requires review.")}</p>
      <footer>${escapeHtml(wikiDisplayLabel(item.code || item.item_type))}</footer>
    </article>
  `).join("");
}

function renderWikiArtifacts() {
  const container = document.getElementById("wiki-artifact-list");
  if (!container) return;
  const rows = wikiArtifactRows();
  setText("wiki-artifact-note", `${formatCount(rows.length, "0")} files`);
  if (!rows.length) {
    container.innerHTML = renderEmptyState("No wiki artifacts yet", "This pilot is still in mapping mode. Supporting documents will appear here as they are generated.", { eyebrow: "Artifacts" });
    return;
  }
  container.innerHTML = rows.slice(0, 12).map((item) => {
    const title = item.title || item.artifact_id || item.relative_path || item.path || "artifact";
    const role = item.wiki_role || item.artifact_type || item.schema_version || "wiki_artifact";
    const summaryLine = wikiArtifactSummaryLine(item);
    return `
      <article class="wiki-artifact-card">
        <div class="wiki-artifact-head">
          <strong>${escapeHtml(title)}</strong>
          <span>${escapeHtml(wikiDisplayLabel(role))}</span>
        </div>
        ${summaryLine ? `<p>${escapeHtml(summaryLine)}</p>` : ""}
        <small>${escapeHtml(item.relative_path || item.path || "")} / ${escapeHtml(displayFileSize(item.bytes || item.size, DISPLAY_EMPTY))}</small>
      </article>
    `;
  }).join("");
}

function wikiPageRowsHtml(pages) {
  const visiblePages = pages
    .filter((page) => (page.clause_context_relevance || page.standard_band_relevance) !== "none");
  if (!visiblePages.length) {
    return renderEmptyState("No tagged pages", "This document map has no pages tagged for clause or context review.", { eyebrow: "Pages" });
  }
  return `
    <div class="wiki-table-wrap">
      <table class="wiki-map-table">
        <thead>
          <tr>
            <th>Page</th>
            <th>Relevance</th>
            <th>Detected tags</th>
            <th>Headings</th>
          </tr>
        </thead>
        <tbody>
          ${visiblePages.map((page) => {
            const relevance = wikiRecordRelevance(page);
            return `
            <tr>
              <td>p.${escapeHtml(page.page || "")}</td>
              <td><span class="wiki-relevance wiki-relevance-${escapeHtml(relevance)}">${escapeHtml(wikiDisplayLabel(relevance))}</span></td>
              <td><div class="wiki-tag-list">${wikiTagPills(page.tags, 4)}</div></td>
              <td>${formatCount(page.heading_count, "0")}</td>
            </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function wikiSectionRowsHtml(sections) {
  const visibleSections = sections
    .filter((section) => (section.clause_context_relevance || section.standard_band_relevance) !== "none");
  if (!visibleSections.length) return "";
  return `
    <div class="wiki-section-strip">
      ${visibleSections.map((section) => `
        <article class="wiki-section-card">
          <div>
            <strong>${escapeHtml(section.title || section.heading || "Detected section")}</strong>
            <span>${escapeHtml(wikiSourceRefLabel(section.source_ref))} / ${escapeHtml(wikiDisplayLabel(wikiRecordRelevance(section)))}</span>
          </div>
          <p>${escapeHtml(section.evidence_excerpt || "")}</p>
        </article>
      `).join("")}
    </div>
  `;
}

async function renderWikiMapDetail({ force = false } = {}) {
  const container = document.getElementById("wiki-map-detail");
  if (!container) return;
  const rows = wikiDocumentMapRows();
  const aeId = state.wikiSelectedAeId || String(rows[0]?.agreement_id || "").toLowerCase();
  if (!aeId) {
    setText("wiki-map-detail-title", "Document Map");
    setText("wiki-map-detail-note", "No agreement selected");
    container.innerHTML = renderEmptyState("No agreement selected", "Choose a mapped agreement to inspect clause tags, context signals and source sections.", { eyebrow: "Document map" });
    return;
  }
  state.wikiSelectedAeId = aeId;
  setText("wiki-map-detail-title", String(aeId).toUpperCase());
  setText("wiki-map-detail-note", "Loading document map...");
  container.innerHTML = `<div class="wiki-loading-row">Loading document map...</div>`;
  try {
    const detail = await ensureWikiDocumentMapDetail(aeId, { force });
    const summary = detail?.summary || {};
    const pages = wikiAsArray(detail?.pages);
    const sections = wikiAsArray(detail?.sections);
    setText("wiki-map-detail-title", detail?.agreement_name || String(aeId).toUpperCase());
    setText(
      "wiki-map-detail-note",
      `${String(detail?.agreement_id || aeId).toUpperCase()} / ${formatCount(pages.length, "0")} pages / ${formatCount(sections.length, "0")} detected sections`,
    );
    container.innerHTML = `
      <div class="wiki-detail-summary">
        <div>
          <span>Review state</span>
          <strong>${escapeHtml(wikiDisplayLabel(detail?.review_state, "Proposed"))}</strong>
        </div>
        <div>
          <span>Scope focus</span>
          <strong>${escapeHtml(wikiDisplayLabel(detail?.scope_focus))}</strong>
        </div>
        <div>
          <span>Language candidates</span>
          <strong>${formatCount(summary.language_candidates, "0")}</strong>
        </div>
        <div>
          <span>Learning items</span>
          <strong>${formatCount(summary.learning_backlog_items, "0")}</strong>
        </div>
      </div>
      <div class="wiki-detail-columns">
        <section>
          <h4>Clause Function Weight</h4>
          <div class="wiki-chip-cloud">${wikiTopClauseHtml(summary, 8)}</div>
        </section>
        <section>
          <h4>Clause/Context Relevance</h4>
          <div class="wiki-relevance-cloud">${wikiRelevanceCountsHtml(summary)}</div>
        </section>
      </div>
      ${wikiPageRowsHtml(pages)}
      ${wikiSectionRowsHtml(sections)}
    `;
  } catch (error) {
    setText("wiki-map-detail-note", "Document map failed to load");
    container.innerHTML = renderEmptyState("Map load failed", apiErrorMessage(error), { eyebrow: "Document map" });
  }
}

async function renderWikiCockpit({ force = false } = {}) {
  if (!document.getElementById("view-wiki")) return;
  setWikiStatus("Loading wiki layer...", "loading");
  try {
    await ensureWikiData({ force });
    renderWikiMetrics();
    renderWikiRunList();
    renderWikiClauseTree();
    renderWikiEntitlementDetail();
    renderWikiClauseDetail();
    await renderWikiTagExplorer({ force });
    renderWikiReferenceList();
    renderWikiLanguageList();
    renderWikiDocumentMaps();
    await renderWikiMapDetail();
    renderWikiQuestionList();
    renderWikiBacklogList();
    renderWikiArtifacts();
    const summary = state.wikiTagRegistry?.summary || state.wikiClauseLibrary?.summary || {};
    setWikiStatus(
      `Tag registry has ${formatCount(summary.tags, "0")} controlled label(s), ${formatCount(summary.tagged_records, "0")} tagged source record(s), and ${formatCount(summary.discovery_proposals, "0")} discovery proposal(s).`,
      "ready",
    );
  } catch (error) {
    setWikiStatus(`Wiki layer failed to load: ${apiErrorMessage(error)}`, "error");
    const empty = renderEmptyState("Wiki layer unavailable", apiErrorMessage(error), { eyebrow: "Wiki" });
    const ids = ["wiki-run-list", "wiki-clause-tree", "wiki-entitlement-detail", "wiki-clause-detail", "wiki-tag-summary", "wiki-tag-evidence-list", "wiki-reference-list", "wiki-language-list", "wiki-document-maps", "wiki-question-list", "wiki-backlog-list", "wiki-artifact-list"];
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = empty;
    });
  }
}

function auditCouncilNames() {
  const names = new Set();
  const addName = (value) => {
    const clean = String(value || "").trim();
    if (clean && clean !== DISPLAY_EMPTY && clean.toLowerCase() !== "unassigned") names.add(clean);
  };
  state.councils.forEach((row) => {
    addName(row.canonical_lga_short_name);
    addName(row.geography?.short_name);
    addName(row.fetch_metadata?.lga_short_name);
  });
  state.intakeRows.forEach((row) => {
    addName(row.canonical_lga_short_name);
    addName(row.lga_short_name);
    addName(row.fetch_metadata?.lga_short_name);
    (row.matched_lgas || []).forEach(addName);
  });
  wikiAsArray(state.councilReference?.rows).forEach((row) => {
    addName(row.short_name);
  });
  state.canonicalCouncils.forEach((row) => addName(row.short_name));
  return [...names].sort((a, b) => a.localeCompare(b));
}

function defaultAuditCouncil() {
  const names = auditCouncilNames();
  if (state.auditCouncil) return state.auditCouncil;
  const current = state.currentCouncil?.canonical_lga_short_name || currentCouncilRow()?.canonical_lga_short_name;
  if (current) return current;
  return names[0] || "";
}

function renderAuditCouncilOptions(selected = state.auditCouncil || defaultAuditCouncil()) {
  const select = document.getElementById("audit-council-select");
  if (!select) return;
  const names = auditCouncilNames();
  const options = selected && !names.includes(selected) ? [selected, ...names] : names;
  select.innerHTML = options.length
    ? options.map((name) => `<option value="${escapeHtml(name)}" ${name === selected ? "selected" : ""}>${escapeHtml(name)}</option>`).join("")
    : `<option value="">No councils loaded</option>`;
  select.value = selected || "";
}

function auditStatusClass(kind) {
  const clean = String(kind || "").toLowerCase();
  if (clean.includes("governance") || clean.includes("active") || clean.includes("accepted")) return "audit-pill-ok";
  if (clean.includes("superseded") || clean.includes("rejected")) return "audit-pill-muted";
  if (clean.includes("review") || clean.includes("intake")) return "audit-pill-watch";
  return "audit-pill-neutral";
}

function auditPill(label, kind = "") {
  if (!label) return "";
  return `<span class="audit-pill ${auditStatusClass(kind || label)}">${escapeHtml(displayCodeLabel(label))}</span>`;
}

function auditAgreementPeriod(row) {
  return displayDateRange(row?.operative_date, row?.expiry_date);
}

function renderAuditLineageRow(row, latestAeId) {
  const isLatest = row.ae_id === latestAeId;
  const scopeStatus = normaliseScopeStatus(row.scope_resolution_status);
  const sourceDetail = row.source_ready
    ? `Source fetched${row.source_fetched_at ? ` ${displayDate(row.source_fetched_at)}` : ""}`
    : "Source not fetched";
  return `
    <article class="audit-lineage-row workbench-card-scaffold ${isLatest ? "current" : ""}">
      <div class="audit-lineage-main workbench-card-main">
        <div class="audit-lineage-title workbench-card-title">
          <strong>${escapeHtml(row.title || row.ae_id || "Agreement")}</strong>
          ${isLatest ? auditPill("Latest available", "active") : ""}
        </div>
        ${renderInlineMeta([
          displayDate(row.operative_date, "No operative date"),
          String(row.ae_id || "").toUpperCase(),
          auditAgreementPeriod(row),
          sourceDetail,
        ], "audit-lineage-meta workbench-inline-meta")}
        <div class="audit-chip-row">
          ${auditPill(row.pipeline_status, row.pipeline_status)}
          ${scopeStatus ? auditPill(scopeStatus, scopeStatus) : ""}
          ${row.superseded_by_ae_id ? auditPill(`Superseded by ${String(row.superseded_by_ae_id).toUpperCase()}`, "superseded") : ""}
        </div>
      </div>
      ${row.source_ready ? `<div class="audit-lineage-actions workbench-card-actions"><button type="button" class="audit-open-btn" data-audit-open-workspace="${escapeHtml(row.ae_id)}">Open</button></div>` : ""}
    </article>
  `;
}

function renderAuditEvent(event) {
  const fullDetail = event.detail_full && event.detail_full !== event.detail
    ? `
        <details class="audit-event-detail-details workbench-card-details">
          <summary>Full note</summary>
          <pre class="audit-event-full-note">${escapeHtml(event.detail_full)}</pre>
        </details>
      `
    : "";
  return `
    <article class="audit-timeline-item workbench-card-scaffold audit-event-${escapeHtml(event.kind || "other")}">
      <div class="audit-timeline-main workbench-card-main">
        <div class="workbench-card-title">
          <strong>${escapeHtml(event.label || "Process event")}</strong>
        </div>
        ${renderInlineMeta([
          displayDate(event.date),
          String(event.ae_id || "").toUpperCase(),
          event.source || "",
        ], "audit-timeline-meta workbench-inline-meta")}
        ${event.detail ? `<p>${escapeHtml(event.detail)}</p>` : ""}
        ${fullDetail}
      </div>
    </article>
  `;
}

function renderAuditChange(change) {
  const fields = (change.fields || []).slice(0, 4).map((field) => `
    <div class="audit-change-field">
      <span>${escapeHtml(field.field || "Field")}</span>
      <strong>${escapeHtml(field.to || DISPLAY_EMPTY)}</strong>
      <small>Previous: ${escapeHtml(field.from || DISPLAY_EMPTY)}</small>
    </div>
  `).join("");
  return `
    <article class="audit-change-item workbench-card-scaffold">
      <div class="audit-change-main workbench-card-main">
      <div class="audit-change-head workbench-card-title">
        <time>${escapeHtml(displayDate(change.date, "Date not stated"))}</time>
        <strong>${escapeHtml(change.summary || "Lineage changed")}</strong>
      </div>
      ${renderInlineMeta([
        change.detail || "",
        String(change.ae_id || "").toUpperCase(),
        change.source || "",
      ], "audit-change-meta workbench-inline-meta")}
      ${fields ? `
        <details class="audit-change-field-details workbench-card-details">
          <summary>Changed fields</summary>
          <div class="audit-change-fields">${fields}</div>
        </details>
      ` : ""}
      </div>
    </article>
  `;
}

function auditBriefCountLabel(item) {
  const count = Number(item?.event_count || 0);
  if (!count) return "";
  const category = item?.category || "";
  if (category === "governed_outputs") {
    return `${formatCount(count, "0")} governed record${count === 1 ? "" : "s"}`;
  }
  if (category === "row_level_treatment") {
    return `${formatCount(count, "0")} row issue${count === 1 ? "" : "s"}`;
  }
  return `${formatCount(count, "0")} reviewed change${count === 1 ? "" : "s"}`;
}

function auditCompactList(values, limit = 4) {
  const unique = [];
  (values || []).forEach((value) => {
    const text = String(value || "").trim();
    if (text && !unique.includes(text)) unique.push(text);
  });
  if (!unique.length) return "";
  const visible = unique.slice(0, limit);
  if (unique.length > limit) visible.push(`${unique.length - limit} more`);
  return visible.join(", ");
}

function renderAuditQaBriefItem(item) {
  const metaItems = [
    auditBriefCountLabel(item),
    (item.periods || []).length ? `Periods ${auditCompactList(item.periods, 3)}` : "",
    (item.ae_ids || []).length ? `Agreements ${auditCompactList(item.ae_ids.map((id) => String(id).toUpperCase()), 3)}` : "",
  ];
  const notes = (item.notes || []).slice(0, 3).map((note) => `<p class="audit-brief-note">${escapeHtml(note)}</p>`).join("");
  const details = (item.details || []).filter(Boolean).slice(0, 5);
  const detailBlocks = [
    item.impact ? `<p class="audit-brief-impact"><b>Why it matters:</b> ${escapeHtml(item.impact)}</p>` : "",
    notes ? `<div class="audit-brief-notes">${notes}</div>` : "",
    details.length ? `<p class="audit-brief-details">${escapeHtml(details.join("; "))}</p>` : "",
  ].filter(Boolean).join("");
  return `
    <article class="audit-brief-item workbench-card-scaffold audit-brief-${escapeHtml(item.category || "general")}">
      <div class="audit-brief-main workbench-card-main">
      <div class="audit-brief-head workbench-card-title">
        <strong>${escapeHtml(item.heading || "QA summary")}</strong>
      </div>
      ${renderInlineMeta(metaItems, "audit-brief-meta workbench-inline-meta")}
      ${item.body ? `<p class="audit-brief-summary">${escapeHtml(item.body)}</p>` : ""}
      ${detailBlocks ? `
        <details class="audit-brief-details-block workbench-card-details">
          <summary>Details</summary>
          ${detailBlocks}
        </details>
      ` : ""}
      </div>
    </article>
  `;
}

function auditQualityClass(status) {
  const clean = String(status || "").toLowerCase();
  if (clean.includes("excellent") || clean.includes("strong")) return "audit-quality-good";
  if (clean.includes("review")) return "audit-quality-watch";
  if (clean.includes("fragile")) return "audit-quality-fragile";
  return "audit-quality-incomplete";
}

function auditQualityScoreText(item, fallbackMax = 1000) {
  const score = Number(item?.score);
  const maxScore = Number(item?.max_score || fallbackMax);
  if (!Number.isFinite(score)) return `-/${formatCount(maxScore, "0")}`;
  return `${formatCount(score, "0")}/${formatCount(maxScore, "0")}`;
}

function renderAuditQualityMeasure(measure) {
  const signals = (measure.signals || []).slice(0, 2).map((signal) => `<li>${escapeHtml(signal)}</li>`).join("");
  const penalties = (measure.penalties || []).slice(0, 2).map((penalty) => `<li>${escapeHtml(penalty)}</li>`).join("");
  const qualityDetail = signals || penalties;
  return `
    <article class="audit-quality-measure workbench-card-scaffold ${auditQualityClass(measure.status)}">
      <div class="audit-quality-measure-main workbench-card-main">
      <div class="workbench-card-title">
        <strong>${escapeHtml(measure.label || "Quality measure")}</strong>
        <span>${escapeHtml(auditQualityScoreText(measure, measure.max_score || 0))}</span>
      </div>
      ${qualityDetail ? `
        <details class="audit-quality-measure-details workbench-card-details">
          <summary>Signals</summary>
          <ul>${qualityDetail}</ul>
        </details>
      ` : ""}
      </div>
    </article>
  `;
}

function renderAuditQualityAgreementScore(agreement) {
  const measures = (agreement.measures || []).map((measure) => `
    <span class="${auditQualityClass(measure.status)}">
      ${escapeHtml(measure.label || "Measure")} ${escapeHtml(auditQualityScoreText(measure, measure.max_score || 0))}
    </span>
  `).join("");
  return `
    <article class="audit-quality-agreement workbench-card-scaffold ${auditQualityClass(agreement.status)}">
      <div class="audit-quality-agreement-main workbench-card-main">
      <div class="audit-quality-agreement-head workbench-card-title">
        <div>
          <strong>${escapeHtml(agreement.title || agreement.ae_id || "Agreement")}</strong>
          <small>${escapeHtml(String(agreement.ae_id || "").toUpperCase())}</small>
        </div>
        <div class="audit-quality-score">
          <b>${escapeHtml(auditQualityScoreText(agreement))}</b>
          <span>${escapeHtml(agreement.rating || displayCodeLabel(agreement.status))}</span>
        </div>
      </div>
      ${agreement.summary ? `<p>${escapeHtml(agreement.summary)}</p>` : ""}
      ${measures ? `<div class="audit-quality-mini-measures">${measures}</div>` : ""}
      </div>
    </article>
  `;
}

function renderAuditWorkspaceTable(workspace) {
  const sections = workspace?.completed_sections || [];
  const rows = sections
    .filter((section) => ["overview", "uplift_rules", "pay_tables", "scenarios", "uplifts"].includes(section.section))
    .map((section) => `
      <tr>
        <td>${escapeHtml(section.label || section.section)}</td>
        <td>${auditPill(section.status || "not_started", section.status)}</td>
        <td>${escapeHtml(displayDate(section.completed_at, "Not completed"))}</td>
        <td>${escapeHtml(section.source_ref || DISPLAY_EMPTY)}</td>
      </tr>
    `).join("");
  return `
    <table class="audit-process-table">
      <thead><tr><th>Workspace area</th><th>Status</th><th>Completed</th><th>Evidence</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="4">No workspace sections have been reviewed yet.</td></tr>`}</tbody>
    </table>
  `;
}

function auditWorkspaceSection(workspace, sectionName) {
  return (workspace?.completed_sections || []).find((section) => section?.section === sectionName) || {};
}

function auditPromotionStamp(values, emptyLabel) {
  const stamps = [];
  (values || []).map((value) => displayDate(value)).filter(Boolean).forEach((stamp) => {
    if (!stamps.includes(stamp)) stamps.push(stamp);
  });
  return stamps.length ? `Promoted ${stamps.join(", ")}` : emptyLabel;
}

function auditRowTreatmentLabel(treatment) {
  if (treatment?.status === "present" || treatment?.has_non_standard_row_level_treatment) {
    return "Non-standard treatment";
  }
  if (treatment?.status === "not_detected") return "Standard rows only";
  return "Not assessed";
}

function renderCouncilAuditDocument(report) {
  const doc = document.getElementById("audit-report-document");
  if (!doc) return;
  const latest = report.latest || {};
  const summary = report.summary || {};
  const council = report.council || {};
  const workspace = report.latest_workspace || {};
  const lineage = report.lineage || [];
  const events = report.events || [];
  const changes = report.changes || [];
  const qaChanges = report.qa_changes || [];
  const qaBrief = report.qa_brief || [];
  const governed = report.governed || workspace.governed || {};
  const quality = report.quality_standard || {};
  const governedSection = auditWorkspaceSection(workspace, "uplifts");
  const governedSetCompletedAt = governed.governed_set_completed_at || governedSection.completed_at;
  const governedSetStatus = governed.governed_set_status || governedSection.status || "not_started";
  const governedAgreementCount = Number(governed.agreement_count || 0);
  const governedSnapshotStatus = governedSetCompletedAt
    ? `${governedAgreementCount > 1 ? "Latest accepted" : "Accepted"} ${displayDate(governedSetCompletedAt)}`
    : displayCodeLabel(governedSetStatus);
  const governedSnapshotMeta = [
    `${formatCount(governed.periods, "0")} governed periods`,
    governedAgreementCount > 1 ? `${formatCount(governedAgreementCount, "0")} agreements` : "",
    governedSnapshotStatus,
  ].filter(Boolean).join(" / ");
  const rowTreatment = report.row_level_treatment || workspace.row_level_treatment || {};
  setText("audit-lineage-count", formatCount(summary.lineage_agreements, "0"));
  setText("audit-source-count", formatCount(summary.source_pdfs, "0"));
  setText("audit-review-count", `${formatCount(summary.review_done_sections, "0")}/${formatCount(summary.review_total_sections, "0")}`);
  setText("audit-governed-count", formatCount(summary.governed_periods, "0"));
  setText("audit-quality-score", auditQualityScoreText(quality));
  setText("audit-quality-note", quality.rating || "score out of 1000");
  setText("audit-latest-period", auditAgreementPeriod(latest));
  setText("audit-latest-note", latest?.ae_id ? String(latest.ae_id).toUpperCase() : "No current agreement");
  document.getElementById("audit-refresh")?.removeAttribute("disabled");
  doc.innerHTML = `
    <article class="audit-page">
      <header class="audit-page-header">
        <div>
          <div class="audit-page-kicker">Council Audit Document</div>
          <h2>${escapeHtml(council.short_name || state.auditCouncil || "Council")}</h2>
          <p>${escapeHtml(council.long_name || council.short_name || "")}</p>
        </div>
        <div class="audit-page-stamp">
          <span>Generated</span>
          <strong>${escapeHtml(displayDate(report.generated_at))}</strong>
        </div>
      </header>

      <section class="audit-section audit-summary-band">
        <div>
          <span>Latest available agreement</span>
          <strong>${escapeHtml(latest.title || "No agreement identified")}</strong>
          <small>${escapeHtml([String(latest.ae_id || "").toUpperCase(), auditAgreementPeriod(latest)].filter(Boolean).join(" / "))}</small>
        </div>
        <div>
          <span>Current source state</span>
          <strong>${escapeHtml(latest.source_ready ? "Source ready" : "Source incomplete")}</strong>
          <small>${escapeHtml(latest.source_fetched_at ? `Fetched ${displayDate(latest.source_fetched_at)}` : "No fetched PDF recorded")}</small>
        </div>
        <div>
          <span>Governed outputs</span>
          <strong>${escapeHtml(`${formatCount(summary.pay_table_periods, "0")} pay table / ${formatCount(summary.uplift_rule_periods, "0")} uplift`)}</strong>
          <small>${escapeHtml(`${formatCount(summary.pay_table_rows, "0")} pay-table rows / ${formatCount(summary.qa_governance_events, "0")} QA changes`)}</small>
        </div>
        <div>
          <span>Row-level treatment</span>
          <strong>${escapeHtml(auditRowTreatmentLabel(rowTreatment))}</strong>
          <small>${escapeHtml(rowTreatment.summary || "No row-level treatment summary recorded")}</small>
        </div>
        <div>
          <span>Quality standard</span>
          <strong>${escapeHtml(auditQualityScoreText(quality))}</strong>
          <small>${escapeHtml(quality.summary || "No quality standard score available")}</small>
        </div>
      </section>

      <section class="audit-section audit-quality-section">
        <div class="audit-section-head">
          <h3>Quality Standard Score</h3>
          <span>${escapeHtml(`${auditQualityScoreText(quality)} / ${quality.agreement_count || 0} agreement scores`)}</span>
        </div>
        <div class="audit-quality-overview">
          <div class="audit-quality-scorecard ${auditQualityClass(quality.status)}">
            <span>Overall</span>
            <strong>${escapeHtml(auditQualityScoreText(quality))}</strong>
            <small>${escapeHtml(quality.rating || "Incomplete")}</small>
          </div>
          <div class="audit-quality-measure-grid">
            ${(quality.measures || []).length ? quality.measures.map(renderAuditQualityMeasure).join("") : renderEmptyState("No quality measures", "The audit report has no scoreable agreement evidence yet.", { eyebrow: "Quality standard" })}
          </div>
        </div>
        <div class="audit-quality-agreement-list">
          ${(quality.agreements || []).length ? quality.agreements.map(renderAuditQualityAgreementScore).join("") : ""}
        </div>
      </section>

      <section class="audit-section">
        <div class="audit-section-head">
          <h3>Agreement Lineage</h3>
          <span>${escapeHtml(formatCount(lineage.length, "0"))} agreement records</span>
        </div>
        <div class="audit-lineage-list">
          ${lineage.length ? lineage.map((row) => renderAuditLineageRow(row, latest.ae_id)).join("") : renderEmptyState("No lineage records", "No candidate agreements matched this council.", { eyebrow: "Lineage" })}
        </div>
      </section>

      <section class="audit-section">
        <div class="audit-section-head">
          <h3>Workspace Process</h3>
          <span>${escapeHtml(`${formatCount(summary.review_done_sections, "0")} of ${formatCount(summary.review_total_sections, "0")} complete`)}</span>
        </div>
        ${renderAuditWorkspaceTable(workspace)}
      </section>

      <section class="audit-section">
        <div class="audit-section-head">
          <h3>Reviewer QA Summary</h3>
          <span>${escapeHtml(`${formatCount(qaBrief.length, "0")} summary note${qaBrief.length === 1 ? "" : "s"}; ${formatCount(qaChanges.length, "0")} detailed change${qaChanges.length === 1 ? "" : "s"}`)}</span>
        </div>
        <div class="audit-brief-list">
          ${qaBrief.length ? qaBrief.map(renderAuditQaBriefItem).join("") : renderEmptyState("No reviewer QA changes yet", "No pay-table cell, date, note or scenario override changes have been recorded for this council.", { eyebrow: "Reviewer QA" })}
        </div>
        ${qaChanges.length ? `
          <details class="audit-detail-disclosure">
            <summary>View detailed QA change log (${escapeHtml(formatCount(qaChanges.length, "0"))})</summary>
            <div class="audit-change-list audit-change-list-compact">
              ${qaChanges.map(renderAuditChange).join("")}
            </div>
          </details>
        ` : ""}
      </section>

      <section class="audit-section audit-two-column">
        <div>
          <div class="audit-section-head">
            <h3>Process Timeline</h3>
            <span>${escapeHtml(formatCount(events.length, "0"))} events</span>
          </div>
          <div class="audit-timeline-list">
            ${events.length ? events.map(renderAuditEvent).join("") : renderEmptyState("No process events yet", "This council has no dated source, intake, review or governance events.", { eyebrow: "Timeline" })}
          </div>
        </div>
        <div>
          <div class="audit-section-head">
            <h3>What Changed</h3>
            <span>${escapeHtml(formatCount(changes.length, "0"))} lineage changes</span>
          </div>
          <div class="audit-change-list">
            ${changes.length ? changes.map(renderAuditChange).join("") : renderEmptyState("No agreement transition yet", "Only one agreement record is available for this council lineage.", { eyebrow: "Change log" })}
          </div>
        </div>
      </section>

      <section class="audit-section">
        <div class="audit-section-head">
          <h3>Governed Data Snapshot</h3>
          <span>${escapeHtml(governedSnapshotMeta)}</span>
        </div>
        <div class="audit-governed-grid">
          <div><span>Pay-table periods</span><strong>${escapeHtml(formatCount(governed.pay_table_periods, "0"))}</strong><small>${escapeHtml(auditPromotionStamp(governed.pay_table_governed_at, "No governed pay-table stamp"))}</small></div>
          <div><span>Uplift-rule periods</span><strong>${escapeHtml(formatCount(governed.uplift_rule_periods, "0"))}</strong><small>${escapeHtml(auditPromotionStamp(governed.uplift_rule_governed_at, "No governed uplift-rule stamp"))}</small></div>
          <div><span>Pay-table rows</span><strong>${escapeHtml(formatCount(governed.pay_table_rows, "0"))}</strong><small>Weekly governed rows promoted for analysis</small></div>
        </div>
      </section>
    </article>
  `;
  doc.querySelectorAll("[data-audit-open-workspace]").forEach((button) => {
    button.addEventListener("click", () => openCouncil(button.dataset.auditOpenWorkspace, "overview"));
  });
}

async function renderCouncilAudit(councilName = state.auditCouncil || defaultAuditCouncil(), { force = false } = {}) {
  const doc = document.getElementById("audit-report-document");
  if (!doc) return;
  const council = councilName || defaultAuditCouncil();
  renderAuditCouncilOptions(council);
  if (!council) {
    doc.innerHTML = renderEmptyState("No council selected", "Fetch or load council data before generating an audit document.", { eyebrow: "Council audit" });
    return;
  }
  state.auditCouncil = council;
  if (!force && state.auditReportByCouncil[council]) {
    state.auditReport = state.auditReportByCouncil[council];
    renderAuditCouncilOptions(state.auditCouncil);
  }
  doc.innerHTML = renderEmptyState("Loading audit document", `Collecting lineage and process history for ${council}.`, { eyebrow: "Council audit" });
  setText("audit-lineage-count", "-");
  setText("audit-source-count", "-");
  setText("audit-review-count", "-");
  setText("audit-governed-count", "-");
  setText("audit-quality-score", "-");
  setText("audit-quality-note", "score out of 1000");
  setText("audit-latest-period", "Loading");
  setText("audit-latest-note", council);
  try {
    const report = !force && state.auditReportByCouncil[council]
      ? state.auditReportByCouncil[council]
      : await api(`/api/audit/councils/${encodeURIComponent(council)}`);
    state.auditReport = report;
    state.auditCouncil = report?.council?.short_name || council;
    state.auditReportByCouncil[state.auditCouncil] = report;
    state.auditReportByCouncil[council] = report;
    await syncAgreementContextFromAuditReport(report);
    renderAuditCouncilOptions(state.auditCouncil);
    renderCouncilAuditDocument(report);
    if (document.body.dataset.view === "audit") {
      syncWorkbenchRoute("audit");
      updateHeaderForView("audit");
    }
  } catch (error) {
    doc.innerHTML = renderEmptyState("Audit failed", apiErrorMessage(error), { eyebrow: "Council audit" });
    toast(`Audit failed: ${apiErrorMessage(error)}`, "error");
  }
}

function renderMetadataSummary(item) {
  const meta = item.fetch_metadata;
  const decision = item.multi_council_decision || {};
  const isSplitRow = Boolean(item.is_split_row);
  const title = isSplitRow
    ? `${item.canonical_lga_short_name || decision.assigned_lga || "Unknown council"} - part of multi-council ${decision.parent_ae_id?.toUpperCase() || item.parent_ae_id?.toUpperCase() || item.ae_id.toUpperCase()}`
    : metadataPrimaryLabel(item);

  const chips = [];
  if (decision.decision_pending) {
    chips.push('<span class="decision-chip decision-chip-pending">Needs multi-council decision</span>');
  }
  if (isSplitRow) {
    chips.push('<span class="decision-chip decision-chip-split">Split row</span>');
  }
  if (item.processing_gated) {
    chips.push('<span class="decision-chip decision-chip-gated">Processing gated</span>');
  }
  if (item.last_clear_record) {
    chips.push('<span class="decision-chip decision-chip-clear">Clear record logged</span>');
  }

  const primaryActions = [];
  const secondaryActions = [];
  if (decision.decision_pending) {
    primaryActions.push(`<button class="decision-action" data-action="mark-multi" data-ae-id="${escapeHtml(item.ae_id)}">Mark as multi-council</button>`);
    primaryActions.push(`<button class="decision-action" data-action="confirm-single" data-ae-id="${escapeHtml(item.ae_id)}">Confirm single council</button>`);
  }
  if (isSplitRow) {
    secondaryActions.push(`<button class="decision-action decision-action-link" data-action="undo-split" data-ae-id="${escapeHtml(item.parent_ae_id || decision.parent_ae_id || item.ae_id)}">Undo split</button>`);
  }
  secondaryActions.push(`<button class="decision-action decision-action-danger" data-action="clear-record" data-ae-id="${escapeHtml(item.ae_id)}">Clear record</button>`);

  if (!meta) {
    return `
      <div class="pipeline-title-row">
        <div>
          <div class="pipeline-title">${escapeHtml(title)}</div>
          ${renderInlineMeta([item.ae_id.toUpperCase(), "No fetch metadata"], "pipeline-meta-line workbench-inline-meta")}
        </div>
      </div>
      ${chips.length ? `<div class="pipeline-chip-row">${chips.join("")}</div>` : ""}
      ${primaryActions.length ? `<div class="pipeline-action-row">${primaryActions.join("")}</div>` : ""}
      ${secondaryActions.length ? `<details class="matrix-record-actions"><summary>Record actions</summary><div>${secondaryActions.join("")}</div></details>` : ""}
    `;
  }
  const status = meta.pipeline_status || "unknown";
  const matchedNames = splitMatchedNames(meta).join(", ") || "?";
  const metaItems = [
    item.ae_id.toUpperCase(),
    formatDateRange(meta),
    item.canonical_lga_short_name || matchedNames,
    compactStatusLabel(status),
  ];
  return `
    <div class="pipeline-title-row">
      <div>
        <div class="pipeline-title">${escapeHtml(title)}</div>
        ${renderInlineMeta(metaItems, "pipeline-meta-line workbench-inline-meta")}
      </div>
    </div>
    ${chips.length ? `<div class="pipeline-chip-row matrix-status-chip-row">${chips.join("")}</div>` : ""}
    ${primaryActions.length ? `<div class="pipeline-action-row">${primaryActions.join("")}</div>` : ""}
    ${secondaryActions.length ? `<details class="matrix-record-actions"><summary>Record actions</summary><div>${secondaryActions.join("")}</div></details>` : ""}
  `;
}

function renderMetadataDetails(item) {
  const fwc = item.fwc || {};
  const meta = item.fetch_metadata || {};
  const pdfSource = item.pdf_source || {};
  if (!item.fetch_metadata && !Object.keys(fwc).length) return "";

  const displayMetaValue = (label, value) => {
    const lowered = String(label).toLowerCase();
    return escapeHtml(lowered.includes("date") || lowered.includes("landed") ? displayDate(value) : displayValue(value));
  };
  const fields = [
    ["LGA code", fwc.lga_code || meta.lga_code],
    ["Matter number", fwc.matter_number || meta["Matter Number"]],
    ["Print ID", fwc.print_id || meta["Print ID"]],
    ["Operative date", fwc.operative_date || meta["Operative Date"]],
    ["Expiry date", fwc.expiry_date || meta["Expiry Date"]],
    ["Agreement version", fwc.version || meta.Version],
    ["Agreement number", meta.agreement_num_clean],
    ["Canonical LGA", item.canonical_lga_short_name || meta.lga_short_name],
    ["Original LGA", meta.lga_original_name],
    ["State", meta.state_name],
    ["Classification", meta.classification],
    ["Match strength", meta.match_strength],
    ["Scope status", normaliseScopeStatus(meta.scope_resolution_status)],
    ["Matched LGA count", meta.matched_lga_count],
    ["Multi-council flag", meta.possible_multi_council_flag],
    ["Lineage basis", meta.lineage_basis],
    ["Lineage key", meta.lineage_key],
    ["Likely current", meta.likely_most_current],
    ["Pipeline status", meta.pipeline_status],
    ["Fetched PDF size", formatBytes(pdfSource.file_size_bytes)],
    ["Fetched PDF health", pdfSource.size_status ? String(pdfSource.size_status).replaceAll("_", " ") : ""],
    ["Superseded by", fwc.superseded_by_ae_id || meta.superseded_by_ae_id],
    ["Landed at", item.landed_at ? String(item.landed_at).slice(0, 10) : ""],
    ["Last clear record", item.last_clear_record?.cleared_at ? String(item.last_clear_record.cleared_at).slice(0, 10) : ""],
  ].filter(([label, value]) => label !== "Scope status" || value);
  const rows = fields.map(([label, value]) => `
    <div class="canonical-meta-cell">
      <span>${escapeHtml(label)}</span>
      <strong>${displayMetaValue(label, value)}</strong>
    </div>
  `).join("");

  const summary = [
    item.canonical_lga_short_name || meta.lga_short_name,
    (fwc.matter_number || meta["Matter Number"]) ? `Matter ${fwc.matter_number || meta["Matter Number"]}` : null,
    (fwc.print_id || meta["Print ID"]) ? `Print ${fwc.print_id || meta["Print ID"]}` : null,
    (fwc.version || meta.Version) ? `v${fwc.version || meta.Version}` : null,
  ].filter(Boolean).join(" | ") || "Canonical source fields";

  const sourceLinks = [
    `<a class="canonical-meta-link" href="/api/councils/${encodeURIComponent(item.ae_id)}/pdf" target="_blank" rel="noopener">Fetched source PDF</a>`,
    meta.pdf_url
      ? `<a class="canonical-meta-link" href="${escapeHtml(meta.pdf_url)}" target="_blank" rel="noopener">FWC source record</a>`
      : "",
  ].filter(Boolean).join("");

  return `
    <details class="intake-canonical-details matrix-canonical-details">
      <summary>
        <span>Canonical fetch fields</span>
        <strong>${escapeHtml(summary)}</strong>
      </summary>
      <div class="canonical-meta-grid">${rows}</div>
      <div class="canonical-meta-footer">${sourceLinks}</div>
    </details>
  `;
}

function renderMatrix() {
  const list = document.getElementById("matrix-card-list");
  if (!list) return;
  captureMatrixAutomationDisclosureState(list);
  const filter = document.getElementById("matrix-filter")?.value.trim().toLowerCase() || "";
  const filtered = getSortedCouncils(reviewBoardRows()).filter((item) => {
    if (!filter) return true;
    const sourceGate = sourceGateStatus(item);
    const haystacks = [
      item.source_name,
      item.ae_id,
      metadataPrimaryLabel(item),
      item.fetch_metadata?.Industry,
      item.canonical_lga_short_name,
      item.processing_gated ? "gated needs decision scope blocked review board" : "ready review board",
      sourceGate.label,
      sourceGate.detail,
      isSourceReady(item) ? "source ready reviewable" : "source blocked gated",
      item.section_statuses?.pay_tables === "done" ? "pay complete" : "pay table work",
    ].filter(Boolean).map((value) => value.toLowerCase());
    return haystacks.some((value) => value.includes(filter));
  });

  if (!filtered.length) {
    list.innerHTML = '<div class="intake-empty">No Review Board cards match the current filters. Source-ready and scope-clear items appear here after Intake Processing.</div>';
    return;
  }

  list.innerHTML = `
    <div class="intake-result-count">Showing ${escapeHtml(formatCount(filtered.length))} governed QA cards</div>
    ${filtered.map(renderMatrixCard).join("")}
  `;
  wireMatrixAutomationDisclosureState(list);
  list.querySelectorAll(".matrix-section-button").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.disabled) return;
      await openCouncil(button.dataset.aeId, button.dataset.section);
    });
  });
  list.querySelectorAll("[data-review-auto-run]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      setReviewBoardAutomationDetailsOpen(button.dataset.aeId, true);
      queueOverviewPreparation({ aeId: button.dataset.aeId, force: true, source: "matrix" });
    });
  });
  list.querySelectorAll("[data-review-human-run]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      setReviewBoardAutomationDetailsOpen(button.dataset.aeId, true);
      queueSyntheticHumanReview({ aeId: button.dataset.aeId, force: button.dataset.resumeSystemImprovement !== "1" });
    });
  });
  list.querySelectorAll("[data-matrix-next-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.disabled) return;
      await handleMatrixNextAction(button);
    });
  });
  list.querySelectorAll(".decision-action").forEach((button) => {
    button.addEventListener("click", () => handleDecisionAction(button.dataset.action, button.dataset.aeId));
  });
}

const MATRIX_AUTOMATION_SECTION_BY_JOB = {
  overview: "overview",
  pay: "pay_tables",
  uplift: "uplift_rules",
  scenarios: "scenarios",
};

const MATRIX_SYNTHETIC_SECTION_STEPS = {
  overview: "overview",
  uplift_rules: "uplift_rules",
  pay_tables: "pay_tables",
  scenarios: "scenarios",
  uplifts: "uplifts",
};

function matrixAutomationStatusForSection(prep, section) {
  const match = Object.entries(prep?.jobs || {}).find(([key]) => MATRIX_AUTOMATION_SECTION_BY_JOB[key] === section);
  const status = match?.[1]?.status;
  if (status === "running") return "auto-running";
  if (status === "done" || status === "skipped") return "auto-done";
  if (status === "failed") return "auto-failed";
  if (status === "queued" && prep?.running) return "auto-queued";
  return "";
}

function matrixSyntheticHumanStatusForSection(run, section) {
  const match = Object.entries(MATRIX_SYNTHETIC_SECTION_STEPS)
    .find(([, mappedSection]) => mappedSection === section);
  const status = match ? run?.jobs?.[match[0]]?.status : "";
  if (status === "running") return "auto-running";
  if (status === "waiting") return "auto-waiting";
  if (status === "done" || status === "skipped") return "auto-done";
  if (status === "failed") return "auto-failed";
  if (status === "queued" && run?.running) return "auto-queued";
  return "";
}

function renderMatrixAutomationPanel(item) {
  const prep = overviewPreparationState(item.ae_id);
  const human = syntheticHumanReviewState(item.ae_id);
  const jobs = Object.values(prep?.jobs || {});
  const humanJobs = Object.values(human?.jobs || {});
  const running = Boolean(prep?.running || jobs.some((job) => job.status === "running"));
  const humanRunning = Boolean(human?.running || humanJobs.some((job) => job.status === "running"));
  const humanAwaitingSystemImprovement = Boolean(human?.awaitingSystemImprovement);
  const failed = jobs.some((job) => job.status === "failed");
  const humanFailed = humanJobs.some((job) => job.status === "failed");
  const completed = Boolean(prep?.completed);
  const humanCompleted = Boolean(human?.completed);
  const humanStarted = Boolean(human?.startedAt || human?.finishedAt || humanRunning || humanCompleted || humanFailed || humanAwaitingSystemImprovement);
  const gated = Boolean(item.processing_gated || !isSourceReady(item));
  const stateClass = humanAwaitingSystemImprovement ? "waiting" : humanRunning ? "human-running" : running ? "running" : humanFailed || failed ? "failed" : humanCompleted || completed ? "done" : "ready";
  const buttonText = running
    ? "Computer running"
    : completed
      ? "Run computer again"
      : "Get computer to do it";
  const humanButtonText = humanRunning
    ? "Automated reviewer running"
    : humanAwaitingSystemImprovement
      ? "Continue after implementation"
      : humanCompleted
      ? "Run automated reviewer again"
      : "Run reviewer QA";
  const humanDisabled = running || humanRunning || gated;
  const stepsHtml = jobs.map((job) => `
    <div class="matrix-auto-step matrix-auto-step-${escapeHtml(job.status)}">
      <span class="matrix-auto-step-dot" aria-hidden="true"></span>
      <div>
        <strong>${escapeHtml(job.label)}</strong>
        <p>${escapeHtml(job.detail || "")}</p>
      </div>
    </div>
  `).join("");
  const humanStepsHtml = humanStarted ? humanJobs.map((job) => `
    <div class="matrix-auto-step matrix-auto-step-${escapeHtml(job.status)}">
      <span class="matrix-auto-step-dot" aria-hidden="true"></span>
      <div>
        <strong>${escapeHtml(job.label)}</strong>
        <p>${escapeHtml(job.detail || "")}</p>
      </div>
    </div>
  `).join("") : "";
  const pendingRequests = (human?.systemImprovementRequests || []).filter((item) => item?.status === "awaiting_implementation");
  const improvementRequestHtml = pendingRequests.length
    ? `<div class="matrix-system-improvement-request">
        <span>System improvement requested</span>
        ${pendingRequests.slice(0, 3).map((item) => `
          <p><strong>${escapeHtml(item.stage || "Review judgement")}</strong> ${escapeHtml(item.request || item.judgement || "")}</p>
        `).join("")}
      </div>`
    : "";
  const improvementHtml = (human?.improvements || []).length
    ? `<div class="matrix-improvement-log">
        <span>System improvement log</span>
        ${(human.improvements || []).slice(0, 4).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
      </div>`
    : "";
  const decisionHtml = humanStarted
    ? `<div class="matrix-decision-summary">
        <span>Reviewer decisions</span>
        ${(syntheticHumanDecisionSummary(human)).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
      </div>`
    : "";
  const commentaryHtml = humanStarted && (human?.commentary || []).length
    ? `<div class="matrix-reviewer-commentary">
        <span>Reviewer commentary</span>
        ${(human.commentary || []).slice(-5).map((item) => `<p>${escapeHtml(item.text || item)}</p>`).join("")}
      </div>`
    : "";
  return `
    <div class="matrix-auto-panel matrix-auto-panel-${stateClass}">
      <div class="matrix-auto-head">
        <div class="matrix-auto-controls">
          <button class="matrix-auto-run-btn ${running ? "is-running" : ""}" type="button" data-review-auto-run="1" data-ae-id="${escapeHtml(item.ae_id)}" ${running || humanRunning ? "disabled" : ""}>
            ${escapeHtml(buttonText)}
          </button>
          <button class="matrix-human-run-btn ${humanRunning ? "is-running" : ""}" type="button" data-review-human-run="1" ${humanAwaitingSystemImprovement ? 'data-resume-system-improvement="1"' : ""} data-ae-id="${escapeHtml(item.ae_id)}" ${humanDisabled ? "disabled" : ""}>
            ${escapeHtml(humanButtonText)}
          </button>
        </div>
        <div class="matrix-auto-comment" aria-live="polite">
          <p><strong>Computer</strong> ${escapeHtml(overviewPreparationReply(prep))}</p>
          ${humanStarted ? `<p><strong>Synthetic</strong> ${escapeHtml(syntheticHumanReviewReply(human))}</p>` : ""}
        </div>
      </div>
      <div class="matrix-auto-steps">${stepsHtml}</div>
      ${humanStarted ? `<div class="matrix-auto-steps matrix-human-steps">${humanStepsHtml}</div>` : ""}
      ${commentaryHtml}
      ${decisionHtml}
      ${improvementRequestHtml}
      ${improvementHtml}
    </div>
  `;
}

function renderMatrixCard(item) {
  const sourceReady = isSourceReady(item);
  const sourceGate = sourceGateStatus(item);
  const nextAction = nextMatrixAction(item);
  const prep = overviewPreparationState(item.ae_id);
  const coreProgress = matrixCoreProgress(item);
  const gated = Boolean(item.processing_gated || !sourceReady);
  const scopeGated = Boolean(item.processing_gated);
  const primaryActionLabel = matrixPrimaryActionLabel(nextAction);
  const automationDetailsOpen = reviewBoardAutomationDetailsIsOpen(item.ae_id);
  const operationalMeta = [
    scopeGated ? "Scope decision required" : sourceGate.label,
    `${coreProgress.done}/${coreProgress.total} sections`,
    nextAction.detail || primaryActionLabel,
  ];
  const showNextActionHint = Boolean(nextAction.detail && !nextAction.disabled);
  const sectionButtons = Object.entries(SECTION_LABELS).map(([section, label]) => {
    const status = item.section_statuses?.[section] || "not_started";
    const disabled = gated ? "disabled" : "";
    const statusLabel = status.replaceAll("_", " ");
    const compactLabel = MATRIX_SECTION_LABELS[section] || label;
    const ariaLabel = `Open ${label} for ${item.canonical_lga_short_name || item.source_name || item.ae_id} (${statusLabel})`;
    const human = syntheticHumanReviewState(item.ae_id);
    const automationStatus = matrixSyntheticHumanStatusForSection(human, section) || matrixAutomationStatusForSection(prep, section);
    return `
      <button class="matrix-section-button status-${escapeHtml(status)} ${automationStatus ? `matrix-section-${escapeHtml(automationStatus)}` : ""} ${gated ? "is-disabled" : ""}" aria-label="${escapeHtml(ariaLabel)}" title="${escapeHtml(`${label}: ${statusLabel}`)}" data-ae-id="${escapeHtml(item.ae_id)}" data-section="${escapeHtml(section)}" data-status="${escapeHtml(status)}" ${disabled}>
        ${statusDot(status)}
        <span class="matrix-section-label">${escapeHtml(compactLabel)}</span>
      </button>
    `;
  }).join("");

  return `
    <article class="matrix-card ${gated ? "matrix-card-gated" : ""} ${!sourceReady ? "matrix-card-source-blocked" : ""}" data-matrix-card-ae-id="${escapeHtml(item.ae_id)}">
      <div class="matrix-card-main">
        ${renderMetadataSummary(item)}
        ${renderInlineMeta(operationalMeta, "matrix-operational-line workbench-inline-meta")}
      </div>
      <div class="matrix-card-action-cell">
        <button class="matrix-next-action-btn next-action-${escapeHtml(nextAction.kind)}" type="button" data-matrix-next-action="${escapeHtml(nextAction.action)}" data-ae-id="${escapeHtml(item.ae_id)}" ${nextAction.section ? `data-section="${escapeHtml(nextAction.section)}"` : ""} ${nextAction.disabled ? "disabled" : ""}>
          ${escapeHtml(primaryActionLabel)}
        </button>
      </div>
      <div class="matrix-card-progress ${showNextActionHint ? "" : "matrix-card-progress-compact"}">
        <div class="matrix-progress-readout">
          <span>Core review</span>
          <strong>${formatCount(coreProgress.pct, "0")}%</strong>
          <small>${formatCount(coreProgress.done, "0")} of ${formatCount(coreProgress.total, "0")} sections</small>
        </div>
        <div class="matrix-progress-track" aria-label="Core review progress">
          <div class="confidence-bar"><i style="width:${Math.min(100, Math.max(0, coreProgress.pct))}%"></i></div>
        </div>
        ${showNextActionHint ? `
          <div class="next-action-hint">
            <span>${escapeHtml(primaryActionLabel)}</span>
            <small>${escapeHtml(nextAction.detail || "")}</small>
          </div>
        ` : ""}
      </div>
      <details class="matrix-card-details matrix-section-details">
        <summary><span>Sections</span><strong>${escapeHtml(matrixSectionStatusSummary(item))}</strong></summary>
        <div class="matrix-section-grid">
          ${sectionButtons}
        </div>
      </details>
      <details class="matrix-card-details matrix-auto-details" data-matrix-automation-ae-id="${escapeHtml(item.ae_id)}" ${automationDetailsOpen ? "open" : ""}>
        <summary><span>Automation</span><strong>${escapeHtml(matrixAutomationSummary(item))}</strong></summary>
        ${renderMatrixAutomationPanel(item)}
      </details>
      <div class="matrix-card-canonical">
        ${renderMetadataDetails(item)}
      </div>
    </article>
  `;
}

async function handleMatrixNextAction(button) {
  const aeId = button.dataset.aeId;
  const action = button.dataset.matrixNextAction;
  if (!aeId || !action) return;

  if (action === "source") {
    focusIntakeRow(aeId);
    toast("Focused the source record in Intake Processing", "success");
    return;
  }

  if (action === "scope") {
    const card = Array.from(document.querySelectorAll("[data-matrix-card-ae-id]"))
      .find((node) => node.dataset.matrixCardAeId === aeId);
    const actions = card?.querySelector(".pipeline-action-row");
    card?.classList.add("matrix-card-nudge");
    setTimeout(() => card?.classList.remove("matrix-card-nudge"), 1400);
    actions?.querySelector("button")?.focus();
    toast(actions ? "Use the scope decision buttons on this card" : "Scope decision required before section review", "warning");
    return;
  }

  if (action === "section") {
    await openCouncil(aeId, button.dataset.section || "overview");
  }
}


function renderMatrixStats() {
  const rows = reviewBoardRows();
  const agreements = rows.filter((c) => !c.is_split_row).length;
  const payDone = rows.filter((c) => c.section_statuses?.pay_tables === "done").length;
  const inProgress = rows.filter((c) => c.section_statuses?.pay_tables === "in_progress").length;
  const scopeGated = rows.filter((c) => c.processing_gated).length;
  const sourceBlocked = rows.filter((c) => !isSourceReady(c)).length;
  const gated = rows.filter((c) => c.processing_gated || !isSourceReady(c)).length;
  const ready = rows.filter((c) => !c.processing_gated && isSourceReady(c)).length;
  const doneSections = rows.reduce((sum, c) => sum + Number(c.done_count || 0), 0);
  const totalSections = rows.reduce((sum, c) => sum + Number(c.total_sections || 0), 0);

  const lgaInPipeline = new Set(
    rows
      .map((c) => c.canonical_lga_short_name)
      .filter(Boolean)
  ).size;
  const lgaTotal = state.canonicalLgaTotal ?? "?";

  const text = `${agreements} agreements | ${payDone}/${agreements} pay tables done | ${inProgress} in progress | ${sourceBlocked} source blocked | ${scopeGated} scope gated | ${lgaInPipeline}/${lgaTotal} LGAs`;
  setText("matrix-stats", text);
  setText("matrix-agreements", formatCount(agreements, "0"));
  setText("matrix-pay-done", `${formatCount(payDone, "0")}/${formatCount(agreements, "0")}`);
  setText("matrix-in-progress", formatCount(inProgress, "0"));
  setText("matrix-gated", formatCount(gated, "0"));
  setText("matrix-lane-ready", formatCount(ready, "0"));
  setText("matrix-lane-source", formatCount(sourceBlocked, "0"));
  setText("matrix-lane-gated", formatCount(scopeGated, "0"));
  setText("matrix-lane-sections", `${formatCount(doneSections, "0")}/${formatCount(totalSections, "0")}`);
  if (document.getElementById("view-matrix")?.classList.contains("active")) {
    setText("header-stats", text);
  }
}

function formatAnalysisDollar(value, basis) {
  if (value === null || value === undefined || value === "") return DISPLAY_EMPTY;
  const suffix = basis ? ` ${basis}` : "";
  return `${displayCurrency(value)}${suffix}`;
}

function hasRuleValue(value) {
  return value !== null && value !== undefined && value !== "" && value !== DISPLAY_EMPTY;
}

function addRuleDisplayField(fields, label, value) {
  if (hasRuleValue(value)) fields.push({ label, value: String(value) });
}

function ruleFieldClass(label) {
  const slug = String(label || "field").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return slug ? `rule-expression-field-${slug}` : "rule-expression-field-generic";
}

function rateCapDisplayFromDeps(externalDeps = []) {
  const deps = Array.isArray(externalDeps) ? externalDeps : [];
  const dep = deps.find((item) => item?.dep_kind === "rate_cap");
  if (!dep) return null;
  let rawRateCap = dep.raw_rate_cap;
  if (!hasRuleValue(rawRateCap)) {
    rawRateCap = rateCapValueFromStatus(dep.financial_year);
  }
  if (!hasRuleValue(rawRateCap)) {
    rawRateCap = dep.dep_status === "confirmed" ? "NA" : "awaiting";
  }
  return {
    financialYear: dep.financial_year || "",
    rawRateCap,
    effectiveRate: dep.effective_rate,
    resolutionNote: dep.resolution_note || "",
    status: dep.dep_status || "",
  };
}

function financialYearFromEffectiveDate(value) {
  if (!value || typeof value !== "string") return "";
  const match = value.match(/^(\d{4})-(\d{2})-/);
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (!Number.isFinite(year) || !Number.isFinite(month)) return "";
  const startYear = month >= 7 ? year : year - 1;
  return `${startYear}-${String((startYear + 1) % 100).padStart(2, "0")}`;
}

function normaliseFinancialYear(value) {
  if (!value) return "";
  const source = String(value);
  const match = source.match(/\b(20\d{2})\s*[/-]\s*(20\d{2}|\d{2})\b/);
  if (!match) return "";
  return `${match[1]}-${String(match[2]).slice(-2)}`;
}

function financialYearFromRateCapText(text) {
  return normaliseFinancialYear(text);
}

function extractRateCapPercentFromText(text) {
  if (!text) return null;
  const source = String(text);
  const patterns = [
    /(\d+(?:\.\d+)?)\s*%\s*\([^)]*rate\s*cap[^)]*\)/i,
    /(\d+(?:\.\d+)?)\s*%\s+(?:as|is)\s+(?:the\s+)?rate\s*cap/i,
    /rate\s*cap[^0-9%]{0,40}(?:is|of|at|:)?[^0-9%]{0,20}(\d+(?:\.\d+)?)\s*%/i,
  ];
  for (const pattern of patterns) {
    const match = source.match(pattern);
    if (match) return match[1];
  }
  return null;
}

function rateCapStatusForYear(financialYear) {
  const normalised = normaliseFinancialYear(financialYear);
  const years = Array.isArray(state.rateCapStatus?.years) ? state.rateCapStatus.years : [];
  return years.find((year) => normaliseFinancialYear(year.financial_year) === normalised) || null;
}

function rateCapValueFromStatus(financialYear) {
  const row = rateCapStatusForYear(financialYear);
  if (!row) return null;
  if (row.resolution_status && row.resolution_status !== "confirmed") return "awaiting";
  return hasRuleValue(row.standard_rate_cap_value) ? row.standard_rate_cap_value : "NA";
}

function rateCapDisplayValueForDep(dep) {
  if (!dep || dep.dep_kind !== "rate_cap") return null;
  if (hasRuleValue(dep.raw_rate_cap)) return dep.raw_rate_cap;
  const statusValue = rateCapValueFromStatus(dep.financial_year);
  if (hasRuleValue(statusValue)) return statusValue;
  return dep.dep_status === "confirmed" ? "NA" : "awaiting";
}

function rateCapDisplayFromRule(raw = {}, components = {}, fallback = {}) {
  const rateCapFields = [
    raw.quantum_external_ref,
    raw.source_external_ref,
    components.source_external_ref,
    raw.quantum_external_definition,
    raw.quantum,
    raw.quantum_resolution,
    raw.source_quantum,
    raw.pattern_variant,
    components.source_quantum,
    components.pattern_variant,
  ].filter(Boolean);
  const mentionsRateCap = rateCapFields.some((value) => /rate\s*cap/i.test(String(value)));
  const ruleCap =
    hasRuleValue(components.external_cap_pct)
      ? components.external_cap_pct
      : hasRuleValue(components.rate_cap_component)
        ? components.rate_cap_component
        : extractRateCapPercentFromText(rateCapFields.join(" | "));
  if (!mentionsRateCap) return null;
  const financialYear =
    fallback.financialYear
    || normaliseFinancialYear(raw.rate_cap_financial_year || components.rate_cap_financial_year)
    || financialYearFromEffectiveDate(raw.effective_date || components.effective_date || fallback.effectiveDate)
    || financialYearFromRateCapText(rateCapFields.join(" | "));
  const statusValue = rateCapValueFromStatus(financialYear);
  let rawRateCap = ruleCap;
  if (!hasRuleValue(rawRateCap)) rawRateCap = statusValue || "NA";
  return {
    financialYear,
    rawRateCap,
    effectiveRate: null,
    resolutionNote: "",
    status: "",
  };
}

function buildRuleExpression(rule, fallback = {}) {
  const raw = rule && typeof rule === "object" ? rule : {};
  const components = raw.normalised_components || raw;
  const fields = [];
  const notes = Array.isArray(components.notes) ? components.notes.filter(Boolean) : [];
  const rateCapDep = rateCapDisplayFromDeps(fallback.externalDeps);
  const rateCapRule = rateCapDisplayFromRule(raw, components, fallback);
  const rateCapDisplay = rateCapDep || rateCapRule;
  const patternKey =
    raw.pattern_archetype
    || components.pattern_archetype
    || raw.source_quantum_type
    || raw.quantum_type
    || fallback.pattern
    || "unknown";
  const primary =
    raw.pattern_variant
    || raw.source_quantum
    || raw.quantum
    || fallback.quantum
    || raw.quantum_resolution
    || DISPLAY_EMPTY;

  if (raw.quantum_type) addRuleDisplayField(fields, "type", displayCodeLabel(raw.quantum_type));
  addRuleDisplayField(fields, "fixed %", hasRuleValue(components.internal_pct_component) ? displayPercent(components.internal_pct_component) : "");
  addRuleDisplayField(fields, "flat $", hasRuleValue(components.flat_dollar_component) ? formatAnalysisDollar(components.flat_dollar_component, components.flat_dollar_basis || components.dollar_basis) : "");
  addRuleDisplayField(fields, "floor $", hasRuleValue(components.dollar_floor_component) ? formatAnalysisDollar(components.dollar_floor_component, components.dollar_floor_basis || components.dollar_basis) : "");
  addRuleDisplayField(fields, "floor %", hasRuleValue(components.pct_floor_component) ? displayPercent(components.pct_floor_component) : "");
  addRuleDisplayField(fields, "cap share", hasRuleValue(components.external_cap_share) ? displayFractionPercent(components.external_cap_share) : "");
  addRuleDisplayField(fields, "external cap", !rateCapDisplay && hasRuleValue(components.external_cap_pct) ? displayPercent(components.external_cap_pct) : "");
  addRuleDisplayField(fields, "cap delta", hasRuleValue(components.external_cap_delta_pct) ? displayPercentDelta(components.external_cap_delta_pct) : "");
  addRuleDisplayField(fields, "cap result", hasRuleValue(components.external_formula_pct) ? displayPercent(components.external_formula_pct) : "");
  if (rateCapDisplay?.rawRateCap !== null && rateCapDisplay?.rawRateCap !== undefined) {
    addRuleDisplayField(fields, "rate cap", displayPercent(rateCapDisplay.rawRateCap));
  }
  if (rateCapDisplay?.effectiveRate !== null && rateCapDisplay?.effectiveRate !== undefined) {
    addRuleDisplayField(fields, "resolved rate", displayPercent(rateCapDisplay.effectiveRate));
  }
  addRuleDisplayField(
    fields,
    "resolved %",
    hasRuleValue(components.resolved_pct)
      ? `${displayPercent(components.resolved_pct)}${components.resolved_basis ? ` (${displayCodeLabel(components.resolved_basis)})` : ""}`
      : "",
  );

  addRuleDisplayField(fields, "floor", raw.quantum_floor);
  addRuleDisplayField(fields, "ceiling", raw.quantum_ceiling);
  addRuleDisplayField(fields, "external ref", rateCapDisplay ? "" : raw.quantum_external_ref);
  addRuleDisplayField(fields, "resolved", raw.quantum_resolution);
  if (rateCapDisplay?.resolutionNote) notes.push(rateCapDisplay.resolutionNote);

  const sourceId =
    fallback.ruleId
    || raw.source_rule_id
    || (raw.effective_date || raw.period_label ? `${raw.effective_date || ""}::${raw.period_label || ""}` : "");

  return {
    patternKey,
    patternLabel: displayCodeLabel(patternKey),
    primary,
    sourceId,
    fields,
    notes,
  };
}

function renderRuleExpressionFields(expression, { compact = false } = {}) {
  if (!expression.fields.length && !expression.notes.length) return "";
  const fields = expression.fields.map((field) => `
    <span class="rule-expression-field ${escapeHtml(ruleFieldClass(field.label))}">
      <b>${escapeHtml(field.label)}</b>
      <em>${escapeHtml(field.value)}</em>
    </span>
  `).join("");
  const notes = expression.notes.map((note) => `<small>${escapeHtml(note)}</small>`).join("");
  return `<div class="rule-expression-fields${compact ? " rule-expression-fields-compact" : ""}">${fields}${notes}</div>`;
}

function renderRuleExpressionCell(rule, fallback = {}) {
  const expression = buildRuleExpression(rule, fallback);
  return `
    <div class="rule-expression-cell">
      <strong>${escapeHtml(expression.primary)}</strong>
      <span>${escapeHtml(expression.patternLabel)}${expression.sourceId ? ` | ${escapeHtml(expression.sourceId)}` : ""}</span>
      ${renderRuleExpressionFields(expression, { compact: true })}
    </div>
  `;
}

const SCENARIO_RULE_FACT_LABELS = new Map([
  ["fixed %", "Increase"],
  ["flat $", "Flat rise"],
  ["floor $", "Minimum $"],
  ["floor %", "Minimum %"],
  ["cap share", "Cap share"],
  ["external cap", "Rate cap"],
  ["rate cap", "Rate cap"],
  ["cap delta", "Cap margin"],
  ["cap result", "Cap result"],
  ["resolved rate", "Applied rate"],
  ["resolved %", "Applied rate"],
  ["floor", "Minimum"],
  ["ceiling", "Ceiling"],
  ["resolved", "Resolution"],
]);

const SCENARIO_RULE_FACT_PRIORITY = [
  "resolved %",
  "resolved rate",
  "cap result",
  "fixed %",
  "flat $",
  "floor $",
  "floor %",
  "rate cap",
  "external cap",
  "cap delta",
  "cap share",
  "floor",
  "ceiling",
  "resolved",
];

function renderScenarioRuleFacts(expression) {
  const fields = Array.isArray(expression.fields) ? expression.fields : [];
  const byLabel = new Map();
  for (const field of fields) {
    const key = String(field.label || "").toLowerCase();
    if (key && !byLabel.has(key) && hasRuleValue(field.value)) byLabel.set(key, field.value);
  }
  const facts = [];
  const seen = new Set();
  const addFact = (label, value) => {
    if (!hasRuleValue(label) || !hasRuleValue(value)) return;
    const key = `${label}::${value}`;
    if (seen.has(key)) return;
    seen.add(key);
    facts.push({ label, value });
  };
  if (hasRuleValue(expression.patternLabel) && expression.patternLabel !== "Unknown") {
    addFact("Method", expression.patternLabel);
  }
  for (const key of SCENARIO_RULE_FACT_PRIORITY) {
    const value = byLabel.get(key);
    const label = SCENARIO_RULE_FACT_LABELS.get(key);
    addFact(label, value);
  }
  const factsHtml = facts.length
    ? `<dl class="scenario-rule-facts">${facts.slice(0, 6).map((fact) => `
        <div class="scenario-rule-fact">
          <dt>${escapeHtml(fact.label)}</dt>
          <dd>${escapeHtml(fact.value)}</dd>
        </div>
      `).join("")}</dl>`
    : "";
  const note = (Array.isArray(expression.notes) ? expression.notes : []).find(hasRuleValue);
  const noteHtml = note
    ? `<p class="scenario-rule-interpretation"><span>Interpretation</span>${escapeHtml(String(note))}</p>`
    : "";
  return `${factsHtml}${noteHtml}`;
}

function renderScenarioRuleExpression(rule, fallback = {}) {
  const expression = buildRuleExpression(rule, fallback);
  if (!hasRuleValue(expression.primary) && !expression.fields.length) return "";
  const title = [expression.patternLabel, expression.sourceId].filter(hasRuleValue).join(" | ");
  return `
    <div class="scenario-story-block scenario-story-rule" title="${escapeHtml(title)}">
      <span>Rule to test</span>
      <strong class="scenario-rule-statement">${escapeHtml(expression.primary)}</strong>
      ${renderScenarioRuleFacts(expression)}
    </div>
  `;
}

function renderGovernedRuleExpression(rule) {
  const expression = buildRuleExpression(rule);
  return `
    <div class="governed-rule-expression">
      <span class="pattern-chip pattern-chip-${escapeHtml(expression.patternKey)}">${escapeHtml(expression.patternLabel)}</span>
      <div class="muted">${escapeHtml(expression.primary)}</div>
      ${renderRuleExpressionFields(expression)}
    </div>
  `;
}

function currentQuarterStartIso(now = new Date()) {
  const year = now.getFullYear();
  const quarterStartMonth = Math.floor(now.getMonth() / 3) * 3;
  return `${year}-${String(quarterStartMonth + 1).padStart(2, "0")}-01`;
}

function shiftQuarterStartIso(iso, offsetQuarters) {
  if (!isIso(iso)) return currentQuarterStartIso();
  const [year, month] = iso.split("-").map(Number);
  const shifted = new Date(year, month - 1 + (offsetQuarters * 3), 1);
  return `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, "0")}-01`;
}

function trailingQuarterStarts(baseQuarterStart = currentQuarterStartIso(), count = 4) {
  return Array.from({ length: count }, (_, index) => shiftQuarterStartIso(baseQuarterStart, -index)).reverse();
}

function quarterLabelFromIso(iso) {
  if (!isIso(iso)) return "Current quarter";
  const [, month] = iso.split("-").map(Number);
  const quarter = Math.floor((month - 1) / 3) + 1;
  return `Q${quarter} ${iso.slice(0, 4)}`;
}

function quarterRangeLabel(quarterStarts) {
  if (!quarterStarts?.length) return quarterLabelFromIso(currentQuarterStartIso());
  const labels = quarterStarts.map(quarterLabelFromIso);
  return labels.length === 1 ? labels[0] : `${labels[0]} to ${labels[labels.length - 1]}`;
}

function quarterStartFromYearQuarter(year, quarter) {
  const yearNumber = Number(year);
  const quarterNumber = Number(quarter);
  if (!Number.isInteger(yearNumber) || !Number.isInteger(quarterNumber) || quarterNumber < 1 || quarterNumber > 4) {
    return currentQuarterStartIso();
  }
  return `${yearNumber}-${String(((quarterNumber - 1) * 3) + 1).padStart(2, "0")}-01`;
}

function quarterNumberFromIso(iso) {
  if (!isIso(iso)) return Math.floor(new Date().getMonth() / 3) + 1;
  const month = Number(iso.slice(5, 7));
  return Math.floor((month - 1) / 3) + 1;
}

function isoDateTime(iso) {
  if (!isIso(iso)) return null;
  const [year, month, day] = iso.split("-").map(Number);
  return Date.UTC(year, month - 1, day);
}

function normaliseBandValue(value) {
  const text = String(value ?? "").toLowerCase();
  const match = text.match(/\b(?:band\s*)?(\d+)\b/);
  return match ? match[1] : text.replace(/[^a-z0-9]/g, "");
}

function payRowBand(row) {
  return normaliseBandValue(row.standard_band) || normaliseBandValue(row.band) || normaliseBandValue(row.title);
}

function levelSortValue(level) {
  const text = String(level || "");
  if (/^\d+$/.test(text)) return Number(text);
  const first = text.match(/[A-Z]/i)?.[0]?.toUpperCase();
  return first ? first.charCodeAt(0) - 64 : Number.POSITIVE_INFINITY;
}

function payRowMatchesBand(row, band = DEFAULT_ANALYSIS_CHART_BAND) {
  return payRowBand(row) === String(band);
}

function distributionPointAnalysisData() {
  if (state.currentDataSet === "charts" && state.analysisData?.rows) return state.analysisData;
  return state.analysisDataByKind.distribution_point_analysis || null;
}

function agreementKeyForPayRow(row) {
  return row.ae_id || row.canonical_lga_short_name || row.agreement_name || `${row.period_index}-${row.row_index}`;
}

function bandMaxRowsForChartContext({ band, quarterStart, mode }) {
  return distributionPointRowsForChartBasis({
    band,
    quarterStart,
    mode,
    valueField: "max_level_point_weekly_rate",
  });
}

function normaliseDistributionPointRow(row, valueField = "midpoint_weekly_rate") {
  const value = Number(row?.[valueField] ?? row?.weekly_rate);
  if (!Number.isFinite(value)) return null;
  return {
    ...row,
    weekly_rate: value,
    standard_band: row.standard_band || row.band,
    standard_level: row.standard_level || [row.min_level, row.max_level].filter(Boolean).join("-"),
    chart_band: row.chart_band || row.band,
    chart_min_level: row.chart_min_level || row.min_level,
    chart_max_level: row.chart_max_level || row.max_level,
    chart_min_weekly_rate: Number(row.chart_min_weekly_rate ?? row.min_weekly_rate),
    chart_max_weekly_rate: Number(row.chart_max_weekly_rate ?? row.max_weekly_rate),
  };
}

function activeDistributionPointRows({ band = DEFAULT_ANALYSIS_CHART_BAND, quarterStart = currentQuarterStartIso(), valueField = "midpoint_weekly_rate" } = {}) {
  return chartPayRows()
    .filter((row) => row.quarter_start === quarterStart && payRowMatchesBand(row, band))
    .map((row) => normaliseDistributionPointRow(row, valueField))
    .filter(Boolean)
    .sort((a, b) => a.weekly_rate - b.weekly_rate);
}

function fourQuarterAverageDistributionPointRows({ band = DEFAULT_ANALYSIS_CHART_BAND, quarterStart = currentQuarterStartIso(), valueField = "midpoint_weekly_rate" } = {}) {
  const quarterStarts = trailingQuarterStarts(quarterStart, 4);
  const byAgreement = new Map();
  quarterStarts.forEach((start) => {
    activeDistributionPointRows({ band, quarterStart: start, valueField }).forEach((row) => {
      const key = agreementKeyForPayRow(row);
      const existing = byAgreement.get(key) || {
        row,
        sum: 0,
        count: 0,
        quarterStarts: [],
        minRateSum: 0,
        maxRateSum: 0,
      };
      existing.sum += Number(row.weekly_rate);
      existing.minRateSum += Number(row.chart_min_weekly_rate ?? row.weekly_rate);
      existing.maxRateSum += Number(row.chart_max_weekly_rate ?? row.weekly_rate);
      existing.count += 1;
      existing.quarterStarts.push(start);
      if (String(row.quarter_start || "") > String(existing.row.quarter_start || "")) {
        existing.row = row;
      }
      byAgreement.set(key, existing);
    });
  });
  return Array.from(byAgreement.values()).map((item) => ({
    ...item.row,
    weekly_rate: item.sum / item.count,
    chart_min_weekly_rate: item.minRateSum / item.count,
    chart_max_weekly_rate: item.maxRateSum / item.count,
    chart_basis: CHART_BASE_FOUR_QUARTER_AVERAGE,
    chart_quarter_count: item.count,
    chart_quarter_starts: item.quarterStarts,
  })).sort((a, b) => a.weekly_rate - b.weekly_rate);
}

function smoothedPointDate(row) {
  return isIso(row?.effective_from) ? row.effective_from : row?.quarter_start;
}

function numericRowField(row, field, fallbackField = "weekly_rate") {
  const value = Number(row?.[field]);
  if (Number.isFinite(value)) return value;
  const fallback = Number(row?.[fallbackField]);
  return Number.isFinite(fallback) ? fallback : null;
}

function interpolatedRowField(fromRow, toRow, fraction, field, fallbackField = "weekly_rate") {
  const fromValue = numericRowField(fromRow, field, fallbackField);
  const toValue = numericRowField(toRow, field, fallbackField);
  if (fromValue === null && toValue === null) return null;
  if (fromValue === null) return toValue;
  if (toValue === null) return fromValue;
  return fromValue + ((toValue - fromValue) * fraction);
}

function uniqueDatedDistributionPoints(points) {
  const byDate = new Map();
  points.forEach((row) => {
    const date = smoothedPointDate(row);
    const ms = isoDateTime(date);
    if (ms === null) return;
    const existing = byDate.get(date);
    if (!existing || String(row.quarter_start || "") > String(existing.row.quarter_start || "")) {
      byDate.set(date, { row, date, ms });
    }
  });
  return [...byDate.values()].sort((a, b) => a.ms - b.ms);
}

function smoothedDistributionPointRow(points, quarterStart) {
  const targetMs = isoDateTime(quarterStart);
  if (targetMs === null) return null;
  const datedPoints = uniqueDatedDistributionPoints(points);
  if (!datedPoints.length) return null;
  const hasTargetQuarter = points.some((row) => row.quarter_start === quarterStart);
  const firstPoint = datedPoints[0];
  const lastPoint = datedPoints[datedPoints.length - 1];
  if (!hasTargetQuarter && (targetMs < firstPoint.ms || targetMs > lastPoint.ms)) return null;
  let fromPoint = firstPoint;
  let toPoint = lastPoint;
  for (let index = 0; index < datedPoints.length; index += 1) {
    const point = datedPoints[index];
    if (point.ms <= targetMs) fromPoint = point;
    if (point.ms >= targetMs) {
      toPoint = point;
      break;
    }
  }
  const span = Math.max(1, toPoint.ms - fromPoint.ms);
  const fraction = fromPoint.ms === toPoint.ms
    ? 0
    : Math.max(0, Math.min(1, (targetMs - fromPoint.ms) / span));
  const nearestPoint = Math.abs(targetMs - fromPoint.ms) <= Math.abs(toPoint.ms - targetMs)
    ? fromPoint
    : toPoint;
  const weeklyRate = interpolatedRowField(fromPoint.row, toPoint.row, fraction, "weekly_rate");
  if (weeklyRate === null) return null;
  const minWeeklyRate = interpolatedRowField(fromPoint.row, toPoint.row, fraction, "chart_min_weekly_rate");
  const maxWeeklyRate = interpolatedRowField(fromPoint.row, toPoint.row, fraction, "chart_max_weekly_rate");
  return {
    ...nearestPoint.row,
    quarter_start: quarterStart,
    weekly_rate: weeklyRate,
    chart_min_weekly_rate: minWeeklyRate ?? weeklyRate,
    chart_max_weekly_rate: maxWeeklyRate ?? weeklyRate,
    chart_basis: CHART_BASE_DATE_SMOOTHED,
    chart_smoothed_method: fromPoint.date === toPoint.date ? "nearest_dated_value" : "linear_interpolation",
    chart_smoothed_source_count: datedPoints.length,
    chart_smoothed_from: fromPoint.date,
    chart_smoothed_to: toPoint.date,
    chart_smoothed_fraction: Number(fraction.toFixed(3)),
  };
}

function dateSmoothedDistributionPointRows({ band = DEFAULT_ANALYSIS_CHART_BAND, quarterStart = currentQuarterStartIso(), valueField = "midpoint_weekly_rate" } = {}) {
  const byAgreement = new Map();
  chartPayRows()
    .filter((row) => payRowMatchesBand(row, band))
    .map((row) => normaliseDistributionPointRow(row, valueField))
    .filter(Boolean)
    .forEach((row) => {
      const key = agreementKeyForPayRow(row);
      const points = byAgreement.get(key) || [];
      points.push(row);
      byAgreement.set(key, points);
    });
  return Array.from(byAgreement.values())
    .map((points) => smoothedDistributionPointRow(points, quarterStart))
    .filter(Boolean)
    .sort((a, b) => a.weekly_rate - b.weekly_rate);
}

function distributionPointRowsForChartBasis({ band = DEFAULT_ANALYSIS_CHART_BAND, quarterStart = currentQuarterStartIso(), mode = chartBaseMode(), valueField = "midpoint_weekly_rate" } = {}) {
  if (mode === CHART_BASE_FOUR_QUARTER_AVERAGE) {
    return fourQuarterAverageDistributionPointRows({ band, quarterStart, valueField });
  }
  if (mode === CHART_BASE_DATE_SMOOTHED) {
    return dateSmoothedDistributionPointRows({ band, quarterStart, valueField });
  }
  return activeDistributionPointRows({ band, quarterStart, valueField });
}

function chartBaseMode() {
  if (state.analysisChartBaseMode === CHART_BASE_FOUR_QUARTER_AVERAGE) return CHART_BASE_FOUR_QUARTER_AVERAGE;
  if (state.analysisChartBaseMode === CHART_BASE_DATE_SMOOTHED) return CHART_BASE_DATE_SMOOTHED;
  return CHART_BASE_CURRENT;
}

function chartBasisLabel(mode = chartBaseMode()) {
  if (mode === CHART_BASE_FOUR_QUARTER_AVERAGE) return "4Q average";
  if (mode === CHART_BASE_DATE_SMOOTHED) return "Date-smoothed";
  return "Selected quarter";
}

function chartBasisRangeLabel(mode, quarterStart, quarterStarts) {
  if (mode === CHART_BASE_FOUR_QUARTER_AVERAGE) return quarterRangeLabel(quarterStarts);
  if (mode === CHART_BASE_DATE_SMOOTHED) return `${quarterLabelFromIso(quarterStart)} trajectory point`;
  return quarterLabelFromIso(quarterStart);
}

function selectedCouncilStatLabel(mode) {
  if (mode === CHART_BASE_DATE_SMOOTHED) return "Selected smoothed";
  if (mode === CHART_BASE_FOUR_QUARTER_AVERAGE) return "Selected 4Q avg";
  return "Selected council";
}

function selectedCouncilRawQuarterRow({ band, quarterStart } = {}) {
  return currentCouncilDistributionRow(activeDistributionPointRows({ band, quarterStart }));
}

function smoothedBasisFootnote(row, rawRow = null, quarterStart = "") {
  if (row?.chart_basis !== CHART_BASE_DATE_SMOOTHED) return "";
  const count = formatCount(row.chart_smoothed_source_count || 0, "0");
  const rawValue = Number(rawRow?.weekly_rate);
  const smoothedValue = Number(row.weekly_rate);
  const hasRawComparison = Number.isFinite(rawValue) && Number.isFinite(smoothedValue);
  const smoothingDelta = hasRawComparison ? smoothedValue - rawValue : null;
  const rawComparison = hasRawComparison && Math.abs(smoothingDelta) >= 0.005
    ? `; raw selected-quarter value ${displayCurrency(rawValue)}, smoothing delta ${displayCurrencyDelta(smoothingDelta)}`
    : "";
  if (row.chart_smoothed_from && row.chart_smoothed_to && row.chart_smoothed_from !== row.chart_smoothed_to) {
    return `Selected council date-smoothed value interpolated from ${count} dated points between ${displayDate(row.chart_smoothed_from)} and ${displayDate(row.chart_smoothed_to)}${rawComparison}`;
  }
  if (row.chart_smoothed_from) {
    if (hasRawComparison && Math.abs(smoothingDelta) < 0.005) {
      return `Selected council date-smoothed value matches the raw ${quarterLabelFromIso(quarterStart)} snapshot because the trajectory anchors to ${displayDate(row.chart_smoothed_from)}`;
    }
    return `Selected council date-smoothed value anchored to nearest dated point ${displayDate(row.chart_smoothed_from)}${rawComparison}`;
  }
  return `Selected council date-smoothed value estimated from ${count} dated points${rawComparison}`;
}

function chartRangeMode() {
  if (state.analysisChartRangeMode === CHART_RANGE_IQR) return CHART_RANGE_IQR;
  if (state.analysisChartRangeMode === CHART_RANGE_STD_DEV) return CHART_RANGE_STD_DEV;
  return CHART_RANGE_NONE;
}

function chartPayRows() {
  return distributionPointAnalysisData()?.rows || [];
}

function selectedCouncilChartRows() {
  const rows = chartPayRows();
  const currentAeId = state.currentCouncil?.agreement_id;
  if (!currentAeId) return [];
  const exactRows = rows.filter((row) => row.ae_id === currentAeId);
  if (exactRows.length) return exactRows;
  const currentKey = normaliseSpatialKey(
    state.currentCouncil?.geography?.spatial_key
    || state.currentCouncil?.canonical_lga_short_name
    || state.currentCouncil?.geography?.short_name
  );
  if (!currentKey) return [];
  return rows.filter((row) => normaliseSpatialKey(
    row.spatial_key
    || row.map_join_key
    || row.canonical_lga_short_name
    || row.agreement_name
  ) === currentKey);
}

function chartAvailableBands() {
  const bands = new Set();
  const scopedRows = selectedCouncilChartRows();
  const rows = scopedRows.length ? scopedRows : chartPayRows();
  rows.forEach((row) => {
    const band = payRowBand(row);
    if (band) bands.add(band);
  });
  return [...bands].sort((a, b) => Number(a) - Number(b) || String(a).localeCompare(String(b)));
}

function quarterStartForIsoDate(iso) {
  if (!isIso(iso)) return null;
  return quarterStartFromYearQuarter(iso.slice(0, 4), quarterNumberFromIso(iso));
}

function chartAvailableQuarterStarts(band = state.analysisChartBand || DEFAULT_ANALYSIS_CHART_BAND) {
  const scopedRows = selectedCouncilChartRows();
  const rows = (scopedRows.length ? scopedRows : chartPayRows()).filter((row) => {
    if (!Number.isFinite(Number(row.midpoint_weekly_rate ?? row.weekly_rate))) return false;
    return !band || payRowMatchesBand(row, band);
  });
  const quarters = new Set();
  rows.forEach((row) => {
    if (isIso(row.quarter_start)) {
      quarters.add(row.quarter_start);
      return;
    }
    const start = quarterStartForIsoDate(row.effective_from);
    if (!start) return;
    const end = isIso(row.to_date) && Number(row.to_date.slice(0, 4)) < 2100
      ? quarterStartForIsoDate(row.to_date)
      : start;
    for (let cursor = start; cursor <= end; cursor = shiftQuarterStartIso(cursor, 1)) {
      quarters.add(cursor);
    }
  });
  const coveredQuarters = [...quarters].sort();
  if (coveredQuarters.length) return coveredQuarters;
  const starts = rows
    .map((row) => quarterStartForIsoDate(row.effective_from))
    .filter(Boolean)
    .sort();
  const current = currentQuarterStartIso();
  return starts.length ? [...new Set(starts)] : [current];
}

function selectedChartQuarterStart(band = state.analysisChartBand || DEFAULT_ANALYSIS_CHART_BAND) {
  const available = chartAvailableQuarterStarts(band);
  const current = currentQuarterStartIso();
  const selected = isIso(state.analysisChartQuarterStart) ? state.analysisChartQuarterStart : current;
  const next = available.includes(selected)
    ? selected
    : available.includes(current)
      ? current
      : available[available.length - 1] || current;
  state.analysisChartQuarterStart = next;
  return next;
}

function selectedChartBand() {
  const available = chartAvailableBands();
  const selected = String(state.analysisChartBand || DEFAULT_ANALYSIS_CHART_BAND);
  const next = available.includes(selected)
    ? selected
    : available.includes(DEFAULT_ANALYSIS_CHART_BAND)
      ? DEFAULT_ANALYSIS_CHART_BAND
      : available[0] || DEFAULT_ANALYSIS_CHART_BAND;
  state.analysisChartBand = next;
  return next;
}

function chartLevelSpan(rows) {
  const levels = new Set();
  rows.forEach((row) => {
    const minLevel = row.chart_min_level || row.min_level;
    const maxLevel = row.chart_max_level || row.max_level;
    if (minLevel) levels.add(minLevel);
    if (maxLevel) levels.add(maxLevel);
  });
  const sorted = [...levels].sort((a, b) => levelSortValue(a) - levelSortValue(b) || String(a).localeCompare(String(b)));
  const min = sorted[0] || "";
  const max = sorted[sorted.length - 1] || "";
  return {
    min,
    max,
    label: min && max ? `Levels ${min}-${max}` : "Levels not available",
  };
}

function chartPayDistributionContext() {
  const band = selectedChartBand();
  const quarterStart = selectedChartQuarterStart(band);
  const mode = chartBaseMode();
  const rangeMode = chartRangeMode();
  const quarterStarts = mode === CHART_BASE_FOUR_QUARTER_AVERAGE
    ? trailingQuarterStarts(quarterStart, 4)
    : [quarterStart];
  const rows = distributionPointRowsForChartBasis({ band, quarterStart, mode });
  const levelSpan = chartLevelSpan(rows);
  return {
    rows,
    mode,
    rangeMode,
    band,
    bandLabel: `Band ${band}`,
    levelSpan,
    quarterStart,
    quarterStarts,
    basisLabel: chartBasisLabel(mode),
    rangeLabel: chartBasisRangeLabel(mode, quarterStart, quarterStarts),
  };
}

function cohortPayRows(rows, cohortKeys) {
  if (!cohortKeys.size) return [];
  const currentAeId = state.currentCouncil?.agreement_id;
  return rows.filter((row) => {
    if (currentAeId && row.ae_id === currentAeId) return false;
    const rowKey = normaliseSpatialKey(
      row.spatial_key
      || row.map_join_key
      || row.canonical_lga_short_name
      || row.agreement_name
    );
    return cohortKeys.has(rowKey);
  });
}

function localCohortPayRows(rows) {
  return cohortPayRows(rows, selectedLocalCohortKeys());
}

function extendedLocalCohortPayRows(rows) {
  return cohortPayRows(rows, selectedExtendedLocalCohortKeys());
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

function payDistributionStats(rows) {
  const values = rows.map((row) => Number(row.weekly_rate)).filter(Number.isFinite).sort((a, b) => a - b);
  if (!values.length) return null;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / values.length;
  const stdDev = Math.sqrt(variance);
  return {
    count: values.length,
    min: values[0],
    max: values[values.length - 1],
    mean,
    median: percentile(values, 0.5),
    p25: percentile(values, 0.25),
    p75: percentile(values, 0.75),
    stdDev,
    values,
  };
}

function standardSalaryDensity(stats) {
  return (x) => {
    if (!stats?.stdDev || stats.max <= stats.min || x <= stats.min || x >= stats.max) return 0;
    const z = (x - stats.mean) / stats.stdDev;
    const normalDensity = Math.exp(-0.5 * z * z) / (stats.stdDev * Math.sqrt(2 * Math.PI));
    const lowerSpan = Math.max(1, stats.mean - stats.min);
    const upperSpan = Math.max(1, stats.max - stats.mean);
    const sidePosition = x <= stats.mean
      ? Math.max(0, Math.min(1, (x - stats.min) / lowerSpan))
      : Math.max(0, Math.min(1, (stats.max - x) / upperSpan));
    const boundaryTaper = Math.sin((Math.PI / 2) * sidePosition);
    return normalDensity * boundaryTaper;
  };
}

function percentileDropMarkers(stats) {
  if (!stats?.values?.length) return [];
  return [
    ["P0", 0, stats.min],
    ["P25", 25, stats.p25],
    ["P50", 50, stats.median],
    ["P75", 75, stats.p75],
    ["P100", 100, stats.max],
  ].map(([label, percentileValue, value]) => (
    Number.isFinite(Number(value))
      ? { label, percentileValue, value: Number(value) }
      : null
  )).filter(Boolean);
}

function distributionRowCouncilLabel(row) {
  return row?.canonical_lga_short_name || row?.agreement_name || row?.ae_id || "Council";
}

function comparatorCohortExtremeRows(cohort) {
  const sorted = (cohort?.rows || [])
    .map((row) => ({ row, value: Number(row.weekly_rate) }))
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

function distributionRangeOverlay(stats, mode = chartRangeMode()) {
  if (!stats?.values?.length || mode === CHART_RANGE_NONE) return null;
  if (mode === CHART_RANGE_IQR) {
    const min = Number(stats.p25);
    const max = Number(stats.p75);
    if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
    return {
      key: CHART_RANGE_IQR,
      label: "Interquartile range",
      shortLabel: "IQR",
      min,
      max,
      title: `Interquartile range: ${displayCurrency(min)} to ${displayCurrency(max)}`,
    };
  }
  if (mode === CHART_RANGE_STD_DEV) {
    const mean = Number(stats.mean);
    const stdDev = Number(stats.stdDev);
    if (!Number.isFinite(mean) || !Number.isFinite(stdDev) || stdDev <= 0) return null;
    const min = mean - stdDev;
    const max = mean + stdDev;
    return {
      key: CHART_RANGE_STD_DEV,
      label: "Standard deviation range",
      shortLabel: "+/- 1 SD",
      min,
      max,
      title: `Standard deviation range: ${displayCurrency(min)} to ${displayCurrency(max)}`,
    };
  }
  return null;
}

function councilReferenceRows() {
  return state.councilReference?.rows || state.canonicalCouncils || [];
}

function councilReferenceLookup() {
  const lookup = new Map();
  councilReferenceRows().forEach((row) => {
    [
      row.council_key,
      row.spatial_key,
      row.map_join_key,
      row.spatial_name,
      row.short_name,
      row.long_name,
      row.official_name,
      row.abs_lga_code,
      row.abs_lga_code_2025,
      row.lga_code,
    ].forEach((value) => {
      const key = normaliseSpatialKey(value);
      if (key && !lookup.has(key)) lookup.set(key, row);
    });
  });
  return lookup;
}

function councilReferenceForPayRow(row, lookup = councilReferenceLookup()) {
  const candidates = [
    row.spatial_key,
    row.map_join_key,
    row.spatial_name,
    row.canonical_lga_short_name,
    row.agreement_name,
    row.abs_lga_code,
    row.lga_code,
  ];
  for (const candidate of candidates) {
    const ref = lookup.get(normaliseSpatialKey(candidate));
    if (ref) return ref;
  }
  return null;
}

function selectedCouncilReferenceRow(lookup = councilReferenceLookup()) {
  const candidates = [
    state.currentCouncil?.geography?.spatial_key,
    state.currentCouncil?.canonical_lga_short_name,
    state.currentCouncil?.geography?.short_name,
    state.currentCouncil?.fwc?.canonical_lga_short_name,
  ];
  for (const candidate of candidates) {
    const ref = lookup.get(normaliseSpatialKey(candidate));
    if (ref) return ref;
  }
  return null;
}

function isCurrentAgreementRow(row) {
  const currentAeId = state.currentCouncil?.agreement_id;
  return Boolean(currentAeId && row.ae_id === currentAeId);
}

function referenceSeifaScore(row) {
  const score = Number(row?.vgccc_seifa_dis_score ?? row?.lgprf_relative_socioeconomic_disadvantage);
  return Number.isFinite(score) ? score : null;
}

function seifaPeerBand(row) {
  const score = referenceSeifaScore(row);
  if (score === null) return null;
  const scores = councilReferenceRows()
    .map(referenceSeifaScore)
    .filter((value) => value !== null)
    .sort((a, b) => a - b);
  if (!scores.length) return null;
  const index = scores.filter((value) => value <= score).length - 1;
  const quintile = Math.max(1, Math.min(5, Math.floor((index / Math.max(1, scores.length)) * 5) + 1));
  const labels = [
    "Q1 most disadvantaged",
    "Q2 lower SEIFA",
    "Q3 middle SEIFA",
    "Q4 higher SEIFA",
    "Q5 least disadvantaged",
  ];
  return {
    key: `seifa_q${quintile}`,
    label: labels[quintile - 1],
  };
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

function rowsMatchingReference(rows, matcher, { excludeCurrent = true } = {}) {
  const lookup = councilReferenceLookup();
  return rows.filter((row) => {
    if (excludeCurrent && isCurrentAgreementRow(row)) return false;
    const ref = councilReferenceForPayRow(row, lookup);
    return Boolean(ref && matcher(ref, row));
  });
}

function buildReportingCohorts(rows) {
  const lookup = councilReferenceLookup();
  const selectedRef = selectedCouncilReferenceRow(lookup);
  const selectedCategory = selectedRef?.council_category || state.currentCouncil?.geography?.council_category;
  const selectedLgprfGroup = selectedRef?.lgprf_group;
  const selectedSeifaBand = seifaPeerBand(selectedRef);
  return [
    {
      key: "statewide",
      label: "Statewide",
      note: "all active values",
      description: "All active governed weekly-rate values for the selected chart band and date basis.",
      rows,
      baseline: true,
    },
    {
      key: "local_5",
      label: "Local 5",
      note: "nearest councils by distance",
      description: "The five nearest active councils by reference location, excluding the selected agreement.",
      rows: localCohortPayRows(rows),
    },
    {
      key: "local_12",
      label: "Local 12",
      note: "extended nearest councils",
      description: "The 12 nearest active councils by reference location, excluding the selected agreement.",
      rows: extendedLocalCohortPayRows(rows),
    },
    {
      key: "lgv_category",
      label: selectedCategory ? `LGV ${selectedCategory}` : "LGV category",
      note: "same council category",
      description: "Councils sharing the selected council's Local Government Victoria category.",
      rows: selectedCategory
        ? rowsMatchingReference(rows, (ref) => ref.council_category === selectedCategory)
        : [],
    },
    {
      key: "regional_victoria",
      label: "Regional Victoria",
      note: "excludes interface and metro",
      description: "Regional and rural Victorian councils only; metropolitan and interface councils are excluded.",
      rows: rowsMatchingReference(rows, (ref) => isRegionalVictoriaCouncil(ref)),
    },
    {
      key: "lgprf_group",
      label: selectedLgprfGroup ? `LGPRF ${selectedLgprfGroup}` : "LGPRF group",
      note: "same performance group",
      description: "Councils sharing the selected council's Local Government Performance Reporting Framework group.",
      rows: selectedLgprfGroup
        ? rowsMatchingReference(rows, (ref) => ref.lgprf_group === selectedLgprfGroup)
        : [],
    },
    {
      key: "seifa_peer",
      label: selectedSeifaBand?.label || "SEIFA peer band",
      note: "same socioeconomic band",
      description: "Councils in the same SEIFA peer quintile. SEIFA means the ABS Socio-Economic Indexes for Areas disadvantage score.",
      rows: selectedSeifaBand
        ? rowsMatchingReference(rows, (ref) => seifaPeerBand(ref)?.key === selectedSeifaBand.key)
        : [],
    },
  ];
}

function selectedReportingCohort(cohorts) {
  if (!cohorts?.length) return null;
  return cohorts.find((cohort) => cohort.key === state.analysisChartCohortKey)
    || cohorts.find((cohort) => cohort.key === DEFAULT_ANALYSIS_CHART_COHORT_KEY)
    || cohorts[0];
}

function selectedDistributionCohort(cohorts) {
  if (!cohorts?.length) return null;
  return cohorts.find((cohort) => cohort.key === state.analysisChartDistributionCohortKey)
    || cohorts.find((cohort) => cohort.key === DEFAULT_ANALYSIS_CHART_DISTRIBUTION_COHORT_KEY)
    || cohorts[0];
}

function currentCouncilDistributionRow(rows) {
  const currentAeId = state.currentCouncil?.agreement_id;
  if (currentAeId) {
    const exact = rows.find((row) => row.ae_id === currentAeId);
    if (exact) return exact;
  }
  const currentKey = normaliseSpatialKey(
    state.currentCouncil?.geography?.spatial_key
    || state.currentCouncil?.canonical_lga_short_name
    || state.currentCouncil?.geography?.short_name
  );
  if (!currentKey) return null;
  return rows.find((row) => normaliseSpatialKey(
    row.spatial_key
    || row.map_join_key
    || row.canonical_lga_short_name
    || row.agreement_name
  ) === currentKey) || null;
}

function chartBandMaxDeltaRows(context, selectedCohortKey = state.analysisChartCohortKey, bands = null) {
  const selectedBands = Array.isArray(bands) && bands.length
    ? bands
    : chartAvailableBands();
  return selectedBands.map((band) => {
    const rows = bandMaxRowsForChartContext({
      band,
      quarterStart: context.quarterStart,
      mode: context.mode,
    });
    const currentRow = currentCouncilDistributionRow(rows);
    const cohorts = buildReportingCohorts(rows);
    const cohort = cohorts.find((item) => item.key === selectedCohortKey) || selectedReportingCohort(cohorts);
    const cohortStats = payDistributionStats(cohort?.rows || []);
    const selectedValue = Number(currentRow?.weekly_rate);
    if (!Number.isFinite(selectedValue) || !cohortStats?.mean) return null;
    return {
      band,
      maxLevel: currentRow.chart_max_level || "",
      selectedValue,
      cohortMean: cohortStats.mean,
      cohortCount: cohortStats.count,
      deltaPct: (selectedValue - cohortStats.mean) / cohortStats.mean,
    };
  }).filter(Boolean);
}

function renderBandMaxDeltaBars(context, selectedCohort = null) {
  const selectedBand = context?.band || DEFAULT_ANALYSIS_CHART_BAND;
  const rows = chartBandMaxDeltaRows(context, selectedCohort?.key, [selectedBand]);
  const cohortLabel = selectedCohort?.label || "Selected cohort";
  const bandLabel = selectedBand ? `Band ${selectedBand}` : "Selected band";
  if (!rows.length) {
    return `
      <aside class="distribution-band-delta-panel distribution-band-delta-empty">
        <div class="distribution-band-delta-head">
          <span>Max level delta</span>
          <strong>No ${escapeHtml(bandLabel)} comparison</strong>
        </div>
        <p>Selected council and ${escapeHtml(cohortLabel)} values are not both available for this band.</p>
      </aside>
    `;
  }
  const maxAbs = Math.max(...rows.map((row) => Math.abs(row.deltaPct)), 0.05);
  return `
    <aside class="distribution-band-delta-panel" aria-label="Max-level difference for selected band">
      <div class="distribution-band-delta-head">
        <span>Max level delta</span>
        <strong>${escapeHtml(bandLabel)} / ${escapeHtml(cohortLabel)}</strong>
      </div>
      <div class="distribution-band-delta-list">
        ${rows.map((row) => {
    const width = Math.max(4, Math.min(100, (Math.abs(row.deltaPct) / maxAbs) * 100));
    const negative = row.deltaPct < 0;
    const barStyle = negative
      ? `right:50%;width:${width / 2}%`
      : `left:50%;width:${width / 2}%`;
    const rowClass = negative ? "is-negative" : "is-positive";
    return `
          <div class="distribution-band-delta-row ${rowClass}">
            <span class="distribution-band-delta-label">B${escapeHtml(row.band)}<small>${escapeHtml(row.maxLevel ? `L${row.maxLevel}` : "max")}</small></span>
            <span class="distribution-band-delta-track" title="${escapeHtml(`Band ${row.band} max: selected ${displayCurrency(row.selectedValue)}, ${cohortLabel} average ${displayCurrency(row.cohortMean)} across ${formatCount(row.cohortCount, "0")} values`)}">
              <i style="${barStyle}"></i>
            </span>
            <strong>${escapeHtml(displayPercentDelta(row.deltaPct, DISPLAY_EMPTY, { fraction: true }))}</strong>
          </div>
        `;
  }).join("")}
      </div>
    </aside>
  `;
}

function renderReportingCohortSummary(rows, selectedDistributionKey = state.analysisChartDistributionCohortKey, comparatorKey = state.analysisChartCohortKey) {
  const cohorts = buildReportingCohorts(rows);
  return `
    <div class="distribution-cohort-grid" aria-label="Distribution curve cohorts">
      ${cohorts.map((cohort) => {
    const stats = payDistributionStats(cohort.rows);
    const count = cohort.rows.length;
    const selectedClass = cohort.key === selectedDistributionKey ? " is-active" : "";
    const comparatorClass = cohort.key === comparatorKey ? " is-comparator" : "";
    const pressed = cohort.key === selectedDistributionKey ? "true" : "false";
    const badges = [
      cohort.key === selectedDistributionKey ? "Curve" : "",
      cohort.key === comparatorKey ? "Comparator" : "",
    ].filter(Boolean);
    return `
        <button type="button" class="distribution-cohort-card distribution-cohort-${escapeHtml(cohort.key)}${selectedClass}${comparatorClass}" data-analysis-distribution-cohort-key="${escapeHtml(cohort.key)}" aria-pressed="${pressed}" title="${escapeHtml(`Use ${cohort.label} as the distribution curve. ${cohort.description || cohort.note}`)}">
          <span class="distribution-cohort-top">
            <span class="distribution-cohort-label">${escapeHtml(cohort.label)}</span>
            ${badges.length ? `<span class="distribution-cohort-badges">${badges.map((badge) => `<span>${escapeHtml(badge)}</span>`).join("")}</span>` : ""}
          </span>
          <strong>${escapeHtml(stats ? displayCurrency(stats.mean) : DISPLAY_EMPTY)}</strong>
          <small>${escapeHtml(formatCount(count, "0"))} values</small>
        </button>
      `;
  }).join("")}
    </div>
  `;
}

function renderReportingCohortExplainer(distributionCohort, comparatorCohort) {
  const items = [
    ["Distribution curve", distributionCohort],
    ["Comparator marker", comparatorCohort],
  ];
  return `
    <div class="distribution-cohort-explainer" aria-label="Selected chart cohorts">
      ${items.map(([label, cohort]) => `
        <div>
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(cohort?.label || "Selected cohort")}</strong>
          <p>${escapeHtml(cohort?.description || cohort?.note || "No cohort definition is available.")}</p>
        </div>
      `).join("")}
    </div>
  `;
}

function renderPayDistributionSvg(rows, stats, selectedCohort = null, currentRow = null, ariaLabel = "Weekly rate distribution", rangeMode = chartRangeMode()) {
  const width = 920;
  const height = 290;
  const pad = { left: 54, right: 26, top: 58, bottom: 42 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const values = stats.values;
  const cohort = selectedCohort || selectedReportingCohort(buildReportingCohorts(rows));
  const cohortStats = payDistributionStats(cohort?.rows || []);
  const currentValue = Number(currentRow?.weekly_rate);
  const comparatorExtremeRows = comparatorCohortExtremeRows(cohort);
  const comparatorExtremeValues = comparatorExtremeRows.map((item) => item.value).filter(Number.isFinite);
  const markerValues = [currentValue, cohortStats?.mean, ...comparatorExtremeValues].filter(Number.isFinite);
  const domainMin = Math.min(stats.min, stats.mean - (stats.stdDev * 3), ...markerValues);
  const domainMax = Math.max(stats.max, stats.mean + (stats.stdDev * 3), ...markerValues);
  const spread = Math.max(domainMax - domainMin, stats.stdDev * 6, 120);
  const xMin = Math.max(0, Math.floor((domainMin - spread * 0.04) / 25) * 25);
  const xMax = Math.ceil((domainMax + spread * 0.04) / 25) * 25;
  const xScale = (value) => pad.left + ((value - xMin) / Math.max(1, xMax - xMin)) * chartW;
  const salaryDensity = standardSalaryDensity(stats);
  const curveMin = stats.min;
  const curveMax = stats.max;
  const curveSamples = [
    ...Array.from({ length: 88 }, (_, index) => curveMin + ((curveMax - curveMin) * index / 87)),
    stats.mean,
  ].filter(Number.isFinite).sort((a, b) => a - b);
  const maxDensity = Math.max(...curveSamples.map(salaryDensity), 0.001);
  const yScale = (density) => pad.top + chartH - ((density / maxDensity) * chartH);
  const rangeOverlay = distributionRangeOverlay(stats, rangeMode);
  const rangeOverlayMarkup = rangeOverlay ? (() => {
    const rawX1 = xScale(rangeOverlay.min);
    const rawX2 = xScale(rangeOverlay.max);
    const boundedX1 = Math.max(pad.left, Math.min(width - pad.right, Math.min(rawX1, rawX2)));
    const boundedX2 = Math.max(pad.left, Math.min(width - pad.right, Math.max(rawX1, rawX2)));
    const overlayWidth = Math.max(6, boundedX2 - boundedX1);
    const overlayCenter = (boundedX1 + boundedX2) / 2;
    const overlayX = Math.max(pad.left, Math.min(width - pad.right - overlayWidth, overlayCenter - (overlayWidth / 2)));
    const labelX = Math.max(pad.left + 34, Math.min(width - pad.right - 34, overlayCenter));
    return `
      <g class="distribution-range-overlay distribution-range-${escapeHtml(rangeOverlay.key)}">
        <title>${escapeHtml(rangeOverlay.title)}</title>
        <rect x="${overlayX.toFixed(1)}" y="${(pad.top + 8).toFixed(1)}" width="${overlayWidth.toFixed(1)}" height="${(chartH - 8).toFixed(1)}"></rect>
        <line x1="${boundedX1.toFixed(1)}" x2="${boundedX1.toFixed(1)}" y1="${(pad.top + 8).toFixed(1)}" y2="${(pad.top + chartH).toFixed(1)}"></line>
        <line x1="${boundedX2.toFixed(1)}" x2="${boundedX2.toFixed(1)}" y1="${(pad.top + 8).toFixed(1)}" y2="${(pad.top + chartH).toFixed(1)}"></line>
        <text x="${labelX.toFixed(1)}" y="${(pad.top + 18).toFixed(1)}">${escapeHtml(rangeOverlay.shortLabel)}</text>
      </g>
    `;
  })() : "";
  const percentileLines = percentileDropMarkers(stats).map((marker) => {
    const x = xScale(marker.value);
    const axisY = pad.top + chartH;
    const isBoundary = marker.percentileValue === 0 || marker.percentileValue === 100;
    const markerY = yScale(salaryDensity(marker.value));
    const labelY = Math.min(height - 12, axisY + 18);
    const title = isBoundary
      ? `${marker.label} salary boundary: ${displayCurrency(marker.value)}`
      : `${marker.label}: ${displayCurrency(marker.value)}`;
    return `
      <g class="distribution-percentile-line distribution-percentile-${escapeHtml(String(marker.percentileValue))}${isBoundary ? " distribution-percentile-boundary" : ""}">
        <title>${escapeHtml(title)}</title>
        <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${markerY.toFixed(1)}" y2="${axisY.toFixed(1)}"></line>
        <circle cx="${x.toFixed(1)}" cy="${markerY.toFixed(1)}" r="${isBoundary ? "4.2" : "3.1"}"></circle>
        <text x="${x.toFixed(1)}" y="${labelY.toFixed(1)}">${escapeHtml(marker.label)}</text>
      </g>
    `;
  }).join("");
  const curvePath = values.length > 1 && curveMax > curveMin
    ? curveSamples.map((value, index) => `${index === 0 ? "M" : "L"} ${xScale(value).toFixed(1)} ${yScale(salaryDensity(value)).toFixed(1)}`).join(" ")
    : "";
  const tickValues = [xMin, stats.p25, stats.median, stats.p75, xMax]
    .filter((value, index, arr) => Number.isFinite(value) && arr.findIndex((v) => Math.round(v) === Math.round(value)) === index);
  const ticks = tickValues.map((value) => `
    <g class="distribution-tick">
      <line x1="${xScale(value).toFixed(1)}" x2="${xScale(value).toFixed(1)}" y1="${pad.top + chartH}" y2="${pad.top + chartH + 6}"></line>
      <text x="${xScale(value).toFixed(1)}" y="${height - 12}">${escapeHtml(displayCurrency(value, ""))}</text>
    </g>
  `).join("");
  const currentMarker = Number.isFinite(currentValue) ? `
    <g class="distribution-current-marker">
      ${(() => {
    const x = xScale(currentValue);
    const curveY = yScale(salaryDensity(currentValue));
    const labelX = Math.max(pad.left + 8, Math.min(width - pad.right - 92, x - 30));
    const markerLabelGap = 58;
    const markerLabelTop = 16;
    const labelY = Math.max(markerLabelTop, curveY - markerLabelGap);
    const leaderEndY = Math.min(curveY - 8, labelY + 10);
    const markerBasis = currentRow?.chart_basis === CHART_BASE_DATE_SMOOTHED
      ? "Selected council date-smoothed"
      : currentRow?.chart_basis === CHART_BASE_FOUR_QUARTER_AVERAGE
        ? "Selected council 4Q average"
        : "Selected council";
    return `
          <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${curveY.toFixed(1)}" y2="${leaderEndY.toFixed(1)}"></line>
          <circle cx="${x.toFixed(1)}" cy="${curveY.toFixed(1)}" r="4.8"></circle>
          <text x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}">${escapeHtml(currentRow?.canonical_lga_short_name || "selected")}</text>
          <title>${escapeHtml(`${markerBasis}: ${displayCurrency(currentValue)}`)}</title>
        `;
  })()}
    </g>
  ` : "";
  const comparatorExtremeMarkers = comparatorExtremeRows.length ? comparatorExtremeRows.map((item, index) => {
    const x = xScale(item.value);
    const curveY = yScale(salaryDensity(item.value));
    const labelShift = item.key === "high" ? -46 : 46;
    const labelX = Math.max(pad.left + 48, Math.min(width - pad.right - 48, x + labelShift));
    const labelY = Math.max(18, curveY - 48 - (index * 18));
    const leaderEndY = Math.min(curveY - 7, labelY + 10);
    const councilLabel = distributionRowCouncilLabel(item.row);
    const visibleLabel = `${item.key === "high" ? "High" : item.key === "low" ? "Low" : "Low/high"} ${councilLabel}`;
    return `
      <g class="distribution-comparator-extreme-marker distribution-comparator-extreme-${escapeHtml(item.key)}">
        <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${curveY.toFixed(1)}" y2="${leaderEndY.toFixed(1)}"></line>
        <circle cx="${x.toFixed(1)}" cy="${curveY.toFixed(1)}" r="4.1"></circle>
        <text x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}">${escapeHtml(visibleLabel)}</text>
        <title>${escapeHtml(`${item.label}: ${councilLabel} ${displayCurrency(item.value)} in ${cohort?.label || "comparator cohort"}`)}</title>
      </g>
    `;
  }).join("") : "";
  const cohortAverageMarker = cohortStats ? `
    <g class="distribution-selected-cohort-average-marker">
      ${(() => {
    const x = xScale(cohortStats.mean);
    const curveY = yScale(salaryDensity(cohortStats.mean));
    const visibleLabel = `${cohort.label} avg`;
    const labelX = Math.max(pad.left + 8, Math.min(width - pad.right - 112, x - 42));
    const labelY = Math.min(pad.top + chartH - 12, curveY + 36);
    return `
          <line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${curveY.toFixed(1)}" y2="${(labelY - 9).toFixed(1)}"></line>
          <circle cx="${x.toFixed(1)}" cy="${curveY.toFixed(1)}" r="4.4"></circle>
          <text x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}">${escapeHtml(visibleLabel)}</text>
          <title>${escapeHtml(`${cohort.label} average: ${displayCurrency(cohortStats.mean)} across ${formatCount(cohortStats.count, "0")} values`)}</title>
        `;
  })()}
    </g>
  ` : "";
  return `
    <svg class="distribution-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(ariaLabel)}">
      <line class="distribution-axis" x1="${pad.left}" x2="${width - pad.right}" y1="${pad.top + chartH}" y2="${pad.top + chartH}"></line>
      ${rangeOverlayMarkup}
      <g class="distribution-percentile-lines">${percentileLines}</g>
      ${curvePath ? `<path class="distribution-curve" d="${curvePath}"></path>` : ""}
      ${comparatorExtremeMarkers}
      ${cohortAverageMarker}
      ${currentMarker}
      ${ticks}
    </svg>
  `;
}

function renderDistributionBasisToggle(mode) {
  const options = [
    [CHART_BASE_CURRENT, "Selected quarter"],
    [CHART_BASE_FOUR_QUARTER_AVERAGE, "4Q average"],
    [CHART_BASE_DATE_SMOOTHED, "Date-smoothed"],
  ];
  return `
    <div class="distribution-basis-toggle" role="group" aria-label="Chart base value">
      ${options.map(([value, label]) => `
        <button
          type="button"
          class="${value === mode ? "is-active" : ""}"
          data-distribution-basis="${escapeHtml(value)}"
          aria-pressed="${value === mode ? "true" : "false"}"
        >${escapeHtml(label)}</button>
      `).join("")}
    </div>
  `;
}

function renderDistributionRangeToggle(mode = chartRangeMode()) {
  const options = [
    [CHART_RANGE_NONE, "No range"],
    [CHART_RANGE_IQR, "IQR"],
    [CHART_RANGE_STD_DEV, "1 SD"],
  ];
  return `
    <div class="distribution-range-toggle" role="group" aria-label="Chart range overlay">
      ${options.map(([value, label]) => `
        <button
          type="button"
          class="${value === mode ? "is-active" : ""}"
          data-distribution-range="${escapeHtml(value)}"
          aria-pressed="${value === mode ? "true" : "false"}"
        >${escapeHtml(label)}</button>
      `).join("")}
    </div>
  `;
}

function renderChartSelectorControls(context) {
  const quarterStart = context?.quarterStart || selectedChartQuarterStart();
  const selectedYear = quarterStart.slice(0, 4);
  const selectedQuarter = String(quarterNumberFromIso(quarterStart));
  const availableQuarters = chartAvailableQuarterStarts(context?.band);
  const years = [...new Set(availableQuarters.map((start) => start.slice(0, 4)))];
  const quarters = availableQuarters
    .filter((start) => start.slice(0, 4) === selectedYear)
    .map((start) => quarterNumberFromIso(start));
  const bands = chartAvailableBands();
  return `
    <div class="distribution-picker-grid" aria-label="Chart date and band">
      <label>
        <span>Year</span>
        <select data-chart-year>
          ${years.map((year) => `<option value="${escapeHtml(year)}"${year === selectedYear ? " selected" : ""}>${escapeHtml(year)}</option>`).join("")}
        </select>
      </label>
      <label>
        <span>Quarter</span>
        <select data-chart-quarter>
          ${(quarters.length ? quarters : [1, 2, 3, 4]).map((quarter) => `<option value="${quarter}"${String(quarter) === selectedQuarter ? " selected" : ""}>Q${quarter}</option>`).join("")}
        </select>
      </label>
      <label>
        <span>Band</span>
        <select data-chart-band>
          ${bands.map((band) => `<option value="${escapeHtml(band)}"${band === context.band ? " selected" : ""}>Band ${escapeHtml(band)}</option>`).join("")}
        </select>
      </label>
      <div class="distribution-level-span">
        <span>Levels</span>
        <strong>${escapeHtml(context.levelSpan?.label || "Levels not available")}</strong>
      </div>
    </div>
  `;
}

function wireDistributionBasisToggle(host) {
  host.querySelectorAll("[data-distribution-basis]").forEach((button) => {
    button.addEventListener("click", () => {
      setChartBaseMode(button.dataset.distributionBasis);
    });
  });
  host.querySelectorAll("[data-distribution-range]").forEach((button) => {
    button.addEventListener("click", () => {
      setChartRangeMode(button.dataset.distributionRange);
    });
  });
}

function setChartBaseMode(value) {
  const next = [CHART_BASE_FOUR_QUARTER_AVERAGE, CHART_BASE_DATE_SMOOTHED].includes(value)
    ? value
    : CHART_BASE_CURRENT;
  if (state.analysisChartBaseMode === next && state.currentDataSet === "charts") return;
  state.analysisChartBaseMode = next;
  if (state.currentDataSet !== "charts") setCurrentDataSet("charts");
  renderAnalysisWorkspace();
}

function setChartRangeMode(value) {
  const next = value === CHART_RANGE_IQR
    ? CHART_RANGE_IQR
    : value === CHART_RANGE_STD_DEV
      ? CHART_RANGE_STD_DEV
      : CHART_RANGE_NONE;
  if (state.analysisChartRangeMode === next && state.currentDataSet === "charts") return;
  state.analysisChartRangeMode = next;
  if (state.currentDataSet !== "charts") setCurrentDataSet("charts");
  renderAnalysisWorkspace();
}

function setChartQuarterStart(value) {
  state.analysisChartQuarterStart = isIso(value) ? value : currentQuarterStartIso();
  renderAnalysisWorkspace();
}

function setChartBand(value) {
  state.analysisChartBand = value || DEFAULT_ANALYSIS_CHART_BAND;
  renderAnalysisWorkspace();
}

function setChartCohortKey(value) {
  const next = value || DEFAULT_ANALYSIS_CHART_COHORT_KEY;
  if (state.analysisChartCohortKey === next && state.currentDataSet === "charts") return;
  state.analysisChartCohortKey = next;
  state.analysisFilter = "";
  if (state.currentDataSet !== "charts") setCurrentDataSet("charts");
  const filter = document.getElementById("analysis-filter");
  if (filter) filter.value = "";
  renderAnalysisWorkspace();
}

function setChartDistributionCohortKey(value) {
  const next = value || DEFAULT_ANALYSIS_CHART_DISTRIBUTION_COHORT_KEY;
  if (state.analysisChartDistributionCohortKey === next && state.currentDataSet === "charts") return;
  state.analysisChartDistributionCohortKey = next;
  if (state.currentDataSet !== "charts") setCurrentDataSet("charts");
  renderAnalysisWorkspace();
}

function reportExportAsset() {
  return reportExportAssetState(state);
}

function reportAssetStatus(asset = reportExportAsset()) {
  return String(asset?.manifest?.status || "draft").toLowerCase();
}

function reportAssetStatusLabel(status) {
  return REPORT_ASSET_STATUS_LABELS[status] || displayCodeLabel(status);
}

async function updateReportAssetStatus(status) {
  return updateReportAssetStatusState(state, status);
}

function renderReportExportFileMeta(file) {
  if (!file?.exists) return "Not generated";
  return [
    displayFileSize(file.bytes),
    file.last_modified ? displayDate(file.last_modified) : "",
  ].filter(Boolean).join(" / ");
}

function renderReportExportTarget(target) {
  const format = String(target.format || "").toLowerCase();
  const file = target.file || {};
  const exists = Boolean(file.exists);
  return `
    <article class="report-export-target ${exists ? "is-ready" : "is-missing"}">
      <div>
        <span>${escapeHtml(REPORT_EXPORT_FORMAT_LABELS[format] || format.toUpperCase())}</span>
        <strong>${escapeHtml(exists ? "Generated" : "Pending")}</strong>
        <small title="${escapeHtml(file.path || "")}">${escapeHtml(renderReportExportFileMeta(file))}</small>
      </div>
      ${exists ? `<a href="${escapeHtml(reportExportDownloadHref(format))}" download>Download</a>` : `<em>Waiting</em>`}
    </article>
  `;
}

function renderReportAssetLifecycle(asset, manifestValid) {
  const currentStatus = reportAssetStatus(asset);
  const assetId = asset?.asset_id || "distribution_point_analysis_default";
  const updatedAt = asset?.manifest?.status_updated_at
    ? `Updated ${displayDate(asset.manifest.status_updated_at)}`
    : "No lifecycle update recorded";
  const buttons = REPORT_ASSET_LIFECYCLE_STATUSES.map((status) => {
    const active = currentStatus === status;
    const label = reportAssetStatusLabel(status);
    return `
      <button
        id="report-asset-status-${escapeHtml(status)}"
        type="button"
        class="${active ? "is-active" : ""}"
        aria-pressed="${active ? "true" : "false"}"
        data-report-asset-status-target="${escapeHtml(status)}"
        ${!manifestValid || active ? "disabled" : ""}
      >${escapeHtml(label)}</button>
    `;
  }).join("");
  return `
    <div class="report-export-lifecycle">
      <div>
        <span>Lifecycle</span>
        <strong>${escapeHtml(reportAssetStatusLabel(currentStatus))}</strong>
        <small title="${escapeHtml(assetId)}">${escapeHtml(updatedAt)}</small>
      </div>
      <div class="report-export-lifecycle-actions" role="group" aria-label="Report asset lifecycle status">
        ${buttons}
      </div>
    </div>
  `;
}

function renderReportExportPanel() {
  const host = document.getElementById("report-export-panel");
  if (!host) return;
  host.hidden = state.currentDataSet !== "charts";
  if (state.currentDataSet !== "charts") {
    host.innerHTML = "";
    return;
  }
  const asset = reportExportAsset();
  const targets = asset?.targets || [];
  const readyCount = targets.filter((target) => target.file?.exists).length;
  const manifestValid = Boolean(asset?.manifest?.validation?.valid);
  const assetStatus = reportAssetStatus(asset);
  const exportManifest = asset?.export_manifest || state.reportExportResult?.manifest || {};
  const rowCount = state.reportExportResult?.row_count;
  const generatedLabel = exportManifest?.exists
    ? renderReportExportFileMeta(exportManifest)
    : "No export manifest";
  if (state.reportExportError && !asset) {
    host.innerHTML = `
      <div class="report-export-card workbench-card-scaffold report-export-card-error">
        <div>
          <span class="distribution-eyebrow">Report assets</span>
          <h3>Export catalog unavailable</h3>
          <p>${escapeHtml(state.reportExportError)}</p>
        </div>
        <button id="report-export-refresh" type="button">Retry</button>
      </div>
    `;
    wireReportExportPanel(host);
    return;
  }
  host.innerHTML = `
    <div class="report-export-card workbench-card-scaffold">
      <div class="report-export-head">
        <div>
          <span class="distribution-eyebrow">Report asset outputs</span>
          <h3>Distribution point export pack</h3>
          ${renderInlineMeta([
            reportAssetStatusLabel(assetStatus),
            `${formatCount(readyCount, "0")}/${formatCount(targets.length, "0")} formats ready`,
            exportManifest?.exists ? "Manifest generated" : "Manifest pending",
            `${formatCount(rowCount ?? state.analysisData?.summary?.distribution_points ?? state.analysisData?.rows?.length ?? 0, "0")} rows`,
          ], "report-export-meta workbench-inline-meta")}
        </div>
        <div class="report-export-controls">
          <label>
            <span>Rows</span>
            <input id="report-export-row-limit" type="number" min="0" step="1" inputmode="numeric" placeholder="All" />
          </label>
          <button id="report-export-refresh" type="button">Refresh</button>
          <button id="report-export-generate" class="primary" type="button"${manifestValid ? "" : " disabled"}>Generate exports</button>
        </div>
      </div>
      <div class="report-export-summary">
        <div><span>Formats ready</span><strong>${escapeHtml(`${formatCount(readyCount, "0")}/${formatCount(targets.length, "0")}`)}</strong></div>
        <div><span>Asset status</span><strong>${escapeHtml(reportAssetStatusLabel(assetStatus))}</strong></div>
        <div><span>Manifest</span><strong>${escapeHtml(exportManifest?.exists ? "Generated" : "Pending")}</strong></div>
        <div><span>Source rows</span><strong>${escapeHtml(formatCount(rowCount ?? state.analysisData?.summary?.distribution_points ?? state.analysisData?.rows?.length ?? 0, "0"))}</strong></div>
      </div>
      ${renderReportAssetLifecycle(asset, manifestValid)}
      <div class="report-export-target-grid">
        ${targets.length ? targets.map(renderReportExportTarget).join("") : `<div class="muted">No export targets published yet.</div>`}
      </div>
      <div class="report-export-foot">
        <span>${escapeHtml(generatedLabel)}</span>
        ${exportManifest?.exists ? `<a href="${escapeHtml(reportExportDownloadHref("manifest"))}" download>Manifest</a>` : ""}
      </div>
    </div>
  `;
  wireReportExportPanel(host);
}

function wireReportExportPanel(host) {
  host.querySelector("#report-export-refresh")?.addEventListener("click", async () => {
    try {
      await ensureReportExportCatalog({ force: true });
      renderReportExportPanel();
    } catch (error) {
      toast(apiErrorMessage(error), "error");
      renderReportExportPanel();
    }
  });
  host.querySelector("#report-export-generate")?.addEventListener("click", async () => {
    const input = host.querySelector("#report-export-row-limit");
    const rawLimit = String(input?.value || "").trim();
    const rowLimit = rawLimit ? Number(rawLimit) : null;
    if (rawLimit && (!Number.isFinite(rowLimit) || rowLimit < 0)) {
      toast("Row limit must be zero or greater.", "error");
      return;
    }
    const query = rowLimit === null ? "" : `?row_limit=${encodeURIComponent(String(Math.floor(rowLimit)))}`;
    try {
      await withBusyButton("report-export-generate", "Generating...", async () => {
        const result = await api(`${REPORT_EXPORT_ENDPOINT}${query}`, { method: "POST" });
        state.reportExportResult = result.exports || null;
        await ensureReportExportCatalog({ force: true });
      });
      const count = state.reportExportResult?.row_count;
      toast(`Generated report exports${Number.isFinite(Number(count)) ? ` for ${formatCount(count, "0")} rows` : ""}`, "success");
      renderReportExportPanel();
    } catch (error) {
      toast(apiErrorMessage(error), "error");
      renderReportExportPanel();
    }
  });
  host.querySelectorAll("[data-report-asset-status-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const nextStatus = button.dataset.reportAssetStatusTarget;
      if (!nextStatus) return;
      try {
        await withBusyButton(button.id, "Updating...", async () => {
          await updateReportAssetStatus(nextStatus);
        });
        toast(`Report asset marked ${reportAssetStatusLabel(nextStatus).toLowerCase()}`, "success");
        renderReportExportPanel();
      } catch (error) {
        toast(apiErrorMessage(error), "error");
        renderReportExportPanel();
      }
    });
  });
}

function renderPayDistributionPanel() {
  const host = document.getElementById("analysis-distribution-panel");
  if (!host) return;
  host.hidden = state.currentDataSet !== "charts";
  if (state.currentDataSet !== "charts") {
    host.innerHTML = "";
    return;
  }
  const context = chartPayDistributionContext();
  const { rows, mode, rangeMode, band, quarterStart, quarterStarts, basisLabel, rangeLabel, bandLabel, levelSpan } = context;
  const allStats = payDistributionStats(rows);
  if (!allStats) {
    host.innerHTML = `
      <div class="distribution-card workbench-card-scaffold distribution-card-empty">
        <div class="distribution-card-head">
          <div>
          <span class="distribution-eyebrow">${escapeHtml(bandLabel)} / ${escapeHtml(levelSpan.label)}</span>
          <h3>${escapeHtml(basisLabel)} distribution</h3>
          ${renderInlineMeta([
            `No governed ${bandLabel} rows`,
            rangeLabel,
            levelSpan.label,
          ], "distribution-card-meta workbench-inline-meta")}
        </div>
          <div class="distribution-head-actions">
            ${renderChartSelectorControls(context)}
            ${renderDistributionBasisToggle(mode)}
            ${renderDistributionRangeToggle(rangeMode)}
          </div>
        </div>
      </div>
    `;
    wireDistributionBasisToggle(host);
    return;
  }
  const currentRow = currentCouncilDistributionRow(rows);
  const reportingCohorts = buildReportingCohorts(rows);
  const comparatorCohort = selectedReportingCohort(reportingCohorts);
  const distributionCohort = selectedDistributionCohort(reportingCohorts);
  const distributionRows = distributionCohort?.rows?.length ? distributionCohort.rows : rows;
  const stats = payDistributionStats(distributionRows) || allStats;
  const comparatorStats = payDistributionStats(comparatorCohort?.rows || []);
  const selectedGap = currentRow && comparatorStats ? currentRow.weekly_rate - comparatorStats.mean : null;
  const selectedQuarterCount = currentRow?.chart_quarter_count;
  const selectedRawRow = mode === CHART_BASE_DATE_SMOOTHED
    ? selectedCouncilRawQuarterRow({ band, quarterStart })
    : null;
  const selectedSmoothedFootnote = smoothedBasisFootnote(currentRow, selectedRawRow, quarterStart);
  const selectedStatLabel = selectedCouncilStatLabel(mode);
  const rangeOverlay = distributionRangeOverlay(stats, rangeMode);
  host.innerHTML = `
    <div class="distribution-card workbench-card-scaffold">
      <div class="distribution-card-head">
        <div>
          <span class="distribution-eyebrow">${escapeHtml(bandLabel)} weekly midpoint</span>
          <h3>${escapeHtml(distributionCohort?.label || "Selected cohort")} distribution / ${escapeHtml(comparatorCohort?.label || "selected cohort")} comparator</h3>
          ${renderInlineMeta([
            basisLabel,
            rangeLabel,
            levelSpan.label,
            `Curve ${distributionCohort?.label || "selected cohort"}`,
            `Comparator ${comparatorCohort?.label || "selected cohort"}`,
          ], "distribution-card-meta workbench-inline-meta")}
        </div>
        <div class="distribution-head-actions">
          ${renderChartSelectorControls(context)}
          ${renderDistributionBasisToggle(mode)}
          ${renderDistributionRangeToggle(rangeMode)}
          <div class="distribution-stat-grid">
            <div><span>Basis</span><strong>${escapeHtml(basisLabel)}</strong></div>
            <div><span>Comparator avg</span><strong>${escapeHtml(comparatorStats ? displayCurrency(comparatorStats.mean) : DISPLAY_EMPTY)}</strong></div>
            <div><span>${escapeHtml(selectedStatLabel)}</span><strong>${escapeHtml(currentRow ? displayCurrency(currentRow.weekly_rate) : DISPLAY_EMPTY)}</strong></div>
            <div><span>Delta</span><strong>${escapeHtml(selectedGap !== null ? displayCurrencyDelta(selectedGap) : DISPLAY_EMPTY)}</strong></div>
          </div>
        </div>
      </div>
      <div class="distribution-chart-grid">
        <div class="distribution-curve-panel">
          ${renderPayDistributionSvg(distributionRows, stats, comparatorCohort, currentRow, `${distributionCohort?.label || "Selected cohort"} ${bandLabel} ${levelSpan.label} weekly midpoint distribution with ${comparatorCohort?.label || "selected cohort"} comparator`, rangeMode)}
        </div>
        ${renderBandMaxDeltaBars(context, comparatorCohort)}
      </div>
      ${renderReportingCohortSummary(rows, distributionCohort?.key, comparatorCohort?.key)}
      ${renderReportingCohortExplainer(distributionCohort, comparatorCohort)}
      <div class="distribution-foot">
        <span>Curve ${escapeHtml(distributionCohort?.label || "Selected cohort")} range ${escapeHtml(displayCurrency(stats.min))} to ${escapeHtml(displayCurrency(stats.max))}</span>
        <span>Comparator ${escapeHtml(comparatorCohort?.label || "Selected cohort")} average ${escapeHtml(comparatorStats ? displayCurrency(comparatorStats.mean) : DISPLAY_EMPTY)}</span>
        <span>${escapeHtml(formatCount(comparatorStats?.count || 0, "0"))} comparator values</span>
        <span>${escapeHtml(bandLabel)} ${escapeHtml(levelSpan.label)}</span>
        <span>Basis ${escapeHtml(rangeLabel)}</span>
        ${selectedQuarterCount ? `<span>Selected value averaged from ${escapeHtml(formatCount(selectedQuarterCount, "0"))}/${escapeHtml(formatCount(quarterStarts.length, "0"))} quarters</span>` : ""}
        ${selectedSmoothedFootnote ? `<span>${escapeHtml(selectedSmoothedFootnote)}</span>` : ""}
        ${mode === CHART_BASE_DATE_SMOOTHED ? "<span>Date-smoothed values estimate each council's dated rate trajectory</span>" : ""}
        ${rangeOverlay ? `<span>${escapeHtml(rangeOverlay.shortLabel)} ${escapeHtml(displayCurrency(rangeOverlay.min))} to ${escapeHtml(displayCurrency(rangeOverlay.max))}</span>` : ""}
        ${currentRow ? `<span>Selected council ${escapeHtml(displayCurrency(currentRow.weekly_rate))}</span>` : ""}
      </div>
    </div>
  `;
  wireDistributionBasisToggle(host);
}

function renderPayCandidateQualityPanel() {
  const host = document.getElementById("pay-candidate-quality-panel");
  if (!host) return;
  if (!currentDataSetConfig().showCandidateDiagnostics) {
    host.hidden = true;
    host.innerHTML = "";
    return;
  }
  const quality = state.currentDataSet === "pay_tables" ? state.analysisData?.candidate_quality : null;
  const summary = quality?.summary || {};
  const falsePositivePages = quality?.false_positive_pages || [];
  const missedUsedPages = quality?.missed_used_pages || [];
  const reasonPatterns = quality?.patterns || [];
  const recommendations = quality?.recommendations || [];
  if (!quality || (!falsePositivePages.length && !missedUsedPages.length && !reasonPatterns.length)) {
    host.hidden = true;
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  const maxReasonCount = Math.max(...reasonPatterns.map((item) => Number(item.count || 0)), 1);
  const unusedRate = typeof summary.unused_candidate_rate === "number"
    ? displayFractionPercent(summary.unused_candidate_rate, "0%")
    : DISPLAY_EMPTY;
  const topFalsePositiveRows = falsePositivePages.slice(0, 8).map((item) => {
    const signalBits = [
      item.standard_signal ? "standard signal" : "",
      item.allowance_signal ? "allowance signal" : "",
      item.specialist_signal ? "specialist cohort" : "",
      item.uplift_keyword_count ? `${formatCount(item.uplift_keyword_count, "0")} uplift terms` : "",
      item.dollar_count ? `${formatCount(item.dollar_count, "0")} dollar values` : "",
    ].filter(Boolean).join(" / ");
    return `
      <tr>
        <td class="analysis-entity-cell">
          <strong>${escapeHtml(item.canonical_lga_short_name || item.agreement_name || item.ae_id)}</strong>
          <span>${escapeHtml(String(item.ae_id || "").toUpperCase())}</span>
        </td>
        <td class="analysis-code-cell">${escapeHtml(displayPages(item.page))}</td>
        <td class="analysis-pattern-cell">
          <strong>${escapeHtml(displayCodeLabel(item.reason || "unknown_unused_candidate"))}</strong>
          ${signalBits ? `<span>${escapeHtml(signalBits)}</span>` : ""}
        </td>
        <td>${escapeHtml(item.excerpt || (item.text_available ? DISPLAY_EMPTY : "No page text available"))}</td>
        <td><button class="analysis-open-btn" data-analysis-open-ae="${escapeHtml(item.ae_id)}">Open</button></td>
      </tr>
    `;
  }).join("");
  const missedRows = missedUsedPages.slice(0, 4).map((item) => `
    <span>${escapeHtml(item.canonical_lga_short_name || item.agreement_name || item.ae_id)} ${escapeHtml(displayPages(item.page))}</span>
  `).join("");
  host.innerHTML = `
    <details class="pay-candidate-quality-card workbench-card-scaffold">
      <summary class="pay-candidate-quality-summary">
        <span class="distribution-eyebrow">Candidate QA</span>
        <strong>False-positive analysis</strong>
        <span>${escapeHtml(`${formatCount(summary.unused_candidate_pages, "0")} unused / ${unusedRate}; ${formatCount(summary.missed_used_pages, "0")} missed used`)}</span>
      </summary>
      <div class="pay-candidate-quality-details">
        <div class="pay-candidate-quality-head">
          <div>
            <span class="distribution-eyebrow">Candidate false-positive analysis</span>
            <h3>Tagged pages not used by governed pay tables</h3>
            ${renderInlineMeta([
              `${formatCount(summary.candidate_pages, "0")} candidates`,
              `${formatCount(summary.unused_candidate_pages, "0")} unused`,
              `${unusedRate} unused rate`,
              `${formatCount(summary.missed_used_pages, "0")} missed used`,
            ], "pay-candidate-quality-meta workbench-inline-meta")}
          </div>
          <div class="pay-candidate-stat-grid">
            <div><span>Candidates</span><strong>${escapeHtml(formatCount(summary.candidate_pages, "0"))}</strong></div>
            <div><span>Unused</span><strong>${escapeHtml(formatCount(summary.unused_candidate_pages, "0"))}</strong></div>
            <div><span>Unused rate</span><strong>${escapeHtml(unusedRate)}</strong></div>
            <div><span>Missed used</span><strong>${escapeHtml(formatCount(summary.missed_used_pages, "0"))}</strong></div>
          </div>
        </div>
        <div class="pay-candidate-quality-body">
          <div class="pay-candidate-reason-list">
            ${reasonPatterns.length ? reasonPatterns.slice(0, 8).map((item) => {
              const width = Math.max(8, Math.round((Number(item.count || 0) / maxReasonCount) * 100));
              return `
                <div class="pay-candidate-reason-row">
                  <span>${escapeHtml(displayCodeLabel(item.pattern))}</span>
                  <strong>${escapeHtml(formatCount(item.count, "0"))}</strong>
                  <i><b style="width:${width}%"></b></i>
                </div>
              `;
            }).join("") : `<div class="muted">No unused candidate reasons detected.</div>`}
          </div>
          <div class="pay-candidate-rule-list">
            ${recommendations.length ? recommendations.slice(0, 4).map((item) => `
              <div class="pay-candidate-rule">
                <strong>${escapeHtml(displayCodeLabel(item.rule))}</strong>
                <span>${escapeHtml(item.action || item.message || item.trigger || "")}</span>
              </div>
            `).join("") : `<div class="muted">No rule refinements suggested.</div>`}
          </div>
        </div>
        ${missedRows ? `<div class="pay-candidate-missed"><strong>Used pages not in candidates</strong>${missedRows}</div>` : ""}
        ${topFalsePositiveRows ? `
          <div class="pay-candidate-table-scroll">
            <table class="analysis-data-table pay-candidate-table">
              <thead>
                <tr>
                  <th>Agreement</th>
                  <th>Page</th>
                  <th>Reason</th>
                  <th>Page clue</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>${topFalsePositiveRows}</tbody>
            </table>
          </div>
        ` : ""}
      </div>
    </details>
  `;
  wireAnalysisOpenButtons(host, "pay_tables");
}

function analysisRuleSearchText(row) {
  if (state.currentDataSet === "councils") {
    return [
      row.council_key,
      row.short_name,
      row.long_name,
      row.status,
      row.council_type,
      row.council_category,
      row.spatial_name,
      row.official_name,
      row.lga_code,
      row.abs_lga_code,
      row.office_township,
      row.office_address,
      row.office_geocoded,
      row.polygon_attributed,
      row.map_join_key,
      row.spatial_key,
      row.vif_metropolitan_region,
      row.vif_regional_partnership,
      row.vec_electoral_structure,
      row.vec_councillor_count,
      row.vec_ward_count,
      row.lgprf_group,
      row.governance_yes_count,
      row.governance_item_count,
      row.vgccc_region,
      row.vgccc_seifa_dis_score,
      row.vgccc_unemployment_rate_june_2024,
    ].filter(Boolean).join(" ").toLowerCase();
  }
  if (state.currentDataSet === "pay_tables") {
    return [
      row.ae_id,
      row.agreement_name,
      row.canonical_lga_short_name,
      row.effective_from,
      row.to_date,
      row.table_title,
      row.rate_kind,
      row.source_clause,
      row.source_page !== null && row.source_page !== undefined ? `page ${row.source_page}` : "",
      row.band !== null && row.band !== undefined ? `band ${row.band}` : "",
      row.level !== null && row.level !== undefined ? `level ${row.level}` : "",
      row.standard_band !== null && row.standard_band !== undefined ? `standard band ${row.standard_band}` : "",
      row.standard_level !== null && row.standard_level !== undefined ? `standard level ${row.standard_level}` : "",
      row.classification_key,
      row.classification_label,
      row.title,
      row.notes,
      row.weekly_rate_basis,
      row.weekly_rate !== null && row.weekly_rate !== undefined ? `weekly ${row.weekly_rate}` : "",
    ].filter(Boolean).join(" ").toLowerCase();
  }
  if (state.currentDataSet === "end_of_band_dollars") {
    return [
      row.ae_id,
      row.agreement_name,
      row.canonical_lga_short_name,
      row.effective_from,
      row.to_date,
      row.band !== null && row.band !== undefined ? `band ${row.band}` : "",
      row.end_of_band_cash_amount !== null && row.end_of_band_cash_amount !== undefined ? `amount ${row.end_of_band_cash_amount}` : "",
      row.amount_basis,
      row.calculation_status,
      row.rule_kind,
      row.clause_number,
      row.clause_heading,
      row.source_page !== null && row.source_page !== undefined ? `page ${row.source_page}` : "",
      row.clause_extract,
    ].filter(Boolean).join(" ").toLowerCase();
  }
  return [
    row.ae_id,
    row.agreement_name,
    row.canonical_lga_short_name,
    row.effective_from,
    row.pattern_archetype,
    row.pattern_variant,
    row.source_rule_id,
    row.has_rate_cap ? "rate cap rate-cap cap linked" : "",
    row.resolved_basis,
    row.internal_pct_component !== null && row.internal_pct_component !== undefined ? `internal ${row.internal_pct_component}` : "",
    row.external_cap_share !== null && row.external_cap_share !== undefined ? `cap share ${row.external_cap_share}` : "",
    row.external_cap_pct !== null && row.external_cap_pct !== undefined ? `external cap ${row.external_cap_pct}` : "",
    row.resolved_pct !== null && row.resolved_pct !== undefined ? `resolved ${row.resolved_pct}` : "",
    (row.dollar_floor_component !== null && row.dollar_floor_component !== undefined)
      || (row.pct_floor_component !== null && row.pct_floor_component !== undefined)
      ? "floor minimum" : "",
  ].filter(Boolean).join(" ").toLowerCase();
}

function sortedAnalysisRows() {
  const rows = [...(state.analysisData?.rows || [])];
  const filter = state.analysisFilter.trim().toLowerCase();
  const filterTokens = filter.split(/\s+/).filter(Boolean);
  const filtered = filterTokens.length
    ? rows.filter((row) => {
      const searchText = analysisRuleSearchText(row);
      return filterTokens.every((token) => searchText.includes(token));
    })
    : rows;
  filtered.sort((a, b) => {
    if (state.currentDataSet === "councils") {
      if (state.analysisSort === "status") {
        return String(a.status || "").localeCompare(String(b.status || ""))
          || String(a.short_name || "").localeCompare(String(b.short_name || ""));
      }
      if (state.analysisSort === "type") {
        return String(a.council_type || "").localeCompare(String(b.council_type || ""))
          || String(a.short_name || "").localeCompare(String(b.short_name || ""));
      }
      if (state.analysisSort === "category") {
        return String(a.council_category || "").localeCompare(String(b.council_category || ""))
          || String(a.short_name || "").localeCompare(String(b.short_name || ""));
      }
      if (state.analysisSort === "region") {
        return String(a.vif_regional_partnership || a.vif_metropolitan_region || "").localeCompare(String(b.vif_regional_partnership || b.vif_metropolitan_region || ""))
          || String(a.short_name || "").localeCompare(String(b.short_name || ""));
      }
      if (state.analysisSort === "electoral") {
        const aCount = Number.isFinite(Number(a.vec_councillor_count)) ? Number(a.vec_councillor_count) : Number.POSITIVE_INFINITY;
        const bCount = Number.isFinite(Number(b.vec_councillor_count)) ? Number(b.vec_councillor_count) : Number.POSITIVE_INFINITY;
        return aCount - bCount
          || String(a.short_name || "").localeCompare(String(b.short_name || ""));
      }
      return String(a.short_name || "").localeCompare(String(b.short_name || ""));
    }
    if (state.currentDataSet === "pay_tables") {
      if (state.analysisSort === "council") {
        return String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""));
      }
      if (state.analysisSort === "classification") {
        const aSort = Number.isFinite(Number(a.classification_sort)) ? Number(a.classification_sort) : Number.POSITIVE_INFINITY;
        const bSort = Number.isFinite(Number(b.classification_sort)) ? Number(b.classification_sort) : Number.POSITIVE_INFINITY;
        return aSort - bSort
          || String(a.standard_band || a.band || "").localeCompare(String(b.standard_band || b.band || ""), undefined, { numeric: true })
          || String(a.standard_level || a.level || "").localeCompare(String(b.standard_level || b.level || ""), undefined, { numeric: true })
          || String(a.effective_from || "").localeCompare(String(b.effective_from || ""));
      }
      if (state.analysisSort === "weekly_rate") {
        const aRate = Number.isFinite(Number(a.weekly_rate)) ? Number(a.weekly_rate) : Number.POSITIVE_INFINITY;
        const bRate = Number.isFinite(Number(b.weekly_rate)) ? Number(b.weekly_rate) : Number.POSITIVE_INFINITY;
        return aRate - bRate
          || String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""));
      }
      return String(a.effective_from || "9999-99-99").localeCompare(String(b.effective_from || "9999-99-99"))
        || String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""))
        || String(a.standard_band || a.band || "").localeCompare(String(b.standard_band || b.band || ""), undefined, { numeric: true })
        || String(a.standard_level || a.level || "").localeCompare(String(b.standard_level || b.level || ""), undefined, { numeric: true });
    }
    if (state.currentDataSet === "end_of_band_dollars") {
      if (state.analysisSort === "council") {
        return String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""))
          || String(a.band || "").localeCompare(String(b.band || ""), undefined, { numeric: true });
      }
      if (state.analysisSort === "band") {
        return String(a.band || "").localeCompare(String(b.band || ""), undefined, { numeric: true })
          || String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""));
      }
      if (state.analysisSort === "amount") {
        const aAmount = Number.isFinite(Number(a.end_of_band_cash_amount)) ? Number(a.end_of_band_cash_amount) : Number.POSITIVE_INFINITY;
        const bAmount = Number.isFinite(Number(b.end_of_band_cash_amount)) ? Number(b.end_of_band_cash_amount) : Number.POSITIVE_INFINITY;
        return aAmount - bAmount
          || String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""));
      }
      return String(a.effective_from || "9999-99-99").localeCompare(String(b.effective_from || "9999-99-99"))
        || String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""))
        || String(a.band || "").localeCompare(String(b.band || ""), undefined, { numeric: true });
    }
    if (state.analysisSort === "council") {
      return String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""));
    }
    if (state.analysisSort === "pattern") {
      return String(a.pattern_archetype || "").localeCompare(String(b.pattern_archetype || ""))
        || String(a.effective_from || "").localeCompare(String(b.effective_from || ""));
    }
    return String(a.effective_from || "9999-99-99").localeCompare(String(b.effective_from || "9999-99-99"))
      || String(a.canonical_lga_short_name || a.agreement_name || "").localeCompare(String(b.canonical_lga_short_name || b.agreement_name || ""));
  });
  return filtered;
}

function renderAnalysisPatterns() {
  const host = document.getElementById("analysis-pattern-list");
  if (!host) return;
  const patterns = state.currentDataSet === "charts"
    ? buildReportingCohorts(chartPayDistributionContext().rows)
      .map((cohort) => ({
        pattern: cohort.label,
        count: cohort.rows.length,
        key: cohort.key,
        description: cohort.description,
      }))
    : state.currentDataSet === "councils"
      ? Object.entries((state.analysisData?.rows || []).reduce((acc, row) => {
      const category = row.council_category || "unknown";
      acc[category] = (acc[category] || 0) + 1;
      return acc;
    }, {})).map(([pattern, count]) => ({ pattern, count }))
      : state.analysisData?.patterns || [];
  if (!patterns.length) {
    const emptyLabel = state.currentDataSet === "councils"
      ? "No council status groups available."
      : `No promoted ${escapeHtml(currentDataSetConfig().label.toLowerCase())} groups yet.`;
    host.innerHTML = `<div class="muted">${emptyLabel}</div>`;
    return;
  }
  const max = Math.max(...patterns.map((item) => Number(item.count || 0)), 1);
  host.innerHTML = patterns.slice(0, 8).map((item) => {
    const width = Math.max(8, Math.round((Number(item.count || 0) / max) * 100));
    const selected = state.currentDataSet === "charts" && item.key === selectedReportingCohort(patterns)?.key;
    const classes = ["analysis-pattern-row", selected ? "is-active" : ""].filter(Boolean).join(" ");
    const cohortKeyAttr = item.key ? ` data-analysis-cohort-key="${escapeHtml(item.key)}"` : "";
    const pressedAttr = state.currentDataSet === "charts" ? ` aria-pressed="${selected ? "true" : "false"}"` : "";
    const titleAttr = item.description ? ` title="${escapeHtml(item.description)}"` : "";
    return `
      <button class="${classes}" data-analysis-pattern="${escapeHtml(item.pattern)}"${cohortKeyAttr}${pressedAttr}${titleAttr}>
        <span>${escapeHtml(displayCodeLabel(item.pattern))}</span>
        <strong>${escapeHtml(formatCount(item.count, "0"))}</strong>
        <i><b style="width:${width}%"></b></i>
      </button>
    `;
  }).join("");
  host.querySelectorAll("[data-analysis-pattern]").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.currentDataSet === "charts") {
        setChartCohortKey(button.dataset.analysisCohortKey);
        return;
      }
      state.analysisFilter = button.dataset.analysisPattern || "";
      const filter = document.getElementById("analysis-filter");
      if (filter) filter.value = state.analysisFilter;
      renderAnalysisWorkspace();
    });
  });
}

function renderAnalysisRows() {
  const host = document.getElementById("analysis-rule-table");
  const status = document.getElementById("analysis-status");
  if (!host) return;
  if (state.currentDataSet === "charts") {
    host.hidden = true;
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  const rows = sortedAnalysisRows();
  const total = state.analysisData?.rows?.length || 0;
  if (status) {
    const rowLabel = state.currentDataSet === "councils"
      ? "council reference rows"
      : state.currentDataSet === "pay_tables"
        ? "governed pay-table rows"
        : state.currentDataSet === "end_of_band_dollars"
          ? "end-of-band dollar rows"
          : "governed uplift rules";
    const assetId = ["pay_tables", "end_of_band_dollars"].includes(state.currentDataSet) && state.analysisData?.set_id
      ? `${state.analysisData.set_id}: `
      : "";
    status.textContent = `${assetId}Showing ${formatCount(rows.length, "0")} of ${formatCount(total, "0")} ${rowLabel}`;
  }
  if (!rows.length) {
    const config = currentDataSetConfig();
    host.innerHTML = renderEmptyState(
      `No ${config.label.toLowerCase()} match the current filters`,
      "Clear the current filter or switch data sets to inspect another governed entity set.",
      {
        eyebrow: "Data set",
        actionHtml: '<button class="intake-wide-btn workbench-empty-action" data-analysis-empty-clear="1">Clear data filters</button>',
      },
    );
    host.querySelector("[data-analysis-empty-clear]")?.addEventListener("click", () => {
      state.analysisFilter = "";
      const filter = document.getElementById("analysis-filter");
      if (filter) filter.value = "";
      renderAnalysisWorkspace();
    });
    return;
  }
  if (state.currentDataSet === "pay_tables") {
    renderPayTableDataRows(host, rows);
    return;
  }
  if (state.currentDataSet === "end_of_band_dollars") {
    renderEndOfBandDollarRows(host, rows);
    return;
  }
  if (state.currentDataSet === "councils") {
    renderCouncilReferenceRows(host, rows);
    return;
  }
  renderUpliftRuleDataRows(host, rows);
}

function wireAnalysisOpenButtons(host, section = "uplifts") {
  host.querySelectorAll("[data-analysis-open-ae]").forEach((button) => {
    button.addEventListener("click", () => openCouncil(button.dataset.analysisOpenAe, section));
  });
}

function renderUpliftRuleDataRows(host, rows) {
  host.innerHTML = `
    <div class="analysis-table-scroll">
      <table class="analysis-data-table">
        <thead>
          <tr>
            <th>Council / agreement</th>
            <th>AE ID</th>
            <th>Effective</th>
            <th>Pattern</th>
            <th>Fixed %</th>
            <th>Rate cap</th>
            <th>Cap result</th>
            <th>Floor</th>
            <th>Resolved</th>
            <th>Governed</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => {
      const components = row.normalised_components || {};
      const fixedPct = components.internal_pct_component !== null && components.internal_pct_component !== undefined
        ? displayPercent(components.internal_pct_component)
        : DISPLAY_EMPTY;
      const dollarFloor = components.dollar_floor_component !== null && components.dollar_floor_component !== undefined
        ? formatAnalysisDollar(components.dollar_floor_component, components.dollar_floor_basis)
        : DISPLAY_EMPTY;
      const pctFloor = components.pct_floor_component !== null && components.pct_floor_component !== undefined
        ? displayPercent(components.pct_floor_component)
        : DISPLAY_EMPTY;
      const rateCap = components.external_cap_pct !== null && components.external_cap_pct !== undefined
        ? displayPercent(components.external_cap_pct)
        : (row.has_rate_cap ? "Rate cap linked" : DISPLAY_EMPTY);
      const capShare = components.external_cap_share !== null && components.external_cap_share !== undefined
        ? displayFractionPercent(components.external_cap_share)
        : DISPLAY_EMPTY;
      const capDelta = components.external_cap_delta_pct !== null && components.external_cap_delta_pct !== undefined
        ? displayPercentDelta(components.external_cap_delta_pct)
        : DISPLAY_EMPTY;
      const resolved = components.resolved_pct !== null && components.resolved_pct !== undefined
        ? displayPercent(components.resolved_pct)
        : DISPLAY_EMPTY;
      const capFormula = components.external_formula_pct !== null && components.external_formula_pct !== undefined
        ? displayPercent(components.external_formula_pct)
        : DISPLAY_EMPTY;
      const basis = components.resolved_basis ? displayCodeLabel(components.resolved_basis) : DISPLAY_EMPTY;
      const capDisplay = [
        rateCap,
        capShare !== DISPLAY_EMPTY ? capShare : "",
        capDelta !== DISPLAY_EMPTY ? capDelta : "",
      ].filter(Boolean).join(" / ");
      const floorDisplay = dollarFloor !== DISPLAY_EMPTY
        ? dollarFloor
        : pctFloor !== DISPLAY_EMPTY
          ? pctFloor
          : DISPLAY_EMPTY;
      const ruleExpression = renderRuleExpressionCell(row);
      return `
        <tr class="analysis-rule-row">
          <td class="analysis-entity-cell">
            <strong>${escapeHtml(row.canonical_lga_short_name || row.agreement_name || row.ae_id)}</strong>
            <span>${escapeHtml(row.agreement_name || "")}</span>
          </td>
          <td class="analysis-code-cell">${escapeHtml(String(row.ae_id || "").toUpperCase())}</td>
          <td>${escapeHtml(displayDate(row.effective_from))}</td>
          <td class="analysis-pattern-cell">
            ${ruleExpression}
          </td>
          <td class="analysis-number-cell">${escapeHtml(fixedPct)}</td>
          <td class="analysis-number-cell">${escapeHtml(capDisplay || DISPLAY_EMPTY)}</td>
          <td class="analysis-number-cell">${escapeHtml(capFormula)}</td>
          <td class="analysis-number-cell">${escapeHtml(floorDisplay)}</td>
          <td class="analysis-resolved-cell">
            <strong>${escapeHtml(resolved)}</strong>
            <span>${escapeHtml(basis)}</span>
          </td>
          <td>${escapeHtml(displayDate(row.governed_at, "Not stated"))}</td>
          <td><button class="analysis-open-btn" data-analysis-open-ae="${escapeHtml(row.ae_id)}">Open</button></td>
        </tr>
      `;
    }).join("")}
        </tbody>
      </table>
    </div>
  `;
  wireAnalysisOpenButtons(host, "uplifts");
}

function renderPayTableDataRows(host, rows) {
  host.innerHTML = `
    <div class="analysis-table-scroll">
      <table class="analysis-data-table analysis-pay-table">
        <thead>
          <tr>
            <th>Council / agreement</th>
            <th>AE ID</th>
            <th>Effective</th>
            <th>To</th>
            <th>Table</th>
            <th>Source</th>
            <th>Band</th>
            <th>Level</th>
            <th>Title</th>
            <th>Weekly</th>
            <th>Basis</th>
            <th>Governed</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => {
      const sourceBits = [
        row.source_page !== null && row.source_page !== undefined ? `p.${row.source_page}` : "",
        row.source_clause ? `cl. ${row.source_clause}` : "",
      ].filter(Boolean).join(" / ");
      return `
        <tr class="analysis-rule-row">
          <td class="analysis-entity-cell" title="${escapeHtml(row.agreement_name || "")}">
            <strong>${escapeHtml(row.canonical_lga_short_name || row.agreement_name || row.ae_id)}</strong>
          </td>
          <td class="analysis-code-cell">${escapeHtml(String(row.ae_id || "").toUpperCase())}</td>
          <td>${escapeHtml(displayDate(row.effective_from))}</td>
          <td>${escapeHtml(displayDate(row.to_date))}</td>
          <td class="analysis-pattern-cell" title="${escapeHtml([row.table_title, row.effective_from_note].filter(Boolean).join(" / "))}">
            <strong>${escapeHtml(row.table_title || "Untitled table")}</strong>
          </td>
          <td class="analysis-code-cell" title="${escapeHtml(row.source_clause || "")}">${escapeHtml(sourceBits || DISPLAY_EMPTY)}</td>
          <td class="analysis-code-cell">${escapeHtml(displayValue(row.standard_band || row.band))}</td>
          <td class="analysis-code-cell">${escapeHtml(displayValue(row.standard_level || row.level))}</td>
          <td title="${escapeHtml(displayValue(row.title))}">${escapeHtml(displayValue(row.title))}</td>
          <td class="analysis-number-cell">${escapeHtml(displayCurrency(row.weekly_rate))}</td>
          <td>${escapeHtml(displayCodeLabel(row.weekly_rate_basis || "weekly_rate"))}</td>
          <td>${escapeHtml(displayDate(row.governed_at, "Not stated"))}</td>
          <td><button class="analysis-open-btn" data-analysis-open-ae="${escapeHtml(row.ae_id)}">Open</button></td>
        </tr>
      `;
    }).join("")}
        </tbody>
      </table>
    </div>
  `;
  wireAnalysisOpenButtons(host, "pay_tables");
}

function renderEndOfBandDollarRows(host, rows) {
  host.innerHTML = `
    <div class="analysis-table-scroll">
      <table class="analysis-data-table analysis-pay-table">
        <thead>
          <tr>
            <th>Council / agreement</th>
            <th>AE ID</th>
            <th>Effective</th>
            <th>To</th>
            <th>Band</th>
            <th>EOB cash</th>
            <th>Basis</th>
            <th>Status</th>
            <th>Clause</th>
            <th>Page</th>
            <th>Governed</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => {
      const clause = [
        row.clause_number ? `cl. ${row.clause_number}` : "",
        row.clause_heading || "",
      ].filter(Boolean).join(" ");
      return `
        <tr class="analysis-rule-row">
          <td class="analysis-entity-cell" title="${escapeHtml(row.agreement_name || "")}">
            <strong>${escapeHtml(row.canonical_lga_short_name || row.agreement_name || row.ae_id)}</strong>
          </td>
          <td class="analysis-code-cell">${escapeHtml(String(row.ae_id || "").toUpperCase())}</td>
          <td>${escapeHtml(displayDate(row.effective_from))}</td>
          <td>${escapeHtml(displayDate(row.to_date))}</td>
          <td class="analysis-code-cell">${escapeHtml(displayValue(row.band))}</td>
          <td class="analysis-number-cell"><strong>${escapeHtml(displayCurrency(row.end_of_band_cash_amount))}</strong></td>
          <td class="analysis-pattern-cell">
            <strong>${escapeHtml(displayCodeLabel(row.rule_kind || "cash"))}</strong>
            <span>${escapeHtml(displayCodeLabel(row.amount_basis || ""))}</span>
          </td>
          <td>${escapeHtml(displayCodeLabel(row.calculation_status || ""))}</td>
          <td class="analysis-pattern-cell" title="${escapeHtml(row.clause_extract || "")}">
            <strong>${escapeHtml(clause || DISPLAY_EMPTY)}</strong>
          </td>
          <td class="analysis-code-cell">${escapeHtml(row.source_page ? `p.${row.source_page}` : DISPLAY_EMPTY)}</td>
          <td>${escapeHtml(displayDate(row.governed_at, "Derived"))}</td>
          <td><button class="analysis-open-btn" data-analysis-open-ae="${escapeHtml(row.ae_id)}">Open</button></td>
        </tr>
      `;
    }).join("")}
        </tbody>
      </table>
    </div>
  `;
  wireAnalysisOpenButtons(host, "uplifts");
}

function renderCouncilReferenceRows(host, rows) {
  host.innerHTML = `
    <div class="analysis-table-scroll">
      <table class="analysis-data-table analysis-council-table">
        <thead>
          <tr>
            <th>Council</th>
            <th>Cohorts</th>
            <th>Electoral</th>
            <th>Spatial</th>
            <th>Performance Context</th>
            <th>Governance</th>
            <th>Socioeconomic</th>
            <th>Codes</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => {
      const codes = [
        row.lga_code ? `LGA ${row.lga_code}` : "",
        row.abs_lga_code_2025 ? `ABS ${row.abs_lga_code_2025}` : row.abs_lga_code ? `ABS ${row.abs_lga_code}` : "",
      ].filter(Boolean).join(" / ");
      const officeText = [
        row.office_township || "",
        row.office_address || "",
      ].filter(Boolean).join(" - ");
      const regionText = [
        row.vif_metropolitan_region ? `Metro: ${row.vif_metropolitan_region}` : "",
        row.vif_regional_partnership ? `RP: ${row.vif_regional_partnership}` : "",
      ].filter(Boolean).join(" / ");
      const wardCount = row.vec_ward_count === 0 ? "unsubdivided" : `${formatCount(row.vec_ward_count, "0")} wards`;
      const governanceText = row.governance_item_count
        ? `${formatCount(row.governance_yes_count, "0")}/${formatCount(row.governance_item_count, "0")} checklist yes`
        : DISPLAY_EMPTY;
      const seifaText = [
        row.vgccc_seifa_dis_score ? `DIS ${displayNumber(row.vgccc_seifa_dis_score, DISPLAY_EMPTY, { maximumFractionDigits: 1 })}` : "",
        row.vgccc_unemployment_rate_june_2024 !== null && row.vgccc_unemployment_rate_june_2024 !== undefined
          ? `Unemp ${displayFractionPercent(row.vgccc_unemployment_rate_june_2024, DISPLAY_EMPTY)}`
          : "",
      ].filter(Boolean).join(" / ");
      return `
        <tr class="analysis-rule-row">
          <td class="analysis-entity-cell">
            <strong>${escapeHtml(row.short_name || "")}</strong>
            <span>${escapeHtml(row.long_name || "")}</span>
          </td>
          <td class="analysis-pattern-cell">
            <strong>${escapeHtml(row.council_category || DISPLAY_EMPTY)}</strong>
            <span>${escapeHtml(regionText || displayCodeLabel(row.council_type || "unknown"))}</span>
          </td>
          <td>
            <strong>${escapeHtml(row.vec_councillor_count ? `${formatCount(row.vec_councillor_count, "0")} councillors` : DISPLAY_EMPTY)}</strong>
            <span>${escapeHtml(row.vec_electoral_structure ? `${displayCodeLabel(row.vec_electoral_structure)} / ${wardCount}` : DISPLAY_EMPTY)}</span>
          </td>
          <td>
            <strong>${escapeHtml(row.abs_area_albers_sqkm ? `${displayNumber(row.abs_area_albers_sqkm, DISPLAY_EMPTY, { maximumFractionDigits: 1 })} sq km` : DISPLAY_EMPTY)}</strong>
            <span>${escapeHtml(officeText || `office ${row.office_geocoded || "missing"}`)}</span>
          </td>
          <td>
            <strong>${escapeHtml(row.lgprf_group || DISPLAY_EMPTY)}</strong>
            <span>${escapeHtml(row.lgprf_relative_socioeconomic_disadvantage ? `SEIFA ${displayNumber(row.lgprf_relative_socioeconomic_disadvantage, DISPLAY_EMPTY, { maximumFractionDigits: 1 })}` : DISPLAY_EMPTY)}</span>
          </td>
          <td>
            <strong>${escapeHtml(governanceText)}</strong>
            <span>${escapeHtml(row.governance_latest_year || DISPLAY_EMPTY)}</span>
          </td>
          <td>
            <strong>${escapeHtml(seifaText || DISPLAY_EMPTY)}</strong>
            <span>${escapeHtml(row.vgccc_region ? `${row.vgccc_region} / adult pop ${formatCount(row.vgccc_adult_population_2024, "0")}` : DISPLAY_EMPTY)}</span>
          </td>
          <td class="analysis-code-cell">${escapeHtml(codes || DISPLAY_EMPTY)}</td>
        </tr>
      `;
    }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function renderAnalysisWorkspace({ force = false } = {}) {
  const status = document.getElementById("analysis-status");
  if (!document.getElementById("view-analysis")) return;
  const dataSetKind = DATA_SET_CONFIG[state.currentDataSet] ? state.currentDataSet : "uplift_rules";
  const config = DATA_SET_CONFIG[dataSetKind] || DATA_SET_CONFIG.uplift_rules;
  const cachedData = force ? null : analysisDataForKind(dataSetKind);
  if (cachedData) state.analysisData = cachedData;
  updateDataSetNav();
  if (dataSetKind === "charts") {
    await ensureAnalysisCouncilContext();
    if (state.currentDataSet !== dataSetKind) return;
  }
  renderAnalysisBannerHeader();
  setText("analysis-title", `Think > ${config.title}`);
  setText("analysis-description", config.description);
  setText("analysis-run-id", config.runId);
  setText("analysis-run-meta", config.runMeta);
  setText("analysis-primary-label", config.primaryLabel);
  setText("analysis-primary-note", config.primaryNote);
  setText("analysis-agreement-label", config.agreementLabel || "Agreements");
  setText("analysis-agreement-note", config.agreementNote);
  setText("analysis-secondary-label", config.secondaryLabel);
  setText("analysis-secondary-note", config.secondaryNote);
  setText("analysis-date-label", config.dateLabel || "Effective range");
  setText("analysis-date-note", config.dateNote || "earliest to latest rule");
  setText("analysis-pattern-heading", config.patternHeading);
  setText("analysis-table-title", config.tableTitle);
  setText("analysis-table-description", config.tableDescription);
  const hideTableControls = Boolean(config.hideTableControls);
  const hideSidePanel = Boolean(config.hideSidePanel);
  const workbench = document.querySelector("#view-analysis .analysis-workbench");
  if (workbench) workbench.classList.toggle("analysis-workbench-asset", hideSidePanel);
  const sidePanel = document.querySelector("#view-analysis .analysis-side-panel");
  if (sidePanel) sidePanel.hidden = hideSidePanel;
  const controlCard = document.getElementById("analysis-control-card");
  if (controlCard) controlCard.hidden = hideTableControls || hideSidePanel;
  const tableTools = document.querySelector(".analysis-tools");
  if (tableTools) tableTools.hidden = hideTableControls;
  const filter = document.getElementById("analysis-filter");
  if (filter) {
    filter.placeholder = config.filterPlaceholder;
    filter.value = state.analysisFilter;
  }
  const sort = document.getElementById("analysis-sort");
  if (sort) {
    sort.innerHTML = config.sortOptions
      .map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`)
      .join("");
    if (!config.sortOptions.some(([value]) => value === state.analysisSort)) {
      state.analysisSort = config.sortOptions[0]?.[0] || "effective_date";
    }
    sort.value = state.analysisSort;
  }
  setText("analysis-focus-rate-cap", config.firstFilterLabel);
  setText("analysis-focus-floor", config.secondFilterLabel);
  if (!analysisDataForKind(dataSetKind) || force) {
    if (status) status.textContent = `Loading ${config.label.toLowerCase()} data set...`;
    try {
      const loadedData = await api(config.endpoint);
      if (dataSetKind === "councils" && !Array.isArray(loadedData.rows)) {
        loadedData.rows = loadedData.councils || [];
      }
      setAnalysisDataForKind(dataSetKind, loadedData);
      if (state.currentDataSet !== dataSetKind) return;
      state.analysisData = analysisDataForKind(dataSetKind) || loadedData;
    } catch (error) {
      if (status) status.textContent = `Data set failed: ${apiErrorMessage(error)}`;
      return;
    }
  }
  if (state.currentDataSet !== dataSetKind) return;
  renderAnalysisBannerHeader();
  if (dataSetKind === "charts") {
    try {
      await ensureReportExportCatalog();
    } catch {
      // The report export panel renders the captured error without blocking chart review.
    }
  }
  const summary = state.analysisData?.summary || {};
  if (dataSetKind === "councils") {
    const rows = state.analysisData?.rows || [];
    const activeRows = rows.filter((row) => row.status === "active").length;
    const exceptionRows = rows.filter((row) => row.status && row.status !== "active").length;
    setText("analysis-rule-count", formatCount(summary.councils ?? rows.length, "0"));
    setText("analysis-agreement-count", formatCount(activeRows, "0"));
    setText("analysis-rate-cap-count", formatCount(exceptionRows, "0"));
    const categoryCount = Object.keys(summary.categories || {}).length
      || new Set(rows.map((row) => row.council_category).filter(Boolean)).size;
    setText("analysis-date-range", formatCount(categoryCount, "0"));
  } else if (dataSetKind === "charts") {
    const context = chartPayDistributionContext();
    const { rows, mode, basisLabel, rangeLabel, bandLabel, levelSpan } = context;
    const reportingCohorts = buildReportingCohorts(rows);
    const selectedCohort = selectedReportingCohort(reportingCohorts);
    const selectedStats = payDistributionStats(selectedCohort?.rows || []);
    setText("analysis-table-title", `${bandLabel} ${levelSpan.label} Distribution`);
    setText(
      "analysis-table-description",
      `${basisLabel} weekly midpoint rates for ${rangeLabel}, using the selected band's minimum and maximum levels.`
    );
    setText("analysis-primary-note", `${bandLabel} ${levelSpan.label.toLowerCase()}`);
    setText("analysis-date-label", mode === CHART_BASE_FOUR_QUARTER_AVERAGE
      ? "Quarter range"
      : mode === CHART_BASE_DATE_SMOOTHED
        ? "Trajectory date"
        : "Quarter");
    setText("analysis-date-note", mode === CHART_BASE_FOUR_QUARTER_AVERAGE
      ? "4Q average base"
      : mode === CHART_BASE_DATE_SMOOTHED
        ? "date-smoothed estimate"
        : "selected snapshot");
    setText("analysis-rule-count", formatCount(rows.length, "0"));
    setText("analysis-agreement-count", formatCount(Math.max(0, reportingCohorts.length - 1), "0"));
    setText("analysis-rate-cap-count", formatCount(selectedStats?.count || 0, "0"));
    setText("analysis-date-range", rangeLabel);
    if (status) {
      status.textContent = `Showing ${bandLabel} ${levelSpan.label.toLowerCase()} ${basisLabel.toLowerCase()} comparison for ${selectedCohort?.label || "selected cohort"}: selected council plus ${formatCount(selectedStats?.count || 0, "0")} values averaged.`;
    }
  } else if (dataSetKind === "pay_tables") {
    setText("analysis-rule-count", formatCount(summary.rows, "0"));
    setText("analysis-agreement-count", formatCount(summary.agreements_with_governed_pay_tables, "0"));
    setText("analysis-rate-cap-count", formatCount(summary.tables, "0"));
  } else if (dataSetKind === "end_of_band_dollars") {
    setText("analysis-rule-count", formatCount(summary.rows, "0"));
    setText("analysis-agreement-count", formatCount(summary.agreements_with_end_of_band_cash, "0"));
    setText("analysis-rate-cap-count", formatCount(summary.bands, "0"));
  } else {
    setText("analysis-rule-count", formatCount(summary.rules, "0"));
    setText("analysis-agreement-count", formatCount(summary.agreements_with_uplift_rules, "0"));
    setText("analysis-rate-cap-count", formatCount(summary.rate_cap_rules, "0"));
  }
  if (dataSetKind !== "councils" && dataSetKind !== "charts") {
    setText("analysis-date-range", displayDateRange(summary.earliest_effective_from, summary.latest_effective_from, "No dates"));
  }
  renderPayDistributionPanel();
  renderReportExportPanel();
  renderPayCandidateQualityPanel();
  renderAnalysisPatterns();
  renderAnalysisRows();
}

function renderCouncilSelect() {
  const select = document.getElementById("council-select");
  if (!select) return;
  const sorted = [...state.councils].sort((a, b) => {
    const labelA = (a.canonical_lga_short_name || a.source_name || a.ae_id).toLowerCase();
    const labelB = (b.canonical_lga_short_name || b.source_name || b.ae_id).toLowerCase();
    return labelA.localeCompare(labelB);
  });
  const selectedAeId = state.currentCouncil?.agreement_id || select.value;
  select.innerHTML = sorted.map((item) => {
    const short = item.canonical_lga_short_name || "";
    const label = short ? `${short} - ${item.source_name}` : item.source_name;
    const selectedAttr = item.ae_id === selectedAeId ? " selected" : "";
    return `<option value="${escapeHtml(item.ae_id)}"${selectedAttr}>${escapeHtml(label)}</option>`;
  }).join("");
}

// Scan all draft pay tables and return the min/max ISO effective_from values, or null/null if none present.
function computeDraftCommencingRange() {
  const tables = state?.payDraft?.tables || [];
  const dates = tables
    .map((t) => (t?.effective_from || "").trim())
    .filter((d) => isIso(d));
  if (dates.length === 0) return { earliest: null, latest: null };
  dates.sort();
  return { earliest: dates[0], latest: dates[dates.length - 1] };
}

function renderAlterations(alterations) {
  if (!Array.isArray(alterations) || alterations.length === 0) return DISPLAY_EMPTY;
  const items = alterations.map((a) => {
    const page = a.page != null ? displayPages(a.page) : "";
    const heading = a.heading ? escapeHtml(a.heading) : "Untitled";
    const affects = a.affects ? ` - <em>${escapeHtml(a.affects)}</em>` : "";
    const summary = a.summary ? `: ${escapeHtml(a.summary)}` : "";
    return `<li><strong>${heading}</strong>${page ? ` <span class="muted">(${page})</span>` : ""}${affects}${summary}</li>`;
  }).join("");
  return `<ul class="overview-alterations">${items}</ul>`;
}

function renderOverview() {
  const overview = state.currentCouncil?.overview;
  const fwc = state.currentCouncil?.fwc || {};
  const el = document.getElementById("overview-content");
  if (!el) return;
  if (!overview?.generated_at) {
    el.innerHTML = '<span class="muted">Not generated yet.</span>';
    return;
  }
  // Prefer live-computed range from draft tables; fall back to LLM estimate; then ?.
  const draft = computeDraftCommencingRange();
  const earliestLive = draft.earliest;
  const latestLive = draft.latest;
  const earliestLlm = overview.estimated_earliest_commencing || null;
  const latestLlm = overview.estimated_latest_commencing || null;
  const earliest = earliestLive || earliestLlm;
  const latest = latestLive || latestLlm;
  const earliestSource = earliestLive ? "draft tables" : (earliestLlm ? "LLM estimate" : null);
  const latestSource = latestLive ? "draft tables" : (latestLlm ? "LLM estimate" : null);
  const fmt = (v, src) => v ? `${escapeHtml(displayDate(v))} <span class="muted" style="font-size:0.85em;">(${src})</span>` : DISPLAY_EMPTY;
  const fwcApproval = fwc.operative_date || null;
  const fwcExpiry = fwc.expiry_date || null;
  const rawNotes = String(overview.document_structure_notes || "");
  const generationWarning = overview.generation_warning || (rawNotes.startsWith("ERROR:") ? rawNotes : "");
  const safeNotes = rawNotes.startsWith("ERROR:") ? "" : rawNotes;
  const warningHtml = generationWarning
    ? '<div class="overview-warning"><strong>Generation warning:</strong> AI narrative unavailable; deterministic page scan used.</div>'
    : "";
  // If draft earliest is BEFORE FWC approval, flag as backdated ? useful signal.
  let backdatedNote = "";
  if (earliest && fwcApproval && earliest < fwcApproval) {
    backdatedNote = ` <span class="muted" style="font-size:0.85em;">(backdated before FWC approval)</span>`;
  }
  el.innerHTML = `
    <div class="stack-sm">
      <div><strong>Pages:</strong> ${htmlDisplay(overview.page_count)}</div>
      <div><strong>Pay pages:</strong> ${escapeHtml(displayPages(overview.likely_pay_table_pages || []))}</div>
      <div><strong>Uplift pages:</strong> ${escapeHtml(displayPages(overview.likely_uplift_pages || []))}</div>
      <div><strong>Earliest commencing:</strong> ${fmt(earliest, earliestSource)}${backdatedNote}</div>
      <div><strong>Latest commencing:</strong> ${fmt(latest, latestSource)}</div>
      <div><strong>FWC approval date:</strong> ${escapeHtml(displayDate(fwcApproval))}</div>
      <div><strong>FWC nominal expiry:</strong> ${escapeHtml(displayDate(fwcExpiry))}</div>
      ${warningHtml}
      <div><strong>Notes:</strong> ${safeNotes ? escapeHtml(safeNotes) : DISPLAY_EMPTY}</div>
      <div><strong>Red flags:</strong> ${(overview.red_flags || []).join("; ") || DISPLAY_EMPTY}</div>
      <div><strong>Band/level alterations:</strong> ${renderAlterations(overview.band_level_alterations || [])}</div>
    </div>
  `;
}

function renderOverviewPane() {
  const pane = document.getElementById("section-pane");
  if (!state.currentCouncil) {
    clearWorkspaceModuleHeader();
    pane.innerHTML = '<div class="muted">Select a council first.</div>';
    return;
  }
  const overviewAccepted = sectionFinalActionAccepted("overview");
  const overviewActionsHtml = `
    <button
      id="overview-generate-btn"
      type="button"
      class="primary"
      data-confirm-mode-action="1"
      title="${escapeHtml(overviewAccepted ? "Generate or refresh the accepted overview without reopening downstream sections." : "Generate or refresh the agreement overview.")}"
    >Generate agreement overview</button>
  `;
  const finalActionHtml = renderSectionFinalAction({
    eyebrow: "Overview acceptance",
    title: "Document map ready",
    detail: "Generate the overview and mark this section complete.",
    buttonId: "overview-qa-btn",
  });
  setWorkspaceModuleHeader("overview");
  pane.innerHTML = `
    ${renderSectionActionBar(overviewActionsHtml, finalActionHtml)}
    <div class="grid-two">
      <div class="card">
        <h3>Document Overview</h3>
        <div id="overview-content">Not generated yet.</div>
      </div>
      <div class="card">
        <h3>FWC Governance</h3>
        <div id="fwc-content" class="muted">-</div>
      </div>
    </div>
  `;
  document.getElementById("overview-generate-btn")?.addEventListener("click", generateOverview);
  renderOverview();
  renderFwc();
}

function renderFwc() {
  const fwc = state.currentCouncil?.fwc || {};
  const el = document.getElementById("fwc-content");
  if (!el) return;
  const fields = [
    ["lga_code", "LGA Code"],
    ["matter_number", "Matter Number"],
    ["print_id", "Print ID"],
    ["operative_date", "Operative Date"],
    ["expiry_date", "Expiry Date"],
    ["version", "Version"],
    ["superseded_by_ae_id", "Superseded By"],
  ];
  const rows = fields
    .filter(([k]) => { const v = fwc[k]; return v !== null && v !== undefined && v !== ""; })
    .map(([k, label]) => {
      const v = fwc[k];
      const display = k.includes("date") ? displayDate(v) : displayValue(v);
      return `<div><strong>${escapeHtml(label)}:</strong> ${escapeHtml(display)}</div>`;
    });
  el.innerHTML = rows.length > 0
    ? `<div class="stack-sm">${rows.join("")}</div>`
    : `<span class="muted">No FWC metadata.</span>`;
}

function renderSectionsList() {
  const tabbar = document.getElementById("sections-tabbar");
  if (!tabbar) return;
  const workspaceActive = document.getElementById("view-workspace")?.classList.contains("active") || false;
  tabbar.innerHTML = SECTION_GROUPS.map((group) => {
    const buttons = group.sections.map((section) => {
      const label = SECTION_LABELS[section] || section;
      const status = sectionDisplayStatus(section);
      const active = workspaceActive && state.currentSection === section;
      const pendingClass = state.currentCouncil ? "" : " section-tab-awaiting";
      const blocker = sectionQaGateBlocker(section);
      const lockedClass = blocker ? " section-tab-locked" : "";
      const blockedBy = blocker ? SECTION_LABELS[blocker] || blocker : "";
      const title = blocker
        ? `${label}: locked until ${blockedBy} is accepted`
        : `${label}: ${sectionFinalActionAccepted(section) ? "accepted" : "edit mode"}`;
      return `
        <button
          role="tab"
          aria-selected="${active}"
          class="section-tab section-tab-${escapeHtml(status)}${pendingClass}${lockedClass}${active ? " active" : ""}"
          data-section="${section}"
          data-status="${escapeHtml(status)}"
          title="${escapeHtml(title)}"
          ${blocker ? 'disabled aria-disabled="true"' : ""}
        >
          <span class="section-tab-label">${label}</span>
          <span class="section-tab-status">${statusPill(status)}</span>
        </button>
      `;
    }).join("");
    return `
      <div class="section-tab-group">
        <div class="section-tab-group-label">${escapeHtml(group.label)}</div>
        ${buttons}
      </div>
    `;
  }).join("");
  tabbar.querySelectorAll(".section-tab").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.disabled) return;
      openWorkspaceSection(button.dataset.section);
    });
  });
}

async function openWorkspaceSection(section) {
  const targetSection = openableWorkspaceSection(section, { notify: true });
  if (!state.currentCouncil) {
    await openDefaultWorkspaceAgreement(targetSection);
    return;
  }
  state.currentSection = targetSection;
  switchView("workspace");
  renderSectionPane();
}

async function loadCouncilContext(aeId, section = state.currentSection || "overview") {
  const canonical = await api(`/api/councils/${aeId}`);
  state.currentCouncil = canonical;
  state.wikiComparatorCouncilKey = "";
  state.currentSection = openableWorkspaceSection(section);
  syncPayDraftFromCanonical();
  renderCouncilSelect();
  renderSectionsList();
  renderAgreementNavigator();
  return canonical;
}

async function ensureDefaultAgreementContextForNavigator() {
  if (state.currentCouncil || !state.councils.length) return;
  const route = parseWorkbenchRoute();
  if (route?.view === "workspace" && route.aeId) return;
  const firstAgreement = agreementNavigationItems()[0];
  if (!firstAgreement?.ae_id) return;
  try {
    await loadCouncilContext(firstAgreement.ae_id, state.currentSection || "overview");
  } catch {
    // The navigator remains usable even if the first default context cannot be loaded.
  }
}

async function syncAgreementContextFromAuditReport(report) {
  const aeId = report?.latest?.ae_id;
  if (!aeId || String(state.currentCouncil?.agreement_id || "").toLowerCase() === String(aeId).toLowerCase()) return;
  try {
    await loadCouncilContext(aeId, state.currentSection || "overview");
  } catch {
    renderAgreementNavigator();
  }
}

async function ensureAnalysisCouncilContext() {
  if (state.currentCouncil) return state.currentCouncil;
  const reviewRows = reviewBoardRows();
  const firstAvailable = reviewRows.find((item) => item.section_statuses?.pay_tables !== "done") || reviewRows[0];
  if (!firstAvailable) return null;
  return loadCouncilContext(firstAvailable.ae_id, state.currentSection || "overview");
}

async function selectAnalysisCouncil(aeId) {
  await loadCouncilContext(aeId, state.currentSection || "overview");
  if (!state.lgaBoundaryGeojson) {
    await ensureLgaBoundaryData();
  }
  await renderAnalysisWorkspace();
}

async function refreshContextAwareViewAfterAgreementChange(view) {
  if (view === "analysis") {
    await renderAnalysisWorkspace();
    return;
  }
  if (view === "audit") {
    const context = currentWorkspaceContext();
    const councilName = context.councilName === "Unknown council" ? defaultAuditCouncil() : context.councilName;
    await renderCouncilAudit(councilName);
    return;
  }
  if (view === "wiki") {
    renderWikiEntitlementDetail();
    renderAgreementNavigator();
  }
}

async function navigateAgreementContext(direction) {
  const { previous, next } = agreementNavigatorState();
  const target = direction === "previous" ? previous : next;
  if (!target?.ae_id) return;
  const currentView = document.body.dataset.view || "incoming";
  const section = state.currentSection || "overview";
  if (currentView === "workspace") {
    await openCouncil(target.ae_id, section);
    return;
  }
  await loadCouncilContext(target.ae_id, section);
  renderAgreementNavigator();
  updateHeaderForView(currentView);
  await refreshContextAwareViewAfterAgreementChange(currentView);
}

async function openCouncil(aeId, section = "overview") {
  const canonical = await api(`/api/councils/${aeId}`);
  const shouldRefreshMap = !state.lgaBoundaryGeojson;
  state.currentCouncil = canonical;
  state.wikiComparatorCouncilKey = "";
  state.currentSection = openableWorkspaceSection(section, { notify: true });
  syncPayDraftFromCanonical();
  renderCouncilSelect();
  renderAgreementNavigator();
  const title = document.getElementById("council-title");
  if (title) title.textContent = canonical.source_name;
  renderOverview();
  renderFwc();
  renderSectionsList();
  renderSectionPane();
  switchView("workspace");
  if (shouldRefreshMap) {
    ensureLgaBoundaryData().then((geojson) => {
      if (geojson && state.currentCouncil?.agreement_id === canonical.agreement_id && document.body.dataset.view === "workspace") {
        renderSectionPane();
      }
    });
  }
  await loadPdf(canonical.agreement_id);
}

async function loadPdf(aeId) {
  await state.pdfViewer.load(`/api/councils/${aeId}/pdf`);
}

async function generateOverview() {
  const button = document.getElementById("overview-generate-btn") || document.getElementById("overview-btn");
  const originalText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "Generating...";
  }
  try {
    const canonical = await api(`/api/councils/${state.currentCouncil.agreement_id}/overview/generate`, { method: "POST", body: "{}" });
    state.currentCouncil = canonical;
    if (state.currentSection === "overview") {
      renderOverviewPane();
    } else {
      renderOverview();
      renderFwc();
    }
    renderSectionsList();
    const warning = canonical.overview?.generation_warning;
    toast(warning ? "Overview generated from deterministic page scan; AI notes unavailable" : "Overview generated", "success");
  } catch (error) {
    toast(`Overview failed: ${error.message}`, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText || "Generate agreement overview";
    }
  }
}

function overviewPreparationState(aeId = state.currentCouncil?.agreement_id) {
  if (!aeId) return null;
  if (!state.overviewPreparation[aeId]) {
    state.overviewPreparation[aeId] = {
      running: false,
      completed: false,
      startedAt: null,
      finishedAt: null,
      jobs: overviewPreparationDefaultJobs(),
    };
  }
  normaliseOverviewPreparationJobs(state.overviewPreparation[aeId]);
  return state.overviewPreparation[aeId];
}

function overviewPreparationDefaultJobs() {
  return {
    overview: { status: "queued", label: "Document map", detail: "Waiting to start" },
    pay: { status: "queued", label: "Pay-table extraction", detail: "Waiting to start" },
    uplift: { status: "queued", label: "Uplift-rule extraction", detail: "Waiting to start" },
    scenarios: { status: "queued", label: "Scenario checks", detail: "Waiting for uplift-rule work" },
  };
}

function normaliseOverviewPreparationJobs(prep) {
  if (!prep) return;
  const defaults = overviewPreparationDefaultJobs();
  prep.jobs = prep.jobs && typeof prep.jobs === "object" ? prep.jobs : {};
  Object.entries(defaults).forEach(([key, fallback]) => {
    prep.jobs[key] = {
      ...fallback,
      ...(prep.jobs[key] || {}),
    };
  });
}

function renderOverviewPreparation() {
  const prep = overviewPreparationState();
  const content = document.getElementById("overview-prep-content");
  const reply = document.getElementById("overview-prep-reply");
  const stateEl = document.getElementById("overview-prep-state");
  const startBtn = document.getElementById("overview-prep-start");
  if (!prep || !content) return;
  const jobs = Object.values(prep.jobs || {});
  const failed = jobs.filter((job) => job.status === "failed").length;
  const running = jobs.some((job) => job.status === "running");
  const done = jobs.every((job) => ["done", "skipped", "failed"].includes(job.status));
  const statusLabel = running ? "Running" : failed ? "Needs review" : done ? "Ready" : "Ready";
  if (stateEl) {
    stateEl.textContent = statusLabel;
    stateEl.className = `mb-status-chip ${failed ? "mb-status-chip-warning" : running ? "mb-status-chip-neutral" : "mb-status-chip-success"}`;
  }
  if (startBtn) {
    startBtn.disabled = running;
    startBtn.textContent = running ? "Running" : done ? "Run again" : "Run";
  }
  if (reply) {
    reply.textContent = overviewPreparationReply(prep);
  }
  content.innerHTML = jobs.map((job) => `
    <div class="overview-prep-row workbench-card-scaffold overview-prep-${escapeHtml(job.status)}">
      <span class="overview-prep-dot" aria-hidden="true"></span>
      <div>
        <strong>${escapeHtml(job.label)}</strong>
        <p>${escapeHtml(job.detail || "")}</p>
      </div>
    </div>
  `).join("");
}

function overviewPreparationReply(prep) {
  const jobs = Object.values(prep?.jobs || {});
  const running = jobs.find((job) => job.status === "running");
  if (running) {
    return `I am working on ${running.label.toLowerCase()}: ${running.detail || "checking the agreement now"}.`;
  }
  const failed = jobs.filter((job) => job.status === "failed");
  if (failed.length) {
    const names = failed.map((job) => job.label.toLowerCase()).join(", ");
    const lastDetail = failed[failed.length - 1]?.detail || "I could not finish that step.";
    return `I could not get through ${names}. ${lastDetail}`;
  }
  const done = jobs.filter((job) => job.status === "done").length;
  const skipped = jobs.filter((job) => job.status === "skipped").length;
  if (done || skipped) {
    return `I have finished the automatic checks I could run: ${done} done, ${skipped} skipped.`;
  }
  return "I am ready to map the document, find useful pages, suggest uplift rules and prepare scenario checks.";
}

function automationWorkspaceSectionForJob(jobKey) {
  return {
    overview: "overview",
    pay: "pay_tables",
    uplift: "uplift_rules",
    uplift_rules: "uplift_rules",
    pay_tables: "pay_tables",
    scenarios: "scenarios",
    end_of_band_dollars: "end_of_band_dollars",
    uplifts: "uplifts",
  }[jobKey] || "";
}

function followAutomationWorkspaceSection(aeId, jobKey) {
  const section = automationWorkspaceSectionForJob(jobKey);
  if (!section) return;
  if (document.body?.dataset?.view !== "workspace") return;
  if (state.currentCouncil?.agreement_id !== aeId) return;
  if (state.currentSection === section) return;
  state.currentSection = SECTION_LABELS[section] ? section : "overview";
  switchView("workspace");
  renderSectionPane();
}

function renderPreparationSurfaces(aeId) {
  if (state.currentCouncil?.agreement_id === aeId && document.body?.dataset?.view === "workspace") {
    setWorkspaceModuleHeader(state.currentSection);
  }
  if (state.currentCouncil?.agreement_id === aeId && state.currentSection === "overview") {
    renderOverviewPreparation();
  }
  if (document.body?.dataset?.view === "matrix") {
    renderMatrix();
  }
}

function setOverviewPreparationJob(aeId, jobKey, status, detail) {
  const prep = overviewPreparationState(aeId);
  if (!prep?.jobs?.[jobKey]) return;
  prep.jobs[jobKey].status = status;
  prep.jobs[jobKey].detail = detail;
  if (status === "running") followAutomationWorkspaceSection(aeId, jobKey);
  renderPreparationSurfaces(aeId);
}

function resetOverviewPreparation(prep) {
  if (!prep) return;
  normaliseOverviewPreparationJobs(prep);
  prep.completed = false;
  prep.finishedAt = null;
  prep.jobs.overview.status = "queued";
  prep.jobs.overview.detail = "Waiting to start";
  prep.jobs.pay.status = "queued";
  prep.jobs.pay.detail = "Waiting to start";
  prep.jobs.uplift.status = "queued";
  prep.jobs.uplift.detail = "Waiting to start";
  prep.jobs.scenarios.status = "queued";
  prep.jobs.scenarios.detail = "Waiting for uplift-rule work";
}

function overviewPreparationMinimumMs(jobKey) {
  return {
    overview: 2200,
    pay: 3200,
    uplift: 2600,
    scenarios: 2600,
  }[jobKey] || 2200;
}

async function holdOverviewPreparationJobForImpact(jobKey, startedAt) {
  const remaining = overviewPreparationMinimumMs(jobKey) - (Date.now() - startedAt);
  if (remaining > 0) await delay(remaining);
}

function contiguousPageGroups(pages, maxPagesPerGroup = 20) {
  const clean = [...new Set((pages || []).map((page) => Number(page)).filter((page) => Number.isInteger(page) && page > 0))]
    .sort((a, b) => a - b);
  const groups = [];
  for (const page of clean) {
    const last = groups[groups.length - 1];
    if (last && page === last[last.length - 1] + 1 && last.length < maxPagesPerGroup) {
      last.push(page);
    } else {
      groups.push([page]);
    }
  }
  return groups;
}

function renderPayTablesIfActive(aeId) {
  if (state.currentCouncil?.agreement_id === aeId && state.currentSection === "pay_tables") {
    renderSectionPane();
  }
}

async function ensureOverviewPreparationCouncil(aeId) {
  if (!aeId) return null;
  if (state.currentCouncil?.agreement_id === aeId) return state.currentCouncil;
  return loadCouncilContext(aeId, "overview");
}

async function runOverviewDocumentMapPreparation(aeId) {
  const startedAt = Date.now();
  setOverviewPreparationJob(aeId, "overview", "running", "Checking the document map and FWC metadata");
  await ensureOverviewPreparationCouncil(aeId);
  const council = state.currentCouncil;
  const overview = council?.overview || {};
  const section = council?.sections?.overview || {};
  if (overview.generated_at || section.status === "done") {
    const pages = overview.page_count || council?.page_count || "";
    await holdOverviewPreparationJobForImpact("overview", startedAt);
    setOverviewPreparationJob(aeId, "overview", "skipped", pages ? `Document map already available across ${pages} pages` : "Document map already available");
    return;
  }
  const canonical = await api(`/api/councils/${encodeURIComponent(aeId)}/overview/generate`, { method: "POST", body: "{}" });
  if (state.currentCouncil?.agreement_id === aeId) {
    state.currentCouncil = canonical;
    syncPayDraftFromCanonical();
    renderOverview();
    renderFwc();
    renderSectionsList();
  }
  const pages = canonical?.overview?.page_count || canonical?.page_count || "";
  await holdOverviewPreparationJobForImpact("overview", startedAt);
  setOverviewPreparationJob(aeId, "overview", "done", pages ? `Generated document map across ${pages} pages` : "Generated document map");
}

async function runOverviewPayExtractionPreview(aeId) {
  const startedAt = Date.now();
  setOverviewPreparationJob(aeId, "pay", "running", "Finding candidate pay-table pages");
  const candidates = await api(`/api/councils/${encodeURIComponent(aeId)}/pay-tables/find-candidates`, {
    method: "POST",
    body: "{}",
  });
  if (state.currentCouncil?.agreement_id !== aeId) return;
  const overviewPayPages = overviewEvidencePages("pay");
  const overviewUpliftPages = overviewEvidencePages("uplift");
  state.payDraft.payTablePages = normalisePageList([
    ...overviewPayPages,
    ...(candidates.pay_table_pages || []),
  ]);
  state.payDraft.upliftRulePages = overviewUpliftPages.length
    ? overviewUpliftPages
    : normalisePageList(candidates.uplift_rule_pages || []);
  state.payDraft.candidatePages = normalisePageList(candidates.candidate_pages || [
    ...state.payDraft.payTablePages,
    ...state.payDraft.upliftRulePages,
  ]);
  renderPayTablesIfActive(aeId);
  const pagePlan = payExtractionPagePlan(
    overviewPayPages,
    state.payDraft.payTablePages,
    state.payDraft.candidatePages,
    currentAgreementPageCount(),
  );
  const plannedGroups = [...pagePlan.primary, ...pagePlan.fallback];
  if (!plannedGroups.length) {
    await holdOverviewPreparationJobForImpact("pay", startedAt);
    setOverviewPreparationJob(aeId, "pay", "skipped", "No pay-table candidate pages found");
    renderPayTablesIfActive(aeId);
    return;
  }
  const extractions = [];
  const triedPages = new Set();
  const extractPayPageRange = async (start, end) => {
    const result = await api(`/api/councils/${encodeURIComponent(aeId)}/pay-tables/extract-range`, {
      method: "POST",
      body: JSON.stringify({ start_page: start, end_page: end }),
    });
    return { ...result, range: { start, end } };
  };
  const extractGroup = async (group) => {
    const start = group[0];
    const end = group[group.length - 1];
    group.forEach((page) => triedPages.add(page));
    setOverviewPreparationJob(aeId, "pay", "running", `Extracting preview from ${displayPages([start, end])}`);
    const result = await extractPayPageRange(start, end);
    if (group.length > 1 && !(result.tables || []).length) {
      for (const page of group) {
        triedPages.add(page);
        setOverviewPreparationJob(aeId, "pay", "running", `Extracting preview from page ${page}`);
        extractions.push(await extractPayPageRange(page, page));
      }
    } else {
      extractions.push(result);
    }
  };
  for (const group of pagePlan.primary) {
    await extractGroup(group);
    if (extractions.some((result) => (result.tables || []).length)) break;
  }
  let tables = extractions.flatMap((result) => result.tables || []);
  if (!tables.length) {
    for (const group of pagePlan.fallback) {
      setOverviewPreparationJob(aeId, "pay", "running", `Trying fallback pay range ${displayPages([group[0], group[group.length - 1]])}`);
      await extractGroup(group);
      tables = extractions.flatMap((item) => item.tables || []);
      if (tables.length) break;
    }
  }
  if (state.currentCouncil?.agreement_id !== aeId) return;
  state.payDraft.rangeExtraction = {
    tables,
    raw: extractions.map((result) => result.raw || "").filter(Boolean).join("\n\n---\n\n"),
    range: {
      start: Math.min(...triedPages),
      end: Math.max(...triedPages),
      groups: extractions.map((result) => result.range),
    },
    accepted: new Set(),
    previewOnly: true,
  };
  await holdOverviewPreparationJobForImpact("pay", startedAt);
  setOverviewPreparationJob(aeId, "pay", "done", `Preview extracted ${tables.length} table${tables.length === 1 ? "" : "s"} from ${triedPages.size} candidate page${triedPages.size === 1 ? "" : "s"}`);
  renderPayTablesIfActive(aeId);
}

async function ensureOverviewUpliftSuggestion(aeId) {
  const startedAt = Date.now();
  const council = state.currentCouncil;
  const section = council?.sections?.uplift_rules || {};
  const data = section.data && typeof section.data === "object" ? section.data : {};
  if (data.accepted?.document?.rules?.length) {
    const count = data.accepted.document.rules.length;
    await holdOverviewPreparationJobForImpact("uplift", startedAt);
    setOverviewPreparationJob(aeId, "uplift", "skipped", `Uplift rules already accepted (${count} rule${count === 1 ? "" : "s"})`);
    return data.accepted;
  }

  let suggestion = data.suggestion || null;
  if (!suggestion?.document?.rules?.length) {
    setOverviewPreparationJob(aeId, "uplift", "running", "Running uplift-rule suggestion");
    const result = await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/suggest`, { method: "POST" });
    suggestion = result.suggestion;
    if (state.currentCouncil?.agreement_id === aeId) {
      const sections = council.sections || (council.sections = {});
      const uplift = sections.uplift_rules || (sections.uplift_rules = {});
      const nextData = uplift.data && typeof uplift.data === "object" ? uplift.data : {};
      nextData.suggestion = suggestion;
      nextData.suggestion_generated_at = new Date().toISOString();
      uplift.data = nextData;
      uplift.status = result.section_status || uplift.status || "in_progress";
    }
  }

  if (state.currentCouncil?.agreement_id === aeId) {
    const sections = council.sections || (council.sections = {});
    const uplift = sections.uplift_rules || (sections.uplift_rules = {});
    const nextData = uplift.data && typeof uplift.data === "object" ? uplift.data : {};
    nextData.suggestion = suggestion;
    uplift.data = nextData;
    if (!uplift.status || uplift.status === "not_started") uplift.status = "in_progress";
    renderSectionsList();
  }
  const count = suggestion?.document?.rules?.length || 0;
  await holdOverviewPreparationJobForImpact("uplift", startedAt);
  setOverviewPreparationJob(aeId, "uplift", "done", `Extracted ${count} uplift rule${count === 1 ? "" : "s"} for sign-off`);
  return suggestion;
}

async function runOverviewScenarioPreparation(aeId) {
  const startedAt = Date.now();
  setOverviewPreparationJob(aeId, "scenarios", "running", "Running scenario checks");
  const result = await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/scenarios`, {
    method: "POST",
    body: JSON.stringify({ overrides: scenarioOverrides.get(aeId) || {} }),
  });
  if (state.currentCouncil?.agreement_id === aeId && state.currentCouncil?.sections?.scenarios) {
    state.currentCouncil.sections.scenarios.status = result.section_status || state.currentCouncil.sections.scenarios.status;
    state.currentCouncil.sections.scenarios.data = {
      future_triggers: result.future_triggers || [],
      blocking_results: result.blocking_results || [],
    };
  }
  const scenarios = result.scenarios || [];
  const constructable = result.constructable_periods || [];
  await holdOverviewPreparationJobForImpact("scenarios", startedAt);
  setOverviewPreparationJob(
    aeId,
    "scenarios",
    "done",
    `Prepared ${scenarios.length} scenario row${scenarios.length === 1 ? "" : "s"} and ${constructable.length} constructable period${constructable.length === 1 ? "" : "s"}`,
  );
  if (state.currentCouncil?.agreement_id === aeId) renderSectionsList();
}

function queueOverviewPreparation({ force = false, aeId = state.currentCouncil?.agreement_id, source = "overview" } = {}) {
  if (!aeId) return;
  const prep = overviewPreparationState(aeId);
  renderPreparationSurfaces(aeId);
  if (prep.running) return;
  if (prep.completed && !force) return;
  if (force) resetOverviewPreparation(prep);
  prep.running = true;
  prep.startedAt = new Date().toISOString();
  state.reviewBoardAutomationActiveAeId = source === "matrix" ? aeId : state.reviewBoardAutomationActiveAeId;
  renderPreparationSurfaces(aeId);
  (async () => {
    let results;
    try {
      await ensureOverviewPreparationCouncil(aeId);
      try {
        await runOverviewDocumentMapPreparation(aeId);
      } catch (error) {
        setOverviewPreparationJob(aeId, "overview", "failed", apiErrorMessage(error));
      }
      results = await Promise.allSettled([
        runOverviewPayExtractionPreview(aeId).catch((error) => {
          setOverviewPreparationJob(aeId, "pay", "failed", apiErrorMessage(error));
          throw error;
        }),
        ensureOverviewUpliftSuggestion(aeId)
          .then(() => runOverviewScenarioPreparation(aeId))
          .catch((error) => {
            const upliftJob = overviewPreparationState(aeId)?.jobs?.uplift;
            if (upliftJob?.status === "running" || upliftJob?.status === "queued") {
              setOverviewPreparationJob(aeId, "uplift", "failed", apiErrorMessage(error));
            }
            setOverviewPreparationJob(aeId, "scenarios", "failed", apiErrorMessage(error));
            throw error;
          }),
      ]);
      await fetchCouncils().catch(() => {});
    } catch (error) {
      const message = apiErrorMessage(error);
      Object.entries(prep.jobs || {}).forEach(([key, job]) => {
        if (job.status === "queued" || job.status === "running") {
          setOverviewPreparationJob(aeId, key, "failed", message);
        }
      });
      results = [{ status: "rejected", reason: error }];
    } finally {
      prep.running = false;
      prep.completed = true;
      prep.finishedAt = new Date().toISOString();
      if (state.reviewBoardAutomationActiveAeId === aeId) state.reviewBoardAutomationActiveAeId = "";
      renderPreparationSurfaces(aeId);
      const failed = results.filter((result) => result.status === "rejected").length
        + Object.values(prep.jobs || {}).filter((job) => job.status === "failed").length;
      if (failed) {
        toast(`Computer run finished with ${failed} issue${failed === 1 ? "" : "s"}`, "warning");
      } else {
        toast("Computer run finished", "success");
      }
    }
  })();
}

function syntheticHumanReviewDefaultJobs() {
  return {
    overview: { status: "queued", label: "Overview QA", detail: "Waiting for evidence prep" },
    uplift_rules: { status: "queued", label: "Uplift QA", detail: "Waiting for accepted rules" },
    pay_tables: { status: "queued", label: "Pay QA", detail: "Waiting for accepted tables" },
    scenarios: { status: "queued", label: "Scenario QA", detail: "Waiting for scenario checks" },
    end_of_band_dollars: { status: "queued", label: "End-of-band QA", detail: "Waiting for scenario promotions" },
    uplifts: { status: "queued", label: "Governed QA", detail: "Waiting for promotions" },
    learning: { status: "queued", label: "System learning", detail: "Waiting for review decisions" },
  };
}

class SyntheticHumanSystemImprovementPause extends Error {
  constructor(message) {
    super(message);
    this.name = "SyntheticHumanSystemImprovementPause";
    this.systemImprovementPause = true;
  }
}

function isSyntheticSystemImprovementPause(error) {
  return Boolean(error?.systemImprovementPause || error?.name === "SyntheticHumanSystemImprovementPause");
}

function syntheticHumanReviewState(aeId = state.currentCouncil?.agreement_id) {
  if (!aeId) return null;
  if (!state.syntheticHumanReview[aeId]) {
    state.syntheticHumanReview[aeId] = {
      running: false,
      completed: false,
      startedAt: null,
      finishedAt: null,
      jobs: syntheticHumanReviewDefaultJobs(),
      improvements: [],
      decisions: [],
      commentary: [],
      systemImprovementRequests: [],
      awaitingSystemImprovement: false,
      resumeFrom: "",
    };
  }
  normaliseSyntheticHumanReviewJobs(state.syntheticHumanReview[aeId]);
  return state.syntheticHumanReview[aeId];
}

function normaliseSyntheticHumanReviewJobs(run) {
  if (!run) return;
  const defaults = syntheticHumanReviewDefaultJobs();
  run.jobs = run.jobs && typeof run.jobs === "object" ? run.jobs : {};
  Object.entries(defaults).forEach(([key, fallback]) => {
    run.jobs[key] = {
      ...fallback,
      ...(run.jobs[key] || {}),
    };
  });
  run.improvements = Array.isArray(run.improvements) ? run.improvements : [];
  run.decisions = Array.isArray(run.decisions) ? run.decisions : [];
  run.commentary = Array.isArray(run.commentary) ? run.commentary : [];
  run.systemImprovementRequests = Array.isArray(run.systemImprovementRequests) ? run.systemImprovementRequests : [];
  run.awaitingSystemImprovement = Boolean(run.awaitingSystemImprovement);
  run.resumeFrom = typeof run.resumeFrom === "string" ? run.resumeFrom : "";
}

function resetSyntheticHumanReview(run) {
  if (!run) return;
  normaliseSyntheticHumanReviewJobs(run);
  run.completed = false;
  run.finishedAt = null;
  run.improvements = [];
  run.decisions = [];
  run.commentary = [];
  run.systemImprovementRequests = [];
  run.awaitingSystemImprovement = false;
  run.resumeFrom = "";
  Object.entries(syntheticHumanReviewDefaultJobs()).forEach(([key, fallback]) => {
    run.jobs[key].status = fallback.status;
    run.jobs[key].detail = fallback.detail;
  });
}

function syntheticSystemImprovementId(request) {
  return [
    request?.stage,
    request?.ruleKey,
    request?.request,
    request?.resumeFrom,
  ].map((part) => String(part || "").trim().toLowerCase()).filter(Boolean).join("::");
}

function requestSyntheticSystemImprovement(aeId, request) {
  const run = syntheticHumanReviewState(aeId);
  if (!run) return;
  const normalized = {
    id: syntheticSystemImprovementId(request),
    requestedAt: new Date().toISOString(),
    status: "awaiting_implementation",
    stage: request?.stage || "Synthetic QA",
    judgement: request?.judgement || "",
    request: request?.request || "Bake this reviewer judgement into the backend engine before continuing.",
    resumeFrom: request?.resumeFrom || "",
  };
  const existing = run.systemImprovementRequests.find((item) => item.id === normalized.id);
  if (!existing) {
    run.systemImprovementRequests.push(normalized);
  } else {
    Object.assign(existing, normalized);
  }
  const line = `${normalized.stage}: ${normalized.request}`;
  if (!run.improvements.includes(line)) run.improvements.push(line);
  addSyntheticHumanComment(aeId, "I can make this call, but making it by hand forever would be ritual paperwork in a tiny hat. I am pausing so the engine learns the pattern before it touches downstream evidence.");
  run.awaitingSystemImprovement = true;
  run.resumeFrom = normalized.resumeFrom;
  setSyntheticHumanJob(aeId, "learning", "waiting", `Awaiting implementation: ${normalized.request}`);
  throw new SyntheticHumanSystemImprovementPause(`System improvement requested before continuing: ${normalized.request}`);
}

function markSyntheticSystemImprovementsImplemented(run) {
  if (!run?.awaitingSystemImprovement) return "";
  const now = new Date().toISOString();
  for (const item of run.systemImprovementRequests || []) {
    if (item?.status === "awaiting_implementation") {
      item.status = "implemented";
      item.implementedAt = now;
    }
  }
  run.awaitingSystemImprovement = false;
  return run.resumeFrom || "";
}

function addSyntheticHumanDecision(aeId, decision) {
  const run = syntheticHumanReviewState(aeId);
  const text = String(decision || "").trim();
  if (!run || !text) return;
  if (!run.decisions.includes(text)) run.decisions.push(text);
}

function addSyntheticHumanComment(aeId, comment) {
  const run = syntheticHumanReviewState(aeId);
  const text = String(comment || "").trim();
  if (!run || !text) return;
  const entry = { at: new Date().toISOString(), text };
  run.commentary.push(entry);
  if (run.commentary.length > 12) run.commentary = run.commentary.slice(-12);
  renderSyntheticHumanSurfaces(aeId);
}

function syntheticHumanDecisionSummary(run) {
  const decisions = (run?.decisions || []).filter(Boolean);
  if (decisions.length) return decisions.slice(0, 5);
  const failed = Object.values(run?.jobs || {}).find((job) => job.status === "failed");
  if (failed) return [`Stopped before completion: ${failed.detail || "a human decision is required."}`];
  if (run?.completed) return ["Process was unremarkable: no material synthetic-review judgement calls were needed."];
  return ["No reviewer decisions recorded yet."];
}

function renderSyntheticHumanSurfaces(aeId) {
  if (state.currentCouncil?.agreement_id === aeId && document.body?.dataset?.view === "workspace") {
    setWorkspaceModuleHeader(state.currentSection);
  }
  if (document.body?.dataset?.view === "matrix") renderMatrix();
  if (state.currentCouncil?.agreement_id === aeId) renderSectionsList();
}

function setSyntheticHumanJob(aeId, jobKey, status, detail) {
  const run = syntheticHumanReviewState(aeId);
  if (!run?.jobs?.[jobKey]) return;
  run.jobs[jobKey].status = status;
  run.jobs[jobKey].detail = detail;
  if (status === "running") followAutomationWorkspaceSection(aeId, jobKey);
  renderSyntheticHumanSurfaces(aeId);
}

function syntheticHumanReviewReply(run) {
  const jobEntries = Object.entries(run?.jobs || {});
  const jobs = jobEntries.map(([, job]) => job);
  const runningEntry = jobEntries.find(([, job]) => job.status === "running");
  if (runningEntry) {
    const [key, running] = runningEntry;
    const stageMood = {
      overview: "checking the agreement identity before the spreadsheet starts believing in itself",
      uplift_rules: "turning wage-rule prose into dates and percentages the engine can actually use",
      pay_tables: "making the numbers prove they belong to the general benchmark cohort",
      scenarios: "letting the tables and rules argue, then keeping the useful argument",
      end_of_band_dollars: "checking whether end-of-band cash belongs beside each governed band",
      uplifts: "checking that governed evidence promoted into analysis-ready assets",
      learning: "looking for repeated judgement patterns that should become system behaviour",
    }[key] || "checking the record now";
    return `I am acting as the reviewer on ${running.label.toLowerCase()}: ${running.detail || stageMood}.`;
  }
  if (run?.awaitingSystemImprovement) {
    const request = (run.systemImprovementRequests || []).find((item) => item?.status === "awaiting_implementation");
    return `I made a judgement and requested a system improvement before continuing. ${request?.request || "Awaiting implementation."}`;
  }
  const failed = jobs.find((job) => job.status === "failed");
  if (failed) return `I stopped at ${failed.label.toLowerCase()}. ${failed.detail || "A human decision is still required."}`;
  if (run?.completed) {
    const improvementCount = (run.improvements || []).length;
    return improvementCount
      ? `I completed the automated review and logged ${improvementCount} system improvement signal${improvementCount === 1 ? "" : "s"}.`
      : "I completed the automated review; no new improvement signals were raised.";
  }
  if (run?.running) {
    const latest = (run.commentary || []).filter(Boolean).slice(-1)[0];
    const text = latest?.text || latest || "moving between review stages";
    return `I am still running: ${text}`;
  }
  return "I can act as the reviewer after the source is ready.";
}

function syntheticHumanNote(section, lines = []) {
  const label = SECTION_LABELS[section] || section;
  return [
    `Automated reviewer accepted ${label} from the Review Board.`,
    ...lines,
  ].filter(Boolean).join("\n");
}

async function saveSyntheticSectionHumanQa(aeId, section, detailLines = []) {
  await ensureOverviewPreparationCouncil(aeId);
  const summary = [
    buildSectionQaSummary(section, { enabled: true }),
    "",
    "Reviewer action:",
    ...detailLines.map((line) => `- ${line}`),
  ].join("\n");
  const notes = syntheticHumanNote(section, detailLines);
  if (section === "scenarios") {
    await persistScenarioHumanQaNote(aeId, summary, notes, true);
  }
  const resp = await api(`/api/councils/${encodeURIComponent(aeId)}/sections/${encodeURIComponent(section)}/human-qa`, {
    method: "PATCH",
    body: JSON.stringify({ enabled: true, notes, summary }),
  });
  applyHumanQaResponse(resp);
  return resp;
}

function syntheticExtractedPayTables() {
  const extracted = state.payDraft.rangeExtraction?.tables;
  if (!Array.isArray(extracted)) return [];
  return extracted.filter((table) => Array.isArray(table?.rows) && table.rows.length);
}

function adoptSyntheticExtractedPayTables() {
  if (state.payDraft.tables.length) return 0;
  const extracted = syntheticExtractedPayTables();
  if (!extracted.length) return 0;
  state.payDraft.tables = JSON.parse(JSON.stringify(extracted));
  applyToDateRecalc();
  return extracted.length;
}

function blockingPayValidations(validations = []) {
  return (Array.isArray(validations) ? validations : []).filter((item) => {
    const level = String(item?.level || item?.severity || "").toLowerCase();
    return ["error", "critical", "blocker", "failed"].includes(level);
  });
}

function syntheticPayTableLabel(table, index) {
  const title = String(table?.table_title || "").trim() || `Table ${index + 1}`;
  const date = String(table?.effective_from || "").trim();
  const kind = String(table?.rate_kind || "").trim();
  return [title, date, kind].filter(Boolean).join(" | ");
}

function syntheticPayTableText(table) {
  const parts = [
    table?.table_title,
    table?.source_clause,
    table?.effective_from_note,
    table?.period_label_source,
    table?.rate_kind,
  ];
  for (const row of table?.rows || []) {
    if (row && typeof row === "object") {
      parts.push(row.title, row.classification, row.notes);
    }
  }
  return parts.map((part) => String(part || "")).join(" ").toLowerCase();
}

function syntheticLgaNameParts() {
  const raw = String(state.currentCouncil?.canonical_lga_short_name || "").toLowerCase();
  return raw
    .split(/[^a-z0-9]+/)
    .map((part) => part.trim())
    .filter((part) => part.length >= 3 && !["city", "shire", "rural", "council", "borough"].includes(part));
}

function syntheticStandardCellKey(row) {
  const band = String(row?.band ?? "").trim();
  const level = String(row?.level ?? "").trim().toUpperCase();
  if (!band || !level) return "";
  return `${band}::${level}`;
}

function syntheticPayTableCells(table) {
  const cells = new Set();
  for (const row of table?.rows || []) {
    const key = syntheticStandardCellKey(row);
    if (key) cells.add(key);
  }
  return cells;
}

function syntheticPayTableBandNumbers(table) {
  const bands = new Set();
  for (const row of table?.rows || []) {
    const band = Number(String(row?.band ?? "").trim());
    if (Number.isInteger(band) && band > 0) bands.add(band);
  }
  return [...bands].sort((a, b) => a - b);
}

function syntheticPayTablePageNumbers(table) {
  return normalisePageList([
    ...(Array.isArray(table?.source_pages) ? table.source_pages : []),
    ...(Array.isArray(table?.pages) ? table.pages : []),
    table?.source_page,
    table?.page,
  ]);
}

function syntheticPayTablePagesTouch(a, b) {
  const aPages = syntheticPayTablePageNumbers(a);
  const bPages = syntheticPayTablePageNumbers(b);
  if (!aPages.length || !bPages.length) return false;
  return aPages.some((left) => bPages.some((right) => Math.abs(left - right) <= 1));
}

function syntheticPayTableOverlapProfile(a, b) {
  const aRows = Array.isArray(a?.rows) ? a.rows : [];
  const bRows = Array.isArray(b?.rows) ? b.rows : [];
  const aByCell = new Map();
  const bByCell = new Map();
  for (const row of aRows) {
    const key = syntheticStandardCellKey(row);
    if (key) aByCell.set(key, syntheticComparableRate(row));
  }
  for (const row of bRows) {
    const key = syntheticStandardCellKey(row);
    if (key) bByCell.set(key, syntheticComparableRate(row));
  }
  let overlap = 0;
  let conflicts = 0;
  let matching = 0;
  let newFromB = 0;
  for (const [key, rate] of bByCell.entries()) {
    if (!aByCell.has(key)) {
      newFromB += 1;
      continue;
    }
    overlap += 1;
    if (aByCell.get(key) === rate) matching += 1;
    else conflicts += 1;
  }
  return { overlap, conflicts, matching, newFromB };
}

function syntheticTablesCompatibleForContinuation(keeper, candidate) {
  const profile = syntheticPayTableOverlapProfile(keeper, candidate);
  if (profile.overlap <= 0 || profile.newFromB <= 0 || profile.conflicts > 0) return false;
  if (syntheticStandardHoursConflict(keeper, candidate)) return false;
  if (syntheticDistinctCohortTitlePair(keeper, candidate)) return false;
  const titleText = `${normalisedSyntheticTableTitle(keeper)} ${normalisedSyntheticTableTitle(candidate)}`;
  const continuationTitle = /\bstandard rates?\b|\bband\s*\d+\b|\bbanded structure\b/.test(titleText);
  return syntheticPayTablePagesTouch(keeper, candidate) || continuationTitle;
}

function syntheticUnknownTableCanMergeAsContinuation(keeper, candidate) {
  const profile = syntheticPayTableOverlapProfile(keeper, candidate);
  if (profile.conflicts > 0 || profile.overlap > 0 || profile.newFromB <= 0) return false;
  if (syntheticStandardHoursConflict(keeper, candidate)) return false;
  if (syntheticDistinctCohortTitlePair(keeper, candidate)) return false;
  const titleText = `${normalisedSyntheticTableTitle(keeper)} ${normalisedSyntheticTableTitle(candidate)}`;
  return syntheticPayTablePagesTouch(keeper, candidate) && /\bstandard rates?\b|\bband\s*\d+\b|\bbanded structure\b/.test(titleText);
}

function syntheticTableIsAbsorbedByKeeper(keeper, candidate) {
  const profile = syntheticPayTableOverlapProfile(keeper, candidate);
  return profile.overlap > 0 && profile.conflicts === 0 && profile.newFromB === 0;
}

function syntheticPayTableCohort(table) {
  const text = syntheticPayTableText(table);
  const lgaParts = syntheticLgaNameParts();
  if (state.currentCouncil?.is_split_row && lgaParts.length && lgaParts.some((part) => text.includes(part))) {
    return { kind: "general", label: "current LGA table", confidence: "high" };
  }
  if (/\ball employees except\b|\bexcept\s+(library|maternal|mch|nurs|pool|leisure|school crossing)/.test(text)) {
    return { kind: "general", label: "general table excluding specialist cohorts", confidence: "high" };
  }
  const specialised = [
    ["casual rates", /\bcasual\b/],
    ["maternal and child health", /\b(maternal|mch|child health|immunisation|nurse|nursing)\b/],
    ["pool services", /\b(pool|aquatic|lifeguard|swim|swimming)\b/],
    ["child care / early years", /\b(child care|childcare|early years|kindergarten|preschool)\b/],
    ["library", /\b(library|libraries|librarian)\b/],
    ["street cleaning", /\bstreet cleaning\b|\bwaste collection\b/],
    ["art gallery annualised rates", /\bart gallery\b|\bannualised rates\b/],
    ["allowance schedule", /\ballowance(s)?\s+(table|schedule)\b|^allowance(s)?\b/],
    ["parks and gardens", /\bparks?\s+and\s+gardens?\b/],
    ["arboriculture", /\barboriculture\b|\barborist\b/],
    ["tourism / visitor services", /\b(tourism|visitor information|visitor services)\b/],
    ["senior officers", /\b(senior officer|executive|chief executive|ceo)\b/],
    ["apprentices / trainees", /\b(apprentice|trainee|cadet|graduate)\b/],
    ["school crossing", /\b(school crossing|crossing supervisor)\b/],
    ["community transport", /\bcommunity transport\b|\btransport staff\b/],
    ["aged / disability / home care", /\b(aged care|disability|home care|home\/personal care|personal care|community care)\b/],
    ["loaded allowance rates", /\b(including|inclusive of|with)\s+(industry\s+)?allowance\b|\bindustry allowance\b/],
    ["operational outdoor cohort", /\b(outdoor\s+full\s+time|outdoor\s+[–-]|outdoor\b.{0,80}(physical\s*&\s*community services|physical and community services))\b/],
    ["physical services loaded cohort", /\bphysical and community services\b|\bphysical\s*&\s*community services\b/],
    ["legacy council cohort", /\b(ex[-\s]?(city|shire|council)|former\s+(city|shire|council)|pre[-\s]?amalgamation)\b/],
    ["leisure services", /\bleisure\b/],
  ];
  for (const [label, pattern] of specialised) {
    if (pattern.test(text)) {
      return { kind: "specialised", label, confidence: "high" };
    }
  }
  const cells = syntheticPayTableCells(table);
  const bandNumbers = syntheticPayTableBandNumbers(table);
  if (/\bstandard rates?\b|\bstandard salary\b|\bstandard\s+band/.test(text)) {
    return { kind: "general", label: "standard rates", confidence: "high" };
  }
  if (bandNumbers.length === 1 && /\bband\s*\d+\b/.test(text)) {
    return { kind: "general", label: "single-band standard continuation", confidence: "medium" };
  }
  if (bandNumbers.length >= 3 && cells.size >= 12) {
    return { kind: "general", label: "multi-band standard rates", confidence: "medium" };
  }
  if (/\bindoor\b|\bother than physical\b/.test(text)) {
    return { kind: "general", label: "standard indoor benchmark bandings", confidence: "high" };
  }
  if (/\bgeneral classifications?\b|\bgeneral\s+classifications?\s+and\s+rates?\s+of\s+pay\b/.test(text)) {
    return { kind: "general", label: "general classification benchmark table", confidence: "high" };
  }
  if (/\btechnical\b.{0,60}\bprofessional\b.{0,60}\badministrative\b|\bpay\s+rates?\s+20\d{2}\b/.test(text)) {
    return { kind: "general", label: "standard technical/professional benchmark bandings", confidence: "high" };
  }
  const generalSignals = [
    /\bband(s)?\s*1\s*(-|to|through|&|and)?\s*8\b/.test(text),
    /\bclassification(s)?\b/.test(text),
    /\b(salary|wage|weekly|annual)\s+(rates|table)\b/.test(text),
    /\btechnical\b|\bprofessional\b|\badministrative\b/.test(text),
    /\bordinary\b|\bbase rate\b|\bgeneral employee\b|\bemployee classifications\b/.test(text),
    /\bindoor\b|\bother than physical\b/.test(text),
    cells.size >= 20,
  ].filter(Boolean).length;
  if (generalSignals >= 2 || cells.size >= 24) {
    return { kind: "general", label: "standard bandings", confidence: generalSignals >= 3 ? "high" : "medium" };
  }
  return { kind: "unknown", label: "unclear cohort", confidence: "low" };
}

function syntheticComparableRate(row) {
  const value = row?.weekly_rate ?? row?.annual_rate ?? row?.fortnightly_rate ?? row?.hourly_rate ?? row?.rate;
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number * 100) / 100 : null;
}

function syntheticTablesHaveSameRates(a, b) {
  const aRows = Array.isArray(a?.rows) ? a.rows : [];
  const bRows = Array.isArray(b?.rows) ? b.rows : [];
  const bByCell = new Map();
  for (const row of bRows) {
    const key = syntheticStandardCellKey(row);
    if (key) bByCell.set(key, syntheticComparableRate(row));
  }
  let compared = 0;
  for (const row of aRows) {
    const key = syntheticStandardCellKey(row);
    if (!key || !bByCell.has(key)) continue;
    compared += 1;
    if (syntheticComparableRate(row) !== bByCell.get(key)) return false;
  }
  return compared > 0 && compared === Math.min(syntheticPayTableCells(a).size, syntheticPayTableCells(b).size);
}

function normalisedSyntheticTableTitle(table) {
  return String(table?.table_title || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function syntheticSameTitleDuplicate(a, b) {
  const aTitle = normalisedSyntheticTableTitle(a);
  const bTitle = normalisedSyntheticTableTitle(b);
  return Boolean(aTitle && aTitle === bTitle);
}

function syntheticDistinctCohortTitlePair(a, b) {
  const titles = `${normalisedSyntheticTableTitle(a)} || ${normalisedSyntheticTableTitle(b)}`;
  const markerPairs = [
    [/\bschedule\s*1\b/, /\bschedule\s*2\b/],
    [/\byear\s*1\b/, /\byear\s*2\b/],
  ];
  if (markerPairs.some(([left, right]) => left.test(titles) && right.test(titles))) return true;
  return /\bmchn\b|\bmaternal\b|\bcommunity transport\b|\bphysical and community\b/.test(titles);
}

function syntheticStandardHoursRank(table) {
  const text = syntheticPayTableText(table);
  if (/\b38\s*hours?\b|\b38\s*hour\b/.test(text)) return 0;
  if (/\b35\s*hours?\b|\b35\s*hour\b/.test(text)) return 2;
  return 1;
}

function syntheticRateKindRank(table) {
  return { weekly: 0, annual: 1, fortnightly: 2 }[String(table?.rate_kind || "").toLowerCase()] ?? 3;
}

function syntheticBenchmarkSort(a, b) {
  return (
    syntheticStandardHoursRank(a.table) - syntheticStandardHoursRank(b.table)
    || syntheticRateKindRank(a.table) - syntheticRateKindRank(b.table)
    || b.cells.size - a.cells.size
  );
}

function syntheticStandardHoursConflict(a, b) {
  const ranks = new Set([syntheticStandardHoursRank(a), syntheticStandardHoursRank(b)]);
  return ranks.has(0) && ranks.has(2);
}

function nearestSyntheticRuleDate(sourceIso, ruleDates) {
  if (!isIso(sourceIso) || !Array.isArray(ruleDates)) return { date: null, tieIssue: null };
  const sourceTime = Date.parse(`${sourceIso}T00:00:00Z`);
  const dayMs = 24 * 60 * 60 * 1000;
  const maxSnapMs = 183 * dayMs;
  const candidates = [...new Set(ruleDates.filter((date) => isIso(date)))]
    .map((date) => ({
      date,
      delta: Math.abs(Date.parse(`${date}T00:00:00Z`) - sourceTime),
    }))
    .sort((a, b) => (a.delta - b.delta) || a.date.localeCompare(b.date));
  if (!candidates.length) return { date: null, tieIssue: null };
  if (candidates.length > 1 && candidates[0].delta === candidates[1].delta) {
    return {
      date: null,
      tieIssue: `source date ${sourceIso} is equidistant to uplift rule dates ${candidates[0].date} and ${candidates[1].date}`,
    };
  }
  if (candidates[0].delta > maxSnapMs) {
    return {
      date: null,
      tieIssue: `nearest uplift rule date is ${Math.round(candidates[0].delta / dayMs)} days away, beyond the 183-day snap guard`,
    };
  }
  return { date: candidates[0].date, tieIssue: null };
}

function applySyntheticRuleAnchoredDatesToDraftTables() {
  const ruleDates = collectUpliftRuleDates(state.currentCouncil);
  if (!ruleDates.length || !Array.isArray(state.payDraft.tables)) return [];
  const prepared = state.payDraft.tables.map((table, index) => {
    const sourceIso = [table?.source_date_iso, table?.source_date_raw, table?.effective_from]
      .map((value) => String(value || "").trim())
      .find((value) => isIso(value)) || "";
    return { table, index, sourceIso };
  });
  for (const item of prepared) {
    if (!item.sourceIso) continue;
    const nearest = nearestSyntheticRuleDate(item.sourceIso, ruleDates);
    if (nearest.tieIssue && nearest.tieIssue.includes("equidistant")) {
      return [`Skipped rule-anchored pre-save snapping because table ${item.index} has a date tie: ${nearest.tieIssue}.`];
    }
  }
  const decisions = [];
  for (const item of prepared) {
    if (!item.sourceIso) continue;
    const nearest = nearestSyntheticRuleDate(item.sourceIso, ruleDates);
    if (!nearest.date) {
      if (nearest.tieIssue) {
        decisions.push(`Kept ${syntheticPayTableLabel(item.table, item.index)} at source date ${item.sourceIso}: ${nearest.tieIssue}.`);
      }
      continue;
    }
    item.table.source_date_iso = item.sourceIso;
    if (!item.table.source_date_raw) item.table.source_date_raw = item.table.effective_from;
    if (item.table.effective_from !== nearest.date) {
      decisions.push(`Aligned ${syntheticPayTableLabel(item.table, item.index)} from source date ${item.sourceIso} to uplift rule date ${nearest.date} before cohort QA.`);
    }
    item.table.canonical_date_iso = nearest.date;
    item.table.date_snapped = nearest.date !== item.sourceIso;
    item.table.snap_basis = nearest.date !== item.sourceIso ? "uplift_rule_event" : null;
    item.table.snap_note = nearest.date !== item.sourceIso
      ? `Snapped ${item.sourceIso} to uplift rule date ${nearest.date}`
      : "Already aligned to uplift rule date";
    item.table.effective_from = nearest.date;
  }
  return decisions;
}

function mergeSyntheticPayTableContinuation(target, source) {
  const targetCells = syntheticPayTableCells(target);
  const sourceRows = Array.isArray(source?.rows) ? source.rows : [];
  const rowsToAdd = sourceRows.filter((row) => {
    const key = syntheticStandardCellKey(row);
    return key && !targetCells.has(key);
  });
  if (!rowsToAdd.length) return false;
  target.rows = [...(target.rows || []), ...rowsToAdd];
  const pages = normalisePageList([
    ...(Array.isArray(target.source_pages) ? target.source_pages : []),
    target.source_page,
    ...(Array.isArray(source.source_pages) ? source.source_pages : []),
    source.source_page,
  ]);
  if (pages.length) target.source_pages = pages;
  if (!target.source_clause && source.source_clause) target.source_clause = source.source_clause;
  return true;
}

function resolveSyntheticPayTableCohorts() {
  const tables = Array.isArray(state.payDraft.tables) ? state.payDraft.tables : [];
  const workingTables = JSON.parse(JSON.stringify(tables));
  const groups = new Map();
  workingTables.forEach((table, index) => {
    const effective = String(table?.effective_from || "").trim();
    const kind = String(table?.rate_kind || "").trim() || "__unknown__";
    if (!effective) return;
    const key = `${effective}::${kind}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ table, index });
  });

  const remove = new Set();
  const decisions = [];
  const blockers = [];
  for (const [key, group] of groups.entries()) {
    if (group.length < 2) continue;
    const assessed = group.map((item) => ({
      ...item,
      cohort: syntheticPayTableCohort(item.table),
      cells: syntheticPayTableCells(item.table),
    }));
    const currentLga = state.currentCouncil?.is_split_row
      ? assessed.filter((item) => item.cohort.label === "current LGA table")
      : [];
    if (currentLga.length) {
      currentLga.sort((a, b) => b.cells.size - a.cells.size);
      const keeper = currentLga[0];
      for (const item of assessed) {
        if (item.index === keeper.index) continue;
        remove.add(item.index);
        decisions.push(`Split-agreement QA retained current LGA table ${syntheticPayTableLabel(keeper.table, keeper.index)} and dropped other council table ${syntheticPayTableLabel(item.table, item.index)}.`);
      }
      continue;
    }
    const general = assessed.filter((item) => item.cohort.kind === "general");
    const specialised = assessed.filter((item) => item.cohort.kind === "specialised");
    const unclear = assessed.filter((item) => item.cohort.kind === "unknown");
    if (!general.length) {
      const byTitle = new Map();
      for (const item of assessed) {
        const title = normalisedSyntheticTableTitle(item.table);
        if (!title) continue;
        if (!byTitle.has(title)) byTitle.set(title, []);
        byTitle.get(title).push(item);
      }
      const duplicateTitleGroups = [...byTitle.values()].filter((items) => items.length > 1);
      if (duplicateTitleGroups.length) {
        for (const items of duplicateTitleGroups) {
          items.sort((a, b) => b.cells.size - a.cells.size);
          const keeper = items[0];
          for (const candidate of items.slice(1)) {
            mergeSyntheticPayTableContinuation(keeper.table, candidate.table);
            remove.add(candidate.index);
            decisions.push(`Removed duplicate non-general pay table ${syntheticPayTableLabel(candidate.table, candidate.index)} and retained the fuller same-title extraction ${syntheticPayTableLabel(keeper.table, keeper.index)}.`);
          }
        }
        const remaining = assessed.filter((item) => !remove.has(item.index));
        if (remaining.length <= 1) continue;
      }
      blockers.push(`Duplicate pay tables need cohort review for ${key}: ${assessed.map((item) => syntheticPayTableLabel(item.table, item.index)).join("; ")}`);
      continue;
    }

    general.sort(syntheticBenchmarkSort);
    const keeper = general[0];
    const unresolvedGeneral = [];
    const unresolvedUnclear = [];
    for (const candidate of general.slice(1)) {
      const overlap = [...candidate.cells].filter((cell) => keeper.cells.has(cell)).length;
      if (overlap > 0 && syntheticStandardHoursConflict(keeper.table, candidate.table)) {
        remove.add(candidate.index);
        decisions.push(`Benchmark QA retained standard 38-hour table ${syntheticPayTableLabel(keeper.table, keeper.index)} and dropped non-standard 35-hour table ${syntheticPayTableLabel(candidate.table, candidate.index)}.`);
      } else if (overlap > 0 && syntheticTablesHaveSameRates(keeper.table, candidate.table)) {
        mergeSyntheticPayTableContinuation(keeper.table, candidate.table);
        keeper.cells = syntheticPayTableCells(keeper.table);
        remove.add(candidate.index);
        decisions.push(`Removed duplicate copy ${syntheticPayTableLabel(candidate.table, candidate.index)} after matching it to ${syntheticPayTableLabel(keeper.table, keeper.index)}.`);
      } else if (overlap > 0 && syntheticTablesCompatibleForContinuation(keeper.table, candidate.table)) {
        mergeSyntheticPayTableContinuation(keeper.table, candidate.table);
        keeper.cells = syntheticPayTableCells(keeper.table);
        remove.add(candidate.index);
        decisions.push(`Merged split-page standard rate continuation ${syntheticPayTableLabel(candidate.table, candidate.index)} into ${syntheticPayTableLabel(keeper.table, keeper.index)}.`);
      } else if (overlap > 0 && syntheticSameTitleDuplicate(keeper.table, candidate.table)) {
        mergeSyntheticPayTableContinuation(keeper.table, candidate.table);
        keeper.cells = syntheticPayTableCells(keeper.table);
        remove.add(candidate.index);
        decisions.push(`Removed same-title duplicate pay table ${syntheticPayTableLabel(candidate.table, candidate.index)} and retained the fuller extraction ${syntheticPayTableLabel(keeper.table, keeper.index)}.`);
      } else if (
        overlap > 0
        && !syntheticDistinctCohortTitlePair(keeper.table, candidate.table)
        && overlap / Math.max(1, Math.min(keeper.cells.size, candidate.cells.size)) >= 0.8
      ) {
        mergeSyntheticPayTableContinuation(keeper.table, candidate.table);
        keeper.cells = syntheticPayTableCells(keeper.table);
        remove.add(candidate.index);
        decisions.push(`Removed overlapping generic duplicate pay table ${syntheticPayTableLabel(candidate.table, candidate.index)} and retained fuller extraction ${syntheticPayTableLabel(keeper.table, keeper.index)}.`);
      } else if (overlap === 0 && mergeSyntheticPayTableContinuation(keeper.table, candidate.table)) {
        remove.add(candidate.index);
        decisions.push(`Merged continuation pay table ${syntheticPayTableLabel(candidate.table, candidate.index)} into ${syntheticPayTableLabel(keeper.table, keeper.index)}.`);
        keeper.cells = syntheticPayTableCells(keeper.table);
      } else {
        unresolvedGeneral.push(candidate);
      }
    }
    for (const candidate of unclear) {
      if (remove.has(candidate.index)) continue;
      if (syntheticTableIsAbsorbedByKeeper(keeper.table, candidate.table)) {
        remove.add(candidate.index);
        decisions.push(`Removed partial duplicate pay table ${syntheticPayTableLabel(candidate.table, candidate.index)} after its matching cells were absorbed into ${syntheticPayTableLabel(keeper.table, keeper.index)}.`);
      } else if (syntheticTablesCompatibleForContinuation(keeper.table, candidate.table) || syntheticUnknownTableCanMergeAsContinuation(keeper.table, candidate.table)) {
        mergeSyntheticPayTableContinuation(keeper.table, candidate.table);
        keeper.cells = syntheticPayTableCells(keeper.table);
        remove.add(candidate.index);
        decisions.push(`Merged unclear split-page pay table ${syntheticPayTableLabel(candidate.table, candidate.index)} into ${syntheticPayTableLabel(keeper.table, keeper.index)} after matching it to the standard-rate evidence.`);
      } else {
        unresolvedUnclear.push(candidate);
      }
    }
    if (unresolvedGeneral.length) {
      blockers.push(`Duplicate general pay tables need human selection for ${key}: ${[keeper, ...unresolvedGeneral].map((item) => syntheticPayTableLabel(item.table, item.index)).join("; ")}`);
      continue;
    }
    if (unresolvedUnclear.length) {
      blockers.push(`Unclear duplicate pay tables need human selection for ${key}: ${[keeper, ...unresolvedUnclear].map((item) => syntheticPayTableLabel(item.table, item.index)).join("; ")}`);
      continue;
    }
    for (const item of specialised) {
      remove.add(item.index);
      decisions.push(`Cohort QA retained ${syntheticPayTableLabel(keeper.table, keeper.index)} and dropped specialised ${item.cohort.label} table ${syntheticPayTableLabel(item.table, item.index)}.`);
    }
  }

  if (remove.size && !blockers.length) {
    state.payDraft.tables = workingTables.filter((_, index) => !remove.has(index));
    const noteLine = `[${new Date().toISOString().slice(0, 10)}] Synthetic cohort QA: ${decisions.join(" ")}`;
    state.payDraft.notes = [state.payDraft.notes, noteLine].filter(Boolean).join("\n");
    applyToDateRecalc();
  }
  return { changed: remove.size > 0, decisions, blockers };
}

async function saveSyntheticPayTables(aeId, adoptedCount) {
  const sourceRef = state.payDraft.sourceRef
    || (state.payDraft.payTablePages.length ? `Automated review pages ${displayPages(state.payDraft.payTablePages)}` : "Automated review");
  const noteLine = adoptedCount
    ? `Automated reviewer accepted ${adoptedCount} extracted pay-table candidate${adoptedCount === 1 ? "" : "s"} for scenario testing.`
    : "Automated reviewer re-saved the existing accepted pay-table draft for scenario testing.";
  const notes = [state.payDraft.notes, noteLine].filter(Boolean).join("\n");
  const result = await api(`/api/councils/${encodeURIComponent(aeId)}/pay-tables/save`, {
    method: "POST",
    body: JSON.stringify({
      action: "replace",
      tables: state.payDraft.tables,
      source_ref: sourceRef,
      notes,
      status: "done",
    }),
  });
  state.payDraft.sourceRef = sourceRef;
  state.payDraft.notes = notes;
  state.payDraft.status = "done";
  state.payDraft.validations = result.validations || [];
  await loadCouncilContext(aeId, "pay_tables");
  return result;
}

function acceptedUpliftRuleDates() {
  const rules = state.currentCouncil?.sections?.uplift_rules?.data?.accepted?.document?.rules || [];
  return new Set(rules.map((rule) => rule?.effective_date).filter(Boolean));
}

function acceptedUpliftRuleCount() {
  return acceptedUpliftRuleDates().size;
}

function currentUpliftTableAlignmentIssues() {
  const issues = state.currentCouncil?.sections?.uplift_rules?.data?.table_alignment_issues;
  return Array.isArray(issues) ? issues : [];
}

function upliftAlignmentIssueSummary(issue = {}) {
  const period = issue.period_effective_from || "Unknown period";
  const rule = issue.rule_quantum || "Accepted uplift rule";
  const affected = issue.affected_cells && issue.covered_cells
    ? `${issue.affected_cells}/${issue.covered_cells} cells`
    : "";
  const mechanised = issue.mechanised_weekly_increase == null ? "" : displayCurrency(issue.mechanised_weekly_increase);
  const implied = issue.implied_weekly_increase == null ? "" : displayCurrency(issue.implied_weekly_increase);
  const movement = mechanised && implied
    ? `Rule implies ${mechanised}/week; table implies ${implied}/week.`
    : "";
  return [period, rule, affected, movement].filter(Boolean).join(" - ");
}

function renderUpliftTableAlignmentIssues(issues = []) {
  const items = Array.isArray(issues) ? issues : [];
  if (!items.length) return "";
  return `
    <div class="card mb-panel-card uplift-alignment-card">
      <div class="uplift-alignment-head">
        <div>
          <span class="mb-eyebrow">Rule/table alignment</span>
          <h3>Review uplift extraction before scenarios</h3>
        </div>
        <span class="mb-status-chip mb-status-chip-warning">${items.length} issue${items.length === 1 ? "" : "s"}</span>
      </div>
      <p>The published table movement is coherent, but it does not match the accepted uplift rule. Treat this as an upstream rule/table binding problem before scenario QA or governed promotion.</p>
      <div class="uplift-alignment-list">
        ${items.map((issue) => {
          const tableNames = Array.isArray(issue.table_names) ? issue.table_names.filter(Boolean) : [];
          return `
            <article class="uplift-alignment-issue">
              <strong>${escapeHtml(issue.period_effective_from || "Unknown period")}</strong>
              <p>${escapeHtml(issue.message || upliftAlignmentIssueSummary(issue))}</p>
              <dl>
                <div><dt>Rule</dt><dd>${escapeHtml(issue.rule_quantum || "Accepted uplift rule")}</dd></div>
                <div><dt>Cells</dt><dd>${escapeHtml(issue.affected_cells && issue.covered_cells ? `${issue.affected_cells}/${issue.covered_cells}` : DISPLAY_EMPTY)}</dd></div>
                <div><dt>Rule movement</dt><dd>${escapeHtml(issue.mechanised_weekly_increase == null ? DISPLAY_EMPTY : `${displayCurrency(issue.mechanised_weekly_increase)}/week`)}</dd></div>
                <div><dt>Table movement</dt><dd>${escapeHtml(issue.implied_weekly_increase == null ? DISPLAY_EMPTY : `${displayCurrency(issue.implied_weekly_increase)}/week`)}</dd></div>
              </dl>
              ${tableNames.length ? `<small>${escapeHtml(tableNames.slice(0, 3).join(" | "))}</small>` : ""}
            </article>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function requestSyntheticRuleBindingImprovement(aeId, issues = [], resumeFrom = "uplift_rules") {
  const items = Array.isArray(issues) ? issues : [];
  const summary = items.length
    ? items.map((issue) => upliftAlignmentIssueSummary(issue)).join(" ")
    : "Accepted uplift rule conflicts with the published table movement pattern.";
  addSyntheticHumanComment(aeId, `Serious stop: ${items.length || 1} rule/table mismatch${(items.length || 1) === 1 ? "" : "es"} found. The table movement is coherent, which means the rule binding is the suspect in the hallway, not the pay table.`);
  addSyntheticHumanDecision(aeId, `Stopped for uplift-rule extraction review: ${summary}`);
  setSyntheticHumanJob(aeId, "uplift_rules", "waiting", "Rule/table binding conflict needs extraction review");
  setSyntheticHumanJob(aeId, "scenarios", "queued", "Waiting for uplift-rule review");
  requestSyntheticSystemImprovement(aeId, {
    stage: "Uplift QA rule/table binding",
    ruleKey: "uplift_rule_table_binding_conflict",
    judgement: summary,
    request: "Stop scenario QA when an accepted uplift rule conflicts with a coherent published table pattern; route the record back to uplift-rule extraction review.",
    resumeFrom,
  });
}

function syntheticScenarioEligible(scenario) {
  return ["consistent", "table_resolved", "baseline"].includes(String(scenario?.status || ""));
}

function syntheticScenarioPayTableOnly(scenario) {
  if (String(scenario?.status || "") !== "needs_attention") return false;
  const reason = String(scenario?.reason || "").toLowerCase();
  return reason.includes("table exists for this period but no uplift rule covers it")
    || reason.includes("rule did not cover any cells");
}

function scenarioHasUnhandledDeltas(scenario) {
  return (scenario?.cell_deltas || []).some((delta) => (
    !delta.within_tolerance
    && delta.override_action == null
  ));
}

function scenarioPayTablePromotable(scenario) {
  return syntheticScenarioEligible(scenario)
    || (syntheticScenarioPayTableOnly(scenario) && !scenarioHasUnhandledDeltas(scenario));
}

function syntheticScenarioRuleExtractionIssues(result) {
  const issues = [];
  for (const scenario of result?.scenarios || []) {
    const decision = scenario?.decision_recommendation;
    if (!decision || decision.action !== "needs_rule_extraction_review") continue;
    issues.push({
      period_effective_from: scenario.period_effective_from,
      rule_quantum: scenario.rule_quantum || decision.rule_quantum,
      affected_cells: decision.affected_cells,
      covered_cells: decision.covered_cells,
      mechanised_weekly_increase: decision.mechanised_weekly_increase,
      implied_weekly_increase: decision.implied_weekly_increase,
      message: decision.reason,
      table_names: scenario.table_names || [],
    });
  }
  return issues;
}

function syntheticScenarioComputedOverrides(result) {
  const overrides = {};
  const decisions = [];
  for (const scenario of result?.scenarios || []) {
    if (syntheticScenarioEligible(scenario)) continue;
    const period = scenario?.period_effective_from;
    if (!period) continue;
    const failing = (scenario.cell_deltas || []).filter((delta) => (
      !delta.within_tolerance
      && delta.override_action == null
      && delta.computed_weekly != null
    ));
    if (!failing.length) continue;
    const allRecommendedComputed = failing.every((delta) => delta.recommended_action === "use_computed");
    const isolatedVariance = failing.length === 1 && (scenario.cell_deltas || []).length >= 10;
    if (!allRecommendedComputed && !isolatedVariance) continue;
    overrides[period] = overrides[period] || {};
    for (const delta of failing) {
      const cellKey = `${delta.band}:${delta.level}`;
      overrides[period][cellKey] = { action: "use_computed", weekly: Number(delta.computed_weekly) };
    }
    decisions.push(
      allRecommendedComputed
        ? `Used computed values for ${failing.length} recommended variance cell${failing.length === 1 ? "" : "s"} in ${period}.`
        : `Used computed value for isolated variance ${failing[0].band}:${failing[0].level} in ${period} to preserve downstream rule consistency.`,
    );
  }
  return { overrides, decisions };
}

async function applySyntheticScenarioComputedOverrides(aeId, scenarioResult) {
  const current = JSON.parse(JSON.stringify(scenarioOverrides.get(aeId) || {}));
  let result = scenarioResult;
  const decisions = [];
  for (let pass = 0; pass < 4; pass += 1) {
    const generated = syntheticScenarioComputedOverrides(result);
    if (!Object.keys(generated.overrides).length) break;
    let changed = false;
    for (const [period, cells] of Object.entries(generated.overrides)) {
      current[period] = { ...(current[period] || {}) };
      for (const [cellKey, override] of Object.entries(cells || {})) {
        if (JSON.stringify(current[period][cellKey]) !== JSON.stringify(override)) {
          current[period][cellKey] = override;
          changed = true;
        }
      }
    }
    if (!changed) break;
    decisions.push(...generated.decisions);
    scenarioOverrides.set(aeId, current);
    await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/scenarios/overrides`, {
      method: "POST",
      body: JSON.stringify({
        overrides: current,
        change_context: {
          scope: "synthetic_human",
          action: "use_computed_recommended",
          affected_cells: Object.values(generated.overrides).reduce((total, cells) => total + Object.keys(cells || {}).length, 0),
        },
      }),
    });
    result = await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/scenarios`, {
      method: "POST",
      body: JSON.stringify({
        overrides: current,
        change_context: { scope: "synthetic_human", action: "rerun_after_computed_overrides" },
      }),
    });
  }
  return { result, decisions };
}

async function promoteSyntheticGovernedAssets(aeId, scenarioResult) {
  const governedResult = await api(`/api/councils/${encodeURIComponent(aeId)}/governed-set`).catch(() => ({ governed: { periods: [] } }));
  const governedByPeriod = new Map();
  for (const period of governedResult?.governed?.periods || []) {
    if (period?.effective_from) governedByPeriod.set(period.effective_from, period);
  }
  const acceptedRuleDates = acceptedUpliftRuleDates();
  const scenarios = Array.isArray(scenarioResult?.scenarios) ? scenarioResult.scenarios : [];
  const datedScenarios = scenarios.filter((scenario) => scenario?.period_effective_from);
  const reviewRequired = datedScenarios.filter((scenario) => !syntheticScenarioEligible(scenario) && !syntheticScenarioPayTableOnly(scenario));
  if (reviewRequired.length) {
    throw new Error(`${reviewRequired.length} scenario period${reviewRequired.length === 1 ? "" : "s"} still need a human decision before governed promotion.`);
  }

  const promoted = [];
  for (const scenario of datedScenarios.filter((item) => syntheticScenarioEligible(item) || syntheticScenarioPayTableOnly(item))) {
    const date = scenario.period_effective_from;
    const governedPeriod = governedByPeriod.get(date) || {};
    const kinds = [];
    if (!governedPeriod.pay_table_governed_at) kinds.push("pay_table");
    if (syntheticScenarioEligible(scenario) && acceptedRuleDates.has(date) && !governedPeriod.uplift_rule_governed_at) kinds.push("uplift_rule");
    for (const kind of kinds) {
      const result = await api(`/api/councils/${encodeURIComponent(aeId)}/governed-set/promote`, {
        method: "POST",
        body: JSON.stringify({ period_effective_from: date, kind }),
      });
      promoted.push(`${governedAssetKindLabel(kind)} ${date}`);
      for (const period of result?.governed?.periods || []) {
        if (period?.effective_from) governedByPeriod.set(period.effective_from, period);
      }
    }
  }
  await loadCouncilContext(aeId, "scenarios");
  return promoted;
}

async function runSyntheticHumanOverview(aeId) {
  setSyntheticHumanJob(aeId, "overview", "running", "Checking source map, identity and metadata");
  addSyntheticHumanComment(aeId, "First pass is identity work: agreement ID, council, source map and page clues. If this bit is wrong, everything downstream becomes confidently wrong in a suit.");
  await runOverviewDocumentMapPreparation(aeId);
  const overview = state.currentCouncil?.overview || state.currentCouncil?.sections?.overview?.data || {};
  const pageCount = overview.page_count || state.currentCouncil?.page_count || "";
  const payPages = normalisePageList(overview.likely_pay_table_pages || overview.likely_pay_pages || []);
  const upliftPages = normalisePageList(overview.likely_uplift_pages || overview.likely_uplift_rule_pages || []);
  addSyntheticHumanComment(
    aeId,
    `Source map settled${pageCount ? ` across ${pageCount} pages` : ""}: ${payPages.length} pay-table clue${payPages.length === 1 ? "" : "s"} and ${upliftPages.length} uplift-rule clue${upliftPages.length === 1 ? "" : "s"}. The ledger has a spine now.`,
  );
  await saveSyntheticSectionHumanQa(aeId, "overview", ["Source map and metadata were available for downstream review."]);
  setSyntheticHumanJob(aeId, "overview", "done", "Human QA accepted for Overview");
}

async function runSyntheticHumanUpliftRules(aeId) {
  setSyntheticHumanJob(aeId, "uplift_rules", "running", "Testing wage-rule dates, quanta and table alignment");
  addSyntheticHumanComment(aeId, "Now I am turning wage-rule prose into machinery: dates, percentages, caps and whatever little conditional sentence is trying to run payroll from the shadows.");
  await ensureOverviewUpliftSuggestion(aeId);
  if (!acceptedUpliftRuleCount()) {
    await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/accept`, { method: "POST", body: JSON.stringify({}) });
    await loadCouncilContext(aeId, "uplift_rules");
  }
  const count = acceptedUpliftRuleCount();
  if (!count) throw new Error("No uplift rules were available to accept.");
  addSyntheticHumanComment(aeId, `I have ${count} accepted uplift rule date${count === 1 ? "" : "s"} to anchor scenario testing. These are the rails; crooked rails make expensive little trains.`);
  const alignmentIssues = currentUpliftTableAlignmentIssues();
  if (alignmentIssues.length) {
    requestSyntheticRuleBindingImprovement(aeId, alignmentIssues, "uplift_rules");
  }
  setOverviewPreparationJob(aeId, "uplift", "done", `Accepted ${count} uplift rule${count === 1 ? "" : "s"} for scenario testing`);
  addSyntheticHumanDecision(aeId, `Accepted ${count} uplift rule${count === 1 ? "" : "s"} as the governed rule basis.`);
  await saveSyntheticSectionHumanQa(aeId, "uplift_rules", [`Accepted ${count} uplift rule${count === 1 ? "" : "s"} for scenario testing.`]);
  setSyntheticHumanJob(aeId, "uplift_rules", "done", `Accepted ${count} uplift rule${count === 1 ? "" : "s"}`);
}

async function runSyntheticHumanPayTables(aeId) {
  setSyntheticHumanJob(aeId, "pay_tables", "running", "Reviewing source coverage, cohorts and duplicate tables");
  addSyntheticHumanComment(aeId, "Pay-table QA is where the agreement hides numbers in the furniture. I am checking source coverage, duplicate dates, rate kinds and whether a table is general benchmark or specialised side quest.");
  if (!state.payDraft.tables.length) {
    await runOverviewPayExtractionPreview(aeId);
  }
  const extractedCount = syntheticExtractedPayTables().length;
  if (extractedCount) {
    addSyntheticHumanComment(aeId, `Extraction surfaced ${extractedCount} usable pay-table candidate${extractedCount === 1 ? "" : "s"}. Now I am deciding which ones are evidence and which ones are decorative confusion.`);
  }
  const adopted = adoptSyntheticExtractedPayTables();
  if (!state.payDraft.tables.length) {
    throw new Error("No pay tables could be accepted synthetically. Open Pay Tables to choose the correct source pages.");
  }
  addSyntheticHumanComment(
    aeId,
    adopted
      ? `Adopted ${adopted} extracted table${adopted === 1 ? "" : "s"} into the draft. The numbers are in the room; now they have to show ID.`
      : `Reusing ${state.payDraft.tables.length} existing draft table${state.payDraft.tables.length === 1 ? "" : "s"}. No victory parade yet; existing numbers can still wear fake moustaches.`,
  );
  const cohortResolution = resolveSyntheticPayTableCohorts();
  if (cohortResolution.blockers.length) {
    addSyntheticHumanComment(aeId, `Serious stop: ${cohortResolution.blockers.length} cohort blocker${cohortResolution.blockers.length === 1 ? "" : "s"} remain. I cannot safely infer the governing cohort from the extracted labels.`);
    throw new Error(cohortResolution.blockers[0]);
  }
  if (cohortResolution.decisions.length) {
    addSyntheticHumanComment(aeId, `Cohort QA made ${cohortResolution.decisions.length} selection call${cohortResolution.decisions.length === 1 ? "" : "s"}: keeping the general benchmark signal and sweeping duplicate/specialised furniture out of the walkway.`);
  }
  let ruleSnapDecisions = applySyntheticRuleAnchoredDatesToDraftTables();
  let snappedCohortResolution = { decisions: [], blockers: [] };
  if (ruleSnapDecisions.length) {
    addSyntheticHumanComment(aeId, `Rule-date snap made ${ruleSnapDecisions.length} timing call${ruleSnapDecisions.length === 1 ? "" : "s"}. I am checking duplicates again because chronology likes to move the chairs after you sit down.`);
    ruleSnapDecisions.forEach((decision) => addSyntheticHumanDecision(aeId, decision));
    snappedCohortResolution = resolveSyntheticPayTableCohorts();
    if (snappedCohortResolution.blockers.length) {
      addSyntheticHumanComment(aeId, "Serious stop: the rule-anchored dates created a duplicate pay-table group that still needs cohort selection.");
      throw new Error(snappedCohortResolution.blockers[0]);
    }
    if (snappedCohortResolution.decisions.length) {
      addSyntheticHumanComment(aeId, `Post-snap cohort QA cleaned up ${snappedCohortResolution.decisions.length} duplicate table call${snappedCohortResolution.decisions.length === 1 ? "" : "s"}. The calendar tried a trick; noted.`);
    }
    snappedCohortResolution.decisions.forEach((decision) => addSyntheticHumanDecision(aeId, decision));
  }
  cohortResolution.decisions.forEach((decision) => addSyntheticHumanDecision(aeId, decision));
  const result = await saveSyntheticPayTables(aeId, adopted);
  const blockers = blockingPayValidations(result.validations);
  if (blockers.length) {
    addSyntheticHumanComment(aeId, `Serious stop: pay tables saved, but validation still found ${blockers.length} blocker${blockers.length === 1 ? "" : "s"}. I am stopping before scenario calculations compound the issue.`);
    throw new Error(`${blockers.length} pay-table validation blocker${blockers.length === 1 ? "" : "s"} remained after save.`);
  }
  const tables = state.currentCouncil?.sections?.pay_tables?.tables || [];
  addSyntheticHumanComment(aeId, `Saved ${tables.length} governed pay table${tables.length === 1 ? "" : "s"} with no blocking validations. The numbers have stopped crawling around the ceiling.`);
  setOverviewPreparationJob(aeId, "pay", "done", `Saved ${tables.length} pay table${tables.length === 1 ? "" : "s"} for scenario testing`);
  addSyntheticHumanDecision(
    aeId,
    adopted
      ? `Adopted ${adopted} extracted pay-table candidate${adopted === 1 ? "" : "s"} into the accepted pay-table draft.`
      : `Re-used the existing ${tables.length} accepted pay table${tables.length === 1 ? "" : "s"} without material changes.`,
  );
  const qaLines = [
    `Saved ${tables.length} pay table${tables.length === 1 ? "" : "s"} with no blocking validation errors.`,
    cohortResolution.changed ? "Checked duplicate pay-table dates by cohort and retained the general benchmark table set." : "",
  ].filter(Boolean);
  await saveSyntheticSectionHumanQa(aeId, "pay_tables", qaLines);
  setSyntheticHumanJob(aeId, "pay_tables", "done", `Saved ${tables.length} pay table${tables.length === 1 ? "" : "s"}`);
  const alignmentIssues = currentUpliftTableAlignmentIssues();
  if (alignmentIssues.length) {
    requestSyntheticRuleBindingImprovement(aeId, alignmentIssues, "uplift_rules");
  }
  if (cohortResolution.decisions.length) {
    requestSyntheticSystemImprovement(aeId, {
      stage: "Pay QA cohort judgement",
      ruleKey: "pay_table_cohort_resolution",
      judgement: [...cohortResolution.decisions, ...ruleSnapDecisions, ...snappedCohortResolution.decisions].join(" "),
      request: "Turn this pay-table cohort selection, including post-snap duplicate resolution, into backend cohort-resolution policy before scenario processing continues.",
      resumeFrom: "scenarios",
    });
  } else if (ruleSnapDecisions.length || snappedCohortResolution.decisions.length) {
    requestSyntheticSystemImprovement(aeId, {
      stage: "Pay QA rule-anchored date normalisation",
      ruleKey: "pay_table_post_snap_cohort_resolution",
      judgement: [...ruleSnapDecisions, ...snappedCohortResolution.decisions].join(" "),
      request: "Run duplicate cohort QA after rule-anchored date snapping so save-time date alignment cannot reintroduce blockers.",
      resumeFrom: "scenarios",
    });
  }
}

async function runSyntheticHumanScenarios(aeId) {
  setSyntheticHumanJob(aeId, "scenarios", "running", "Comparing accepted tables against uplift rules");
  addSyntheticHumanComment(aeId, "Scenario QA is the argument room. Tables say one thing, rules say another, and I am here with a clipboard asking everyone to use evidence voices.");
  const initialResult = await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/scenarios`, {
    method: "POST",
    body: JSON.stringify({
      overrides: scenarioOverrides.get(aeId) || {},
      change_context: { scope: "synthetic_human", action: "run_scenarios" },
    }),
  });
  const extractionIssues = syntheticScenarioRuleExtractionIssues(initialResult);
  addSyntheticHumanComment(
    aeId,
    `Ran ${(initialResult.scenarios || []).length} scenario period${(initialResult.scenarios || []).length === 1 ? "" : "s"}; ${extractionIssues.length} upstream rule-binding issue${extractionIssues.length === 1 ? "" : "s"} surfaced before overrides.`,
  );
  if (extractionIssues.length) {
    requestSyntheticRuleBindingImprovement(aeId, extractionIssues, "uplift_rules");
  }
  const overridePass = await applySyntheticScenarioComputedOverrides(aeId, initialResult);
  const result = overridePass.result;
  const remainingExtractionIssues = syntheticScenarioRuleExtractionIssues(result);
  if (remainingExtractionIssues.length) {
    requestSyntheticRuleBindingImprovement(aeId, remainingExtractionIssues, "uplift_rules");
  }
  overridePass.decisions.forEach((decision) => addSyntheticHumanDecision(aeId, decision));
  if (overridePass.decisions.length) {
    addSyntheticHumanComment(aeId, `Computed-value QA made ${overridePass.decisions.length} override call${overridePass.decisions.length === 1 ? "" : "s"}. That is real judgement, not spreadsheet jazz, so I am asking the engine to learn it.`);
    requestSyntheticSystemImprovement(aeId, {
      stage: "Scenario QA computed-value judgement",
      ruleKey: "scenario_computed_override_policy",
      judgement: overridePass.decisions.join(" "),
      request: "Bake this computed-value override decision into the scenario engine before governed promotion continues.",
      resumeFrom: "scenarios",
    });
  }
  const promotions = await promoteSyntheticGovernedAssets(aeId, result);
  addSyntheticHumanComment(
    aeId,
    promotions.length
      ? `Promotion pass moved ${promotions.length} governed asset${promotions.length === 1 ? "" : "s"} into the reusable set. The evidence has keys now.`
      : "Promotion pass found nothing new to move. Weirdly satisfying: sometimes the correct output is a clean shrug.",
  );
  addSyntheticHumanDecision(
    aeId,
    promotions.length
      ? `Promoted ${promotions.length} governed asset${promotions.length === 1 ? "" : "s"} after scenario checks aligned.`
      : "Scenario checks were unremarkable; no additional governed promotion was needed.",
  );
  setOverviewPreparationJob(
    aeId,
    "scenarios",
    "done",
    `Scenario checks completed by automated reviewer; ${promotions.length} governed asset${promotions.length === 1 ? "" : "s"} promoted`,
  );
  await saveSyntheticSectionHumanQa(aeId, "scenarios", [
    `Ran ${formatCount((result.scenarios || []).length, "0")} scenario period${(result.scenarios || []).length === 1 ? "" : "s"}.`,
    promotions.length ? `Promoted ${promotions.join(", ")}.` : "No additional governed promotions were needed.",
  ]);
  setSyntheticHumanJob(aeId, "scenarios", "done", promotions.length ? `Promoted ${promotions.length} governed asset${promotions.length === 1 ? "" : "s"}` : "Scenario checks accepted");
}

async function runSyntheticHumanEndOfBandDollars(aeId) {
  setSyntheticHumanJob(aeId, "end_of_band_dollars", "running", "Resolving cash end-of-band rows");
  addSyntheticHumanComment(aeId, "End-of-band check: I am looking for current cash amounts and projecting only those dollars onto governed operative periods and bands.");
  await loadCouncilContext(aeId, "end_of_band_dollars");
  const data = await loadEndOfBandDollarsData({ force: true });
  const rows = currentAgreementEndOfBandRows(data);
  const status = currentAgreementEndOfBandStatus(data);
  syncEndOfBandSectionData(rows, status);
  const periodCount = new Set(rows.map((row) => row.effective_from).filter(Boolean)).size;
  const bandCount = new Set(rows.map((row) => row.band).filter(Boolean)).size;
  addSyntheticHumanComment(
    aeId,
    rows.length
      ? `Resolved ${rows.length} end-of-band cash row${rows.length === 1 ? "" : "s"} across ${periodCount} operative period${periodCount === 1 ? "" : "s"} and ${bandCount} band${bandCount === 1 ? "" : "s"}.`
      : "No current non-grandfathered cash end-of-band rows resolved for this agreement.",
  );
  await saveSyntheticSectionHumanQa(aeId, "end_of_band_dollars", [
    rows.length
      ? `Reviewed ${rows.length} derived end-of-band cash row${rows.length === 1 ? "" : "s"} with clause evidence.`
      : "Accepted the no-current-cash-end-of-band finding.",
  ]);
  setSyntheticHumanJob(
    aeId,
    "end_of_band_dollars",
    "done",
    rows.length ? `${rows.length} EOB cash row${rows.length === 1 ? "" : "s"} accepted` : "No EOB cash rows",
  );
}

async function runSyntheticHumanGovernedSet(aeId) {
  setSyntheticHumanJob(aeId, "uplifts", "running", "Checking promoted governed periods");
  addSyntheticHumanComment(aeId, "Governed set check: I am making sure the accepted evidence actually became reusable analysis assets, not just a very tidy pile of good intentions.");
  const governedResult = await api(`/api/councils/${encodeURIComponent(aeId)}/governed-set`);
  const periods = governedResult?.governed?.periods || [];
  const promotedPeriods = periods.filter((period) => period?.pay_table || period?.uplift_rule);
  if (!promotedPeriods.length) throw new Error("No governed periods were promoted.");
  addSyntheticHumanComment(aeId, `Found ${promotedPeriods.length} promoted governed period${promotedPeriods.length === 1 ? "" : "s"} from ${periods.length} period record${periods.length === 1 ? "" : "s"}. This is the part where the pipeline either has a floor or politely reveals a trapdoor.`);
  addSyntheticHumanDecision(aeId, `Accepted ${promotedPeriods.length} governed period${promotedPeriods.length === 1 ? "" : "s"} as ready for analysis outputs.`);
  await saveSyntheticSectionHumanQa(aeId, "uplifts", [`Accepted ${promotedPeriods.length} governed period${promotedPeriods.length === 1 ? "" : "s"} for analysis outputs.`]);
  setSyntheticHumanJob(aeId, "uplifts", "done", `Accepted ${promotedPeriods.length} governed period${promotedPeriods.length === 1 ? "" : "s"}`);
}

async function runSyntheticHumanLearning(aeId) {
  const run = syntheticHumanReviewState(aeId);
  setSyntheticHumanJob(aeId, "learning", "running", "Reading review-learning snapshot");
  addSyntheticHumanComment(aeId, "Learning pass: I am looking for repeated judgement patterns. If I made the same call twice, the system should probably stop asking me to perform the tiny ceremony.");
  const learning = await api("/api/analysis/review-learning");
  const suggestions = Array.isArray(learning?.policy_suggestions) ? learning.policy_suggestions : [];
  const promotions = Array.isArray(learning?.rule_promotions) ? learning.rule_promotions : [];
  const improvementLines = [
    ...suggestions.map((item) => item.message || item.rule).filter(Boolean),
    ...promotions.map((item) => item.message || item.rule).filter(Boolean),
  ];
  run.improvements = improvementLines.length ? [...new Set(improvementLines)] : ["No new policy suggestions were raised from the current review-learning snapshot."];
  addSyntheticHumanComment(aeId, `Learning found ${suggestions.length} policy suggestion${suggestions.length === 1 ? "" : "s"} and ${promotions.length} promotable rule${promotions.length === 1 ? "" : "s"}. ${improvementLines.length ? "There is reusable judgement here." : "No new ritual to automate today."}`);
  setSyntheticHumanJob(aeId, "learning", "done", `${suggestions.length} suggestion${suggestions.length === 1 ? "" : "s"}, ${promotions.length} promotable rule${promotions.length === 1 ? "" : "s"}`);
}

function syntheticHumanWorkflowSteps() {
  return [
    ["overview", runSyntheticHumanOverview],
    ["uplift_rules", runSyntheticHumanUpliftRules],
    ["pay_tables", runSyntheticHumanPayTables],
    ["scenarios", runSyntheticHumanScenarios],
    ["end_of_band_dollars", runSyntheticHumanEndOfBandDollars],
    ["uplifts", runSyntheticHumanGovernedSet],
    ["learning", runSyntheticHumanLearning],
  ];
}

function syntheticHumanStepMinimumMs(stepKey) {
  return {
    overview: 2600,
    uplift_rules: 2800,
    pay_tables: 3200,
    scenarios: 3000,
    end_of_band_dollars: 2400,
    uplifts: 2600,
    learning: 2400,
  }[stepKey] || 2400;
}

async function holdSyntheticHumanStepForImpact(stepKey, startedAt) {
  const elapsed = Date.now() - startedAt;
  const remaining = syntheticHumanStepMinimumMs(stepKey) - elapsed;
  if (remaining > 0) await delay(remaining);
}

async function runSyntheticHumanWorkflow(aeId, startFrom = "") {
  const steps = syntheticHumanWorkflowSteps();
  const startIndex = Math.max(0, steps.findIndex(([key]) => key === startFrom));
  for (const [stepKey, runner] of steps.slice(startIndex)) {
    const startedAt = Date.now();
    try {
      await runner(aeId);
    } finally {
      await holdSyntheticHumanStepForImpact(stepKey, startedAt);
    }
  }
}

function queueSyntheticHumanReview({ force = false, aeId = state.currentCouncil?.agreement_id } = {}) {
  if (!aeId) return;
  const run = syntheticHumanReviewState(aeId);
  if (run.running) return;
  let resumeFrom = "";
  if (run.awaitingSystemImprovement && !force) {
    resumeFrom = markSyntheticSystemImprovementsImplemented(run);
    addSyntheticHumanComment(aeId, `System improvement marked as implemented. I am resuming from ${SECTION_LABELS[resumeFrom] || resumeFrom || "the next review step"}; same hallway, better lighting.`);
  } else if (force) {
    resetSyntheticHumanReview(run);
  }
  run.running = true;
  run.completed = false;
  run.startedAt = new Date().toISOString();
  if (!resumeFrom) addSyntheticHumanComment(aeId, "Fresh automated reviewer pass. I will narrate the evidence as it changes shape, and I will stop if a judgement belongs in the engine instead of in my tiny mental clipboard.");
  renderSyntheticHumanSurfaces(aeId);
  (async () => {
    try {
      await ensureOverviewPreparationCouncil(aeId);
      await runSyntheticHumanWorkflow(aeId, resumeFrom);
      await fetchCouncils().catch(() => {});
      run.completed = true;
      toast("Automated review completed", "success");
    } catch (error) {
      const message = apiErrorMessage(error);
      if (isSyntheticSystemImprovementPause(error)) {
        toast("Automated review paused for system improvement", "warning");
      } else {
        Object.entries(run.jobs || {}).forEach(([key, job]) => {
          if (job.status === "running") {
            setSyntheticHumanJob(aeId, key, "failed", message);
          } else if (job.status === "queued") {
            setSyntheticHumanJob(aeId, key, "queued", "Waiting for earlier review steps");
          }
        });
        toast(`Automated review stopped: ${message}`, "error");
      }
      await fetchCouncils().catch(() => {});
    } finally {
      run.running = false;
      run.finishedAt = new Date().toISOString();
      renderSyntheticHumanSurfaces(aeId);
    }
  })();
}

function renderTableHtml(table) {
  const RATE_FIELDS = ["weekly_rate", "fortnightly_rate", "annual_rate", "hourly_rate"];
  const RATE_LABELS = {
    weekly_rate: "Weekly",
    fortnightly_rate: "Fortnightly",
    annual_rate: "Annual",
    hourly_rate: "Hourly",
  };

  const rows = table.rows || [];
  const activeRateCols = RATE_FIELDS.filter((field) => rows.some((row) => row[field] != null));

  const effectiveFromField = (() => {
    if (table.effective_from) return { label: "Effective from", value: displayDate(table.effective_from) };
    if (table.effective_from_note) return { label: "Effective from (date TBD)", value: table.effective_from_note };
    return { label: "Effective from", value: null };
  })();
  const metaFields = [
    { label: "Title", value: table.table_title },
    { label: "Clause", value: table.source_clause },
    table.source_pages != null
      ? { label: "Pages", value: displayPages(table.source_pages) }
      : { label: "Page", value: displayPages(table.source_page) },
    effectiveFromField,
    { label: "To date", value: displayDate(table.to_date) },
  ];

  const headerHtml = `<div class="extract-preview-header">${metaFields.map((f) => `<span><span class="muted">${f.label}:</span> <strong>${htmlDisplay(f.value)}</strong></span>`).join("")}</div>`;

  const prov = table.provenance || null;
  let provHtml = "";
  if (prov) {
    const lga = prov.canonical_lga_short_name || prov.lga_short_name;
    const govFields = [
      ["Agreement ID", prov.agreement_id],
      ["LGA", lga],
      ["LGA Code", prov.lga_code],
      ["Matter", prov.matter_number],
      ["Print ID", prov.print_id],
      ["Expiry", displayDate(prov.expiry_date)],
      ["Version", prov.version],
      ["Superseded by", prov.superseded_by_ae_id],
    ].filter(([, v]) => v !== null && v !== undefined && v !== "");
    const qaFields = [
      ["Scope", normaliseScopeStatus(prov.scope_resolution_status)],
      ["Lineage", prov.lineage_key],
    ].filter(([, v]) => v !== null && v !== undefined && v !== "");
    const renderFields = (fields) => `<div class="extract-preview-header" style="font-size:0.85em;margin-top:0.25rem;">${fields.map(([label, value]) => `<span><span class="muted">${escapeHtml(label)}:</span> <strong>${htmlDisplay(value)}</strong></span>`).join("")}</div>`;
    const blocks = [];
    if (govFields.length > 0) {
      blocks.push(`<details class="extract-preview-provenance"><summary class="muted" style="cursor:pointer;font-size:0.85em;">Governance (${govFields.length})</summary>${renderFields(govFields)}</details>`);
    }
    if (qaFields.length > 0) {
      blocks.push(`<details class="extract-preview-provenance"><summary class="muted" style="cursor:pointer;font-size:0.85em;">Pipeline QA (${qaFields.length})</summary>${renderFields(qaFields)}</details>`);
    }
    provHtml = blocks.join("");
  }

  const theadCols = ["Band", "Level", "Title", ...activeRateCols.map((f) => RATE_LABELS[f])];
  const theadHtml = `<thead><tr>${theadCols.map((c) => `<th>${c}</th>`).join("")}</tr></thead>`;

  const tbodyHtml = `<tbody>${rows.map((row) => {
    const cells = [
      escapeHtml(row.band ?? ""),
      escapeHtml(row.level ?? ""),
      escapeHtml(row.title ?? ""),
      ...activeRateCols.map((f) => displayCurrency(row[f])),
    ];
    return `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
  }).join("")}</tbody>`;

  const captionHtml = `<caption>${rows.length} row${rows.length !== 1 ? "s" : ""}</caption>`;

  return `${headerHtml}${provHtml}<table class="extract-preview-table">${captionHtml}${theadHtml}${tbodyHtml}</table>`;
}

function renderValidations(validations) {
  if (!validations?.length) return '<div class="quality-empty muted">No quality issues found.</div>';
  return `<div class="validation-list">${validations.map((item) => `
    <div class="quality-check-item workbench-card-scaffold val-card-${item.level}">
      <div class="quality-check-head"><span class="validation-pill val-${item.level}">${item.level}</span> <strong>${item.code}</strong></div>
      <div class="quality-check-message">${item.message}</div>
      <div class="muted">table ${item.table_idx}${item.row_idx !== null && item.row_idx !== undefined ? `, row ${item.row_idx}` : ""}</div>
    </div>
  `).join("")}</div>`;
}

function renderReviewHints(hints, options = {}) {
  const items = Array.isArray(hints) ? hints : [];
  const empty = options.empty || "No review hints yet.";
  if (!items.length) {
    return `<div class="review-hints-empty quality-empty muted">${escapeHtml(empty)}</div>`;
  }
  return `<div class="review-hint-list">${items.map((hint) => {
    const severity = hint.severity || "info";
    const confidence = hint.confidence ? `Confidence: ${hint.confidence}` : "";
    const evidence = Array.isArray(hint.evidence) ? hint.evidence.filter(Boolean) : [];
    const evidenceHtml = evidence.length
      ? `<ul class="review-hint-evidence">${evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
      : "";
    const noteHtml = hint.save_note
      ? `<div class="review-hint-note"><span>Save reason</span>${escapeHtml(hint.save_note)}</div>`
      : "";
    const appendButton = options.appendNotes && hint.save_note
      ? `<button class="append-review-note" data-hint-id="${escapeHtml(hint.id || "")}">Append reason to notes</button>`
      : "";
    return `
      <div class="review-hint review-hint-${escapeHtml(severity)}">
        <div class="review-hint-head">
          <span class="review-hint-severity">${escapeHtml(severity.replaceAll("_", " "))}</span>
          <strong>${escapeHtml(hint.title || hint.code || "Review hint")}</strong>
          ${confidence ? `<small>${escapeHtml(confidence)}</small>` : ""}
        </div>
        <p>${escapeHtml(hint.message || "")}</p>
        ${hint.recommendation ? `<p><strong>Next:</strong> ${escapeHtml(hint.recommendation)}</p>` : ""}
        ${evidenceHtml}
        ${noteHtml}
        ${appendButton}
      </div>
    `;
  }).join("")}</div>`;
}

function appendPayReviewHintNote(hintId) {
  const hint = (state.payDraft.reviewHints || []).find((item) => item.id === hintId);
  if (!hint?.save_note) return;
  const textarea = document.getElementById("pay-notes");
  if (textarea) state.payDraft.notes = textarea.value;
  const noteLine = `[${new Date().toISOString().slice(0, 10)}] ${hint.save_note}`;
  const current = (state.payDraft.notes || "").trim();
  if (current.includes(hint.save_note)) {
    toast("Review reason is already in the notes", "info");
    return;
  }
  state.payDraft.notes = current ? `${current}\n${noteLine}` : noteLine;
  if (textarea) textarea.value = state.payDraft.notes;
  toast("Review reason appended to notes", "success");
}

function formatQaEventTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return String(iso);
  }
}

function qaEventTitle(event) {
  const labels = {
    pay_table_added: "Table added",
    pay_table_removed: "Table removed",
    pay_table_date_changed: "Effective date changed",
    pay_table_cell_value_changed: "Pay rate changed",
    pay_table_note_updated: "Reviewer note updated",
    pay_table_source_ref_updated: "Source reference updated",
    pay_table_row_added: "Row added",
    pay_table_row_removed: "Row removed",
    scenario_cell_override_added: "Scenario decision saved",
    scenario_cell_override_changed: "Scenario decision changed",
    scenario_cell_override_removed: "Scenario decision removed",
    scenario_group_override_applied: "Scenario group decision saved",
    scenario_note_updated: "Scenario note updated",
    scenario_overrides_cleared: "Scenario decisions cleared",
  };
  return labels[event?.event_type] || String(event?.event_type || "QA change").replaceAll("_", " ");
}

function qaDisplayValue(value) {
  if (value === null || value === undefined || value === "") return "blank";
  if (typeof value === "object") {
    if (value.action && value.weekly !== undefined) return `${value.action} ${value.weekly}`;
    if (value.action) return value.action;
    return JSON.stringify(value);
  }
  return String(value);
}

function qaEventDetail(event) {
  const pieces = [];
  if (event.period_effective_from) pieces.push(event.period_effective_from);
  if (event.table_label) pieces.push(event.table_label);
  if (event.cell_key) pieces.push(event.cell_key);
  if (event.row_key) pieces.push(event.row_key);
  if (event.field) pieces.push(event.field);
  if (event.action) pieces.push(String(event.action).replaceAll("_", " "));
  if (event.affected_count !== undefined) pieces.push(`${event.affected_count} cell${Number(event.affected_count) === 1 ? "" : "s"}`);
  if (event.previous !== undefined || event.next !== undefined) {
    pieces.push(`${qaDisplayValue(event.previous)} to ${qaDisplayValue(event.next)}`);
  }
  if (event.previous_length !== undefined || event.next_length !== undefined) {
    pieces.push(`note length ${event.previous_length || 0} to ${event.next_length || 0} characters`);
  }
  return pieces.join(", ");
}

function renderQaGovernanceEvents(events, options = {}) {
  const recent = (Array.isArray(events) ? events : []).slice(-(options.limit || 8)).reverse();
  const idAttr = options.id ? ` id="${escapeHtml(options.id)}"` : "";
  if (!recent.length) {
    return `<div${idAttr} class="qa-change-log"><div class="quality-empty muted">${escapeHtml(options.empty || "No reviewer changes recorded yet.")}</div></div>`;
  }
  return `<div${idAttr} class="qa-change-log">${recent.map((event) => `
    <div class="qa-change-item">
      <time>${escapeHtml(formatQaEventTime(event.changed_at))}</time>
      <div>
        <strong>${escapeHtml(qaEventTitle(event))}</strong>
        <p>${escapeHtml(qaEventDetail(event))}</p>
      </div>
    </div>
  `).join("")}</div>`;
}

function setScenarioAuditEvents(events) {
  _scenarioAuditEvents = Array.isArray(events) ? events : [];
  const log = document.getElementById("scenario-qa-change-log");
  if (log) {
    log.outerHTML = renderQaGovernanceEvents(_scenarioAuditEvents, {
      id: "scenario-qa-change-log",
      empty: "No scenario review changes recorded yet.",
    });
  }
}

// Like renderTableHtml but adds a per-row ? delete button for use in the draft editor.
function renderDraftTableHtml(table, tableIndex) {
  const RATE_FIELDS = ["weekly_rate", "fortnightly_rate", "annual_rate", "hourly_rate"];
  const RATE_LABELS = { weekly_rate: "Weekly", fortnightly_rate: "Fortnightly", annual_rate: "Annual", hourly_rate: "Hourly" };

  const rows = table.rows || [];
  const activeRateCols = RATE_FIELDS.filter((field) => rows.some((row) => row[field] != null));
  const effectiveFromDisplay = table.effective_from
    ? escapeHtml(displayDate(table.effective_from))
    : (table.effective_from_note ? `<em>${escapeHtml(table.effective_from_note)}</em>` : DISPLAY_EMPTY);
  const toDateDisplay = escapeHtml(displayDate(table.to_date));
  const metaHtml = `<div class="draft-table-meta"><span><span class="muted">Effective from:</span> <strong>${effectiveFromDisplay}</strong></span><span><span class="muted">To:</span> <strong>${toDateDisplay}</strong></span>${table.rate_kind ? `<span><span class="muted">Rate kind:</span> <strong>${escapeHtml(table.rate_kind)}</strong></span>` : ""}</div>`;
  const theadCols = ["Band", "Level", "Title", ...activeRateCols.map((f) => RATE_LABELS[f]), ""];
  const theadHtml = `<thead><tr>${theadCols.map((c) => `<th>${c}</th>`).join("")}</tr></thead>`;
  const tbodyHtml = `<tbody>${rows.map((row, rowIndex) => {
    const cells = [
      escapeHtml(row.band ?? ""),
      escapeHtml(row.level ?? ""),
      escapeHtml(row.title ?? ""),
      ...activeRateCols.map((f) => displayCurrency(row[f])),
      `<button class="delete-table-row" data-table-index="${tableIndex}" data-row-index="${rowIndex}" title="Remove row">Remove</button>`,
    ];
    return `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
  }).join("")}</tbody>`;
  const captionHtml = `<caption>${rows.length} row${rows.length !== 1 ? "s" : ""}</caption>`;
  return `${metaHtml}<table class="extract-preview-table">${captionHtml}${theadHtml}${tbodyHtml}</table>`;
}

function renderPayTablesPane() {
  const pane = document.getElementById("section-pane");
  const llm = state.llmStatus;
  const visionReady = Boolean(llm?.ready && llm?.vision_capable);
  const llmBanner = llm && !visionReady
    ? `<div class="overview-warning"><strong>Vision extraction unavailable:</strong> ${escapeHtml(llm.message || "Configure a vision-capable LLM provider.")}</div>`
    : "";
  const payQaEvents = state.currentCouncil?.sections?.pay_tables?.qa_events || [];

  let rangePreviewHtml = "";
  const r = state.payDraft.rangeExtraction;
  if (r) {
    const rangePages = displayPages([r.range.start, r.range.end]);
    rangePreviewHtml = `
      <div class="card pay-card pay-range-card" id="range-preview-card">
        <h3>Range extraction preview (${escapeHtml(rangePages)}, ${r.tables.length} tables)</h3>
        ${r.tables.length === 0 ? '<div class="muted">No tables detected in this range.</div>' : ""}
        ${r.tables.map((t, i) => `
          <div class="range-preview-entry" data-index="${i}">
            ${renderTableHtml(t)}
            <div class="toolbar range-preview-actions">
              <button class="range-accept" data-index="${i}" ${r.accepted.has(i) ? "disabled" : ""}>${r.accepted.has(i) ? "Added ?" : "Add to draft"}</button>
              <button class="range-reject" data-index="${i}">Reject</button>
            </div>
          </div>
        `).join("")}
        <details class="extract-preview-raw"><summary>View raw response</summary><pre>${escapeHtml(r.raw || "")}</pre></details>
      </div>
    `;
  }

  const actionsHtml = `
    <button id="pay-find-candidates">Find pages</button>
    <button id="pay-extract-current" class="primary">Extract page</button>
    <input type="number" id="pay-range-start" placeholder="Start page" value="${state.payDraft.rangeStart ?? ""}">
    <input type="number" id="pay-range-end" placeholder="End page" value="${state.payDraft.rangeEnd ?? ""}">
    <button id="pay-extract-range">Extract range</button>
    <button id="pay-suggest-dates">Suggest dates</button>
    <button id="pay-review-hints">Hints</button>
    <button id="pay-validate">Validate</button>
  `;
  const finalActionHtml = renderSectionFinalAction({
    eyebrow: "Pay table acceptance",
    title: "Draft evidence ready",
    detail: "Save the reviewed pay tables and mark this section complete.",
    buttonId: "pay-save",
    buttonClass: "pay-save-accept",
  });

  setWorkspaceModuleHeader("pay_tables");
  pane.innerHTML = `
    ${llmBanner}
    ${renderSectionActionBar(actionsHtml, finalActionHtml)}
    <div class="grid-two pay-evidence-grid">
      <div class="pay-evidence-source">
        <div class="card pay-card pay-candidates-card">
          <h3>Candidate pages</h3>
          ${renderPayCandidatePageGroups()}
        </div>
        ${rangePreviewHtml}
        <div class="card pay-card pay-acceptance-card">
          <h3>Acceptance Notes</h3>
          <label class="stack-sm">Source ref
            <input id="pay-source-ref" value="${escapeHtml(state.payDraft.sourceRef)}" placeholder="e.g. Appendix 2 pp. 42-45">
          </label>
          <label class="stack-sm" style="margin-top:0.75rem;">Notes
            <textarea id="pay-notes" placeholder="Working notes">${escapeHtml(state.payDraft.notes)}</textarea>
          </label>
        </div>
      </div>
      <div class="pay-evidence-review">
        <div class="card pay-card pay-draft-card">
          <h3>Draft Pay Table Evidence (${state.payDraft.tables.length})</h3>
          <div class="table-list">
            ${state.payDraft.tables.length ? state.payDraft.tables.map((table, index) => {
              const editing = state.payDraft.editingJsonIndex.has(index);
              const bodyHtml = editing
                ? `<textarea class="table-json" data-index="${index}">${escapeHtml(JSON.stringify(table, null, 2))}</textarea>`
                : `<div class="draft-table-view">${renderDraftTableHtml(table, index)}</div>`;
              return `
                <div class="table-card pay-table-card">
                  <div class="toolbar">
                    <strong>Table ${index + 1}: ${escapeHtml(table.table_title || "Untitled")}</strong>
                    <div class="toolbar-right">
                      <button class="toggle-json" data-index="${index}">${editing ? "View as table" : "Edit JSON"}</button>
                      <button class="remove-table" data-index="${index}">Remove</button>
                    </div>
                  </div>
                  ${bodyHtml}
                </div>
              `;
            }).join("") : '<div class="muted">No draft tables yet.</div>'}
          </div>
        </div>
        <div class="card pay-card pay-quality-card">
          <h3>Quality Checks</h3>
          <div id="validation-panel">${renderValidations(state.payDraft.validations)}</div>
          <div class="qa-change-log-block">
            <h4>Reviewer Change Log</h4>
            ${renderQaGovernanceEvents(payQaEvents, { empty: "No pay-table review changes recorded yet." })}
          </div>
        </div>
        <div class="card pay-card pay-review-hints-card">
          <h3>Review Hints</h3>
          <div id="pay-review-hints-panel">${renderReviewHints(state.payDraft.reviewHints, {
            empty: "Run review hints after extraction or date suggestions.",
            appendNotes: true,
          })}</div>
        </div>
      </div>
    </div>
  `;

  document.getElementById("pay-find-candidates")?.addEventListener("click", findPayTableCandidates);
  document.getElementById("pay-extract-current")?.addEventListener("click", extractPayTableCurrentPage);
  document.getElementById("pay-extract-range")?.addEventListener("click", extractPayTableRange);
  document.getElementById("pay-suggest-dates")?.addEventListener("click", suggestEffectiveDatesRemote);
  document.getElementById("pay-review-hints")?.addEventListener("click", () => loadPayReviewHints());
  document.getElementById("pay-validate")?.addEventListener("click", validatePayTablesRemote);
  document.getElementById("pay-save")?.addEventListener("click", () => savePayTables());
  pane.querySelectorAll(".append-review-note").forEach((button) => {
    button.addEventListener("click", () => appendPayReviewHintNote(button.dataset.hintId || ""));
  });
  pane.querySelectorAll(".candidate-page").forEach((button) => {
    button.addEventListener("click", () => {
      const page = Number(button.dataset.page);
      if (button.dataset.evidenceKind === "pay" && state.payDraft.rangeStart === null) {
        state.payDraft.rangeStart = page;
      }
      if (button.dataset.evidenceKind === "pay" && state.payDraft.rangeEnd === null) {
        state.payDraft.rangeEnd = (state.payDraft.rangeStart ?? page) + 3;
      }
      state.pdfViewer.goTo(page);
    });
  });
  pane.querySelectorAll(".toggle-json").forEach((button) => {
    button.addEventListener("click", () => {
      const idx = Number(button.dataset.index);
      if (state.payDraft.editingJsonIndex.has(idx)) {
        state.payDraft.editingJsonIndex.delete(idx);
      } else {
        state.payDraft.editingJsonIndex.add(idx);
      }
      renderSectionPane();
    });
  });
  pane.querySelectorAll(".delete-table-row").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tIdx = Number(btn.dataset.tableIndex);
      const rIdx = Number(btn.dataset.rowIndex);
      state.payDraft.tables[tIdx].rows.splice(rIdx, 1);
      renderSectionPane();
      loadPayReviewHints({ silent: true }).catch(() => {});
    });
  });
  pane.querySelectorAll(".remove-table").forEach((button) => {
    button.addEventListener("click", () => {
      const removedIdx = Number(button.dataset.index);
      state.payDraft.tables.splice(removedIdx, 1);
      const newEditing = new Set();
      state.payDraft.editingJsonIndex.forEach((i) => {
        if (i < removedIdx) newEditing.add(i);
        else if (i > removedIdx) newEditing.add(i - 1);
      });
      state.payDraft.editingJsonIndex = newEditing;
      applyToDateRecalc();
      renderSectionPane();
      loadPayReviewHints({ silent: true }).catch(() => {});
    });
  });
  pane.querySelectorAll(".table-json").forEach((textarea) => {
    textarea.addEventListener("change", () => {
      try {
        state.payDraft.tables[Number(textarea.dataset.index)] = JSON.parse(textarea.value);
        applyToDateRecalc();
        renderSectionPane();
        loadPayReviewHints({ silent: true }).catch(() => {});
      } catch (error) {
        toast(`Invalid table JSON: ${error.message}`, "error");
      }
    });
  });
  pane.querySelectorAll(".range-accept").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = Number(btn.dataset.index);
      const r = state.payDraft.rangeExtraction;
      if (!r || r.accepted.has(i)) return;
      state.payDraft.tables.push(r.tables[i]);
      r.accepted.add(i);
      applyToDateRecalc();
      renderSectionPane();
      loadPayReviewHints({ silent: true }).catch(() => {});
      toast("Added to draft", "success");
    });
  });
  pane.querySelectorAll(".range-reject").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = Number(btn.dataset.index);
      const r = state.payDraft.rangeExtraction;
      if (!r) return;
      r.tables.splice(i, 1);
      const newAccepted = new Set();
      r.accepted.forEach((idx) => { if (idx < i) newAccepted.add(idx); else if (idx > i) newAccepted.add(idx - 1); });
      r.accepted = newAccepted;
      renderSectionPane();
      loadPayReviewHints({ silent: true }).catch(() => {});
    });
  });
}

function renderStubPane() {
  const section = state.currentSection;
  const data = state.currentCouncil.sections[section];
  const pane = document.getElementById("section-pane");
  const finalActionHtml = renderSectionFinalAction({
    eyebrow: "Section acceptance",
    title: "Status ready",
    detail: "Save the selected section status.",
    buttonId: "stub-save",
  });
  setWorkspaceModuleHeader(section);
  pane.innerHTML = `
    ${renderSectionActionBar("", finalActionHtml)}
    <div class="card">
      <p class="muted">Playbook not built yet. Status controls available.</p>
      <label class="stack-sm">Status
        <select id="stub-status">
          ${["not_started", "in_progress", "done", "flagged"].map((status) => `<option value="${status}" ${data.status === status ? "selected" : ""}>${status}</option>`).join("")}
        </select>
      </label>
    </div>
  `;
  document.getElementById("stub-save")?.addEventListener("click", async () => {
    const status = pane.querySelector("#stub-status").value;
    await api(`/api/councils/${state.currentCouncil.agreement_id}/sections/${section}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    await refreshCurrentCouncil(section);
    toast("Section status saved", "success");
  });
}

async function loadEndOfBandDollarsData({ force = false } = {}) {
  if (force) delete state.analysisDataByKind.end_of_band_dollars;
  if (!state.analysisDataByKind.end_of_band_dollars) {
    state.analysisDataByKind.end_of_band_dollars = await api("/api/analysis/end-of-band-dollars");
  }
  return state.analysisDataByKind.end_of_band_dollars;
}

function currentAgreementEndOfBandRows(data) {
  const aeId = state.currentCouncil?.agreement_id;
  if (!aeId) return [];
  return (data?.rows || []).filter((row) => row?.ae_id === aeId);
}

function currentAgreementEndOfBandStatus(data) {
  const aeId = state.currentCouncil?.agreement_id;
  return aeId ? (data?.agreement_statuses || {})[aeId] || null : null;
}

function syncEndOfBandSectionData(rows, status) {
  if (!state.currentCouncil) return;
  const sections = state.currentCouncil.sections || (state.currentCouncil.sections = {});
  const section = sections.end_of_band_dollars || (sections.end_of_band_dollars = {
    status: "not_started",
    completed_at: null,
    source_ref: "",
    data: null,
    notes: "",
  });
  section.data = {
    rows,
    status,
    summary: {
      row_count: rows.length,
      period_count: new Set(rows.map((row) => row.effective_from).filter(Boolean)).size,
      band_count: new Set(rows.map((row) => row.band).filter(Boolean)).size,
    },
  };
}

function renderEndOfBandRowsTable(rows) {
  if (!rows.length) {
    return '<div class="quality-empty muted">No current non-grandfathered cash end-of-band rows resolved for this agreement.</div>';
  }
  return `
    <table class="analysis-table">
      <thead>
        <tr>
          <th>Period</th>
          <th>Band</th>
          <th>EOB cash</th>
          <th>Basis</th>
          <th>Clause</th>
          <th>Page</th>
          <th>Extract</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${escapeHtml(displayDate(row.effective_from))}${row.to_date ? `<br><span class="muted">to ${escapeHtml(displayDate(row.to_date))}</span>` : ""}</td>
            <td>${escapeHtml(String(row.band || ""))}</td>
            <td><strong>${escapeHtml(displayCurrency(row.end_of_band_cash_amount))}</strong></td>
            <td>${escapeHtml(displayCodeLabel(row.amount_basis || row.calculation_status || ""))}</td>
            <td>${escapeHtml([row.clause_number, row.clause_heading].filter(Boolean).join(" ")) || DISPLAY_EMPTY}</td>
            <td>${escapeHtml(displayPages(row.source_page))}</td>
            <td class="analysis-clause-extract">${escapeHtml(row.clause_extract || "")}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderEndOfBandStatusSummary(rows, status) {
  const candidateCount = Number(status?.candidate_count || 0);
  const excludedCount = Number(status?.excluded_candidate_count || 0);
  const governedPeriods = Number(status?.governed_periods || 0);
  const sourceStatus = status?.source_text_status || (rows.length ? "in_scope_cash_candidate" : "not_checked");
  return `
    <div class="grid-two">
      <div class="card">
        <h3>Agreement Result</h3>
        <div class="stack-sm">
          <div><strong>Rows:</strong> ${escapeHtml(formatCount(rows.length, "0"))}</div>
          <div><strong>Governed periods checked:</strong> ${escapeHtml(formatCount(governedPeriods, "0"))}</div>
          <div><strong>Text candidates:</strong> ${escapeHtml(formatCount(candidateCount, "0"))}</div>
          <div><strong>Excluded candidates:</strong> ${escapeHtml(formatCount(excludedCount, "0"))}</div>
          <div><strong>Status:</strong> ${escapeHtml(displayCodeLabel(sourceStatus))}</div>
        </div>
      </div>
      <div class="card">
        <h3>Rule</h3>
        <p class="muted">This stage keeps only current, non-grandfathered cash end-of-band or top-of-band values. Leave, one-off bonuses, recognition programs, absorbed payments and historical cohorts are not projected as dollar rows.</p>
      </div>
    </div>
  `;
}

async function renderEndOfBandDollarsPane({ force = false } = {}) {
  const pane = document.getElementById("section-pane");
  setWorkspaceModuleHeader("end_of_band_dollars");
  pane.innerHTML = '<div class="card"><p class="muted">Loading end-of-band dollars...</p></div>';
  let data;
  try {
    data = await loadEndOfBandDollarsData({ force });
  } catch (error) {
    pane.innerHTML = `<div class="card"><p class="error">Failed to load: ${escapeHtml(error.message)}</p></div>`;
    return;
  }
  const rows = currentAgreementEndOfBandRows(data);
  const status = currentAgreementEndOfBandStatus(data);
  syncEndOfBandSectionData(rows, status);
  const finalActionHtml = renderSectionFinalAction({
    eyebrow: "End-of-band acceptance",
    title: rows.length ? "Band values ready" : "No cash EOB rows resolved",
    detail: rows.length
      ? "Review the derived cash values and clause evidence before accepting this stage."
      : "Accept the no-current-cash-EOB finding for this agreement.",
    buttonId: "end-of-band-save",
  });
  const actionsHtml = '<button id="end-of-band-refresh" type="button">Refresh</button>';
  pane.innerHTML = `
    ${renderSectionActionBar(actionsHtml, finalActionHtml)}
    ${renderEndOfBandStatusSummary(rows, status)}
    <div class="card">
      <h3>Band Values</h3>
      ${renderEndOfBandRowsTable(rows)}
    </div>
  `;
  document.getElementById("end-of-band-refresh")?.addEventListener("click", () => renderEndOfBandDollarsPane({ force: true }));
  document.getElementById("end-of-band-save")?.addEventListener("click", saveEndOfBandDollarsSection);
  syncSectionPaneQaMode();
}

async function saveEndOfBandDollarsSection() {
  await withBusyButton("end-of-band-save", "Saving...", async () => {
    await api(`/api/councils/${state.currentCouncil.agreement_id}/sections/end_of_band_dollars/status`, {
      method: "PATCH",
      body: JSON.stringify({ status: "done" }),
    });
    await refreshCurrentCouncil("end_of_band_dollars");
    toast("End-of-band dollars stage saved and accepted", "success");
  });
}

async function renderGovernedSetPane() {
  const pane = document.getElementById("section-pane");
  setWorkspaceModuleHeader("uplifts");
  pane.innerHTML = '<div class="card"><p class="muted">Loading...</p></div>';
  let governed;
  try {
    const result = await api(`/api/councils/${state.currentCouncil.agreement_id}/governed-set`);
    governed = result.governed || { periods: [] };
  } catch (error) {
    pane.innerHTML = `<div class="card"><p class="error">Failed to load: ${error.message}</p></div>`;
    return;
  }
  governed = governed || { periods: [] };
  const periods = governed.periods || [];
  const hasPromotedPeriods = periods.some((period) => period.pay_table || period.uplift_rule);
  const finalActionHtml = renderSectionFinalAction({
    eyebrow: "Governed set acceptance",
    title: hasPromotedPeriods ? "Governed output ready" : "Promotion required",
    detail: hasPromotedPeriods
      ? "Save the promoted governed set and mark this section complete."
      : "Promote at least one scenario period before accepting the governed set.",
    buttonId: "governed-save",
    buttonAttrs: hasPromotedPeriods ? "" : "disabled",
  });
  if (periods.length === 0) {
    pane.innerHTML = `
      ${renderSectionActionBar("", finalActionHtml)}
      <div class="card">
        <p class="muted">Nothing promoted yet. Visit the Scenarios section and use the Promote buttons once a period is validated.</p>
      </div>`;
    wireGovernedSetActions();
    syncSectionPaneQaMode();
    return;
  }
  const rows = periods.map(renderGovernedPeriod).join("");
  pane.innerHTML = `
    ${renderSectionActionBar("", finalActionHtml)}
    <div class="card">
      <p class="muted">Read-only. Promoted assets per operative period.</p>
      <div class="governed-periods">${rows}</div>
    </div>`;
  wireGovernedSetActions();
  syncSectionPaneQaMode();
}

function wireGovernedSetActions() {
  document.getElementById("governed-save")?.addEventListener("click", saveGovernedSet);
}

async function saveGovernedSet() {
  await withBusyButton("governed-save", "Saving...", async () => {
    try {
      await api(`/api/councils/${state.currentCouncil.agreement_id}/sections/uplifts/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: "done" }),
      });
      await refreshCurrentCouncil("uplifts");
      const status = state.currentCouncil?.sections?.uplifts?.status || state.currentCouncil?.section_statuses?.uplifts;
      if (status === "done") {
        toast("Governed set saved and accepted", "success");
      } else {
        toast("Governed set still needs remaining promotions before it can be accepted", "error");
      }
    } catch (error) {
      toast(`Save failed: ${error.message}`, "error");
    }
  });
}

function renderGovernedPeriod(period) {
  const effFrom = displayDate(period.effective_from);
  const tableBlock = period.pay_table
    ? `<div class="governed-asset governed-asset-pay-table">
         <strong>Pay table</strong>
         <span class="governed-at">governed ${escapeHtml(displayDate(period.pay_table_governed_at))}</span>
         <div class="muted">${(period.pay_table.rows || []).length} rows</div>
       </div>`
    : `<div class="governed-asset governed-asset-empty">Pay table: not governed</div>`;
  const rule = period.uplift_rule;
  const ruleBlock = rule
    ? `<div class="governed-asset governed-asset-uplift-rule">
         <strong>Uplift rule</strong>
         <span class="governed-at">governed ${escapeHtml(displayDate(period.uplift_rule_governed_at))}</span>
         ${renderGovernedRuleExpression(rule)}
       </div>`
    : `<div class="governed-asset governed-asset-empty">Uplift rule: not governed</div>`;
  return `
    <div class="governed-period">
      <h4>Period ${effFrom}</h4>
      ${tableBlock}
      ${ruleBlock}
    </div>`;
}

// -----------------------------------------------------------------
// Uplift rules pane
// -----------------------------------------------------------------

const UPLIFT_RULES_TIMING_PATTERN_LABELS = {
  annual_fixed_date: "Annual, fixed date",
  annual_specific_pp: "Annual, first full pay period",
  annual_anniversary: "Annual, anniversary of commencement",
  irregular_multi_date: "Irregular, multiple dates",
  biannual_fixed: "Biannual (twice per year)",
  one_time: "One-time only",
  performance_based: "Performance-based",
  external_confirmation: "Awaiting external confirmation",
  unknown: "Unknown / not stated",
};

function upliftSuggestionStatus(suggestion) {
  return suggestion?.provenance?.extraction_status || "";
}

function isFailedUpliftSuggestion(suggestion) {
  const status = upliftSuggestionStatus(suggestion);
  return Boolean(status && status !== "ok");
}

function renderUpliftFailure(suggestion, generatedAt) {
  const status = upliftSuggestionStatus(suggestion) || "unknown";
  const raw = suggestion?.provenance?.llm_raw_response || "";
  const reason = raw.startsWith("ERROR:") ? raw : `Extraction status was ${status}`;
  const pages = suggestion?.provenance?.inputs?.page_numbers || [];
  return `
    <div class="card mb-panel-card mb-note-callout uplift-failure-card">
      <span class="mb-eyebrow">Extraction notice</span>
      <h3>Uplift extraction did not complete</h3>
      <p>The system did not save analyst-ready uplift rules from this run. Re-run after the LLM provider is configured, or discard this failed run.</p>
      <div class="stack-sm mb-mono-metadata-block">
        <div><strong>Status:</strong> ${escapeHtml(status)}</div>
        <div><strong>Reason:</strong> ${escapeHtml(reason)}</div>
        <div><strong>Generated:</strong> ${escapeHtml(displayDate(generatedAt))}</div>
        <div><strong>Source pages scanned:</strong> ${escapeHtml(displayPages(pages))}</div>
      </div>
    </div>
  `;
}

function timestampValue(value) {
  const parsed = Date.parse(value || "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function upliftSuggestionReviewKey(suggestion, aeId = state.currentCouncil?.agreement_id) {
  if (!suggestion) return "";
  return `${String(aeId || "").toLowerCase()}::${suggestion.suggestion_id || "latest"}`;
}

function upliftSuggestionExcludedIndexes(suggestion) {
  const key = upliftSuggestionReviewKey(suggestion);
  const values = key ? state.upliftSuggestionExclusions[key] : [];
  return new Set((Array.isArray(values) ? values : []).map((value) => Number(value)).filter(Number.isInteger));
}

function setUpliftSuggestionExcludedIndex(suggestion, index, excluded) {
  const key = upliftSuggestionReviewKey(suggestion);
  if (!key || !Number.isInteger(index) || index < 0) return;
  const next = upliftSuggestionExcludedIndexes(suggestion);
  if (excluded) {
    next.add(index);
  } else {
    next.delete(index);
  }
  state.upliftSuggestionExclusions[key] = [...next].sort((a, b) => a - b);
}

function clearUpliftSuggestionExclusions(suggestion, aeId = state.currentCouncil?.agreement_id) {
  const key = upliftSuggestionReviewKey(suggestion, aeId);
  if (key) delete state.upliftSuggestionExclusions[key];
}

function upliftSuggestionIsPendingReview(suggestion, accepted, generatedAt, acceptedAt) {
  if (!suggestion || isFailedUpliftSuggestion(suggestion)) return false;
  if (!accepted) return true;
  if ((suggestion.suggestion_id || "") !== (accepted.suggestion_id || "")) return true;
  return timestampValue(generatedAt) > timestampValue(acceptedAt);
}

function includedUpliftSuggestionRules(suggestion) {
  const rules = suggestion?.document?.rules || [];
  const excluded = upliftSuggestionExcludedIndexes(suggestion);
  return (Array.isArray(rules) ? rules : []).filter((_, index) => !excluded.has(index));
}

function renderUpliftRulesPane() {
  const pane = document.getElementById("section-pane");
  const council = state.currentCouncil;
  if (!council) {
    clearWorkspaceModuleHeader();
    pane.innerHTML = '<div class="muted">Select a council first.</div>';
    return;
  }

  const section = (council.sections || {}).uplift_rules || {};
  const data = (section.data && typeof section.data === "object") ? section.data : {};
  const suggestion = data.suggestion || null;
  const accepted = data.accepted || null;
  const generatedAt = data.suggestion_generated_at || null;
  const acceptedAt = data.accepted_at || null;
  const sectionStatus = section.status || "not_started";
  const alignmentIssues = Array.isArray(data.table_alignment_issues) ? data.table_alignment_issues : [];
  const hasAlignmentIssues = alignmentIssues.length > 0;
  const hasAccepted = !!accepted;
  const hasPendingSuggestion = upliftSuggestionIsPendingReview(suggestion, accepted, generatedAt, acceptedAt);
  if (hasPendingSuggestion && section.status === "done") {
    section.status = "in_progress";
  }
  const effectiveSectionStatus = section.status || sectionStatus;
  const isAccepted = effectiveSectionStatus === "done" && hasAccepted && !hasAlignmentIssues && !hasPendingSuggestion;
  const isFailed = !hasAccepted && suggestion && isFailedUpliftSuggestion(suggestion);
  const headerActionsHtml = !suggestion && !accepted
    ? `<button id="uplift-suggest" class="primary mb-action-button mb-action-button-primary">Suggest uplift rules</button>`
    : isFailed
    ? `<button id="uplift-rerun" class="primary mb-action-button mb-action-button-primary">Re-run extraction</button><button id="uplift-discard" class="mb-toolbar-button">Discard failed run</button>`
    : hasPendingSuggestion
    ? `<button id="uplift-rerun" class="mb-toolbar-button">Re-run extraction</button><button id="uplift-discard" class="mb-toolbar-button">Discard candidate run</button>`
    : hasAccepted
    ? `<button id="uplift-rerun" class="mb-toolbar-button">Re-run extraction</button>`
    : `<button id="uplift-rerun" class="mb-toolbar-button">Re-run extraction</button><button id="uplift-discard" class="mb-toolbar-button">Discard suggestion</button>`;
  const upliftFinalState = (() => {
    if (hasAlignmentIssues) {
      return {
        title: "Extraction binding needs review",
        detail: "A published table movement conflicts with the accepted uplift rule.",
        disabled: true,
      };
    }
    if (!suggestion && !accepted) {
      return {
        title: "Extraction required",
        detail: "Run the suggestion pipeline before this section can be accepted.",
        disabled: true,
      };
    }
    if (isFailed) {
      return {
        title: "Extraction needs attention",
        detail: "Re-run or discard the failed extraction before accepting this section.",
        disabled: true,
      };
    }
    if (hasPendingSuggestion) {
      const included = includedUpliftSuggestionRules(suggestion).length;
      const total = (suggestion?.document?.rules || []).length;
      return {
        title: hasAccepted ? "Candidate run ready to replace accepted rules" : "Candidate rules ready",
        detail: `Review all ${total} extracted rule${total === 1 ? "" : "s"}; ${included} included rule${included === 1 ? "" : "s"} will be saved.`,
        disabled: false,
      };
    }
    if (isAccepted) {
      return {
        title: "Section complete",
        detail: "Uplift rules have been saved and accepted.",
        disabled: false,
      };
    }
    return {
      title: "Rules ready for scenarios",
      detail: "Save the extracted uplift rules and mark this section complete.",
      disabled: false,
    };
  })();
  const finalActionHtml = renderSectionFinalAction({
    eyebrow: "Uplift rule acceptance",
    title: upliftFinalState.title,
    detail: upliftFinalState.detail,
    buttonId: "uplift-accept",
    buttonAttrs: upliftFinalState.disabled ? "disabled" : "",
  });

  setWorkspaceModuleHeader("uplift_rules");
  pane.innerHTML = `
    ${renderSectionActionBar(headerActionsHtml, finalActionHtml)}
    <div id="uplift-rules-body"></div>
  `;

  const body = pane.querySelector("#uplift-rules-body");

  if (!suggestion && !accepted) {
    body.innerHTML = `
      <div class="card mb-panel-card mb-note-callout uplift-empty-card">
        <span class="mb-eyebrow">Extraction pipeline</span>
        <p class="stack-sm">Run the suggest pipeline to extract wage-increase rules from this agreement. Results are deterministic and cached by content hash; running again on the same PDF returns the same answer instantly.</p>
        <div class="muted mb-mono-metadata" style="margin-top:0.5rem;">Calls Claude; ~4k tokens; ~$0.01.</div>
      </div>
    `;
    document.getElementById("uplift-suggest")?.addEventListener("click", () => runUpliftSuggest({ forceRefresh: false }));
    return;
  }

  if (isFailed) {
    body.innerHTML = renderUpliftFailure(suggestion, generatedAt);
    document.getElementById("uplift-rerun")?.addEventListener("click", () => runUpliftSuggest({ forceRefresh: true }));
    document.getElementById("uplift-discard")?.addEventListener("click", discardUpliftSuggestion);
    return;
  }

  const acceptedBanner = isAccepted
    ? `<div class="banner-ok mb-note-callout">This section is complete.</div>`
    : "";
  const alignmentHtml = renderUpliftTableAlignmentIssues(alignmentIssues);
  const suggestionRules = suggestion?.document?.rules || [];
  const excludedSuggestionIndexes = upliftSuggestionExcludedIndexes(suggestion);
  const includedSuggestionCount = suggestionRules.filter((_, index) => !excludedSuggestionIndexes.has(index)).length;
  const suggestionHtml = hasPendingSuggestion
    ? `
      <div class="card mb-panel-card mb-workspace-card uplift-rules-card uplift-candidate-card">
        <div class="uplift-card-header">
          <div>
            <span class="mb-eyebrow">Candidate extraction run</span>
            <h3>Extracted uplift rule candidates</h3>
          </div>
          <span class="mb-status-chip mb-status-chip-neutral">${includedSuggestionCount} included / ${excludedSuggestionIndexes.size} discarded</span>
        </div>
        <p class="uplift-review-note">All extracted rules stay visible here. Discard marks a candidate out of the accepted set; it does not hide the row.</p>
        ${renderUpliftRulesTable(
          suggestionRules,
          suggestion?.document,
          {
            candidateReview: true,
            excludedIndexes: excludedSuggestionIndexes,
            filterToCurrentCouncil: false,
          },
        )}
      </div>
    `
    : "";
  const acceptedRules = accepted?.document?.rules || [];
  const acceptedHtml = hasAccepted
    ? `
      <div class="card mb-panel-card mb-workspace-card uplift-rules-card">
        <div class="uplift-card-header">
          <div>
            <span class="mb-eyebrow">Accepted rule basis</span>
            <h3>Current accepted uplift rules</h3>
          </div>
          <span class="mb-status-chip mb-status-chip-neutral">${acceptedRules.length} rules</span>
        </div>
        ${renderUpliftRulesTable(
          acceptedRules,
          accepted?.document,
          { editable: hasAccepted },
        )}
      </div>
    `
    : "";

  body.innerHTML = `
    ${acceptedBanner}
    ${alignmentHtml}
    ${suggestionHtml}
    ${acceptedHtml}
  `;

  if (hasPendingSuggestion) {
    document.getElementById("uplift-accept")?.addEventListener("click", acceptUpliftSuggestion);
    document.getElementById("uplift-discard")?.addEventListener("click", discardUpliftSuggestion);
  }
  document.getElementById("uplift-rerun")?.addEventListener("click", () => runUpliftSuggest({ forceRefresh: true }));

  body.querySelectorAll(".toggle-uplift-candidate-rule").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = Number(btn.dataset.origIndex);
      const excluded = btn.dataset.excluded !== "true";
      setUpliftSuggestionExcludedIndex(suggestion, index, excluded);
      renderUpliftRulesPane();
    });
  });

  // Wire per-rule delete buttons (accepted view only)
  if (hasAccepted) {
    body.querySelectorAll(".delete-uplift-rule").forEach((btn) => {
      btn.addEventListener("click", () => deleteAcceptedUpliftRule(council.agreement_id, Number(btn.dataset.origIndex)));
    });
  }

  // Wire rule source-page links to jump the PDF viewer.
  body.querySelectorAll(".uplift-page-link").forEach((link) => {
    link.addEventListener("click", (ev) => {
      ev.preventDefault();
      const page = Number(link.dataset.page);
      if (Number.isFinite(page) && state.pdfViewer) {
        state.pdfViewer.goTo(page);
      }
    });
  });
}

function renderUpliftRulesTable(
  rules,
  document_,
  {
    editable = false,
    candidateReview = false,
    excludedIndexes = new Set(),
    filterToCurrentCouncil = true,
  } = {},
) {
  const doc = document_ || {};
  const allRules = Array.isArray(rules) ? rules : [];
  const excluded = excludedIndexes instanceof Set
    ? excludedIndexes
    : new Set((Array.isArray(excludedIndexes) ? excludedIndexes : []).map((value) => Number(value)).filter(Number.isInteger));

  // Tag each rule with its original index before any filtering so that delete
  // buttons can reference the correct position in the unfiltered rules array.
  let indexed = allRules.map((rule, origIdx) => ({ rule, origIdx }));

  // For multi-employer agreements, filter rules to only those relating to the
  // current council.  Rules carry the council name in period_label
  // (e.g. "Year 1 ? Ararat Rural City Council").  If we can derive a needle
  // from the ae_id split slug (ae532042__ararat ? "ararat") and it matches
  // any period_label we keep only the matching subset; single-employer
  // agreements (generic labels like "Year 1") are unaffected.
  const aeId = (state.currentCouncil || {}).agreement_id || "";
  const splitSlug = aeId.includes("__") ? aeId.split("__").slice(1).join("__") : "";
  const lgaNeedle = splitSlug.replace(/_/g, " ").toLowerCase(); // "ararat" or "central goldfields"
  if (filterToCurrentCouncil && lgaNeedle) {
    const matched = indexed.filter(({ rule }) => (rule.period_label || "").toLowerCase().includes(lgaNeedle));
    if (matched.length) indexed = matched;
  }
  const safeRules = indexed;
  const timingLabel = UPLIFT_RULES_TIMING_PATTERN_LABELS[doc.timing_pattern] || doc.timing_pattern || "unknown";

  const metaLines = [
    `Council: <strong>${htmlDisplay(doc.council)}</strong>`,
    `Timing pattern: <strong>${escapeHtml(displayCodeLabel(timingLabel))}</strong>`,
    doc.multi_employer
      ? `Multi-employer: <strong>yes</strong> - covers ${(doc.covered_councils || []).map((c) => escapeHtml(c)).join(", ")}`
      : null,
    doc.notes ? `Notes: ${escapeHtml(doc.notes)}` : null,
  ].filter(Boolean);

  if (safeRules.length === 0) {
    return `
      <div class="muted stack-sm uplift-meta">${metaLines.map((l) => `<div class="uplift-meta-item">${l}</div>`).join("")}</div>
      <div class="muted mb-note-callout" style="margin-top:0.75rem;">No uplift rules detected.</div>
    `;
  }

  const rows = safeRules.map(({ rule: r, origIdx }) => {
    const date = displayDate(r.effective_date);
    const conf = typeof r.confidence === "number" ? r.confidence.toFixed(2) : DISPLAY_EMPTY;
    const page = r.source_page ? `<a href="#" class="uplift-page-link mb-evidence-tag" data-page="${r.source_page}">${escapeHtml(displayPages(r.source_page))}</a>` : DISPLAY_EMPTY;
    const isExcluded = candidateReview && excluded.has(origIdx);
    const deleteBtn = editable
      ? `<button class="delete-uplift-rule mb-toolbar-button" data-orig-index="${origIdx}" title="Remove rule">Remove</button>`
      : "";
    const candidateBtn = candidateReview
      ? `<button class="toggle-uplift-candidate-rule mb-toolbar-button" data-orig-index="${origIdx}" data-excluded="${isExcluded ? "true" : "false"}">${isExcluded ? "Restore" : "Discard"}</button>`
      : "";
    return `
      <tr class="${isExcluded ? "uplift-rule-excluded" : ""}">
        <td>${escapeHtml(r.period_label || "")}</td>
        <td>${escapeHtml(date)}</td>
        <td>${renderRuleExpressionCell(r)}</td>
        <td>${escapeHtml(r.timing_clause || "")}</td>
        <td class="uplift-source-cell">${page}</td>
        <td class="uplift-conf" data-conf="${conf}"><span class="mb-status-chip mb-status-chip-confidence">${conf}</span></td>
        ${editable || candidateReview ? `<td>${deleteBtn}${candidateBtn}</td>` : ""}
      </tr>
    `;
  }).join("");

  return `
    <div class="stack-sm uplift-meta">${metaLines.map((l) => `<div class="uplift-meta-item">${l}</div>`).join("")}</div>
    <div class="uplift-table-scroll">
      <table class="uplift-rules-table mb-extraction-table">
        <thead>
          <tr>
            <th>Period</th>
            <th>Effective</th>
            <th>Quantum</th>
            <th>Timing clause</th>
            <th title="Source page">Src.</th>
            <th title="Confidence">Conf.</th>
            ${editable || candidateReview ? "<th></th>" : ""}
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

// -----------------------------------------------------------------
// Uplift rules API actions
// -----------------------------------------------------------------

async function runUpliftSuggest({ forceRefresh }) {
  const council = state.currentCouncil;
  if (!council) return;
  const ae_id = council.agreement_id;
  const btn = document.getElementById("uplift-suggest") || document.getElementById("uplift-rerun");
  const originalText = btn ? btn.textContent : "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Running?";
  }
  try {
    const url = `/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/suggest${forceRefresh ? "?force_refresh=true" : ""}`;
    const result = await api(url, { method: "POST" });
    // Merge server-reported suggestion into local state + re-render
    const sec = council.sections || (council.sections = {});
    const ur = sec.uplift_rules || (sec.uplift_rules = {});
    const data = (ur.data && typeof ur.data === "object") ? ur.data : {};
    data.suggestion = result.suggestion;
    data.suggestion_generated_at = new Date().toISOString();
    ur.data = data;
    clearUpliftSuggestionExclusions(result.suggestion, ae_id);
    ur.status = result.section_status || ur.status || "in_progress";
    renderUpliftRulesPane();
  } catch (err) {
    alert(`Suggest failed: ${apiErrorMessage(err)}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
}

async function acceptUpliftSuggestion() {
  const council = state.currentCouncil;
  if (!council) return;
  const ae_id = council.agreement_id;
  const btn = document.getElementById("uplift-accept");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Saving...";
  }
  try {
    const url = `/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/accept`;
    const suggestion = council.sections?.uplift_rules?.data?.suggestion || null;
    const rules = suggestion ? includedUpliftSuggestionRules(suggestion) : null;
    await api(url, { method: "POST", body: JSON.stringify(rules ? { rules } : {}) });
    clearUpliftSuggestionExclusions(suggestion, ae_id);
    await refreshCurrentCouncil("uplift_rules");
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Save & Accept";
    }
    alert(`Accept failed: ${err.message}`);
  }
}

async function discardUpliftSuggestion() {
  const council = state.currentCouncil;
  if (!council) return;
  if (!confirm("Discard this candidate run? The content-addressed cache still keeps it; re-running will be instant.")) {
    return;
  }
  const aeId = council.agreement_id;
  const suggestion = council.sections?.uplift_rules?.data?.suggestion || null;
  try {
    await api(`/api/councils/${encodeURIComponent(aeId)}/uplift-rules/suggestion`, { method: "DELETE" });
    clearUpliftSuggestionExclusions(suggestion, aeId);
    await refreshCurrentCouncil("uplift_rules");
  } catch (err) {
    alert(`Discard failed: ${err.message}`);
  }
}

async function deleteAcceptedUpliftRule(aeId, origIdx) {
  const council = state.currentCouncil;
  if (!council) return;
  const rules = (council.sections?.uplift_rules?.data?.accepted?.document?.rules) || [];
  const updated = rules.filter((_, i) => i !== origIdx);
  try {
    const result = await api(
      `/api/councils/${encodeURIComponent(aeId)}/uplift-rules/accepted/rules`,
      { method: "PATCH", body: JSON.stringify({ rules: updated }) },
    );
    council.sections.uplift_rules.data.accepted.document.rules = result.rules;
    renderUpliftRulesPane();
  } catch (err) {
    toast(`Failed to delete rule: ${err.message}`, "error");
  }
}

function renderScenariosPane() {
  const pane = document.getElementById("section-pane");
  const council = state.currentCouncil;
  if (!council) {
    clearWorkspaceModuleHeader();
    pane.innerHTML = '<div class="muted">Select a council first.</div>';
    return;
  }

  setWorkspaceModuleHeader("scenarios");
  const finalActionHtml = renderSectionFinalAction({
    eyebrow: "Scenario acceptance",
    title: "QA judgement ready",
    detail: "Save reviewer notes and scenario overrides for the audit trail.",
    buttonId: "scenario-save-note-btn",
    buttonAttrs: `data-ae-id="${escapeHtml(council.agreement_id)}"`,
  });
  pane.innerHTML = `
    ${renderSectionActionBar("", finalActionHtml)}
    <div id="uplift-scenarios-host">
      <div class="card scenario-card">
        <h3>Scenario testing</h3>
        <div class="muted">Loading scenarios...</div>
      </div>
    </div>
  `;

  restoreScenarioOverrides(council.agreement_id).then((saved) => {
    _scenarioSavedNotes = saved.notes || null;
    updateScenarioSavedBadge(council.agreement_id, saved.saved_at);
    loadUpliftScenarios(council.agreement_id);
  });
}

async function restoreScenarioOverrides(ae_id) {
  try {
    const saved = await api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios/overrides`);
    if (saved.overrides && Object.keys(saved.overrides).length) {
      scenarioOverrides.set(ae_id, saved.overrides);
    } else {
      scenarioOverrides.delete(ae_id);
    }
    _scenarioSavedAt = saved.saved_at || null;
    _scenarioSavedNotes = saved.notes || null;
    setScenarioAuditEvents(saved.audit_events || []);
    return saved;
  } catch {
    scenarioOverrides.delete(ae_id);
    _scenarioSavedAt = null;
    _scenarioSavedNotes = null;
    setScenarioAuditEvents([]);
    return { overrides: {}, notes: null, saved_at: null };
  }
}

function updateScenarioSavedBadge(ae_id, saved_at) {
  _scenarioSavedAt = saved_at;
  const badge = document.getElementById("scenario-saved-badge");
  if (!badge) return;
  if (saved_at) {
    const t = new Date(saved_at);
    const hhmm = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    badge.textContent = `?? Saved ${hhmm}`;
    badge.style.display = "";
  } else {
    badge.textContent = "";
    badge.style.display = "none";
  }
  const saveBtn = document.getElementById("scenario-save-note-btn");
  if (saveBtn) {
    saveBtn.style.display = "";
  }
  const clearBtn = document.getElementById("scenario-clear-btn");
  if (clearBtn) {
    clearBtn.style.display = saved_at ? "" : "none";
  }
}

function buildScenarioNoteSummary(ae_id) {
  const overrides = scenarioOverrides.get(ae_id) || {};
  const lines = [];
  Object.entries(overrides).forEach(([period, cells]) => {
    Object.entries(cells || {}).forEach(([cellKey, override]) => {
      const [band, level] = cellKey.split(":");
      if (override.action === "use_computed") {
        lines.push(`Used computed for ${band}:${level} (${period}) · ${override.weekly}.`);
      } else if (override.action === "accept") {
        lines.push(`Accepted ${band}:${level} (${period}) as-is.`);
      } else if (override.action === "deleted") {
        lines.push(`Deleted ${band}:${level} (${period}).`);
      }
    });
  });
  return lines.join(" ");
}

function closeScenarioNoteDialog() {
  const dialog = document.querySelector("dialog.scenario-note-dialog");
  if (!dialog) return;
  dialog.close();
  dialog.remove();
}

function openScenarioNoteDialog(ae_id) {
  closeScenarioNoteDialog();
  const summary = buildScenarioNoteSummary(ae_id);
  const dialog = document.createElement("dialog");
  dialog.className = "scenario-note-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="stack-sm">
      <h3>Save & Accept</h3>
      <div class="dialog-summary">${escapeHtml(summary)}</div>
      <textarea id="scenario-note-textarea" placeholder="Add your reasoning here?">${escapeHtml(_scenarioSavedNotes || "")}</textarea>
      <div class="toolbar">
        <button type="button" id="scenario-note-save" class="primary" data-ae-id="${escapeHtml(ae_id)}">Save & Accept</button>
        <button type="button" id="scenario-note-cancel">Cancel</button>
      </div>
    </form>
  `;
  document.body.appendChild(dialog);
  dialog.showModal();
}

async function loadUpliftScenarios(ae_id) {
  const host = document.getElementById("uplift-scenarios-host");
  if (!host) return;
  try {
    const overridesForCouncil = scenarioOverrides.get(ae_id) || {};
    const [result, governedResult] = await Promise.all([
      api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ overrides: overridesForCouncil }),
      }),
      api(`/api/councils/${encodeURIComponent(ae_id)}/governed-set`).catch(() => ({ governed: { periods: [] } })),
      ensureRateCapStatus().catch(() => null),
    ]);
    const governedByPeriod = new Map();
    for (const p of (governedResult?.governed?.periods || [])) {
      if (p && p.effective_from) governedByPeriod.set(p.effective_from, p);
    }
    if (state.currentCouncil?.sections?.scenarios && result.section_status) {
      state.currentCouncil.sections.scenarios.status = result.section_status;
      renderSectionsList();
      if (state.currentSection === "scenarios") {
        syncSectionFinalActionState("scenario-save-note-btn", "scenarios");
      }
    }
    const openPeriods = new Set();
    host.querySelectorAll('details.scenario-deltas[open]').forEach((el) => {
      const p = el.getAttribute('data-period');
      if (p) openPeriods.add(p);
    });
    host.innerHTML = renderUpliftScenarios(
      result.scenarios || [],
      ae_id,
      result.constructable_periods || [],
      governedByPeriod,
      result.future_triggers || [],
      result.review_hints || [],
    );
    openPeriods.forEach((p) => {
      host.querySelectorAll('details.scenario-deltas[data-period]').forEach((el) => {
        if (el.getAttribute('data-period') === p) el.open = true;
      });
    });
  } catch (error) {
    host.innerHTML = `
      <div class="card scenario-card">
        <h3>Scenario testing</h3>
        <div class="scenario-error">Failed to load scenarios: ${escapeHtml(error.message)}</div>
      </div>
    `;
  }
}

function governedAssetKindLabel(kind) {
  if (kind === "pay_table") return "pay table";
  if (kind === "uplift_rule") return "uplift rule";
  return kind;
}

function formatGovernedAssetKinds(kinds) {
  const labels = kinds.map(governedAssetKindLabel);
  if (labels.length <= 1) return labels[0] || "governed asset";
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

// Event delegation: a single document-level click listener handles scenario
// controls regardless of when they were injected via innerHTML.
document.addEventListener("click", async (event) => {
  const promoteBtn = event.target.closest("[data-promote-governed]");
  if (promoteBtn) {
    const date = promoteBtn.getAttribute("data-promote-date");
    const aeId = promoteBtn.getAttribute("data-promote-ae");
    const kinds = (promoteBtn.getAttribute("data-promote-kinds") || "")
      .split(",")
      .map((kind) => kind.trim())
      .filter(Boolean);
    if (!date || !aeId || kinds.length === 0) return;
    const originalLabel = promoteBtn.textContent;
    const promotedKinds = [];
    promoteBtn.disabled = true;
    promoteBtn.textContent = "Promoting...";
    try {
      for (const kind of kinds) {
        await api(`/api/councils/${aeId}/governed-set/promote`, {
          method: "POST",
          body: JSON.stringify({ period_effective_from: date, kind }),
        });
        promotedKinds.push(kind);
      }
      toast(`Promoted ${formatGovernedAssetKinds(promotedKinds)} for ${date}`, "success");
      // Re-render scenario section so buttons show "promoted at ..." timestamps.
      // Fire-and-forget; the button itself goes away in the re-render.
      loadUpliftScenarios(aeId).catch(() => {
        // Fallback: if reload fails, at least restore the button to usable state.
        promoteBtn.disabled = false;
        promoteBtn.textContent = originalLabel;
      });
    } catch (error) {
      const prefix = promotedKinds.length ? `Partially promoted ${formatGovernedAssetKinds(promotedKinds)}. ` : "";
      toast(`${prefix}Promote failed: ${error.message}`, "error");
      promoteBtn.disabled = false;
      promoteBtn.textContent = originalLabel;
      if (promotedKinds.length) loadUpliftScenarios(aeId);
    }
    return;
  }

  const unwindBtn = event.target.closest("[data-governed-undo]");
  if (unwindBtn) {
    const date = unwindBtn.getAttribute("data-unwind-date");
    const aeId = unwindBtn.getAttribute("data-unwind-ae");
    const kinds = (unwindBtn.getAttribute("data-unwind-kinds") || "")
      .split(",")
      .map((kind) => kind.trim())
      .filter(Boolean);
    if (!date || !aeId || kinds.length === 0) return;
    const confirmMsg = `Undo governed promotion for ${date}?\n\nThis clears ${formatGovernedAssetKinds(kinds)} for this period, and also clears both governed slots on every later period. Upstream draft tables/rules are untouched - you can re-promote after.`;
    if (!window.confirm(confirmMsg)) return;
    const originalLabel = unwindBtn.innerHTML;
    unwindBtn.disabled = true;
    unwindBtn.innerHTML = "...";
    const summaries = [];
    try {
      for (const kind of kinds) {
        const result = await api(`/api/councils/${aeId}/governed-set/unwind`, {
          method: "POST",
          body: JSON.stringify({ period_effective_from: date, kind }),
        });
        summaries.push(result.summary || {});
      }
      const downstreamDates = new Set();
      const removedDates = new Set();
      summaries.forEach((summary) => {
        (summary.downstream_cleared || []).forEach((item) => downstreamDates.add(item.effective_from));
        (summary.periods_removed || []).forEach((period) => removedDates.add(period));
      });
      toast(`Undid governed promotion for ${date}${downstreamDates.size ? ` - ${downstreamDates.size} downstream period(s) cleared` : ""}${removedDates.size ? ` - ${removedDates.size} period(s) removed` : ""}`, "success");
      loadUpliftScenarios(aeId);
    } catch (err) {
      toast(`Undo failed: ${err.message}`, "error");
      unwindBtn.disabled = false;
      unwindBtn.innerHTML = originalLabel;
      loadUpliftScenarios(aeId);
    }
    return;
  }

  const bulkActionBtn = event.target.closest("[data-scenario-bulk-action]");
  if (bulkActionBtn) {
    const bulkAction = bulkActionBtn.getAttribute("data-scenario-bulk-action");
    const ae_id = bulkActionBtn.getAttribute("data-ae-id");
    const period = bulkActionBtn.getAttribute("data-period");
    if (!ae_id || !period || bulkAction !== "use_computed_all") return;
    const row = bulkActionBtn.closest(".scenario-row");
    if (!row) return;
    const failingComputedButtons = Array.from(
      row.querySelectorAll('button[data-scenario-action="use_computed"]')
    ).filter((btn) => btn.getAttribute('data-period') === period);
    for (const btn of failingComputedButtons) {
      const band = btn.getAttribute("data-band");
      const level = btn.getAttribute("data-level");
      const computed = btn.getAttribute("data-computed");
      if (band == null || level == null) continue;
      applyScenarioOverride(ae_id, period, band, level, "use_computed", Number(computed), { skipPersist: true });
    }
    loadUpliftScenarios(ae_id);
    api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios/overrides`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        overrides: scenarioOverrides.get(ae_id) || {},
        change_context: {
          scope: "group",
          action: "use_computed_all",
          period,
          affected_cells: failingComputedButtons.length,
        },
      }),
    }).then((resp) => {
      setScenarioAuditEvents(resp.audit_events || _scenarioAuditEvents);
      updateScenarioSavedBadge(ae_id, resp.saved_at);
    }).catch((err) => console.warn(err));
    return;
  }

  const actionBtn = event.target.closest("[data-scenario-action]");
  if (actionBtn) {
    const action = actionBtn.getAttribute("data-scenario-action");
    const ae_id = actionBtn.getAttribute("data-ae-id");
    const period = actionBtn.getAttribute("data-period");
    const band = actionBtn.getAttribute("data-band");
    const level = actionBtn.getAttribute("data-level");
    const computedAttr = actionBtn.getAttribute("data-computed");
    const weekly = computedAttr != null ? Number(computedAttr) : undefined;
    if (!ae_id || !period || band == null || level == null) return;
    applyScenarioOverride(ae_id, period, band, level, action, weekly);
    return;
  }

  const constructBtn = event.target.closest("[data-construct-table]");
  if (constructBtn) {
    const ae_id = constructBtn.getAttribute("data-ae-id");
    const effective_date = constructBtn.getAttribute("data-effective-date");
    if (ae_id && effective_date) {
      constructBtn.disabled = true;
      constructBtn.textContent = "Constructing?";
      const constructed = await constructProjectedTable(ae_id, effective_date);
      if (!constructed) {
        constructBtn.disabled = false;
        constructBtn.textContent = "Construct table";
      }
    }
    return;
  }

  const saveNoteBtn = event.target.closest("#scenario-save-note-btn");
  if (saveNoteBtn) {
    const ae_id = saveNoteBtn.getAttribute("data-ae-id");
    if (ae_id) openScenarioNoteDialog(ae_id);
    return;
  }

  const clearBtn = event.target.closest("#scenario-clear-btn");
  if (clearBtn) {
    const ae_id = clearBtn.getAttribute("data-ae-id");
    if (!ae_id) return;
    if (!window.confirm("Clear all saved overrides for this council?")) return;
    const resp = await api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios/overrides`, { method: "DELETE" });
    scenarioOverrides.delete(ae_id);
    _scenarioSavedNotes = null;
    setScenarioAuditEvents(resp.audit_events || []);
    updateScenarioSavedBadge(ae_id, null);
    loadUpliftScenarios(ae_id);
    return;
  }

  const saveDialogBtn = event.target.closest("#scenario-note-save");
  if (saveDialogBtn) {
    const ae_id = saveDialogBtn.getAttribute("data-ae-id");
    const textarea = document.getElementById("scenario-note-textarea");
    if (!ae_id || !textarea) return;
    const summary = buildScenarioNoteSummary(ae_id);
    const notes = `${summary}\n---\n${textarea.value}`;
    const currentOverrides = scenarioOverrides.get(ae_id) || {};
    const resp = await api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios/note`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes, overrides: currentOverrides, change_context: { scope: "note", action: "save_note" } }),
    });
    _scenarioSavedNotes = notes;
    setScenarioAuditEvents(resp.audit_events || _scenarioAuditEvents);
    updateScenarioSavedBadge(ae_id, resp.saved_at);
    closeScenarioNoteDialog();
    return;
  }

  if (event.target.closest("#scenario-note-cancel")) {
    closeScenarioNoteDialog();
  }
});

function applyScenarioOverride(ae_id, period, band, level, action, weekly, options = {}) {
  const cellKey = `${band}:${level}`;
  if (!scenarioOverrides.has(ae_id)) {
    scenarioOverrides.set(ae_id, {});
  }
  const council = scenarioOverrides.get(ae_id);
  if (action === "revert") {
    if (council[period]) {
      delete council[period][cellKey];
      if (!Object.keys(council[period]).length) delete council[period];
    }
    if (!Object.keys(council).length) scenarioOverrides.delete(ae_id);
  } else {
    if (!council[period]) council[period] = {};
    council[period][cellKey] = weekly != null
      ? { action, weekly }
      : { action };
  }
  if (!options.skipPersist) {
    loadUpliftScenarios(ae_id);

    const overridesForCouncil = scenarioOverrides.get(ae_id) || {};
    api(`/api/councils/${encodeURIComponent(ae_id)}/uplift-rules/scenarios/overrides`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        overrides: overridesForCouncil,
        change_context: options.changeContext || { scope: "cell", action, period, band, level },
      }),
    }).then((resp) => {
      _scenarioSavedNotes = overridesForCouncil && Object.keys(overridesForCouncil).length ? _scenarioSavedNotes : null;
      setScenarioAuditEvents(resp.audit_events || _scenarioAuditEvents);
      updateScenarioSavedBadge(ae_id, resp.saved_at);
    }).catch((err) => console.warn("auto-save failed:", err));
  }
}


function computeStructuralHints(cell_deltas) {
  const added = [];
  const removed = [];
  for (const d of (cell_deltas || [])) {
    const key = `${d.band}${d.level}`;
    if (d.prior_weekly == null && d.actual_weekly != null) {
      added.push(key);
    } else if (d.prior_weekly != null && d.actual_weekly == null) {
      removed.push(key);
    }
  }
  return { added, removed };
}

function currentUpliftRulesForDisplay() {
  const data = state.currentCouncil?.sections?.uplift_rules?.data || {};
  return (
    data.accepted?.document?.rules
    || data.suggestion?.document?.rules
    || data.rules
    || []
  ).filter((rule) => rule && typeof rule === "object");
}

function ruleDisplayId(rule) {
  return `${rule?.effective_date || ""}::${rule?.period_label || ""}`;
}

function buildUpliftRuleDisplayLookup(rules = currentUpliftRulesForDisplay()) {
  const byDate = new Map();
  const byId = new Map();
  rules.forEach((rule) => {
    const date = rule.effective_date;
    const id = ruleDisplayId(rule);
    if (date && !byDate.has(date)) byDate.set(date, rule);
    if (id && !byId.has(id)) byId.set(id, rule);
  });
  return { byDate, byId };
}

function findScenarioDisplayRule(scenario, ruleLookup) {
  if (!ruleLookup) return null;
  return (
    ruleLookup.byId.get(scenario?.rule_id)
    || ruleLookup.byDate.get(scenario?.period_effective_from)
    || null
  );
}

function renderConstructableRow(aeId, p, periodDescriptor, ruleLookup = null) {
  // Renders a constructable period as an inline scenario-style row.
  // Shape matches renderScenarioRow so the list stays visually unified.
  const displayRule = p.rule || ruleLookup?.byId.get(p.rule_id) || ruleLookup?.byDate.get(p.effective_date) || null;
  const ruleInfo = renderScenarioRuleExpression(displayRule, {
    quantum: p.rule_quantum,
    ruleId: p.rule_id,
  });
  const metaHtml = ruleInfo
    ? `<div class="scenario-row-meta scenario-story scenario-story-constructable">${ruleInfo}</div>`
    : "";
  // Event delegation (see document-level click listener below) wires the action via data-*
  // attributes, avoiding inline onclick escaping issues entirely.
  const btn = `<button class="btn-construct-table" data-construct-table="1" data-ae-id="${escapeHtml(String(aeId))}" data-effective-date="${escapeHtml(String(p.effective_date))}">Construct table</button>`;
  return `
    <div class="scenario-row workbench-card-scaffold scenario-row-constructable">
      <div class="scenario-row-head">
        <span class="scenario-status scenario-status-constructable">no table yet</span>
        ${renderPeriodHeading(periodDescriptor, p.effective_date)}
        <span class="scenario-row-actions">${btn}</span>
      </div>
      ${metaHtml}
      <div class="scenario-reason muted">Rule exists for this period but no pay table has been extracted yet. Construct a projected table from the prior period to validate.</div>
    </div>
  `;
}

async function constructProjectedTable(aeId, effectiveDate) {
  try {
    await api(`/api/councils/${encodeURIComponent(aeId)}/pay-tables/construct`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ effective_date: effectiveDate }),
    });
    toast(`Constructed projected table for ${effectiveDate}`, "success");
    loadUpliftScenarios(aeId);
    return true;
  } catch (e) {
    toast(`Construct table failed: ${e.message || e}`, "error");
    return false;
  }
}

function renderScenarioFutureTriggers(triggers = []) {
  if (!Array.isArray(triggers) || !triggers.length) return "";
  const chips = triggers.map((trigger) => {
    const date = trigger.trigger_date || trigger.period_effective_from || "";
    const period = trigger.period_effective_from || "";
    const label = [
      period ? `Period ${displayDate(period)}` : "",
      date ? `review ${displayDate(date)}` : "",
    ].filter(Boolean).join(" / ");
    return `<span class="scenario-future-trigger">${escapeHtml(label || "Future trigger")}</span>`;
  }).join("");
  return `
    <div class="scenario-future-triggers">
      <span class="scenario-future-trigger-label">Future-dated triggers</span>
      ${chips}
    </div>
  `;
}

function renderUpliftScenarios(
  scenarios,
  ae_id,
  constructablePeriods = [],
  governedByPeriod = new Map(),
  futureTriggers = [],
  reviewHints = [],
) {
  const ruleLookup = buildUpliftRuleDisplayLookup();
  const periods = Array.isArray(constructablePeriods) ? constructablePeriods : [];
  const constructableRowsHtml = periods
    .slice()
    .sort((a, b) => String(a.effective_date).localeCompare(String(b.effective_date)))
    .map((p) => renderConstructableRow(ae_id, p, null, ruleLookup))
    .join("");

  if (!scenarios.length) {
    const bodyHtml = constructableRowsHtml
      ? `<div class="scenario-list">${constructableRowsHtml}</div>`
      : renderEmptyState(
          "Scenario testing is waiting for comparable periods",
          "Complete at least one baseline pay table and a later uplift rule or pay table to validate rule application.",
          { eyebrow: "Validation" },
        );
    return `
      <div class="card scenario-card">
        <div class="scenario-header">
          <h3>Scenario testing</h3>
        </div>
        ${bodyHtml}
      </div>
    `;
  }

  // Blocked is always a single synthetic result with empty period_effective_from.
  if (scenarios.length === 1 && scenarios[0].status === "blocked") {
    const s = scenarios[0];
    const constructableSection = constructableRowsHtml
      ? `<div class="scenario-list">${constructableRowsHtml}</div>`
      : "";
    return `
      <div class="card scenario-card">
        <div class="scenario-header">
          <h3>Scenario testing</h3>
        </div>
        <div class="scenario-blocked workbench-empty-state">
          <span>Validation blocked</span>
          <strong>Scenario testing cannot run yet</strong>
          <p>${escapeHtml(s.reason)}</p>
        </div>
        ${constructableSection}
      </div>
    `;
  }

  const counts = scenarios.reduce((acc, s) => {
    acc[s.status] = (acc[s.status] || 0) + 1;
    return acc;
  }, {});
  const summary = ["consistent", "needs_attention", "table_resolved", "needs_review", "awaiting_input", "baseline"]
    .filter((k) => counts[k])
    .map((k) => `<span class="scenario-status scenario-status-${k}">${k.replace("_", " ")}: ${counts[k]}</span>`)
    .join(" ");
  const constructableCount = periods.length;
  const summaryWithConstructable = constructableCount
    ? `${summary} <span class="scenario-status scenario-status-constructable">no table yet: ${constructableCount}</span>`
    : summary;
  const futureTriggersHtml = renderScenarioFutureTriggers(futureTriggers);
  const reviewHintsHtml = Array.isArray(reviewHints) && reviewHints.length
    ? renderReviewHints(reviewHints)
    : "";

  // Merge scenario rows + constructable rows into one list, sorted by effective_date ASC.
  const nominatedExpiry = state.currentCouncil?.sections?.front_matter?.data?.nominated_expiry || null;

  // Build a lookup of period effective_date -> rule's period_label (e.g. "Year 2").
  // The scenario engine's own period_label is just the ISO date or "Baseline (date)",
  // not the human rule label. For readable headings we need to join rules by date.
  const acceptedRules = currentUpliftRulesForDisplay();
  const ruleLabelByDate = new Map();
  for (const r of acceptedRules) {
    if (r && typeof r === "object") {
      const d = r.effective_date;
      const l = r.period_label;
      if (typeof d === "string" && d && typeof l === "string" && l.trim()) {
        ruleLabelByDate.set(d, l.trim());
      }
    }
  }

  // Build a lookup of pay-table effective_from -> pay-table to_date. The pay tables
  // section of the canonical is the source of truth for period end dates; they're
  // computed once via recalcToDates and persisted in the canonical YAML. Do not
  // recompute them here ? just read them.
  const payTables =
    state.currentCouncil?.sections?.pay_tables?.tables || [];
  const payToDateByFrom = new Map();
  for (const t of payTables) {
    if (t && typeof t === "object") {
      const from = t.effective_from;
      const to = t.to_date;
      if (typeof from === "string" && from && typeof to === "string" && to) {
        // If multiple pay tables share the same effective_from (different rate_kinds),
        // prefer the one with a later to_date ? it describes the widest coverage.
        const prev = payToDateByFrom.get(from);
        if (!prev || to > prev) {
          payToDateByFrom.set(from, to);
        }
      }
    }
  }

  // Phase 1: collect raw items with date + kind + source object, sorted by date ASC.
  const rawItems = [
    ...scenarios.map((s) => ({ date: s.period_effective_from || "", kind: "scenario", raw: s })),
    ...periods.map((p) => ({ date: p.effective_date || "", kind: "constructable", raw: p })),
  ];
  rawItems.sort((a, b) => String(a.date).localeCompare(String(b.date)));

  // Phase 2: derive per-row period descriptors (ordinal + human range).
  const descriptors = describeScenarioPeriod(rawItems, ruleLabelByDate, payToDateByFrom, nominatedExpiry);

  // Phase 3: render each row with its descriptor.
  const rows = rawItems
    .map((item, i) =>
      item.kind === "scenario"
        ? renderScenarioRow(item.raw, ae_id, governedByPeriod.get(item.date || ""), descriptors[i], findScenarioDisplayRule(item.raw, ruleLookup))
        : renderConstructableRow(ae_id, item.raw, descriptors[i], ruleLookup),
    )
    .join("");

  // Collect structural hints across all periods
  const structuralHints = [];
  for (const s of scenarios) {
    const h = s.status === "baseline" ? { added: [], removed: [] } : computeStructuralHints(s.cell_deltas || []);
    for (const k of h.added) structuralHints.push(`${k} added`);
    for (const k of h.removed) structuralHints.push(`${k} removed`);
  }
  const uniqueHints = [...new Set(structuralHints)];
  const structuralHtml = uniqueHints.length
    ? `<div class="scenario-structural">${uniqueHints
        .map((h) => `<span class="scenario-hint">${escapeHtml(h)}</span>`)
        .join("")}</div>`
    : "";
  const scenarioQaHtml = _scenarioAuditEvents.length
    ? renderQaGovernanceEvents(_scenarioAuditEvents, { id: "scenario-qa-change-log" })
    : "";

  return `
    <div class="card scenario-card">
      <div class="scenario-header">
        <h3>Scenario testing</h3>
        <div class="scenario-summary">${summaryWithConstructable}</div>
        <span id="scenario-saved-badge" class="scenario-saved-badge" style="display:${_scenarioSavedAt ? "" : "none"};">${_scenarioSavedAt ? `?? Saved ${new Date(_scenarioSavedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}</span>
        <button id="scenario-clear-btn" class="scenario-clear-btn" data-ae-id="${escapeHtml(ae_id)}" style="display:${_scenarioSavedAt ? "" : "none"};">Clear overrides</button>
      </div>
      ${futureTriggersHtml}
      ${reviewHintsHtml ? `<div class="scenario-review-hints">${reviewHintsHtml}</div>` : ""}
      ${structuralHtml}
      ${scenarioQaHtml ? `<div class="qa-change-log-block scenario-qa-change-log-block"><h4>Reviewer Change Log</h4>${scenarioQaHtml}</div>` : ""}
      <div class="scenario-list">${rows}</div>
    </div>
  `;
}

function renderScenarioPromoteButtons(scenario, aeId, governedPeriod, displayRule = null) {
  const eligible = scenarioPayTablePromotable(scenario);
  if (!eligible || !scenario.period_effective_from) return "";
  const payAt = governedPeriod?.pay_table_governed_at || null;
  const ruleAt = governedPeriod?.uplift_rule_governed_at || null;
  const fmtTs = (iso) => {
    try {
      return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch {
      return iso;
    }
  };
  const hasMatchingRule = Boolean(displayRule && displayRule.effective_date === scenario.period_effective_from);
  const rulePromotable = syntheticScenarioEligible(scenario);
  const promoteKinds = [];
  if (!payAt) promoteKinds.push("pay_table");
  if (rulePromotable && hasMatchingRule && !ruleAt) promoteKinds.push("uplift_rule");
  const undoKinds = [];
  if (payAt) undoKinds.push("pay_table");
  if (ruleAt) undoKinds.push("uplift_rule");
  const allAvailableAssetsPromoted = Boolean(payAt) && (!rulePromotable || !hasMatchingRule || Boolean(ruleAt));
  const promoteTitleParts = [];
  if (promoteKinds.length) {
    promoteTitleParts.push(`Promote ${formatGovernedAssetKinds(promoteKinds)} for this period.`);
  }
  if (!rulePromotable) {
    promoteTitleParts.push("The source table has been accepted, but the uplift rule still needs extraction review, so this promotes the pay table only.");
  } else if (!hasMatchingRule) {
    promoteTitleParts.push(`No accepted uplift rule has effective_date=${scenario.period_effective_from}; this promotes the pay table only.`);
  }
  if (allAvailableAssetsPromoted) {
    promoteTitleParts.push("All available governed assets are already promoted.");
  }
  const promoteLabel = allAvailableAssetsPromoted ? "Promoted" : "Promote to Governed Set";
  const promoteClass = allAvailableAssetsPromoted
    ? "btn btn-sm btn-promote-governed btn-promoted"
    : "btn btn-sm btn-promote-governed";
  const promoteDisabled = promoteKinds.length ? "" : " disabled";
  const promotedMeta = [
    payAt ? `Pay ${fmtTs(payAt)}` : null,
    ruleAt ? `Rule ${fmtTs(ruleAt)}` : null,
  ].filter(Boolean);
  const statusHtml = promotedMeta.length
    ? `<span class="scenario-governed-status">${promotedMeta.map(escapeHtml).join(" + ")}</span>`
    : "";
  const undoHtml = undoKinds.length
    ? `<button class="btn btn-sm btn-governed-undo" data-governed-undo="1" data-unwind-kinds="${escapeHtml(undoKinds.join(","))}" data-unwind-date="${escapeHtml(scenario.period_effective_from)}" data-unwind-ae="${escapeHtml(aeId)}" aria-label="Undo governed promotion for ${escapeHtml(scenario.period_effective_from)}" title="Undo governed promotion for this period. All later periods will also be cleared."><span aria-hidden="true">&larrhk;</span></button>`
    : "";
  return `
    <div class="scenario-promote-buttons">
      <button class="${promoteClass}" data-promote-governed="1" data-promote-kinds="${escapeHtml(promoteKinds.join(","))}" data-promote-date="${escapeHtml(scenario.period_effective_from)}" data-promote-ae="${escapeHtml(aeId)}" title="${escapeHtml(promoteTitleParts.join(" "))}"${promoteDisabled}>${promoteLabel}</button>
      ${undoHtml}
      ${statusHtml}
    </div>`;
}

// Build per-item period descriptors (ordinal + human range) for a merged, date-sorted list.
// items: [{ date: ISOString, kind: "scenario"|"constructable", raw: <scenario or constructable object> }]
// nominatedExpiry: ISOString | null ? used as the to-date for the last row when truthy.
// Returns: parallel array of { ordinal, label, fromIso, toIso, fromHuman, toHuman }.
// Build per-item period descriptors (ordinal + human range) for a merged, date-sorted list.
// items: [{ date: ISOString, kind: "scenario"|"constructable", raw: <scenario or constructable object> }]
// ruleLabelByDate: Map<ISOString, string> ? looks up the human rule label (e.g. "Year 2")
//                   by period effective date. May be empty/missing entries.
// payToDateByFrom: Map<ISOString, ISOString> ? looks up the pay table's stored to_date
//                  by the period's effective_from. Source of truth when present.
// nominatedExpiry: ISOString | null ? used as the to-date for the last row when truthy.
// Returns: parallel array of { ordinal, label, fromIso, toIso, fromHuman, toHuman }.
function describeScenarioPeriod(items, ruleLabelByDate, payToDateByFrom, nominatedExpiry) {
  // Parse "YYYY-MM-DD" as a UTC date. Never use `new Date("YYYY-MM-DDT00:00:00")` ?
  // that's local midnight and mixes with toISOString() to silently shift by the TZ offset.
  const parseUtc = (iso) => {
    if (!iso || typeof iso !== "string") return null;
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
    return Number.isNaN(d.getTime()) ? null : d;
  };
  const toIso = (d) => (d ? d.toISOString().slice(0, 10) : null);
  const fmt = (iso) => displayDate(iso, "");
  const minusOneDay = (iso) => {
    const d = parseUtc(iso);
    if (!d) return null;
    d.setUTCDate(d.getUTCDate() - 1);
    return toIso(d);
  };
  const lookupRuleLabel = (iso) => {
    if (!ruleLabelByDate || typeof ruleLabelByDate.get !== "function") return "";
    const raw = ruleLabelByDate.get(iso);
    return typeof raw === "string" ? raw.trim() : "";
  };
  const labelFor = (item, idx) => {
    // Prefer the joined rule's own period_label (e.g. "Year 2", "Year 4 (Sign-off)").
    // Fall through only if no rule is joined OR the label doesn't parse cleanly.
    const fromRule = lookupRuleLabel(item.date);
    if (fromRule) {
      // "Year N" optionally followed by anything (including "(Sign-off / backdated)")
      const yearMatch = fromRule.match(/^Year\s+0*(\d+)\b/i);
      if (yearMatch) return `Year ${yearMatch[1]}`;
      const nounMatch = fromRule.match(/^(Period|Stage|Phase)\s+0*(\d+)\b/i);
      if (nounMatch) {
        const noun = nounMatch[1].charAt(0).toUpperCase() + nounMatch[1].slice(1).toLowerCase();
        return `${noun} ${nounMatch[2]}`;
      }
      // Rule has a label but doesn't match known short patterns ? use it verbatim.
      // Don't truncate: verbose labels (e.g. "First Instalment (1 July 2022 ? 30 June 2023)")
      // are intentional and the UI now elides the redundant date-range span for them.
      return fromRule;
    }
    // No rule joined (e.g. blocked/baseline with no corresponding rule row).
    const raw = item.raw || {};
    const isBaseline = item.kind === "scenario" && raw.status === "baseline";
    if (isBaseline) return "Baseline";
    return `Period ${idx + 1}`;
  };
  const lookupPayToDate = (iso) => {
    if (!iso || !payToDateByFrom || typeof payToDateByFrom.get !== "function") return null;
    const raw = payToDateByFrom.get(iso);
    return typeof raw === "string" && raw ? raw : null;
  };
  const result = [];
  for (let i = 0; i < items.length; i++) {
    const fromIso = items[i].date || null;
    let toIsoStr = lookupPayToDate(fromIso);  // Tier 1: pay table's own to_date.
    if (!toIsoStr) {
      // Tier 2: one day before the next row's effective date (rule-only periods).
      if (i < items.length - 1) {
        toIsoStr = minusOneDay(items[i + 1].date);
      } else {
        // Tier 3: nominated expiry for the final row.
        toIsoStr = nominatedExpiry || null;
      }
    }
    result.push({
      ordinal: i + 1,
      label: labelFor(items[i], i),
      fromIso,
      toIso: toIsoStr,
      fromHuman: fmt(fromIso),
      toHuman: fmt(toIsoStr),
    });
  }
  return result;
}

// Matches things like "1 July 2022 ? 30 June 2023", "1 Jul 2022 - 30 Jun 2023",
// "01/07/2022 ? 30/06/2023". Tolerant to en-dash, em-dash, hyphen, arrow, and to
// month names full or abbreviated.
const LABEL_HAS_RANGE_RE = /\b\d{1,2}[\s./-][A-Za-z0-9]{1,9}[\s./-]\d{2,4}\s*[??\-?][\s]*\d{1,2}[\s./-][A-Za-z0-9]{1,9}[\s./-]\d{2,4}\b/;

function renderPeriodHeading(d, fallbackIso) {
  // Defensive: if descriptor is missing (shouldn't happen), fall back to ISO.
  if (!d) {
    return `<span class="scenario-period">${escapeHtml(fallbackIso || "")}</span>`;
  }
  const labelHasRange = typeof d.label === "string" && LABEL_HAS_RANGE_RE.test(d.label);
  const rangeText = (!labelHasRange && d.toHuman)
    ? `${d.fromHuman} to ${d.toHuman}`
    : (!labelHasRange && d.fromHuman ? `from ${d.fromHuman}` : "");
  const isoChip = d.fromIso
    ? `<span class="scenario-period-iso muted" title="ISO start date">(${escapeHtml(d.fromIso)})</span>`
    : "";
  return `
    <span class="scenario-period">
      <span class="scenario-period-ordinal">${escapeHtml(d.label)}</span>
      ${rangeText ? `<span class="scenario-period-range">${escapeHtml(rangeText)}</span>` : ""}
      ${isoChip}
    </span>
  `.trim();
}

function renderScenarioStoryBlock(label, valueHtml, detailHtml = "") {
  if (!valueHtml) return "";
  return `
    <div class="scenario-story-block">
      <span>${escapeHtml(label)}</span>
      <strong>${valueHtml}</strong>
      ${detailHtml ? `<small>${detailHtml}</small>` : ""}
    </div>
  `;
}

function compactScenarioReason(reason, status = "") {
  const text = String(reason || "").trim();
  if (!text) return "";
  if (/all cells match rule application/i.test(text)) return "";
  if (/within 0\.1% tolerance/i.test(text)) return "";
  if (status === "baseline" && /first period of agreement/i.test(text)) return "";
  if (status === "baseline" && /no scenario applies/i.test(text)) return "";
  return text.length > 118 ? `${text.slice(0, 115).trim()}...` : text;
}

function renderScenarioTablesStory(tableNames) {
  const names = Array.isArray(tableNames) ? tableNames.filter(Boolean) : [];
  if (!names.length) return "";
  const primary = names[0];
  const remainder = names.length - 1;
  const detail = remainder > 0 ? `<small>+${remainder} tbl</small>` : "";
  return `
    <div class="scenario-story-block scenario-story-tables" title="${escapeHtml(names.join(" | "))}">
      <span>Source table</span>
      <strong class="scenario-table-name">${escapeHtml(primary)}</strong>
      ${detail}
    </div>
  `;
}

function renderScenarioCalculationStory(s) {
  const deltas = Array.isArray(s.cell_deltas) ? s.cell_deltas : [];
  const checked = deltas.length;
  if (!checked) {
    const baselineText = s.status === "baseline"
      ? "Baseline"
      : "No calculations";
    const detail = s.status === "baseline" ? "comparison source" : "";
    return renderScenarioStoryBlock("Result", escapeHtml(baselineText), escapeHtml(detail));
  }
  const aligned = deltas.filter((d) => d.within_tolerance).length;
  const needsReview = checked - aligned;
  const computed = deltas.filter((d) => d.computed_weekly != null).length;
  const accepted = deltas.filter((d) => d.override_action === "accept").length;
  const overridden = deltas.filter((d) => d.override_action != null).length;
  const headline = needsReview
    ? `${formatCount(needsReview, "0")} to review`
    : "All aligned";
  const detailParts = [
    `${formatCount(checked, "0")} checked`,
    needsReview ? `${formatCount(aligned, "0")} aligned` : "",
    computed ? `${formatCount(computed, "0")} calc` : "",
    accepted ? `${formatCount(accepted, "0")} accepted` : "",
    overridden && !accepted ? `${formatCount(overridden, "0")} override` : "",
  ].filter(Boolean);
  const reviewClass = needsReview ? " scenario-story-alert" : "";
  return `
    <div class="scenario-story-block scenario-story-calculation${reviewClass}">
      <span>Result</span>
      <strong>${escapeHtml(headline)}</strong>
      <small>${escapeHtml(detailParts.join(" / "))}</small>
    </div>
  `;
}

function renderScenarioRow(s, ae_id, governedPeriod, periodDescriptor, displayRule = null) {
  const periodHtml = renderPeriodHeading(periodDescriptor, s.period_effective_from);
  const statusLabel = s.status.replace("_", " ");
  const subLabel = s.sub_status ? ` - ${s.sub_status.replace("_", " ")}` : "";
  const ruleInfo = renderScenarioRuleExpression(displayRule, {
    quantum: s.rule_quantum,
    ruleId: s.rule_id,
    externalDeps: s.external_deps || [],
  });
  const tables = renderScenarioTablesStory(s.table_names || []);
  const prior = s.prior_period_effective_from
    ? renderScenarioStoryBlock("Baseline", escapeHtml(displayDate(s.prior_period_effective_from)))
    : "";
  const calculation = renderScenarioCalculationStory(s);
  const deltas = renderScenarioDeltas(s.cell_deltas || [], s.status === "baseline", ae_id, s.period_effective_from);
  const bulkEligible = (s.cell_deltas || []).filter(
    (d) => !d.within_tolerance && d.override_action == null && d.computed_weekly != null
  );
  const bulkBtnHtml = s.status !== "baseline" && bulkEligible.length > 0
    ? `<button class="scenario-action-btn scenario-action-bulk-computed"
              data-scenario-bulk-action="use_computed_all"
              data-ae-id="${escapeHtml(ae_id)}"
              data-period="${escapeHtml(s.period_effective_from)}"
              title="Apply computed value to all ${bulkEligible.length} failing cell(s) in this period">
         Use computed (${bulkEligible.length})
       </button>`
    : "";
  const hints = s.status === "baseline" ? { added: [], removed: [] } : computeStructuralHints(s.cell_deltas || []);
  const hintParts = [
    ...hints.added.map((k) => `<span class="scenario-hint scenario-hint-added">${escapeHtml(k)} added</span>`),
    ...hints.removed.map((k) => `<span class="scenario-hint scenario-hint-removed">${escapeHtml(k)} removed</span>`),
  ];
  const hintsHtml = hintParts.length
    ? `<div class="scenario-row-hints">${hintParts.join("")}</div>`
    : "";
  const depChips = (s.external_deps || [])
    .map((d) => {
      const statusClass = d.dep_status === "confirmed" ? "scenario-dep-chip-confirmed" : "scenario-dep-chip-pending";
      const icon = d.dep_status === "confirmed" ? "ok" : "wait";
      const rateCapValue = rateCapDisplayValueForDep(d);
      const rateCapLabel = hasRuleValue(rateCapValue)
        ? ` ${displayPercent(rateCapValue)}`
        : "";
      const label = `${icon} ${d.dep_kind.replace("_", " ")} ${escapeHtml(d.financial_year)}${escapeHtml(rateCapLabel)}`;
      const title = d.confirmed_at
        ? `confirmed ${new Date(d.confirmed_at).toLocaleDateString()}${d.resolution_note ? ` - ${d.resolution_note}` : ""}`
        : `pending; blocks automatic resolution`;
      return `<span class="scenario-dep-chip ${statusClass}" title="${escapeHtml(title)}">${label}</span>`;
    })
    .join("");
  const depChipsHtml = depChips ? `<div class="scenario-dep-chips">${depChips}</div>` : "";
  const reason = compactScenarioReason(s.reason, s.status);
  const reasonHtml = reason ? `<div class="scenario-reason">${escapeHtml(reason)}</div>` : "";

  return `
    <div class="scenario-row workbench-card-scaffold scenario-row-${s.status}">
      <div class="scenario-row-head">
        <span class="scenario-status scenario-status-${s.status}">${statusLabel}${subLabel}</span>
        ${periodHtml}
      </div>
      <div class="scenario-row-meta scenario-story">${[ruleInfo, tables, prior, calculation].filter(Boolean).join("")}</div>
      ${bulkBtnHtml ? `<div class="scenario-story-actions">${bulkBtnHtml}</div>` : ""}
      ${reasonHtml}
      ${depChipsHtml}
      ${hintsHtml}
      ${deltas}
      ${renderScenarioPromoteButtons(s, ae_id, governedPeriod, displayRule)}
    </div>
  `;
}

function renderScenarioDeltas(deltas, isBaseline = false, ae_id = null, period = null) {
  if (!deltas.length) return "";
  const fmt = (v) => displayNumber(v, DISPLAY_EMPTY, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtPct = (v) => displayFractionPercent(v);
  const fmtMoneyDelta = (v) => displayCurrencyDelta(v);
  const fmtPctDelta = (v) => displayPercentDelta(v, DISPLAY_EMPTY, { fraction: true });

  const rows = deltas
    .map((d) => {
      const rowClass = d.override_action === "use_computed"
        ? "scenario-delta-override"
        : d.override_action === "accept"
        ? "scenario-delta-accepted"
        : d.override_action === "deleted"
        ? "scenario-delta-deleted"
        : d.within_tolerance
        ? ""
        : "scenario-delta-fail";

      const okIcon =
        d.prior_weekly == null && d.computed_weekly == null && d.override_action == null
          ? "—"
          : d.within_tolerance
          ? "✔"
          : "✘";

      const prior = d.prior_weekly == null ? null : Number(d.prior_weekly);
      const newWeekly = d.computed_weekly == null
        ? d.actual_weekly == null
          ? null
          : Number(d.actual_weekly)
        : Number(d.computed_weekly);
      const priorToNewDelta = prior == null || newWeekly == null ? null : newWeekly - prior;
      const priorToNewPct =
        priorToNewDelta == null || prior == null || prior === 0 ? null : priorToNewDelta / prior;

      let actionsHtml = "";
      if (ae_id && period && !isBaseline) {
        const dataAttrs = `data-ae-id="${escapeHtml(ae_id)}" data-period="${escapeHtml(period)}" data-band="${escapeHtml(String(d.band))}" data-level="${escapeHtml(String(d.level))}"`;
        if (d.override_action != null) {
          actionsHtml = `<button class="scenario-action-btn revert" data-scenario-action="revert" ${dataAttrs}>? revert</button>`;
        } else if (!d.within_tolerance) {
          const btns = [];
          if (d.computed_weekly != null) {
            btns.push(`<button class="scenario-action-btn use-computed" data-scenario-action="use_computed" data-computed="${d.computed_weekly}" ${dataAttrs}>? computed</button>`);
          }
          btns.push(`<button class="scenario-action-btn accept" data-scenario-action="accept" ${dataAttrs}>? accept</button>`);
          btns.push(`<button class="scenario-action-btn delete" data-scenario-action="deleted" ${dataAttrs}>? delete</button>`);
          actionsHtml = `<div class="scenario-delta-actions">${btns.join("")}</div>`;
        }
      }

      return `
        <tr class="${rowClass}">
          <td>${escapeHtml(String(d.band))}</td>
          <td>${escapeHtml(String(d.level))}</td>
          <td>${fmt(d.prior_weekly)}</td>
          <td>${fmt(d.computed_weekly)}</td>
          <td>${fmtMoneyDelta(priorToNewDelta)}</td>
          <td>${fmtPctDelta(priorToNewPct)}</td>
          <td>${fmt(d.actual_weekly)}</td>
          <td>${fmt(d.abs_delta)}</td>
          <td>${fmtPct(d.pct_delta)}</td>
          <td>${okIcon}</td>
          <td>${actionsHtml}</td>
        </tr>`;
    })
    .join("");

  return `
    <details class="scenario-deltas" data-period="${escapeHtml(period || '')}">
      <summary>${isBaseline ? `Rates (${deltas.length})` : `Cell deltas (${deltas.length})`}</summary>
      <table class="scenario-delta-table">
        <thead><tr><th>Band</th><th>Level</th><th>Prior</th><th>Computed</th><th>↑ $</th><th>↑ %</th><th>Actual</th><th>Δ abs</th><th>Δ %</th><th>OK</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </details>`;
}

function renderSectionPane() {
  const pane = document.getElementById("section-pane");
  if (pane) {
    pane.classList.toggle("section-pane-qa-off", sectionQaIsGrey(state.currentSection));
  }
  if (state.currentSection === "overview") {
    renderOverviewPane();
  } else if (state.currentSection === "pay_tables") {
    renderPayTablesPane();
  } else if (state.currentSection === "uplift_rules") {
    renderUpliftRulesPane();
  } else if (state.currentSection === "scenarios") {
    renderScenariosPane();
  } else if (state.currentSection === "end_of_band_dollars") {
    renderEndOfBandDollarsPane();
  } else if (state.currentSection === "uplifts") {
    renderGovernedSetPane();
  } else {
    renderStubPane();
  }
  syncSectionPaneQaMode();
}

async function findPayTableCandidates() {
  await withBusyButton("pay-find-candidates", "Finding candidates?", async () => {
    try {
      const result = await api(`/api/councils/${state.currentCouncil.agreement_id}/pay-tables/find-candidates`, { method: "POST", body: "{}" });
      const overviewPayPages = overviewEvidencePages("pay");
      const overviewUpliftPages = overviewEvidencePages("uplift");
      state.payDraft.payTablePages = overviewPayPages.length
        ? overviewPayPages
        : normalisePageList(result.pay_table_pages || result.candidate_pages || []);
      state.payDraft.upliftRulePages = overviewUpliftPages.length
        ? overviewUpliftPages
        : normalisePageList(result.uplift_rule_pages || []);
      state.payDraft.candidatePages = normalisePageList(result.candidate_pages || [
        ...state.payDraft.payTablePages,
        ...state.payDraft.upliftRulePages,
      ]);
      renderSectionPane();
      loadPayReviewHints({ silent: true }).catch(() => {});
      toast(`Candidate pages loaded: ${state.payDraft.payTablePages.length} pay, ${state.payDraft.upliftRulePages.length} uplift`, "success");
    } catch (error) {
      toast(`Candidate scan failed: ${error.message}`, "error");
    }
  });
}

async function extractPayTableCurrentPage() {
  const page = state.pdfViewer.currentPage();
  await withBusyButton("pay-extract-current", "Extracting?", async () => {
    try {
      const result = await api(`/api/councils/${state.currentCouncil.agreement_id}/pay-tables/extract`, {
        method: "POST",
        body: JSON.stringify({ page_num: page }),
      });
      state.payDraft.rangeExtraction = {
        tables: result.tables || [],
        raw: result.raw || "",
        range: { start: page, end: page },
        accepted: new Set(),
      };
      renderSectionPane();
      loadPayReviewHints({ silent: true }).catch(() => {});
      toast(`Extracted ${(result.tables || []).length} tables from page ${page}`, "success");
    } catch (error) {
      toast(`Extraction failed: ${apiErrorMessage(error)}`, "error");
    }
  });
}

async function extractPayTableRange() {
  const startInput = document.getElementById("pay-range-start");
  const endInput = document.getElementById("pay-range-end");
  const start = Number(startInput.value);
  const end = Number(endInput.value);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 1 || end < start) {
    toast("Invalid page range", "error");
    return;
  }
  state.payDraft.rangeStart = start;
  state.payDraft.rangeEnd = end;
  await withBusyButton("pay-extract-range", "Extracting range?", async () => {
    try {
      const result = await api(`/api/councils/${state.currentCouncil.agreement_id}/pay-tables/extract-range`, {
        method: "POST",
        body: JSON.stringify({ start_page: start, end_page: end }),
      });
      if (result.error) {
        toast(`Range extract error: ${result.error}`, "error");
      }
      state.payDraft.rangeExtraction = {
        tables: result.tables || [],
        raw: result.raw || "",
        range: { start, end },
        accepted: new Set(),
      };
      renderSectionPane();
      loadPayReviewHints({ silent: true }).catch(() => {});
      toast(`Extracted ${(result.tables || []).length} tables from pages ${start}-${end}`, "success");
    } catch (error) {
      toast(`Range extraction failed: ${apiErrorMessage(error)}`, "error");
    }
  });
}

async function savePayTables() {
  await withBusyButton("pay-save", "Saving?", async () => {
    try {
      state.payDraft.sourceRef = document.getElementById("pay-source-ref").value;
      state.payDraft.notes = document.getElementById("pay-notes").value;
      state.payDraft.status = "done";
      const result = await api(`/api/councils/${state.currentCouncil.agreement_id}/pay-tables/save`, {
        method: "POST",
        body: JSON.stringify({
          action: "replace",
          tables: state.payDraft.tables,
          source_ref: state.payDraft.sourceRef,
          notes: state.payDraft.notes,
          status: state.payDraft.status,
        }),
      });
      state.payDraft.validations = result.validations || [];
      await refreshCurrentCouncil("pay_tables");
      toast("Pay tables saved and accepted", "success");
    } catch (error) {
      toast(`Save failed: ${error.message}`, "error");
    }
  });
}

async function validatePayTablesRemote() {
  await withBusyButton("pay-validate", "Validating?", async () => {
    try {
      const result = await api(`/api/councils/${state.currentCouncil.agreement_id}/pay-tables/validate`, { method: "POST", body: "{}" });
      state.payDraft.validations = result.validations || [];
      document.getElementById("validation-panel").innerHTML = renderValidations(state.payDraft.validations);
      toast("Validation complete", "success");
    } catch (error) {
      toast(`Validation failed: ${error.message}`, "error");
    }
  });
}

async function loadPayReviewHints(options = {}) {
  const aeId = state.currentCouncil?.agreement_id;
  if (!aeId) return;
  const run = async () => {
    try {
      const candidatePages = state.payDraft.candidatePages?.length
        ? state.payDraft.candidatePages
        : state.payDraft.payTablePages || [];
      const result = await api(`/api/councils/${encodeURIComponent(aeId)}/pay-tables/review-hints`, {
        method: "POST",
        body: JSON.stringify({
          tables: state.payDraft.tables,
          suggestions: state.dateSuggestions?.suggestions || [],
          candidate_pages: candidatePages,
        }),
      });
      state.payDraft.reviewHints = result.hints || [];
      const panel = document.getElementById("pay-review-hints-panel");
      if (panel) {
        panel.innerHTML = renderReviewHints(state.payDraft.reviewHints, {
          empty: "No review hints for the current draft.",
          appendNotes: true,
        });
        panel.querySelectorAll(".append-review-note").forEach((button) => {
          button.addEventListener("click", () => appendPayReviewHintNote(button.dataset.hintId || ""));
        });
      }
      if (!options.silent) {
        toast(`Review hints: ${state.payDraft.reviewHints.length}`, "success");
      }
    } catch (error) {
      if (!options.silent) toast(`Review hint check failed: ${error.message}`, "error");
    }
  };
  if (options.silent) {
    await run();
  } else {
    await withBusyButton("pay-review-hints", "Checking?", run);
  }
}

async function suggestEffectiveDatesRemote() {
  const aeId = state.currentCouncil?.agreement_id;
  if (!aeId) return;
  if (!state.payDraft.tables.length) {
    alert("No tables in draft to suggest dates for.");
    return;
  }
  await withBusyButton("pay-suggest-dates", "Asking LLM?", async () => {
    try {
      const data = await api(`/api/councils/${aeId}/pay-tables/suggest-effective-dates`, {
        method: "POST",
        body: JSON.stringify({ tables: state.payDraft.tables }),
      });
      state.dateSuggestions = data;
      await loadPayReviewHints({ silent: true });
      renderDateSuggestionsModal();
    } catch (e) {
      alert(`Suggest failed: ${apiErrorMessage(e)}`);
    }
  });
}

function renderDateSuggestionsModal() {
  let root = document.getElementById("date-suggest-modal");
  if (root) root.remove();
  root = document.createElement("div");
  root.id = "date-suggest-modal";
  root.className = "modal-overlay";
  const data = state.dateSuggestions;
  const rows = data.suggestions.map((s) => {
    const table = state.payDraft.tables[s.index] || {};
    const matches = s.current_effective_from === s.suggested_effective_from;
    if (matches) {
      return `
        <div class="suggest-row workbench-card-scaffold suggest-match" data-index="${s.index}">
          <div><strong>Table ${s.index + 1}</strong> ${escapeHtml(table.table_title || "(untitled)")} (${escapeHtml(table.rate_kind || "?")})</div>
          <div class="suggest-match-text">Already matches: <code>${escapeHtml(s.suggested_effective_from)}</code> · ${escapeHtml(s.rationale || "")}</div>
          <button class="suggest-dismiss" data-index="${s.index}">Dismiss</button>
        </div>`;
    }
    return `
      <div class="suggest-row workbench-card-scaffold" data-index="${s.index}">
        <div><strong>Table ${s.index + 1}</strong> ${escapeHtml(table.table_title || "(untitled)")} (${escapeHtml(table.rate_kind || "?")})</div>
        <div>Current: <code>${escapeHtml(s.current_effective_from || "?")}</code> ? Suggested: <strong>${escapeHtml(s.suggested_effective_from)}</strong></div>
        <div class="suggest-meta">Confidence: ${escapeHtml(s.confidence)} ? Clause: ${escapeHtml(s.clause_ref || "?")}</div>
        <div class="suggest-rationale">${escapeHtml(s.rationale || "")}</div>
        <div class="suggest-actions">
          <button class="suggest-apply primary" data-index="${s.index}" data-date="${escapeHtml(s.suggested_effective_from)}" data-clause="${escapeHtml(s.clause_ref || "")}" data-rationale="${escapeHtml(s.rationale || "")}">Apply</button>
          <button class="suggest-discard" data-index="${s.index}">Discard</button>
        </div>
      </div>`;
  }).join("");
  const unsuggested = data.unsuggested_indices.map((i) => {
    const table = state.payDraft.tables[i] || {};
    return `<li>Table ${i} · ${escapeHtml(table.table_title || "(untitled)")} (${escapeHtml(table.rate_kind || "?")})</li>`;
  }).join("");
  root.innerHTML = `
    <div class="modal-panel">
      <button class="modal-close" id="date-suggest-close">?</button>
      <h3>Suggested effective dates</h3>
      <p class="modal-subtext">Pages scanned: ${data.pages_used.join(", ") || "none"}.</p>
      <div class="suggest-list">${rows || "<p>No suggestions.</p>"}</div>
      ${unsuggested ? `<h4>No suggestion for these tables</h4><ul>${unsuggested}</ul>` : ""}
    </div>`;
  document.body.appendChild(root);

  root.querySelector("#date-suggest-close").addEventListener("click", () => root.remove());
  root.querySelectorAll(".suggest-apply").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-index"));
      const suggestedDate = btn.getAttribute("data-date");
      const clause = btn.getAttribute("data-clause");
      const rationale = btn.getAttribute("data-rationale");
      applySuggestion(idx, suggestedDate, clause, rationale);
      btn.closest(".suggest-row").remove();
    });
  });
  root.querySelectorAll(".suggest-discard, .suggest-dismiss").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.closest(".suggest-row").remove();
    });
  });
}

function applySuggestion(index, suggestedDate, clauseRef, rationale) {
  const table = state.payDraft.tables[index];
  if (!table) return;
  const oldDate = table.effective_from || "?";
  table.effective_from = suggestedDate;
  const noteLine = `[${new Date().toISOString().slice(0, 10)}] Table ${index + 1} effective_from ${oldDate} ? ${suggestedDate}${clauseRef ? ` (clause ${clauseRef})` : ""}${rationale ? `: ${rationale}` : ""}`;
  state.payDraft.notes = (state.payDraft.notes || "").trim();
  state.payDraft.notes = state.payDraft.notes ? state.payDraft.notes + "\n" + noteLine : noteLine;
  applyToDateRecalc();
  renderSectionPane();
  loadPayReviewHints({ silent: true }).catch(() => {});
}

async function handleDecisionAction(action, aeId) {
  if (action === "mark-multi") {
    openSplitModal(aeId);
    return;
  }
  if (action === "confirm-single") {
    openConfirmSingleModal(aeId);
    return;
  }
  if (action === "undo-split") {
    await undoSplit(aeId);
    return;
  }
  if (action === "clear-record") {
    openClearRecordModal(aeId);
  }
}

function closeModal(id = "decision-modal") {
  document.getElementById(id)?.remove();
}

function addModalCloseHandlers(root, id) {
  root.addEventListener("click", (event) => {
    if (event.target === root) closeModal(id);
  });
  root.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => closeModal(id));
  });
}

function openSplitModal(aeId) {
  closeModal();
  const item = state.councils.find((row) => row.ae_id === aeId);
  const matched = splitMatchedNames(item?.fetch_metadata);
  const modal = document.createElement("div");
  modal.id = "decision-modal";
  modal.className = "modal-overlay";
  modal.innerHTML = `
    <div class="modal-panel modal-panel-narrow">
      <button class="modal-close" data-close-modal>?</button>
      <h3>Mark ${escapeHtml(aeId.toUpperCase())} as multi-council</h3>
      <p class="modal-subtext">Select at least two active councils. Matched LGAs are preselected.</p>
      <div class="modal-form-grid">
        <label class="stack-sm">
          Search council
          <input type="search" id="split-search" placeholder="Search councils...">
        </label>
        <label class="stack-sm">
          Add council
          <select id="split-add-council">${getCouncilOptionsHtml("", true)}</select>
        </label>
      </div>
      <div id="split-selected" class="modal-checklist"></div>
      <label class="stack-sm" style="margin-top:0.75rem;">
        Notes
        <textarea id="split-notes" placeholder="Why this agreement should be split"></textarea>
      </label>
      <div class="toolbar" style="margin-top:0.75rem;">
        <button id="split-submit" class="primary">Split</button>
        <button data-close-modal>Cancel</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  addModalCloseHandlers(modal, "decision-modal");

  const selected = new Set(matched);
  const renderSelected = () => {
    const query = modal.querySelector("#split-search").value.trim().toLowerCase();
    const selectedDiv = modal.querySelector("#split-selected");
    const visible = state.canonicalCouncils.filter((council) => {
      if (selected.has(council.short_name)) return true;
      if (!query) return false;
      return council.short_name.toLowerCase().includes(query) || council.long_name.toLowerCase().includes(query);
    });
    selectedDiv.innerHTML = visible.map((council) => {
      const checked = selected.has(council.short_name) ? "checked" : "";
      return `
        <label class="checklist-item">
          <input type="checkbox" value="${escapeHtml(council.short_name)}" ${checked}>
          <span>${escapeHtml(council.short_name)}</span>
        </label>
      `;
    }).join("") || '<div class="muted">No councils match this search.</div>';
    selectedDiv.querySelectorAll("input[type=checkbox]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selected.add(checkbox.value);
        else selected.delete(checkbox.value);
      });
    });
  };

  modal.querySelector("#split-search").addEventListener("input", renderSelected);
  modal.querySelector("#split-add-council").addEventListener("change", (event) => {
    if (event.target.value) {
      selected.add(event.target.value);
      event.target.value = "";
      renderSelected();
    }
  });
  renderSelected();

  modal.querySelector("#split-submit").addEventListener("click", async () => {
    const lgas = [...selected];
    if (lgas.length < 2) {
      toast("Select at least two councils", "error");
      return;
    }
    try {
      await api(`/api/councils/${aeId}/split`, {
        method: "POST",
        body: JSON.stringify({
          lgas,
          notes: modal.querySelector("#split-notes").value,
        }),
      });
      closeModal();
      await fetchCouncils();
      toast("Agreement split recorded", "success");
    } catch (error) {
      toast(`Split failed: ${error.message}`, "error");
    }
  });
}

function openConfirmSingleModal(aeId) {
  closeModal();
  const item = state.councils.find((row) => row.ae_id === aeId);
  const matched = splitMatchedNames(item?.fetch_metadata);
  const preselected = matched.length === 1 ? matched[0] : (item?.canonical_lga_short_name || "");
  const modal = document.createElement("div");
  modal.id = "decision-modal";
  modal.className = "modal-overlay";
  modal.innerHTML = `
    <div class="modal-panel modal-panel-narrow">
      <button class="modal-close" data-close-modal>?</button>
      <h3>Confirm single council for ${escapeHtml(aeId.toUpperCase())}</h3>
      <label class="stack-sm">
        Search council
        <input type="search" id="single-search" placeholder="Search councils...">
      </label>
      <label class="stack-sm" style="margin-top:0.75rem;">
        Council
        <select id="single-lga">${getCouncilOptionsHtml(preselected, true)}</select>
      </label>
      <label class="stack-sm" style="margin-top:0.75rem;">
        Notes
        <textarea id="single-notes" placeholder="Why this is a single-council agreement"></textarea>
      </label>
      <div class="toolbar" style="margin-top:0.75rem;">
        <button id="single-submit" class="primary">Confirm single</button>
        <button data-close-modal>Cancel</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  addModalCloseHandlers(modal, "decision-modal");

  modal.querySelector("#single-search").addEventListener("input", (event) => {
    const query = event.target.value.trim().toLowerCase();
    const options = state.canonicalCouncils.filter((council) => (
      !query || council.short_name.toLowerCase().includes(query) || council.long_name.toLowerCase().includes(query)
    ));
    const select = modal.querySelector("#single-lga");
    const current = select.value;
    select.innerHTML = `<option value="">Select council</option>${options.map((council) => {
      const selectedAttr = council.short_name === current ? "selected" : "";
      return `<option value="${escapeHtml(council.short_name)}" ${selectedAttr}>${escapeHtml(council.short_name)}</option>`;
    }).join("")}`;
  });

  modal.querySelector("#single-submit").addEventListener("click", async () => {
    const lga = modal.querySelector("#single-lga").value;
    if (!lga) {
      toast("Choose a council", "error");
      return;
    }
    try {
      await api(`/api/councils/${aeId}/confirm-single`, {
        method: "POST",
        body: JSON.stringify({
          lga,
          notes: modal.querySelector("#single-notes").value,
        }),
      });
      closeModal();
      await fetchCouncils();
      toast("Single-council decision recorded", "success");
    } catch (error) {
      toast(`Confirm single failed: ${error.message}`, "error");
    }
  });
}

async function undoSplit(aeId) {
  if (!window.confirm(`Undo split for ${aeId.toUpperCase()}?`)) return;
  try {
    await api(`/api/councils/${aeId}/split`, { method: "DELETE" });
    await fetchCouncils();
    toast("Split removed", "success");
  } catch (error) {
    toast(`Undo failed: ${error.message}`, "error");
  }
}

function openClearRecordModal(aeId) {
  closeModal();
  const item = state.councils.find((row) => row.ae_id === aeId);
  const label = item?.source_name || item?.fetch_metadata?.["Agreement Title"] || aeId.toUpperCase();
  const modal = document.createElement("div");
  modal.id = "decision-modal";
  modal.className = "modal-overlay";
  modal.innerHTML = `
    <div class="modal-panel modal-panel-narrow">
      <button class="modal-close" data-close-modal>?</button>
      <h3>Clear record for ${escapeHtml(aeId.toUpperCase())}</h3>
      <p class="modal-subtext">${escapeHtml(label)}</p>
      <label class="stack-sm" style="margin-top:0.75rem;">
        Reason
        <textarea id="clear-record-reason" placeholder="Why this agreement is being reset"></textarea>
      </label>
      <label class="stack-sm" style="margin-top:0.75rem;">
        Type ${escapeHtml(aeId.toUpperCase())}
        <input id="clear-record-confirm" type="text" autocomplete="off">
      </label>
      <div class="toolbar" style="margin-top:0.75rem;">
        <button id="clear-record-submit" class="decision-action-danger">Clear record</button>
        <button data-close-modal>Cancel</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  addModalCloseHandlers(modal, "decision-modal");
  modal.querySelector("#clear-record-submit").addEventListener("click", async () => {
    const typed = modal.querySelector("#clear-record-confirm").value.trim().toLowerCase();
    if (typed !== aeId.toLowerCase()) {
      toast("Agreement ID confirmation does not match", "error");
      return;
    }
    const submit = modal.querySelector("#clear-record-submit");
    const originalText = submit.textContent;
    submit.disabled = true;
    submit.textContent = "Clearing...";
    try {
      const result = await api(`/api/councils/${encodeURIComponent(aeId)}/clear-review-record`, {
        method: "POST",
        body: JSON.stringify({
          reason: modal.querySelector("#clear-record-reason").value,
          include_related: true,
        }),
      });
      closeModal();
      state.analysisDataByKind = {};
      state.analysisData = null;
      await fetchCouncils();
      const moved = result?.moved_artifacts?.length || 0;
      toast(`Clear record archived ${formatCount(moved, "0")} artifact(s)`, "success");
    } catch (error) {
      submit.disabled = false;
      submit.textContent = originalText;
      toast(apiErrorMessage(error), "error");
    }
  });
}

async function refreshCurrentCouncil(section = state.currentSection) {
  const refreshed = await api(`/api/councils/${state.currentCouncil.agreement_id}`);
  const shouldRefreshMap = !state.lgaBoundaryGeojson;
  state.currentCouncil = refreshed;
  state.currentSection = section;
  syncPayDraftFromCanonical();
  await fetchCouncils();
  renderCouncilSelect();
  const title = document.getElementById("council-title");
  if (title) title.textContent = refreshed.source_name;
  renderOverview();
  renderFwc();
  renderSectionsList();
  renderSectionPane();
  if (shouldRefreshMap) {
    ensureLgaBoundaryData().then((geojson) => {
      if (geojson && state.currentCouncil?.agreement_id === refreshed.agreement_id && document.body.dataset.view === "workspace") {
        renderSectionPane();
      }
    });
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function quickSwitchSearchText(item) {
  return [
    item.label,
    item.group,
    item.detail,
    ...(item.keywords || []),
  ].filter(Boolean).join(" ").toLowerCase();
}

function quickSwitchItems() {
  const recentItems = readRecentWorkbenchDestinations().map((item) => ({
    group: "Recent",
    label: item.label,
    detail: item.detail || item.route,
    keywords: [...(item.keywords || []), item.route],
    action: () => openWorkbenchRoute(item.route),
  }));
  const capabilityItems = flattenCapabilityNodes()
    .filter((item) => item.route)
    .map((item) => ({
      group: item.parentLabel || "Capability",
      label: item.label,
      detail: item.description || item.route,
      keywords: [item.id, item.label, item.status, item.countSummary, item.route],
      action: () => openWorkbenchRoute(item.route),
    }));
  const items = [
    ...recentItems,
    ...capabilityItems,
    {
      group: "Screen",
      label: "Incoming",
      detail: "New source candidates grouped by confidence",
      keywords: ["incoming", "source", "registry", "confidence"],
      action: () => switchView("incoming"),
    },
    {
      group: "Screen",
      label: "Intake Processing",
      detail: "Accepted source processing and PDF fetch queue",
      keywords: ["intake", "processing", "source", "pdf", "fetch"],
      action: () => switchView("intake"),
    },
    {
      group: "Screen",
      label: "Review Board",
      detail: "Agreement pipeline and section progress",
      keywords: ["matrix", "review", "pipeline"],
      action: () => switchView("matrix"),
    },
    {
      group: "Screen",
      label: "Council Audit",
      detail: "Agreement lineage, source process and governed changes by council",
      keywords: ["audit", "lineage", "report", "council"],
      action: () => switchView("audit"),
    },
    {
      group: "Screen",
      label: "Settings",
      detail: "Provider status, rate caps and reference controls",
      keywords: ["admin", "settings", "rate cap", "llm"],
      action: () => switchView("admin"),
    },
  ];

  Object.entries(DATA_SET_CONFIG).forEach(([kind, config]) => {
    items.push({
      group: "Data set",
      label: config.title,
      detail: config.tableDescription || config.description,
      keywords: [kind, config.label, config.runId, config.sourceInput, config.sourceUse],
      action: () => {
        setCurrentDataSet(kind);
        switchView("analysis");
      },
    });
  });

  SECTION_GROUPS.forEach((group) => {
    group.sections.forEach((section) => {
      items.push({
        group: group.label,
        label: SECTION_LABELS[section] || section,
        detail: SECTION_DESCRIPTIONS[section] || "Agreement workspace section",
        keywords: ["workspace", "section", section],
        action: () => openWorkspaceSection(section),
      });
    });
  });

  workspaceNavigationItems().forEach((item) => {
    const shortName = item.canonical_lga_short_name || item.fetch_metadata?.lga_short_name || "";
    const agreementName = item.fetch_metadata?.["Agreement Title"] || item.source_name || item.ae_id;
    const label = shortName ? `${shortName} - ${agreementName}` : agreementName;
    items.push({
      group: "Agreement",
      label,
      detail: [item.ae_id, item.agreement_status, item.section_statuses?.pay_tables].filter(Boolean).join(" / "),
      keywords: [item.ae_id, item.source_name, shortName, agreementName],
      action: () => openCouncil(item.ae_id, state.currentSection || "overview"),
    });
  });

  auditCouncilNames().forEach((name) => {
    items.push({
      group: "Council audit",
      label: `${name} audit`,
      detail: "Lineage and process audit document",
      keywords: [name, "audit", "lineage", "report"],
      action: () => openWorkbenchRoute(`#audit/${encodeURIComponent(name)}`),
    });
  });

  return items;
}

function filterQuickSwitchItems(query) {
  const cleanQuery = String(query || "").trim().toLowerCase();
  const tokens = cleanQuery.split(/\s+/).filter(Boolean);
  const items = quickSwitchItems();
  if (!tokens.length) return items.slice(0, 18);
  return items
    .map((item) => {
      const haystack = quickSwitchSearchText(item);
      const score = tokens.reduce((total, token) => {
        if (String(item.label || "").toLowerCase().startsWith(token)) return total + 5;
        if (haystack.includes(token)) return total + 2;
        return total - 20;
      }, 0);
      return { item, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.item.label.localeCompare(b.item.label))
    .map((entry) => entry.item)
    .slice(0, 18);
}

function renderQuickSwitchResultButton(item, index) {
  return `
    <button
      type="button"
      class="quick-switch-result${index === quickSwitchState.activeIndex ? " active" : ""}"
      data-quick-switch-index="${index}"
      role="option"
      aria-selected="${index === quickSwitchState.activeIndex}"
    >
      <span class="quick-switch-result-main">
        <strong>${escapeHtml(item.label)}</strong>
        <small>${escapeHtml(item.detail || "")}</small>
      </span>
      <span class="quick-switch-result-group">${escapeHtml(item.group)}</span>
    </button>
  `;
}

function renderQuickSwitchResultRows(results, isSearching) {
  let previousGroup = "";
  return results.map((item, index) => {
    const heading = !isSearching && item.group !== previousGroup
      ? `<div class="quick-switch-section-heading" role="presentation">${escapeHtml(item.group)}</div>`
      : "";
    previousGroup = item.group;
    return `${heading}${renderQuickSwitchResultButton(item, index)}`;
  }).join("");
}

function renderQuickSwitchResults() {
  const input = document.getElementById("quick-switch-input");
  const resultsEl = document.getElementById("quick-switch-results");
  if (!resultsEl) return;
  const query = input?.value || "";
  const isSearching = query.trim().length > 0;
  quickSwitchState.results = filterQuickSwitchItems(query);
  if (quickSwitchState.activeIndex >= quickSwitchState.results.length) {
    quickSwitchState.activeIndex = Math.max(0, quickSwitchState.results.length - 1);
  }
  if (!quickSwitchState.results.length) {
    resultsEl.innerHTML = renderEmptyState(
      "No matching destination",
      "Try a council name, data set, workspace section or screen name.",
      { eyebrow: "Quick switch" },
    );
    return;
  }
  resultsEl.innerHTML = renderQuickSwitchResultRows(quickSwitchState.results, isSearching);
}

function setQuickSwitchActiveIndex(index) {
  if (!quickSwitchState.results.length) return;
  quickSwitchState.activeIndex = (index + quickSwitchState.results.length) % quickSwitchState.results.length;
  renderQuickSwitchResults();
  document.querySelector(`[data-quick-switch-index="${quickSwitchState.activeIndex}"]`)?.scrollIntoView({ block: "nearest" });
}

function openQuickSwitch() {
  const dialog = document.getElementById("quick-switch-dialog");
  const input = document.getElementById("quick-switch-input");
  if (!dialog || !input) return;
  quickSwitchState.open = true;
  quickSwitchState.activeIndex = 0;
  dialog.hidden = false;
  document.body.classList.add("quick-switch-open");
  input.value = "";
  renderQuickSwitchResults();
  window.requestAnimationFrame(() => input.focus());
}

function closeQuickSwitch() {
  const dialog = document.getElementById("quick-switch-dialog");
  if (!dialog) return;
  dialog.hidden = true;
  quickSwitchState.open = false;
  document.body.classList.remove("quick-switch-open");
  document.getElementById("quick-switch-open")?.focus();
}

async function activateQuickSwitchItem(index = quickSwitchState.activeIndex) {
  const item = quickSwitchState.results[index];
  if (!item) return;
  closeQuickSwitch();
  try {
    await item.action();
  } catch (error) {
    toast(apiErrorMessage(error), "error");
  }
}

function wireQuickSwitch() {
  document.getElementById("quick-switch-open")?.addEventListener("click", openQuickSwitch);
  document.querySelectorAll("[data-quick-switch-close]").forEach((element) => {
    element.addEventListener("click", closeQuickSwitch);
  });
  document.getElementById("quick-switch-input")?.addEventListener("input", () => {
    quickSwitchState.activeIndex = 0;
    renderQuickSwitchResults();
  });
  document.getElementById("quick-switch-results")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-quick-switch-index]");
    if (!button) return;
    activateQuickSwitchItem(Number(button.dataset.quickSwitchIndex));
  });
  document.addEventListener("keydown", (event) => {
    const key = event.key;
    if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "k") {
      event.preventDefault();
      openQuickSwitch();
      return;
    }
    if (!quickSwitchState.open) return;
    if (key === "Escape") {
      event.preventDefault();
      closeQuickSwitch();
    } else if (key === "ArrowDown") {
      event.preventDefault();
      setQuickSwitchActiveIndex(quickSwitchState.activeIndex + 1);
    } else if (key === "ArrowUp") {
      event.preventDefault();
      setQuickSwitchActiveIndex(quickSwitchState.activeIndex - 1);
    } else if (key === "Enter") {
      event.preventDefault();
      activateQuickSwitchItem();
    }
  });
}

function normalisePageList(pages) {
  const seen = new Set();
  return (Array.isArray(pages) ? pages : [])
    .map((page) => Number(page))
    .filter((page) => Number.isInteger(page) && page > 0)
    .filter((page) => {
      if (seen.has(page)) return false;
      seen.add(page);
      return true;
    });
}

function overviewEvidencePages(kind) {
  const overview = state.currentCouncil?.overview || {};
  const overviewSection = state.currentCouncil?.sections?.overview?.data || {};
  const field = kind === "uplift" ? "likely_uplift_pages" : "likely_pay_table_pages";
  return normalisePageList([
    ...(overview[field] || []),
    ...(overviewSection[field] || []),
  ]);
}

function currentAgreementPageCount() {
  const overview = state.currentCouncil?.overview || {};
  const candidates = [
    overview.page_count,
    state.currentCouncil?.page_count,
    state.currentCouncil?.pdf_pages,
    state.currentCouncil?.total_pages,
  ];
  for (const value of candidates) {
    const count = Number(value);
    if (Number.isInteger(count) && count > 0) return count;
  }
  return null;
}

function payAnchorWindow(page, pageCount = null) {
  const clean = Number(page);
  if (!Number.isInteger(clean) || clean < 1) return [];
  const start = Math.max(1, clean - 12);
  const end = pageCount ? Math.min(pageCount, clean + 4) : clean + 4;
  const pages = [];
  for (let candidate = start; candidate <= end; candidate += 1) {
    pages.push(candidate);
  }
  return pages;
}

function payExtractionPagePlan(overviewPages, rankedPayPages, candidatePages, pageCount = null) {
  const primary = [];
  const fallback = [];
  const seenGroups = new Set();
  const add = (target, pages) => {
    const clean = normalisePageList(pages).filter((page) => !pageCount || page <= pageCount);
    for (const group of contiguousPageGroups(clean)) {
      const key = group.join(",");
      if (!key || seenGroups.has(key)) continue;
      seenGroups.add(key);
      target.push(group);
    }
  };
  for (const page of overviewPages) add(primary, payAnchorWindow(page, pageCount));
  for (const group of contiguousPageGroups(rankedPayPages.slice(0, 18))) add(primary, group);
  for (const page of candidatePages.slice(0, 30)) add(fallback, [page]);
  for (const page of normalisePageList([...rankedPayPages.slice(18, 40), ...candidatePages.slice(30, 60)])) {
    add(fallback, payAnchorWindow(page, pageCount));
  }
  return { primary, fallback };
}

function payEvidencePageGroups() {
  const overviewPayPages = overviewEvidencePages("pay");
  const overviewUpliftPages = overviewEvidencePages("uplift");
  const payTablePages = normalisePageList(
    overviewPayPages.length
      ? overviewPayPages
      : state.payDraft.payTablePages.length
      ? state.payDraft.payTablePages
      : state.payDraft.candidatePages.length
      ? state.payDraft.candidatePages
      : [],
  );
  const upliftRulePages = normalisePageList(
    overviewUpliftPages.length
      ? overviewUpliftPages
      : state.payDraft.upliftRulePages.length
      ? state.payDraft.upliftRulePages
      : [],
  );
  return [
    {
      kind: "pay",
      title: "Pay table pages",
      note: "Use these for pay-table extraction.",
      pages: payTablePages,
      empty: "No pay table pages loaded.",
      buttonLabel: "Pay",
    },
    {
      kind: "uplift",
      title: "Uplift rule pages",
      note: "Use these to anchor effective dates.",
      pages: upliftRulePages,
      empty: "No uplift rule pages loaded.",
      buttonLabel: "Uplift",
    },
  ];
}

function renderPayCandidatePageGroups() {
  const groups = payEvidencePageGroups();
  const hasAnyPages = groups.some((group) => group.pages.length);
  if (!hasAnyPages) {
    return '<div id="candidate-pages" class="candidate-page-groups"><span class="muted">No candidates loaded.</span></div>';
  }

  return `
    <div id="candidate-pages" class="candidate-page-groups">
      ${groups.map((group) => `
        <div class="candidate-page-group candidate-page-group-${group.kind}">
          <div class="candidate-page-group-head">
            <span>${escapeHtml(group.title)}</span>
            <small>${escapeHtml(group.note)}</small>
          </div>
          <div class="candidate-list">
            ${group.pages.length
              ? group.pages.map((page) => `
                <button
                  data-page="${page}"
                  data-evidence-kind="${escapeHtml(group.kind)}"
                  class="candidate-page candidate-page-${escapeHtml(group.kind)}"
                >${escapeHtml(group.buttonLabel)} p. ${page}</button>
              `).join("")
              : `<span class="muted">${escapeHtml(group.empty)}</span>`}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function initViewer() {
  setPdfPaneMode(state.pdfPaneMode);
  document.getElementById("pdf-pane-collapse")?.addEventListener("click", togglePdfPaneCollapsed);
  document.getElementById("pdf-pane-expand")?.addEventListener("click", togglePdfPaneExpanded);
  state.pdfViewer = new PdfViewer(document.getElementById("pdf-canvas"), {
    prev: document.getElementById("pdf-prev"),
    next: document.getElementById("pdf-next"),
    indicator: document.getElementById("pdf-page-indicator"),
    jumpInput: document.getElementById("pdf-page-jump"),
    jumpBtn: document.getElementById("pdf-jump-btn"),
    zoomIn: document.getElementById("pdf-zoom-in"),
    zoomOut: document.getElementById("pdf-zoom-out"),
    zoomLevel: document.getElementById("pdf-zoom-level"),
  });
  state.pdfViewer.onPageChange = (page) => {
    if (state.payDraft.rangeStart === null) {
      state.payDraft.rangeStart = page;
      if (state.payDraft.rangeEnd === null) {
        state.payDraft.rangeEnd = page + 3;
      }
      const startEl = document.getElementById("pay-range-start");
      const endEl = document.getElementById("pay-range-end");
      if (startEl) startEl.value = state.payDraft.rangeStart;
      if (endEl) endEl.value = state.payDraft.rangeEnd;
    }
  };
}

function wireShell() {
  wireCapabilityTreeNavigation();
  wireQuickSwitch();
  document.getElementById("current-link-copy")?.addEventListener("click", copyCurrentWorkbenchLink);
  window.addEventListener("hashchange", () => {
    applyWorkbenchRouteFromHash().catch((error) => toast(apiErrorMessage(error), "error"));
  });
  document.getElementById("analysis-refresh")?.addEventListener("click", () => {
    rebuildAndRefreshCurrentAnalysisDataSet().catch((error) => {
      toast(`Refresh failed: ${apiErrorMessage(error)}`, "error");
    });
  });
  document.getElementById("analysis-filter")?.addEventListener("input", (event) => {
    state.analysisFilter = event.target.value;
    renderAnalysisWorkspace();
  });
  document.getElementById("analysis-sort")?.addEventListener("change", (event) => {
    state.analysisSort = event.target.value;
    renderAnalysisWorkspace();
  });
  document.getElementById("analysis-focus-rate-cap")?.addEventListener("click", () => {
    state.analysisFilter = currentDataSetConfig().firstFilterValue;
    const filter = document.getElementById("analysis-filter");
    if (filter) filter.value = state.analysisFilter;
    renderAnalysisWorkspace();
  });
  document.getElementById("analysis-focus-floor")?.addEventListener("click", () => {
    state.analysisFilter = currentDataSetConfig().secondFilterValue;
    const filter = document.getElementById("analysis-filter");
    if (filter) filter.value = state.analysisFilter;
    renderAnalysisWorkspace();
  });
  document.getElementById("analysis-clear-filter")?.addEventListener("click", () => {
    state.analysisFilter = "";
    const filter = document.getElementById("analysis-filter");
    if (filter) filter.value = "";
    renderAnalysisWorkspace();
  });
  document.getElementById("job-intake-filter")?.addEventListener("input", (event) => {
    state.jobIntakeFilter = event.target.value;
    renderJobIntake();
  });
  document.getElementById("job-intake-tier")?.addEventListener("change", (event) => {
    state.jobIntakeTier = event.target.value;
    renderJobIntake();
  });
  document.getElementById("job-intake-platform")?.addEventListener("change", (event) => {
    state.jobIntakePlatform = event.target.value;
    renderJobIntake();
  });
  document.getElementById("job-intake-status")?.addEventListener("change", (event) => {
    state.jobIntakeStatus = event.target.value;
    renderJobIntake();
  });
  document.querySelectorAll("[data-job-intake-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.jobIntakeTab = button.dataset.jobIntakeTab || "jobs";
      renderJobIntake();
    });
  });
  document.getElementById("job-observed-filter")?.addEventListener("input", (event) => {
    state.jobObservedFilter = event.target.value;
    renderJobIntake();
  });
  document.getElementById("job-observed-governance")?.addEventListener("change", (event) => {
    state.jobObservedGovernance = event.target.value;
    renderJobIntake();
  });
  document.getElementById("job-observed-platform")?.addEventListener("change", (event) => {
    state.jobObservedPlatform = event.target.value;
    renderJobIntake();
  });
  document.getElementById("job-observed-band")?.addEventListener("change", (event) => {
    state.jobObservedBand = event.target.value;
    renderJobIntake();
  });
  document.getElementById("job-history-filter")?.addEventListener("input", (event) => {
    state.jobAccumulatorFilter = event.target.value;
    renderJobHistoryPanel();
  });
  document.getElementById("job-intake-clear")?.addEventListener("click", () => {
    clearJobIntakeFilters();
    renderJobIntake();
  });
  document.getElementById("job-intake-refresh")?.addEventListener("click", () => {
    withBusyButton("job-intake-refresh", "Refreshing...", async () => {
      await ensureJobSourceRegistry({ force: true });
      renderJobIntake();
    }).catch((error) => toast(`Job intake refresh failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("job-observed-refresh")?.addEventListener("click", () => {
    withBusyButton("job-observed-refresh", "Scraping...", async () => {
      await runJobScrapePreview();
    }).catch((error) => toast(`Job preview scrape failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("job-observed-enrich")?.addEventListener("click", () => {
    withBusyButton("job-observed-enrich", "Enriching...", async () => {
      await runJobScrapePreview({ enrichAttachments: true });
    }).catch((error) => toast(`Linked document enrichment failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("job-completion-enrich")?.addEventListener("click", () => {
    withBusyButton("job-completion-enrich", "Mining...", async () => {
      await runJobScrapePreview({ enrichAttachments: true });
    }).catch((error) => toast(`Linked document enrichment failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("job-secondary-refresh")?.addEventListener("click", () => {
    withBusyButton("job-secondary-refresh", "Checking...", async () => {
      await runJobSecondaryPreview();
    }).catch((error) => toast(`Secondary source refresh failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("job-history-ingest")?.addEventListener("click", () => {
    withBusyButton("job-history-ingest", "Accumulating...", async () => {
      await runJobAccumulatorIngest();
    }).catch(() => {});
  });
  document.getElementById("job-history-refresh")?.addEventListener("click", () => {
    withBusyButton("job-history-refresh", "Collecting...", async () => {
      await runJobAccumulatorRefresh();
    }).catch(() => {});
  });
  document.getElementById("job-resolution-refresh")?.addEventListener("click", () => {
    withBusyButton("job-resolution-refresh", "Probing...", async () => {
      await runJobEndpointResolution();
    }).catch((error) => toast(`Endpoint resolution needs attention: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("job-pipeline-filter")?.addEventListener("input", (event) => {
    state.jobPipelineFilter = event.target.value;
    renderJobPipeline();
  });
  document.getElementById("job-pipeline-status")?.addEventListener("change", (event) => {
    state.jobPipelineStatus = event.target.value;
    renderJobPipeline();
  });
  document.getElementById("job-pipeline-refresh")?.addEventListener("click", () => {
    withBusyButton("job-pipeline-refresh", "Loading...", async () => {
      await ensureJobPipelineStage1({ force: true });
      renderJobPipeline();
    }).catch((error) => toast(`Job pipeline load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("job-pipeline-open-intake")?.addEventListener("click", () => {
    switchView("job-intake");
  });
  document.getElementById("wiki-refresh")?.addEventListener("click", () => {
    withBusyButton("wiki-refresh", "Refreshing...", async () => {
      await renderWikiCockpit({ force: true });
    }).catch((error) => toast(`Wiki refresh failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("wiki-open-map")?.addEventListener("click", () => {
    const select = document.getElementById("wiki-map-select");
    state.wikiSelectedAeId = String(select?.value || state.wikiSelectedAeId || "").toLowerCase();
    renderWikiDocumentMaps();
    renderWikiMapDetail().catch((error) => toast(`Map load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("wiki-map-select")?.addEventListener("change", (event) => {
    state.wikiSelectedAeId = String(event.target.value || "").toLowerCase();
    renderWikiDocumentMaps();
    renderWikiMapDetail().catch((error) => toast(`Map load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("wiki-tag-filter")?.addEventListener("change", (event) => {
    state.wikiTagFilter = String(event.target.value || "all");
    resetWikiTaggedEvidence();
    renderWikiTagExplorer({ force: true }).catch((error) => toast(`Tag evidence load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("wiki-tag-source-type")?.addEventListener("change", (event) => {
    state.wikiTagSourceType = String(event.target.value || "all");
    resetWikiTaggedEvidence();
    renderWikiTagExplorer({ force: true }).catch((error) => toast(`Tag evidence load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("wiki-tag-record-type")?.addEventListener("change", (event) => {
    state.wikiTagRecordType = String(event.target.value || "all");
    resetWikiTaggedEvidence();
    renderWikiTagExplorer({ force: true }).catch((error) => toast(`Tag evidence load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("wiki-tag-relevance")?.addEventListener("change", (event) => {
    state.wikiTagRelevance = String(event.target.value || "all");
    resetWikiTaggedEvidence();
    renderWikiTagExplorer({ force: true }).catch((error) => toast(`Tag evidence load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.getElementById("wiki-tag-query")?.addEventListener("input", (event) => {
    state.wikiTagQuery = String(event.target.value || "").trim();
    resetWikiTaggedEvidence();
    renderWikiTagExplorer({ force: true }).catch((error) => toast(`Tag evidence load failed: ${apiErrorMessage(error)}`, "error"));
  });
  document.addEventListener("click", (event) => {
    const target = event.target && typeof event.target.closest === "function" ? event.target : null;
    if (!target) return;
    const reviewCouncilButton = target.closest("[data-capability-review-council-key]");
    if (reviewCouncilButton) {
      event.preventDefault();
      state.capabilityReviewCouncilId = String(reviewCouncilButton.dataset.capabilityReviewCouncilKey || "").toLowerCase();
      rerenderCapabilityReviewWorkspace();
      return;
    }
    const reviewStageFilterButton = target.closest("[data-capability-review-stage-filter]");
    if (reviewStageFilterButton) {
      event.preventDefault();
      state.capabilityReviewStageFilter = String(reviewStageFilterButton.dataset.capabilityReviewStageFilter || "all");
      rerenderCapabilityReviewWorkspace();
      return;
    }
    const wikiMapButton = target.closest("[data-wiki-open-map]");
    if (wikiMapButton) {
      event.preventDefault();
      state.wikiSelectedAeId = String(wikiMapButton.dataset.wikiOpenMap || "").toLowerCase();
      renderWikiDocumentMaps();
      renderWikiMapSelect();
      renderWikiMapDetail().catch((error) => toast(`Map load failed: ${apiErrorMessage(error)}`, "error"));
      return;
    }
    const wikiGoldEntitlementButton = target.closest("[data-wiki-gold-entitlement-id]");
    if (wikiGoldEntitlementButton) {
      event.preventDefault();
      state.wikiSelectedGoldEntitlementId = String(wikiGoldEntitlementButton.dataset.wikiGoldEntitlementId || "");
      renderWikiClauseTree();
      renderWikiEntitlementDetail();
      return;
    }
    const wikiClauseButton = target.closest("[data-wiki-clause-id]");
    if (wikiClauseButton) {
      event.preventDefault();
      state.wikiSelectedClauseId = String(wikiClauseButton.dataset.wikiClauseId || "");
      renderWikiClauseTree();
      renderWikiClauseDetail();
      return;
    }
    const wikiTagPick = target.closest("[data-wiki-tag-pick]");
    if (wikiTagPick) {
      event.preventDefault();
      state.wikiTagFilter = String(wikiTagPick.dataset.wikiTagPick || "all");
      resetWikiTaggedEvidence();
      renderWikiTagExplorer({ force: true }).catch((error) => toast(`Tag evidence load failed: ${apiErrorMessage(error)}`, "error"));
      return;
    }
    const wikiTagMore = target.closest("[data-wiki-tag-more]");
    if (wikiTagMore) {
      event.preventDefault();
      renderWikiTagExplorer({ append: true }).catch((error) => toast(`Tag evidence load failed: ${apiErrorMessage(error)}`, "error"));
      return;
    }
    const wikiCohortButton = target.closest("[data-wiki-cohort-key]");
    if (wikiCohortButton) {
      event.preventDefault();
      const nextKey = String(wikiCohortButton.dataset.wikiCohortKey || WIKI_DEFAULT_COHORT_KEY);
      state.wikiComparatorCohortKey = WIKI_COHORT_KEYS.includes(nextKey) ? nextKey : WIKI_DEFAULT_COHORT_KEY;
      renderWikiEntitlementDetail();
      return;
    }
    const distributionCohortButton = target.closest("[data-analysis-distribution-cohort-key]");
    if (distributionCohortButton) {
      event.preventDefault();
      setChartDistributionCohortKey(distributionCohortButton.dataset.analysisDistributionCohortKey);
      return;
    }
    const cohortButton = target.closest("[data-analysis-cohort-key]");
    if (cohortButton) {
      event.preventDefault();
      setChartCohortKey(cohortButton.dataset.analysisCohortKey);
      return;
    }
    const basisButton = target.closest("[data-distribution-basis]");
    if (basisButton) {
      event.preventDefault();
      setChartBaseMode(basisButton.dataset.distributionBasis);
      return;
    }
    const rangeButton = target.closest("[data-distribution-range]");
    if (rangeButton) {
      event.preventDefault();
      setChartRangeMode(rangeButton.dataset.distributionRange);
    }
  });
  document.addEventListener("change", (event) => {
    const target = event.target && typeof event.target.matches === "function" ? event.target : null;
    if (!target) return;
    if (target.matches("[data-capability-review-entitlement]")) {
      state.capabilityReviewEntitlementId = String(target.value || "");
      state.capabilityReviewStageFilter = "";
      rerenderCapabilityReviewWorkspace();
      return;
    }
    if (target.matches("[data-capability-review-council]")) {
      state.capabilityReviewCouncilId = String(target.value || "").toLowerCase();
      rerenderCapabilityReviewWorkspace();
      return;
    }
    if (target.matches("[data-wiki-comparator-council]")) {
      const nextAeId = String(target.value || "");
      if (!nextAeId) return;
      loadCouncilContext(nextAeId, state.currentSection || "overview")
        .then(() => refreshContextAwareViewAfterAgreementChange("wiki"))
        .catch((error) => toast(`Council context failed: ${apiErrorMessage(error)}`, "error"));
      return;
    }
    if (target.matches("[data-chart-year]")) {
      const quarter = document.querySelector("[data-chart-quarter]")?.value || String(quarterNumberFromIso(selectedChartQuarterStart()));
      setChartQuarterStart(quarterStartFromYearQuarter(target.value, quarter));
      return;
    }
    if (target.matches("[data-chart-quarter]")) {
      const year = document.querySelector("[data-chart-year]")?.value || selectedChartQuarterStart().slice(0, 4);
      setChartQuarterStart(quarterStartFromYearQuarter(year, target.value));
      return;
    }
    if (target.matches("[data-chart-band]")) {
      setChartBand(target.value);
    }
  });
  document.getElementById("matrix-filter")?.addEventListener("input", renderMatrix);
  document.getElementById("matrix-sort")?.addEventListener("change", (event) => {
    state.pipelineSort = event.target.value;
    renderMatrix();
  });
  document.getElementById("matrix-open-next")?.addEventListener("click", () => {
    const reviewRows = reviewBoardRows();
    const next = reviewRows.find((item) => item.section_statuses?.pay_tables !== "done")
      || reviewRows[0];
    if (!next) {
      toast("No reviewable agreement is available", "error");
      return;
    }
    openCouncil(next.ae_id, "pay_tables");
  });
  document.getElementById("matrix-focus-gated")?.addEventListener("click", () => {
    const filter = document.getElementById("matrix-filter");
    if (filter) filter.value = "gated";
    renderMatrix();
  });
  document.getElementById("matrix-focus-pay")?.addEventListener("click", () => {
    const filter = document.getElementById("matrix-filter");
    if (filter) filter.value = "pay table work";
    renderMatrix();
    toast("Showing rows where pay tables still need work", "success");
  });
  document.getElementById("matrix-clear-filter")?.addEventListener("click", () => {
    const filter = document.getElementById("matrix-filter");
    if (filter) filter.value = "";
    renderMatrix();
  });
  document.getElementById("intake-filter")?.addEventListener("input", (event) => {
    state.intakeQuickFilter = "custom";
    state.intakeFilter = event.target.value;
    renderIntake();
  });
  document.getElementById("intake-sort")?.addEventListener("change", (event) => {
    state.intakeSort = event.target.value;
    renderIntake();
  });
  document.getElementById("intake-status-filter")?.addEventListener("change", (event) => {
    state.intakeQuickFilter = "custom";
    state.intakeStatusFilter = event.target.value;
    renderIntake();
  });
  document.querySelectorAll("[data-intake-quick-filter]").forEach((button) => {
    button.addEventListener("click", () => applyIntakeQuickFilter(button.dataset.intakeQuickFilter));
  });
  document.getElementById("incoming-run-fetch")?.addEventListener("click", async () => {
    try {
      await fetchFairWorkRegistryRun("incoming-run-fetch");
    } catch (error) {
      toast(`Registry fetch failed: ${apiErrorMessage(error)}`, "error");
    }
  });
  document.getElementById("audit-council-select")?.addEventListener("change", (event) => {
    const council = event.target.value;
    if (council) openWorkbenchRoute(`#audit/${encodeURIComponent(council)}`);
  });
  document.getElementById("audit-refresh")?.addEventListener("click", () => {
    renderCouncilAudit(state.auditCouncil || defaultAuditCouncil(), { force: true }).catch((error) => {
      toast(`Audit refresh failed: ${apiErrorMessage(error)}`, "error");
    });
  });
  document.getElementById("intake-freeze")?.addEventListener("click", () => {
    state.intakeQuickFilter = "custom";
    state.intakeStatusFilter = "all";
    state.intakeFilter = "pdf not fetched";
    const filter = document.getElementById("intake-status-filter");
    const search = document.getElementById("intake-filter");
    if (filter) filter.value = "all";
    if (search) search.value = state.intakeFilter;
    renderIntake();
    toast("Showing sources that need PDF fetch before QA", "success");
  });
  document.getElementById("intake-source-retry-btn")?.addEventListener("click", () => {
    applyIntakeQuickFilter("source_retry");
    toast("Showing fetched PDFs under 500 KB that need a source retry", "warning");
  });
  document.getElementById("intake-reconcile")?.addEventListener("click", () => {
    state.intakeQuickFilter = "custom";
    state.intakeStatusFilter = "all";
    state.intakeFilter = "scope check";
    const filter = document.getElementById("intake-status-filter");
    const search = document.getElementById("intake-filter");
    if (filter) filter.value = "all";
    if (search) search.value = state.intakeFilter;
    renderIntake();
  });
  document.getElementById("intake-promote")?.addEventListener("click", () => {
    state.intakeQuickFilter = "accepted";
    state.intakeStatusFilter = "accepted";
    state.intakeFilter = "";
    const filter = document.getElementById("intake-status-filter");
    const search = document.getElementById("intake-filter");
    if (filter) filter.value = "accepted";
    if (search) search.value = "";
    renderIntake();
    const staged = state.intakeRows.filter((item) => item.acceptance_state === "accepted" && !item.in_working_set).length;
    toast(staged ? `${formatCount(staged)} accepted sources still need promotion/fetch` : "Showing accepted governed sources", "success");
  });
  document.getElementById("council-select")?.addEventListener("change", (event) => openCouncil(event.target.value, state.currentSection || "overview"));
  document.getElementById("overview-btn")?.addEventListener("click", generateOverview);
}

async function init() {
  initViewer();
  renderCapabilityTree();
  wireShell();
  suppressWorkbenchRouteSync = true;
  applyInitialWorkbenchViewFromHash();
  suppressWorkbenchRouteSync = false;
  await refreshLlmStatus();
  await fetchCouncils();
  const routed = await applyWorkbenchRouteFromHash();
  if (!routed) syncWorkbenchRoute("capability");
  await renderLlmStatusPane();
  await renderRateCapAdminPane();
}

async function refreshLlmStatus() {
  try {
    state.llmStatus = await api("/api/llm/status");
  } catch (e) {
    state.llmStatus = {
      ready: false,
      text_capable: false,
      vision_capable: false,
      message: apiErrorMessage(e),
      provider: "unknown",
      model: "unknown",
      credential: "unknown",
    };
  }
  return state.llmStatus;
}

async function refreshConnectionSettings() {
  try {
    state.llmConnections = await api("/api/connections");
    state.llmStatus = state.llmConnections?.llm?.active || state.llmStatus;
  } catch (e) {
    const fallbackStatus = {
      ready: false,
      text_capable: false,
      vision_capable: false,
      message: apiErrorMessage(e),
      provider: "unknown",
      model: "unknown",
      credential: "unknown",
    };
    state.llmStatus = fallbackStatus;
    state.llmConnections = {
      llm: {
        active: fallbackStatus,
        providers: [],
      },
      env_file: null,
    };
  }
  return state.llmConnections;
}

function connectionReadinessLabel(status) {
  if (status?.ready && status?.vision_capable) return "Ready";
  if (status?.ready && status?.text_capable) return "Text only";
  if (status?.credential === "set") return "Key detected";
  return "Needs setup";
}

function connectionCardClass(provider) {
  const status = provider.status || {};
  if (provider.active && status.ready && status.vision_capable) return "connection-card-active connection-card-ready";
  if (provider.active) return "connection-card-active connection-card-attention";
  if (provider.adapter_state === "planned") return "connection-card-planned";
  if (status.ready) return "connection-card-ready";
  return "";
}

function credentialStateLabel(status) {
  if (status?.credential === "set") return "Configured";
  if (status?.credential === "managed") return "Managed";
  if (status?.credential === "unknown") return "Unknown";
  return "Missing";
}

function renderConnectionProviderCard(provider) {
  const status = provider.status || {};
  const active = Boolean(provider.active);
  const metaItems = [
    provider.description || "",
    active ? "Active" : "",
    provider.capability_label || "",
    `Model ${status.model || provider.default_model || DISPLAY_EMPTY}`,
    `Credential ${credentialStateLabel(status)}`,
    status.text_capable ? "Text available" : "Text blocked",
    status.vision_capable ? "Vision available" : "Vision blocked",
    provider.adapter_state === "planned" ? "Adapter planned" : "",
  ];
  const message = String(status.message || "").trim();
  return `
    <article class="connection-provider-card workbench-card-scaffold ${connectionCardClass(provider)}">
      <div class="connection-provider-main workbench-card-main">
      <div class="connection-provider-head workbench-card-title">
        <h4>${escapeHtml(provider.label || provider.id)}</h4>
        <span class="connection-status-pill">${escapeHtml(connectionReadinessLabel(status))}</span>
      </div>
      ${renderInlineMeta(metaItems, "connection-provider-meta workbench-inline-meta")}
      ${message ? `
        <details class="connection-provider-details workbench-card-details">
          <summary>Status note</summary>
          <p>${escapeHtml(message)}</p>
        </details>
      ` : ""}
      </div>
    </article>
  `;
}

function selectedConnectionProvider() {
  const providers = state.llmConnections?.llm?.providers || [];
  return providers.find((provider) => provider.active && provider.can_activate)
    || providers.find((provider) => provider.id === "anthropic")
    || providers.find((provider) => provider.can_activate)
    || null;
}

function updateConnectionFormFromSelection() {
  const providers = state.llmConnections?.llm?.providers || [];
  const providerSelect = document.getElementById("connection-provider");
  const modelInput = document.getElementById("connection-model");
  const keyRow = document.getElementById("connection-key-row");
  const saveButton = document.getElementById("connection-save");
  const selected = providers.find((provider) => provider.id === providerSelect?.value);
  if (modelInput && selected) {
    modelInput.value = selected.status?.model || selected.default_model || "";
    modelInput.disabled = !selected.can_activate;
  }
  if (keyRow) {
    keyRow.hidden = !selected?.credential_env;
  }
  if (saveButton) {
    saveButton.disabled = !selected?.can_activate;
  }
}

async function renderLlmStatusPane() {
  const container = document.getElementById("llm-status-container");
  if (!container) return;
  const connections = await refreshConnectionSettings();
  const status = connections.llm?.active || state.llmStatus || {};
  const providers = connections.llm?.providers || [];
  const currentProvider = selectedConnectionProvider();
  const ready = Boolean(status.ready && status.vision_capable);
  const statusLabel = ready ? "Ready for extraction" : connectionReadinessLabel(status);
  const envPath = connections.env_file?.path || ".env";
  const providerOptions = providers.map((provider) => `
    <option value="${escapeHtml(provider.id)}" ${provider.id === currentProvider?.id ? "selected" : ""} ${provider.can_activate ? "" : "disabled"}>
      ${escapeHtml(provider.label || provider.id)}${provider.can_activate ? "" : " (planned)"}
    </option>
  `).join("");
  container.innerHTML = `
    <div class="settings-card workbench-card-scaffold extraction-settings connection-settings ${ready ? "settings-ready" : "settings-attention"}">
      <div class="settings-card-main">
        <div class="settings-heading">
          <span class="settings-icon" aria-hidden="true"></span>
          <div>
            <div class="settings-kicker">Connections</div>
            <h3>LLM provider console</h3>
            <p>Provider readiness, model selection and local credentials for extraction.</p>
          </div>
        </div>
        <div class="settings-status ${ready ? "status-ready" : "status-attention"}">
          <span>${ready ? "Connected" : "Not connected"}</span>
          <strong>${escapeHtml(statusLabel)}</strong>
        </div>
      </div>
      <div class="settings-grid">
        <div><span>Active provider</span><strong>${escapeHtml(status.provider || "unknown")}</strong></div>
        <div><span>Model</span><strong>${escapeHtml(status.model || "unknown")}</strong></div>
        <div><span>Credential</span><strong>${escapeHtml(credentialStateLabel(status))}</strong></div>
        <div><span>Vision extraction</span><strong>${ready ? "Available" : "Blocked"}</strong></div>
      </div>
      <div class="settings-message ${ready ? "settings-message-ok" : "settings-message-warn"}">
        <strong>${ready ? "Ready" : "Action needed"}:</strong> ${escapeHtml(status.message || (ready ? "Vision extraction ready." : "Choose a supported provider and save local configuration."))}
      </div>
      <section class="connection-layout" aria-label="LLM provider connections">
        <div class="connection-provider-list">
          ${providers.length ? providers.map(renderConnectionProviderCard).join("") : `
            <div class="connection-empty">Connection registry unavailable.</div>
          `}
        </div>
        <form id="llm-connection-form" class="connection-form">
          <div>
            <div class="settings-kicker">Configure</div>
            <h4>Local extraction connection</h4>
          </div>
          <label>
            <span>Provider</span>
            <select id="connection-provider" name="provider" ${providers.length ? "" : "disabled"}>
              ${providerOptions}
            </select>
          </label>
          <label>
            <span>Model</span>
            <input id="connection-model" name="model" type="text" autocomplete="off" value="${escapeHtml(currentProvider?.status?.model || currentProvider?.default_model || "")}">
          </label>
          <label id="connection-key-row">
            <span>API key</span>
            <input id="connection-api-key" name="api_key" type="password" autocomplete="off" placeholder="${credentialStateLabel(currentProvider?.status) === "Configured" ? "Existing key retained" : "API key"}">
          </label>
          <div class="connection-env-path">
            <span>Local env file</span>
            <strong>${escapeHtml(envPath)}</strong>
          </div>
          <div class="settings-actions connection-actions">
            <button id="llm-status-refresh" type="button">Check connection</button>
            <button id="connection-save" class="primary" type="submit">Save connection</button>
          </div>
        </form>
      </section>
    </div>
  `;
  updateConnectionFormFromSelection();
  container.querySelector("#llm-status-refresh")?.addEventListener("click", renderLlmStatusPane);
  container.querySelector("#connection-provider")?.addEventListener("change", updateConnectionFormFromSelection);
  container.querySelector("#llm-connection-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const payload = {
      provider: formData.get("provider") || "",
      model: formData.get("model") || "",
      api_key: formData.get("api_key") || "",
    };
    try {
      const updated = await withBusyButton("connection-save", "Saving", () => api("/api/connections/llm", {
        method: "POST",
        body: JSON.stringify(payload),
      }));
      state.llmConnections = updated;
      state.llmStatus = updated?.llm?.active || state.llmStatus;
      await renderLlmStatusPane();
      toast("Connection saved", "success");
    } catch (error) {
      toast(`Connection save failed: ${apiErrorMessage(error)}`, "error");
    }
  });
}

async function renderRateCapAdminPane() {
  const container = document.getElementById("rate-cap-admin-container");
  if (!container) return;
  container.innerHTML = `<div class="card rate-cap-admin-card workbench-card-scaffold"><div class="muted">Loading rate cap status?</div></div>`;
  let data;
  try {
    data = await ensureRateCapStatus({ force: true });
  } catch (e) {
    container.innerHTML = `<div class="card rate-cap-admin-card workbench-card-scaffold"><div class="scenario-error">Failed to load: ${escapeHtml(String(e))}</div></div>`;
    return;
  }
  const years = Array.isArray(data.years) ? data.years : [];
  const pending = years.filter((y) => y.resolution_status !== "confirmed");
  const recentConfirmed = years
    .filter((y) => y.resolution_status === "confirmed")
    .slice(-5)
    .reverse();
  const rowHtml = (y) => `
    <tr>
      <td>${escapeHtml(y.financial_year)}</td>
      <td><span class="rate-cap-status-${escapeHtml(y.resolution_status)}">${escapeHtml(y.resolution_status)}</span></td>
      <td>${escapeHtml(displayPercent(y.standard_rate_cap_value))}</td>
      <td>${escapeHtml(displayDate(y.confirmed_date))}</td>
      <td>${escapeHtml(y.notes || "")}</td>
    </tr>
  `;
  const pendingRowsHtml = pending.length
    ? pending.map(rowHtml).join("")
    : `<tr><td colspan="5" class="muted">No pending years.</td></tr>`;
  const confirmedRowsHtml = recentConfirmed.map(rowHtml).join("");
  const formTargets = pending.map((y) => `<option value="${escapeHtml(y.financial_year)}">${escapeHtml(y.financial_year)}</option>`).join("");
  container.innerHTML = `
    <div class="card rate-cap-admin-card workbench-card-scaffold">
      <h3>Rate cap registry</h3>
      <div class="muted">Source: ESC annual council rate caps page (https://www.esc.vic.gov.au/local-government/annual-council-rate-caps)</div>
      <h4>Pending</h4>
      <table class="rate-cap-admin-table">
        <thead><tr><th>FY</th><th>Status</th><th>Cap</th><th>Confirmed</th><th>Notes</th></tr></thead>
        <tbody>${pendingRowsHtml}</tbody>
      </table>
      ${pending.length ? `
      <form class="rate-cap-confirm-form" id="rate-cap-confirm-form">
        <label>FY <select name="financial_year" required>${formTargets}</select></label>
        <label>Cap % <input type="number" name="rate_cap_value" step="0.01" min="0" required /></label>
        <label>Confirmed <input type="date" name="confirmed_date" required /></label>
        <input type="text" name="notes" placeholder="Notes (optional)" />
        <button type="submit" class="rate-cap-confirm-btn">Confirm</button>
        <div class="rate-cap-confirm-msg" id="rate-cap-confirm-msg"></div>
      </form>
      ` : ""}
      <h4 style="margin-top:1rem;">Recently confirmed</h4>
      <table class="rate-cap-admin-table">
        <thead><tr><th>FY</th><th>Status</th><th>Cap</th><th>Confirmed</th><th>Notes</th></tr></thead>
        <tbody>${confirmedRowsHtml || `<tr><td colspan="5" class="muted">?</td></tr>`}</tbody>
      </table>
    </div>
  `;
  const form = document.getElementById("rate-cap-confirm-form");
  if (form) {
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const msg = document.getElementById("rate-cap-confirm-msg");
      msg.className = "rate-cap-confirm-msg";
      msg.textContent = "Saving?";
      const fd = new FormData(form);
      const payload = {
        financial_year: fd.get("financial_year"),
        rate_cap_value: Number(fd.get("rate_cap_value")),
        confirmed_date: fd.get("confirmed_date"),
        notes: fd.get("notes") || "",
      };
      try {
        const body = await api("/api/rate-caps/confirm", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (!body.ok) throw new Error(body.error || "Rate-cap confirmation failed.");
        msg.classList.add("rate-cap-confirm-msg-ok");
        msg.textContent = `Confirmed ${body.financial_year} at ${displayPercent(body.rate_cap_value)}`;
        await renderRateCapAdminPane();
      } catch (e) {
        msg.classList.add("rate-cap-confirm-msg-err");
        msg.textContent = `Error: ${apiErrorMessage(e)}`;
      }
    });
  }
}

init().catch((error) => {
  console.error(error);
  toast(`Init failed: ${error.message}`, "error");
});
