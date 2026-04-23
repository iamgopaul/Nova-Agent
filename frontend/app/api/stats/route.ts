import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

export async function GET(_req: NextRequest) {
  try {
    const upstream = await fetch(`${NOVA_API_BASE}/stats`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    })

    if (!upstream.ok) {
      return Response.json({ system: null, last_request: null }, { status: 200 })
    }

    const data = await upstream.json()
    return Response.json(data)
  } catch {
    return Response.json({ system: null, last_request: null }, { status: 200 })
  }
}
