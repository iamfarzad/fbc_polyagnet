"use client"

import { useState, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { getApiUrl, getWsUrl } from "@/lib/api-url"
import { 
  Brain, 
  RefreshCw, 
  Zap, 
  TrendingUp,
  Copy,
  ChevronDown,
  ChevronUp,
  Terminal,
  Circle
} from "lucide-react"

interface LLMActivity {
  id: string
  agent: string
  timestamp: string
  action_type: string
  market_question: string
  prompt_summary: string
  reasoning: string
  conclusion: string
  confidence: number
  data_sources: string[]
  duration_ms: number
  tokens_used: number
  cost_usd: number
}

interface LLMStats {
  total_calls: number
  total_tokens: number
  total_cost_usd: number
  avg_confidence: number
  by_agent: {
    [key: string]: {
      calls: number
      avg_confidence: number
      bet_rate: number
    }
  }
  decisions: {
    BET: number
    PASS: number
    ERROR: number
  }
}

interface LLMActivityData {
  activities: LLMActivity[]
  stats: LLMStats
}

const AGENT_STYLES: Record<string, { color: string; icon: React.ReactNode }> = {
  safe: { 
    color: "text-emerald-400", 
    icon: <TrendingUp className="h-3 w-3" /> 
  },
  scalper: { 
    color: "text-amber-400", 
    icon: <Zap className="h-3 w-3" /> 
  },
  copy: { 
    color: "text-violet-400", 
    icon: <Copy className="h-3 w-3" /> 
  },
}

const CONCLUSION_COLORS: Record<string, string> = {
  BET: "text-emerald-400",
  PASS: "text-zinc-500",
  ERROR: "text-red-400",
  TIMEOUT: "text-orange-400",
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString("en-US", { 
    hour12: false, 
    hour: "2-digit", 
    minute: "2-digit", 
    second: "2-digit" 
  })
}

function TerminalEntry({ 
  activity, 
  expanded, 
  onToggle 
}: { 
  activity: LLMActivity
  expanded: boolean
  onToggle: () => void 
}) {
  const agentStyle = AGENT_STYLES[activity.agent] || AGENT_STYLES.safe
  const conclusionColor = CONCLUSION_COLORS[activity.conclusion] || CONCLUSION_COLORS.PASS
  
  return (
    <button 
      type="button"
      className="terminal-entry hover:bg-secondary/30 cursor-pointer transition-colors w-full text-left"
      onClick={onToggle}
    >
      {/* Main line */}
      <div className="flex items-start gap-2 px-3 py-2">
        <span className="text-muted-foreground/60 font-mono text-[10px] shrink-0">
          [{formatTime(activity.timestamp)}]
        </span>
        <span className={`font-mono text-[10px] font-bold uppercase shrink-0 ${agentStyle.color}`}>
          {activity.agent}
        </span>
        <span className="text-muted-foreground font-mono text-[10px]">▸</span>
        <span className="text-foreground/80 font-mono text-[10px] uppercase">
          {activity.action_type}
        </span>
        <div className="flex-1" />
        {expanded ? (
          <ChevronUp className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        )}
      </div>
      
      {/* Market question */}
      <div className="px-3 pb-2">
        <p className="font-mono text-[11px] text-muted-foreground truncate pl-[72px]">
          {activity.market_question}
        </p>
      </div>
      
      {/* Result line */}
      <div className="flex items-center gap-2 px-3 pb-2 pl-[84px]">
        <span className="text-muted-foreground font-mono text-[10px]">►</span>
        <span className={`font-mono text-[10px] font-bold ${conclusionColor}`}>
          {activity.conclusion}
        </span>
        <span className="text-muted-foreground font-mono text-[10px]">
          ({(activity.confidence * 100).toFixed(0)}%)
        </span>
        <span className="text-muted-foreground/60 font-mono text-[10px]">
          {activity.duration_ms}ms
        </span>
      </div>
      
      {/* Expanded details */}
      {expanded && (
        <div className="bg-secondary/20 border-t border-border/30 px-3 py-2.5 space-y-2.5 animate-fade-in">
          {/* Reasoning */}
          <div className="pl-[72px]">
            <span className="text-muted-foreground/60 font-mono text-[9px] uppercase">Reasoning</span>
            <p className="font-mono text-[10px] text-muted-foreground mt-1 whitespace-pre-wrap">
              {activity.reasoning}
            </p>
          </div>
          
          {/* Data sources */}
          {activity.data_sources && activity.data_sources.length > 0 && (
            <div className="pl-[72px]">
              <span className="text-muted-foreground/60 font-mono text-[9px] uppercase">Sources</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {activity.data_sources.map((source, i) => (
                  <Badge 
                    key={i} 
                    variant="secondary" 
                    className="font-mono text-[9px] bg-secondary text-muted-foreground h-4 rounded"
                  >
                    {source}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          
          {/* Metrics */}
          <div className="flex items-center gap-4 pl-[72px] pt-1">
            <span className="font-mono text-[9px] text-muted-foreground/60">
              {activity.tokens_used} tokens
            </span>
            <span className="font-mono text-[9px] text-muted-foreground/60">
              ${activity.cost_usd.toFixed(4)}
            </span>
          </div>
        </div>
      )}
    </button>
  )
}

export function LLMTerminal() {
  const [data, setData] = useState<LLMActivityData | null>(null)
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const apiUrl = getApiUrl()
      const response = await fetch(`${apiUrl}/api/llm-activity?limit=50`)
      const json = await response.json()
      setData(json)
    } catch (error) {
      console.error("Failed to fetch LLM activity:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const wsUrl = `${getWsUrl()}/ws/llm-activity`

    try {
      wsRef.current = new WebSocket(wsUrl)
      wsRef.current.onopen = () => setLoading(false)
      wsRef.current.onmessage = (event) => {
        try {
          const json = JSON.parse(event.data) as LLMActivityData
          setData(json)
        } catch (e) {
          // ignore malformed payload
        }
      }
      wsRef.current.onerror = () => {
        // fallback to polling if WS fails
        wsRef.current?.close()
      }
      wsRef.current.onclose = () => {
        // fallback to polling
        fetchData()
        pollIntervalRef.current = setInterval(fetchData, 5000)
      }
    } catch {
      fetchData()
      pollIntervalRef.current = setInterval(fetchData, 5000)
    }

    return () => {
      try {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
      } catch {}
      try {
        wsRef.current?.close()
      } catch {}
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auto-scroll to top on new data
  useEffect(() => {
    if (scrollRef.current && data?.activities?.length) {
      scrollRef.current.scrollTop = 0
    }
  }, [data?.activities?.length])

  const stats = data?.stats
  const activities = data?.activities || []

  return (
    <div className="h-full flex flex-col bg-background font-mono">
      {/* Terminal Header */}
      <div className="shrink-0 flex items-center justify-between px-3 py-2.5 border-b border-border/40 glass">
        <div className="flex items-center gap-2">
          <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-[11px] font-semibold text-foreground">LLM TERMINAL</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <Circle className={`h-2 w-2 ${loading ? "text-amber-400" : "text-emerald-400"} fill-current`} />
            <span className="text-[9px] text-muted-foreground">
              {loading ? "syncing" : "live"}
            </span>
          </div>
          <Button
            onClick={fetchData}
            disabled={loading}
            size="sm"
            variant="ghost"
            className="h-6 w-6 p-0 hover:bg-secondary"
          >
            <RefreshCw className={`h-3 w-3 text-muted-foreground ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* Terminal Body */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto overflow-x-hidden terminal-scroll"
      >
        {activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground animate-fade-in">
            <Brain className="h-8 w-8 mb-2 opacity-30" />
            <p className="text-[11px]">No LLM activity yet</p>
            <p className="text-[9px] text-muted-foreground/60 mt-1">
              Activity appears when agents research
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border/30">
            {activities.map((activity) => (
              <TerminalEntry
                key={activity.id}
                activity={activity}
                expanded={expandedId === activity.id}
                onToggle={() => setExpandedId(
                  expandedId === activity.id ? null : activity.id
                )}
              />
            ))}
          </div>
        )}
      </div>

      {/* Terminal Footer - Stats */}
      {stats && (
        <div className="shrink-0 border-t border-border/40 glass px-3 py-2">
          <div className="flex items-center justify-between text-[9px]">
            <div className="flex items-center gap-3">
              <span className="text-muted-foreground">
                Calls: <span className="text-foreground">{stats.total_calls}</span>
              </span>
              <span className="text-muted-foreground">
                Tokens: <span className="text-foreground">{(stats.total_tokens / 1000).toFixed(1)}k</span>
              </span>
              <span className="text-muted-foreground">
                Cost: <span className="text-amber-400">${stats.total_cost_usd?.toFixed(3) || "0.000"}</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-emerald-400">{stats.decisions?.BET || 0} BET</span>
              <span className="text-border">|</span>
              <span className="text-muted-foreground">{stats.decisions?.PASS || 0} PASS</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
