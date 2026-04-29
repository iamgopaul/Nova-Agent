"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import {
  MessageSquare,
  Mic,
  Headphones,
  Network,
  Scale,
  Code2,
  Cog,
  LogOut,
  ArrowRight,
  GraduationCap,
  Zap,
  Monitor,
  Film,
} from "lucide-react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { cn } from "@/lib/utils"

interface UserInfo {
  display_name: string
  avatar_color: string
}

type AppStatus = "live" | "new" | "soon"

interface Feature {
  key: string
  label: string
  description: string
  href: string
  icon: React.ElementType
  gradient: string
  border: string
  iconBg: string
  iconColor: string
  glow: string
  status: AppStatus
  statusLabel?: string
}

const FEATURES: Feature[] = [
  {
    key: "chat",
    label: "GAAIA Chat",
    description: "Intelligent multi-model conversations with web search, image generation, and document creation.",
    href: "/chat",
    icon: MessageSquare,
    gradient: "from-blue-500/[0.18] via-cyan-500/[0.08] to-transparent",
    border: "border-blue-500/25 hover:border-blue-400/55",
    iconBg: "bg-blue-500/15 border-blue-500/30",
    iconColor: "text-blue-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.72_0.14_220_/_0.18)]",
    status: "live",
  },
  {
    key: "voice",
    label: "GAAIA Voice",
    description: "Real-time voice conversations with GAAIA. Speak naturally and get spoken responses with camera support.",
    href: "/voice",
    icon: Mic,
    gradient: "from-cyan-500/[0.18] via-teal-500/[0.08] to-transparent",
    border: "border-cyan-500/25 hover:border-cyan-400/55",
    iconBg: "bg-cyan-500/15 border-cyan-500/30",
    iconColor: "text-cyan-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.80_0.12_195_/_0.18)]",
    status: "live",
  },
  {
    key: "education",
    label: "GAAIA Education",
    description: "GAAIA teaches a topic, builds quizzes and exams, then grades your answers with detailed feedback.",
    href: "/education",
    icon: GraduationCap,
    gradient: "from-rose-500/[0.18] via-fuchsia-500/[0.08] to-transparent",
    border: "border-rose-500/25 hover:border-rose-400/55",
    iconBg: "bg-rose-500/15 border-rose-500/30",
    iconColor: "text-rose-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.72_0.16_15_/_0.18)]",
    status: "new",
  },
  {
    key: "podcast",
    label: "GAAIA Podcast",
    description: "Two AI models host a dynamic podcast on any topic you choose. Sit back and listen.",
    href: "/podcast",
    icon: Headphones,
    gradient: "from-violet-500/[0.15] via-purple-500/[0.07] to-transparent",
    border: "border-violet-500/20 hover:border-violet-400/45",
    iconBg: "bg-violet-500/12 border-violet-500/25",
    iconColor: "text-violet-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.65_0.18_280_/_0.15)]",
    status: "soon",
  },
  {
    key: "agents",
    label: "GAAIA Agents",
    description: "Assign tasks to specialized GAAIA models working in parallel — like your own AI team.",
    href: "/agents",
    icon: Network,
    gradient: "from-emerald-500/[0.15] via-green-500/[0.07] to-transparent",
    border: "border-emerald-500/20 hover:border-emerald-400/45",
    iconBg: "bg-emerald-500/12 border-emerald-500/25",
    iconColor: "text-emerald-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.80_0.14_160_/_0.15)]",
    status: "soon",
  },
  {
    key: "debate",
    label: "GAAIA Debate",
    description: "Watch two AI models argue opposing sides of any topic. Moderated, scored, and insightful.",
    href: "/debate",
    icon: Scale,
    gradient: "from-orange-500/[0.15] via-amber-500/[0.07] to-transparent",
    border: "border-orange-500/20 hover:border-orange-400/45",
    iconBg: "bg-orange-500/12 border-orange-500/25",
    iconColor: "text-orange-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.80_0.16_60_/_0.15)]",
    status: "soon",
  },
  {
    key: "ide",
    label: "GAAIA IDE",
    description: "AI-powered code editor. Write, debug, and ship code with GAAIA models as your co-pilot.",
    href: "/ide",
    icon: Code2,
    gradient: "from-indigo-500/[0.15] via-blue-500/[0.07] to-transparent",
    border: "border-indigo-500/20 hover:border-indigo-400/45",
    iconBg: "bg-indigo-500/12 border-indigo-500/25",
    iconColor: "text-indigo-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.60_0.18_250_/_0.15)]",
    status: "soon",
  },
  {
    key: "screen",
    label: "GAAIA Screen",
    description: "Ask GAAIA what's on your screen or explain anything you've copied. Vision-powered, fully local.",
    href: "/screen",
    icon: Monitor,
    gradient: "from-sky-500/[0.15] via-cyan-500/[0.07] to-transparent",
    border: "border-sky-500/20 hover:border-sky-400/45",
    iconBg: "bg-sky-500/12 border-sky-500/25",
    iconColor: "text-sky-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.72_0.18_215_/_0.15)]",
    status: "new",
  },
  {
    key: "video",
    label: "GAAIA Video",
    description: "Analyse YouTube videos, direct links, or local files. Frame extraction + vision LLM, no cloud.",
    href: "/video",
    icon: Film,
    gradient: "from-purple-500/[0.15] via-violet-500/[0.07] to-transparent",
    border: "border-purple-500/20 hover:border-purple-400/45",
    iconBg: "bg-purple-500/12 border-purple-500/25",
    iconColor: "text-purple-400",
    glow: "hover:shadow-[0_4px_32px_oklch(0.60_0.20_280_/_0.15)]",
    status: "new",
  },
]

