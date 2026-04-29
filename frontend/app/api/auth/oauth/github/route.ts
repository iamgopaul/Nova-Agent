import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

/** Initiate GitHub OAuth — see google/route.ts for the pattern. */
export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const cookie = req.cookies.get("gaaia_token")?.value
  const upstream = await fetch(`${gaaiaApiBase()}/auth/oauth/github${url.search}`, {
    redirect: "manual",
    headers: cookie ? { Cookie: `gaaia_token=${cookie}` } : {},
  })

  const headers: Record<string, string> = {}
  const location = upstream.headers.get("location")
  if (location) headers["Location"] = location
  const setCookie = upstream.headers.get("set-cookie")
  if (setCookie) headers["Set-Cookie"] = setCookie

  return new Response(null, { status: upstream.status, headers })
}
