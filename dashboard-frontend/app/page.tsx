"use client"

import { useState, useEffect } from "react"
import { Brain, AlertTriangle, Loader2, Sun, Moon, ChevronUp, ChevronDown, MessageSquare, X, Settings, Terminal, TrendingUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ThemeToggle } from "@/components/theme-toggle"
import { PortfolioMetricsCard } from "@/components/portfolio-metrics-card"
import { AgentNetwork } from "@/components/agent-network"
import { AISuggestions } from "@/components/ai-suggestions"
import { ActivityFeed } from "@/components/activity-feed"
import { FBPChat } from "@/components/fbp-chat"
import { PerformanceGraph } from "@/components/performance-graph"
import { FinancialsCard } from "@/components/financials-card"
import { LLMTerminal } from "@/components/llm-terminal"
import { AllocationPieChart } from "@/components/allocation-chart"
import { getApiUrl, getWsUrl } from "@/lib/api-url"

// ============================================================================
// TYPES
// ============================================================================

interface DashboardData {
  balance: number
  equity: number
  unrealizedPnl: number
  gasSpent: number
  total_redeemed: number
  scalp_profits_instant: number
  estimated_rebate_daily: number
  compounding_velocity: number
  costs: {
    openai: number
    perplexity: number
    gemini: number
    fly: number
    neural_total: number
    infra_total: number
  }
  riskStatus: {
    safe: boolean
    message: string
  }
  agents: {
    safe: { running: boolean; activity: string }
    scalper: { running: boolean; activity: string }
    copyTrader: { running: boolean; lastSignal: string }
    smartTrader: { running: boolean; activity: string; trades: number }
    esportsTrader: { running: boolean; activity: string; trades: number; pnl: number }
    sportsTrader: { running: boolean; activity: string; trades: number }
  }
  positions: Array<{
    market: string
    side: string
    cost: number
    value: number
    pnl: number
  }>
  trades: Array<{
    time: string
    market: string
    side: string
    amount: number
  }>
  stats: {
    tradeCount: number
    volume24h: number
  }
  dryRun: boolean
  lastUpdate: string
  walletAddress: string
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)

  // -------------------------------------------------------------------------
  // DATA FETCHING
  // -------------------------------------------------------------------------

  const fetchData = async () => {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5000)
      const res = await fetch(`${getApiUrl()}/api/dashboard`, { signal: controller.signal })
      clearTimeout(timeout)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
      setConnectionError(null)
    } catch (e) {
      console.error("Fetch error:", e)
      setConnectionError("Connection lost. Retrying...")
    }
  }

  const toggleAgent = async (id: string, _state: boolean) => {
    try {
      await fetch(`${getApiUrl()}/api/toggle-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent: id }),
      })
      setTimeout(fetchData, 500)
    } catch (e) {
      console.error("Toggle failed:", e)
    }
  }

  const toggleDryRun = async () => {
    if (!data) return
    try {
      await fetch(`${getApiUrl()}/api/update-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "dry_run", value: data.dryRun ? 0 : 1 }),
      })
      fetchData()
    } catch (e) {
      console.error("Toggle dry run failed:", e)
    }
  }

  useEffect(() => {
    let ws: WebSocket | null = null
    let poll: NodeJS.Timeout | null = null

    const startPoll = () => {
      fetchData()
      poll = setInterval(fetchData, 3000)
    }

    try {
      ws = new WebSocket(`${getWsUrl()}/ws/dashboard`)
      ws.onmessage = (e) => {
        try {
          const json = JSON.parse(e.data)
          if (json && typeof json === 'object' && !json.error) {
            setData(json)
            setConnectionError(null)
          }
        } catch { }
      }
      ws.onerror = () => ws?.close()
      ws.onclose = () => { if (!poll) startPoll() }
    } catch {
      startPoll()
    }

    return () => {
      if (poll) clearInterval(poll)
      try { ws?.close() } catch { }
    }
  }, [])

  // -------------------------------------------------------------------------
  // LOADING STATE
  // -------------------------------------------------------------------------

  if (!data) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground text-xs animate-pulse">Connecting to Neural Core...</p>
        {connectionError && (
          <p className="text-[10px] text-red-400 max-w-md text-center px-4">{connectionError}</p>
        )}
      </div>
    )
  }

  // -------------------------------------------------------------------------
  // HELPERS
  // -------------------------------------------------------------------------

  const agents = Object.entries(data.agents).map(([id, agent]: [string, any]) => ({
    id,
    name: id.charAt(0).toUpperCase() + id.slice(1).replace(/([A-Z])/g, ' $1'),
    isActive: agent.running,
    activity: agent.activity || agent.lastSignal || "",
  }))

  const greeting = () => {
    const hour = new Date().getHours()
    if (hour < 12) return "Good morning"
    if (hour < 18) return "Good afternoon"
    return "Good evening"
  }

  const formatDate = () => {
    return new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  }

  // -------------------------------------------------------------------------
  // RENDER
  // -------------------------------------------------------------------------

  return (
    <div className="min-h-screen bg-background text-foreground font-sans text-sm flex flex-col h-screen overflow-hidden">

      {/* =============================================================== */}
      {/* HEADER */}
      {/* =============================================================== */}
      <header className="border-b border-border/40 bg-card/20 backdrop-blur sticky top-0 z-50 shrink-0">
        <div className="container mx-auto px-6 h-14 flex items-center justify-between">
          {/* Left: Greeting */}
          <div className="flex items-center gap-4">
            <div>
              <p className="text-[10px] text-muted-foreground">{formatDate()}</p>
              <h1 className="text-lg font-semibold tracking-tight">
                {greeting()}, <span className="text-primary">Trader</span>
              </h1>
            </div>
          </div>

          {/* Center: Key Metrics */}
          <div className="hidden md:flex items-center gap-6">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/20 border border-border/30">
              <Brain className="h-4 w-4 text-primary" />
              <span className="text-xs font-medium">{agents.filter(a => a.isActive).length} Agents</span>
            </div>
            <div className="text-xs">
              <span className="text-muted-foreground">Today</span>
              <span className="ml-2 font-bold">{data.stats?.tradeCount || 0} trades</span>
            </div>
            <div className="text-xs">
              <span className="text-muted-foreground">PnL</span>
              <span className={`ml-2 font-bold ${data.unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {data.unrealizedPnl >= 0 ? '+' : ''}{data.unrealizedPnl.toFixed(2)}
              </span>
            </div>
          </div>

          {/* Right: Controls */}
          <div className="flex items-center gap-3">
            {/* Dry Run Toggle */}
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-card/50 border border-border/30">
              <Switch
                checked={!data.dryRun}
                onCheckedChange={toggleDryRun}
                className="data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-amber-500 h-4 w-7"
              />
              <span className={`text-[9px] font-bold uppercase ${!data.dryRun ? 'text-emerald-500' : 'text-amber-500'}`}>
                {data.dryRun ? 'SIM' : 'LIVE'}
              </span>
            </div>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* =============================================================== */}
      {/* MAIN CONTENT (WAR ROOM LAYOUT) */}
      {/* =============================================================== */}
      <main className="flex-1 container mx-auto px-4 py-4 flex flex-col gap-4 min-h-0">

        {/* TOP ROW: Metrics & Financials (Fixed Height) */}
        <div className="grid grid-cols-12 gap-4 h-[25%] max-h-[220px] shrink-0">
          <div className="col-span-8 h-full">
            <PortfolioMetricsCard
              cash={data.balance}
              equity={data.equity}
              unrealizedPnl={data.unrealizedPnl}
              tradeCount={data.compounding_velocity || data.stats?.tradeCount || 0}
              aiTip="Compounding Active: 3-second chasing cycle enabled."
            />
          </div>
          <div className="col-span-4 h-full">
            <FinancialsCard
              data={{
                ...data,
                scalp_profits_instant: data.scalp_profits_instant || 0,
                estimated_rebate_daily: data.estimated_rebate_daily || 0,
                compounding_velocity: data.compounding_velocity || 0
              }}
            />
          </div>
        </div>

        {/* MIDDLE ROW: Agents Status Bar (Compact) */}
        <div className="shrink-0 bg-card/20 border border-border/40 rounded-lg p-2 flex items-center justify-between">
          <AgentNetwork agents={agents} onToggle={toggleAgent} />
          <div className="flex items-center gap-4 text-[10px] px-4">
            <span className="text-muted-foreground">Network: <span className="text-emerald-400 font-bold">OPTIMAL</span></span>
            <span className="text-muted-foreground hidden sm:inline">Strategy: <span className="text-foreground font-mono">Smart Maker-Only</span></span>
          </div>
        </div>

        {/* BOTTOM ROW: Action & Intelligence (Fill Remaining) */}
        <div className="grid grid-cols-12 gap-4 flex-1 min-h-0">
          {/* Left: Positions & Trades */}
          <div className="col-span-7 flex flex-col gap-4 min-h-0 h-full">
            <Tabs defaultValue="positions" className="flex-1 flex flex-col min-h-0">
              <div className="flex items-center justify-between mb-2 shrink-0">
                <TabsList className="h-7 bg-muted/20 p-0.5">
                  <TabsTrigger value="positions" className="text-[10px] h-6 px-3">Positions ({data.positions?.length || 0})</TabsTrigger>
                  <TabsTrigger value="trades" className="text-[10px] h-6 px-3">Recent Trades</TabsTrigger>
                </TabsList>
                <span className="text-[10px] text-muted-foreground">
                  Open Value: <span className="text-foreground font-mono">${(data.positions || []).reduce((acc, p) => acc + (p.value || 0), 0).toFixed(2)}</span>
                </span>
              </div>

              <TabsContent value="positions" className="flex-1 m-0 min-h-0 overflow-hidden rounded-xl border border-border/40 bg-card/30">
                <div className="h-full overflow-y-auto">
                  <Table>
                    <TableHeader className="bg-muted/10 sticky top-0 z-10 backdrop-blur-sm">
                      <TableRow className="hover:bg-transparent border-border/20 h-8">
                        <TableHead className="text-[10px] font-bold h-8">MARKET</TableHead>
                        <TableHead className="text-[10px] font-bold w-16 h-8">SIDE</TableHead>
                        <TableHead className="text-[10px] font-bold text-right w-20 h-8">COST</TableHead>
                        <TableHead className="text-[10px] font-bold text-right w-20 h-8">VALUE</TableHead>
                        <TableHead className="text-[10px] font-bold text-right w-20 h-8">PNL</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(data.positions || []).length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} className="text-center py-12 text-muted-foreground text-[10px]">
                            No active positions. Scanners hunting...
                          </TableCell>
                        </TableRow>
                      ) : (
                        data.positions.map((pos, i) => (
                          <TableRow key={i} className="hover:bg-muted/5 border-border/20 h-9">
                            <TableCell className="text-[10px] truncate max-w-[220px]">{pos.market}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className={`text-[9px] h-4 px-1 ${pos.side.includes('Yes') ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'}`}>
                                {pos.side}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right text-muted-foreground text-[10px] font-mono">${pos.cost.toFixed(2)}</TableCell>
                            <TableCell className="text-right font-medium text-[10px] font-mono">${pos.value.toFixed(2)}</TableCell>
                            <TableCell className={`text-right font-bold text-[10px] font-mono ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>

              <TabsContent value="trades" className="flex-1 m-0 min-h-0 overflow-hidden rounded-xl border border-border/40 bg-card/30">
                <div className="h-full overflow-y-auto">
                  <Table>
                    <TableBody>
                      {(data.trades || []).map((t, i) => (
                        <TableRow key={i} className="hover:bg-muted/5 border-border/20 h-8">
                          <TableCell className="text-muted-foreground text-[9px] w-16">{t.time.split(' ')[1] || t.time}</TableCell>
                          <TableCell className="text-[10px] truncate max-w-[300px]">{t.market}</TableCell>
                          <TableCell className="text-right">
                            <span className={`text-[9px] px-1.5 py-0.5 rounded ${t.side.includes('Buy') ? 'bg-emerald-500/10 text-emerald-400' : 'bg-blue-500/10 text-blue-400'}`}>
                              {t.side}
                            </span>
                          </TableCell>
                          <TableCell className="text-right font-mono text-[10px]">${t.amount.toFixed(2)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </TabsContent>
            </Tabs>
          </div>

          {/* Right: LLM Terminal (Logs) */}
          <div className="col-span-5 h-full min-h-0 flex flex-col">
            <div className="flex items-center justify-between mb-2 shrink-0 px-1">
              <span className="text-[10px] font-bold uppercase text-muted-foreground tracking-wider">Neural Logic Feed</span>
            </div>
            <div className="flex-1 min-h-0 rounded-xl border border-border/40 overflow-hidden shadow-inner bg-black/40">
              <LLMTerminal className="h-full" />
            </div>
          </div>
        </div>
      </main>

      {/* =============================================================== */}
      {/* FLOATING CHAT BUTTON */}
      {/* =============================================================== */}
      <Button
        onClick={() => setChatOpen(!chatOpen)}
        className="fixed bottom-6 right-6 rounded-full w-14 h-14 shadow-2xl z-50 bg-primary hover:bg-primary/90"
      >
        {chatOpen ? <X className="h-6 w-6" /> : <MessageSquare className="h-6 w-6" />}
      </Button>

      {/* =============================================================== */}
      {/* CHAT PANEL (Overlay) */}
      {/* =============================================================== */}
      {chatOpen && (
        <div className="fixed bottom-24 right-6 w-[400px] h-[500px] max-h-[70vh] rounded-2xl border border-border/40 bg-background shadow-2xl overflow-hidden z-50 flex flex-col animate-in slide-in-from-bottom-4 duration-200">
          <div className="px-4 py-3 border-b border-border/40 bg-card/50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Brain className="h-4 w-4 text-primary" />
              <span className="font-semibold text-sm">FBP Chat</span>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setChatOpen(false)} className="h-7 w-7 p-0">
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="flex-1 overflow-hidden">
            <FBPChat />
          </div>
        </div>
      )}
    </div>
  )
}
