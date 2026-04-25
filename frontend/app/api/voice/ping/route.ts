import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

/** Proxies to FastAPI GET /voice/ping — use to verify the Python API is reachable and the voice router is mounted. */
export async function GET() {
  const upstream = await fetch(`${novaApiBase()}/voice/ping`, { method: "GET" })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}
