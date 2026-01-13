"use client"

import { useState, useEffect } from "react"
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Loader2, TrendingUp } from "lucide-react"

interface HistoryPoint {
    timestamp: string
    equity: number
    balance: number
    unrealized_pnl: number
}

export function PerformanceGraph() {
    const [data, setData] = useState<HistoryPoint[]>([])
    const [loading, setLoading] = useState(true)

    const fetchData = async () => {
        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
            const res = await fetch(`${apiUrl}/api/history?period=24h`)
            const json = await res.json()
            if (json.history) {
                // Format timestamps
                const formatted = json.history.map((h: any) => ({
                    ...h,
                    time: new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    equity: Number(h.equity),
                }))
                setData(formatted)
            }
        } catch (e) {
            console.error("Failed to fetch history", e)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 60000) // update every minute
        return () => clearInterval(interval)
    }, [])

    if (loading) {
        return <div className="h-[200px] flex items-center justify-center text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
        </div>
    }

    if (data.length === 0) {
        return <div className="h-[200px] flex items-center justify-center text-muted-foreground text-xs border border-dashed border-border/50 rounded-lg">
            Waiting for data...
        </div>
    }

    const pnlColor = (data[data.length - 1]?.equity || 0) >= (data[0]?.equity || 0) ? "#10b981" : "#ef4444"

    return (
        <Card className="border-border/40 bg-card/40 glass h-full">
            <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between">
                <CardTitle className="text-sm font-mono flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-primary" />
                    Portfolio Performance
                </CardTitle>
                <div className="text-xs font-mono text-muted-foreground">24H</div>
            </CardHeader>
            <CardContent className="p-0 h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={pnlColor} stopOpacity={0.3} />
                                <stop offset="95%" stopColor={pnlColor} stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.3} />
                        <XAxis
                            dataKey="time"
                            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                            tickLine={false}
                            axisLine={false}
                            minTickGap={30}
                        />
                        <YAxis
                            domain={['auto', 'auto']}
                            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                            tickFormatter={(val) => `$${val.toFixed(0)}`}
                            tickLine={false}
                            axisLine={false}
                            width={40}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: 'hsl(var(--popover))',
                                borderRadius: '8px',
                                border: '1px solid hsl(var(--border))',
                                fontSize: '12px'
                            }}
                        />
                        <Area
                            type="monotone"
                            dataKey="equity"
                            stroke={pnlColor}
                            strokeWidth={2}
                            fillOpacity={1}
                            fill="url(#colorEquity)"
                        />
                    </AreaChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    )
}
