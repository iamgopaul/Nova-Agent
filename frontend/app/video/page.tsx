"use client"

import { useRef, useState } from "react"
import { Film, Play, RefreshCw, ChevronDown, ChevronUp, SlidersHorizontal } from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"

type Mode = "idle" | "running" | "streaming" | "done" | "error"

const FOCUS_OPTIONS = [
  { value: "all",     label: "Full Analysis",    desc: "Scenes, text, objects, and summary" },
  { value: "general", label: "Scene Overview",   desc: "What's happening in each frame" },
  { value: "text",    label: "Extract Text",     desc: "Captions, subtitles, on-screen labels" },
  { value: "objects", label: "Detect Objects",   desc: "People, logos, entities" },
]

const FRAME_OPTIONS = [3, 5, 10, 15, 20]

export default function VideoPage() {
  const [mode, setMode] = useState<Mode>("idle")
  const [url, setUrl] = useState("")
  const [focus, setFocus] = useState("all")
  const [frameCount, setFrameCount] = useState(5)
  const [question, setQuestion] = useState("")
  const [showOptions, setShowOptions] = useState(false)
  const [output, setOutput] = useState("")
  const [statusMsg, setStatusMsg] = useState("")
  const outputRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  function scrollToBottom() {
    outputRef.current?.scrollIntoView?.({ behavior: "smooth" })
    if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight
  }

  async function analyze() {
    if (!url.trim() || mode === "running" || mode === "streaming") return

    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setOutput("")
    setMode("running")
    setStatusMsg("Fetching video…")

    try {
      const resp = await fetch("/api/video/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_source: url.trim(), frame_count: frameCount, focus, question }),
        signal: ctrl.signal,
      })

      if (!resp.ok || !resp.body) {
        setMode("error")
        setStatusMsg("Request failed — is GAAIA running?")
        return
      }

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ""

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === "status") {
              setStatusMsg(evt.text)
              if (evt.text.startsWith("Analys")) setMode("streaming")
            } else if (evt.type === "token") {
              setMode("streaming")
              setStatusMsg("")
              setOutput(prev => {
                const next = prev + evt.text
                setTimeout(scrollToBottom, 0)
                return next
              })
            } else if (evt.type === "error") {
              setMode("error")
              setStatusMsg(evt.text)
            } else if (evt.type === "done") {
              setMode("done")
              setStatusMsg("")
            }
          } catch {}
        }
      }
      setMode("done")
      setStatusMsg("")
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        setMode("error")
        setStatusMsg("Something went wrong.")
      }
    }
  }

  function reset() {
    abortRef.current?.abort()
    setMode("idle")
    setOutput("")
    setStatusMsg("")
  }

  const isRunning = mode === "running" || mode === "streaming"
  const selectedFocus = FOCUS_OPTIONS.find(f => f.value === focus)

  return (
    <AppShell title="Video" titleColor="text-purple-400" isStreaming={mode === "streaming"}>
      <div className="flex h-full flex-col overflow-hidden">

        {/* Ambient blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-20 left-1/4 w-96 h-96 rounded-full bg-purple-500/6 blur-3xl" />
          <div className="absolute bottom-0 right-0 w-80 h-80 rounded-full bg-violet-500/5 blur-3xl" />
        </div>

        <div className="relative z-10 flex flex-col h-full px-4 sm:px-6 py-4 sm:py-5 gap-4">

          {/* ── URL input ── */}
          <div className="shrink-0 space-y-3">
            <div className="flex gap-2">
              <div className="flex-1 flex items-center gap-3 bg-white/4 border border-white/8 rounded-2xl px-4 py-3 focus-within:border-purple-500/40 transition-colors">
                <Film className="w-4 h-4 text-white/25 shrink-0" />
                <input
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") analyze() }}
                  placeholder="YouTube URL, video link, or local file path…"
                  className="flex-1 bg-transparent text-sm text-white/80 placeholder:text-white/20 focus:outline-none"
                  disabled={isRunning}
                />
              </div>
              <button
                onClick={analyze}
                disabled={!url.trim() || isRunning}
                className={cn(
                  "px-5 py-3 rounded-2xl font-semibold text-sm transition-all",
                  "bg-purple-500/20 border border-purple-500/30 text-purple-300",
                  "hover:bg-purple-500/30 hover:border-purple-400/50",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                )}
              >
                {isRunning
                  ? <RefreshCw className="w-4 h-4 animate-spin" />
                  : <Play className="w-4 h-4" />
                }
              </button>
            </div>

            {/* Options toggle */}
            <button
              onClick={() => setShowOptions(v => !v)}
              className="flex items-center gap-1.5 text-xs text-white/35 hover:text-white/60 transition-colors"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              {showOptions ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              Options — {selectedFocus?.label}, {frameCount} frames
            </button>

            {showOptions && (
              <div className="space-y-3 p-4 rounded-2xl border border-white/6 bg-white/2">
                {/* Focus */}
                <div>
                  <p className="text-xs text-white/40 mb-2 font-medium">Analysis focus</p>
                  <div className="grid grid-cols-2 gap-1.5">
                    {FOCUS_OPTIONS.map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => setFocus(opt.value)}
                        className={cn(
                          "flex flex-col items-start px-3 py-2 rounded-xl border text-left transition-all text-xs",
                          focus === opt.value
                            ? "bg-purple-500/15 border-purple-500/35 text-purple-300"
                            : "bg-white/3 border-white/6 text-white/50 hover:border-white/20",
                        )}
                      >
                        <span className="font-semibold">{opt.label}</span>
                        <span className="text-[10px] opacity-60 mt-0.5">{opt.desc}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Frame count */}
                <div>
                  <p className="text-xs text-white/40 mb-2 font-medium">Frames to extract</p>
                  <div className="flex gap-1.5">
                    {FRAME_OPTIONS.map(n => (
                      <button
                        key={n}
                        onClick={() => setFrameCount(n)}
                        className={cn(
                          "px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all",
                          frameCount === n
                            ? "bg-purple-500/15 border-purple-500/35 text-purple-300"
                            : "bg-white/3 border-white/6 text-white/40 hover:border-white/20",
                        )}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Custom question */}
                <div>
                  <p className="text-xs text-white/40 mb-2 font-medium">Custom question (optional)</p>
                  <input
                    value={question}
                    onChange={e => setQuestion(e.target.value)}
                    placeholder="e.g. What product is being reviewed?"
                    className="w-full bg-white/4 border border-white/8 rounded-xl px-3.5 py-2 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:border-purple-500/40"
                  />
                </div>
              </div>
            )}
          </div>

          {/* ── Status / output ── */}
          {(statusMsg || output) && (
            <div className="flex-1 min-h-0 flex flex-col gap-2">
              {statusMsg && (
                <div className="flex items-center gap-2 text-xs text-white/40 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                  {statusMsg}
                </div>
              )}

              {output && (
                <div
                  ref={outputRef}
                  className="flex-1 min-h-0 overflow-y-auto rounded-2xl border border-white/7 bg-white/2 p-4"
                >
                  <pre className="text-sm text-white/75 whitespace-pre-wrap leading-relaxed font-sans">
                    {output}
                    {mode === "streaming" && <span className="text-purple-400 animate-pulse">▍</span>}
                  </pre>
                </div>
              )}

              {mode === "done" && (
                <button
                  onClick={reset}
                  className="shrink-0 self-end text-xs text-white/30 hover:text-white/60 transition-colors px-2 py-1"
                >
                  Clear
                </button>
              )}
            </div>
          )}

          {/* ── Empty state ── */}
          {!output && !statusMsg && mode === "idle" && (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center space-y-3 max-w-xs">
                <div className="w-16 h-16 mx-auto rounded-2xl border border-purple-500/25 bg-purple-500/10 flex items-center justify-center">
                  <Film className="w-8 h-8 text-purple-400/60" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white/40">Paste a video URL above</p>
                  <p className="text-xs text-white/20 mt-1">YouTube, direct links, or a local file path. GAAIA extracts frames and analyses them locally.</p>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </AppShell>
  )
}
