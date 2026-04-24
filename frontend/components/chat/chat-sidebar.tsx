"use client"

import { useEffect, useMemo, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  Cog,
  FolderInput,
  FolderPlus,
  LogOut,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
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
  onOpenSettings?: () => void
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
  onOpenSettings,
}: ChatSidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [newFolderName, setNewFolderName] = useState("")
  const [renameTarget, setRenameTarget] = useState<ChatSessionSummary | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [moveTarget, setMoveTarget] = useState<ChatSessionSummary | null>(null)
  const [moveValue, setMoveValue] = useState<string>("(no folder)")
  const [user, setUser] = useState<{ display_name: string; avatar_color: string } | null>(null)
  const [showAccountMenu, setShowAccountMenu] = useState(false)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.display_name) setUser({ display_name: data.display_name, avatar_color: data.avatar_color || "#0ea5e9" }) })
      .catch(() => {})
  }, [])

  const sessionSwitchLocked = isStreaming
  const newChatLocked = isStreaming
  const rowLocked = (id: string) => sessionSwitchLocked && id !== activeId

  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return sessions
    }
    return sessions.filter(session =>
      [session.title, session.preview, session.folder || ""].some(value => value.toLowerCase().includes(query))
    )
  }, [searchQuery, sessions])

  const grouped = useMemo(() => ({
    Today: filtered.filter(session => getGroupLabel(session) === "Today"),
    Yesterday: filtered.filter(session => getGroupLabel(session) === "Yesterday"),
    Earlier: filtered.filter(session => getGroupLabel(session) === "Earlier"),
  }), [filtered])

  const collapsedSessions = useMemo(
    () => [...filtered].sort((left, right) => {
      const leftTime = new Date(left.last_message_at || left.created_at).getTime()
      const rightTime = new Date(right.last_message_at || right.created_at).getTime()
      return rightTime - leftTime
    }),
    [filtered]
  )

  return (
    <aside
      className={cn(
        "flex flex-col h-full transition-all duration-300 ease-in-out border-r border-border",
        "bg-sidebar/90 backdrop-blur-xl text-sidebar-foreground",
        collapsed ? "w-48" : "w-64"
      )}
    >
      <div className="flex items-center justify-between px-3 py-4 border-b border-border">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <NovaIcon size={28} />
            <span className="font-semibold text-sm text-foreground tracking-wide">Nova</span>
          </div>
        )}
        {collapsed && (
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground px-1">Chats</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "p-1.5 rounded-md hover:bg-sidebar-accent text-muted-foreground hover:text-foreground transition-colors",
            collapsed && "ml-auto"
          )}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      <div className="p-3">
        <button
          type="button"
          onClick={onNewChat}
          disabled={newChatLocked}
          title={newChatLocked ? "Wait for the reply to finish" : "Start a new chat"}
          className={cn(
            "w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
            "bg-primary text-primary-foreground hover:opacity-90 active:scale-95",
            newChatLocked && "opacity-50 cursor-not-allowed"
          )}
        >
          <Plus className="w-4 h-4 shrink-0" />
          {!collapsed && <span>New Chat</span>}
        </button>
      </div>

      {!collapsed && (
        <div className="px-3 pb-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search chats..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-xs bg-input rounded-lg border border-border focus:outline-none focus:ring-1 focus:ring-ring text-foreground placeholder:text-muted-foreground"
            />
          </div>
        </div>
      )}

      <nav className="flex-1 overflow-y-auto px-2 pb-4 space-y-1 scrollbar-thin">
        {loading && sessions.length === 0 && (
          <div className="px-2 py-3 text-xs text-muted-foreground">Loading chats...</div>
        )}

        {!loading && filtered.length === 0 && (
          <div className="px-3 py-4 rounded-xl border border-dashed border-border text-xs text-muted-foreground">
            No chats yet. Start a new one and Nova will keep the history here.
          </div>
        )}

        {!collapsed && Object.entries(grouped).map(([group, convos]) =>
          convos.length > 0 ? (
            <div key={group} className="mb-3">
              <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {group}
              </p>
              {convos.map(convo => {
                const locked = rowLocked(convo.id)
                return (
                <div
                  key={convo.id}
                  role="button"
                  tabIndex={locked ? -1 : 0}
                  onClick={() => {
                    if (locked) {
                      return
                    }
                    onSelect(convo.id)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      if (locked) {
                        return
                      }
                      event.preventDefault()
                      onSelect(convo.id)
                    }
                  }}
                  onMouseEnter={() => setHoveredId(convo.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  title={locked ? "Wait for the reply to finish to switch chats" : undefined}
                  className={cn(
                    "w-full group flex items-start justify-between gap-3 px-2 py-2 rounded-lg text-left transition-colors duration-100",
                    activeId === convo.id
                      ? "bg-sidebar-accent text-foreground"
                      : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
                    locked && "opacity-50 cursor-not-allowed pointer-events-auto",
                    locked && "hover:!bg-transparent",
                  )}
                >
                  <div className="flex items-start gap-2 min-w-0">
                    <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70 mt-0.5" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-xs truncate">{convo.title}</span>
                        <span className="text-[10px] text-muted-foreground shrink-0">{formatSessionTime(convo)}</span>
                      </div>
                      {convo.folder && (
                        <p className="text-[10px] text-muted-foreground/90 mt-0.5 truncate">Folder: {convo.folder}</p>
                      )}
                      <p className="text-[10px] text-muted-foreground mt-0.5 line-clamp-2 text-left">
                        {convo.preview}
                      </p>
                    </div>
                  </div>
                  {hoveredId === convo.id && (
                    <div className="flex items-center gap-0.5 shrink-0 ml-1">
                      <button
                        onClick={(event) => {
                          event.stopPropagation()
                          setRenameTarget(convo)
                          setRenameValue(convo.title)
                        }}
                        className="p-1 rounded hover:bg-border/60 opacity-70 hover:opacity-100 transition-opacity"
                        title="Rename chat"
                      >
                        <Pencil className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation()
                          setMoveTarget(convo)
                          setMoveValue(convo.folder || "(no folder)")
                        }}
                        className="p-1 rounded hover:bg-border/60 opacity-70 hover:opacity-100 transition-opacity"
                        title="Move to folder"
                      >
                        <FolderInput className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation()
                          onDelete(convo.id)
                        }}
                        className="p-1 rounded hover:bg-destructive/20 text-destructive opacity-70 hover:opacity-100 transition-opacity"
                        title="Delete chat"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  )}
                </div>
                )
              })}
            </div>
          ) : null
        )}

        {collapsed && (
          <div className="flex flex-col gap-1 pt-1">
            {collapsedSessions.map(session => {
              const locked = rowLocked(session.id)
              return (
              <div
                key={session.id}
                role="button"
                tabIndex={locked ? -1 : 0}
                onClick={() => {
                  if (locked) {
                    return
                  }
                  onSelect(session.id)
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    if (locked) {
                      return
                    }
                    event.preventDefault()
                    onSelect(session.id)
                  }
                }}
                onMouseEnter={() => setHoveredId(session.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={cn(
                  "w-full flex items-center gap-2 px-2 py-2 rounded-lg text-left transition-colors text-xs truncate",
                  activeId === session.id ? "bg-sidebar-accent text-foreground" : "text-muted-foreground hover:bg-sidebar-accent hover:text-foreground",
                  locked && "opacity-50 cursor-not-allowed",
                  locked && "hover:!bg-transparent"
                )}
                title={locked ? "Wait for the reply to switch chats" : session.title}
              >
                <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70" />
                <span className="truncate">{session.title}</span>
                {hoveredId === session.id && (
                  <button
                    onClick={(event) => {
                      event.stopPropagation()
                      onDelete(session.id)
                    }}
                    className="p-1 rounded hover:bg-destructive/20 text-destructive ml-auto shrink-0 opacity-70 hover:opacity-100 transition-opacity"
                    title="Delete chat"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
              )
            })}
          </div>
        )}
      </nav>

      {!collapsed && (
        <div className="px-3 pb-3 border-t border-border">
          <p className="pt-3 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Folders</p>
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              placeholder="New folder"
              value={newFolderName}
              onChange={event => setNewFolderName(event.target.value)}
              className="flex-1 px-2.5 py-1.5 text-xs bg-input rounded-lg border border-border focus:outline-none focus:ring-1 focus:ring-ring text-foreground placeholder:text-muted-foreground"
            />
            <button
              onClick={() => {
                const name = newFolderName.trim()
                if (!name) {
                  return
                }
                onCreateFolder(name)
                setNewFolderName("")
              }}
              className="p-1.5 rounded-md border border-border hover:bg-sidebar-accent transition-colors"
              title="Create folder"
            >
              <FolderPlus className="w-3.5 h-3.5" />
            </button>
          </div>
          {folders.length > 0 && (
            <div className="mt-2 space-y-1">
              {folders.map(folder => (
                <div key={folder} className="flex items-center justify-between px-2 py-1 rounded-md bg-sidebar-accent/50">
                  <span className="text-[11px] truncate">{folder}</span>
                  <button
                    onClick={() => onDeleteFolder(folder)}
                    className="p-1 rounded hover:bg-destructive/20 text-destructive"
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

      {!collapsed && (
        <div className="p-3 border-t border-border relative">
          <div className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-sidebar-accent transition-colors">
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
              style={{ backgroundColor: user?.avatar_color ?? "#0ea5e9" }}
            >
              {(user?.display_name?.[0] ?? "U").toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-foreground truncate">{user?.display_name ?? "Account"}</p>
            </div>
            <button
              onClick={() => setShowAccountMenu(prev => !prev)}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors"
              title="Settings"
            >
              <Cog className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={async () => {
                await fetch("/api/auth/logout", { method: "POST" })
                window.location.href = "/login"
              }}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-destructive/20 transition-colors"
              title="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
          {showAccountMenu && (
            <>
              <div className="fixed inset-0 z-30" onClick={() => setShowAccountMenu(false)} />
              <div className="absolute bottom-16 left-3 right-3 z-40 rounded-xl border border-border bg-popover shadow-2xl p-1.5">
                <button
                  onClick={() => {
                    setShowAccountMenu(false)
                    onOpenSettings?.()
                  }}
                  className="w-full text-left px-3 py-2 rounded-lg text-xs text-foreground hover:bg-muted transition-colors"
                >
                  Profile & Identity
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {renameTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={() => setRenameTarget(null)}>
          <div className="w-full max-w-sm rounded-xl border border-border bg-popover p-4 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <p className="text-sm font-semibold text-foreground">Rename chat</p>
            <input
              autoFocus
              type="text"
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  const value = renameValue.trim()
                  if (!value) {
                    return
                  }
                  onRename(renameTarget.id, value)
                  setRenameTarget(null)
                }
                if (event.key === "Escape") {
                  setRenameTarget(null)
                }
              }}
              className="mt-3 w-full px-3 py-2 text-sm bg-input rounded-lg border border-border focus:outline-none focus:ring-1 focus:ring-ring text-foreground"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setRenameTarget(null)}
                className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const value = renameValue.trim()
                  if (!value) {
                    return
                  }
                  onRename(renameTarget.id, value)
                  setRenameTarget(null)
                }}
                className="px-3 py-1.5 text-xs rounded-md bg-primary text-primary-foreground hover:opacity-90"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {moveTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={() => setMoveTarget(null)}>
          <div className="w-full max-w-sm rounded-xl border border-border bg-popover p-4 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <p className="text-sm font-semibold text-foreground">Move chat to folder</p>
            <select
              value={moveValue}
              onChange={(event) => setMoveValue(event.target.value)}
              className="mt-3 w-full px-3 py-2 text-sm bg-input rounded-lg border border-border focus:outline-none focus:ring-1 focus:ring-ring text-foreground"
            >
              <option value="(no folder)">(no folder)</option>
              {folders.map(folder => (
                <option key={folder} value={folder}>{folder}</option>
              ))}
            </select>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setMoveTarget(null)}
                className="px-3 py-1.5 text-xs rounded-md border border-border hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  onMove(moveTarget.id, moveValue === "(no folder)" ? null : moveValue)
                  setMoveTarget(null)
                }}
                className="px-3 py-1.5 text-xs rounded-md bg-primary text-primary-foreground hover:opacity-90"
              >
                Move
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
