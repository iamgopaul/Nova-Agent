"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { AppShell } from "@/components/app-shell"
import {
  CheckCircle,
  Crown,
  FileText,
  Loader2,
  MessageSquare,
  RefreshCw,
  ShieldCheck,
  ShieldOff,
  Users,
} from "lucide-react"
import { cn } from "@/lib/utils"

type AdminTab = "overview" | "users" | "audit"

interface Stats {
  total_users: number
  pro_users: number
  total_sessions: number
  total_messages: number
  total_files: number
}

interface AdminUser {
  id: string
  email: string
  display_name: string
  avatar_color: string
  is_admin: boolean
  subscription_tier: string
  totp_enabled: boolean
  created_at: string
}

interface AuditLog {
  id: string
  user_id: string | null
  action: string
  ip_address: string | null
  resource: string | null
  created_at: string
}

const ACTION_COLORS: Record<string, string> = {
  login:             "text-emerald-400 border-emerald-400/20 bg-emerald-500/10",
  login_2fa:         "text-emerald-400 border-emerald-400/20 bg-emerald-500/10",
  login_2fa_challenge:"text-blue-400 border-blue-400/20 bg-blue-500/10",
  login_failed:      "text-red-400 border-red-400/20 bg-red-500/10",
  "2fa_enabled":     "text-indigo-400 border-indigo-400/20 bg-indigo-500/10",
  "2fa_disabled":    "text-amber-400 border-amber-400/20 bg-amber-500/10",
  "2fa_failed":      "text-red-400 border-red-400/20 bg-red-500/10",
  register:          "text-cyan-400 border-cyan-400/20 bg-cyan-500/10",
}

function formatTs(iso: string): string {
  return new Date(iso).toLocaleString()
}

function AdminPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = (searchParams.get("tab") as AdminTab | null) ?? "overview"

  const [activeTab, setActiveTab] = useState<AdminTab>(initialTab)
  const [stats, setStats] = useState<Stats | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [audit, setAudit] = useState<AuditLog[]>([])
  const [loadingStats, setLoadingStats] = useState(true)
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [adminToggles, setAdminToggles] = useState<Record<string, boolean>>({})

  useEffect(() => {
    fetch("/api/admin/stats")
      .then(r => {
        if (r.status === 403) { router.replace("/home"); return null }
        return r.ok ? r.json() as Promise<Stats> : null
      })
      .then(d => { if (d) setStats(d) })
      .catch(() => {})
      .finally(() => setLoadingStats(false))
  }, [router])

  const fetchUsers = useCallback(async () => {
    setLoadingUsers(true)
    try {
      const r = await fetch("/api/admin/users")
      if (r.ok) setUsers(await r.json() as AdminUser[])
    } catch { /* ignore */ }
    finally { setLoadingUsers(false) }
  }, [])

  const fetchAudit = useCallback(async () => {
    setLoadingAudit(true)
    try {
      const r = await fetch("/api/admin/audit?limit=100")
      if (r.ok) setAudit(await r.json() as AuditLog[])
    } catch { /* ignore */ }
    finally { setLoadingAudit(false) }
  }, [])

  useEffect(() => {
    if (activeTab === "users" && users.length === 0) void fetchUsers()
    if (activeTab === "audit" && audit.length === 0) void fetchAudit()
  }, [activeTab, users.length, audit.length, fetchUsers, fetchAudit])

  const toggleAdmin = async (userId: string, current: boolean) => {
    setAdminToggles(p => ({ ...p, [userId]: true }))
    try {
      const r = await fetch(`/api/admin/users/${userId}/admin?is_admin=${!current}`, { method: "PATCH" })
      if (r.ok) setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_admin: !current } : u))
    } catch { /* ignore */ }
    finally { setAdminToggles(p => ({ ...p, [userId]: false })) }
  }

  const TABS: { id: AdminTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "users",    label: "Users"    },
    { id: "audit",    label: "Audit Log"},
  ]

  return (
    <AppShell title="Admin">
      <div className="flex h-full overflow-hidden">
        {/* Sidebar */}
        <aside className="w-48 shrink-0 border-r border-white/[0.07] px-3 py-5 space-y-1 bg-[#0d0d12]">
          <div className="px-3 py-2 mb-3">
            <p className="text-xs font-bold uppercase tracking-wider text-white/30">Admin Panel</p>
          </div>
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id)
                router.replace(`/admin?tab=${tab.id}`, { scroll: false })
              }}
              className={cn(
                "w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium transition-all text-left",
                activeTab === tab.id
                  ? "bg-indigo-600/20 text-white border border-indigo-500/20"
                  : "text-white/35 hover:text-white/70 hover:bg-white/[0.05] border border-transparent"
              )}
            >
              {tab.label}
            </button>
          ))}
        </aside>

        {/* Main */}
        <main className="flex-1 overflow-y-auto px-8 py-7 bg-[#0a0a10]">
          {activeTab === "overview" && (
            <OverviewTab stats={stats} loading={loadingStats} />
          )}
          {activeTab === "users" && (
            <UsersTab
              users={users}
              loading={loadingUsers}
              adminToggles={adminToggles}
              onToggleAdmin={toggleAdmin}
              onRefresh={fetchUsers}
            />
          )}
          {activeTab === "audit" && (
            <AuditTab
              logs={audit}
              loading={loadingAudit}
              onRefresh={fetchAudit}
            />
          )}
        </main>
      </div>
    </AppShell>
  )
}

