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

    const upstream = await fetch(`${gaaiaApiBase()}/music/generate`, {
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

    const audioBuffer = await upstream.arrayBuffer()
    return new Response(audioBuffer, {
      status: 200,
      headers: {
        "Content-Type": "audio/wav",
        "Content-Disposition": "inline; filename=gaaia_beat.wav",
      },
    })
  } catch (err) {
    return new Response(`Music generation failed: ${err}`, { status: 500 })
  }
}
