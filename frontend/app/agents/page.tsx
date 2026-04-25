"use client"

import { useCallback, useRef, useState } from "react"
import {
  AlertCircle,
  BarChart3,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Code2,
  FileText,
  Loader2,
  Network,
  Search,
  Send,
  X,
} from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { cn } from "@/lib/utils"

// ── Types ─────────────────────────────────────────────────────────────────────

interface PlanAgent {
  id: string
  task: string
  depends_on: string[]
}

type AgentStatus = "idle" | "running" | "done" | "error"

interface AgentState {
  status: AgentStatus
  task: string
  output: string
  statusMsg: string
  agentName: string
}

// ── Agent metadata ─────────────────────────────────────────────────────────────

const AGENT_META: Record<string, { name: string; Icon: React.FC<{ className?: string }>; color: string; desc: string }> = {
  research: { name: "GAAIA Research", Icon: Search,   color: "sky",     desc: "Web search & synthesis" },
  code:     { name: "GAAIA Code",     Icon: Code2,    color: "violet",  desc: "Code & architecture" },
  analyst:  { name: "GAAIA Analyst",  Icon: BarChart3, color: "amber",  desc: "Data analysis & insights" },
  writer:   { name: "GAAIA Writer",   Icon: FileText,  color: "emerald", desc: "Documents & reports" },
}

const COLOR: Record<string, { border: string; activeBorder: string; bg: string; iconBg: string; iconText: string; cursor: string }> = {
  sky:     { border: "border-sky-500/20",     activeBorder: "border-sky-500/50",     bg: "bg-sky-500/[0.05]",     iconBg: "bg-sky-500/20 border-sky-500/30",     iconText: "text-sky-400",    cursor: "text-sky-400" },
  violet:  { border: "border-violet-500/20",  activeBorder: "border-violet-500/50",  bg: "bg-violet-500/[0.05]",  iconBg: "bg-violet-500/20 border-violet-500/30", iconText: "text-violet-400", cursor: "text-violet-400" },
  amber:   { border: "border-amber-500/20",   activeBorder: "border-amber-500/50",   bg: "bg-amber-500/[0.05]",   iconBg: "bg-amber-500/20 border-amber-500/30",   iconText: "text-amber-400",  cursor: "text-amber-400" },
  emerald: { border: "border-emerald-500/20", activeBorder: "border-emerald-500/50", bg: "bg-emerald-500/[0.05]", iconBg: "bg-emerald-500/20 border-emerald-500/30",iconText: "text-emerald-400",cursor: "text-emerald-400" },
}

// ── Agent Card ────────────────────────────────────────────────────────────────

