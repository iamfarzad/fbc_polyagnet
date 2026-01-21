"use client"

import { Zap } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

export interface FinancialsProps {
    data: {
        total_redeemed: number
        gasSpent: number
        balance: number
        costs: {
            openai: number
            perplexity: number
            gemini: number
            fly: number
            neural_total: number
            infra_total: number
        }
        instant_scalp_total: number
        estimated_rebate: number
        compounding_velocity: number
    }
}

export function FinancialsCard({ data }: FinancialsProps) {
    if (!data) return null

    // Safety checks for new fields
    const scalpTotal = data.instant_scalp_total || 0
    const rebate = data.estimated_rebate || 0
    const flyCost = data.costs?.fly || 0
    const roi = ((scalpTotal / 150) * 100).toFixed(2)

    return (
        <Card className="rounded-xl border border-border/40 glass bg-slate-950/50 overflow-hidden h-full flex flex-col justify-between">
            <div className="p-4 flex-1 flex flex-col justify-center gap-4">
                <div className="flex justify-between items-center mb-1">
                    <h3 className="text-[10px] text-emerald-500 font-bold uppercase tracking-wider flex items-center gap-2 font-mono">
                        <Zap className="h-3 w-3 fill-emerald-500" /> Scalper Performance
                    </h3>
                    <Badge variant="outline" className="text-[9px] border-emerald-500/30 text-emerald-500 animate-pulse bg-emerald-500/5">
                        LIVE: 48 CYCLE MODE
                    </Badge>
                </div>

                <div className="space-y-4">
                    {/* Instant Profits: The 1.5% Snipe */}
                    <div className="bg-emerald-500/10 p-4 rounded-lg border border-emerald-500/20 shadow-inner">
                        <div className="flex justify-between items-end">
                            <span className="text-[10px] text-emerald-400/80 uppercase font-bold tracking-tight">Instant Scalp Profits</span>
                            <span className="text-2xl font-mono text-emerald-400 font-bold">
                                +${scalpTotal.toFixed(2)}
                            </span>
                        </div>
                    </div>

                    {/* Daily Rebates: The USDC Bonus */}
                    <div className="bg-blue-500/10 p-4 rounded-lg border border-blue-500/20 shadow-inner">
                        <div className="flex justify-between items-end">
                            <span className="text-[10px] text-blue-400/80 uppercase font-bold tracking-tight">Pending Maker Rebates</span>
                            <span className="text-2xl font-mono text-blue-400 font-bold">
                                ~${rebate.toFixed(2)}
                            </span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3 pt-1 text-center">
                        <div className="p-2 border border-border/20 rounded bg-card/30 flex flex-col justify-center">
                            <p className="text-[9px] text-muted-foreground uppercase font-semibold">Cloud Overhead</p>
                            <p className="text-xs font-mono text-red-400 font-bold">-${flyCost.toFixed(2)}</p>
                        </div>
                        <div className="p-2 border border-border/20 rounded bg-card/30 flex flex-col justify-center">
                            <p className="text-[9px] text-muted-foreground uppercase font-semibold">Net Daily ROI</p>
                            <p className="text-xs font-mono text-white font-bold">{roi}%</p>
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    )
}
