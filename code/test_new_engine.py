import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict

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

def add_days(d_str, days):
    dt = parse_date(d_str) + timedelta(days=days)
    return format_date(dt)

def simulate_balance(initial_balance, min_balance, cashflows, extra_payments):
    daily_delta = defaultdict(float)
    for cf in cashflows:
        daily_delta[cf["date"]] += cf["amount"]
    for d, amt in extra_payments:
        daily_delta[d] -= amt

    all_dates = sorted(daily_delta.keys())
    cur_bal = initial_balance
    lowest_bal = cur_bal

    for d in all_dates:
        cur_bal += daily_delta[d]
        if cur_bal < lowest_bal:
            lowest_bal = cur_bal

    is_safe = (lowest_bal >= min_balance - 1e-4)
    return lowest_bal, is_safe

# Let's write the new cashflow generator:
def generate_cashflows_v2(user_id, request_date, msg_adjustments, spending_changes=None):
    if spending_changes is None:
        spending_changes = {}

    req_dt = parse_date(request_date)
    end_dt = req_dt + timedelta(days=90)
    user_evs = events.get(user_id, [])
    past_evs = [e for e in user_evs if (e["settlement_date"] or e["event_date"]) <= request_date]

    cashflows = []

    # 1. Pending debits from dataset
    ignore_ids = msg_adjustments.get("ignore_event_ids", set())
    for e in user_evs:
        dt_str = e["settlement_date"] or e["event_date"]
        if not dt_str:
            continue
        ev_dt = parse_date(dt_str)
        if req_dt <= ev_dt <= end_dt:
            if e["event_id"] in ignore_ids:
                continue
            if e["direction"] == "debit" and e["status"] in ["pending", "scheduled"]:
                amt = e["amount"]
                if e["event_id"] in spending_changes:
                    action, new_amt = spending_changes[e["event_id"]]
                    if action == "stop":
                        continue
                    elif action == "reduce_to" and new_amt is not None:
                        amt = new_amt
                cashflows.append({
                    "date": dt_str,
                    "amount": -amt,
                    "type": "pending_debit",
                    "event_id": e["event_id"],
                    "category": e["category"],
                })

    # 2. Confirmed message inflows
    for inf in msg_adjustments.get("confirmed_inflow_events", []):
        if inf.get("category") != "salary":
            dt_str = inf["date"]
            inf_dt = parse_date(dt_str)
            if req_dt <= inf_dt <= end_dt:
                cashflows.append({
                    "date": dt_str,
                    "amount": inf["amount"],
                    "type": "confirmed_inflow",
                    "event_id": None,
                    "category": inf["category"],
                })

    # 3. Salary
    salary_info = None
    upcoming_sal = [
        e for e in user_evs
        if e["category"] == "salary" and e["direction"] == "credit"
        and (e["settlement_date"] or e["event_date"]) >= request_date
        and e["status"] in ["scheduled", "settled"]
    ]
    if upcoming_sal:
        sal = upcoming_sal[0]
        salary_info = {
            "amount": sal["amount"],
            "pay_day": parse_date(sal["settlement_date"]).day,
        }
    else:
        past_sal = [e for e in past_evs if e["category"] == "salary" and e["direction"] == "credit" and e["status"] == "settled"]
        if past_sal:
            last_sal = past_sal[-1]
            if "final" not in last_sal["description"].lower():
                salary_info = {
                    "amount": last_sal["amount"],
                    "pay_day": parse_date(last_sal["settlement_date"]).day,
                }

    if msg_adjustments.get("contract_ended"):
        salary_info = None
    else:
        if msg_adjustments.get("new_recurring_salary") is not None:
            salary_info = {"amount": msg_adjustments["new_recurring_salary"], "pay_day": 15}
        elif msg_adjustments.get("salary_override_amount") is not None:
            salary_info = {"amount": msg_adjustments["salary_override_amount"], "pay_day": 15}
        if salary_info and msg_adjustments.get("salary_override_date"):
            salary_info["pay_day"] = parse_date(msg_adjustments["salary_override_date"]).day

    if salary_info and salary_info["amount"] > 0:
        cur_dt = req_dt
        while cur_dt <= end_dt:
            pay_day = min(salary_info["pay_day"], 28)
            try:
                sal_date = cur_dt.replace(day=salary_info["pay_day"])
            except ValueError:
                sal_date = cur_dt.replace(day=pay_day)
            if req_dt <= sal_date <= end_dt:
                cashflows.append({
                    "date": format_date(sal_date),
                    "amount": salary_info["amount"],
                    "type": "salary",
                    "event_id": None,
                    "category": "salary",
                })
            next_m = cur_dt.month + 1 if cur_dt.month < 12 else 1
            next_y = cur_dt.year + (1 if cur_dt.month == 12 else 0)
            cur_dt = cur_dt.replace(year=next_y, month=next_m, day=1)

    # 4. Recurring expenses
    # Group by category (since within a category descriptions change: e.g. "Neighbourhood restaurant", "Bakery and snacks")
    cat_groups = defaultdict(list)
    for e in past_evs:
        if e["direction"] == "debit" and e["category"] != "salary" and e["status"] == "settled":
            cat_groups[e["category"]].append(e)

    for cat, ev_list in cat_groups.items():
        ev_list.sort(key=lambda x: x["settlement_date"])
        dates = [parse_date(e["settlement_date"]) for e in ev_list]
        latest_ev = ev_list[-1]
        days_since_last = (req_dt - dates[-1]).days

        if len(dates) < 2:
            continue

        diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        recent_diffs = diffs[-3:]
        cadence = sum(recent_diffs) / len(recent_diffs)

        # Skip if expense stopped (no occurrence in 2 * cadence + 5 days)
        if days_since_last > max(35, int(cadence * 1.8)):
            continue

        amt = latest_ev["amount"]
        ev_id = latest_ev["event_id"]

        if cat == "rent" and msg_adjustments.get("rent_increase_percent", 0.0) > 0:
            amt = round(amt * (1.0 + msg_adjustments["rent_increase_percent"] / 100.0), 2)

        # Apply spending change
        if ev_id in spending_changes:
            action, new_amt = spending_changes[ev_id]
            if action == "stop":
                continue
            elif action == "reduce_to" and new_amt is not None:
                amt = new_amt

        # Classify cadence
        if cadence >= 25:
            # Monthly on fixed calendar day
            pay_day = dates[-1].day
            cur_dt = req_dt
            while cur_dt <= end_dt:
                try:
                    exp_date = cur_dt.replace(day=pay_day)
                except ValueError:
                    exp_date = cur_dt.replace(day=28)
                if req_dt <= exp_date <= end_dt:
                    cashflows.append({
                        "date": format_date(exp_date),
                        "amount": -amt,
                        "type": "recurring_monthly",
                        "event_id": ev_id,
                        "category": cat,
                    })
                next_m = cur_dt.month + 1 if cur_dt.month < 12 else 1
                next_y = cur_dt.year + (1 if cur_dt.month == 12 else 0)
                cur_dt = cur_dt.replace(year=next_y, month=next_m, day=1)
        else:
            # Periodic interval (e.g. 5, 7, 10, 14, 21 days)
            int_days = max(1, round(cadence))
            # Step forward from last_date
            cur_dt = dates[-1] + timedelta(days=int_days)
            while cur_dt <= end_dt:
                if cur_dt >= req_dt:
                    cashflows.append({
                        "date": format_date(cur_dt),
                        "amount": -amt,
                        "type": "recurring_periodic",
                        "event_id": ev_id,
                        "category": cat,
                    })
                cur_dt += timedelta(days=int_days)

    return cashflows

