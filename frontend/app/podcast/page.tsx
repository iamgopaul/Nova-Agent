"use client"

import { useEffect, useRef, useState } from "react"
import { Headphones, Mic2, Play, Radio, Square, ChevronRight, Sparkles } from "lucide-react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"

// ── Types ──────────────────────────────────────────────────────────────────────

interface HostInfo {
  model:    string
  identity: string
  color:    "violet" | "purple"
}

interface TurnEntry {
  speaker:  "host_a" | "host_b"
  identity: string
  text:     string
  done:     boolean
}

type Status    = "idle" | "starting" | "running" | "done"
type Segment   = "intro" | "discussion" | "outro"

// ── Palette ────────────────────────────────────────────────────────────────────

const PAL = {
  violet: {
    hex:    "#8b5cf6",
    text:   "text-violet-400",
    bg:     "bg-violet-500/[0.09]",
    border: "border-violet-500/30",
    glow:   "shadow-[0_0_40px_oklch(0.55_0.25_275_/_0.35)]",
    bubble: "bg-violet-500/[0.10] border-violet-500/25",
  },
  purple: {
    hex:    "#a855f7",
    text:   "text-purple-400",
    bg:     "bg-purple-500/[0.09]",
    border: "border-purple-500/30",
    glow:   "shadow-[0_0_40px_oklch(0.55_0.25_300_/_0.35)]",
    bubble: "bg-purple-500/[0.10] border-purple-500/25",
  },
}

// ── Waveform animation ─────────────────────────────────────────────────────────

function Waveform({ active, color }: { active: boolean; color: string }) {
  const bars = [14, 28, 20, 36, 16, 32, 18, 30, 12]
  return (
    <div className="flex items-center gap-[3px]">
      {bars.map((h, i) => (
        <div
          key={i}
          className="w-[3px] rounded-full transition-all duration-300"
          style={{
            height:           active ? `${h}px` : "4px",
            backgroundColor:  color,
            opacity:          active ? 0.8 : 0.25,
            animation:        active ? `waveBar 0.6s ease-in-out infinite alternate` : "none",
            animationDelay:   `${i * 65}ms`,
          }}
        />
      ))}
    </div>
  )
}

// ── Host Avatar ────────────────────────────────────────────────────────────────

function HostAvatar({
  host,
  isActive,
  isThinking,
  side,
}: {
  host:       HostInfo
  isActive:   boolean
  isThinking: boolean
  side:       "left" | "right"
}) {
  const pal  = PAL[host.color]
  const Icon = side === "left" ? Headphones : Mic2

  return (
    <div className={cn(
      "flex flex-col items-center gap-2 transition-all duration-500",
      isActive || isThinking ? "scale-105" : "scale-100",
    )}>
      <div className={cn(
        "relative w-14 h-14 rounded-2xl border-2 flex items-center justify-center transition-all duration-500",
        pal.border, pal.bg,
        (isActive || isThinking) && pal.glow,
      )}>
        <Icon className={cn("w-6 h-6", pal.text)} />
        {isThinking && (
          <div className="absolute -bottom-1 -right-1 flex gap-[3px] px-1.5 py-0.5 rounded-full bg-[#0a0a18] border border-white/10">
            {[0, 1, 2].map(i => (
              <div key={i} className="w-1 h-1 rounded-full animate-bounce"
                style={{ backgroundColor: pal.hex, animationDelay: `${i * 0.15}s` }} />
            ))}
          </div>
        )}
        {isActive && (
          <div
            className="absolute inset-0 rounded-2xl border-2 animate-ping"
            style={{ borderColor: `${pal.hex}60` }}
          />
        )}
      </div>
      <div className="text-center">
        <p className={cn("text-[11px] font-bold", pal.text)}>{host.identity}</p>
        <p className="text-[9px] text-white/25 font-mono truncate max-w-[80px]">{host.model}</p>
      </div>
      <Waveform active={isActive} color={pal.hex} />
    </div>
  )
}

