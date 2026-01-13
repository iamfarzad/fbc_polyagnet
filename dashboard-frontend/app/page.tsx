"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import {
  TrendingUp, TrendingDown, DollarSign,
  Activity, Zap, Wallet, ExternalLink, Brain, Shield,
  BarChart3, Settings, PieChart,
  X, XCircle, Loader2, Gamepad2, Users, LayoutDashboard, Terminal,
  ChevronRight, AlertTriangle, Monitor, Trophy, Lock
} from "lucide-react"
import { LLMTerminal } from "@/components/llm-terminal"
import { FBPChat } from "@/components/fbp-chat"
import { ThemeToggle } from "@/components/theme-toggle"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

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
    sportsTrader: { running: boolean; activity: string; trades: number; mode: string; lastScan: string }
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
  safe: { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-400", icon: Shield, label: "Safety" },
  scalper: { bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-400", icon: Zap, label: "Scalper" },
  copy: { bg: "bg-violet-500/10", border: "border-violet-500/30", text: "text-violet-400", icon: Users, label: "Copy Trading" },
  smart: { bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-400", icon: Brain, label: "Smart (Politics)" },
  esports: { bg: "bg-pink-500/10", border: "border-pink-500/30", text: "text-pink-400", icon: Gamepad2, label: "eSports" },
  sports: { bg: "bg-orange-500/10", border: "border-orange-500/30", text: "text-orange-400", icon: Trophy, label: "Sports Trader" },
}

export default function ProDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [maxBet, setMaxBet] = useState(0.50)
  const [updatingConfig, setUpdatingConfig] = useState(false)

  const fetchDashboardData = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      const response = await fetch(`${apiUrl}/api/dashboard`)
      const json = await response.json()
      setData(json)
      if (json.maxBetAmount !== undefined && !updatingConfig) setMaxBet(json.maxBetAmount)
    } catch (error) {
      console.error("Failed to fetch dashboard data:", error)
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

  const toggleDryRun = async (current: boolean) => {
    setUpdatingConfig(true)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
      await fetch(`${apiUrl}/api/update-config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "dry_run", value: current ? 0 : 1 }), // Toggle inverted
      })
      fetchDashboardData()
    } finally {
      setUpdatingConfig(false)
    }
  }

  const emergencyStop = async () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    await fetch(`${apiUrl}/api/emergency-stop`, { method: "POST" })
    fetchDashboardData()
  }

  useEffect(() => {
    fetchDashboardData()
    const interval = setInterval(fetchDashboardData, 5000) // Fast refresh
    return () => clearInterval(interval)
  }, [])

  if (!data) return <div className="flex h-screen items-center justify-center bg-background"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>

  return (
    <div className="min-h-screen bg-background text-foreground font-mono text-xs flex flex-col">

      {/* 1. Header: Status & Global Controls */}
      <header className="border-b border-border/40 bg-card/20 backdrop-blur sticky top-0 z-50">
        <div className="container mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Brain className="h-5 w-5 text-primary" />
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm tracking-tight">POLYAGENT PRO</span>
              <Badge variant="outline" className="text-[10px] h-5">{data.walletAddress.slice(0, 6)}...</Badge>
            </div>
          </div>

          <div className="flex items-center gap-6">
            {/* Financial Summary (Compact) */}
            <div className="hidden md:flex gap-6 text-xs">
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

            <Separator orientation="vertical" className="h-6 hidden md:block" />

            {/* Global Toggles */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-bold ${data.dryRun ? 'text-amber-500' : 'text-muted-foreground'}`}>SIM</span>
                <Switch
                  checked={!data.dryRun}
                  onCheckedChange={() => toggleDryRun(data.dryRun)}
                  className="data-[state=checked]:bg-emerald-500 data-[state=unchecked]:bg-amber-500 border-none h-5 w-9"
                />
                <span className={`text-[10px] font-bold ${!data.dryRun ? 'text-emerald-500' : 'text-muted-foreground'}`}>LIVE</span>
              </div>

              <Button variant="ghost" size="icon" onClick={emergencyStop} className="text-red-500 hover:text-red-600 hover:bg-red-500/10">
                <AlertTriangle className="h-4 w-4" />
              </Button>
              <ThemeToggle />
            </div>
          </div>
        </div>
      </header>

      {/* 2. Main Content Grid */}
      <main className="flex-1 container mx-auto px-4 py-4 grid grid-cols-1 lg:grid-cols-4 gap-4">

        {/* Left Column: Agents & Config (25%) */}
        <div className="lg:col-span-1 flex flex-col gap-4">
          <Card className="border-border/40 glass">
            <CardHeader className="py-3 px-4 border-b border-border/40"><CardTitle className="text-xs font-bold uppercase tracking-wider flex items-center gap-2"><Zap className="h-3.5 w-3.5" /> Active Agents</CardTitle></CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-border/20">
                {Object.entries(data.agents).map(([key, agent]: [string, any]) => {
                  const theme = AGENT_THEMES[key as keyof typeof AGENT_THEMES] || AGENT_THEMES.safe
                  const Icon = theme.icon
                  return (
                    <div key={key} className="p-3 flex items-center justify-between hover:bg-white/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className={`h-8 w-8 rounded-lg ${theme.bg} flex items-center justify-center`}>
                          <Icon className={`h-4 w-4 ${theme.text}`} />
                        </div>
                        <div>
                          <p className="font-bold text-xs capitalize">{theme.label}</p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <div className={`w-1.5 h-1.5 rounded-full ${agent.running ? 'bg-emerald-500 animate-pulse' : 'bg-muted'}`} />
                            <p className="text-[10px] text-muted-foreground truncate max-w-[100px]">{agent.activity || 'Idle'}</p>
                          </div>
                        </div>
                      </div>
                      <Switch checked={agent.running} onCheckedChange={() => toggleAgent(key)} className="scale-75" />
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          {/* Risk Config */}
          <Card className="border-border/40 glass">
            <CardHeader className="py-3 px-4 border-b border-border/40"><CardTitle className="text-xs font-bold uppercase tracking-wider flex items-center gap-2"><Lock className="h-3.5 w-3.5" /> Risk Controls</CardTitle></CardHeader>
            <CardContent className="p-4 space-y-4">
              <div>
                <label className="text-[10px] text-muted-foreground mb-1.5 block">MAX BET / POSITION (USDC)</label>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    value={maxBet}
                    onChange={(e) => setMaxBet(parseFloat(e.target.value))}
                    className="h-8 text-xs font-mono"
                  />
                  {/* Auto-save on blur/enter would be better, adding basic save btn for now */}
                </div>
              </div>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-2 border-t border-border/20">
                <span>RISK CHECK</span>
                <span className={data.riskStatus.safe ? "text-emerald-400" : "text-amber-400"}>{data.riskStatus.message}</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Center Column: Data & Trade Positions (75%) */}
        <div className="lg:col-span-3 flex flex-col gap-4">

          {/* Open Positions Table */}
          <Card className="border-border/40 glass flex-1 min-h-[300px]">
            <CardHeader className="py-3 px-4 border-b border-border/40 flex flex-row items-center justify-between">
              <CardTitle className="text-xs font-bold uppercase tracking-wider flex items-center gap-2"><BarChart3 className="h-3.5 w-3.5" /> Active Portoflio ({data.positions.length})</CardTitle>
              <span className="text-[10px] text-muted-foreground">Market Value: ${data.stats.volume24h.toFixed(2)}</span>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-muted/10">
                  <TableRow className="hover:bg-transparent border-border/20">
                    <TableHead className="h-8 text-[10px] font-bold">MARKET</TableHead>
                    <TableHead className="h-8 text-[10px] font-bold">SIDE</TableHead>
                    <TableHead className="h-8 text-[10px] font-bold text-right">COST</TableHead>
                    <TableHead className="h-8 text-[10px] font-bold text-right">VALUE</TableHead>
                    <TableHead className="h-8 text-[10px] font-bold text-right">PnL</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.positions.length === 0 ? (
                    <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">No active positions</TableCell></TableRow>
                  ) : (
                    data.positions.map((pos, i) => (
                      <TableRow key={i} className="hover:bg-muted/5 border-border/20 text-xs">
                        <TableCell className="font-medium max-w-[200px] truncate">{pos.market}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={`text-[10px] border-border/40 ${pos.side.includes('Yes') ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'}`}>
                            {pos.side}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">${pos.cost.toFixed(2)}</TableCell>
                        <TableCell className="text-right font-medium">${pos.value.toFixed(2)}</TableCell>
                        <TableCell className={`text-right font-bold ${pos.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Trade History & Logs Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 h-[300px]">

            {/* History */}
            <Card className="border-border/40 glass flex flex-col">
              <CardHeader className="py-2 px-4 border-b border-border/40"><CardTitle className="text-xs font-bold uppercase tracking-wider">Recent Activity</CardTitle></CardHeader>
              <CardContent className="flex-1 overflow-auto p-0">
                <Table>
                  <TableBody>
                    {data.trades.map((t, i) => (
                      <TableRow key={i} className="hover:bg-muted/5 border-border/20 text-[10px]">
                        <TableCell className="text-muted-foreground w-[80px]">{t.time.split(' ')[1] || t.time}</TableCell>
                        <TableCell className="truncate max-w-[120px]">{t.market}</TableCell>
                        <TableCell className="text-right">
                          <span className={`px-1.5 py-0.5 rounded ${t.side.includes('Buy') ? 'bg-emerald-500/10 text-emerald-400' : 'bg-blue-500/10 text-blue-400'}`}>
                            {t.side}
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-mono">${t.amount.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Terminal View */}
            <div className="border border-border/40 rounded-xl bg-black/40 overflow-hidden flex flex-col">
              <div className="bg-muted/10 px-3 py-1.5 border-b border-border/40 text-[10px] text-muted-foreground flex justify-between">
                <span>TERMINAL</span>
              </div>
              <div className="flex-1 relative">
                <LLMTerminal />
              </div>
            </div>

          </div>
        </div>
      </main>

    </div>
  )
}
