"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense } from "react"
import { AppShell } from "@/components/app-shell"
import { CheckCircle, Crown, ExternalLink, Loader2, Sparkles, Users, Zap } from "lucide-react"
import { cn } from "@/lib/utils"

interface Plan {
  id: string
  name: string
  price_monthly_cents: number
  price_yearly_cents: number
  max_seats: number | null
  features: string[]
}

interface Subscription {
  tier: string
  status: string
  current_period_end: string | null
  cancel_at_period_end: boolean
  stripe_customer_id: string | null
}

const PLAN_ICONS: Record<string, React.ElementType> = {
  Free: Zap,
  Pro: Crown,
  Teams: Users,
}

const PLAN_COLORS: Record<string, string> = {
  Free:  "border-white/8 bg-white/2",
  Pro:   "border-indigo-500/30 bg-indigo-500/5",
  Teams: "border-violet-500/30 bg-violet-500/5",
}

const PLAN_BUTTON_COLORS: Record<string, string> = {
  Free:  "bg-white/10 text-white/60",
  Pro:   "bg-indigo-600 hover:bg-indigo-500 text-white",
  Teams: "bg-violet-600 hover:bg-violet-500 text-white",
}

function centsToDisplay(cents: number): string {
  if (cents === 0) return "Free"
  return `$${(cents / 100).toFixed(0)}`
}

function BillingPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [plans, setPlans] = useState<Plan[]>([])
  const [sub, setSub] = useState<Subscription | null>(null)
  const [interval, setInterval] = useState<"month" | "year">("month")
  const [loading, setLoading] = useState(true)
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null)
  const [portalLoading, setPortalLoading] = useState(false)
  const [toast, setToast] = useState<{ type: "success" | "error"; msg: string } | null>(null)

  const showToast = (type: "success" | "error", msg: string) => {
    setToast({ type, msg })
    setTimeout(() => setToast(null), 4000)
  }

  useEffect(() => {
    const success = searchParams.get("success")
    const canceled = searchParams.get("canceled")
    if (success) showToast("success", "Subscription activated — welcome to Pro!")
    if (canceled) showToast("error", "Checkout canceled. No charges were made.")
  }, [searchParams])

  useEffect(() => {
    Promise.all([
      fetch("/api/billing/plans").then(r => r.ok ? r.json() as Promise<Plan[]> : []),
      fetch("/api/billing/subscription").then(r => r.ok ? r.json() as Promise<Subscription> : null),
    ]).then(([p, s]) => {
      setPlans(p as Plan[])
      setSub(s as Subscription | null)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleCheckout = async (planName: string) => {
    // Map plan name → env-configured price ID (backend resolves this)
    const priceKey = planName === "Pro"
      ? interval === "month" ? "pro_monthly" : "pro_yearly"
      : interval === "month" ? "teams_monthly" : "teams_yearly"

    setCheckoutLoading(planName)
    try {
      const res = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ price_id: priceKey, interval }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({})) as { detail?: string }
        showToast("error", d.detail ?? "Billing not configured.")
        return
      }
      const { url } = await res.json() as { url: string }
      window.location.href = url
    } catch {
      showToast("error", "Network error. Please try again.")
    } finally {
      setCheckoutLoading(null)
    }
  }

  const handlePortal = async () => {
    setPortalLoading(true)
    try {
      const res = await fetch("/api/billing/portal", { method: "POST" })
      if (!res.ok) {
        const d = await res.json().catch(() => ({})) as { detail?: string }
        showToast("error", d.detail ?? "Could not open billing portal.")
        return
      }
      const { url } = await res.json() as { url: string }
      window.location.href = url
    } catch {
      showToast("error", "Network error.")
    } finally {
      setPortalLoading(false)
    }
  }

  const currentTier = sub?.tier ?? "free"
  const isSubscribed = sub?.stripe_customer_id != null && currentTier !== "free"

  return (
    <AppShell title="Billing">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-8 sm:space-y-10">

        {/* Toast */}
        {toast && (
          <div className={cn(
            "fixed top-5 right-5 z-50 flex items-center gap-3 px-5 py-3.5 rounded-xl border shadow-xl text-sm font-medium",
            toast.type === "success"
              ? "bg-emerald-950 border-emerald-500/30 text-emerald-300"
              : "bg-red-950 border-red-500/30 text-red-300"
          )}>
            {toast.type === "success" ? <CheckCircle className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
            {toast.msg}
          </div>
        )}

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold">Billing & Plans</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {isSubscribed
              ? `You are on the ${currentTier.charAt(0).toUpperCase() + currentTier.slice(1)} plan.`
              : "Upgrade to unlock more features and increase your limits."}
          </p>
        </div>

        {/* Current subscription banner */}
        {isSubscribed && sub && (
          <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 px-5 py-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Crown className="w-5 h-5 text-indigo-400 shrink-0" />
              <div>
                <p className="text-sm font-semibold capitalize">{currentTier} Plan</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {sub.cancel_at_period_end
                    ? `Cancels on ${sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString() : "period end"}`
                    : sub.current_period_end
                      ? `Renews ${new Date(sub.current_period_end).toLocaleDateString()}`
                      : "Active"}
                </p>
              </div>
            </div>
            <button
              onClick={() => void handlePortal()}
              disabled={portalLoading}
              className="flex items-center gap-1.5 text-sm px-4 py-2 rounded-xl border border-indigo-500/30 hover:bg-indigo-500/10 transition-colors text-indigo-300"
            >
              {portalLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ExternalLink className="w-4 h-4" />}
              Manage subscription
            </button>
          </div>
        )}

        {/* Billing interval toggle */}
        <div className="flex items-center justify-center gap-1 p-1 rounded-xl bg-white/4 border border-white/7 w-fit mx-auto">
          <button
            onClick={() => setInterval("month")}
            className={cn(
              "px-5 py-2 rounded-lg text-sm font-medium transition-all",
              interval === "month" ? "bg-white/10 text-white" : "text-white/40 hover:text-white/70"
            )}
          >
            Monthly
          </button>
          <button
            onClick={() => setInterval("year")}
            className={cn(
              "px-5 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5",
              interval === "year" ? "bg-white/10 text-white" : "text-white/40 hover:text-white/70"
            )}
          >
            Yearly
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-400/20">
              Save 20%
            </span>
          </button>
        </div>

        {/* Plans grid */}
        {loading ? (
          <div className="flex items-center justify-center py-16 gap-3 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin" />
            Loading plans…
          </div>
        ) : plans.length === 0 ? (
          <FallbackPlans interval={interval} currentTier={currentTier} onUpgrade={handleCheckout} checkoutLoading={checkoutLoading} />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {plans.map(plan => {
              const Icon = PLAN_ICONS[plan.name] ?? Zap
              const isCurrentPlan = currentTier.toLowerCase() === plan.name.toLowerCase()
              const price = interval === "month" ? plan.price_monthly_cents : plan.price_yearly_cents
              const isFree = price === 0

              return (
                <div
                  key={plan.id}
                  className={cn(
                    "relative rounded-2xl border p-6 flex flex-col gap-5",
                    PLAN_COLORS[plan.name] ?? "border-white/8 bg-white/2",
                    plan.name === "Pro" && "ring-1 ring-indigo-500/20"
                  )}
                >
                  {plan.name === "Pro" && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                      <span className="text-[10px] font-bold px-3 py-1 rounded-full bg-indigo-600 text-white border border-indigo-400/30">
                        MOST POPULAR
                      </span>
                    </div>
                  )}

                  <div className="flex items-center gap-3">
                    <div className={cn(
                      "w-10 h-10 rounded-xl flex items-center justify-center border",
                      plan.name === "Pro" ? "bg-indigo-500/20 border-indigo-400/25" :
                      plan.name === "Teams" ? "bg-violet-500/20 border-violet-400/25" :
                      "bg-white/7 border-white/10"
                    )}>
                      <Icon className={cn(
                        "w-5 h-5",
                        plan.name === "Pro" ? "text-indigo-400" :
                        plan.name === "Teams" ? "text-violet-400" :
                        "text-white/50"
                      )} />
                    </div>
                    <div>
                      <p className="font-semibold">{plan.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {plan.max_seats ? `Up to ${plan.max_seats} seats` : "Unlimited seats"}
                      </p>
                    </div>
                  </div>

                  <div>
                    <span className="text-3xl font-bold">{centsToDisplay(price)}</span>
                    {!isFree && (
                      <span className="text-sm text-muted-foreground ml-1">
                        /{interval === "month" ? "mo" : "yr"}
                      </span>
                    )}
                  </div>

                  <ul className="space-y-2 flex-1">
                    {(plan.features as string[]).map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>

                  {isCurrentPlan ? (
                    <div className="w-full py-2.5 rounded-xl text-center text-sm font-medium bg-white/6 text-white/50 border border-white/8">
                      Current plan
                    </div>
                  ) : isFree ? (
                    <div className="w-full py-2.5 rounded-xl text-center text-sm font-medium bg-white/4 text-white/30 border border-white/6 cursor-not-allowed">
                      Default
                    </div>
                  ) : (
                    <button
                      onClick={() => void handleCheckout(plan.name)}
                      disabled={checkoutLoading === plan.name}
                      className={cn(
                        "w-full py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-60 flex items-center justify-center gap-2",
                        PLAN_BUTTON_COLORS[plan.name] ?? "bg-white/10 text-white"
                      )}
                    >
                      {checkoutLoading === plan.name ? (
                        <><Loader2 className="w-4 h-4 animate-spin" /> Redirecting…</>
                      ) : (
                        `Upgrade to ${plan.name}`
                      )}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Manage existing subscription */}
        {isSubscribed && (
          <div className="text-center">
            <p className="text-xs text-muted-foreground">
              Need to update payment method, download invoices, or cancel?{" "}
              <button
                onClick={() => void handlePortal()}
                className="text-primary hover:underline"
              >
                Open billing portal
              </button>
            </p>
          </div>
        )}

        {/* Privacy note */}
        <div className="rounded-xl border border-white/6 bg-white/2 px-5 py-4 text-center">
          <p className="text-xs text-muted-foreground">
            Payments are processed securely by <strong className="text-foreground">Stripe</strong>. GAAIA never stores your card details.
            All your AI data stays on your machine regardless of plan.
          </p>
        </div>
      </div>
    </AppShell>
  )
}

// Fallback when no plans are seeded (Stripe not configured)
function FallbackPlans({
  interval,
  currentTier,
  onUpgrade,
  checkoutLoading,
}: {
  interval: "month" | "year"
  currentTier: string
  onUpgrade: (plan: string) => void
  checkoutLoading: string | null
}) {
  const FALLBACK = [
    {
      name: "Free",
      price: { month: 0, year: 0 },
      max_seats: 1,
      features: ["1 user", "Local Ollama models", "Chat & voice", "10 MB file uploads", "Web Watch (3 topics)"],
    },
    {
      name: "Pro",
      price: { month: 1200, year: 9600 },
      max_seats: 1,
      features: ["Everything in Free", "Unlimited file uploads", "Unlimited Web Watch topics", "Scheduled automations", "Priority support", "Early access to new features"],
    },
    {
      name: "Teams",
      price: { month: 3500, year: 28000 },
      max_seats: 10,
      features: ["Everything in Pro", "Up to 10 team members", "Shared knowledge base", "Admin dashboard", "Audit logs", "SSO (coming soon)"],
    },
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {FALLBACK.map(plan => {
        const Icon = PLAN_ICONS[plan.name] ?? Zap
        const isCurrentPlan = currentTier.toLowerCase() === plan.name.toLowerCase()
        const price = plan.price[interval]

        return (
          <div
            key={plan.name}
            className={cn(
              "relative rounded-2xl border p-6 flex flex-col gap-5",
              PLAN_COLORS[plan.name] ?? "border-white/8 bg-white/2",
              plan.name === "Pro" && "ring-1 ring-indigo-500/20"
            )}
          >
            {plan.name === "Pro" && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                <span className="text-[10px] font-bold px-3 py-1 rounded-full bg-indigo-600 text-white border border-indigo-400/30">
                  MOST POPULAR
                </span>
              </div>
            )}

            <div className="flex items-center gap-3">
              <div className={cn(
                "w-10 h-10 rounded-xl flex items-center justify-center border",
                plan.name === "Pro" ? "bg-indigo-500/20 border-indigo-400/25" :
                plan.name === "Teams" ? "bg-violet-500/20 border-violet-400/25" :
                "bg-white/7 border-white/10"
              )}>
                <Icon className={cn(
                  "w-5 h-5",
                  plan.name === "Pro" ? "text-indigo-400" :
                  plan.name === "Teams" ? "text-violet-400" : "text-white/50"
                )} />
              </div>
              <div>
                <p className="font-semibold">{plan.name}</p>
                <p className="text-xs text-muted-foreground">
                  {plan.max_seats ? `Up to ${plan.max_seats} seat${plan.max_seats > 1 ? "s" : ""}` : "Unlimited"}
                </p>
              </div>
            </div>

            <div>
              <span className="text-3xl font-bold">{price === 0 ? "Free" : `$${(price / 100).toFixed(0)}`}</span>
              {price > 0 && (
                <span className="text-sm text-muted-foreground ml-1">/{interval === "month" ? "mo" : "yr"}</span>
              )}
            </div>

            <ul className="space-y-2 flex-1">
              {plan.features.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                  {f}
                </li>
              ))}
            </ul>

            {isCurrentPlan ? (
              <div className="w-full py-2.5 rounded-xl text-center text-sm font-medium bg-white/6 text-white/50 border border-white/8">
                Current plan
              </div>
            ) : price === 0 ? (
              <div className="w-full py-2.5 rounded-xl text-center text-sm font-medium bg-white/4 text-white/30 border border-white/6 cursor-not-allowed">
                Default
              </div>
            ) : (
              <button
                onClick={() => onUpgrade(plan.name)}
                disabled={checkoutLoading === plan.name}
                className={cn(
                  "w-full py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-60 flex items-center justify-center gap-2",
                  PLAN_BUTTON_COLORS[plan.name] ?? "bg-white/10 text-white"
                )}
              >
                {checkoutLoading === plan.name ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Redirecting…</>
                ) : (
                  `Upgrade to ${plan.name}`
                )}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function BillingPage() {
  return (
    <Suspense>
      <BillingPageContent />
    </Suspense>
  )
}
