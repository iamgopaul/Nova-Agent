import { NovaIcon } from "@/components/icons/nova-icon"

const SUGGESTIONS = [
  "Explain quantum entanglement simply",
  "Write a Python web scraper",
  "Summarize the latest AI research trends",
  "Help me draft a professional email",
]

export function ChatWelcome() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-12 gap-8 select-none">
      <div className="flex flex-col items-center gap-5 text-center">
        <div className="relative">
          <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-blue-500/20 via-cyan-500/10 to-transparent blur-2xl scale-150" />
          <div className="relative w-14 h-14 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex items-center justify-center shadow-[0_0_40px_oklch(0.72_0.14_220_/_0.12)]">
            <NovaIcon size={28} />
          </div>
        </div>
        <div className="space-y-1.5">
          <h1 className="text-2xl font-bold text-white/80 tracking-tight">
            How can I help you today?
          </h1>
          <p className="text-sm text-white/25 max-w-xs">
            Ask me anything — I can write, reason, code, and research.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
        {SUGGESTIONS.map(s => (
          <button
            key={s}
            className="text-left px-4 py-3 rounded-xl border border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06] hover:border-blue-500/30 text-xs text-white/40 hover:text-white/70 transition-all duration-150 leading-relaxed"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
