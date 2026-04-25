import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const body = await req.text()

  const upstream = await fetch(`${novaApiBase()}/voice/speak`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Cookie: `${COOKIE}=${token}` } : {}),
    },
    body,
  })

  const contentType = upstream.headers.get("content-type") || "application/json"
  const bytes = await upstream.arrayBuffer()

  return new Response(bytes, {
    status: upstream.status,
    headers: { "Content-Type": contentType, "Cache-Control": "no-store" },
  })
}
