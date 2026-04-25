import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


function cookieHeader(req: NextRequest): Record<string, string> {
  const token = req.cookies.get("nova_token")?.value
  return token ? { Cookie: `nova_token=${token}` } : {}
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params
  const upstream = await fetch(`${novaApiBase()}/memory/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    headers: cookieHeader(req),
  })
  if (upstream.status === 204) return new Response(null, { status: 204, headers: { "Cache-Control": "no-cache" } })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params
  const payload = await req.json()
  const upstream = await fetch(`${novaApiBase()}/memory/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...cookieHeader(req) },
    body: JSON.stringify(payload || {}),
  })
  if (upstream.status === 204) return new Response(null, { status: 204, headers: { "Cache-Control": "no-cache" } })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}
