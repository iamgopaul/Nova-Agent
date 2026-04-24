import { NextRequest, NextResponse } from "next/server"

const PROTECTED = ["/chat"]
const AUTH_PAGES = ["/login", "/signup"]
const COOKIE = "nova_token"

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl
  const token = request.cookies.get(COOKIE)?.value

  const isProtected = PROTECTED.some(p => pathname === p || pathname.startsWith(p + "/"))
  const isAuthPage  = AUTH_PAGES.some(p => pathname === p || pathname.startsWith(p + "/"))

  if (isProtected && !token) {
    const url = request.nextUrl.clone()
    url.pathname = "/login"
    url.searchParams.set("next", pathname)
    return NextResponse.redirect(url)
  }

  if (isAuthPage && token) {
    const url = request.nextUrl.clone()
    url.pathname = "/chat"
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/chat/:path*", "/login", "/signup"],
}
