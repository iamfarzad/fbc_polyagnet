"use client"

import { useState, useEffect, useRef } from "react"
import { Activity, Zap, Brain, Shield, Users, Gamepad2, Trophy } from "lucide-react"
import { getApiUrl } from "@/lib/api-url"

interface ActivityEntry {
    id: string
    timestamp: string
    agent: string
    action: string
    detail?: string
    type: "scan" | "trade" | "analysis" | "info"
}

interface ActivityFeedProps {
    className?: string
}

const AGENT_COLORS: Record<string, string> = {
    safe: "text-emerald-400",
    scalper: "text-amber-400",
    copyTrader: "text-violet-400",
    smartTrader: "text-blue-400",
    esportsTrader: "text-pink-400",
    sportsTrader: "text-orange-400",
}

export function ActivityFeed({ className }: ActivityFeedProps) {
    const [activities, setActivities] = useState<ActivityEntry[]>([])
    const scrollRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        const fetchActivities = async () => {
            try {
                const res = await fetch(`${getApiUrl()}/api/llm-activity`)
                if (res.ok) {
                    const data = await res.json()
                    const entries: ActivityEntry[] = (data.activities || []).slice(0, 20).map((a: any, i: number) => ({
                        id: `${i}-${a.timestamp}`,
                        timestamp: a.timestamp,
                        agent: a.agent || "system",
                        action: a.action_type || "INFO",
                        detail: a.market_question || a.reasoning || "",
                        type: (a.action_type || "").toLowerCase().includes("trade") ? "trade"
                            : (a.action_type || "").toLowerCase().includes("scan") ? "scan"
                                : (a.action_type || "").toLowerCase().includes("analy") ? "analysis"
                                    : "info"
                    }))
                    setActivities(entries)
                }
            } catch (e) {
                console.error("Failed to fetch activities", e)
            }
        }

        fetchActivities()
        const interval = setInterval(fetchActivities, 5000)
        return () => clearInterval(interval)
    }, [])

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = 0
        }
    }, [activities])

    const formatTime = (ts: string) => {
        try {
            const d = new Date(ts)
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        } catch {
            return ""
        }
    }

    return (
        <div className={`rounded-xl border border-border/40 bg-card/30 backdrop-blur-sm overflow-hidden flex flex-col ${className}`}>
            {/* Header */}
            <div className="px-4 py-2.5 border-b border-border/30 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                    <Activity className="h-3.5 w-3.5 text-primary" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Activity</span>
                </div>
                <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                    Live
                </span>
            </div>

            {/* Feed */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto">
                {activities.length === 0 ? (
                    <div className="p-4 text-center text-muted-foreground text-xs">No recent activity</div>
                ) : (
                    activities.map((entry) => {
                        const color = AGENT_COLORS[entry.agent] || "text-muted-foreground"
                        return (
                            <div key={entry.id} className="px-4 py-2 border-b border-border/10 hover:bg-muted/5 transition-colors">
                                <div className="flex items-center gap-2 text-[10px]">
                                    <span className="text-muted-foreground/70 w-12 shrink-0">{formatTime(entry.timestamp)}</span>
                                    <span className={`font-bold uppercase ${color}`}>{entry.agent.slice(0, 6)}</span>
                                    <span className="text-muted-foreground">·</span>
                                    <span className="text-foreground/80">{entry.action}</span>
                                </div>
                                {entry.detail && (
                                    <p className="text-[10px] text-muted-foreground mt-0.5 ml-14 truncate">{entry.detail}</p>
                                )}
                            </div>
                        )
                    })
                )}
            </div>
        </div>
    )
}
