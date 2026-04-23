import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    const upstream = await fetch(`${NOVA_API_BASE}/music/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
        "Content-Disposition": "inline; filename=nova_beat.wav",
      },
    })
  } catch (err) {
    return new Response(`Music generation failed: ${err}`, { status: 500 })
  }
}
