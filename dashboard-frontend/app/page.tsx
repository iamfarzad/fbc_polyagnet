"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  TrendingUp, TrendingDown, DollarSign,
  Activity, Zap, Wallet, ExternalLink, Brain, Shield,
  BarChart3, Settings, PieChart,
  X, XCircle, Loader2, Gamepad2, Users, LayoutDashboard, Terminal,
  ChevronRight, ChevronUp, AlertTriangle, Monitor, Trophy, Lock, MessageSquare, Minimize2, Maximize2,
  Info, ChevronDown
} from "lucide-react"
import { LLMTerminal } from "@/components/llm-terminal"
import { FBPChat } from "@/components/fbp-chat"
import { ThemeToggle } from "@/components/theme-toggle"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PerformanceGraph } from "@/components/performance-graph"
import { FinancialsCard } from "@/components/financials-card"
import { getApiUrl, getWsUrl } from "@/lib/api-url"

interface DashboardData {
  balance: number
  equity: number
  unrealizedPnl: number
  gasSpent: number
  total_redeemed: number
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
    safe: { running: boolean; activity: string; endpoint: string }
    scalper: { running: boolean; activity: string; endpoint: string }
    copyTrader: { running: boolean; lastSignal: string }
    smartTrader: { running: boolean; activity: string; positions: number; trades: number; mode: string; lastScan: string }
    esportsTrader: { running: boolean; activity: string; trades: number; mode: string; lastScan: string; pnl: number }
    sportsTrader: { running: boolean; activity: string; trades: number; mode: string; lastScan: string }
  }
  positions: Array<{
    market: string
    side: string
    cost: number
    value: number
    pnl: number
  }>
  openOrders: Array<{
    id: string
    market: string
    side: string
    size: number
    price: number
    filled: number
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
  maxBetAmount?: number
}

