"use client"

import { useEffect, useRef, useState, type DragEvent, useMemo } from "react"
import Link from "next/link"
import {
  ChevronDown,
  ChevronRight,
  Folder,
  FolderOpen,
  FolderPlus,
  Menu,
  MessageSquare,
  MoreHorizontal,
  MoveRight,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react"
import { GaaiaIcon } from "@/components/icons/gaaia-icon"
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

// ── Folder picker dropdown ────────────────────────────────────────────────────

interface FolderPickerProps {
  folders: string[]
  currentFolder: string | null
  onPick: (folder: string | null) => void
  onCreateAndPick: (name: string) => void
  onClose: () => void
  anchorRef: React.RefObject<HTMLElement>
}

function FolderPicker({ folders, currentFolder, onPick, onCreateAndPick, onClose, anchorRef }: FolderPickerProps) {
  const [search, setSearch] = useState("")
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState("")
  const ref = useRef<HTMLDivElement>(null)

  const filtered = folders.filter(f => f.toLowerCase().includes(search.toLowerCase()))

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        ref.current && !ref.current.contains(e.target as Node) &&
        anchorRef.current && !anchorRef.current.contains(e.target as Node)
      ) {
        onClose()
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [onClose, anchorRef])

  return (
    <div
      ref={ref}
      className="absolute left-full top-0 ml-1 z-50 w-48 rounded-xl border border-white/[0.1] shadow-xl overflow-hidden"
      style={{ backgroundColor: "var(--surface-3)" }}
    >
      {/* Search */}
      <div className="px-2 py-2 border-b border-white/[0.07]">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-white/25" />
          <input
            autoFocus
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Find folder…"
            className="w-full pl-6 pr-2 py-1.5 text-[11px] bg-white/[0.06] rounded-lg border border-white/[0.08] focus:outline-none focus:ring-1 focus:ring-blue-500/40 text-white/70 placeholder:text-white/25"
          />
        </div>
      </div>

      <div className="max-h-48 overflow-y-auto">
        {/* Remove from folder */}
        {currentFolder && (
          <>
            <button
              onClick={() => { onPick(null); onClose() }}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-amber-400/70 hover:bg-amber-500/[0.07] hover:text-amber-400 transition-colors"
            >
              <X className="w-3 h-3" />
              Remove from &ldquo;{currentFolder}&rdquo;
            </button>
            <div className="border-t border-white/[0.07]" />
          </>
        )}

        {filtered.length === 0 && !creating && (
          <p className="px-3 py-3 text-[11px] text-white/25">No folders yet</p>
        )}

        {filtered.map(folder => (
          <button
            key={folder}
            onClick={() => { onPick(folder); onClose() }}
            className={cn(
              "w-full flex items-center gap-2 px-3 py-2 text-[11px] transition-colors",
              currentFolder === folder
                ? "bg-blue-600/15 text-blue-300"
                : "text-white/55 hover:bg-white/[0.06] hover:text-white/80"
            )}
          >
            <Folder className="w-3 h-3 shrink-0" />
            <span className="truncate">{folder}</span>
            {currentFolder === folder && <span className="ml-auto text-blue-400 text-[10px]">✓</span>}
          </button>
        ))}
      </div>

      {/* New folder */}
      <div className="border-t border-white/[0.07] px-2 py-2">
        {creating ? (
          <div className="flex items-center gap-1">
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter") {
                  const n = newName.trim()
                  if (n) { onCreateAndPick(n); onClose() }
                }
                if (e.key === "Escape") setCreating(false)
              }}
              placeholder="Folder name…"
              className="flex-1 px-2 py-1 text-[11px] bg-white/[0.06] rounded border border-white/[0.1] focus:outline-none focus:ring-1 focus:ring-blue-500/40 text-white/70 placeholder:text-white/25"
            />
            <button
              onClick={() => { const n = newName.trim(); if (n) { onCreateAndPick(n); onClose() } }}
              className="p-1 rounded bg-blue-600 hover:bg-blue-500 text-white"
            >
              <Plus className="w-3 h-3" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className="w-full flex items-center gap-2 px-1 py-1 text-[11px] text-white/40 hover:text-blue-400 transition-colors"
          >
            <FolderPlus className="w-3 h-3" />
            New folder
          </button>
        )}
      </div>
    </div>
  )
}

