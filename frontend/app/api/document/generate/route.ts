import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const COOKIE = "gaaia_token"

const MIME_MAP: Record<string, string> = {
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  pdf:  "application/pdf",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  txt:  "text/plain; charset=utf-8",
  csv:  "text/csv; charset=utf-8",
}

export async function POST(req: NextRequest) {
  try {
    const token = req.cookies.get(COOKIE)?.value
    if (!token) {
      return new Response(JSON.stringify({ detail: "Not authenticated." }), { status: 401 })
    }

    const body = await req.json()
    const fmt: string = (body.format ?? "docx").toLowerCase().replace(/^\./, "")

    const upstream = await fetch(`${gaaiaApiBase()}/document/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: `${COOKIE}=${token}`,
      },
      body: JSON.stringify(body),
    })

    if (!upstream.ok) {
      const errText = await upstream.text()
      return new Response(errText, { status: upstream.status })
    }

    const fileBuffer  = await upstream.arrayBuffer()
    const filename    = upstream.headers.get("X-GAAIA-Filename") ?? `nova_document.${fmt}`
    const contentType = MIME_MAP[fmt] ?? "application/octet-stream"

    return new Response(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${filename}"`,
        "X-GAAIA-Filename": filename,
      },
    })
  } catch (err) {
    return new Response(`Document generation failed: ${err}`, { status: 500 })
  }
}
