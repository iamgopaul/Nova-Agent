"use client"

import { Suspense, useCallback, useEffect, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  Camera,
  CheckCircle,
  Code2,
  Copy,
  Eye,
  EyeOff,
  ExternalLink,
  Globe,
  KeyRound,
  Loader2,
  Lock,
  LogOut,
  Mic,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2 as Trash2Icon,
  ToggleLeft,
  ToggleRight,
  User,
  UserCircle,
} from "lucide-react"
import { PasswordStrength } from "@/components/password-strength"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"
import { fingerSegmentDisplayLabel, mapNormBoxToDisplayPixels } from "@/lib/camera-overlay"

// ─── Types ───────────────────────────────────────────────────────────────────

type Tab = "profile" | "account" | "security" | "voice-camera" | "web-watch" | "developer"

interface UserInfo {
  display_name: string
  email: string
  avatar_color: string
  has_password: boolean
}

interface IdentitySummary {
  name: string
  has_face: boolean
  has_voice: boolean
  face_samples: number
  voice_samples: number
  total_samples: number
}

// ─── Sidebar tabs ─────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string; icon: React.ElementType; description: string }[] = [
  { id: "profile",      label: "Profile",           icon: UserCircle,  description: "Name, avatar & display preferences" },
  { id: "account",      label: "Account",           icon: KeyRound,    description: "Linked accounts & security"         },
  { id: "security",     label: "Security",          icon: ShieldCheck, description: "Two-factor authentication & sessions"},
  { id: "voice-camera", label: "Voice & Camera",    icon: Mic,         description: "Enrollment & recognition setup"     },
  { id: "web-watch",    label: "Web Watch",         icon: Globe,       description: "Topics GAAIA actively monitors"     },
  { id: "developer",    label: "Developer",         icon: Code2,       description: "API endpoints & configuration"      },
]

const AVATAR_COLORS = [
  "#38bdf8", "#818cf8", "#34d399", "#fb923c",
  "#f472b6", "#facc15", "#a78bfa", "#f87171",
  "#22d3ee", "#4ade80", "#e879f9", "#f97316",
]

// ─── Profile Tab ──────────────────────────────────────────────────────────────

