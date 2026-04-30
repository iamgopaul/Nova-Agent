"use client"

import { ChevronDown, Zap, Brain, Code2, Sigma, FlaskConical, Eye, Lightbulb, Star, MessagesSquare } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

type SpeedTier = "instant" | "fast" | "medium" | "slow"

const SPEED_COLOR: Record<SpeedTier, string> = {
  instant: "text-emerald-400",
  fast:    "text-cyan-400",
  medium:  "text-blue-400",
  slow:    "text-amber-400",
}

const SPEED_DOT: Record<SpeedTier, string> = {
  instant: "bg-emerald-400",
  fast:    "bg-cyan-400",
  medium:  "bg-blue-400",
  slow:    "bg-amber-400",
}

const SPEED_LABEL: Record<SpeedTier, string> = {
  instant: "Instant",
  fast:    "Fast",
  medium:  "Balanced",
  slow:    "Deep",
}

const MODELS = [
  { key: "auto",     name: "GAAIA Auto",     description: "Intelligently picks the best model",              badge: "AUTO",   speed: "fast"    as SpeedTier, icon: Zap },
  { key: "spark",    name: "GAAIA Spark",    description: "Ultra-fast · voice queries & instant replies",    badge: "FAST",   speed: "instant" as SpeedTier, icon: Zap },
  { key: "air",      name: "GAAIA Air",      description: "Light & snappy conversational chat",                               speed: "fast"    as SpeedTier, icon: MessagesSquare },
  { key: "core",     name: "GAAIA Core",     description: "Balanced everyday queries with full tool access",                  speed: "fast"    as SpeedTier, icon: Star },
  { key: "pro",      name: "GAAIA Pro",      description: "Most powerful · deep reasoning & web search",     badge: "PRO",   speed: "slow"    as SpeedTier, icon: Brain },
  { key: "code",     name: "GAAIA Code",     description: "Coding specialist · generation & debugging",      badge: "CODE",  speed: "slow"    as SpeedTier, icon: Code2 },
  { key: "quant",    name: "GAAIA Quant",    description: "Maths, calculus & quantitative finance",          badge: "MATH",  speed: "medium"  as SpeedTier, icon: Sigma },
  { key: "reason",   name: "GAAIA Reason",   description: "Proofs, derivations & chain-of-thought",          badge: "THINK", speed: "medium"  as SpeedTier, icon: Brain },
  { key: "vision",   name: "GAAIA Vision",   description: "Image & scene understanding",                     badge: "VISION",speed: "medium"  as SpeedTier, icon: Eye },
  { key: "mind",     name: "GAAIA Mind",     description: "Deep, nuanced conversation",                                       speed: "slow"    as SpeedTier, icon: Brain },
  { key: "creative", name: "GAAIA Creative", description: "Writing, brainstorming & creative style",         badge: "CREATE",speed: "slow"    as SpeedTier, icon: FlaskConical },
  { key: "insight",  name: "GAAIA Insight",  description: "Focused analysis and sharp reasoning",                             speed: "medium"  as SpeedTier, icon: Lightbulb },
  { key: "sage",     name: "GAAIA Sage",     description: "Strong instruction following & structured output", badge: "SMART", speed: "medium"  as SpeedTier, icon: Star },
  { key: "chat",     name: "GAAIA Chat",     description: "Friendly & natural conversational flow",                           speed: "fast"    as SpeedTier, icon: MessagesSquare },
  { key: "logic",    name: "GAAIA Logic",    description: "Concise and precise logical tasks",                                speed: "fast"    as SpeedTier, icon: Brain },
  { key: "mini",     name: "GAAIA Mini",     description: "Smallest & snappiest · ultra-lightweight",                         speed: "instant" as SpeedTier, icon: Zap },
  { key: "star",     name: "GAAIA Star",     description: "Polished, well-rounded general responses",                         speed: "medium"  as SpeedTier, icon: Star },
  { key: "open",     name: "GAAIA Open",     description: "OpenChat baseline · open-ended conversation",                      speed: "medium"  as SpeedTier, icon: MessagesSquare },
]

export type ChatModelKey = (typeof MODELS)[number]["key"]

interface ChatHeaderProps {
  selectedModelKey: ChatModelKey
  onModelChange: (modelKey: ChatModelKey) => void
}

