"use client"

import { ChevronDown, Mic } from "lucide-react"
import { useState } from "react"
import { cn } from "@/lib/utils"

type SpeedTier = "instant" | "fast" | "medium" | "slow"

const SPEED_LABEL: Record<SpeedTier, string> = {
  instant: "Instant",
  fast:    "Fast",
  medium:  "Medium",
  slow:    "Slow",
}

const SPEED_COLOR: Record<SpeedTier, string> = {
  instant: "text-emerald-400",
  fast:    "text-green-400",
  medium:  "text-yellow-400",
  slow:    "text-orange-400",
}

const SPEED_DOT: Record<SpeedTier, string> = {
  instant: "bg-emerald-400",
  fast:    "bg-green-400",
  medium:  "bg-yellow-400",
  slow:    "bg-orange-400",
}

const MODELS = [
  // ── Core ─────────────────────────────────────────────────────────────────
  { key: "auto",     name: "Nova Auto",     description: "Intelligently picks the best model for every query",   badge: "AUTO",   speed: "fast"    as SpeedTier },
  { key: "spark",    name: "Nova Spark",    description: "Ultra-fast · voice queries & instant one-liners",      badge: "FAST",   speed: "instant" as SpeedTier },
  { key: "air",      name: "Nova Air",      description: "Light & snappy conversational chat",                                    speed: "fast"    as SpeedTier },
  { key: "core",     name: "Nova Core",     description: "Balanced everyday queries with full tool access",                       speed: "fast"    as SpeedTier },
  { key: "pro",      name: "Nova Pro",      description: "Most powerful · deep reasoning, research & web search", badge: "PRO",   speed: "slow"    as SpeedTier },
  // ── Specialists ──────────────────────────────────────────────────────────
  { key: "code",     name: "Nova Code",     description: "Coding specialist · generation, debugging & review",          badge: "CODE",   speed: "slow"    as SpeedTier },
  { key: "quant",   name: "Nova Quant",    description: "Maths, calculus, statistics & quantitative finance",         badge: "MATH",   speed: "medium"  as SpeedTier },
  { key: "reason",  name: "Nova Reason",   description: "Proofs, derivations & chain-of-thought problem solving",    badge: "THINK",  speed: "medium"  as SpeedTier },
  { key: "vision",   name: "Nova Vision",   description: "Image & scene understanding · visual questions",            badge: "VISION", speed: "medium"  as SpeedTier },
  { key: "mind",     name: "Nova Mind",     description: "Deep, nuanced conversation · no tool overhead",                                speed: "slow"    as SpeedTier },
  { key: "creative", name: "Nova Creative", description: "Writing, brainstorming & creative style",                   badge: "CREATE", speed: "slow"    as SpeedTier },
  { key: "insight",  name: "Nova Insight",  description: "Focused analysis and sharp reasoning",                                        speed: "medium"  as SpeedTier },
  { key: "sage",     name: "Nova Sage",     description: "Strong instruction following & structured output",          badge: "SMART",  speed: "medium"  as SpeedTier },
  // ── Lightweight ──────────────────────────────────────────────────────────
  { key: "chat",     name: "Nova Chat",     description: "Friendly & natural conversational flow",                                speed: "fast"    as SpeedTier },
  { key: "logic",    name: "Nova Logic",    description: "Concise and precise logical tasks",                                     speed: "fast"    as SpeedTier },
  { key: "mini",     name: "Nova Mini",     description: "Smallest & snappiest · ultra-lightweight",                              speed: "instant" as SpeedTier },
  { key: "star",     name: "Nova Star",     description: "Polished, well-rounded general responses",                              speed: "medium"  as SpeedTier },
  { key: "open",     name: "Nova Open",     description: "OpenChat baseline · open-ended conversation",                           speed: "medium"  as SpeedTier },
]

export type ChatModelKey = (typeof MODELS)[number]["key"]

interface ChatHeaderProps {
  selectedModelKey: ChatModelKey
  onModelChange: (modelKey: ChatModelKey) => void
  onVoiceMode?: () => void
}

export function ChatHeader({ selectedModelKey, onModelChange, onVoiceMode }: ChatHeaderProps) {
  const [showModelPicker, setShowModelPicker] = useState(false)
  const selectedModel = MODELS.find(model => model.key === selectedModelKey) ?? MODELS[0]

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-border bg-background/80 backdrop-blur-sm sticky top-0 z-10">
      {/* Model selector */}
      <div className="relative">
        <button
          onClick={() => setShowModelPicker(!showModelPicker)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors border border-transparent hover:border-border"
        >
          <span>{selectedModel.name}</span>
          <ChevronDown className={cn("w-3.5 h-3.5 text-muted-foreground transition-transform duration-200", showModelPicker && "rotate-180")} />
        </button>

        {showModelPicker && (
          <>
            <div
              className="fixed inset-0 z-20"
              onClick={() => setShowModelPicker(false)}
            />
            <div className="absolute top-full left-0 mt-2 w-72 rounded-xl border border-border bg-popover shadow-2xl z-30 overflow-hidden">
              <div className="p-2 space-y-1 max-h-[60vh] overflow-y-auto">
                {MODELS.map(model => (
                  <button
                    key={model.key}
                    onClick={() => { onModelChange(model.key); setShowModelPicker(false) }}
                    className={cn(
                      "w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-left transition-colors",
                      selectedModel.key === model.key
                        ? "bg-primary/10 text-foreground"
                        : "hover:bg-muted text-foreground"
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium">{model.name}</span>
                        {model.badge && (
                          <span className={cn(
                            "text-[10px] font-bold px-1.5 py-0.5 rounded-md border",
                            model.key === "vision"
                              ? "bg-violet-500/20 text-violet-400 border-violet-500/30"
                              : model.key === "code"
                              ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                              : model.key === "pro"
                              ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
                              : model.key === "creative"
                              ? "bg-pink-500/20 text-pink-400 border-pink-500/30"
                              : model.key === "sage"
                              ? "bg-cyan-500/20 text-cyan-400 border-cyan-500/30"
                              : model.key === "quant"
                              ? "bg-blue-500/20 text-blue-400 border-blue-500/30"
                              : model.key === "reason"
                              ? "bg-indigo-500/20 text-indigo-400 border-indigo-500/30"
                              : "bg-primary/20 text-primary border-primary/30"
                          )}>
                            {model.badge}
                          </span>
                        )}
                        {model.speed && (
                          <span className={cn("flex items-center gap-1 text-[10px] font-medium", SPEED_COLOR[model.speed])}>
                            <span className={cn("w-1.5 h-1.5 rounded-full", SPEED_DOT[model.speed])} />
                            {SPEED_LABEL[model.speed]}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-0.5 leading-snug">{model.description}</p>
                    </div>
                    {selectedModel.key === model.key && (
                      <div className="w-2 h-2 rounded-full bg-primary shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1">
        {onVoiceMode && (
          <button 
            onClick={onVoiceMode}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium bg-gradient-to-r from-blue-500/20 to-cyan-500/20 text-primary hover:from-blue-500/30 hover:to-cyan-500/30 border border-primary/30 transition-all"
            title="Voice conversation"
          >
            <Mic className="w-4 h-4" />
            <span className="hidden sm:inline">Voice</span>
          </button>
        )}
      </div>
    </header>
  )
}
