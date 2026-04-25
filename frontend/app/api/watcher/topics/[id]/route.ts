import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

function cookieHeader(req: NextRequest): Record<string, string> {
  const token = req.cookies.get(COOKIE)?.value
  return token ? { Cookie: `${COOKIE}=${token}` } : {}
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const body = await req.json()
  const upstream = await fetch(`${gaaiaApiBase()}/watcher/topics/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...cookieHeader(req) },
    body: JSON.stringify(body),
  })
  if (upstream.status === 204) return new Response(null, { status: 204 })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const upstream = await fetch(`${gaaiaApiBase()}/watcher/topics/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: cookieHeader(req),
  })
  if (upstream.status === 204) return new Response(null, { status: 204 })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
