"use client"

import { useEffect, useRef, useState } from "react"
import { Gavel, Sparkles, Trophy, ChevronRight, Square, Zap } from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"

// ── Types ─────────────────────────────────────────────────────────────────────

interface Contestant {
  id: string
  model: string
  identity: string
  color: string
}

interface ChatMessage {
  contestantId: string
  identity: string
  color: string
  round: number
  text: string
  done: boolean
}

interface EliminationEntry {
  round: number
  eliminated_id: string
  identity: string
  model: string
  reason: string
  score: number
}

interface Report {
  winner_id: string
  winner_identity: string
  winner_model: string
  winner_color: string
  reasoning: string
  best_argument: string
  synthesis: string
  round_scores: Record<string, Record<string, number>>
  elimination_log: EliminationEntry[]
  topic: string
}

type Status = "idle" | "starting" | "running" | "verdict" | "done"

// ── Color palette ─────────────────────────────────────────────────────────────

const PALETTE: Record<string, {
  hex: string; text: string; bg: string; border: string; glow: string; ring: string
}> = {
  blue:   { hex: "#3b82f6", text: "text-blue-400",   bg: "bg-blue-500/[0.09]",   border: "border-blue-500/30",   glow: "shadow-[0_0_50px_oklch(0.65_0.2_220_/_0.5)]",  ring: "oklch(0.65_0.2_220)" },
  violet: { hex: "#8b5cf6", text: "text-violet-400", bg: "bg-violet-500/[0.09]", border: "border-violet-500/30", glow: "shadow-[0_0_50px_oklch(0.55_0.25_275_/_0.5)]", ring: "oklch(0.55_0.25_275)" },
  amber:  { hex: "#f59e0b", text: "text-amber-400",  bg: "bg-amber-500/[0.09]",  border: "border-amber-500/30",  glow: "shadow-[0_0_50px_oklch(0.78_0.18_55_/_0.5)]",   ring: "oklch(0.78_0.18_55)"  },
  rose:   { hex: "#f43f5e", text: "text-rose-400",   bg: "bg-rose-500/[0.09]",   border: "border-rose-500/30",   glow: "shadow-[0_0_50px_oklch(0.65_0.25_15_/_0.5)]",  ring: "oklch(0.65_0.25_15)"  },
}

// Orb positions in the 100×100 SVG viewBox
const ORB_POS: Record<string, { x: number; y: number }> = {
  alpha: { x: 23, y: 27 },
  beta:  { x: 77, y: 27 },
  gamma: { x: 23, y: 73 },
  delta: { x: 77, y: 73 },
}

// ── Battle Arena (SVG) ────────────────────────────────────────────────────────

