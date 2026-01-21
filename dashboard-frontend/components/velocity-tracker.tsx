"use client"

import { Zap, Timer } from "lucide-react"

interface VelocityTrackerProps {
    tradeCount: number
}

export function VelocityTracker({ tradeCount }: VelocityTrackerProps) {
    const goals = 248
    const progress = Math.min((tradeCount / goals) * 100, 100)

    return (
        <div className="space-y-4 font-mono">
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                <Timer className="h-3 w-3 text-emerald-500" />
                Execution Velocity
            </h3>

            <div className="bg-slate-900/50 border border-white/5 p-4 rounded-sm space-y-4 shadow-inner relative overflow-hidden group hover:border-emerald-500/20 transition-colors">
                <div className="flex justify-between items-end relative z-10">
                    <div className="flex flex-col">
                        <span className="text-[10px] text-slate-500 uppercase font-bold tracking-tight">Cycle Count (24H)</span>
                        <div className="flex items-center gap-2">
                            <Zap className="h-3 w-3 text-emerald-500 fill-emerald-500" />
                            <span className="text-xl font-bold text-white leading-none">
                                {tradeCount} / {goals}
                            </span>
                        </div>
                    </div>
                    <div className="text-right flex flex-col items-end">
                        <span className="text-[10px] text-slate-500 uppercase font-bold tracking-tight">Efficiency</span>
                        <span className="text-sm font-bold text-emerald-500">
                            {progress.toFixed(1)}%
                        </span>
                    </div>
                </div>

                <div className="h-1 w-full bg-black/40 rounded-full overflow-hidden relative z-10 border border-white/5">
                    <div
                        className="h-full bg-emerald-500 transition-all duration-1000 ease-out shadow-[0_0_8px_rgba(16,185,129,0.3)]"
                        style={{ width: `${progress}%` }}
                    />
                </div>

                <div className="text-[9px] text-slate-600 font-bold uppercase tracking-widest text-center relative z-10 pt-1">
                    Target_Frequency: 48 Cycles Per Hour
                </div>
            </div>
        </div>
    )
}
