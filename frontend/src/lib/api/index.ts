/**
 * Backend client — the single integration point.
 *
 * If the backend URL or any endpoint changes, this file is the only thing to
 * edit. Components depend on the three exported functions, not on `fetch`.
 */

import type {
  AnalysisCreatedResponse,
  AnalysisResult,
  ProgressEvent,
} from "@/types/analysis";

import { ApiError } from "./errors";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

export const apiBaseUrl = API_BASE;

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (res.ok) {
    return (await res.json()) as T;
  }
  let body: { error?: string; code?: string; details?: Record<string, unknown> } = {};
  try {
    body = await res.json();
  } catch {
    // server returned non-JSON
  }
  throw new ApiError(
    res.status,
    body.code ?? "HTTP_ERROR",
    body.error ?? `요청이 실패했습니다 (HTTP ${res.status})`,
    body.details ?? null,
  );
}

// ── 1. POST /api/analyze ───────────────────────────────────────────────────

export async function startAnalysis(url: string, token?: string): Promise<AnalysisCreatedResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify({ url }),
  });
  return jsonOrThrow<AnalysisCreatedResponse>(res);
}

// ── 2. GET /api/analyze/{id}/progress (polling fallback) ───────────────────

export async function fetchProgress(analysisId: string): Promise<ProgressEvent> {
  const res = await fetch(`${API_BASE}/api/analyze/${analysisId}/progress`, {
    cache: "no-store",
  });
  return jsonOrThrow<ProgressEvent>(res);
}

// ── 3. GET /api/analyze/{id}/result ────────────────────────────────────────

export async function fetchResult(analysisId: string): Promise<AnalysisResult> {
  const res = await fetch(`${API_BASE}/api/analyze/${analysisId}/result`, {
    cache: "no-store",
  });
  return jsonOrThrow<AnalysisResult>(res);
}

// ── 4. GET /api/analyze/{id}/stream (SSE) ──────────────────────────────────

export interface ProgressStreamHandlers {
  onProgress?: (event: ProgressEvent) => void;
  onComplete?: (event: ProgressEvent) => void;
  onError?: (error: ProgressStreamError) => void;
}

export type ProgressStreamError =
  | { kind: "server"; event: ProgressEvent & { message?: string } }
  | { kind: "transport"; error: Event };

/**
 * Open an EventSource against the SSE stream. Returns a `close()` function;
 * call it in your effect cleanup.
 *
 * Falls back to polling is the caller's responsibility — the `transport`
 * error variant signals when to switch.
 */
export function openProgressStream(
  analysisId: string,
  handlers: ProgressStreamHandlers,
): () => void {
  const url = `${API_BASE}/api/analyze/${analysisId}/stream`;
  const source = new EventSource(url);

  const parse = (ev: MessageEvent): ProgressEvent | null => {
    try {
      return JSON.parse(ev.data) as ProgressEvent;
    } catch {
      return null;
    }
  };

  source.addEventListener("progress", (ev) => {
    const parsed = parse(ev as MessageEvent);
    if (parsed) handlers.onProgress?.(parsed);
  });

  source.addEventListener("complete", (ev) => {
    const parsed = parse(ev as MessageEvent);
    if (parsed) handlers.onComplete?.(parsed);
    source.close();
  });

  source.addEventListener("error", (ev) => {
    // SSE delivers two kinds of `error`:
    //   1. server-sent named `event: error` with a JSON payload → ev is MessageEvent
    //   2. transport-level disconnect → ev is plain Event with readyState === CLOSED
    if (ev instanceof MessageEvent && ev.data) {
      const parsed = parse(ev);
      if (parsed) {
        handlers.onError?.({ kind: "server", event: parsed });
        source.close();
        return;
      }
    }
    handlers.onError?.({ kind: "transport", error: ev });
  });

  return () => source.close();
}
