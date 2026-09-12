import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.abspath("code"))
from data_loader import load_financial_profiles, load_financial_events, load_exchange_rates, load_requests

profiles = load_financial_profiles()
rates = load_exchange_rates()
events = load_financial_events(profiles, rates)
samples = load_requests("sample_requests.csv")

for s in samples[:8]:
    u_id = s["user_id"]
    req_date = s["request_date"]
    evs = events[u_id]
    past_debits = [e for e in evs if e["settlement_date"] <= req_date and e["direction"] == "debit" and e["status"] == "settled"]
    by_cat = defaultdict(float)
    for e in past_debits:
        by_cat[e["category"]] += e["amount"]
    dates = [e["settlement_date"] for e in past_debits]
    d_min = datetime.strptime(min(dates), "%Y-%m-%d")
    d_max = datetime.strptime(max(dates), "%Y-%m-%d")
    months = max(1.0, (d_max - d_min).days / 30.4375)
    print(f"\n{s['request_id']} ({u_id}) over {months:.1f} months:")
    for c, tot in sorted(by_cat.items()):
        print(f"  {c}: {tot/months:.2f} per month (total={tot:.2f})")
