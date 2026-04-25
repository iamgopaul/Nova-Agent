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
} from "lucide-react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { cn } from "@/lib/utils"

interface UserInfo {
  display_name: string
  avatar_color: string
}

const FEATURES = [
  {
    key: "education",
    label: "Nova Education",
    description:
      "Nova teaches a topic, builds quizzes and exams, then grades your answers with clear feedback and next steps.",
    href: "/education",
    icon: GraduationCap,
    gradient: "from-rose-500/20 via-fuchsia-500/10 to-transparent",
    border: "border-rose-500/30 hover:border-rose-400/60",
    iconColor: "text-rose-400",
    glow: "shadow-[0_0_40px_oklch(0.72_0.16_15_/_0.15)]",
    badge: "New",
  },
  {
    key: "chat",
    label: "Nova Chat",
    description: "Intelligent multi-model conversations with web search, image generation, and document creation.",
    href: "/chat",
    icon: MessageSquare,
    gradient: "from-blue-500/20 via-cyan-500/10 to-transparent",
    border: "border-blue-500/30 hover:border-blue-400/60",
    iconColor: "text-blue-400",
    glow: "shadow-[0_0_40px_oklch(0.72_0.14_220_/_0.15)]",
    badge: null,
  },
  {
    key: "voice",
    label: "Nova Voice",
    description: "Real-time voice conversations with Nova. Speak naturally and get spoken responses.",
    href: "/voice",
    icon: Mic,
    gradient: "from-cyan-500/20 via-teal-500/10 to-transparent",
    border: "border-cyan-500/30 hover:border-cyan-400/60",
    iconColor: "text-cyan-400",
    glow: "shadow-[0_0_40px_oklch(0.80_0.12_195_/_0.15)]",
    badge: null,
  },
  {
    key: "podcast",
    label: "Nova Podcast",
    description: "Two AI models host a dynamic podcast on any topic you choose. Sit back and listen.",
    href: "/podcast",
    icon: Headphones,
    gradient: "from-violet-500/20 via-purple-500/10 to-transparent",
    border: "border-violet-500/30 hover:border-violet-400/60",
    iconColor: "text-violet-400",
    glow: "shadow-[0_0_40px_oklch(0.65_0.18_280_/_0.15)]",
    badge: "New",
  },
  {
    key: "agents",
    label: "Nova Agents",
    description: "Assign tasks to specialized Nova models working in parallel — like your own AI team.",
    href: "/agents",
    icon: Network,
    gradient: "from-emerald-500/20 via-green-500/10 to-transparent",
    border: "border-emerald-500/30 hover:border-emerald-400/60",
    iconColor: "text-emerald-400",
    glow: "shadow-[0_0_40px_oklch(0.80_0.14_160_/_0.15)]",
    badge: "New",
  },
  {
    key: "debate",
    label: "Nova Debate",
    description: "Watch two AI models argue opposing sides of any topic. Moderated, scored, and insightful.",
    href: "/debate",
    icon: Scale,
    gradient: "from-orange-500/20 via-amber-500/10 to-transparent",
    border: "border-orange-500/30 hover:border-orange-400/60",
    iconColor: "text-orange-400",
    glow: "shadow-[0_0_40px_oklch(0.80_0.16_60_/_0.15)]",
    badge: "New",
  },
  {
    key: "ide",
    label: "Nova IDE",
    description: "AI-powered code editor. Write, debug, and ship code with Nova models as your co-pilot.",
    href: "/ide",
    icon: Code2,
    gradient: "from-indigo-500/20 via-blue-500/10 to-transparent",
    border: "border-indigo-500/30 hover:border-indigo-400/60",
    iconColor: "text-indigo-400",
    glow: "shadow-[0_0_40px_oklch(0.60_0.18_250_/_0.15)]",
    badge: "New",
  },
]

