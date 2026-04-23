"use client"

import { useEffect, useRef, useState } from "react"
import { Music2, Pause, Play } from "lucide-react"
import { cn } from "@/lib/utils"

interface MusicPlayerProps {
  url: string
  prompt?: string
  className?: string
}

export function MusicPlayer({ url, prompt, className }: MusicPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const onTimeUpdate = () => {
      setCurrentTime(audio.currentTime)
      if (audio.duration) setProgress(audio.currentTime / audio.duration)
    }
    const onLoaded = () => setDuration(audio.duration || 0)
    const onEnded = () => {
      setPlaying(false)
      setProgress(0)
      setCurrentTime(0)
    }

    audio.addEventListener("timeupdate", onTimeUpdate)
    audio.addEventListener("loadedmetadata", onLoaded)
    audio.addEventListener("ended", onEnded)

    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate)
      audio.removeEventListener("loadedmetadata", onLoaded)
      audio.removeEventListener("ended", onEnded)
    }
  }, [url])

  const togglePlay = () => {
    const audio = audioRef.current
    if (!audio) return
    if (playing) {
      audio.pause()
      setPlaying(false)
    } else {
      void audio.play()
      setPlaying(true)
    }
  }

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const audio = audioRef.current
    if (!audio || !audio.duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const ratio = (e.clientX - rect.left) / rect.width
    audio.currentTime = ratio * audio.duration
    setProgress(ratio)
  }

  const fmt = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60).toString().padStart(2, "0")
    return `${m}:${sec}`
  }

  return (
    <div className={cn(
      "flex items-center gap-3 px-3 py-2.5 rounded-xl",
      "bg-violet-950/30 border border-violet-500/20",
      className,
    )}>
      <audio ref={audioRef} src={url} preload="auto" />

      {/* Icon */}
      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-violet-500/20 shrink-0">
        <Music2 className={cn("w-4 h-4 text-violet-400", playing && "animate-pulse")} />
      </div>

      <div className="flex-1 min-w-0">
        {prompt && (
          <p className="text-xs text-violet-300/70 truncate mb-1.5 capitalize">{prompt}</p>
        )}

        <div className="flex items-center gap-2">
          {/* Play/Pause */}
          <button
            onClick={togglePlay}
            className="flex items-center justify-center w-7 h-7 rounded-full bg-violet-500 hover:bg-violet-400 transition-colors shrink-0"
          >
            {playing
              ? <Pause className="w-3 h-3 text-white fill-white" />
              : <Play  className="w-3 h-3 text-white fill-white ml-0.5" />
            }
          </button>

          {/* Progress bar */}
          <div
            className="flex-1 relative h-1.5 bg-violet-900/50 rounded-full overflow-hidden cursor-pointer"
            onClick={handleSeek}
          >
            <div
              className="absolute inset-y-0 left-0 bg-violet-500 rounded-full transition-all"
              style={{ width: `${progress * 100}%` }}
            />
          </div>

          {/* Time */}
          <span className="text-xs text-muted-foreground tabular-nums shrink-0">
            {duration > 0 ? `${fmt(currentTime)} / ${fmt(duration)}` : "--:--"}
          </span>
        </div>
      </div>

      {/* Download */}
      <a
        href={url}
        download="nova_beat.wav"
        title="Download"
        className="shrink-0 text-violet-400/60 hover:text-violet-300 transition-colors text-xs"
      >
        ↓
      </a>
    </div>
  )
}


export function MusicGenerating({ prompt, className }: { prompt?: string; className?: string }) {
  return (
    <div className={cn(
      "flex items-center gap-3 px-3 py-2.5 rounded-xl",
      "bg-violet-950/30 border border-violet-500/20",
      className,
    )}>
      {/* Animated icon */}
      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-violet-500/20 shrink-0">
        <Music2 className="w-4 h-4 text-violet-400 animate-pulse" />
      </div>

      <div className="flex-1 min-w-0">
        {prompt && (
          <p className="text-xs text-violet-300/70 truncate mb-1.5 capitalize">{prompt}</p>
        )}
        <div className="flex items-center gap-2">
          {/* Waveform bars */}
          <div className="flex gap-0.5 items-end h-5">
            {[0.4, 0.7, 1, 0.6, 0.9, 0.5, 0.8].map((h, i) => (
              <div
                key={i}
                className="w-1 bg-violet-500 rounded-full animate-bounce"
                style={{
                  height: `${h * 100}%`,
                  animationDelay: `${i * 0.08}s`,
                  animationDuration: "0.7s",
                }}
              />
            ))}
          </div>
          <span className="text-xs text-violet-300/80">Generating beat…</span>
        </div>
      </div>
    </div>
  )
}
