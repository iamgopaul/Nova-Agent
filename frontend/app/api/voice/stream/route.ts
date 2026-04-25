import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })
  }

  const form = await req.formData()

  // Forward to FastAPI's /voice/stream. We keep the stream body flowing
  // through so NDJSON events arrive at the browser the moment the Python
  // side yields them — no intermediate buffering.
  const upstream = await fetch(`${novaApiBase()}/voice/stream`, {
    method: "POST",
    headers: { Cookie: `${COOKIE}=${token}` },
    body: form,
  })

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "")
    const hint =
      upstream.status === 404
        ? " Nova API returned 404 — set NOVA_API_BASE to the Python server root (e.g. http://127.0.0.1:8765) with no /api suffix, then restart Next.js."
        : ""
    return new Response(
      text ||
        JSON.stringify({
          detail: `Voice stream failed (${upstream.status}).${hint}`,
        }),
      {
        status: upstream.status || 500,
        headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
      },
    )
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "application/x-ndjson",
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
    },
  })
}
