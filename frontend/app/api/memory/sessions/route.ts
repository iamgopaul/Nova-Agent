import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


function cookieHeader(req: NextRequest): Record<string, string> {
  const token = req.cookies.get("nova_token")?.value
  return token ? { Cookie: `nova_token=${token}` } : {}
}

export async function GET(req: NextRequest) {
  const upstream = await fetch(`${novaApiBase()}/memory/sessions`, {
    headers: cookieHeader(req),
  })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}
