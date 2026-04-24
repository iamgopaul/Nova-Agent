import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: NextRequest) {
  const cookie = req.cookies.get("nova_token")?.value
  const upstream = await fetch(`${NOVA_API_BASE}/auth/logout`, {
    method: "POST",
    headers: cookie ? { Cookie: `nova_token=${cookie}` } : {},
  })

  const setCookie = upstream.headers.get("set-cookie")
  const headers: Record<string, string> = {}
  if (setCookie) headers["Set-Cookie"] = setCookie

  return new Response(null, { status: 204, headers })
}
