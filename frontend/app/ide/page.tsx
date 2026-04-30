"use client"

import { Code2, Terminal, GitBranch, Layers } from "lucide-react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { AppShell } from "@/components/app-shell"

export default function IdePage() {
  return (
    <AppShell title="IDE" titleColor="text-indigo-400">
      <div className="flex h-full flex-col items-center justify-center px-6 py-10 relative overflow-hidden">
        {/* Page gradient */}
        <div className="pointer-events-none absolute inset-0 page-gradient-ide" />
        {/* Ambient blobs */}
        <div className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute top-0 right-1/4 w-96 h-96 rounded-full bg-indigo-500/7 blur-3xl" />
          <div className="absolute bottom-0 left-0 w-80 h-80 rounded-full bg-blue-500/5 blur-3xl" />
        </div>

        <div className="relative z-10 max-w-lg w-full text-center space-y-8">

          {/* IDE window mockup */}
          <div className="w-full rounded-xl border border-indigo-500/25 bg-indigo-500/6 overflow-hidden shadow-[0_0_48px_oklch(0.60_0.18_265/0.16)]">
            {/* Title bar */}
            <div className="flex items-center gap-1.5 px-3 py-2.5 border-b border-white/7 bg-white/3">
              <div className="w-2.5 h-2.5 rounded-full bg-red-400/50" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-400/50" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-400/50" />
              <span className="ml-2 text-xs text-white/25 font-mono">gaaia_app.py</span>
            </div>
            {/* Code */}
            <div className="px-5 py-4 font-mono text-xs space-y-1.5 text-left select-none">
              <p>
                <span className="text-violet-400">def</span>{" "}
                <span className="text-blue-300">create_agent</span>
                <span className="text-white/30">(</span>
                <span className="text-orange-300">name</span>
                <span className="text-white/30">: </span>
                <span className="text-green-300">str</span>
                <span className="text-white/30">):</span>
              </p>
              <p className="ml-5">
                <span className="text-white/20 italic"># GAAIA IDE writes this for you</span>
              </p>
              <p className="ml-5">
                <span className="text-violet-400">return</span>{" "}
                <span className="text-blue-300">GAAIAAgent</span>
                <span className="text-white/30">(</span>
                <span className="text-orange-300">model</span>
                <span className="text-white/30">=</span>
                <span className="text-green-300">&quot;gaaia-core&quot;</span>
                <span className="text-white/30">, </span>
                <span className="text-orange-300">name</span>
                <span className="text-white/30">=</span>
                <span className="text-orange-300">name</span>
                <span className="text-white/30">)</span>
              </p>
              <p className="text-indigo-400/70 animate-pulse">▍</p>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-center gap-2 mb-3">
              <GaaiaIcon size={20} />
              <h1 className="text-3xl font-bold text-white/85">GAAIA IDE</h1>
            </div>
            <p className="text-white/40 leading-relaxed text-sm max-w-sm mx-auto">
              A full AI-native code editor powered by GAAIA models. Write, explain, refactor, debug, and ship code with an intelligent co-pilot at every keystroke.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-2.5 text-left">
            {[
              { icon: Code2,     label: "Multi-language support", desc: "Python, TypeScript, Rust, Go, and more" },
              { icon: Terminal,  label: "Integrated terminal",    desc: "Run and test your code without leaving GAAIA" },
              { icon: GitBranch, label: "Git integration",        desc: "Commit, branch, and PR directly from the IDE" },
              { icon: Layers,    label: "GAAIA model panel",       desc: "Switch between GAAIA Code, Core, or Pro per task" },
            ].map(item => (
              <div key={item.label} className="flex items-start gap-3 p-3.5 rounded-xl border border-indigo-500/15 bg-indigo-500/5 hover:bg-indigo-500/8 transition-colors">
                <div className="w-7 h-7 rounded-lg bg-indigo-500/15 border border-indigo-500/20 flex items-center justify-center shrink-0 mt-0.5">
                  <item.icon className="w-3.5 h-3.5 text-indigo-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white/75">{item.label}</p>
                  <p className="text-xs text-white/35 mt-0.5">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-indigo-500/30 bg-indigo-500/8 text-indigo-300/80 text-sm font-semibold">
            <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
            Coming soon — in development
          </div>
        </div>
      </div>
    </AppShell>
  )
}
