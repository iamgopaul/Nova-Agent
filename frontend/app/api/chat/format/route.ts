import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  const body = await req.json()
  const content: string = body?.content || ""

  const upstream = await fetch(`${novaApiBase()}/chat/format`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Cookie: `${COOKIE}=${token}` } : {}),
    },
    body: JSON.stringify({ content }),
  })

  if (!upstream.ok) {
    return Response.json({ intro: "", body: content, outro: "" }, { status: 200 })
  }

  const data = await upstream.json()
  return Response.json(data)
}
