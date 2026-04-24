import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params
  const url = new URL(req.url)
  const limit = url.searchParams.get("n") || "2000"
  const token = req.cookies.get("nova_token")?.value
  const upstream = await fetch(
    `${NOVA_API_BASE}/memory/history/${encodeURIComponent(sessionId)}?n=${encodeURIComponent(limit)}`,
    { headers: token ? { Cookie: `nova_token=${token}` } : {} },
  )
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}
