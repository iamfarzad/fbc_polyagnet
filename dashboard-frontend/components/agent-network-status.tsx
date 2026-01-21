"use client"

import { Cpu, Activity } from "lucide-react"

interface Agent {
    id: string
    name: string
    isActive: boolean
    activity: string
}

interface AgentNetworkStatusProps {
    agents: Agent[]
}

export function AgentNetworkStatus({ agents }: AgentNetworkStatusProps) {
    const runningAgents = agents.filter(a => a.isActive)

    return (
        <div className="space-y-4 font-mono">
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                <Cpu className="h-3 w-3 text-emerald-500" />
                Neural Grid Status
            </h3>

            <div className="grid gap-2">
                {agents.map((agent) => (
                    <div
                        key={agent.id}
                        className={`bg-slate-900/50 border ${agent.isActive ? 'border-emerald-500/20' : 'border-white/5 opacity-50'} p-3 rounded-sm flex justify-between items-center transition-all`}
                    >
                        <div className="flex flex-col gap-0.5">
                            <span className={`text-[10px] font-bold uppercase tracking-tight ${agent.isActive ? 'text-white' : 'text-slate-500'}`}>
                                {agent.id.replace(/([A-Z])/g, '_$1').toUpperCase()}
                            </span>
                            <span className="text-[9px] text-slate-500 truncate max-w-[180px]">
                                {agent.activity || "LISTENING_STATE"}
                            </span>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className={`h-1.5 w-1.5 rounded-full ${agent.isActive ? 'bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)] animate-pulse' : 'bg-slate-700'}`} />
                            <span className={`text-[9px] font-bold uppercase ${agent.isActive ? 'text-emerald-500' : 'text-slate-700'}`}>
                                {agent.isActive ? "ONLINE" : "OFFLINE"}
                            </span>
                        </div>
                    </div>
                ))}
            </div>

            <div className="flex justify-between items-center pt-1 px-1">
                <span className="text-[9px] text-slate-500 font-bold uppercase tracking-widest">Active_Node_Count</span>
                <span className="text-[10px] text-emerald-500 font-bold">{runningAgents.length} / {agents.length}</span>
            </div>
        </div>
    )
}
