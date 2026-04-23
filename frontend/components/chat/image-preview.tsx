"use client"

import { useEffect, useState } from "react"
import { Download, ImageIcon, Maximize2, X, ZoomIn, ZoomOut } from "lucide-react"
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
      {/* Inline card */}
      <div className={cn(
        "rounded-xl overflow-hidden border border-border/40 bg-muted/30",
        className,
      )}>
        {/* Image */}
        <div
          className="relative cursor-zoom-in group"
          onClick={() => !imgError && setLightbox(true)}
          title={imgError ? "Image unavailable" : "Click to enlarge"}
        >
          {imgError ? (
            <div className="w-full h-32 flex flex-col items-center justify-center gap-2 bg-muted/50 text-muted-foreground">
              <ImageIcon className="w-8 h-8 opacity-40" />
              <span className="text-xs opacity-60">Image unavailable</span>
            </div>
          ) : (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={prompt ?? "Generated image"}
                className="w-full h-auto object-cover max-h-80"
                onError={() => setImgError(true)}
              />
              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                <Maximize2 className="w-8 h-8 text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow-lg" />
              </div>
            </>
          )}
        </div>

        {/* Footer bar */}
        <div className="flex items-center justify-between px-3 py-2 bg-background/60 border-t border-border/30">
          <div className="flex items-center gap-1.5 min-w-0">
            <ImageIcon className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            {displayLabel && (
              <span className="text-xs text-muted-foreground truncate max-w-xs" title={prompt}>
                {displayLabel}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => setLightbox(true)}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title="View full size"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
            <a
              href={url}
              download="nova_image.png"
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title="Download PNG"
            >
              <Download className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
          onClick={() => setLightbox(false)}
        >
          <div
            className="relative max-w-[95vw] max-h-[95vh] flex flex-col gap-2"
            onClick={e => e.stopPropagation()}
          >
            {/* Controls */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}
                  className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors"
                  title="Zoom out"
                >
                  <ZoomOut className="w-4 h-4" />
                </button>
                <span className="text-white text-xs tabular-nums px-2">{Math.round(zoom * 100)}%</span>
                <button
                  onClick={() => setZoom(z => Math.min(4, z + 0.25))}
                  className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors"
                  title="Zoom in"
                >
                  <ZoomIn className="w-4 h-4" />
                </button>
                <a
                  href={url}
                  download="nova_image.png"
                  onClick={e => e.stopPropagation()}
                  className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors ml-1"
                  title="Download"
                >
                  <Download className="w-4 h-4" />
                </a>
              </div>
              <button
                onClick={() => setLightbox(false)}
                className="p-1.5 rounded-md bg-white/10 hover:bg-white/20 text-white transition-colors"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Zoomed image */}
            <div className="overflow-auto rounded-lg max-w-[95vw] max-h-[85vh]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={prompt ?? "Generated image"}
                style={{ transform: `scale(${zoom})`, transformOrigin: "top left" }}
                className="transition-transform duration-200"
              />
            </div>

            {displayLabel && (
              <p className="text-white/60 text-xs text-center truncate px-4">{displayLabel}</p>
            )}
          </div>
        </div>
      )}
    </>
  )
}


export function ImageGenerating({ className }: { prompt?: string; className?: string }) {
  return (
    <div className={cn(
      "rounded-xl overflow-hidden border border-violet-500/40 shadow-xl shadow-violet-900/30",
      className,
    )}>
      {/* Rich purple gradient canvas */}
      <div
        className="relative h-56 flex flex-col items-center justify-center gap-4 overflow-hidden"
        style={{ background: "linear-gradient(135deg, #2d1b69 0%, #4c1d95 35%, #6d28d9 65%, #7e22ce 100%)" }}
      >
        {/* Radial glow blob */}
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <div
            className="w-48 h-48 rounded-full"
            style={{
              background: "radial-gradient(circle, rgba(167,139,250,0.25) 0%, transparent 70%)",
              animation: "nova-pulse-ring 2.5s ease-in-out infinite",
            }}
          />
        </div>

        {/* Sweeping shimmer stripe (uses global keyframe) */}
        <div
          className="absolute inset-0 opacity-25 pointer-events-none"
          style={{
            background: "linear-gradient(108deg, transparent 38%, rgba(220,180,255,0.55) 50%, transparent 62%)",
            backgroundSize: "250% 100%",
            animation: "nova-shimmer 2.4s linear infinite",
          }}
        />

        {/* Icon circle + orbiting dot */}
        <div className="relative z-10">
          <div
            className="w-16 h-16 rounded-full flex items-center justify-center"
            style={{
              background: "rgba(139,92,246,0.3)",
              border: "1.5px solid rgba(196,181,253,0.45)",
              boxShadow: "0 0 28px rgba(139,92,246,0.5)",
            }}
          >
            <ImageIcon className="w-8 h-8 text-violet-100" />
          </div>
          {/* Orbiting accent dot */}
          <div
            className="absolute w-3 h-3 rounded-full"
            style={{
              top: "-4px", right: "-4px",
              background: "#e879f9",
              boxShadow: "0 0 10px rgba(232,121,249,0.8)",
              animation: "nova-orbit 2.2s linear infinite",
            }}
          />
        </div>

        {/* Label — no prompt shown */}
        <div className="relative z-10 flex flex-col items-center gap-1">
          <span
            className="text-base font-semibold tracking-wide"
            style={{ color: "#ede9fe" }}
          >
            Generating image…
          </span>
          <span className="text-xs" style={{ color: "rgba(196,181,253,0.6)" }}>
            This may take a moment
          </span>
        </div>

        {/* Bottom progress bar */}
        <div
          className="absolute bottom-0 inset-x-0 h-[3px] animate-pulse"
          style={{ background: "linear-gradient(90deg, transparent, #c084fc, #e879f9, transparent)" }}
        />
      </div>

      {/* Footer skeleton row */}
      <div
        className="px-4 py-3 flex items-center gap-3"
        style={{ background: "#130820", borderTop: "1px solid rgba(139,92,246,0.2)" }}
      >
        <div className="w-2.5 h-2.5 rounded-full bg-violet-500/50 animate-pulse flex-shrink-0" />
        <div className="h-2 rounded-full bg-violet-400/12 animate-pulse flex-1" />
        <div className="h-2 w-16 rounded-full bg-violet-400/8 animate-pulse" />
      </div>
    </div>
  )
}


