import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function GET(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const upstream = await fetch(`${novaApiBase()}/camera/identities`, {
    headers: token ? { Cookie: `${COOKIE}=${token}` } : {},
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
