export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function POST(req: Request) {
  const form = await req.formData()
  const upstream = await fetch(`${NOVA_API_BASE}/camera/live`, {
    method: "POST",
    body: form,
  })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-cache" },
  })
}
