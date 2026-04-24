import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ folderName: string }> },
) {
  const { folderName } = await params
  const token = req.cookies.get("nova_token")?.value
  const upstream = await fetch(`${NOVA_API_BASE}/memory/folders/${encodeURIComponent(folderName)}`, {
    method: "DELETE",
    headers: token ? { Cookie: `nova_token=${token}` } : {},
  })
  if (upstream.status === 204) return new Response(null, { status: 204, headers: { "Cache-Control": "no-cache" } })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}
