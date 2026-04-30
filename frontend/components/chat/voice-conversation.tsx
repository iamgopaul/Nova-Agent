"use client"

import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react"
import { Mic, MicOff, X, Volume2, VolumeX, Settings, Camera, User } from "lucide-react"
import { cn } from "@/lib/utils"
import { fingerSegmentDisplayLabel, mapNormBoxToDisplayPixels } from "@/lib/camera-overlay"
import { VoiceOrb } from "./voice-orb"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
import type { ChatModelKey } from "./chat-header"

interface VoiceConversationProps {
  onClose: () => void
  onOpenProfile: () => void
  sessionId: string
  modelKey: ChatModelKey
  onConversationTurn: (userText: string, assistantText: string) => void
  /** Render as an embedded panel (no fixed overlay) instead of full-screen. */
  embedded?: boolean
  /** Called when the internal camera stream starts or stops. Use to mirror the feed externally. */
  onCameraStream?: (stream: MediaStream | null) => void
}

type VoiceState = "idle" | "listening" | "thinking" | "speaking"

type VoiceDiagnosticStage =
  | "Idle"
  | "Requesting microphone"
  | "Capturing audio"
  | "Waiting for speech"
  | "Sending audio"
  | "Thinking"
  | "Transcribing"
  | "Retrying listen"
  | "Speaking"

type VoiceApiResponse = {
  transcript: string
  response: string
  session_id: string
}

type VoiceStreamEvent =
  | { type: "transcript"; text: string; session_id: string }
  | { type: "sentence"; text: string }
  | { type: "done"; response: string; session_id: string }
  | { type: "error"; detail: string }

/**
 * Open `/api/voice/stream` as an NDJSON stream and yield parsed events.
 * The stream surfaces the transcript the instant STT finishes, then each
 * sentence from the LLM as soon as it completes — so TTS can start while
 * GAAIA is still generating the rest of her reply.
 */
async function* streamVoiceTurn(
  audioBlob: Blob,
  sessionId: string,
  modelKey: string | undefined,
  signal: AbortSignal,
  camFrame: Blob | null,
): AsyncGenerator<VoiceStreamEvent> {
  const form = new FormData()
  // Use a filename that matches the blob's actual MIME type. Whisper/ffmpeg
  // sniffs content rather than extension, but a sane hint helps the upload
  // route log usefully and keeps multipart parsers happy on edge cases.
  const audioExt = (audioBlob.type || "").includes("webm") ? "webm"
    : (audioBlob.type || "").includes("mp4") || (audioBlob.type || "").includes("aac") ? "m4a"
    : "wav"
  form.append("audio", audioBlob, `turn.${audioExt}`)
  form.append("session_id", sessionId)
  form.append("mode", "fast")
  // Voice UX: pin a small tier when the UI is on Auto — Air (swift) balances
  // speed and quality; explicit model choice is always respected.
  const resolvedModel = !modelKey || modelKey === "auto" ? "air" : modelKey
  form.append("model_key", resolvedModel)
  if (camFrame && camFrame.size > 400) {
    form.append("camera_frame", camFrame, "turn_frame.jpg")
  }

  const response = await fetch("/api/voice/stream", {
    method: "POST",
    body: form,
    signal,
  })

  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => "")
    yield { type: "error", detail: detail || `Voice stream failed (${response.status})` }
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder("utf-8")
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (value) {
        buffer += decoder.decode(value, { stream: true })
      }
      let newlineIdx = buffer.indexOf("\n")
      while (newlineIdx >= 0) {
        const line = buffer.slice(0, newlineIdx).trim()
        buffer = buffer.slice(newlineIdx + 1)
        if (line) {
          try {
            yield JSON.parse(line) as VoiceStreamEvent
          } catch {
            // Skip malformed chunks.
          }
        }
        newlineIdx = buffer.indexOf("\n")
      }
      if (done) {
        break
      }
    }
    // Flush any trailing line (server may omit the final "\n").
    const tail = buffer.trim()
    if (tail) {
      try {
        yield JSON.parse(tail) as VoiceStreamEvent
      } catch {
        // Ignore.
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      // Already released.
    }
  }
}

type TtsSessionRefs = {
  stopRequestedRef: { current: boolean }
  bargeInRef: { current: boolean }
}

type TtsSession = {
  enqueue: (sentence: string) => void
  finish: () => void
  abort: () => void
  drain: () => Promise<void>
}

type TtsSessionOpts = { isMuted: boolean } & TtsSessionRefs & {
  /** If set, reuse this context (from a user-gesture unlock) instead of creating a new one. */
  playbackCtxRef?: MutableRefObject<AudioContext | null>
}

/**
 * Streaming TTS queue that plays sentences gap-lessly on a single
 * AudioContext. `enqueue` fires a request to `/api/voice/speak/stream`
 * for each sentence; the resulting WAV chunks are decoded and scheduled
 * back-to-back so consecutive sentences play without a perceptible gap.
 */
