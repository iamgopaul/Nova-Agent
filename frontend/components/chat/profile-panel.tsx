"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Camera, CheckCircle, Loader2, User, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { fingerSegmentDisplayLabel, mapNormBoxToDisplayPixels } from "@/lib/camera-overlay"

interface FaceProfile {
  name: string
  sample_count: number
  enrolled_at: number
}

interface IdentitySummary {
  name: string
  has_face: boolean
  has_voice: boolean
  face_samples: number
  voice_samples: number
  total_samples: number
}

interface ProfilePanelProps {
  onClose: () => void
}

export function ProfilePanel({ onClose }: ProfilePanelProps) {
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
  const [enrollName, setEnrollName] = useState("Josh Gopaul")
  const [status, setStatus] = useState<{ type: "success" | "error" | "info"; msg: string } | null>(null)
  const [loadingProfiles, setLoadingProfiles] = useState(true)

  type Detection = { label: string; type: string; confidence: number; box: { x: number; y: number; w: number; h: number } }

  const drawDetections = useCallback((detections: Detection[]) => {
    const canvas = canvasRef.current
    const video = videoRef.current
    if (!canvas || !video) return

    const rect = video.getBoundingClientRect()
    const displayWidth = Math.max(1, rect.width || video.clientWidth || 320)
    const displayHeight = Math.max(1, rect.height || video.clientHeight || 240)
    const dpr = window.devicePixelRatio || 1

    canvas.width = Math.round(displayWidth * dpr)
    canvas.height = Math.round(displayHeight * dpr)
    canvas.style.width = `${displayWidth}px`
    canvas.style.height = `${displayHeight}px`

    const ctx = canvas.getContext("2d")
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, displayWidth, displayHeight)

    const typeOrder: Record<string, number> = {
      body: 0,
      body_part: 1,
      face: 2,
      object: 3,
      hand: 4,
      finger: 5,
    }
    const sorted = [...detections].sort(
      (a, b) => (typeOrder[a.type] ?? 2) - (typeOrder[b.type] ?? 2),
    )

    const mirrorOverlayX = true
    for (const det of sorted) {
      const { x, y, w, h } = mapNormBoxToDisplayPixels(
        det.box,
        video,
        displayWidth,
        displayHeight,
        mirrorOverlayX,
      )
      if (!Number.isFinite(x + y + w + h) || w <= 0 || h <= 0) continue
      const isFinger = det.type === "finger"
      const color =
        det.type === "face" ? "#22d3ee" :
        det.type === "hand" ? "#f97316" :
        det.type === "finger" ? "#fdba74" :
        det.type === "body" || det.type === "body_part" ? "#a78bfa" :
        "#a3e635"

      const labelText = isFinger
        ? fingerSegmentDisplayLabel(det.label)
        : `${det.label} ${Math.round(det.confidence * 100)}%`

      const lineW =
        isFinger ? 1.35 :
        det.type === "body_part" ? 1.5 :
        3
      ctx.strokeStyle = color
      ctx.lineWidth = lineW
      ctx.strokeRect(x, y, w, h)

      ctx.font = isFinger
        ? "600 10px ui-sans-serif, system-ui, sans-serif"
        : det.type === "body_part"
          ? "600 10px ui-sans-serif, system-ui, sans-serif"
          : "bold 12px ui-sans-serif, system-ui, sans-serif"
      const pillH = isFinger ? 14 : 18
      const textPad = isFinger ? 6 : 8
      const textW = ctx.measureText(labelText).width
      const labelY = y > 18 ? y - 4 : y + h + 14
      ctx.fillStyle = color
      ctx.globalAlpha = 0.9
      ctx.fillRect(x - 1, labelY - pillH, textW + textPad, pillH)
      ctx.globalAlpha = 1
      ctx.fillStyle = "#04111f"
      ctx.fillText(labelText, x + 2, labelY - 4)
    }
  }, [])

  const fetchProfiles = useCallback(async () => {
    try {
      const res = await fetch("/api/camera/identities")
      if (res.ok) {
        const data = await res.json()
        setProfiles(Array.isArray(data) ? data : [])
      }
    } catch {
      /* ignore */
    } finally {
      setLoadingProfiles(false)
    }
  }, [])

  useEffect(() => {
    void fetchProfiles()
  }, [fetchProfiles])

  const captureFrame = useCallback((): Promise<Blob | null> => {
    return new Promise(resolve => {
      const video = videoRef.current
      const canvas = canvasRef.current
      if (!video || !canvas || video.readyState < 2) return resolve(null)
      canvas.width = video.videoWidth || 640
      canvas.height = video.videoHeight || 480
      const ctx = canvas.getContext("2d")
      if (!ctx) return resolve(null)
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      canvas.toBlob(blob => resolve(blob), "image/jpeg", 0.92)
    })
  }, [])

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
      }
      setCameraActive(true)
      setStatus({ type: "info", msg: "Camera ready. Position your face clearly and click Enroll." })

      let detectInFlight = false
      detectIntervalRef.current = setInterval(async () => {
        if (detectInFlight) return
        detectInFlight = true
        try {
          const frame = await captureFrame()
          if (!frame) return
          const form = new FormData()
          form.append("image", frame, "frame.jpg")
          const res = await fetch("/api/camera/detect", { method: "POST", body: form })
          if (res.ok) {
            const data = await res.json() as { detections: Detection[] }
            drawDetections(data.detections || [])
          }
        } catch {
          // best-effort visual feedback only
        } finally {
          detectInFlight = false
        }
      }, 400)
    } catch {
      setStatus({ type: "error", msg: "Could not access camera. Check browser permissions." })
    }
  }, [captureFrame, drawDetections])

  const stopCamera = useCallback(() => {
    if (detectIntervalRef.current !== null) {
      clearInterval(detectIntervalRef.current)
      detectIntervalRef.current = null
    }
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    const canvas = canvasRef.current
    if (canvas) {
      const ctx = canvas.getContext("2d")
      ctx?.clearRect(0, 0, canvas.width, canvas.height)
    }
    setCameraActive(false)
  }, [])

  const stopVoiceEnrollment = useCallback(() => {
    if (voiceStopTimerRef.current !== null) {
      clearTimeout(voiceStopTimerRef.current)
      voiceStopTimerRef.current = null
    }
    voiceRecorderRef.current?.stop()
    voiceRecorderRef.current = null
    voiceStreamRef.current?.getTracks().forEach(track => track.stop())
    voiceStreamRef.current = null
  }, [])

  useEffect(() => {
    return () => {
      stopVoiceEnrollment()
    }
  }, [stopVoiceEnrollment])

  useEffect(() => {
    void startCamera()
    return () => stopCamera()
  }, [startCamera, stopCamera])

  const enrollFace = useCallback(async () => {
    const name = enrollName.trim()
    if (!name) {
      setStatus({ type: "error", msg: "Enter a name before enrolling." })
      return
    }
    if (!cameraActive) {
      setStatus({ type: "error", msg: "Start the camera first." })
      return
    }

    setEnrolling(true)
    setStatus({ type: "info", msg: "Capturing 8 frames — hold still and look at the camera..." })

    const frames: Blob[] = []
    for (let i = 0; i < 8; i++) {
      await new Promise(r => setTimeout(r, 350))
      const blob = await captureFrame()
      if (blob) frames.push(blob)
    }

    if (frames.length < 3) {
      setStatus({ type: "error", msg: "Couldn't capture enough frames. Try better lighting." })
      setEnrolling(false)
      return
    }

    try {
      const form = new FormData()
      form.append("name", name)
      frames.forEach((f, i) => form.append("images", f, `frame_${i}.jpg`))

      const res = await fetch("/api/camera/enroll", { method: "POST", body: form })
      if (res.ok) {
        const data = await res.json()
        setStatus({ type: "success", msg: `Enrolled "${data.name}" with ${data.sample_count} face samples.` })
        void fetchProfiles()
      } else {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }))
        setStatus({ type: "error", msg: `Enrollment failed: ${err.detail}` })
      }
    } catch (e) {
      setStatus({ type: "error", msg: `Network error: ${String(e)}` })
    } finally {
      setEnrolling(false)
    }
  }, [cameraActive, captureFrame, enrollName, fetchProfiles])

  const enrollVoice = useCallback(async () => {
    const name = enrollName.trim()
    if (!name) {
      setStatus({ type: "error", msg: "Enter a name before enrolling voice." })
      return
    }
    if (voiceEnrolling) {
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      voiceStreamRef.current = stream

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : ""
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
      voiceRecorderRef.current = recorder
      const chunks: BlobPart[] = []

      setVoiceEnrolling(true)
      setStatus({ type: "info", msg: "Recording a short voice sample. Say your name clearly." })

      const sample = await new Promise<Blob>((resolve, reject) => {
        recorder.ondataavailable = event => {
          if (event.data.size > 0) {
            chunks.push(event.data)
          }
        }
        recorder.onerror = () => reject(new Error("Voice recorder failed."))
        recorder.onstop = () => {
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" })
          resolve(blob)
        }
        recorder.start()
        voiceStopTimerRef.current = setTimeout(() => {
          if (recorder.state === "recording") {
            recorder.stop()
          }
        }, 4500)
      })

      voiceStopTimerRef.current = null
      stream.getTracks().forEach(track => track.stop())
      voiceStreamRef.current = null
      voiceRecorderRef.current = null

      if (sample.size === 0) {
        setStatus({ type: "error", msg: "No voice audio was captured." })
        return
      }

      const form = new FormData()
      form.append("name", name)
      form.append("audio", sample, "voice.webm")

      const res = await fetch("/api/voice/enroll", { method: "POST", body: form })
      if (res.ok) {
        const data = await res.json()
        setStatus({ type: "success", msg: `Enrolled voice for "${data.name}".` })
        void fetchProfiles()
      } else {
        const err = await res.json().catch(() => ({ detail: "Unknown error" }))
        setStatus({ type: "error", msg: `Voice enrollment failed: ${err.detail}` })
      }
    } catch (error) {
      voiceStreamRef.current?.getTracks().forEach(track => track.stop())
      voiceStreamRef.current = null
      voiceRecorderRef.current = null
      setStatus({ type: "error", msg: `Could not access microphone. ${String(error)}` })
    } finally {
      setVoiceEnrolling(false)
    }
  }, [enrollName, fetchProfiles, voiceEnrolling])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-background border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <User className="w-5 h-5 text-primary" />
            <span className="font-semibold text-sm">Identity & Recognition</span>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-5 max-h-[80vh] overflow-y-auto">
          <section className="rounded-xl border border-cyan-400/20 bg-cyan-500/5 p-4 text-sm text-foreground/90">
            <p className="font-semibold text-cyan-300">How to enroll your face</p>
            <ol className="mt-2 space-y-1 text-sm text-muted-foreground list-decimal list-inside">
              <li>Allow camera access when Nova asks.</li>
              <li>Keep your face centered and well lit.</li>
              <li>Use your name, then click Enroll Face.</li>
            </ol>
            <p className="mt-2 text-xs text-muted-foreground">
              You only need to do this once on this device. Nova will keep the face profile locally.
            </p>
          </section>

          {/* Enrolled profiles */}
          <section>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Enrolled Users
            </h3>
            <p className="mb-2 text-xs text-muted-foreground">
              This is the list of people Nova can recognize on this device. It only shows whether face and/or voice data are stored.
            </p>
            {loadingProfiles ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading...
              </div>
            ) : profiles.length === 0 ? (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">No users are enrolled yet.</p>
                <p className="text-xs text-muted-foreground">Start the camera and enroll once so Nova can remember this person in future chats.</p>
              </div>
            ) : (
              <ul className="space-y-1.5">
                {profiles.map(p => (
                  <li key={p.name} className="flex items-center justify-between gap-3 bg-muted/50 rounded-lg px-3 py-2">
                    <div>
                      <span className="text-sm font-medium">{p.name}</span>
                      <span className="ml-2 text-xs text-muted-foreground">{p.total_samples} stored sample{p.total_samples === 1 ? "" : "s"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={cn("text-[10px] px-2 py-0.5 rounded-full border", p.has_face ? "border-cyan-400/30 text-cyan-300 bg-cyan-500/10" : "border-white/10 text-white/35 bg-white/5")}>{p.has_face ? `Face ${p.face_samples}` : "No face"}</span>
                      <span className={cn("text-[10px] px-2 py-0.5 rounded-full border", p.has_voice ? "border-emerald-400/30 text-emerald-300 bg-emerald-500/10" : "border-white/10 text-white/35 bg-white/5")}>{p.has_voice ? `Voice ${p.voice_samples}` : "No voice"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Enroll new face */}
          <section>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              Enroll Your Face
            </h3>

            <div className="space-y-3">
              <input
                type="text"
                value={enrollName}
                onChange={e => setEnrollName(e.target.value)}
                placeholder="Enter the name Nova should remember"
                className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
              />

              <p className="text-xs text-muted-foreground">
                Use the same name for face and voice so Nova stores both under one private profile.
              </p>

              {/* Camera preview */}
              <div className="relative bg-black rounded-xl overflow-hidden aspect-video">
                <div className={cn("absolute inset-0", !cameraActive && "hidden")}>
                  <video
                    ref={videoRef}
                    muted
                    playsInline
                    className="absolute inset-0 z-10 w-full h-full object-cover -scale-x-100"
                  />
                  <canvas
                    ref={canvasRef}
                    className="absolute inset-0 z-20 w-full h-full pointer-events-none"
                  />
                </div>
                {!cameraActive && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/60">
                    <Camera className="w-8 h-8" />
                    <span className="text-xs">Camera off</span>
                  </div>
                )}
                {enrolling && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/50">
                    <div className="text-center text-white">
                      <Loader2 className="w-6 h-6 animate-spin mx-auto mb-1" />
                      <span className="text-xs">Capturing...</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Status */}
              {status && (
                <div className={cn(
                  "text-xs px-3 py-2 rounded-lg",
                  status.type === "success" && "bg-green-500/10 text-green-600 dark:text-green-400",
                  status.type === "error" && "bg-red-500/10 text-red-600 dark:text-red-400",
                  status.type === "info" && "bg-blue-500/10 text-blue-600 dark:text-blue-400",
                )}>
                  {status.type === "success" && <CheckCircle className="inline w-3.5 h-3.5 mr-1" />}
                  {status.msg}
                </div>
              )}

              {/* Buttons */}
              <div className="flex gap-2">
                {!cameraActive ? (
                  <button
                    onClick={() => void startCamera()}
                    className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-muted hover:bg-muted/80 text-sm font-medium transition-colors"
                  >
                    <Camera className="w-4 h-4" />
                    Start Camera
                  </button>
                ) : (
                  <button
                    onClick={stopCamera}
                    className="px-3 py-2 rounded-lg bg-muted hover:bg-muted/80 text-sm transition-colors"
                  >
                    Stop
                  </button>
                )}
                <button
                  onClick={() => void enrollFace()}
                  disabled={!cameraActive || enrolling || !enrollName.trim()}
                  className={cn(
                    "flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors",
                    cameraActive && !enrolling
                      ? "bg-primary text-primary-foreground hover:bg-primary/90"
                      : "bg-muted text-muted-foreground cursor-not-allowed opacity-50"
                  )}
                >
                  {enrolling ? <Loader2 className="w-4 h-4 animate-spin" /> : <User className="w-4 h-4" />}
                  {enrolling ? "Enrolling..." : "Enroll Face"}
                </button>
              </div>

              <button
                onClick={() => void enrollVoice()}
                disabled={voiceEnrolling || !enrollName.trim()}
                className={cn(
                  "w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors",
                  !voiceEnrolling && enrollName.trim()
                    ? "bg-emerald-500 text-white hover:bg-emerald-500/90"
                    : "bg-muted text-muted-foreground cursor-not-allowed opacity-50"
                )}
              >
                {voiceEnrolling ? <Loader2 className="w-4 h-4 animate-spin" /> : <User className="w-4 h-4" />}
                {voiceEnrolling ? "Recording Voice..." : "Enroll Voice"}
              </button>

              <p className="text-xs text-muted-foreground">
                Face the camera in good lighting for face enrollment. Voice enrollment records a short local sample after microphone access is granted.
              </p>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
