import os
import sys
sys.path.insert(0, os.path.abspath("code"))
from data_loader import (
    load_financial_profiles,
    load_financial_events,
    load_exchange_rates,
    load_request_payment_options,
    load_messages,
    load_requests,
)
from cashflow_engine import CashflowEngine
from decision_engine import DecisionEngine
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

def evaluate_suite(cf_eng):
    dec_eng = DecisionEngine(cf_eng)
    correct_status = 0
    correct_method = 0
    correct_plan = 0
    correct_date = 0
    correct_sp = 0
    diffs = []
    for s in samples:
        req_id = s["request_id"]
        res = dec_eng.evaluate_request(
            request=s,
            profile=profiles[s["user_id"]],
            payment_options=payment_options.get(req_id, []),
            user_messages=messages_by_user.get(s["user_id"], []),
        )
        s_ok = (res["affordability_status"] == s["gt_affordability_status"])
        m_ok = (res["recommended_payment_method"] == s["gt_recommended_payment_method"])
        p_ok = (res["payment_plan"] == s["gt_payment_plan"])
        d_ok = (res["earliest_date_for_full_payment"] == s["gt_earliest_date_for_full_payment"])
        sp_ok = (res["spending_changes_needed"] == s["gt_spending_changes_needed"])

        if s_ok: correct_status += 1
        if m_ok: correct_method += 1
        if p_ok: correct_plan += 1
        if d_ok: correct_date += 1
        if sp_ok: correct_sp += 1

        if not (s_ok and m_ok and p_ok and d_ok and sp_ok):
            diffs.append((req_id, res, s))

    print(f"Status: {correct_status}/25, Method: {correct_method}/25, Plan: {correct_plan}/25, Date: {correct_date}/25, SP: {correct_sp}/25")
    for r_id, pred, gt in diffs:
        print(f"\n{r_id}:")
        if pred["affordability_status"] != gt["gt_affordability_status"]:
            print(f"  Status: {pred['affordability_status']} (GT: {gt['gt_affordability_status']})")
        if pred["recommended_payment_method"] != gt["gt_recommended_payment_method"]:
            print(f"  Method: {pred['recommended_payment_method']} (GT: {gt['gt_recommended_payment_method']})")
        if pred["payment_plan"] != gt["gt_payment_plan"]:
            print(f"  Plan:   {pred['payment_plan']} (GT: {gt['gt_payment_plan']})")
        if pred["earliest_date_for_full_payment"] != gt["gt_earliest_date_for_full_payment"]:
            print(f"  Date:   {pred['earliest_date_for_full_payment']} (GT: {gt['gt_earliest_date_for_full_payment']})")
        if pred["spending_changes_needed"] != gt["gt_spending_changes_needed"]:
            print(f"  SP:     {pred['spending_changes_needed']} (GT: {gt['gt_spending_changes_needed']})")

cf_eng = CashflowEngine(profiles, events, messages_by_user)
evaluate_suite(cf_eng)
