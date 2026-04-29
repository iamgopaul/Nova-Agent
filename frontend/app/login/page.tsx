"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { ShieldCheck } from "lucide-react"

type Step = "credentials" | "2fa"

export default function LoginPage() {
  const router = useRouter()
  const [step, setStep] = useState<Step>("credentials")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [challengeToken, setChallengeToken] = useState("")
  const [twoFaMethod, setTwoFaMethod] = useState<"totp" | "email">("totp")
  const [code, setCode] = useState("")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleCredentials = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        credentials: "include",
      })

      if (res.status === 202) {
        // 2FA required
        const data = await res.json() as { requires_2fa: boolean; challenge_token: string; method: string }
        setChallengeToken(data.challenge_token)
        setTwoFaMethod(data.method as "totp" | "email")
        if (data.method === "email") {
          // Trigger OTP send via the challenge path — user is not yet authenticated,
          // so we POST the challenge_token itself to trigger the send
          await fetch("/api/auth/2fa/email/send-challenge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ challenge_token: data.challenge_token }),
          })
        }
        setStep("2fa")
        return
      }

      if (!res.ok) {
        const data = await res.json().catch(() => ({})) as { detail?: string }
        setError(data.detail || "Invalid email or password.")
        return
      }
      router.push("/home")
    } catch {
      setError("Something went wrong. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  const handle2FA = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const res = await fetch("/api/auth/2fa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ challenge_token: challengeToken, code }),
        credentials: "include",
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({})) as { detail?: string }
        setError(data.detail || "Invalid code. Please try again.")
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
    <div className="min-h-screen aurora-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-3xl border border-border/50 bg-card/60 backdrop-blur-md p-8 shadow-[0_8px_48px_oklch(0.72_0.14_220_/_0.10)]">

          {step === "credentials" ? (
            <>
              <div className="flex flex-col items-center mb-8">
                <GaaiaIcon size={56} className="mb-3" />
                <h1 className="text-xl font-bold">Welcome back</h1>
                <p className="text-sm text-muted-foreground mt-1">Sign in to your GAAIA account</p>
              </div>

              <div className="space-y-2.5 mb-5">
                <a
                  href="/api/auth/oauth/google"
                  className="flex items-center justify-center gap-2.5 w-full py-2.5 rounded-xl border border-border bg-input/60 hover:bg-input/90 transition-all text-sm font-medium"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                  Continue with Google
                </a>
                <a
                  href="/api/auth/oauth/github"
                  className="flex items-center justify-center gap-2.5 w-full py-2.5 rounded-xl border border-border bg-input/60 hover:bg-input/90 transition-all text-sm font-medium"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
                  Continue with GitHub
                </a>
              </div>

              <div className="flex items-center gap-3 mb-5">
                <div className="flex-1 h-px bg-border" />
                <span className="text-xs text-muted-foreground">or</span>
                <div className="flex-1 h-px bg-border" />
              </div>

              <form onSubmit={handleCredentials} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Email</label>
                  <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email"
                    placeholder="you@example.com"
                    className="w-full rounded-xl border border-border bg-input/85 px-3.5 py-2.5 text-sm focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Password</label>
                  <input type="password" value={password} onChange={e => setPassword(e.target.value)} required autoComplete="current-password"
                    placeholder="••••••••"
                    className="w-full rounded-xl border border-border bg-input/85 px-3.5 py-2.5 text-sm focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all" />
                </div>
                {error && <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
                <button type="submit" disabled={loading}
                  className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 disabled:opacity-60 transition-all mt-2">
                  {loading ? "Signing in…" : "Sign in"}
                </button>
              </form>

              <p className="text-center text-xs text-muted-foreground mt-6">
                Don&apos;t have an account?{" "}
                <Link href="/signup" className="text-primary hover:underline">Create one</Link>
              </p>
            </>
          ) : (
            <>
              <div className="flex flex-col items-center mb-8">
                <div className="w-14 h-14 rounded-2xl bg-primary/15 border border-primary/25 flex items-center justify-center mb-3">
                  <ShieldCheck className="w-7 h-7 text-primary" />
                </div>
                <h1 className="text-xl font-bold">Two-factor verification</h1>
                <p className="text-sm text-muted-foreground mt-1 text-center">
                  {twoFaMethod === "totp"
                    ? "Enter the 6-digit code from your authenticator app."
                    : "Enter the 6-digit code sent to your email."}
                </p>
              </div>

              <form onSubmit={handle2FA} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Verification code</label>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9A-Za-z]{6,10}"
                    value={code}
                    onChange={e => setCode(e.target.value.replace(/\s/g, ""))}
                    required
                    autoFocus
                    placeholder="000000"
                    maxLength={10}
                    className="w-full rounded-xl border border-border bg-input/85 px-3.5 py-3 text-xl font-mono tracking-[0.4em] text-center focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/20 transition-all"
                  />
                </div>
                {error && <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">{error}</p>}
                <button type="submit" disabled={loading || code.length < 6}
                  className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:opacity-90 disabled:opacity-60 transition-all">
                  {loading ? "Verifying…" : "Verify"}
                </button>
              </form>

              <button onClick={() => { setStep("credentials"); setCode(""); setError("") }}
                className="w-full mt-4 text-xs text-muted-foreground hover:text-foreground transition-colors">
                ← Back to sign in
              </button>
            </>
          )}
        </div>

        <p className="text-center text-[10px] text-muted-foreground mt-4">Your data stays on your machine. Always.</p>
        <div className="text-center mt-3">
          <Link href="/" className="text-[11px] text-muted-foreground/60 hover:text-muted-foreground transition-colors">← Back to GAAIA</Link>
        </div>
      </div>
    </div>
  )
}
