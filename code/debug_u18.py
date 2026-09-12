import os
import sys
sys.path.insert(0, os.path.abspath("code"))
from data_loader import load_financial_profiles, load_financial_events, load_exchange_rates, load_messages, load_requests
from cashflow_engine import CashflowEngine, parse_date
from message_analyzer import analyze_messages_for_user

profiles = load_financial_profiles()
rates = load_exchange_rates()
events = load_financial_events(profiles, rates)
messages = load_messages()
messages_by_user = {}
for m in messages:
    messages_by_user.setdefault(m['user_id'], []).append(m)
cf_engine = CashflowEngine(profiles, events, messages_by_user)
req_date = '2026-07-07'
msg_adj = analyze_messages_for_user('user_18', messages_by_user.get('user_18', []), req_date)
prof = profiles['user_18']
print("Profile 18:")
print("Available:", prof["current_available_balance"])
print("Min bal:", prof["minimum_balance_to_keep"])
print("Events for user 18:")
for e in events["user_18"]:
    print(e["settlement_date"], e["category"], e["description"], e["amount"], e["status"])