// Agent color schemes
const AGENT_THEMES = {
  safe: { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-400", icon: Shield, label: "Safety" },
  scalper: { bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-400", icon: Zap, label: "Scalper" },
  copyTrader: { bg: "bg-violet-500/10", border: "border-violet-500/30", text: "text-violet-400", icon: Users, label: "Copy Trading" },
  smartTrader: { bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-400", icon: Brain, label: "Smart (Politics)" },
  esportsTrader: { bg: "bg-pink-500/10", border: "border-pink-500/30", text: "text-pink-400", icon: Gamepad2, label: "eSports" },
  sportsTrader: { bg: "bg-orange-500/10", border: "border-orange-500/30", text: "text-orange-400", icon: Trophy, label: "Sports Trader" },
}

const AGENT_DESCRIPTIONS: Record<string, string> = {
  safe: "Growth Protocol check. Validates markets with Perplexity/LLM. Confirms Edge > 15%, Confidence > 75%. Uses Kelly Criterion for sizing.",
  scalper: "HFT + Binance Arb. High-frequency trading on 15m crypto markets. Exploits price dislocations between Polymarket and Binance.",
  copyTrader: "Whale Follower. Tracks elite traders (e.g., monkeyfish69). Copies trades with 15% wallet cap.",
  smartTrader: "Market Maker. Provides liquidity on spread. (Currently Idle).",
  esportsTrader: "Teemu v2. Hybrid Strategy. Uses PandaScore live data for latency arbitrage (30s edge). Includes Dynamic Whale Search and Smart Polling.",
  sportsTrader: "Direct Gamma. Fast execution on sports events using Gamma API odds."
}

interface Notification {
  id: string
  type: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  timestamp: number
  actionUrl?: string
}

export default function ProDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [maxBet, setMaxBet] = useState(0.50)
  const [updatingConfig, setUpdatingConfig] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [showNotifications, setShowNotifications] = useState(false)

  // Mobile panel state: 'chat', 'terminal', or null (closed)
  const [mobilePanel, setMobilePanel] = useState<'chat' | 'terminal' | null>(null)
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null)

  const fetchDashboardData = async () => {
    let id: NodeJS.Timeout | undefined
    try {
      const controller = new AbortController()
      id = setTimeout(() => controller.abort(), 5000) // 5s timeout

      const response = await fetch(`${getApiUrl()}/api/dashboard`, { signal: controller.signal })
      clearTimeout(id)

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const json = await response.json()
      setData(json)
      setConnectionError(null)
      if (json.maxBetAmount !== undefined && !updatingConfig) setMaxBet(json.maxBetAmount)
    } catch (error) {
      console.error("Failed to fetch dashboard data:", error)
      setConnectionError("Failed to access Neural Core. Retrying...")
    }
  }

  const toggleAgent = async (agent: string) => {
    try {
      const response = await fetch(`${getApiUrl()}/api/toggle-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent }),
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      // Small delay to ensure Supabase update propagates
      setTimeout(() => fetchDashboardData(), 1000)
    } catch (error) {
      console.error("Failed to toggle agent:", error)
    }
  }

  const toggleDryRun = async (current: boolean) => {
    setUpdatingConfig(true)
    try {
      await fetch(`${getApiUrl()}/api/update-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "dry_run", value: current ? 0 : 1 }),
      })
      fetchDashboardData()
    } finally {
      setUpdatingConfig(false)
    }
  }

  const emergencyStop = async () => {
    await fetch(`${getApiUrl()}/api/emergency-stop`, { method: "POST" })
    fetchDashboardData()
  }

  const checkLiveMatches = async () => {
    try {
      const response = await fetch(`${getApiUrl()}/api/live-matches`)
      if (response.ok) {
        const matchData = await response.json()

        // Check for esports matches
        const esportsMatches = matchData.esports || []
        if (esportsMatches.length > 0 && esportsMatches.length !== notifications.filter(n => n.type === 'success').length) {
          const newNotification: Notification = {
            id: `esports-${Date.now()}`,
            type: 'success',
            title: '🎮 Live Esports Matches Detected!',
            message: `Found ${esportsMatches.length} active esports matches. Trading opportunities available!`,
            timestamp: Date.now(),
            actionUrl: 'https://polymarket.com/search?_q=esports'
          }

          setNotifications(prev => [newNotification, ...prev.slice(0, 4)]) // Keep last 5
          setShowNotifications(true)

          // Auto-hide after 30 seconds
          setTimeout(() => {
            setNotifications(prev => prev.filter(n => n.id !== newNotification.id))
          }, 30000)
        }
      }
    } catch (error) {
      console.error("Failed to check live matches:", error)
    }
  }

  useEffect(() => {
    let pollInterval: ReturnType<typeof setInterval> | null = null
    let ws: WebSocket | null = null

    const startPolling = () => {
      fetchDashboardData()
      pollInterval = setInterval(fetchDashboardData, 3000)
    }

    // Check for live matches every 30 seconds
    const matchInterval = setInterval(checkLiveMatches, 30000)

    try {
      ws = new WebSocket(`${getWsUrl()}/ws/dashboard`)
      ws.onmessage = (event) => {
        try {
          const json = JSON.parse(event.data) as DashboardData
          if (json && typeof json === 'object' && !json.error) {
            setData(json)
            if (json.maxBetAmount !== undefined && !updatingConfig) setMaxBet(json.maxBetAmount)
          }
        } catch (error) {
          console.error("Failed to parse WebSocket message:", error)
        }
      }
      ws.onerror = () => {
        try {
          ws?.close()
        } catch { }
      }
      ws.onclose = () => {
        if (!pollInterval) startPolling()
      }
    } catch {
      startPolling()
    }

    return () => {
      if (pollInterval) clearInterval(pollInterval)
      try {
        ws?.close()
      } catch { }
    }
  }, [])

  if (!data || !data.agents || !data.positions || !data.trades) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground text-xs animate-pulse">Connecting to Neural Core...</p>
        {connectionError && (
          <p className="text-[10px] text-red-400 max-w-md text-center px-4">
            {connectionError}
          </p>
        )}
        <p className="text-[10px] text-muted-foreground/50 max-w-md text-center px-4">
          If this persists, the API might be sleeping. It should wake up in ~10s.
        </p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground font-mono text-xs flex flex-col">

      {/* Notifications Panel */}
      {showNotifications && notifications.length > 0 && (
        <div className="fixed top-14 right-4 z-50 w-96 max-w-sm bg-card border border-border rounded-lg shadow-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-sm flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Live Match Alerts
            </h3>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowNotifications(false)}
              className="h-6 w-6 p-0"
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
          <div className="space-y-3">
            {notifications.map((notification) => (
              <div key={notification.id} className="border border-border/50 rounded p-3 bg-background/50">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h4 className="font-semibold text-sm text-foreground">{notification.title}</h4>
                    <p className="text-xs text-muted-foreground mt-1">{notification.message}</p>
                    <p className="text-[10px] text-muted-foreground/70 mt-2">
                      {new Date(notification.timestamp).toLocaleTimeString()}
                    </p>
                  </div>
                  {notification.actionUrl && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-xs ml-2"
                      onClick={() => window.open(notification.actionUrl, '_blank')}
                    >
                      View
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-border/50">
            <p className="text-[10px] text-muted-foreground text-center">
              Esports monitor checks every 30 seconds
            </p>
          </div>
        </div>
      )}

      {/* 1. Header: Status & Global Controls */}
      <header className="border-b border-border/40 bg-card/20 backdrop-blur sticky top-0 z-50">
        <div className="container mx-auto px-4 h-12 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Brain className="h-4 w-4 text-primary" />
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm tracking-tight">POLYAGENT PRO</span>
              <Badge variant="outline" className="text-[10px] h-5 border-border/40">{data.walletAddress.slice(0, 6)}...</Badge>
            </div>
          </div>

          <div className="flex items-center gap-6">
            {/* Notifications */}
            {notifications.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowNotifications(!showNotifications)}
                className="relative h-8 px-3 text-xs border-orange-500/50 hover:border-orange-500"
              >
                <AlertTriangle className="h-3 w-3 mr-1 text-orange-500" />
                {notifications.length} Alert{notifications.length !== 1 ? 's' : ''}
                {showNotifications ? <ChevronUp className="h-3 w-3 ml-1" /> : <ChevronDown className="h-3 w-3 ml-1" />}
              </Button>
            )}

            <div className="hidden md:flex gap-6 text-[11px]">
              <div>
                <span className="text-muted-foreground mr-2">CASH</span>
                <span className="font-bold">${data.balance.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-muted-foreground mr-2">EQUITY</span>
                <span className="font-bold text-blue-400">${data.equity.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-muted-foreground mr-2">PnL</span>
                <span className={`font-bold ${data.unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {data.unrealizedPnl >= 0 ? '+' : ''}{data.unrealizedPnl.toFixed(2)}
                </span>
              </div>
            </div>

            <Separator orientation="vertical" className="h-4 hidden md:block" />

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 bg-card/50 rounded-full px-2 py-0.5 border border-border/20">
                <Switch
                  checked={!data.dryRun}
                  onCheckedChange={() => toggleDryRun(data.dryRun)}
                  className="data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-amber-500 border-none h-4 w-7"
                />
                <span className={`text-[9px] font-bold ${!data.dryRun ? 'text-emerald-500' : 'text-amber-500'}`}>
                  {data.dryRun ? 'SIMULATION' : 'LIVE TRADING'}
                </span>
              </div>

              <Button variant="ghost" size="icon" onClick={emergencyStop} className="text-red-500 hover:text-red-600 hover:bg-red-500/10 h-8 w-8">
                <AlertTriangle className="h-4 w-4" />
              </Button>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      {/* 2. Main Content Grid - 3 Columns */}
      <main className="flex-1 container mx-auto px-4 py-4 grid grid-cols-1 lg:grid-cols-12 gap-4">

        {/* Left Column: Agents & Config (20% -> col-span-2) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <Card className="border-border/40 glass">
            <CardHeader className="py-2 px-3 border-b border-border/40"><CardTitle className="text-[10px] font-bold uppercase tracking-wider flex items-center gap-2"><Zap className="h-3 w-3" /> Agents</CardTitle></CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-border/20">
                {Object.entries(data.agents).map(([key, agent]: [string, any]) => {
                  const theme = AGENT_THEMES[key as keyof typeof AGENT_THEMES] || AGENT_THEMES.safe
                  const Icon = theme.icon
                  const isExpanded = expandedAgent === key

                  return (
                    <div key={key} className="flex flex-col border-b border-border/10 last:border-0 hover:bg-white/5 transition-colors group">
                      <div className="p-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className={`h-6 w-6 rounded-sm ${theme.bg} flex items-center justify-center opacity-80 group-hover:opacity-100`}>
                            <Icon className={`h-3 w-3 ${theme.text}`} />
                          </div>
                          <p className="font-bold text-[10px] capitalize leading-tight">{theme.label}</p>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-4 w-4 ml-1 opacity-50 hover:opacity-100"
                            onClick={() => setExpandedAgent(isExpanded ? null : key)}
                          >
                            {isExpanded ? <ChevronDown className="h-3 w-3" /> : <Info className="h-3 w-3" />}
                          </Button>
                        </div>
                        <Switch checked={agent.running} onCheckedChange={() => toggleAgent(key)} className="scale-75 origin-right" />
                      </div>

                      {isExpanded && (
                        <div className="px-3 pb-2 text-[9px] text-muted-foreground animate-in slide-in-from-top-1 fade-in duration-200">
                          <div className="bg-background/50 p-2 rounded border border-border/20 shadow-inner">
                            {AGENT_DESCRIPTIONS[key] || "No description available."}
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/40 glass">
            <CardHeader className="py-2 px-3 border-b border-border/40"><CardTitle className="text-[10px] font-bold uppercase tracking-wider flex items-center gap-2"><Lock className="h-3 w-3" /> Risk</CardTitle></CardHeader>
            <CardContent className="p-3 space-y-3">
              <div>
                <label className="text-[9px] text-muted-foreground mb-1 block">MAX BET</label>
                <Input
                  type="number"
                  value={maxBet}
                  onChange={(e) => setMaxBet(parseFloat(e.target.value))}
                  className="h-7 text-xs font-mono"
                />
              </div>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-2 border-t border-border/20">
                <span>STATUS</span>
                <span className={data.riskStatus.safe ? "text-emerald-400" : "text-amber-400"}>{data.riskStatus.message}</span>
              </div>
            </CardContent>
          </Card>

          {/* Financials Card */}
          <FinancialsCard data={data} />
        </div>

        {/* Center Column: Graphs & Portfolio (55% -> col-span-7) */}
        <div className="lg:col-span-7 flex flex-col gap-4">

          {/* Graph */}
          <Card className="border-border/40 glass h-[200px] flex flex-col text-xs">
            <CardContent className="p-2 h-full">
              <PerformanceGraph />
            </CardContent>
          </Card>

          {/* Active Portfolio & Orders */}
          <Card className="border-border/40 glass flex-1 min-h-[300px]">
            <Tabs defaultValue="positions" className="h-full flex flex-col">
              <CardHeader className="py-2 px-3 border-b border-border/40 flex flex-row items-center justify-between h-9">
                <div className="flex items-center gap-4">
                  <CardTitle className="text-[10px] font-bold uppercase tracking-wider flex items-center gap-2">
                    <BarChart3 className="h-3 w-3" /> Portfolio
                  </CardTitle>
                  <TabsList className="h-6 bg-secondary/50 p-0 ml-2">
                    <TabsTrigger value="positions" className="h-full text-[10px] px-3 data-[state=active]:bg-background/80 transition-all rounded-sm">
                      Positions ({data.positions?.length || 0})
                    </TabsTrigger>
                  </TabsList>
                </div>
                <span className="text-[10px] text-muted-foreground">
                  Open Value: ${(data.positions || []).reduce((acc, p) => acc + (p.value || 0), 0).toFixed(2)}
                </span>
              </CardHeader>
              <CardContent className="p-0 flex-1">
                <TabsContent value="positions" className="m-0 h-full">
                  <Table>
                    <TableHeader className="bg-muted/10">
                      <TableRow className="hover:bg-transparent border-border/20 h-8">
                        <TableHead className="h-8 text-[10px] font-bold">MARKET</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold w-[60px]">SIDE</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold text-right w-[80px]">COST</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold text-right w-[80px]">VALUE</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold text-right w-[80px]">PnL</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(!(data.positions || []).length) ? (
                        <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No active positions</TableCell></TableRow>
                      ) : (
                        (data.positions || []).map((pos, i) => (
                          <TableRow key={i} className="hover:bg-muted/5 border-border/20 text-xs h-9">
                            <TableCell className="font-medium truncate max-w-[300px] py-1 text-[11px]">{pos.market}</TableCell>
                            <TableCell className="py-1">
                              <Badge variant="outline" className={`text-[9px] border-border/40 px-1.5 h-5 ${pos.side.includes('Yes') ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'}`}>
                                {pos.side}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right text-muted-foreground py-1">${pos.cost.toFixed(2)}</TableCell>
                            <TableCell className="text-right font-medium py-1">${pos.value.toFixed(2)}</TableCell>
                            <TableCell className={`text-right font-bold py-1 ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </TabsContent>

                <TabsContent value="orders" className="m-0 h-full">
                  <Table>
                    <TableHeader className="bg-muted/10">
                      <TableRow className="hover:bg-transparent border-border/20 h-8">
                        <TableHead className="h-8 text-[10px] font-bold">MARKET</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold w-[60px]">SIDE</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold text-right w-[80px]">PRICE</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold text-right w-[80px]">SIZE</TableHead>
                        <TableHead className="h-8 text-[10px] font-bold text-right w-[80px]">STATUS</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(!(data.openOrders || []).length) ? (
                        <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No open orders</TableCell></TableRow>
                      ) : (
                        (data.openOrders || []).map((ord, i) => (
                          <TableRow key={i} className="hover:bg-muted/5 border-border/20 text-xs h-9">
                            <TableCell className="font-medium truncate max-w-[300px] py-1 text-[11px]">{ord.market}</TableCell>
                            <TableCell className="py-1">
                              <Badge variant="outline" className={`text-[9px] border-border/40 px-1.5 h-5 ${ord.side === 'BUY' ? 'text-emerald-400 bg-emerald-500/10' : 'text-amber-400 bg-amber-500/10'}`}>
                                {ord.side}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono py-1">${ord.price.toFixed(3)}</TableCell>
                            <TableCell className="text-right font-mono py-1">${ord.size.toFixed(2)}</TableCell>
                            <TableCell className="text-right text-muted-foreground py-1 text-[10px]">OPEN</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </TabsContent>
              </CardContent>
            </Tabs>
          </Card>

          {/* Recent History */}
          <Card className="border-border/40 glass h-[200px] flex flex-col">
            <CardHeader className="py-2 px-3 border-b border-border/40 h-9"><CardTitle className="text-[10px] font-bold uppercase tracking-wider">Recent Trades</CardTitle></CardHeader>
            <CardContent className="flex-1 overflow-auto p-0">
              <Table>
                <TableBody>
                  {(data.trades || []).map((t, i) => (
                    <TableRow key={i} className="hover:bg-muted/5 border-border/20 text-[10px] h-8">
                      <TableCell className="text-muted-foreground w-[80px] py-1">{t.time.split(' ')[1] || t.time}</TableCell>
                      <TableCell className="truncate max-w-[400px] py-1">{t.market}</TableCell>
                      <TableCell className="text-right py-1">
                        <span className={`px-1.5 py-0.5 rounded ${t.side.includes('Buy') ? 'bg-emerald-500/10 text-emerald-400' : 'bg-blue-500/10 text-blue-400'}`}>
                          {t.side}
                        </span>
                      </TableCell>
                      <TableCell className="text-right font-mono py-1">${t.amount.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Communication (25% -> col-span-3) */}
        <div className="lg:col-span-3 flex flex-col h-[calc(100vh-80px)] sticky top-20">
          <div className="border border-border/40 rounded-xl bg-black/40 overflow-hidden flex flex-col h-full shadow-2xl">
            <Tabs defaultValue="chat" className="flex-1 flex flex-col">
              <div className="bg-muted/10 px-0 border-b border-border/40 flex">
                <TabsList className="h-9 bg-transparent p-0 w-full justify-start rounded-none">
                  <TabsTrigger value="chat" className="rounded-none border-r border-border/20 data-[state=active]:bg-muted/20 text-[10px] h-9 px-4">
                    <MessageSquare className="w-3 h-3 mr-2" /> CHAT
                  </TabsTrigger>
                  <TabsTrigger value="terminal" className="rounded-none border-r border-border/20 data-[state=active]:bg-muted/20 text-[10px] h-9 px-4">
                    <Terminal className="w-3 h-3 mr-2" /> TERMINAL
                  </TabsTrigger>
                </TabsList>
              </div>

              <div className="flex-1 relative">
                <TabsContent value="terminal" className="absolute inset-0 m-0">
                  <LLMTerminal />
                </TabsContent>
                <TabsContent value="chat" className="absolute inset-0 m-0 bg-background/50">
                  <FBPChat />
                </TabsContent>
              </div>
            </Tabs>
          </div>
        </div>

      </main>

      {/* Mobile Floating Action Buttons - Only visible on small screens */}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2 lg:hidden z-40">
        <Button
          onClick={() => setMobilePanel('terminal')}
          size="lg"
          className="rounded-full w-14 h-14 shadow-lg bg-primary hover:bg-primary/90"
        >
          <Terminal className="h-6 w-6" />
        </Button>
        <Button
          onClick={() => setMobilePanel('chat')}
          size="lg"
          className="rounded-full w-14 h-14 shadow-lg bg-violet-500 hover:bg-violet-600"
        >
          <MessageSquare className="h-6 w-6" />
        </Button>
      </div>

      {/* Mobile Full-Screen Overlay Panel */}
      {mobilePanel && (
        <div className="fixed inset-0 z-50 bg-background lg:hidden flex flex-col animate-in slide-in-from-bottom duration-300">
          {/* Header */}
          <header className="h-12 border-b border-border/40 bg-card/50 backdrop-blur flex items-center justify-between px-4">
            <div className="flex items-center gap-2">
              {mobilePanel === 'terminal' ? (
                <>
                  <Terminal className="h-4 w-4 text-primary" />
                  <span className="font-bold text-sm">LLM Terminal</span>
                </>
              ) : (
                <>
                  <MessageSquare className="h-4 w-4 text-violet-400" />
                  <span className="font-bold text-sm">FBP Chat</span>
                </>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setMobilePanel(null)}
              className="h-8 w-8 p-0"
            >
              <X className="h-5 w-5" />
            </Button>
          </header>

          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {mobilePanel === 'terminal' ? <LLMTerminal /> : <FBPChat />}
          </div>
        </div>
      )}
    </div>
  )
}