function createTtsSession(opts: TtsSessionOpts): TtsSession {
  const AC =
    typeof window !== "undefined"
      ? window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      : null

  const pendingSentences: string[] = []
  let ctx: AudioContext | null = null
  let ctxOwned = false
  let nextTime = 0
  let done = false
  let aborted = false
  let notifyWork: (() => void) | null = null

  const ensureContext = async (): Promise<AudioContext | null> => {
    if (aborted || opts.isMuted) return null
    if (ctx) return ctx
    const ext = opts.playbackCtxRef?.current
    if (ext && ext.state !== "closed") {
      try {
        if (ext.state === "suspended") {
          await ext.resume()
        }
      } catch {
        // ignore — playback will just be silent
      }
      ctx = ext
      ctxOwned = false
      nextTime = ctx.currentTime + 0.04
      return ctx
    }
    if (!AC) return null
    ctx = new AC()
    ctxOwned = true
    try {
      if (ctx.state === "suspended") {
        await ctx.resume()
      }
    } catch {
      // ignore — playback will just be silent
    }
    nextTime = ctx.currentTime + 0.04
    return ctx
  }

  const shouldStop = () =>
    aborted || opts.stopRequestedRef.current || opts.bargeInRef.current

  const playSentenceStream = async (text: string) => {
    if (!text || opts.isMuted || shouldStop()) return
    const audioCtx = await ensureContext()
    if (!audioCtx) return

    const controller = new AbortController()
    let response: Response
    try {
      response = await fetch("/api/voice/speak/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        signal: controller.signal,
      })
    } catch {
      return
    }

    if (!response.ok || !response.body) {
      try {
        await response.text()
      } catch {
        // ignore
      }
      return
    }

    const reader = response.body.getReader()
    let buf = new Uint8Array(0)

    try {
      while (true) {
        if (shouldStop()) {
          try {
            controller.abort()
          } catch {
            // ignore
          }
          break
        }
        const { done: streamDone, value } = await reader.read()
        if (value) {
          const next = new Uint8Array(buf.length + value.length)
          next.set(buf)
          next.set(value, buf.length)
          buf = next
        }
        while (buf.length >= 4) {
          const size = new DataView(buf.buffer, buf.byteOffset, 4).getUint32(0, true)
          if (buf.length < 4 + size) break
          const wavBytes = buf.slice(4, 4 + size)
          buf = buf.slice(4 + size)
          try {
            const audioBuffer = await audioCtx.decodeAudioData(wavBytes.slice(0).buffer)
            if (shouldStop()) break
            const startAt = Math.max(nextTime, audioCtx.currentTime)
            const source = audioCtx.createBufferSource()
            source.buffer = audioBuffer
            source.connect(audioCtx.destination)
            source.start(startAt)
            nextTime = startAt + audioBuffer.duration
          } catch {
            // malformed WAV chunk; skip
          }
        }
        if (streamDone) break
      }
    } finally {
      try {
        reader.releaseLock()
      } catch {
        // ignore
      }
    }
  }

  const processor = (async () => {
    while (!aborted) {
      while (pendingSentences.length === 0 && !done && !aborted) {
        await new Promise<void>((r) => {
          notifyWork = r
        })
      }
      if (aborted) break
      if (pendingSentences.length === 0 && done) break
      const next = pendingSentences.shift()!
      await playSentenceStream(next)
      if (shouldStop()) break
    }

    // Wait for scheduled audio to finish before closing the context so the
    // last sentence isn't cut off. We cache `ctx` to a local because TS's
    // closure flow analysis narrows the outer `ctx` to `null`.
    const tail = ctx as AudioContext | null
    if (tail) {
      try {
        const waitMs = Math.max(0, (nextTime - tail.currentTime) * 1000) + 60
        await new Promise<void>((r) => setTimeout(r, waitMs))
      } catch {
        // ignore
      }
      if (ctxOwned) {
        try {
          await tail.close()
        } catch {
          // ignore
        }
      }
      ctx = null
    }
  })()

  return {
    enqueue(sentence: string) {
      if (aborted || !sentence) return
      const trimmed = sentence.trim()
      if (!trimmed) return
      pendingSentences.push(trimmed)
      notifyWork?.()
      notifyWork = null
    },
    finish() {
      done = true
      notifyWork?.()
      notifyWork = null
    },
    abort() {
      aborted = true
      done = true
      notifyWork?.()
      notifyWork = null
      if (ctx && ctxOwned) {
        try {
          void ctx.close()
        } catch {
          // ignore
        }
      }
      ctx = null
    },
    drain() {
      return processor
    },
  }
}

async function getSpeechVoices(): Promise<SpeechSynthesisVoice[]> {
  if (!window.speechSynthesis) {
    return []
  }

  let voices = window.speechSynthesis.getVoices()
  if (voices.length) {
    return voices
  }

  await new Promise<void>((resolve) => {
    const done = () => {
      window.speechSynthesis.onvoiceschanged = null
      resolve()
    }
    window.speechSynthesis.onvoiceschanged = done
    setTimeout(done, 400)
  })

  voices = window.speechSynthesis.getVoices()
  return voices
}

function pickPreferredVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (!voices.length) {
    return null
  }

  const rankVoice = (voice: SpeechSynthesisVoice) => {
    const name = (voice.name || "").toLowerCase()
    const lang = (voice.lang || "").toLowerCase()
    let score = 0

    if (/(siri|premium|enhanced)/.test(name)) score += 120
    if (/(alex|ava|allison|samantha|karen|daniel|moira|victoria|serena|tessa|fiona)/.test(name)) score += 80
    if (lang === "en-us") score += 40
    else if (lang.startsWith("en")) score += 20
    if (voice.localService) score += 10
    if (voice.default) score += 5

    return score
  }

  const ranked = [...voices].sort((a, b) => rankVoice(b) - rankVoice(a))
  return ranked[0] ?? null
}

async function speakWithBrowserTTS(text: string): Promise<boolean> {
  if (!window.speechSynthesis) {
    return false
  }

  const voices = await getSpeechVoices()
  const preferredVoice = pickPreferredVoice(voices)
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = 0.92
  utterance.pitch = 1.0
  utterance.volume = 1
  utterance.lang = "en-US"
  if (preferredVoice) {
    utterance.voice = preferredVoice
  }

  return await new Promise<boolean>((resolve) => {
    utterance.onend = () => resolve(true)
    utterance.onerror = () => resolve(false)
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(utterance)
  })
}

