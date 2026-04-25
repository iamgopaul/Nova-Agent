import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


export async function POST(req: NextRequest) {
  const cookie = req.cookies.get("nova_token")?.value
  if (!cookie) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const body = await req.json()
  const upstream = await fetch(`${novaApiBase()}/auth/password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: `nova_token=${cookie}`,
    },
    body: JSON.stringify(body),
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
