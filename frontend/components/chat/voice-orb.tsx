"use client"

import { useEffect, useRef } from "react"
import { cn } from "@/lib/utils"

interface VoiceOrbProps {
  state: "idle" | "listening" | "thinking" | "speaking"
  className?: string
}

// ─── Color palettes per state (matches home “GAAIA Voice” card: cyan + teal) ─
const PALETTE = {
  idle:      { core: "#0d9488", mid: "#2dd4bf", outer: "#134e4a", glow: "20,184,166" },
  listening: { core: "#06b6d4", mid: "#22d3ee", outer: "#164e63", glow: "6,182,212"  },
  thinking:  { core: "#0e7490", mid: "#5eead4", outer: "#134e4a", glow: "20,184,166" },
  speaking:  { core: "#22d3ee", mid: "#99f6e4", outer: "#0f766e", glow: "6,182,212" },
}

export function VoiceOrb({ state, className }: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef    = useRef<number>(0)
  const tRef      = useRef(0)
  // Smoothly interpolated state intensity (0 = fully idle, 1 = fully active)
  const intensityRef = useRef(0)
  // Ripple rings for listening / speaking  state
  const ringsRef = useRef<{ r: number; alpha: number; speed: number }[]>([])
  // Orbiting particles for thinking state
  const particlesRef = useRef<{ angle: number; speed: number; dist: number; size: number; alpha: number }[]>([])
  // Frequency bars for speaking state
  const barsRef = useRef<number[]>(Array.from({ length: 48 }, () => 0.1 + Math.random() * 0.3))

  // Initialise constant data
  useEffect(() => {
    particlesRef.current = Array.from({ length: 24 }, (_, i) => ({
      angle: (i / 24) * Math.PI * 2,
      speed: 0.008 + Math.random() * 0.012,
      dist:  70 + Math.random() * 30,
      size:  1.5 + Math.random() * 2.5,
      alpha: 0.4 + Math.random() * 0.6,
    }))
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")!
    if (!ctx) return

    const dpr  = window.devicePixelRatio || 1
    const SIZE = 340
    canvas.width  = SIZE * dpr
    canvas.height = SIZE * dpr
    canvas.style.width  = `${SIZE}px`
    canvas.style.height = `${SIZE}px`
    ctx.scale(dpr, dpr)

    const cx = SIZE / 2
    const cy = SIZE / 2
    const R  = 80   // core radius

    // ── target intensities ────────────────────────────────────────────────────
    const TARGET_INTENSITY = { idle: 0.06, listening: 0.55, thinking: 0.45, speaking: 0.85 }
    const TARGET_SPEED     = { idle: 0.3,  listening: 0.9,  thinking: 1.4,  speaking: 1.8  }

    // ── spawn rings periodically ──────────────────────────────────────────────
    let lastRingSpawn = 0

    function spawnRing() {
      ringsRef.current.push({ r: R * 0.6, alpha: 0.7, speed: 1.2 + Math.random() })
      if (ringsRef.current.length > 8) ringsRef.current.shift()
    }

    function draw() {
      const now    = performance.now() / 1000
      const dt     = 0.016
      tRef.current += dt * TARGET_SPEED[state]

      // Smooth intensity towards target
      const target = TARGET_INTENSITY[state]
      intensityRef.current += (target - intensityRef.current) * 0.06
      const intensity = intensityRef.current

      // Spawn ripple rings
      const ringInterval = state === "speaking" ? 0.25 : state === "listening" ? 0.5 : 2.5
      if (now - lastRingSpawn > ringInterval && state !== "idle" && state !== "thinking") {
        spawnRing()
        lastRingSpawn = now
      }

      ctx.clearRect(0, 0, SIZE, SIZE)
      const pal = PALETTE[state]
      const t   = tRef.current

      // ═══════════════════════════════════════════════════════════════════════
      // 1. Background ambient glow
      // ═══════════════════════════════════════════════════════════════════════
      const breathe = 1 + Math.sin(t * 0.8) * 0.08
      const ambGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 2.8 * breathe)
      ambGlow.addColorStop(0,   `rgba(${pal.glow},${0.18 + intensity * 0.12})`)
      ambGlow.addColorStop(0.4, `rgba(${pal.glow},${0.07 + intensity * 0.06})`)
      ambGlow.addColorStop(1,   "rgba(0,0,0,0)")
      ctx.fillStyle = ambGlow
      ctx.fillRect(0, 0, SIZE, SIZE)

      // ═══════════════════════════════════════════════════════════════════════
      // 2. Ripple rings  (listening / speaking)
      // ═══════════════════════════════════════════════════════════════════════
      ringsRef.current = ringsRef.current.filter(ring => ring.alpha > 0.01)
      for (const ring of ringsRef.current) {
        ring.r     += ring.speed * 2.5
        ring.alpha *= 0.965
        ctx.beginPath()
        ctx.arc(cx, cy, ring.r, 0, Math.PI * 2)
        ctx.strokeStyle = `rgba(${pal.glow},${ring.alpha * 0.7})`
        ctx.lineWidth   = 1.5
        ctx.stroke()
      }

      // ═══════════════════════════════════════════════════════════════════════
      // 3. Rotating arc segments  (thinking)
      // ═══════════════════════════════════════════════════════════════════════
      if (state === "thinking") {
        const segments = 6
        const gap      = 0.28
        const arcR     = R + 22
        for (let i = 0; i < segments; i++) {
          const start = t * 1.4 + (i / segments) * Math.PI * 2
          const end   = start + (Math.PI * 2 / segments) - gap
          const alpha = 0.5 + 0.5 * Math.sin(t * 2 + i)
          ctx.beginPath()
          ctx.arc(cx, cy, arcR, start, end)
          ctx.strokeStyle = `rgba(${pal.glow},${alpha * 0.9})`
          ctx.lineWidth   = 3
          ctx.lineCap     = "round"
          ctx.stroke()
        }
        // Counter-rotate inner ring
        const innerR = R + 10
        const seg2   = 3
        for (let i = 0; i < seg2; i++) {
          const start = -t * 2.2 + (i / seg2) * Math.PI * 2
          const end   = start + (Math.PI * 2 / seg2) - 0.6
          ctx.beginPath()
          ctx.arc(cx, cy, innerR, start, end)
          ctx.strokeStyle = `rgba(${pal.glow},0.4)`
          ctx.lineWidth   = 1.5
          ctx.lineCap     = "round"
          ctx.stroke()
        }
      }

      // ═══════════════════════════════════════════════════════════════════════
      // 4. Radial frequency bars  (speaking)
      // ═══════════════════════════════════════════════════════════════════════
      if (state === "speaking") {
        const bars   = barsRef.current
        const numBars = bars.length
        for (let i = 0; i < numBars; i++) {
          // Animate bar heights with independent sine waves
          bars[i] = 0.15 + 0.6 * Math.abs(Math.sin(t * (3 + i * 0.3) + i * 0.5))
          const angle  = (i / numBars) * Math.PI * 2 - Math.PI / 2
          const inner  = R + 4
          const outer  = R + 4 + bars[i] * 44
          const x1 = cx + Math.cos(angle) * inner
          const y1 = cy + Math.sin(angle) * inner
          const x2 = cx + Math.cos(angle) * outer
          const y2 = cy + Math.sin(angle) * outer
          const alpha = 0.5 + bars[i] * 0.5
          ctx.beginPath()
          ctx.moveTo(x1, y1)
          ctx.lineTo(x2, y2)
          ctx.strokeStyle = `rgba(${pal.glow},${alpha})`
          ctx.lineWidth   = 2.5
          ctx.lineCap     = "round"
          ctx.stroke()
        }
      }

      // ═══════════════════════════════════════════════════════════════════════
      // 5. Orbiting particles  (thinking + idle)
      // ═══════════════════════════════════════════════════════════════════════
      if (state === "thinking" || state === "idle") {
        const speedMult = state === "thinking" ? 1.6 : 0.35
        for (const p of particlesRef.current) {
          p.angle += p.speed * speedMult
          const px = cx + Math.cos(p.angle) * p.dist
          const py = cy + Math.sin(p.angle) * p.dist
          const fade = state === "idle" ? 0.25 : 0.7
          ctx.beginPath()
          ctx.arc(px, py, p.size * (state === "thinking" ? 1.2 : 0.7), 0, Math.PI * 2)
          ctx.fillStyle = `rgba(${pal.glow},${p.alpha * fade})`
          ctx.fill()
        }
      }

      // ═══════════════════════════════════════════════════════════════════════
      // 6. Core orb — morphing blob
      // ═══════════════════════════════════════════════════════════════════════
      const numPts = 80
      const pts: { x: number; y: number }[] = []
      for (let i = 0; i < numPts; i++) {
        const angle = (i / numPts) * Math.PI * 2
        const w1 = Math.sin(t * 1.1 + angle * 3) * intensity
        const w2 = Math.sin(t * 0.7 + angle * 5 + 1.2) * intensity * 0.5
        const w3 = Math.cos(t * 1.4 + angle * 2 + 2.4) * intensity * 0.3
        // speaking micro-vibration
        const sv = state === "speaking" ? Math.sin(t * 12 + angle * 7) * 0.06 : 0
        const r  = R * (1 + w1 + w2 + w3 + sv)
        pts.push({ x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r })
      }

      ctx.beginPath()
      ctx.moveTo(pts[0].x, pts[0].y)
      for (let i = 0; i < pts.length; i++) {
        const a  = pts[i]
        const b  = pts[(i + 1) % pts.length]
        const cpx = (a.x + b.x) / 2
        const cpy = (a.y + b.y) / 2
        ctx.quadraticCurveTo(a.x, a.y, cpx, cpy)
      }
      ctx.closePath()

      // Rotating gradient fill
      const ga = t * 0.4
      const grad = ctx.createLinearGradient(
        cx + Math.cos(ga)       * R, cy + Math.sin(ga)       * R,
        cx + Math.cos(ga + Math.PI) * R, cy + Math.sin(ga + Math.PI) * R
      )
      grad.addColorStop(0,    pal.core)
      grad.addColorStop(0.5,  pal.mid)
      grad.addColorStop(1,    pal.outer)
      ctx.fillStyle = grad
      ctx.fill()

      // Inner highlight
      const hi = ctx.createRadialGradient(cx - R * 0.25, cy - R * 0.25, 0, cx, cy, R)
      hi.addColorStop(0,   "rgba(255,255,255,0.30)")
      hi.addColorStop(0.4, "rgba(255,255,255,0.06)")
      hi.addColorStop(1,   "rgba(255,255,255,0)")
      ctx.fillStyle = hi
      ctx.fill()

      // ═══════════════════════════════════════════════════════════════════════
      // 7. Outer glow bloom
      // ═══════════════════════════════════════════════════════════════════════
      const glowAlpha = 0.15 + intensity * 0.35
      ctx.save()
      ctx.filter = "blur(18px)"
      ctx.globalAlpha = glowAlpha
      const bloom = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.4)
      bloom.addColorStop(0, pal.core)
      bloom.addColorStop(1, "transparent")
      ctx.fillStyle = bloom
      ctx.beginPath()
      ctx.arc(cx, cy, R * 1.4, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()

      rafRef.current = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(rafRef.current)
  }, [state])

  return (
    <div className={cn("relative flex flex-col items-center justify-center gap-4 select-none", className)}>
      {/* Canvas orb */}
      <div className="relative">
        <canvas ref={canvasRef} className="w-[340px] h-[340px]" />
        {/* State label ring beneath the orb */}
        <div className={cn(
          "absolute inset-0 m-auto rounded-full pointer-events-none transition-all duration-700",
          "border",
          state === "idle"      && "border-teal-500/25",
          state === "listening" && "border-cyan-400/40 animate-pulse",
          state === "thinking"  && "border-teal-400/35",
          state === "speaking"  && "border-cyan-300/50",
        )} style={{ width: 178, height: 178 }} />
      </div>

      {/* Status pill */}
      <div className={cn(
        "flex items-center gap-2 px-4 py-1.5 rounded-full border text-xs font-semibold tracking-wide transition-all duration-500",
        state === "idle"      && "bg-teal-950/50 border-teal-500/30 text-teal-200/80",
        state === "listening" && "bg-cyan-950/60   border-cyan-400/35  text-cyan-300",
        state === "thinking"  && "bg-teal-950/55 border-cyan-400/30 text-cyan-200/90",
        state === "speaking"  && "bg-cyan-950/60 border-cyan-300/40 text-cyan-100",
      )}>
        {/* Animated dot */}
        <span className={cn(
          "w-1.5 h-1.5 rounded-full",
          state === "idle"      && "bg-teal-400/70",
          state === "listening" && "bg-cyan-400 animate-ping",
          state === "thinking"  && "bg-teal-400 animate-spin",
          state === "speaking"  && "bg-cyan-300 animate-pulse",
        )} />
        {state === "idle"      && "Ready"}
        {state === "listening" && "Listening…"}
        {state === "thinking"  && "Thinking…"}
        {state === "speaking"  && "Speaking"}
      </div>
    </div>
  )
}
