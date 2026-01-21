"use client"

import { useState, useEffect } from "react"
import { Shield, Zap, TrendingUp, Cpu, Wallet, Wifi } from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"

interface BinancePrice {
    symbol: string
    price: number
}

interface TerminalHeaderProps {
    data: {
        walletAddress: string
        dryRun: boolean
        balance: number
        referenceTokenId?: string
    }
}

export function TerminalHeader({ data }: TerminalHeaderProps) {
    const [time, setTime] = useState(new Date())
    const [prices, setPrices] = useState<BinancePrice[]>([
        { symbol: "BTC", price: 0 },
        { symbol: "ETH", price: 0 },
        { symbol: "SOL", price: 0 }
    ])
    const [marketStatus, setMarketStatus] = useState<"LIVE" | "STANDBY">("LIVE")

    // Polling for market status (simple version for header)
    useEffect(() => {
        if (!data.referenceTokenId) return
        const check = async () => {
            try {
                const res = await fetch(`https://clob.polymarket.com/fee-rate?token_id=${data.referenceTokenId}`)
                if (res.ok) {
                    const json = await res.json()
                    setMarketStatus((json.base_fee === 0 || json.base_fee === undefined) ? "STANDBY" : "LIVE")
                } else {
                    setMarketStatus("STANDBY")
                }
            } catch { setMarketStatus("STANDBY") }
        }
        check()
        const i = setInterval(check, 60000)
        return () => clearInterval(i)
    }, [data.referenceTokenId])

    useEffect(() => {
        const timer = setInterval(() => setTime(new Date()), 1000)

        const fetchPrices = async () => {
            try {
                const res = await fetch("https://api.binance.com/api/v3/ticker/price?symbols=%5B%22BTCUSDT%22,%22ETHUSDT%22,%22SOLUSDT%22%5D")
                const json = await res.json()
                const updated = json.map((p: any) => ({
                    symbol: p.symbol.replace("USDT", ""),
                    price: parseFloat(p.price)
                }))
                setPrices(updated)
            } catch (e) {
                console.error("Failed to fetch prices:", e)
            }
        }

        fetchPrices()
        const priceTimer = setInterval(fetchPrices, 10000)

        return () => {
            clearInterval(timer)
            clearInterval(priceTimer)
        }
    }, [])

    const formatAddress = (addr: string) => addr ? `${addr.slice(0, 6)}...${addr.slice(-4)}` : "0x00...0000"
    const utcTime = time.toUTCString().split(' ')[4]

    return (
        <div className="flex items-center justify-between w-full font-mono text-[10px] tracking-tight text-slate-400">
            {/* Left: Clock, Wallet, Balance */}
            <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 border-r border-white/5 pr-4">
                    <Cpu className="h-3 w-3 text-emerald-500" />
                    <span className="text-white font-bold">{utcTime} UTC</span>
                </div>
                <div className="flex items-center gap-2 border-r border-white/5 pr-4">
                    <Shield className="h-3 w-3" />
                    <span>{formatAddress(data.walletAddress)}</span>
                </div>
                <div className="flex items-center gap-2">
                    <Wallet className="h-3 w-3 text-emerald-500" />
                    <span className="text-white font-bold">${data.balance.toFixed(2)}</span>
                </div>
            </div>

            {/* Center: Mode Badge & Market Status */}
            <div className="flex items-center gap-3">
                <div className={`px-2 py-0.5 rounded-sm border ${data.dryRun ? 'bg-amber-500/10 border-amber-500/20 text-amber-500' : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500'} font-bold flex items-center gap-1.5`}>
                    <Zap className={`h-2.5 w-2.5 ${data.dryRun ? 'fill-amber-500' : 'fill-emerald-500'}`} />
                    <span>{data.dryRun ? "SIMULATED_SCALPER" : "FBP Agent"}</span>
                </div>
                {/* Market Status Badge */}
                <div className={`px-2 py-0.5 rounded-sm border ${marketStatus === 'LIVE' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-rose-500/10 border-rose-500/20 text-rose-500'} font-bold flex items-center gap-1.5`}>
                    <Wifi className="h-2.5 w-2.5" />
                    <span>{marketStatus === 'LIVE' ? "MARKET: LIVE" : "MARKET: STANDBY"}</span>
                </div>
            </div>

            {/* Right: Binance Tickers & Theme */}
            <div className="flex items-center gap-4">
                {prices.map((p) => (
                    <div key={p.symbol} className="flex items-center gap-1.5 border-l border-white/5 pl-4 first:border-l-0">
                        <span className="text-slate-500">{p.symbol}</span>
                        <span className="text-white font-bold">
                            {p.price.toLocaleString(undefined, { minimumFractionDigits: p.symbol === "SOL" ? 2 : 0 })}
                        </span>
                        <TrendingUp className="h-2.5 w-2.5 text-emerald-500" />
                    </div>
                ))}
                <div className="pl-4 border-l border-white/5">
                    <ThemeToggle />
                </div>
            </div>
        </div>
    )
}
