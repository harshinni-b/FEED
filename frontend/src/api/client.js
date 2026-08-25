const API_BASE = "/api";
const DEFAULT_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  constructor(message, { status, detail, cause } = {}) {
    super(message, { cause });
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, { method = "GET", body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const cancel = () => controller.abort();
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    const response = await fetch(path === "/health" ? path : `${API_BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail;
      throw new ApiError(typeof detail === "string" ? detail : `Request failed (${response.status})`, { status: response.status, detail });
    }
    return payload;
  } catch (error) {
    if (error.name === "AbortError") throw new ApiError("The EDOCA request timed out. Please try again.", { cause: error });
    if (error instanceof ApiError) throw error;
    throw new ApiError("Unable to reach the EDOCA API. Check that the backend is running.", { cause: error });
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", cancel);
  }
}

function queryString(filters = {}) {
  const parameters = new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== undefined && value !== null && value !== ""));
  return parameters.size ? `?${parameters}` : "";
}

export const analyzeQuery = (query, options) => request("/analyze", { ...options, method: "POST", body: { query } });
export const getFindings = (filters = {}, options) => request(`/findings${queryString(filters)}`, options);
export const getFinding = (findingId, options) => request(`/findings/${encodeURIComponent(findingId)}`, options);
export const updateFindingReview = (findingId, review, options) => request(`/findings/${encodeURIComponent(findingId)}/review`, { ...options, method: "PATCH", body: review });
export const addFindingComment = (findingId, comment, options) => request(`/findings/${encodeURIComponent(findingId)}/comments`, { ...options, method: "POST", body: typeof comment === "string" ? { reviewer: "Engineer", comment } : comment });
export const getGraphContext = (entity, depth = 1, { includeContext = false, ...options } = {}) => request(`/graph/${encodeURIComponent(entity)}?depth=${depth}&include_context=${includeContext}`, options);
export const runImpactAnalysis = (payload, options) => request("/impact-analysis", { ...options, method: "POST", body: payload });
export const getHealth = options => request("/health", options);
