"use client"

import { Scale, MessageCircle, Trophy, Gavel } from "lucide-react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { AppShell } from "@/components/app-shell"

export default function DebatePage() {
  return (
    <AppShell title="Debate">
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 relative overflow-hidden bg-[#0a0a10]">
        {/* Ambient blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-20 left-1/3 w-96 h-96 rounded-full bg-orange-500/8 blur-3xl" />
          <div className="absolute bottom-1/3 right-0 w-80 h-80 rounded-full bg-amber-500/6 blur-3xl" />
        </div>

        <div className="relative z-10 max-w-md w-full text-center space-y-8">
          {/* Debaters illustration */}
          <div className="flex items-center justify-center gap-6">
            <div className="flex flex-col items-center gap-2">
              <div className="w-14 h-14 rounded-2xl border border-blue-500/30 bg-blue-500/12 flex items-center justify-center shadow-[0_0_30px_rgba(59,130,246,0.15)]">
                <MessageCircle className="w-7 h-7 text-blue-400" />
              </div>
              <span className="text-xs text-blue-400/70 font-medium">Proponent</span>
            </div>
            <div className="w-14 h-14 rounded-2xl border border-orange-500/30 bg-orange-500/12 flex items-center justify-center shadow-[0_0_40px_rgba(249,115,22,0.15)]">
              <Scale className="w-7 h-7 text-orange-400" />
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="w-14 h-14 rounded-2xl border border-red-500/30 bg-red-500/12 flex items-center justify-center shadow-[0_0_30px_rgba(239,68,68,0.15)]">
                <MessageCircle className="w-7 h-7 text-red-400 scale-x-[-1]" />
              </div>
              <span className="text-xs text-red-400/70 font-medium">Opposition</span>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-center gap-2 mb-3">
              <NovaIcon size={20} />
              <h1 className="text-3xl font-bold text-white/80">Nova Debate</h1>
            </div>
            <p className="text-white/35 leading-relaxed text-sm">
              Pick a topic and watch two Nova models argue opposing positions. A moderator scores each round, declares a winner, and you can jump in to challenge either side.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 text-left">
            {[
              { icon: Gavel,  label: "AI moderator",     desc: "Keeps the debate on track and scores arguments" },
              { icon: Scale,  label: "Real-time scoring", desc: "Logic, evidence, and persuasion tracked per round" },
              { icon: Trophy, label: "Join the debate",   desc: "Step in and argue your own position live" },
            ].map(item => (
              <div key={item.label} className="flex items-start gap-3 p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]">
                <item.icon className="w-4 h-4 text-orange-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-white/70">{item.label}</p>
                  <p className="text-xs text-white/30 mt-0.5">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-orange-500/30 bg-orange-500/8 text-orange-300/80 text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-orange-400 animate-pulse" />
            Coming soon — in development
          </div>
        </div>
      </div>
    </AppShell>
  )
}
