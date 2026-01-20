"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AlertTriangle, Zap, ShieldAlert, Crosshair } from "lucide-react"
import { toast } from "sonner"

export function WarRoom() {
    const [marketId, setMarketId] = useState("")
    const [amount, setAmount] = useState("5")
    const [loading, setLoading] = useState(false)

    const executeManualTrade = async (action: string) => {
        if (!marketId) {
            toast.error("Market ID required")
            return
        }

        setLoading(true)
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/manual/trade`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action,
                    market_id: marketId,
                    amount: parseFloat(amount),
                    reason: "Manual Override from War Room"
                })
            })

            if (!res.ok) throw new Error("Failed to queue")

            const data = await res.json()
            toast.success(`Trade Queued! (Queue Pos: ${data.queue_length})`)
        } catch (e) {
            toast.error("Failed to execute manual trade")
        } finally {
            setLoading(false)
        }
    }

    const emergencyStop = async () => {
        if (!confirm("ARE YOU SURE? THIS WILL STOP ALL AGENTS.")) return;
        try {
            await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/emergency-stop`, { method: "POST" })
            toast.error("🚨 EMERGENCY STOP ACTIVATED")
        } catch (e) {
            toast.error("Failed to stop")
        }
    }

    return (
        <Card className="w-full border-red-900/30 bg-red-950/5">
            <CardHeader>
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                        <ShieldAlert className="text-red-600 h-6 w-6" />
                        <div>
                            <CardTitle className="text-red-700 dark:text-red-400">War Room</CardTitle>
                            <CardDescription>Manual Overrides & Emergency Controls</CardDescription>
                        </div>
                    </div>
                    <Button variant="destructive" onClick={emergencyStop} className="animate-pulse font-bold">
                        <AlertTriangle className="mr-2 h-4 w-4" /> KILL SWITCH (ALL STOP)
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="space-y-6">
                <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>Warning: Manual Override</AlertTitle>
                    <AlertDescription>
                        Manual trades bypass all risk checks (Daily Loss, Max drawdown, etc). Use with extreme caution.
                    </AlertDescription>
                </Alert>

                <div className="grid gap-4 p-4 border rounded-lg bg-background">
                    <h3 className="font-semibold flex items-center gap-2">
                        <Crosshair className="h-4 w-4" /> Tactical Nuke (Force Trade)
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Market ID / URL Slug</Label>
                            <Input
                                placeholder="e.g. 0x123... or active-market-slug"
                                value={marketId}
                                onChange={(e) => setMarketId(e.target.value)}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Amount (USDC)</Label>
                            <Input
                                type="number"
                                value={amount}
                                onChange={(e) => setAmount(e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 pt-2">
                        <Button
                            className="bg-green-600 hover:bg-green-700 w-full"
                            onClick={() => executeManualTrade("FORCE_BUY_YES")}
                            disabled={loading}
                        >
                            <Zap className="mr-2 h-4 w-4" /> FORCE BUY YES
                        </Button>
                        <Button
                            className="bg-red-600 hover:bg-red-700 w-full"
                            onClick={() => executeManualTrade("FORCE_BUY_NO")}
                            disabled={loading}
                        >
                            <Zap className="mr-2 h-4 w-4" /> FORCE BUY NO
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
