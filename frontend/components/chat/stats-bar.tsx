"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { ChevronDown, ChevronUp, Activity } from "lucide-react"

interface SystemStats {
  cpu_percent: number | null
  ram_used_gb: number | null
  ram_total_gb: number | null
  ram_percent: number | null
  committed_used_gb: number | null
  committed_total_gb: number | null
  committed_percent: number | null
  gpu: {
    type?: "nvidia" | "apple_silicon"
    chip?: string
    utilization_percent: number
    memory_used_mb: number
    memory_total_mb: number
    temperature_c: number | null
  } | null
}

interface LastRequest {
  model: string
  tokens_generated: number
  elapsed_seconds: number
  tokens_per_second: number
  routed_via: string
  status: "idle" | "streaming" | "done" | "error"
}

interface PerfProfile {
  description: string
  ram_pressure: "ok" | "moderate" | "critical"
  model_tier: "full" | "mid" | "light"
  num_gpu: number
  num_thread: number
  num_batch: number
  num_ctx: number
  use_mmap: boolean
  mlock: boolean
  keep_alive: string
}

interface StatsPayload {
  system: SystemStats
  last_request: LastRequest
  perf_profile?: PerfProfile
}

function pct(value: number | null): string {
  return value !== null ? `${Math.round(value)}%` : "—"
}

function colorFor(percent: number | null): string {
  if (percent === null) return "text-muted-foreground"
  if (percent >= 85) return "text-red-400"
  if (percent >= 60) return "text-yellow-400"
  return "text-emerald-400"
}

function BarFill({ percent, className }: { percent: number | null; className?: string }) {
  const w = percent !== null ? Math.min(100, Math.max(0, percent)) : 0
  return (
    <div className={cn("h-1 w-12 rounded-full bg-muted overflow-hidden", className)}>
      <div
        className={cn(
          "h-full rounded-full transition-all duration-700",
          percent !== null && percent >= 85
            ? "bg-red-400"
            : percent !== null && percent >= 60
            ? "bg-yellow-400"
            : "bg-emerald-400"
        )}
        style={{ width: `${w}%` }}
      />
    </div>
  )
}

interface StatsBarProps {
  isStreaming: boolean
}

