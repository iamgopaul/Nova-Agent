"use client"

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { ChatSidebar, type ChatSessionSummary } from "@/components/chat/chat-sidebar"
import { ChatWindow } from "@/components/chat/chat-window"
import { ChatInput } from "@/components/chat/chat-input"
import { ChatHeader, type ChatModelKey } from "@/components/chat/chat-header"
import { AppShell } from "@/components/app-shell"
import type { Message, MessageAttachment, DocItem, StorySectionItem } from "@/components/chat/message-bubble"
import {
  clearSessionMessagesStorage,
  loadSessionMessagesFromStorage,
  saveSessionMessagesToStorage,
} from "@/lib/chat-messages-persist"
import { tryHandleSuggestionAction } from "@/lib/suggestion-actions"

function newId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `msg-${crypto.randomUUID()}`
  }
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

function createSessionId() {
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// Detect messages that are actually leaked format/system prompts accidentally saved
// to the DB by the old LLM-based /chat/format endpoint.  They should never appear
// in the UI chat window and must not be sent to the LLM as prior conversation.
const CORRUPT_PATTERNS = [
  /Reproduce ALL text verbatim/i,
  /Return ONLY a single valid JSON object with keys .intro/i,
  /Never shorten,?\s+paraphrase,?\s+omit/i,
  /Here's the breakdown of your request/i,
  /'intro': ONLY an explicit conversational opening/i,
  /"outro" must ONLY contain text/i,
]

function apiHistoryToMessages(sessionId: string, history: HistoryMessage[]): Message[] {
  return history
    .filter(entry => !isCorruptMessage(entry.content))
    .map((entry, index) => ({
      id: `history-${sessionId}-${index}`,
      role: entry.role,
      content: entry.content,
      timestamp: new Date(entry.created_at),
    }))
}

function isCorruptMessage(content: string): boolean {
  return CORRUPT_PATTERNS.some(p => p.test(content))
}

const VALID_MODEL_KEYS = new Set<ChatModelKey>([
  "auto", "spark", "air", "core", "pro", "code", "vision", "mind",
  "creative", "insight", "sage", "chat", "logic", "mini", "star", "open",
  "quant", "reason",
  // legacy aliases kept for localStorage compatibility
  "basic", "swift",
])

function isChatModelKey(value: string | null): value is ChatModelKey {
  return value !== null && VALID_MODEL_KEYS.has(value as ChatModelKey)
}

type NovaChunk = {
  type: "text" | "done" | "error" | "status" | "replace" | "music_generate" | "image_generate" | "doc_generate" | "chart_generate" | "mermaid_generate" | "story_sections" | "web_results" | "weather_data" | "clock_widget"
  content: string
  response?: string   // actual assistant reply, present on doc_generate events
  web_images?: string // JSON-encoded list of web image URLs, present on doc_generate for essay+images
  index?: number      // 0-based index for multi-image batches
  total?: number      // total images requested in this batch
}


type HistoryMessage = {
  role: "user" | "assistant"
  content: string
  created_at: string
}

type FolderSummary = {
  name: string
  created_at: string
}

type AttachmentPayload = {
  name: string
  content_type: string
  data: string
}

function buildInitialSteps(attachments: File[]) {
  if (!attachments.length) {
    return ["Message received", "Analyzing request"]
  }

  const hasImage = attachments.some(file => file.type.startsWith("image/"))
  const hasZip = attachments.some(file => file.type.includes("zip") || file.name.toLowerCase().endsWith(".zip"))
  const hasPdf = attachments.some(file => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"))
  const hasOtherFile = attachments.some(file => !file.type.startsWith("image/") && !file.type.includes("zip") && file.type !== "application/pdf")

  const steps: string[] = ["Message and attachments received", "Classifying attachments"]
  if (hasZip) {
    steps.push("Preparing to unzip archive")
  }
  if (hasImage) {
    steps.push("Preparing image analysis")
  }
  if (hasPdf) {
    steps.push("Preparing PDF text extraction")
  }
  if (hasOtherFile) {
    steps.push("Preparing file text extraction")
  }
  steps.push("Building response plan")
  return steps
}

function appendStatusStep(existing: string[] | undefined, nextStep: string) {
  const normalized = (nextStep || "").trim()
  if (!normalized) {
    return existing || []
  }

  const current = existing || []
  if (current[current.length - 1] === normalized) {
    return current
  }

  const deduped = current.filter(step => step !== normalized)
  const combined = [...deduped, normalized]
  return combined.slice(-12)
}

async function fetchLLMSuggestions(userText: string, assistantText: string): Promise<string[]> {
  try {
    const res = await fetch("/api/chat/suggestions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_message: userText.slice(0, 300),
        assistant_response: assistantText.slice(0, 1200),
      }),
    })
    if (!res.ok) return []
    const data = await res.json() as { suggestions: string[] }
    return Array.isArray(data.suggestions) ? data.suggestions.slice(0, 3) : []
  } catch {
    return []
  }
}

async function fetchLLMFormat(content: string): Promise<{ intro: string; body: string; outro: string } | null> {
  try {
    const res = await fetch("/api/chat/format", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    })
    if (!res.ok) return null
    const data = await res.json() as { intro: string; body: string; outro: string }
    // Only return sections if they actually split something meaningful
    if (!data.intro && !data.outro) return null
    return data
  } catch {
    return null
  }
}

async function fetchMusicAudio(prompt: string, duration: number = 12): Promise<string | null> {
  try {
    const res = await fetch("/api/music/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, duration }),
    })
    if (!res.ok) return null
    const blob = await res.blob()
    return URL.createObjectURL(blob)
  } catch {
    return null
  }
}

