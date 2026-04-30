import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

/**
 * Initiate Google OAuth: forwards GET /api/auth/oauth/google to the backend
 * which builds the Google auth URL and returns a 302 redirect. We follow the
 * redirect through to the user's browser unmodified so they end up on Google.
 *
 * Backend's GOOGLE_REDIRECT_URI must be set to
 *   https://gaaia.co/api/auth/oauth/google/callback
 * so Google sends the user back here after auth — see callback/route.ts.
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const cookie = req.cookies.get("gaaia_token")?.value
  const origin = req.headers.get("origin") || `${url.protocol}//${url.host}`
  const upstream = await fetch(`${gaaiaApiBase()}/auth/oauth/google${url.search}`, {
    redirect: "manual",
    headers: {
      ...(cookie ? { Cookie: `gaaia_token=${cookie}` } : {}),
      Origin: origin,
    },
  })

  const headers: Record<string, string> = {}
  const location = upstream.headers.get("location")
  if (location) headers["Location"] = location
  const setCookie = upstream.headers.get("set-cookie")
  if (setCookie) headers["Set-Cookie"] = setCookie

  return new Response(null, { status: upstream.status, headers })
}