/** Per-model badge color overrides — falls back to blue (GAAIA Chat theme). */
function badgeClass(key: string): string {
  switch (key) {
    case "vision":   return "bg-violet-500/15 text-violet-400 border-violet-500/20"
    case "code":     return "bg-emerald-500/15 text-emerald-400 border-emerald-500/20"
    case "pro":      return "bg-amber-500/15 text-amber-400 border-amber-500/20"
    case "creative": return "bg-pink-500/15 text-pink-400 border-pink-500/20"
    case "sage":     return "bg-cyan-500/15 text-cyan-400 border-cyan-500/20"
    case "quant":    return "bg-sky-500/15 text-sky-400 border-sky-500/20"
    case "reason":   return "bg-violet-500/15 text-violet-400 border-violet-500/20"
    default:         return "bg-blue-500/15 text-blue-400 border-blue-500/20"
  }
}

export function ChatHeader({ selectedModelKey, onModelChange }: ChatHeaderProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const selectedModel = MODELS.find(m => m.key === selectedModelKey) ?? MODELS[0]
  const ModelIcon = selectedModel.icon

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false) }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      {/* Trigger */}
      <button
        onClick={() => setOpen(v => !v)}
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm font-semibold transition-all duration-150",
          "border hover:text-white",
          open
            ? "bg-white/8 border-blue-500/30 text-white"
            : "text-white/75 border-transparent hover:bg-white/6 hover:border-white/8"
        )}
      >
        <ModelIcon className="w-3.5 h-3.5 text-blue-400 shrink-0" />
        <span className="hidden sm:inline">{selectedModel.name}</span>
        {selectedModel.badge && (
          <span className="hidden sm:inline text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-blue-500/15 text-blue-400 border border-blue-500/20">
            {selectedModel.badge}
          </span>
        )}
        <span className={cn("flex items-center gap-1 text-[10px] shrink-0", SPEED_COLOR[selectedModel.speed])}>
          <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", SPEED_DOT[selectedModel.speed])} />
          <span className="hidden sm:inline">{SPEED_LABEL[selectedModel.speed]}</span>
        </span>
        <ChevronDown className={cn("w-3.5 h-3.5 text-white/30 transition-transform duration-200", open && "rotate-180")} />
      </button>

      {/* Dropdown — right-aligned so it never clips off the edge */}
      {open && (
        <div className="absolute top-full right-0 mt-2 w-80 rounded-2xl border border-white/8 shadow-2xl shadow-black/70 z-50 overflow-hidden" style={{ backgroundColor: "var(--surface-2)" }}>
          <div className="px-3 pt-3 pb-1">
            <p className="text-[9px] font-bold uppercase tracking-widest text-white/25 px-1">Select Model</p>
          </div>

          <div className="p-2 max-h-[min(65vh,480px)] overflow-y-auto scrollbar-thin space-y-0.5">
            {MODELS.map(model => {
              const Icon = model.icon
              const isSelected = selectedModel.key === model.key
              return (
                <button
                  key={model.key}
                  onClick={() => { onModelChange(model.key); setOpen(false) }}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all duration-100",
                    isSelected
                      ? "bg-blue-600/20 border border-blue-500/20 text-white"
                      : "hover:bg-white/5 text-white/55 hover:text-white/90 border border-transparent"
                  )}
                >
                  <Icon className={cn("w-4 h-4 shrink-0", isSelected ? "text-blue-400" : "text-white/20")} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-semibold leading-tight">{model.name}</span>
                      {model.badge && (
                        <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded-md border", badgeClass(model.key))}>
                          {model.badge}
                        </span>
                      )}
                      <span className={cn("flex items-center gap-1 text-[9px] font-medium ml-auto", SPEED_COLOR[model.speed])}>
                        <span className={cn("w-1.5 h-1.5 rounded-full", SPEED_DOT[model.speed])} />
                        {SPEED_LABEL[model.speed]}
                      </span>
                    </div>
                    <p className="text-[11px] text-white/30 mt-0.5 leading-snug">{model.description}</p>
                  </div>

                  {isSelected && (
                    <div className="w-2 h-2 rounded-full bg-blue-400 shrink-0" />
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