async function fetchImageGen(
  prompt: string,
  opts?: { width?: number; height?: number; steps?: number; guidance_scale?: number }
): Promise<string | null> {
  try {
    const res = await fetch("/api/image/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        width:          opts?.width          ?? 640,
        height:         opts?.height         ?? 640,
        steps:          opts?.steps          ?? 30,
        guidance_scale: opts?.guidance_scale ?? 8.5,
      }),
    })
    if (!res.ok) return null
    const blob = await res.blob()
    return URL.createObjectURL(blob)
  } catch {
    return null
  }
}

async function fetchDocGen(
  prompt: string,
  format: string,
  response?: string,
  webImageUrls?: string[],
): Promise<{ url: string; filename: string; sizeBytes: number } | null> {
  try {
    const res = await fetch("/api/document/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        format,
        ...(response ? { response } : {}),
        ...(webImageUrls && webImageUrls.length > 0 ? { web_image_urls: webImageUrls } : {}),
      }),
    })
    if (!res.ok) return null
    const blob     = await res.blob()
    const filename = res.headers.get("X-Nova-Filename") ?? `nova_document.${format}`
    return { url: URL.createObjectURL(blob), filename, sizeBytes: blob.size }
  } catch {
    return null
  }
}

const MODEL_STORAGE_KEY = "nova.selectedModelKey"
const SESSION_STORAGE_KEY = "nova.activeSessionId"

function messageTimestampToIso(t: Date | string | number | undefined): string {
  if (t == null) {
    return new Date().toISOString()
  }
  if (t instanceof Date) {
    return t.toISOString()
  }
  const d = new Date(t)
  return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString()
}

function buildSessionSummaryFromMessages(
  sessionId: string,
  currentMessages: Message[],
): ChatSessionSummary {
  const firstUser = currentMessages.find(message => message.role === "user")
  const firstLine = (firstUser?.content || "").replace(/\n/g, " ").trim()
  const title = firstLine.slice(0, 64) || "New chat"
  const last = currentMessages.length
    ? currentMessages[currentMessages.length - 1]
    : null
  const lastLine = (last?.content || "").replace(/\n/g, " ").trim()
  const preview = lastLine.slice(0, 200)
  const lastIso = last
    ? messageTimestampToIso(last.timestamp)
    : null
  const createdIso = firstUser
    ? messageTimestampToIso(firstUser.timestamp)
    : lastIso ?? new Date().toISOString()
  return {
    id:         sessionId,
    title:      title || "New chat",
    preview:    preview,
    folder:     null,
    created_at: createdIso,
    last_message_at: lastIso,
    message_count: currentMessages.length,
  }
}

/**
 * The API response replaces the whole list, but rows that only existed as client-side
 * placeholder summaries (or localStorage) must be preserved until the server lists them.
 */
function mergeSessionListWithOrphans(
  fromApi: ChatSessionSummary[],
  previous: ChatSessionSummary[],
): ChatSessionSummary[] {
  if (typeof window === "undefined") {
    return fromApi
  }
  const fromApiIds = new Set(fromApi.map(s => s.id))
  const out: ChatSessionSummary[] = [...fromApi]
  for (const s of previous) {
    if (fromApiIds.has(s.id)) {
      continue
    }
    if (s.message_count > 0) {
      out.push(s)
      continue
    }
    const stored = loadSessionMessagesFromStorage(s.id)
    if (stored && stored.length > 0) {
      out.push(s)
    }
  }
  return out.sort((a, b) => {
    const t = (x: ChatSessionSummary) =>
      new Date(x.last_message_at || x.created_at).getTime() || 0
    return t(b) - t(a)
  })
}

/**
 * The sessions API lags or omits a row until the first message is fully persisted
 * (or a brand-new local session id is made).  Show the active thread in the
 * sidebar anyway so the list matches what is open in the main panel.
 */
function withSidebarPlaceholder(
  fromApi: ChatSessionSummary[],
  activeId: string,
  currentMessages: Message[],
): ChatSessionSummary[] {
  if (!activeId) {
    return fromApi
  }
  if (fromApi.some(session => session.id === activeId)) {
    return fromApi
  }
  // Show this conversation first; it is the one open in the main pane.
  return [buildSessionSummaryFromMessages(activeId, currentMessages), ...fromApi]
}