function ProfileTab({ user, onUserChange }: { user: UserInfo | null; onUserChange: (u: UserInfo) => void }) {
  const [displayName, setDisplayName] = useState(user?.display_name ?? "")
  const [avatarColor, setAvatarColor] = useState(user?.avatar_color ?? "#0ea5e9")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (user) {
      setDisplayName(user.display_name)
      setAvatarColor(user.avatar_color)
    }
  }, [user])

  const handleSave = async () => {
    if (!displayName.trim()) { setError("Display name cannot be empty."); return }
    setSaving(true); setError(""); setSaved(false)
    try {
      const res = await fetch("/api/auth/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName.trim(), avatar_color: avatarColor }),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})) as { detail?: string }; setError(d.detail ?? "Failed to save."); return }
      const updated = await res.json() as UserInfo
      onUserChange(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch { setError("Network error.") }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-8 max-w-lg">
      <div>
        <h2 className="text-lg font-semibold">Profile</h2>
        <p className="text-sm text-muted-foreground mt-1">Manage how you appear across GAAIA.</p>
      </div>

      {/* Avatar preview + color picker */}
      <section className="space-y-4">
        <div className="flex items-center gap-5">
          <div
            className="w-20 h-20 rounded-2xl flex items-center justify-center text-white text-3xl font-bold shadow-lg ring-4 ring-border"
            style={{ backgroundColor: avatarColor }}
          >
            {(displayName || "U")[0].toUpperCase()}
          </div>
          <div>
            <p className="text-sm font-medium text-foreground mb-2">Avatar color</p>
            <div className="flex flex-wrap gap-2">
              {AVATAR_COLORS.map(c => (
                <button
                  key={c}
                  onClick={() => setAvatarColor(c)}
                  className={cn(
                    "w-7 h-7 rounded-full transition-all",
                    avatarColor === c ? "ring-2 ring-offset-2 ring-offset-background ring-white scale-110" : "hover:scale-110"
                  )}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Display name */}
      <section className="space-y-3">
        <label className="block text-sm font-medium">Display name</label>
        <input
          type="text"
          value={displayName}
          onChange={e => setDisplayName(e.target.value)}
          className="w-full px-4 py-2.5 rounded-xl border border-border bg-input text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          placeholder="Your name"
        />
      </section>

      {/* Email (read-only) */}
      {user?.email && (
        <section className="space-y-3">
          <label className="block text-sm font-medium">Email</label>
          <div className="w-full px-4 py-2.5 rounded-xl border border-border bg-muted/30 text-sm text-muted-foreground select-all">
            {user.email}
          </div>
        </section>
      )}

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle className="w-4 h-4" /> : null}
        {saving ? "Saving…" : saved ? "Saved!" : "Save changes"}
      </button>
    </div>
  )
}

// ─── Account Tab ──────────────────────────────────────────────────────────────

function PasswordInput({
  value, onChange, placeholder, id,
}: { value: string; onChange: (v: string) => void; placeholder: string; id: string }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        id={id}
        type={show ? "text" : "password"}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="new-password"
        className="w-full px-4 py-2.5 pr-10 rounded-xl border border-border bg-input text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
      <button
        type="button"
        onClick={() => setShow(s => !s)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
      >
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  )
}

function AccountTab({ user, onUserChange }: { user: UserInfo | null; onUserChange: (u: UserInfo) => void }) {
  const router = useRouter()
  const [linkedProviders, setLinkedProviders] = useState({ google: false, github: false })

  // Username state
  const [displayName, setDisplayName] = useState(user?.display_name ?? "")
  const [savingName, setSavingName] = useState(false)
  const [savedName, setSavedName] = useState(false)
  const [nameError, setNameError] = useState("")

  // Password state
  const [currentPw, setCurrentPw] = useState("")
  const [newPw, setNewPw] = useState("")
  const [confirmPw, setConfirmPw] = useState("")
  const [savingPw, setSavingPw] = useState(false)
  const [savedPw, setSavedPw] = useState(false)
  const [pwError, setPwError] = useState("")

  useEffect(() => {
    if (user) setDisplayName(user.display_name)
  }, [user])

  useEffect(() => {
    fetch("/api/auth/providers")
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setLinkedProviders({ google: !!d.google, github: !!d.github }) })
      .catch(() => {})
  }, [])

  const handleSaveName = async () => {
    if (!displayName.trim()) { setNameError("Username cannot be empty."); return }
    setSavingName(true); setNameError(""); setSavedName(false)
    try {
      const res = await fetch("/api/auth/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName.trim() }),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})) as { detail?: string }; setNameError(d.detail ?? "Failed to save."); return }
      const updated = await res.json() as UserInfo
      onUserChange(updated)
      setSavedName(true)
      setTimeout(() => setSavedName(false), 2500)
    } catch { setNameError("Network error.") }
    finally { setSavingName(false) }
  }

  const handleSavePassword = async () => {
    setPwError("")
    if (newPw.length < 8) { setPwError("Password must be at least 8 characters."); return }
    if (newPw !== confirmPw) { setPwError("Passwords do not match."); return }
    if (user?.has_password && !currentPw) { setPwError("Enter your current password."); return }

    setSavingPw(true); setSavedPw(false)
    try {
      const body: Record<string, string> = { new_password: newPw, confirm_password: confirmPw }
      if (user?.has_password && currentPw) body.current_password = currentPw
      const res = await fetch("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({})) as { detail?: string }
        setPwError(d.detail ?? "Failed to update password.")
        return
      }
      const updated = await res.json() as UserInfo
      onUserChange(updated)
      setSavedPw(true)
      setCurrentPw(""); setNewPw(""); setConfirmPw("")
      setTimeout(() => setSavedPw(false), 3000)
    } catch { setPwError("Network error.") }
    finally { setSavingPw(false) }
  }

  const handleSignOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" })
    router.push("/signout")
  }

  const hasPassword = user?.has_password ?? false

  return (
    <div className="space-y-10 max-w-lg">
      <div>
        <h2 className="text-lg font-semibold">Account</h2>
        <p className="text-sm text-muted-foreground mt-1">Manage your username, password, and linked sign-in providers.</p>
      </div>

      {/* ── Username ────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <User className="w-4 h-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Username</h3>
        </div>
        <p className="text-xs text-muted-foreground -mt-2">
          This is your display name across all GAAIA experiences.
        </p>

        <div className="space-y-2">
          <label className="block text-xs font-medium text-muted-foreground">Display name</label>
          <input
            type="text"
            value={displayName}
            onChange={e => setDisplayName(e.target.value)}
            placeholder="Your name"
            className="w-full px-4 py-2.5 rounded-xl border border-border bg-input text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        {nameError && <p className="text-xs text-destructive">{nameError}</p>}

        <button
          onClick={() => void handleSaveName()}
          disabled={savingName}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
        >
          {savingName ? <Loader2 className="w-4 h-4 animate-spin" /> : savedName ? <CheckCircle className="w-4 h-4" /> : null}
          {savingName ? "Saving…" : savedName ? "Saved!" : "Update username"}
        </button>
      </section>

      {/* ── Password ────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">
            {hasPassword ? "Change password" : "Set a password"}
          </h3>
          {!hasPassword && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-400/20 font-medium">
              OAuth only
            </span>
          )}
        </div>

        {!hasPassword && (
          <div className="flex items-start gap-3 rounded-xl border border-blue-400/20 bg-blue-500/5 px-4 py-3">
            <ShieldCheck className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
            <p className="text-xs text-muted-foreground leading-relaxed">
              Your account currently uses <strong className="text-foreground">Google or GitHub</strong> to sign in.
              You can create a password below to also sign in with your email and password.
              Your linked accounts will still work.
            </p>
          </div>
        )}

        <div className="space-y-3">
          {hasPassword && (
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-muted-foreground">Current password</label>
              <PasswordInput id="current-pw" value={currentPw} onChange={setCurrentPw} placeholder="Enter current password" />
            </div>
          )}
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-muted-foreground">New password</label>
            <PasswordInput id="new-pw" value={newPw} onChange={setNewPw} placeholder="Min. 8 characters" />
            <PasswordStrength password={newPw} showRules />
          </div>
          <div className="space-y-1.5">
            <label className="block text-xs font-medium text-muted-foreground">Confirm new password</label>
            <PasswordInput id="confirm-pw" value={confirmPw} onChange={setConfirmPw} placeholder="Repeat new password" />
          </div>
        </div>

        {pwError && (
          <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
            {pwError}
          </p>
        )}
        {savedPw && (
          <p className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-400/20 rounded-lg px-3 py-2 flex items-center gap-2">
            <CheckCircle className="w-3.5 h-3.5" />
            {hasPassword ? "Password changed successfully." : "Password set! You can now sign in with email & password."}
          </p>
        )}

        <button
          onClick={() => void handleSavePassword()}
          disabled={savingPw || !newPw || !confirmPw}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
        >
          {savingPw ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
          {savingPw ? "Saving…" : hasPassword ? "Change password" : "Set password"}
        </button>
      </section>

      {/* ── Linked providers ────────────────────────────────────────── */}
      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">Linked providers</h3>
        </div>
        <p className="text-xs text-muted-foreground">
          Link social accounts to sign in without a password. Multiple providers can be linked to the same account.
        </p>

        <div className="rounded-xl border border-border overflow-hidden divide-y divide-border">
          {/* Google */}
          <div className="flex items-center justify-between px-4 py-3 bg-muted/20">
            <div className="flex items-center gap-3">
              <svg width="20" height="20" viewBox="0 0 24 24">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              <div>
                <p className="text-sm">Google</p>
                {linkedProviders.google && <p className="text-[10px] text-muted-foreground">Linked to this account</p>}
              </div>
            </div>
            {linkedProviders.google ? (
              <span className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-emerald-400/30 bg-emerald-500/10 text-emerald-400">
                <CheckCircle className="w-3 h-3" /> Linked
              </span>
            ) : (
              <a
                href="/api/auth/oauth/google?link=1"
                className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
              >
                Link account
              </a>
            )}
          </div>

          {/* GitHub */}
          <div className="flex items-center justify-between px-4 py-3 bg-muted/20">
            <div className="flex items-center gap-3">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
              </svg>
              <div>
                <p className="text-sm">GitHub</p>
                {linkedProviders.github && <p className="text-[10px] text-muted-foreground">Linked to this account</p>}
              </div>
            </div>
            {linkedProviders.github ? (
              <span className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-emerald-400/30 bg-emerald-500/10 text-emerald-400">
                <CheckCircle className="w-3 h-3" /> Linked
              </span>
            ) : (
              <a
                href="/api/auth/oauth/github?link=1"
                className="text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
              >
                Link account
              </a>
            )}
          </div>
        </div>
      </section>

      {/* ── Session ──────────────────────────────────────────────────── */}
      <section className="space-y-3 pt-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Session</h3>
        <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Sign out of GAAIA</p>
            <p className="text-xs text-muted-foreground mt-0.5">You&apos;ll be redirected to the landing page.</p>
          </div>
          <button
            onClick={() => void handleSignOut()}
            className="flex items-center gap-1.5 text-sm text-destructive hover:text-destructive/80 font-medium transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </section>
    </div>
  )
}

// ─── Voice & Camera Tab ───────────────────────────────────────────────────────

function VoiceCameraTab() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const voiceRecorderRef = useRef<MediaRecorder | null>(null)
  const voiceStreamRef = useRef<MediaStream | null>(null)
  const voiceStopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const detectIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [profiles, setProfiles] = useState<IdentitySummary[]>([])
  const [cameraActive, setCameraActive] = useState(false)
  const [enrolling, setEnrolling] = useState(false)
  const [voiceEnrolling, setVoiceEnrolling] = useState(false)
  const [enrollName, setEnrollName] = useState("")
  const [status, setStatus] = useState<{ type: "success" | "error" | "info"; msg: string } | null>(null)
  const [loadingProfiles, setLoadingProfiles] = useState(true)

  type Detection = { label: string; type: string; confidence: number; box: { x: number; y: number; w: number; h: number } }

  const drawDetections = useCallback((detections: Detection[]) => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video) return
    const safeDetections = Array.isArray(detections) ? detections : []
    const rect = video.getBoundingClientRect()
    const dw = Math.max(1, rect.width || video.clientWidth || 320)
    const dh = Math.max(1, rect.height || video.clientHeight || 240)
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.round(dw * dpr); canvas.height = Math.round(dh * dpr)
    canvas.style.width = `${dw}px`; canvas.style.height = `${dh}px`
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, dw, dh)
    for (const det of safeDetections) {
      const { x, y, w, h } = mapNormBoxToDisplayPixels(det.box, video, dw, dh, false)
      const isHand = det.type === "hand" || det.type === "finger"
      ctx.strokeStyle = isHand ? "rgba(6,182,212,0.85)" : "rgba(99,102,241,0.85)"
      ctx.lineWidth = 1.5; ctx.strokeRect(x, y, w, h)
      const label = det.type === "finger" ? fingerSegmentDisplayLabel(det.label) : det.label
      const text = label ? `${label} ${Math.round(det.confidence * 100)}%` : `${Math.round(det.confidence * 100)}%`
      ctx.font = "11px sans-serif"; ctx.fillStyle = ctx.strokeStyle
      ctx.fillText(text, x + 4, y - 4 < 10 ? y + 14 : y - 4)
    }
  }, [])

  const fetchProfiles = useCallback(async () => {
    setLoadingProfiles(true)
    try {
      const r = await fetch("/api/camera/identities")
      if (r.ok) { const d = await r.json(); setProfiles(Array.isArray(d) ? d : []) }
      else { setProfiles([]) }
    } catch { setProfiles([]) }
    finally { setLoadingProfiles(false) }
  }, [])

  const deleteProfile = useCallback(async (name: string) => {
    try {
      const r = await fetch(`/api/camera/profiles/${encodeURIComponent(name)}`, { method: "DELETE" })
      if (r.ok || r.status === 204) {
        setStatus({ type: "success", msg: `Profile "${name}" deleted.` })
        void fetchProfiles()
      } else {
        const e = await r.json().catch(() => ({ detail: "Error" })) as { detail?: string }
        setStatus({ type: "error", msg: e.detail ?? "Failed to delete profile." })
      }
    } catch (e) { setStatus({ type: "error", msg: `Network error: ${String(e)}` }) }
  }, [fetchProfiles])

  const captureFrame = useCallback(async (): Promise<Blob | null> => {
    const v = videoRef.current; const c = canvasRef.current
    if (!v || !c || v.readyState < 2) return null
    const tmp = document.createElement("canvas")
    tmp.width = v.videoWidth || 640; tmp.height = v.videoHeight || 480
    tmp.getContext("2d")?.drawImage(v, 0, 0)
    return new Promise(res => tmp.toBlob(b => res(b), "image/jpeg", 0.85))
  }, [])

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false })
      streamRef.current = stream
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play() }
      setCameraActive(true)
      detectIntervalRef.current = setInterval(async () => {
        const blob = await captureFrame()
        if (!blob) return
        const fd = new FormData(); fd.append("image", blob, "frame.jpg")
        const r = await fetch("/api/camera/detect", { method: "POST", body: fd }).catch(() => null)
        if (r?.ok) { const d = await r.json(); drawDetections(d.detections ?? []) }
      }, 600)
    } catch (e) { setStatus({ type: "error", msg: `Camera error: ${String(e)}` }) }
  }, [captureFrame, drawDetections])

  const stopCamera = useCallback(() => {
    if (detectIntervalRef.current) { clearInterval(detectIntervalRef.current); detectIntervalRef.current = null }
    streamRef.current?.getTracks().forEach(t => t.stop()); streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setCameraActive(false)
    const c = canvasRef.current; if (c) c.getContext("2d")?.clearRect(0, 0, c.width, c.height)
  }, [])

  const stopVoiceEnrollment = useCallback(() => {
    if (voiceStopTimerRef.current) { clearTimeout(voiceStopTimerRef.current); voiceStopTimerRef.current = null }
    voiceRecorderRef.current?.stop(); voiceRecorderRef.current = null
    voiceStreamRef.current?.getTracks().forEach(t => t.stop()); voiceStreamRef.current = null
    setVoiceEnrolling(false)
  }, [])

  useEffect(() => { void fetchProfiles() }, [fetchProfiles])
  useEffect(() => { void startCamera(); return () => stopCamera() }, [startCamera, stopCamera])
  useEffect(() => () => stopVoiceEnrollment(), [stopVoiceEnrollment])

  const enrollFace = useCallback(async () => {
    const name = enrollName.trim()
    if (!name) { setStatus({ type: "error", msg: "Enter a name first." }); return }
    if (!cameraActive) { setStatus({ type: "error", msg: "Start the camera first." }); return }
    setEnrolling(true); setStatus({ type: "info", msg: "Capturing 8 frames — hold still…" })
    const frames: Blob[] = []
    for (let i = 0; i < 8; i++) { await new Promise(r => setTimeout(r, 350)); const b = await captureFrame(); if (b) frames.push(b) }
    if (frames.length < 3) { setStatus({ type: "error", msg: "Not enough frames. Try better lighting." }); setEnrolling(false); return }
    try {
      const form = new FormData(); form.append("name", name); frames.forEach((f, i) => form.append("images", f, `frame_${i}.jpg`))
      const r = await fetch("/api/camera/enroll", { method: "POST", body: form })
      if (r.ok) { const d = await r.json(); setStatus({ type: "success", msg: `Enrolled "${d.name}" with ${d.sample_count} face samples.` }); void fetchProfiles() }
      else { const e = await r.json().catch(() => ({ detail: "Unknown error" })); setStatus({ type: "error", msg: `Enrollment failed: ${e.detail}` }) }
    } catch (e) { setStatus({ type: "error", msg: `Network error: ${String(e)}` }) }
    finally { setEnrolling(false) }
  }, [cameraActive, captureFrame, enrollName, fetchProfiles])

  const enrollVoice = useCallback(async () => {
    const name = enrollName.trim()
    if (!name) { setStatus({ type: "error", msg: "Enter a name first." }); return }
    if (voiceEnrolling) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      voiceStreamRef.current = stream
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : ""
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      voiceRecorderRef.current = recorder; setVoiceEnrolling(true)
      const chunks: Blob[] = []
      recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data) }
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" })
        const form = new FormData(); form.append("name", name); form.append("audio", blob, "voice.webm")
        try {
          const r = await fetch("/api/voice/enroll", { method: "POST", body: form })
          if (r.ok) { setStatus({ type: "success", msg: `Voice enrolled for "${name}".` }); void fetchProfiles() }
          else { const e = await r.json().catch(() => ({ detail: "Error" })); setStatus({ type: "error", msg: `Voice enrollment failed: ${e.detail}` }) }
        } catch (e) { setStatus({ type: "error", msg: `Network error: ${String(e)}` }) }
        finally { stopVoiceEnrollment() }
      }
      recorder.start(); setStatus({ type: "info", msg: "Recording voice sample… speak naturally for ~10 seconds." })
      voiceStopTimerRef.current = setTimeout(() => recorder.state === "recording" && recorder.stop(), 10000)
    } catch (e) { voiceStreamRef.current?.getTracks().forEach(t => t.stop()); setStatus({ type: "error", msg: `Microphone error: ${String(e)}` }); setVoiceEnrolling(false) }
  }, [enrollName, fetchProfiles, stopVoiceEnrollment, voiceEnrolling])

  return (
    <div className="space-y-8 max-w-xl">
      <div>
        <h2 className="text-lg font-semibold">Voice & Camera</h2>
        <p className="text-sm text-muted-foreground mt-1">Enroll your face and voice so GAAIA can recognize you.</p>
      </div>

      {/* How-to */}
      <section className="rounded-xl border border-cyan-400/20 bg-cyan-500/5 p-4 text-sm">
        <p className="font-semibold text-cyan-300 mb-2">How to enroll</p>
        <ol className="space-y-1 text-sm text-muted-foreground list-decimal list-inside">
          <li>Allow camera & microphone access when prompted.</li>
          <li>Enter the name GAAIA should remember you by.</li>
          <li>Click <strong className="text-foreground">Enroll Face</strong> and keep your face centered.</li>
          <li>Click <strong className="text-foreground">Enroll Voice</strong> and speak naturally for ~10 s.</li>
        </ol>
      </section>

      {/* Enrolled users */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Enrolled Users</h3>
        {loadingProfiles ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="w-3 h-3 animate-spin" /> Loading…</div>
        ) : profiles.length === 0 ? (
          <p className="text-sm text-muted-foreground">No users enrolled yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {profiles.map(p => (
              <li key={p.name} className="flex items-center justify-between gap-3 bg-muted/40 rounded-xl px-4 py-2.5">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-xs font-bold text-primary">
                    {p.name[0].toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm font-medium">{p.name}</p>
                    <p className="text-xs text-muted-foreground">{p.total_samples} sample{p.total_samples !== 1 ? "s" : ""}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={cn("text-[10px] px-2 py-0.5 rounded-full border", p.has_face ? "border-cyan-400/30 text-cyan-300 bg-cyan-500/10" : "border-border text-muted-foreground")}>{p.has_face ? `Face ×${p.face_samples}` : "No face"}</span>
                  <span className={cn("text-[10px] px-2 py-0.5 rounded-full border", p.has_voice ? "border-emerald-400/30 text-emerald-300 bg-emerald-500/10" : "border-border text-muted-foreground")}>{p.has_voice ? `Voice ×${p.voice_samples}` : "No voice"}</span>
                  <button
                    onClick={() => void deleteProfile(p.name)}
                    className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                    title={`Delete ${p.name}`}
                  >
                    <Trash2Icon className="w-3.5 h-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Enrollment form */}
      <section className="space-y-4">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Enroll New User</h3>

        <input
          type="text"
          value={enrollName}
          onChange={e => setEnrollName(e.target.value)}
          placeholder="Name to remember (e.g. your first name)"
          className="w-full px-4 py-2.5 rounded-xl border border-border bg-input text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
        />

        {/* Camera preview */}
        <div className="relative bg-black rounded-xl overflow-hidden" style={{ aspectRatio: "16/9" }}>
          <div className={cn("absolute inset-0", !cameraActive && "hidden")}>
            <video ref={videoRef} muted playsInline className="absolute inset-0 z-10 w-full h-full object-cover -scale-x-100" />
            <canvas ref={canvasRef} className="absolute inset-0 z-20 w-full h-full pointer-events-none" />
          </div>
          {!cameraActive && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/50">
              <Camera className="w-10 h-10" /><span className="text-sm">Camera off</span>
            </div>
          )}
          {enrolling && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60 z-30">
              <div className="text-center text-white"><Loader2 className="w-8 h-8 animate-spin mx-auto mb-2" /><span className="text-sm">Capturing…</span></div>
            </div>
          )}
        </div>

        {status && (
          <div className={cn("text-sm px-4 py-2.5 rounded-xl", status.type === "success" && "bg-green-500/10 text-green-400", status.type === "error" && "bg-red-500/10 text-red-400", status.type === "info" && "bg-blue-500/10 text-blue-400")}>
            {status.type === "success" && <CheckCircle className="inline w-4 h-4 mr-1.5" />}{status.msg}
          </div>
        )}

        <div className="flex gap-3">
          {!cameraActive ? (
            <button onClick={() => void startCamera()} className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl border border-border hover:bg-muted text-sm font-medium transition-colors">
              <Camera className="w-4 h-4" /> Start Camera
            </button>
          ) : (
            <button onClick={stopCamera} className="px-4 py-2.5 rounded-xl border border-border hover:bg-muted text-sm transition-colors">Stop</button>
          )}
          <button
            onClick={() => void enrollFace()}
            disabled={!cameraActive || enrolling || !enrollName.trim()}
            className={cn("flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium transition-colors", cameraActive && !enrolling && enrollName.trim() ? "bg-primary text-primary-foreground hover:opacity-90" : "bg-muted text-muted-foreground opacity-50 cursor-not-allowed")}
          >
            {enrolling ? <Loader2 className="w-4 h-4 animate-spin" /> : <User className="w-4 h-4" />}{enrolling ? "Enrolling…" : "Enroll Face"}
          </button>
        </div>

        <button
          onClick={() => void enrollVoice()}
          disabled={voiceEnrolling || !enrollName.trim()}
          className={cn("w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium transition-colors", !voiceEnrolling && enrollName.trim() ? "bg-emerald-500 text-white hover:bg-emerald-500/90" : "bg-muted text-muted-foreground opacity-50 cursor-not-allowed")}
        >
          {voiceEnrolling ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mic className="w-4 h-4" />}{voiceEnrolling ? "Recording…" : "Enroll Voice"}
        </button>
      </section>
    </div>
  )
}

// ─── Web Watch Tab ────────────────────────────────────────────────────────────

interface WatchedTopic {
  id: string
  label: string
  query: string
  category: string
  enabled: boolean
  last_fetched_at: string | null
  last_result: string | null
  created_at: string
}

interface FeedItem {
  title: string
  body: string
  href: string
}

interface LastResult {
  label: string
  query: string
  fetched_at: string
  items: FeedItem[]
}

const PRESET_TOPICS: { label: string; query: string; category: string; emoji: string }[] = [
  { label: "World News",       query: "world news today",                  category: "news",        emoji: "🌍" },
  { label: "Tech & AI",        query: "artificial intelligence technology news 2026", category: "tech", emoji: "🤖" },
  { label: "Sports",           query: "sports news today highlights",      category: "sports",      emoji: "⚽" },
  { label: "Science",          query: "science discoveries research 2026", category: "science",     emoji: "🔬" },
  { label: "Finance & Markets",query: "stock market finance news today",   category: "finance",     emoji: "📈" },
  { label: "Entertainment",    query: "entertainment celebrity news today", category: "entertainment",emoji: "🎬" },
  { label: "Crypto & Web3",    query: "cryptocurrency bitcoin ethereum news today", category: "crypto", emoji: "₿" },
  { label: "Health & Wellness",query: "health wellness medical news 2026", category: "health",      emoji: "🏥" },
]

const CATEGORY_COLORS: Record<string, string> = {
  news:          "border-blue-400/30 bg-blue-500/10 text-blue-300",
  tech:          "border-violet-400/30 bg-violet-500/10 text-violet-300",
  sports:        "border-emerald-400/30 bg-emerald-500/10 text-emerald-300",
  science:       "border-cyan-400/30 bg-cyan-500/10 text-cyan-300",
  finance:       "border-yellow-400/30 bg-yellow-500/10 text-yellow-300",
  entertainment: "border-pink-400/30 bg-pink-500/10 text-pink-300",
  crypto:        "border-orange-400/30 bg-orange-500/10 text-orange-300",
  health:        "border-rose-400/30 bg-rose-500/10 text-rose-300",
  custom:        "border-white/20 bg-white/5 text-white/50",
}

function formatRelative(iso: string | null): string {
  if (!iso) return "Never"
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "Just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function WebWatchTab() {
  const [topics, setTopics] = useState<WatchedTopic[]>([])
  const [loading, setLoading] = useState(true)
  const [addingPreset, setAddingPreset] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  // Custom topic form
  const [customLabel, setCustomLabel] = useState("")
  const [customQuery, setCustomQuery] = useState("")
  const [addingCustom, setAddingCustom] = useState(false)
  const [customError, setCustomError] = useState("")

  const fetchTopics = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetch("/api/watcher/topics")
      if (r.ok) { const d = await r.json() as WatchedTopic[]; setTopics(Array.isArray(d) ? d : []) }
      else setTopics([])
    } catch { setTopics([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void fetchTopics() }, [fetchTopics])

  const addPreset = async (preset: typeof PRESET_TOPICS[0]) => {
    if (topics.some(t => t.query === preset.query)) return
    setAddingPreset(preset.label)
    try {
      const r = await fetch("/api/watcher/topics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: preset.label, query: preset.query, category: preset.category }),
      })
      if (r.ok) void fetchTopics()
    } catch { /* ignore */ }
    finally { setAddingPreset(null) }
  }

  const addCustom = async () => {
    setCustomError("")
    if (!customLabel.trim()) { setCustomError("Label is required."); return }
    if (!customQuery.trim()) { setCustomError("Search query is required."); return }
    setAddingCustom(true)
    try {
      const r = await fetch("/api/watcher/topics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: customLabel.trim(), query: customQuery.trim(), category: "custom" }),
      })
      if (r.ok) {
        setCustomLabel(""); setCustomQuery("")
        void fetchTopics()
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string }
        setCustomError(d.detail ?? "Failed to add topic.")
      }
    } catch { setCustomError("Network error.") }
    finally { setAddingCustom(false) }
  }

  const toggleTopic = async (id: string, enabled: boolean) => {
    setTopics(prev => prev.map(t => t.id === id ? { ...t, enabled } : t))
    await fetch(`/api/watcher/topics/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).catch(() => { void fetchTopics() })
  }

  const deleteTopic = async (id: string) => {
    setTopics(prev => prev.filter(t => t.id !== id))
    await fetch(`/api/watcher/topics/${id}`, { method: "DELETE" }).catch(() => { void fetchTopics() })
  }

  const runTopic = async (id: string) => {
    setRefreshing(id)
    try {
      const r = await fetch(`/api/watcher/topics/${id}/run`, { method: "POST" })
      if (r.ok) { const updated = await r.json() as WatchedTopic; setTopics(prev => prev.map(t => t.id === id ? updated : t)) }
    } catch { /* ignore */ }
    finally { setRefreshing(null) }
  }

  const activeTopics = topics.filter(t => t.enabled)
  const inactiveTopics = topics.filter(t => !t.enabled)
  const presetQueries = new Set(topics.map(t => t.query))

  return (
    <div className="space-y-6 sm:space-y-8 max-w-2xl">
      <div>
        <h2 className="text-lg font-semibold">Web Watch</h2>
        <p className="text-sm text-muted-foreground mt-1">
          GAAIA automatically searches these topics every hour so she always has fresh context.
          Results are injected into her knowledge when you chat.
        </p>
      </div>

      {/* Preset topics */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Quick-add Presets</h3>
        <div className="grid grid-cols-2 gap-2">
          {PRESET_TOPICS.map(preset => {
            const alreadyAdded = presetQueries.has(preset.query)
            return (
              <button
                key={preset.query}
                onClick={() => !alreadyAdded && void addPreset(preset)}
                disabled={alreadyAdded || addingPreset === preset.label}
                className={cn(
                  "flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl border text-sm font-medium text-left transition-all",
                  alreadyAdded
                    ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-400 cursor-default"
                    : "border-white/10 bg-white/[0.03] hover:bg-white/[0.07] hover:border-white/20 text-white/70 cursor-pointer"
                )}
              >
                <span className="text-base leading-none">{preset.emoji}</span>
                <span className="truncate">{preset.label}</span>
                {alreadyAdded ? (
                  <CheckCircle className="w-3.5 h-3.5 ml-auto shrink-0 text-emerald-400" />
                ) : addingPreset === preset.label ? (
                  <Loader2 className="w-3.5 h-3.5 ml-auto shrink-0 animate-spin" />
                ) : (
                  <Plus className="w-3.5 h-3.5 ml-auto shrink-0 text-white/30" />
                )}
              </button>
            )
          })}
        </div>
      </section>

      {/* Custom topic */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Add Custom Topic</h3>
        <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-medium">Topic name</label>
              <input
                type="text"
                value={customLabel}
                onChange={e => setCustomLabel(e.target.value)}
                placeholder="e.g. Climate Change"
                className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-muted-foreground font-medium">Search query</label>
              <input
                type="text"
                value={customQuery}
                onChange={e => setCustomQuery(e.target.value)}
                placeholder="e.g. climate change news 2026"
                className="w-full px-3 py-2 rounded-lg border border-border bg-input text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                onKeyDown={e => e.key === "Enter" && void addCustom()}
              />
            </div>
          </div>
          {customError && <p className="text-xs text-destructive">{customError}</p>}
          <button
            onClick={() => void addCustom()}
            disabled={addingCustom || !customLabel.trim() || !customQuery.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
          >
            {addingCustom ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            Add topic
          </button>
        </div>
      </section>

      {/* Active topics */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Watching ({activeTopics.length})
          </h3>
          {topics.length > 0 && (
            <button
              onClick={() => void fetchTopics()}
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              <RefreshCw className="w-3 h-3" /> Refresh list
            </button>
          )}
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading topics…
          </div>
        ) : activeTopics.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/10 px-5 py-6 text-center">
            <Globe className="w-8 h-8 mx-auto text-white/20 mb-2" />
            <p className="text-sm text-muted-foreground">No active watch topics yet.</p>
            <p className="text-xs text-muted-foreground/60 mt-1">Add some above to keep GAAIA informed.</p>
          </div>
        ) : (
          <ul className="space-y-2">
            {activeTopics.map(topic => {
              let parsed: LastResult | null = null
              try { if (topic.last_result) parsed = JSON.parse(topic.last_result) as LastResult } catch { /* */ }
              const isExpanded = expanded === topic.id
              return (
                <li key={topic.id} className="rounded-xl border border-white/[0.08] bg-white/[0.02] overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-3">
                    <span className={cn(
                      "text-[10px] px-2 py-0.5 rounded-full border shrink-0",
                      CATEGORY_COLORS[topic.category] ?? CATEGORY_COLORS.custom
                    )}>
                      {topic.category}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{topic.label}</p>
                      <p className="text-[10px] text-muted-foreground/60 font-mono truncate">{topic.query}</p>
                    </div>
                    <span className="text-[10px] text-muted-foreground shrink-0">{formatRelative(topic.last_fetched_at)}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      {parsed && parsed.items.length > 0 && (
                        <button
                          onClick={() => setExpanded(isExpanded ? null : topic.id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-colors text-xs"
                          title="View results"
                        >
                          {isExpanded ? "▲" : "▼"}
                        </button>
                      )}
                      <button
                        onClick={() => void runTopic(topic.id)}
                        disabled={refreshing === topic.id}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-colors"
                        title="Refresh now"
                      >
                        <RefreshCw className={cn("w-3.5 h-3.5", refreshing === topic.id && "animate-spin")} />
                      </button>
                      <button
                        onClick={() => void toggleTopic(topic.id, false)}
                        className="p-1.5 rounded-lg text-emerald-400 hover:text-white/50 hover:bg-white/[0.06] transition-colors"
                        title="Disable"
                      >
                        <ToggleRight className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => void deleteTopic(topic.id)}
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                        title="Delete"
                      >
                        <Trash2Icon className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* Expandable results */}
                  {isExpanded && parsed && parsed.items.length > 0 && (
                    <div className="border-t border-white/[0.06] px-4 py-3 space-y-2 bg-black/20">
                      <p className="text-[10px] text-muted-foreground/60 uppercase tracking-wider font-medium mb-2">
                        Last fetched {new Date(parsed.fetched_at).toLocaleString()}
                      </p>
                      {parsed.items.slice(0, 5).map((item, i) => (
                        <a
                          key={i}
                          href={item.href}
                          target="_blank"
                          rel="noreferrer"
                          className="block rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5 hover:bg-white/[0.05] transition-colors group"
                        >
                          <p className="text-xs font-medium text-foreground/80 group-hover:text-foreground truncate">
                            {item.title || item.href}
                          </p>
                          {item.body && (
                            <p className="text-[11px] text-muted-foreground mt-0.5 line-clamp-2">{item.body}</p>
                          )}
                        </a>
                      ))}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* Paused / disabled topics */}
      {!loading && inactiveTopics.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Paused ({inactiveTopics.length})</h3>
          <ul className="space-y-1.5">
            {inactiveTopics.map(topic => (
              <li key={topic.id} className="flex items-center gap-3 px-4 py-2.5 rounded-xl border border-white/[0.05] bg-white/[0.01] opacity-60">
                <span className={cn(
                  "text-[10px] px-2 py-0.5 rounded-full border shrink-0",
                  CATEGORY_COLORS[topic.category] ?? CATEGORY_COLORS.custom
                )}>
                  {topic.category}
                </span>
                <p className="text-sm flex-1 truncate text-muted-foreground">{topic.label}</p>
                <button
                  onClick={() => void toggleTopic(topic.id, true)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-emerald-400 hover:bg-white/[0.06] transition-colors"
                  title="Enable"
                >
                  <ToggleLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={() => void deleteTopic(topic.id)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                  title="Delete"
                >
                  <Trash2Icon className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

// ─── Security Tab ─────────────────────────────────────────────────────────────

type SetupStep = "idle" | "scanning" | "backup_codes"

function SecurityTab() {
  const [status, setStatus] = useState<{ totp_enabled: boolean; backup_codes_remaining: number } | null>(null)
  const [setupStep, setSetupStep] = useState<SetupStep>("idle")
  const [qrDataUrl, setQrDataUrl] = useState("")
  const [totpSecret, setTotpSecret] = useState("")
  const [enableCode, setEnableCode] = useState("")
  const [disableCode, setDisableCode] = useState("")
  const [backupCodes, setBackupCodes] = useState<string[]>([])
  const [copiedSecret, setCopiedSecret] = useState(false)
  const [copiedCodes, setCopiedCodes] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [showDisableForm, setShowDisableForm] = useState(false)

  const fetchStatus = async () => {
    try {
      const r = await fetch("/api/auth/2fa/status")
      if (r.ok) setStatus(await r.json() as typeof status)
    } catch { /* ignore */ }
  }

  useEffect(() => { void fetchStatus() }, [])

  const startSetup = async () => {
    setError(""); setLoading(true)
    try {
      const r = await fetch("/api/auth/2fa/totp/setup", { method: "POST" })
      if (!r.ok) { const d = await r.json().catch(() => ({})) as { detail?: string }; setError(d.detail ?? "Setup failed."); return }
      const d = await r.json() as { secret: string; qr_data_url: string }
      setQrDataUrl(d.qr_data_url)
      setTotpSecret(d.secret)
      setEnableCode("")
      setSetupStep("scanning")
    } catch { setError("Network error.") }
    finally { setLoading(false) }
  }

  const confirmEnable = async () => {
    if (enableCode.length < 6) return
    setError(""); setLoading(true)
    try {
      const r = await fetch("/api/auth/2fa/totp/enable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret: totpSecret, code: enableCode }),
      })
      if (!r.ok) { const d = await r.json().catch(() => ({})) as { detail?: string }; setError(d.detail ?? "Invalid code."); return }
      const d = await r.json() as { backup_codes: string[] }
      setBackupCodes(d.backup_codes)
      setSetupStep("backup_codes")
      void fetchStatus()
    } catch { setError("Network error.") }
    finally { setLoading(false) }
  }

  const disable2FA = async () => {
    if (disableCode.length < 6) return
    setError(""); setLoading(true)
    try {
      const r = await fetch("/api/auth/2fa/totp/disable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: disableCode }),
      })
      if (!r.ok) { const d = await r.json().catch(() => ({})) as { detail?: string }; setError(d.detail ?? "Invalid code."); return }
      setDisableCode(""); setShowDisableForm(false)
      void fetchStatus()
    } catch { setError("Network error.") }
    finally { setLoading(false) }
  }

  const copySecret = () => {
    navigator.clipboard.writeText(totpSecret).then(() => { setCopiedSecret(true); setTimeout(() => setCopiedSecret(false), 2000) }).catch(() => {})
  }

  const copyBackupCodes = () => {
    navigator.clipboard.writeText(backupCodes.join("\n")).then(() => { setCopiedCodes(true); setTimeout(() => setCopiedCodes(false), 2000) }).catch(() => {})
  }

  const finishSetup = () => { setSetupStep("idle"); setBackupCodes([]); setQrDataUrl(""); setTotpSecret(""); setEnableCode(""); setError("") }

  return (
    <div className="space-y-8 max-w-lg">
      <div>
        <h2 className="text-lg font-semibold">Security</h2>
        <p className="text-sm text-muted-foreground mt-1">Protect your account with two-factor authentication.</p>
      </div>

      {/* ── 2FA Status card ─────────────────────────────────────────── */}
      <section className="rounded-xl border border-border overflow-hidden">
        <div className="px-5 py-4 bg-muted/10 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-10 h-10 rounded-xl flex items-center justify-center shrink-0",
              status?.totp_enabled ? "bg-emerald-500/15 border border-emerald-400/25" : "bg-muted/40 border border-border"
            )}>
              <ShieldCheck className={cn("w-5 h-5", status?.totp_enabled ? "text-emerald-400" : "text-muted-foreground")} />
            </div>
            <div>
              <p className="text-sm font-semibold">Authenticator app (TOTP)</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {status === null
                  ? "Loading…"
                  : status.totp_enabled
                    ? `Enabled · ${status.backup_codes_remaining} backup code${status.backup_codes_remaining !== 1 ? "s" : ""} remaining`
                    : "Not enabled — your account uses only a password."}
              </p>
            </div>
          </div>
          {status?.totp_enabled ? (
            <span className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border border-emerald-400/30 bg-emerald-500/10 text-emerald-400 shrink-0">
              <CheckCircle className="w-3 h-3" /> Active
            </span>
          ) : (
            <span className="text-[10px] px-2.5 py-1 rounded-full border border-amber-400/30 bg-amber-500/10 text-amber-400 shrink-0 font-medium">
              Disabled
            </span>
          )}
        </div>

        {/* Setup flow */}
        {setupStep === "idle" && !status?.totp_enabled && (
          <div className="px-5 py-4 border-t border-border space-y-3">
            <p className="text-xs text-muted-foreground leading-relaxed">
              Use an authenticator app like <strong className="text-foreground">Google Authenticator</strong>, <strong className="text-foreground">Authy</strong>, or <strong className="text-foreground">1Password</strong> to generate time-based codes. Each login will require both your password and a fresh 6-digit code.
            </p>
            {error && <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
            <button
              onClick={() => void startSetup()}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
              Set up two-factor authentication
            </button>
          </div>
        )}

        {/* QR code scanning step */}
        {setupStep === "scanning" && (
          <div className="px-5 py-5 border-t border-border space-y-5">
            <div>
              <p className="text-sm font-medium mb-1">Step 1 — Scan this QR code</p>
              <p className="text-xs text-muted-foreground">Open your authenticator app and scan the code below. If you can&apos;t scan, enter the secret manually.</p>
            </div>

            {/* QR code */}
            <div className="flex justify-center">
              {qrDataUrl ? (
                <div className="p-3 rounded-xl bg-white shadow-lg">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={qrDataUrl} alt="TOTP QR code" width={180} height={180} />
                </div>
              ) : (
                <div className="w-44 h-44 rounded-xl bg-muted/30 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              )}
            </div>

            {/* Manual secret */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Manual entry key</label>
              <div className="flex items-center gap-2">
                <div className="flex-1 px-3 py-2 rounded-xl border border-border bg-muted/20 text-xs font-mono tracking-widest text-center select-all">
                  {totpSecret.match(/.{1,4}/g)?.join(" ") ?? totpSecret}
                </div>
                <button onClick={copySecret} className="p-2 rounded-xl border border-border hover:bg-muted transition-colors shrink-0" title="Copy secret">
                  {copiedSecret ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4 text-muted-foreground" />}
                </button>
              </div>
            </div>

            {/* Verify code */}
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Step 2 — Enter the 6-digit code</p>
              <p className="text-xs text-muted-foreground">Type the code shown in your app to confirm the link.</p>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                value={enableCode}
                onChange={e => setEnableCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="000 000"
                autoFocus
                maxLength={6}
                className="w-full rounded-xl border border-border bg-input/85 px-4 py-3 text-xl font-mono tracking-[0.5em] text-center focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all"
              />
            </div>

            {error && <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}

            <div className="flex gap-3">
              <button
                onClick={() => { setSetupStep("idle"); setError("") }}
                className="px-4 py-2.5 rounded-xl border border-border text-sm hover:bg-muted transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => void confirmEnable()}
                disabled={loading || enableCode.length < 6}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                {loading ? "Verifying…" : "Enable 2FA"}
              </button>
            </div>
          </div>
        )}

        {/* Backup codes step */}
        {setupStep === "backup_codes" && (
          <div className="px-5 py-5 border-t border-border space-y-4">
            <div className="flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-500/5 px-4 py-3">
              <KeyRound className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
              <div>
                <p className="text-sm font-semibold text-amber-300">Save your backup codes now</p>
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                  Each code can be used once if you lose access to your authenticator app. Store them in a safe place — you won&apos;t see them again.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {backupCodes.map(code => (
                <div key={code} className="px-3 py-2 rounded-lg border border-border bg-muted/20 text-sm font-mono text-center tracking-widest">
                  {code}
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button
                onClick={copyBackupCodes}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-border text-sm hover:bg-muted transition-colors"
              >
                {copiedCodes ? <CheckCircle className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                {copiedCodes ? "Copied!" : "Copy all"}
              </button>
              <button
                onClick={finishSetup}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:opacity-90 transition-all"
              >
                <CheckCircle className="w-4 h-4" />
                Done — I&apos;ve saved these codes
              </button>
            </div>
          </div>
        )}

        {/* Disable 2FA (when enabled) */}
        {status?.totp_enabled && setupStep === "idle" && (
          <div className="px-5 py-4 border-t border-border">
            {!showDisableForm ? (
              <button
                onClick={() => { setShowDisableForm(true); setError("") }}
                className="text-xs text-destructive hover:text-destructive/80 transition-colors"
              >
                Disable two-factor authentication…
              </button>
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">Enter your authenticator code (or a backup code) to disable 2FA.</p>
                <input
                  type="text"
                  inputMode="numeric"
                  value={disableCode}
                  onChange={e => setDisableCode(e.target.value.replace(/\s/g, "").slice(0, 10))}
                  placeholder="000000"
                  autoFocus
                  className="w-full rounded-xl border border-border bg-input/85 px-4 py-2.5 text-lg font-mono tracking-[0.4em] text-center focus:outline-none focus:border-destructive/50 focus:ring-2 focus:ring-destructive/20 transition-all"
                />
                {error && <p className="text-xs text-destructive">{error}</p>}
                <div className="flex gap-2">
                  <button
                    onClick={() => { setShowDisableForm(false); setDisableCode(""); setError("") }}
                    className="px-3 py-2 rounded-xl border border-border text-xs hover:bg-muted transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void disable2FA()}
                    disabled={loading || disableCode.length < 6}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-destructive text-destructive-foreground text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-all"
                  >
                    {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                    {loading ? "Disabling…" : "Disable 2FA"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── What is 2FA info ──────────────────────────────────────────── */}
      {!status?.totp_enabled && setupStep === "idle" && (
        <section className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-5 space-y-3">
          <p className="text-sm font-semibold">Why enable 2FA?</p>
          <ul className="space-y-2 text-xs text-muted-foreground">
            {[
              "Protects your AI conversations and personal data even if your password leaks.",
              "Required for team and enterprise plans where your data matters to others.",
              "Takes under 2 minutes to set up with any TOTP app.",
            ].map((item, i) => (
              <li key={i} className="flex items-start gap-2">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

// ─── Developer Tab ────────────────────────────────────────────────────────────

function DeveloperTab() {
  const [apiBase, setApiBase] = useState("http://127.0.0.1:8765")
  const [copied, setCopied] = useState<string | null>(null)
  const [stats, setStats] = useState<{ models?: string[]; version?: string } | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem("gaaia_api_base")
    if (stored) setApiBase(stored)
    fetch("/api/stats").then(r => r.ok ? r.json() : null).then(d => { if (d) setStats(d) }).catch(() => {})
  }, [])

  const saveApiBase = () => {
    localStorage.setItem("gaaia_api_base", apiBase)
    setCopied("saved")
    setTimeout(() => setCopied(null), 2000)
  }

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => { setCopied(key); setTimeout(() => setCopied(null), 2000) }).catch(() => {})
  }

  const ENDPOINTS = [
    { label: "Chat stream",      path: "/api/chat",                method: "POST" },
    { label: "Memory sessions",  path: "/api/memory/sessions",     method: "GET"  },
    { label: "Voice",            path: "/api/voice",               method: "POST" },
    { label: "Image generate",   path: "/api/image/generate",      method: "POST" },
    { label: "Document generate",path: "/api/document/generate",   method: "POST" },
    { label: "Camera enroll",    path: "/api/camera/enroll",       method: "POST" },
    { label: "Camera detect",    path: "/api/camera/detect",       method: "POST" },
    { label: "Auth me",          path: "/api/auth/me",             method: "GET"  },
  ]

  return (
    <div className="space-y-8 max-w-xl">
      <div>
        <h2 className="text-lg font-semibold">Developer</h2>
        <p className="text-sm text-muted-foreground mt-1">API configuration and available endpoints.</p>
      </div>

      {/* API base URL */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Backend API URL</h3>
        <p className="text-xs text-muted-foreground">The URL where GAAIA's FastAPI backend is running.</p>
        <div className="flex gap-2">
          <input
            type="text"
            value={apiBase}
            onChange={e => setApiBase(e.target.value)}
            className="flex-1 px-4 py-2.5 rounded-xl border border-border bg-input text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50"
            placeholder="http://127.0.0.1:8765"
          />
          <button onClick={saveApiBase} className="px-4 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-all">
            {copied === "saved" ? "Saved!" : "Save"}
          </button>
        </div>
      </section>

      {/* System info */}
      {stats && (
        <section className="space-y-3">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">System Info</h3>
          <div className="rounded-xl border border-border bg-muted/20 divide-y divide-border overflow-hidden">
            {stats.version && (
              <div className="flex items-center justify-between px-4 py-2.5 text-sm">
                <span className="text-muted-foreground">Version</span>
                <span className="font-mono text-xs">{stats.version}</span>
              </div>
            )}
            {stats.models && (
              <div className="flex items-start justify-between px-4 py-2.5 text-sm gap-4">
                <span className="text-muted-foreground shrink-0">Loaded models</span>
                <div className="flex flex-wrap gap-1 justify-end">
                  {stats.models.map(m => (
                    <span key={m} className="text-[10px] px-2 py-0.5 rounded-full border border-border bg-muted font-mono">{m}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Endpoint reference */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">API Endpoints</h3>
          <a href="http://127.0.0.1:8765/docs" target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary hover:underline">
            OpenAPI docs <ExternalLink className="w-3 h-3" />
          </a>
        </div>

        <div className="rounded-xl border border-border overflow-hidden divide-y divide-border">
          {ENDPOINTS.map(ep => (
            <div key={ep.path} className="flex items-center justify-between px-4 py-2.5 bg-muted/10 group">
              <div className="flex items-center gap-3 min-w-0">
                <span className={cn(
                  "text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0",
                  ep.method === "GET" ? "bg-emerald-500/20 text-emerald-400" : "bg-blue-500/20 text-blue-400"
                )}>{ep.method}</span>
                <div className="min-w-0">
                  <p className="text-xs font-medium truncate">{ep.label}</p>
                  <p className="text-[10px] font-mono text-muted-foreground">{ep.path}</p>
                </div>
              </div>
              <button
                onClick={() => copyToClipboard(`${apiBase}${ep.path}`, ep.path)}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors opacity-0 group-hover:opacity-100"
                title="Copy URL"
              >
                {copied === ep.path ? <CheckCircle className="w-3.5 h-3.5 text-primary" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* Quick links */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Quick Links</h3>
        <div className="flex flex-wrap gap-2">
          {[
            { label: "Interactive Docs", href: "http://127.0.0.1:8765/docs" },
            { label: "ReDoc",            href: "http://127.0.0.1:8765/redoc" },
            { label: "Health Check",     href: "http://127.0.0.1:8765/health" },
          ].map(link => (
            <a
              key={link.href}
              href={link.href}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border hover:bg-muted transition-colors"
            >
              <Server className="w-3 h-3" />
              {link.label}
              <ExternalLink className="w-3 h-3 text-muted-foreground" />
            </a>
          ))}
        </div>
      </section>
    </div>
  )
}

// ─── Main Settings Page ───────────────────────────────────────────────────────

function SettingsPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = (searchParams.get("tab") as Tab | null) ?? "profile"

  const [activeTab, setActiveTab] = useState<Tab>(initialTab)
  const [user, setUser] = useState<UserInfo | null>(null)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => { if (!r.ok) { router.replace("/login"); return null } return r.json() })
      .then(d => { if (d?.display_name) setUser({ display_name: d.display_name, email: d.email ?? "", avatar_color: d.avatar_color || "#0ea5e9", has_password: !!d.has_password }) })
      .catch(() => router.replace("/login"))
  }, [router])

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab)
    router.replace(`/settings?tab=${tab}`, { scroll: false })
  }

  return (
    <AppShell title="Settings">
      {/* Stack on mobile (tabs as a horizontal scroller above the content),
          side-by-side on md+ where the aside fits comfortably. */}
      <div className="flex flex-col md:flex-row h-full overflow-hidden">
        {/* Settings nav: sidebar on md+, horizontal scroll tabs on mobile */}
        <aside className="md:w-56 shrink-0 md:border-r border-b md:border-b-0 border-white/[0.07] md:px-3 md:py-5 px-2 py-2 md:space-y-1 bg-[#0d0d12] md:overflow-y-auto overflow-x-auto md:overflow-x-hidden">
          {/* User mini-card — md+ only; phones already show the avatar in the
              top bar via AppShell, so this would be redundant on mobile. */}
          {user && (
            <div className="hidden md:flex items-center gap-3 px-3 py-3 mb-3 rounded-xl bg-white/[0.04] border border-white/[0.06]">
              <div
                className="w-8 h-8 rounded-xl flex items-center justify-center text-white font-bold text-sm shrink-0"
                style={{ backgroundColor: user.avatar_color }}
              >
                {user.display_name[0].toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-white/70 truncate">{user.display_name}</p>
                {user.email && <p className="text-[10px] text-white/30 truncate">{user.email}</p>}
              </div>
            </div>
          )}

          <div className="flex md:flex-col md:space-y-1 gap-1.5 md:gap-0 min-w-max md:min-w-0">
            {TABS.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={cn(
                    "shrink-0 md:w-full flex items-center gap-2 md:gap-3 px-3 py-2 md:py-2.5 rounded-xl text-sm font-medium transition-all duration-100 text-left whitespace-nowrap",
                    isActive
                      ? "bg-indigo-600/20 text-white border border-indigo-500/20"
                      : "text-white/35 hover:text-white/70 hover:bg-white/[0.05] border border-transparent"
                  )}
                >
                  <Icon className={cn("w-4 h-4 shrink-0", isActive ? "text-indigo-400" : "text-white/25")} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-6 md:px-8 py-5 sm:py-7 bg-[#0a0a10]">
          {activeTab === "profile"      && <ProfileTab user={user} onUserChange={u => setUser(u)} />}
          {activeTab === "account"      && <AccountTab user={user} onUserChange={u => setUser(u)} />}
          {activeTab === "security"     && <SecurityTab />}
          {activeTab === "voice-camera" && <VoiceCameraTab />}
          {activeTab === "web-watch"    && <WebWatchTab />}
          {activeTab === "developer"    && <DeveloperTab />}
        </main>
      </div>
    </AppShell>
  )
}

export default function SettingsPage() {
  return (
    <Suspense>
      <SettingsPageContent />
    </Suspense>
  )
}
