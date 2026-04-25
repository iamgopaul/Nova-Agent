import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"


export async function POST(req: NextRequest) {
  const cookie = req.cookies.get("gaaia_token")?.value
  const upstream = await fetch(`${gaaiaApiBase()}/auth/logout`, {
    method: "POST",
    headers: cookie ? { Cookie: `gaaia_token=${cookie}` } : {},
  })

  const setCookie = upstream.headers.get("set-cookie")
  const headers: Record<string, string> = {}
  if (setCookie) headers["Set-Cookie"] = setCookie

  return new Response(null, { status: 204, headers })
}