// ── Chat row action menu ───────────────────────────────────────────────────────

interface ChatRowMenuProps {
  session: ChatSessionSummary
  folders: string[]
  onRename: () => void
  onMove: (folder: string | null) => void
  onCreateFolderAndMove: (name: string) => void
  onDelete: () => void
  onClose: () => void
}

function ChatRowMenu({ session, folders, onRename, onMove, onCreateFolderAndMove, onDelete, onClose }: ChatRowMenuProps) {
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const folderBtnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        if (!showFolderPicker) onClose()
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [onClose, showFolderPicker])

  return (
    <div
      ref={menuRef}
      className="absolute right-0 top-6 z-40 w-44 rounded-xl border border-white/[0.1] shadow-xl overflow-visible py-1"
      style={{ backgroundColor: "var(--surface-3)" }}
    >
      <button
        onClick={() => { onRename(); onClose() }}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] text-white/55 hover:bg-white/[0.06] hover:text-white/80 transition-colors"
      >
        <Pencil className="w-3 h-3" />
        Rename
      </button>

      <div className="relative">
        <button
          ref={folderBtnRef}
          onClick={() => setShowFolderPicker(v => !v)}
          className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] text-white/55 hover:bg-white/[0.06] hover:text-white/80 transition-colors"
        >
          <MoveRight className="w-3 h-3" />
          Move to folder
          <ChevronRight className="w-3 h-3 ml-auto" />
        </button>
        {showFolderPicker && (
          <FolderPicker
            folders={folders}
            currentFolder={session.folder}
            onPick={folder => { onMove(folder); onClose() }}
            onCreateAndPick={name => { onCreateFolderAndMove(name); onClose() }}
            onClose={() => setShowFolderPicker(false)}
            anchorRef={folderBtnRef as React.RefObject<HTMLElement>}
          />
        )}
      </div>

      <div className="my-1 border-t border-white/[0.06]" />
      <button
        onClick={() => { onDelete(); onClose() }}
        className="w-full flex items-center gap-2.5 px-3 py-2 text-[11px] text-red-400/70 hover:bg-red-500/[0.07] hover:text-red-400 transition-colors"
      >
        <Trash2 className="w-3 h-3" />
        Delete chat
      </button>
    </div>
  )
}

// ── Chat row ──────────────────────────────────────────────────────────────────

interface ChatRowProps {
  session: ChatSessionSummary
  folders: string[]
  isActive: boolean
  locked: boolean
  isDragging: boolean
  onSelect: () => void
  onRename: (id: string, title: string) => void
  onMove: (id: string, folder: string | null) => void
  onCreateFolderAndMove: (id: string, name: string) => void
  onDelete: (id: string) => void
  onDragStart: (e: DragEvent) => void
  onDragEnd: () => void
}

