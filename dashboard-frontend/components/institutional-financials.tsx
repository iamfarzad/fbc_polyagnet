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
        <div className="space-y-3 font-mono">
            <h3 className="text-[9px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                <Landmark className="h-3 w-3 text-emerald-500" />
                Capital Efficiency
            </h3>

            <div className="grid grid-cols-2 gap-2">
                {/* Main PnL */}
                <Tooltip>
                    <TooltipTrigger asChild>
                        <div className="bg-card border border-border/40 p-2 rounded-sm flex flex-col justify-between h-[60px] group hover:border-emerald-500/30 transition-colors shadow-sm">
                            <span className="text-[8px] text-muted-foreground uppercase font-bold tracking-tight">Instant Settled PnL</span>
                            <div className="flex items-center gap-2">
                                <Zap className="h-3 w-3 text-emerald-500 fill-emerald-500" />
                                <span className="text-lg font-bold text-emerald-500 leading-none">
                                    +${scalpTotal.toFixed(2)}
                                </span>
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
                        <div className="bg-card border border-border/40 p-2 rounded-sm flex flex-col justify-between h-[60px] group hover:border-blue-500/30 transition-colors shadow-sm">
                            <div className="flex justify-between items-start">
                                <span className="text-[8px] text-muted-foreground uppercase font-bold tracking-tight">Maker Rebate</span>
                                <div className="text-[8px] text-blue-400/50 font-bold border border-blue-400/20 px-1 py-0 rounded-[2px]">
                                    3.5 BPS
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="text-lg font-bold text-blue-400 leading-none">
                                    +${rebate.toFixed(2)}
                                </span>
                            </div>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="bg-blue-500 border-none text-white font-bold uppercase text-[9px]">
                        Estimated liquidity provider rewards
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
