import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  try {
    const token = req.cookies.get(COOKIE)?.value
    if (!token) {
      return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
    }

    const body = await req.json()

    const upstream = await fetch(`${novaApiBase()}/image/generate`, {
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
