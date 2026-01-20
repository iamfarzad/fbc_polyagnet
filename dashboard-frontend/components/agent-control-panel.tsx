"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Loader2, Settings, Power, Activity, TrendingUp, DollarSign } from "lucide-react"
import { toast } from "sonner"

interface AgentData {
    running: boolean
    activity?: string
    endpoint?: string
    markets?: number
    prices?: Record<string, number>
    lastSignal?: string
    lastScan?: string
    positions?: number
    trades?: number
    mode?: string
    pnl?: number
    strategy?: string
}

interface AgentControlPanelProps {
    data: Record<string, AgentData>
    maxBet: number
}

// Map frontend keys to friendly names
const AGENT_NAMES: Record<string, string> = {
    safe: "Safe Agent",
    scalper: "Scalper Agent",
    copyTrader: "Copy Trader",
    smartTrader: "Smart Politics",
    esportsTrader: "Esports Trader",
    sportsTrader: "Sports Trader"
}

// Map keys to API IDs
const API_KEYS: Record<string, string> = {
    safe: "safe",
    scalper: "scalper",
    copyTrader: "copy",
    smartTrader: "smart",
    esportsTrader: "esports",
    sportsTrader: "sport"
}

export function AgentControlPanel({ data, maxBet }: AgentControlPanelProps) {
    const [loading, setLoading] = useState<string | null>(null)

    // Local state for optimistic updates
    const [localData, setLocalData] = useState(data)

    const toggleAgent = async (agentKey: string, currentState: boolean) => {
        setLoading(agentKey)
        try {
            // Optimistic update
            setLocalData(prev => ({
                ...prev,
                [agentKey]: { ...prev[agentKey], running: !currentState }
            }))

            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/toggle-agent`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ agent: agentKey })
            })

            if (!res.ok) throw new Error("Failed to toggle")

            toast.success(`${AGENT_NAMES[agentKey]} ${!currentState ? "Started" : "Paused"}`)
        } catch (error) {
            // Revert
            setLocalData(prev => ({
                ...prev,
                [agentKey]: { ...prev[agentKey], running: currentState }
            }))
            toast.error("Failed to toggle agent")
        } finally {
            setLoading(null)
        }
    }

    const updateConfig = async (key: string, value: number) => {
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/update-config`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ key, value })
            })
            if (!res.ok) throw new Error("Failed to update")
            toast.success("Config updated")
        } catch (e) {
            toast.error("Failed to update config")
        }
    }

    return (
        <Card className="w-full">
            <CardHeader>
                <div className="flex justify-between items-center">
                    <div>
                        <CardTitle>Swarm Control Center</CardTitle>
                        <CardDescription>Manage active agents and parameters</CardDescription>
                    </div>
                    <Dialog>
                        <DialogTrigger asChild>
                            <Button variant="outline" size="sm">
                                <Settings className="w-4 h-4 mr-2" />
                                Global Config
                            </Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader>
                                <DialogTitle>Global Parameters</DialogTitle>
                            </DialogHeader>
                            <div className="space-y-6 py-4">
                                <div className="space-y-2">
                                    <Label>Max Bet Size (USDC)</Label>
                                    <div className="flex items-center gap-4">
                                        <Slider
                                            defaultValue={[maxBet]} max={50} step={0.5}
                                            onValueCommit={(v) => updateConfig("max_bet", v[0])}
                                        />
                                        <span className="font-mono">{maxBet.toFixed(2)}</span>
                                    </div>
                                    <p className="text-xs text-muted-foreground">Applies to all agents unless overridden.</p>
                                </div>
                            </div>
                        </DialogContent>
                    </Dialog>
                </div>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {Object.entries(localData).map(([key, info]) => (
                        <Card key={key} className={`border-l-4 ${info.running ? "border-l-green-500" : "border-l-secondary"}`}>
                            <CardContent className="p-4 space-y-4">
                                <div className="flex justify-between items-start">
                                    <div className="space-y-1">
                                        <h3 className="font-semibold flex items-center gap-2">
                                            {AGENT_NAMES[key] || key}
                                        </h3>
                                        <Badge variant={info.running ? "default" : "secondary"} className="text-xs">
                                            {info.running ? "RUNNING" : "PAUSED"}
                                        </Badge>
                                    </div>
                                    <Switch
                                        checked={info.running}
                                        onCheckedChange={() => toggleAgent(key, info.running)}
                                        disabled={loading === key}
                                    />
                                </div>

                                <div className="space-y-2 text-sm bg-muted/50 p-2 rounded-md">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">Activity:</span>
                                        <span className="truncate max-w-[120px]" title={info.activity}>{info.activity}</span>
                                    </div>
                                    {info.mode && (
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Mode:</span>
                                            <span className={info.mode.includes("LIVE") ? "text-red-500 font-bold" : "text-yellow-600"}>
                                                {info.mode}
                                            </span>
                                        </div>
                                    )}
                                    {info.trades !== undefined && (
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Trades:</span>
                                            <span>{info.trades}</span>
                                        </div>
                                    )}
                                    {info.lastScan && (
                                        <div className="flex justify-between">
                                            <span className="text-muted-foreground">Last Scan:</span>
                                            <span>{info.lastScan}</span>
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </CardContent>
        </Card>
    )
}
