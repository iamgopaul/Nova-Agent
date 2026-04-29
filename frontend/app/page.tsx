"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import {
  MessageSquare,
  Mic,
  Headphones,
  Network,
  Scale,
  Code2,
  GraduationCap,
  ArrowRight,
  CheckCircle,
  Crown,
  Sparkles,
  Users,
  Zap,
  Shield,
} from "lucide-react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { cn } from "@/lib/utils"

const FEATURES = [
  { icon: MessageSquare, label: "GAAIA Chat",      color: "text-blue-400",    bg: "bg-blue-500/10 border-blue-500/20",    description: "Multi-model conversations with web search, image generation & document creation." },
  { icon: Mic,           label: "GAAIA Voice",     color: "text-cyan-400",    bg: "bg-cyan-500/10 border-cyan-500/20",    description: "Real-time voice conversations. Speak naturally, get spoken responses." },
  { icon: GraduationCap, label: "GAAIA Education", color: "text-rose-400",    bg: "bg-rose-500/10 border-rose-500/20",    description: "AI-powered lessons, quizzes, and exams — graded with instant feedback." },
  { icon: Headphones,    label: "GAAIA Podcast",   color: "text-violet-400",  bg: "bg-violet-500/10 border-violet-500/20",description: "Two AI models host a dynamic podcast on any topic you choose." },
  { icon: Network,       label: "GAAIA Agents",    color: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/20", description: "Assign tasks to specialised GAAIA models working in parallel." },
  { icon: Scale,         label: "GAAIA Debate",    color: "text-orange-400",  bg: "bg-orange-500/10 border-orange-500/20", description: "Watch two AI models argue opposing sides of any topic." },
  { icon: Code2,         label: "GAAIA IDE",       color: "text-indigo-400",  bg: "bg-indigo-500/10 border-indigo-500/20", description: "AI-powered code editor — write, debug, and ship with GAAIA as co-pilot." },
]

const PILLARS = [
  { icon: Sparkles, title: "Multi-model intelligence", body: "Switch between leading AI models mid-conversation. Always use the right tool for the task." },
  { icon: Zap,      title: "Real-time everything",     body: "Streaming responses, live voice, instant image generation — no waiting, no reloading." },
  { icon: Shield,   title: "Private by design",        body: "Your data stays on your machine. No telemetry, no cloud storage of your conversations." },
]

export default function LandingPage() {
  const router = useRouter()
  const [resuming, setResuming] = useState(false)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => {
        if (r.ok) { setResuming(true); router.replace("/home") }
      })
      .catch(() => {})
  }, [router])

  if (resuming) {
    return (
      <div className="min-h-screen aurora-bg flex flex-col items-center justify-center gap-4 text-foreground">
        <GaaiaIcon size={56} className="animate-pulse" />
        <p className="text-sm text-muted-foreground">Resuming your session…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen aurora-bg relative overflow-x-hidden text-foreground">
      {/* Ambient blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 w-[520px] h-[520px] rounded-full bg-blue-500/[0.09] blur-3xl" />
        <div className="absolute top-1/2 -right-40 w-96 h-96 rounded-full bg-violet-500/[0.09] blur-3xl" />
        <div className="absolute bottom-0 left-1/4 w-80 h-80 rounded-full bg-cyan-500/[0.07] blur-3xl" />
      </div>

      {/* ── Nav ─────────────────────────────────────────────────────── */}
      <nav className="relative z-10 flex items-center justify-between px-6 md:px-12 py-5 max-w-7xl mx-auto">
        <div className="flex items-center gap-2.5">
          <GaaiaIcon size={28} />
          <span className="font-bold text-lg tracking-tight">GAAIA</span>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5"
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            className="flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-xl bg-primary text-primary-foreground hover:opacity-90 active:scale-[0.98] transition-all shadow-[0_0_20px_oklch(0.72_0.14_220_/_0.25)]"
          >
            Get started <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </nav>

      {/* ── Hero ────────────────────────────────────────────────────── */}
      <section className="relative z-10 text-center px-6 pt-20 pb-24 max-w-4xl mx-auto">
        <div className="inline-flex items-center gap-2 text-xs font-semibold px-3.5 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary mb-8">
          <Sparkles className="w-3.5 h-3.5" />
          Your personal AI platform
        </div>

        <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight leading-[1.08] mb-6">
          One platform.{" "}
          <span className="bg-gradient-to-r from-blue-400 via-cyan-400 to-violet-400 bg-clip-text text-transparent">
            Every AI experience.
          </span>
        </h1>

        <p className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed">
          Chat, voice, podcast, debate, agents, IDE, and education — all powered by the world&apos;s leading AI models,
          unified in one beautifully designed app.
        </p>

        <div className="flex items-center justify-center gap-4 flex-wrap">
          <Link
            href="/signup"
            className="flex items-center gap-2 px-7 py-3.5 rounded-2xl bg-primary text-primary-foreground font-bold text-base hover:opacity-90 active:scale-[0.98] transition-all shadow-[0_0_32px_oklch(0.72_0.14_220_/_0.30)]"
          >
            Start for free <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/login"
            className="flex items-center gap-2 px-7 py-3.5 rounded-2xl border border-border bg-card/50 backdrop-blur-sm font-semibold text-base hover:bg-card/80 transition-all"
          >
            Sign in
          </Link>
        </div>
      </section>

      {/* ── Feature grid ────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-6xl mx-auto px-6 pb-28">
        <p className="text-center text-[10px] font-bold tracking-widest text-muted-foreground uppercase mb-10">
          Seven experiences. One account.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3.5">
          {FEATURES.map(f => {
            const Icon = f.icon
            return (
              <div
                key={f.label}
                className="flex items-start gap-3.5 p-4 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-sm hover:bg-card/60 hover:border-border/80 transition-all"
              >
                <div className={cn("w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border", f.bg)}>
                  <Icon className={cn("w-4 h-4", f.color)} />
                </div>
                <div>
                  <p className="text-sm font-semibold mb-1">{f.label}</p>
                  <p className="text-xs text-muted-foreground leading-relaxed">{f.description}</p>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Pillars ─────────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-4xl mx-auto px-6 pb-32">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 text-center">
          {PILLARS.map(p => {
            const Icon = p.icon
            return (
              <div key={p.title} className="flex flex-col items-center gap-3">
                <div className="w-11 h-11 rounded-2xl flex items-center justify-center bg-primary/15 border border-primary/20">
                  <Icon className="w-5 h-5 text-primary" />
                </div>
                <h3 className="text-sm font-bold">{p.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{p.body}</p>
              </div>
            )
          })}
        </div>
      </section>

      {/* ── Pricing ─────────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-5xl mx-auto px-6 pb-32">
        <div className="text-center mb-12">
          <p className="text-[10px] font-bold tracking-widest text-muted-foreground uppercase mb-3">Pricing</p>
          <h2 className="text-3xl font-extrabold tracking-tight">Simple, transparent pricing</h2>
          <p className="text-muted-foreground text-sm mt-3 max-w-lg mx-auto">
            Start free. Upgrade when you need more. All plans include the full GAAIA experience on your local machine.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Free */}
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-6 flex flex-col gap-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-white/[0.07] border border-white/[0.1] flex items-center justify-center">
                <Zap className="w-5 h-5 text-white/50" />
              </div>
              <div>
                <p className="font-semibold">Free</p>
                <p className="text-xs text-muted-foreground">1 user</p>
              </div>
            </div>
            <div><span className="text-3xl font-bold">$0</span></div>
            <ul className="space-y-2 flex-1">
              {["Local Ollama models", "Chat, voice & all 7 experiences", "10 MB file uploads", "3 Web Watch topics", "Community support"].map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />{f}
                </li>
              ))}
            </ul>
            <Link href="/signup" className="w-full py-2.5 rounded-xl text-center text-sm font-medium bg-white/[0.06] text-white/50 border border-white/[0.08] hover:bg-white/[0.10] transition-colors">
              Get started free
            </Link>
          </div>

          {/* Pro */}
          <div className="relative rounded-2xl border border-indigo-500/30 bg-indigo-500/5 p-6 flex flex-col gap-5 ring-1 ring-indigo-500/20">
            <div className="absolute -top-3.5 left-1/2 -translate-x-1/2">
              <span className="text-[10px] font-bold px-3 py-1 rounded-full bg-indigo-600 text-white border border-indigo-400/30">
                MOST POPULAR
              </span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-400/25 flex items-center justify-center">
                <Crown className="w-5 h-5 text-indigo-400" />
              </div>
              <div>
                <p className="font-semibold">Pro</p>
                <p className="text-xs text-muted-foreground">1 user</p>
              </div>
            </div>
            <div>
              <span className="text-3xl font-bold">$12</span>
              <span className="text-sm text-muted-foreground ml-1">/month</span>
            </div>
            <ul className="space-y-2 flex-1">
              {["Everything in Free", "Unlimited file uploads & RAG", "Unlimited Web Watch topics", "Scheduled automations", "Priority email support", "Early access to new features"].map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />{f}
                </li>
              ))}
            </ul>
            <Link href="/signup" className="w-full py-2.5 rounded-xl text-center text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors">
              Start Pro trial
            </Link>
          </div>

          {/* Teams */}
          <div className="rounded-2xl border border-violet-500/30 bg-violet-500/5 p-6 flex flex-col gap-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-violet-500/20 border border-violet-400/25 flex items-center justify-center">
                <Users className="w-5 h-5 text-violet-400" />
              </div>
              <div>
                <p className="font-semibold">Teams</p>
                <p className="text-xs text-muted-foreground">Up to 10 seats</p>
              </div>
            </div>
            <div>
              <span className="text-3xl font-bold">$35</span>
              <span className="text-sm text-muted-foreground ml-1">/month</span>
            </div>
            <ul className="space-y-2 flex-1">
              {["Everything in Pro", "Up to 10 team members", "Shared knowledge base", "Admin dashboard & audit logs", "Organisation management", "SSO (coming soon)"].map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />{f}
                </li>
              ))}
            </ul>
            <Link href="/signup" className="w-full py-2.5 rounded-xl text-center text-sm font-semibold bg-violet-600 hover:bg-violet-500 text-white transition-colors">
              Start Teams trial
            </Link>
          </div>
        </div>
      </section>

      {/* ── CTA Banner ──────────────────────────────────────────────── */}
      <section className="relative z-10 max-w-3xl mx-auto px-6 pb-28 text-center">
        <div className="rounded-3xl border border-primary/20 bg-primary/[0.06] backdrop-blur-sm px-10 py-12">
          <h2 className="text-3xl font-extrabold tracking-tight mb-3">Ready for GAAIA?</h2>
          <p className="text-muted-foreground mb-8 text-sm">
            Create your free account and start exploring every AI experience in seconds.
          </p>
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 px-8 py-3.5 rounded-2xl bg-primary text-primary-foreground font-bold text-base hover:opacity-90 active:scale-[0.98] transition-all shadow-[0_0_32px_oklch(0.72_0.14_220_/_0.30)]"
          >
            Create free account <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <footer className="relative z-10 border-t border-border/30 px-6 py-8">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <GaaiaIcon size={20} />
            <span className="text-sm font-bold text-muted-foreground">GAAIA</span>
          </div>
          <div className="flex items-center gap-6 text-xs text-muted-foreground">
            <Link href="/login"  className="hover:text-foreground transition-colors">Sign in</Link>
            <Link href="/signup" className="hover:text-foreground transition-colors">Sign up</Link>
          </div>
          <p className="text-[11px] text-muted-foreground/50">Your data stays on your machine. Always.</p>
        </div>
      </footer>
    </div>
  )
}
