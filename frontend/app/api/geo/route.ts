import { NextRequest, NextResponse } from "next/server"

export async function POST(req: NextRequest) {
  try {
    const { lat, lon } = await req.json()
    if (typeof lat !== "number" || typeof lon !== "number") {
      return NextResponse.json({ error: "lat and lon required" }, { status: 400 })
    }

    const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`
    const res = await fetch(url, {
      headers: { "User-Agent": "GAAIA/1.0 (joshgopaul91@gmail.com)" },
      signal: AbortSignal.timeout(5000),
    })

    if (!res.ok) {
      return NextResponse.json({ error: "Nominatim error" }, { status: 502 })
    }

    const data = await res.json()
    const addr = data.address ?? {}
    const city =
      addr.city || addr.town || addr.village || addr.county || addr.municipality || ""
    const region = addr.state || addr.province || ""
    const country = addr.country || ""
    const countryCode = (addr.country_code || "").toUpperCase()

    return NextResponse.json({ city, region, country, countryCode, lat, lon })
  } catch {
    return NextResponse.json({ error: "Geocode failed" }, { status: 500 })
  }
}
