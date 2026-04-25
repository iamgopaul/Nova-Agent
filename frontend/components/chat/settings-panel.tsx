"use client"

import { useEffect, useState } from "react"
import { Cog, LogOut, User, X } from "lucide-react"
import { ProfilePanel } from "@/components/chat/profile-panel"
import { cn } from "@/lib/utils"

type Tab = "account" | "identity"

interface SettingsPanelProps {
  onClose: () => void
}

export function SettingsPanel({ onClose }: SettingsPanelProps) {
  const [tab, setTab] = useState<Tab>("account")
  const [user, setUser] = useState<{ display_name: string; avatar_color: string } | null>(null)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.display_name) {
          setUser({ display_name: data.display_name, avatar_color: data.avatar_color || "#0ea5e9" })
        }
      })
      .catch(() => {})
  }, [])

  const handleSignOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" })
    window.location.href = "/login"
  }

  if (tab === "identity") {
    return (
      <ProfilePanel
        onClose={onClose}
      />
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-background border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Cog className="w-5 h-5 text-primary" />
            <span className="font-semibold text-sm">Settings</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-muted transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          <button
            onClick={() => setTab("account")}
            className={cn(
              "flex-1 px-4 py-2.5 text-xs font-medium transition-colors",
              tab === "account"
                ? "text-foreground border-b-2 border-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            Account
          </button>
          <button
            onClick={() => setTab("identity")}
            className={cn(
              "flex-1 px-4 py-2.5 text-xs font-medium transition-colors",
              tab === "identity"
                ? "text-foreground border-b-2 border-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            Identity & Recognition
          </button>
        </div>

        {/* Account tab body */}
        <div className="p-5 space-y-5">
          {/* Avatar + name */}
          <div className="flex items-center gap-4">
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center text-white text-xl font-bold shrink-0 shadow-lg"
              style={{ backgroundColor: user?.avatar_color ?? "#0ea5e9" }}
            >
              {(user?.display_name?.[0] ?? "U").toUpperCase()}
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">{user?.display_name ?? "Account"}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Signed in</p>
            </div>
          </div>

          {/* Profile & Identity shortcut */}
          <div className="rounded-xl border border-border bg-muted/30 divide-y divide-border overflow-hidden">
            <button
              onClick={() => setTab("identity")}
              className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-muted transition-colors"
            >
              <div className="flex items-center gap-2.5">
                <User className="w-4 h-4 text-muted-foreground" />
                <span>Identity & Recognition</span>
              </div>
              <span className="text-xs text-muted-foreground">›</span>
            </button>
          </div>

          {/* Sign out */}
          <button
            onClick={handleSignOut}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-destructive/30 text-destructive text-sm font-medium hover:bg-destructive/10 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </div>
    </div>
  )
}
