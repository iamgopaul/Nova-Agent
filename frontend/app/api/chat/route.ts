import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: NextRequest) {
  const body = await req.json()
  const rawModelKey = (body?.model_key ?? null) as string | null
  const normalizedModelKey = (
    !rawModelKey ||
    rawModelKey === "auto" ||
    rawModelKey === "default" ||
    rawModelKey === "basic" ||
    rawModelKey === "swift"
  ) ? null : rawModelKey

  const upstream = await fetch(`${NOVA_API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
