import { api, apiErrorMessage } from "/static/api-client.js";

export const REPORT_EXPORT_ENDPOINT = "/api/analysis/distribution-point-analysis/exports";
const REPORT_ASSET_STATUS_ENDPOINT = "/api/analysis/distribution-point-analysis/report-asset/status";

export function createReportExportState() {
  return {
    reportExportCatalog: null,
    reportExportCatalogLoad: null,
    reportExportResult: null,
    reportExportError: "",
  };
}

export async function ensureReportExportCatalog(state, { force = false } = {}) {
  if (!force && state.reportExportCatalog) return state.reportExportCatalog;
  if (!force && state.reportExportCatalogLoad) return state.reportExportCatalogLoad;
  state.reportExportError = "";
  state.reportExportCatalogLoad = api(REPORT_EXPORT_ENDPOINT)
    .then((catalog) => {
      state.reportExportCatalog = catalog;
      return catalog;
    })
    .catch((error) => {
      state.reportExportError = apiErrorMessage(error);
      throw error;
    })
    .finally(() => {
      state.reportExportCatalogLoad = null;
    });
  return state.reportExportCatalogLoad;
}

export function resetReportExportState(state) {
  state.reportExportCatalog = null;
  state.reportExportResult = null;
}

export function reportExportAsset(state) {
  return state.reportExportCatalog?.assets?.[0] || null;
}

export function reportExportDownloadHref(format) {
  return `${REPORT_EXPORT_ENDPOINT}/${encodeURIComponent(format)}`;
}

export async function updateReportAssetStatus(state, status) {
  const result = await api(REPORT_ASSET_STATUS_ENDPOINT, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
  await ensureReportExportCatalog(state, { force: true });
  return result;
}