function cleanSpokenText(input: string) {
  const text = (input || "").trim()
  if (!text) {
    return ""
  }

  const withoutLinks = text.replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1").replace(/https?:\/\/\S+/g, "")
  const withoutMarkdown = withoutLinks.replace(/[\*`#_~]+/g, " ").replace(/^\s*[-•]\s/gm, "")
  const normalized = withoutMarkdown.replace(/\s{2,}/g, " ").trim()
  if (normalized.length <= 1200) {
    return normalized
  }
  return `${normalized.slice(0, 1200).trimEnd()}...`
}

const TURN_MAX_MS = 18000
const PRE_SPEECH_TIMEOUT_MS = 6000
// 240 ms is the sweet spot: short enough to feel instant, long enough to
// survive brief mid-sentence hesitations without cutting the speaker off.
const SILENCE_TIMEOUT_MS = 240
const MIN_VOICE_TURN_MS = 220
const SPEECH_RMS_THRESHOLD = 0.0003
const MAX_POST_SPEECH_MS = 7000
const MIN_SPEECH_STREAK = 1
// Barge-in: while GAAIA is speaking, user speech above this RMS for this many
// consecutive audio chunks will cut her off and flip to listening. Chosen
// higher than SPEECH_RMS_THRESHOLD to reject residual TTS bleed-through.
const BARGEIN_RMS_THRESHOLD = 0.015
const BARGEIN_MIN_STREAK = 3

/** Set `true` to draw detection boxes on the camera preview. */
const SHOW_CAMERA_DETECTION_BOXES = true

/** How often we POST frames for detection (lower = fresher boxes, more server load). */
const CAMERA_DETECT_INTERVAL_MS = 300

function getDesktopLikeVoiceMode(): "fast" {
  return "fast"
}

export function VoiceConversation({ onClose, onOpenProfile, sessionId, modelKey, onConversationTurn, embedded = false, onCameraStream }: VoiceConversationProps) {
  const [state, setState] = useState<VoiceState>("idle")
  const [diagnosticStage, setDiagnosticStage] = useState<VoiceDiagnosticStage>("Idle")
  const [transcript, setTranscript] = useState("")
  const [response, setResponse] = useState("")
  const [displayedResponse, setDisplayedResponse] = useState("")
  const [isMuted, setIsMuted] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cameraStatus, setCameraStatus] = useState<string>("Starting camera...")
  const [lastDetectionCount, setLastDetectionCount] = useState<number>(0)
  const [detectionPreview, setDetectionPreview] = useState<string>("")
  const [recognizedFace, setRecognizedFace] = useState<{ name: string; confidence: number } | null>(null)
  const [enrolling, setEnrolling] = useState(false)
  const [enrollName, setEnrollName] = useState<string | null>(null)

  const activeRef = useRef(false)
  const stopRequestedRef = useRef(false)
  const requestAbortRef = useRef<AbortController | null>(null)
  const forceFinalizeRef = useRef(false)
  /** Set to true when a barge-in detector catches user speech mid-TTS. */
  const bargeInRef = useRef(false)
  /** Active TTS streaming session; `abort()` stops all in-flight audio. */
  const ttsSessionRef = useRef<TtsSession | null>(null)
  /** Dedicated mic stream + analyser that listens while GAAIA is speaking. */
  const bargeInStreamRef = useRef<MediaStream | null>(null)
  const bargeInCtxRef = useRef<AudioContext | null>(null)
  const bargeInRafRef = useRef<number | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const rafRef = useRef<number | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const sinkNodeRef = useRef<GainNode | null>(null)
  // Used on mobile in place of the deprecated ScriptProcessorNode capture path.
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const activeAudioRef = useRef<HTMLAudioElement | null>(null)
  const activeAudioUrlRef = useRef<string | null>(null)
  /** TTS read-back from GAAIA (separate from capture `audioCtxRef`) */
  const speakTtsContextRef = useRef<AudioContext | null>(null)
  /** Output AudioContext created/resumed on Start (user gesture) for autoplay policy. */
  const playbackAudioCtxRef = useRef<AudioContext | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const cameraStreamRef = useRef<MediaStream | null>(null)
  const onCameraStreamRef = useRef(onCameraStream)
  useEffect(() => { onCameraStreamRef.current = onCameraStream }, [onCameraStream])
  const identifyIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const detectIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const enrollFramesRef = useRef<Blob[]>([])

  // ── Camera helpers ──────────────────────────────────────────────────
  /** Full-res, high quality — enrollment only. */
  const captureFrameJpeg = useCallback(async (): Promise<Blob | null> => {
    const video = videoRef.current
    if (!video || video.readyState < 2) return null
    const vw = video.videoWidth
    const vh = video.videoHeight
    if (!vw || !vh || vw < 160 || vh < 120) return null
    try {
      const canvas = document.createElement("canvas")
      canvas.width = vw
      canvas.height = vh
      const ctx = canvas.getContext("2d")
      if (!ctx) return null
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      return new Promise<Blob | null>(resolve => {
        canvas.toBlob(blob => resolve(blob), "image/jpeg", 0.92)
      })
    } catch {
      return null
    }
  }, [])

  /**
   * Downscaled JPEG for live/detect/identify — smaller uploads and faster server inference
   * while keeping enough pixels for boxes and face-id (identify uses a larger maxWidth).
   */
  const captureFrameJpegScaled = useCallback(
    async (maxWidth: number, quality: number): Promise<Blob | null> => {
      const video = videoRef.current
      if (!video || video.readyState < 2) return null
      const vw = video.videoWidth
      const vh = video.videoHeight
      if (!vw || !vh || vw < 160 || vh < 120) return null
      if (maxWidth < 160) return null
      try {
        const scale = Math.min(1, maxWidth / vw)
        const tw = Math.max(160, Math.round(vw * scale))
        const th = Math.max(120, Math.round(vh * scale))
        const canvas = document.createElement("canvas")
        canvas.width = tw
        canvas.height = th
        const ctx = canvas.getContext("2d")
        if (!ctx) return null
        ctx.drawImage(video, 0, 0, tw, th)
        return new Promise<Blob | null>(resolve => {
          canvas.toBlob(blob => resolve(blob), "image/jpeg", quality)
        })
      } catch {
        return null
      }
    },
    [],
  )

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
    if (!SHOW_CAMERA_DETECTION_BOXES) {
      return
    }

    const typeOrder: Record<string, number> = {
      body: 0,
      body_part: 1,
      face: 2,
      person: 3,
      object: 4,
      hand: 5,
      finger: 6,
    }
    const sorted = [...detections].sort(
      (a, b) => (typeOrder[a.type] ?? 2) - (typeOrder[b.type] ?? 2),
    )

    // Video is CSS-mirrored only; canvas is not — flip X so boxes match selfie preview, text stays readable.
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
      const isFace = det.type === "face"
      const isFinger = det.type === "finger"
      const color =
        det.type === "face" ? "#22d3ee" :
        det.type === "person" ? "#34d399" :
        det.type === "hand" ? "#f97316" :
        det.type === "finger" ? "#fdba74" :
        det.type === "body" || det.type === "body_part" ? "#a78bfa" :
        "#a3e635"

      const lineW =
        isFinger ? 1.35 :
        det.type === "body_part" ? 1.5 :
        3
      ctx.strokeStyle = color
      ctx.lineWidth = lineW
      ctx.strokeRect(x, y, w, h)

      const labelText = isFinger
        ? fingerSegmentDisplayLabel(det.label)
        : `${det.label} ${Math.round(det.confidence * 100)}%`
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

  const stopCamera = useCallback(() => {
    if (identifyIntervalRef.current !== null) {
      clearInterval(identifyIntervalRef.current)
      identifyIntervalRef.current = null
    }
    if (detectIntervalRef.current !== null) {
      clearInterval(detectIntervalRef.current)
      detectIntervalRef.current = null
    }
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach(t => t.stop())
      cameraStreamRef.current = null
      onCameraStreamRef.current?.(null)
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    const canvas = canvasRef.current
    if (canvas) {
      const ctx = canvas.getContext("2d")
      ctx?.clearRect(0, 0, canvas.width, canvas.height)
    }
    setRecognizedFace(null)
    setLastDetectionCount(0)
    setDetectionPreview("")
    setCameraStatus("Camera stopped")
  }, [drawDetections])

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
      cameraStreamRef.current = stream
      onCameraStreamRef.current?.(stream)
      setCameraStatus("Camera live")
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => {})
      }

      // Detection loop — draws bounding boxes on the canvas overlay
      let detectInFlight = false
      detectIntervalRef.current = setInterval(async () => {
        if (detectInFlight) return
        detectInFlight = true
        try {
          const frame = await captureFrameJpegScaled(640, 0.82)
          if (!frame) {
            drawDetections([])
            return
          }
          const form = new FormData()
          form.append("image", frame, "frame.jpg")
          const res = await fetch("/api/camera/detect", { method: "POST", body: form })
          if (res.ok) {
            const data = await res.json() as { detections: Detection[] }
            const detections = data.detections || []
            setLastDetectionCount(detections.length)
            const uniqLabels = [...new Set(detections.map(d => d.label).filter(Boolean))]
            setDetectionPreview(
              uniqLabels.length
                ? uniqLabels.slice(0, 8).join(", ") + (uniqLabels.length > 8 ? "…" : "")
                : "",
            )
            setCameraStatus(detections.length > 0 ? `Detected ${detections.length} item${detections.length === 1 ? "" : "s"}` : "No detections yet")
            drawDetections(detections)
          } else {
            setCameraStatus("Detection unavailable")
            drawDetections([])
          }
        } catch {
          setCameraStatus("Detection error")
          drawDetections([])
        } finally {
          detectInFlight = false
        }
      }, CAMERA_DETECT_INTERVAL_MS)

      let identifyInFlight = false
      identifyIntervalRef.current = setInterval(async () => {
        if (identifyInFlight) return
        identifyInFlight = true
        try {
          const frame = await captureFrameJpegScaled(896, 0.88)
          if (!frame) return
          const form = new FormData()
          form.append("image", frame, "frame.jpg")
          const res = await fetch("/api/camera/identify", { method: "POST", body: form })
          if (res.ok) {
            const data = await res.json() as { name: string | null; confidence: number }
            if (data.name && data.confidence > 0) {
              setRecognizedFace({ name: data.name, confidence: data.confidence })
            } else {
              setRecognizedFace(null)
            }
          }
        } catch {
          // camera identify is best-effort
        } finally {
          identifyInFlight = false
        }
      }, 780)
    } catch {
      // camera permission denied or unavailable — non-fatal
      setCameraStatus("Camera access denied")
    }
  }, [captureFrameJpeg, captureFrameJpegScaled, drawDetections])

  const enrollFromCamera = useCallback(async (name: string) => {
    setEnrolling(true)
    enrollFramesRef.current = []
    const captures: Blob[] = []
    for (let i = 0; i < 5; i++) {
      await new Promise(r => setTimeout(r, 600))
      const frame = await captureFrameJpeg()
      if (frame) captures.push(frame)
    }
    if (captures.length === 0) {
      setEnrolling(false)
      return
    }
    try {
      const form = new FormData()
      form.append("name", name)
      captures.forEach((blob, idx) => form.append("images", blob, `frame_${idx}.jpg`))
      await fetch("/api/camera/enroll", { method: "POST", body: form })
    } catch {
      // enroll is best-effort
    }
    setEnrolling(false)
    setEnrollName(null)
  }, [captureFrameJpeg])

  const cleanupCapture = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }

    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current.onaudioprocess = null
      processorRef.current = null
    }

    if (mediaRecorderRef.current) {
      try {
        if (mediaRecorderRef.current.state !== "inactive") {
          mediaRecorderRef.current.stop()
        }
      } catch { /* ignore */ }
      mediaRecorderRef.current = null
    }

    if (sourceNodeRef.current) {
      sourceNodeRef.current.disconnect()
      sourceNodeRef.current = null
    }

    if (sinkNodeRef.current) {
      sinkNodeRef.current.disconnect()
      sinkNodeRef.current = null
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop())
      mediaStreamRef.current = null
    }

    if (audioCtxRef.current) {
      void audioCtxRef.current.close()
      audioCtxRef.current = null
    }
  }, [])

  const stopBargeInListener = useCallback(() => {
    if (bargeInRafRef.current !== null) {
      cancelAnimationFrame(bargeInRafRef.current)
      bargeInRafRef.current = null
    }
    if (bargeInCtxRef.current) {
      try {
        void bargeInCtxRef.current.close()
      } catch {
        // ignore
      }
      bargeInCtxRef.current = null
    }
    if (bargeInStreamRef.current) {
      bargeInStreamRef.current.getTracks().forEach((t) => t.stop())
      bargeInStreamRef.current = null
    }
  }, [])

  /**
   * While GAAIA is speaking, keep a lightweight mic analyser running so we can
   * detect when the user starts talking again and cut her off instantly. The
   * analyser uses a *higher* RMS threshold than normal listening so GAAIA's
   * own TTS bleeding through the mic (no echo cancellation during capture)
   * won't false-trigger.
   */
  const startBargeInListener = useCallback(async (onSpeech: () => void) => {
    stopBargeInListener()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          // Echo cancellation + noise suppression here are fine: we don't
          // need pristine audio for VAD, and they help suppress TTS spill.
          noiseSuppression: true,
          echoCancellation: true,
          autoGainControl: true,
        },
      })
      bargeInStreamRef.current = stream
      const AC = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!AC) return
      const ctx = new AC()
      bargeInCtxRef.current = ctx
      if (ctx.state === "suspended") {
        try {
          await ctx.resume()
        } catch {
          // ignore
        }
      }
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      source.connect(analyser)
      const data = new Float32Array(analyser.fftSize)
      let streak = 0

      const tick = () => {
        if (!bargeInCtxRef.current || bargeInCtxRef.current !== ctx) return
        analyser.getFloatTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i += 1) {
          sum += data[i] * data[i]
        }
        const rms = Math.sqrt(sum / data.length)
        if (rms >= BARGEIN_RMS_THRESHOLD) {
          streak += 1
          if (streak >= BARGEIN_MIN_STREAK) {
            onSpeech()
            return
          }
        } else {
          streak = 0
        }
        bargeInRafRef.current = requestAnimationFrame(tick)
      }
      bargeInRafRef.current = requestAnimationFrame(tick)
    } catch {
      // Barge-in is best-effort — if the mic can't be opened we just don't
      // support interruption this turn.
    }
  }, [stopBargeInListener])

  const stopConversation = useCallback(() => {
    stopRequestedRef.current = true
    forceFinalizeRef.current = false
    activeRef.current = false
    setDiagnosticStage("Idle")

    requestAbortRef.current?.abort()
    requestAbortRef.current = null

    if (ttsSessionRef.current) {
      ttsSessionRef.current.abort()
      ttsSessionRef.current = null
    }

    stopBargeInListener()

    if (activeAudioRef.current) {
      activeAudioRef.current.pause()
      activeAudioRef.current.src = ""
      activeAudioRef.current = null
    }
    if (activeAudioUrlRef.current) {
      URL.revokeObjectURL(activeAudioUrlRef.current)
      activeAudioUrlRef.current = null
    }
    if (speakTtsContextRef.current) {
      try { void speakTtsContextRef.current.close() } catch { /* */ }
      speakTtsContextRef.current = null
    }
    if (playbackAudioCtxRef.current) {
      try { void playbackAudioCtxRef.current.close() } catch { /* */ }
      playbackAudioCtxRef.current = null
    }

    if (window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }

    cleanupCapture()
    stopCamera()
    const sid = sessionId
    if (sid) {
      const fd = new FormData()
      fd.append("session_id", sid)
      void fetch("/api/camera/live/clear", { method: "POST", body: fd }).catch(() => {})
    }
    setState("idle")
  }, [cleanupCapture, stopCamera, sessionId])

  const playAudioBlob = useCallback(async (blob: Blob): Promise<boolean> => {
    if (!blob.size) return false
    const url = URL.createObjectURL(blob)
    activeAudioUrlRef.current = url
    const audio = new Audio(url)
    audio.volume = 1
    activeAudioRef.current = audio
    let started = false
    await new Promise<void>((resolve) => {
      audio.onplay = () => { started = true }
      audio.onended = () => resolve()
      audio.onerror = () => resolve()
      void audio.play().catch(() => resolve())
    })
    audio.src = ""
    activeAudioRef.current = null
    URL.revokeObjectURL(url)
    activeAudioUrlRef.current = null
    return started
  }, [])

  const recordVoiceTurn = useCallback(async (): Promise<Blob> => {
    setDiagnosticStage("Requesting microphone")
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          noiseSuppression: false,
          echoCancellation: false,
          autoGainControl: false,
        },
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : "Microphone access failed"
      throw new Error(`I can't access the microphone. ${message}`)
    }
    mediaStreamRef.current = stream
    setDiagnosticStage("Capturing audio")

    const audioCtx = new AudioContext()
    audioCtxRef.current = audioCtx
    if (audioCtx.state === "suspended") {
      await audioCtx.resume()
    }
    const source = audioCtx.createMediaStreamSource(stream)
    sourceNodeRef.current = source
    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 2048
    const processor = audioCtx.createScriptProcessor(4096, 1, 1)
    processorRef.current = processor
    const silentSink = audioCtx.createGain()
    silentSink.gain.value = 0
    sinkNodeRef.current = silentSink

    const pcmChunks: Float32Array[] = []
    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0)
      pcmChunks.push(new Float32Array(input))

      // Chunk RMS is more stable than analyser-only checks on some mics.
      let sum = 0
      for (let i = 0; i < input.length; i += 1) {
        sum += input[i] * input[i]
      }
      const chunkRms = Math.sqrt(sum / input.length)
      if (chunkRms >= SPEECH_RMS_THRESHOLD * 0.6) {
        speechStreak += 1
        if (speechStreak >= MIN_SPEECH_STREAK) {
          if (!sawSpeech) {
            firstSpeechAt = performance.now()
          }
          sawSpeech = true
          lastSpeechAt = performance.now()
          analyserSawEnergy = true
        }
      } else {
        speechStreak = 0
      }
    }

    source.connect(analyser)
    source.connect(processor)
    processor.connect(silentSink)
    silentSink.connect(audioCtx.destination)

    const data = new Float32Array(analyser.fftSize)
    let analyserSawEnergy = false

    let sawSpeech = false
    const startedAt = performance.now()
    let lastSpeechAt = startedAt
    let firstSpeechAt: number | null = null
    let speechStreak = 0

    const shouldStop = () => {
      const now = performance.now()
      const elapsed = now - startedAt

      analyser.getFloatTimeDomainData(data)
      let sum = 0
      for (let i = 0; i < data.length; i += 1) {
        sum += data[i] * data[i]
      }
      const rms = Math.sqrt(sum / data.length)

      if (rms >= SPEECH_RMS_THRESHOLD) {
        analyserSawEnergy = true
      }

      if (elapsed >= TURN_MAX_MS) {
        return true
      }
      if (!sawSpeech && elapsed >= PRE_SPEECH_TIMEOUT_MS) {
        setDiagnosticStage("Waiting for speech")
        return true
      }
      if (sawSpeech && elapsed >= MIN_VOICE_TURN_MS && (now - lastSpeechAt) >= SILENCE_TIMEOUT_MS) {
        return true
      }
      if (sawSpeech && firstSpeechAt !== null && (now - firstSpeechAt) >= MAX_POST_SPEECH_MS) {
        return true
      }
      return false
    }

    const stopIfDone = () => {
      if (stopRequestedRef.current || forceFinalizeRef.current || !activeRef.current) {
        if (rafRef.current !== null) {
          cancelAnimationFrame(rafRef.current)
          rafRef.current = null
        }
        return
      }

      if (shouldStop()) {
        if (rafRef.current !== null) {
          cancelAnimationFrame(rafRef.current)
          rafRef.current = null
        }
        return
      }

      rafRef.current = requestAnimationFrame(stopIfDone)
    }

    rafRef.current = requestAnimationFrame(stopIfDone)

    const started = performance.now()
    await new Promise<void>((resolve) => {
      const pollStop = () => {
        const elapsed = performance.now() - started
        const reachedMax = elapsed >= TURN_MAX_MS
        const noVoiceTimeout = !sawSpeech && elapsed >= PRE_SPEECH_TIMEOUT_MS
        const afterVoiceSilence = sawSpeech && elapsed >= MIN_VOICE_TURN_MS && (performance.now() - lastSpeechAt) >= SILENCE_TIMEOUT_MS
        const reachedPostSpeechMax = sawSpeech && firstSpeechAt !== null && (performance.now() - firstSpeechAt) >= MAX_POST_SPEECH_MS

        if (stopRequestedRef.current || forceFinalizeRef.current || !activeRef.current || reachedMax || noVoiceTimeout || afterVoiceSilence || reachedPostSpeechMax) {
          resolve()
          return
        }

        setTimeout(pollStop, 10)
      }
      pollStop()
    })

    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }

    source.disconnect()
    processor.disconnect()
    silentSink.disconnect()

    const merged = mergePcmChunks(pcmChunks)

    if (!analyserSawEnergy && merged.length > 0) {
      cleanupCapture()
      const wav = encodeWav16kMono(downsampleTo16k(merged, audioCtx.sampleRate))
      const blob = new Blob([wav], { type: "audio/wav" })
      if (blob.size) {
        return blob
      }
    }

    const downsampled = downsampleTo16k(merged, audioCtx.sampleRate)
    const wav = encodeWav16kMono(downsampled)
    cleanupCapture()

    const blob = new Blob([wav], { type: "audio/wav" })

    if (!blob.size) {
      throw new Error("I couldn't hear anything. Try speaking a bit louder.")
    }

    return blob
  }, [cleanupCapture])

  // ── MediaRecorder capture path (mobile devices) ──────────────────────────
  // ScriptProcessorNode is deprecated and broken on iOS Safari — its callback
  // either never fires or fires with empty buffers, so the desktop PCM path
  // produces no audio on phones. MediaRecorder is well supported on iOS 14.5+
  // and modern Android, gives us encoded audio (webm/opus or mp4/aac) that
  // Whisper happily transcribes server-side via ffmpeg.
  //
  // We still use AnalyserNode for VAD — that part of Web Audio works fine on
  // iOS. So push-to-talk auto-stop on silence still works the same way.
  const recordVoiceTurnMobile = useCallback(async (): Promise<Blob> => {
    setDiagnosticStage("Requesting microphone")
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          noiseSuppression: false,
          echoCancellation: false,
          autoGainControl: false,
        },
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : "Microphone access failed"
      throw new Error(`I can't access the microphone. ${message}`)
    }
    mediaStreamRef.current = stream
    setDiagnosticStage("Capturing audio")

    // Pick the best supported MIME type. iOS Safari only supports mp4/aac;
    // Chrome/Android prefers webm/opus. Whisper handles either via ffmpeg.
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4;codecs=mp4a.40.2",
      "audio/mp4",
      "audio/aac",
      "audio/wav",
    ]
    let mimeType = ""
    for (const c of candidates) {
      // Some browsers don't expose isTypeSupported; fall through to the empty
      // string which tells MediaRecorder to pick its own default.
      if (typeof MediaRecorder !== "undefined" &&
          typeof MediaRecorder.isTypeSupported === "function" &&
          MediaRecorder.isTypeSupported(c)) {
        mimeType = c
        break
      }
    }

    const recorderOpts: MediaRecorderOptions = mimeType
      ? { mimeType, audioBitsPerSecond: 64000 }
      : { audioBitsPerSecond: 64000 }
    let recorder: MediaRecorder
    try {
      recorder = new MediaRecorder(stream, recorderOpts)
    } catch {
      // Last-ditch: let the browser pick everything.
      recorder = new MediaRecorder(stream)
    }
    mediaRecorderRef.current = recorder

    const chunks: Blob[] = []
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data)
    }

    // Set up an AnalyserNode purely for silence detection — no audio capture
    // happens here, the recorder is already grabbing the encoded stream.
    const audioCtx = new AudioContext()
    audioCtxRef.current = audioCtx
    if (audioCtx.state === "suspended") {
      await audioCtx.resume()
    }
    const source = audioCtx.createMediaStreamSource(stream)
    sourceNodeRef.current = source
    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 2048
    source.connect(analyser)

    const data = new Float32Array(analyser.fftSize)
    let analyserSawEnergy = false
    let sawSpeech = false
    const startedAt = performance.now()
    let lastSpeechAt = startedAt
    let firstSpeechAt: number | null = null

    recorder.start()
    const startedRecAt = performance.now()

    // Poll the analyser to detect silence, just like the desktop path.
    await new Promise<void>((resolve) => {
      const poll = () => {
        const now = performance.now()
        const elapsed = now - startedAt

        analyser.getFloatTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i]
        const rms = Math.sqrt(sum / data.length)
        if (rms >= SPEECH_RMS_THRESHOLD) {
          if (!sawSpeech) firstSpeechAt = now
          sawSpeech = true
          lastSpeechAt = now
          analyserSawEnergy = true
        }

        const reachedMax = elapsed >= TURN_MAX_MS
        const noVoiceTimeout = !sawSpeech && elapsed >= PRE_SPEECH_TIMEOUT_MS
        const afterVoiceSilence = sawSpeech && elapsed >= MIN_VOICE_TURN_MS && (now - lastSpeechAt) >= SILENCE_TIMEOUT_MS
        const reachedPostSpeechMax = sawSpeech && firstSpeechAt !== null && (now - firstSpeechAt) >= MAX_POST_SPEECH_MS

        if (
          stopRequestedRef.current ||
          forceFinalizeRef.current ||
          !activeRef.current ||
          reachedMax ||
          noVoiceTimeout ||
          afterVoiceSilence ||
          reachedPostSpeechMax
        ) {
          resolve()
          return
        }
        setTimeout(poll, 30)
      }
      poll()
    })

    // Stop the recorder and wait for the final data chunk.
    if (recorder.state !== "inactive") {
      const stopped = new Promise<void>((resolve) => {
        recorder.onstop = () => resolve()
      })
      recorder.stop()
      await stopped
    }

    source.disconnect()
    cleanupCapture()

    void analyserSawEnergy  // referenced for parity with desktop path
    void startedRecAt

    if (chunks.length === 0) {
      throw new Error("I couldn't hear anything. Try speaking a bit louder.")
    }
    const blobMime = mimeType || (chunks[0]?.type ?? "audio/webm")
    const blob = new Blob(chunks, { type: blobMime })
    if (!blob.size) {
      throw new Error("I couldn't hear anything. Try speaking a bit louder.")
    }
    return blob
  }, [cleanupCapture])

