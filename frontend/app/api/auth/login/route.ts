import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"


export async function POST(req: NextRequest) {
  const body = await req.json()
  const upstream = await fetch(`${novaApiBase()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
