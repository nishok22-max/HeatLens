import type { HeatData } from "./types";
import type { DatasetKey } from "./data";
import { API_ORIGIN, DATASETS, fetchDataset } from "./data";

/**
 * HEATSHIELD frontend-to-backend service layer.
 *
 * Speaks to the FastAPI app in `api/main.py` (`uvicorn api.main:app --port 8000`),
 * which is the only backend: it owns the five-minute live refresh loop, so it is
 * the only one whose Forecast numbers actually move.
 *
 * The transport lives in `data.ts` (`fetchDataset`) so the route names exist in
 * exactly one place. This module adds the two things the UI needs on top of it:
 * a liveness probe, and a fetch that degrades to the bundled floor instead of
 * throwing.
 */

/** Re-exported from `data.ts`, which owns the single definition. */
export const API_BASE_URL = API_ORIGIN;

export interface BackendStatus {
  connected: boolean;
  serverName?: string;
  version?: string;
  city?: string;
  /** IST timestamp of the last live recompute, or null if none has run yet. */
  liveRefreshedAt?: string | null;
  lastChecked: string;
  error?: string;
}

/** Fetch with a deadline, so an unreachable API fails fast instead of hanging
 *  the UI behind a TCP timeout on stage. */
async function withTimeout(url: string, ms: number): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Health check ping to verify backend connectivity.
 */
export async function checkBackendHealth(): Promise<BackendStatus> {
  try {
    const res = await withTimeout(`${API_BASE_URL}/api/health`, 3000);

    if (res.ok) {
      const data = await res.json();
      return {
        connected: true,
        serverName: data.server,
        version: data.version,
        city: data.city,
        liveRefreshedAt: data.live_refreshed_at ?? null,
        lastChecked: new Date().toLocaleTimeString(),
      };
    }
    return {
      connected: false,
      lastChecked: new Date().toLocaleTimeString(),
      error: `Server returned status ${res.status}`,
    };
  } catch (err: unknown) {
    const errMsg = err instanceof Error ? err.message : "Backend server unreachable";
    return {
      connected: false,
      lastChecked: new Date().toLocaleTimeString(),
      error: errMsg,
    };
  }
}

/**
 * Fetch a complete HeatData payload from the backend, falling back to the
 * bundled copy. The fallback is not an error path: it is what NFR-1 (open the
 * page from a USB stick, wifi off) requires, so a failure here downgrades the
 * badge and nothing else.
 */
export async function fetchHeatDataFromAPI(
  dataset: DatasetKey,
): Promise<{ data: HeatData; fromBackend: boolean; error?: string }> {
  try {
    return { data: await fetchDataset(dataset), fromBackend: true };
  } catch (err: unknown) {
    const errMsg = err instanceof Error ? err.message : "Network error";
    return {
      data: DATASETS[dataset].data,
      fromBackend: false,
      error: errMsg,
    };
  }
}
