"use client"

import { Network, BrainCircuit, Workflow, Zap } from "lucide-react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { AppShell } from "@/components/app-shell"

export default function AgentsPage() {
  return (
    <AppShell title="Agents">
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 relative overflow-hidden bg-[#0a0a10]">
        {/* Ambient blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute top-1/4 right-0 w-96 h-96 rounded-full bg-emerald-500/8 blur-3xl" />
          <div className="absolute bottom-0 left-1/4 w-80 h-80 rounded-full bg-green-500/6 blur-3xl" />
        </div>

        <div className="relative z-10 max-w-md w-full text-center space-y-8">
          {/* Animated agent nodes */}
          <div className="flex items-center justify-center">
            <div className="relative w-40 h-40">
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-14 h-14 rounded-2xl border border-emerald-500/30 bg-emerald-500/12 flex items-center justify-center shadow-[0_0_40px_rgba(52,211,153,0.15)]">
                  <Network className="w-7 h-7 text-emerald-400" />
                </div>
              </div>
              {[0, 72, 144, 216, 288].map((deg, i) => {
                const rad = (deg * Math.PI) / 180
                const x = 50 + 44 * Math.cos(rad)
                const y = 50 + 44 * Math.sin(rad)
                return (
                  <div
                    key={i}
                    className="absolute w-8 h-8 rounded-full border border-emerald-500/25 bg-emerald-500/8 flex items-center justify-center"
                    style={{ left: `${x}%`, top: `${y}%`, transform: "translate(-50%,-50%)" }}
                  >
                    <Zap className="w-3.5 h-3.5 text-emerald-400/70" />
                  </div>
                )
              })}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-center gap-2 mb-3">
              <NovaIcon size={20} />
              <h1 className="text-3xl font-bold text-white/80">Nova Agents</h1>
            </div>
            <p className="text-white/35 leading-relaxed text-sm">
              Orchestrate a team of specialized AI agents. Assign tasks to Nova Code, Nova Research, Nova Analyst and watch them collaborate on complex workflows.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 text-left">
            {[
              { icon: Workflow,     label: "Multi-agent workflows", desc: "Chain tasks across specialized Nova models" },
              { icon: BrainCircuit, label: "Parallel execution",    desc: "Agents work simultaneously, not sequentially" },
              { icon: Network,      label: "Visual pipeline editor", desc: "Drag-and-drop task graph with real-time output" },
            ].map(item => (
              <div key={item.label} className="flex items-start gap-3 p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]">
                <item.icon className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-white/70">{item.label}</p>
                  <p className="text-xs text-white/30 mt-0.5">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-emerald-500/30 bg-emerald-500/8 text-emerald-300/80 text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Coming soon — in development
          </div>
        </div>
      </div>
    </AppShell>
  )
}
