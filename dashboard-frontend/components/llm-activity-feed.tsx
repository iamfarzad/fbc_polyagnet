"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Brain,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
  DollarSign,
  TrendingUp,
  Search,
  Copy,
  ChevronDown,
  ChevronUp
} from "lucide-react"
import { getApiUrl } from "@/lib/api-url"

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

const AGENT_COLORS: Record<string, string> = {
  safe: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  scalper: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  copy: "bg-violet-500/20 text-violet-400 border-violet-500/30",
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  safe: <TrendingUp className="h-3 w-3" />,
  scalper: <Zap className="h-3 w-3" />,
  copy: <Copy className="h-3 w-3" />,
}

const CONCLUSION_STYLES: Record<string, string> = {
  BET: "bg-emerald-500/20 text-emerald-400",
  PASS: "bg-zinc-500/20 text-zinc-400",
  ERROR: "bg-red-500/20 text-red-400",
  TIMEOUT: "bg-orange-500/20 text-orange-400",
}

function ActivityCard({ activity, expanded, onToggle }: {
  activity: LLMActivity
  expanded: boolean
  onToggle: () => void
}) {
  const agentColor = AGENT_COLORS[activity.agent] || "bg-zinc-500/20 text-zinc-400"
  const conclusionStyle = CONCLUSION_STYLES[activity.conclusion] || CONCLUSION_STYLES.PASS

  const timeAgo = (timestamp: string) => {
    const diff = Date.now() - new Date(timestamp).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return "just now"
    if (mins < 60) return `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  return (
    <div className="group rounded-lg border border-border/50 bg-card/30 hover:bg-card/50 transition-all">
      <div
        className="flex items-start gap-2 p-2 cursor-pointer"
        onClick={onToggle}
      >
        {/* Agent Badge */}
        <div className={`flex items-center gap-1 rounded-full border px-1.5 py-0 text-[9px] font-medium ${agentColor}`}>
          {AGENT_ICONS[activity.agent]}
          <span className="uppercase">{activity.agent}</span>
        </div>

        {/* Main Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[9px] text-muted-foreground">
              {activity.action_type.toUpperCase()}
            </span>
            <span className="text-muted-foreground/50 text-[9px]">•</span>
            <span className="font-mono text-[9px] text-muted-foreground">
              {timeAgo(activity.timestamp)}
            </span>
          </div>
          <p className="font-mono text-[10px] text-foreground truncate mt-0.5">
            {activity.market_question}
          </p>
        </div>

        {/* Right Side: Conclusion + Confidence */}
        <div className="flex items-center gap-1.5">
          <div className={`rounded px-1.5 py-0 text-[9px] font-bold ${conclusionStyle}`}>
            {activity.conclusion}
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] font-semibold text-foreground">
              {(activity.confidence * 100).toFixed(0)}%
            </div>
            <div className="font-mono text-[8px] text-muted-foreground">
              {activity.duration_ms}ms
            </div>
          </div>
          {expanded ? (
            <ChevronUp className="h-3 w-3 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          )}
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="border-t border-border/30 px-3 py-3 space-y-3 bg-background/50">
          {/* Prompt */}
          <div>
            <span className="font-mono text-[10px] uppercase text-muted-foreground">Prompt</span>
            <p className="font-mono text-xs text-foreground/80 mt-1">
              {activity.prompt_summary}
            </p>
          </div>

          {/* Reasoning */}
          <div>
            <span className="font-mono text-[10px] uppercase text-muted-foreground">LLM Reasoning</span>
            <p className="font-mono text-xs text-foreground/80 mt-1 whitespace-pre-wrap">
              {activity.reasoning}
            </p>
          </div>

          {/* Data Sources */}
          {activity.data_sources && activity.data_sources.length > 0 && (
            <div>
              <span className="font-mono text-[10px] uppercase text-muted-foreground">Sources</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {activity.data_sources.map((source, i) => (
                  <Badge
                    key={i}
                    variant="secondary"
                    className="font-mono text-[10px] bg-primary/10"
                  >
                    {source}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Metrics */}
          <div className="flex items-center gap-4 pt-2 border-t border-border/30">
            <div className="flex items-center gap-1 text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span className="font-mono text-[10px]">{activity.duration_ms}ms</span>
            </div>
            <div className="flex items-center gap-1 text-muted-foreground">
              <Zap className="h-3 w-3" />
              <span className="font-mono text-[10px]">{activity.tokens_used} tokens</span>
            </div>
            <div className="flex items-center gap-1 text-muted-foreground">
              <DollarSign className="h-3 w-3" />
              <span className="font-mono text-[10px]">${activity.cost_usd.toFixed(4)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function LLMActivityFeed({ className }: { className?: string }) {
  const [data, setData] = useState<LLMActivityData | null>(null)
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<string>("all")
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const apiUrl = getApiUrl()
      const agentParam = filter !== "all" ? `&agent=${filter}` : ""
      const response = await fetch(`${apiUrl}/api/llm-activity?limit=50${agentParam}`)
      const json = await response.json()
      setData(json)
    } catch (error) {
      console.error("Failed to fetch LLM activity:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 15000) // Refresh every 15s
    return () => clearInterval(interval)
  }, [filter])

  const stats = data?.stats
  const activities = data?.activities || []

  return (
    <Card className={`border-0 bg-transparent shadow-none ${className}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            <CardTitle className="font-mono text-sm font-semibold">
              LLM Activity Feed
            </CardTitle>
          </div>
          <Button
            onClick={fetchData}
            disabled={loading}
            size="sm"
            variant="ghost"
            className="h-7 gap-1.5"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            <span className="text-xs">Refresh</span>
          </Button>
        </div>

        {/* Stats Row */}
        {stats && (
          <div className="grid grid-cols-4 gap-2 mt-2">
            <div className="rounded-md bg-background/50 p-1.5 text-center">
              <div className="font-mono text-sm font-bold text-foreground">
                {stats.total_calls}
              </div>
              <div className="font-mono text-[8px] text-muted-foreground">
                Total Calls
              </div>
            </div>
            <div className="rounded-md bg-background/50 p-1.5 text-center">
              <div className="font-mono text-sm font-bold text-emerald-400">
                {stats.decisions?.BET || 0}
              </div>
              <div className="font-mono text-[8px] text-muted-foreground">
                BET Signals
              </div>
            </div>
            <div className="rounded-md bg-background/50 p-1.5 text-center">
              <div className="font-mono text-sm font-bold text-foreground">
                {(stats.avg_confidence * 100).toFixed(0)}%
              </div>
              <div className="font-mono text-[8px] text-muted-foreground">
                Avg Confidence
              </div>
            </div>
            <div className="rounded-md bg-background/50 p-1.5 text-center">
              <div className="font-mono text-sm font-bold text-amber-400">
                ${stats.total_cost_usd?.toFixed(3) || "0.000"}
              </div>
              <div className="font-mono text-[8px] text-muted-foreground">
                Total Cost
              </div>
            </div>
          </div>
        )}
      </CardHeader>

      <CardContent className="pt-0">
        {/* Filter Tabs */}
        <Tabs value={filter} onValueChange={setFilter} className="mb-3">
          <TabsList className="grid w-full grid-cols-4 h-8">
            <TabsTrigger value="all" className="text-xs">All</TabsTrigger>
            <TabsTrigger value="safe" className="text-xs">Safe</TabsTrigger>
            <TabsTrigger value="scalper" className="text-xs">Scalper</TabsTrigger>
            <TabsTrigger value="copy" className="text-xs">Copy</TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Activity List */}
        <ScrollArea className="h-[400px] pr-3">
          <div className="space-y-2">
            {activities.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <Brain className="h-8 w-8 mb-2 opacity-50" />
                <p className="font-mono text-xs">No LLM activity yet</p>
                <p className="font-mono text-[10px] text-muted-foreground/70 mt-1">
                  Activity will appear when agents start researching
                </p>
              </div>
            ) : (
              activities.map((activity) => (
                <ActivityCard
                  key={activity.id}
                  activity={activity}
                  expanded={expandedId === activity.id}
                  onToggle={() => setExpandedId(
                    expandedId === activity.id ? null : activity.id
                  )}
                />
              ))
            )}
          </div>
        </ScrollArea>

        {/* Agent Stats Footer */}
        {stats?.by_agent && (
          <div className="mt-3 pt-3 border-t border-border/30">
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(stats.by_agent).map(([agent, agentStats]) => (
                <div
                  key={agent}
                  className={`rounded-md border p-2 ${AGENT_COLORS[agent]}`}
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    {AGENT_ICONS[agent]}
                    <span className="font-mono text-[10px] font-semibold uppercase">
                      {agent}
                    </span>
                  </div>
                  <div className="font-mono text-xs">
                    {agentStats.calls} calls • {(agentStats.bet_rate * 100).toFixed(0)}% bet rate
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
