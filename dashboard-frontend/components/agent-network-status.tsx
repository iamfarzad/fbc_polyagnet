import { useState } from "react"
import { Cpu, Activity, Clock, Loader2, Info } from "lucide-react"
import { Switch } from "@/components/ui/switch"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { toast } from "sonner"
import { getApiUrl } from "@/lib/api-url"

interface Agent {
    id: string
    name: string
    isActive: boolean
    activity: string
    heartbeat?: number | string
}

interface AgentNetworkStatusProps {
    agents: Agent[]
}

const AGENT_NAMES: Record<string, string> = {
    safe: "safe",
    scalper: "scalper",
    copy: "copyTrader",   // Map API ID to Toggle ID if different
    copyTrader: "copyTrader",
    smart: "smartTrader",
    smartTrader: "smartTrader",
    esports: "esportsTrader",
    esportsTrader: "esportsTrader",
    sport: "sportsTrader",
    sportsTrader: "sportsTrader"
}

export function AgentNetworkStatus({ agents }: AgentNetworkStatusProps) {
    const [loadingId, setLoadingId] = useState<string | null>(null)

    // Process agents with heartbeat logic
    const processedAgents = agents.map(agent => {
        let isAlive = agent.isActive;
        let timeAgo = "N/A";
        let secondsAgo = 999999;

        if (agent.heartbeat) {
            const hbTime = typeof agent.heartbeat === 'string'
                ? new Date(agent.heartbeat).getTime()
                : agent.heartbeat * 1000;

            const now = Date.now();
            secondsAgo = Math.floor((now - hbTime) / 1000);
            timeAgo = `${secondsAgo}s ago`;

            // Force offline if > 60s
            if (secondsAgo > 60) {
                isAlive = false;
            }
        }

        return { ...agent, isAlive, timeAgo, secondsAgo };
    });

    const runningAgents = processedAgents.filter(a => a.isAlive);

    const toggleAgent = async (agentId: string, currentState: boolean) => {
        setLoadingId(agentId)
        try {
            // Map simple ID to backend expected toggle ID
            const target = AGENT_NAMES[agentId] || agentId

            const res = await fetch(`${getApiUrl()}/api/toggle-agent`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ agent: target })
            })

            if (!res.ok) throw new Error("Failed to toggle")
            toast.success(`${agentId.toUpperCase()} ${!currentState ? "Started" : "Paused"}`)
        } catch (error) {
            toast.error(`Failed to toggle ${agentId}`)
        } finally {
            setLoadingId(null)
        }
    }

    return (
        <div className="space-y-4 font-mono">
            <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                <Cpu className="h-3 w-3 text-emerald-500" />
                Neural Grid Status
            </h3>

            <div className="grid grid-cols-2 gap-2">
                {processedAgents.map((agent) => (
                    <div
                        key={agent.id}
                        className={`bg-card border ${agent.isAlive ? 'border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.05)]' : 'border-border/40'} p-2 rounded-sm flex justify-between items-center transition-all group h-[50px]`}
                    >
                        <div className="flex flex-col gap-0.5">
                            <div className="flex items-center gap-2">
                                <span className={`text-[9px] font-bold uppercase tracking-tight ${agent.isAlive ? 'text-foreground' : 'text-muted-foreground'}`}>
                                    {agent.id.replace(/([A-Z])/g, '_$1').toUpperCase()}
                                </span>
                            </div>
                            <span className="text-[8px] text-muted-foreground truncate max-w-[80px]">
                                {loadingId === agent.id ? "UPDATING..." : (agent.activity || "LISTENING")}
                            </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <Switch
                                checked={agent.isActive} // Use raw active state for switch, not 'isAlive' (heartbeat)
                                onCheckedChange={() => toggleAgent(agent.id, agent.isActive)}
                                disabled={loadingId === agent.id}
                                className="scale-50 data-[state=checked]:bg-emerald-500 origin-right"
                            />
                        </div>
                    </div>
                ))}
            </div>

            <div className="flex justify-between items-center pt-1 px-1">
                <span className="text-[9px] text-muted-foreground font-bold uppercase tracking-widest">Active_Node_Count</span>
                <span className="text-[10px] text-emerald-500 font-bold">{runningAgents.length} / {agents.length}</span>
            </div>
        </div>
    )
}

