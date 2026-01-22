"use client"

import { useState, useEffect } from "react"
import { Loader2, MessageSquare, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { TerminalHeader } from "@/components/terminal-header"
import { InstitutionalFinancials } from "@/components/institutional-financials"
import { MomentumStalker } from "@/components/momentum-stalker"
import { InstitutionalLedger } from "@/components/institutional-ledger"
import { AgentNetworkStatus } from "@/components/agent-network-status"
import { VelocityTracker } from "@/components/velocity-tracker"
import { ScannerStatus } from "@/components/scanner-status"
import { LLMActivityFeed } from "@/components/llm-activity-feed"
import { FBPChat } from "@/components/fbp-chat"
import { getApiUrl, getWsUrl } from "@/lib/api-url"


// ... (existing imports)

interface DashboardData {
  balance: number
  equity: number
  unrealizedPnl: number
  gasSpent: number
  total_redeemed: number
  instant_scalp_total: number
  estimated_rebate: number
  compounding_velocity: number
  costs: {
    openai: number
    perplexity: number
    gemini: number
    fly: number
    neural_total: number
    infra_total: number
  }
  riskStatus: {
    safe: boolean
    message: string
  }
  agents: Record<string, { running: boolean; activity: string; lastSignal?: string }>
  positions: Array<{
    market: string
    side: string
    cost: number
    value: number
    pnl: number
  }>
  openOrders: Array<{  // [NEW] Added openOrders
    id: string
    market: string
    side: string
    price: number
    size: number
    filled: number
    status: string
  }>
  trades: Array<{
    time: string
    market: string
    side: string
    amount: number
  }>
  stats: {
    tradeCount: number
    volume24h: number
  }
  dryRun: boolean
  lastUpdate: string
  walletAddress: string
  referenceTokenId: string
}

// ... (rest of component)

{/* Bottom Third: Ledger Table */ }
<div className="h-[35%] border-t border-border/40 bg-background">
  <InstitutionalLedger
    trades={data.trades}
    positions={data.positions}
    openOrders={data.openOrders || []} // [NEW] Pass openOrders
  />
</div>


// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState(false)

  const fetchData = async () => {
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5000)
      const res = await fetch(`${getApiUrl()}/api/dashboard`, { signal: controller.signal })
      clearTimeout(timeout)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const json = await res.json()
      setData(json)
      setConnectionError(null)
    } catch (e) {
      console.error("Fetch error:", e)
      setConnectionError("Connection lost. Retrying...")
    }
  }

  useEffect(() => {
    let ws: WebSocket | null = null
    let poll: NodeJS.Timeout | null = null

    const startPoll = () => {
      fetchData()
      poll = setInterval(fetchData, 3000)
    }

    try {
      ws = new WebSocket(`${getWsUrl()}/ws/dashboard`)
      ws.onmessage = (e) => {
        try {
          const json = JSON.parse(e.data)
          if (json && typeof json === 'object' && !json.error) {
            setData(json)
            setConnectionError(null)
          }
        } catch { }
      }
      ws.onerror = () => ws?.close()
      ws.onclose = () => { if (!poll) startPoll() }
    } catch {
      startPoll()
    }

    return () => {
      if (poll) clearInterval(poll)
      try { ws?.close() } catch { }
    }
  }, [])

  if (!data) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-background gap-4 font-mono">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground text-[10px] uppercase tracking-widest animate-pulse">Initializing_Terminal_Core...</p>
        {connectionError && (
          <p className="text-[10px] text-destructive max-w-md text-center px-4 uppercase font-bold tracking-tighter">{connectionError}</p>
        )}
      </div>
    )
  }

  const agents = Object.entries(data.agents).map(([id, agent]: [string, any]) => ({
    id,
    name: id.charAt(0).toUpperCase() + id.slice(1).replace(/([A-Z])/g, ' $1'),
    isActive: agent.running,
    activity: agent.activity || agent.lastSignal || "",
    heartbeat: agent.heartbeat,
  }))

  return (
    <div className="min-h-screen bg-background text-foreground font-sans text-sm flex flex-col h-screen overflow-hidden selection:bg-primary/30">

      {/* Command Bar (Zone A) */}
      <div className="shrink-0 border-b border-border/40 bg-background px-4 py-2 flex items-center h-10">
        <TerminalHeader data={{
          walletAddress: data.walletAddress,
          dryRun: data.dryRun,
          balance: data.balance,
          referenceTokenId: data.referenceTokenId
        }} />
      </div>

      {/* Main Terminal Grid */}
      <main className="flex-1 grid grid-cols-1 md:grid-cols-12 gap-0 divide-y md:divide-y-0 md:divide-x divide-border/40 min-h-0 w-full overflow-x-hidden">

        {/* Left Column: Execution (Zone B) - 4 Cols Desktop, Full Mobile */}
        <div className="col-span-1 md:col-span-4 p-6 space-y-8 overflow-y-auto custom-scrollbar bg-muted/20 w-full">
          <InstitutionalFinancials data={data} />

          <div className="border-t border-border/40 pt-6">
            <VelocityTracker tradeCount={data.stats.tradeCount} />
          </div>

          <div className="border-t border-border/40 pt-6">
            <ScannerStatus referenceTokenId={data.referenceTokenId} />
          </div>

          <div className="border-t border-border/40 pt-6">
            <AgentNetworkStatus agents={agents} />
          </div>

          {/* Connection Monitor */}
          {connectionError && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-destructive/10 border border-destructive/20 text-destructive text-[9px] font-bold uppercase tracking-widest animate-pulse">
              <span className="h-1.5 w-1.5 rounded-full bg-destructive shrink-0" />
              {connectionError}
            </div>
          )}
        </div>

        {/* Right Column: Intelligence & Terminal (Zone C) - 8 Cols Desktop, Full Mobile */}
        <div className="col-span-1 md:col-span-8 flex flex-col min-h-0 bg-muted/10 w-full">

          {/* Top Half: Momentum & Logic */}
          <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/40">
            <div className="p-6">
              <MomentumStalker data={data} />
            </div>
            <div className="p-6 flex flex-col gap-4">
              <h3 className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2 shrink-0">
                <span className="h-1.5 w-1.5 bg-primary rounded-full animate-pulse" />
                Neural_Logic_Stream
              </h3>
              <div className="flex-1 min-h-[300px] md:min-h-0 rounded-sm overflow-hidden border border-border/40 shadow-2xl">
                <LLMActivityFeed className="h-full w-full" />
              </div>
            </div>
          </div>

          {/* Bottom Third: Ledger Table */}
          <div className="h-[35%] border-t border-border/40 bg-background">
            <InstitutionalLedger
              trades={data.trades}
              positions={data.positions}
              openOrders={data.openOrders || []}
            />
          </div>
        </div>
      </main>

      {/* Floating Chat Button */}
      <button
        onClick={() => setChatOpen(!chatOpen)}
        className={`fixed bottom-6 right-6 rounded-full w-12 h-12 shadow-[0_0_20px_rgba(16,185,129,0.3)] z-[100] flex items-center justify-center transition-all ${chatOpen ? 'bg-destructive rotate-180' : 'bg-primary hover:scale-110'}`}
      >
        {chatOpen ? <X className="h-5 w-5 text-destructive-foreground" /> : <MessageSquare className="h-5 w-5 text-primary-foreground" />}
      </button>

      {/* FBP Chat Panel */}
      {chatOpen && (
        <div className="fixed bottom-20 right-6 w-[calc(100vw-3rem)] md:w-[400px] h-[60vh] md:h-[550px] rounded-sm border border-border/40 bg-background shadow-2xl overflow-hidden z-[100] flex flex-col animate-in slide-in-from-bottom-4 duration-300">
          <div className="px-4 py-2.5 border-b border-border/40 bg-muted/40 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 bg-primary rounded-full animate-pulse" />
              <span className="font-mono font-bold text-[10px] text-foreground/80 uppercase tracking-widest">FBP:LINK_ESTABLISHED</span>
            </div>
            <button onClick={() => setChatOpen(false)} className="text-muted-foreground hover:text-foreground transition-colors">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-hidden font-mono">
            <FBPChat />
          </div>
        </div>
      )}

      <style jsx global>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: var(--border);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: var(--primary);
        }
      `}</style>
    </div>
  )
}
