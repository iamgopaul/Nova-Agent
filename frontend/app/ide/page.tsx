"use client"

import { Code2, Terminal, GitBranch, Layers } from "lucide-react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { AppShell } from "@/components/app-shell"

export default function IdePage() {
  return (
    <AppShell title="IDE">
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-10 relative overflow-hidden bg-[#0a0a10]">
        {/* Ambient blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute top-0 right-1/4 w-96 h-96 rounded-full bg-indigo-500/8 blur-3xl" />
          <div className="absolute bottom-0 left-0 w-80 h-80 rounded-full bg-blue-500/6 blur-3xl" />
        </div>

        <div className="relative z-10 max-w-md w-full text-center space-y-8">
          {/* IDE window mockup */}
          <div className="w-full rounded-xl border border-indigo-500/20 bg-indigo-500/5 overflow-hidden shadow-[0_0_40px_rgba(99,102,241,0.12)]">
            <div className="flex items-center gap-1.5 px-3 py-2 border-b border-white/[0.07] bg-white/[0.03]">
              <div className="w-2.5 h-2.5 rounded-full bg-red-400/50" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-400/50" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-400/50" />
              <span className="ml-2 text-xs text-white/25">nova_app.py</span>
            </div>
            <div className="px-4 py-3 font-mono text-xs space-y-1 text-left">
              <p><span className="text-violet-400">def</span> <span className="text-blue-300">create_agent</span><span className="text-white/30">(</span><span className="text-orange-300">name</span><span className="text-white/30">: </span><span className="text-green-300">str</span><span className="text-white/30">):</span></p>
              <p className="ml-4"><span className="text-white/20"># Nova IDE writes this for you</span></p>
              <p className="ml-4"><span className="text-violet-400">return</span> <span className="text-blue-300">NovaAgent</span><span className="text-white/30">(</span><span className="text-orange-300">model</span><span className="text-white/30">=</span><span className="text-green-300">&quot;nova-core&quot;</span><span className="text-white/30">, </span><span className="text-orange-300">name</span><span className="text-white/30">=</span><span className="text-orange-300">name</span><span className="text-white/30">)</span></p>
              <p className="text-indigo-400/50 animate-pulse">|</p>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-center gap-2 mb-3">
              <NovaIcon size={20} />
              <h1 className="text-3xl font-bold text-white/80">Nova IDE</h1>
            </div>
            <p className="text-white/35 leading-relaxed text-sm">
              A full AI-native code editor powered by Nova models. Write, explain, refactor, debug, and ship code with an intelligent co-pilot at every keystroke.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-3 text-left">
            {[
              { icon: Code2,     label: "Multi-language support", desc: "Python, TypeScript, Rust, Go, and more" },
              { icon: Terminal,  label: "Integrated terminal",    desc: "Run and test your code without leaving Nova" },
              { icon: GitBranch, label: "Git integration",        desc: "Commit, branch, and PR directly from the IDE" },
              { icon: Layers,    label: "Nova model panel",       desc: "Switch between Nova Code, Core, or Pro per task" },
            ].map(item => (
              <div key={item.label} className="flex items-start gap-3 p-3 rounded-xl border border-white/[0.07] bg-white/[0.03]">
                <item.icon className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-white/70">{item.label}</p>
                  <p className="text-xs text-white/30 mt-0.5">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-indigo-500/30 bg-indigo-500/8 text-indigo-300/80 text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
            Coming soon — in development
          </div>
        </div>
      </div>
    </AppShell>
  )
}
