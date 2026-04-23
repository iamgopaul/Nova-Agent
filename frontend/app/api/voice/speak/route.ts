export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: Request) {
  const body = await req.text()

  const upstream = await fetch(`${NOVA_API_BASE}/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  })

  const contentType = upstream.headers.get("content-type") || "application/json"
  const bytes = await upstream.arrayBuffer()

  return new Response(bytes, {
    status: upstream.status,
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "no-store",
    },
  })
}
