import { NextRequest } from "next/server"

export const runtime = "nodejs"

const NOVA_API_BASE = process.env.NOVA_API_BASE || "http://127.0.0.1:8765"

// Map of document MIME types used to set the correct Content-Type
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
    const body = await req.json()
    const fmt: string = (body.format ?? "docx").toLowerCase().replace(/^\./, "")

    const upstream = await fetch(`${NOVA_API_BASE}/document/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    if (!upstream.ok) {
      const errText = await upstream.text()
      return new Response(errText, { status: upstream.status })
    }

    const fileBuffer  = await upstream.arrayBuffer()
    const filename    = upstream.headers.get("X-Nova-Filename") ?? `nova_document.${fmt}`
    const contentType = MIME_MAP[fmt] ?? "application/octet-stream"

    return new Response(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${filename}"`,
        "X-Nova-Filename": filename,
      },
    })
  } catch (err) {
    return new Response(`Document generation failed: ${err}`, { status: 500 })
  }
}
