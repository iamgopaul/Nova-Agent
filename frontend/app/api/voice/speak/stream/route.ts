export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: Request) {
  const body = await req.text()

  const upstream = await fetch(`${NOVA_API_BASE}/voice/speak/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  })

  if (!upstream.ok || !upstream.body) {
    return new Response(null, { status: upstream.status })
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "application/octet-stream",
      "Cache-Control": "no-store",
    },
  })
}
