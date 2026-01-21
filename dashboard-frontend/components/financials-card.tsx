import { Card, CardContent } from "@/components/ui/card"
import { DollarSign } from "lucide-react"
import { Separator } from "@/components/ui/separator"

interface FinancialsProps {
    data: {
        total_redeemed: number
        gasSpent: number
        unrealizedPnl: number
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
    // Calculate True Net PnL
    // Formula: Unrealized PnL + Redeemed - Gas - Neural Costs - Infra Costs
    const totalOverhead = data.costs.neural_total + data.costs.infra_total
    const trueNetPnl = (data.unrealizedPnl + data.total_redeemed) - data.gasSpent - totalOverhead

    return (
        <Card className="border-border/40 glass">
            <div className="p-4">
                <h3 className="text-[10px] text-amber-500 font-bold mb-3 uppercase tracking-wider flex items-center gap-2">
                    <DollarSign className="h-3 w-3" /> Financials
                </h3>

                <div className="space-y-2 text-xs">
                    {/* Revenue Top Line */}
                    <div className="flex justify-between items-center">
                        <span className="text-muted-foreground">Total Redeemed:</span>
                        <span className="text-emerald-400 font-mono">${data.total_redeemed.toFixed(2)}</span>
                    </div>

                    <Separator className="bg-border/20 my-2" />

                    {/* Neural Breakdown */}
                    <div className="flex justify-between items-center text-[10px]">
                        <span className="text-muted-foreground">OpenAI (Auditor):</span>
                        <span className="text-red-400 font-mono">-${data.costs.openai.toFixed(4)}</span>
                    </div>
                    <div className="flex justify-between items-center text-[10px]">
                        <span className="text-muted-foreground">Perplexity (Research):</span>
                        <span className="text-blue-400 font-mono">-${data.costs.perplexity.toFixed(3)} [Credit]</span>
                    </div>
                    <div className="flex justify-between items-center text-[10px]">
                        <span className="text-muted-foreground">Gemini (Fallback):</span>
                        <span className="text-emerald-500 font-mono">$0.00 [Free]</span>
                    </div>

                    {/* Infra Breakdown */}
                    <div className="flex justify-between items-center text-[10px] mt-1">
                        <span className="text-muted-foreground font-semibold">Fly.io (8x Cluster):</span>
                        <span className="text-red-400 font-mono">-${data.costs.fly.toFixed(3)}</span>
                    </div>

                    {/* Gas */}
                    <div className="flex justify-between items-center text-[10px] mt-1">
                        <span className="text-muted-foreground">Polygon Gas (Est):</span>
                        <span className="text-red-400/80 font-mono">-${data.gasSpent.toFixed(2)}</span>
                    </div>

                    <Separator className="bg-border/20 my-2" />

                    {/* Scalper Intel */}
                    <div className="mt-4 space-y-1 bg-emerald-500/5 p-2 rounded border border-emerald-500/10">
                        <div className="flex justify-between items-center text-[9px] text-emerald-500 font-bold uppercase">
                            <span>Scalper Intel</span>
                            <span className="animate-pulse">● Instant</span>
                        </div>
                        <div className="flex justify-between items-center text-xs">
                            <span className="text-muted-foreground">Scalp Profits:</span>
                            <span className="text-emerald-400">
                                +${data.scalp_profits_instant.toFixed(2)}
                            </span>
                        </div>
                        <div className="flex justify-between items-center text-[10px]">
                            <span className="text-muted-foreground">Velocity:</span>
                            <span className="text-emerald-500/80">{data.compounding_velocity}x / day</span>
                        </div>

                        <Separator className="bg-border/20 my-1" />

                        <div className="flex justify-between items-center text-[10px]">
                            <span className="text-muted-foreground">Pending Rebate:</span>
                            <span className="text-blue-400">
                                +${data.estimated_rebate_daily.toFixed(2)} (Daily)
                            </span>
                        </div>
                    </div>

                    <Separator className="bg-border/20 my-2" />

                    {/* True Net PnL */}
                    <div className="flex justify-between items-center font-bold">
                        <span className="text-slate-300">TRUE NET PNL:</span>
                        <span className={`font-mono ${trueNetPnl >= 0 ? "text-emerald-400" : "text-rose-500"}`}>
                            ${trueNetPnl.toFixed(2)}
                        </span>
                    </div>
                </div>
            </div>
        </Card>
    )
}
