import { Bot } from "lucide-react"

export function ChatWelcome() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-4 py-12 gap-5">
      {/* Logo + greeting */}
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="w-16 h-16 rounded-2xl bg-primary/15 border border-primary/30 flex items-center justify-center">
          <Bot className="w-8 h-8 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-foreground text-balance">
            Start a conversation with Nova
          </h1>
          <p className="mt-1 text-sm text-muted-foreground text-balance">
            Your chat history will appear here once you start sending messages.
          </p>
        </div>
      </div>
    </div>
  )
}
