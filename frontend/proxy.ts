import { NextRequest, NextResponse } from "next/server"

// Pages that require authentication
const PROTECTED_PREFIXES = [
  "/chat",
  "/voice",
  "/podcast",
  "/agents",
  "/debate",
  "/ide",
  "/settings",
  "/home",
]

// Pages only for unauthenticated users (redirect away if already signed in)
const AUTH_PAGES = ["/login", "/signup"]

const COOKIE = "gaaia_token"

export function proxy(request: NextRequest) {
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
    "/chat/:path*",
    "/voice/:path*",
    "/podcast/:path*",
    "/agents/:path*",
    "/debate/:path*",
    "/ide/:path*",
    "/settings/:path*",
    "/home/:path*",
    "/login",
    "/signup",
  ],
}
