"use client"

import React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { CheckCircle, Circle, Clock, LayoutPanelLeft } from "lucide-react"

interface Task {
  id: string
  title: string
  status: "backlog" | "todo" | "in-progress" | "done"
  priority: "low" | "medium" | "high"
  category: "trading" | "infra" | "admin"
}

const tasks: Task[] = [
  { id: "1", title: "Analyze Sniper Strategy Bleed", status: "in-progress", priority: "high", category: "trading" },
  { id: "2", title: "Implement Darius Kanban Board", status: "in-progress", priority: "medium", category: "infra" },
  { id: "3", title: "Fix Samsung ADB Bridge", status: "todo", priority: "medium", category: "infra" },
  { id: "4", title: "FaraSlim Inventory Gen Logic", status: "backlog", priority: "high", category: "trading" },
  { id: "5", title: "NAV Bureaucracy Document Scan", status: "backlog", priority: "medium", category: "admin" },
  { id: "6", title: "Moltbot Config Migration", status: "done", priority: "high", category: "infra" },
]

export function DariusKanban() {
  const columns = [
    { id: "backlog", title: "Backlog", icon: Circle },
    { id: "todo", title: "To Do", icon: Clock },
    { id: "in-progress", title: "In Progress", icon: LayoutPanelLeft },
    { id: "done", title: "Done", icon: CheckCircle },
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 h-full">
      {columns.map((column) => (
        <div key={column.id} className="flex flex-col gap-3">
          <div className="flex items-center gap-2 px-2">
            <column.icon className="h-4 w-4 text-muted-foreground" />
            <h3 className="font-bold text-[10px] uppercase tracking-widest text-muted-foreground">
              {column.title}
            </h3>
            <Badge variant="outline" className="ml-auto text-[9px] h-4">
              {tasks.filter((t) => t.status === column.id).length}
            </Badge>
          </div>
          <ScrollArea className="flex-1 rounded-md border border-border/40 bg-muted/5 p-2">
            <div className="flex flex-col gap-2">
              {tasks
                .filter((task) => task.status === column.id)
                .map((task) => (
                  <Card key={task.id} className="bg-background border-border/40 shadow-sm">
                    <CardContent className="p-3 space-y-2">
                      <div className="flex justify-between items-start gap-2">
                        <span className="text-xs font-medium leading-tight">{task.title}</span>
                      </div>
                      <div className="flex gap-1.5">
                        <Badge className="text-[8px] h-3.5 uppercase px-1" variant={task.priority === "high" ? "destructive" : "secondary"}>
                          {task.priority}
                        </Badge>
                        <Badge className="text-[8px] h-3.5 uppercase px-1 bg-primary/10 text-primary border-none">
                          {task.category}
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>
                ))}
            </div>
          </ScrollArea>
        </div>
      ))}
    </div>
  )
}
