"use client"

import { useState, useRef, useEffect, KeyboardEvent } from "react"
import { 
  Send, Bot, User, Wrench, Loader2, Trash2, Sparkles,
  TrendingUp, TrendingDown, Wallet, Activity, Power, PowerOff,
  DollarSign, BarChart3, Search, Brain, Zap, ExternalLink
} from "lucide-react"
import { cn } from "@/lib/utils"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

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

const TOOL_ICONS: Record<string, typeof Wallet> = {
  get_balance: Wallet,
  get_positions: BarChart3,
  get_agents: Activity,
  search_markets: Search,
  get_market_details: TrendingUp,
  research: Brain,
  analyze_market: Zap,
  open_trade: TrendingUp,
  close_position: TrendingDown,
  toggle_agent: Power,
  get_prices: DollarSign,
  get_llm_activity: Activity
}

const SUGGESTIONS = [
  "What's my balance?",
  "Show positions",
  "Agent status",
  "Search BTC markets",
  "Crypto prices",
  "Find me a trade"
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
    <div className="flex flex-col h-full bg-gradient-to-b from-zinc-950 to-zinc-900 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 bg-zinc-950/50 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Bot className="w-5 h-5 text-violet-400" />
            <Sparkles className="w-2.5 h-2.5 text-amber-400 absolute -top-0.5 -right-0.5" />
          </div>
          <span className="font-bold text-sm bg-gradient-to-r from-violet-400 to-fuchsia-400 bg-clip-text text-transparent">
            FBP Agent
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 font-mono">
            sonar-pro
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
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin min-h-0">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500/20 to-fuchsia-500/20 flex items-center justify-center mb-4">
              <Bot className="w-8 h-8 text-violet-400" />
            </div>
            <h3 className="font-semibold text-zinc-200 mb-1">FBP Agent</h3>
            <p className="text-xs text-zinc-500 mb-6 max-w-[250px]">
              Your AI trading assistant with real-time market access.
            </p>
            
            {/* Suggestions */}
            <div className="flex flex-wrap gap-2 justify-center max-w-[300px]">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => useSuggestion(s)}
                  className="text-xs px-3 py-1.5 rounded-full bg-zinc-800/50 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-all hover:scale-105 border border-zinc-700/50"
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
          <div className="flex items-center gap-2 text-violet-400 px-2">
            <div className="flex gap-1">
              <span className="w-2 h-2 rounded-full bg-violet-400 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-violet-400 animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-violet-400 animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-xs">FBP is thinking...</span>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-zinc-800 bg-zinc-950/50 shrink-0">
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

// =============================================================================
// TOOL RESULT CARDS
// =============================================================================

