"use client"

import { useMemo, useRef, useState, type DragEvent } from "react"
import Link from "next/link"
import {
  ChevronRight,
  FolderPlus,
  MessageSquare,
  Plus,
  Search,
  Trash2,
  X,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react"
import { NovaIcon } from "@/components/icons/nova-icon"
import { cn } from "@/lib/utils"

export interface ChatSessionSummary {
  id: string
  title: string
  preview: string
  folder: string | null
  created_at: string
  last_message_at: string | null
  message_count: number
}

interface ChatSidebarProps {
  sessions: ChatSessionSummary[]
  folders: string[]
  activeId: string
  loading?: boolean
  /**
   * While a reply is streaming, only the active thread can be used: no new chat
   * and no switching to another session (one model turn at a time for hardware).
   */
  isStreaming?: boolean
  onNewChat: () => void
  onSelect: (id: string) => void
  onRename: (id: string, title: string) => void
  onMove: (id: string, folder: string | null) => void
  onCreateFolder: (name: string) => void
  onDeleteFolder: (name: string) => void
  onDelete: (id: string) => void
}

function getGroupLabel(session: ChatSessionSummary) {
  const reference = session.last_message_at || session.created_at
  const date = new Date(reference)
  const now = new Date()
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()

  if (sameDay) return "Today"

  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate()

  return isYesterday ? "Yesterday" : "Earlier"
}

function formatSessionTime(session: ChatSessionSummary) {
  const reference = session.last_message_at || session.created_at
  return new Date(reference).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
}

export function ChatSidebar({
  sessions,
  folders,
  activeId,
  loading = false,
  isStreaming = false,
  onNewChat,
  onSelect,
  onRename,
  onMove,
  onCreateFolder,
  onDeleteFolder,
  onDelete,
}: ChatSidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [newFolderName, setNewFolderName] = useState("")
  /** Session id being dragged (HTML5 DnD) */
  const [draggingId, setDraggingId] = useState<string | null>(null)
  /** Drop highlight: folder name, "unfiled", or null */
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const skipClickRef = useRef(false)

  const SESSION_MIME = "application/x-nova-chat-session"

  const newChatLocked = isStreaming
  const rowLocked = (id: string) => isStreaming && id !== activeId

  const handleRowDragStart = (e: DragEvent, sessionId: string) => {
    if (rowLocked(sessionId)) {
      e.preventDefault()
      return
    }
    e.dataTransfer.setData(SESSION_MIME, sessionId)
    e.dataTransfer.effectAllowed = "move"
    setDraggingId(sessionId)
    skipClickRef.current = false
  }

  const handleRowDragEnd = () => {
    setDraggingId(null)
    setDropTarget(null)
    skipClickRef.current = true
    window.setTimeout(() => {
      skipClickRef.current = false
    }, 0)
  }

  const handleRowClick = (sessionId: string, select: () => void) => {
    if (skipClickRef.current) return
    select()
  }

  const readSessionId = (e: DragEvent): string | null =>
    e.dataTransfer.getData(SESSION_MIME) || e.dataTransfer.getData("text/plain") || null

  const handleDropOnFolder = (e: DragEvent, folder: string | null) => {
    e.preventDefault()
    e.stopPropagation()
    const sid = readSessionId(e)
    if (sid) void onMove(sid, folder)
    setDraggingId(null)
    setDropTarget(null)
  }

  const handleFolderDragOver = (e: DragEvent, key: string) => {
    if (!draggingId) return
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    setDropTarget(key)
  }

  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return sessions
    return sessions.filter(session =>
      [session.title, session.preview, session.folder || ""].some(v => v.toLowerCase().includes(query))
    )
  }, [searchQuery, sessions])

  const grouped = useMemo(() => ({
    Today:     filtered.filter(s => getGroupLabel(s) === "Today"),
    Yesterday: filtered.filter(s => getGroupLabel(s) === "Yesterday"),
    Earlier:   filtered.filter(s => getGroupLabel(s) === "Earlier"),
  }), [filtered])

  const collapsedSessions = useMemo(
    () => [...filtered].sort((a, b) => {
      const at = new Date(a.last_message_at || a.created_at).getTime()
      const bt = new Date(b.last_message_at || b.created_at).getTime()
      return bt - at
    }),
    [filtered]
  )

  return (
    <aside
      className={cn(
        "flex flex-col h-full transition-all duration-300 ease-in-out shrink-0",
        "border-r border-blue-500/15 bg-[#0d0d12] text-white/80",
        collapsed ? "w-14" : "w-60"
      )}
    >
      {/* ── Top bar: Nova logo + collapse ── */}
      <div className={cn(
        "flex items-center py-4 border-b border-white/[0.06] shrink-0",
        collapsed ? "justify-center px-0" : "justify-between px-4"
      )}>
        <Link
          href="/home"
          className="flex items-center gap-2.5 hover:opacity-80 transition-opacity"
          title="Go to Home"
        >
          <NovaIcon size={24} />
          {!collapsed && (
            <span className="font-bold text-sm text-white tracking-wide">Nova</span>
          )}
        </Link>
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="p-1.5 rounded-lg text-white/30 hover:text-white/70 hover:bg-white/[0.07] transition-colors"
            title="Collapse sidebar"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* ── New Chat button ── */}
      <div className={cn("py-3 shrink-0", collapsed ? "px-2" : "px-3")}>
        <button
          type="button"
          onClick={onNewChat}
          disabled={newChatLocked}
          title={newChatLocked ? "Wait for the reply to finish" : "Start a new chat"}
          className={cn(
            "w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150",
            "bg-blue-600 hover:bg-blue-500 text-white active:scale-95 shadow-lg shadow-blue-900/30",
            collapsed && "justify-center px-0",
            newChatLocked && "opacity-40 cursor-not-allowed hover:bg-blue-600"
          )}
        >
          <Plus className="w-4 h-4 shrink-0" />
          {!collapsed && <span>New Chat</span>}
        </button>
      </div>

      {/* ── Search ── */}
      {!collapsed && (
        <div className="px-3 pb-3 shrink-0">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/25" />
            <input
              type="text"
              placeholder="Search chats…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-xs bg-white/[0.05] rounded-lg border border-white/[0.08] focus:outline-none focus:ring-1 focus:ring-blue-500/40 text-white/70 placeholder:text-white/20"
            />
          </div>
        </div>
      )}

      {/* ── Session list ── */}
      <nav className="flex-1 overflow-y-auto px-2 pb-2 space-y-0.5 scrollbar-thin">
        {loading && sessions.length === 0 && (
          <p className="px-3 py-3 text-xs text-white/25">Loading chats…</p>
        )}
        {!loading && filtered.length === 0 && !collapsed && (
          <p className="mx-1 px-3 py-4 rounded-xl border border-dashed border-white/[0.08] text-xs text-white/25 leading-relaxed">
            No chats yet. Start a new one!
          </p>
        )}

        {/* Expanded grouped view */}
        {!collapsed && Object.entries(grouped).map(([group, convos]) =>
          convos.length > 0 ? (
            <div key={group} className="mb-2">
              <p className="px-2 pt-2 pb-1.5 text-[9px] font-bold uppercase tracking-widest text-white/20">
                {group}
              </p>
              {convos.map(convo => {
                const locked = rowLocked(convo.id)
                const isActive = activeId === convo.id
                return (
                  <div
                    key={convo.id}
                    role="button"
                    tabIndex={locked ? -1 : 0}
                    draggable={!locked}
                    onDragStart={e => handleRowDragStart(e, convo.id)}
                    onDragEnd={handleRowDragEnd}
                    onClick={() => { if (!locked) handleRowClick(convo.id, () => onSelect(convo.id)) }}
                    onKeyDown={e => {
                      if ((e.key === "Enter" || e.key === " ") && !locked) {
                        e.preventDefault(); onSelect(convo.id)
                      }
                    }}
                    title={locked ? "Wait for the reply to finish to switch chats" : `${convo.title} — drag to a folder below`}
                    className={cn(
                      "w-full group flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-all duration-100 cursor-pointer",
                      isActive
                        ? "bg-blue-600/20 text-white border border-blue-500/20"
                        : "text-white/45 hover:bg-white/[0.05] hover:text-white/80 border border-transparent",
                      locked && "opacity-30 cursor-not-allowed hover:!bg-transparent hover:!text-white/45",
                      draggingId === convo.id && "opacity-50 ring-1 ring-blue-500/40"
                    )}
                  >
                    <MessageSquare className={cn("w-3.5 h-3.5 shrink-0 mt-0.5", isActive ? "text-blue-400" : "text-white/20")} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <span className="text-xs font-medium truncate flex-1">{convo.title}</span>
                        <span className="text-[9px] text-white/20 shrink-0 group-hover:hidden">{formatSessionTime(convo)}</span>
                        <button
                          type="button"
                          draggable={false}
                          onMouseDown={e => e.stopPropagation()}
                          onClick={e => { e.stopPropagation(); onDelete(convo.id) }}
                          className="hidden group-hover:flex items-center justify-center w-5 h-5 shrink-0 rounded hover:bg-red-500/15 text-white/20 hover:text-red-400 transition-colors"
                          title="Delete chat"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                      {convo.folder && (
                        <p className="text-[10px] text-white/20 mt-0.5 truncate">📁 {convo.folder}</p>
                      )}
                      <p className="text-[10px] text-white/25 mt-0.5 line-clamp-1">
                        {convo.preview}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : null
        )}

        {/* Collapsed icon-only view */}
        {collapsed && (
          <div className="flex flex-col gap-1 pt-1">
            {collapsedSessions.map(session => {
              const locked = rowLocked(session.id)
              const isActive = activeId === session.id
              return (
                <div
                  key={session.id}
                  role="button"
                  tabIndex={locked ? -1 : 0}
                  draggable={!locked}
                  onDragStart={e => handleRowDragStart(e, session.id)}
                  onDragEnd={handleRowDragEnd}
                  onClick={() => { if (!locked) handleRowClick(session.id, () => onSelect(session.id)) }}
                  onKeyDown={e => {
                    if ((e.key === "Enter" || e.key === " ") && !locked) {
                      e.preventDefault(); onSelect(session.id)
                    }
                  }}
                  className={cn(
                    "flex items-center justify-center p-2.5 rounded-lg transition-colors",
                    isActive ? "bg-blue-600/25 text-blue-400" : "text-white/25 hover:bg-white/[0.06] hover:text-white/60",
                    locked && "opacity-30 cursor-not-allowed hover:!bg-transparent",
                    draggingId === session.id && "ring-1 ring-blue-500/50"
                  )}
                  title={locked ? "Wait for the reply to switch chats" : `${session.title} — expand sidebar to drop into folders`}
                >
                  <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                </div>
              )
            })}
          </div>
        )}

        {/* Expand handle when collapsed */}
        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            className="mt-3 flex items-center justify-center w-full p-2.5 rounded-lg text-white/20 hover:text-white/60 hover:bg-white/[0.06] transition-colors"
            title="Expand sidebar"
          >
            <PanelLeftOpen className="w-4 h-4" />
          </button>
        )}
      </nav>

      {/* ── Folders (drop targets) ── */}
      {!collapsed && (
        <div className="px-3 py-3 border-t border-white/[0.06] shrink-0">
          <p className="pb-2 text-[9px] font-bold uppercase tracking-widest text-white/20">Folders</p>
          <p className="text-[10px] text-white/20 leading-snug mb-2">
            Drag a chat here to file it, or onto <span className="text-white/35">Unfiled</span> to remove it from a folder.
          </p>
          <div
            onDragOver={e => handleFolderDragOver(e, "__unfiled__")}
            onDrop={e => handleDropOnFolder(e, null)}
            onDragLeave={() => setDropTarget(t => (t === "__unfiled__" ? null : t))}
            className={cn(
              "mb-2 px-2.5 py-2 rounded-lg border border-dashed transition-colors",
              dropTarget === "__unfiled__"
                ? "border-cyan-400/50 bg-cyan-500/10"
                : "border-white/[0.1] bg-white/[0.02] hover:border-white/20"
            )}
          >
            <span className="text-[11px] text-white/50">Unfiled</span>
            <p className="text-[9px] text-white/20 mt-0.5">Not in any folder</p>
          </div>
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              placeholder="New folder…"
              value={newFolderName}
              onChange={e => setNewFolderName(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter") {
                  const name = newFolderName.trim()
                  if (name) { onCreateFolder(name); setNewFolderName("") }
                }
              }}
              className="flex-1 px-2.5 py-1.5 text-xs bg-white/[0.04] rounded-lg border border-white/[0.08] focus:outline-none focus:ring-1 focus:ring-blue-500/40 text-white/60 placeholder:text-white/20"
            />
            <button
              onClick={() => {
                const name = newFolderName.trim()
                if (name) { onCreateFolder(name); setNewFolderName("") }
              }}
              className="p-1.5 rounded-lg border border-white/[0.08] hover:bg-white/[0.07] text-white/30 hover:text-white/70 transition-colors"
              title="Create folder"
            >
              <FolderPlus className="w-3.5 h-3.5" />
            </button>
          </div>
          {folders.length > 0 && (
            <div className="mt-2 space-y-1">
              {folders.map(folder => (
                <div
                  key={folder}
                  onDragOver={e => handleFolderDragOver(e, folder)}
                  onDrop={e => handleDropOnFolder(e, folder)}
                  onDragLeave={e => {
                    if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                      setDropTarget(t => (t === folder ? null : t))
                    }
                  }}
                  className={cn(
                    "flex items-center justify-between px-2.5 py-1.5 rounded-lg border transition-colors",
                    dropTarget === folder
                      ? "bg-blue-500/15 border-blue-500/40 ring-1 ring-blue-400/30"
                      : "bg-white/[0.03] border-white/[0.06]"
                  )}
                >
                  <span className="text-[11px] text-white/40 truncate min-w-0 pr-1">📁 {folder}</span>
                  <button
                    type="button"
                    onClick={e => { e.stopPropagation(); onDeleteFolder(folder) }}
                    className="p-1 rounded hover:bg-red-500/10 text-white/20 hover:text-red-400 transition-colors shrink-0"
                    title="Delete folder"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Expand chevron at the very bottom when collapsed ── */}
      {collapsed && (
        <div className="pb-3 flex justify-center shrink-0 border-t border-white/[0.06] pt-3">
          <button
            onClick={() => setCollapsed(false)}
            className="p-1.5 rounded-lg text-white/20 hover:text-white/60 hover:bg-white/[0.06] transition-colors"
            title="Expand sidebar"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </aside>
  )
}
