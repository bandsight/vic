export const DISPLAY_EMPTY = "Not stated";

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATETIME_RE = /^(\d{4}-\d{2}-\d{2})[T ]/;
const HIDDEN_CODE_LABELS = new Set(["title_only_unresolved"]);

export function displayValue(value, empty = DISPLAY_EMPTY) {
  if (value === null || value === undefined || value === "") return empty;
  if (Array.isArray(value)) {
    const values = value.map((item) => displayValue(item, "")).filter(Boolean);
    return values.length ? values.join(", ") : empty;
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

export function displayCodeLabel(value, empty = DISPLAY_EMPTY) {
  const raw = displayValue(value, empty);
  if (HIDDEN_CODE_LABELS.has(raw)) return empty;
  return raw === empty ? raw : raw.replaceAll("_", " ");
}

export function displayDate(value, empty = DISPLAY_EMPTY) {
  const raw = displayValue(value, "").trim();
  if (!raw) return empty;
  const datetimeMatch = raw.match(ISO_DATETIME_RE);
  if (datetimeMatch) return datetimeMatch[1];
  return raw;
}

export function displayDateRange(start, end, empty = "Dates not stated") {
  const from = displayDate(start, "");
  const to = displayDate(end, "");
  if (from && to) return `${from} to ${to}`;
  if (from) return `${from} to open ended`;
  if (to) return `Until ${to}`;
  return empty;
}

export function displayPages(value, empty = DISPLAY_EMPTY) {
  const pages = Array.isArray(value) ? value : (value === null || value === undefined || value === "" ? [] : [value]);
  const clean = pages.map((page) => String(page).trim()).filter(Boolean);
  if (!clean.length) return empty;
  return `${clean.length === 1 ? "p." : "pp."} ${clean.join(", ")}`;
}

export function displayNumber(value, empty = DISPLAY_EMPTY, options = {}) {
  if (value === null || value === undefined || value === "") return empty;
  const number = Number(String(value).replace(/,/g, ""));
  if (!Number.isFinite(number)) return String(value);
  return number.toLocaleString("en-AU", options);
}

export function displayCurrency(value, empty = DISPLAY_EMPTY) {
  if (value === null || value === undefined || value === "") return empty;
  const number = Number(String(value).replace(/[$,]/g, ""));
  if (!Number.isFinite(number)) return String(value);
  return `A$${number.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function displayCurrencyDelta(value, empty = DISPLAY_EMPTY) {
  if (value === null || value === undefined || value === "") return empty;
  const number = Number(String(value).replace(/[$,]/g, ""));
  if (!Number.isFinite(number)) return String(value);
  const sign = number >= 0 ? "+" : "-";
  return `${sign}${displayCurrency(Math.abs(number), empty)}`;
}

export function displayPercent(value, empty = DISPLAY_EMPTY) {
  if (value === null || value === undefined || value === "") return empty;
  const number = Number(String(value).replace("%", ""));
  if (!Number.isFinite(number)) return String(value);
  return `${Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}%`;
}

export function displayFractionPercent(value, empty = DISPLAY_EMPTY) {
  if (value === null || value === undefined || value === "") return empty;
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return displayPercent(number * 100, empty);
}

export function displayPercentDelta(value, empty = DISPLAY_EMPTY, { fraction = false } = {}) {
  if (value === null || value === undefined || value === "") return empty;
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  const percentValue = fraction ? Math.abs(number) * 100 : Math.abs(number);
  const sign = number >= 0 ? "+" : "-";
  return `${sign}${displayPercent(percentValue, empty)}`;
}

export function displayFileSize(value, empty = DISPLAY_EMPTY) {
  const size = Number(value);
  if (!Number.isFinite(size) || size < 0) return empty;
  if (size < 1024) return `${size} B`;
  const units = ["KB", "MB", "GB"];
  let current = size / 1024;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }
  return `${current >= 10 ? current.toFixed(0) : current.toFixed(1)} ${units[unitIndex]}`;
}

export function displayHtml(value, escapeHtml, empty = DISPLAY_EMPTY) {
  return escapeHtml(displayValue(value, empty));
}

export function isIsoDate(value) {
  return ISO_DATE_RE.test(value || "");
}
