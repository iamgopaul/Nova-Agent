import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"


export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params
  const url = new URL(req.url)
  const limit = url.searchParams.get("n") || "2000"
  const token = req.cookies.get("gaaia_token")?.value
  const upstream = await fetch(
    `${gaaiaApiBase()}/memory/history/${encodeURIComponent(sessionId)}?n=${encodeURIComponent(limit)}`,
    { headers: token ? { Cookie: `gaaia_token=${token}` } : {} },
  )
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}
