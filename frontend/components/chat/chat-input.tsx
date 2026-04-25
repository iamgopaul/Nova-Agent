"use client"

import { useState, useRef, useEffect, KeyboardEvent } from "react"
import { useRouter } from "next/navigation"
import { Send, Paperclip, Mic, Square } from "lucide-react"
import { cn } from "@/lib/utils"

interface ChatInputProps {
  onSend: (message: string, attachments: File[]) => void | Promise<void>
  isStreaming: boolean
  onStop: () => void
  disabled?: boolean
}

export function ChatInput({ onSend, isStreaming, onStop, disabled }: ChatInputProps) {
  const router = useRouter()
  const [value, setValue] = useState("")
  const [attachments, setAttachments] = useState<File[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const adjustHeight = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 200) + "px"
  }

  useEffect(() => {
    adjustHeight()
  }, [value])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = () => {
    if ((!value.trim() && attachments.length === 0) || disabled) return
    void onSend(value.trim(), attachments)
    setValue("")
    setAttachments([])
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handlePickFiles = () => {
    fileInputRef.current?.click()
  }

  const handleFilesSelected = (files: FileList | null) => {
    if (!files?.length) {
      return
    }
    const nextFiles = Array.from(files)
    setAttachments(prev => [...prev, ...nextFiles])
  }

  const removeAttachment = (index: number) => {
    setAttachments(prev => prev.filter((_, currentIndex) => currentIndex !== index))
  }

  return (
    <div className="w-full px-4 pb-4 pt-2 bg-gradient-to-b from-[#0d0d12] to-blue-950/20 border-t border-blue-500/20">
      <div className="max-w-3xl mx-auto">
        <div
          className={cn(
            "relative flex items-end gap-2 rounded-2xl border border-white/[0.08] bg-white/[0.04] p-3 transition-all duration-200",
            "focus-within:border-blue-500/40 focus-within:ring-2 focus-within:ring-blue-500/15",
          )}
        >
          {/* Attachment button */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={event => handleFilesSelected(event.target.files)}
          />
          <button
            type="button"
            onClick={handlePickFiles}
            disabled={disabled || isStreaming}
            className="shrink-0 mb-0.5 p-1.5 rounded-lg text-white/25 hover:text-white/60 hover:bg-white/[0.07] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Attach files or images"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={e => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Nova…"
            rows={1}
            disabled={disabled}
            className={cn(
              "flex-1 resize-none bg-transparent text-sm text-white/80 placeholder:text-white/20",
              "focus:outline-none leading-relaxed py-0.5 max-h-[200px] scrollbar-thin"
            )}
          />

          {/* Mic & Send buttons */}
          <div className="flex items-center gap-1 shrink-0 mb-0.5">
            {!isStreaming && !value && (
              <button
                type="button"
                onClick={() => router.push("/voice")}
                className="p-1.5 rounded-lg text-white/25 hover:text-white/60 hover:bg-white/[0.07] transition-colors"
                title="Nova Voice"
              >
                <Mic className="w-4 h-4" />
              </button>
            )}

            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                className="flex items-center justify-center w-8 h-8 rounded-xl bg-red-500/80 hover:bg-red-500 transition-colors active:scale-95"
                title="Stop generating"
              >
                <Square className="w-3.5 h-3.5 fill-white text-white" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSend}
                disabled={(!value.trim() && attachments.length === 0) || disabled}
                className={cn(
                  "flex items-center justify-center w-8 h-8 rounded-xl transition-all duration-150 active:scale-95",
                  (value.trim() || attachments.length > 0) && !disabled
                    ? "bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-900/40"
                    : "bg-white/[0.05] text-white/20 cursor-not-allowed"
                )}
                title="Send message (Enter)"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {attachments.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {attachments.map((file, index) => (
              <div
                key={`${file.name}-${file.size}-${index}`}
                className="flex items-center gap-2 max-w-full rounded-full border border-white/[0.08] bg-white/[0.05] px-3 py-1.5 text-xs text-white/70"
              >
                <span className="max-w-[240px] truncate" title={file.name}>
                  {file.name}
                </span>
                <span className="text-muted-foreground shrink-0">
                  {file.type.startsWith("image/") ? "image" : file.type || "file"}
                </span>
                <button
                  type="button"
                  onClick={() => removeAttachment(index)}
                  className="ml-1 rounded-full px-1.5 py-0.5 text-muted-foreground hover:text-foreground hover:bg-muted"
                  aria-label={`Remove ${file.name}`}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <p className="text-center text-[10px] text-white/15 mt-2">
          Nova can make mistakes. Consider verifying important information.
        </p>
      </div>
    </div>
  )
}
