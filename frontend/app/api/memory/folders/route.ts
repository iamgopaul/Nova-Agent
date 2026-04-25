import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


function cookieHeader(req: NextRequest): Record<string, string> {
  const token = req.cookies.get("nova_token")?.value
  return token ? { Cookie: `nova_token=${token}` } : {}
}

export async function GET(req: NextRequest) {
  const upstream = await fetch(`${novaApiBase()}/memory/folders`, { headers: cookieHeader(req) })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}

export async function POST(req: NextRequest) {
  const payload = await req.json()
  const upstream = await fetch(`${novaApiBase()}/memory/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...cookieHeader(req) },
    body: JSON.stringify(payload || {}),
  })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}
