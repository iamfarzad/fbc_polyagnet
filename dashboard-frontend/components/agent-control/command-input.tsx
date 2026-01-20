"use client"

import { useState, useRef, KeyboardEvent } from "react"
import { Send, Terminal, Loader2, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { getApiUrl } from "@/lib/api-url"
import { cn } from "@/lib/utils"
import { useToast } from "@/hooks/use-toast"

interface CommandInputProps {
    agentId: string
    agentName: string
    onCommandSent?: () => void
    className?: string
}

export function CommandInput({ agentId, agentName, onCommandSent, className }: CommandInputProps) {
    const [input, setInput] = useState("")
    const [isLoading, setIsLoading] = useState(false)
    const { toast } = useToast()
    const inputRef = useRef<HTMLInputElement>(null)

    const sendCommand = async () => {
        if (!input.trim() || isLoading) return

        setIsLoading(true)
        try {
            const apiUrl = getApiUrl()
            // We use the main chat endpoint but prefix the message with context
            const response = await fetch(`${apiUrl}/api/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    messages: [{
                        role: "user",
                        content: `[CONTEXT: This is a direct command for agent: ${agentId}] ${input.trim()}`
                    }]
                })
            })

            if (!response.ok) throw new Error("Failed to send command")

            setInput("")
            toast({
                title: "Command Sent",
                description: `Instruction sent to ${agentName}`,
                variant: "default",
            })

            if (onCommandSent) onCommandSent()

        } catch (error) {
            console.error("Command error:", error)
            toast({
                title: "Command Failed",
                description: "Could not reach the agent. Try again.",
                variant: "destructive",
            })
        } finally {
            setIsLoading(false)
            // Keep focus for rapid commands
            setTimeout(() => inputRef.current?.focus(), 100)
        }
    }

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault()
            sendCommand()
        }
    }

    return (
        <div className={cn("relative", className)}>
            <div className="relative flex items-center">
                <div className="absolute left-3 flex items-center pointer-events-none">
                    <Terminal className="h-4 w-4 text-muted-foreground/50" />
                </div>
                <Input
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={`Command ${agentName}...`}
                    disabled={isLoading}
                    className="pl-9 pr-12 h-10 font-mono text-xs bg-secondary/30 border-border/40 focus-visible:ring-violet-500/20"
                />
                <div className="absolute right-1">
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={sendCommand}
                        disabled={!input.trim() || isLoading}
                        className={cn(
                            "h-8 w-8 p-0 rounded-md transition-all",
                            input.trim() && !isLoading
                                ? "text-violet-400 hover:text-violet-300 hover:bg-violet-500/20"
                                : "text-muted-foreground/30"
                        )}
                    >
                        {isLoading ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                            <Send className="h-4 w-4" />
                        )}
                    </Button>
                </div>
            </div>
            {/* Helper hint */}
            <div className="flex items-center justify-between mt-1 px-1">
                <span className="text-[9px] text-muted-foreground/50 flex items-center gap-1">
                    <Sparkles className="h-2 w-2" /> AI Agent Command Line
                </span>
                <span className="text-[9px] text-muted-foreground/40 font-mono">
                    ENTER to send
                </span>
            </div>
        </div>
    )
}
