import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return Response.json({ detail: "Not authenticated." }, { status: 401 })
  }

  const body = await req.json()
  const upstream = await fetch(`${novaApiBase()}/education/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: `${COOKIE}=${token}`,
    },
    body: JSON.stringify(body),
  })

  const text = await upstream.text()
  try {
    const data = JSON.parse(text) as unknown
    return Response.json(data, { status: upstream.status })
  } catch {
    return new Response(text, { status: upstream.status })
  }
}
