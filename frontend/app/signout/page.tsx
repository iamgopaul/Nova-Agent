"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import { LogOut } from "lucide-react"

const REDIRECT_DELAY = 4 // seconds

export default function SignOutPage() {
  const router = useRouter()
  const [countdown, setCountdown] = useState(REDIRECT_DELAY)

  useEffect(() => {
    if (countdown <= 0) {
      router.replace("/")
      return
    }
    const t = setTimeout(() => setCountdown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [countdown, router])

  return (
    <div className="min-h-screen aurora-bg flex items-center justify-center px-4">
      {/* Ambient blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-blue-500/8 blur-3xl" />
        <div className="absolute bottom-0 right-0 w-80 h-80 rounded-full bg-violet-500/8 blur-3xl" />
      </div>

      <div className="relative z-10 flex flex-col items-center gap-6 text-center max-w-sm">
        {/* Icon */}
        <div className="relative">
          <div className="w-20 h-20 rounded-full bg-white/4 border border-white/8 flex items-center justify-center">
            <LogOut className="w-8 h-8 text-white/40" />
          </div>
          {/* Countdown ring */}
          <svg
            className="absolute inset-0 w-20 h-20 -rotate-90"
            viewBox="0 0 80 80"
          >
            <circle
              cx="40" cy="40" r="36"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="text-white/6"
            />
            <circle
              cx="40" cy="40" r="36"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 36}`}
              strokeDashoffset={`${2 * Math.PI * 36 * (1 - countdown / REDIRECT_DELAY)}`}
              className="text-primary transition-all duration-1000 ease-linear"
            />
          </svg>
        </div>

        {/* GAAIA logo */}
        <div className="flex items-center gap-2">
          <GaaiaIcon size={22} />
          <span className="font-bold text-base tracking-tight">GAAIA</span>
        </div>

        <div>
          <h1 className="text-2xl font-bold mb-2">You&apos;ve been signed out</h1>
          <p className="text-sm text-muted-foreground">
            Thanks for using GAAIA. Redirecting you back in{" "}
            <span className="font-semibold text-foreground">{countdown}s</span>…
          </p>
        </div>

        <button
          onClick={() => router.replace("/")}
          className="text-xs text-primary hover:underline transition-colors"
        >
          Go now
        </button>
      </div>
    </div>
  )
}
