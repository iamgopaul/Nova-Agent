"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { ChevronUp, Cog, LogOut, UserCircle } from "lucide-react"
import { cn } from "@/lib/utils"

interface UserInfo {
  display_name: string
  avatar_color: string
}

interface AppFooterProps {
  className?: string
  fixed?: boolean
}

export function AppFooter({ className, fixed = true }: AppFooterProps) {
  const router = useRouter()
  const [user, setUser] = useState<UserInfo | null>(null)
  const [showMenu, setShowMenu] = useState(false)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.display_name) {
          setUser({ display_name: d.display_name, avatar_color: d.avatar_color || "#0ea5e9" })
        }
      })
      .catch(() => {})
  }, [])

  const handleSignOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" })
    router.push("/signout")
  }

  return (
    <footer
      className={cn(
        fixed ? "fixed bottom-0 left-0 right-0 z-50" : "shrink-0",
        "border-t border-white/[0.07] backdrop-blur-md px-5 py-2",
        className
      )}
      style={{ backgroundColor: "var(--surface-2)" }}
    >
      <div className="flex items-center justify-between gap-4">

        {/* ── Profile ─────────────────────────────────────────────── */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(prev => !prev)}
            className="flex items-center gap-2.5 px-2 py-1 rounded-lg hover:bg-white/[0.06] transition-colors group"
          >
            {user ? (
              <>
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0 ring-1 ring-white/10 group-hover:ring-white/25 transition-all"
                  style={{ backgroundColor: user.avatar_color }}
                >
                  {user.display_name[0].toUpperCase()}
                </div>
                <span className="text-xs font-medium text-white/60 group-hover:text-white/90 transition-colors max-w-[120px] truncate">
                  {user.display_name}
                </span>
                <ChevronUp
                  className={cn(
                    "w-3 h-3 text-white/30 transition-transform",
                    showMenu && "rotate-180"
                  )}
                />
              </>
            ) : (
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-full bg-white/10 animate-pulse" />
                <div className="w-20 h-3 rounded bg-white/10 animate-pulse" />
              </div>
            )}
          </button>

          {/* Dropdown */}
          {showMenu && user && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
              <div
                className="absolute bottom-full left-0 mb-2 w-52 rounded-2xl border border-white/[0.09] shadow-2xl overflow-hidden z-20"
                style={{ backgroundColor: "var(--surface-3)" }}
              >
                {/* User card */}
                <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/[0.07] bg-white/[0.02]">
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-bold shrink-0"
                    style={{ backgroundColor: user.avatar_color }}
                  >
                    {user.display_name[0].toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white/85 truncate">{user.display_name}</p>
                    <p className="text-[10px] text-white/30">GAAIA Account</p>
                  </div>
                </div>
                {/* Actions */}
                <div className="p-1.5 space-y-0.5">
                  <Link
                    href="/settings"
                    onClick={() => setShowMenu(false)}
                    className="flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-white/55 hover:text-white hover:bg-white/[0.07] transition-colors"
                  >
                    <Cog className="w-4 h-4" />
                    Settings
                  </Link>
                  <Link
                    href="/settings?tab=profile"
                    onClick={() => setShowMenu(false)}
                    className="flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-white/55 hover:text-white hover:bg-white/[0.07] transition-colors"
                  >
                    <UserCircle className="w-4 h-4" />
                    Edit profile
                  </Link>
                  <div className="my-1 border-t border-white/[0.06]" />
                  <button
                    onClick={() => void handleSignOut()}
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-red-400/80 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    <LogOut className="w-4 h-4" />
                    Sign out
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* ── Settings shortcut ────────────────────────────────────── */}
        <Link
          href="/settings"
          className="flex items-center gap-1.5 text-xs text-white/30 hover:text-white/65 transition-colors"
        >
          <Cog className="w-3.5 h-3.5" />
          Settings
        </Link>
      </div>
    </footer>
  )
}
