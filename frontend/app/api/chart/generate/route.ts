import { NextRequest, NextResponse } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const body = await req.json()

  const res = await fetch(`${gaaiaApiBase()}/chart/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Cookie: `${COOKIE}=${token}` } : {}),
    },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const text = await res.text()
    return new NextResponse(text, { status: res.status })
  }

  const blob = await res.blob()
  return new NextResponse(blob, {
    status: 200,
    headers: { "Content-Type": "image/png" },
  })
}