// ── Speech Bubble ──────────────────────────────────────────────────────────────

function SpeechBubble({ entry, isStreaming }: { entry: TurnEntry; isStreaming: boolean }) {
  const isA   = entry.speaker === "host_a"
  const color = isA ? "violet" : "purple"
  const pal   = PAL[color]

  return (
    <div className={cn(
      "flex gap-3 animate-in fade-in slide-in-from-bottom-2 duration-300",
      isA ? "flex-row" : "flex-row-reverse",
    )}>
      {/* Avatar dot */}
      <div className="shrink-0 mt-1">
        <div
          className="w-6 h-6 rounded-full border flex items-center justify-center"
          style={{ backgroundColor: `${pal.hex}18`, borderColor: `${pal.hex}50` }}
        >
          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: pal.hex }} />
        </div>
      </div>

      {/* Bubble */}
      <div className={cn(
        "flex-1 max-w-[82%] rounded-2xl border p-3.5 transition-all duration-300",
        pal.bubble,
        isA ? "rounded-tl-sm" : "rounded-tr-sm",
      )}>
        <p className={cn("text-[10px] font-bold mb-1.5", pal.text)}>{entry.identity}</p>
        <p className="text-sm text-white/75 leading-relaxed">
          {entry.text}
          {isStreaming && (
            <span
              className="inline-block w-0.5 h-3.5 ml-0.5 rounded-full align-text-bottom animate-pulse"
              style={{ backgroundColor: pal.hex }}
            />
          )}
        </p>
      </div>
    </div>
  )
}

// ── Segment Badge ──────────────────────────────────────────────────────────────