export function DiagramGenerating({ label, className }: { label?: string; className?: string }) {
  return (
    <div className={cn(
      "rounded-xl overflow-hidden border border-cyan-500/40 shadow-xl shadow-cyan-900/30",
      className,
    )}>
      {/* Teal/cyan gradient canvas */}
      <div
        className="relative h-44 flex flex-col items-center justify-center gap-4 overflow-hidden"
        style={{ background: "linear-gradient(135deg, #0c2a3a 0%, #0e4d5e 35%, #0891b2 65%, #06b6d4 100%)" }}
      >
        {/* Radial glow */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div
            className="w-40 h-40 rounded-full"
            style={{
              background: "radial-gradient(circle, rgba(34,211,238,0.22) 0%, transparent 70%)",
              animation: "nova-pulse-ring 2.8s ease-in-out infinite",
            }}
          />
        </div>

        {/* Shimmer sweep */}
        <div
          className="absolute inset-0 opacity-25 pointer-events-none"
          style={{
            background: "linear-gradient(108deg, transparent 38%, rgba(103,232,249,0.55) 50%, transparent 62%)",
            backgroundSize: "250% 100%",
            animation: "nova-shimmer 2.6s linear infinite",
          }}
        />

        {/* Icon + orbit dot */}
        <div className="relative z-10">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center"
            style={{
              background: "rgba(8,145,178,0.3)",
              border: "1.5px solid rgba(103,232,249,0.4)",
              boxShadow: "0 0 24px rgba(8,145,178,0.5)",
            }}
          >
            <svg className="w-7 h-7" viewBox="0 0 24 24" fill="none"
              stroke="rgba(207,250,254,0.9)" strokeWidth="1.8" strokeLinecap="round">
              <circle cx="12" cy="4"  r="2" />
              <circle cx="4"  cy="20" r="2" />
              <circle cx="20" cy="20" r="2" />
              <line x1="12" y1="6"  x2="4"  y2="18" />
              <line x1="12" y1="6"  x2="20" y2="18" />
              <line x1="4"  y1="20" x2="20" y2="20" />
            </svg>
          </div>
          <div
            className="absolute w-2.5 h-2.5 rounded-full"
            style={{
              top: "-3px", right: "-3px",
              background: "#34d399",
              boxShadow: "0 0 8px rgba(52,211,153,0.8)",
              animation: "nova-orbit 2.6s linear infinite",
            }}
          />
        </div>

        {/* Label */}
        <div className="relative z-10 flex flex-col items-center gap-1">
          <span className="text-sm font-semibold tracking-wide" style={{ color: "#cffafe" }}>
            {label || "Rendering diagram…"}
          </span>
        </div>

        {/* Bottom bar */}
        <div
          className="absolute bottom-0 inset-x-0 h-[3px] animate-pulse"
          style={{ background: "linear-gradient(90deg, transparent, #22d3ee, #67e8f9, transparent)" }}
        />
      </div>

      {/* Footer skeleton */}
      <div
        className="px-4 py-3 flex items-center gap-3"
        style={{ background: "#061218", borderTop: "1px solid rgba(8,145,178,0.2)" }}
      >
        <div className="w-2.5 h-2.5 rounded-full bg-cyan-500/50 animate-pulse flex-shrink-0" />
        <div className="h-2 rounded-full bg-cyan-400/12 animate-pulse flex-1" />
        <div className="h-2 w-12 rounded-full bg-cyan-400/8 animate-pulse" />
      </div>
    </div>
  )
}
