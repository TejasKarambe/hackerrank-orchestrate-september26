import os
import sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.abspath("code"))
from data_loader import load_financial_profiles, load_financial_events, load_exchange_rates, load_messages
from cashflow_engine import CashflowEngine, parse_date, format_date
from message_analyzer import analyze_messages_for_user
profiles = load_financial_profiles()
rates = load_exchange_rates()
events = load_financial_events(profiles, rates)
messages = load_messages()
messages_by_user = {}
for m in messages:
    messages_by_user.setdefault(m['user_id'], []).append(m)
cf_engine = CashflowEngine(profiles, events, messages_by_user)
req_date = '2026-01-03'
msg_adj = analyze_messages_for_user('user_06', messages_by_user.get('user_06', []), req_date)
rec = cf_engine.analyze_user_recurring('user_06', req_date, msg_adj)
# Filter monthly and weekly expenses in recurring analysis
active_monthly = []
for m in rec['monthly_expenses']:
    days_ago = (parse_date(req_date) - parse_date(m['last_date'])).days
    if days_ago <= 35:
        active_monthly.append(m)

active_weekly = []
for w in rec['weekly_expenses']:
    days_ago = (parse_date(req_date) - parse_date(w['last_date'])).days
    if days_ago <= 14:
        active_weekly.append(w)

print("Active monthly count:", len(active_monthly))
print("Active weekly count:", len(active_weekly))

# Test simulate
cfs = []
req_dt = parse_date(req_date)
end_dt = req_dt + timedelta(days=90)
sal = rec['salary']
if sal:
    cur_dt = req_dt
    while cur_dt <= end_dt:
        try:
            sal_date = cur_dt.replace(day=sal['pay_day'])
        except ValueError:
            sal_date = cur_dt.replace(day=28)
        if req_dt <= sal_date <= end_dt:
            cfs.append({'date': format_date(sal_date), 'amount': sal['amount'], 'category': 'salary'})
        next_month = cur_dt.month + 1 if cur_dt.month < 12 else 1
        next_year = cur_dt.year + (1 if cur_dt.month == 12 else 0)
        cur_dt = cur_dt.replace(year=next_year, month=next_month, day=1)

for exp in active_monthly:
    cur_dt = req_dt
    while cur_dt <= end_dt:
        try:
            exp_date = cur_dt.replace(day=exp['pay_day'])
        except ValueError:
            exp_date = cur_dt.replace(day=28)
        if req_dt <= exp_date <= end_dt:
            cfs.append({'date': format_date(exp_date), 'amount': -exp['amount'], 'category': exp['category'], 'event_id': exp['event_id']})
        next_month = cur_dt.month + 1 if cur_dt.month < 12 else 1
        next_year = cur_dt.year + (1 if cur_dt.month == 12 else 0)
        cur_dt = cur_dt.replace(year=next_year, month=next_month, day=1)

from decision_engine import DecisionEngine
lowest_bal, _, _ = cf_engine.simulate_balance(
    'user_06', req_date, profiles['user_06']['current_available_balance'], profiles['user_06']['minimum_balance_to_keep'],
    cfs, []
)
safe = max(0.0, lowest_bal - profiles['user_06']['minimum_balance_to_keep'])
print(f"Safe amount with recency filter: {safe} (GT: 603.3)")


