import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()

    const upstream = await fetch(`${NOVA_API_BASE}/image/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    if (!upstream.ok) {
      const errText = await upstream.text()
      return new Response(errText, { status: upstream.status })
    }

    const imageBuffer = await upstream.arrayBuffer()
    return new Response(imageBuffer, {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Content-Disposition": "inline; filename=nova_image.png",
      },
    })
  } catch (err) {
    return new Response(`Image generation failed: ${err}`, { status: 500 })
  }
}
