import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


export async function GET(req: NextRequest) {
  const token = req.cookies.get("nova_token")?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const upstream = await fetch(`${novaApiBase()}/auth/providers`, {
    headers: { Cookie: `nova_token=${token}` },
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}
