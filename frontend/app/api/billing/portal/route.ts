import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

export async function POST(req: NextRequest) {
  const upstream = await fetch(`${gaaiaApiBase()}/billing/portal`, {
    method: "POST",
    headers: { cookie: req.headers.get("cookie") ?? "" },
  })
  const text = await upstream.text()
  return new Response(text, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") || "application/json" },
  })
}
