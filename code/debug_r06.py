import sys
import os
sys.path.insert(0, os.path.abspath("code"))
from data_loader import (
    load_exchange_rates,
    load_financial_profiles,
    load_financial_events,
    load_request_payment_options,
    load_messages,
    load_requests,
)
from cashflow_engine import CashflowEngine
from message_analyzer import analyze_messages_for_user
from decision_engine import DecisionEngine

rates = load_exchange_rates()
profiles = load_financial_profiles()
events = load_financial_events(profiles, rates)
payment_options = load_request_payment_options()
messages = load_messages()
samples = load_requests("sample_requests.csv")

req = [r for r in samples if r["request_id"] == "request_06"][0]
profile = profiles[req["user_id"]]
user_msgs = [m for m in messages if m["user_id"] == req["user_id"]]

messages_by_user = {}
for m in messages:
    uid = m["user_id"]
    if uid not in messages_by_user:
        messages_by_user[uid] = []
    messages_by_user[uid].append(m)

cf_engine = CashflowEngine(profiles, events, messages_by_user)
dec_engine = DecisionEngine(cf_engine)

msg_adj = analyze_messages_for_user(req["user_id"], user_msgs, req["request_date"])
print("Available Balance:", profile["current_available_balance"])
print("Minimum Balance:", profile["minimum_balance_to_keep"])
print("Difference:", profile["current_available_balance"] - profile["minimum_balance_to_keep"])
print("Requested Amount:", req["requested_amount"])
print("GT Safe Amount:", req.get("gt_amount_safe_to_pay"))



