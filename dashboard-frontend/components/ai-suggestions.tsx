"use client"

import { Lightbulb, TrendingUp, AlertTriangle, Zap, ExternalLink } from "lucide-react"

interface Suggestion {
    id: string
    icon: "tip" | "warning" | "trend" | "action"
    title: string
    savings?: string
    actionUrl?: string
}

interface AISuggestionsProps {
    suggestions?: Suggestion[]
    potentialSavings?: string
}

const ICONS = {
    tip: Lightbulb,
    warning: AlertTriangle,
    trend: TrendingUp,
    action: Zap,
}

const DEFAULT_SUGGESTIONS: Suggestion[] = [
    { id: "1", icon: "tip", title: "Enable Scalper during high volatility", savings: "+$15/day" },
    { id: "2", icon: "trend", title: "SOL momentum detected - consider position", savings: "+$8 potential" },
    { id: "3", icon: "warning", title: "esportsTrader has no active matches", savings: "" },
    { id: "4", icon: "action", title: "Redeem 2 settled positions", savings: "+$12.50" },
]

export function AISuggestions({ suggestions = DEFAULT_SUGGESTIONS, potentialSavings = "+$35/day" }: AISuggestionsProps) {
    return (
        <div className="rounded-xl border border-border/40 bg-card/30 backdrop-blur-sm overflow-hidden h-full flex flex-col">
            {/* Header */}
            <div className="px-4 py-2.5 border-b border-border/30 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Lightbulb className="h-3.5 w-3.5 text-amber-400" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">AI Suggestions</span>
                </div>
                <span className="text-[10px] text-emerald-400 font-medium">{potentialSavings} potential</span>
            </div>

            {/* Suggestions List */}
            <div className="flex-1 overflow-y-auto">
                {suggestions.map((suggestion) => {
                    const Icon = ICONS[suggestion.icon] || Lightbulb
                    const iconColor = {
                        tip: "text-amber-400",
                        warning: "text-orange-400",
                        trend: "text-emerald-400",
                        action: "text-violet-400",
                    }[suggestion.icon]

                    return (
                        <div
                            key={suggestion.id}
                            className="px-4 py-3 border-b border-border/20 hover:bg-muted/10 transition-colors cursor-pointer flex items-start gap-3"
                        >
                            <Icon className={`h-4 w-4 ${iconColor} shrink-0 mt-0.5`} />
                            <div className="flex-1 min-w-0">
                                <p className="text-xs text-foreground truncate">{suggestion.title}</p>
                            </div>
                            {suggestion.savings && (
                                <span className="text-[10px] text-emerald-400 font-medium shrink-0">{suggestion.savings}</span>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
