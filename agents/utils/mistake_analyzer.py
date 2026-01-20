"""
Mistake Analyzer - Agent Self-Learning System

Analyzes resolved trades to extract lessons learned and inject them into 
future decision prompts for continuous improvement.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
import uuid

from openai import OpenAI

try:
    from agents.utils.supabase_client import get_supabase_state
except ImportError:
    get_supabase_state = None


logger = logging.getLogger("MistakeAnalyzer")


@dataclass
class Lesson:
    """A lesson learned from a past trade."""
    agent: str
    market_question: str
    original_reasoning: str
    predicted_outcome: str
    actual_outcome: str
    pnl: float
    mistake_type: str  # "false_positive", "false_negative", "sizing", "timing", "none"
    lesson_learned: str
    trade_id: int = 0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


POST_MORTEM_PROMPT = """You are analyzing a past trade to extract lessons for future improvement.

TRADE DETAILS:
- Market: {question}
- Agent's Prediction: {predicted_outcome}
- Agent's Reasoning: {reasoning}
- Entry Price: ${price:.2f}
- Actual Outcome: {actual_outcome}
- PnL: ${pnl:+.2f}

ANALYZE THIS TRADE:
1. Was the prediction correct?
2. If incorrect, what category of mistake was it?
   - "false_positive": Bet YES but should have passed
   - "false_negative": Passed but should have bet
   - "sizing": Bet size was wrong for confidence level
   - "timing": Entered too early or too late
   - "none": Correct decision, just unlucky or normal variance

3. What specific lesson should the agent learn for similar future markets?

