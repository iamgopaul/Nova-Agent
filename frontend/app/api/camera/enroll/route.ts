import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const form = await req.formData()

  const upstream = await fetch(`${novaApiBase()}/camera/enroll`, {
    method: "POST",
    headers: { Cookie: `${COOKIE}=${token}` },
    body: form,
  })

  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
  })
}
