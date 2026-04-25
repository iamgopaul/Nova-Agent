import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


export async function POST(req: NextRequest) {
  const cookie = req.cookies.get("nova_token")?.value
  const upstream = await fetch(`${novaApiBase()}/auth/logout`, {
    method: "POST",
    headers: cookie ? { Cookie: `nova_token=${cookie}` } : {},
  })

  const setCookie = upstream.headers.get("set-cookie")
  const headers: Record<string, string> = {}
  if (setCookie) headers["Set-Cookie"] = setCookie

  return new Response(null, { status: 204, headers })
}
