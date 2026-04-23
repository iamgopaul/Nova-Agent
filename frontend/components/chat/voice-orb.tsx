"use client"

import { useEffect, useRef, useMemo } from "react"
import { cn } from "@/lib/utils"

interface VoiceOrbProps {
  state: "idle" | "listening" | "thinking" | "speaking"
  className?: string
}

export function VoiceOrb({ state, className }: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animationRef = useRef<number>(0)
  const timeRef = useRef(0)

  // Generate blob points with memo
  const blobPoints = useMemo(() => {
    const points: { angle: number; radius: number; speed: number; offset: number }[] = []
    const numPoints = 64
    for (let i = 0; i < numPoints; i++) {
      points.push({
        angle: (i / numPoints) * Math.PI * 2,
        radius: 0.85 + Math.random() * 0.15,
        speed: 0.5 + Math.random() * 1.5,
        offset: Math.random() * Math.PI * 2,
      })
    }
    return points
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const size = 280
    canvas.width = size * dpr
    canvas.height = size * dpr
    canvas.style.width = `${size}px`
    canvas.style.height = `${size}px`
    ctx.scale(dpr, dpr)

    const centerX = size / 2
    const centerY = size / 2
    const baseRadius = 90

    function getIntensity() {
      switch (state) {
        case "idle": return 0.02
        case "listening": return 0.08
        case "thinking": return 0.12
        case "speaking": return 0.25
        default: return 0.02
      }
    }

    function getSpeed() {
      switch (state) {
        case "idle": return 0.3
        case "listening": return 0.6
        case "thinking": return 1.2
        case "speaking": return 2.0
        default: return 0.3
      }
    }

    // Gemini colors - blue, cyan, purple gradients
    function getGradientColors(): [string, string, string, string] {
      switch (state) {
        case "idle":
          return ["#4285F4", "#34A0D9", "#7B61FF", "#4285F4"]
        case "listening":
          return ["#34A0D9", "#4285F4", "#EA4335", "#34A0D9"]
        case "thinking":
          return ["#7B61FF", "#4285F4", "#34A0D9", "#7B61FF"]
        case "speaking":
          return ["#4285F4", "#34A0D9", "#7B61FF", "#EA4335"]
        default:
          return ["#4285F4", "#34A0D9", "#7B61FF", "#4285F4"]
      }
    }

    function draw() {
      const intensity = getIntensity()
      const speed = getSpeed()
      timeRef.current += 0.016 * speed

      ctx.clearRect(0, 0, size, size)

      // Draw multiple layers for depth
      const layers = state === "speaking" ? 4 : 3
      
      for (let layer = 0; layer < layers; layer++) {
        const layerOpacity = layer === 0 ? 1 : 0.15 - layer * 0.03
        const layerScale = 1 + layer * 0.15
        const layerTimeOffset = layer * 0.5

        ctx.save()
        ctx.globalAlpha = layerOpacity

        // Create blob path
        ctx.beginPath()

        const points: { x: number; y: number }[] = []
        
        for (let i = 0; i < blobPoints.length; i++) {
          const p = blobPoints[i]
          
          // Multiple wave frequencies for organic movement
          const wave1 = Math.sin(timeRef.current * p.speed + p.offset + layerTimeOffset) * intensity
          const wave2 = Math.sin(timeRef.current * p.speed * 0.7 + p.offset * 1.3 + layerTimeOffset) * intensity * 0.5
          const wave3 = Math.cos(timeRef.current * p.speed * 1.3 + p.offset * 0.7 + layerTimeOffset) * intensity * 0.3
          
          // Extra "speaking" animation - rapid micro-vibrations
          const speakWave = state === "speaking" 
            ? Math.sin(timeRef.current * 8 + p.angle * 3) * 0.03 
            : 0
          
          const r = baseRadius * layerScale * (p.radius + wave1 + wave2 + wave3 + speakWave)
          const x = centerX + Math.cos(p.angle) * r
          const y = centerY + Math.sin(p.angle) * r
          
          points.push({ x, y })
        }

        // Draw smooth curve through points
        ctx.moveTo(points[0].x, points[0].y)
        
        for (let i = 0; i < points.length; i++) {
          const p0 = points[(i - 1 + points.length) % points.length]
          const p1 = points[i]
          const p2 = points[(i + 1) % points.length]
          const p3 = points[(i + 2) % points.length]

          const cp1x = p1.x + (p2.x - p0.x) / 6
          const cp1y = p1.y + (p2.y - p0.y) / 6
          const cp2x = p2.x - (p3.x - p1.x) / 6
          const cp2y = p2.y - (p3.y - p1.y) / 6

          ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
        }

        ctx.closePath()

        // Create gradient fill
        const colors = getGradientColors()
        const gradientAngle = timeRef.current * 0.5
        const gx1 = centerX + Math.cos(gradientAngle) * baseRadius
        const gy1 = centerY + Math.sin(gradientAngle) * baseRadius
        const gx2 = centerX + Math.cos(gradientAngle + Math.PI) * baseRadius
        const gy2 = centerY + Math.sin(gradientAngle + Math.PI) * baseRadius

        const gradient = ctx.createLinearGradient(gx1, gy1, gx2, gy2)
        gradient.addColorStop(0, colors[0])
        gradient.addColorStop(0.33, colors[1])
        gradient.addColorStop(0.66, colors[2])
        gradient.addColorStop(1, colors[3])

        ctx.fillStyle = gradient
        ctx.fill()

        // Add subtle inner glow for first layer
        if (layer === 0) {
          const innerGlow = ctx.createRadialGradient(
            centerX, centerY, 0,
            centerX, centerY, baseRadius
          )
          innerGlow.addColorStop(0, "rgba(255, 255, 255, 0.3)")
          innerGlow.addColorStop(0.5, "rgba(255, 255, 255, 0.1)")
          innerGlow.addColorStop(1, "rgba(255, 255, 255, 0)")
          ctx.fillStyle = innerGlow
          ctx.fill()
        }

        ctx.restore()
      }

      // Outer glow
      ctx.save()
      ctx.globalAlpha = state === "speaking" ? 0.4 : state === "thinking" ? 0.3 : 0.2
      ctx.filter = "blur(20px)"
      ctx.beginPath()
      ctx.arc(centerX, centerY, baseRadius * 0.8, 0, Math.PI * 2)
      const glowGradient = ctx.createRadialGradient(
        centerX, centerY, 0,
        centerX, centerY, baseRadius
      )
      glowGradient.addColorStop(0, "#4285F4")
      glowGradient.addColorStop(0.5, "#7B61FF")
      glowGradient.addColorStop(1, "transparent")
      ctx.fillStyle = glowGradient
      ctx.fill()
      ctx.restore()

      animationRef.current = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      cancelAnimationFrame(animationRef.current)
    }
  }, [state, blobPoints])

  return (
    <div className={cn("relative flex items-center justify-center", className)}>
      <canvas
        ref={canvasRef}
        className="w-[280px] h-[280px]"
      />
      
      {/* State indicator ring */}
      <div
        className={cn(
          "absolute inset-0 rounded-full border-2 transition-all duration-500",
          state === "listening" && "border-blue-400/30 animate-pulse",
          state === "thinking" && "border-purple-400/30 animate-pulse",
          state === "speaking" && "border-cyan-400/40",
          state === "idle" && "border-transparent"
        )}
        style={{ margin: "auto", width: 260, height: 260 }}
      />
    </div>
  )
}
