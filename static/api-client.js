export async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response.text();
}

export function apiErrorMessage(error) {
  const raw = error?.message || String(error || "");
  try {
    const parsed = JSON.parse(raw);
    const detail = parsed.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      return [detail.message, detail.reason].filter(Boolean).join(" ");
    }
  } catch {
    // Fall back to the original message.
  }
  return raw;
}
