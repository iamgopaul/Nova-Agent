import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const upstream = await fetch(`${NOVA_API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })

  const text = await upstream.text()
  const setCookie = upstream.headers.get("set-cookie")

  const headers: Record<string, string> = {
    "Content-Type": upstream.headers.get("content-type") || "application/json",
  }
  if (setCookie) headers["Set-Cookie"] = setCookie

  return new Response(text, { status: upstream.status, headers })
}
