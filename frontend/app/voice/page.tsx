"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { User as UserIcon, Camera, History, MessageSquare, Clock, Trash2, Plus } from "lucide-react"
import { VoiceConversation } from "@/components/chat/voice-conversation"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"
import type { ChatModelKey } from "@/components/chat/chat-header"

type ChatMessage = {
  id: string
  role: "user" | "nova"
  text: string
  ts: number
}

type VoiceSession = {
  id: string
  title: string
  preview: string
  created_at: string
  message_count: number
}

type UserInfo = { display_name: string; avatar_color: string }

function createVoiceSessionId() {
  return `voice-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return ""
  const diff = Date.now() - date.getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 2) return "Just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString()
}

export default function VoicePage() {
  const router = useRouter()
  const [sessionId, setSessionId] = useState(() => createVoiceSessionId())
  const [modelKey] = useState<ChatModelKey>("air")

  // Current session live messages
  const [messages, setMessages] = useState<ChatMessage[]>([])
  // History panel
  const [voiceSessions, setVoiceSessions] = useState<VoiceSession[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [selectedSession, setSelectedSession] = useState<string | null>(null)
  const selectedSessionRef = useRef<string | null>(null)
  selectedSessionRef.current = selectedSession
  const [selectedMessages, setSelectedMessages] = useState<ChatMessage[]>([])
  const [selectedLoading, setSelectedLoading] = useState(false)
  const [rightTab, setRightTab] = useState<"live" | "history">("live")

  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null)
  const [user, setUser] = useState<UserInfo | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const cameraVideoRef = useRef<HTMLVideoElement>(null)

  // Auth guard + user fetch
  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => {
        if (!r.ok) { router.replace("/login"); return null }
        return r.json()
      })
      .then(d => {
        if (d?.display_name) setUser({ display_name: d.display_name, avatar_color: d.avatar_color || "#0ea5e9" })
      })
      .catch(() => router.replace("/login"))
  }, [router])

  // Load voice session history list
  const loadVoiceSessions = useCallback(async () => {
    setHistoryLoading(true)
    try {
      const r = await fetch("/api/memory/voice-sessions")
      if (r.ok) {
        const data = await r.json()
        setVoiceSessions(Array.isArray(data) ? data : [])
      }
    } catch { /* silent */ }
    finally { setHistoryLoading(false) }
  }, [])

  useEffect(() => { void loadVoiceSessions() }, [loadVoiceSessions])

  // Mirror camera stream to the bottom-left panel
  useEffect(() => {
    if (cameraVideoRef.current) {
      cameraVideoRef.current.srcObject = cameraStream
    }
  }, [cameraStream])

  // Auto-scroll live chat to bottom on new messages
  useEffect(() => {
    if (rightTab === "live") chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, rightTab])

  const handleConversationTurn = useCallback((userText: string, novaText: string) => {
    const now = Date.now()
    setMessages(prev => [
      ...prev,
      { id: `u-${now}`, role: "user", text: userText, ts: now },
      { id: `n-${now}`, role: "nova", text: novaText, ts: now + 1 },
    ])
    // Refresh history list when a turn completes
    void loadVoiceSessions()
  }, [loadVoiceSessions])

  const handleNewVoiceSession = useCallback(() => {
    setMessages([])
    setSessionId(createVoiceSessionId())
    setRightTab("live")
  }, [])

  const deleteVoiceSession = useCallback(async (sid: string) => {
    try {
      const r = await fetch(`/api/memory/sessions/${encodeURIComponent(sid)}`, { method: "DELETE" })
      if (r.ok) {
        setVoiceSessions(prev => prev.filter(s => s.id !== sid))
        if (selectedSessionRef.current === sid) {
          setSelectedSession(null)
          setSelectedMessages([])
        }
      } else {
        void loadVoiceSessions()
      }
    } catch {
      void loadVoiceSessions()
    }
  }, [loadVoiceSessions])

  const loadSessionMessages = useCallback(async (sid: string) => {
    setSelectedSession(sid)
    setSelectedLoading(true)
    try {
      const r = await fetch(`/api/memory/history/${sid}`)
      if (r.ok) {
        const data = await r.json() as Array<{ role: string; content: string; created_at?: string }>
        const msgs: ChatMessage[] = data.map((m, i) => ({
          id: `h-${sid}-${i}`,
          role: m.role === "user" ? "user" : "nova",
          text: m.content,
          ts: m.created_at ? new Date(m.created_at).getTime() : i,
        }))
        setSelectedMessages(msgs)
      }
    } catch { /* silent */ }
    finally { setSelectedLoading(false) }
  }, [])

  return (
    <AppShell title="Voice" titleColor="text-cyan-400">
      {/* Home card: Nova Voice — cyan-400 icon, from-cyan-500/20 via-teal-500/10, border-cyan-500/30 */}
      <div className="relative flex h-full min-h-0 overflow-hidden">
        <div className="pointer-events-none absolute inset-0 z-0">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/[0.08] via-teal-500/[0.05] to-transparent" />
          <div className="absolute -top-16 right-0 w-80 h-80 rounded-full bg-cyan-500/10 blur-3xl" />
          <div className="absolute bottom-8 left-1/4 w-72 h-72 rounded-full bg-teal-500/8 blur-3xl" />
        </div>
        <div className="relative z-[1] flex h-full w-full min-h-0 overflow-hidden">
        {/* ── Main 2-column body ──────────────────────────────────────────── */}
        <div className="flex h-full min-h-0 flex-1 overflow-hidden">

        {/* Left column — voice orb (full height) */}
        <div className="flex flex-col w-[40%] min-w-[280px] max-w-[480px] border-r border-cyan-500/15 min-h-0">
          <div className="flex-1 min-h-0 relative overflow-hidden bg-[#070710]">
            <div className="absolute inset-0 pointer-events-none">
              <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-72 h-72 rounded-full bg-gradient-to-br from-cyan-500/12 to-teal-500/8 blur-3xl" />
              <div className="absolute bottom-1/4 left-1/4 w-48 h-48 rounded-full bg-teal-500/10 blur-3xl" />
            </div>
            <VoiceConversation
              embedded
              onClose={() => router.push("/home")}
              onOpenProfile={() => router.push("/settings?tab=voice-camera")}
              sessionId={sessionId}
              modelKey={modelKey}
              onConversationTurn={handleConversationTurn}
              onCameraStream={setCameraStream}
            />
          </div>
        </div>

        {/* Right column — camera (top) + live conversation + history */}
        <div className="flex-1 flex flex-col bg-[#09090f] min-w-0 min-h-0">

          {/* Top: Camera panel — sized to show the full frame */}
          <div className="h-64 shrink-0 border-b border-white/[0.07] bg-[#060609] flex flex-col">
            <div className="flex items-center justify-between px-3 py-2 border-b border-white/[0.07] shrink-0">
              <div className="flex items-center gap-1.5">
                <Camera className="w-3 h-3 text-cyan-400/70" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-white/30">Nova Camera</span>
              </div>
              <span className={cn("text-[10px] font-medium", cameraStream ? "text-emerald-400" : "text-white/20")}>
                {cameraStream ? "● Live" : "Off"}
              </span>
            </div>
            <div className="relative flex-1 min-h-0 bg-black overflow-hidden">
              {cameraStream ? (
                <video ref={cameraVideoRef} autoPlay muted playsInline className="w-full h-full object-contain -scale-x-100" />
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-white/10">
                  <Camera className="w-8 h-8" />
                  <p className="text-[11px]">Activates with voice</p>
                </div>
              )}
            </div>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-white/[0.07] shrink-0 bg-[#09090f]">
            <button
              onClick={() => setRightTab("live")}
              className={cn(
                "flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-all duration-150",
                rightTab === "live"
                  ? "border-cyan-500 text-white"
                  : "border-transparent text-white/25 hover:text-white/60"
              )}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              Live
              {messages.length > 0 && (
                <span className="ml-1 bg-cyan-500/20 text-cyan-400 text-[10px] rounded-full px-1.5 py-0.5 font-bold">
                  {messages.length}
                </span>
              )}
            </button>
            <button
              onClick={() => { setRightTab("history"); setSelectedSession(null) }}
              className={cn(
                "flex items-center gap-2 px-5 py-3 text-sm font-semibold border-b-2 transition-all duration-150",
                rightTab === "history"
                  ? "border-cyan-500 text-white"
                  : "border-transparent text-white/25 hover:text-white/60"
              )}
            >
              <History className="w-3.5 h-3.5" />
              History
              {voiceSessions.length > 0 && (
                <span className="ml-1 bg-white/[0.07] text-white/35 text-[10px] rounded-full px-1.5 py-0.5 font-bold">
                  {voiceSessions.length}
                </span>
              )}
            </button>
          </div>

          {/* ── Live tab ── */}
          {rightTab === "live" && (
            <>
              <div className="flex-1 min-h-0 overflow-y-auto px-5 py-5 space-y-5 scrollbar-thin">
                {messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full gap-4 text-white/15 select-none">
                    <div className="w-16 h-16 rounded-full border-2 border-dashed border-white/10 flex items-center justify-center">
                      <UserIcon className="w-7 h-7" />
                    </div>
                    <div className="text-center space-y-1">
                      <p className="text-sm font-medium text-white/20">No transcript yet</p>
                      <p className="text-xs text-white/10">Press the mic and start speaking</p>
                    </div>
                  </div>
                ) : (
                  messages.map(msg => (
                    <div
                      key={msg.id}
                      className={cn(
                        "flex gap-3 max-w-[85%]",
                        msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                      )}
                    >
                      <div className={cn(
                        "w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-[11px] font-bold mt-0.5",
                        msg.role === "nova"
                          ? "bg-gradient-to-br from-cyan-500 to-teal-600 text-white shadow-lg shadow-cyan-900/30"
                          : "text-white"
                      )} style={msg.role === "user" && user ? { backgroundColor: user.avatar_color } : {}}>
                        {msg.role === "nova" ? "N" : (user?.display_name[0].toUpperCase() ?? "U")}
                      </div>
                      <div className={cn(
                        "px-4 py-2.5 text-sm leading-relaxed",
                        msg.role === "nova"
                          ? "bg-white/[0.05] text-white/80 rounded-2xl rounded-tl-sm border border-white/[0.07]"
                          : "bg-cyan-600/20 text-white/90 rounded-2xl rounded-tr-sm border border-cyan-500/20"
                      )}>
                        {msg.text}
                      </div>
                    </div>
                  ))
                )}
                <div ref={chatEndRef} />
              </div>
              <div className="px-5 py-2.5 border-t border-white/[0.07] shrink-0 flex items-center justify-between bg-[#09090f]">
                <div className="flex items-center gap-3">
                  <span className="text-[10px] text-white/20">
                    {messages.length === 0 ? "Transcript will appear here" : `${messages.length} turn${messages.length !== 1 ? "s" : ""}`}
                  </span>
                  {messages.length > 0 && (
                    <button
                      onClick={handleNewVoiceSession}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold bg-cyan-600/20 hover:bg-cyan-600/35 text-cyan-400 border border-cyan-500/20 transition-colors"
                    >
                      <Plus className="w-3 h-3" />
                      New
                    </button>
                  )}
                </div>
                {user && (
                  <div className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold shrink-0" style={{ backgroundColor: user.avatar_color }}>
                      {user.display_name[0].toUpperCase()}
                    </div>
                    <span className="text-[10px] text-white/30">{user.display_name}</span>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── History tab ── */}
          {rightTab === "history" && !selectedSession && (
            <div className="flex-1 min-h-0 overflow-y-auto scrollbar-thin">
              {historyLoading ? (
                <div className="flex items-center justify-center h-full text-white/20 text-sm">Loading…</div>
              ) : voiceSessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-3 text-white/15 select-none">
                  <div className="w-16 h-16 rounded-full border-2 border-dashed border-white/10 flex items-center justify-center">
                    <History className="w-7 h-7" />
                  </div>
                  <div className="text-center">
                    <p className="text-sm font-medium text-white/20">No past conversations</p>
                    <p className="text-xs text-white/10 mt-1">Your voice history will appear here</p>
                  </div>
                </div>
              ) : (
                <ul className="divide-y divide-white/[0.05]">
                  {voiceSessions.map(s => (
                    <li key={s.id} className="group relative">
                      <button
                        onClick={() => loadSessionMessages(s.id)}
                        className="w-full text-left px-5 py-4 hover:bg-white/[0.04] transition-colors"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-semibold text-white/70 group-hover:text-white/90 truncate transition-colors">{s.title}</p>
                            <p className="text-xs text-white/25 mt-0.5 truncate">{s.preview}</p>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="flex items-center gap-1 text-[10px] text-white/20">
                              <Clock className="w-3 h-3" />
                              {formatRelativeTime(s.created_at)}
                            </div>
                            <p className="text-[10px] text-white/15 mt-0.5">{s.message_count} msg</p>
                          </div>
                        </div>
                      </button>
                      <button
                        onClick={e => { e.stopPropagation(); void deleteVoiceSession(s.id) }}
                        className="absolute top-3 right-3 hidden group-hover:flex items-center justify-center w-6 h-6 rounded hover:bg-red-500/15 text-white/20 hover:text-red-400 transition-colors"
                        title="Delete session"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* ── History detail view ── */}
          {rightTab === "history" && selectedSession && (
            <>
              <div className="px-4 py-3 border-b border-white/[0.07] shrink-0 flex items-center gap-3 bg-[#09090f]">
                <button
                  onClick={() => setSelectedSession(null)}
                  className="text-[11px] text-white/30 hover:text-white/60 transition-colors flex items-center gap-1"
                >
                  ← Back
                </button>
                <div className="w-px h-3.5 bg-white/10 shrink-0" />
                <span className="text-xs text-white/40 truncate font-medium">
                  {voiceSessions.find(s => s.id === selectedSession)?.title ?? "Session"}
                </span>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto px-5 py-5 space-y-5 scrollbar-thin">
                {selectedLoading ? (
                  <div className="flex items-center justify-center h-full text-white/20 text-sm">Loading…</div>
                ) : selectedMessages.length === 0 ? (
                  <div className="flex items-center justify-center h-full text-white/20 text-sm">No messages</div>
                ) : (
                  selectedMessages.map(msg => (
                    <div
                      key={msg.id}
                      className={cn(
                        "flex gap-3 max-w-[85%]",
                        msg.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                      )}
                    >
                      <div className={cn(
                        "w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-[11px] font-bold mt-0.5",
                        msg.role === "nova"
                          ? "bg-gradient-to-br from-cyan-500 to-teal-600 text-white"
                          : "text-white"
                      )} style={msg.role === "user" && user ? { backgroundColor: user.avatar_color } : {}}>
                        {msg.role === "nova" ? "N" : (user?.display_name[0].toUpperCase() ?? "U")}
                      </div>
                      <div className={cn(
                        "px-4 py-2.5 text-sm leading-relaxed",
                        msg.role === "nova"
                          ? "bg-white/[0.05] text-white/75 rounded-2xl rounded-tl-sm border border-white/[0.07]"
                          : "bg-cyan-600/20 text-white/85 rounded-2xl rounded-tr-sm border border-cyan-500/20"
                      )}>
                        {msg.text}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}

        </div>
        </div>
        </div>
      </div>
    </AppShell>
  )
}
