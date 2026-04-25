"use client"

import { Headphones, Play, Mic2, Radio } from "lucide-react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { AppShell } from "@/components/app-shell"

export default function PodcastPage() {
  return (
    <AppShell title="Podcast">
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 relative overflow-hidden bg-[#0a0a10]">
        {/* Ambient blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute top-0 left-1/4 w-96 h-96 rounded-full bg-violet-500/8 blur-3xl" />
          <div className="absolute bottom-1/4 right-0 w-80 h-80 rounded-full bg-purple-500/8 blur-3xl" />
        </div>

        <div className="relative z-10 max-w-md w-full text-center space-y-8">
          {/* Icon cluster */}
          <div className="flex items-center justify-center gap-4">
            <div className="w-16 h-16 rounded-2xl border border-violet-500/25 bg-violet-500/10 flex items-center justify-center shadow-[0_0_40px_rgba(139,92,246,0.15)]">
              <Headphones className="w-8 h-8 text-violet-400" />
            </div>
            <div className="flex items-center gap-1.5">
              {[0, 150, 300, 450, 600].map(delay => (
                <div key={delay} className="w-2 rounded-full bg-violet-400/60 animate-pulse" style={{ height: `${[20, 32, 16, 36, 12][delay / 150]}px`, animationDelay: `${delay}ms` }} />
              ))}
            </div>
            <div className="w-16 h-16 rounded-2xl border border-violet-500/25 bg-violet-500/10 flex items-center justify-center shadow-[0_0_40px_rgba(139,92,246,0.15)]">
              <Mic2 className="w-8 h-8 text-violet-400" />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-center gap-2 mb-3">
              <NovaIcon size={20} />
              <h1 className="text-3xl font-bold text-white/80">Nova Podcast</h1>
            </div>
            <p className="text-white/35 leading-relaxed text-sm">
              Choose any topic and two Nova AI models will host a dynamic, engaging podcast episode — with distinct voices, perspectives, and personality.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 text-left">
            {[
              { icon: Radio,       label: "Dual-host format",    desc: "Two AI models with distinct voices and viewpoints" },
              { icon: Play,        label: "Any topic on demand", desc: "From science to pop culture to deep philosophy" },
              { icon: Headphones,  label: "Listen or read along", desc: "Audio playback with a live transcript" },
            ].map(item => (
              <div key={item.label} className="flex items-start gap-3 p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]">
                <item.icon className="w-4 h-4 text-violet-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-white/70">{item.label}</p>
                  <p className="text-xs text-white/30 mt-0.5">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-violet-500/30 bg-violet-500/8 text-violet-300/80 text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
            Coming soon — in development
          </div>
        </div>
      </div>
    </AppShell>
  )
}