function AgentCard({
  agentId,
  state,
  expanded,
  onToggle,
}: {
  agentId: string
  state: AgentState
  expanded: boolean
  onToggle: () => void
}) {
  const meta = AGENT_META[agentId]
  if (!meta) return null
  const c = COLOR[meta.color] ?? COLOR.sky
  const { Icon } = meta

  const borderClass =
    state.status === "running" ? c.activeBorder
    : state.status === "done"  ? c.border
    : state.status === "error" ? "border-red-500/30"
    : "border-white/[0.07]"

  return (
    <div
      className={cn(
        "rounded-xl border overflow-hidden transition-all duration-300",
        borderClass,
        state.status === "idle" ? "opacity-40" : "opacity-100",
      )}
    >
      <button
        onClick={onToggle}
        className={cn(
          "w-full flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.03]",
          state.status !== "idle" ? c.bg : "bg-transparent",
        )}
      >
        <div className={cn("w-7 h-7 rounded-lg border flex items-center justify-center shrink-0", c.iconBg)}>
          <Icon className={cn("w-3.5 h-3.5", c.iconText)} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white/75">{state.agentName || meta.name}</span>
            {state.status === "running" && <Loader2 className={cn("w-3 h-3 animate-spin", c.iconText)} />}
            {state.status === "done"    && <CheckCircle2 className={cn("w-3 h-3", c.iconText)} />}
            {state.status === "error"   && <AlertCircle className="w-3 h-3 text-red-400" />}
          </div>
          <p className="text-xs text-white/30 truncate">
            {state.statusMsg || state.task || meta.desc}
          </p>
        </div>

        {state.output && (
          expanded
            ? <ChevronUp   className="w-3.5 h-3.5 text-white/25 shrink-0" />
            : <ChevronDown className="w-3.5 h-3.5 text-white/25 shrink-0" />
        )}
      </button>

      {expanded && state.output && (
        <div className="px-4 py-3 border-t border-white/[0.05] text-sm text-white/60 whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">
          {state.output}
          {state.status === "running" && (
            <span className={cn("animate-pulse", c.cursor)}>▋</span>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AgentsPage() {
  const [request, setRequest] = useState("")
  const [running, setRunning] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [goal, setGoal] = useState("")
  const [plan, setPlan] = useState<PlanAgent[]>([])
  const [agents, setAgents] = useState<Record<string, AgentState>>({})
  const [synthesis, setSynthesis] = useState("")
  const [synthesizing, setSynthesizing] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState("")
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const readerRef = useRef<ReadableStreamDefaultReader | null>(null)

  const reset = () => {
    setPlanning(false)
    setGoal("")
    setPlan([])
    setAgents({})
    setSynthesis("")
    setSynthesizing(false)
    setDone(false)
    setError("")
    setExpanded({})
  }

  const updateAgent = useCallback((id: string, patch: Partial<AgentState>) => {
    setAgents(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }))
  }, [])

  const handleEvent = useCallback((event: Record<string, unknown>) => {
    switch (event.type) {
      case "planning":
        setPlanning(true)
        break
      case "plan": {
        setPlanning(false)
        setGoal(event.goal as string)
        const planAgents = event.agents as PlanAgent[]
        setPlan(planAgents)
        const initStates: Record<string, AgentState> = {}
        const initExpanded: Record<string, boolean> = {}
        for (const a of planAgents) {
          const meta = AGENT_META[a.id]
          initStates[a.id] = {
            status: "idle",
            task: a.task,
            output: "",
            statusMsg: "",
            agentName: meta?.name ?? a.id,
          }
          initExpanded[a.id] = true
        }
        setAgents(initStates)
        setExpanded(initExpanded)
        break
      }
      case "agent_start":
        updateAgent(event.agent_id as string, {
          status: "running",
          agentName: event.agent_name as string,
          statusMsg: "Starting…",
        })
        break
      case "agent_status":
        updateAgent(event.agent_id as string, { statusMsg: event.status as string })
        break
      case "token":
        setAgents(prev => {
          const id = event.agent_id as string
          return {
            ...prev,
            [id]: { ...prev[id], output: (prev[id]?.output ?? "") + (event.text as string) },
          }
        })
        break
      case "agent_done":
        updateAgent(event.agent_id as string, { status: "done", statusMsg: "" })
        break
      case "agent_error":
        updateAgent(event.agent_id as string, { status: "error", statusMsg: event.error as string })
        break
      case "synthesizing":
        setSynthesizing(true)
        break
      case "synthesis_token":
        setSynthesis(prev => prev + (event.text as string))
        break
      case "done":
        setSynthesizing(false)
        setDone(true)
        break
      case "error":
        setError(event.message as string)
        break
    }
  }, [updateAgent])

  const handleRun = async () => {
    if (!request.trim() || running) return
    reset()
    setRunning(true)

    try {
      const res = await fetch("/api/agents/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: request.trim() }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || "Failed to start agent run")
      }
      const { run_id } = await res.json()

      const streamRes = await fetch(`/api/agents/${run_id}/stream`)
      if (!streamRes.body) throw new Error("No stream body")

      const reader = streamRes.body.getReader()
      readerRef.current = reader
      const decoder = new TextDecoder()
      let buffer = ""

      while (true) {
        const { done: streamDone, value } = await reader.read()
        if (streamDone) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            handleEvent(JSON.parse(line.slice(6)))
          } catch { /* ignore malformed SSE */ }
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong")
    } finally {
      setRunning(false)
    }
  }

  const handleStop = () => {
    readerRef.current?.cancel()
    setRunning(false)
  }

  const hasStarted = plan.length > 0 || planning

  return (
    <AppShell title="Agents" titleColor="text-emerald-400">
      <div className="flex h-full flex-col px-4 py-4 gap-4 overflow-y-auto relative">
        {/* Background */}
        <div className="pointer-events-none absolute inset-0 page-gradient-agents" />
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute top-1/4 right-0 w-96 h-96 rounded-full bg-emerald-500/[0.07] blur-3xl" />
          <div className="absolute bottom-0 left-1/4 w-80 h-80 rounded-full bg-green-500/[0.05] blur-3xl" />
        </div>

        <div className="relative z-10 max-w-3xl w-full mx-auto flex flex-col gap-4">

          {/* Header */}
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl border border-emerald-500/35 bg-emerald-500/15 flex items-center justify-center">
              <Network className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <GaaiaIcon size={16} />
                <h1 className="text-lg font-bold text-white/85">GAAIA Agents</h1>
              </div>
              <p className="text-xs text-white/30">Manager coordinates Research · Code · Analyst · Writer</p>
            </div>
          </div>

          {/* Input */}
          <div className="flex gap-2 items-end">
            <textarea
              value={request}
              onChange={e => setRequest(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun() }}
              placeholder="What should the agents work on? e.g. 'Research the latest AI trends and write a market report'"
              rows={3}
              className="flex-1 bg-white/[0.04] border border-white/10 rounded-xl px-4 py-3 text-sm text-white/80 placeholder:text-white/20 resize-none outline-none focus:border-emerald-500/40 focus:bg-white/[0.06] transition-all"
              disabled={running}
            />
            <div className="flex flex-col gap-2 shrink-0">
              <button
                onClick={handleRun}
                disabled={!request.trim() || running}
                className="px-4 py-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-2 text-sm font-semibold"
              >
                {running
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Send className="w-4 h-4" />
                }
                {running ? "Running…" : "Run"}
              </button>
              {running && (
                <button
                  onClick={handleStop}
                  className="px-4 py-2 rounded-xl border border-white/10 bg-white/[0.04] text-white/40 hover:text-white/60 hover:border-white/20 transition-all flex items-center gap-2 text-sm"
                >
                  <X className="w-3.5 h-3.5" />
                  Stop
                </button>
              )}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl border border-red-500/30 bg-red-500/10 text-red-300 text-sm">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {error}
            </div>
          )}

          {/* Planning indicator */}
          {planning && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06]">
              <Loader2 className="w-4 h-4 text-emerald-400 animate-spin shrink-0" />
              <div>
                <p className="text-sm font-semibold text-white/70">GAAIA Manager is planning…</p>
                <p className="text-xs text-white/30">Deciding which agents to deploy and what tasks to assign</p>
              </div>
            </div>
          )}

          {/* Plan banner */}
          {goal && (
            <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06]">
              <Brain className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-emerald-400 mb-0.5">Manager's Plan</p>
                <p className="text-sm text-white/65">{goal}</p>
              </div>
            </div>
          )}

          {/* Agent cards */}
          {plan.length > 0 && (
            <div className="flex flex-col gap-2.5">
              {plan.map(pa => {
                const state = agents[pa.id]
                if (!state) return null
                return (
                  <AgentCard
                    key={pa.id}
                    agentId={pa.id}
                    state={state}
                    expanded={expanded[pa.id] ?? true}
                    onToggle={() => setExpanded(prev => ({ ...prev, [pa.id]: !prev[pa.id] }))}
                  />
                )
              })}
            </div>
          )}

          {/* Synthesis */}
          {(synthesizing || synthesis) && (
            <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/[0.05] overflow-hidden">
              <div className="flex items-center gap-2.5 px-4 py-3 border-b border-emerald-500/10">
                <div className="w-6 h-6 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center">
                  <Brain className="w-3.5 h-3.5 text-emerald-400" />
                </div>
                <div className="flex-1">
                  <span className="text-sm font-semibold text-white/75">GAAIA Manager</span>
                  <span className="text-xs text-white/30 ml-2">Final synthesis</span>
                </div>
                {synthesizing && !done && <Loader2 className="w-3.5 h-3.5 text-emerald-400 animate-spin" />}
                {done && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
              </div>
              <div className="px-4 py-4 text-sm text-white/70 whitespace-pre-wrap leading-relaxed">
                {synthesis}
                {synthesizing && !done && (
                  <span className="animate-pulse text-emerald-400">▋</span>
                )}
              </div>
            </div>
          )}

          {/* Empty state */}
          {!hasStarted && !running && !error && (
            <div className="flex flex-col items-center justify-center py-16 gap-6 text-center">
              {/* Animated node diagram */}
              <div className="relative w-36 h-36">
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="w-12 h-12 rounded-2xl border border-emerald-500/35 bg-emerald-500/15 flex items-center justify-center shadow-[0_0_40px_oklch(0.80_0.14_160_/_0.15)]">
                    <Network className="w-6 h-6 text-emerald-400" />
                  </div>
                </div>
                {[
                  { deg: 0,   Icon: Search,   color: "text-sky-400/70",     bg: "bg-sky-500/10 border-sky-500/25" },
                  { deg: 90,  Icon: Code2,    color: "text-violet-400/70",  bg: "bg-violet-500/10 border-violet-500/25" },
                  { deg: 180, Icon: BarChart3, color: "text-amber-400/70",  bg: "bg-amber-500/10 border-amber-500/25" },
                  { deg: 270, Icon: FileText, color: "text-emerald-400/70", bg: "bg-emerald-500/10 border-emerald-500/25" },
                ].map(({ deg, Icon, color, bg }, i) => {
                  const rad = (deg * Math.PI) / 180
                  const x = 50 + 42 * Math.cos(rad)
                  const y = 50 + 42 * Math.sin(rad)
                  return (
                    <div
                      key={i}
                      className={cn("absolute w-8 h-8 rounded-full border flex items-center justify-center", bg)}
                      style={{
                        left: `${x}%`,
                        top: `${y}%`,
                        transform: "translate(-50%,-50%)",
                        animation: `gaaia-pulse-ring ${1.5 + i * 0.3}s ease-in-out infinite`,
                      }}
                    >
                      <Icon className={cn("w-3.5 h-3.5", color)} />
                    </div>
                  )
                })}
              </div>

              <div>
                <div className="flex items-center justify-center gap-2 mb-2">
                  <GaaiaIcon size={18} />
                  <h2 className="text-xl font-bold text-white/75">GAAIA Agents</h2>
                </div>
                <p className="text-sm text-white/30 max-w-xs">
                  Enter a request above. GAAIA Manager will deploy Research, Code, Analyst, and Writer agents to get it done.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
