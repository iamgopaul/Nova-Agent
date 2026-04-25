"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import {
  Download,
  FileText,
  FileSpreadsheet,
  Presentation,
  File,
  Loader2,
  Eye,
  Minus,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"

// ── helpers ───────────────────────────────────────────────────────────────────

const FORMAT_META: Record<string, {
  label: string
  color: string
  bg: string
  border: string
  Icon: React.ElementType
}> = {
  docx: {
    label: "Word Document",
    color: "text-blue-400",
    bg: "bg-blue-950/30",
    border: "border-blue-500/20",
    Icon: FileText,
  },
  xlsx: {
    label: "Excel Spreadsheet",
    color: "text-emerald-400",
    bg: "bg-emerald-950/30",
    border: "border-emerald-500/20",
    Icon: FileSpreadsheet,
  },
  pdf: {
    label: "PDF Document",
    color: "text-red-400",
    bg: "bg-red-950/30",
    border: "border-red-500/20",
    Icon: FileText,
  },
  pptx: {
    label: "PowerPoint Presentation",
    color: "text-orange-400",
    bg: "bg-orange-950/30",
    border: "border-orange-500/20",
    Icon: Presentation,
  },
  txt: {
    label: "Text File",
    color: "text-slate-400",
    bg: "bg-slate-950/30",
    border: "border-slate-500/20",
    Icon: FileText,
  },
  csv: {
    label: "CSV File",
    color: "text-teal-400",
    bg: "bg-teal-950/30",
    border: "border-teal-500/20",
    Icon: FileSpreadsheet,
  },
}

