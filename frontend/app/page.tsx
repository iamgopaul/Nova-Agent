"use client"

import Link from "next/link"
import { NovaIcon } from "@/components/icons/nova-icon"

const FEATURES = [
  {
    icon: "✦",
    title: "Private by Design",
    desc: "Everything runs on your device via Ollama. No cloud, no telemetry, no data ever leaves your machine.",
  },
  {
    icon: "⚡",
    title: "Blazing Fast",
    desc: "Local inference with hardware-aware model routing. Spark for instant replies, Pro for deep reasoning.",
  },
  {
    icon: "🎙",
    title: "Voice & Vision",
    desc: "Full voice conversations with Whisper STT and Kokoro TTS. Real-time camera detection and face identity.",
  },
  {
    icon: "🖼",
    title: "Rich Generation",
    desc: "Generate images, documents, charts, music, and stories. All rendered inline in the chat window.",
  },
  {
    icon: "🔍",
    title: "Live Web Search",
    desc: "Brave Search integration brings fresh news, images, and articles into every relevant response.",
  },
  {
    icon: "🧠",
    title: "Persistent Memory",
    desc: "Nova remembers facts about you across conversations. Notes, knowledge feed, and contextual recall.",
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen aurora-bg text-foreground font-sans antialiased flex flex-col">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-6xl mx-auto w-full">
        <div className="flex items-center gap-2.5">
          <NovaIcon size={36} />
          <span className="text-lg font-semibold tracking-wide">Nova</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            className="px-4 py-2 text-sm font-medium rounded-xl bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
          >
            Get started
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="flex-1 flex flex-col items-center justify-center text-center px-6 py-20 max-w-4xl mx-auto w-full">
        {/* Badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary text-xs font-medium mb-8">
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
          Fully local · No API keys · Privacy first
        </div>

        {/* Icon */}
        <div className="mb-8 relative">
          <div className="absolute inset-0 rounded-full blur-3xl bg-primary/20 scale-150" />
          <NovaIcon size={96} className="relative" />
        </div>

        {/* Heading */}
        <h1 className="text-5xl sm:text-6xl font-bold tracking-tight mb-6 leading-tight">
          Your personal AI,{" "}
          <span
            className="bg-clip-text text-transparent"
            style={{
              backgroundImage:
                "linear-gradient(135deg, oklch(0.80 0.16 210), oklch(0.70 0.18 250))",
            }}
          >
            on your terms
          </span>
        </h1>

        <p className="text-lg text-muted-foreground max-w-2xl mb-10 leading-relaxed">
          Nova is a powerful AI assistant that runs entirely on your hardware. Chat, research, create, and automate —
          with complete privacy, zero subscriptions, and no data ever leaving your machine.
        </p>

        <div className="flex items-center gap-4 flex-wrap justify-center">
          <Link
            href="/signup"
            className="px-7 py-3.5 text-base font-semibold rounded-2xl bg-primary text-primary-foreground hover:opacity-90 active:scale-95 transition-all shadow-[0_0_32px_oklch(0.72_0.14_220_/_0.35)]"
          >
            Create free account
          </Link>
          <Link
            href="/login"
            className="px-7 py-3.5 text-base font-medium rounded-2xl border border-border bg-card/60 backdrop-blur-sm hover:border-primary/40 transition-all"
          >
            Sign in
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-center mb-2">Everything you need, nothing you don&apos;t</h2>
          <p className="text-muted-foreground text-center mb-12 text-sm">
            Built for power users who value privacy.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="rounded-2xl border border-border/50 bg-card/60 backdrop-blur-sm p-5 hover:border-primary/30 hover:shadow-[0_0_20px_oklch(0.72_0.14_220_/_0.07)] transition-all duration-200"
              >
                <div className="text-2xl mb-3">{f.icon}</div>
                <h3 className="font-semibold text-sm mb-1.5">{f.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA strip */}
      <section className="py-16 px-6">
        <div className="max-w-2xl mx-auto text-center rounded-3xl border border-primary/20 bg-primary/5 backdrop-blur-sm p-10">
          <NovaIcon size={48} className="mx-auto mb-4" />
          <h2 className="text-2xl font-bold mb-3">Ready to get started?</h2>
          <p className="text-muted-foreground text-sm mb-6">
            Create your account and launch Nova in seconds. Your data stays yours.
          </p>
          <Link
            href="/signup"
            className="inline-block px-8 py-3.5 font-semibold rounded-2xl bg-primary text-primary-foreground hover:opacity-90 transition-opacity shadow-[0_0_24px_oklch(0.72_0.14_220_/_0.30)]"
          >
            Get started for free
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-border/40 text-center text-xs text-muted-foreground">
        <div className="flex items-center justify-center gap-2 mb-2">
          <NovaIcon size={18} />
          <span className="font-medium text-foreground">Nova</span>
        </div>
        <p>Local AI assistant · All data stays on your machine · Built with privacy in mind</p>
      </footer>
    </div>
  )
}
