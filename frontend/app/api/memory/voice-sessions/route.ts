import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

function cookieHeader(req: NextRequest): Record<string, string> {
  const token = req.cookies.get(COOKIE)?.value
  return token ? { Cookie: `${COOKIE}=${token}` } : {}
}

export async function GET(req: NextRequest) {
  const upstream = await fetch(`${novaApiBase()}/memory/voice-sessions`, {
    headers: cookieHeader(req),
  })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-cache",
    },
  })
}
