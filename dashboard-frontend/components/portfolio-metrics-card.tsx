"use client"

import { TrendingUp, TrendingDown, Wallet, BarChart3, Zap, Lightbulb } from "lucide-react"

interface PortfolioMetricsCardProps {
    cash: number
    equity: number
    unrealizedPnl: number
    tradeCount: number
    aiTip?: string
}

export function PortfolioMetricsCard({
    cash,
    equity,
    unrealizedPnl,
    tradeCount,
    aiTip
}: PortfolioMetricsCardProps) {
    const pnlChange = unrealizedPnl >= 0
    const pnlPercent = equity > 0 ? ((unrealizedPnl / equity) * 100).toFixed(1) : "0.0"

    return (
        <div className="rounded-xl border border-border/40 bg-card/30 backdrop-blur-sm overflow-hidden">
            {/* Header */}
            <div className="px-5 py-3 border-b border-border/30 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Wallet className="h-4 w-4 text-primary" />
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Portfolio Overview</span>
                </div>
                <div className="text-xs text-muted-foreground">
                    Budget <span className="text-foreground font-bold ml-1">${(cash + equity).toFixed(0)}</span>
                </div>
            </div>

            {/* Main Value */}
            <div className="px-5 py-4">
                <div className="flex items-baseline gap-3">
                    <span className="text-3xl font-bold tracking-tight">${equity.toFixed(2)}</span>
                    <span className={`text-sm font-medium ${pnlChange ? 'text-emerald-400' : 'text-red-400'}`}>
                        {pnlChange ? '↑' : '↓'} {pnlChange ? '+' : ''}{unrealizedPnl.toFixed(2)} ({pnlPercent}%)
                    </span>
                </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-4 gap-px bg-border/20">
                {/* Cash */}
                <div className="bg-card/50 p-4 space-y-1">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-emerald-500" />
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Cash</span>
                    </div>
                    <div className="text-lg font-bold">${cash.toFixed(2)}</div>
                </div>

                {/* Equity */}
                <div className="bg-card/50 p-4 space-y-1">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-blue-500" />
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Positions</span>
                    </div>
                    <div className="text-lg font-bold">${(equity - cash).toFixed(2)}</div>
                </div>

                {/* Unrealized PnL */}
                <div className="bg-card/50 p-4 space-y-1">
                    <div className="flex items-center gap-1.5">
                        <div className={`w-2 h-2 rounded-full ${pnlChange ? 'bg-emerald-500' : 'bg-red-500'}`} />
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Unrealized</span>
                    </div>
                    <div className={`text-lg font-bold ${pnlChange ? 'text-emerald-400' : 'text-red-400'}`}>
                        {pnlChange ? '+' : ''}{unrealizedPnl.toFixed(2)}
                    </div>
                </div>

                {/* Trades */}
                <div className="bg-card/50 p-4 space-y-1">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-violet-500" />
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Trades</span>
                    </div>
                    <div className="text-lg font-bold">{tradeCount}</div>
                </div>
            </div>

            {/* AI Tip Banner */}
            {aiTip && (
                <div className="px-4 py-2.5 bg-primary/10 border-t border-primary/20 flex items-center gap-2">
                    <Lightbulb className="h-3.5 w-3.5 text-primary shrink-0" />
                    <span className="text-[11px] text-primary">{aiTip}</span>
                </div>
            )}
        </div>
    )
}
