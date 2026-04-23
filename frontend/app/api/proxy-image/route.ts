import { NextRequest, NextResponse } from "next/server"

export const runtime = "nodejs"

const ALLOWED_MIME = new Set([
  "image/jpeg", "image/png", "image/webp", "image/gif",
  "image/svg+xml", "image/avif",
])

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url")
  if (!url || !url.startsWith("http")) {
    return new NextResponse("Missing or invalid url param", { status: 400 })
  }

  try {
    const upstream = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; NovaAgent/1.0)",
        "Accept": "image/*,*/*;q=0.8",
        // No Referer — bypasses most hotlink protection
      },
      redirect: "follow",
      signal: AbortSignal.timeout(8000),
    })

    const contentType = upstream.headers.get("content-type") ?? ""
    const mime = contentType.split(";")[0].trim()

    if (!upstream.ok || !ALLOWED_MIME.has(mime)) {
      return new NextResponse("Image unavailable", { status: 502 })
    }

    const body = await upstream.arrayBuffer()

    return new NextResponse(body, {
      status: 200,
      headers: {
        "Content-Type": mime,
        "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
        "Access-Control-Allow-Origin": "*",
      },
    })
  } catch {
    return new NextResponse("Fetch failed", { status: 502 })
  }
}
