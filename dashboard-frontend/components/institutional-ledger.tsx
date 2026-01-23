import { useState } from "react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Loader2, HelpCircle } from "lucide-react"

interface Trade {
    time: string
    market: string
    side: string
    amount: number
}

interface Position {
    market: string
    side: string
    cost: number
    value: number
    pnl: number
}

interface Order {
    id: string
    market: string
    side: string // "BUY" | "SELL"
    price: number
    size: number
    status: string
}

interface InstitutionalLedgerProps {
    trades: Trade[]
    positions: Position[]
    openOrders: Order[]
}

export function InstitutionalLedger({ trades, positions, openOrders }: InstitutionalLedgerProps) {
    const [view, setView] = useState<"positions" | "activity" | "orders">("positions")
    const [positionFilter, setPositionFilter] = useState<"active" | "closed">("active")

    // Infer closed positions from trades
    const closedPositions = trades.filter(t =>
        t.side.includes("Shell") || t.side.includes("Redeem") || t.amount < 0 || t.side.toUpperCase().includes("SELL")
    ).map(t => ({
        market: t.market,
        side: t.side,
        cost: 0, // We don't track entry cost per trade easily here
        value: 0,
        pnl: t.amount, // Using amount as realized value/PnL proxy
        time: t.time
    }))

    const getHeaderInfo = () => {
        if (view === "activity") return `RECORDS: ${trades.length}`
        if (view === "positions" && positionFilter === "active") return `EXPOSURE: $${positions.reduce((acc, p) => acc + p.value, 0).toFixed(2)}`
        if (view === "positions" && positionFilter === "closed") return `CLOSED: ${closedPositions.length}`
        if (view === "orders") return `OPEN: ${openOrders.length}`
        return ""
    }

    return (
        <div className="h-full flex flex-col font-mono bg-background">
            {/* Ledger Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-border/40 shrink-0 bg-muted/20">
                <div className="flex gap-4">
                    <div className="flex gap-6">
                        <div className="flex flex-col">
                            <button
                                onClick={() => setView("positions")}
                                className={`text-sm font-bold pb-2 border-b-2 transition-all ${view === "positions" ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                            >
                                Positions
                            </button>
                        </div>
                        <button
                            onClick={() => setView("activity")}
                            className={`text-sm font-bold pb-2 border-b-2 transition-all ${view === "activity" ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                        >
                            Activity
                        </button>
                        <button
                            onClick={() => setView("orders")}
                            className={`text-sm font-bold pb-2 border-b-2 transition-all ${view === "orders" ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
                        >
                            Orders
                        </button>
                    </div>
                </div>
                <div className="text-[10px] text-muted-foreground tabular-nums font-bold">
                    {getHeaderInfo()}
                </div>
            </div>

            {/* Sub Tabs for Positions */}
            {view === "positions" && (
                <div className="px-4 py-2 border-b border-border/40 flex gap-2">
                    <button
                        onClick={() => setPositionFilter("active")}
                        className={`px-3 py-1 rounded-sm text-xs font-bold transition-colors ${positionFilter === "active" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50"}`}
                    >
                        Active
                    </button>
                    <button
                        onClick={() => setPositionFilter("closed")}
                        className={`px-3 py-1 rounded-sm text-xs font-bold transition-colors ${positionFilter === "closed" ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/50"}`}
                    >
                        Closed
                    </button>
                </div>
            )}

            {/* Ledger Table */}
            <div className="flex-1 overflow-auto custom-scrollbar">
                <Table>
                    <TableHeader className="bg-muted/40 sticky top-0 z-10 backdrop-blur-sm">
                        <TableRow className="border-border/40 hover:bg-transparent h-8">
                            {view === "activity" && (
                                <>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24">Timestamp</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-center">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Value</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-20 text-right">Status</TableHead>
                                </>
                            )}
                            {view === "positions" && positionFilter === "active" && (
                                <>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Avg</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Value</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">PnL</TableHead>
                                </>
                            )}
                            {view === "positions" && positionFilter === "closed" && (
                                <>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Entry</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Exit Value</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Realized</TableHead>
                                </>
                            )}
                            {view === "orders" && (
                                <>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Size</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Price</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-20 text-right">Status</TableHead>
                                </>
                            )}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {view === "activity" && trades.map((t, i) => (
                            <TableRow key={i} className="border-border/40 hover:bg-muted/30 h-8 transition-colors">
                                <TableCell className="text-[10px] text-muted-foreground py-1">{t.time.split(' ')[1] || t.time}</TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 truncate max-w-[400px] font-bold">{t.market}</TableCell>
                                <TableCell className="py-1 flex justify-center">
                                    <Tooltip>
                                        <TooltipTrigger asChild>
                                            <span className={`text-[9px] px-1.5 py-0.5 rounded-sm border font-bold cursor-help ${t.side.includes('Buy') ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-rose-500/10 border-rose-500/20 text-rose-500'}`}>
                                                {t.side.toUpperCase()}
                                            </span>
                                        </TooltipTrigger>
                                        <TooltipContent side="top" className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                                            Direction: {t.side.includes('Buy') ? 'Accumulation' : 'Distribution'}
                                        </TooltipContent>
                                    </Tooltip>
                                </TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 text-right font-bold tabular-nums">${Math.abs(t.amount).toFixed(2)}</TableCell>
                                <TableCell className="py-1 text-right">
                                    {t.side.includes("Chasing") ? (
                                        <div className="flex items-center justify-end gap-1.5 text-amber-500">
                                            <Loader2 className="h-2.5 w-2.5 animate-spin" />
                                            <span className="text-[9px] font-bold uppercase">Chasing</span>
                                        </div>
                                    ) : (
                                        <span className="text-[9px] text-emerald-500 font-bold uppercase">Filled</span>
                                    )}
                                </TableCell>
                            </TableRow>
                        ))}

                        {view === "positions" && positionFilter === "active" && positions.map((p, i) => (
                            <TableRow key={i} className="border-border/40 hover:bg-muted/30 h-8 transition-colors">
                                <TableCell className="text-[10px] text-foreground py-1 truncate max-w-[400px] font-bold">{p.market}</TableCell>
                                <TableCell className="py-1 text-right">
                                    <Badge variant="outline" className={`text-[9px] rounded-sm py-0 h-4 border-white/10 ${p.side.includes('Yes') ? 'text-emerald-500' : 'text-rose-500'}`}>
                                        {p.side.toUpperCase()}
                                    </Badge>
                                </TableCell>
                                <TableCell className="text-[10px] text-muted-foreground py-1 text-right tabular-nums">${p.cost.toFixed(2)}</TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 text-right font-bold tabular-nums">${p.value.toFixed(2)}</TableCell>
                                <TableCell className={`text-[10px] py-1 text-right font-bold tabular-nums ${p.pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                    {p.pnl >= 0 ? '+' : ''}{p.pnl.toFixed(2)}
                                </TableCell>
                            </TableRow>
                        ))}

                        {view === "positions" && positionFilter === "closed" && closedPositions.map((p, i) => (
                            <TableRow key={i} className="border-border/40 hover:bg-muted/30 h-8 transition-colors">
                                <TableCell className="text-[10px] text-foreground py-1 truncate max-w-[400px] font-bold">{p.market}</TableCell>
                                <TableCell className="py-1 text-right">
                                    <Badge variant="outline" className={`text-[9px] rounded-sm py-0 h-4 border-white/10 ${p.side.includes('Yes') ? 'text-emerald-500' : 'text-rose-500'}`}>
                                        {p.side.toUpperCase()}
                                    </Badge>
                                </TableCell>
                                <TableCell className="text-[10px] text-muted-foreground py-1 text-right tabular-nums">-</TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 text-right font-bold tabular-nums">${p.pnl.toFixed(2)}</TableCell>
                                <TableCell className={`text-[10px] py-1 text-right font-bold tabular-nums text-emerald-500`}>
                                    REALIZED
                                </TableCell>
                            </TableRow>
                        ))}

                        {view === "orders" && openOrders.map((o, i) => (
                            <TableRow key={i} className="border-border/40 hover:bg-muted/30 h-8 transition-colors">
                                <TableCell className="text-[10px] text-foreground py-1 truncate max-w-[400px] font-bold">{o.market}</TableCell>
                                <TableCell className="py-1 text-right">
                                    <Badge variant="outline" className={`text-[9px] rounded-sm py-0 h-4 border-white/10 ${o.side === 'BUY' ? 'text-emerald-500' : 'text-rose-500'}`}>
                                        {o.side}
                                    </Badge>
                                </TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 text-right tabular-nums">{o.size.toFixed(0)}</TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 text-right tabular-nums font-bold">
                                    {o.price >= 1 ? `$${o.price.toFixed(2)}` : `${(o.price * 100).toFixed(1)}¢`}
                                </TableCell>
                                <TableCell className="py-1 text-right">
                                    <div className="flex items-center justify-end gap-1.5 text-amber-500">
                                        <Loader2 className="h-2 w-2 animate-spin" />
                                        <span className="text-[9px] font-bold uppercase">{o.status}</span>
                                    </div>
                                </TableCell>
                            </TableRow>
                        ))}

                        {(view === "activity" && trades.length === 0) ||
                            (view === "positions" && positionFilter === "active" && positions.length === 0) ||
                            (view === "positions" && positionFilter === "closed" && closedPositions.length === 0) ||
                            (view === "orders" && openOrders.length === 0) ? (
                            <TableRow>
                                <TableCell colSpan={5} className="text-center py-12 text-muted-foreground/50 text-[10px] font-bold uppercase tracking-widest">
                                    {view === "orders" ? "No_Open_Orders" : "No_Records_Found_In_Ledger"}
                                </TableCell>
                            </TableRow>
                        ) : null}
                    </TableBody>
                </Table>
            </div>
        </div>
    )
}
