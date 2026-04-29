import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

/** GitHub OAuth callback — see google/callback/route.ts for the pattern. */
export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const upstream = await fetch(`${gaaiaApiBase()}/auth/oauth/github/callback${url.search}`, {
    redirect: "manual",
  })

  const headers: Record<string, string> = {}
  const location = upstream.headers.get("location")
  if (location) headers["Location"] = location
  const setCookie = upstream.headers.get("set-cookie")
  if (setCookie) headers["Set-Cookie"] = setCookie
  const contentType = upstream.headers.get("content-type")
  if (contentType) headers["Content-Type"] = contentType

  if (upstream.status >= 300 && upstream.status < 400) {
    return new Response(null, { status: upstream.status, headers })
  }
  const text = await upstream.text()
  return new Response(text, { status: upstream.status, headers })
}
