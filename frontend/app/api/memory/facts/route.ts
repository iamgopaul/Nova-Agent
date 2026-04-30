import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

function cookieHeader(req: NextRequest): Record<string, string> {
  const token = req.cookies.get("gaaia_token")?.value
  return token ? { Cookie: `gaaia_token=${token}` } : {}
}

export async function GET(req: NextRequest) {
  const upstream = await fetch(`${gaaiaApiBase()}/memory/facts`, {
    headers: cookieHeader(req),
  })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const upstream = await fetch(`${gaaiaApiBase()}/memory/facts`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...cookieHeader(req),
    },
    body: JSON.stringify(body),
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}
