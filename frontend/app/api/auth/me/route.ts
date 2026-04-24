import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function GET(req: NextRequest) {
  const cookie = req.cookies.get("nova_token")?.value
  if (!cookie) return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })

  const upstream = await fetch(`${NOVA_API_BASE}/auth/me`, {
    headers: { Cookie: `nova_token=${cookie}` },
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}

export async function PATCH(req: NextRequest) {
  const cookie = req.cookies.get("nova_token")?.value
  if (!cookie) return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })

  const body = await req.json()
  const upstream = await fetch(`${NOVA_API_BASE}/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Cookie: `nova_token=${cookie}` },
    body: JSON.stringify(body),
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