function SegmentBadge({ segment, label }: { segment: Segment; label: string }) {
  const colors: Record<Segment, string> = {
    intro:      "bg-violet-500/[0.12] border-violet-500/25 text-violet-300",
    discussion: "bg-purple-500/[0.12] border-purple-500/25 text-purple-300",
    outro:      "bg-indigo-500/[0.12] border-indigo-500/25 text-indigo-300",
  }
  return (
    <div className={cn(
      "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-bold",
      colors[segment],
    )}>
      <Radio className="w-2.5 h-2.5" />
      {label}
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────────

export default function PodcastPage() {
  const [topic,       setTopic]       = useState("")
  const [status,      setStatus]      = useState<Status>("idle")
  const [startError,  setStartError]  = useState<string | null>(null)
  const [hostA,       setHostA]       = useState<HostInfo | null>(null)
  const [hostB,       setHostB]       = useState<HostInfo | null>(null)
  const [turns,       setTurns]       = useState<TurnEntry[]>([])
  const [activeSpeaker, setActiveSpeaker] = useState<"host_a" | "host_b" | null>(null)
  const [thinkingSpeaker, setThinkingSpeaker] = useState<"host_a" | "host_b" | null>(null)
  const [segment,     setSegment]     = useState<Segment | null>(null)
  const [segmentLabel, setSegmentLabel] = useState("")

  const abortRef  = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll transcript
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [turns])

  // ── Start ──────────────────────────────────────────────────────────────────

  async function startPodcast() {
    if (!topic.trim() || status !== "idle") return
    setStartError(null)
    setStatus("starting")

    try {
      const res = await fetch("/api/podcast/start", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ topic: topic.trim() }),
      })

      if (!res.ok) {
        let detail = `Server returned ${res.status}`
        try {
          const body = await res.json()
          if (body?.detail) detail = body.detail
        } catch {
          const text = await res.text().catch(() => "")
          if (text) detail = text.slice(0, 200)
        }
        if (res.status === 401) detail = "Not signed in — please log in first."
        if (res.status === 404) detail = "Podcast API not found — please restart the GAAIA backend."
        throw new Error(detail)
      }

      const data = await res.json()
      setHostA(data.host_a)
      setHostB(data.host_b)
      setTurns([])
      setActiveSpeaker(null)
      setThinkingSpeaker(null)
      setSegment(null)
      setSegmentLabel("")
      setStatus("running")

      runStream(data.podcast_id)
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error"
      console.error("[Podcast]", msg)
      setStartError(msg)
      setStatus("idle")
    }
  }

  // ── Stream ─────────────────────────────────────────────────────────────────

  function runStream(podcastId: string) {
    const ctrl = new AbortController()
    abortRef.current = ctrl

    ;(async () => {
      try {
        const res = await fetch(`/api/podcast/${podcastId}/stream`, { signal: ctrl.signal })
        if (!res.ok || !res.body) throw new Error("Stream unavailable")

        const reader  = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer    = ""

        while (true) {
          const { value, done } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split("\n")
          buffer = lines.pop() || ""

          for (const line of lines) {
            if (!line.startsWith("data:")) continue
            const payload = line.slice(5).trim()
            if (!payload) continue
            try { handleEvent(JSON.parse(payload)) } catch { /* skip */ }
          }
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name !== "AbortError") console.error("[Podcast stream]", e)
      }
    })()
  }

  // ── Event handler ──────────────────────────────────────────────────────────

  function handleEvent(evt: Record<string, unknown>) {
    switch (evt.type as string) {
      case "init":
        setHostA(evt.host_a as HostInfo)
        setHostB(evt.host_b as HostInfo)
        break

      case "segment_start":
        setSegment(evt.segment as Segment)
        setSegmentLabel(evt.label as string)
        break

      case "thinking":
        setThinkingSpeaker(evt.speaker as "host_a" | "host_b")
        setActiveSpeaker(null)
        break

      case "turn_start": {
        const speaker  = evt.speaker  as "host_a" | "host_b"
        const identity = evt.identity as string
        setActiveSpeaker(speaker)
        setThinkingSpeaker(null)
        setTurns(prev => [...prev, { speaker, identity, text: "", done: false }])
        break
      }

      case "token": {
        const speaker = evt.speaker as "host_a" | "host_b"
        const tok     = evt.text    as string
        setTurns(prev => {
          const next = [...prev]
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].speaker === speaker && !next[i].done) {
              next[i] = { ...next[i], text: next[i].text + tok }
              break
            }
          }
          return next
        })
        break
      }

      case "turn_end":
        setActiveSpeaker(null)
        setTurns(prev => {
          const next = [...prev]
          for (let i = next.length - 1; i >= 0; i--) {
            if (!next[i].done) { next[i] = { ...next[i], done: true }; break }
          }
          return next
        })
        break

      case "done":
        setStatus("done")
        setActiveSpeaker(null)
        setThinkingSpeaker(null)
        break
    }
  }

  function stop() {
    abortRef.current?.abort()
    setStatus("idle")
    setActiveSpeaker(null)
    setThinkingSpeaker(null)
  }

  function reset() {
    abortRef.current?.abort()
    setStatus("idle")
    setHostA(null)
    setHostB(null)
    setTurns([])
    setActiveSpeaker(null)
    setThinkingSpeaker(null)
    setSegment(null)
    setSegmentLabel("")
    setStartError(null)
  }

  const isRunning = status === "running"

  // ── Idle screen ────────────────────────────────────────────────────────────

  if (status === "idle" || status === "starting") {
    return (
      <AppShell title="Podcast" titleColor="text-violet-400">
        <div className="flex h-full flex-col items-center justify-center px-6 py-10 relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 page-gradient-podcast" />
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            <div className="absolute -top-20 left-1/4 w-96 h-96 rounded-full bg-violet-500/[0.07] blur-3xl" />
            <div className="absolute bottom-1/4 right-0 w-80 h-80 rounded-full bg-purple-500/[0.06] blur-3xl" />
          </div>

          <div className="relative z-10 max-w-lg w-full space-y-8">
            {/* Host illustration */}
            <div className="flex items-center justify-center gap-6">
              <div className="flex flex-col items-center gap-2">
                <div className={cn(
                  "w-16 h-16 rounded-2xl border-2 flex items-center justify-center",
                  PAL.violet.border, PAL.violet.bg, PAL.violet.glow,
                )}>
                  <Headphones className="w-7 h-7 text-violet-400" />
                </div>
                <span className="text-[10px] font-bold text-violet-400/60 uppercase tracking-wider">GAAIA Cast</span>
              </div>

              {/* Static waveform divider */}
              <div className="flex items-center gap-1">
                {[16, 26, 14, 34, 12, 30, 16].map((h, i) => (
                  <div key={i} className="w-1.5 rounded-full bg-violet-400/30 animate-pulse"
                    style={{ height: `${h}px`, animationDelay: `${i * 120}ms` }} />
                ))}
              </div>

              <div className="flex flex-col items-center gap-2">
                <div className={cn(
                  "w-16 h-16 rounded-2xl border-2 flex items-center justify-center",
                  PAL.purple.border, PAL.purple.bg, PAL.purple.glow,
                )}>
                  <Mic2 className="w-7 h-7 text-purple-400" />
                </div>
                <span className="text-[10px] font-bold text-purple-400/60 uppercase tracking-wider">GAAIA Deep</span>
              </div>
            </div>

            {/* Title */}
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-2">
                <GaaiaIcon size={20} />
                <h1 className="text-3xl font-bold text-white/85">GAAIA Podcast</h1>
              </div>
              <p className="text-sm text-white/40 leading-relaxed max-w-sm mx-auto">
                Enter any topic and two GAAIA AI hosts will improvise a full podcast episode — live, streaming, with distinct voices and perspectives.
              </p>
            </div>

            {/* Input */}
            <div className="space-y-3">
              <textarea
                className="w-full rounded-2xl border border-white/[0.10] bg-white/[0.04] px-4 py-3.5 text-sm text-white/85 placeholder:text-white/25 focus:outline-none focus:border-violet-500/50 focus:bg-white/[0.06] resize-none transition-all"
                placeholder={'e.g. "The future of human memory", "Why music gives us chills", "Should we terraform Mars?"'}
                rows={3}
                value={topic}
                onChange={e => { setTopic(e.target.value); setStartError(null) }}
                onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) startPodcast() }}
                disabled={status === "starting"}
              />

              <button
                onClick={startPodcast}
                disabled={!topic.trim() || status === "starting"}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-gradient-to-r from-violet-600 to-purple-600 text-white font-bold text-sm transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-[0_4px_30px_rgba(0,0,0,0.4)]"
              >
                {status === "starting" ? (
                  <><Sparkles className="w-4 h-4 animate-spin" />Setting up hosts…</>
                ) : (
                  <><Play className="w-4 h-4 fill-current" />Start Episode<ChevronRight className="w-4 h-4" /></>
                )}
              </button>

              <p className="text-center text-[11px] text-white/20">⌘↵ to start · 2 hosts · 8 turns · ~5 min episode</p>

              {startError && (
                <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/[0.08] px-3.5 py-2.5">
                  <span className="text-red-400 mt-0.5 shrink-0">⚠</span>
                  <p className="text-xs text-red-300/80 leading-relaxed">{startError}</p>
                </div>
              )}
            </div>

            {/* Feature pills */}
            <div className="grid grid-cols-1 gap-2 text-left">
              {[
                { icon: Radio,      label: "Dual-host format",      desc: "GAAIA Cast & GAAIA Deep — distinct personalities" },
                { icon: Play,       label: "Any topic on demand",   desc: "Science, culture, philosophy, pop culture" },
                { icon: Headphones, label: "Live transcript",        desc: "Watch the conversation build turn by turn" },
              ].map(item => (
                <div key={item.label} className="flex items-start gap-3 p-3 rounded-xl border border-violet-500/15 bg-violet-500/[0.04]">
                  <div className="w-7 h-7 rounded-lg bg-violet-500/15 border border-violet-500/20 flex items-center justify-center shrink-0 mt-0.5">
                    <item.icon className="w-3.5 h-3.5 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-white/70">{item.label}</p>
                    <p className="text-xs text-white/30 mt-0.5">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </AppShell>
    )
  }

  // ── Running / Done screen ──────────────────────────────────────────────────

  return (
    <AppShell
      title="Podcast"
      titleColor="text-violet-400"
      isStreaming={isRunning}
      headerActions={
        isRunning ? (
          <button onClick={stop}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 text-xs font-semibold hover:bg-red-500/20 transition-colors">
            <Square className="w-3 h-3 fill-current" />Stop
          </button>
        ) : (
          <button onClick={reset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/[0.05] text-white/50 text-xs font-semibold hover:bg-white/[0.08] transition-colors">
            New Episode
          </button>
        )
      }
    >
      <div className="flex flex-col h-full overflow-hidden">

        {/* ── Episode header bar ─────────────────────────────────────────────── */}
        <div
          className="shrink-0 flex items-center justify-between px-5 py-2 border-b border-white/[0.06]"
          style={{ backgroundColor: "var(--surface-2)" }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] text-white/25 font-bold shrink-0">Topic:</span>
            <span className="text-xs text-white/65 truncate">{topic}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-3">
            {status === "done" && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-green-500/[0.12] border border-green-500/25">
                <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
                <span className="text-[10px] font-bold text-green-300">Episode complete</span>
              </div>
            )}
            {segment && isRunning && (
              <SegmentBadge segment={segment} label={segmentLabel} />
            )}
          </div>
        </div>

        {/* ── Body: hosts + transcript ───────────────────────────────────────── */}
        <div className="flex-1 min-h-0 flex gap-4 px-5 py-4 overflow-hidden">

          {/* Left: Host A avatar */}
          {hostA && (
            <div className="shrink-0 flex flex-col items-center pt-2">
              <HostAvatar
                host={hostA}
                isActive={activeSpeaker === "host_a"}
                isThinking={thinkingSpeaker === "host_a"}
                side="left"
              />
            </div>
          )}

          {/* Centre: transcript */}
          <div className="flex-1 min-w-0 flex flex-col rounded-2xl border border-white/[0.07] bg-[#05050d] overflow-hidden">
            {/* Transcript header */}
            <div
              className="px-4 py-2.5 border-b border-white/[0.06] flex items-center gap-2 shrink-0"
              style={{ backgroundColor: "rgba(255,255,255,0.02)" }}
            >
              <Radio className="w-3.5 h-3.5 text-white/25" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-white/25">Live Transcript</span>
              {isRunning && (
                <div className="ml-auto flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
                  <span className="text-[10px] text-violet-400/70 font-semibold">On Air</span>
                </div>
              )}
            </div>

            {/* Bubbles */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scrollbar-thin">
              {turns.length === 0 && (
                <p className="text-center text-xs text-white/20 mt-10">
                  The hosts are warming up…
                </p>
              )}

              {turns.map((entry, i) => (
                <SpeechBubble
                  key={i}
                  entry={entry}
                  isStreaming={i === turns.length - 1 && !entry.done && isRunning}
                />
              ))}

              <div ref={bottomRef} />
            </div>
          </div>

          {/* Right: Host B avatar */}
          {hostB && (
            <div className="shrink-0 flex flex-col items-center pt-2">
              <HostAvatar
                host={hostB}
                isActive={activeSpeaker === "host_b"}
                isThinking={thinkingSpeaker === "host_b"}
                side="right"
              />
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes waveBar {
          from { transform: scaleY(0.4); }
          to   { transform: scaleY(1.0); }
        }
      `}</style>
    </AppShell>
  )
}
