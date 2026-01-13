"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  TrendingUp, TrendingDown, DollarSign,
  Activity, Zap, Wallet, ExternalLink, Brain, Shield,
  BarChart3, Settings, PieChart,
  X, XCircle, Loader2, Gamepad2, Users, LayoutDashboard, Terminal,
  ChevronRight, AlertTriangle, Monitor
} from "lucide-react"
import { LLMTerminal } from "@/components/llm-terminal"
import { FBPChat } from "@/components/fbp-chat"
import { ThemeToggle } from "@/components/theme-toggle"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { PerformanceGraph } from "@/components/performance-graph"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

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
    smartTrader: { running: boolean; activity: string; positions: number; trades: number; mode: string; lastScan: string }
    esportsTrader: { running: boolean; activity: string; trades: number; mode: string; lastScan: string; pnl: number }
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
  safe: { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-400", icon: Shield, allocation: 20 },
  scalper: { bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-400", icon: Zap, allocation: 10 },
  copy: { bg: "bg-violet-500/10", border: "border-violet-500/30", text: "text-violet-400", icon: Users, allocation: 15 },
  smart: { bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-400", icon: Brain, allocation: 25 },
  esports: { bg: "bg-pink-500/10", border: "border-pink-500/30", text: "text-pink-400", icon: Gamepad2, allocation: 30 },
}

export default function PolymarketDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [activeView, setActiveView] = useState("overview")
  const [maxBet, setMaxBet] = useState(0.50)
  const [updatingConfig, setUpdatingConfig] = useState(false)
  const [closingPosition, setClosingPosition] = useState<string | null>(null)

  // Mobile specific state
  const [mobileTab, setMobileTab] = useState("overview") // overview, agents, positions, intel, settings

  const fetchDashboardData = async () => {
    setLoading(true)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
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

  const toggleAgent = async (agent: string) => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
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
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    await fetch(`${apiUrl}/api/emergency-stop`, { method: "POST" })
    fetchDashboardData()
  }

  const updateMaxBet = async () => {
    setUpdatingConfig(true)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      await fetch(`${apiUrl}/api/update-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "max_bet", value: Number(maxBet) }),
      })
      fetchDashboardData()
    } finally {
      setUpdatingConfig(false)
    }
  }

  const closePosition = async (tokenId: string, size: number) => {
    // Logic for closePosition - existing logic
    setClosingPosition(tokenId)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      await fetch(`${apiUrl}/api/close-position`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token_id: tokenId, size }),
      })
      fetchDashboardData()
    } finally {
      setClosingPosition(null)
    }
  }

  useEffect(() => {
    fetchDashboardData()
    const interval = setInterval(fetchDashboardData, 10000)
    return () => clearInterval(interval)
  }, [])

  // Sync mobile tab to active view (except intel)
  useEffect(() => {
    if (activeView !== 'intel') {
      setMobileTab(activeView)
    }
  }, [activeView])

  if (!data) return <div className="flex h-screen items-center justify-center bg-background"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>

  const pnlIsPositive = data.unrealizedPnl >= 0
  const activeCount = [data.agents.safe, data.agents.scalper, data.agents.copyTrader, data.agents.smartTrader, data.agents.esportsTrader].filter(a => a?.running).length

  // Decide what to show based on screen size and active tabs
  // Desktop: Sidebar + Main + Intel Panel
  // Mobile: Bottom Bar + Main Content Area (which swaps between views)

  return (
    <div className="flex flex-col lg:flex-row min-h-screen w-full bg-background font-mono text-sm selection:bg-primary/20 pb-16 lg:pb-0 lg:h-screen lg:overflow-hidden">

      {/* 1. Desktop Sidebar Navigation (Hidden on Mobile) */}
      <nav className="hidden lg:flex w-[60px] border-r border-border/40 bg-card/20 flex-col items-center py-6 gap-6 z-20 h-full">
        <div className="h-10 w-10 rounded-xl bg-primary/20 flex items-center justify-center mb-4">
          <Brain className="h-6 w-6 text-primary" />
        </div>

        {['overview', 'agents', 'positions', 'settings'].map((view) => (
          <button
            key={view}
            onClick={() => setActiveView(view)}
            className={`p-3 rounded-xl transition-all ${activeView === view ? 'bg-primary/20 text-primary shadow-glow' : 'text-muted-foreground hover:bg-white/5'}`}
            title={view.charAt(0).toUpperCase() + view.slice(1)}
          >
            {view === 'overview' && <LayoutDashboard className="h-5 w-5" />}
            {view === 'agents' && <Users className="h-5 w-5" />}
            {view === 'positions' && <BarChart3 className="h-5 w-5" />}
            {view === 'settings' && <Settings className="h-5 w-5" />}
          </button>
        ))}

        <div className="mt-auto flex flex-col gap-4">
          <ThemeToggle />
          <div className={`h-2 w-2 rounded-full ${data.riskStatus.safe ? "bg-emerald-500" : "bg-red-500"}`} title={data.riskStatus.message} />
        </div>
      </nav>

      {/* 2. Main Stage (Mission Control) */}
      {/* Hide on mobile if "intel" tab is selected */}
      <main className={`flex-1 flex flex-col min-w-0 p-4 lg:p-6 gap-4 lg:gap-6 relative ${mobileTab === 'intel' ? 'hidden lg:flex' : 'flex'}`}>

        {/* Header */}
        <header className="flex flex-wrap items-center justify-between shrink-0 gap-4">
          <div>
            <h1 className="text-lg lg:text-xl font-bold tracking-tight flex items-center gap-2">
              <span className="lg:hidden h-8 w-8 rounded-lg bg-primary/20 flex items-center justify-center"><Brain className="h-4 w-4 text-primary" /></span>
              MISSION CONTROL
            </h1>
            <p className="text-[10px] lg:text-xs text-muted-foreground flex items-center gap-2 mt-1">
              <span className={`w-2 h-2 rounded-full ${data.dryRun ? 'bg-amber-500' : 'bg-emerald-500'}`} />
              {data.dryRun ? 'SIM' : 'LIVE'}
              <span className="text-border/60">|</span>
              {new Date(data.lastUpdate).toLocaleTimeString()}
            </p>
          </div>

          <div className="flex items-center gap-2 lg:gap-3">
            <div className="hidden lg:block"><ThemeToggle /></div>
            <Button variant="outline" size="sm" onClick={emergencyStop} className="border-red-500/30 hover:bg-red-500/10 hover:text-red-400 text-red-500 h-8 text-xs gap-2">
              <AlertTriangle className="h-3 w-3" /> <span className="hidden sm:inline">STOP ALL</span>
            </Button>
            {data.walletAddress && (
              <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border/40 bg-card/40 text-xs text-muted-foreground">
                <Wallet className="h-3 w-3" />
                {data.walletAddress.slice(0, 6)}...
              </div>
            )}
          </div>
        </header>

        {/* Dynamic View Content */}
        <div className="flex-1 flex flex-col gap-4 lg:gap-6 min-h-0 lg:overflow-y-auto lg:pr-2 lg:pb-2">

          {/* KPI Row - Responsive Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 lg:gap-6 shrink-0">
            <Card className="glass flex items-center px-4 py-3 lg:px-6 lg:gap-4 gap-3 border-border/40">
              <div className="h-10 w-10 shrink-0 rounded-full bg-primary/10 flex items-center justify-center"><DollarSign className="h-5 w-5 text-primary" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Balance</p>
                <p className="text-xl lg:text-2xl font-bold">${data.balance.toFixed(2)}</p>
              </div>
            </Card>
            <Card className="glass flex items-center px-4 py-3 lg:px-6 lg:gap-4 gap-3 border-border/40">
              <div className="h-10 w-10 shrink-0 rounded-full bg-blue-500/10 flex items-center justify-center"><TrendingUp className="h-5 w-5 text-blue-400" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Equity</p>
                <p className="text-xl lg:text-2xl font-bold">${data.equity.toFixed(2)}</p>
              </div>
            </Card>
            <Card className="glass flex items-center px-4 py-3 lg:px-6 lg:gap-4 gap-3 border-border/40">
              <div className={`h-10 w-10 shrink-0 rounded-full flex items-center justify-center ${pnlIsPositive ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
                {pnlIsPositive ? <TrendingUp className="h-5 w-5 text-emerald-400" /> : <TrendingDown className="h-5 w-5 text-red-400" />}
              </div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-widest">Unrealized PnL</p>
                <p className={`text-xl lg:text-2xl font-bold ${pnlIsPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {pnlIsPositive ? '+' : ''}{data.unrealizedPnl.toFixed(2)}
                </p>
              </div>
            </Card>
          </div>

          {/* Graph Section */}
          {(activeView === 'overview') && (
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 lg:gap-6 min-h-[300px]">
              <div className="lg:col-span-3 h-[250px] lg:h-full">
                <PerformanceGraph />
              </div>
              <div className="flex flex-col gap-4">
                <Card className="flex-1 glass border-border/40 p-4">
                  <h3 className="text-xs font-semibold mb-4 flex items-center gap-2"><Activity className="h-4 w-4" /> Market Activity</h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-muted-foreground">Active Agents</span>
                      <span className="font-bold">{activeCount}/5</span>
                    </div>
                    <Progress value={(activeCount / 5) * 100} className="h-1.5" />
                    <div className="flex justify-between items-center text-xs pt-2">
                      <span className="text-muted-foreground">Volume (24h)</span>
                      <span className="font-bold">${data.stats.volume24h.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-muted-foreground">Trades</span>
                      <span className="font-bold">{data.stats.tradeCount}</span>
                    </div>
                  </div>
                </Card>
              </div>
            </div>
          )}

          {/* Agents Grid (Responsive) */}
          {(activeView === 'overview' || activeView === 'agents') && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 shrink-0">
              {Object.entries(data.agents).map(([key, agent]: [string, any]) => {
                const theme = AGENT_THEMES[key as keyof typeof AGENT_THEMES] || AGENT_THEMES.safe
                const Icon = theme.icon
                // Don't show stopped agents on mobile overview to save space, unless in agents tab
                if (activeView === 'overview' && !agent.running && 'ontouchstart' in window) return null; // Simple mobile check

                return (
                  <Card key={key} className={`border-border/40 ${agent.running ? theme.bg : 'bg-card/20'} glass transition-all hover:scale-[1.02]`}>
                    <CardContent className="p-3">
                      <div className="flex justify-between items-start mb-2">
                        <Icon className={`h-4 w-4 ${theme.text}`} />
                        <Switch checked={agent.running} onCheckedChange={() => toggleAgent(key)} className="scale-75 origin-top-right" />
                      </div>
                      <p className="font-semibold text-xs mb-0.5 capitalize">{key.replace('Trader', '')}</p>
                      <div className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${agent.running ? 'bg-emerald-500 animate-pulse' : 'bg-muted'}`} />
                        <p className="text-[9px] text-muted-foreground truncate opacity-70">{agent.lastSignal || agent.activity || 'Idle'}</p>
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}

          {/* Positions Table (Minified) */}
          {(activeView === 'overview' || activeView === 'positions') && (
            <Card className="flex-1 min-h-[200px] border-border/40 glass">
              <CardHeader className="py-3 px-4 border-b border-border/40 flex flex-row items-center justify-between">
                <CardTitle className="text-xs flex items-center gap-2"><BarChart3 className="h-3.5 w-3.5" /> Active Positions ({data.positions.length})</CardTitle>
              </CardHeader>
              <CardContent className="p-0 overflow-auto max-h-[400px]">
                {data.positions.length === 0 ? (
                  <div className="p-8 text-center text-xs text-muted-foreground">No open positions</div>
                ) : (
                  <table className="w-full text-left">
                    <thead className="bg-muted/30 text-[10px] uppercase text-muted-foreground sticky top-0 backdrop-blur-md">
                      <tr>
                        <th className="px-4 py-2 font-medium">Market</th>
                        <th className="px-4 py-2 font-medium text-right hidden sm:table-cell">Value</th>
                        <th className="px-4 py-2 font-medium text-right">PnL</th>
                        <th className="px-4 py-2 font-medium w-[40px]"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {data.positions.map((pos, i) => (
                        <tr key={i} className="hover:bg-muted/20 text-xs group">
                          <td className="px-4 py-2 truncate max-w-[150px] sm:max-w-[250px]">
                            {pos.market}
                            <div className="sm:hidden text-[9px] text-muted-foreground pt-0.5">${pos.value.toFixed(2)}</div>
                          </td>
                          <td className="px-4 py-2 text-right text-muted-foreground hidden sm:table-cell">${pos.value.toFixed(2)}</td>
                          <td className={`px-4 py-2 text-right ${(pos.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {(pos.pnl || 0) >= 0 ? '+' : ''}{pos.pnl.toFixed(2)}
                          </td>
                          <td className="px-4 py-2 text-right">
                            {pos.value > 0 && <button className="opacity-100 lg:opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 text-red-400 rounded transition-all" onClick={() => closePosition(pos.market, 1)}><X className="h-3 w-3" /></button>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          )}

          {/* Settings View */}
          {activeView === 'settings' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="glass border-border/40">
                <CardHeader><CardTitle className="text-sm">Risk Configuration</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <label className="text-xs text-muted-foreground">Max Bet Amount (USDC)</label>
                    <div className="flex gap-2">
                      <Input
                        type="number"
                        step="0.1"
                        value={maxBet}
                        onChange={(e) => setMaxBet(parseFloat(e.target.value))}
                        className="h-8 text-xs font-mono"
                      />
                      <Button size="sm" onClick={updateMaxBet} disabled={updatingConfig}>
                        {updatingConfig ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </main>

      {/* 3. Right Intelligence Panel (Desktop) / Mobile Tab Content */}
      <aside className={`w-full lg:w-[380px] border-l border-border/40 bg-card/20 flex flex-col z-10 ${mobileTab === 'intel' ? 'flex flex-1' : 'hidden lg:flex'}`}>
        <Tabs defaultValue="terminal" className="flex-1 flex flex-col min-h-0">
          <TabsList className="w-full justify-start rounded-none border-b border-border/40 bg-transparent p-0 h-10">
            <TabsTrigger value="terminal" className="flex-1 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/10">
              <Terminal className="mr-2 h-4 w-4" /> Network
            </TabsTrigger>
            <TabsTrigger value="chat" className="flex-1 rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-muted/10">
              <Brain className="mr-2 h-4 w-4" /> Agent
            </TabsTrigger>
          </TabsList>
          <div className="flex-1 overflow-hidden relative">
            <TabsContent value="terminal" className="h-full mt-0 absolute inset-0">
              <LLMTerminal />
            </TabsContent>
            <TabsContent value="chat" className="h-full mt-0 absolute inset-0">
              <FBPChat />
            </TabsContent>
          </div>
        </Tabs>
      </aside>

      {/* 4. Mobile Bottom Navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 h-16 bg-background/90 backdrop-blur-lg border-t border-border/40 flex items-center justify-around px-2 z-50">
        {[
          { id: 'overview', icon: LayoutDashboard, label: 'Home' },
          { id: 'agents', icon: Users, label: 'Agents' },
          { id: 'positions', icon: BarChart3, label: 'Pos' },
          { id: 'intel', icon: Terminal, label: 'Intel' },
          { id: 'settings', icon: Settings, label: 'Config' },
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => { setActiveView(item.id); setMobileTab(item.id); }}
            className={`flex flex-col items-center gap-1 p-2 rounded-lg transition-colors ${mobileTab === item.id ? 'text-primary' : 'text-muted-foreground'}`}
          >
            <item.icon className="h-5 w-5" />
            <span className="text-[10px] font-medium">{item.label}</span>
          </button>
        ))}
      </nav>

    </div>
  )
}
