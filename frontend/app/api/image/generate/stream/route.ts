import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function POST(req: NextRequest) {
  try {
    const token = req.cookies.get(COOKIE)?.value
    if (!token) {
      return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
    }

    const body = await req.json()

    const upstream = await fetch(`${gaaiaApiBase()}/image/generate/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: `${COOKIE}=${token}`,
      },
      body: JSON.stringify(body),
    })

    if (!upstream.ok) {
      const errText = await upstream.text()
      return new Response(errText, { status: upstream.status })
    }

    return new Response(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
      },
    })
  } catch (err) {
    return new Response(`Image stream failed: ${err}`, { status: 500 })
  }
}
