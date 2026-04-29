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
    // Use realistic browser headers — Wikipedia, Wikimedia, and most CDNs
    // check User-Agent + Referer and block bare API-looking requests.
    const upstream = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(12000),
    })

    const contentType = upstream.headers.get("content-type") ?? ""
    const mime = contentType.split(";")[0].trim()

    // Some hosts return text/html on redirect failures — treat as unavailable
    if (!upstream.ok || (!ALLOWED_MIME.has(mime) && mime !== "application/octet-stream")) {
      return new NextResponse("Image unavailable", { status: 502 })
    }

    // Normalise octet-stream to the likely type based on URL extension
    const resolvedMime = mime === "application/octet-stream"
      ? (url.match(/\.(png)$/i) ? "image/png"
        : url.match(/\.(gif)$/i) ? "image/gif"
        : url.match(/\.(webp)$/i) ? "image/webp"
        : "image/jpeg")
      : mime

    const body = await upstream.arrayBuffer()

    return new NextResponse(body, {
      status: 200,
      headers: {
        "Content-Type": resolvedMime,
        "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
        "Access-Control-Allow-Origin": "*",
      },
    })
  } catch {
    return new NextResponse("Fetch failed", { status: 502 })
  }
}
