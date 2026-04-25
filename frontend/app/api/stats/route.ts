import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

export async function GET(req: NextRequest) {
  try {
    const token = req.cookies.get(COOKIE)?.value

    const upstream = await fetch(`${gaaiaApiBase()}/stats`, {
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