function getMeta(fmt: string) {
  return FORMAT_META[fmt.toLowerCase()] ?? {
    label: "Document",
    color: "text-muted-foreground",
    bg: "bg-muted/20",
    border: "border-border/30",
    Icon: File,
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// ── Preview renderer ──────────────────────────────────────────────────────────

type PreviewState = "idle" | "loading" | "ready" | "error"

function DocPreview({ url, format, fullscreen }: { url: string; format: string; fullscreen?: boolean }) {
  const fmt = format.toLowerCase()
  const [state, setState] = useState<PreviewState>("idle")
  const [html, setHtml] = useState<string>("")
  const containerRef = useRef<HTMLDivElement>(null)
  const didLoad = useRef(false)

  const loadPreview = useCallback(async () => {
    if (didLoad.current) return
    didLoad.current = true
    setState("loading")

    try {
      const res = await fetch(url)
      const buf = await res.arrayBuffer()

      if (fmt === "pdf") {
        // PDF is handled by <iframe> directly — no JS conversion needed
        setState("ready")
        return
      }

      if (fmt === "docx") {
        const mammoth = await import("mammoth")
        const result = await mammoth.convertToHtml({ arrayBuffer: buf })
        setHtml(result.value)
        setState("ready")
        return
      }

      if (fmt === "xlsx" || fmt === "csv") {
        const XLSX = await import("xlsx")
        const wb = XLSX.read(buf, { type: "array" })
        const firstSheet = wb.Sheets[wb.SheetNames[0]]
        const tableHtml = XLSX.utils.sheet_to_html(firstSheet, {
          id: "nova-sheet",
          editable: false,
        })
        setHtml(tableHtml)
        setState("ready")
        return
      }

      if (fmt === "pptx") {
        // python-pptx doesn't have a great JS equivalent — show slide text
        const { read: zipRead } = await import("xlsx").then(m => ({ read: m.read }))
        // Fallback: show a message for PPTX
        setHtml(`<div style="padding:16px;color:#999;font-family:sans-serif">
          <p>PowerPoint preview is not supported in the browser.</p>
          <p>Please download the file to view it in PowerPoint or LibreOffice Impress.</p>
        </div>`)
        setState("ready")
        return
      }

      if (fmt === "txt") {
        const text = new TextDecoder().decode(buf)
        setHtml(`<pre style="white-space:pre-wrap;font-family:monospace;font-size:13px;line-height:1.6;padding:16px">${
          text.replace(/</g, "&lt;").replace(/>/g, "&gt;")
        }</pre>`)
        setState("ready")
        return
      }

      setState("error")
    } catch (e) {
      console.error("[DocPreview] error:", e)
      setState("error")
    }
  }, [url, fmt])

  useEffect(() => {
    loadPreview()
  }, [loadPreview])

  if (fmt === "pdf") {
    return (
      <iframe
        src={url}
        title="PDF preview"
        className={cn("w-full bg-white border-t border-inherit", fullscreen ? "h-full" : "h-[500px]")}
        style={fullscreen ? { minHeight: "calc(100vh - 56px)" } : undefined}
      />
    )
  }

  if (state === "loading") {
    return (
      <div className="flex items-center justify-center h-24 border-t border-inherit text-muted-foreground text-sm gap-2">
        <Loader2 className="w-4 h-4 animate-spin" />
        Rendering preview…
      </div>
    )
  }

  if (state === "error") {
    return (
      <div className="px-4 py-3 border-t border-inherit text-muted-foreground text-sm">
        Preview unavailable — download to view.
      </div>
    )
  }

  if (state === "ready" && html) {
    return (
      <div
        ref={containerRef}
        className={cn("border-t border-inherit overflow-auto bg-white text-black", fullscreen ? "" : "max-h-[500px]")}
        style={{ fontSize: "13px", lineHeight: "1.6", ...(fullscreen ? { minHeight: "calc(100vh - 56px)" } : {}) }}
      >
        {/* Inject basic table styles for xlsx previews */}
        <style>{`
          #nova-sheet table { border-collapse: collapse; width: 100%; font-size: 12px; }
          #nova-sheet td, #nova-sheet th { border: 1px solid #ddd; padding: 4px 8px; }
          #nova-sheet th { background: #f0f0f0; font-weight: 600; }
          #nova-sheet tr:nth-child(even) { background: #f9f9f9; }
        `}</style>
        <div
          className="p-4 prose prose-sm max-w-none"
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    )
  }

  return null
}

// ── DocumentCard ──────────────────────────────────────────────────────────────

interface DocumentCardProps {
  url: string
  filename: string
  format: string
  sizeBytes?: number
  prompt?: string
  className?: string
}

export function DocumentCard({
  url, filename, format, sizeBytes, prompt, className,
}: DocumentCardProps) {
  const meta = getMeta(format)
  const { Icon } = meta
  const [modalOpen, setModalOpen] = useState(false)
  const fmt = format.toLowerCase()

  const canPreview = ["pdf", "docx", "xlsx", "csv", "txt"].includes(fmt)

  // Close modal on Escape
  useEffect(() => {
    if (!modalOpen) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setModalOpen(false) }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [modalOpen])

  return (
    <>
      <div className={cn("rounded-xl border overflow-hidden", meta.bg, meta.border, className)}>
        {/* Card header */}
        <div className="flex items-center gap-3 px-3 py-2.5">
          <div className={cn("flex items-center justify-center w-9 h-9 rounded-lg shrink-0", meta.bg, "border", meta.border)}>
            <Icon className={cn("w-5 h-5", meta.color)} />
          </div>

          <div className="flex-1 min-w-0">
            <p className={cn("text-sm font-medium truncate", meta.color)} title={filename}>
              {filename}
            </p>
            <p className="text-xs text-muted-foreground">
              {meta.label}
              {sizeBytes != null && ` · ${formatBytes(sizeBytes)}`}
            </p>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {canPreview && (
              <button
                onClick={() => setModalOpen(true)}
                className={cn(
                  "flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors",
                  meta.color, "hover:bg-white/10"
                )}
                title="Preview document"
              >
                <Eye className="w-3.5 h-3.5" />
                <span className="hidden sm:inline ml-1">Preview</span>
              </button>
            )}
            <a
              href={url}
              download={filename}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors",
                "bg-white/10 hover:bg-white/15", meta.color
              )}
              title="Download"
            >
              <Download className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Download</span>
            </a>
          </div>
        </div>

        {prompt && (
          <div className="px-3 pb-2 border-t border-inherit">
            <p className="text-xs text-muted-foreground/60 truncate mt-1.5" title={prompt}>
              {prompt}
            </p>
          </div>
        )}
      </div>

      {/* Full-screen document preview modal — portal escapes backdrop-blur ancestors */}
      {modalOpen && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 flex flex-col" style={{ zIndex: 9999, backgroundColor: "rgba(0,0,0,0.85)" }}>
          {/* Modal header */}
          <div
            className="flex items-center justify-between gap-3 px-4 py-3 border-b border-white/10 shrink-0"
            style={{ backgroundColor: "var(--surface-2)" }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Icon className={cn("w-4 h-4 shrink-0", meta.color)} />
              <span className={cn("text-sm font-medium truncate", meta.color)} title={filename}>
                {filename}
              </span>
              {sizeBytes != null && (
                <span className="text-xs text-white/30 shrink-0">{formatBytes(sizeBytes)}</span>
              )}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <a
                href={url}
                download={filename}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white/10 hover:bg-white/15 text-white/70 transition-colors"
                title="Download"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download</span>
              </a>
              <button
                onClick={() => setModalOpen(false)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-white/10 hover:bg-white/15 text-white/70 transition-colors"
                title="Minimize (Esc)"
              >
                <Minus className="w-3.5 h-3.5" />
                <span>Minimize</span>
              </button>
              <button
                onClick={() => setModalOpen(false)}
                className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white/70 transition-colors"
                title="Close (Esc)"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Preview content — fills remaining height */}
          <div className="flex-1 flex flex-col min-h-0">
            <DocPreview url={url} format={fmt} fullscreen />
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}


// ── DocumentGenerating ────────────────────────────────────────────────────────

interface DocumentGeneratingProps {
  format?: string
  prompt?: string
  className?: string
}

export function DocumentGenerating({ format = "docx", prompt, className }: DocumentGeneratingProps) {
  const meta = getMeta(format)
  const { Icon } = meta

  return (
    <div className={cn("rounded-xl border overflow-hidden", meta.bg, meta.border, className)}>
      <div className="flex items-center gap-3 px-3 py-2.5">
        <div className={cn("flex items-center justify-center w-9 h-9 rounded-lg shrink-0", meta.bg, "border", meta.border)}>
          <Icon className={cn("w-5 h-5", meta.color, "animate-pulse")} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Loader2 className={cn("w-3.5 h-3.5 animate-spin shrink-0", meta.color)} />
            <span className={cn("text-sm font-medium", meta.color)}>
              Generating {meta.label}…
            </span>
          </div>
          {prompt && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">{prompt}</p>
          )}
        </div>
      </div>
    </div>
  )
}
