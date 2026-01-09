"use client"

import { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { 
  RefreshCw, AlertTriangle, TrendingUp, TrendingDown, DollarSign, 
  Activity, Zap, Wallet, ExternalLink, Brain, Shield, Gauge,
  BarChart3, Clock, Target, Users, Layers, Settings, PieChart
} from "lucide-react"
import { LLMTerminal } from "@/components/llm-terminal"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"

interface DashboardData {
  balance: number
  equity: number
  unrealizedPnl: number
  gasSpent: number
  riskStatus: {
    safe: boolean
    message: string
  }
  agents: {
    safe: { running: boolean; activity: string; endpoint: string }
    scalper: { running: boolean; activity: string; endpoint: string }
    copyTrader: { running: boolean; lastSignal: string }
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
  maxBetAmount?: number
}

// Agent color schemes
const AGENT_THEMES = {
  safe: {
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    text: "text-emerald-400",
    icon: Shield,
    allocation: 50,
  },
  scalper: {
    bg: "bg-amber-500/10",
    border: "border-amber-500/30",
    text: "text-amber-400",
    icon: Zap,
    allocation: 30,
  },
  copy: {
    bg: "bg-violet-500/10",
    border: "border-violet-500/30",
    text: "text-violet-400",
    icon: Users,
    allocation: 20,
  },
}

export default function PolymarketDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [maxBet, setMaxBet] = useState(0.50)
  const [updatingConfig, setUpdatingConfig] = useState(false)
  const [activeTab, setActiveTab] = useState("overview")

  const fetchDashboardData = async () => {
    setLoading(true)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || ""
      const response = await fetch(`${apiUrl}/api/dashboard`)
      const json = await response.json()
      setData(json)
      if (json.maxBetAmount !== undefined) setMaxBet(json.maxBetAmount)
    } catch (error) {
      console.error("Failed to fetch dashboard data:", error)
    } finally {
      setLoading(false)
    }
  }

  const toggleAgent = async (agent: "safe" | "scalper" | "copyTrader") => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || ""
      await fetch(`${apiUrl}/api/toggle-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent }),
      })
      fetchDashboardData()
    } catch (error) {
      console.error("Failed to toggle agent:", error)
    }
  }

  const emergencyStop = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || ""
      await fetch(`${apiUrl}/api/emergency-stop`, { method: "POST" })
      fetchDashboardData()
    } catch (error) {
      console.error("Failed to emergency stop:", error)
    }
  }

  const toggleDryRun = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || ""
      await fetch(`${apiUrl}/api/toggle-dry-run`, { method: "POST" })
      fetchDashboardData()
    } catch (error) {
      console.error("Failed to toggle dry run:", error)
    }
  }

  const updateMaxBet = async () => {
    setUpdatingConfig(true)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || ""
      await fetch(`${apiUrl}/api/update-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "max_bet", value: Number(maxBet) }),
      })
      fetchDashboardData()
    } catch (error) {
      console.error("Failed to update config:", error)
    } finally {
      setUpdatingConfig(false)
    }
  }

  useEffect(() => {
    fetchDashboardData()
    const interval = setInterval(fetchDashboardData, 30000)
    return () => clearInterval(interval)
  }, [])

  if (!data) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a0a0f]">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="h-12 w-12 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
            <Brain className="absolute inset-0 m-auto h-5 w-5 text-primary" />
          </div>
          <span className="font-mono text-sm text-muted-foreground">Initializing agents...</span>
        </div>
      </div>
    )
  }

  const pnlIsPositive = data.unrealizedPnl >= 0
  const activeAgentCount = [data.agents.safe.running, data.agents.scalper.running, data.agents.copyTrader.running].filter(Boolean).length

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[#0a0a0f] text-foreground">
      {/* Top Status Bar - Fixed Height */}
      <div className="h-12 shrink-0 border-b border-border/30 bg-[#0a0a0f]/80 backdrop-blur-xl z-50">
        <div className="h-full mx-auto max-w-[1800px] px-4 flex items-center">
          <div className="flex-1 flex items-center justify-between">
            {/* Left: Branding + Status */}
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-primary to-primary/50 flex items-center justify-center">
                  <Brain className="h-4 w-4 text-primary-foreground" />
                </div>
                <div>
                  <h1 className="font-mono text-sm font-bold tracking-tight">POLYAGENT</h1>
                  <p className="font-mono text-[10px] text-muted-foreground">{data.lastUpdate}</p>
                </div>
              </div>
              
              <Separator orientation="vertical" className="h-8" />
              
              {/* Quick Stats */}
              <div className="hidden md:flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <div className={`h-2 w-2 rounded-full ${data.riskStatus.safe ? "bg-emerald-500" : "bg-red-500"} animate-pulse`} />
                  <span className="font-mono text-xs text-muted-foreground">
                    {data.riskStatus.safe ? "Systems Normal" : "Risk Alert"}
                  </span>
                </div>
                <div className="font-mono text-xs">
                  <span className="text-muted-foreground">Agents: </span>
                  <span className="text-foreground font-semibold">{activeAgentCount}/3</span>
                </div>
                <div className="font-mono text-xs">
                  <span className="text-muted-foreground">Mode: </span>
                  <Badge variant={data.dryRun ? "secondary" : "default"} className="text-[10px] h-5">
                    {data.dryRun ? "🧪 SIMULATION" : "💸 LIVE"}
                  </Badge>
                </div>
              </div>
            </div>

            {/* Right: Controls */}
            <div className="flex items-center gap-2">
              {data.walletAddress && (
                <a
                  href={`https://polymarket.com/profile/${data.walletAddress}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hidden sm:flex items-center gap-1.5 rounded-md border border-border/50 bg-card/30 px-2.5 py-1.5 font-mono text-xs text-muted-foreground hover:text-foreground hover:border-border transition-colors"
                >
                  <Wallet className="h-3 w-3" />
                  {data.walletAddress.slice(0, 6)}...{data.walletAddress.slice(-4)}
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
              
              <Button
                onClick={fetchDashboardData}
                disabled={loading}
                size="sm"
                variant="ghost"
                className="h-8 gap-1.5"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
                <span className="hidden sm:inline text-xs">Refresh</span>
              </Button>
              
              <Button 
                onClick={emergencyStop} 
                size="sm" 
                variant="destructive" 
                className="h-8 gap-1.5"
              >
                <AlertTriangle className="h-3.5 w-3.5" />
                <span className="hidden sm:inline text-xs">STOP ALL</span>
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Grid - Fills remaining height */}
      <div className="flex-1 grid grid-cols-[1fr_380px] min-h-0">
        {/* Left Panel - Dashboard with tabs */}
        <main className="overflow-y-auto">
          <div className="max-w-[1400px] p-4 md:p-6">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
          {/* Tab Navigation */}
          <TabsList className="bg-card/30 border border-border/30 p-1">
            <TabsTrigger value="overview" className="gap-2 data-[state=active]:bg-primary/20">
              <Gauge className="h-4 w-4" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="agents" className="gap-2 data-[state=active]:bg-primary/20">
              <Brain className="h-4 w-4" />
              Agents
            </TabsTrigger>
            <TabsTrigger value="positions" className="gap-2 data-[state=active]:bg-primary/20">
              <BarChart3 className="h-4 w-4" />
              Positions
            </TabsTrigger>
            <TabsTrigger value="settings" className="gap-2 data-[state=active]:bg-primary/20">
              <Settings className="h-4 w-4" />
              Settings
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-6">
            {/* Portfolio Stats Row */}
            <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
              <Card className="border-border/30 bg-gradient-to-br from-card/80 to-card/40 backdrop-blur">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Balance</p>
                      <p className="font-mono text-2xl font-bold mt-1">${data.balance.toFixed(2)}</p>
                    </div>
                    <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <DollarSign className="h-5 w-5 text-primary" />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/30 bg-gradient-to-br from-card/80 to-card/40 backdrop-blur">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Equity</p>
                      <p className="font-mono text-2xl font-bold mt-1">${data.equity.toFixed(2)}</p>
                    </div>
                    <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center">
                      <TrendingUp className="h-5 w-5 text-blue-400" />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/30 bg-gradient-to-br from-card/80 to-card/40 backdrop-blur">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Unrealized PnL</p>
                      <p className={`font-mono text-2xl font-bold mt-1 ${pnlIsPositive ? "text-emerald-400" : "text-red-400"}`}>
                        {pnlIsPositive ? "+" : ""}${data.unrealizedPnl.toFixed(2)}
                      </p>
                    </div>
                    <div className={`h-10 w-10 rounded-full flex items-center justify-center ${pnlIsPositive ? "bg-emerald-500/10" : "bg-red-500/10"}`}>
                      {pnlIsPositive ? (
                        <TrendingUp className="h-5 w-5 text-emerald-400" />
                      ) : (
                        <TrendingDown className="h-5 w-5 text-red-400" />
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className={`border-border/30 backdrop-blur ${data.riskStatus.safe ? "bg-gradient-to-br from-emerald-500/5 to-emerald-500/0" : "bg-gradient-to-br from-red-500/10 to-red-500/0"}`}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Risk Status</p>
                      <p className={`font-mono text-xl font-bold mt-1 ${data.riskStatus.safe ? "text-emerald-400" : "text-red-400"}`}>
                        {data.riskStatus.safe ? "SAFE" : "WARNING"}
                      </p>
                      <p className="font-mono text-[10px] text-muted-foreground mt-0.5">{data.riskStatus.message}</p>
                    </div>
                    <div className={`h-10 w-10 rounded-full flex items-center justify-center ${data.riskStatus.safe ? "bg-emerald-500/10" : "bg-red-500/10"}`}>
                      <Shield className={`h-5 w-5 ${data.riskStatus.safe ? "text-emerald-400" : "text-red-400"}`} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Agent Status Row */}
            <div className="grid gap-4 md:grid-cols-3">
              {[
                { key: "safe", name: "Safe Agent", data: data.agents.safe, theme: AGENT_THEMES.safe },
                { key: "scalper", name: "Scalper", data: data.agents.scalper, theme: AGENT_THEMES.scalper },
                { key: "copy", name: "Copy Trader", data: data.agents.copyTrader, theme: AGENT_THEMES.copy },
              ].map(({ key, name, data: agentData, theme }) => {
                const Icon = theme.icon
                const isRunning = agentData.running
                return (
                  <Card key={key} className={`border-border/30 ${theme.bg} transition-all hover:border-border/50`}>
                    <CardContent className="p-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <div className={`h-7 w-7 rounded-lg ${theme.bg} border ${theme.border} flex items-center justify-center`}>
                            <Icon className={`h-3.5 w-3.5 ${theme.text}`} />
                          </div>
                          <div>
                            <p className="font-mono text-xs font-semibold">{name}</p>
                            <p className="font-mono text-[9px] text-muted-foreground">
                              {theme.allocation}% · ${(data.balance * theme.allocation / 100).toFixed(2)}
                            </p>
                          </div>
                        </div>
                        <Switch 
                          checked={isRunning} 
                          onCheckedChange={() => toggleAgent(key as "safe" | "scalper" | "copyTrader")} 
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <Badge variant={isRunning ? "default" : "secondary"} className="text-[9px] h-5">
                          {isRunning ? "ACTIVE" : "PAUSED"}
                        </Badge>
                        <span className="font-mono text-[9px] text-muted-foreground truncate max-w-[120px]">
                          {'activity' in agentData ? agentData.activity : ('lastSignal' in agentData ? agentData.lastSignal : 'Idle')}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>

            {/* 24h Stats Mini */}
            <Card className="border-border/30 bg-card/30">
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono text-xs font-medium text-muted-foreground">24H ACTIVITY</span>
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <span className="font-mono text-[10px] text-muted-foreground">Trades</span>
                      <p className="font-mono text-sm font-bold">{data.stats.tradeCount}</p>
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-[10px] text-muted-foreground">Volume</span>
                      <p className="font-mono text-sm font-bold">${data.stats.volume24h.toFixed(2)}</p>
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-[10px] text-muted-foreground">Gas</span>
                      <p className="font-mono text-sm font-bold">{data.gasSpent.toFixed(4)} POL</p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Positions & Trades Row - Compact */}
            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="border-border/30 bg-card/30">
                <CardContent className="p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Target className="h-4 w-4 text-muted-foreground" />
                      <span className="font-mono text-xs font-medium">Open Positions</span>
                    </div>
                    <Badge variant="secondary" className="text-[9px] h-5">
                      {data.positions.length}
                    </Badge>
                  </div>
                  {data.positions.length === 0 ? (
                    <div className="flex items-center justify-center py-4 text-muted-foreground">
                      <p className="font-mono text-[10px]">No open positions</p>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {data.positions.slice(0, 4).map((pos, i) => (
                        <div key={`pos-${pos.market}-${i}`} className="flex items-center justify-between rounded border border-border/30 bg-background/50 px-2 py-1.5">
                          <p className="font-mono text-[10px] truncate max-w-[180px]">{pos.market}</p>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[10px]">${pos.value.toFixed(2)}</span>
                            <span className={`font-mono text-[10px] ${pos.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                              {pos.pnl >= 0 ? "+" : ""}{pos.pnl.toFixed(2)}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-border/30 bg-card/30">
                <CardContent className="p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      <span className="font-mono text-xs font-medium">Recent Trades</span>
                    </div>
                    <Badge variant="secondary" className="text-[9px] h-5">
                      {data.trades.length}
                    </Badge>
                  </div>
                  {data.trades.length === 0 ? (
                    <div className="flex items-center justify-center py-4 text-muted-foreground">
                      <p className="font-mono text-[10px]">No recent trades</p>
                    </div>
                  ) : (
                    <div className="space-y-1.5">
                      {data.trades.slice(0, 4).map((trade, i) => (
                        <div key={`trade-${trade.market}-${i}`} className="flex items-center justify-between rounded border border-border/30 bg-background/50 px-2 py-1.5">
                          <div className="flex-1 min-w-0">
                            <p className="font-mono text-[10px] truncate max-w-[180px]">{trade.market}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[10px]">${trade.amount.toFixed(2)}</span>
                            <Badge variant="outline" className="text-[8px] h-4 px-1">{trade.side}</Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Agents Tab */}
          <TabsContent value="agents" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3">
              {[
                { key: "safe", name: "Safe Agent", desc: "High-probability LLM-validated trades", data: data.agents.safe, theme: AGENT_THEMES.safe },
                { key: "scalper", name: "Crypto Scalper", desc: "15-min crypto volatility trading via RTDS", data: data.agents.scalper, theme: AGENT_THEMES.scalper },
                { key: "copy", name: "Copy Trader", desc: "Mirror top Polymarket performers", data: data.agents.copyTrader, theme: AGENT_THEMES.copy },
              ].map(({ key, name, desc, data: agentData, theme }) => {
                const Icon = theme.icon
                const isRunning = agentData.running
                return (
                  <Card key={key} className={`border-border/30 ${theme.bg}`}>
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className={`h-10 w-10 rounded-xl ${theme.bg} border ${theme.border} flex items-center justify-center`}>
                            <Icon className={`h-5 w-5 ${theme.text}`} />
                          </div>
                          <div>
                            <p className="font-mono text-sm font-semibold">{name}</p>
                            <p className="font-mono text-[10px] text-muted-foreground">{desc}</p>
                          </div>
                        </div>
                        <Switch 
                          checked={isRunning} 
                          onCheckedChange={() => toggleAgent(key as "safe" | "scalper" | "copyTrader")} 
                        />
                      </div>
                      
                      <div className="space-y-3">
                        <div>
                          <div className="flex justify-between text-[10px] mb-1">
                            <span className="font-mono text-muted-foreground">Capital Allocation</span>
                            <span className="font-mono font-semibold">{theme.allocation}% · ${(data.balance * theme.allocation / 100).toFixed(2)}</span>
                          </div>
                          <Progress value={theme.allocation} className="h-1.5" />
                        </div>
                        
                        <div className="flex items-center justify-between pt-2 border-t border-border/30">
                          <Badge variant={isRunning ? "default" : "secondary"} className="text-[9px]">
                            {isRunning ? "RUNNING" : "STOPPED"}
                          </Badge>
                          <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[150px]">
                            {'activity' in agentData ? agentData.activity : ('lastSignal' in agentData ? agentData.lastSignal : 'Idle')}
                          </span>
                        </div>
                        
                        {'endpoint' in agentData && (
                          <div className="pt-2 border-t border-border/30">
                            <span className="font-mono text-[9px] text-muted-foreground">Endpoint: </span>
                            <span className="font-mono text-[9px] text-foreground/70 truncate">{agentData.endpoint}</span>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          </TabsContent>

          {/* Positions Tab */}
          <TabsContent value="positions" className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <Card className="border-border/30 bg-card/30">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Target className="h-4 w-4 text-muted-foreground" />
                      <span className="font-mono text-xs font-medium">All Open Positions</span>
                    </div>
                    <Badge variant="secondary" className="text-[9px]">{data.positions.length}</Badge>
                  </div>
                  {data.positions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <Layers className="h-8 w-8 mb-2 opacity-30" />
                      <p className="font-mono text-xs">No open positions</p>
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                      {data.positions.map((pos, i) => (
                        <div key={`pos-full-${pos.market}-${i}`} className="flex items-center justify-between rounded border border-border/30 bg-background/50 p-2.5">
                          <div className="flex-1 min-w-0">
                            <p className="font-mono text-xs font-medium truncate">{pos.market}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                              <Badge variant="outline" className="text-[9px] h-4">{pos.side}</Badge>
                              <span className="font-mono text-[9px] text-muted-foreground">
                                Cost: ${pos.cost.toFixed(2)}
                              </span>
                            </div>
                          </div>
                          <div className="text-right ml-3">
                            <p className="font-mono text-xs font-semibold">${pos.value.toFixed(2)}</p>
                            <p className={`font-mono text-[10px] ${pos.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                              {pos.pnl >= 0 ? "+" : ""}{((pos.pnl / pos.cost) * 100).toFixed(1)}%
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-border/30 bg-card/30">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      <span className="font-mono text-xs font-medium">Trade History</span>
                    </div>
                    <Badge variant="secondary" className="text-[9px]">{data.trades.length}</Badge>
                  </div>
                  {data.trades.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <BarChart3 className="h-8 w-8 mb-2 opacity-30" />
                      <p className="font-mono text-xs">No trade history</p>
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                      {data.trades.map((trade, i) => (
                        <div key={`trade-full-${trade.market}-${i}`} className="flex items-center justify-between rounded border border-border/30 bg-background/50 p-2.5">
                          <div className="flex-1 min-w-0">
                            <p className="font-mono text-xs font-medium truncate">{trade.market}</p>
                            <p className="font-mono text-[9px] text-muted-foreground mt-0.5">{trade.time}</p>
                          </div>
                          <div className="text-right ml-3">
                            <p className="font-mono text-xs font-semibold">${trade.amount.toFixed(2)}</p>
                            <Badge variant="outline" className="text-[9px] h-4">{trade.side}</Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Settings Tab */}
          <TabsContent value="settings" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Card className="border-border/30 bg-card/30">
                <CardContent className="p-4 space-y-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Settings className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono text-xs font-medium">Trading Configuration</span>
                  </div>
                  
                  {/* Max Bet */}
                  <div className="space-y-1.5">
                    <span className="font-mono text-[10px] text-muted-foreground">Maximum Bet Size (USDC)</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.1"
                        min="0.1"
                        className="flex-1 h-8 rounded-md border border-border/50 bg-background px-2.5 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary/50"
                        value={maxBet}
                        onChange={(e) => setMaxBet(parseFloat(e.target.value) || 0)}
                      />
                      <Button 
                        onClick={updateMaxBet} 
                        disabled={updatingConfig}
                        size="sm"
                        className="h-8"
                      >
                        {updatingConfig ? "..." : "Update"}
                      </Button>
                    </div>
                  </div>

                  <Separator />

                  {/* Trading Mode */}
                  <div className="flex items-center justify-between rounded border border-border/50 bg-background p-3">
                    <div>
                      <p className="font-mono text-xs font-semibold">
                        {data.dryRun ? "🧪 Simulation" : "💸 Live"}
                      </p>
                      <p className="font-mono text-[9px] text-muted-foreground mt-0.5">
                        {data.dryRun ? "No real money at risk" : "Real trades on Polymarket"}
                      </p>
                    </div>
                    <Switch 
                      checked={!data.dryRun} 
                      onCheckedChange={toggleDryRun}
                    />
                  </div>

                  <Separator />

                  {/* Emergency Stop */}
                  <Button 
                    onClick={emergencyStop} 
                    variant="destructive" 
                    className="w-full h-10 gap-2"
                  >
                    <AlertTriangle className="h-4 w-4" />
                    EMERGENCY STOP
                  </Button>
                </CardContent>
              </Card>

              <Card className="border-border/30 bg-card/30">
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-center gap-2 mb-2">
                    <PieChart className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono text-xs font-medium">Capital Allocation</span>
                  </div>
                  
                  {[
                    { name: "Safe Agent", pct: 50, theme: AGENT_THEMES.safe },
                    { name: "Scalper", pct: 30, theme: AGENT_THEMES.scalper },
                    { name: "Copy Trader", pct: 20, theme: AGENT_THEMES.copy },
                  ].map(({ name, pct, theme }) => (
                    <div key={name} className="space-y-1">
                      <div className="flex justify-between">
                        <span className="font-mono text-[10px]">{name}</span>
                        <span className="font-mono text-[10px] font-semibold">{pct}% · ${(data.balance * pct / 100).toFixed(2)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-background overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${theme.text.replace('text-', 'bg-')}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  ))}
                  
                  <Separator className="my-2" />
                  
                  <div className="rounded border border-border/30 bg-background/50 p-3">
                    <p className="font-mono text-[10px] text-muted-foreground">Total Balance</p>
                    <p className="font-mono text-xl font-bold">${data.balance.toFixed(2)}</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
            </Tabs>
          </div>
        </main>

        {/* Right Panel - LLM Terminal */}
        <aside className="border-l border-border/30 flex flex-col min-h-0">
          <LLMTerminal />
        </aside>
      </div>
    </div>
  )
}
