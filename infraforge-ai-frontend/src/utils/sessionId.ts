/** Browser session key — per-tab only (never localStorage: Chrome sync shares that across devices). */
export const SESSION_STORAGE_KEY = "infraforge_session_id";

/** Legacy key — removed on load so synced browsers stop sharing one session. */
const LEGACY_LOCAL_KEY = "infraforge_session_id";

export function createSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `sess_${crypto.randomUUID()}`;
  }
  return `sess_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 11)}`;
}

/**
 * Each browser tab gets its own session id. Not shared across devices or browser profiles.
 */
export function loadSessionId(): string {
  try {
    const existing = sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (existing?.trim()) {
      return existing.trim();
    }
  } catch {
    /* sessionStorage may be unavailable */
  }

  const fresh = createSessionId();
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, fresh);
    // Stop cross-device bleed from older builds that used localStorage (browser sync).
    localStorage.removeItem(LEGACY_LOCAL_KEY);
  } catch {
    /* ignore */
  }
  return fresh;
}

export function persistSessionId(sessionId: string): void {
  try {
    sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    localStorage.removeItem(LEGACY_LOCAL_KEY);
  } catch {
    /* ignore */
  }
}
