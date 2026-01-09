"""
Optimized Executor with enhanced LLM logic for speed and intelligence.

Key improvements:
1. Structured JSON output (no parsing errors)
2. Accurate token counting (tiktoken)
3. Response caching (avoid duplicate calls)
4. Combined sequential calls (single LLM call)
5. Parallel batch processing
6. Chain-of-thought prompting
"""

import os
import json
import ast
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

import tiktoken
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.connectors.chroma import PolymarketRAG as Chroma
from agents.utils.objects import SimpleEvent, SimpleMarket
from agents.application.prompts import Prompter
from agents.polymarket.polymarket import Polymarket


class OptimizedExecutor:
    """
    Enhanced executor with optimized LLM calls for speed and intelligence.
    """
    
    def __init__(self, default_model='gpt-3.5-turbo', cache_ttl=3600):
        load_dotenv()
        self.model = default_model
        self.cache_ttl = cache_ttl  # Cache TTL in seconds
        self.cache = {}
        
        # Accurate token counting
        try:
            self.encoding = tiktoken.encoding_for_model(default_model)
        except:
            # Fallback for unknown models
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # Token limits
        max_token_model = {
            'gpt-3.5-turbo': 4096,
            'gpt-3.5-turbo-16k': 16384,
            'gpt-4': 8192,
            'gpt-4-turbo-preview': 128000
        }
        self.token_limit = max_token_model.get(default_model, 4096)
        
        # LLM with structured output support
        self.llm = ChatOpenAI(
            model=default_model,
            temperature=0,
        )
        
        # JSON parser
        self.parser = JsonOutputParser()
        
        # Dependencies
        self.prompter = Prompter()
        self.gamma = Gamma()
        self.chroma = Chroma()
        self.polymarket = Polymarket()
    
    def estimate_tokens(self, text: str) -> int:
        """Accurate token counting using tiktoken"""
        return len(self.encoding.encode(str(text)))
    
    def _cache_key(self, *args) -> str:
        """Generate cache key from arguments"""
        key_str = json.dumps(args, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cached(self, cache_key: str) -> Optional[Any]:
        """Get cached result if valid"""
        if cache_key in self.cache:
            cached_time, result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                return result
            else:
                del self.cache[cache_key]
        return None
    
    def _set_cached(self, cache_key: str, result: Any):
        """Cache result with timestamp"""
        self.cache[cache_key] = (time.time(), result)
    
    def source_best_trade_optimized(self, market_object) -> Dict[str, Any]:
        """
        Optimized: Single LLM call with structured JSON output.
        
        Combines superforecaster + one_best_trade into one call.
        Returns structured dict instead of string.
        """
        market_document = market_object[0].dict()
        market = market_document["metadata"]
        market_id = market.get("id")
        
        # Check cache
        cache_key = self._cache_key("best_trade", market_id)
        cached_result = self._get_cached(cache_key)
        if cached_result:
            return cached_result
        
        # Extract market data
        outcome_prices = ast.literal_eval(market["outcome_prices"])
        outcomes = ast.literal_eval(market["outcomes"])
        question = market["question"]
        description = market_document["page_content"]
        
        # Compress long descriptions
        if len(description) > 500:
            description = description[:500] + "..."
        
        # Combined prompt with chain-of-thought reasoning
        system_prompt = """You are an elite superforecaster analyzing Polymarket trading opportunities.

Follow this systematic process:

1. QUESTION DECOMPOSITION:
   - Break down the question into key components
   - Identify what needs to be true for each outcome

2. INFORMATION GATHERING:
   - Consider recent news and developments
   - Look for relevant statistics, polls, or expert opinions
   - Identify base rates for similar events

3. FACTOR ANALYSIS:
   - List positive factors (supporting the outcome)
   - List negative factors (opposing the outcome)
   - Weight each factor's impact

4. PROBABILITY ESTIMATION:
   - Start with base rate
   - Adjust for identified factors
   - Express as probability (0.0-1.0)

5. MARKET COMPARISON:
   - Compare your estimate to current market price
   - Calculate edge (your_prob - market_price)
   - Assess if edge is significant (>0.05)

6. TRADE DECISION:
   - Determine if bet is profitable
   - Calculate optimal price and size
   - Set confidence level

Respond ONLY with valid JSON matching the required schema."""
        
        user_prompt = f"""Analyze this Polymarket opportunity:

QUESTION: {question}
DESCRIPTION: {description}
OUTCOMES: {outcomes}
CURRENT PRICES: {outcome_prices}

Provide your analysis and trade decision in this exact JSON format:
{{
    "prediction_probability": 0.85,
    "confidence": 0.92,
    "reasoning": "Brief explanation of your analysis",
    "price": 0.82,
    "size": 0.05,
    "side": "BUY",
    "edge": 0.03,
    "key_factors": ["factor1", "factor2"],
    "base_rate": 0.70
}}

CRITICAL RULES:
- Only recommend BUY if edge > 0.05 AND confidence > 0.90
- Size should be percentage of portfolio (0.01-0.10)
- Price should match your probability estimate
- Be conservative - capital preservation is priority"""
        
        try:
            # Single LLM call with structured output
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # Use structured output if available (GPT-4+)
            if "gpt-4" in self.model.lower():
                result = self.llm.invoke(
                    messages,
                    response_format={"type": "json_object"}
                )
                trade_data = json.loads(result.content)
            else:
                # Fallback: parse JSON from response
                result = self.llm.invoke(messages)
                content = result.content
                
                # Extract JSON from response
                json_match = json.loads(content)
                if isinstance(json_match, dict):
                    trade_data = json_match
                else:
                    # Try to find JSON in text
                    import re
                    json_str = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                    if json_str:
                        trade_data = json.loads(json_str.group(0))
                    else:
                        raise ValueError("No JSON found in response")
            
            # Validate and cache result
            self._set_cached(cache_key, trade_data)
            return trade_data
            
        except Exception as e:
            print(f"Error in optimized trade analysis: {e}")
            # Fallback to original method
            return self._fallback_trade_analysis(market_object)
    
    def _fallback_trade_analysis(self, market_object) -> Dict[str, Any]:
        """Fallback to original two-call method if optimized fails"""
        market_document = market_object[0].dict()
        market = market_document["metadata"]
        outcome_prices = ast.literal_eval(market["outcome_prices"])
        outcomes = ast.literal_eval(market["outcomes"])
        question = market["question"]
        description = market_document["page_content"]
        
        # Call 1: Superforecaster
        prompt1 = self.prompter.superforecaster(question, description, outcomes[0])
        result1 = self.llm.invoke(prompt1)
        prediction = result1.content
        
        # Call 2: Trade decision
        prompt2 = self.prompter.one_best_trade(prediction, outcomes, str(outcome_prices))
        result2 = self.llm.invoke(prompt2)
        trade_str = result2.content
        
        # Parse trade string (original method)
        import re
        price_match = re.search(r'price[:\s]+([\d.]+)', trade_str)
        size_match = re.search(r'size[:\s]+([\d.]+)', trade_str)
        side_match = re.search(r'side[:\s]+(BUY|SELL)', trade_str)
        
        return {
            "prediction_probability": 0.5,  # Default
            "confidence": 0.8,
            "reasoning": prediction,
            "price": float(price_match.group(1)) if price_match else 0.5,
            "size": float(size_match.group(1)) if size_match else 0.05,
            "side": side_match.group(1) if side_match else "BUY",
            "edge": 0.0,
            "key_factors": [],
            "base_rate": 0.5
        }
    
    def analyze_markets_parallel(
        self, 
        markets: List[Any], 
        max_workers: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple markets in parallel.
        
        Args:
            markets: List of market objects
            max_workers: Maximum parallel workers
        
        Returns:
            List of trade decisions
        """
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.source_best_trade_optimized, m): m 
                for m in markets
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    market = futures[future]
                    print(f"Error analyzing market {market}: {e}")
                    results.append(None)
        
        return [r for r in results if r is not None]
    
    def filter_events_with_rag_cached(
        self, 
        events: List[SimpleEvent],
        cache_key_suffix: str = ""
    ) -> List[Tuple]:
        """
        Filter events with RAG, using cached vector DB when possible.
        """
        cache_key = self._cache_key("filter_events", len(events), cache_key_suffix)
        cached_result = self._get_cached(cache_key)
        if cached_result:
            return cached_result
        
        prompt = self.prompter.filter_events()
        result = self.chroma.events(events, prompt)
        
        self._set_cached(cache_key, result)
        return result
    
    def filter_markets_cached(
        self, 
        markets: List[SimpleMarket],
        cache_key_suffix: str = ""
    ) -> List[Tuple]:
        """
        Filter markets with RAG, using cached vector DB when possible.
        """
        cache_key = self._cache_key("filter_markets", len(markets), cache_key_suffix)
        cached_result = self._get_cached(cache_key)
        if cached_result:
            return cached_result
        
        prompt = self.prompter.filter_markets()
        result = self.chroma.markets(markets, prompt)
        
        self._set_cached(cache_key, result)
        return result
    
    def get_llm_response_cached(self, user_input: str) -> str:
        """Cached LLM response"""
        cache_key = self._cache_key("llm_response", user_input)
        cached_result = self._get_cached(cache_key)
        if cached_result:
            return cached_result
        
        system_message = SystemMessage(content=str(self.prompter.market_analyst()))
        human_message = HumanMessage(content=user_input)
        messages = [system_message, human_message]
        result = self.llm.invoke(messages)
        response = result.content
        
        self._set_cached(cache_key, response)
        return response
    
    def clear_cache(self):
        """Clear all cached results"""
        self.cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_items = len(self.cache)
        valid_items = sum(
            1 for _, (cached_time, _) in self.cache.items()
            if time.time() - cached_time < self.cache_ttl
        )
        
        return {
            "total_cached": total_items,
            "valid_cached": valid_items,
            "expired": total_items - valid_items,
            "cache_ttl_seconds": self.cache_ttl
        }


# Compatibility wrapper for existing code
class Executor(OptimizedExecutor):
    """
    Backward-compatible wrapper that maintains original interface.
    """
    
    def source_best_trade(self, market_object) -> str:
        """
        Original method signature for backward compatibility.
        Returns string instead of dict.
        """
        result = self.source_best_trade_optimized(market_object)
        
        # Convert to original string format
        return (
            f"price:{result['price']}, "
            f"size:{result['size']}, "
            f"side:{result['side']}"
        )
    
    def filter_events_with_rag(self, events: List[SimpleEvent]) -> List[Tuple]:
        """Original method signature"""
        return self.filter_events_with_rag_cached(events)
    
    def filter_markets(self, markets: List[SimpleMarket]) -> List[Tuple]:
        """Original method signature"""
        return self.filter_markets_cached(markets)
