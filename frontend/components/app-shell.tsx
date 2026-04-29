"use client"

import Link from "next/link"
import type { ReactNode } from "react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { AppFooter } from "@/components/app-footer"
import { StatsBar } from "@/components/chat/stats-bar"
import { cn } from "@/lib/utils"

interface AppShellProps {
  /** Page name — rendered as "GAAIA [title]" in the top bar */
  title: string
  /**
   * Tailwind text-color class for the title accent.
   * e.g. "text-blue-400" for GAAIA Chat, "text-cyan-400" for GAAIA Voice.
   */
  titleColor?: string
  /** Slot for page-specific controls on the right side of the top bar */
  headerActions?: ReactNode
  /** Set true while a model is streaming */
  isStreaming?: boolean
  children: ReactNode
}

/**
 * Consistent frame used by every app page.
 *
 *  ┌── border ──────────────────────────────────────────┐
 *  │  top bar:  [GAAIA / Title]          [headerActions] │
 *  ├────────────────────────────────────────────────────┤
 *  │  stats bar (collapsible)                           │
 *  ├────────────────────────────────────────────────────┤
 *  │                                                    │
 *  │   {children}                                       │
 *  │                                                    │
 *  ├────────────────────────────────────────────────────┤
 *  │  footer bar                                        │
 *  └────────────────────────────────────────────────────┘
 */
export function AppShell({ title, titleColor, headerActions, isStreaming = false, children }: AppShellProps) {
  return (
    <div
      // h-[100dvh] / dvh dynamic viewport units avoid the mobile-Safari URL-bar
      // bug where 100vh exceeds the visible area when the bar is showing.
      // pb-[env(safe-area-inset-bottom)] keeps content above iPhone home bar.
      className="h-[100dvh] flex flex-col border border-white/[0.06] overflow-hidden"
      style={{ backgroundColor: "var(--surface-1)" }}
    >
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header
        className="flex items-center justify-between px-3 sm:px-5 h-11 shrink-0 border-b border-white/[0.07]"
        style={{
          backgroundColor: "var(--surface-2)",
          paddingTop: "env(safe-area-inset-top)",
        }}
      >
        <Link
          href="/home"
          className="flex items-center gap-2 hover:opacity-75 transition-opacity"
          title="Back to hub"
        >
          <GaaiaIcon size={20} />
          <span className="text-sm font-bold tracking-wide text-white/50">
            GAAIA
            <span className={cn("ml-1.5", titleColor ?? "text-white/80")}>{title}</span>
          </span>
        </Link>

        {headerActions && (
          <div className="flex items-center gap-2">
            {headerActions}
          </div>
        )}
      </header>

      {/* ── Stats bar ───────────────────────────────────────────────── */}
      <StatsBar isStreaming={isStreaming} />

      {/* ── Page content ────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {children}
      </div>

      {/* ── Footer bar ──────────────────────────────────────────────── */}
      <AppFooter fixed={false} />
    </div>
  )
}
