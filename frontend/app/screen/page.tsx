"use client"

import { useRef, useState } from "react"
import { Monitor, Clipboard, Send, RefreshCw, ChevronDown, ChevronUp } from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"

type Mode = "idle" | "capturing" | "streaming" | "done" | "error"

export default function ScreenPage() {
  const [mode, setMode] = useState<Mode>("idle")
  const [activeAction, setActiveAction] = useState<"screen" | "clipboard" | null>(null)
  const [question, setQuestion] = useState("")
  const [showQuestion, setShowQuestion] = useState(false)
  const [output, setOutput] = useState("")
  const [statusMsg, setStatusMsg] = useState("")
  const outputRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  function scrollToBottom() {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }

  async function runAction(action: "screen" | "clipboard") {
    if (mode === "streaming" || mode === "capturing") return

    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setActiveAction(action)
    setOutput("")
    setMode("capturing")
    setStatusMsg(action === "screen" ? "Taking screenshot…" : "Reading clipboard…")

    try {
      const endpoint = action === "screen" ? "/api/screen/capture" : "/api/screen/clipboard"
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: ctrl.signal,
      })

      if (!resp.ok || !resp.body) {
        setMode("error")
        setStatusMsg("Request failed — is GAAIA running?")
        return
      }

      setMode("streaming")
      setStatusMsg("GAAIA is analysing…")

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
            if (evt.type === "token") {
              setOutput(prev => {
                const next = prev + evt.text
                setTimeout(scrollToBottom, 0)
                return next
              })
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
    setActiveAction(null)
  }

  const isRunning = mode === "capturing" || mode === "streaming"

  return (
    <AppShell title="Screen" titleColor="text-sky-400" isStreaming={mode === "streaming"}>
      <div className="flex h-full flex-col overflow-hidden">
        {/* ── Ambient blobs ── */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-20 right-1/4 w-96 h-96 rounded-full bg-sky-500/[0.06] blur-3xl" />
          <div className="absolute bottom-0 left-0 w-80 h-80 rounded-full bg-cyan-500/[0.05] blur-3xl" />
        </div>

        <div className="relative z-10 flex flex-col h-full px-6 py-5 gap-4">

          {/* ── Action cards ── */}
          <div className="grid grid-cols-2 gap-3 shrink-0">
            {/* Screen card */}
            <button
              onClick={() => runAction("screen")}
              disabled={isRunning}
              className={cn(
                "group flex flex-col items-start gap-3 p-4 rounded-2xl border text-left transition-all",
                "bg-sky-500/[0.06] border-sky-500/20 hover:border-sky-400/45 hover:bg-sky-500/[0.10]",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                activeAction === "screen" && mode === "streaming" && "border-sky-400/60 bg-sky-500/[0.12] shadow-[0_0_24px_oklch(0.72_0.18_215_/_0.15)]",
              )}
            >
              <div className="w-10 h-10 rounded-xl bg-sky-500/15 border border-sky-500/25 flex items-center justify-center">
                {isRunning && activeAction === "screen"
                  ? <RefreshCw className="w-5 h-5 text-sky-400 animate-spin" />
                  : <Monitor className="w-5 h-5 text-sky-400" />
                }
              </div>
              <div>
                <p className="text-sm font-semibold text-white/80">Analyze My Screen</p>
                <p className="text-xs text-white/35 mt-0.5 leading-relaxed">Take a screenshot and ask GAAIA what's on it</p>
              </div>
            </button>

            {/* Clipboard card */}
            <button
              onClick={() => runAction("clipboard")}
              disabled={isRunning}
              className={cn(
                "group flex flex-col items-start gap-3 p-4 rounded-2xl border text-left transition-all",
                "bg-teal-500/[0.06] border-teal-500/20 hover:border-teal-400/45 hover:bg-teal-500/[0.10]",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                activeAction === "clipboard" && mode === "streaming" && "border-teal-400/60 bg-teal-500/[0.12] shadow-[0_0_24px_oklch(0.75_0.14_175_/_0.15)]",
              )}
            >
              <div className="w-10 h-10 rounded-xl bg-teal-500/15 border border-teal-500/25 flex items-center justify-center">
                {isRunning && activeAction === "clipboard"
                  ? <RefreshCw className="w-5 h-5 text-teal-400 animate-spin" />
                  : <Clipboard className="w-5 h-5 text-teal-400" />
                }
              </div>
              <div>
                <p className="text-sm font-semibold text-white/80">Explain Clipboard</p>
                <p className="text-xs text-white/35 mt-0.5 leading-relaxed">Read whatever you've copied and have GAAIA explain it</p>
              </div>
            </button>
          </div>

          {/* ── Optional question ── */}
          <div className="shrink-0">
            <button
              onClick={() => setShowQuestion(v => !v)}
              className="flex items-center gap-1.5 text-xs text-white/35 hover:text-white/60 transition-colors"
            >
              {showQuestion ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              Add a specific question (optional)
            </button>
            {showQuestion && (
              <div className="mt-2 flex gap-2">
                <input
                  value={question}
                  onChange={e => setQuestion(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && activeAction) runAction(activeAction) }}
                  placeholder="e.g. What error is shown? Summarise this code."
                  className="flex-1 bg-white/[0.04] border border-white/[0.08] rounded-xl px-3.5 py-2 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:border-sky-500/40"
                />
                {activeAction && (
                  <button
                    onClick={() => runAction(activeAction)}
                    disabled={isRunning}
                    className="px-3 py-2 rounded-xl bg-sky-500/15 border border-sky-500/25 text-sky-400 hover:bg-sky-500/25 transition-colors disabled:opacity-40"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                )}
              </div>
            )}
          </div>

          {/* ── Status / output ── */}
          {(output || statusMsg) && (
            <div className="flex-1 min-h-0 flex flex-col gap-2">
              {statusMsg && mode !== "done" && (
                <div className="flex items-center gap-2 text-xs text-white/40 shrink-0">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
                  {statusMsg}
                </div>
              )}

              <div
                ref={outputRef}
                className="flex-1 min-h-0 overflow-y-auto rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4"
              >
                <pre className="text-sm text-white/75 whitespace-pre-wrap leading-relaxed font-sans">
                  {output}
                  {mode === "streaming" && <span className="text-sky-400 animate-pulse">▍</span>}
                </pre>
              </div>

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
              <div className="text-center space-y-2">
                <div className="flex items-center justify-center gap-3 opacity-20">
                  <Monitor className="w-8 h-8 text-sky-400" />
                  <Clipboard className="w-8 h-8 text-teal-400" />
                </div>
                <p className="text-sm text-white/25">Click an action above to get started</p>
              </div>
            </div>
          )}

        </div>
      </div>
    </AppShell>
  )
}
