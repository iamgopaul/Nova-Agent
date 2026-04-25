import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const body = await req.text()

  const upstream = await fetch(`${novaApiBase()}/voice/speak/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Cookie: `${COOKIE}=${token}` } : {}),
    },
    body,
  })

  if (!upstream.ok || !upstream.body) {
    return new Response(null, { status: upstream.status })
  }

  return new Response(upstream.body, {
    status: 200,
    headers: { "Content-Type": "application/octet-stream", "Cache-Control": "no-store" },
  })
}
