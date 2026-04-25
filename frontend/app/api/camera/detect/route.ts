import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const form = await req.formData()

  const upstream = await fetch(`${gaaiaApiBase()}/camera/detect`, {
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
