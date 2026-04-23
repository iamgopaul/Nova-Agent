"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { ChevronDown, ChevronUp, Activity } from "lucide-react"

interface SystemStats {
  cpu_percent: number | null
  ram_used_gb: number | null
  ram_total_gb: number | null
  ram_percent: number | null
  gpu: {
    utilization_percent: number
    memory_used_mb: number
    memory_total_mb: number
    temperature_c: number
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
  const [open, setOpen] = useState(true)
  const intervalRef  = useRef<ReturnType<typeof setInterval>  | null>(null)
  const startDelayRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const readyRef = useRef(false)

  const fetchStats = async () => {
    if (!readyRef.current) return
    try {
      const res = await fetch("/api/stats")
      if (res.ok) {
        setData(await res.json() as StatsPayload)
      }
    } catch {
      // silently ignore — server may not be ready
    }
  }

  useEffect(() => {
    // Wait 4 s after mount before starting — gives webpack time to finish
    // its initial compile so we don't flood the terminal with 500 errors.
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
    // Poll faster while streaming, slower at rest
    const ms = isStreaming ? 800 : 2500
    intervalRef.current = setInterval(() => void fetchStats(), ms)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming])

  const sys  = data?.system
  const req  = data?.last_request
  const perf = data?.perf_profile

  const hasRequest = req && req.status !== "idle" && req.tokens_generated > 0

  return (
    <div className="border-b border-border bg-background/60 backdrop-blur-sm text-xs select-none">
      {/* Toggle bar */}
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-1.5 px-4 py-1 hover:bg-muted/40 transition-colors text-muted-foreground"
      >
        <Activity className="w-3 h-3" />
        <span className="font-medium tracking-wide uppercase text-[10px]">System Stats</span>
        <div className="flex-1" />
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {open && (
        <div className="px-4 pb-2 grid grid-cols-2 gap-x-8 gap-y-2 sm:flex sm:flex-wrap sm:gap-x-6 sm:gap-y-0 sm:items-center sm:pb-2.5">

          {/* ── System ─────────────────────────────────────────────────── */}
          <StatGroup label="CPU">
            <span className={cn("font-mono font-semibold", colorFor(sys?.cpu_percent ?? null))}>
              {pct(sys?.cpu_percent ?? null)}
            </span>
            <BarFill percent={sys?.cpu_percent ?? null} />
          </StatGroup>

          <StatGroup label="RAM">
            <span className={cn("font-mono font-semibold", colorFor(sys?.ram_percent ?? null))}>
              {sys ? `${sys.ram_used_gb?.toFixed(1)} / ${sys.ram_total_gb?.toFixed(0)} GB` : "—"}
            </span>
            <BarFill percent={sys?.ram_percent ?? null} />
          </StatGroup>

          {sys?.gpu && (
            <>
              <StatGroup label="GPU">
                <span className={cn("font-mono font-semibold", colorFor(sys.gpu.utilization_percent))}>
                  {pct(sys.gpu.utilization_percent)}
                </span>
                <BarFill percent={sys.gpu.utilization_percent} />
              </StatGroup>

              <StatGroup label="VRAM">
                <span className="font-mono font-semibold text-foreground">
                  {(sys.gpu.memory_used_mb / 1024).toFixed(1)} / {(sys.gpu.memory_total_mb / 1024).toFixed(0)} GB
                </span>
                <BarFill percent={(sys.gpu.memory_used_mb / sys.gpu.memory_total_mb) * 100} />
              </StatGroup>

              <StatGroup label="Temp">
                <span className={cn(
                  "font-mono font-semibold",
                  sys.gpu.temperature_c >= 85 ? "text-red-400"
                    : sys.gpu.temperature_c >= 70 ? "text-yellow-400"
                    : "text-emerald-400"
                )}>
                  {sys.gpu.temperature_c}°C
                </span>
              </StatGroup>
            </>
          )}

          {/* ── Divider ────────────────────────────────────────────────── */}
          <div className="hidden sm:block w-px h-5 bg-border mx-1" />

          {/* ── Last request ───────────────────────────────────────────── */}
          <StatGroup label="Model">
            <span className="font-mono font-semibold text-primary truncate max-w-[120px]">
              {req?.model ? req.model : "—"}
            </span>
          </StatGroup>

          <StatGroup label="Tokens">
            <span className={cn(
              "font-mono font-semibold",
              isStreaming ? "text-primary animate-pulse" : "text-foreground"
            )}>
              {hasRequest ? req!.tokens_generated.toLocaleString() : "—"}
            </span>
          </StatGroup>

          <StatGroup label="Speed">
            <span className={cn(
              "font-mono font-semibold",
              hasRequest && req!.tokens_per_second >= 10 ? "text-emerald-400"
                : hasRequest && req!.tokens_per_second >= 4 ? "text-yellow-400"
                : "text-foreground"
            )}>
              {hasRequest ? `${req!.tokens_per_second} tok/s` : "—"}
            </span>
          </StatGroup>

          <StatGroup label="Time">
            <span className="font-mono font-semibold text-foreground">
              {hasRequest ? `${req!.elapsed_seconds.toFixed(1)}s` : "—"}
            </span>
          </StatGroup>

          <StatGroup label="Router">
            <span className="font-mono text-muted-foreground">
              {req?.routed_via || "—"}
            </span>
          </StatGroup>

          {/* ── Perf profile ────────────────────────────────────────────── */}
          {perf && (
            <>
              <div className="hidden sm:block w-px h-5 bg-border mx-1" />

              {/* RAM pressure indicator */}
              <StatGroup label="Pressure">
                <span className={cn(
                  "font-mono font-semibold",
                  perf.ram_pressure === "critical" ? "text-red-400 animate-pulse" :
                  perf.ram_pressure === "moderate" ? "text-yellow-400" :
                  "text-emerald-400"
                )}>
                  {perf.ram_pressure === "critical" ? "⚠ Low RAM" :
                   perf.ram_pressure === "moderate" ? "~ Moderate" : "✓ OK"}
                </span>
              </StatGroup>

              {perf.ram_pressure !== "ok" && (
                <StatGroup label="Tier">
                  <span className={cn(
                    "font-mono font-semibold",
                    perf.model_tier === "light" ? "text-red-400" : "text-yellow-400"
                  )}>
                    {perf.model_tier}
                  </span>
                </StatGroup>
              )}

              <StatGroup label="GPU">
                <span className="font-mono font-semibold text-violet-400">
                  {perf.num_gpu >= 999 ? "max" : perf.num_gpu === 0 ? "off" : `${perf.num_gpu}L`}
                </span>
              </StatGroup>
              <StatGroup label="Threads">
                <span className="font-mono font-semibold text-sky-400">{perf.num_thread}</span>
              </StatGroup>
              <StatGroup label="Batch">
                <span className="font-mono font-semibold text-sky-400">{perf.num_batch}</span>
              </StatGroup>
              <StatGroup label="ctx">
                <span className="font-mono text-muted-foreground">{perf.num_ctx}</span>
              </StatGroup>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function StatGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-1.5 py-1">
      <span className="text-muted-foreground w-10 shrink-0">{label}</span>
      <div className="flex items-center gap-1.5">{children}</div>
    </div>
  )
}
