import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const body = await req.json()
  const upstream = await fetch(`${gaaiaApiBase()}/video/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: `${COOKIE}=${token}` },
    body: JSON.stringify({
      video_source: body.video_source || "",
      frame_count: body.frame_count ?? 5,
      focus: body.focus || "all",
      question: body.question || "",
    }),
  })

  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text() || "Upstream error", { status: upstream.status || 502 })
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  })
}
