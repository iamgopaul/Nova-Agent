import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const content: string = body?.content || ""

  const upstream = await fetch(`${NOVA_API_BASE}/chat/format`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  })

  if (!upstream.ok) {
    return Response.json({ intro: "", body: content, outro: "" }, { status: 200 })
  }

  const data = await upstream.json()
  return Response.json(data)
}