function OverviewTab({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground py-16 justify-center">
        <Loader2 className="w-5 h-5 animate-spin" /> Loading…
      </div>
    )
  }

  const CARDS = [
    { label: "Total users",    value: stats?.total_users ?? 0,    icon: Users,         color: "text-cyan-400"    },
    { label: "Pro users",      value: stats?.pro_users ?? 0,      icon: Crown,         color: "text-indigo-400"  },
    { label: "Conversations",  value: stats?.total_sessions ?? 0, icon: MessageSquare, color: "text-violet-400"  },
    { label: "Messages",       value: stats?.total_messages ?? 0, icon: MessageSquare, color: "text-emerald-400" },
    { label: "Uploaded files", value: stats?.total_files ?? 0,    icon: FileText,      color: "text-amber-400"   },
  ]

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h2 className="text-lg font-semibold">Overview</h2>
        <p className="text-sm text-muted-foreground mt-1">System-wide statistics at a glance.</p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        {CARDS.map(card => {
          const Icon = card.icon
          return (
            <div key={card.label} className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-5 py-4 space-y-2">
              <div className="flex items-center gap-2">
                <Icon className={cn("w-4 h-4", card.color)} />
                <span className="text-xs text-muted-foreground">{card.label}</span>
              </div>
              <p className="text-2xl font-bold">{card.value.toLocaleString()}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function UsersTab({
  users,
  loading,
  adminToggles,
  onToggleAdmin,
  onRefresh,
}: {
  users: AdminUser[]
  loading: boolean
  adminToggles: Record<string, boolean>
  onToggleAdmin: (id: string, current: boolean) => void
  onRefresh: () => void
}) {
  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Users</h2>
          <p className="text-sm text-muted-foreground mt-1">All registered accounts. Toggle admin access below.</p>
        </div>
        <button
          onClick={onRefresh}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground py-10 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading users…
        </div>
      ) : (
        <div className="rounded-xl border border-white/[0.07] overflow-hidden">
          <div className="grid grid-cols-[auto_1fr_auto_auto_auto] gap-0 text-[10px] font-bold uppercase tracking-wider text-white/30 px-4 py-2.5 bg-white/[0.03] border-b border-white/[0.07]">
            <span className="w-8" />
            <span>User</span>
            <span className="w-24 text-center">Plan</span>
            <span className="w-16 text-center">2FA</span>
            <span className="w-20 text-center">Admin</span>
          </div>

          <ul className="divide-y divide-white/[0.04]">
            {users.map(user => (
              <li key={user.id} className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-0 px-4 py-3 hover:bg-white/[0.02] transition-colors">
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold mr-3 shrink-0"
                  style={{ backgroundColor: user.avatar_color }}
                >
                  {(user.display_name || "?")[0].toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{user.display_name}</p>
                  <p className="text-xs text-muted-foreground truncate">{user.email}</p>
                </div>
                <div className="w-24 flex justify-center">
                  <span className={cn(
                    "text-[10px] px-2 py-0.5 rounded-full border font-medium",
                    user.subscription_tier === "pro"
                      ? "border-indigo-400/30 bg-indigo-500/10 text-indigo-400"
                      : user.subscription_tier === "teams"
                        ? "border-violet-400/30 bg-violet-500/10 text-violet-400"
                        : "border-white/10 text-white/30"
                  )}>
                    {user.subscription_tier || "free"}
                  </span>
                </div>
                <div className="w-16 flex justify-center">
                  {user.totp_enabled ? (
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  ) : (
                    <ShieldOff className="w-4 h-4 text-white/20" />
                  )}
                </div>
                <div className="w-20 flex justify-center">
                  <button
                    onClick={() => onToggleAdmin(user.id, user.is_admin)}
                    disabled={adminToggles[user.id]}
                    className={cn(
                      "flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg border transition-all disabled:opacity-50",
                      user.is_admin
                        ? "border-amber-400/30 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                        : "border-white/[0.08] text-white/30 hover:text-white/60 hover:bg-white/[0.05]"
                    )}
                  >
                    {adminToggles[user.id] ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <CheckCircle className="w-3 h-3" />
                    )}
                    {user.is_admin ? "Admin" : "User"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function AuditTab({
  logs,
  loading,
  onRefresh,
}: {
  logs: AuditLog[]
  loading: boolean
  onRefresh: () => void
}) {
  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Audit Log</h2>
          <p className="text-sm text-muted-foreground mt-1">Last 100 security-sensitive events across all users.</p>
        </div>
        <button
          onClick={onRefresh}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground py-10 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading logs…
        </div>
      ) : logs.length === 0 ? (
        <div className="text-center py-10 text-sm text-muted-foreground">No audit logs yet.</div>
      ) : (
        <div className="rounded-xl border border-white/[0.07] overflow-hidden divide-y divide-white/[0.04]">
          {logs.map(log => (
            <div key={log.id} className="flex items-center gap-4 px-4 py-3 hover:bg-white/[0.02] transition-colors">
              <span className={cn(
                "text-[10px] px-2 py-0.5 rounded-full border font-medium shrink-0",
                ACTION_COLORS[log.action] ?? "border-white/10 text-white/30"
              )}>
                {log.action}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-xs text-muted-foreground font-mono truncate">
                  {log.user_id ?? "anonymous"}
                </p>
                {log.ip_address && (
                  <p className="text-[10px] text-white/20 font-mono">{log.ip_address}</p>
                )}
              </div>
              <span className="text-[10px] text-white/25 shrink-0">{formatTs(log.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AdminPage() {
  return (
    <Suspense>
      <AdminPageContent />
    </Suspense>
  )
}
