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

interface InstitutionalLedgerProps {
    trades: Trade[]
    positions: Position[]
}

export function InstitutionalLedger({ trades, positions }: InstitutionalLedgerProps) {
    const [view, setView] = useState<"trades" | "positions">("trades")

    return (
        <div className="h-full flex flex-col font-mono bg-black/20">
            {/* Ledger Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 shrink-0">
                <div className="flex gap-4">
                    <button
                        onClick={() => setView("trades")}
                        className={`text-[10px] font-bold uppercase tracking-widest pb-1 border-b ${view === "trades" ? "text-emerald-500 border-emerald-500" : "text-slate-500 border-transparent hover:text-slate-300"}`}
                    >
                        Trade_History
                    </button>
                    <button
                        onClick={() => setView("positions")}
                        className={`text-[10px] font-bold uppercase tracking-widest pb-1 border-b ${view === "positions" ? "text-emerald-500 border-emerald-500" : "text-slate-500 border-transparent hover:text-slate-300"}`}
                    >
                        Active_Positions
                    </button>
                </div>
                <div className="text-[10px] text-slate-500 tabular-nums">
                    {view === "trades" ? `RECORDS: ${trades.length}` : `EXPOSURE: $${positions.reduce((acc, p) => acc + p.value, 0).toFixed(2)}`}
                </div>
            </div>

            {/* Ledger Table */}
            <div className="flex-1 overflow-auto">
                <Table>
                    <TableHeader className="bg-slate-950 sticky top-0 z-10">
                        <TableRow className="border-white/5 hover:bg-transparent h-8">
                            {view === "trades" ? (
                                <>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-24">Timestamp</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-20">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-24 text-right">Size_USD</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-20 text-right">Status</TableHead>
                                </>
                            ) : (
                                <>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8">Market</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-20 text-right">Side</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-24 text-right">Cost</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-24 text-right">Value</TableHead>
                                    <TableHead className="text-[9px] font-bold text-slate-500 uppercase h-8 w-24 text-right">PnL</TableHead>
                                </>
                            )}
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {view === "trades" ? (
                            trades.map((t, i) => (
                                <TableRow key={i} className="border-white/5 hover:bg-white/5 h-8">
                                    <TableCell className="text-[10px] text-slate-500 py-1">{t.time.split(' ')[1] || t.time}</TableCell>
                                    <TableCell className="text-[10px] text-slate-300 py-1 truncate max-w-[400px]">{t.market}</TableCell>
                                    <TableCell className="py-1">
                                        <span className={`text-[9px] px-1.5 py-0.5 rounded-sm border font-bold ${t.side.includes('Buy') ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-rose-500/10 border-rose-500/20 text-rose-500'}`}>
                                            {t.side.toUpperCase()}
                                        </span>
                                    </TableCell>
                                    <TableCell className="text-[10px] text-slate-300 py-1 text-right font-bold">${t.amount.toFixed(2)}</TableCell>
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
                            ))
                        ) : (
                            positions.map((p, i) => (
                                <TableRow key={i} className="border-white/5 hover:bg-white/5 h-8">
                                    <TableCell className="text-[10px] text-slate-300 py-1 truncate max-w-[400px]">{p.market}</TableCell>
                                    <TableCell className="py-1 text-right">
                                        <Badge variant="outline" className={`text-[9px] rounded-sm py-0 h-4 border-white/10 ${p.side.includes('Yes') ? 'text-emerald-500' : 'text-rose-500'}`}>
                                            {p.side.toUpperCase()}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-[10px] text-slate-500 py-1 text-right tabular-nums">${p.cost.toFixed(2)}</TableCell>
                                    <TableCell className="text-[10px] text-slate-300 py-1 text-right font-bold tabular-nums">${p.value.toFixed(2)}</TableCell>
                                    <TableCell className={`text-[10px] py-1 text-right font-bold tabular-nums ${p.pnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                                        {p.pnl >= 0 ? '+' : ''}{p.pnl.toFixed(2)}
                                    </TableCell>
                                </TableRow>
                            ))
                        )}
                        {(view === "trades" ? trades : positions).length === 0 && (
                            <TableRow>
                                <TableCell colSpan={5} className="text-center py-12 text-slate-600 text-[10px] font-bold uppercase tracking-widest">
                                    No_Records_Found_In_Ledger
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </div>
        </div>
    )
}