function mergePcmChunks(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const merged = new Float32Array(length)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.length
  }
  return merged
}

function downsampleTo16k(input: Float32Array, inputSampleRate: number): Float32Array {
  const targetRate = 16000
  if (inputSampleRate === targetRate) {
    return input
  }

  const ratio = inputSampleRate / targetRate
  const outputLength = Math.max(1, Math.floor(input.length / ratio))
  const output = new Float32Array(outputLength)

  let pos = 0
  for (let i = 0; i < outputLength; i += 1) {
    const nextPos = Math.min(input.length, Math.floor((i + 1) * ratio))
    let sum = 0
    let count = 0
    for (; pos < nextPos; pos += 1) {
      sum += input[pos]
      count += 1
    }
    output[i] = count ? sum / count : 0
  }

  return output
}

function encodeWav16kMono(samples: Float32Array): ArrayBuffer {
  const bytesPerSample = 2
  const blockAlign = bytesPerSample
  const sampleRate = 16000
  const byteRate = sampleRate * blockAlign
  const dataLength = samples.length * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataLength)
  const view = new DataView(buffer)

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i))
    }
  }

  writeString(0, "RIFF")
  view.setUint32(4, 36 + dataLength, true)
  writeString(8, "WAVE")
  writeString(12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, byteRate, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeString(36, "data")
  view.setUint32(40, dataLength, true)

  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }

  return buffer
}

  const runTurn = useCallback(async () => {
    if (!activeRef.current || stopRequestedRef.current) {
      return
    }

    setError(null)
    setTranscript("")
    setResponse("")
    setDisplayedResponse("")
    forceFinalizeRef.current = false
    bargeInRef.current = false

    try {
      setState("listening")
      // Mobile devices route through MediaRecorder because their Web Audio
      // ScriptProcessor implementation is broken / deprecated. Detection
      // covers iOS Safari, iPadOS Safari, Android Chrome, and Mobile Firefox.
      const isMobile = typeof window !== "undefined" && (
        /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) ||
        ("maxTouchPoints" in navigator && navigator.maxTouchPoints > 1 && /Mac/i.test(navigator.userAgent))
      )
      const audioBlob = isMobile
        ? await recordVoiceTurnMobile()
        : await recordVoiceTurn()
      if (!activeRef.current || stopRequestedRef.current) {
        return
      }

      setState("thinking")
      setDiagnosticStage("Thinking")

      // Capture a frame concurrently — race against a 60ms deadline so JPEG
      // encode never delays the audio upload. The continuous live-buffer
      // provides fallback context if we miss the snapshot.
      let camFrame: Blob | null = null
      try {
        const frameRace = Promise.race([
          captureFrameJpegScaled(320, 0.65),
          new Promise<null>(resolve => setTimeout(() => resolve(null), 60)),
        ])
        camFrame = await frameRace
      } catch {
        camFrame = null
      }

      const controller = new AbortController()
      requestAbortRef.current = controller

      const tts = createTtsSession({
        isMuted,
        stopRequestedRef,
        bargeInRef,
        playbackCtxRef: playbackAudioCtxRef,
      })
      ttsSessionRef.current = tts

      // Barge-in: as soon as GAAIA starts speaking (first sentence arrives),
      // open a dedicated mic analyser. If it hears the user, we abort TTS,
      // cancel the in-flight HTTP stream (so the LLM doesn't keep generating
      // sentences we'll never play), and loop back to listening instantly.
      let bargeInArmed = false
      const armBargeIn = () => {
        if (bargeInArmed) return
        bargeInArmed = true
        void startBargeInListener(() => {
          bargeInRef.current = true
          tts.abort()
          try {
            controller.abort()
          } catch {
            // ignore
          }
        })
      }

      let turnTranscript = ""
      let turnResponse = ""
      let gotTranscript = false
      let errorDetail: string | null = null

      try {
        for await (const evt of streamVoiceTurn(
          audioBlob,
          sessionId,
          modelKey,
          controller.signal,
          camFrame,
        )) {
          if (stopRequestedRef.current || bargeInRef.current) break

          if (evt.type === "transcript") {
            turnTranscript = evt.text
            setTranscript(evt.text)
            gotTranscript = true
            setDiagnosticStage("Transcribing")
          } else if (evt.type === "sentence") {
            // Enrollment marker may land in a sentence chunk.
            const enrollMatch = evt.text.match(/__ENROLL_FACE__:([^_\s]+(?:\s[^_\s]+)*)/)
            const cleanText = evt.text.replace(/__ENROLL_FACE__:[^\s]*/g, "").trim()
            if (enrollMatch) {
              const nameToEnroll = enrollMatch[1].trim()
              setEnrollName(nameToEnroll)
              void enrollFromCamera(nameToEnroll)
            }
            if (cleanText) {
              turnResponse = turnResponse ? `${turnResponse} ${cleanText}` : cleanText
              setResponse(turnResponse)
              setDisplayedResponse(turnResponse)
              setState("speaking")
              setDiagnosticStage("Speaking")
              tts.enqueue(cleanText)
              armBargeIn()
            }
          } else if (evt.type === "done") {
            if (evt.response && evt.response.trim()) {
              const cleanFull = evt.response.replace(/__ENROLL_FACE__:[^\s]*/g, "").trim()
              turnResponse = cleanFull || turnResponse
              setResponse(turnResponse)
              setDisplayedResponse(turnResponse)
            }
            tts.finish()
            break
          } else if (evt.type === "error") {
            errorDetail = evt.detail || "Voice stream error"
            tts.finish()
            break
          }
        }

        // If the server closed without an explicit done/error, ensure the
        // queue drains.
        tts.finish()

        if (errorDetail && !turnResponse) {
          const lower = errorDetail.toLowerCase()
          if (lower.includes("no speech detected")) {
            setState("listening")
            setDiagnosticStage("Retrying listen")
            void runTurn()
            return
          }
          throw new Error(errorDetail)
        }

        if (!gotTranscript) {
          setState("listening")
          setDiagnosticStage("Retrying listen")
          void runTurn()
          return
        }

        if (!turnResponse.trim()) {
          setState("listening")
          setDiagnosticStage("Capturing audio")
          void runTurn()
          return
        }

        onConversationTurn(turnTranscript, turnResponse)

        // Wait for the TTS queue to finish playing the last sentence.
        await tts.drain()
      } finally {
        if (requestAbortRef.current === controller) {
          requestAbortRef.current = null
        }
        if (ttsSessionRef.current === tts) {
          ttsSessionRef.current = null
        }
        stopBargeInListener()
      }

      if (!activeRef.current || stopRequestedRef.current) {
        return
      }

      // If the user barged in, loop straight back to listening — no gap.
      void runTurn()
    } catch (err) {
      const message = err instanceof Error ? err.message : "Voice conversation failed"
      setError(message)
      setState("idle")
      setDiagnosticStage(message.toLowerCase().includes("microphone") ? "Requesting microphone" : "Idle")
      activeRef.current = false
      if (ttsSessionRef.current) {
        ttsSessionRef.current.abort()
        ttsSessionRef.current = null
      }
      stopBargeInListener()
    }
  }, [
    onConversationTurn,
    recordVoiceTurn,
    recordVoiceTurnMobile,
    enrollFromCamera,
    captureFrameJpegScaled,
    sessionId,
    modelKey,
    isMuted,
    startBargeInListener,
    stopBargeInListener,
  ])

  const handleStart = () => {
    if (state !== "idle") {
      return
    }

    stopRequestedRef.current = false
    activeRef.current = true
    setDiagnosticStage("Capturing audio")

    void (async () => {
      try {
        const AC =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        if (AC) {
          let ac = playbackAudioCtxRef.current
          if (!ac || ac.state === "closed") {
            ac = new AC()
            playbackAudioCtxRef.current = ac
          }
          await ac.resume()
        }
      } catch {
        // TTS will retry resume on first sentence; unlock here fixes most browsers.
      }
      void startCamera()
      void runTurn()
    })()
  }

  const handleClose = () => {
    stopConversation()
    onClose()
  }

  const handleSendNow = () => {
    if (state !== "listening") {
      return
    }
    forceFinalizeRef.current = true
    setDiagnosticStage("Thinking")
  }

  useEffect(() => {
    return () => {
      stopConversation()
    }
  }, [stopConversation])

  useEffect(() => {
    void startCamera()
    return () => {
      stopCamera()
    }
  }, [startCamera, stopCamera])

  /** Continuous live frames → server rolling buffer (hands, detector, throttled scene). */
  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    const loop = async () => {
      while (!cancelled) {
        await new Promise<void>(r => setTimeout(r, 450))
        if (cancelled) break
        const track = cameraStreamRef.current?.getVideoTracks()[0]
        if (!track || track.readyState !== "live") continue
        const blob = await captureFrameJpegScaled(512, 0.72)
        if (cancelled || !blob) continue
        const fd = new FormData()
        fd.append("session_id", sessionId)
        fd.append("image", blob, "live.jpg")
        void fetch("/api/camera/live", { method: "POST", body: fd }).catch(() => {})
      }
    }
    void loop()
    return () => {
      cancelled = true
    }
  }, [sessionId, captureFrameJpegScaled])

  const getStatusText = () => {
    switch (state) {
      case "idle":
        return "Tap the mic to start"
      case "listening":
        return "I’m listening"
      case "thinking":
        return "One sec"
      case "speaking":
        return isMuted ? "Muted" : "Talking"
      default:
        return ""
    }
  }

  return (
    <div
      className={cn(
        embedded
          ? "relative flex flex-col items-center justify-center w-full h-full"
          : "fixed inset-0 z-50 flex flex-col items-center justify-center"
      )}
      style={{ backgroundColor: "var(--surface-0)" }}
    >
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className={cn(
            "absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full transition-opacity duration-1000",
            "bg-linear-to-br from-blue-500/10 via-purple-500/10 to-cyan-500/10 blur-3xl",
            state === "speaking" ? "opacity-60" : "opacity-30"
          )}
        />
        <div
          className={cn(
            "absolute top-1/4 right-1/4 w-[300px] h-[300px] rounded-full transition-opacity duration-1000",
            "bg-linear-to-br from-cyan-500/10 to-transparent blur-3xl",
            state === "listening" ? "opacity-50" : "opacity-20"
          )}
        />
      </div>

      {!embedded && (
        <div className="absolute top-0 left-0 right-0 flex items-center justify-between p-4">
          <button
            onClick={handleClose}
            className="flex items-center gap-2 px-3 py-2 rounded-full hover:bg-white/10 transition-colors"
            aria-label="Go to Home"
          >
            <GaaiaIcon size={24} />
            <span className="text-white/80 text-sm font-semibold tracking-wide">GAAIA</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={onOpenProfile}
              className="p-3 rounded-full hover:bg-white/10 transition-colors text-white/80"
              aria-label="Open profiles"
              title="Stored users"
            >
              <User className="w-5 h-5" />
            </button>
            <button
              onClick={() => setIsMuted(!isMuted)}
              className={cn(
                "p-3 rounded-full transition-colors",
                isMuted ? "bg-red-500/20 text-red-400" : "hover:bg-white/10 text-white/80"
              )}
              aria-label={isMuted ? "Unmute" : "Mute"}
            >
              {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="p-3 rounded-full hover:bg-white/10 transition-colors text-white/80"
              aria-label="Settings"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-col items-center gap-4 z-10">
        <VoiceOrb state={state} />

        <div className="max-w-xs px-4 text-center space-y-2">
          <p className="text-[10px] uppercase tracking-[0.2em] text-white/20">
            {diagnosticStage}
          </p>

          {state === "listening" && (
            <p className="text-sm text-white/75 animate-in fade-in duration-300">
              {transcript || "Listening…"}
              <span className="inline-block w-0.5 h-4 bg-cyan-400 ml-1 animate-pulse" />
            </p>
          )}

          {state === "speaking" && displayedResponse && (
            <p className="text-sm text-white/75 animate-in fade-in duration-300 leading-relaxed">
              {displayedResponse}
            </p>
          )}

          {error && (
            <p className="text-sm text-red-300/80">{error}</p>
          )}
        </div>
      </div>

      {/* Camera preview — shown in fullscreen mode; in embedded mode video/canvas are kept
          off-screen so detection / enrollment logic continues to run */}
      {embedded ? (
        <div className="absolute pointer-events-none" style={{ left: -9999, top: -9999, width: 1, height: 1, overflow: "hidden" }}>
          <video ref={videoRef} autoPlay muted playsInline style={{ width: 320, height: 240 }} />
          <canvas ref={canvasRef} style={{ width: 320, height: 240 }} />
        </div>
      ) : (cameraStreamRef.current !== null || state !== "idle") ? (
        <div className="absolute top-20 right-6 z-30 w-[360px] max-w-[42vw] rounded-2xl overflow-hidden border border-cyan-400/30 shadow-2xl shadow-cyan-500/10 bg-black/90 backdrop-blur-sm">
          <div className="px-3 py-2 flex items-center justify-between border-b border-white/10 bg-black/70">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-300">Camera Live</span>
            <span className="text-[10px] text-white/40">{cameraStatus}</span>
          </div>
          <div className="relative aspect-video overflow-hidden">
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              className="absolute inset-0 z-10 h-full w-full object-cover block -scale-x-100"
            />
            <canvas
              ref={canvasRef}
              className="absolute inset-0 z-20 h-full w-full pointer-events-none"
            />
          </div>
          <div className="px-3 py-2 bg-black/80 flex items-center gap-1.5 border-t border-white/10">
            {recognizedFace ? (
              <>
                <span className="text-[11px] font-semibold text-cyan-300 truncate">{recognizedFace.name}</span>
                <span className="text-[10px] text-white/40 ml-auto shrink-0">{Math.round(recognizedFace.confidence * 100)}%</span>
              </>
            ) : (
              <>
                <Camera className="w-3 h-3 text-white/30" />
                <span className="text-[10px] text-white/30 truncate max-w-[280px]" title={detectionPreview || undefined}>
                  {enrolling
                    ? "Enrolling..."
                    : detectionPreview
                      ? `Seeing: ${detectionPreview}`
                      : lastDetectionCount > 0
                        ? `${lastDetectionCount} region(s) — check overlay`
                        : "Point the camera at something to label"}
                </span>
              </>
            )}
          </div>
        </div>
      ) : null}

      <div className="absolute bottom-12 flex items-center gap-4">
        {state === "idle" ? (
          <button
            onClick={handleStart}
            className={cn(
              "px-6 py-3 rounded-full font-medium transition-all text-white",
              "bg-linear-to-br from-blue-500 to-cyan-500 hover:from-blue-400 hover:to-cyan-400 shadow-lg shadow-blue-500/30"
            )}
            aria-label="Start listening"
          >
            Start
          </button>
        ) : (
          <button
            onClick={stopConversation}
            className={cn(
              "px-6 py-3 rounded-full font-medium transition-all text-white",
              "bg-white/10 hover:bg-white/20 border border-white/20"
            )}
            aria-label="Stop conversation"
          >
            Stop
          </button>
        )}
      </div>

      {showSettings && (
        <div className="absolute right-6 top-20 w-72 rounded-2xl border border-white/10 bg-black/80 backdrop-blur-xl p-4 text-sm text-white/80 shadow-2xl">
          <div className="flex items-center justify-between">
            <p className="font-medium text-white">Voice settings</p>
            <button onClick={() => setShowSettings(false)} className="text-white/50 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="mt-4 space-y-3">
            <div className="flex items-center justify-between gap-4">
              <span>Assistant voice</span>
              <span className="text-white/50">API voice-over (Lauren)</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>STT engine</span>
              <span className="text-white/50">GAAIA Whisper backend</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>Model</span>
              <span className="text-white/50">{modelKey}</span>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>Session</span>
              <span className="text-white/50 truncate max-w-[120px]">{sessionId}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
