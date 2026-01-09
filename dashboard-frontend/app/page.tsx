"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { 
  RefreshCw, AlertTriangle, TrendingUp, TrendingDown, DollarSign, 
  Activity, Zap, Wallet, ExternalLink, Brain, Shield, Gauge,
  BarChart3, Clock, Target, Users, Layers, Settings, PieChart
} from "lucide-react"
import { LLMActivityFeed } from "@/components/llm-activity-feed"
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
      <div className="flex min-h-screen items-center justify-center bg-[#0a0a0f]">
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
  const totalAllocation = data.balance
  const activeAgentCount = [data.agents.safe.running, data.agents.scalper.running, data.agents.copyTrader.running].filter(Boolean).length

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-foreground">
      {/* Top Status Bar */}
      <div className="border-b border-border/30 bg-[#0a0a0f]/80 backdrop-blur-xl sticky top-0 z-50">
        <div className="mx-auto max-w-[1800px] px-4 py-3">
          <div className="flex items-center justify-between">
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

      {/* Main Content */}
      <div className="mx-auto max-w-[1800px] p-4 md:p-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
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

            {/* Two Column Layout */}
            <div className="grid gap-6 lg:grid-cols-3">
              {/* Left Column - Agents Overview */}
              <div className="lg:col-span-1 space-y-4">
                <h2 className="font-mono text-sm font-semibold text-muted-foreground flex items-center gap-2">
                  <Brain className="h-4 w-4" />
                  AGENT STATUS
                </h2>
                
                {/* Agent Cards */}
                {[
                  { key: "safe", name: "Safe Agent", data: data.agents.safe, theme: AGENT_THEMES.safe },
                  { key: "scalper", name: "Scalper", data: data.agents.scalper, theme: AGENT_THEMES.scalper },
                  { key: "copy", name: "Copy Trader", data: data.agents.copyTrader, theme: AGENT_THEMES.copy },
                ].map(({ key, name, data: agentData, theme }) => {
                  const Icon = theme.icon
                  const isRunning = agentData.running
                  return (
                    <Card key={key} className={`border-border/30 ${theme.bg} transition-all hover:border-border/50`}>
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <div className={`h-8 w-8 rounded-lg ${theme.bg} border ${theme.border} flex items-center justify-center`}>
                              <Icon className={`h-4 w-4 ${theme.text}`} />
                            </div>
                            <div>
                              <p className="font-mono text-sm font-semibold">{name}</p>
                              <p className="font-mono text-[10px] text-muted-foreground">
                                {theme.allocation}% allocation
                              </p>
                            </div>
                          </div>
                          <Switch 
                            checked={isRunning} 
                            onCheckedChange={() => toggleAgent(key as "safe" | "scalper" | "copyTrader")} 
                          />
                        </div>
                        
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[10px] text-muted-foreground">Status</span>
                            <Badge variant={isRunning ? "default" : "secondary"} className="text-[10px]">
                              {isRunning ? "ACTIVE" : "PAUSED"}
                            </Badge>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-[10px] text-muted-foreground">Capital</span>
                            <span className="font-mono text-xs font-semibold">
                              ${(data.balance * theme.allocation / 100).toFixed(2)}
                            </span>
                          </div>
                          <div>
                            <span className="font-mono text-[10px] text-muted-foreground">Activity</span>
                            <p className="font-mono text-[11px] text-foreground/80 truncate mt-0.5">
                              {'activity' in agentData ? agentData.activity : ('lastSignal' in agentData ? agentData.lastSignal : 'Idle')}
                            </p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}

                {/* 24h Stats */}
                <Card className="border-border/30 bg-card/30">
                  <CardHeader className="pb-2">
                    <CardTitle className="font-mono text-xs font-medium flex items-center gap-2">
                      <Activity className="h-4 w-4" />
                      24H ACTIVITY
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-muted-foreground">Trades</span>
                      <span className="font-mono text-lg font-bold">{data.stats.tradeCount}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-muted-foreground">Volume</span>
                      <span className="font-mono text-lg font-bold">${data.stats.volume24h.toFixed(2)}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-muted-foreground">Gas Used</span>
                      <span className="font-mono text-sm">{data.gasSpent.toFixed(4)} POL</span>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Right Column - LLM Activity */}
              <div className="lg:col-span-2">
                <LLMActivityFeed />
              </div>
            </div>

            {/* Positions & Trades Row */}
            <div className="grid gap-6 lg:grid-cols-2">
              <Card className="border-border/30 bg-card/30">
                <CardHeader>
                  <CardTitle className="font-mono text-sm font-semibold flex items-center gap-2">
                    <Target className="h-4 w-4" />
                    Open Positions
                  </CardTitle>
                  <CardDescription className="font-mono text-xs">
                    {data.positions.length} active position{data.positions.length !== 1 ? "s" : ""}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {data.positions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <Layers className="h-8 w-8 mb-2 opacity-30" />
                      <p className="font-mono text-xs">No open positions</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {data.positions.slice(0, 5).map((pos, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg border border-border/30 bg-background/50 p-3">
                          <div className="flex-1 min-w-0">
                            <p className="font-mono text-xs font-medium truncate">{pos.market}</p>
                            <p className="font-mono text-[10px] text-muted-foreground">{pos.side}</p>
                          </div>
                          <div className="text-right ml-4">
                            <p className="font-mono text-xs font-medium">${pos.value.toFixed(2)}</p>
                            <p className={`font-mono text-[10px] ${pos.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                              {pos.pnl >= 0 ? "+" : ""}${pos.pnl.toFixed(2)}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-border/30 bg-card/30">
                <CardHeader>
                  <CardTitle className="font-mono text-sm font-semibold flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Recent Trades
                  </CardTitle>
                  <CardDescription className="font-mono text-xs">
                    Last {data.trades.length} trades
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {data.trades.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                      <BarChart3 className="h-8 w-8 mb-2 opacity-30" />
                      <p className="font-mono text-xs">No recent trades</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {data.trades.slice(0, 5).map((trade, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg border border-border/30 bg-background/50 p-3">
                          <div className="flex-1 min-w-0">
                            <p className="font-mono text-xs font-medium truncate">{trade.market}</p>
                            <p className="font-mono text-[10px] text-muted-foreground">{trade.time}</p>
                          </div>
                          <div className="text-right ml-4">
                            <p className="font-mono text-xs font-medium">${trade.amount.toFixed(2)}</p>
                            <p className="font-mono text-[10px] text-muted-foreground">{trade.side}</p>
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
          <TabsContent value="agents" className="space-y-6">
            <div className="grid gap-6 md:grid-cols-3">
              {[
                { key: "safe", name: "Safe Agent", desc: "High-probability LLM-validated trades", data: data.agents.safe, theme: AGENT_THEMES.safe },
                { key: "scalper", name: "Crypto Scalper", desc: "15-min crypto volatility trading via RTDS", data: data.agents.scalper, theme: AGENT_THEMES.scalper },
                { key: "copy", name: "Copy Trader", desc: "Mirror top Polymarket performers", data: data.agents.copyTrader, theme: AGENT_THEMES.copy },
              ].map(({ key, name, desc, data: agentData, theme }) => {
                const Icon = theme.icon
                const isRunning = agentData.running
                return (
                  <Card key={key} className={`border-border/30 ${theme.bg}`}>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <div className={`h-12 w-12 rounded-xl ${theme.bg} border ${theme.border} flex items-center justify-center`}>
                          <Icon className={`h-6 w-6 ${theme.text}`} />
                        </div>
                        <Switch 
                          checked={isRunning} 
                          onCheckedChange={() => toggleAgent(key as "safe" | "scalper" | "copyTrader")} 
                        />
                      </div>
                      <CardTitle className="font-mono text-base mt-4">{name}</CardTitle>
                      <CardDescription className="font-mono text-xs">{desc}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="font-mono text-muted-foreground">Capital Allocation</span>
                          <span className="font-mono font-semibold">{theme.allocation}%</span>
                        </div>
                        <Progress value={theme.allocation} className="h-2" />
                        <p className="font-mono text-xs text-right text-muted-foreground">
                          ${(data.balance * theme.allocation / 100).toFixed(2)} USDC
                        </p>
                      </div>
                      
                      <Separator />
                      
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs text-muted-foreground">Status</span>
                          <Badge variant={isRunning ? "default" : "secondary"}>
                            {isRunning ? "RUNNING" : "STOPPED"}
                          </Badge>
                        </div>
                        <div>
                          <span className="font-mono text-[10px] text-muted-foreground">Last Activity</span>
                          <p className="font-mono text-xs mt-1">
                            {'activity' in agentData ? agentData.activity : ('lastSignal' in agentData ? agentData.lastSignal : 'Idle')}
                          </p>
                        </div>
                        {'endpoint' in agentData && (
                          <div>
                            <span className="font-mono text-[10px] text-muted-foreground">API Endpoint</span>
                            <p className="font-mono text-xs mt-1 truncate">{agentData.endpoint}</p>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
            
            {/* Full LLM Activity on Agents Tab */}
            <LLMActivityFeed />
          </TabsContent>

          {/* Positions Tab */}
          <TabsContent value="positions" className="space-y-6">
            <div className="grid gap-6 lg:grid-cols-2">
              <Card className="border-border/30 bg-card/30">
                <CardHeader>
                  <CardTitle className="font-mono text-sm flex items-center gap-2">
                    <Target className="h-4 w-4" />
                    All Open Positions
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {data.positions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                      <Layers className="h-12 w-12 mb-3 opacity-30" />
                      <p className="font-mono text-sm">No open positions</p>
                      <p className="font-mono text-xs text-muted-foreground/70 mt-1">Positions will appear when agents open trades</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {data.positions.map((pos, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg border border-border/30 bg-background/50 p-4">
                          <div className="flex-1 min-w-0">
                            <p className="font-mono text-sm font-medium">{pos.market}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <Badge variant="outline" className="text-[10px]">{pos.side}</Badge>
                              <span className="font-mono text-[10px] text-muted-foreground">
                                Cost: ${pos.cost.toFixed(2)}
                              </span>
                            </div>
                          </div>
                          <div className="text-right ml-4">
                            <p className="font-mono text-sm font-semibold">${pos.value.toFixed(2)}</p>
                            <p className={`font-mono text-xs ${pos.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
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
                <CardHeader>
                  <CardTitle className="font-mono text-sm flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Trade History
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {data.trades.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                      <BarChart3 className="h-12 w-12 mb-3 opacity-30" />
                      <p className="font-mono text-sm">No trade history</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {data.trades.map((trade, i) => (
                        <div key={i} className="flex items-center justify-between rounded-lg border border-border/30 bg-background/50 p-4">
                          <div className="flex-1 min-w-0">
                            <p className="font-mono text-sm font-medium">{trade.market}</p>
                            <p className="font-mono text-[10px] text-muted-foreground mt-1">{trade.time}</p>
                          </div>
                          <div className="text-right ml-4">
                            <p className="font-mono text-sm font-semibold">${trade.amount.toFixed(2)}</p>
                            <Badge variant="outline" className="text-[10px]">{trade.side}</Badge>
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
          <TabsContent value="settings" className="space-y-6">
            <div className="grid gap-6 md:grid-cols-2">
              <Card className="border-border/30 bg-card/30">
                <CardHeader>
                  <CardTitle className="font-mono text-sm flex items-center gap-2">
                    <Settings className="h-4 w-4" />
                    Trading Configuration
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Max Bet */}
                  <div className="space-y-2">
                    <label className="font-mono text-xs text-muted-foreground">Maximum Bet Size (USDC)</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.1"
                        min="0.1"
                        className="flex-1 h-10 rounded-md border border-border/50 bg-background px-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                        value={maxBet}
                        onChange={(e) => setMaxBet(parseFloat(e.target.value) || 0)}
                      />
                      <Button 
                        onClick={updateMaxBet} 
                        disabled={updatingConfig}
                        className="h-10"
                      >
                        {updatingConfig ? "Saving..." : "Update"}
                      </Button>
                    </div>
                    <p className="font-mono text-[10px] text-muted-foreground">
                      Controls the maximum bet size per trade for all agents
                    </p>
                  </div>

                  <Separator />

                  {/* Trading Mode */}
                  <div className="space-y-2">
                    <label className="font-mono text-xs text-muted-foreground">Trading Mode</label>
                    <div className="flex items-center justify-between rounded-lg border border-border/50 bg-background p-4">
                      <div>
                        <p className="font-mono text-sm font-semibold">
                          {data.dryRun ? "🧪 Simulation Mode" : "💸 Live Trading"}
                        </p>
                        <p className="font-mono text-[10px] text-muted-foreground mt-1">
                          {data.dryRun 
                            ? "Trades are simulated, no real money at risk" 
                            : "Real trades will be executed on Polymarket"}
                        </p>
                      </div>
                      <Switch 
                        checked={!data.dryRun} 
                        onCheckedChange={toggleDryRun}
                      />
                    </div>
                  </div>

                  <Separator />

                  {/* Emergency Stop */}
                  <div className="space-y-2">
                    <label className="font-mono text-xs text-muted-foreground">Emergency Controls</label>
                    <Button 
                      onClick={emergencyStop} 
                      variant="destructive" 
                      className="w-full h-12 gap-2"
                    >
                      <AlertTriangle className="h-5 w-5" />
                      EMERGENCY STOP ALL AGENTS
                    </Button>
                    <p className="font-mono text-[10px] text-muted-foreground text-center">
                      Immediately stops all trading activity
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border/30 bg-card/30">
                <CardHeader>
                  <CardTitle className="font-mono text-sm flex items-center gap-2">
                    <PieChart className="h-4 w-4" />
                    Capital Allocation
                  </CardTitle>
                  <CardDescription className="font-mono text-xs">
                    How your capital is distributed across agents
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {[
                    { name: "Safe Agent", pct: 50, theme: AGENT_THEMES.safe },
                    { name: "Scalper", pct: 30, theme: AGENT_THEMES.scalper },
                    { name: "Copy Trader", pct: 20, theme: AGENT_THEMES.copy },
                  ].map(({ name, pct, theme }) => (
                    <div key={name} className="space-y-2">
                      <div className="flex justify-between">
                        <span className="font-mono text-xs">{name}</span>
                        <span className="font-mono text-xs font-semibold">{pct}% (${(data.balance * pct / 100).toFixed(2)})</span>
                      </div>
                      <div className="h-3 rounded-full bg-background overflow-hidden">
                        <div 
                          className={`h-full rounded-full ${theme.text.replace('text-', 'bg-')}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  ))}
                  
                  <Separator className="my-4" />
                  
                  <div className="rounded-lg border border-border/30 bg-background/50 p-4">
                    <p className="font-mono text-xs text-muted-foreground mb-2">Total Balance</p>
                    <p className="font-mono text-2xl font-bold">${data.balance.toFixed(2)}</p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
