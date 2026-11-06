/**
 * Owner session persistence.
 *
 * "Remember me" keeps the session in localStorage until it expires; otherwise it is
 * kept in sessionStorage and disappears when the tab is closed. Expired or malformed
 * entries are discarded. The backend still validates every token on every request.
 */
import { z } from "zod";

export const SESSION_KEY = "ownerSession";
export const REMEMBERED_USER_KEY = "ownerRememberedUsername";

const sessionSchema = z.object({ token: z.string().min(1), expiresAt: z.number().int().positive(), username: z.string() });
export type OwnerSession = z.infer<typeof sessionSchema>;

function stores(): Storage[] {
  const result: Storage[] = [];
  try { result.push(window.localStorage); } catch { /* Storage blocked: fall back to memory only. */ }
  try { result.push(window.sessionStorage); } catch { /* Storage blocked: fall back to memory only. */ }
  return result;
}

function read(store: Storage, key: string): string | null {
  try { return store.getItem(key); } catch { return null; }
}

export function loadSession(now = Date.now()): OwnerSession | null {
  for (const store of stores()) {
    const raw = read(store, SESSION_KEY);
    if (!raw) continue;
    try {
      const session = sessionSchema.parse(JSON.parse(raw));
      if (session.expiresAt > now) return session;
    } catch { /* Malformed entry: discard below. */ }
    try { store.removeItem(SESSION_KEY); } catch { /* Ignore. */ }
  }
  return null;
}

export function saveSession(session: OwnerSession, remember: boolean): void {
  clearSession();
  const local = safeLocal();
  const target = remember ? local : safeSession();
  try { target?.setItem(SESSION_KEY, JSON.stringify(session)); } catch { /* Quota or blocked: session stays in memory. */ }
  try {
    if (remember) local?.setItem(REMEMBERED_USER_KEY, session.username);
    else local?.removeItem(REMEMBERED_USER_KEY);
  } catch { /* Ignore. */ }
}

export function clearSession(): void {
  for (const store of stores()) { try { store.removeItem(SESSION_KEY); } catch { /* Ignore. */ } }
}

export function rememberedUsername(): string {
  const local = safeLocal();
  return (local && read(local, REMEMBERED_USER_KEY)) || "";
}

function safeLocal(): Storage | null { try { return window.localStorage; } catch { return null; } }
function safeSession(): Storage | null { try { return window.sessionStorage; } catch { return null; } }
