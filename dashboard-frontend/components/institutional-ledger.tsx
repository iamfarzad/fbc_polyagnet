"use client"

import { useState } from "react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Loader2 } from "lucide-react"

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
    const [view, setView] = useState<"trades" | "positions" | "orders">("trades")

    const getHeaderInfo = () => {
        if (view === "trades") return `RECORDS: ${trades.length}`
        if (view === "positions") return `EXPOSURE: $${positions.reduce((acc, p) => acc + p.value, 0).toFixed(2)}`
        if (view === "orders") return `OPEN: ${openOrders.length}`
        return ""
    }

    return (
        <div className="h-full flex flex-col font-mono bg-muted/10">
            {/* Ledger Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-border/40 shrink-0">
                <div className="flex gap-4">
                    <button
                        onClick={() => setView("trades")}
                        className={`text-[10px] font-bold uppercase tracking-widest pb-1 border-b ${view === "trades" ? "text-emerald-500 border-emerald-500" : "text-muted-foreground border-transparent hover:text-foreground"}`}
                    >
                        Trade_History
                    </button>
                    <button
                        onClick={() => setView("positions")}
                        className={`text-[10px] font-bold uppercase tracking-widest pb-1 border-b ${view === "positions" ? "text-emerald-500 border-emerald-500" : "text-muted-foreground border-transparent hover:text-foreground"}`}
                    >
                        Active_Positions
                    </button>
                    <button
                        onClick={() => setView("orders")}
                        className={`text-[10px] font-bold uppercase tracking-widest pb-1 border-b ${view === "orders" ? "text-amber-500 border-amber-500" : "text-muted-foreground border-transparent hover:text-foreground"}`}
                    >
                        Active_Orders
                    </button>
                </div>
                <div className="text-[10px] text-muted-foreground tabular-nums">
                    {getHeaderInfo()}
                </div>
            </div>

            {/* Ledger Table */}
            <div className="flex-1 overflow-auto">
                <Table>
                    <TableHeader className="bg-card sticky top-0 z-10">
                        <TableRow className="border-border/40 hover:bg-transparent h-8">
                            {view === "trades" && (
                                <>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24">Timestamp</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-20">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Size_USD</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-20 text-right">Status</TableHead>
                                </>
                            )}
                            {view === "positions" && (
                                <>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-20 text-right">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Cost</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Value</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">PnL</TableHead>
                                </>
                            )}
                            {view === "orders" && (
                                <>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-20 text-right">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Size</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-24 text-right">Price</TableHead>
                                    <TableHead className="text-[9px] font-bold text-muted-foreground uppercase h-8 w-20 text-right">Status</TableHead>
                                </>
                            )}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {view === "trades" && trades.map((t, i) => (
                            <TableRow key={i} className="border-border/40 hover:bg-muted/20 h-8">
                                <TableCell className="text-[10px] text-muted-foreground py-1">{t.time.split(' ')[1] || t.time}</TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 truncate max-w-[400px]">{t.market}</TableCell>
                                <TableCell className="py-1">
                                    <span className={`text-[9px] px-1.5 py-0.5 rounded-sm border font-bold ${t.side.includes('Buy') ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-rose-500/10 border-rose-500/20 text-rose-500'}`}>
                                        {t.side.toUpperCase()}
                                    </span>
                                </TableCell>
                                <TableCell className="text-[10px] text-foreground py-1 text-right font-bold">${t.amount.toFixed(2)}</TableCell>
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

                        {view === "positions" && positions.map((p, i) => (
                            <TableRow key={i} className="border-border/40 hover:bg-muted/20 h-8">
                                <TableCell className="text-[10px] text-foreground py-1 truncate max-w-[400px]">{p.market}</TableCell>
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

                        {view === "orders" && openOrders.map((o, i) => (
                            <TableRow key={i} className="border-border/40 hover:bg-muted/20 h-8">
                                <TableCell className="text-[10px] text-foreground py-1 truncate max-w-[400px]">{o.market}</TableCell>
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

                        {(view === "trades" && trades.length === 0) ||
                            (view === "positions" && positions.length === 0) ||
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
