import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ userId: string }> }
) {
  const { userId } = await params
  const { searchParams } = new URL(req.url)
  const isAdmin = searchParams.get("is_admin")
  const upstream = await fetch(
    `${gaaiaApiBase()}/admin/users/${userId}/admin?is_admin=${isAdmin}`,
    { method: "PATCH", headers: { cookie: req.headers.get("cookie") ?? "" } }
  )
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}
