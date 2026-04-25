import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

function cookieHeader(req: NextRequest): Record<string, string> {
  const token = req.cookies.get(COOKIE)?.value
  return token ? { Cookie: `${COOKIE}=${token}` } : {}
}

export async function GET(req: NextRequest) {
  const upstream = await fetch(`${novaApiBase()}/watcher/topics`, {
    headers: cookieHeader(req),
  })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
  })
}

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }
  const body = await req.json()
  const upstream = await fetch(`${novaApiBase()}/watcher/topics`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: `${COOKIE}=${token}` },
    body: JSON.stringify(body),
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
