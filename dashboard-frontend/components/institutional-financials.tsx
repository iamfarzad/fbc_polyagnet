import { Zap, Landmark, Server } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface InstitutionalFinancialsProps {
    data: {
        instant_scalp_total: number
        estimated_rebate: number
        costs: {
            fly: number
        }
    }
}

export function InstitutionalFinancials({ data }: InstitutionalFinancialsProps) {
    const scalpTotal = data?.instant_scalp_total || 0
    const rebate = data?.estimated_rebate || 0
    const flyCost = data?.costs?.fly || 0

    return (
        <div className="space-y-4 font-mono">
            <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                <Landmark className="h-3 w-3 text-emerald-500" />
                Capital Efficiency
            </h3>

            <div className="grid gap-3">
                {/* Main PnL */}
                <Tooltip>
                    <TooltipTrigger asChild>
                        <div className="bg-card border border-border/40 p-4 rounded-sm flex justify-between items-center group hover:border-emerald-500/30 transition-colors shadow-sm">
                            <div className="space-y-1">
                                <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-tight">Instant Settled PnL</span>
                                <div className="flex items-center gap-2">
                                    <Zap className="h-3 w-3 text-emerald-500 fill-emerald-500" />
                                    <span className="text-2xl font-bold text-emerald-500 leading-none">
                                        +${scalpTotal.toFixed(2)}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="bg-emerald-500 border-none text-white font-bold uppercase text-[9px]">
                        Profit from realized scalps (net of slippage)
                    </TooltipContent>
                </Tooltip>

                {/* Maker Rebate */}
                <Tooltip>
                    <TooltipTrigger asChild>
                        <div className="bg-card border border-border/40 p-4 rounded-sm flex justify-between items-center group hover:border-blue-500/30 transition-colors shadow-sm">
                            <div className="space-y-1">
                                <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-tight">Estimated Maker Rebate</span>
                                <div className="flex items-center gap-2">
                                    <span className="text-xl font-bold text-blue-400 leading-none">
                                        +${rebate.toFixed(2)}
                                    </span>
                                </div>
                            </div>
                            <div className="text-[10px] text-blue-400/50 font-bold border border-blue-400/20 px-1.5 py-0.5 rounded-sm">
                                3.5 BPS
                            </div>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="bg-blue-500 border-none text-white font-bold uppercase text-[9px]">
                        Estimated liquidity provider rewards from Polymarket
                    </TooltipContent>
                </Tooltip>
            </div>

            {/* Infrastructure Footnote */}
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className="pt-2 flex items-center gap-2 text-[10px] cursor-help">
                        <Server className="h-3 w-3 text-rose-500" />
                        <span className="text-muted-foreground uppercase font-bold tracking-tight">Infrastructure Overhead (Fly.io):</span>
                        <span className="text-rose-500 font-bold">-${flyCost.toFixed(2)}</span>
                    </div>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="bg-rose-500 border-none text-white font-bold uppercase text-[9px]">
                    Monthly hosting & operational compute costs
                </TooltipContent>
            </Tooltip>
        </div>
    )
}
