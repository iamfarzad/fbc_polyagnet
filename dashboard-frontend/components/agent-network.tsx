"use client"

import { useState } from "react"
import { Brain, Zap, Users, Shield, Gamepad2, Trophy } from "lucide-react"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { Switch } from "@/components/ui/switch"

interface Agent {
    id: string
    name: string
    isActive: boolean
    activity?: string
}

interface AgentNetworkProps {
    agents: Agent[]
    onToggle: (id: string, state: boolean) => void
}

const AGENT_ICONS: Record<string, { icon: typeof Brain; color: string }> = {
    safe: { icon: Shield, color: "text-emerald-400" },
    scalper: { icon: Zap, color: "text-amber-400" },
    copyTrader: { icon: Users, color: "text-violet-400" },
    smartTrader: { icon: Brain, color: "text-blue-400" },
    esportsTrader: { icon: Gamepad2, color: "text-pink-400" },
    sportsTrader: { icon: Trophy, color: "text-orange-400" },
}

export function AgentNetwork({ agents, onToggle }: AgentNetworkProps) {
    return (
        <div className="rounded-xl border border-border/40 bg-card/30 backdrop-blur-sm overflow-hidden">
            {/* Header */}
            <div className="px-4 py-2.5 border-b border-border/30 flex items-center justify-between">
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Agent Network</span>
                <span className="text-[10px] text-muted-foreground">
                    {agents.filter(a => a.isActive).length} active
                </span>
            </div>

            {/* Agent Icons Row */}
            <div className="p-4">
                <TooltipProvider>
                    <div className="flex items-center justify-center gap-3">
                        {agents.map((agent, idx) => {
                            const config = AGENT_ICONS[agent.id] || { icon: Brain, color: "text-muted-foreground" }
                            const Icon = config.icon

                            return (
                                <Tooltip key={agent.id}>
                                    <TooltipTrigger asChild>
                                        <button
                                            onClick={() => onToggle(agent.id, !agent.isActive)}
                                            className={`
                                                relative p-3 rounded-full border transition-all duration-200
                                                ${agent.isActive
                                                    ? `border-current bg-current/10 ${config.color}`
                                                    : 'border-border/40 bg-muted/20 text-muted-foreground'
                                                }
                                                hover:scale-110 hover:shadow-lg
                                            `}
                                        >
                                            <Icon className="h-5 w-5" />
                                            {/* Connection Line */}
                                            {idx < agents.length - 1 && (
                                                <div className="absolute top-1/2 -right-3 w-3 h-px bg-border/50" />
                                            )}
                                            {/* Active Pulse */}
                                            {agent.isActive && (
                                                <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-emerald-500 rounded-full animate-pulse" />
                                            )}
                                        </button>
                                    </TooltipTrigger>
                                    <TooltipContent side="bottom" className="text-xs">
                                        <div className="font-bold">{agent.name}</div>
                                        <div className="text-muted-foreground">{agent.isActive ? agent.activity || "Active" : "Paused"}</div>
                                    </TooltipContent>
                                </Tooltip>
                            )
                        })}
                    </div>
                </TooltipProvider>
            </div>

            {/* Activity Log (Compact) */}
            <div className="px-4 pb-3 space-y-1.5 max-h-32 overflow-y-auto">
                {agents.filter(a => a.isActive && a.activity).slice(0, 3).map(agent => {
                    const config = AGENT_ICONS[agent.id] || { color: "text-muted-foreground" }
                    return (
                        <div key={agent.id} className="flex items-center gap-2 text-[10px]">
                            <span className={`font-bold uppercase ${config.color}`}>{agent.id.slice(0, 6)}</span>
                            <span className="text-muted-foreground">→</span>
                            <span className="truncate">{agent.activity}</span>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
