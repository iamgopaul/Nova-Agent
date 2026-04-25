import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value
  if (!token) {
    return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
  }

  const body = await req.json()
  const rawModelKey = (body?.model_key ?? null) as string | null
  const normalizedModelKey = (
    !rawModelKey ||
    rawModelKey === "auto" ||
    rawModelKey === "default" ||
    rawModelKey === "basic" ||
    rawModelKey === "swift"
  ) ? null : rawModelKey

  const upstream = await fetch(`${gaaiaApiBase()}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: `${COOKIE}=${token}`,
    },
    body: JSON.stringify({
      message: body?.message || "",
      session_id: body?.session_id || null,
      mode: body?.mode || "default",
      model_key: normalizedModelKey,
      attachments: body?.attachments || [],
    }),
  })

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text()
    return new Response(detail || "Upstream error", { status: upstream.status || 502 })
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  })
}
