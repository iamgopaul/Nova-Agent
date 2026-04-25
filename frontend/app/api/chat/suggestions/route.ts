import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const body = await req.json()

  const upstream = await fetch(`${novaApiBase()}/chat/suggestions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Cookie: `${COOKIE}=${token}` } : {}),
    },
    body: JSON.stringify({
      user_message: body?.user_message || "",
      assistant_response: body?.assistant_response || "",
    }),
  })

  if (!upstream.ok) {
    return Response.json({ suggestions: [] }, { status: 200 })
  }

  const data = await upstream.json()
  return Response.json(data)
}