function ChatRow({
  session, folders, isActive, locked, isDragging,
  onSelect, onRename, onMove, onCreateFolderAndMove, onDelete,
  onDragStart, onDragEnd,
}: ChatRowProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [renameVal, setRenameVal] = useState(session.title)
  const skipClickRef = useRef(false)

  const handleDragStart = (e: DragEvent) => {
    if (locked) { e.preventDefault(); return }
    skipClickRef.current = false
    onDragStart(e)
  }

  const handleDragEnd = () => {
    skipClickRef.current = true
    onDragEnd()
    window.setTimeout(() => { skipClickRef.current = false }, 0)
  }

  if (renaming) {
    return (
      <div className="px-2 py-1.5">
        <input
          autoFocus
          value={renameVal}
          onChange={e => setRenameVal(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter") { onRename(session.id, renameVal.trim() || session.title); setRenaming(false) }
            if (e.key === "Escape") setRenaming(false)
          }}
          onBlur={() => { onRename(session.id, renameVal.trim() || session.title); setRenaming(false) }}
          className="w-full px-2 py-1 text-xs bg-white/[0.08] rounded border border-blue-500/40 focus:outline-none text-white/80"
        />
      </div>
    )
  }

  return (
    <div
      role="button"
      tabIndex={locked ? -1 : 0}
      draggable={!locked}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onClick={() => { if (skipClickRef.current || locked || menuOpen) return; onSelect() }}
      onKeyDown={e => { if ((e.key === "Enter" || e.key === " ") && !locked) { e.preventDefault(); onSelect() } }}
      title={locked ? "Wait for reply to finish" : session.title}
      className={cn(
        "relative group w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-all duration-100 cursor-pointer",
        isActive
          ? "bg-blue-600/20 text-white border border-blue-500/20"
          : "text-white/45 hover:bg-white/[0.05] hover:text-white/80 border border-transparent",
        locked && "opacity-30 cursor-not-allowed hover:!bg-transparent",
        isDragging && "opacity-50 ring-1 ring-blue-500/40"
      )}
    >
      <MessageSquare className={cn("w-3.5 h-3.5 shrink-0 mt-0.5", isActive ? "text-blue-400" : "text-white/20")} />
      <div className="min-w-0 flex-1 pr-5">
        <div className="flex items-center gap-1">
          <span className="text-xs font-medium truncate flex-1">{session.title}</span>
          <span className="text-[9px] text-white/20 shrink-0 group-hover:hidden">{formatSessionTime(session)}</span>
        </div>
        <p className="text-[10px] text-white/25 mt-0.5 line-clamp-1">{session.preview}</p>
      </div>

      {/* Action menu trigger */}
      <button
        type="button"
        onMouseDown={e => { e.stopPropagation(); setMenuOpen(v => !v) }}
        onClick={e => e.stopPropagation()}
        className={cn(
          "absolute right-1.5 top-1.5 p-1 rounded-md transition-colors",
          menuOpen
            ? "bg-white/[0.1] text-white/70"
            : "opacity-0 group-hover:opacity-100 text-white/30 hover:bg-white/[0.08] hover:text-white/70"
        )}
        title="Options"
      >
        <MoreHorizontal className="w-3.5 h-3.5" />
      </button>

      {menuOpen && (
        <ChatRowMenu
          session={session}
          folders={folders}
          onRename={() => { setRenaming(true); setRenameVal(session.title) }}
          onMove={folder => onMove(session.id, folder)}
          onCreateFolderAndMove={name => onCreateFolderAndMove(session.id, name)}
          onDelete={() => onDelete(session.id)}
          onClose={() => setMenuOpen(false)}
        />
      )}
    </div>
  )
}

// ── Main sidebar ──────────────────────────────────────────────────────────────

