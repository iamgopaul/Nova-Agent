"use client"

import { useRef, useState, useEffect, createContext, useContext, useMemo } from "react"
import type { ElementType } from "react"
import {
  Copy, Check, ThumbsUp, ThumbsDown, RefreshCw, Bot, User, Paperclip, Volume2, Square,
  BarChart2, GitBranch, Download, Maximize2, X, ExternalLink, ChevronDown, ChevronUp,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { MusicGenerating, MusicPlayer } from "@/components/chat/music-player"
import { DocumentCard, DocumentGenerating } from "@/components/chat/document-card"
import { ImageGenerating, ImagePreview, DiagramGenerating } from "@/components/chat/image-preview"
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area,
  PieChart, Pie, Cell, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts"
// StorySectionItem is defined and exported here; page.tsx imports from here

// ── Chart types ───────────────────────────────────────────────────────────────

export interface ChartDataset {
  label: string
  data: number[]
  color?: string
}

export interface ChartSpec {
  type: "bar" | "line" | "area" | "pie" | "scatter" | "table"
  title?: string
  labels?: string[]
  datasets?: ChartDataset[]
  headers?: string[]
  rows?: (string | number)[][]
  xlabel?: string
  ylabel?: string
}

const _CHART_COLOURS = [
  "#2563eb", "#16a34a", "#dc2626", "#d97706",
  "#7c3aed", "#0891b2", "#db2777", "#65a30d",
]

function NovaChartInner({ spec }: { spec: ChartSpec & { _height?: number } }) {
  const { type, title, labels = [], datasets = [], headers = [], rows = [], xlabel, ylabel } = spec

  // Transform spec → recharts data array: [{ name: "Jan", Sales: 100, Profit: 50 }, ...]
  const data = labels.map((lbl, i) => {
    const entry: Record<string, string | number> = { name: lbl }
    datasets.forEach(ds => { entry[ds.label] = ds.data[i] ?? 0 })
    return entry
  })

  const w = "100%"
  const h = spec._height ?? 320

  if (type === "table") {
    return (
      <div className="overflow-x-auto rounded-lg border border-border/30">
        {title && <p className="px-3 py-2 font-semibold text-sm text-foreground border-b border-border/30">{title}</p>}
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-blue-600/20">
              {headers.map((h, i) => (
                <th key={i} className="px-3 py-2 text-left font-semibold text-blue-400">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className={ri % 2 === 0 ? "bg-background/40" : "bg-muted/20"}>
                {row.map((cell, ci) => (
                  <td key={ci} className="px-3 py-1.5 text-foreground/80">{String(cell)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  const chartTitle = title && (
    <p className="text-sm font-semibold text-foreground/80 mb-2 text-center">{title}</p>
  )

  if (type === "pie") {
    const pieData = labels.map((lbl, i) => ({
      name: lbl,
      value: (datasets[0]?.data[i] ?? 0),
    }))
    return (
      <div>
        {chartTitle}
        <ResponsiveContainer width={w} height={h}>
          <PieChart>
            <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={110}
                 label={({ name, percent }) => `${name} ${(percent * 100).toFixed(1)}%`}
                 labelLine={{ stroke: "#94a3b8" }}>
              {pieData.map((_, idx) => (
                <Cell key={idx} fill={_CHART_COLOURS[idx % _CHART_COLOURS.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#e2e8f0" }} />
            <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 12 }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    )
  }

  const commonAxis = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
      <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} label={xlabel ? { value: xlabel, fill: "#94a3b8", fontSize: 11, position: "insideBottom", offset: -4 } : undefined} />
      <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} label={ylabel ? { value: ylabel, fill: "#94a3b8", fontSize: 11, angle: -90, position: "insideLeft" } : undefined} />
      <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#e2e8f0" }} />
      {datasets.length > 1 && <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 12 }} />}
    </>
  )

  if (type === "bar") {
    return (
      <div>
        {chartTitle}
        <ResponsiveContainer width={w} height={h}>
          <BarChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 24 }}>
            {commonAxis}
            {datasets.map((ds, i) => (
              <Bar key={i} dataKey={ds.label} fill={ds.color || _CHART_COLOURS[i % _CHART_COLOURS.length]} radius={[3, 3, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (type === "area") {
    return (
      <div>
        {chartTitle}
        <ResponsiveContainer width={w} height={h}>
          <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 24 }}>
            <defs>
              {datasets.map((ds, i) => {
                const c = ds.color || _CHART_COLOURS[i % _CHART_COLOURS.length]
                return (
                  <linearGradient key={i} id={`grad${i}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={c} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={c} stopOpacity={0.02} />
                  </linearGradient>
                )
              })}
            </defs>
            {commonAxis}
            {datasets.map((ds, i) => {
              const c = ds.color || _CHART_COLOURS[i % _CHART_COLOURS.length]
              return <Area key={i} type="monotone" dataKey={ds.label} stroke={c} strokeWidth={2} fill={`url(#grad${i})`} />
            })}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }

  // Default: line
  return (
    <div>
      {chartTitle}
      <ResponsiveContainer width={w} height={h}>
        <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 24 }}>
          {commonAxis}
          {datasets.map((ds, i) => {
            const c = ds.color || _CHART_COLOURS[i % _CHART_COLOURS.length]
            return <Line key={i} type="monotone" dataKey={ds.label} stroke={c} strokeWidth={2} dot={{ r: 4 }} />
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Wrapper that adds expand/lightbox to any chart */
function NovaChart({ spec }: { spec: ChartSpec }) {
  const [lightbox, setLightbox] = useState(false)

  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setLightbox(false) }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [lightbox])

  return (
    <>
      <div className="relative">
        {/* Expand button overlay */}
        <button
          onClick={() => setLightbox(true)}
          className="absolute top-1 right-1 z-10 p-1.5 rounded-md bg-black/30 hover:bg-black/60 text-white/70 hover:text-white transition-colors"
          title="Expand chart"
        >
          <Maximize2 size={13} />
        </button>
        <NovaChartInner spec={spec} />
      </div>

      {/* Fullscreen lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4"
          onClick={() => setLightbox(false)}
        >
          <div
            className="relative bg-[#0a0f1a] rounded-xl border border-border/30 p-6 shadow-2xl w-[90vw] max-h-[90vh] overflow-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-blue-400 text-sm font-medium">
                <BarChart2 size={14} />
                <span>{spec.title || "Chart"}</span>
              </div>
              <button
                onClick={() => setLightbox(false)}
                className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white transition-colors"
                title="Close"
              >
                <X size={16} />
              </button>
            </div>
            {/* Larger chart in lightbox */}
            <NovaChartInner spec={{ ...spec, _height: 520 } as ChartSpec} />
          </div>
        </div>
      )}
    </>
  )
}

function MermaidDiagram({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [svgContent, setSvgContent] = useState<string>("")
  const [lightbox, setLightbox] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function render() {
      try {
        const mermaid = (await import("mermaid")).default
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          themeVariables: {
            primaryColor: "#2563eb",
            primaryTextColor: "#e2e8f0",
            primaryBorderColor: "#334155",
            lineColor: "#64748b",
            secondaryColor: "#1e293b",
            tertiaryColor: "#0f172a",
            background: "#0f172a",
            mainBkg: "#1e293b",
            nodeBorder: "#2563eb",
            clusterBkg: "#0f172a",
            titleColor: "#e2e8f0",
            edgeLabelBackground: "#1e293b",
          },
        })
        const id = `mermaid-${Math.random().toString(36).slice(2)}`
        const { svg } = await mermaid.render(id, code)
        if (!cancelled) setSvgContent(svg)
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    }
    render()
    return () => { cancelled = true }
  }, [code])

  // Close lightbox on Escape
  useEffect(() => {
    if (!lightbox) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setLightbox(false) }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [lightbox])

  const downloadSvg = () => {
    if (!svgContent) return
    const blob = new Blob([svgContent], { type: "image/svg+xml" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url; a.download = "diagram.svg"; a.click()
    URL.revokeObjectURL(url)
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
        <p className="font-semibold mb-1">Diagram render error</p>
        <pre className="text-xs whitespace-pre-wrap opacity-70">{code}</pre>
      </div>
    )
  }

  const diagramContent = (fullscreen = false) => (
    <div
      className={cn(
        "flex justify-center overflow-auto",
        fullscreen ? "max-h-[80vh] max-w-[90vw]" : "overflow-x-auto"
      )}
      dangerouslySetInnerHTML={{ __html: svgContent }}
    />
  )

  return (
    <>
      <div className="relative rounded-lg border border-border/30 bg-[#0f172a] p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 text-blue-400 text-xs font-medium">
            <GitBranch size={13} />
            <span>Diagram</span>
          </div>
          {svgContent && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setLightbox(true)}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                title="Expand diagram"
              >
                <Maximize2 size={12} /> Expand
              </button>
              <button
                onClick={downloadSvg}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                title="Download as SVG"
              >
                <Download size={12} /> SVG
              </button>
            </div>
          )}
        </div>
        {svgContent
          ? <div ref={ref} className="flex justify-center overflow-x-auto cursor-zoom-in" onClick={() => setLightbox(true)}>
              {diagramContent()}
            </div>
          : <DiagramGenerating />
        }
      </div>

      {/* Fullscreen lightbox */}
      {lightbox && svgContent && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4"
          onClick={() => setLightbox(false)}
        >
          <div
            className="relative bg-[#0f172a] rounded-xl border border-border/30 p-6 shadow-2xl max-w-[95vw] max-h-[95vh] overflow-auto"
            onClick={e => e.stopPropagation()}
          >
            {/* Lightbox toolbar */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-blue-400 text-sm font-medium">
                <GitBranch size={14} />
                <span>Diagram</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={downloadSvg}
                  className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white transition-colors"
                >
                  <Download size={12} /> Download SVG
                </button>
                <button
                  onClick={() => setLightbox(false)}
                  className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white transition-colors"
                  title="Close"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            {diagramContent(true)}
          </div>
        </div>
      )}
    </>
  )
}

// ── Story Mode — interleaved paragraph + visual renderer ─────────────────────

const _VISUAL_TYPE_LABEL: Record<string, string> = {
  image:        "Photo-realistic",
  sketch:       "Pencil Sketch",
  watercolor:   "Watercolor",
  oil_painting: "Oil Painting",
  concept_art:  "Concept Art",
  pixel_art:    "Pixel Art",
}

/** Strip SD style suffixes to get a human-readable caption from an image prompt */
function _readableCaption(prompt: string, heading: string): string {
  if (heading) return heading
  // Remove common quality/style tags after the first comma
  return prompt.split(",")[0].trim()
}

function StoryVisual({ section }: { section: StorySectionItem }) {
  // Show if either a generated image prompt exists OR a web image URL is provided
  if (!section.image_prompt && !section.imageUrl) return null

  const caption    = _readableCaption(section.image_prompt, section.heading)
  const styleLabel = section.imageUrl && !section.image_prompt
    ? "Web Image"
    : (_VISUAL_TYPE_LABEL[section.visual_type] ?? "Visual")

  return (
    <div className="flex flex-col gap-1.5 my-1">
      {/* Style badge */}
      <div className="flex items-center gap-1.5">
        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-blue-600/15 text-blue-400 border border-blue-500/20">
          {styleLabel}
        </span>
      </div>

      {/* Image */}
      {section.imageGenerating && !section.imageUrl ? (
        <ImageGenerating prompt={section.image_prompt} />
      ) : section.imageUrl ? (
        <ImagePreview
          url={section.imageUrl}
          prompt={section.image_prompt || section.heading}
          caption={caption}
        />
      ) : null}

      {/* Caption below image */}
      {(section.imageUrl || section.imageGenerating) && caption && (
        <p className="text-xs text-center text-muted-foreground/70 italic px-2 pt-0.5">
          {caption}
        </p>
      )}
    </div>
  )
}

function StoryView({ sections }: { sections: StorySectionItem[] }) {
  return (
    <div className="flex flex-col gap-8 py-1">
      {sections.map((sec, i) => {
        // Split multi-paragraph text for proper rendering
        const paragraphs = sec.text
          ? sec.text.split(/\n\n+/).map(p => p.trim()).filter(Boolean)
          : []
        const hasVisual = !!(sec.image_prompt || sec.imageUrl)

        return (
          <div key={i} className="flex flex-col gap-3">
            {/* Section heading */}
            {sec.heading && (
              <h3 className="font-semibold text-foreground text-sm border-b border-border/20 pb-1.5 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-blue-600/20 text-blue-400 text-[10px] flex items-center justify-center flex-shrink-0 font-bold">
                  {i + 1}
                </span>
                {sec.heading}
              </h3>
            )}

            {/* Paragraph text — render each paragraph separately */}
            {paragraphs.length > 0 && (
              <div className="flex flex-col gap-2">
                {paragraphs.map((para, pi) => (
                  <p key={pi} className="text-foreground/85 leading-relaxed text-sm">{para}</p>
                ))}
              </div>
            )}

            {/* Visual — image placed right after its section text */}
            {hasVisual && (
              <StoryVisual section={sec} />
            )}
          </div>
        )
      })}
    </div>
  )
}

export interface MessageAttachment {
  name: string
  type: string
  size: number
  url?: string
}

export interface MessageSections {
  intro: string
  body: string
  outro: string
}

export interface DocItem {
  prompt: string
  format: string
  url?: string
  filename?: string
  sizeBytes?: number
  generating: boolean
}

export interface StorySectionItem {
  heading:       string
  text:          string
  image_prompt:  string
  visual_type:   "image" | "sketch" | "watercolor" | "oil_painting" | "concept_art" | "pixel_art"
  imageUrl?:     string
  imageGenerating?: boolean
}

export interface WebImage {
  title: string
  image_url: string
  thumbnail_url: string
  source_url: string
}

export interface WebArticle {
  title: string
  description: string
  url: string
  source: string
}

export interface WebResults {
  query: string
  images: WebImage[]
  articles: WebArticle[]
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  thinking?: boolean
  statusText?: string
  statusSteps?: string[]
  attachments?: MessageAttachment[]
  suggestions?: string[]
  suggestionsLoading?: boolean
  sections?: MessageSections
  sectionsLoading?: boolean
  musicPrompt?: string
  musicUrl?: string
  musicGenerating?: boolean
  musicError?: boolean
  imagePrompt?: string
  imageUrl?: string
  imageUrls?: string[]   // populated for multi-image requests
  imageGenerating?: boolean
  // Chart data (recharts-compatible spec)
  chartSpec?: ChartSpec
  chartGenerating?: boolean
  // Mermaid diagram code
  mermaidCode?: string
  // Story mode — interleaved paragraphs + visuals
  storySections?: StorySectionItem[]
  // Multiple documents can be generated from a single message
  docs?: DocItem[]
  // Web results (images + articles) from visual show requests
  webResults?: WebResults
  // Live weather widget
  weatherData?: WeatherData
  // Live clock widget
  showClock?: boolean
}

interface MessageBubbleProps {
  message: Message
  onSuggestionClick?: (suggestion: string, messageContent: string) => void
}

async function copyTextSafe(text: string): Promise<boolean> {
  if (!text) {
    return false
  }

  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    // Route rejections through .then so the browser does not log NotAllowedError as
    // an unhandled rejection; fall back to execCommand when write is denied.
    const usedClipboard = await navigator.clipboard
      .writeText(text)
      .then(() => true)
      .catch(() => false)
    if (usedClipboard) {
      return true
    }
  }

  try {
    const textarea = document.createElement("textarea")
    textarea.value = text
    textarea.setAttribute("readonly", "")
    textarea.style.position = "fixed"
    textarea.style.left = "-9999px"
    document.body.appendChild(textarea)
    textarea.focus()
    textarea.select()
    const ok = document.execCommand("copy")
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    const ok = await copyTextSafe(code)
    if (!ok) {
      return
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="my-3 rounded-xl overflow-hidden border border-border">
      <div className="flex items-center justify-between px-4 py-2 bg-muted border-b border-border">
        <span className="text-xs font-mono text-muted-foreground">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-primary" />
              <span className="text-primary">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copy code</span>
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-sm font-mono text-foreground bg-card leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  )
}

function parseContent(content: string) {
  const parts: Array<{ type: "text" | "code"; content: string; language?: string }> = []
  const codeRegex = /```(\w+)?\n([\s\S]*?)```/g
  let lastIndex = 0
  let match

  while ((match = codeRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      let textChunk = content.slice(lastIndex, match.index)
      // Strip a trailing label line (e.g. "Timeline Image\n") that Nova writes
      // before ```mermaid / ```json blocks — the UI already shows its own header.
      const lang = (match[1] || "").toLowerCase()
      if (lang === "mermaid" || lang === "json") {
        textChunk = textChunk.replace(/[ \t]*[A-Za-z][^\n]{0,80}\n\s*$/, "")
      }
      if (textChunk) {
        parts.push({ type: "text", content: textChunk })
      }
    }
    parts.push({ type: "code", language: match[1] || "plaintext", content: match[2].trim() })
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < content.length) {
    parts.push({ type: "text", content: content.slice(lastIndex) })
  }

  return parts
}

function FormattedText({ text }: { text: string }) {
  // Strip standalone label lines that Nova wrote immediately before a ```mermaid
  // or ```json fence (e.g. "Timeline Image\n```mermaid"). The component for each
  // type already renders its own header so the extra label is noise.
  const cleaned = text.replace(
    /(^|\n)([ \t]*[A-Za-z][^\n]{0,60})\n(```(?:mermaid|json))/g,
    "$1$3"
  )
  const lines = cleaned.split("\n")

  return (
    <div className="space-y-2">
      {lines.map((line, i) => {
        const headingMatch = line.match(/^(#{1,6})\s+(.*)$/)
        if (headingMatch) {
          const level = headingMatch[1].length
          return renderHeading(level, headingMatch[2], i)
        }
        if (line.startsWith("- ") || line.startsWith("* ")) {
          return (
            <div key={i} className="flex items-start gap-2 leading-7">
              <span className="text-primary mt-1.5 shrink-0">•</span>
              <span><RichLine line={line.replace(/^[-*] /, "")} /></span>
            </div>
          )
        }
        if (/^\d+\. /.test(line)) {
          const num = line.match(/^(\d+)\. /)?.[1]
          return (
            <div key={i} className="flex items-start gap-2 leading-7">
              <span className="text-primary shrink-0 font-medium">{num}.</span>
              <span><RichLine line={line.replace(/^\d+\. /, "")} /></span>
            </div>
          )
        }
        if (/^[-=]{3,}$/.test(line.trim())) return <hr key={i} className="border-border/40 my-3" />
        if (line === "") return <div key={i} className="h-1" />
        return <p key={i} className="leading-7 text-[15px]"><RichLine line={line} /></p>
      })}
    </div>
  )
}

function renderHeading(level: number, content: string, key: number) {
  const classesByLevel: Record<number, string> = {
    1: "text-2xl font-bold mt-4 mb-1",
    2: "text-xl font-semibold mt-4 mb-1",
    3: "text-lg font-semibold mt-3 mb-1",
    4: "text-base font-semibold mt-3 mb-1",
    5: "text-sm font-semibold mt-2 mb-1",
    6: "text-sm font-medium mt-2 mb-1",
  }
  const Tag = `h${Math.min(level, 6)}` as ElementType
  const classes = classesByLevel[level] || classesByLevel[6]
  return (
    <Tag key={key} className={cn(classes, "text-foreground font-sans tracking-tight")}><RichLine line={content} /></Tag>
  )
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|==[^=]+==|`[^`]+`|\*[^*]+\*|_[^_]+_)/g)
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith("==") && part.endsWith("==")) {
      return <mark key={i} className="rounded px-1 py-0.5 bg-primary/20 text-foreground">{part.slice(2, -2)}</mark>
    }
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) {
      return <em key={i} className="italic text-foreground/90">{part.slice(1, -1)}</em>
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="px-1.5 py-0.5 rounded-md bg-muted text-primary text-sm font-mono border border-border/50">
          {part.slice(1, -1)}
        </code>
      )
    }
    return part
  })
}

// Keywords that mean the user wants the message read aloud
const READ_ALOUD_TRIGGERS = [
  "read aloud", "read it aloud", "read it to me", "read this to me",
  "read it out", "read out loud", "listen to this", "play it",
  "speak it", "say it out loud", "read the response", "read the poem",
  "read the essay", "read this", "hear it",
]

function stripMarkdownForTTS(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "")              // fenced code blocks
    .replace(/`[^`]*`/g, "")                      // inline code
    .replace(/^#{1,6}\s+/gm, "")                  // heading markers (line-start only)
    .replace(/^[-=]{3,}$/gm, "")                  // horizontal rules --- / ===
    .replace(/^\s*[-*+>]\s/gm, "")               // bullet/blockquote markers
    .replace(/^\s*\d+\.\s/gm, "")                // numbered list markers
    .replace(/\*\*([^*]+)\*\*/g, "$1")            // **bold**
    .replace(/\*([^*]+)\*/g, "$1")                // *italic*
    .replace(/__([^_]+)__/g, "$1")                // __bold__
    .replace(/_([^_]+)_/g, "$1")                  // _italic_
    .replace(/~~([^~]+)~~/g, "$1")                // ~~strikethrough~~
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")      // [link](url)
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

// Strip markdown markers for word-count purposes — must produce the same
// word count as stripMarkdownForTTS so part offsets stay in sync with TTS.
function stripForWordCount(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`[^`]*`/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^[-=]{3,}$/gm, "")
    .replace(/^\s*[-*+>]\s/gm, "")
    .replace(/^\s*\d+\.\s/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/~~([^~]+)~~/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

// Approximate TTS reading speed (Kokoro tends to be ~3.2 words/sec)
const WORDS_PER_SEC = 3.2

// ── In-chat web embed (iframe) — open / minimize / close ─────────────────────
export type WebEmbedState = {
  url: string
  title: string
  mode: "open" | "minimized"
}

type WebEmbedContextValue = {
  open: (url: string, title?: string) => void
}

const WebEmbedContext = createContext<WebEmbedContextValue | null>(null)

function useWebEmbed(): WebEmbedContextValue | null {
  return useContext(WebEmbedContext)
}

function hostLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url.slice(0, 48)
  }
}

/** Only http(s) URLs are safe to pass to iframes and window.open. */
function isHttpUrlForEmbed(s: string): boolean {
  const t = (s || "").trim()
  if (!t) return false
  try {
    const href = /^https?:\/\//i.test(t) ? t : `https://${t}`
    const u = new URL(href)
    return u.protocol === "http:" || u.protocol === "https:"
  } catch {
    return false
  }
}

/** Public Brave Search pages (aligns with Brave Search API on the server; DDG is fallback only for fetches). */
function braveSearchPageUrl(query: string, kind: "web" | "images" = "web"): string {
  const q = encodeURIComponent(query)
  return kind === "web"
    ? `https://search.brave.com/search?q=${q}`
    : `https://search.brave.com/images?q=${q}`
}

function EmbeddedWebDrawer({
  panel,
  onClose,
  onMinimize,
  onExpand,
}: {
  panel: WebEmbedState | null
  onClose: () => void
  onMinimize: () => void
  onExpand: () => void
}) {
  if (!panel) return null
  const { url, title, mode } = panel
  if (!isHttpUrlForEmbed(url)) return null

  if (mode === "minimized") {
    return (
      <div className="mt-2 flex items-center gap-2 rounded-lg border border-blue-500/25 bg-blue-950/20 px-3 py-2">
        <span className="text-xs text-blue-300/90 truncate flex-1 min-w-0" title={url}>
          {title || hostLabel(url)}
        </span>
        <span className="text-[10px] text-muted-foreground shrink-0 hidden sm:inline">{hostLabel(url)}</span>
        <button
          type="button"
          onClick={onExpand}
          className="shrink-0 p-1.5 rounded-md text-blue-400 hover:bg-blue-500/15"
          title="Expand preview"
        >
          <ChevronUp className="w-4 h-4" />
        </button>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted"
          title="Open in browser tab"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10"
          title="Close"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="mt-2 rounded-xl border border-blue-500/30 overflow-hidden bg-card shadow-lg shadow-black/20">
      <div className="flex items-center gap-2 px-2 py-1.5 border-b border-border/40 bg-muted/40">
        <span className="text-xs font-medium text-foreground truncate flex-1 min-w-0" title={url}>
          {title || hostLabel(url)}
        </span>
        <button
          type="button"
          onClick={onMinimize}
          className="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted"
          title="Minimize"
        >
          <ChevronDown className="w-4 h-4" />
        </button>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-blue-400 hover:bg-blue-500/10"
          title="Open in new browser tab"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10"
          title="Close"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      <iframe
        src={url}
        title={title || "Web preview"}
        className="w-full h-[min(70vh,520px)] bg-background border-0"
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads"
        referrerPolicy="no-referrer-when-downgrade"
      />
      <p className="text-[10px] text-muted-foreground px-2 py-1.5 bg-muted/20 border-t border-border/30">
        Blank? Many sites forbid iframes (X-Frame-Options / CSP). Use the external tab icon to open the page normally.
      </p>
    </div>
  )
}

type LinkToken =
  | { kind: "text"; value: string }
  | { kind: "md"; label: string; url: string }
  | { kind: "raw"; url: string }

function tokenizeLineWithLinks(line: string): LinkToken[] {
  const out: LinkToken[] = []
  const re = /\[([^\]]+)\]\(([^)]+)\)|(https?:\/\/[^\s<>"'[\]()]+)/gi
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) {
      out.push({ kind: "text", value: line.slice(last, m.index) })
    }
    if (m[1] !== undefined && m[2] !== undefined) {
      const u = m[2].trim()
      if (u) {
        out.push({ kind: "md", label: m[1], url: u })
      } else {
        out.push({ kind: "text", value: m[0] })
      }
    } else if (m[3]) {
      out.push({ kind: "raw", url: m[3].trim() })
    }
    last = m.index + m[0].length
  }
  if (last < line.length) {
    out.push({ kind: "text", value: line.slice(last) })
  }
  return out.length ? out : [{ kind: "text", value: line }]
}

function RichLine({ line }: { line: string }) {
  const embed = useWebEmbed()
  const tokens = useMemo(() => tokenizeLineWithLinks(line), [line])

  return (
    <>
      {tokens.map((tok, ti) => {
        if (tok.kind === "text") {
          return <span key={ti}>{renderInline(tok.value)}</span>
        }
        const url = tok.url
        const label = tok.kind === "md" ? tok.label : tok.url
        if (!isHttpUrlForEmbed(url)) {
          return (
            <span key={ti} className="text-muted-foreground break-all">
              {tok.kind === "md" ? renderInline(tok.label) : label}
            </span>
          )
        }
        if (!embed) {
          return (
            <a key={ti} href={url} target="_blank" rel="noopener noreferrer" className="text-blue-400 underline break-all">
              {label}
            </a>
          )
        }
        return (
          <button
            key={ti}
            type="button"
            onClick={() => embed.open(url, tok.kind === "md" ? tok.label : undefined)}
            className="text-blue-400 hover:text-blue-300 underline underline-offset-2 text-left break-all inline"
          >
            {tok.kind === "md" ? renderInline(tok.label) : label}
          </button>
        )
      })}
    </>
  )
}

// Global singleton — only one message may speak at a time
let _globalStopSpeaking: (() => void) | null = null

// Detect whether a paragraph is short conversational prose (intro/outro candidate)
function isShortProse(p: string): boolean {
  const t = p.trim()
  if (!t) return false
  if (t.startsWith("```") || t.startsWith("#") || t.startsWith("- ") ||
      t.startsWith("* ") || /^\d+\./.test(t)) return false
  const lines = t.split("\n").filter(Boolean)
  return lines.length <= 3 && t.length <= 220
}

type ResponseSections = MessageSections

function splitResponseSections(content: string): ResponseSections {
  const paras = content.split(/\n{2,}/)
  if (paras.length <= 1) return { intro: "", body: content, outro: "" }

  let introEnd = 0
  let outroStart = paras.length

  // Grab up to 1 short-prose paragraph as intro, only if there is body content remaining
  if (isShortProse(paras[0]) && paras.length > 1) introEnd = 1

  // Grab up to 1 short-prose paragraph as outro, only if it won't eat all body
  const lastIdx = paras.length - 1
  if (lastIdx > introEnd && isShortProse(paras[lastIdx])) outroStart = lastIdx

  const intro = introEnd > 0 ? paras.slice(0, introEnd).join("\n\n") : ""
  const outro = outroStart < paras.length ? paras.slice(outroStart).join("\n\n") : ""
  const body  = paras.slice(introEnd, outroStart).join("\n\n")

  if (!intro && !outro) return { intro: "", body: content, outro: "" }
  return { intro, body, outro }
}

// Strip inline markdown for word counting only (not for display)
function stripInlineMarkdown(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
}

type InlineSegment =
  | { tag: "strong" | "em" | "code" | "span"; content: string }
  | { tag: "ws"; content: string }

// Tokenize text into inline markdown segments (preserves bold/italic/code)
function parseInlineSegments(text: string): InlineSegment[] {
  const result: InlineSegment[] = []
  let s = text
  while (s.length > 0) {
    let m: RegExpMatchArray | null
    if ((m = s.match(/^(\*\*|__)([\s\S]*?)\1/)))  { result.push({ tag: "strong", content: m[2] }); s = s.slice(m[0].length); continue }
    if ((m = s.match(/^(\*|_)([\s\S]*?)\1/)))      { result.push({ tag: "em",     content: m[2] }); s = s.slice(m[0].length); continue }
    if ((m = s.match(/^`([^`]+)`/)))               { result.push({ tag: "code",   content: m[1] }); s = s.slice(m[0].length); continue }
    if ((m = s.match(/^(\s+)/)))                   { result.push({ tag: "ws",     content: m[1] }); s = s.slice(m[0].length); continue }
    if ((m = s.match(/^(\S+)/)))                   { result.push({ tag: "span",   content: m[1] }); s = s.slice(m[0].length); continue }
    s = s.slice(1)
  }
  return result
}

// Render whitespace, converting \n to <br /> so line breaks are preserved in HTML
function renderWs(content: string, key: number): React.ReactNode {
  if (!content.includes("\n")) return <span key={key}>{content}</span>
  const lines = content.split("\n")
  return lines.flatMap((chunk, i) => {
    const nodes: React.ReactNode[] = []
    if (chunk) nodes.push(<span key={`${key}-t${i}`}>{chunk}</span>)
    if (i < lines.length - 1) nodes.push(<br key={`${key}-br${i}`} />)
    return nodes
  })
}

// Render word tokens inside a segment, tracking global word index
function WordTokens({
  content, tag, activeWordIdx, wordOffset, wordCountRef,
}: {
  content: string
  tag: string
  activeWordIdx: number
  wordOffset: number
  wordCountRef: React.MutableRefObject<number>
}) {
  const tokens = content.split(/(\s+)/)
  // Word index is still tracked (for potential future use) but no visual highlight applied
  void activeWordIdx
  const spans = tokens.map((token, i) => {
    if (/^\s+$/.test(token)) return renderWs(token, i)
    wordCountRef.current++
    return <span key={i}>{token}</span>
  })
  if (tag === "strong") return <strong>{spans}</strong>
  if (tag === "em")     return <em>{spans}</em>
  if (tag === "code")   return <code className="text-xs bg-muted/60 px-0.5 rounded">{spans}</code>
  return <>{spans}</>
}

// Strip only inline markers (bold/italic/code) from a single line for word rendering.
// This keeps word count consistent with stripForWordCount while avoiding raw `**` in display.
function stripInlineMarkers(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
}

// Markdown-aware read-along renderer. Preserves headings, bullets, numbered lists,
// and horizontal rules while tracking words across all text nodes.
function ReadAlongFormattedText({
  text, activeWordIdx, wordOffset,
}: { text: string; activeWordIdx: number; wordOffset: number }) {
  const lines = text.split("\n")
  const wc = { current: 0 }
  const classesByLevel: Record<number, string> = {
    1: "text-2xl font-bold mt-4 mb-1",
    2: "text-xl font-semibold mt-4 mb-1",
    3: "text-lg font-semibold mt-3 mb-1",
    4: "text-base font-semibold mt-3 mb-1",
    5: "text-sm font-semibold mt-2 mb-1",
    6: "text-sm font-medium mt-2 mb-1",
  }
  return (
    <div className="space-y-2">
      {lines.map((line, i) => {
        const hm = line.match(/^(#{1,6})\s+(.*)$/)
        if (hm) {
          const level = hm[1].length
          const Tag = `h${Math.min(level, 6)}` as ElementType
          return (
            <Tag key={i} className={cn(classesByLevel[level] ?? classesByLevel[6], "text-foreground font-sans tracking-tight")}>
              <WordTokens content={stripInlineMarkers(hm[2])} tag="span" activeWordIdx={activeWordIdx} wordOffset={wordOffset} wordCountRef={wc} />
            </Tag>
          )
        }
        if (line.startsWith("- ") || line.startsWith("* ")) {
          return (
            <div key={i} className="flex items-start gap-2 leading-7">
              <span className="text-primary mt-1.5 shrink-0">•</span>
              <span>
                <WordTokens content={stripInlineMarkers(line.replace(/^[-*] /, ""))} tag="span" activeWordIdx={activeWordIdx} wordOffset={wordOffset} wordCountRef={wc} />
              </span>
            </div>
          )
        }
        if (/^\d+\. /.test(line)) {
          const num = line.match(/^(\d+)\. /)?.[1]
          return (
            <div key={i} className="flex items-start gap-2 leading-7">
              <span className="text-primary shrink-0 font-medium">{num}.</span>
              <span>
                <WordTokens content={stripInlineMarkers(line.replace(/^\d+\. /, ""))} tag="span" activeWordIdx={activeWordIdx} wordOffset={wordOffset} wordCountRef={wc} />
              </span>
            </div>
          )
        }
        if (/^[-=]{3,}$/.test(line.trim())) return <hr key={i} className="border-border/40 my-3" />
        if (line === "") return <div key={i} className="h-1" />
        return (
          <p key={i} className="leading-7 text-[15px]">
            <WordTokens content={stripInlineMarkers(line)} tag="span" activeWordIdx={activeWordIdx} wordOffset={wordOffset} wordCountRef={wc} />
          </p>
        )
      })}
    </div>
  )
}

// Render a text block word-by-word preserving bold/italic/code formatting
function ReadAlongPart({
  text, activeWordIdx, wordOffset,
}: { text: string; activeWordIdx: number; wordOffset: number }) {
  const segments = parseInlineSegments(text)
  // Use a ref-like object to thread wordCount across segments without re-renders
  const wc = { current: 0 }
  return (
    <span className="whitespace-pre-wrap">
      {segments.map((seg, i) => {
        if (seg.tag === "ws") return renderWs(seg.content, i)
        return (
          <WordTokens
            key={i}
            content={seg.content}
            tag={seg.tag}
            activeWordIdx={activeWordIdx}
            wordOffset={wordOffset}
            wordCountRef={wc}
          />
        )
      })}
    </span>
  )
}

// ── WeatherData type ──────────────────────────────────────────────────────────
export interface WeatherForecastDay {
  date: string
  max_c: string
  min_c: string
  max_f: string
  min_f: string
  code: string
  desc: string
}

export interface WeatherData {
  location:      string
  temp_c:        string
  temp_f:        string
  feels_like_c:  string
  feels_like_f:  string
  code:          string
  desc:          string
  humidity:      string
  wind_mph:      string
  wind_kmph:     string
  wind_dir:      string
  uv_index:      string
  visibility_km: string
  precip_mm:     string
  obs_time:      string
  forecast:      WeatherForecastDay[]
}

// WMO weather code → emoji
function weatherEmoji(code: string | number): string {
  const c = Number(code)
  if (c === 113) return "☀️"
  if (c === 116) return "⛅"
  if (c === 119) return "🌥️"
  if (c === 122) return "☁️"
  if (c === 143 || c === 248 || c === 260) return "🌫️"
  if (c === 200 || c === 386 || c === 389 || c === 392 || c === 395) return "⛈️"
  if (c === 227 || c === 230) return "🌨️"
  if ([182, 311, 314, 317, 362, 365, 374, 377].includes(c)) return "🌨️"
  if ([176, 263, 266, 281, 284, 293, 296, 353].includes(c)) return "🌦️"
  if ([299, 302, 305, 308, 356, 359].includes(c)) return "🌧️"
  if ([317, 320, 323, 326, 329, 332, 335, 338, 368, 371].includes(c)) return "❄️"
  return "🌡️"
}

// Weather card gradient by condition family
function weatherGradient(code: string): string {
  const c = Number(code)
  if (c === 113) return "from-blue-500/25 via-sky-400/10 to-orange-300/10"
  if (c === 116 || c === 119) return "from-blue-400/20 via-slate-500/10 to-slate-600/5"
  if (c === 122) return "from-slate-500/20 to-slate-700/10"
  if (c >= 200 && c <= 230) return "from-purple-900/30 via-slate-800/20 to-gray-900/10"
  if (c >= 293 && c <= 359) return "from-blue-800/25 via-indigo-700/10 to-blue-900/10"
  if (c >= 320 && c <= 395) return "from-blue-200/10 via-slate-300/5 to-indigo-200/5"
  if (c === 143 || c === 248 || c === 260) return "from-gray-500/20 to-slate-600/10"
  return "from-blue-500/15 to-slate-600/10"
}

// ── WeatherCard ───────────────────────────────────────────────────────────────
function WeatherCard({ data }: { data: WeatherData }) {
  const useFahrenheit = true // could be a user pref
  const temp   = useFahrenheit ? `${data.temp_f}°F`        : `${data.temp_c}°C`
  const feels  = useFahrenheit ? `${data.feels_like_f}°F`  : `${data.feels_like_c}°C`
  const icon   = weatherEmoji(data.code)
  const grad   = weatherGradient(data.code)

  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })

  return (
    <div className={cn("mt-3 rounded-2xl border border-white/10 bg-gradient-to-br p-4 backdrop-blur-sm", grad)}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <svg className="w-3.5 h-3.5 text-blue-300/80" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/><circle cx="12" cy="9" r="2.5"/>
          </svg>
          <span className="text-sm font-medium text-white/90">{data.location}</span>
        </div>
        <span className="text-xs text-white/50">{today}</span>
      </div>

      {/* Main temp */}
      <div className="flex items-center gap-4 mb-4">
        <span className="text-5xl">{icon}</span>
        <div>
          <div className="text-4xl font-light text-white leading-none">{temp}</div>
          <div className="text-sm text-white/70 mt-1">{data.desc}</div>
          <div className="text-xs text-white/50 mt-0.5">Feels like {feels}</div>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {[
          { label: "Wind",     value: `${data.wind_mph} mph ${data.wind_dir}` },
          { label: "Humidity", value: `${data.humidity}%` },
          { label: "UV",       value: data.uv_index || "—" },
          { label: "Precip",   value: `${data.precip_mm} mm` },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-xl bg-white/5 border border-white/10 p-2 text-center">
            <div className="text-[10px] text-white/50 uppercase tracking-wide mb-0.5">{label}</div>
            <div className="text-xs font-medium text-white/85">{value}</div>
          </div>
        ))}
      </div>

      {/* 3-day forecast */}
      {data.forecast.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {data.forecast.map((day, i) => {
            const dayLabel = i === 0 ? "Today"
              : new Date(day.date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" })
            const hi = useFahrenheit ? `${day.max_f}°` : `${day.max_c}°`
            const lo = useFahrenheit ? `${day.min_f}°` : `${day.min_c}°`
            return (
              <div key={day.date} className="rounded-xl bg-white/5 border border-white/10 p-2 text-center">
                <div className="text-[10px] text-white/50 mb-1">{dayLabel}</div>
                <div className="text-lg">{weatherEmoji(day.code)}</div>
                <div className="text-xs text-white/80 mt-0.5 font-medium">{hi}</div>
                <div className="text-[10px] text-white/40">{lo}</div>
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-2 text-[10px] text-white/30 text-right">
        via wttr.in · {data.obs_time || "live"}
      </div>
    </div>
  )
}

// ── LiveClock ─────────────────────────────────────────────────────────────────
function LiveClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const timeStr = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  const dateStr = now.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })
  const tz      = Intl.DateTimeFormat().resolvedOptions().timeZone.replace(/_/g, " ")

  return (
    <div className="mt-3 rounded-2xl border border-white/10 bg-gradient-to-br from-violet-900/30 via-indigo-900/20 to-blue-900/10 p-5 text-center backdrop-blur-sm">
      <div className="text-5xl font-mono font-light text-white tracking-wider mb-2">{timeStr}</div>
      <div className="text-sm text-white/70 mb-1">{dateStr}</div>
      <div className="flex items-center justify-center gap-1 text-xs text-white/40">
        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        {tz}
      </div>
    </div>
  )
}

// ── WebResultsPanel ───────────────────────────────────────────────────────────
function WebResultsPanel({ results }: { results: WebResults }) {
  const webEmbed = useWebEmbed()
  const [lightbox, setLightbox]   = useState<WebImage | null>(null)
  const [imgErrors, setImgErrors] = useState<Set<number>>(new Set())
  const hasImages   = results.images.length > 0
  const hasArticles = results.articles.length > 0
  const visibleImgs = results.images.filter((_, i) => !imgErrors.has(i))
  const empty       = !hasImages && !hasArticles

  const markError = (i: number) =>
    setImgErrors(prev => new Set([...prev, i]))

  return (
    <div className="mt-4 rounded-xl border border-border/40 bg-muted/20 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30 bg-muted/30">
        <svg className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <span className="text-xs font-medium text-muted-foreground">Web results for</span>
        <span className="text-xs font-semibold text-foreground truncate max-w-[200px]">{results.query}</span>
        <a
          href={braveSearchPageUrl(results.query, "web")}
          target="_blank"
          rel="noopener noreferrer"
          title="Open in Brave Search (public search; matches the Brave Search API used for in-app results — DuckDuckGo is only a server-side fallback when the API is unavailable)"
          className="ml-auto flex items-center gap-1 text-[10px] text-blue-400/70 hover:text-blue-400 transition-colors flex-shrink-0"
        >
          Search web
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </a>
      </div>

      {empty && (
        <div className="px-3 py-4 text-center border-b border-border/20">
          <p className="text-xs text-muted-foreground leading-relaxed">
            No image or article previews were returned (network, rate limits, or provider filters).
            Use <span className="text-foreground font-medium">Search web</span> (Brave Search) above to open the same query in your browser.
          </p>
        </div>
      )}

      {/* Images — grid layout, larger thumbnails */}
      {hasImages && (
        <div className="p-3 border-b border-border/20">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
              Images {visibleImgs.length > 0 && <span className="normal-case font-normal">({visibleImgs.length})</span>}
            </p>
            <a
              href={braveSearchPageUrl(results.query, "images")}
              target="_blank"
              rel="noopener noreferrer"
              title="More image results in Brave Search"
              className="text-[10px] text-blue-400/70 hover:text-blue-400 transition-colors"
            >
              More images →
            </a>
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            {results.images.map((img, i) => (
              !imgErrors.has(i) && (
                <div
                  key={i}
                  className="relative group cursor-pointer aspect-square overflow-hidden rounded-lg border border-border/30 hover:border-blue-400/60 transition-colors"
                  onClick={() => setLightbox(img)}
                >
                  <img
                    src={img.thumbnail_url || img.image_url}
                    alt={img.title || `Result ${i + 1}`}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                    onError={() => markError(i)}
                  />
                  {/* Hover overlay */}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-1.5">
                    {img.title && (
                      <p className="text-white text-[9px] leading-tight line-clamp-2">{img.title}</p>
                    )}
                    <div className="flex gap-1 mt-1">
                      <button
                        onClick={e => { e.stopPropagation(); setLightbox(img) }}
                        className="flex-1 py-0.5 rounded bg-white/20 hover:bg-white/30 text-white text-[9px] text-center"
                      >
                        Expand
                      </button>
                      <button
                        onClick={e => {
                          e.stopPropagation()
                          const u = (img.source_url || img.image_url || "").trim()
                          if (!isHttpUrlForEmbed(u)) return
                          if (webEmbed) webEmbed.open(u, img.title || "Image source")
                          else window.open(u, "_blank", "noopener")
                        }}
                        disabled={!isHttpUrlForEmbed((img.source_url || img.image_url || "").trim())}
                        className="flex-1 py-0.5 rounded bg-white/20 enabled:hover:bg-white/30 disabled:opacity-40 disabled:cursor-not-allowed text-white text-[9px] text-center"
                      >
                        Source
                      </button>
                    </div>
                  </div>
                </div>
              )
            ))}
          </div>
        </div>
      )}

      {/* Articles */}
      {hasArticles && (
        <div className="p-3">
          <p className="text-[11px] font-medium text-muted-foreground mb-2 uppercase tracking-wide">Articles</p>
          <div className="space-y-2">
            {results.articles.map((art, i) => {
              const href = (art.url || "").trim()
              const canOpen = isHttpUrlForEmbed(href)
              return (
                <div
                  key={i}
                  role={canOpen ? "button" : undefined}
                  tabIndex={canOpen ? 0 : undefined}
                  onClick={canOpen ? () => webEmbed?.open(art.url, art.title) : undefined}
                  onKeyDown={canOpen ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); webEmbed?.open(art.url, art.title) } } : undefined}
                  className={cn(
                    "flex items-start gap-2.5 p-2 rounded-lg transition-colors group text-left",
                    canOpen && "hover:bg-muted/60 cursor-pointer",
                    !canOpen && "cursor-default",
                  )}
                >
                <div className="w-4 h-4 mt-0.5 rounded-full bg-blue-500/15 flex items-center justify-center flex-shrink-0">
                  <svg className="w-2.5 h-2.5 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                  </svg>
                </div>
                <div className="min-w-0 flex-1">
                  <p className={cn(
                    "text-[13px] font-medium text-foreground truncate transition-colors leading-tight",
                    canOpen && "group-hover:text-blue-400",
                  )}>{art.title}</p>
                  {art.description && <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">{art.description}</p>}
                  {canOpen ? (
                    <p className="text-[10px] text-blue-400/70 mt-0.5 truncate">{art.source}</p>
                  ) : (
                    <p className="text-[10px] text-amber-600/90 mt-0.5">Snippet only — use Brave Search above for links.</p>
                  )}
                </div>
                {canOpen ? (
                  <button
                    type="button"
                    title="Open in new browser tab"
                    className="shrink-0 p-1 rounded-md text-muted-foreground/50 hover:text-blue-400 hover:bg-blue-500/10"
                    onClick={e => { e.stopPropagation(); window.open(art.url, "_blank", "noopener,noreferrer") }}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                ) : null}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
        >
          <div className="relative max-w-3xl w-full" onClick={e => e.stopPropagation()}>
            <button
              onClick={() => setLightbox(null)}
              className="absolute -top-10 right-0 text-white/70 hover:text-white transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
            <img
              src={lightbox.image_url}
              alt={lightbox.title}
              className="w-full max-h-[80vh] object-contain rounded-xl"
            />
            {lightbox.title && (
              <p className="text-white/80 text-sm text-center mt-2">{lightbox.title}</p>
            )}
            <div className="flex justify-center gap-3 mt-3">
              <a
                href={lightbox.image_url}
                download
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs transition-colors"
              >
                <Download className="w-3.5 h-3.5" /> Download
              </a>
              <a
                href={lightbox.source_url || lightbox.image_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs transition-colors"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                Open source
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


export function MessageBubble({ message, onSuggestionClick }: MessageBubbleProps) {
  const [liked, setLiked] = useState(false)
  const [disliked, setDisliked] = useState(false)
  const [copied, setCopied] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [activeWordIdx, setActiveWordIdx] = useState(-1)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const ttsAudioContextRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number | null>(null)
  // Sentence-chunk word tracking — chunk N = sentence N = known word range
  const currentAudioElRef    = useRef<HTMLAudioElement | null>(null)
  const currentChunkIdxRef   = useRef(0)
  const sentenceWordRangesRef = useRef<Array<{start: number; end: number}>>([])
  // Pre-split clean words for tracking; populated when speaking starts
  const allWordsRef = useRef<string[]>([])
  // Word offset for each part: partWordOffsets[i] = index of first word in parts[i]
  const partWordOffsetsRef = useRef<number[]>([])

  const isUser = message.role === "user"
  // Prefer LLM-formatted sections; fall back to heuristic while loading or if unavailable
  const sections: ResponseSections = message.sections ?? splitResponseSections(message.content)
  // Suppress json/mermaid code blocks from the text body when the message
  // already has a dedicated rendered visualization (chart, mermaid, story).
  // This stops the raw JSON/mermaid source from appearing as an ugly code block.
  const _hasChart   = !!(message.chartSpec || message.chartGenerating)
  const _hasMermaid = !!message.mermaidCode
  const _bodyText   = (sections.body || message.content)

  function _filterVisualCodeBlocks(raw: string): string {
    return raw
      // Always remove ```mermaid blocks from the text body — if the backend detected
      // a diagram intent it renders MermaidDiagram separately; if it didn't, the LLM
      // produced the block erroneously (e.g. for an image request) and it should be hidden.
      .replace(/```mermaid[\s\S]*?```/g, "")
      // Remove ```json blocks only when a chart spec has been extracted & rendered
      .replace(_hasChart ? /```json[\s\S]*?```/g : /(?!)/g, "")
  }

  const parts = parseContent(_filterVisualCodeBlocks(_bodyText))
  const attachments = message.attachments || []
  // Filter out any "read aloud" suggestion — that button lives permanently in the header
  const suggestions = (message.suggestions || [])
    .filter(s => !READ_ALOUD_TRIGGERS.some(t => s.toLowerCase().includes(t)))
    .slice(0, 3)

  const [webEmbed, setWebEmbed] = useState<WebEmbedState | null>(null)

  const webEmbedApi = useMemo<WebEmbedContextValue>(() => ({
    open: (url: string, title?: string) => {
      const trimmed = (url || "").trim()
      if (!isHttpUrlForEmbed(trimmed)) return
      try {
        const href = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
        const u = new URL(href)
        setWebEmbed({
          url: u.href,
          title: (title || "").trim() || hostLabel(u.href),
          mode: "open",
        })
      } catch {
        /* invalid URL */
      }
    },
  }), [])

  const handleCopy = async () => {
    const ok = await copyTextSafe(message.content)
    if (!ok) {
      return
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const stopRequestedRef = useRef(false)

  const stopSpeaking = () => {
    stopRequestedRef.current = true
    if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
    if (audioRef.current) { audioRef.current.pause(); audioRef.current.src = ""; audioRef.current = null }
    if (ttsAudioContextRef.current) {
      try { void ttsAudioContextRef.current.close() } catch { /* */ }
      ttsAudioContextRef.current = null
    }
    setIsSpeaking(false)
    setActiveWordIdx(-1)
    allWordsRef.current = []
    partWordOffsetsRef.current = []
    sentenceWordRangesRef.current = []
    currentChunkIdxRef.current  = 0
    currentAudioElRef.current   = null
    if (_globalStopSpeaking === stopSpeaking) _globalStopSpeaking = null
  }

  // Word tracker — word highlighting is disabled; this is a no-op placeholder kept
  // so the rest of the audio playback pipeline (chunk sequencing, stopSpeaking) is unchanged.
  const startWordTracker = (audioEl: HTMLAudioElement) => {
    currentAudioElRef.current = audioEl
    // RAF loop removed — word-by-word highlighting is turned off.
  }

  const finishReading = () => {
    if (rafRef.current !== null) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
    setActiveWordIdx(allWordsRef.current.length - 1)
    setTimeout(() => {
      setIsSpeaking(false)
      setActiveWordIdx(-1)
      allWordsRef.current = []
      partWordOffsetsRef.current = []
      sentenceWordRangesRef.current = []
      currentChunkIdxRef.current  = 0
    }, 500)
  }

  const handleReadAloud = async () => {
    if (isSpeaking) { stopSpeaking(); return }

    // Stop any other message that is currently being read aloud
    if (_globalStopSpeaking && _globalStopSpeaking !== stopSpeaking) {
      _globalStopSpeaking()
    }
    // Register this instance as the active speaker
    _globalStopSpeaking = stopSpeaking

    // Use the body section for TTS + word tracking so offsets align with rendered parts.
    // If there's no section split yet, fall back to full content.
    const bodyText = sections.body || message.content
    const clean = stripMarkdownForTTS(bodyText)
    if (!clean) return

    // Pre-compute word list and per-part word offsets (body parts only)
    const cleanWords = clean.split(/\s+/).filter(Boolean)
    allWordsRef.current = cleanWords

    const offsets: number[] = []
    let offset = 0
    for (const part of parts) {
      offsets.push(offset)
      if (part.type !== "code") {
        // Use the same stripping logic as stripMarkdownForTTS so word counts align
        offset += stripForWordCount(part.content).split(/\s+/).filter(Boolean).length
      }
    }
    partWordOffsetsRef.current = offsets

    // Build sentence → word-range map using the SAME split the backend uses.
    // Backend _CHUNK_RE: r'(?<=[.!?])\s+|(?<=[,;:])\s+|\n+'
    // Splitting at clause boundaries keeps chunks to ~2-6 words, which makes
    // linear-interpolation far more accurate.
    const sentences = clean.split(/(?<=[.!?,;:])\s+|\n+/).map(s => s.trim()).filter(Boolean)
    const ranges: Array<{start: number; end: number}> = []
    let wOffset = 0
    for (const sent of sentences) {
      const wCount = sent.split(/\s+/).filter(Boolean).length
      ranges.push({ start: wOffset, end: wOffset + wCount })
      wOffset += wCount
    }
    // If split produced fewer ranges than words (e.g. no sentence-ending punctuation),
    // fall back to a single range covering everything.
    sentenceWordRangesRef.current = ranges.length > 0 ? ranges : [{ start: 0, end: cleanWords.length }]
    currentChunkIdxRef.current = 0
    currentAudioElRef.current  = null

    setIsSpeaking(true)
    setActiveWordIdx(0)
    stopRequestedRef.current = false

    // Streaming endpoint — plays first WAV chunk immediately
    try {
      const res = await fetch("/api/voice/speak/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: clean }),
      })
      if (!res.ok || !res.body) throw new Error("stream failed")

      const chunkQueue: Blob[] = []
      let streamDone = false
      let notifyPlayer: (() => void) | null = null

      const readStream = async () => {
        const reader = res.body!.getReader()
        let buf = new Uint8Array(0)
        while (true) {
          const { done, value } = await reader.read()
          if (value) {
            const next = new Uint8Array(buf.length + value.length)
            next.set(buf); next.set(value, buf.length)
            buf = next
          }
          while (buf.length >= 4) {
            const size = new DataView(buf.buffer, buf.byteOffset, 4).getUint32(0, true)
            if (buf.length < 4 + size) break
            chunkQueue.push(new Blob([buf.slice(4, 4 + size)], { type: "audio/wav" }))
            buf = buf.slice(4 + size)
            notifyPlayer?.(); notifyPlayer = null
          }
          if (done) break
        }
        streamDone = true
        notifyPlayer?.(); notifyPlayer = null
      }

      const playQueue = async () => {
        const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        if (AC) {
          if (ttsAudioContextRef.current) {
            try { void ttsAudioContextRef.current.close() } catch { /* */ }
            ttsAudioContextRef.current = null
          }
          const ctx = new AC()
          ttsAudioContextRef.current = ctx
          try {
            if (ctx.state === "suspended") {
              await ctx.resume()
            }
          } catch {
            /* */
          }
          // Pipelined decode: while chunk N plays, N+1 is being decoded to avoid gaps.
          const decodeWav = (blob: Blob) =>
            blob.arrayBuffer().then(raw => ctx.decodeAudioData(raw.slice(0)))
          let nextTime = ctx.currentTime + 0.04
          const decodeStream = (async function* () {
            for (;;) {
              while (chunkQueue.length === 0 && !streamDone) {
                await new Promise<void>(r => { notifyPlayer = r })
              }
              if (chunkQueue.length === 0) {
                return
              }
              const blob = chunkQueue.shift()!
              let buffer: AudioBuffer
              try {
                buffer = await decodeWav(blob)
              } catch {
                continue
              }
              yield buffer
            }
          })()
          let r = await decodeStream.next()
          while (!r.done) {
            if (stopRequestedRef.current) {
              break
            }
            const buffer = r.value
            const nextDecode = decodeStream.next() // decode next chunk while this one plays
            const t = Math.max(nextTime, ctx.currentTime)
            try {
              const source = ctx.createBufferSource()
              source.buffer = buffer
              source.connect(ctx.destination)
              source.start(t)
              currentAudioElRef.current = null
              currentChunkIdxRef.current += 1
              nextTime = t + buffer.duration
            } catch {
              /* */
            }
            r = await nextDecode
            if (stopRequestedRef.current) {
              break
            }
          }
          if (!stopRequestedRef.current) {
            const waitMs = Math.max(0, (nextTime - ctx.currentTime) * 1000) + 40
            await new Promise<void>(r => { setTimeout(r, waitMs) })
          }
          if (ttsAudioContextRef.current === ctx) {
            ttsAudioContextRef.current = null
          }
          try {
            await ctx.close()
          } catch {
            /* */
          }
        } else {
          // No Web Audio — fall back to chained <audio> (longer gaps between chunks)
          while (true) {
            if (chunkQueue.length === 0) {
              if (streamDone) {
                break
              }
              await new Promise<void>(r => { notifyPlayer = r })
              continue
            }
            if (stopRequestedRef.current) {
              break
            }
            const blob = chunkQueue.shift()!
            const url  = URL.createObjectURL(blob)

            await new Promise<void>(resolve => {
              const audio = new Audio(url)
              audioRef.current = audio

              audio.onloadedmetadata = () => startWordTracker(audio)

              const _watchdog = setTimeout(() => {
                currentAudioElRef.current = null
                currentChunkIdxRef.current++
                URL.revokeObjectURL(url)
                resolve()
              }, 45_000)

              const _done = () => {
                clearTimeout(_watchdog)
                currentAudioElRef.current = null
                currentChunkIdxRef.current++
                URL.revokeObjectURL(url)
                resolve()
              }

              audio.onended = _done
              audio.onerror = _done
              audio.play().catch(_done)
            })
            if (stopRequestedRef.current) {
              break
            }
          }
        }
        // If we exited with an empty queue (0 chunks streamed = backend produced
        // nothing), reset the button so the user can try again.
        if (!stopRequestedRef.current) {
          if (currentChunkIdxRef.current > 0) {
            finishReading()
          } else {
            stopSpeaking()
          }
        }
      }

      await Promise.all([readStream(), playQueue()])
    } catch {
      // Fallback: non-streaming single request
      try {
        const res2 = await fetch("/api/voice/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: clean }),
        })
        if (!res2.ok) { stopSpeaking(); return }
        const blob = await res2.blob()
        const url  = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audioRef.current = audio
        sentenceWordRangesRef.current = [{ start: 0, end: allWordsRef.current.length }]
        currentChunkIdxRef.current = 0
        audio.onloadedmetadata = () => startWordTracker(audio)
        audio.onended = () => { currentAudioElRef.current = null; URL.revokeObjectURL(url); finishReading() }
        audio.onerror = () => { currentAudioElRef.current = null; stopSpeaking(); URL.revokeObjectURL(url) }
        audio.play().catch(() => { currentAudioElRef.current = null; stopSpeaking(); URL.revokeObjectURL(url) })
      } catch {
        stopSpeaking()
      }
    }
  }

  const handleSuggestionClick = (suggestion: string) => {
    const lower = suggestion.toLowerCase()
    const isReadAloud = READ_ALOUD_TRIGGERS.some(trigger => lower.includes(trigger))
    if (isReadAloud) {
      void handleReadAloud()
    } else {
      onSuggestionClick?.(suggestion, message.content)
    }
  }

  if (message.thinking) {
    const thinkingLabel = message.statusText?.trim() || message.content?.trim() || "Working on your request"
    const steps = message.statusSteps || []
    const recentSteps = steps.slice(-6)
    return (
      <div className="flex items-start gap-3 px-4 py-4 max-w-3xl mx-auto w-full">
        <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/40 flex items-center justify-center shrink-0">
          <Bot className="w-4 h-4 text-primary" />
        </div>
        <div className="pt-1.5 text-sm text-muted-foreground min-w-0">
          <div className="flex items-center gap-2">
            <span>{thinkingLabel}</span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-primary animate-bounce [animation-delay:0ms]" />
              <span className="w-2 h-2 rounded-full bg-primary animate-bounce [animation-delay:150ms]" />
              <span className="w-2 h-2 rounded-full bg-primary animate-bounce [animation-delay:300ms]" />
            </span>
          </div>
          {recentSteps.length > 0 && (
            <div className="mt-2 space-y-1">
              {recentSteps.map((step, index) => {
                const isCurrent = index === recentSteps.length - 1
                return (
                  <div key={`${step}-${index}`} className="flex items-start gap-2 text-xs">
                    <span className={cn("mt-1 h-1.5 w-1.5 rounded-full", isCurrent ? "bg-primary" : "bg-primary/45")} />
                    <span className={cn("leading-5", isCurrent ? "text-foreground" : "text-muted-foreground")}>{step}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={cn("group w-full px-4 py-3", isUser ? "flex justify-end" : "")}>
      {isUser ? (
        /* ── User message box ── */
        <div className="flex items-end gap-2 max-w-[75%]">
          <div className="relative rounded-2xl rounded-br-sm border border-border/50 bg-secondary overflow-hidden text-sm leading-relaxed">
            {/* Header: label + copy */}
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/30 bg-muted/30">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 flex items-center gap-1">
                <User className="w-3 h-3" /> You
              </span>
              <button
                onClick={handleCopy}
                title="Copy"
                className="p-1 rounded text-muted-foreground/60 hover:text-foreground hover:bg-muted transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
            {/* Content */}
            <div className="px-4 py-3 space-y-2">
              {message.content && <div>{message.content}</div>}
              {attachments.length > 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {attachments.map((attachment, index) => {
                    const isImage = attachment.type.startsWith("image/")
                    return (
                      <a
                        key={`${attachment.name}-${index}`}
                        href={attachment.url || "#"}
                        target="_blank"
                        rel="noreferrer"
                        className={cn(
                          "flex items-center gap-2 rounded-lg border border-border/60 bg-background/60 px-2.5 py-1.5 text-xs",
                          attachment.url ? "hover:bg-background/80" : "cursor-default opacity-80"
                        )}
                        onClick={(event) => { if (!attachment.url) event.preventDefault() }}
                        title={attachment.name}
                      >
                        {isImage && attachment.url ? (
                          <img src={attachment.url} alt={attachment.name} className="h-8 w-8 rounded object-cover border border-border/50" />
                        ) : (
                          <Paperclip className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                        )}
                        <span className="truncate max-w-[180px]">{attachment.name}</span>
                      </a>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* ── Assistant message box ── */
        <div className="flex items-start gap-3 max-w-3xl mx-auto w-full">
          <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/40 flex items-center justify-center shrink-0 mt-0.5">
            <Bot className="w-4 h-4 text-primary" />
          </div>
          <WebEmbedContext.Provider value={webEmbedApi}>
          <div className="flex-1 min-w-0 rounded-2xl rounded-tl-sm border border-border/50 bg-card/40 overflow-hidden">

            {/* Card header: Nova label + action icons */}
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/30 bg-muted/20">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-primary/70 flex items-center gap-1">
                <Bot className="w-3 h-3" /> Nova
              </span>
              <div className="flex items-center gap-0.5">
                {/* Read aloud */}
                <button
                  onClick={() => void handleReadAloud()}
                  title={isSpeaking ? "Stop reading" : "Read aloud"}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors",
                    isSpeaking
                      ? "text-cyan-400 bg-cyan-500/10 hover:bg-cyan-500/20"
                      : "text-muted-foreground/60 hover:text-cyan-400 hover:bg-cyan-500/10"
                  )}
                >
                  {isSpeaking ? <Square className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
                  <span className="hidden sm:inline">{isSpeaking ? "Stop" : "Read aloud"}</span>
                </button>
                {/* Copy */}
                <button
                  onClick={handleCopy}
                  title="Copy response"
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground/60 hover:text-foreground hover:bg-muted transition-colors"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
                  <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
                </button>
                {/* Thumbs */}
                <button
                  onClick={() => { setLiked(!liked); setDisliked(false) }}
                  className={cn(
                    "p-1.5 rounded-md text-xs transition-colors",
                    liked ? "text-primary bg-primary/10" : "text-muted-foreground/60 hover:text-foreground hover:bg-muted"
                  )}
                >
                  <ThumbsUp className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => { setDisliked(!disliked); setLiked(false) }}
                  className={cn(
                    "p-1.5 rounded-md text-xs transition-colors",
                    disliked ? "text-destructive bg-destructive/10" : "text-muted-foreground/60 hover:text-foreground hover:bg-muted"
                  )}
                >
                  <ThumbsDown className="w-3.5 h-3.5" />
                </button>
                <button className="p-1.5 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-muted transition-colors">
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Intro — conversational preamble (shimmer while LLM formats) */}
            {message.sectionsLoading && !message.sections && (
              <div className="px-4 pt-3 pb-2 border-b border-border/25">
                <div className="h-4 w-2/3 rounded bg-muted-foreground/10 animate-pulse" />
              </div>
            )}
            {sections.intro && (
              <div className="px-4 pt-3 pb-2 border-b border-border/25 space-y-1">
                {sections.intro.split("\n").map((ln, i) => (
                  <p key={i} className="text-sm italic text-muted-foreground leading-relaxed">
                    <RichLine line={ln} />
                  </p>
                ))}
              </div>
            )}

            {/* Card body: main content */}
            <div className="px-4 py-3 text-foreground leading-relaxed font-[ui-sans-serif]">
              {/* Story Mode — interleaved paragraphs + visuals */}
              {message.storySections && message.storySections.length > 0 ? (
                <StoryView sections={message.storySections} />
              ) : (
                parts.map((part, i) => {
                  if (!isSpeaking || activeWordIdx < 0) {
                    return part.type === "code"
                      ? <CodeBlock key={i} code={part.content} language={part.language || "plaintext"} />
                      : <FormattedText key={i} text={part.content} />
                  }

                  const wordOffset = partWordOffsetsRef.current[i] ?? 0
                  const nextOffset = partWordOffsetsRef.current[i + 1] ?? allWordsRef.current.length
                  const isActive = activeWordIdx >= wordOffset && activeWordIdx < nextOffset
                  const isPast   = activeWordIdx >= nextOffset

                  return (
                    <div
                      key={i}
                      className={cn(
                        "transition-all duration-300 rounded",
                        isActive && "bg-cyan-500/10 -mx-1.5 px-1.5 border-l-2 border-cyan-400/50",
                        isPast && "opacity-40"
                      )}
                    >
                      {part.type === "code" ? (
                        <CodeBlock code={part.content} language={part.language || "plaintext"} />
                      ) : isActive ? (
                        <ReadAlongFormattedText
                          text={part.content}
                          activeWordIdx={activeWordIdx}
                          wordOffset={wordOffset}
                        />
                      ) : (
                        <FormattedText text={part.content} />
                      )}
                    </div>
                  )
                })
              )}
            </div>

            {/* Outro — closing remark (shimmer while LLM formats) */}
            {message.sectionsLoading && !message.sections && (
              <div className="px-4 pt-2 pb-3 border-t border-border/25">
                <div className="h-4 w-1/2 rounded bg-muted-foreground/10 animate-pulse" />
              </div>
            )}
            {sections.outro && (
              <div className="px-4 pt-2 pb-3 border-t border-border/25 space-y-1">
                {sections.outro.split("\n").map((ln, i) => (
                  <p key={i} className="text-sm italic text-muted-foreground leading-relaxed">
                    <RichLine line={ln} />
                  </p>
                ))}
              </div>
            )}

            {/* Music player — shown when a beat was requested */}
            {(message.musicGenerating || message.musicUrl || message.musicError) && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                {message.musicGenerating && !message.musicUrl
                  ? <MusicGenerating prompt={message.musicPrompt} />
                  : message.musicUrl
                    ? <MusicPlayer url={message.musicUrl} prompt={message.musicPrompt} />
                    : message.musicError
                      ? (
                        <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-red-950/30 border border-red-500/20 text-red-400 text-xs">
                          <span className="text-base">🎵</span>
                          Music generation failed — MusicGen may still be loading or ran out of memory.
                          Try again or ask Nova for a shorter clip.
                        </div>
                      )
                      : null
                }
              </div>
            )}

            {/* Image preview — single image or multi-image grid */}
            {(message.imageGenerating || message.imageUrl || (message.imageUrls ?? []).length > 0) && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                {(() => {
                  // Filter out undefined slot placeholders — only real loaded URLs
                  const urls = (
                    message.imageUrls ?? (message.imageUrl ? [message.imageUrl] : [])
                  ).filter((u): u is string => !!u)

                  // Still loading (no real URLs yet)
                  if (message.imageGenerating && urls.length === 0) {
                    return <ImageGenerating />
                  }

                  // Multi-image grid (some may still be loading)
                  if (urls.length > 1 || (urls.length >= 1 && message.imageGenerating)) {
                    return (
                      <div className="flex flex-col gap-3">
                        <div className={`grid gap-2 ${urls.length === 2 ? "grid-cols-2" : "grid-cols-2"}`}>
                          {urls.map((url, idx) => (
                            <ImagePreview key={idx} url={url} prompt={message.imagePrompt} />
                          ))}
                        </div>
                        {/* Show loading card for the remaining in-flight images */}
                        {message.imageGenerating && (
                          <ImageGenerating />
                        )}
                      </div>
                    )
                  }

                  // Single image
                  if (urls.length === 1) {
                    return <ImagePreview url={urls[0]} prompt={message.imagePrompt} />
                  }
                  return null
                })()}
              </div>
            )}

            {/* Interactive chart — rendered with recharts */}
            {(message.chartGenerating || message.chartSpec) && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                {message.chartGenerating && !message.chartSpec
                  ? <DiagramGenerating label="Building chart…" />
                  : message.chartSpec
                    ? (
                      <div className="rounded-lg border border-border/30 bg-[#0a0f1a] p-3">
                        <NovaChart spec={message.chartSpec} />
                      </div>
                    )
                    : null
                }
              </div>
            )}

            {/* Mermaid diagram */}
            {message.mermaidCode && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                <MermaidDiagram code={message.mermaidCode} />
              </div>
            )}

            {/* Live weather widget */}
            {message.weatherData && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                <WeatherCard data={message.weatherData} />
              </div>
            )}

            {/* Live clock widget */}
            {message.showClock && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                <LiveClock />
              </div>
            )}

            {/* Web results — images + articles for visual show requests */}
            {message.webResults && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                <WebResultsPanel results={message.webResults} />
              </div>
            )}

            <EmbeddedWebDrawer
              panel={webEmbed}
              onClose={() => setWebEmbed(null)}
              onMinimize={() => setWebEmbed(prev => (prev?.mode === "open" ? { ...prev, mode: "minimized" } : prev))}
              onExpand={() => setWebEmbed(prev => (prev?.mode === "minimized" ? { ...prev, mode: "open" } : prev))}
            />

            {/* Document cards — one per generated document (supports multiple per message) */}
            {(message.docs ?? []).length > 0 && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3 flex flex-col gap-2">
                {(message.docs ?? []).map((doc, idx) => (
                  <div key={idx}>
                    {doc.generating && !doc.url
                      ? <DocumentGenerating format={doc.format} prompt={doc.prompt} />
                      : doc.url && doc.filename
                        ? (
                          <DocumentCard
                            url={doc.url}
                            filename={doc.filename}
                            format={doc.format}
                            sizeBytes={doc.sizeBytes}
                            prompt={doc.prompt}
                          />
                        )
                        : null
                    }
                  </div>
                ))}
              </div>
            )}

            {/* Card footer: suggestions */}
            {(message.suggestionsLoading || suggestions.length > 0) && (
              <div className="px-4 pb-3 border-t border-border/20 pt-3">
                {message.suggestionsLoading && suggestions.length === 0 && (
                  <div className="flex flex-wrap gap-2">
                    {[80, 110, 95].map(w => (
                      <div key={w} className="h-6 rounded-full bg-primary/10 animate-pulse" style={{ width: `${w}px` }} />
                    ))}
                  </div>
                )}
                {suggestions.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {suggestions.map(suggestion => {
                      const isReadTrigger = READ_ALOUD_TRIGGERS.some(t => suggestion.toLowerCase().includes(t))
                      return (
                        <button
                          key={suggestion}
                          type="button"
                          onClick={() => handleSuggestionClick(suggestion)}
                          className={cn(
                            "rounded-full border px-3 py-1 text-xs transition-colors flex items-center gap-1.5",
                            isReadTrigger
                              ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20"
                              : "border-primary/30 bg-primary/10 text-primary hover:bg-primary/15 hover:border-primary/45"
                          )}
                        >
                          {isReadTrigger && <Volume2 className="w-3 h-3" />}
                          {suggestion}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
          </WebEmbedContext.Provider>
        </div>
      )}
    </div>
  )
}
