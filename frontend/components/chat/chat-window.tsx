"use client"

import { useEffect, useRef } from "react"
import { MessageBubble, type Message } from "./message-bubble"
import { ChatWelcome } from "./chat-welcome"
import { ChevronDown } from "lucide-react"
import { useState } from "react"
import { cn } from "@/lib/utils"

interface ChatWindowProps {
  messages: Message[]
  isStreaming: boolean
  onSuggestionClick?: (suggestion: string) => void
}

export function ChatWindow({ messages, isStreaming, onSuggestionClick }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)

  const scrollToBottom = (smooth = true) => {
    bottomRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowScrollBtn(distanceFromBottom > 200)
  }

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto scrollbar-thin"
      >
        {messages.length === 0 ? (
          <ChatWelcome />
        ) : (
          <div className="py-4 space-y-1">
            {messages.map((msg, i) => (
              <MessageBubble
                key={`${i}-${msg.id}`}
                message={msg}
                onSuggestionClick={onSuggestionClick}
              />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Scroll to bottom button */}
      <button
        onClick={() => scrollToBottom()}
        className={cn(
          "absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-3 py-1.5 rounded-full",
          "bg-[#1a1a26] border border-white/10 text-xs text-white/40 hover:text-white/70 hover:border-blue-500/40 shadow-xl transition-all duration-200",
          showScrollBtn ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4 pointer-events-none"
        )}
      >
        <ChevronDown className="w-3.5 h-3.5" />
        Scroll to bottom
      </button>
    </div>
  )
}
