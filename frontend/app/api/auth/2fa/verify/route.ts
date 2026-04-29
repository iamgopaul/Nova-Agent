import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const upstream = await fetch(`${gaaiaApiBase()}/auth/2fa/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json", cookie: req.headers.get("cookie") ?? "" },
    body: JSON.stringify(body),
  })
  const text = await upstream.text()
  const setCookie = upstream.headers.get("set-cookie")
  const headers: Record<string, string> = {
    "Content-Type": upstream.headers.get("content-type") || "application/json",
  }
  if (setCookie) headers["Set-Cookie"] = setCookie
  return new Response(text, { status: upstream.status, headers })
}