function BattleArena({
  contestants,
  eliminated,
  activeId,
  thinkingId,
  judging,
  scores,
  currentRound,
}: {
  contestants: Contestant[]
  eliminated: Set<string>
  activeId: string | null
  thinkingId: string | null
  judging: boolean
  scores: Record<string, Record<string, number>>
  currentRound: number
}) {
  const byId: Record<string, Contestant> = {}
  contestants.forEach(c => { byId[c.id] = c })
  const alive = contestants.filter(c => !eliminated.has(c.id))
  const roundScores = scores[String(currentRound)] ?? {}

  return (
    <div className="relative w-full rounded-2xl border border-white/[0.07] overflow-hidden bg-[#05050d]"
      style={{ aspectRatio: "16/10" }}>

      {/* SVG layer */}
      <svg viewBox="0 0 100 100" className="absolute inset-0 w-full h-full" preserveAspectRatio="xMidYMid meet">
        <defs>
          {/* Grid pattern */}
          <pattern id="dg" width="8" height="8" patternUnits="userSpaceOnUse">
            <path d="M8 0L0 0 0 8" fill="none" stroke="rgba(255,255,255,0.025)" strokeWidth="0.3" />
          </pattern>
          {/* Radial vignette */}
          <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
            <stop offset="0%" stopColor="transparent" />
            <stop offset="100%" stopColor="rgba(0,0,0,0.6)" />
          </radialGradient>
        </defs>
        <rect width="100" height="100" fill="url(#dg)" />
        <rect width="100" height="100" fill="url(#vignette)" />

        {/* Centre clash zone */}
        <g>
          <circle cx="50" cy="50" r="6" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="0.5"
            strokeDasharray="3 3">
            {judging && (
              <animateTransform attributeName="transform" type="rotate"
                from="0 50 50" to="360 50 50" dur="2s" repeatCount="indefinite" />
            )}
          </circle>
          {judging && (
            <circle cx="50" cy="50" r="3" fill="rgba(255,200,50,0.12)">
              <animate attributeName="r" values="2;7;2" dur="1.1s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.3;0.08;0.3" dur="1.1s" repeatCount="indefinite" />
            </circle>
          )}
        </g>

        {/* Energy beams from active orb → all alive opponents */}
        {activeId && alive.filter(c => c.id !== activeId).map(target => {
          const from = ORB_POS[activeId] ?? { x: 50, y: 50 }
          const to   = ORB_POS[target.id] ?? { x: 50, y: 50 }
          const hex  = PALETTE[byId[activeId]?.color ?? "blue"]?.hex ?? "#3b82f6"
          return (
            <line key={target.id}
              x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke={hex} strokeWidth="0.9" strokeDasharray="4 3" opacity="0.55"
              style={{ animation: "flowBeam 0.45s linear infinite" }}
            />
          )
        })}

        {/* Cross-beams (static, faint) between all alive pairs */}
        {alive.length >= 2 && alive.map((a, i) =>
          alive.slice(i + 1).map(b => (
            <line key={`${a.id}-${b.id}`}
              x1={ORB_POS[a.id]?.x ?? 50} y1={ORB_POS[a.id]?.y ?? 50}
              x2={ORB_POS[b.id]?.x ?? 50} y2={ORB_POS[b.id]?.y ?? 50}
              stroke="rgba(255,255,255,0.04)" strokeWidth="0.4"
            />
          ))
        )}

        {/* Orbs */}
        {contestants.map(c => {
          const pos     = ORB_POS[c.id] ?? { x: 50, y: 50 }
          const pal     = PALETTE[c.color] ?? PALETTE.blue
          const isElim  = eliminated.has(c.id)
          const isActive   = activeId === c.id
          const isThinking = thinkingId === c.id
          const score   = roundScores[c.id]

          return (
            <g key={c.id} style={{
              filter: isElim ? "grayscale(1) brightness(0.35)" : "none",
              transition: "filter 1.2s ease, opacity 1.2s ease",
              opacity: isElim ? 0.4 : 1,
            }}>
              {/* Outer pulse halo (speaking) */}
              {isActive && !isElim && (
                <circle cx={pos.x} cy={pos.y} r="13" fill="none" stroke={pal.hex} strokeWidth="0.5">
                  <animate attributeName="r"       values="10;18;10" dur="0.9s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.4;0;0.4" dur="0.9s" repeatCount="indefinite" />
                </circle>
              )}
              {/* Mid glow fill */}
              {isActive && !isElim && (
                <circle cx={pos.x} cy={pos.y} r="9" fill={pal.hex} opacity="0.12">
                  <animate attributeName="opacity" values="0.12;0.28;0.12" dur="0.7s" repeatCount="indefinite" />
                </circle>
              )}

              {/* Main orb body */}
              <circle cx={pos.x} cy={pos.y}
                r={isActive ? "8" : "7"}
                fill={isElim ? "#111" : `${pal.hex}22`}
                stroke={isElim ? "#444" : pal.hex}
                strokeWidth={isActive ? "1.8" : "1.2"}
                style={{ transition: "r 0.4s ease" }}>
                {isActive && !isElim && (
                  <animate attributeName="r" values="7;9;7" dur="0.85s" repeatCount="indefinite" />
                )}
              </circle>

              {/* Thinking dots */}
              {isThinking && !isElim && [-2, 0, 2].map((dx, i) => (
                <circle key={i} cx={pos.x + dx} cy={pos.y} r="0.9" fill={pal.hex}>
                  <animate attributeName="opacity" values="0.2;1;0.2" dur="0.6s"
                    begin={`${i * 0.2}s`} repeatCount="indefinite" />
                </circle>
              ))}

              {/* Score badge */}
              {score !== undefined && !isElim && (
                <g>
                  <circle cx={pos.x + 7} cy={pos.y - 7} r="3.5" fill="#0a0a18" stroke={pal.hex} strokeWidth="0.8" />
                  <text x={pos.x + 7} y={pos.y - 6} textAnchor="middle" fontSize="3"
                    fill={pal.hex} fontWeight="bold">{score}</text>
                </g>
              )}

              {/* Eliminated X */}
              {isElim && (
                <>
                  <line x1={pos.x - 3.5} y1={pos.y - 3.5} x2={pos.x + 3.5} y2={pos.y + 3.5}
                    stroke="rgba(255,80,80,0.7)" strokeWidth="1.2" strokeLinecap="round" />
                  <line x1={pos.x + 3.5} y1={pos.y - 3.5} x2={pos.x - 3.5} y2={pos.y + 3.5}
                    stroke="rgba(255,80,80,0.7)" strokeWidth="1.2" strokeLinecap="round" />
                </>
              )}

              {/* Identity label */}
              <text x={pos.x} y={pos.y + 12} textAnchor="middle" fontSize="3.2"
                fill={isElim ? "rgba(255,255,255,0.2)" : pal.hex} fontWeight="700">
                {c.identity.replace("GAAIA ", "")}
              </text>
              <text x={pos.x} y={pos.y + 15.5} textAnchor="middle" fontSize="2"
                fill="rgba(255,255,255,0.18)">
                {c.model.length > 14 ? c.model.slice(0, 13) + "…" : c.model}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Judging overlay pill */}
      {judging && (
        <div className="absolute bottom-3 inset-x-0 flex justify-center pointer-events-none">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-yellow-500/15 border border-yellow-500/30 backdrop-blur-sm">
            <Gavel className="w-3 h-3 text-yellow-400" />
            <span className="text-[10px] font-bold text-yellow-300 uppercase tracking-wider">Judge deliberating</span>
            {[0, 1, 2].map(i => (
              <div key={i} className="w-1 h-1 rounded-full bg-yellow-400 animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Live Chat ─────────────────────────────────────────────────────────────────

function LiveChat({
  messages,
  activeId,
  activeText,
  contestants,
}: {
  messages: ChatMessage[]
  activeId: string | null
  activeText: string
  contestants: Contestant[]
}) {
  const endRef = useRef<HTMLDivElement>(null)
  const byId: Record<string, Contestant> = {}
  contestants.forEach(c => { byId[c.id] = c })

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, activeText])

  return (
    <div className="flex flex-col h-full rounded-2xl border border-white/[0.07] bg-[#05050d] overflow-hidden">
      <div className="px-3.5 py-2.5 border-b border-white/[0.06] flex items-center gap-2 shrink-0"
        style={{ backgroundColor: "rgba(255,255,255,0.02)" }}>
        <Zap className="w-3.5 h-3.5 text-white/30" />
        <span className="text-[11px] font-bold uppercase tracking-wider text-white/30">Live Feed</span>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 scrollbar-thin">
        {messages.length === 0 && !activeId && (
          <p className="text-center text-xs text-white/20 mt-8">Messages will appear here as the battle begins…</p>
        )}

        {messages.filter(msg => msg.done).map((msg, i) => {
          const pal = PALETTE[msg.color] ?? PALETTE.blue
          return (
            <div key={i} className="space-y-1 animate-in fade-in slide-in-from-bottom-1 duration-300">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: pal.hex }} />
                <span className={cn("text-[10px] font-bold", pal.text)}>{msg.identity}</span>
                <span className="text-[9px] text-white/20">R{msg.round}</span>
              </div>
              <div
                className="text-xs text-white/65 leading-relaxed pl-3.5 border-l"
                style={{ borderColor: `${pal.hex}40` }}
              >
                {msg.text}
              </div>
            </div>
          )
        })}

        {/* Actively streaming message */}
        {activeId && activeText && (() => {
          const c   = byId[activeId]
          const pal = PALETTE[c?.color ?? "blue"] ?? PALETTE.blue
          return (
            <div className="space-y-1 animate-in fade-in duration-200">
              <div className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full shrink-0 animate-pulse" style={{ backgroundColor: pal.hex }} />
                <span className={cn("text-[10px] font-bold", pal.text)}>{c?.identity}</span>
                <span className="text-[9px] text-white/20">streaming…</span>
              </div>
              <div className="text-xs text-white/65 leading-relaxed pl-3.5 border-l"
                style={{ borderColor: `${pal.hex}40` }}>
                {activeText}
                <span className="inline-block w-0.5 h-3 ml-0.5 rounded-full align-text-bottom animate-pulse"
                  style={{ backgroundColor: pal.hex }} />
              </div>
            </div>
          )
        })()}

        <div ref={endRef} />
      </div>
    </div>
  )
}

// ── Score Bar ─────────────────────────────────────────────────────────────────

function ScoreBar({
  contestants,
  eliminated,
  scores,
  currentRound,
}: {
  contestants: Contestant[]
  eliminated: Set<string>
  scores: Record<string, Record<string, number>>
  currentRound: number
}) {
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-white/[0.07] bg-white/[0.02]">
      <span className="text-[10px] text-white/25 font-bold uppercase tracking-widest shrink-0">Scores</span>
      <div className="flex flex-wrap gap-2 flex-1">
        {contestants.map(c => {
          const pal     = PALETTE[c.color] ?? PALETTE.blue
          const isElim  = eliminated.has(c.id)
          const roundScore = scores[String(currentRound)]?.[c.id]
          const bestScore  = Object.values(scores).reduce<number | null>((best, rs) => {
            const s = rs[c.id]
            return s !== undefined ? (best === null ? s : Math.max(best, s)) : best
          }, null)

          return (
            <div key={c.id}
              className={cn(
                "flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[10px] transition-all duration-500",
                isElim ? "border-white/10 bg-white/[0.02] opacity-40" : cn(pal.border, pal.bg),
              )}>
              <div className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ backgroundColor: isElim ? "#444" : pal.hex }} />
              <span className={cn("font-semibold", isElim ? "text-white/30" : pal.text)}>
                {c.identity.replace("GAAIA ", "")}
              </span>
              {!isElim && roundScore !== undefined && (
                <span className="font-black text-white/50">{roundScore}</span>
              )}
              {isElim && <span className="text-red-400/60 font-bold">✕</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Final Report ──────────────────────────────────────────────────────────────

function ReportCard({
  report,
  contestants,
}: {
  report: Report
  contestants: Contestant[]
}) {
  const byId: Record<string, Contestant> = {}
  contestants.forEach(c => { byId[c.id] = c })
  const winner = byId[report.winner_id]
  const winPal = PALETTE[winner?.color ?? "blue"] ?? PALETTE.blue
  const rounds = ["1", "2", "3"]

  return (
    <div className="space-y-4 mt-4">
      {/* Winner banner */}
      <div className={cn(
        "relative overflow-hidden rounded-2xl border p-5",
        winPal.border, winPal.bg, winPal.glow,
      )}>
        <div className="pointer-events-none absolute -top-8 -right-8 w-40 h-40 rounded-full blur-3xl opacity-15"
          style={{ backgroundColor: winPal.hex }} />
        <div className="relative z-10 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Trophy className={cn("w-5 h-5", winPal.text)} />
              <span className="text-[10px] font-black uppercase tracking-widest text-white/40">Battle Winner</span>
            </div>
            <h2 className={cn("text-2xl font-black", winPal.text)}>{report.winner_identity}</h2>
            <p className="text-xs font-mono text-white/30 mt-0.5">{report.winner_model}</p>
          </div>
          <div className="shrink-0 w-16 h-16 rounded-2xl border flex items-center justify-center"
            style={{ backgroundColor: `${winPal.hex}20`, borderColor: `${winPal.hex}50` }}>
            <Trophy className={cn("w-8 h-8", winPal.text)} />
          </div>
        </div>
      </div>

      {/* Best argument */}
      {report.best_argument && (
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
          <p className="text-[10px] font-bold uppercase tracking-wider text-white/25 mb-2">Winning Argument</p>
          <p className="text-sm text-white/60 italic leading-relaxed">"{report.best_argument}"</p>
        </div>
      )}

      {/* Two-column: elimination log + score table */}
      <div className="grid grid-cols-2 gap-4">
        {/* Elimination log */}
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-white/25 mb-2">Elimination Log</p>
          <div className="space-y-2">
            {report.elimination_log.map((entry, i) => {
              const c   = byId[entry.eliminated_id]
              const pal = PALETTE[c?.color ?? "blue"] ?? PALETTE.blue
              return (
                <div key={i} className={cn(
                  "flex items-start gap-2.5 rounded-xl border p-2.5 opacity-70",
                  pal.border, pal.bg,
                )}>
                  <span className="text-[9px] font-black text-white/30 shrink-0 mt-0.5">R{entry.round}</span>
                  <div>
                    <p className={cn("text-[11px] font-bold", pal.text)}>
                      {entry.identity} <span className="text-red-400">eliminated</span>
                    </p>
                    <p className="text-[10px] text-white/35 mt-0.5 leading-relaxed">{entry.reason}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Score table */}
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-white/25 mb-2">Round Scores</p>
          <div className="rounded-xl border border-white/[0.08] overflow-hidden">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-white/[0.07]" style={{ backgroundColor: "rgba(255,255,255,0.02)" }}>
                  <th className="text-left px-3 py-2 text-white/25 font-semibold">Model</th>
                  {rounds.map(r => (
                    <th key={r} className="text-center px-2 py-2 text-white/25 font-semibold">R{r}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {contestants.map(c => {
                  const pal    = PALETTE[c.color] ?? PALETTE.blue
                  const isWin  = c.id === report.winner_id
                  return (
                    <tr key={c.id} className="border-b border-white/[0.04] last:border-0">
                      <td className={cn("px-3 py-2 font-semibold", pal.text)}>
                        {c.identity.replace("GAAIA ", "")}
                        {isWin && <span className="ml-1 text-yellow-400">★</span>}
                      </td>
                      {rounds.map(r => {
                        const s = report.round_scores?.[r]?.[c.id]
                        return (
                          <td key={r} className="text-center px-2 py-2 text-white/45">
                            {s ?? <span className="text-white/15">—</span>}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Synthesis */}
      {report.synthesis && (
        <div className="rounded-xl border border-purple-500/20 bg-purple-500/[0.05] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-3.5 h-3.5 text-purple-400" />
            <p className="text-[10px] font-bold uppercase tracking-wider text-purple-400/60">
              Final Synthesis — Best Answer
            </p>
          </div>
          <p className="text-sm text-white/70 leading-relaxed">{report.synthesis}</p>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DebatePage() {
  const [topic, setTopic]           = useState("")
  const [status, setStatus]         = useState<Status>("idle")
  const [startError, setStartError] = useState<string | null>(null)

  // Debate state
  const [contestants, setContestants]       = useState<Contestant[]>([])
  const [eliminated, setEliminated]         = useState<Set<string>>(new Set())
  const [activeId, setActiveId]             = useState<string | null>(null)
  const [activeText, setActiveText]         = useState("")
  const [thinkingId, setThinkingId]         = useState<string | null>(null)
  const [judging, setJudging]               = useState(false)
  const [currentRound, setCurrentRound]     = useState(0)
  const [phaseLabel, setPhaseLabel]         = useState("")
  const [scores, setScores]                 = useState<Record<string, Record<string, number>>>({})
  const [messages, setMessages]             = useState<ChatMessage[]>([])
  const [report, setReport]                 = useState<Report | null>(null)
  const [lastElim, setLastElim]             = useState<{ identity: string; reason: string } | null>(null)

  const abortRef    = useRef<AbortController | null>(null)
  const byIdRef     = useRef<Record<string, Contestant>>({})

  // ── Start ────────────────────────────────────────────────────────────────────

  async function startDebate() {
    if (!topic.trim() || status !== "idle") return
    setStartError(null)
    setStatus("starting")

    try {
      const res = await fetch("/api/debate/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: topic.trim() }),
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
        if (res.status === 404) detail = "Debate API not found — please restart the GAAIA backend."
        if (res.status === 401) detail = "Not signed in — please log in first."
        throw new Error(detail)
      }

      const data = await res.json()
      const cs: Contestant[] = data.contestants

      byIdRef.current = {}
      cs.forEach(c => { byIdRef.current[c.id] = c })

      setContestants(cs)
      setEliminated(new Set())
      setActiveId(null)
      setActiveText("")
      setThinkingId(null)
      setJudging(false)
      setCurrentRound(0)
      setPhaseLabel("")
      setScores({})
      setMessages([])
      setReport(null)
      setLastElim(null)
      setStatus("running")

      runStream(data.debate_id)
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error"
      console.error("[Debate]", msg)
      setStartError(msg)
      setStatus("idle")
    }
  }

  // ── Stream ────────────────────────────────────────────────────────────────────

  function runStream(debateId: string) {
    const ctrl = new AbortController()
    abortRef.current = ctrl

    ;(async () => {
      try {
        const res = await fetch(`/api/debate/${debateId}/stream`, { signal: ctrl.signal })
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
            try { handleEvent(JSON.parse(payload)) } catch { /* skip bad JSON */ }
          }
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name !== "AbortError") console.error("[Debate stream]", e)
      }
    })()
  }

  // ── Event handler ─────────────────────────────────────────────────────────────

  function handleEvent(evt: Record<string, unknown>) {
    const type = evt.type as string

    switch (type) {
      case "init":
        // Already handled in startDebate; contestants already set
        break

      case "round_start":
        setCurrentRound(evt.round as number)
        setPhaseLabel(evt.label as string)
        setJudging(false)
        setLastElim(null)
        break

      case "thinking":
        setThinkingId(evt.contestant_id as string)
        setActiveId(null)
        setActiveText("")
        break

      case "turn_start": {
        const cid      = evt.contestant_id as string
        const identity = evt.identity as string
        const round    = evt.round as number
        const c        = byIdRef.current[cid]
        setActiveId(cid)
        setThinkingId(null)
        setActiveText("")
        setMessages(prev => {
          // Guard against duplicate entries if the event fires more than once
          const alreadyHas = prev.some(m => m.contestantId === cid && m.round === round && !m.done)
          if (alreadyHas) return prev
          return [...prev, {
            contestantId: cid,
            identity,
            color: c?.color ?? "blue",
            round,
            text: "",
            done: false,
          }]
        })
        break
      }

      case "token": {
        const cid = evt.contestant_id as string
        const tok = evt.text as string
        setActiveText(p => p + tok)
        setMessages(prev => {
          const next = [...prev]
          // Update last entry for this contestant
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].contestantId === cid && !next[i].done) {
              next[i] = { ...next[i], text: next[i].text + tok }
              break
            }
          }
          return next
        })
        break
      }

      case "turn_end": {
        const cid = evt.contestant_id as string
        setActiveId(null)
        setActiveText("")
        setMessages(prev => {
          const next = [...prev]
          for (let i = next.length - 1; i >= 0; i--) {
            if (next[i].contestantId === cid && !next[i].done) {
              next[i] = { ...next[i], done: true }
              break
            }
          }
          return next
        })
        break
      }

      case "judging":
        setJudging(true)
        setActiveId(null)
        break

      case "scores":
        setScores(prev => ({ ...prev, [String(evt.round)]: evt.scores as Record<string, number> }))
        break

      case "elimination":
        setEliminated(prev => new Set([...prev, evt.eliminated_id as string]))
        setLastElim({ identity: evt.identity as string, reason: evt.reason as string })
        setJudging(false)
        break

      case "verdict_start":
        setStatus("verdict")
        setJudging(false)
        break

      case "verdict_token":
        // Raw JSON from judge — discarded, not displayed
        break

      case "report":
        setReport(evt as unknown as Report)
        setStatus("done")
        break

      case "done":
        setStatus("done")
        setActiveId(null)
        setThinkingId(null)
        setJudging(false)
        break
    }
  }

  function stopDebate() {
    abortRef.current?.abort()
    setStatus("idle")
    setActiveId(null)
    setThinkingId(null)
    setJudging(false)
  }

  function reset() {
    abortRef.current?.abort()
    setStatus("idle")
    setContestants([])
    setEliminated(new Set())
    setActiveId(null)
    setActiveText("")
    setThinkingId(null)
    setJudging(false)
    setCurrentRound(0)
    setPhaseLabel("")
    setScores({})
    setMessages([])
    setReport(null)
    setLastElim(null)
    setStartError(null)
  }

  const isRunning = status === "running" || status === "verdict"
  const isDone    = status === "done"

  // ── Idle screen ───────────────────────────────────────────────────────────────
  if (status === "idle" || status === "starting") {
    return (
      <AppShell title="Debate" titleColor="text-orange-400">
        <div className="flex h-full flex-col items-center justify-center px-6 py-10 relative overflow-hidden">
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            <div className="absolute -top-20 left-[15%] w-80 h-80 rounded-full bg-blue-500/[0.06] blur-3xl" />
            <div className="absolute top-0 right-[20%] w-72 h-72 rounded-full bg-violet-500/[0.06] blur-3xl" />
            <div className="absolute bottom-0 left-[25%] w-80 h-80 rounded-full bg-amber-500/[0.05] blur-3xl" />
            <div className="absolute -bottom-10 right-[15%] w-72 h-72 rounded-full bg-rose-500/[0.05] blur-3xl" />
          </div>

          <div className="relative z-10 max-w-xl w-full space-y-8">
            {/* Title */}
            <div className="text-center">
              {/* 4 orb preview */}
              <div className="flex items-center justify-center gap-3 mb-5">
                {[
                  { color: "blue",   label: "Spark" },
                  { color: "violet", label: "Air"   },
                  { color: "amber",  label: "Core"  },
                  { color: "rose",   label: "Insight" },
                ].map((o, i) => {
                  const pal = PALETTE[o.color]
                  return (
                    <div key={i} className="flex flex-col items-center gap-1.5">
                      <div className={cn(
                        "w-11 h-11 rounded-full border-2 flex items-center justify-center",
                        pal.border, pal.bg, pal.glow,
                      )} style={{ animation: `orbFloat ${1.8 + i * 0.4}s ease-in-out infinite alternate` }}>
                        <Zap className={cn("w-4 h-4", pal.text)} />
                      </div>
                      <span className={cn("text-[9px] font-bold", pal.text)}>{o.label}</span>
                    </div>
                  )
                })}
              </div>

              <h1 className="text-3xl font-black text-white/90 mb-2">GAAIA Battle Debate</h1>
              <p className="text-sm text-white/40 max-w-sm mx-auto">
                4 AI models enter. 3 brutal rounds. One winner. Watch them collide in real time —
                the last model standing delivers the best answer.
              </p>
            </div>

            {/* Input */}
            <div className="space-y-3">
              <textarea
                className="w-full rounded-2xl border border-white/[0.10] bg-white/[0.04] px-4 py-3.5 text-sm text-white/85 placeholder:text-white/25 focus:outline-none focus:border-orange-500/50 focus:bg-white/[0.06] resize-none transition-all"
                placeholder={'Ask anything — e.g. "Is remote work better than in-office?" or "What programming language should I learn first?"'}
                rows={3}
                value={topic}
                onChange={e => { setTopic(e.target.value); setStartError(null) }}
                onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) startDebate() }}
                disabled={status === "starting"}
              />
              <button
                onClick={startDebate}
                disabled={!topic.trim() || status === "starting"}
                className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl bg-gradient-to-r from-blue-600 via-violet-600 to-rose-600 text-white font-bold text-sm transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-[0_4px_30px_rgba(0,0,0,0.4)]"
              >
                {status === "starting" ? (
                  <><Sparkles className="w-4 h-4 animate-spin" />Selecting models…</>
                ) : (
                  <><Zap className="w-4 h-4" />Start Battle<ChevronRight className="w-4 h-4" /></>
                )}
              </button>
              <p className="text-center text-[11px] text-white/20">⌘↵ to start · 4 models · 3 rounds · 1 winner</p>

              {startError && (
                <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/[0.08] px-3.5 py-2.5">
                  <span className="text-red-400 mt-0.5 shrink-0">⚠</span>
                  <p className="text-xs text-red-300/80 leading-relaxed">{startError}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </AppShell>
    )
  }

  // ── Arena screen ──────────────────────────────────────────────────────────────
  return (
    <AppShell
      title="Debate"
      titleColor="text-orange-400"
      isStreaming={isRunning}
      headerActions={
        isRunning ? (
          <button onClick={stopDebate}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 text-xs font-semibold hover:bg-red-500/20 transition-colors">
            <Square className="w-3 h-3 fill-current" />Stop
          </button>
        ) : (
          <button onClick={reset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/10 bg-white/[0.05] text-white/50 text-xs font-semibold hover:bg-white/[0.08] transition-colors">
            New Battle
          </button>
        )
      }
    >
      <div className="flex flex-col h-full overflow-hidden">

        {/* ── Phase header ───────────────────────────────────────────────────── */}
        <div className="shrink-0 flex items-center justify-between px-5 py-2 border-b border-white/[0.06]"
          style={{ backgroundColor: "var(--surface-2)" }}>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] text-white/25 font-bold shrink-0">Topic:</span>
            <span className="text-xs text-white/65 truncate">{topic}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-3">
            {currentRound > 0 && (
              <span className="text-[10px] font-mono text-white/30">Round {currentRound}/3</span>
            )}
            {phaseLabel && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-orange-500/[0.12] border border-orange-500/25">
                <Gavel className="w-2.5 h-2.5 text-orange-400" />
                <span className="text-[10px] font-bold text-orange-300">{phaseLabel}</span>
              </div>
            )}
            {status === "verdict" && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-purple-500/[0.15] border border-purple-500/30">
                <Sparkles className="w-2.5 h-2.5 text-purple-400 animate-spin" />
                <span className="text-[10px] font-bold text-purple-300">Final Verdict</span>
              </div>
            )}
          </div>
        </div>

        {/* ── Elimination toast ──────────────────────────────────────────────── */}
        {lastElim && (
          <div className="shrink-0 mx-5 mt-2 flex items-center gap-2 px-3 py-2 rounded-xl border border-red-500/25 bg-red-500/[0.07] animate-in fade-in slide-in-from-top-2 duration-300">
            <span className="text-red-400 text-sm">✕</span>
            <span className="text-xs text-red-300/80 font-semibold">{lastElim.identity} eliminated</span>
            <span className="text-xs text-white/30 ml-1">— {lastElim.reason}</span>
          </div>
        )}

        {/* ── Main body ──────────────────────────────────────────────────────── */}
        <div className="flex-1 min-h-0 grid grid-cols-[1fr_320px] gap-4 px-5 py-3 overflow-hidden">

          {/* Left: Arena + scores + report */}
          <div className="flex flex-col gap-3 min-h-0 overflow-y-auto scrollbar-thin pr-1">
            <BattleArena
              contestants={contestants}
              eliminated={eliminated}
              activeId={activeId}
              thinkingId={thinkingId}
              judging={judging}
              scores={scores}
              currentRound={currentRound}
            />

            <ScoreBar
              contestants={contestants}
              eliminated={eliminated}
              scores={scores}
              currentRound={currentRound}
            />

            {/* Judge deliberating spinner (verdict tokens are raw JSON — don't show them) */}
            {status === "verdict" && !report && (
              <div className="rounded-xl border border-purple-500/20 bg-purple-500/[0.04] p-4">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-3 h-3 text-purple-400 animate-spin" />
                  <span className="text-[10px] font-bold uppercase tracking-wider text-purple-400/60">
                    Judge deliberating…
                  </span>
                </div>
              </div>
            )}

            {/* Winner announcement */}
            {report && (() => {
              const byId2: Record<string, Contestant> = {}
              contestants.forEach(c => { byId2[c.id] = c })
              const w   = byId2[report.winner_id]
              const pal = PALETTE[w?.color ?? "blue"] ?? PALETTE.blue
              return (
                <div
                  className={cn(
                    "flex flex-col items-center gap-2 rounded-2xl border py-6 px-5 text-center",
                    "animate-in fade-in slide-in-from-top-3 duration-500",
                    pal.border, pal.bg, pal.glow,
                  )}
                >
                  <span className="text-[10px] font-black uppercase tracking-[0.25em] text-white/35">
                    🏆 The winner is…
                  </span>
                  <h2 className={cn("text-4xl font-black tracking-tight leading-none", pal.text)}>
                    {report.winner_identity}
                  </h2>
                  {report.reasoning && (
                    <p className="text-sm text-white/55 max-w-md leading-relaxed mt-1">
                      {report.reasoning}
                    </p>
                  )}
                </div>
              )
            })()}

            {/* Full report */}
            {report && <ReportCard report={report} contestants={contestants} />}
          </div>

          {/* Right: Live chat */}
          <LiveChat
            messages={messages}
            activeId={activeId}
            activeText={activeText}
            contestants={contestants}
          />
        </div>
      </div>

      {/* Keyframe styles */}
      <style>{`
        @keyframes flowBeam {
          from { stroke-dashoffset: 28; }
          to   { stroke-dashoffset: 0; }
        }
        @keyframes orbFloat {
          from { transform: translateY(0px); }
          to   { transform: translateY(-5px); }
        }
      `}</style>
    </AppShell>
  )
}