function StatusBadge({ status }: { status: AppStatus }) {
  if (status === "live") {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        Live
      </span>
    )
  }
  if (status === "new") {
    return (
      <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-primary/20 text-primary border border-primary/30">
        <Zap className="w-2.5 h-2.5" />
        New
      </span>
    )
  }
  return (
    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-white/[0.06] text-white/30 border border-white/[0.08]">
      Soon
    </span>
  )
}

export default function HomePage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [showMenu, setShowMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(async r => {
        // Only redirect to login on explicit 401 (token invalid/expired)
        if (r.status === 401) {
          await fetch("/api/auth/logout", { method: "POST" }).catch(() => {})
          router.replace("/login")
          return null
        }
        if (!r.ok) return null  // server error — stay on page, don't log out
        return r.json()
      })
      .then(data => {
        if (data?.display_name) {
          setUser({ display_name: data.display_name, avatar_color: data.avatar_color || "#0ea5e9" })
        }
      })
      .catch(() => {})  // network error — stay on page silently
  }, [router])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    if (showMenu) document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [showMenu])

  const handleSignOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" })
    router.push("/signout")
  }

  const greeting = () => {
    const h = new Date().getHours()
    if (h < 12) return "Good morning"
    if (h < 17) return "Good afternoon"
    return "Good evening"
  }

  const liveFeatures = FEATURES.filter(f => f.status === "live" || f.status === "new")
  const soonFeatures = FEATURES.filter(f => f.status === "soon")

  return (
    <div className="min-h-screen aurora-bg relative overflow-hidden">
      {/* Ambient blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 w-[480px] h-[480px] rounded-full bg-blue-500/[0.08] blur-3xl" />
        <div className="absolute top-1/3 -right-32 w-96 h-96 rounded-full bg-violet-500/[0.08] blur-3xl" />
        <div className="absolute bottom-0 left-1/3 w-80 h-80 rounded-full bg-cyan-500/[0.06] blur-3xl" />
      </div>

      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header className="relative z-10 flex items-center justify-between px-6 py-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-2.5">
          <GaaiaIcon size={28} />
          <span className="font-bold text-base tracking-tight">GAAIA</span>
        </div>

        <div className="flex items-center gap-3">
          {user && (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setShowMenu(prev => !prev)}
                className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold",
                  "ring-2 ring-transparent transition-all",
                  showMenu ? "ring-primary/60 scale-105" : "hover:ring-primary/40 hover:scale-105"
                )}
                style={{ backgroundColor: user.avatar_color }}
                title={user.display_name}
              >
                {user.display_name[0].toUpperCase()}
              </button>

              {showMenu && (
                <div className="absolute right-0 top-full mt-2 w-52 rounded-2xl border border-border bg-popover shadow-2xl overflow-hidden z-50">
                  <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-muted/30">
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
                      style={{ backgroundColor: user.avatar_color }}
                    >
                      {user.display_name[0].toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">{user.display_name}</p>
                      <p className="text-xs text-muted-foreground">GAAIA account</p>
                    </div>
                  </div>
                  <div className="p-1.5 space-y-0.5">
                    <Link
                      href="/settings"
                      onClick={() => setShowMenu(false)}
                      className="flex items-center gap-3 px-3 py-2 rounded-xl text-sm hover:bg-muted transition-colors"
                    >
                      <Cog className="w-4 h-4 text-muted-foreground" />
                      Settings
                    </Link>
                    <button
                      onClick={handleSignOut}
                      className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-destructive hover:bg-destructive/10 transition-colors"
                    >
                      <LogOut className="w-4 h-4" />
                      Sign out
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* ── Hero ────────────────────────────────────────────────────── */}
      <section className="relative z-10 text-center px-6 pt-8 pb-12 max-w-3xl mx-auto">
        <p className="text-sm text-muted-foreground mb-2">
          {greeting()}{user ? `, ${user.display_name}` : ""}
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4 leading-tight">
          What would you like to{" "}
          <span className="bg-gradient-to-r from-blue-400 via-cyan-400 to-violet-400 bg-clip-text text-transparent">
            create today?
          </span>
        </h1>
        <p className="text-muted-foreground text-sm max-w-lg mx-auto">
          Choose an experience below — from intelligent conversation to AI-hosted podcasts, debates, and more.
        </p>
      </section>

      {/* ── Feature grid ────────────────────────────────────────────── */}
      <main className="relative z-10 max-w-6xl mx-auto px-6 pb-24 space-y-10">

        {/* Live apps section */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Available now</span>
            <div className="flex-1 h-px bg-border/40" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {liveFeatures.map(f => <AppCard key={f.key} feature={f} />)}
          </div>
        </div>

        {/* Coming soon section */}
        <div>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">In development</span>
            <div className="flex-1 h-px bg-border/40" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {soonFeatures.map(f => <AppCard key={f.key} feature={f} dimmed />)}
          </div>
        </div>

      </main>

      {/* ── Bottom status bar ───────────────────────────────────────── */}
      <footer
        className="fixed bottom-0 left-0 right-0 z-10 px-6 py-2.5 border-t border-white/[0.07] backdrop-blur-sm"
        style={{ backgroundColor: "var(--surface-2)" }}
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          {user && (
            <div className="flex items-center gap-2">
              <div
                className="w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold shrink-0"
                style={{ backgroundColor: user.avatar_color }}
              >
                {user.display_name[0].toUpperCase()}
              </div>
              <span className="text-xs text-muted-foreground">{user.display_name}</span>
            </div>
          )}
          <Link href="/settings" className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
            <Cog className="w-3.5 h-3.5" />
            Settings
          </Link>
        </div>
      </footer>
    </div>
  )
}

