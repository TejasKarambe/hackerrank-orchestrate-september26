import os
import sys
import itertools
sys.path.insert(0, os.path.abspath("code"))
from data_loader import load_financial_profiles, load_financial_events, load_exchange_rates, load_requests

profiles = load_financial_profiles()
rates = load_exchange_rates()
events = load_financial_events(profiles, rates)
samples = load_requests("sample_requests.csv")

for s in samples:
    req_id = s["request_id"]
    u_id = s["user_id"]
    req_date = s["request_date"]
    p = profiles[u_id]
    cur = p["current_available_balance"]
    min_b = p["minimum_balance_to_keep"]
    safe = s["gt_amount_safe_to_pay"]
    req_amt = s["requested_amount"]
    if safe >= req_amt:
        continue
    target_dd = cur - (min_b + safe)
    user_evs = events[u_id]
    
    # Check debits occurring between req_date and payday, or in past month
    # Find subset of fixed/scheduled/recurring debits that sum to target_dd
    # Let's collect candidate debits
    past_month_debits = [e for e in user_evs if e["settlement_date"] <= req_date and e["direction"] == "debit" and e["status"] == "settled"]
    # Group by description/category to see monthly amounts
    print(f"\n--- {req_id} ({u_id}) Target Drawdown: {target_dd:.2f} (safe: {safe}) ---")
    # Also print any upcoming pending/scheduled debits in the dataset
    upcoming = [e for e in user_evs if e["settlement_date"] > req_date and e["direction"] == "debit"]
    if upcoming:
        print(f"  Upcoming debits in dataset: {[(e['settlement_date'], e['description'], e['amount'], e['status']) for e in upcoming]}")