OUTPUT FORMAT (JSON only):
{{
    "was_correct": true/false,
    "mistake_type": "false_positive|false_negative|sizing|timing|none",
    "lesson": "One clear, actionable lesson for future similar trades"
}}
"""


class MistakeAnalyzer:
    """
    Analyzes completed trades to extract lessons for continuous learning.
    
    Usage:
        analyzer = MistakeAnalyzer(agent_name="safe")
        lessons = analyzer.analyze_completed_trades(limit=10)
    """
    
    def __init__(self, agent_name: str = None):
        self.agent_name = agent_name
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.openai_key) if self.openai_key else None
        
        # Import Supabase client
        if get_supabase_state:
            self.supabase = get_supabase_state()
        else:
            self.supabase = None
            logger.warning("Supabase client not available for MistakeAnalyzer")
    
    def get_resolved_trades(self, limit: int = 10) -> List[Dict]:
        """
        Fetch trades where the market has resolved but we haven't analyzed yet.
        """
        if not self.supabase or not self.supabase.client:
            return []
        
        try:
            # Get trades that are filled but not yet analyzed
            query = self.supabase.client.table("trades")\
                .select("*")\
                .eq("status", "filled")\
                .is_("lesson_analyzed", "null")\
                .order("created_at", desc=True)\
                .limit(limit)
            
            if self.agent_name:
                query = query.eq("agent", self.agent_name)
            
            result = query.execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to fetch resolved trades: {e}")
            return []
    
    def analyze_trade(self, trade: Dict) -> Optional[Lesson]:
        """
        Analyze a single trade to extract a lesson.
        """
        if not self.client:
            logger.warning("No OpenAI client - cannot analyze trades")
            return None
        
        try:
            # Determine actual outcome (if available)
            # For now, we infer from PnL
            pnl = float(trade.get("pnl", 0))
            predicted = trade.get("outcome", "YES")
            
            # If PnL > 0, prediction was correct; if < 0, incorrect
            # This is a simplification - ideally we'd check market resolution
            if pnl > 0:
                actual = predicted
            elif pnl < 0:
                actual = "NO" if predicted == "YES" else "YES"
            else:
                # Break-even or unknown - skip
                actual = "UNKNOWN"
            
            prompt = POST_MORTEM_PROMPT.format(
                question=trade.get("market_question", "Unknown"),
                predicted_outcome=predicted,
                reasoning=trade.get("reasoning", "No reasoning recorded"),
                price=float(trade.get("price", 0)),
                actual_outcome=actual,
                pnl=pnl
            )
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            # Handle code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            analysis = json.loads(content)
            
            return Lesson(
                agent=trade.get("agent", "unknown"),
                market_question=trade.get("market_question", ""),
                original_reasoning=trade.get("reasoning", ""),
                predicted_outcome=predicted,
                actual_outcome=actual,
                pnl=pnl,
                mistake_type=analysis.get("mistake_type", "none"),
                lesson_learned=analysis.get("lesson", "No lesson extracted"),
                trade_id=trade.get("id", 0)
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to analyze trade: {e}")
            return None
    
    def save_lesson(self, lesson: Lesson) -> bool:
        """Save a lesson to Supabase."""
        if not self.supabase or not self.supabase.client:
            return False
        
        try:
            self.supabase.client.table("lessons_learned").insert(asdict(lesson)).execute()
            
            # Mark the original trade as analyzed
            if lesson.trade_id:
                self.supabase.client.table("trades")\
                    .update({"lesson_analyzed": True})\
                    .eq("id", lesson.trade_id)\
                    .execute()
            
            logger.info(f"📚 Lesson saved: [{lesson.mistake_type}] {lesson.lesson_learned[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to save lesson: {e}")
            return False
    
    def analyze_completed_trades(self, limit: int = 10) -> List[Lesson]:
        """
        Main entry point: Analyze recent completed trades and save lessons.
        """
        trades = self.get_resolved_trades(limit=limit)
        logger.info(f"Analyzing {len(trades)} resolved trades for {self.agent_name or 'all agents'}...")
        
        lessons = []
        for trade in trades:
            lesson = self.analyze_trade(trade)
            if lesson:
                if self.save_lesson(lesson):
                    lessons.append(lesson)
        
        logger.info(f"Generated {len(lessons)} new lessons")
        return lessons
    
    def get_relevant_lessons(self, market_question: str, limit: int = 3) -> List[Dict]:
        """
        Fetch lessons that might be relevant to a new market.
        Uses simple keyword matching for now - could be enhanced with embeddings.
        """
        if not self.supabase or not self.supabase.client:
            return []
        
        try:
            # Get recent lessons for this agent
            query = self.supabase.client.table("lessons_learned")\
                .select("*")\
                .order("created_at", desc=True)\
                .limit(limit * 3)  # Get more to filter
            
            if self.agent_name:
                query = query.eq("agent", self.agent_name)
            
            result = query.execute()
            lessons = result.data or []
            
            # Simple relevance: Check for keyword overlap
            keywords = set(market_question.lower().split())
            
            scored = []
            for lesson in lessons:
                lesson_keywords = set(lesson.get("market_question", "").lower().split())
                overlap = len(keywords & lesson_keywords)
                scored.append((overlap, lesson))
            
            # Sort by overlap and return top N
            scored.sort(key=lambda x: x[0], reverse=True)
            return [l for _, l in scored[:limit]]
            
        except Exception as e:
            logger.error(f"Failed to fetch lessons: {e}")
            return []
    
    def format_lessons_for_prompt(self, lessons: List[Dict]) -> str:
        """Format lessons into a string for injection into LLM prompts."""
        if not lessons:
            return ""
        
        lines = ["📚 LESSONS FROM PAST MISTAKES:", ""]
        for i, lesson in enumerate(lessons, 1):
            mistake = lesson.get("mistake_type", "unknown")
            text = lesson.get("lesson_learned", "")
            market = lesson.get("market_question", "")[:50]
            lines.append(f"{i}. [{mistake.upper()}] {text}")
            lines.append(f"   (From: {market}...)")
            lines.append("")
        
        lines.append("Apply these lessons to avoid repeating past mistakes.")
        return "\n".join(lines)


# Convenience function
def run_daily_analysis(agent_name: str = None, limit: int = 10):
    """
    Run daily post-mortem analysis for an agent.
    Call this from a cron job or at the start of each trading cycle.
    """
    analyzer = MistakeAnalyzer(agent_name=agent_name)
    lessons = analyzer.analyze_completed_trades(limit=limit)
    return lessons
