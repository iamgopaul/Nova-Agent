import { NextRequest, NextResponse } from "next/server"

const PROTECTED_PREFIXES = [
  "/chat",
  "/voice",
  "/podcast",
  "/agents",
  "/debate",
  "/ide",
  "/settings",
  "/home",
  "/billing",
  "/screen",
  "/video",
  "/education",
  "/admin",
]

const AUTH_PAGES = ["/login", "/signup"]

const COOKIE = "gaaia_token"

export default function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const token = request.cookies.get(COOKIE)?.value

  const isProtected = PROTECTED_PREFIXES.some(
    p => pathname === p || pathname.startsWith(p + "/")
  )
  const isAuthPage = AUTH_PAGES.some(
    p => pathname === p || pathname.startsWith(p + "/")
  )

  // Unauthenticated user hitting a protected page → send to login
  if (isProtected && !token) {
    const url = request.nextUrl.clone()
    url.pathname = "/login"
    url.searchParams.set("next", pathname)
    return NextResponse.redirect(url)
  }

  // Authenticated user hitting login/signup → send to home dashboard
  if (isAuthPage && token) {
    const url = request.nextUrl.clone()
    url.pathname = "/home"
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    "/chat",
    "/chat/:path*",
    "/voice",
    "/voice/:path*",
    "/podcast",
    "/podcast/:path*",
    "/agents",
    "/agents/:path*",
    "/debate",
    "/debate/:path*",
    "/ide",
    "/ide/:path*",
    "/settings",
    "/settings/:path*",
    "/home",
    "/home/:path*",
    "/billing",
    "/billing/:path*",
    "/screen",
    "/screen/:path*",
    "/video",
    "/video/:path*",
    "/education",
    "/education/:path*",
    "/admin",
    "/admin/:path*",
    "/login",
    "/signup",
  ],
}
