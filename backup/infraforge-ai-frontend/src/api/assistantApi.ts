// ---------------------------------------------------------------------------
// Thin, typed client for the Infra AI-Assistant FastAPI backend.
//
// All machine data comes from the backend — the frontend never fabricates
// results. Every helper returns the raw ApiResponse envelope so callers can
// branch on `success` and show clean errors.
// ---------------------------------------------------------------------------

import type {
  ApiResponse,
  ChatData,
  CompareResult,
  DealScoreResult,
  ImageSearchData,
  Machine,
  PriceInsightResult,
  RagAnswer,
} from "../types";

export const API_BASE_URL: string =
  (import.meta.env && import.meta.env.VITE_API_BASE_URL) ||
  "http://127.0.0.1:8000";

/** Thrown when the backend cannot be reached at all (server offline, CORS, DNS). */
export class BackendUnreachableError extends Error {
  constructor(message = "Backend not reachable") {
    super(message);
    this.name = "BackendUnreachableError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResponse<T>> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    // Network-level failure: server down, refused connection, CORS block.
    throw new BackendUnreachableError(
      "Backend not reachable. Make sure the API is running at " + API_BASE_URL,
    );
  }

  // The backend returns its standard envelope even on handled errors, so we
  // try to parse JSON regardless of status code.
  let body: ApiResponse<T>;
  try {
    body = (await res.json()) as ApiResponse<T>;
  } catch {
    throw new BackendUnreachableError(
      `Backend returned a non-JSON response (HTTP ${res.status}).`,
    );
  }

  return body;
}

// --- Health -----------------------------------------------------------------

export function checkHealth(): Promise<ApiResponse<{ status: string; database: string }>> {
  return request<{ status: string; database: string }>("/health");
}

// --- Text chat --------------------------------------------------------------

export function sendChat(
  sessionId: string,
  message: string,
): Promise<ApiResponse<ChatData>> {
  return request<ChatData>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

// --- Voice ------------------------------------------------------------------

export function sendVoiceChat(
  sessionId: string,
  file: File,
): Promise<ApiResponse<ChatData>> {
  const form = new FormData();
  form.append("session_id", sessionId);
  form.append("file", file);
  return request<ChatData>("/voice/chat", { method: "POST", body: form });
}

// --- Image search -----------------------------------------------------------

export function imageSearch(
  file: File,
  sessionId?: string,
): Promise<ApiResponse<ImageSearchData>> {
  const form = new FormData();
  form.append("file", file);
  if (sessionId) {
    form.append("session_id", sessionId);
  }
  return request<ImageSearchData>("/image-search", {
    method: "POST",
    body: form,
  });
}

// --- Friendly aliases (stable public names used across the UI) --------------

/** Alias of {@link sendChat}. */
export const sendChatMessage = sendChat;

/** Alias of {@link imageSearch}. */
export const sendImageSearch = imageSearch;

// --- RAG document Q&A -------------------------------------------------------

export function ragUploadText(
  text: string,
): Promise<ApiResponse<{ chunks_added: number; total_chunks: number }>> {
  return request<{ chunks_added: number; total_chunks: number }>("/rag/upload-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

export function ragUploadPdf(
  file: File,
): Promise<ApiResponse<{ file_name: string; chunks_added: number; total_chunks: number }>> {
  const form = new FormData();
  form.append("file", file);
  return request<{ file_name: string; chunks_added: number; total_chunks: number }>(
    "/rag/upload-pdf",
    { method: "POST", body: form },
  );
}

export function ragAsk(question: string): Promise<ApiResponse<RagAnswer>> {
  return request<RagAnswer>("/rag/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

// --- Support requests -------------------------------------------------------

export interface SupportRequestPayload {
  session_id: string;
  name: string;
  mobile: string;
  order_id?: string;
  issue_type?: string;
  message: string;
}

export function submitSupportRequest(
  payload: SupportRequestPayload,
): Promise<ApiResponse<{ request_id?: string }>> {
  return request<{ request_id?: string }>("/support/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// --- Per-machine intelligence ----------------------------------------------

export function compareMachines(
  machine1Id: string,
  machine2Id: string,
): Promise<ApiResponse<CompareResult>> {
  const qs = new URLSearchParams({
    machine1_id: machine1Id,
    machine2_id: machine2Id,
  });
  return request<CompareResult>(`/compare-machines?${qs.toString()}`);
}

export function getPriceInsight(
  machineId: string,
): Promise<ApiResponse<PriceInsightResult>> {
  return request<PriceInsightResult>(`/price-insight/${encodeURIComponent(machineId)}`);
}

export function getDealScore(
  machineId: string,
): Promise<ApiResponse<DealScoreResult>> {
  return request<DealScoreResult>(`/deal-score/${encodeURIComponent(machineId)}`);
}

export function getRecommendations(
  machineId: string,
): Promise<ApiResponse<{ machine_id: string; count: number; recommendations: Machine[] }>> {
  const safeId = encodeURIComponent(machineId);
  return request<{ machine_id: string; count: number; recommendations: Machine[] }>(
    `/machines/${safeId}/recommendations`,
  );
}
