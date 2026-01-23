import { Zap, Timer } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface VelocityTrackerProps {
    tradeCount: number
    dailyGoal?: number
}

export function VelocityTracker({ tradeCount, dailyGoal = 100 }: VelocityTrackerProps) {
    const progress = Math.min((tradeCount / dailyGoal) * 100, 100)

    return (
        <div className="space-y-4 font-mono">
            <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                <Timer className="h-3 w-3 text-emerald-500" />
                Execution Velocity
            </h3>

            <Tooltip>
                <TooltipTrigger asChild>
                    <div className="bg-card border border-border/40 p-4 rounded-sm space-y-4 shadow-sm relative overflow-hidden group hover:border-emerald-500/20 transition-colors">
                        <div className="flex justify-between items-end relative z-10">
                            <div className="flex flex-col">
                                <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-tight">Cycle Count (24H)</span>
                                <div className="flex items-center gap-2">
                                    <Zap className="h-3 w-3 text-emerald-500 fill-emerald-500" />
                                    <span className="text-xl font-bold text-foreground leading-none">
                                        {tradeCount} / {dailyGoal}
                                    </span>
                                </div>
                            </div>
                            <div className="text-right flex flex-col items-end">
                                <span className="text-[10px] text-muted-foreground uppercase font-bold tracking-tight">Efficiency</span>
                                <span className="text-sm font-bold text-emerald-500">
                                    {progress.toFixed(1)}%
                                </span>
                            </div>
                        </div>

                        <div className="h-1.5 w-full bg-muted/20 rounded-full overflow-hidden relative z-10 border border-border/40">
                            <div
                                className="h-full bg-emerald-500 transition-all duration-1000 ease-out shadow-[0_0_8px_rgba(16,185,129,0.3)]"
                                style={{ width: `${progress}%` }}
                            />
                        </div>

                        <div className="text-[9px] text-muted-foreground/60 font-bold uppercase tracking-widest text-center relative z-10 pt-1">
                            Target_Frequency: {(dailyGoal / 24).toFixed(1)} Cycles Per Hour
                        </div>
                    </div>
                </TooltipTrigger>
                <TooltipContent side="right" className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px] max-w-[200px]">
                    Frequency of HFT execution cycles in the last 24 hours relative to the daily liquidity capture target.
                </TooltipContent>
            </Tooltip>
        </div>
    )
}

