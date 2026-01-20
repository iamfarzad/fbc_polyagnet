#!/usr/bin/env python3
"""Test Supabase write and read operations."""
import sys
import os
sys.path.append(os.getcwd())

from agents.utils.supabase_client import get_supabase_state
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

print('Testing Supabase connection...')
supa = get_supabase_state()
print(f'URL present: {bool(supa.url)}')
print(f'Key present: {bool(supa.key)}')
print(f'Use local fallback: {supa.use_local_fallback}')
print(f'Client initialized: {bool(supa.client)}')

print('\nTesting write...')
result = supa.log_llm_activity(
    agent='test',
    action_type='test',
    market_question='Test connection',
    prompt_summary='Testing Supabase write',
    reasoning='Verifying connection works',
    conclusion='TEST',
    confidence=1.0
)
print(f'Write result: {result}')

print('\nTesting read...')
activities = supa.get_llm_activity(limit=5, agent='test')
print(f'Read result: {len(activities)} activities found')
if activities:
    print(f'Latest: {activities[0].get("action_type")} - {activities[0].get("conclusion")}')
