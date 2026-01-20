"use client"

import { AgentCard } from "./agent-card"

// Types match what we expect from the API/Parent
export interface AgentStatus {
    id: string
    name: string
    isActive: boolean
    lastActive?: number
    stats?: {
        dailyPnL: number
        tradeCount: number
    }
}

interface AgentControlCenterProps {
    agents: AgentStatus[]
    onToggleAgent: (agentId: string, newState: boolean) => void
}

export function AgentControlCenter({ agents, onToggleAgent }: AgentControlCenterProps) {
    return (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 2xl:grid-cols-1">
            {agents.map((agent) => (
                <AgentCard
                    key={agent.id}
                    id={agent.id}
                    name={agent.name}
                    isActive={agent.isActive}
                    lastActive={agent.lastActive || Date.now()} // Fallback if missing
                    dailyPnL={agent.stats?.dailyPnL ?? 0}
                    tradeCount={agent.stats?.tradeCount ?? 0}
                    onToggle={(newState) => onToggleAgent(agent.id, newState)}
                />
            ))}
        </div>
    )
}