export default function HomePage() {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [showMenu, setShowMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(async r => {
        if (!r.ok) {
          // Token is invalid/expired — clear the cookie then go to login.
          // Without calling logout first the proxy would see the stale cookie
          // and redirect /login → /home, creating an infinite loop.
          await fetch("/api/auth/logout", { method: "POST" }).catch(() => {})
          router.replace("/login")
          return null
        }
        return r.json()
      })
      .then(data => {
        if (data?.display_name) {
          setUser({ display_name: data.display_name, avatar_color: data.avatar_color || "#0ea5e9" })
        }
      })
      .catch(async () => {
        await fetch("/api/auth/logout", { method: "POST" }).catch(() => {})
        router.replace("/login")
      })
  }, [router])

  // Close dropdown on outside click
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

  return (
    <div className="min-h-screen aurora-bg relative overflow-hidden">
      {/* Ambient blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl" />
        <div className="absolute top-1/3 -right-32 w-80 h-80 rounded-full bg-violet-500/10 blur-3xl" />
        <div className="absolute bottom-0 left-1/3 w-72 h-72 rounded-full bg-cyan-500/8 blur-3xl" />
      </div>

      {/* Top bar */}
      <header className="relative z-10 flex items-center justify-between px-6 py-5 max-w-7xl mx-auto">
        <div className="flex items-center gap-2.5">
          <NovaIcon size={32} />
          <span className="font-bold text-lg tracking-tight">Nova</span>
        </div>

        <div className="flex items-center gap-3">
          {/* Profile avatar with dropdown */}
          {user && (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setShowMenu(prev => !prev)}
                className={cn(
                  "w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold",
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
                  {/* User info header */}
                  <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-muted/30">
                    <div
                      className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
                      style={{ backgroundColor: user.avatar_color }}
                    >
                      {user.display_name[0].toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">{user.display_name}</p>
                      <p className="text-xs text-muted-foreground">Nova account</p>
                    </div>
                  </div>

                  {/* Menu items */}
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

      {/* Hero */}
      <section className="relative z-10 text-center px-6 pt-10 pb-14 max-w-3xl mx-auto">
        <p className="text-sm text-muted-foreground mb-2">
          {greeting()}{user ? `, ${user.display_name}` : ""}
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
          What would you like to{" "}
          <span className="bg-gradient-to-r from-blue-400 via-cyan-400 to-violet-400 bg-clip-text text-transparent">
            create today?
          </span>
        </h1>
        <p className="text-muted-foreground text-base max-w-xl mx-auto">
          Choose an experience below — from intelligent conversation to AI-hosted podcasts and debates.
        </p>
      </section>

      {/* Feature grid */}
      <main className="relative z-10 max-w-6xl mx-auto px-6 pb-24">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map(f => {
            const Icon = f.icon
            return (
              <Link
                key={f.key}
                href={f.href}
                className={cn(
                  "group relative flex flex-col gap-4 p-6 rounded-2xl border transition-all duration-300",
                  "bg-card/50 backdrop-blur-sm",
                  f.border,
                  f.glow,
                  "hover:-translate-y-1 hover:bg-card/70"
                )}
              >
                <div className={cn("absolute inset-0 rounded-2xl bg-gradient-to-br opacity-40 group-hover:opacity-60 transition-opacity", f.gradient)} />

                <div className="relative flex items-start justify-between">
                  <div className={cn(
                    "w-11 h-11 rounded-xl flex items-center justify-center",
                    "bg-background/60 border border-border/50 backdrop-blur-sm"
                  )}>
                    <Icon className={cn("w-5 h-5", f.iconColor)} />
                  </div>
                  {f.badge && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-primary/20 text-primary border border-primary/30">
                      {f.badge}
                    </span>
                  )}
                </div>

                <div className="relative flex-1">
                  <h2 className="text-base font-semibold text-foreground mb-1.5">{f.label}</h2>
                  <p className="text-sm text-muted-foreground leading-relaxed">{f.description}</p>
                </div>

                <div className={cn(
                  "relative flex items-center gap-1 text-xs font-medium transition-colors",
                  f.iconColor,
                  "opacity-60 group-hover:opacity-100"
                )}>
                  <span>Open</span>
                  <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                </div>
              </Link>
            )
          })}
        </div>
      </main>

      {/* Bottom status bar */}
      <footer className="fixed bottom-0 left-0 right-0 z-10 px-6 py-3 border-t border-border/40 bg-background/60 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          {user && (
            <div className="flex items-center gap-2.5">
              <div
                className="w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0"
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
