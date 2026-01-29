"use client"

import React, { useState } from "react"
import { 
  LayoutDashboard, 
  LayoutKanban, 
  Calendar, 
  Wallet, 
  Bot, 
  MessageSquare, 
  Settings,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  ShieldAlert
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

interface SidebarItemProps {
  icon: any
  label: string
  active: boolean
  collapsed: boolean
  onClick: () => void
  badge?: string
}

function SidebarItem({ icon: Icon, label, active, collapsed, onClick, badge }: SidebarItemProps) {
  return (
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={onClick}
            className={cn(
              "flex items-center gap-3 w-full px-3 py-2 rounded-md transition-all duration-200 group relative",
              active 
                ? "bg-primary/15 text-primary border border-primary/20" 
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <Icon className={cn("h-4 w-4 shrink-0", active && "text-primary")} />
            {!collapsed && <span className="text-[11px] font-bold uppercase tracking-widest">{label}</span>}
            {!collapsed && badge && (
              <span className="ml-auto text-[8px] bg-primary/20 text-primary px-1 rounded-sm animate-pulse">
                {badge}
              </span>
            )}
            {collapsed && active && (
              <div className="absolute left-0 w-1 h-4 bg-primary rounded-r-full" />
            )}
          </button>
        </TooltipTrigger>
        {collapsed && (
          <TooltipContent side="right" className="text-[10px] uppercase font-bold tracking-tighter">
            {label}
          </TooltipContent>
        )}
      </Tooltip>
    </TooltipProvider>
  )
}

export function DariusSidebar({ 
  activeTab, 
  onTabChange 
}: { 
  activeTab: string
  onTabChange: (tab: string) => void 
}) {
  const [collapsed, setCollapsed] = useState(false)

  const menuItems = [
    { id: "polyagent", label: "PolyAgent", icon: TrendingUp, badge: "LIVE" },
    { id: "kanban", label: "Missions", icon: LayoutDashboard },
    { id: "calendar", label: "Timeline", icon: Calendar },
    { id: "finance", label: "Financials", icon: Wallet },
    { id: "agents", label: "Agent Fleet", icon: Bot },
    { id: "warroom", label: "War Room", icon: ShieldAlert },
  ]

  return (
    <div 
      className={cn(
        "flex flex-col border-r border-border/40 bg-background transition-all duration-300 h-full",
        collapsed ? "w-14" : "w-56"
      )}
    >
      {/* Sidebar Header */}
      <div className="h-10 border-b border-border/40 flex items-center px-4 justify-between">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 bg-primary rounded-full animate-pulse" />
            <span className="font-mono font-bold text-[10px] uppercase tracking-[0.2em]">Darius_OS</span>
          </div>
        )}
        <button 
          onClick={() => setCollapsed(!collapsed)}
          className="text-muted-foreground hover:text-foreground p-1"
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Navigation items */}
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto custom-scrollbar">
        {menuItems.map((item) => (
          <SidebarItem
            key={item.id}
            icon={item.icon}
            label={item.label}
            active={activeTab === item.id}
            collapsed={collapsed}
            onClick={() => onTabChange(item.id)}
            badge={item.badge}
          />
        ))}
      </nav>

      {/* Footer / Settings */}
      <div className="p-2 border-t border-border/40">
        <SidebarItem
          icon={Settings}
          label="Config"
          active={activeTab === "settings"}
          collapsed={collapsed}
          onClick={() => onTabChange("settings")}
        />
      </div>
    </div>
  )
}
