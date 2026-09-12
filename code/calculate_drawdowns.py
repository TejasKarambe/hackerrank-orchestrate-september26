import os
import sys
sys.path.insert(0, os.path.abspath("code"))
from data_loader import load_financial_profiles, load_requests

profiles = load_financial_profiles()
samples = load_requests("sample_requests.csv")
for s in samples:
    p = profiles[s["user_id"]]
    cur = p["current_available_balance"]
    min_b = p["minimum_balance_to_keep"]
    safe = s["gt_amount_safe_to_pay"]
    req_amt = s["requested_amount"]
    if safe < req_amt:
        dd = cur - (min_b + safe)
        print(f"{s['request_id']} ({s['user_id']}) req_date={s['request_date']}: cur={cur}, min={min_b}, safe={safe} => drawdown={dd:.2f}")
    else:
        print(f"{s['request_id']} ({s['user_id']}) req_date={s['request_date']}: FULL SAFE ({safe} >= {req_amt})")
