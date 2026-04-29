import { NextRequest } from "next/server"
import { gaaiaApiBase } from "@/lib/gaaia-api-base"

export const runtime = "nodejs"

const MIME: Record<string, string> = {
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  pdf:  "application/pdf",
  txt:  "text/plain",
  csv:  "text/csv",
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ filename: string }> },
) {
  const { filename } = await params
  try {
    const upstream = await fetch(`${gaaiaApiBase()}/document/assets/${encodeURIComponent(filename)}`)
    if (!upstream.ok) return new Response("Not found", { status: 404 })
    const ext = filename.split(".").pop()?.toLowerCase() ?? ""
    const mime = MIME[ext] ?? "application/octet-stream"
    return new Response(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": mime,
        "Content-Disposition": `attachment; filename="${filename}"`,
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    })
  } catch {
    return new Response("Failed to fetch document asset", { status: 500 })
  }
}
