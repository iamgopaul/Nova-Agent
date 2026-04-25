"use client"

import { useMemo } from "react"
import { cn } from "@/lib/utils"
import { CheckCircle, XCircle } from "lucide-react"

interface Rule {
  label: string
  test: (p: string) => boolean
}

const RULES: Rule[] = [
  { label: "At least 8 characters",          test: p => p.length >= 8 },
  { label: "Uppercase letter (A–Z)",          test: p => /[A-Z]/.test(p) },
  { label: "Lowercase letter (a–z)",          test: p => /[a-z]/.test(p) },
  { label: "Number (0–9)",                    test: p => /\d/.test(p) },
  { label: "Special character (!@#$%…)",      test: p => /[^A-Za-z0-9]/.test(p) },
]

const COMMON = new Set([
  "password","password1","password123","12345678","qwerty123",
  "iloveyou","admin123","welcome1","letmein1","passw0rd",
])

function scorePassword(password: string): number {
  if (!password) return 0
  let score = 0
  if (password.length >= 8)  score++
  if (password.length >= 12) score++
  if (/[A-Z]/.test(password)) score++
  if (/[a-z]/.test(password)) score++
  if (/\d/.test(password))    score++
  if (/[^A-Za-z0-9]/.test(password)) score++
  if (COMMON.has(password.toLowerCase())) score = Math.max(0, score - 3)
  return Math.min(4, Math.floor(score * 4 / 6))
}

const SCORE_META = [
  { label: "Very weak", color: "bg-red-500",    text: "text-red-400"    },
  { label: "Weak",      color: "bg-orange-500",  text: "text-orange-400" },
  { label: "Fair",      color: "bg-yellow-500",  text: "text-yellow-400" },
  { label: "Good",      color: "bg-blue-500",    text: "text-blue-400"   },
  { label: "Strong",    color: "bg-emerald-500", text: "text-emerald-400"},
]

interface PasswordStrengthProps {
  password: string
  /** If true, show the per-rule checklist in addition to the bar */
  showRules?: boolean
  className?: string
}

export function PasswordStrength({ password, showRules = false, className }: PasswordStrengthProps) {
  const score  = useMemo(() => scorePassword(password), [password])
  const meta   = SCORE_META[score]
  const filled = score + 1   // 1-5 segments filled

  if (!password) return null

  return (
    <div className={cn("space-y-2", className)}>
      {/* Strength bar */}
      <div className="flex items-center gap-3">
        <div className="flex gap-1 flex-1">
          {SCORE_META.map((m, i) => (
            <div
              key={i}
              className={cn(
                "h-1.5 flex-1 rounded-full transition-all duration-300",
                i < filled ? m.color : "bg-white/10"
              )}
            />
          ))}
        </div>
        <span className={cn("text-[11px] font-semibold shrink-0 w-16 text-right", meta.text)}>
          {meta.label}
        </span>
      </div>

      {/* Per-rule checklist */}
      {showRules && (
        <ul className="space-y-1">
          {RULES.map(rule => {
            const ok = rule.test(password)
            return (
              <li key={rule.label} className="flex items-center gap-2 text-[11px]">
                {ok
                  ? <CheckCircle className="w-3 h-3 text-emerald-400 shrink-0" />
                  : <XCircle    className="w-3 h-3 text-white/20 shrink-0" />
                }
                <span className={ok ? "text-white/50" : "text-white/30"}>{rule.label}</span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
