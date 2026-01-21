"use client"

import { Zap } from "lucide-react"

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
        scalp_profits_instant: number
        estimated_rebate_daily: number
        compounding_velocity: number
    }
}

export function FinancialsCard({ data }: FinancialsProps) {
    if (!data) return null

    // Safety checks for new fields
    const scalpProfit = data.scalp_profits_instant || 0
    const rebate = data.estimated_rebate_daily || 0
    const flyCost = data.costs?.fly || 0
    // Net ROI based on initial $150 allocation. 
    // If balance includes profit, we should use base. Assuming constant base 150 for calc.
    const roi = ((scalpProfit / 150) * 100).toFixed(2)

    return (
        <div className="rounded-xl border border-border/40 glass bg-slate-950/50 overflow-hidden h-full flex flex-col justify-between">
            <div className="p-4 flex-1 flex flex-col justify-center gap-3">
                <div className="flex justify-between items-center mb-1">
                    <h3 className="text-[10px] text-emerald-500 font-bold uppercase tracking-wider flex items-center gap-2">
                        <Zap className="h-3 w-3 fill-emerald-500" /> Scalper Performance
                    </h3>
                    <div className="text-[9px] border border-emerald-500/30 text-emerald-500 px-2 py-0.5 rounded-full animate-pulse flex items-center gap-1">
                        <span className="w-1 h-1 bg-emerald-500 rounded-full" /> LIVE CYCLE
                    </div>
                </div>

                <div className="space-y-3">
                    {/* Primary Scalp Profit (Instant) */}
                    <div className="bg-emerald-500/10 p-3 rounded-lg border border-emerald-500/20">
                        <div className="flex justify-between items-end">
                            <span className="text-[10px] text-emerald-400/80 uppercase font-medium">Instant Scalp Profits</span>
                            <span className="text-xl font-mono text-emerald-400 font-bold">
                                +${scalpProfit.toFixed(2)}
                            </span>
                        </div>
                    </div>

                    {/* Secondary Rebate (Daily) */}
                    <div className="bg-blue-500/10 p-3 rounded-lg border border-blue-500/20">
                        <div className="flex justify-between items-end">
                            <span className="text-[10px] text-blue-400/80 uppercase font-medium">Pending Maker Rebates</span>
                            <span className="text-xl font-mono text-blue-400 font-bold">
                                ~${rebate.toFixed(2)}
                            </span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 pt-1">
                        <div className="text-center p-2 border border-border/20 rounded bg-card/30">
                            <p className="text-[9px] text-muted-foreground uppercase">Cloud Overhead</p>
                            <p className="text-xs font-mono text-red-400">-${flyCost.toFixed(4)}</p>
                        </div>
                        <div className="text-center p-2 border border-border/20 rounded bg-card/30">
                            <p className="text-[9px] text-muted-foreground uppercase">Net ROI (150)</p>
                            <p className={`text-xs font-mono font-bold ${Number(roi) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{roi}%</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