def find_spending_changes(user_id, req_date, req_amt, msg_adj, profile):
    # Candidate stops and reduces
    past_evs = [e for e in events.get(user_id, []) if (e["settlement_date"] or e["event_date"]) <= req_date and e["status"] == "settled"]
    willing_stop = profile["expense_categories_user_is_willing_to_stop"]
    willing_reduce = profile["expense_categories_user_is_willing_to_reduce"]
    protected = profile["expense_categories_to_protect"]

    # Find unique recurring events
    latest_by_cat = {}
    for e in past_evs:
        cat = e["category"]
        if cat in protected:
            continue
        latest_by_cat[cat] = e

    candidate_stops = []
    candidate_reduces = []
    for cat, e in latest_by_cat.items():
        flex = e["flexibility"]
        ev_id = e["event_id"]
        amt = e["amount"]
        min_amt = e["minimum_allowed_amount"] or 0.0

        if "stoppable" in flex and cat in willing_stop:
            candidate_stops.append((ev_id, amt))
        if "reducible" in flex and cat in willing_reduce:
            saving = amt - min_amt
            if saving > 0:
                candidate_reduces.append((ev_id, min_amt, saving))

    # Test single stop
    for s_id, _ in candidate_stops:
        changes = {s_id: ("stop", None)}
        cfs = generate_cashflows_v2(user_id, req_date, msg_adj, changes)
        _, is_safe = simulate_balance(profile["current_available_balance"], profile["minimum_balance_to_keep"], cfs, [(req_date, req_amt)])
        if is_safe:
            return f"stop:{s_id}"

    # Test single reduce
    for r_id, min_amt, _ in candidate_reduces:
        changes = {r_id: ("reduce_to", min_amt)}
        cfs = generate_cashflows_v2(user_id, req_date, msg_adj, changes)
        _, is_safe = simulate_balance(profile["current_available_balance"], profile["minimum_balance_to_keep"], cfs, [(req_date, req_amt)])
        if is_safe:
            new_amt_str = f"{min_amt:.2f}".rstrip("0").rstrip(".") if min_amt % 1 != 0 else str(int(min_amt))
            return f"reduce_to:{r_id}:{new_amt_str}"

    # Test stop + reduce
    for s_id, _ in candidate_stops:
        for r_id, min_amt, _ in candidate_reduces:
            if s_id == r_id:
                continue
            changes = {s_id: ("stop", None), r_id: ("reduce_to", min_amt)}
            cfs = generate_cashflows_v2(user_id, req_date, msg_adj, changes)
            _, is_safe = simulate_balance(profile["current_available_balance"], profile["minimum_balance_to_keep"], cfs, [(req_date, req_amt)])
            if is_safe:
                new_amt_str = f"{min_amt:.2f}".rstrip("0").rstrip(".") if min_amt % 1 != 0 else str(int(min_amt))
                return f"stop:{s_id}|reduce_to:{r_id}:{new_amt_str}"

    return "none"

print("\nTesting spending changes for target requests:")
for req_id in ["request_06", "request_11", "request_21"]:
    s = [x for x in samples if x["request_id"] == req_id][0]
    u_id = s["user_id"]
    r_date = s["request_date"]
    r_amt = s["requested_amount"]
    p = profiles[u_id]
    msg_adj = analyze_messages_for_user(u_id, messages_by_user.get(u_id, []), r_date)
    sp = find_spending_changes(u_id, r_date, r_amt, msg_adj, p)
    print(f"{req_id}: Found={sp} | GT={s['gt_spending_changes_needed']}")

