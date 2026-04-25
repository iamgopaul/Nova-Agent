"use client"

import { useEffect, useState } from "react"
import { AlertTriangle, Cog, Cpu, LogOut, User, X } from "lucide-react"
import { ProfilePanel } from "@/components/chat/profile-panel"
import { cn } from "@/lib/utils"

type Tab = "account" | "identity" | "models"

type ModelRole = {
  role: string
  label: string
  configured: string
  effective: string
  ram_gb: number
  downgraded: boolean
}

type ModelRouting = {
  ram_gb: number
  installed_count: number
  installed_models: string[]
  roles: ModelRole[]
  constraints_applied: number
  log: string[]
}

interface SettingsPanelProps {
  onClose: () => void
}

export function SettingsPanel({ onClose }: SettingsPanelProps) {
  const [tab, setTab] = useState<Tab>("account")
  const [user, setUser] = useState<{ display_name: string; avatar_color: string } | null>(null)
  const [modelRouting, setModelRouting] = useState<ModelRouting | null>(null)

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

  useEffect(() => {
    if (tab !== "models") return
    fetch("/api/stats/models")
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setModelRouting(data as ModelRouting) })
      .catch(() => {})
  }, [tab])

  const handleSignOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" })
    window.location.href = "/login"
  }

  if (tab === "identity") {
    return <ProfilePanel onClose={onClose} />
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg bg-background border border-border rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Cog className="w-5 h-5 text-primary" />
            <span className="font-semibold text-sm">Settings</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border shrink-0">
          {(["account", "models", "identity"] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex-1 px-3 py-2.5 text-xs font-medium transition-colors capitalize",
                tab === t
                  ? "text-foreground border-b-2 border-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t === "identity" ? "Identity" : t === "models" ? "Models" : "Account"}
            </button>
          ))}
        </div>

        {/* ── Account tab ── */}
        {tab === "account" && (
          <div className="p-5 space-y-5 overflow-y-auto">
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
              <button
                onClick={() => setTab("models")}
                className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-muted transition-colors"
              >
                <div className="flex items-center gap-2.5">
                  <Cpu className="w-4 h-4 text-muted-foreground" />
                  <span>Model routing</span>
                </div>
                <span className="text-xs text-muted-foreground">›</span>
              </button>
            </div>
            <button
              onClick={handleSignOut}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-destructive/30 text-destructive text-sm font-medium hover:bg-destructive/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Sign out
            </button>
          </div>
        )}

        {/* ── Models tab ── */}
        {tab === "models" && (
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {!modelRouting ? (
              <p className="text-xs text-muted-foreground">Loading model info…</p>
            ) : (
              <>
                {/* System summary */}
                <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/20 px-4 py-3">
                  <Cpu className="w-4 h-4 text-primary shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">{modelRouting.ram_gb} GB RAM detected</p>
                    <p className="text-xs text-muted-foreground">
                      {modelRouting.installed_count} model{modelRouting.installed_count !== 1 ? "s" : ""} installed in Ollama
                      {modelRouting.constraints_applied > 0 && (
                        <span className="text-amber-400 ml-2">· {modelRouting.constraints_applied} downgraded to fit RAM</span>
                      )}
                    </p>
                  </div>
                </div>

                {modelRouting.constraints_applied > 0 && (
                  <div className="flex items-start gap-2 rounded-xl border border-amber-500/20 bg-amber-500/[0.07] px-3 py-2.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-300/80 leading-relaxed">
                      Some models were automatically downgraded because they require more RAM than your system has.
                      To use a heavier model, run <code className="bg-black/20 px-1 rounded">ollama pull &lt;model&gt;</code> after upgrading RAM.
                    </p>
                  </div>
                )}

                {/* Role table */}
                <div className="rounded-xl border border-border overflow-hidden">
                  <div className="grid grid-cols-[1fr_1fr_auto] gap-0 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/60 px-3 py-2 border-b border-border bg-muted/20">
                    <span>Role</span>
                    <span>Active model</span>
                    <span>RAM</span>
                  </div>
                  <div className="divide-y divide-border/50 max-h-72 overflow-y-auto">
                    {modelRouting.roles.map(r => (
                      <div
                        key={r.role}
                        className={cn(
                          "grid grid-cols-[1fr_1fr_auto] gap-2 items-center px-3 py-2.5 text-xs",
                          r.downgraded && "bg-amber-500/[0.04]"
                        )}
                      >
                        <div>
                          <span className="text-foreground/80 font-medium">{r.label}</span>
                          {r.downgraded && (
                            <span className="block text-[10px] text-muted-foreground/50 mt-0.5 line-through">{r.configured}</span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5 min-w-0">
                          {r.downgraded && <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />}
                          <span className={cn("truncate font-mono", r.downgraded ? "text-amber-400" : "text-foreground/70")}>
                            {r.effective}
                          </span>
                        </div>
                        <span className="text-muted-foreground/50 text-[10px] shrink-0 tabular-nums">
                          ~{r.ram_gb}GB
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
