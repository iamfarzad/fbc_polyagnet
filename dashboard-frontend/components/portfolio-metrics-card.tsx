"use client"

import { Wallet, TrendingUp, DollarSign, Activity, AlertCircle, BarChart3, Zap } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"

interface PortfolioMetricsProps {
    cash: number
    equity: number
    unrealizedPnl: number
    tradeCount: number
    aiTip?: string
    scalperActivity?: string // New prop for "Why am I not trading?"
}

export function PortfolioMetricsCard({
    cash,
    equity,
    unrealizedPnl,
    tradeCount,
    aiTip,
    scalperActivity
}: PortfolioMetricsProps) {

    // Velocity Logic
    const velocityTarget = 48
    const velocityProgress = Math.min((tradeCount / velocityTarget) * 100, 100)

    // Derived Status
    // If activity contains "NO MOMENTUM" or "Low Volatility", show that.
    const isFiltering = scalperActivity?.includes("NO MOMENTUM") || scalperActivity?.includes("Low Volatility")
    const statusMessage = isFiltering ? "FILTERED: Low Volatility (Waiting for trigger...)" : "ACTIVE: Hunting Cycles"

    return (
        <Card className="border-border/40 bg-card/40 backdrop-blur-sm h-full flex flex-col justify-between overflow-hidden relative">
            <div className="absolute top-0 left-0 w-1 h-full bg-primary/20" />

            <div className="grid grid-cols-3 gap-0 h-full divide-x divide-border/10">

                {/* 1. Cash (Bankroll) */}
                <div className="p-4 flex flex-col justify-center">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="p-1.5 rounded bg-emerald-500/10">
                            <Wallet className="h-3.5 w-3.5 text-emerald-400" />
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Bankroll</span>
                    </div>
                    <div className="mt-1">
                        <span className="text-2xl font-mono font-bold tracking-tight">${cash.toFixed(2)}</span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                        <span className="text-emerald-400 font-bold">Goal: $248</span>
                        <Progress value={(cash / 248) * 100} className="h-1 w-12 ml-2" />
                    </div>
                </div>

                {/* 2. Velocity (The Stalker View) */}
                <div className="p-4 flex flex-col justify-center bg-violet-500/5">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="p-1.5 rounded bg-violet-500/10">
                            <BarChart3 className="h-3.5 w-3.5 text-violet-400" />
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Cycle Velocity</span>
                    </div>
                    <div className="mt-1 flex items-baseline gap-1">
                        <span className="text-2xl font-mono font-bold tracking-tight text-violet-100">{tradeCount}</span>
                        <span className="text-xs text-muted-foreground font-mono">/ {velocityTarget}</span>
                    </div>
                    <div className="mt-2">
                        <Progress value={velocityProgress} className="h-1.5 bg-violet-950/50" />
                    </div>
                </div>

                {/* 3. Status / Momentum */}
                <div className="p-4 flex flex-col justify-center">
                    <div className="flex items-center gap-2 mb-1">
                        <div className="p-1.5 rounded bg-amber-500/10">
                            <Activity className="h-3.5 w-3.5 text-amber-400" />
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Scanner</span>
                    </div>
                    <div className="mt-1">
                        {/* Logic to parse momentum would be here, for now using PnL as proxy for 'Action' if positive, or Status message */}
                        <div className={`text-xs font-mono font-bold ${unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            Open PnL: {unrealizedPnl >= 0 ? '+' : ''}{unrealizedPnl.toFixed(2)}
                        </div>
                    </div>
                    <div className="mt-2 flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${isFiltering ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500'}`} />
                        <span className="text-[9px] text-muted-foreground truncate max-w-[120px]" title={statusMessage}>
                            {statusMessage}
                        </span>
                    </div>
                </div>
            </div>
        </Card>
    )
}
