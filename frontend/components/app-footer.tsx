"use client"

import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { ChevronUp, Cog, CreditCard, LogOut, ShieldCheck, UserCircle } from "lucide-react"
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
  const buttonRef = useRef<HTMLButtonElement | null>(null)
  const [menuPos, setMenuPos] = useState<{ left: number; bottom: number } | null>(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => { setMounted(true) }, [])

  // Recompute the dropdown anchor whenever it opens or the window resizes.
  // Using `position: fixed` + portal to document.body means the dropdown
  // escapes any ancestor `overflow: hidden` / stacking-context clipping
  // (the AppShell wraps everything in `overflow-hidden`, which was hiding
  // the menu when AppFooter is rendered with `fixed={false}`).
  useLayoutEffect(() => {
    if (!showMenu) return
    const update = () => {
      const r = buttonRef.current?.getBoundingClientRect()
      if (r) setMenuPos({ left: r.left, bottom: window.innerHeight - r.top + 8 })
    }
    update()
    window.addEventListener("resize", update)
    window.addEventListener("scroll", update, true)
    return () => {
      window.removeEventListener("resize", update)
      window.removeEventListener("scroll", update, true)
    }
  }, [showMenu])

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
        "border-t border-white/[0.07] backdrop-blur-md px-3 sm:px-5 py-2",
        className
      )}
      style={{
        backgroundColor: "var(--surface-2)",
        paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))",
      }}
    >
      <div className="flex items-center justify-between gap-4">

        {/* ── Profile ─────────────────────────────────────────────── */}
        <div className="relative">
          <button
            ref={buttonRef}
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

          {/* Dropdown — rendered via portal to document.body with fixed
              positioning so the AppShell's `overflow-hidden` wrapper doesn't
              clip it when the footer is rendered with fixed={false}. */}
          {mounted && showMenu && user && createPortal(
            <>
              <div className="fixed inset-0 z-[60]" onClick={() => setShowMenu(false)} />
              <div
                className="fixed w-52 rounded-2xl border border-white/[0.09] shadow-2xl overflow-hidden z-[70]"
                style={{
                  left: menuPos?.left ?? 0,
                  bottom: menuPos?.bottom ?? 56,
                  backgroundColor: "var(--surface-3)",
                  visibility: menuPos ? "visible" : "hidden",
                }}
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
                  <Link
                    href="/settings?tab=security"
                    onClick={() => setShowMenu(false)}
                    className="flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-white/55 hover:text-white hover:bg-white/[0.07] transition-colors"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    Security &amp; 2FA
                  </Link>
                  <Link
                    href="/billing"
                    onClick={() => setShowMenu(false)}
                    className="flex items-center gap-3 px-3 py-2 rounded-xl text-sm text-white/55 hover:text-white hover:bg-white/[0.07] transition-colors"
                  >
                    <CreditCard className="w-4 h-4" />
                    Billing &amp; Plans
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
            </>,
            document.body,
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
