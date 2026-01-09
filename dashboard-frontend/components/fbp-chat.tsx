"use client"

import { useState, useRef, useEffect, KeyboardEvent } from "react"
import { Send, Bot, User, Wrench, Loader2, Trash2, Sparkles } from "lucide-react"
import { cn } from "@/lib/utils"

interface Message {
  role: "user" | "assistant"
  content: string
  toolCalls?: ToolCall[]
  timestamp: Date
}

interface ToolCall {
  tool: string
  params: Record<string, unknown>
  result: Record<string, unknown> | string
}

const TOOL_ICONS: Record<string, string> = {
  get_balance: "💰",
  get_positions: "📊",
  get_agents: "🤖",
  search_markets: "🔍",
  get_market_details: "📈",
  research: "🧠",
  analyze_market: "🎯",
  open_trade: "📥",
  close_position: "📤",
  toggle_agent: "⚡",
  get_prices: "💵",
  get_llm_activity: "📋"
}

const SUGGESTIONS = [
  "What's my balance?",
  "Show my positions",
  "Search for Bitcoin markets",
  "Get crypto prices",
  "What are my agents doing?",
  "Find me a good trade"
]

export function FBPChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId] = useState(() => `session-${Date.now()}`)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    const userMessage: Message = {
      role: "user",
      content: input.trim(),
      timestamp: new Date()
    }

    setMessages(prev => [...prev, userMessage])
    setInput("")
    setIsLoading(true)

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      const response = await fetch(`${apiUrl}/api/chat/${sessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{ role: "user", content: userMessage.content }]
        })
      })

      const data = await response.json()

      const assistantMessage: Message = {
        role: "assistant",
        content: data.response,
        toolCalls: data.tool_calls,
        timestamp: new Date()
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error("Chat error:", error)
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Error connecting to FBP Agent. Make sure the API is running.",
        timestamp: new Date()
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const clearChat = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      await fetch(`${apiUrl}/api/chat/${sessionId}`, { method: "DELETE" })
    } catch (e) {
      console.error("Clear session error:", e)
    }
    setMessages([])
  }

  const useSuggestion = (text: string) => {
    setInput(text)
    inputRef.current?.focus()
  }

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-zinc-950 to-zinc-900 rounded-lg border border-zinc-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-950/50 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Bot className="w-5 h-5 text-violet-400" />
            <Sparkles className="w-2.5 h-2.5 text-amber-400 absolute -top-0.5 -right-0.5" />
          </div>
          <span className="font-bold text-sm bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
            FBP Agent
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 font-mono">
            perplexity
          </span>
        </div>
        <button
          onClick={clearChat}
          className="p-1.5 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
          title="Clear chat"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/20 flex items-center justify-center mb-4">
              <Bot className="w-8 h-8 text-violet-400" />
            </div>
            <h3 className="font-semibold text-zinc-200 mb-1">FBP Agent</h3>
            <p className="text-xs text-zinc-500 mb-6 max-w-[250px]">
              Your AI trading assistant. Ask me anything about markets, positions, or let me help you trade.
            </p>
            
            {/* Suggestions */}
            <div className="flex flex-wrap gap-2 justify-center max-w-[300px]">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => useSuggestion(s)}
                  className="text-xs px-3 py-1.5 rounded-full bg-zinc-800/50 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-all hover:scale-105"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <MessageBubble key={idx} message={msg} />
          ))
        )}
        
        {isLoading && (
          <div className="flex items-center gap-2 text-violet-400">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-xs">FBP is thinking...</span>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-zinc-800 bg-zinc-950/50">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask FBP anything..."
            className="flex-1 bg-zinc-800/50 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-500 resize-none focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20 min-h-[40px] max-h-[120px]"
            rows={1}
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isLoading}
            className={cn(
              "p-2.5 rounded-lg transition-all",
              input.trim() && !isLoading
                ? "bg-violet-500 hover:bg-violet-600 text-white"
                : "bg-zinc-800 text-zinc-600 cursor-not-allowed"
            )}
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={cn("flex gap-2", isUser ? "flex-row-reverse" : "flex-row")}>
      {/* Avatar */}
      <div className={cn(
        "w-7 h-7 rounded-lg flex items-center justify-center shrink-0",
        isUser ? "bg-emerald-500/20" : "bg-violet-500/20"
      )}>
        {isUser ? (
          <User className="w-4 h-4 text-emerald-400" />
        ) : (
          <Bot className="w-4 h-4 text-violet-400" />
        )}
      </div>

      {/* Content */}
      <div className={cn(
        "flex flex-col gap-2 max-w-[85%]",
        isUser ? "items-end" : "items-start"
      )}>
        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="w-full space-y-1">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-zinc-400"
            >
              <Wrench className="w-3 h-3" />
              {message.toolCalls.length} tool{message.toolCalls.length > 1 ? "s" : ""} used
              <span className="text-zinc-600">{expanded ? "▼" : "▶"}</span>
            </button>
            
            {expanded && (
              <div className="space-y-1">
                {message.toolCalls.map((tc, i) => (
                  <div key={i} className="text-[10px] bg-zinc-800/50 rounded px-2 py-1 font-mono">
                    <div className="flex items-center gap-1 text-zinc-400">
                      <span>{TOOL_ICONS[tc.tool] || "🔧"}</span>
                      <span className="text-violet-400">{tc.tool}</span>
                      <span className="text-zinc-600">
                        ({JSON.stringify(tc.params).slice(0, 30)}...)
                      </span>
                    </div>
                    <div className="text-zinc-500 truncate max-w-full">
                      → {typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result).slice(0, 80)}...
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Message */}
        <div className={cn(
          "px-3 py-2 rounded-xl text-sm",
          isUser
            ? "bg-emerald-500/20 text-emerald-100"
            : "bg-zinc-800/50 text-zinc-200"
        )}>
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>

        {/* Timestamp */}
        <span className="text-[10px] text-zinc-600">
          {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </div>
  )
}
