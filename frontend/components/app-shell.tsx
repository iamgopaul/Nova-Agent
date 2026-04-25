"use client"

import Link from "next/link"
import type { ReactNode } from "react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { AppFooter } from "@/components/app-footer"
import { StatsBar } from "@/components/chat/stats-bar"
import { cn } from "@/lib/utils"

interface AppShellProps {
  /** Page name — rendered as "Nova [title]" in the top bar, e.g. "Nova Chat" */
  title: string
  /**
   * Tailwind text-color class applied to the page title portion of the header.
   * Defaults to neutral white/80. Pass e.g. "text-blue-400" for Nova Chat
   * or "text-cyan-400" for Nova Voice to match the home-page card accent.
   */
  titleColor?: string
  /** Slot for page-specific controls on the right side of the top bar */
  headerActions?: ReactNode
  /** Passed through to StatsBar — set true while a model is streaming */
  isStreaming?: boolean
  children: ReactNode
}

/**
 * Consistent bordered frame used by every app page (chat, voice, podcast, …).
 *
 * Layout:
 *  ┌── border ──────────────────────────────────────────┐
 *  │  top bar:  [Nova / Title]          [headerActions] │
 *  ├────────────────────────────────────────────────────┤
 *  │  stats bar (collapsible)                           │
 *  ├────────────────────────────────────────────────────┤
 *  │                                                    │
 *  │   {children}                                       │
 *  │                                                    │
 *  ├────────────────────────────────────────────────────┤
 *  │  footer:  [avatar · name]           [Settings ⚙]  │
 *  └── border ──────────────────────────────────────────┘
 */
export function AppShell({ title, titleColor, headerActions, isStreaming = false, children }: AppShellProps) {
  return (
    <div className="h-screen flex flex-col bg-[#0a0a10] border border-white/[0.07] overflow-hidden">

      {/* ── Top bar ───────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-5 h-11 shrink-0 border-b border-white/[0.07] bg-[#0d0d12]">
        <Link
          href="/home"
          className="flex items-center gap-2 hover:opacity-75 transition-opacity"
          title="Go to Home"
        >
          <NovaIcon size={20} />
          <span className={cn("text-sm font-bold tracking-wide", titleColor ?? "text-white/80")}>
            Nova{" "}
            <span className={titleColor ?? "text-white/80"}>{title}</span>
          </span>
        </Link>

        {headerActions && (
          <div className="flex items-center gap-2">
            {headerActions}
          </div>
        )}
      </header>

      {/* ── Stats bar ─────────────────────────────────────────────────── */}
      <StatsBar isStreaming={isStreaming} />

      {/* ── Page content ──────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {children}
      </div>

      {/* ── Footer bar ────────────────────────────────────────────────── */}
      <AppFooter fixed={false} />

    </div>
  )
}
