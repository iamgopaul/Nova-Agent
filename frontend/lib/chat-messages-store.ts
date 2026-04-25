import type { Message } from "@/components/chat/message-bubble"

// Module-level store — survives React component mount/unmount (i.e., page navigation).
// This allows an active SSE stream to keep writing messages even while the user is
// on a different page. When they return to /chat the component remounts and reads
// the latest messages from here instead of stale localStorage data.

type Updater = Message[] | ((prev: Message[]) => Message[])

const _messages = new Map<string, Message[]>()
const _EMPTY: Message[] = []
let _streamingSession = ""
let _isStreaming = false
const _listeners = new Set<() => void>()

function _notify() {
  for (const fn of _listeners) fn()
}

export const chatMessagesStore = {
  subscribe(fn: () => void): () => void {
    _listeners.add(fn)
    return () => _listeners.delete(fn)
  },

  getMessages(sessionId: string): Message[] {
    return _messages.get(sessionId) ?? _EMPTY
  },

  setMessages(sessionId: string, updater: Updater): void {
    const prev = _messages.get(sessionId) ?? []
    const next = typeof updater === "function" ? updater(prev) : updater
    _messages.set(sessionId, next)
    _notify()
  },

  // Like setMessages but won't overwrite a session that's actively streaming.
  // Used by loadHistory so navigating back doesn't clobber in-progress content.
  loadMessages(sessionId: string, messages: Message[]): void {
    if (_isStreaming && _streamingSession === sessionId) return
    _messages.set(sessionId, messages)
    _notify()
  },

  beginStream(sessionId: string): void {
    _streamingSession = sessionId
    _isStreaming = true
    _notify()
  },

  endStream(): void {
    _isStreaming = false
    _streamingSession = ""
    _notify()
  },

  isStreamingSession(sessionId: string): boolean {
    return _isStreaming && _streamingSession === sessionId
  },

  isAnyStreaming(): boolean {
    return _isStreaming
  },

  getStreamingSession(): string {
    return _streamingSession
  },
}
