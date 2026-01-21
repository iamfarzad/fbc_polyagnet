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
import { LLMTerminal } from "@/components/llm-terminal"
import { FBPChat } from "@/components/fbp-chat"
import { getApiUrl, getWsUrl } from "@/lib/api-url"

// ============================================================================
// TYPES
// ============================================================================

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
}

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
      <div className="flex h-screen flex-col items-center justify-center bg-slate-950 gap-4 font-mono">
        <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
        <p className="text-slate-500 text-[10px] uppercase tracking-widest animate-pulse">Initializing_Terminal_Core...</p>
        {connectionError && (
          <p className="text-[10px] text-rose-500 max-w-md text-center px-4 uppercase font-bold tracking-tighter">{connectionError}</p>
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
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans text-sm flex flex-col h-screen overflow-hidden selection:bg-emerald-500/30">

      {/* Command Bar (Zone A) */}
      <div className="shrink-0 border-b border-white/5 bg-slate-950 px-4 py-2 flex items-center h-10">
        <TerminalHeader data={{
          walletAddress: data.walletAddress,
          dryRun: data.dryRun,
          balance: data.balance,
          referenceTokenId: data.referenceTokenId
        }} />
      </div>

      {/* Main Terminal Grid */}
      <main className="flex-1 grid grid-cols-12 gap-0 divide-x divide-white/5 min-h-0">

        {/* Left Column: Execution (Zone B) - 4 Cols */}
        <div className="col-span-4 p-6 space-y-8 overflow-y-auto custom-scrollbar bg-slate-950/20">
          <InstitutionalFinancials data={data} />

          <div className="border-t border-white/5 pt-6">
            <VelocityTracker tradeCount={data.stats.tradeCount} />
          </div>

          <div className="border-t border-white/5 pt-6">
            <ScannerStatus referenceTokenId={data.referenceTokenId} />
          </div>

          <div className="border-t border-white/5 pt-6">
            <AgentNetworkStatus agents={agents} />
          </div>

          {/* Connection Monitor */}
          {connectionError && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-sm bg-rose-500/10 border border-rose-500/20 text-rose-500 text-[9px] font-bold uppercase tracking-widest animate-pulse">
              <span className="h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" />
              {connectionError}
            </div>
          )}
        </div>

        {/* Right Column: Intelligence & Terminal (Zone C) - 8 Cols */}
        <div className="col-span-8 flex flex-col min-h-0 bg-black/10">

          {/* Top Half: Momentum & Logic */}
          <div className="flex-1 min-h-0 grid grid-cols-2 divide-x divide-white/5">
            <div className="p-6">
              <MomentumStalker data={data} />
            </div>
            <div className="p-6 flex flex-col gap-4">
              <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-2 shrink-0">
                <span className="h-1.5 w-1.5 bg-emerald-500 rounded-full animate-pulse" />
                Neural_Logic_Stream
              </h3>
              <div className="flex-1 min-h-0 rounded-sm overflow-hidden border border-white/5 shadow-2xl">
                <LLMTerminal className="h-full" />
              </div>
            </div>
          </div>

          {/* Bottom Third: Ledger Table */}
          <div className="h-[35%] border-t border-white/5 bg-slate-950">
            <InstitutionalLedger trades={data.trades} positions={data.positions} />
          </div>
        </div>
      </main>

      {/* Floating Chat Button */}
      <button
        onClick={() => setChatOpen(!chatOpen)}
        className={`fixed bottom-6 right-6 rounded-full w-12 h-12 shadow-[0_0_20px_rgba(16,185,129,0.3)] z-50 flex items-center justify-center transition-all ${chatOpen ? 'bg-rose-600 rotate-180' : 'bg-emerald-600 hover:scale-110'}`}
      >
        {chatOpen ? <X className="h-5 w-5" /> : <MessageSquare className="h-5 w-5" />}
      </button>

      {/* FBP Chat Panel */}
      {chatOpen && (
        <div className="fixed bottom-20 right-6 w-[400px] h-[550px] rounded-sm border border-white/10 bg-slate-950 shadow-2xl overflow-hidden z-50 flex flex-col animate-in slide-in-from-bottom-4 duration-300">
          <div className="px-4 py-2.5 border-b border-white/5 bg-black/40 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 bg-emerald-500 rounded-full animate-pulse" />
              <span className="font-mono font-bold text-[10px] text-slate-300 uppercase tracking-widest">FBP:LINK_ESTABLISHED</span>
            </div>
            <button onClick={() => setChatOpen(false)} className="text-slate-500 hover:text-white transition-colors">
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
          background: rgba(255, 255, 255, 0.05);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(16, 185, 129, 0.2);
        }
      `}</style>
    </div>
  )
}
