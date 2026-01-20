"use client"

import { useState, useEffect } from "react"
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetDescription,
    SheetFooter
} from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { CommandInput } from "@/components/agent-control/command-input"
import { LLMTerminal } from "@/components/llm-terminal"
import { Separator } from "@/components/ui/separator"
import {
    TrendingUp,
    Zap,
    Copy,
    Activity,
    DollarSign,
    Settings2,
    Power
} from "lucide-react"

interface AgentDetailSheetProps {
    isOpen: boolean
    onClose: () => void
    agentId: string
    agentName: string
    isRunning: boolean
    onToggle: () => void
    dailyPnL?: number
    tradeCount?: number
}

const AGENT_CONFIGS: Record<string, { description: string; icon: React.ReactNode }> = {
    safe: {
        description: "Conservative long-term trading on established markets.",
        icon: <TrendingUp className="h-5 w-5 text-emerald-400" />
    },
    scalper: {
        description: "High-frequency momentum trading on 15m crypto markets.",
        icon: <Zap className="h-5 w-5 text-amber-400" />
    },
    copy: {
        description: "Social sentiment analysis and copy-trading strategies.",
        icon: <Copy className="h-5 w-5 text-violet-400" />
    },
}

export function AgentDetailSheet({
    isOpen,
    onClose,
    agentId,
    agentName,
    isRunning,
    onToggle,
    dailyPnL = 0,
    tradeCount = 0
}: AgentDetailSheetProps) {
    const config = AGENT_CONFIGS[agentId] || AGENT_CONFIGS.safe
    // Mock config state for now - backend sync to be added
    const [confidence, setConfidence] = useState([70])
    const [maxBet, setMaxBet] = useState([15])

    const handleConfigChange = async (key: string, value: number) => {
        try {
            await fetch("/api/update-config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ key, value })
            })
            // Could add toast notification here
        } catch (e) {
            console.error("Config update failed", e)
        }
    }

    return (
        <Sheet open={isOpen} onOpenChange={onClose}>
            <SheetContent side="right" className="w-[500px] sm:w-[600px] sm:max-w-[80vw] p-0 flex flex-col gap-0 border-l border-border/40">

                {/* Header */}
                <div className="shrink-0 p-6 pb-4 border-b border-border/40 bg-muted/10">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-secondary/50 border border-border/50">
                                {config.icon}
                            </div>
                            <div>
                                <SheetTitle className="text-xl font-bold tracking-tight">{agentName}</SheetTitle>
                                <div className="flex items-center gap-2 mt-1">
                                    <Badge variant={isRunning ? "default" : "secondary"} className={isRunning ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20" : "text-muted-foreground"}>
                                        {isRunning ? "ACTIVE" : "PAUSED"}
                                    </Badge>
                                    <span className="text-xs text-muted-foreground font-mono uppercase tracking-wider">{agentId}</span>
                                </div>
                            </div>
                        </div>

                        <Button
                            variant={isRunning ? "destructive" : "default"}
                            size="sm"
                            onClick={onToggle}
                            className="gap-2"
                        >
                            <Power className="h-3.5 w-3.5" />
                            {isRunning ? "Stop Agent" : "Start Agent"}
                        </Button>
                    </div>

                    <SheetDescription className="text-sm mt-2">
                        {config.description}
                    </SheetDescription>
                </div>

                {/* Scrollable Content */}
                <div className="flex-1 overflow-y-auto">
                    <div className="p-6 space-y-8">

                        {/* Quick Stats Grid */}
                        <div className="grid grid-cols-2 gap-4">
                            <div className="p-4 rounded-xl border border-border/40 bg-card/50 space-y-1">
                                <div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">Daily PnL</div>
                                <div className={`text-2xl font-mono font-bold ${dailyPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    ${dailyPnL.toFixed(2)}
                                </div>
                            </div>
                            <div className="p-4 rounded-xl border border-border/40 bg-card/50 space-y-1">
                                <div className="text-muted-foreground text-xs font-medium uppercase tracking-wider">Trades Today</div>
                                <div className="text-2xl font-mono font-bold text-foreground">
                                    {tradeCount}
                                </div>
                            </div>
                        </div>

                        {/* Command Interface */}
                        <div className="space-y-3">
                            <div className="flex items-center gap-2 text-sm font-medium text-foreground/80">
                                <Activity className="h-4 w-4 text-violet-400" />
                                Command Line
                            </div>
                            <CommandInput
                                agentId={agentId}
                                agentName={agentName}
                                className="w-full"
                            />
                        </div>

                        {/* Configuration */}
                        <div className="space-y-6 p-5 rounded-xl border border-border/40 bg-secondary/10">
                            <div className="flex items-center gap-2 text-sm font-medium text-foreground/80 mb-4">
                                <Settings2 className="h-4 w-4 text-muted-foreground" />
                                Live Configuration
                            </div>

                            <div className="space-y-3">
                                <div className="flex justify-between">
                                    <label className="text-xs text-muted-foreground font-medium">Min Confidence</label>
                                    <span className="text-xs font-mono">{confidence}%</span>
                                </div>
                                <Slider
                                    value={confidence}
                                    onValueChange={setConfidence}
                                    onValueCommit={(vals) => handleConfigChange(`${agentId}_confidence`, vals[0])}
                                    max={100}
                                    step={1}
                                    className="[&_.bg-primary]:bg-emerald-500"
                                />
                            </div>

                            <div className="space-y-3">
                                <div className="flex justify-between">
                                    <label className="text-xs text-muted-foreground font-medium">Max Bet Size</label>
                                    <span className="text-xs font-mono">${maxBet}</span>
                                </div>
                                <Slider
                                    value={maxBet}
                                    onValueChange={setMaxBet}
                                    onValueCommit={(vals) => handleConfigChange(`${agentId}_max_bet`, vals[0])}
                                    max={100}
                                    step={1}
                                />
                            </div>
                        </div>

                        {/* Activity Log */}
                        <div className="h-[400px] border border-border/40 rounded-xl overflow-hidden flex flex-col">
                            <div className="bg-muted/30 px-4 py-2 border-b border-border/40 text-xs font-medium text-muted-foreground">
                                Recent Agent Activity
                            </div>
                            <div className="flex-1 bg-black/20">
                                <LLMTerminal agentFilter={agentId} className="h-full" />
                            </div>
                        </div>

                    </div>
                </div>

            </SheetContent>
        </Sheet>
    )
}