export function StatsBar({ isStreaming }: StatsBarProps) {
  const [data, setData] = useState<StatsPayload | null>(null)
  // Default to collapsed on small screens to save vertical space — phone
  // viewports are tight enough without a 70-px panel of chips taking up
  // the area above every chat. Users can tap the strip to expand.
  const [open, setOpen] = useState(() => {
    if (typeof window === "undefined") return true
    return window.matchMedia("(min-width: 640px)").matches
  })
  const [lastUpdated, setLastUpdated] = useState<number | null>(null)
  const [secAgo, setSecAgo] = useState<number>(0)
  const intervalRef   = useRef<ReturnType<typeof setInterval>  | null>(null)
  const tickRef       = useRef<ReturnType<typeof setInterval>  | null>(null)
  const startDelayRef = useRef<ReturnType<typeof setTimeout>   | null>(null)
  const readyRef = useRef(false)

  const fetchStats = async () => {
    if (!readyRef.current) return
    try {
      const res = await fetch("/api/stats")
      if (res.ok) {
        setData(await res.json() as StatsPayload)
        setLastUpdated(Date.now())
        setSecAgo(0)
      }
    } catch {
      // silently ignore — server may not be ready
    }
  }

  useEffect(() => {
    startDelayRef.current = setTimeout(() => {
      readyRef.current = true
      void fetchStats()
    }, 4000)
    return () => {
      if (startDelayRef.current) clearTimeout(startDelayRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    const ms = isStreaming ? 800 : 2500
    intervalRef.current = setInterval(() => void fetchStats(), ms)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming])

  // Tick the "Xs ago" counter every second
  useEffect(() => {
    if (tickRef.current) clearInterval(tickRef.current)
    tickRef.current = setInterval(() => {
      if (lastUpdated !== null) {
        setSecAgo(Math.floor((Date.now() - lastUpdated) / 1000))
      }
    }, 1000)
    return () => { if (tickRef.current) clearInterval(tickRef.current) }
  }, [lastUpdated])

  const sys = data?.system
  const req = data?.last_request
  const perf = data?.perf_profile

  const hasRequest = req && req.status !== "idle" && req.tokens_generated > 0
  const isAppleSilicon = sys?.gpu?.type === "apple_silicon"

  // Short chip label: "Apple M3 Pro" → "M3 Pro"
  const chipShort = isAppleSilicon
    ? (sys?.gpu?.chip ?? "").replace(/Apple\s+/, "").split(" ").slice(0, 2).join(" ") || "M-series"
    : null

  const ramPressure = perf?.ram_pressure

  return (
    <div className="border-b border-blue-500/15 bg-[#0d0d12]/90 backdrop-blur-sm text-[11px] select-none">

      {/* ── Collapsed toggle strip ──────────────────────────────────────── */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 sm:px-4 h-7 hover:bg-white/[0.03] transition-colors"
      >
        {/* Live dot */}
        <span className={cn(
          "w-1.5 h-1.5 rounded-full shrink-0 transition-colors",
          isStreaming   ? "bg-emerald-400 animate-pulse"
          : lastUpdated ? "bg-emerald-400/50"
          : "bg-white/15"
        )} />

        <span className="text-white/30 font-medium tracking-widest uppercase text-[9px]">
          System
        </span>

        {/* Inline summary when collapsed. On narrow screens we drop the
            request-side chips (model + tok/s) to keep the strip on one line. */}
        {!open && sys && (
          <div className="flex items-center gap-2 sm:gap-3 ml-1 min-w-0 truncate">
            <Chip label="CPU" value={pct(sys.cpu_percent)} color={colorFor(sys.cpu_percent)} />
            <Chip
              label="RAM"
              value={sys.ram_used_gb ? `${sys.ram_used_gb.toFixed(1)} GB` : "—"}
              color={colorFor(sys.ram_percent)}
            />
            {hasRequest && (
              <>
                <Sep />
                <span className="hidden sm:flex items-center gap-3">
                  <Chip label="Model" value={req!.model} color="text-blue-400" />
                  <Chip
                    label=""
                    value={`~${req!.tokens_per_second} t/s`}
                    color={req!.tokens_per_second >= 10 ? "text-emerald-400" : "text-yellow-400"}
                  />
                </span>
                <span className="sm:hidden">
                  <Chip
                    label=""
                    value={`~${req!.tokens_per_second} t/s`}
                    color={req!.tokens_per_second >= 10 ? "text-emerald-400" : "text-yellow-400"}
                  />
                </span>
              </>
            )}
          </div>
        )}

        <div className="flex-1" />

        {lastUpdated !== null && (
          <span className="text-[9px] text-white/20">
            {isStreaming ? "live" : secAgo <= 3 ? "now" : `${secAgo}s`}
          </span>
        )}
        {open
          ? <ChevronUp className="w-3 h-3 text-white/20" />
          : <ChevronDown className="w-3 h-3 text-white/20" />}
      </button>

      {/* ── Expanded panel ──────────────────────────────────────────────── */}
      {open && (
        <div className="px-3 sm:px-4 pb-2.5 pt-1 flex flex-wrap items-center gap-x-3 sm:gap-x-5 gap-y-1.5">

          {/* Hardware group */}
          <Pill label="CPU" value={pct(sys?.cpu_percent ?? null)} color={colorFor(sys?.cpu_percent ?? null)}>
            <MiniBar percent={sys?.cpu_percent ?? null} />
          </Pill>

          {/* Apple Silicon uses a single unified memory pool shared between CPU and GPU.
              Showing a separate "Memory" pill in addition to RAM double-counts the same
              number, so on Apple Silicon we just badge the RAM pill with the chip name. */}
          <Pill
            label={isAppleSilicon && chipShort ? `RAM · ${chipShort}` : "RAM"}
            value={sys ? `${sys.ram_used_gb?.toFixed(1)} / ${sys.ram_total_gb?.toFixed(0)} GB` : "—"}
            color={colorFor(sys?.ram_percent ?? null)}
          >
            <MiniBar percent={sys?.ram_percent ?? null} />
          </Pill>

          {/* Commit charge — RAM + pagefile reservation. On Windows this is the
              "Committed" value Task Manager shows; nearing the limit means the
              system is about to refuse new allocations. */}
          {sys?.committed_used_gb != null && sys?.committed_total_gb != null && (
            <Pill
              label="Total RAM"
              value={`${sys.committed_used_gb.toFixed(1)} / ${sys.committed_total_gb.toFixed(0)} GB`}
              color={colorFor(sys.committed_percent)}
            >
              <MiniBar percent={sys.committed_percent} />
            </Pill>
          )}

          {/* Only show a separate VRAM pill for discrete GPUs (NVIDIA), which have
              their own memory pool distinct from system RAM. */}
          {sys?.gpu && !isAppleSilicon && (
            <Pill
              label="VRAM"
              value={`${(sys.gpu.memory_used_mb / 1024).toFixed(1)} / ${(sys.gpu.memory_total_mb / 1024).toFixed(0)} GB`}
              color={colorFor((sys.gpu.memory_used_mb / sys.gpu.memory_total_mb) * 100)}
            >
              <MiniBar percent={(sys.gpu.memory_used_mb / sys.gpu.memory_total_mb) * 100} />
            </Pill>
          )}

          {sys?.gpu?.temperature_c !== null && sys?.gpu?.temperature_c !== undefined && (
            <Pill
              label="Temp"
              value={`${sys.gpu.temperature_c}°C`}
              color={sys.gpu.temperature_c >= 85 ? "text-red-400" : sys.gpu.temperature_c >= 70 ? "text-yellow-400" : "text-emerald-400"}
            />
          )}

          {/* RAM pressure alert — only shown when not OK */}
          {ramPressure && ramPressure !== "ok" && (
            <span className={cn(
              "text-[10px] font-semibold px-2 py-0.5 rounded-full border",
              ramPressure === "critical"
                ? "text-red-400 border-red-400/30 bg-red-500/10 animate-pulse"
                : "text-yellow-400 border-yellow-400/30 bg-yellow-500/10"
            )}>
              {ramPressure === "critical" ? "⚠ Low RAM" : "~ RAM moderate"}
            </span>
          )}

          {/* Divider */}
          {hasRequest && <div className="w-px h-4 bg-white/[0.08] mx-1" />}

          {/* Last request group */}
          {hasRequest && (
            <>
              <Pill label="Model" value={req!.model} color="text-blue-400" />
              <Pill
                label="Speed"
                value={`~${req!.tokens_per_second} t/s`}
                color={req!.tokens_per_second >= 10 ? "text-emerald-400" : req!.tokens_per_second >= 4 ? "text-yellow-400" : "text-white/60"}
              />
              <Pill
                label="Tokens"
                value={`~${req!.tokens_generated.toLocaleString()}`}
                color={isStreaming ? "text-blue-400 animate-pulse" : "text-white/60"}
              />
              <Pill label="Time" value={`${req!.elapsed_seconds.toFixed(1)}s`} color="text-white/50" />
            </>
          )}

          {!hasRequest && req && (
            <span className="text-white/25 text-[10px]">No recent requests</span>
          )}
        </div>
      )}
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Sep() {
  return <div className="w-px h-3 bg-white/[0.10] shrink-0" />
}

function Chip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span className="flex items-center gap-1">
      {label && <span className="text-white/25">{label}</span>}
      <span className={cn("font-mono font-semibold", color)}>{value}</span>
    </span>
  )
}

function Pill({
  label, value, color, children,
}: {
  label: string
  value: string
  color: string
  children?: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-white/30 shrink-0">{label}</span>
      <span className={cn("font-mono font-semibold", color)}>{value}</span>
      {children}
    </div>
  )
}

function MiniBar({ percent }: { percent: number | null }) {
  const w = percent !== null ? Math.min(100, Math.max(0, percent)) : 0
  return (
    <div className="h-1 w-10 rounded-full bg-white/[0.08] overflow-hidden">
      <div
        className={cn(
          "h-full rounded-full transition-all duration-700",
          percent !== null && percent >= 85 ? "bg-red-400"
            : percent !== null && percent >= 60 ? "bg-yellow-400"
            : "bg-emerald-400/70"
        )}
        style={{ width: `${w}%` }}
      />
    </div>
  )
}
