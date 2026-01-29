"use client"

import React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"

export function DariusCalendar() {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
  // Mock events for visualization
  const events = [
    { day: 29, title: "Sniper Dry-Run End", type: "trading" },
    { day: 30, title: "NAV Deadline", type: "admin" },
    { day: 31, title: "FaraSlim Launch", type: "trading" },
  ]

  return (
    <div className="flex flex-col h-full gap-4">
      <div className="flex items-center justify-between px-2">
        <h3 className="font-bold text-[10px] uppercase tracking-widest text-muted-foreground flex items-center gap-2">
          <CalendarIcon className="h-3 w-3" /> Strategic_Timeline
        </h3>
        <div className="flex gap-1">
          <Button variant="outline" size="icon" className="h-6 w-6"><ChevronLeft className="h-3 w-3" /></Button>
          <Button variant="outline" size="icon" className="h-6 w-6"><ChevronRight className="h-3 w-3" /></Button>
        </div>
      </div>
      
      <div className="flex-1 grid grid-cols-7 gap-px bg-border/20 rounded-md overflow-hidden border border-border/40">
        {days.map(d => (
          <div key={d} className="bg-muted/30 p-2 text-center text-[9px] font-bold text-muted-foreground border-b border-border/40">
            {d}
          </div>
        ))}
        {Array.from({ length: 35 }).map((_, i) => {
          const day = i - 3; // Offset for Jan 2026 starting on Thursday
          const isCurrentMonth = day > 0 && day <= 31;
          const event = events.find(e => e.day === day);
          
          return (
            <div key={i} className={`bg-background p-2 min-h-[60px] flex flex-col gap-1 ${!isCurrentMonth ? 'opacity-20' : ''}`}>
              <span className="text-[10px] font-mono">{isCurrentMonth ? day : ''}</span>
              {event && (
                <div className={`text-[8px] p-1 rounded-sm border ${event.type === 'trading' ? 'bg-primary/10 border-primary/20 text-primary' : 'bg-destructive/10 border-destructive/20 text-destructive'}`}>
                  {event.title}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
