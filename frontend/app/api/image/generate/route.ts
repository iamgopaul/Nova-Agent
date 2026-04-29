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

    const upstream = await fetch(`${gaaiaApiBase()}/image/generate`, {
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
    const assetUrl    = upstream.headers.get("X-GAAIA-Asset-URL") ?? ""
    return new Response(imageBuffer, {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Content-Disposition": "inline; filename=gaaia_image.png",
        ...(assetUrl ? { "X-GAAIA-Asset-URL": assetUrl } : {}),
      },
    })
  } catch (err) {
    return new Response(`Image generation failed: ${err}`, { status: 500 })
  }
}