const MODEL_LABELS: Record<ChatModelKey, { name: string; backend: string }> = {
  auto:    { name: "Nova Auto",     backend: "llm-router"              },
  spark:   { name: "Nova Spark",    backend: "llama3.2:3b"             },
  air:     { name: "Nova Air",      backend: "gemma3:4b"               },
  core:    { name: "Nova Core",     backend: "mistral:7b"              },
  pro:     { name: "Nova Pro",      backend: "qwen2.5:72b"             },
  code:    { name: "Nova Code",     backend: "qwen2.5-coder:32b"       },
  vision:  { name: "Nova Vision",   backend: "llama3.2-vision:11b"     },
  mind:    { name: "Nova Mind",     backend: "gemma3:27b"              },
  creative:{ name: "Nova Creative", backend: "dolphin-mixtral:8x7b"    },
  insight: { name: "Nova Insight",  backend: "zephyr:7b"               },
  sage:    { name: "Nova Sage",     backend: "nous-hermes:13b"         },
  chat:    { name: "Nova Chat",     backend: "neural-chat:7b"          },
  logic:   { name: "Nova Logic",    backend: "orca-mini:7b"            },
  mini:    { name: "Nova Mini",     backend: "phi:2.7b"                },
  star:    { name: "Nova Star",     backend: "starling-lm:7b"          },
  open:    { name: "Nova Open",     backend: "openchat:7b"             },
  // Quantitative & reasoning specialists
  quant:   { name: "Nova Quant",   backend: "mathstral:7b"            },
  reason:  { name: "Nova Reason",  backend: "deepseek-r1:7b"          },
  // legacy aliases
  basic:   { name: "Nova Basic",   backend: "llama3.2:3b"             },
  swift:   { name: "Nova Swift",   backend: "gemma3:4b"               },
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [folders, setFolders] = useState<string[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isLoadingSessions, setIsLoadingSessions] = useState(true)
  const [activeSessionId, setActiveSessionId] = useState("")
  const [selectedModelKey, setSelectedModelKey] = useState<ChatModelKey>("auto")

  const stopRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const activeSessionRef = useRef("")
  const initializedSessionsRef = useRef(false)
  /** Distinguish cold `localStorage` restore from a session id created in this tab (first send before the server list includes it). */
  const sessionOriginRef = useRef<"default" | "restored" | "client">("default")
  const attachmentUrlsRef = useRef<Set<string>>(new Set())
  // Tracks which session's messages are currently held in memory.
  // loadHistory skips if this already matches the requested session,
  // preventing it from wiping rich UI state (attachments, suggestions,
  // images, docs) that was built up during or after streaming.
  const loadedSessionRef = useRef<string>("")
  /** Latest messages for synchronous flush on page hide (debounced save may not have run). */
  const messagesForPersistRef = useRef<Message[]>([])
  /** Cancel in-flight history fetch when the user switches chats quickly. */
  const historyFetchAbortRef = useRef<AbortController | null>(null)
  /** Prefetched thread bodies (other sessions) so switching tabs feels instant. */
  const historyWarmCacheRef = useRef<Map<string, Message[]>>(new Map())

  const revokeAttachmentUrls = useCallback((messagesToClean: Message[]) => {
    for (const message of messagesToClean) {
      for (const attachment of message.attachments || []) {
        if (attachment.url) {
          URL.revokeObjectURL(attachment.url)
          attachmentUrlsRef.current.delete(attachment.url)
        }
      }
    }
  }, [])

  useEffect(() => {
    return () => {
      for (const url of attachmentUrlsRef.current) {
        URL.revokeObjectURL(url)
      }
      attachmentUrlsRef.current.clear()
    }
  }, [])

  const loadHistory = useCallback(async (sessionId: string) => {
    if (!sessionId) {
      loadedSessionRef.current = ""
      setMessages(prev => {
        revokeAttachmentUrls(prev)
        return []
      })
      return
    }

    // Already have in-memory messages for this session (built up during streaming
    // or from a previous load).  Don't replace them — we would lose all rich UI
    // state: attachments, blob URLs, suggestions, sections, generated images, docs.
    if (loadedSessionRef.current === sessionId) {
      return
    }

    loadedSessionRef.current = sessionId

    // 1) Restore full client-side state (web results, weather, sections, suggestions, charts,
    //    mermaid, clock, etc.) — survives page refresh. Blob URLs (generated media, file
    //    previews) are intentionally not persisted; those panels may be empty until regenerated.
    if (typeof window !== "undefined") {
      const fromStorage = loadSessionMessagesFromStorage(sessionId)
      if (fromStorage !== null) {
        setMessages(prev => {
          revokeAttachmentUrls(prev)
          return fromStorage
        })
        return
      }
    }

    if (historyWarmCacheRef.current.has(sessionId)) {
      const warm = historyWarmCacheRef.current.get(sessionId)!
      setMessages(prev => {
        revokeAttachmentUrls(prev)
        return warm
      })
    }

    historyFetchAbortRef.current?.abort()
    const ac = new AbortController()
    historyFetchAbortRef.current = ac

    try {
      const response = await fetch(
        `/api/memory/history/${encodeURIComponent(sessionId)}?n=2000`,
        { signal: ac.signal },
      )
      if (!response.ok) {
        if (!historyWarmCacheRef.current.has(sessionId)) {
          setMessages(prev => {
            revokeAttachmentUrls(prev)
            return []
          })
        }
        return
      }

      const history = await response.json() as HistoryMessage[]
      const mapped = apiHistoryToMessages(sessionId, history)
      historyWarmCacheRef.current.set(sessionId, mapped)
      setMessages(prev => {
        revokeAttachmentUrls(prev)
        return mapped
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return
      }
      if (!historyWarmCacheRef.current.has(sessionId)) {
        setMessages(prev => {
          revokeAttachmentUrls(prev)
          return []
        })
      }
    }
  }, [revokeAttachmentUrls])

  const refreshSessions = useCallback(async (preferredSessionId?: string) => {
    setIsLoadingSessions(true)

    try {
      const [sesRes, foldRes] = await Promise.all([
        fetch("/api/memory/sessions"),
        fetch("/api/memory/folders"),
      ])
      if (foldRes.ok) {
        const data = await foldRes.json() as FolderSummary[]
        setFolders(data.map(folder => folder.name).sort((a, b) => a.localeCompare(b)))
      } else {
        setFolders([])
      }

      if (!sesRes.ok) {
        throw new Error("Failed to load chat sessions")
      }

      const nextSessions = await sesRes.json() as ChatSessionSummary[]
      setSessions(prev => mergeSessionListWithOrphans(nextSessions, prev))

      const idSet = new Set(nextSessions.map(s => s.id))
      for (const k of historyWarmCacheRef.current.keys()) {
        if (!idSet.has(k)) {
          historyWarmCacheRef.current.delete(k)
        }
      }

      if (!initializedSessionsRef.current) {
        initializedSessionsRef.current = true
        const remembered = (preferredSessionId ?? activeSessionRef.current ?? "").trim()
        const inList = nextSessions.some(session => session.id === remembered)
        const matched = inList ? remembered : undefined
        // Prefer the id that exists on the server; otherwise first conversation.
        // Stale `localStorage` ids (not on the server) are dropped in favor of `firstId`
        // so the sidebar and main pane stay in sync. But if the user already sent
        // a message, we use a *client* session id that is not in the list yet; that
        // id must be kept or `loadHistory` will jump to the wrong row and clear the UI.
        const firstId = nextSessions[0]?.id
        // Keep a session id that exists only in localStorage (e.g. first message not yet
        // synced), or the last-opened tab (restored) when the server list is empty
        // or the DB was recreated — the old code dropped "restored" and cleared active
        // session, which removed localStorage and made chat look "wiped" on every restart.
        const fromClientOrRestored =
          sessionOriginRef.current === "client" || sessionOriginRef.current === "restored"
        const keepUnsyncedLocal =
          Boolean(remembered)
          && !inList
          && (fromClientOrRestored || nextSessions.length === 0)
        const nextActive: string = matched
          || (keepUnsyncedLocal ? remembered : firstId)
          || ""
        if (matched) {
          sessionOriginRef.current = "default"
        }
        activeSessionRef.current = nextActive
        setActiveSessionId(nextActive)
      }

      // Prefetch other threads in parallel so switching chats is instant.
      const cur = activeSessionRef.current
      const others = nextSessions.filter(s => s.id !== cur).slice(0, 24)
      for (const s of others) {
        if (historyWarmCacheRef.current.has(s.id)) {
          continue
        }
        const sid = s.id
        void (async () => {
          try {
            const r = await fetch(`/api/memory/history/${encodeURIComponent(sid)}?n=2000`)
            if (!r.ok) {
              return
            }
            const history = (await r.json()) as HistoryMessage[]
            const mapped = apiHistoryToMessages(sid, history)
            historyWarmCacheRef.current.set(sid, mapped)
          } catch {
            /* non-fatal */
          }
        })()
      }
    } catch {
      if (!initializedSessionsRef.current) {
        initializedSessionsRef.current = true
        const fromLs =
          (typeof window !== "undefined" ? window.localStorage.getItem(SESSION_STORAGE_KEY) : null) ?? ""
        const remembered = (preferredSessionId ?? activeSessionRef.current ?? fromLs).trim()
        if (remembered) {
          sessionOriginRef.current = "restored"
          activeSessionRef.current = remembered
          setActiveSessionId(remembered)
        }
      }
    } finally {
      setIsLoadingSessions(false)
    }
  }, [])

  const refreshFolders = useCallback(async () => {
    try {
      const response = await fetch("/api/memory/folders")
      if (!response.ok) {
        throw new Error("Failed to load folders")
      }

      const data = await response.json() as FolderSummary[]
      setFolders(data.map(folder => folder.name).sort((a, b) => a.localeCompare(b)))
    } catch {
      setFolders([])
    }
  }, [])

  // Restore last-open session before paint so the first `loadHistory` / sync effects
  // do not see activeSessionId === "" (that path clears messages and shows an empty
  // main pane on cold start and after closing & reopening the app).
  useLayoutEffect(() => {
    if (typeof window === "undefined") {
      return
    }
    const saved = window.localStorage.getItem(SESSION_STORAGE_KEY)
    if (saved) {
      sessionOriginRef.current = "restored"
      activeSessionRef.current = saved
      setActiveSessionId(saved)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") {
      return
    }

    const savedModelKey = window.localStorage.getItem(MODEL_STORAGE_KEY)
    if (isChatModelKey(savedModelKey)) {
      const migrated = (savedModelKey === "basic" || savedModelKey === "swift")
        ? "auto"
        : savedModelKey
      setSelectedModelKey(migrated)
    }

    const savedSessionId = window.localStorage.getItem(SESSION_STORAGE_KEY)
    void refreshSessions(savedSessionId || undefined)
  }, [refreshSessions])

  useEffect(() => {
    if (typeof window === "undefined") {
      return
    }

    window.localStorage.setItem(MODEL_STORAGE_KEY, selectedModelKey)
  }, [selectedModelKey])

  useEffect(() => {
    activeSessionRef.current = activeSessionId
    if (typeof window === "undefined") {
      return
    }

    if (activeSessionId) {
      window.localStorage.setItem(SESSION_STORAGE_KEY, activeSessionId)
    } else {
      window.localStorage.removeItem(SESSION_STORAGE_KEY)
    }
  }, [activeSessionId])

  useEffect(() => {
    void loadHistory(activeSessionId)
  }, [activeSessionId, loadHistory])

  useEffect(() => {
    messagesForPersistRef.current = messages
  }, [messages])

  // Ask for persistent web storage (less likely to be cleared on disk pressure; Chromium/Firefox).
  useEffect(() => {
    if (typeof window === "undefined" || !navigator.storage?.persist) {
      return
    }
    void navigator.storage.persist().catch(() => {})
  }, [])

  // Synchronous save when the app goes away so the last reply is not lost to debounce.
  useEffect(() => {
    if (typeof window === "undefined") {
      return
    }
    const flush = () => {
      const sid = activeSessionRef.current
      if (sid) {
        saveSessionMessagesToStorage(sid, messagesForPersistRef.current)
      }
    }
    const onVis = () => {
      if (document.visibilityState === "hidden") {
        flush()
      }
    }
    window.addEventListener("pagehide", flush)
    window.addEventListener("beforeunload", flush)
    document.addEventListener("visibilitychange", onVis)
    return () => {
      window.removeEventListener("pagehide", flush)
      window.removeEventListener("beforeunload", flush)
      document.removeEventListener("visibilitychange", onVis)
    }
  }, [])

  // Persist the full in-memory message model so refresh (and hard reload) keeps
  // side panels: web results, weather, clock, sections, suggestions, charts, mermaid, etc.
  useEffect(() => {
    if (typeof window === "undefined" || !activeSessionId) {
      return
    }
    const t = window.setTimeout(() => {
      saveSessionMessagesToStorage(activeSessionId, messages)
    }, 450)
    return () => window.clearTimeout(t)
  }, [messages, activeSessionId])

  const sessionsForSidebar = useMemo(
    () => withSidebarPlaceholder(sessions, activeSessionId, messages),
    [sessions, activeSessionId, messages],
  )

  const streamResponse = useCallback(async (
    text: string,
    aiMsgId: string,
    sessionId: string,
    attachments: AttachmentPayload[] = [],
    seedSteps: string[] = [],
  ) => {
    // Claim session ownership so loadHistory never overwrites our in-progress messages
    loadedSessionRef.current = sessionId

    const controller = new AbortController()
    abortRef.current = controller
    let receivedText = false
    let sawBackendStatus = false
    let stopSeedSteps = false
    let assembledText = ""
    let statusChain: Promise<void> = Promise.resolve()

    const queueStatusStep = (content: string, minDelayMs = 220) => {
      const normalized = (content || "").trim()
      if (!normalized) {
        return statusChain
      }

      statusChain = statusChain.then(async () => {
        setMessages(prev => prev.map(message => (
          message.id === aiMsgId
            ? {
              ...message,
              statusText: normalized,
              statusSteps: appendStatusStep(message.statusSteps, normalized),
              thinking: true,
            }
            : message
        )))
        await new Promise<void>(resolve => setTimeout(resolve, minDelayMs))
      })

      return statusChain
    }

    setMessages(prev => prev.map(message => (
      message.id === aiMsgId
        ? {
          ...message,
          statusText: "Connecting to Nova backend",
          statusSteps: appendStatusStep(message.statusSteps, "Connecting to Nova backend"),
          thinking: true,
        }
        : message
    )))

    if (seedSteps.length > 1) {
      void (async () => {
        for (let i = 1; i < seedSteps.length; i += 1) {
          await new Promise<void>(resolve => setTimeout(resolve, 140))
          if (stopSeedSteps || sawBackendStatus) {
            return
          }
          await queueStatusStep(seedSteps[i], 120)
        }
      })()
    }

    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
        mode: "default",
        model_key: selectedModelKey === "auto" ? null : selectedModelKey,
        attachments,
      }),
      signal: controller.signal,
    })

    if (!response.ok || !response.body) {
      const detail = await response.text()
      throw new Error(detail || "Chat request failed")
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      // Defer handling `done` until every `data:` line in this batch is processed.
      // Otherwise a `done` line that appears before `web_results` in the same TCP
      // chunk would cause an early `return` and drop side-car events (images, weather).
      let donePayloadInBatch: NovaChunk | null = null

      for (const line of lines) {
        if (!line.startsWith("data:")) {
          continue
        }

        const payload = line.slice(5).trim()
        if (!payload) {
          continue
        }

        const chunk = JSON.parse(payload) as NovaChunk

        if (chunk.type === "done") {
          donePayloadInBatch = chunk
          continue
        }

        if (chunk.type === "text") {
          stopSeedSteps = true
          await statusChain
          const content = chunk.content || ""
          receivedText = true
          assembledText += content
          setMessages(prev => prev.map(message => (
            message.id === aiMsgId
              ? {
                ...message,
                content: message.thinking ? content : (message.content || "") + content,
                statusText: "",
                thinking: false,
              }
              : message
          )))
          continue
        }

        // replace: backend detected a corrupt/echo response and sends a clean one
        if (chunk.type === "replace") {
          const clean = chunk.content ?? ""
          assembledText = clean
          setMessages(prev => prev.map(message => (
            message.id === aiMsgId
              ? { ...message, content: clean, statusText: "", thinking: false }
              : message
          )))
          continue
        }

        if (chunk.type === "status") {
          sawBackendStatus = true
          stopSeedSteps = true
          const content = chunk.content || "Working"
          await queueStatusStep(content, 180)
          continue
        }

        if (chunk.type === "error") {
          throw new Error(chunk.content || "Backend error")
        }

        if (chunk.type === "music_generate") {
          const musicPrompt = chunk.content || ""
          setMessages(prev => prev.map(message => (
            message.id === aiMsgId
              ? { ...message, musicPrompt, musicGenerating: true, musicUrl: undefined, musicError: false }
              : message
          )))
          void fetchMusicAudio(musicPrompt).then(musicUrl => {
            setMessages(prev => prev.map(message => (
              message.id === aiMsgId
                ? { ...message, musicGenerating: false, musicError: !musicUrl, ...(musicUrl ? { musicUrl } : {}) }
                : message
            )))
          })
          continue
        }

        if (chunk.type === "image_generate") {
          const imagePrompt = chunk.content || ""
          const imgIdx   = chunk.index ?? 0
          const imgTotal = chunk.total ?? 1

          // Mark generating + reserve a slot for this image index
          setMessages(prev => prev.map(message => {
            if (message.id !== aiMsgId) return message
            const existing = message.imageUrls ?? (message.imageUrl ? [message.imageUrl] : [])
            // Extend array to hold imgTotal entries (undefined = still generating)
            const slots: (string | undefined)[] = [...Array(Math.max(imgTotal, existing.length))]
            existing.forEach((u, i) => { slots[i] = u })
            return {
              ...message,
              imagePrompt,
              imageGenerating: true,
              imageUrls: slots as string[],
            }
          }))

          void fetchImageGen(imagePrompt).then(imageUrl => {
            setMessages(prev => prev.map(message => {
              if (message.id !== aiMsgId) return message
              const slots = [...(message.imageUrls ?? [])]
              if (imageUrl) slots[imgIdx] = imageUrl
              const allDone = slots.filter(Boolean).length >= imgTotal
              return {
                ...message,
                imageGenerating: !allDone,
                imageUrls: slots.filter(Boolean) as string[],
                // Keep backward-compat imageUrl pointing to first image
                imageUrl: slots.find(Boolean),
              }
            }))
          })
          continue
        }

        if (chunk.type === "doc_generate") {
          // content is "format|original_user_message"
          const [docFormat, ...rest] = (chunk.content || "docx|document").split("|")
          const docPrompt = rest.join("|")
          // response carries the actual chat reply — document will match what was shown
          const docResponse = chunk.response ?? ""
          // web_images is a JSON-encoded list of per-section web image URLs
          let docWebImages: string[] = []
          if (chunk.web_images) {
            try { docWebImages = JSON.parse(chunk.web_images) } catch { /* ignore */ }
          }
          // Append a new doc entry (generating=true) — supports multiple docs per message
          const newDocEntry: DocItem = { prompt: docPrompt, format: docFormat, generating: true }
          setMessages(prev => prev.map(message => {
            if (message.id !== aiMsgId) return message
            return { ...message, docs: [...(message.docs ?? []), newDocEntry] }
          }))
          void fetchDocGen(docPrompt, docFormat, docResponse, docWebImages).then(result => {
            setMessages(prev => prev.map(message => {
              if (message.id !== aiMsgId) return message
              // Find the last still-generating entry with this format and update it
              let updated = false
              const updatedDocs = [...(message.docs ?? [])].reverse().map(d => {
                if (!updated && d.generating && d.format === docFormat && d.prompt === docPrompt) {
                  updated = true
                  return {
                    ...d,
                    generating: false,
                    ...(result ? { url: result.url, filename: result.filename, sizeBytes: result.sizeBytes } : {}),
                  }
                }
                return d
              }).reverse()
              return { ...message, docs: updatedDocs }
            }))
          })
          continue
        }

        if (chunk.type === "story_sections") {
          try {
            const rawSections: StorySectionItem[] = JSON.parse(chunk.content || "[]")
            // Show sections immediately. If a section already has imageUrl (web image from backend),
            // preserve it. Otherwise mark imageGenerating=true so the frontend fetches an SD image.
            const sectionsWithState: StorySectionItem[] = rawSections.map(s => ({
              ...s,
              imageGenerating: !!s.image_prompt && !s.imageUrl,
              // imageUrl preserved from spread ...s (don't override with undefined)
            }))
            // Clear thinking state so the StoryView renders instead of the spinner.
            // For essay+images mode the text was held back; story_sections IS the reveal.
            setMessages(prev => prev.map(message =>
              message.id === aiMsgId
                ? {
                    ...message,
                    storySections: sectionsWithState,
                    thinking: false,
                    statusText: "",
                  }
                : message
            ))

            // Fire SD image generation only for sections that have an image_prompt
            // but no existing imageUrl (web images are already set from the backend).
            sectionsWithState.forEach((sec, idx) => {
              if (!sec.image_prompt || sec.imageUrl) return
              void fetchImageGen(sec.image_prompt).then(imageUrl => {
                setMessages(prev => prev.map(message => {
                  if (message.id !== aiMsgId) return message
                  const updated = [...(message.storySections ?? [])]
                  if (updated[idx]) {
                    updated[idx] = { ...updated[idx], imageGenerating: false, imageUrl: imageUrl ?? undefined }
                  }
                  return { ...message, storySections: updated }
                }))
              })
            })
          } catch (e) {
            console.error("[Nova] story_sections parse error", e)
          }
          continue
        }

        if (chunk.type === "web_results") {
          try {
            const results = JSON.parse(chunk.content || "{}")
            setMessages(prev => prev.map(message => (
              message.id === aiMsgId
                ? { ...message, webResults: results }
                : message
            )))
          } catch (e) {
            console.error("[Nova] web_results parse error", e)
          }
          continue
        }

        if (chunk.type === "weather_data") {
          try {
            const weatherData = JSON.parse(chunk.content || "{}")
            setMessages(prev => prev.map(message => (
              message.id === aiMsgId
                ? { ...message, weatherData }
                : message
            )))
          } catch (e) {
            console.error("[Nova] weather_data parse error", e)
          }
          continue
        }

        if (chunk.type === "clock_widget") {
          setMessages(prev => prev.map(message => (
            message.id === aiMsgId
              ? { ...message, showClock: true }
              : message
          )))
          continue
        }

        if (chunk.type === "chart_generate") {
          try {
            const spec = JSON.parse(chunk.content || "{}")
            setMessages(prev => prev.map(message => (
              message.id === aiMsgId
                ? { ...message, chartSpec: spec, chartGenerating: false }
                : message
            )))
          } catch {
            setMessages(prev => prev.map(message => (
              message.id === aiMsgId
                ? { ...message, chartGenerating: false }
                : message
            )))
          }
          continue
        }

        if (chunk.type === "mermaid_generate") {
          // Strip any standalone label line that Nova wrote immediately before
          // the ```mermaid fence (e.g. "Timeline Image\n", "Diagram:\n").
          // These are 1-5 word headings/labels sitting on a line by themselves
          // right before the code block — the MermaidDiagram component already
          // shows a "Diagram" header so the label is redundant and confusing.
          setMessages(prev => prev.map(message => {
            if (message.id !== aiMsgId) return message
            const cleanedContent = message.content
              .replace(
                /\n{0,2}[ \t]*[A-Za-z][^\n]{0,60}\n(?=```mermaid)/g,
                "\n"
              )
              // Also strip bare "label:" lines before the fence
              .replace(/\n{0,2}[ \t]*[\w\s]{1,40}:\s*\n(?=```mermaid)/g, "\n")
              .trimEnd()
            return { ...message, mermaidCode: chunk.content, content: cleanedContent }
          }))
          continue
        }

      }

      if (donePayloadInBatch) {
        stopSeedSteps = true
        if (receivedText) {
          await statusChain
          const finalText = assembledText
          setMessages(prev => prev.map(message => (
            message.id === aiMsgId
              ? { ...message, suggestionsLoading: true, suggestions: [], sectionsLoading: true }
              : message
          )))
          void Promise.all([
            fetchLLMSuggestions(text, finalText),
            fetchLLMFormat(finalText),
          ]).then(([suggestions, sections]) => {
            setMessages(prev => prev.map(message => (
              message.id === aiMsgId
                ? { ...message, suggestions, suggestionsLoading: false, ...(sections ? { sections } : {}), sectionsLoading: false }
                : message
            )))
          })
        }
        return
      }
    }

    if (!receivedText) {
      stopSeedSteps = true
      await statusChain
      setMessages(prev => prev.map(message => (
        message.id === aiMsgId
          ? { ...message, thinking: false, statusText: "", content: message.content || "" }
          : message
      )))
      return
    }

    const finalText = assembledText
    setMessages(prev => prev.map(message => (
      message.id === aiMsgId
        ? { ...message, suggestionsLoading: true, suggestions: [], sectionsLoading: true }
        : message
    )))
    void Promise.all([
      fetchLLMSuggestions(text, finalText),
      fetchLLMFormat(finalText),
    ]).then(([suggestions, sections]) => {
      setMessages(prev => prev.map(message => (
        message.id === aiMsgId
          ? { ...message, suggestions, suggestionsLoading: false, ...(sections ? { sections } : {}), sectionsLoading: false }
          : message
      )))
    })
  }, [selectedModelKey])

  const fileToBase64 = useCallback(async (file: File) => {
    return await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => {
        const result = typeof reader.result === "string" ? reader.result : ""
        const base64 = result.split(",")[1] || ""
        resolve(base64)
      }
      reader.onerror = () => {
        reject(new Error(`Failed to read file '${file.name}'.`))
      }
      reader.readAsDataURL(file)
    })
  }, [])

  const handleSend = useCallback(async (text: string, attachments: File[]) => {
    if (isStreaming) {
      return
    }

    const trimmed = text.trim()
    if (!trimmed && attachments.length === 0) {
      return
    }

    let sessionId = activeSessionRef.current
    if (!sessionId) {
      sessionId = createSessionId()
      sessionOriginRef.current = "client"
      activeSessionRef.current = sessionId
      // Mark the session as owned before setActiveSessionId fires, so the
      // loadHistory useEffect sees it and skips — preventing it from wiping
      // the messages we're about to add.
      loadedSessionRef.current = sessionId
      setActiveSessionId(sessionId)
    } else {
      // Ensure we hold the ownership flag for the current session too.
      loadedSessionRef.current = sessionId
    }

    const attachmentPreviews: MessageAttachment[] = attachments.map(file => {
      const url = URL.createObjectURL(file)
      attachmentUrlsRef.current.add(url)
      return {
        name: file.name,
        type: file.type || "application/octet-stream",
        size: file.size,
        url,
      }
    })

    const userMsg: Message = {
      id: newId(),
      role: "user",
      content: trimmed || (attachments.length > 0 ? `Attached ${attachments.length} file${attachments.length === 1 ? "" : "s"}.` : ""),
      timestamp: new Date(),
      attachments: attachmentPreviews,
    }

    setMessages(prev => [...prev, userMsg])
    setIsStreaming(true)
    stopRef.current = false

    const thinkingId = newId()
    const initialSteps = buildInitialSteps(attachments)
    const firstInitialStep = initialSteps[0] || "Reading your request"
    setMessages(prev => [...prev, {
      id: thinkingId,
      role: "assistant",
      content: "",
      statusText: firstInitialStep,
      statusSteps: [firstInitialStep],
      timestamp: new Date(),
      thinking: true,
    }])

    try {
      const prompt = trimmed || "Please review the attached files and images and summarize what you find."
      const encodedAttachments = await Promise.all(attachments.map(async file => ({
        name: file.name,
        content_type: file.type || "application/octet-stream",
        data: await fileToBase64(file),
      })))
      await streamResponse(prompt, thinkingId, sessionId, encodedAttachments, initialSteps)
      void refreshSessions(sessionId)
    } catch (err) {
      if (!stopRef.current) {
        const message = err instanceof Error ? err.message : "Request failed"
        setMessages(prev => prev.map(entry => (
          entry.id === thinkingId
            ? { ...entry, content: `[Error] ${message}`, statusText: "", thinking: false }
            : entry
        )))
      }
    } finally {
      abortRef.current = null
      setIsStreaming(false)
      historyWarmCacheRef.current.delete(sessionId)
    }
  }, [fileToBase64, isStreaming, refreshSessions, streamResponse])

  const handleSuggestionClick = useCallback(
    (suggestion: string, messageContent = "") => {
      if (isStreaming) {
        return
      }
      const action = tryHandleSuggestionAction(suggestion, messages, text => {
        void handleSend(text, [])
      })
      if (action === "consumed" || action === "direct-send") {
        return
      }
      const preview = messageContent.trim().slice(0, 300)
      const contextual = `Regarding your previous response:\n"${preview}${messageContent.length > 300 ? "…" : ""}"\n\n${suggestion}`
      void handleSend(contextual, [])
    },
    [handleSend, isStreaming, messages],
  )

  const handleNewChat = () => {
    if (isStreaming) {
      return
    }
    const previousId = (activeSessionRef.current || "").trim()
    if (previousId) {
      setSessions(prev => {
        if (prev.some(s => s.id === previousId)) {
          return prev
        }
        if (messages.length > 0) {
          return [buildSessionSummaryFromMessages(previousId, messages), ...prev]
        }
        if (typeof window !== "undefined") {
          const stored = loadSessionMessagesFromStorage(previousId)
          if (stored && stored.length > 0) {
            return [buildSessionSummaryFromMessages(previousId, stored), ...prev]
          }
        }
        return prev
      })
    }
    const newSessionId = createSessionId()
    sessionOriginRef.current = "client"
    activeSessionRef.current = newSessionId
    // Claim ownership before setActiveSessionId so loadHistory skips
    loadedSessionRef.current = newSessionId
    setActiveSessionId(newSessionId)
    setMessages(prev => {
      revokeAttachmentUrls(prev)
      return []
    })
  }

  const handleSelectSession = (sessionId: string) => {
    if (isStreaming && sessionId !== activeSessionId) {
      return
    }
    // Clear ownership so loadHistory actually runs for the new session
    loadedSessionRef.current = ""
    activeSessionRef.current = sessionId
    setActiveSessionId(sessionId)
  }

  const handleDeleteSession = async (sessionId: string) => {
    const wasActive = activeSessionRef.current === sessionId
    const remaining = sessions.filter(session => session.id !== sessionId)
    const fallbackSessionId = remaining[0]?.id || ""

    setSessions(remaining)
    clearSessionMessagesStorage(sessionId)

    try {
      const response = await fetch(`/api/memory/sessions/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
      })

      if (!response.ok && response.status !== 204) {
        void refreshSessions(activeSessionRef.current)
        return
      }
    } finally {
      if (wasActive) {
        activeSessionRef.current = fallbackSessionId
        setActiveSessionId(fallbackSessionId)
        if (!fallbackSessionId) {
          setMessages(prev => {
            revokeAttachmentUrls(prev)
            return []
          })
        }
      }
      void refreshSessions(fallbackSessionId)
    }
  }

  const handleRenameSession = async (sessionId: string, title: string) => {
    const nextTitle = title.trim()
    if (!nextTitle) {
      return
    }

    setSessions(prev => prev.map(session => (
      session.id === sessionId ? { ...session, title: nextTitle } : session
    )))

    const response = await fetch(`/api/memory/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: nextTitle }),
    })

    if (!response.ok && response.status !== 204) {
      void refreshSessions(activeSessionRef.current)
      return
    }

    void refreshSessions(activeSessionRef.current)
  }

  const handleMoveSession = async (sessionId: string, folder: string | null) => {
    setSessions(prev => prev.map(session => (
      session.id === sessionId ? { ...session, folder } : session
    )))

    const response = await fetch(`/api/memory/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder: folder || "" }),
    })

    if (!response.ok && response.status !== 204) {
      void refreshSessions(activeSessionRef.current)
      return
    }

    void refreshSessions(activeSessionRef.current)
    void refreshFolders()
  }

  const handleCreateFolder = async (name: string) => {
    const folderName = name.trim()
    if (!folderName) {
      return
    }

    const response = await fetch("/api/memory/folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: folderName }),
    })

    if (!response.ok) {
      return
    }

    void refreshFolders()
  }

  const handleDeleteFolder = async (name: string) => {
    const folderName = name.trim()
    if (!folderName) {
      return
    }

    const response = await fetch(`/api/memory/folders/${encodeURIComponent(folderName)}`, {
      method: "DELETE",
    })

    if (!response.ok && response.status !== 204) {
      return
    }

    setSessions(prev => prev.map(session => (
      session.folder === folderName ? { ...session, folder: null } : session
    )))
    void refreshFolders()
    void refreshSessions(activeSessionRef.current)
  }

  const handleStop = () => {
    stopRef.current = true
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
  }


  const handleModelChange = (nextModelKey: ChatModelKey) => {
    if (nextModelKey === selectedModelKey) {
      return
    }

    const fromModel = MODEL_LABELS[selectedModelKey]
    const toModel = MODEL_LABELS[nextModelKey]
    setSelectedModelKey(nextModelKey)

    setMessages(prev => [
      ...prev,
      {
        id: newId(),
        role: "assistant",
        content: `Model switched: ${fromModel.name} (${fromModel.backend}) -> ${toModel.name} (${toModel.backend})`,
        timestamp: new Date(),
      },
    ])
  }

  return (
    <AppShell
      title="Chat"
      titleColor="text-blue-400"
      isStreaming={isStreaming}
      headerActions={
        <ChatHeader
          selectedModelKey={selectedModelKey}
          onModelChange={handleModelChange}
        />
      }
    >
      {/* Home card: Nova Chat — blue-400 icon, from-blue-500/20 via-cyan-500/10, border-blue-500/30 */}
      <div className="relative flex h-full min-h-0 overflow-hidden">
        <div className="pointer-events-none absolute inset-0 z-0">
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/[0.08] via-cyan-500/[0.05] to-transparent" />
          <div className="absolute -top-24 -left-20 w-80 h-80 rounded-full bg-blue-500/10 blur-3xl" />
          <div className="absolute bottom-0 right-0 w-72 h-72 rounded-full bg-cyan-500/8 blur-3xl" />
        </div>
        <div className="relative z-[1] flex h-full w-full min-h-0 overflow-hidden">
          <ChatSidebar
            sessions={sessionsForSidebar}
            folders={folders}
            activeId={activeSessionId}
            loading={isLoadingSessions}
            isStreaming={isStreaming}
            onNewChat={handleNewChat}
            onSelect={handleSelectSession}
            onRename={handleRenameSession}
            onMove={handleMoveSession}
            onCreateFolder={handleCreateFolder}
            onDeleteFolder={handleDeleteFolder}
            onDelete={handleDeleteSession}
          />

          <main className="flex flex-col flex-1 min-w-0 h-full">
            <ChatWindow
              messages={messages}
              isStreaming={isStreaming}
              onSuggestionClick={handleSuggestionClick}
            />
            <ChatInput
              onSend={handleSend}
              isStreaming={isStreaming}
              onStop={handleStop}
              disabled={false}
            />
          </main>
        </div>
      </div>
    </AppShell>
  )
}
