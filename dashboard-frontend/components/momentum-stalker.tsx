import { Activity } from "lucide-react"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface MomentumStalkerProps {
    data: {
        agents: Record<string, { running: boolean; activity: string; lastSignal?: string }>
    }
}

export function MomentumStalker({ data }: MomentumStalkerProps) {
    const activity = data.agents?.scalper?.activity || ""

    // Extract momentum if present in activity string
    // Expected format: "STALKING | 12 markets | BTC: $64,231 ... | MOM 0.0002"
    const momMatch = activity.match(/MOM\s+([\d.]+)/i)
    const currentMom = momMatch ? parseFloat(momMatch[1]) : 0
    const trigger = 0.0005
    const progress = Math.min((currentMom / trigger) * 100, 100)

    // Status text logic
    const isStalking = activity.includes("STALKING") || activity.includes("Scanning")
    const statusText = isStalking
        ? `STALKING: BTC MOM ${currentMom.toFixed(4)} < ${trigger} (Waiting)`
        : activity || "SYSTEM_IDLE"

    return (
        <div className="h-full flex flex-col gap-4 font-mono group">
            <div className="flex justify-between items-center">
                <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                    <Activity className="h-3 w-3 text-emerald-500 animate-pulse" />
                    Momentum Heatmap
                </h3>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <span className="text-[10px] font-bold text-emerald-500/80 bg-emerald-500/5 px-2 py-0.5 rounded-sm border border-emerald-500/10 cursor-help">
                            SENSITIVITY: {trigger}
                        </span>
                    </TooltipTrigger>
                    <TooltipContent side="left" className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                        HFT trigger threshold for trade execution
                    </TooltipContent>
                </Tooltip>
            </div>

            <div className="flex-1 bg-card border border-border/40 rounded-sm p-4 flex flex-col justify-center gap-4 relative overflow-hidden shadow-sm">
                {/* Decorative Grid */}
                <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-background"
                    style={{ backgroundImage: 'linear-gradient(currentColor 1px, transparent 1px), linear-gradient(90deg, currentColor 1px, transparent 1px)', backgroundSize: '16px 16px' }} />

                <div className="relative z-10 space-y-2">
                    <div className="flex justify-between text-[10px] font-bold uppercase tracking-tight">
                        <span className="text-muted-foreground">Current Velocity</span>
                        <span className={currentMom >= trigger ? "text-emerald-500 font-black" : "text-amber-500"}>
                            {currentMom.toFixed(6)}
                        </span>
                    </div>

                    {/* Momentum Bar */}
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <div className="h-3 w-full bg-muted/10 border border-border/40 rounded-full overflow-hidden p-[2px] cursor-help">
                                <div
                                    className={`h-full rounded-full transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(16,185,129,0.2)] ${currentMom >= trigger ? 'bg-emerald-500' : 'bg-gradient-to-r from-emerald-500/20 to-emerald-500/60'}`}
                                    style={{ width: `${progress}%` }}
                                />
                            </div>
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                            {progress.toFixed(0)}% to execution threshold
                        </TooltipContent>
                    </Tooltip>
                </div>

                <div className="relative z-10 bg-muted/5 border border-border/40 p-3 rounded-sm shadow-inner overflow-hidden">
                    <div className="flex items-center gap-3 text-[10px]">
                        <div className={`h-2 w-2 rounded-full shrink-0 ${isStalking ? 'bg-emerald-500 animate-pulse' : 'bg-muted'}`} />
                        <span className="text-foreground font-bold tracking-tight truncate">
                            {statusText}
                        </span>
                    </div>
                </div>
            </div>
        </div>
    )
}
