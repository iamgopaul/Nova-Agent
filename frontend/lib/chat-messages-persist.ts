import type { DocItem, Message, MessageAttachment, StorySectionItem } from "@/components/chat/message-bubble"

const STORAGE_KEY_PREFIX = "nova.chatMessages.v1:"

/**
 * localStorage key for a session's full chat state (all UI: web results, weather, sections, etc.).
 * Blob object URLs (generated images, music, file previews) are not persisted; they are cleared on save.
 */
export function sessionMessagesKey(sessionId: string): string {
  return `${STORAGE_KEY_PREFIX}${encodeURIComponent(sessionId)}`
}

function isBlobRef(u: string | undefined | null): boolean {
  return typeof u === "string" && u.startsWith("blob:")
}

function stripBlobsFromAttachments(a: MessageAttachment[] | undefined): MessageAttachment[] | undefined {
  if (!a?.length) return a
  return a.map(f => (isBlobRef(f.url) ? { ...f, url: undefined } : f))
}

function stripBlobsFromDocs(d: DocItem[] | undefined): DocItem[] | undefined {
  if (!d?.length) return d
  return d.map(doc =>
    isBlobRef(doc.url) ? { ...doc, url: undefined, filename: doc.filename, generating: false } : { ...doc, generating: false },
  )
}

function stripBlobsFromStory(secs: StorySectionItem[] | undefined): StorySectionItem[] | undefined {
  if (!secs?.length) return secs
  return secs.map(s => ({
    ...s,
    imageGenerating: false,
    imageUrl: isBlobRef(s.imageUrl) ? undefined : s.imageUrl,
  }))
}

/**
 * Produces a JSON-serializable snapshot. Clears in-flight and blob-backed fields
 * so reload never shows a stuck spinner or dead blob: URLs.
 */
export function messageToStorable(m: Message): Record<string, unknown> {
  return {
    ...m,
    thinking: false,
    statusText: undefined,
    statusSteps: undefined,
    suggestionsLoading: false,
    sectionsLoading: false,
    musicGenerating: false,
    musicError: m.musicError,
    imageGenerating: false,
    chartGenerating: false,
    timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : m.timestamp,
    attachments: stripBlobsFromAttachments(m.attachments),
    imageUrl: isBlobRef(m.imageUrl) ? undefined : m.imageUrl,
    imageUrls: m.imageUrls
      ? m.imageUrls
          .map(u => (u && !isBlobRef(u) ? u : null))
          .filter((u): u is string => u !== null)
      : m.imageUrls,
    musicUrl: isBlobRef(m.musicUrl) ? undefined : m.musicUrl,
    docs: stripBlobsFromDocs(m.docs),
    storySections: stripBlobsFromStory(m.storySections),
  } as unknown as Record<string, unknown>
}

function reviveDate(raw: unknown): Date {
  if (typeof raw === "string") {
    const t = new Date(raw)
    return Number.isNaN(t.getTime()) ? new Date() : t
  }
  if (raw instanceof Date) {
    return raw
  }
  return new Date()
}

/** Restore messages saved with messageToStorable + JSON.parse. */
export function storableToMessages(raw: unknown): Message[] | null {
  if (!Array.isArray(raw)) {
    return null
  }
  if (raw.length === 0) {
    return []
  }
  const out: Message[] = []
  for (const row of raw) {
    if (!row || typeof row !== "object") {
      return null
    }
    const o = row as Record<string, unknown>
    if (o.role !== "user" && o.role !== "assistant") {
      return null
    }
    if (typeof o.id !== "string" || o.id.length === 0) {
      return null
    }
    const content = typeof o.content === "string" ? o.content : ""
    const msg: Message = {
      ...(o as unknown as Message),
      id: o.id,
      role: o.role,
      content,
      timestamp: reviveDate(o.timestamp),
      thinking: false,
      statusText: undefined,
      statusSteps: undefined,
      suggestionsLoading: false,
      sectionsLoading: false,
      musicGenerating: false,
      imageGenerating: false,
      chartGenerating: false,
    }
    if (o.attachments && Array.isArray(o.attachments)) {
      msg.attachments = o.attachments as MessageAttachment[]
    }
    out.push(msg)
  }
  return out
}

const WRAPPER_VERSION = 1

type StoredPayload = { v: number; messages: Record<string, unknown>[] }

/**
 * Read messages for a session, or return null on miss / bad data.
 */
export function loadSessionMessagesFromStorage(sessionId: string): Message[] | null {
  if (typeof window === "undefined" || !sessionId) {
    return null
  }
  const raw = window.localStorage.getItem(sessionMessagesKey(sessionId))
  if (!raw) {
    return null
  }
  try {
    const parsed = JSON.parse(raw) as unknown
    if (Array.isArray(parsed)) {
      // legacy: raw array
      return storableToMessages(parsed)
    }
    if (parsed && typeof parsed === "object" && (parsed as StoredPayload).v === WRAPPER_VERSION) {
      const p = parsed as StoredPayload
      return storableToMessages(p.messages)
    }
    return null
  } catch {
    return null
  }
}

/**
 * Write messages for a session. Silently no-ops on quota errors.
 */
export function saveSessionMessagesToStorage(sessionId: string, messages: Message[]) {
  if (typeof window === "undefined" || !sessionId) {
    return
  }
  try {
    const payload: StoredPayload = {
      v: WRAPPER_VERSION,
      messages: messages.map(m => messageToStorable(m)),
    }
    window.localStorage.setItem(sessionMessagesKey(sessionId), JSON.stringify(payload))
  } catch (e) {
    if (e instanceof Error && (e as Error & { name?: string }).name === "QuotaExceededError") {
      try {
        const slimmer: StoredPayload = {
          v: WRAPPER_VERSION,
          messages: messages.map(m => {
            const s = { ...messageToStorable(m) } as Record<string, unknown>
            delete s.webResults
            return s
          }),
        }
        window.localStorage.setItem(sessionMessagesKey(sessionId), JSON.stringify(slimmer))
      } catch {
        // give up
      }
    }
  }
}

export function clearSessionMessagesStorage(sessionId: string) {
  if (typeof window === "undefined" || !sessionId) {
    return
  }
  try {
    window.localStorage.removeItem(sessionMessagesKey(sessionId))
  } catch {
    /* no-op */
  }
}
