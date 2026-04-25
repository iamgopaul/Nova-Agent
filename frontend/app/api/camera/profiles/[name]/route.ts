import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params
  const token = req.cookies.get(COOKIE)?.value

  const upstream = await fetch(
    `${gaaiaApiBase()}/camera/profiles/${encodeURIComponent(name)}`,
    {
      method: "DELETE",
      headers: token ? { Cookie: `${COOKIE}=${token}` } : {},
    },
  )

  if (upstream.status === 204) {
    return new Response(null, { status: 204 })
  }
  const body = await upstream.text()
  return new Response(body, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  })
}
