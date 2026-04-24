import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function GET(req: NextRequest) {
  const token = req.cookies.get("nova_token")?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const upstream = await fetch(`${NOVA_API_BASE}/auth/providers`, {
    headers: { Cookie: `nova_token=${token}` },
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}
