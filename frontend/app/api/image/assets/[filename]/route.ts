import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ filename: string }> },
) {
  const { filename } = await params
  try {
    const upstream = await fetch(`${gaaiaApiBase()}/image/assets/${encodeURIComponent(filename)}`, {
      headers: { "Cache-Control": "no-cache" },
    })
    if (!upstream.ok) return new Response("Not found", { status: 404 })
    return new Response(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    })
  } catch {
    return new Response("Failed to fetch image asset", { status: 500 })
  }
}
