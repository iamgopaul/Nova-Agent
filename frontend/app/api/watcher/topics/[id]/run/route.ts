import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }
  const upstream = await fetch(
    `${novaApiBase()}/watcher/topics/${encodeURIComponent(id)}/run`,
    {
      method: "POST",
      headers: { Cookie: `${COOKIE}=${token}` },
    },
  )
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
