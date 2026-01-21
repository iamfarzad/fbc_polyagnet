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
    scalperActivity?: string
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

    // Derived Status: "Why am I not trading?"
    const isFiltering = scalperActivity?.includes("NO MOMENTUM") || scalperActivity?.includes("Low Volatility") || scalperActivity?.includes("FILTERED")
    const statusMessage = isFiltering ? "FILTERED: Low Volatility (Waiting for trigger...)" : "ACTIVE: Hunting Cycles"

    return (
        <Card className="border-border/40 bg-card/40 backdrop-blur-sm h-full flex flex-col justify-between overflow-hidden relative font-sans">
            <div className="absolute top-0 left-0 w-1.5 h-full bg-primary/30" />

            <div className="grid grid-cols-1 md:grid-cols-3 gap-0 h-full divide-y md:divide-y-0 md:divide-x divide-border/10">

                {/* 1. Cash (Bankroll) */}
                <div className="p-6 flex flex-col justify-center">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="p-2 rounded bg-emerald-500/10 border border-emerald-500/20">
                            <Wallet className="h-4 w-4 text-emerald-400" />
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Capital Allocation</span>
                    </div>
                    <div className="mt-1 flex items-baseline gap-2">
                        <span className="text-3xl font-mono font-bold tracking-tight">${cash.toFixed(2)}</span>
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                        <span className="text-[10px] font-bold text-emerald-400 uppercase">Goal Progress ($248)</span>
                        <Progress value={(cash / 248) * 100} className="h-1.5 flex-1 bg-emerald-950/30" />
                    </div>
                </div>

                {/* 2. Velocity (HFT Tracker) */}
                <div className="p-6 flex flex-col justify-center bg-violet-500/[0.03]">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="p-2 rounded bg-violet-500/10 border border-violet-500/20">
                            <BarChart3 className="h-4 w-4 text-violet-400" />
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Compounding Velocity</span>
                    </div>
                    <div className="mt-1 flex items-baseline gap-2">
                        <span className="text-3xl font-mono font-bold tracking-tight text-white">{tradeCount}</span>
                        <span className="text-sm text-muted-foreground font-mono">/ {velocityTarget} <span className="text-[10px] ml-1">CYCLES</span></span>
                    </div>
                    <div className="mt-3">
                        <Progress value={velocityProgress} className="h-2 bg-violet-950/50" />
                    </div>
                </div>

                {/* 3. Strategy Status (The "Stalker" View) */}
                <div className="p-6 flex flex-col justify-center">
                    <div className="flex items-center gap-2 mb-2">
                        <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20">
                            <Activity className="h-4 w-4 text-amber-400" />
                        </div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Intelligence Monitor</span>
                    </div>
                    <div className="mt-1">
                        <div className={`text-sm font-mono font-bold flex items-center gap-2 ${unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            Open PnL: {unrealizedPnl >= 0 ? '+$' : '-$'}{Math.abs(unrealizedPnl).toFixed(2)}
                        </div>
                    </div>
                    <div className="mt-4 p-2 rounded-lg bg-card/30 border border-border/20 flex items-center gap-2.5">
                        <span className={`flex-shrink-0 w-2 h-2 rounded-full ${isFiltering ? 'bg-amber-500 animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.5)]' : 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]'}`} />
                        <span className="text-[10px] font-medium text-foreground/90 tracking-tight leading-none">
                            {statusMessage}
                        </span>
                    </div>
                </div>
            </div>
        </Card>
    )
}
