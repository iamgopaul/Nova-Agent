import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


export async function GET(req: NextRequest) {
  const cookie = req.cookies.get("nova_token")?.value
  if (!cookie) return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })

  const upstream = await fetch(`${novaApiBase()}/auth/me`, {
    headers: { Cookie: `nova_token=${cookie}` },
  })
  const text = await upstream.text()

  // If the backend rejects the token (expired / revoked), clear the browser cookie
  // so the proxy middleware doesn't keep bouncing the user between /home and /login.
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  if (upstream.status === 401) {
    headers["Set-Cookie"] = "nova_token=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
  }

  return new Response(text, { status: upstream.status, headers })
}

export async function PATCH(req: NextRequest) {
  const cookie = req.cookies.get("nova_token")?.value
  if (!cookie) return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })

  const body = await req.json()
  const upstream = await fetch(`${novaApiBase()}/auth/me`, {
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
