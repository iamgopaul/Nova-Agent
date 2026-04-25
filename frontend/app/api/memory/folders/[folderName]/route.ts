import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"


export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ folderName: string }> },
) {
  const { folderName } = await params
  const token = req.cookies.get("gaaia_token")?.value
  const upstream = await fetch(`${gaaiaApiBase()}/memory/folders/${encodeURIComponent(folderName)}`, {
    method: "DELETE",
    headers: token ? { Cookie: `gaaia_token=${token}` } : {},
  })
  if (upstream.status === 204) return new Response(null, { status: 204, headers: { "Cache-Control": "no-cache" } })
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-cache" },
  })
}
