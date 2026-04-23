import { NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const res = await fetch(`${BACKEND}/chart/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
