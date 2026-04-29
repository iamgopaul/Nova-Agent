"use client"

import { useEffect, useState } from "react"
import { createPortal } from "react-dom"
import { Download, ImageIcon, Maximize2, Minus, X, ZoomIn, ZoomOut } from "lucide-react"
import { cn } from "@/lib/utils"

interface ImagePreviewProps {
  url: string
  prompt?: string
  caption?: string   // short human-readable label shown in the footer (falls back to prompt)
  className?: string
}

/** Strips quality/style SD tags and truncates to a human-readable label */
function _cleanPromptLabel(raw?: string): string {
  if (!raw) return ""
  const subject = raw.split(",")[0].trim()
  return subject.charAt(0).toUpperCase() + subject.slice(1)
}

/**
 * Route external http(s) URLs through the local proxy to bypass hotlink
 * protection and CORS restrictions.  Base64 data URIs and blob URLs are
 * returned unchanged.
 */
function _resolveImageSrc(url: string): string {
  if (!url) return url
  if (url.startsWith("data:") || url.startsWith("blob:")) return url
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return `/api/proxy-image?url=${encodeURIComponent(url)}`
  }
  return url
}

export function ImagePreview({ url, prompt, caption, className }: ImagePreviewProps) {
  const displayLabel = caption || _cleanPromptLabel(prompt)
  const [lightbox, setLightbox] = useState(false)
  const [zoom, setZoom]         = useState(1)
  const [imgError, setImgError] = useState(false)

  const src = _resolveImageSrc(url)

  // Reset zoom when lightbox closes
  useEffect(() => {
    if (!lightbox) setZoom(1)
  }, [lightbox])

  // Reset error state when url changes
  useEffect(() => { setImgError(false) }, [url])

  // Close lightbox on Escape
  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setLightbox(false) }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [lightbox])

  return (
    <>
      {/* Inline card — compact, elegant */}
      <div className={cn(
        "inline-block max-w-sm rounded-lg overflow-hidden border border-white/10 bg-black/20 shadow-sm",
        className,
      )}>
        {/* Image */}
        <div
          className="relative cursor-zoom-in group bg-black/30"
          onClick={() => !imgError && setLightbox(true)}
          title={imgError ? "Image unavailable" : "Click to enlarge"}
        >
          {imgError ? (
            <div className="w-full h-24 flex flex-col items-center justify-center gap-1.5 bg-muted/40 text-muted-foreground">
              <ImageIcon className="w-5 h-5 opacity-40" />
              <span className="text-[11px] opacity-60">Image unavailable</span>
            </div>
          ) : (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={prompt ?? "Generated image"}
                className="w-full h-auto object-contain max-h-56"
                onError={() => setImgError(true)}
              />
              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center pointer-events-none">
                <Maximize2 className="w-5 h-5 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-lg" />
              </div>
            </>
          )}
        </div>

        {/* Footer bar — slim */}
        <div className="flex items-center justify-between px-2 py-1 bg-black/30 border-t border-white/5">
          <div className="flex items-center gap-1 min-w-0">
            <ImageIcon className="w-3 h-3 text-white/30 shrink-0" />
            {displayLabel && (
              <span className="text-[11px] text-white/45 truncate max-w-[180px]" title={prompt}>
                {displayLabel}
              </span>
            )}
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <button
              onClick={() => setLightbox(true)}
              className="p-1 rounded text-white/40 hover:text-white/80 hover:bg-white/5 transition-colors"
              title="View full size"
            >
              <Maximize2 className="w-3 h-3" />
            </button>
            <a
              href={url}
              download="gaaia_image.png"
              className="p-1 rounded text-white/40 hover:text-white/80 hover:bg-white/5 transition-colors"
              title="Download PNG"
            >
              <Download className="w-3 h-3" />
            </a>
          </div>
        </div>
      </div>

      {/* Lightbox — rendered via portal so backdrop-blur ancestors don't clip it */}
      {lightbox && typeof document !== "undefined" && createPortal(
        <div
          className="fixed inset-0 flex flex-col bg-black/90"
          style={{ zIndex: 9999 }}
          onClick={() => setLightbox(false)}
        >
          {/* Toolbar */}
          <div
            className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-white/10"
            style={{ backgroundColor: "rgba(10,10,20,0.95)" }}
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setZoom(z => Math.max(0.25, z - 0.25))}
                className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors"
                title="Zoom out"
              >
                <ZoomOut className="w-4 h-4" />
              </button>
              <span className="text-white/70 text-xs tabular-nums w-10 text-center">{Math.round(zoom * 100)}%</span>
              <button
                onClick={() => setZoom(z => Math.min(4, z + 0.25))}
                className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors"
                title="Zoom in"
              >
                <ZoomIn className="w-4 h-4" />
              </button>
              <button
                onClick={() => setZoom(1)}
                className="px-2 py-1 rounded-md bg-white/10 hover:bg-white/20 text-white/60 text-xs transition-colors ml-1"
                title="Reset zoom"
              >
                Reset
              </button>
              <a
                href={url}
                download="gaaia_image.png"
                onClick={e => e.stopPropagation()}
                className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors ml-1"
                title="Download"
              >
                <Download className="w-4 h-4" />
              </a>
            </div>
            <div className="flex items-center gap-1.5">
              {displayLabel && (
                <span className="text-white/40 text-xs truncate max-w-[200px] hidden sm:block">{displayLabel}</span>
              )}
              <button
                onClick={() => setLightbox(false)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white/70 text-xs transition-colors"
                title="Minimize (Esc)"
              >
                <Minus className="w-3.5 h-3.5" />
                <span>Minimize</span>
              </button>
              <button
                onClick={() => setLightbox(false)}
                className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors"
                title="Close (Esc)"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Scrollable image area */}
          <div
            className="flex-1 overflow-auto flex items-start justify-center p-4"
            onClick={e => e.stopPropagation()}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={src}
              alt={prompt ?? "Generated image"}
              style={{
                display: "block",
                width: zoom === 1 ? "auto" : `${zoom * 100}%`,
                maxWidth: zoom === 1 ? "100%" : "none",
                transition: "width 0.2s ease",
              }}
            />
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}


export function ImageGenerating({
  className,
  progress,
}: {
  prompt?: string
  className?: string
  progress?: { step: number; total: number }
}) {
  const hasProgress = progress && progress.total > 0
  const pct = hasProgress ? Math.round((progress.step / progress.total) * 100) : 0

  return (
    <div className={cn(
      "flex flex-col gap-2 px-3 py-2.5 rounded-lg border border-blue-500/30 bg-gradient-to-r from-blue-950/50 to-cyan-950/30 backdrop-blur-sm",
      hasProgress ? "w-56" : "inline-flex items-center",
      className,
    )}>
      <div className="flex items-center gap-2.5">
        {/* Animated icon */}
        <div className="relative flex items-center justify-center w-7 h-7 rounded-md bg-blue-500/15 border border-cyan-500/25 overflow-hidden shrink-0">
          <ImageIcon className="w-3.5 h-3.5 text-cyan-200/90 relative z-10" />
          <div
            className="absolute inset-0 opacity-60 pointer-events-none"
            style={{
              background: "linear-gradient(108deg, transparent 38%, rgba(220,180,255,0.5) 50%, transparent 62%)",
              backgroundSize: "250% 100%",
              animation: "gaaia-shimmer 1.8s linear infinite",
            }}
          />
        </div>

        <div className="flex items-center justify-between flex-1 min-w-0">
          <span className="text-[12.5px] font-medium text-blue-100/90 tracking-tight">
            {hasProgress ? "Generating" : "Generating image"}
          </span>
          {hasProgress ? (
            <span className="text-[11px] tabular-nums text-cyan-300/70 font-mono ml-2 shrink-0">
              {progress.step}/{progress.total}
            </span>
          ) : (
            <span className="flex gap-0.5 items-center ml-2">
              <span className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse" style={{ animationDelay: "0ms" }} />
              <span className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse" style={{ animationDelay: "150ms" }} />
              <span className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse" style={{ animationDelay: "300ms" }} />
            </span>
          )}
        </div>
      </div>

      {/* Progress bar — only when we have real step data */}
      {hasProgress && (
        <div className="w-full h-1 rounded-full bg-blue-900/60 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-blue-400 to-cyan-400 transition-all duration-300 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  )
}


export function DiagramGenerating({ label, className }: { label?: string; className?: string }) {
  return (
    <div className={cn(
      "inline-flex items-center gap-2.5 px-3 py-2 rounded-lg border border-cyan-500/25 bg-cyan-950/40 backdrop-blur-sm",
      className,
    )}>
      <div className="relative flex items-center justify-center w-7 h-7 rounded-md bg-cyan-500/20 border border-cyan-400/25 overflow-hidden">
        <svg className="w-3.5 h-3.5 relative z-10" viewBox="0 0 24 24" fill="none"
          stroke="rgba(207,250,254,0.95)" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="4"  r="1.6" />
          <circle cx="4"  cy="20" r="1.6" />
          <circle cx="20" cy="20" r="1.6" />
          <line x1="12" y1="6"  x2="4"  y2="18" />
          <line x1="12" y1="6"  x2="20" y2="18" />
          <line x1="4"  y1="20" x2="20" y2="20" />
        </svg>
        <div
          className="absolute inset-0 opacity-60 pointer-events-none"
          style={{
            background: "linear-gradient(108deg, transparent 38%, rgba(103,232,249,0.5) 50%, transparent 62%)",
            backgroundSize: "250% 100%",
            animation: "gaaia-shimmer 1.8s linear infinite",
          }}
        />
      </div>
      <span className="text-[12.5px] font-medium text-cyan-100/90 tracking-tight">
        {label || "Rendering diagram"}
      </span>
      <span className="flex gap-0.5 items-center">
        <span className="w-1 h-1 rounded-full bg-cyan-300 animate-pulse" style={{ animationDelay: "0ms" }} />
        <span className="w-1 h-1 rounded-full bg-cyan-300 animate-pulse" style={{ animationDelay: "150ms" }} />
        <span className="w-1 h-1 rounded-full bg-cyan-300 animate-pulse" style={{ animationDelay: "300ms" }} />
      </span>
    </div>
  )
}
