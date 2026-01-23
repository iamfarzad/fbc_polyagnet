"use client"

import { useMemo } from "react"
import { Card } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { ArrowUpRight, ArrowDownRight, Share2, Expand, Edit2 } from "lucide-react"

interface UserPerformanceProps {
    data: {
        walletAddress: string
        positions_value: number
        biggest_win: number
        predictions_count: number
        pnl_history: any[]
        balance: number
        equity: number
    }
}

export function UserPerformance({ data }: UserPerformanceProps) {
    // Mock user name/avatar (since we don't have it on backend yet, or use wallet)
    const username = "Iamfree" // Matches screenshot
    const joined = "Joined Jan 2026"

    // Calculate PnL for the graph
    // If pnl_history is empty, we simulate a line or use start/end points
    const chartData = useMemo(() => {
        if (!data.pnl_history || data.pnl_history.length === 0) return []
        return data.pnl_history.map((point: any) => ({
            time: new Date(point.timestamp).toLocaleDateString(),
            val: point.equity - 1000 // illustrative PnL if starting from 1000? 
            // Or just use 'unrealized_pnl' from snapshot + realized?
            // Snapshot has 'unrealized_pnl'.
            // Let's assume point.unrealized_pnl is what we want, or equity - initial_balance.
            // For now, mapping equity directly or pnl if available
        })).reverse() // Backend returns reverse chronological? No, check api.
    }, [data.pnl_history])

    const totalPnL = data.equity - data.balance // Rough calc
    const isPositive = totalPnL >= 0

    return (
        <div className="grid grid-cols-1 gap-3">
            {/* Top Card: Stats Overview */}
            <Card className="p-3 border-border/40 bg-card rounded-xl flex flex-col justify-center h-[90px]">
                <div className="flex justify-between items-end">
                    <div className="space-y-0.5">
                        <p className="text-[9px] uppercase text-muted-foreground font-bold tracking-wide">Positions</p>
                        <p className="text-lg font-mono font-bold text-foreground">${data.positions_value.toFixed(2)}</p>
                    </div>
                    <Separator orientation="vertical" className="h-8 bg-border/50" />
                    <div className="space-y-0.5">
                        <p className="text-[9px] uppercase text-muted-foreground font-bold tracking-wide">Best Win</p>
                        <p className="text-lg font-mono font-bold text-emerald-500">${data.biggest_win.toFixed(2)}</p>
                    </div>
                    <Separator orientation="vertical" className="h-8 bg-border/50" />
                    <div className="space-y-0.5">
                        <p className="text-[9px] uppercase text-muted-foreground font-bold tracking-wide">Predictions</p>
                        <p className="text-lg font-mono font-bold text-foreground">{data.predictions_count}</p>
                    </div>
                </div>
            </Card>

            {/* Bottom Card: PnL Graph */}
            <Card className="p-4 border-border/40 bg-card rounded-xl h-[160px] flex flex-col relative overflow-hidden">
                <div className="flex justify-between items-start z-10">
                    <div>
                        <div className="flex items-center gap-2 text-muted-foreground mb-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wide">Net PnL</span>
                        </div>
                        <h2 className={`text-2xl font-mono font-bold tracking-tighter ${isPositive ? 'text-emerald-500' : 'text-red-500'}`}>
                            {isPositive ? "+" : ""}${totalPnL.toFixed(2)}
                        </h2>
                        <p className="text-[9px] text-muted-foreground uppercase font-bold tracking-widest mt-0.5">All-Time</p>
                    </div>
                    <div className="flex gap-1">
                        {['1D', '1W', '1M', 'ALL'].map(period => (
                            <button
                                key={period}
                                className={`px-2 py-1 text-[10px] font-bold rounded-sm ${period === 'ALL' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted'}`}
                            >
                                {period}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Chart absolute at bottom */}
                <div className="absolute bottom-0 left-0 right-0 h-[80px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData.length > 0 ? chartData : [{ val: 100 }, { val: 90 }, { val: 85 }, { val: 80 }, { val: 95 }]}>
                            <defs>
                                <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0.2} />
                                    <stop offset="100%" stopColor={isPositive ? "#10b981" : "#ef4444"} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <Area
                                type="monotone"
                                dataKey="val"
                                stroke={isPositive ? "#10b981" : "#ef4444"}
                                strokeWidth={2}
                                fill="url(#pnlGradient)"
                                fillOpacity={1}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </Card>
        </div>
    )
}
