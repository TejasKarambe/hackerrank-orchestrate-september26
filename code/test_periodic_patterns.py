import os
import sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.abspath("code"))
from data_loader import (
    load_financial_profiles,
    load_financial_events,
    load_exchange_rates,
    load_request_payment_options,
    load_messages,
    load_requests,
)
from message_analyzer import analyze_messages_for_user

profiles = load_financial_profiles()
rates = load_exchange_rates()
events = load_financial_events(profiles, rates)
payment_options = load_request_payment_options()
messages = load_messages()
messages_by_user = {}
for m in messages:
    messages_by_user.setdefault(m["user_id"], []).append(m)

samples = load_requests("sample_requests.csv")

def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")

def format_date(dt):
    return dt.strftime("%Y-%m-%d")

def test_periodic_patterns(user_id, req_date):
    user_evs = events[user_id]
    past = [e for e in user_evs if e["settlement_date"] <= req_date and e["direction"] == "debit" and e["status"] == "settled"]
    
    # Categories that are fixed calendar subscriptions/bills
    fixed_cats = {"rent", "housing", "utilities", "insurance", "education", "debt_repayment", 
                  "streaming", "cloud_storage", "music_subscription", "delivery_membership", "gym"}
    
    # Check debits by category
    cats = set(e["category"] for e in past)
    print(f"\nUser {user_id} categories on {req_date}:")
    for cat in sorted(cats):
        cat_evs = [e for e in past if e["category"] == cat]
        cat_evs.sort(key=lambda x: x["settlement_date"])
        dates = [parse_date(e["settlement_date"]) for e in cat_evs]
        latest = cat_evs[-1]
        days_ago = (parse_date(req_date) - dates[-1]).days
        if len(dates) >= 2:
            diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
            avg_diff = sum(diffs) / len(diffs)
            recent_diffs = diffs[-3:]
            recent_avg = sum(recent_diffs) / len(recent_diffs)
            print(f"  {cat}: {len(cat_evs)} events, last: {latest['settlement_date']} ({days_ago}d ago), avg_diff: {avg_diff:.1f}d (recent: {recent_avg:.1f}d), latest_amt: {latest['amount']}")

for uid, rdate in [("user_06", "2026-01-03"), ("user_11", "2025-05-03"), ("user_18", "2026-07-07"), ("user_21", "2026-04-03")]:
    test_periodic_patterns(uid, rdate)
