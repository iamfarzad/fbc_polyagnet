"use client"

import { useState, useEffect } from "react"
import { ShieldAlert, Activity, Wifi, WifiOff } from "lucide-react"

interface ScannerStatusProps {
    referenceTokenId?: string
}

export function ScannerStatus({ referenceTokenId }: ScannerStatusProps) {
    const [isSuspended, setIsSuspended] = useState(false)
    const [lastCheck, setLastCheck] = useState<string>("-")
    const [error, setError] = useState(false)

    useEffect(() => {
        if (!referenceTokenId) return

        const checkMarketStatus = async () => {
            try {
                const url = `https://clob.polymarket.com/fee-rate?token_id=${referenceTokenId}`
                const controller = new AbortController()
                const timeoutId = setTimeout(() => controller.abort(), 2000)

                const resp = await fetch(url, { signal: controller.signal })
                clearTimeout(timeoutId)

                if (resp.status === 200) {
                    const data = await resp.json()
                    // If base_fee is 0 or missing, it's suspended
                    const fee = data.base_fee ?? 0
                    setIsSuspended(fee === 0)
                    setError(false)
                } else {
                    // Non-200 response (e.g., 404, 500)
                    setIsSuspended(true)
                    setError(true)
                }
            } catch (e) {
                console.warn("Market status check failed:", e)
                setIsSuspended(true)
                setError(true)
            } finally {
                setLastCheck(new Date().toLocaleTimeString())
            }
        }

        checkMarketStatus()
        const interval = setInterval(checkMarketStatus, 30000) // Poll every 30s
        return () => clearInterval(interval)
    }, [referenceTokenId])

    if (!referenceTokenId) return null

    return (
        <div className="space-y-3 font-mono">
            <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2">
                <ShieldAlert className={`h-3 w-3 ${isSuspended ? 'text-rose-500 animate-pulse' : 'text-emerald-500'}`} />
                Market Availability
            </h3>

            {isSuspended ? (
                <div className="bg-rose-500/10 border border-rose-500/20 p-4 rounded-sm space-y-2 animate-in fade-in duration-500">
                    <div className="flex items-center gap-2">
                        <WifiOff className="h-4 w-4 text-rose-500" />
                        <span className="text-xs font-bold text-rose-500 uppercase tracking-tighter">
                            Market Suspended - Standby
                        </span>
                    </div>
                    <p className="text-[9px] text-rose-500/70 leading-relaxed uppercase">
                        {error ? "Terminal Timeout: CLOB API UNREACHABLE" : "Liquidity Filter: Base Fee 0bps detected"}
                    </p>
                    <div className="pt-1 flex items-center justify-between">
                        <span className="text-[8px] text-rose-500/50">DOWNTIME_PROTOCOL_ACTIVE</span>
                        <span className="text-[8px] text-rose-500/50 font-bold">{lastCheck}</span>
                    </div>
                </div>
            ) : (
                <div className="bg-slate-900/50 border border-white/5 p-4 rounded-sm flex justify-between items-center group hover:border-emerald-500/30 transition-colors">
                    <div className="flex items-center gap-3">
                        <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        <div className="space-y-0.5">
                            <span className="text-[10px] text-slate-200 font-bold uppercase tracking-tight block leading-none">Scanning_Live</span>
                            <span className="text-[9px] text-slate-500 uppercase">HFT Pipelines Clear</span>
                        </div>
                    </div>
                    <div className="text-right">
                        <Wifi className="h-3 w-3 text-emerald-500/40 ml-auto mb-1" />
                        <span className="text-[8px] text-slate-500 font-bold">{lastCheck}</span>
                    </div>
                </div>
            )}
        </div>
    )
}
