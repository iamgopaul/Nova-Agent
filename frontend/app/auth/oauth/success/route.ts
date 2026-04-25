import { NextRequest, NextResponse } from "next/server"

export const runtime = "nodejs"

const COOKIE_NAME = "nova_token"

export async function GET(req: NextRequest) {
  const url = new URL(req.url)
  const token = (url.searchParams.get("token") || "").trim()
  const linked = url.searchParams.get("linked") === "1"
  const provider = (url.searchParams.get("provider") || "").trim()

  if (!token) {
    return NextResponse.redirect(new URL("/login?error=oauth_missing_token", req.url))
  }

  const target = linked
    ? new URL(`/home?linked=${encodeURIComponent(provider || "oauth")}`, req.url)
    : new URL("/home", req.url)

  const response = NextResponse.redirect(target)
  response.cookies.set({
    name: COOKIE_NAME,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: false,
    maxAge: 60 * 60 * 24 * 30,
  })
  return response
}
