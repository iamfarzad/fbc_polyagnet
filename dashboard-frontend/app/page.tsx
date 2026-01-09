"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { RefreshCw, AlertTriangle, TrendingUp, TrendingDown, DollarSign, Activity, Zap, Wallet, ExternalLink } from "lucide-react"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"

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

export default function PolymarketDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [maxBet, setMaxBet] = useState(0.50)
  const [updatingConfig, setUpdatingConfig] = useState(false)

  const fetchDashboardData = async () => {
    setLoading(true)
    try {
      const response = await fetch("/api/dashboard")
      const json = await response.json()
      setData(json)
      if (json.maxBetAmount !== undefined) setMaxBet(json.maxBetAmount)
    } catch (error) {
      console.error("[v0] Failed to fetch dashboard data:", error)
    } finally {
      setLoading(false)
    }
  }

  const toggleAgent = async (agent: "safe" | "scalper" | "copyTrader") => {
    try {
      await fetch(`/api/toggle-agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent }),
      })
      fetchDashboardData()
    } catch (error) {
      console.error("[v0] Failed to toggle agent:", error)
    }
  }

  const emergencyStop = async () => {
    try {
      await fetch("/api/emergency-stop", { method: "POST" })
      fetchDashboardData()
    } catch (error) {
      console.error("[v0] Failed to emergency stop:", error)
    }
  }

  const toggleDryRun = async () => {
    try {
      await fetch("/api/toggle-dry-run", { method: "POST" })
      fetchDashboardData()
    } catch (error) {
      console.error("[v0] Failed to toggle dry run:", error)
    }
  }

  const updateMaxBet = async () => {
    setUpdatingConfig(true)
    try {
      await fetch("/api/update-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: "max_bet", value: Number(maxBet) }),
      })
      fetchDashboardData()
    } catch (error) {
      console.error("[v0] Failed to update config:", error)
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
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-5 w-5 animate-spin" />
          <span className="font-mono text-sm">Initializing...</span>
        </div>
      </div>
    )
  }

  const pnlIsPositive = data.unrealizedPnl >= 0

  return (
    <div className="min-h-screen bg-background p-4 md:p-6 lg:p-8">
      <div className="mx-auto max-w-[1600px] space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="font-mono text-2xl font-bold tracking-tight text-foreground md:text-3xl">
                Farzad Bayat Polymarked AGENT
              </h1>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <p className="font-mono text-xs text-muted-foreground">{data.lastUpdate}</p>
              {data.walletAddress && (
                <a
                  href={`https://polymarket.com/profile/${data.walletAddress}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 font-mono text-xs text-primary hover:underline"
                >
                  <Wallet className="h-3 w-3" />
                  {data.walletAddress.slice(0, 6)}...{data.walletAddress.slice(-4)}
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-md border border-input bg-card/50 p-1 px-2">
              <span className="font-mono text-xs text-muted-foreground whitespace-nowrap">Max Bet: $</span>
              <input
                type="number"
                step="0.1"
                className="h-6 w-12 bg-transparent font-mono text-xs focus:outline-none"
                value={maxBet}
                onChange={(e) => setMaxBet(parseFloat(e.target.value))}
              />
              <Button
                size="sm"
                variant="ghost"
                className="h-6 px-2 text-xs"
                onClick={updateMaxBet}
                disabled={updatingConfig}
              >
                Set
              </Button>
            </div>

            <div className="flex items-center gap-2 rounded-md border border-input bg-card/50 p-1 px-2">
              <span className="font-mono text-xs text-muted-foreground whitespace-nowrap">
                {data.dryRun ? "🧪 Sim" : "💸 Real"}
              </span>
              <Switch checked={data.dryRun} onCheckedChange={toggleDryRun} className="scale-75" />
            </div>

            <Button
              onClick={fetchDashboardData}
              disabled={loading}
              size="sm"
              variant="outline"
              className="gap-2 bg-transparent"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            <Button onClick={emergencyStop} size="sm" variant="destructive" className="gap-2">
              <AlertTriangle className="h-4 w-4" />
              STOP ALL
            </Button>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="font-mono text-xs font-medium uppercase tracking-wide text-muted-foreground">
                USDC Balance
              </CardTitle>
              <DollarSign className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="font-mono text-2xl font-bold text-foreground">${data.balance.toFixed(2)}</div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">Available liquidity</p>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="font-mono text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Total Equity
              </CardTitle>
              <TrendingUp className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="font-mono text-2xl font-bold text-foreground">${data.equity.toFixed(2)}</div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">Portfolio value</p>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="font-mono text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Unrealized PnL
              </CardTitle>
              {pnlIsPositive ? (
                <TrendingUp className="h-4 w-4 text-primary" />
              ) : (
                <TrendingDown className="h-4 w-4 text-destructive" />
              )}
            </CardHeader>
            <CardContent>
              <div className={`font-mono text-2xl font-bold ${pnlIsPositive ? "text-primary" : "text-destructive"}`}>
                {pnlIsPositive ? "+" : ""}${data.unrealizedPnl.toFixed(2)}
              </div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">Open positions</p>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="font-mono text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Gas Spent
              </CardTitle>
              <Zap className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="font-mono text-2xl font-bold text-foreground">{data.gasSpent.toFixed(4)}</div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">POL total</p>
            </CardContent>
          </Card>

          <Card
            className={`border-border/50 backdrop-blur ${data.riskStatus.safe ? "bg-primary/5" : "bg-destructive/5"}`}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
              <CardTitle className="font-mono text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Risk Status
              </CardTitle>
              <div className={`h-2 w-2 rounded-full ${data.riskStatus.safe ? "bg-primary" : "bg-destructive"}`} />
            </CardHeader>
            <CardContent>
              <div
                className={`font-mono text-lg font-bold ${data.riskStatus.safe ? "text-primary" : "text-destructive"}`}
              >
                {data.riskStatus.safe ? "SAFE" : "WARNING"}
              </div>
              <p className="mt-1 font-mono text-xs text-muted-foreground">{data.riskStatus.message}</p>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="font-mono text-sm font-semibold">Safe Agent</CardTitle>
                <div className="flex items-center gap-2">
                  <div className={`h-2 w-2 rounded-full ${data.agents.safe.running ? "bg-primary" : "bg-muted"}`} />
                  <Switch checked={data.agents.safe.running} onCheckedChange={() => toggleAgent("safe")} />
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-muted-foreground">Status</span>
                <Badge variant={data.agents.safe.running ? "default" : "secondary"} className="font-mono text-xs">
                  {data.agents.safe.running ? "Active" : "Paused"}
                </Badge>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-xs text-muted-foreground">Activity</span>
                <p className="font-mono text-xs text-foreground">{data.agents.safe.activity}</p>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-xs text-muted-foreground">API</span>
                <p className="truncate font-mono text-xs text-foreground">{data.agents.safe.endpoint}</p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="font-mono text-sm font-semibold">Scalper</CardTitle>
                <div className="flex items-center gap-2">
                  <div className={`h-2 w-2 rounded-full ${data.agents.scalper.running ? "bg-primary" : "bg-muted"}`} />
                  <Switch checked={data.agents.scalper.running} onCheckedChange={() => toggleAgent("scalper")} />
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-muted-foreground">Status</span>
                <Badge variant={data.agents.scalper.running ? "default" : "secondary"} className="font-mono text-xs">
                  {data.agents.scalper.running ? "Active" : "Paused"}
                </Badge>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-xs text-muted-foreground">Activity</span>
                <p className="font-mono text-xs text-foreground">{data.agents.scalper.activity}</p>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-xs text-muted-foreground">API</span>
                <p className="truncate font-mono text-xs text-foreground">{data.agents.scalper.endpoint}</p>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="font-mono text-sm font-semibold">Copy Trader</CardTitle>
                <div className="flex items-center gap-2">
                  <div
                    className={`h-2 w-2 rounded-full ${data.agents.copyTrader.running ? "bg-primary" : "bg-muted"}`}
                  />
                  <Switch checked={data.agents.copyTrader.running} onCheckedChange={() => toggleAgent("copyTrader")} />
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-muted-foreground">Status</span>
                <Badge variant={data.agents.copyTrader.running ? "default" : "secondary"} className="font-mono text-xs">
                  {data.agents.copyTrader.running ? "Active" : "Paused"}
                </Badge>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-xs text-muted-foreground">Last Signal</span>
                <p className="font-mono text-xs text-foreground">{data.agents.copyTrader.lastSignal}</p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="font-mono text-sm font-semibold">24h Activity</CardTitle>
              <Activity className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-muted-foreground">Total Trades</span>
                <span className="font-mono text-base font-bold text-foreground">{data.stats.tradeCount}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-muted-foreground">Trading Volume</span>
                <span className="font-mono text-base font-bold text-foreground">
                  ${data.stats.volume24h.toFixed(2)}
                </span>
              </div>
            </CardContent>
          </Card>

        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader>
              <CardTitle className="font-mono text-sm font-semibold">Open Positions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {data.positions.length === 0 ? (
                  <p className="py-8 text-center font-mono text-xs text-muted-foreground">No open positions</p>
                ) : (
                  <div className="space-y-2">
                    {data.positions.slice(0, 5).map((pos, i) => (
                      <div key={i} className="flex items-center justify-between rounded-md border border-border/50 p-3">
                        <div className="flex-1 space-y-1">
                          <p className="truncate font-mono text-xs font-medium text-foreground">{pos.market}</p>
                          <p className="font-mono text-xs text-muted-foreground">{pos.side}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-mono text-xs font-medium text-foreground">${pos.value.toFixed(2)}</p>
                          <p className={`font-mono text-xs ${pos.pnl >= 0 ? "text-primary" : "text-destructive"}`}>
                            {pos.pnl >= 0 ? "+" : ""}${pos.pnl.toFixed(2)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/50 backdrop-blur">
            <CardHeader>
              <CardTitle className="font-mono text-sm font-semibold">Recent Trades</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {data.trades.length === 0 ? (
                  <p className="py-8 text-center font-mono text-xs text-muted-foreground">No recent trades</p>
                ) : (
                  <div className="space-y-2">
                    {data.trades.slice(0, 5).map((trade, i) => (
                      <div key={i} className="flex items-center justify-between rounded-md border border-border/50 p-3">
                        <div className="flex-1 space-y-1">
                          <p className="truncate font-mono text-xs font-medium text-foreground">{trade.market}</p>
                          <p className="font-mono text-xs text-muted-foreground">{trade.time}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-mono text-xs font-medium text-foreground">${trade.amount.toFixed(2)}</p>
                          <p className="font-mono text-xs text-muted-foreground">{trade.side}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
