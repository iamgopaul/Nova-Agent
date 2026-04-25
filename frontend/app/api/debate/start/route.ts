import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const body = await req.json()
  const upstream = await fetch(`${gaaiaApiBase()}/debate/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: `${COOKIE}=${token}`,
    },
    body: JSON.stringify({ topic: body.topic || "" }),
  })

  const data = await upstream.text()
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
