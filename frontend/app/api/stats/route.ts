import { NextRequest } from "next/server"
import { novaApiBase } from "@/lib/nova-api-base"

export const runtime = "nodejs"

const COOKIE = "nova_token"

export async function GET(req: NextRequest) {
  try {
    const token = req.cookies.get(COOKIE)?.value

    const upstream = await fetch(`${novaApiBase()}/stats`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Cookie: `${COOKIE}=${token}` } : {}),
      },
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