function ToolResultCard({ tool, result }: { tool: string; result: Record<string, unknown> | string }) {
  if (typeof result === "string") {
    return <div className="text-xs text-zinc-400 font-mono">{result}</div>
  }

  // Balance card
  if (tool === "get_balance" && result.balance_usdc !== undefined) {
    return (
      <div className="flex items-center gap-3 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
        <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
          <Wallet className="w-4 h-4 text-emerald-400" />
        </div>
        <div>
          <div className="text-lg font-bold text-emerald-400">${Number(result.balance_usdc).toFixed(2)}</div>
          <div className="text-[10px] text-zinc-500 font-mono">{String(result.wallet)}</div>
        </div>
      </div>
    )
  }

  // Agents status card
  if (tool === "get_agents") {
    const agents = [
      { key: "safe", name: "Safe", icon: "🛡️", data: result.safe as Record<string, unknown> },
      { key: "scalper", name: "Scalper", icon: "⚡", data: result.scalper as Record<string, unknown> },
      { key: "copyTrader", name: "Copy", icon: "👥", data: result.copyTrader as Record<string, unknown> }
    ]
    return (
      <div className="space-y-1.5">
        {agents.map(a => {
          const running = a.data?.running as boolean
          return (
            <div key={a.key} className={cn(
              "flex items-center justify-between p-2 rounded-lg border",
              running ? "bg-emerald-500/10 border-emerald-500/20" : "bg-zinc-800/50 border-zinc-700/50"
            )}>
              <div className="flex items-center gap-2">
                <span>{a.icon}</span>
                <span className="text-xs font-medium text-zinc-200">{a.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-500 max-w-[100px] truncate">
                  {String(a.data?.activity || "Idle")}
                </span>
                {running ? (
                  <span className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/20 px-1.5 py-0.5 rounded">
                    <Power className="w-3 h-3" /> ON
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[10px] text-zinc-500 bg-zinc-700/50 px-1.5 py-0.5 rounded">
                    <PowerOff className="w-3 h-3" /> OFF
                  </span>
                )}
              </div>
            </div>
          )
        })}
        <div className={cn(
          "text-[10px] px-2 py-1 rounded",
          result.dry_run ? "bg-amber-500/10 text-amber-400" : "bg-red-500/10 text-red-400"
        )}>
          {result.dry_run ? "🧪 Dry Run Mode" : "🔴 LIVE Trading"}
        </div>
      </div>
    )
  }

  // Prices card
  if (tool === "get_prices") {
    const prices = Object.entries(result).filter(([k]) => k !== "error")
    return (
      <div className="grid grid-cols-2 gap-1.5">
        {prices.map(([symbol, price]) => (
          <div key={symbol} className="flex items-center justify-between p-2 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
            <span className="text-xs font-medium text-zinc-300">{symbol}</span>
            <span className="text-xs font-mono text-emerald-400">${Number(price).toLocaleString()}</span>
          </div>
        ))}
      </div>
    )
  }

  // Positions card
  if (tool === "get_positions" && result.positions) {
    const positions = result.positions as Array<Record<string, unknown>>
    return (
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs px-1">
          <span className="text-zinc-500">{result.count} positions</span>
          <span className={cn(
            "font-medium",
            Number(result.total_pnl) >= 0 ? "text-emerald-400" : "text-red-400"
          )}>
            P&L: ${Number(result.total_pnl).toFixed(2)}
          </span>
        </div>
        {positions.slice(0, 3).map((p, i) => (
          <div key={i} className="p-2 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
            <div className="text-xs text-zinc-200 truncate">{String(p.title)}</div>
            <div className="flex items-center justify-between mt-1">
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded",
                p.outcome === "Yes" ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"
              )}>
                {String(p.outcome)}
              </span>
              <span className={cn(
                "text-xs font-mono",
                Number(p.pnl) >= 0 ? "text-emerald-400" : "text-red-400"
              )}>
                {Number(p.pnl) >= 0 ? "+" : ""}${Number(p.pnl).toFixed(2)}
              </span>
            </div>
          </div>
        ))}
        {positions.length > 3 && (
          <div className="text-[10px] text-zinc-500 text-center">+{positions.length - 3} more</div>
        )}
      </div>
    )
  }

  // Markets search card
  if (tool === "search_markets" && result.markets) {
    const markets = result.markets as Array<Record<string, unknown>>
    if (markets.length === 0) {
      return <div className="text-xs text-zinc-500 italic">No markets found</div>
    }
    return (
      <div className="space-y-1.5">
        {markets.slice(0, 3).map((m, i) => (
          <div key={i} className="p-2 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
            <div className="text-xs text-zinc-200 line-clamp-2">{String(m.question)}</div>
            <div className="flex items-center justify-between mt-1.5">
              <span className="text-emerald-400 text-xs font-mono">
                YES: {(Number(m.yes_price) * 100).toFixed(0)}¢
              </span>
              <span className="text-[10px] text-zinc-500">
                Vol: ${Number(m.volume).toLocaleString()}
              </span>
            </div>
          </div>
        ))}
      </div>
    )
  }

  // Trade result card
  if ((tool === "open_trade" || tool === "close_position") && result.status === "success") {
    const isOpen = tool === "open_trade"
    return (
      <div className={cn(
        "p-3 rounded-lg border",
        isOpen ? "bg-emerald-500/10 border-emerald-500/20" : "bg-amber-500/10 border-amber-500/20"
      )}>
        <div className="flex items-center gap-2 mb-2">
          {isOpen ? (
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          ) : (
            <TrendingDown className="w-4 h-4 text-amber-400" />
          )}
          <span className={cn(
            "text-xs font-medium",
            isOpen ? "text-emerald-400" : "text-amber-400"
          )}>
            {isOpen ? "Position Opened" : "Position Closed"}
          </span>
        </div>
        <div className="text-xs text-zinc-300 mb-1">{String(result.market)}</div>
        <div className="flex gap-3 text-[10px] text-zinc-400">
          <span>{String(result.outcome)}</span>
          <span>${Number(result.amount || result.value).toFixed(2)}</span>
          <span>{Number(result.shares || result.shares_sold).toFixed(1)} shares</span>
        </div>
      </div>
    )
  }

  // Default: JSON display
  return (
    <pre className="text-[10px] text-zinc-400 font-mono bg-zinc-800/50 p-2 rounded overflow-x-auto max-h-[100px]">
      {JSON.stringify(result, null, 2)}
    </pre>
  )
}

// =============================================================================
// MESSAGE BUBBLE
// =============================================================================

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user"
  const [expanded, setExpanded] = useState(true)

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
        "flex flex-col gap-2 max-w-[90%]",
        isUser ? "items-end" : "items-start"
      )}>
        {/* Tool calls (before message for assistant) */}
        {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
          <div className="w-full space-y-2">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1.5 text-[10px] text-zinc-500 hover:text-zinc-400 transition-colors"
            >
              <Wrench className="w-3 h-3" />
              <span>{message.toolCalls.length} tool{message.toolCalls.length > 1 ? "s" : ""} used</span>
              <span className="text-zinc-600">{expanded ? "▼" : "▶"}</span>
            </button>
            
            {expanded && (
              <div className="space-y-2">
                {message.toolCalls.map((tc, i) => {
                  const Icon = TOOL_ICONS[tc.tool] || Wrench
                  return (
                    <div key={i} className="rounded-lg border border-zinc-700/50 overflow-hidden">
                      {/* Tool header */}
                      <div className="flex items-center gap-2 px-2 py-1.5 bg-zinc-800/80 border-b border-zinc-700/50">
                        <Icon className="w-3.5 h-3.5 text-violet-400" />
                        <span className="text-[11px] font-medium text-zinc-300">{tc.tool}</span>
                        {Object.keys(tc.params).length > 0 && (
                          <span className="text-[10px] text-zinc-500 font-mono">
                            ({Object.entries(tc.params).map(([k, v]) => `${k}: ${v}`).join(", ")})
                          </span>
                        )}
                      </div>
                      {/* Tool result */}
                      <div className="p-2 bg-zinc-900/50">
                        <ToolResultCard tool={tc.tool} result={tc.result} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* Message content */}
        <div className={cn(
          "px-3 py-2 rounded-xl text-sm",
          isUser
            ? "bg-emerald-500/20 text-emerald-100"
            : "bg-zinc-800/50 text-zinc-200"
        )}>
          {isUser ? (
            <p>{message.content}</p>
          ) : (
            <div className="prose prose-sm prose-invert prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-li:my-0 prose-strong:text-zinc-100 max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Timestamp */}
        <span className="text-[10px] text-zinc-600 px-1">
          {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </div>
  )
}
