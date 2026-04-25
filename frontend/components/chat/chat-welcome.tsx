import { Code2, FileText, Globe, Lightbulb, Pen, Sigma } from "lucide-react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"

const SUGGESTIONS = [
  { icon: Lightbulb, label: "Explain quantum entanglement simply",       color: "text-amber-400",   bg: "hover:bg-amber-500/[0.07] hover:border-amber-500/25" },
  { icon: Code2,     label: "Write a Python web scraper",                color: "text-emerald-400", bg: "hover:bg-emerald-500/[0.07] hover:border-emerald-500/25" },
  { icon: Globe,     label: "Summarize the latest AI research trends",   color: "text-blue-400",    bg: "hover:bg-blue-500/[0.07] hover:border-blue-500/25" },
  { icon: Pen,       label: "Help me draft a professional email",        color: "text-violet-400",  bg: "hover:bg-violet-500/[0.07] hover:border-violet-500/25" },
  { icon: Sigma,     label: "Solve a calculus problem step by step",     color: "text-cyan-400",    bg: "hover:bg-cyan-500/[0.07] hover:border-cyan-500/25" },
  { icon: FileText,  label: "Summarize this document for me",            color: "text-rose-400",    bg: "hover:bg-rose-500/[0.07] hover:border-rose-500/25" },
]

interface ChatWelcomeProps {
  onSuggestionClick?: (text: string) => void
}

export function ChatWelcome({ onSuggestionClick }: ChatWelcomeProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-12 gap-8 select-none">
      <div className="flex flex-col items-center gap-5 text-center">
        <div className="relative">
          <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-blue-500/20 via-cyan-500/10 to-transparent blur-2xl scale-150" />
          <div className="relative w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center shadow-[0_0_40px_oklch(0.72_0.14_220_/_0.12)]">
            <GaaiaIcon size={28} />
          </div>
        </div>
        <div className="space-y-1.5">
          <h1 className="text-2xl font-bold text-white/85 tracking-tight">
            How can I help you today?
          </h1>
          <p className="text-sm text-white/30 max-w-xs leading-relaxed">
            Ask me anything — I can write, reason, code, search, and create.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
        {SUGGESTIONS.map(s => {
          const Icon = s.icon
          return (
            <button
              key={s.label}
              onClick={() => onSuggestionClick?.(s.label)}
              className={`flex items-start gap-3 text-left px-4 py-3 rounded-xl border border-white/[0.07] bg-white/[0.03] ${s.bg} text-xs text-white/45 hover:text-white/75 transition-all duration-150 leading-relaxed group`}
            >
              <Icon className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${s.color} opacity-60 group-hover:opacity-90 transition-opacity`} />
              <span>{s.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
