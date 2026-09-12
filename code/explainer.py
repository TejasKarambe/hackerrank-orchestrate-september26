"""
Explanation generation module producing grounded, concise explanations
matching the benchmark style.
"""
from datetime import datetime
from typing import Dict, Any, Optional

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

def format_date_natural(date_str: str) -> str:
    """Formats YYYY-MM-DD to 'D Month YYYY' without leading zeroes (e.g., '15 November 2019')."""
    if not date_str:
        return ""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.day} {MONTH_NAMES[dt.month]} {dt.year}"

def format_currency_amount(amount: float, currency: str) -> str:
    """Formats float amount with commas and currency code, preserving decimals if present."""
    if amount % 1 == 0:
        val_str = f"{int(amount):,}"
    else:
        val_str = f"{amount:,.2f}"
    return f"{currency} {val_str}"

def generate_decision_explanation(
    request: Dict[str, Any],
    profile: Dict[str, Any],
    amount_safe: float,
    affordability_status: str,
    recommended_method: str,
    payment_plan: str,
    earliest_date: str,
    spending_changes: str,
    selected_plan_info: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generates a concise, grounded explanation supporting the recommendation.
    """
    currency = profile["home_currency"]
    req_amt = request["requested_amount"]
    req_amt_str = format_currency_amount(req_amt, currency)
    min_bal = profile["minimum_balance_to_keep"]
    min_bal_str = format_currency_amount(min_bal, currency)
    comp_date_nat = format_date_natural(request["desired_completion_date"])

    # 1. affordable_now with full_payment
    if recommended_method == "full_payment" and spending_changes == "none":
        return f"Pay {req_amt_str} today. This leaves at least {min_bal_str} available over the next 90 days."

    # 2. affordable_with_plan: full payment with spending changes
    if recommended_method == "full_payment" and spending_changes != "none":
        # Parse spending changes
        parts = spending_changes.split("|")
        actions = []
        for p in parts:
            if p.startswith("stop:"):
                ev_id = p.split(":")[1]
                actions.append(f"Stop the recurring expense ({ev_id})")
            elif p.startswith("reduce_to:"):
                _, ev_id, new_a = p.split(":")
                actions.append(f"Reduce the expense ({ev_id}) to {format_currency_amount(float(new_a), currency)}")
        action_text = " and ".join(actions)
        return f"{action_text}, then pay {req_amt_str} today. This leaves at least {min_bal_str} available."

    # 3. affordable_with_plan: installments
    if recommended_method == "installments" and selected_plan_info:
        opt = selected_plan_info.get("opt", {})
        num_p = selected_plan_info["num_payments"]
        inst_amt = opt.get("payment_amount", req_amt / num_p)
        inst_amt_str = format_currency_amount(inst_amt, currency)
        first_dt_nat = format_date_natural(selected_plan_info["first_date"])
        return f"Use {num_p} installments of {inst_amt_str}, starting {first_dt_nat}. This leaves at least {min_bal_str} available."

    # 4. affordable_with_plan: partial_payment
    if recommended_method == "partial_payment":
        safe_str = format_currency_amount(amount_safe, currency)
        rem_amt = round(req_amt - amount_safe, 2)
        rem_str = format_currency_amount(rem_amt, currency)
        earliest_nat = format_date_natural(earliest_date)
        return f"Pay {safe_str} today and the remaining {rem_str} on {earliest_nat}. This completes the full request and keeps the {min_bal_str} minimum protected."

    # 5. affordable_later: wait
    if recommended_method == "wait":
        earliest_nat = format_date_natural(earliest_date)
        return f"Pay {req_amt_str} in full on {earliest_nat}. Paying earlier would take the balance below the {min_bal_str} minimum."

    # 6. not_affordable / not_recommended
    if earliest_date:
        # Full payment could happen after deadline or never safe
        safe_str = format_currency_amount(amount_safe, currency)
        return f"Do not make this payment by {comp_date_nat}. None of the available options keeps the {min_bal_str} minimum protected."
    else:
        if amount_safe > 0:
            safe_str = format_currency_amount(amount_safe, currency)
            return f"Do not proceed with the {req_amt_str} request. Although {safe_str} is available today, the full amount cannot be completed safely within 90 days."
        return f"Do not make this payment by {comp_date_nat}. None of the available options keeps the {min_bal_str} minimum protected."
