/**
 * Base URL for the GAAIA FastAPI server (used by Next.js route handlers to proxy).
 *
 * Must NOT include a trailing slash or a `/api` suffix — routes are mounted at
 * `/voice`, `/chat`, `/memory`, etc. on the server root (e.g. http://127.0.0.1:8765/voice/stream).
 */
export function gaaiaApiBase(): string {
  const raw = (process.env.GAAIA_API_BASE || "http://127.0.0.1:8765").trim()
  let base = raw.replace(/\/+$/, "")
  if (base.toLowerCase().endsWith("/api")) {
    base = base.slice(0, -4).replace(/\/+$/, "")
  }
  return base || "http://127.0.0.1:8765"
}