function AppCard({ feature: f, dimmed = false }: { feature: Feature; dimmed?: boolean }) {
  const Icon = f.icon
  return (
    <Link
      href={f.href}
      className={cn(
        "group relative flex flex-col gap-3.5 p-5 rounded-2xl border transition-all duration-300",
        "bg-card/40 backdrop-blur-sm",
        f.border,
        f.glow,
        dimmed
          ? "hover:-translate-y-0.5 hover:bg-card/55 opacity-70 hover:opacity-90"
          : "hover:-translate-y-1 hover:bg-card/65"
      )}
    >
      {/* Gradient fill */}
      <div className={cn(
        "absolute inset-0 rounded-2xl bg-gradient-to-br opacity-50 group-hover:opacity-80 transition-opacity duration-300",
        f.gradient
      )} />

      {/* Header: icon + status badge */}
      <div className="relative flex items-start justify-between gap-2">
        <div className={cn(
          "w-10 h-10 rounded-xl flex items-center justify-center border backdrop-blur-sm shrink-0",
          f.iconBg
        )}>
          <Icon className={cn("w-5 h-5", f.iconColor)} />
        </div>
        <StatusBadge status={f.status} />
      </div>

      {/* Text */}
      <div className="relative flex-1 min-w-0">
        <h2 className="text-sm font-semibold text-foreground mb-1">{f.label}</h2>
        <p className={cn(
          "text-xs leading-relaxed",
          dimmed ? "text-muted-foreground/70" : "text-muted-foreground"
        )}>
          {f.description}
        </p>
      </div>

      {/* CTA */}
      <div className={cn(
        "relative flex items-center gap-1 text-xs font-medium transition-all duration-200",
        f.iconColor,
        dimmed ? "opacity-30 group-hover:opacity-50" : "opacity-50 group-hover:opacity-100"
      )}>
        <span>{f.status === "soon" ? "Preview" : "Open"}</span>
        <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
      </div>
    </Link>
  )
}
