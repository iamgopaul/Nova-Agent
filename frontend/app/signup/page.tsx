"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { PasswordStrength } from "@/components/password-strength"

const AVATAR_COLORS = [
  "#38bdf8", "#818cf8", "#34d399", "#fb923c",
  "#f472b6", "#facc15", "#a78bfa", "#f87171",
]

export default function SignupPage() {
  const router = useRouter()
  const [displayName, setDisplayName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [avatarColor, setAvatarColor] = useState(AVATAR_COLORS[0])
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (password !== confirm) {
      setError("Passwords do not match.")
      return
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }

    setLoading(true)
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          display_name: displayName,
          avatar_color: avatarColor,
        }),
        credentials: "include",
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({})) as { detail?: string }
        setError(data.detail || "Registration failed. Please try again.")
        return
      }
      router.push("/home")
    } catch {
      setError("Something went wrong. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen aurora-bg flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm">
        <div className="rounded-3xl border border-border/50 bg-card/60 backdrop-blur-md p-8 shadow-[0_8px_48px_oklch(0.72_0.14_220_/_0.10)]">
          {/* Logo */}
          <div className="flex flex-col items-center mb-7">
            <NovaIcon size={56} className="mb-3" />
            <h1 className="text-xl font-bold">Create your account</h1>
            <p className="text-sm text-muted-foreground mt-1">Join Nova — your private AI assistant</p>
          </div>

          {/* OAuth buttons */}
          <div className="space-y-2.5 mb-5">
            <a
              href="http://127.0.0.1:8765/auth/oauth/google"
              className="flex items-center justify-center gap-2.5 w-full py-2.5 rounded-xl border border-border bg-input/60 hover:bg-input/90 transition-all text-sm font-medium text-foreground"
            >
              <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
              Sign up with Google
            </a>
            <a
              href="http://127.0.0.1:8765/auth/oauth/github"
              className="flex items-center justify-center gap-2.5 w-full py-2.5 rounded-xl border border-border bg-input/60 hover:bg-input/90 transition-all text-sm font-medium text-foreground"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
              Sign up with GitHub
            </a>
          </div>

          <div className="flex items-center gap-3 mb-5">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs text-muted-foreground">or sign up with email</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Avatar color picker */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-2">Avatar color</label>
              <div className="flex gap-2 flex-wrap">
                {AVATAR_COLORS.map(color => (
                  <button
                    key={color}
                    type="button"
                    onClick={() => setAvatarColor(color)}
                    className="w-7 h-7 rounded-full transition-all hover:scale-110"
                    style={{
                      backgroundColor: color,
                      outline: avatarColor === color ? `2px solid ${color}` : "none",
                      outlineOffset: "2px",
                    }}
                  />
                ))}
                {/* Preview */}
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white ml-auto"
                  style={{ backgroundColor: avatarColor }}
                >
                  {displayName.charAt(0).toUpperCase() || "?"}
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Display name</label>
              <input
                type="text"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                required
                autoComplete="name"
                placeholder="Your name"
                className="w-full rounded-xl border border-border bg-input/85 backdrop-blur-sm px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@example.com"
                className="w-full rounded-xl border border-border bg-input/85 backdrop-blur-sm px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-medium text-muted-foreground">Password</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                placeholder="Min. 8 characters"
                className="w-full rounded-xl border border-border bg-input/85 backdrop-blur-sm px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all"
              />
              <PasswordStrength password={password} showRules />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Confirm password</label>
              <input
                type="password"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                required
                autoComplete="new-password"
                placeholder="••••••••"
                className="w-full rounded-xl border border-border bg-input/85 backdrop-blur-sm px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all"
              />
            </div>

            {error && (
              <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-60 disabled:cursor-not-allowed shadow-[0_0_20px_oklch(0.72_0.14_220_/_0.20)] mt-1"
            >
              {loading ? "Creating account…" : "Create account"}
            </button>
          </form>

          <p className="text-center text-xs text-muted-foreground mt-6">
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </div>

        <p className="text-center text-[10px] text-muted-foreground mt-4">
          Your data stays on your machine. Always.
        </p>
        <div className="text-center mt-3">
          <Link href="/" className="text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors">
            ← Back to Nova
          </Link>
        </div>
      </div>
    </div>
  )
}
