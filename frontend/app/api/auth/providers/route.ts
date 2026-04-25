import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"


export async function GET(req: NextRequest) {
  const token = req.cookies.get("gaaia_token")?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const upstream = await fetch(`${gaaiaApiBase()}/auth/providers`, {
    headers: { Cookie: `gaaia_token=${token}` },
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}
