import { useState, useEffect } from "react"
import { Shield, Zap, TrendingUp, Cpu, Wallet, Wifi, AlertTriangle, Monitor } from "lucide-react"
import { ThemeToggle } from "@/components/theme-toggle"
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { WarRoom } from "@/components/war-room"
import { Button } from "@/components/ui/button"

interface BinancePrice {
    symbol: string
    price: number
}

interface TerminalHeaderProps {
    data: {
        walletAddress: string
        dryRun: boolean
        balance: number
        referenceTokenId: string
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
        <div className="flex items-center justify-between w-full font-mono text-[10px] tracking-tight text-muted-foreground bg-background">
            {/* Left: Clock, Wallet, Balance */}
            <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 border-r border-border/40 pr-4">
                    <Cpu className="h-3 w-3 text-emerald-500" />
                    <span className="text-foreground font-bold">{utcTime} UTC</span>
                </div>

                <Tooltip>
                    <TooltipTrigger asChild>
                        <div className="flex items-center gap-2 border-r border-border/40 pr-4 cursor-help">
                            <Shield className="h-3 w-3" />
                            <span className="hover:text-foreground transition-colors">{formatAddress(data.walletAddress)}</span>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                        Polymarket Proxy Wallet: {data.walletAddress}
                    </TooltipContent>
                </Tooltip>

                <Tooltip>
                    <TooltipTrigger asChild>
                        <div className="flex items-center gap-2 cursor-help">
                            <Wallet className="h-3 w-3 text-emerald-500" />
                            <span className="text-foreground font-bold">${data.balance.toFixed(2)}</span>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                        Available USDC liquidity for deployment
                    </TooltipContent>
                </Tooltip>
            </div>

            {/* Center: Mode Badge & Market Status */}
            <div className="flex items-center gap-3">
                <Tooltip>
                    <TooltipTrigger asChild>
                        <div className={`px-2 py-1 rounded-sm border cursor-help ${data.dryRun ? 'bg-amber-500/10 border-amber-500/20 text-amber-500' : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500'} font-bold flex items-center gap-1.5 transition-colors`}>
                            <Zap className={`h-2.5 w-2.5 ${data.dryRun ? 'fill-amber-500' : 'fill-emerald-500'}`} />
                            <span>{data.dryRun ? "SIMULATED" : "LIVE_AGENT"}</span>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                        {data.dryRun ? "Dry-run mode: Trades are simulated but not signed" : "Production mode: All trades are signed and executed on-chain"}
                    </TooltipContent>
                </Tooltip>

                <Tooltip>
                    <TooltipTrigger asChild>
                        <div className={`px-2 py-1 rounded-sm border cursor-help ${marketStatus === 'LIVE' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 'bg-rose-500/10 border-rose-500/20 text-rose-500'} font-bold flex items-center gap-1.5 transition-colors`}>
                            <Wifi className="h-2.5 w-2.5" />
                            <span>{marketStatus === 'LIVE' ? "CLOB: ONLINE" : "CLOB: STANDBY"}</span>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                        Connectivity status to Polymarket Central Limit Order Book
                    </TooltipContent>
                </Tooltip>
            </div>

            {/* Right: War Room, Binance Tickers & Theme */}
            <div className="flex items-center gap-4">
                <Dialog>
                    <DialogTrigger asChild>
                        <Button variant="destructive" size="sm" className="h-6 text-[9px] px-2 font-bold animate-pulse hover:animate-none border-rose-500/50 bg-rose-500/10 text-rose-500 hover:bg-rose-500 hover:text-white transition-all">
                            <AlertTriangle className="h-3 w-3 mr-1" /> WAR ROOM
                        </Button>
                    </DialogTrigger>
                    <DialogContent className="border-red-900/50 bg-background/95 backdrop-blur-xl sm:max-w-[800px]">
                        <WarRoom />
                    </DialogContent>
                </Dialog>

                {prices.map((p) => (
                    <Tooltip key={p.symbol}>
                        <TooltipTrigger asChild>
                            <div className="flex items-center gap-1.5 border-l border-border/40 pl-4 first:border-l-0 cursor-help group">
                                <span className="text-muted-foreground group-hover:text-foreground transition-colors">{p.symbol}</span>
                                <span className="text-foreground font-bold">
                                    {p.price.toLocaleString(undefined, { minimumFractionDigits: p.symbol === "SOL" ? 2 : 0 })}
                                </span>
                                <TrendingUp className="h-2.5 w-2.5 text-emerald-500 opacity-50 group-hover:opacity-100 transition-opacity" />
                            </div>
                        </TooltipTrigger>
                        <TooltipContent className="bg-zinc-900 border-zinc-800 text-zinc-400 font-bold uppercase text-[9px]">
                            Binance Real-time Price Index (USDT)
                        </TooltipContent>
                    </Tooltip>
                ))}

                <div className="pl-4 border-l border-border/40">
                    <ThemeToggle />
                </div>
            </div>
        </div>
    )
}
