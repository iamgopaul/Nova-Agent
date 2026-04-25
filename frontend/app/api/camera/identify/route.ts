import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const form = await req.formData()

  const upstream = await fetch(`${novaApiBase()}/camera/identify`, {
    method: "POST",
    headers: token ? { Cookie: `${COOKIE}=${token}` } : {},
    body: form,
  })

  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
  })
}
