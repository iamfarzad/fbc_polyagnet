"use client"

import { useMemo } from "react"
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PieChart as PieChartIcon } from "lucide-react"

interface Position {
    market: string
    value: number
    pnl: number
}

interface AllocationPieChartProps {
    positions: Position[]
    cashBalance: number
}

const COLORS = [
    "#10b981", // Emerald 500 (Profitable/Cash)
    "#f59e0b", // Amber 500 (Neutral)
    "#ef4444", // Red 500 (Loss)
    "#8b5cf6", // Violet 500
    "#3b82f6", // Blue 500
    "#ec4899", // Pink 500
]

export function AllocationPieChart({ positions, cashBalance }: AllocationPieChartProps) {
    const data = useMemo(() => {
        // 1. Calculate Total Portfolio Value
        // const positionsValue = positions.reduce((acc, p) => acc + p.value, 0)
        // const totalValue = cashBalance + positionsValue

        // 2. Prepare Data Segments
        const segments = [
            { name: "Cash", value: cashBalance, color: "#10b981" }, // Cash is always Emerald
            ...positions.map((p, index) => ({
                name: p.market.length > 20 ? p.market.slice(0, 18) + "..." : p.market,
                value: p.value,
                color: COLORS[(index + 3) % COLORS.length] // Start from index 3 to avoid cash/status colors collision
            }))
        ]

        return segments.filter(s => s.value > 0).sort((a, b) => b.value - a.value)
    }, [positions, cashBalance])

    if (data.length === 0) return null

    return (
        <Card className="flex flex-col border-border/40 glass h-full">
            <CardHeader className="py-2 px-3 border-b border-border/40 h-9">
                <CardTitle className="text-[10px] font-bold uppercase tracking-wider flex items-center gap-2">
                    <PieChartIcon className="h-3 w-3" /> Allocation
                </CardTitle>
            </CardHeader>
            <CardContent className="flex-1 p-0 min-h-[140px]">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={data}
                            cx="50%"
                            cy="50%"
                            innerRadius={40}
                            outerRadius={60}
                            paddingAngle={2}
                            dataKey="value"
                            stroke="none"
                        >
                            {data.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} />
                            ))}
                        </Pie>
                        <Tooltip
                            contentStyle={{
                                backgroundColor: 'rgba(0,0,0,0.8)',
                                border: '1px solid rgba(255,255,255,0.1)',
                                borderRadius: '8px',
                                fontSize: '11px',
                                color: '#fff'
                            }}
                            itemStyle={{ color: '#fff' }}
                            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Value']}
                        />
                    </PieChart>
                </ResponsiveContainer>

                {/* Custom Mini Legend */}
                <div className="flex flex-wrap justify-center gap-2 px-2 pb-2">
                    {data.slice(0, 3).map((d, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-[9px] text-muted-foreground">
                            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: d.color }} />
                            <span className="truncate max-w-[60px]">{d.name}</span>
                        </div>
                    ))}
                    {data.length > 3 && <span className="text-[9px] text-muted-foreground">+{data.length - 3} more</span>}
                </div>
            </CardContent>
        </Card>
    )
}
