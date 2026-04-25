import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const form = await req.formData()

  const upstream = await fetch(`${gaaiaApiBase()}/voice`, {
    method: "POST",
    headers: { Cookie: `${COOKIE}=${token}` },
    body: form,
  })

  const contentType = upstream.headers.get("content-type") || "application/json"
  const body = await upstream.text()

  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": contentType, "Cache-Control": "no-cache" },
  })
}