export function ChatSidebar({
  sessions, folders, activeId, loading = false, isStreaming = false,
  onNewChat, onSelect, onRename, onMove, onCreateFolder, onDeleteFolder, onDelete,
}: ChatSidebarProps) {
  const [collapsed, setCollapsed] = useState(false)
  // Mobile drawer state: hidden by default, opens when the hamburger is tapped.
  // Only relevant below the `md` breakpoint — desktop ignores this and uses
  // the `collapsed` flag for in-flow expand/collapse.
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set(folders))
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState("")
  const newFolderInputRef = useRef<HTMLInputElement>(null)

  const SESSION_MIME = "application/x-gaaia-chat-session"
  const rowLocked = (id: string) => isStreaming && id !== activeId

  // Keep expanded set in sync when new folders are created externally
  useEffect(() => {
    setExpandedFolders(prev => {
      const next = new Set(prev)
      folders.forEach(f => { if (!prev.has(f)) next.add(f) })
      return next
    })
  }, [folders])

  const toggleFolder = (name: string) =>
    setExpandedFolders(prev => {
      const s = new Set(prev)
      s.has(name) ? s.delete(name) : s.add(name)
      return s
    })

  const handleRowDragStart = (e: DragEvent, sessionId: string) => {
    e.dataTransfer.setData(SESSION_MIME, sessionId)
    e.dataTransfer.effectAllowed = "move"
    setDraggingId(sessionId)
  }

  const handleRowDragEnd = () => {
    setDraggingId(null)
    setDropTarget(null)
  }

  const handleDropOnFolder = (e: DragEvent, folder: string | null) => {
    e.preventDefault()
    e.stopPropagation()
    const sid = e.dataTransfer.getData(SESSION_MIME) || e.dataTransfer.getData("text/plain") || null
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

  const handleCreateFolderAndMove = (sessionId: string, name: string) => {
    onCreateFolder(name)
    // Small delay to ensure folder is created before moving
    window.setTimeout(() => onMove(sessionId, name), 50)
  }

  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) return sessions
    return sessions.filter(s =>
      [s.title, s.preview, s.folder || ""].some(v => v.toLowerCase().includes(query))
    )
  }, [searchQuery, sessions])

  // Split: sessions in folders vs unfiled
  const sessionsByFolder = useMemo(() => {
    const map: Record<string, ChatSessionSummary[]> = {}
    const unfiled: ChatSessionSummary[] = []
    for (const s of filtered) {
      if (s.folder) {
        ;(map[s.folder] ??= []).push(s)
      } else {
        unfiled.push(s)
      }
    }
    return { map, unfiled }
  }, [filtered])

  const unfiledGrouped = useMemo(() => ({
    Today:     sessionsByFolder.unfiled.filter(s => getGroupLabel(s) === "Today"),
    Yesterday: sessionsByFolder.unfiled.filter(s => getGroupLabel(s) === "Yesterday"),
    Earlier:   sessionsByFolder.unfiled.filter(s => getGroupLabel(s) === "Earlier"),
  }), [sessionsByFolder.unfiled])

  const collapsedSessions = useMemo(
    () => [...filtered].sort((a, b) => {
      const at = new Date(a.last_message_at || a.created_at).getTime()
      const bt = new Date(b.last_message_at || b.created_at).getTime()
      return bt - at
    }),
    [filtered]
  )

  const submitNewFolder = () => {
    const name = newFolderName.trim()
    if (name) { onCreateFolder(name); setNewFolderName(""); setCreatingFolder(false) }
  }

  return (
    <>
      {/* Mobile hamburger — visible only on <md and only when drawer is shut.
          Floats top-left over the chat content. Tapping it opens the sidebar.
          On desktop the hamburger is hidden; the in-flow sidebar is always
          present (collapsed or expanded). */}
      {!mobileOpen && (
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Open chat list"
          className="md:hidden fixed top-2 left-2 z-30 p-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.1] text-white/70 hover:text-white border border-white/[0.08] backdrop-blur-sm"
        >
          <Menu className="w-4 h-4" />
        </button>
      )}

      {/* Mobile backdrop — tap-to-close when the drawer is open. Desktop
          ignores it (md:hidden). */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-black/50 backdrop-blur-sm"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        style={{ backgroundColor: "var(--surface-1)" }}
        className={cn(
          // Desktop: in-flow sidebar, sized by `collapsed` flag.
          "md:relative md:flex md:translate-x-0",
          // Mobile: fixed slide-over drawer; transform controls visibility.
          "fixed inset-y-0 left-0 z-40 transition-transform duration-300 ease-in-out",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
          // Common: vertical flex column.
          "flex flex-col h-full shrink-0",
          "border-r border-blue-500/10 text-white/80",
          // Width: mobile always full-ish; desktop respects `collapsed`.
          "w-72",
          collapsed ? "md:w-14" : "md:w-64"
        )}
      >
      {/* ── Top bar ── */}
      <div className={cn(
        "flex items-center py-4 border-b border-white/[0.06] shrink-0",
        collapsed ? "md:justify-center md:px-0 justify-between px-4" : "justify-between px-4"
      )}>
        <Link href="/home" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity" title="Go to Home">
          <GaaiaIcon size={24} />
          {(!collapsed || mobileOpen) && (
            <span className="font-bold text-sm text-white tracking-wide md:inline">GAAIA</span>
          )}
        </Link>
        <div className="flex items-center gap-1">
          {/* Mobile close button — visible only when drawer is open on <md. */}
          <button
            onClick={() => setMobileOpen(false)}
            className="md:hidden p-1.5 rounded-lg text-white/40 hover:text-white/80 hover:bg-white/[0.07] transition-colors"
            aria-label="Close chat list"
          >
            <X className="w-4 h-4" />
          </button>
          {/* Desktop collapse button — only on md+ when expanded. */}
          {!collapsed && (
            <button
              onClick={() => setCollapsed(true)}
              className="hidden md:inline-flex p-1.5 rounded-lg text-white/30 hover:text-white/70 hover:bg-white/[0.07] transition-colors"
              title="Collapse sidebar"
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* ── New Chat ── */}
      <div className={cn("py-3 shrink-0", collapsed ? "px-2" : "px-3")}>
        <button
          type="button"
          onClick={() => { onNewChat(); setMobileOpen(false) }}
          disabled={isStreaming}
          title={isStreaming ? "Wait for the reply to finish" : "Start a new chat"}
          className={cn(
            "w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150",
            "bg-blue-600 hover:bg-blue-500 text-white active:scale-95 shadow-lg shadow-blue-900/30",
            collapsed && "justify-center px-0",
            isStreaming && "opacity-40 cursor-not-allowed hover:bg-blue-600"
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

      {/* ── Main nav ── */}
      <nav className="flex-1 overflow-y-auto px-2 pb-2 scrollbar-thin">
        {loading && sessions.length === 0 && (
          <p className="px-3 py-3 text-xs text-white/25">Loading chats…</p>
        )}

        {!collapsed && (
          <>
            {/* Folders with their chats inline */}
            {folders.length > 0 && (
              <div className="mb-1">
                <p className="px-2 pt-2 pb-1 text-[9px] font-bold uppercase tracking-widest text-white/20">Folders</p>
                {folders.map(folder => {
                  const folderSessions = sessionsByFolder.map[folder] ?? []
                  const isExpanded = expandedFolders.has(folder)
                  const isDragTarget = dropTarget === folder
                  return (
                    <div key={folder}>
                      {/* Folder header — drop target */}
                      <div
                        onDragOver={e => handleFolderDragOver(e, folder)}
                        onDrop={e => handleDropOnFolder(e, folder)}
                        onDragLeave={e => {
                          if (!e.currentTarget.contains(e.relatedTarget as Node))
                            setDropTarget(t => (t === folder ? null : t))
                        }}
                        className={cn(
                          "group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all duration-150 select-none",
                          isDragTarget
                            ? "bg-blue-500/15 ring-1 ring-blue-500/40"
                            : "hover:bg-white/[0.04]"
                        )}
                        onClick={() => toggleFolder(folder)}
                      >
                        {isExpanded
                          ? <FolderOpen className="w-3.5 h-3.5 shrink-0 text-blue-400/70" />
                          : <Folder className="w-3.5 h-3.5 shrink-0 text-white/30" />
                        }
                        <span className={cn("text-xs font-medium flex-1 truncate", isExpanded ? "text-white/75" : "text-white/45")}>
                          {folder}
                        </span>
                        <span className="text-[9px] text-white/20 shrink-0 mr-1">
                          {folderSessions.length}
                        </span>
                        {isExpanded
                          ? <ChevronDown className="w-3 h-3 text-white/25 shrink-0" />
                          : <ChevronRight className="w-3 h-3 text-white/20 shrink-0" />
                        }
                        <button
                          type="button"
                          onMouseDown={e => e.stopPropagation()}
                          onClick={e => { e.stopPropagation(); onDeleteFolder(folder) }}
                          className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 text-white/20 hover:text-red-400 transition-all shrink-0"
                          title="Delete folder"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>

                      {/* Folder contents */}
                      {isExpanded && (
                        <div className="ml-3 pl-2 border-l border-white/[0.07] mb-1 space-y-0.5">
                          {folderSessions.length === 0 ? (
                            <p className="px-2 py-2 text-[10px] text-white/20 italic">Empty — drag chats here</p>
                          ) : (
                            folderSessions.map(s => (
                              <ChatRow
                                key={s.id}
                                session={s}
                                folders={folders}
                                isActive={activeId === s.id}
                                locked={rowLocked(s.id)}
                                isDragging={draggingId === s.id}
                                onSelect={() => { onSelect(s.id); setMobileOpen(false) }}
                                onRename={onRename}
                                onMove={onMove}
                                onCreateFolderAndMove={handleCreateFolderAndMove}
                                onDelete={onDelete}
                                onDragStart={e => handleRowDragStart(e, s.id)}
                                onDragEnd={handleRowDragEnd}
                              />
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* New folder button */}
            <div className="mb-2 px-1">
              {creatingFolder ? (
                <div className="flex items-center gap-1.5 px-1 py-1">
                  <input
                    ref={newFolderInputRef}
                    autoFocus
                    value={newFolderName}
                    onChange={e => setNewFolderName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === "Enter") submitNewFolder()
                      if (e.key === "Escape") { setCreatingFolder(false); setNewFolderName("") }
                    }}
                    onBlur={submitNewFolder}
                    placeholder="Folder name…"
                    className="flex-1 px-2 py-1.5 text-xs bg-white/[0.06] rounded-lg border border-blue-500/30 focus:outline-none focus:ring-1 focus:ring-blue-500/40 text-white/70 placeholder:text-white/25"
                  />
                  <button onClick={submitNewFolder} className="p-1 rounded bg-blue-600 hover:bg-blue-500 text-white transition-colors">
                    <Plus className="w-3 h-3" />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setCreatingFolder(true)}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[11px] text-white/30 hover:text-blue-400/80 hover:bg-white/[0.04] transition-colors"
                >
                  <FolderPlus className="w-3.5 h-3.5" />
                  New folder
                </button>
              )}
            </div>

            {/* Unfiled chats */}
            {sessionsByFolder.unfiled.length > 0 && (
              <div>
                {Object.entries(unfiledGrouped).map(([group, convos]) =>
                  convos.length > 0 ? (
                    <div key={group} className="mb-1">
                      <p className="px-2 pt-2 pb-1 text-[9px] font-bold uppercase tracking-widest text-white/20">{group}</p>
                      <div className="space-y-0.5">
                        {convos.map(convo => (
                          <ChatRow
                            key={convo.id}
                            session={convo}
                            folders={folders}
                            isActive={activeId === convo.id}
                            locked={rowLocked(convo.id)}
                            isDragging={draggingId === convo.id}
                            onSelect={() => { onSelect(convo.id); setMobileOpen(false) }}
                            onRename={onRename}
                            onMove={onMove}
                            onCreateFolderAndMove={handleCreateFolderAndMove}
                            onDelete={onDelete}
                            onDragStart={e => handleRowDragStart(e, convo.id)}
                            onDragEnd={handleRowDragEnd}
                          />
                        ))}
                      </div>
                    </div>
                  ) : null
                )}
              </div>
            )}

            {!loading && filtered.length === 0 && (
              <p className="mx-1 px-3 py-4 rounded-xl border border-dashed border-white/[0.08] text-xs text-white/25 leading-relaxed">
                No chats yet. Start a new one!
              </p>
            )}
          </>
        )}

        {/* Collapsed icon-only view */}
        {collapsed && (
          <div className="flex flex-col gap-1 pt-1">
            {collapsedSessions.map(session => {
              const locked = rowLocked(session.id)
              const isActive = activeId === session.id
              return (
                <button
                  key={session.id}
                  onClick={() => { if (!locked) { onSelect(session.id); setMobileOpen(false) } }}
                  className={cn(
                    "flex items-center justify-center p-2.5 rounded-lg transition-colors",
                    isActive ? "bg-blue-600/25 text-blue-400" : "text-white/25 hover:bg-white/[0.06] hover:text-white/60",
                    locked && "opacity-30 cursor-not-allowed"
                  )}
                  title={session.title}
                >
                  <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                </button>
              )
            })}
            <button
              onClick={() => setCollapsed(false)}
              className="mt-3 flex items-center justify-center w-full p-2.5 rounded-lg text-white/20 hover:text-white/60 hover:bg-white/[0.06] transition-colors"
              title="Expand sidebar"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          </div>
        )}
      </nav>

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
    </>
  )
}
