"use client"

import { useState } from "react"
import {
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    CardFooter
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import {
    TrendingUp,
    Zap,
    Copy,
    MoreHorizontal,
    Activity,
    PlayCircle,
    PauseCircle
} from "lucide-react"
import { AgentDetailSheet } from "./agent-detail-sheet"
import { cn } from "@/lib/utils"

interface AgentCardProps {
    id: string
    name: string
    isActive: boolean
    lastActive: number // timestamp
    currentActivity?: string
    dailyPnL?: number
    tradeCount?: number
    onToggle: (isActive: boolean) => void
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
    safe: <TrendingUp className="h-5 w-5 text-emerald-400" />,
    scalper: <Zap className="h-5 w-5 text-amber-400" />,
    copy: <Copy className="h-5 w-5 text-violet-400" />,
}

export function AgentCard({
    id,
    name,
    isActive,
    lastActive,
    currentActivity,
    dailyPnL = 0,
    tradeCount = 0,
    onToggle
}: AgentCardProps) {
    const [showDetail, setShowDetail] = useState(false)

    // Calculate heartbeat status
    const timeSinceLast = Date.now() - lastActive
    let heartbeatColor = "bg-emerald-500" // < 1 min
    let heartbeatStatus = "Live"

    if (!isActive) {
        heartbeatColor = "bg-zinc-500"
        heartbeatStatus = "Paused"
    } else if (timeSinceLast > 300000) { // > 5 mins
        heartbeatColor = "bg-red-500"
        heartbeatStatus = "Stalled"
    } else if (timeSinceLast > 60000) { // > 1 min
        heartbeatColor = "bg-amber-500"
        heartbeatStatus = "Slow"
    }

    const pnlColor = dailyPnL >= 0 ? "text-emerald-400" : "text-red-400"

    return (
        <>
            <Card className="flex flex-col border-border/40 bg-zinc-900/40 hover:bg-zinc-900/60 transition-colors backdrop-blur-sm shadow-sm overflow-hidden group relative">
                {/* Active Status Strip */}
                <div className={cn(
                    "absolute top-0 left-0 bottom-0 w-1 transition-colors",
                    isActive ? "bg-emerald-500/50" : "bg-zinc-800"
                )} />

                <CardHeader className="pb-2 pl-7">
                    <div className="flex justify-between items-start">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-secondary/50 border border-border/50">
                                {AGENT_ICONS[id] || <Activity className="h-5 w-5 text-muted-foreground" />}
                            </div>
                            <div className="space-y-1">
                                <CardTitle className="text-base font-semibold tracking-tight">{name}</CardTitle>
                                <div className="flex flex-col gap-1">
                                    <div className="flex items-center gap-2">
                                        <div className="flex items-center gap-1.5">
                                            <span className={`relative flex h-2 w-2`}>
                                                {isActive && heartbeatStatus === "Live" && (
                                                    <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${heartbeatColor}`}></span>
                                                )}
                                                <span className={`relative inline-flex rounded-full h-2 w-2 ${heartbeatColor}`}></span>
                                            </span>
                                            <span className="text-[10px] uppercase font-mono text-muted-foreground tracking-wide">
                                                {heartbeatStatus}
                                            </span>
                                        </div>
                                    </div>
                                    {isActive && currentActivity && (
                                        <span className="text-[10px] text-muted-foreground/80 font-mono truncate max-w-[140px] block">
                                            {currentActivity}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>

                        <Switch
                            checked={isActive}
                            onCheckedChange={onToggle}
                            className="data-[state=checked]:bg-emerald-500"
                        />
                    </div>
                </CardHeader>

                <CardContent className="py-2 pl-7 grid grid-cols-2 gap-4">
                    <div className="space-y-0.5">
                        <span className="text-[10px] text-muted-foreground uppercase font-medium">Daily PnL</span>
                        <div className={`text-lg font-mono font-bold ${pnlColor}`}>
                            {dailyPnL >= 0 && "+"}${dailyPnL.toFixed(2)}
                        </div>
                    </div>
                    <div className="space-y-0.5">
                        <span className="text-[10px] text-muted-foreground uppercase font-medium">Trades</span>
                        <div className="text-lg font-mono font-bold text-foreground">
                            {tradeCount}
                        </div>
                    </div>
                </CardContent>

                <CardFooter className="pt-2 pl-7 pb-4">
                    <Button
                        variant="outline"
                        size="sm"
                        className="w-full text-xs h-8 border-border/40 hover:bg-secondary/50 group-hover:border-primary/20 transition-all font-medium"
                        onClick={() => setShowDetail(true)}
                    >
                        <MoreHorizontal className="h-3.5 w-3.5 mr-2 text-muted-foreground" />
                        Open Command Center
                    </Button>
                </CardFooter>
            </Card>

            <AgentDetailSheet
                isOpen={showDetail}
                onClose={() => setShowDetail(false)}
                agentId={id}
                agentName={name}
                isRunning={isActive}
                onToggle={() => onToggle(!isActive)}
                dailyPnL={dailyPnL}
                tradeCount={tradeCount}
            />
        </>
    )
}
