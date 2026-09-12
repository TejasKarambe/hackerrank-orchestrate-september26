"""
Data loading and preprocessing utilities.
"""
import csv
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    from code.config import DATASET_DIR, IMAGE_EXTRACTED_AMOUNTS
except (ImportError, ModuleNotFoundError):
    from config import DATASET_DIR, IMAGE_EXTRACTED_AMOUNTS


def load_exchange_rates() -> Dict[tuple, float]:
    """Loads exchange rates into a lookup table."""
    rates = {}
    path = DATASET_DIR / "exchange_rates.csv"
    if not path.exists():
        return rates
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row["rate_date"]
            from_c = row["from_currency"]
            to_c = row["to_currency"]
            r = float(row["rate"])
            rates[(date, from_c, to_c)] = r
    return rates

def get_exchange_rate(rates: Dict[tuple, float], date_str: str, from_c: str, to_c: str) -> float:
    """Gets exchange rate between currencies on or closest to given date."""
    if from_c == to_c:
        return 1.0
    if (date_str, from_c, to_c) in rates:
        return rates[(date_str, from_c, to_c)]
    if (date_str, to_c, from_c) in rates:
        return 1.0 / rates[(date_str, to_c, from_c)]
    # Fallback: search closest date
    matching = [(d, r) for (d, fc, tc), r in rates.items() if fc == from_c and tc == to_c]
    if matching:
        matching.sort(key=lambda x: abs((datetime.strptime(x[0], "%Y-%m-%d") - datetime.strptime(date_str, "%Y-%m-%d")).days))
        return matching[0][1]
    matching_rev = [(d, r) for (d, fc, tc), r in rates.items() if fc == to_c and tc == from_c]
    if matching_rev:
        matching_rev.sort(key=lambda x: abs((datetime.strptime(x[0], "%Y-%m-%d") - datetime.strptime(date_str, "%Y-%m-%d")).days))
        return 1.0 / matching_rev[0][1]
    return 1.0

def load_financial_profiles() -> Dict[str, Dict[str, Any]]:
    """Loads financial profiles by user_id."""
    profiles = {}
    path = DATASET_DIR / "financial_profiles.csv"
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            user_id = row["user_id"]
            max_inst = row["max_installment_months"].strip()
            profiles[user_id] = {
                "user_id": user_id,
                "home_currency": row["home_currency"].strip(),
                "current_available_balance": float(row["current_available_balance"]),
                "minimum_balance_to_keep": float(row["minimum_balance_to_keep"]),
                "financial_priorities": [p.strip() for p in row["financial_priorities"].split("|") if p.strip()],
                "expense_categories_to_protect": set(p.strip() for p in row["expense_categories_to_protect"].split("|") if p.strip()),
                "expense_categories_user_is_willing_to_reduce": [p.strip() for p in row["expense_categories_user_is_willing_to_reduce"].split("|") if p.strip()],
                "expense_categories_user_is_willing_to_stop": [p.strip() for p in row["expense_categories_user_is_willing_to_stop"].split("|") if p.strip()],
                "payment_methods_user_will_consider": set(p.strip() for p in row["payment_methods_user_will_consider"].split("|") if p.strip()),
                "max_installment_months": int(max_inst) if max_inst else None,
            }
    return profiles

def load_financial_events(profiles: Dict[str, Dict[str, Any]], rates: Dict[tuple, float]) -> Dict[str, List[Dict[str, Any]]]:
    """Loads financial events grouped by user_id, converted to home currency and with image amounts filled."""
    user_events = {u: [] for u in profiles}
    path = DATASET_DIR / "financial_events.csv"
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            user_id = row["user_id"]
            if user_id not in profiles:
                continue
            ev_id = row["event_id"]
            raw_amt = row["amount"].strip()
            if not raw_amt:
                amt = IMAGE_EXTRACTED_AMOUNTS.get(ev_id, 0.0)
            else:
                amt = float(raw_amt)

            currency = row["currency"].strip()
            home_currency = profiles[user_id]["home_currency"]
            settle_date = row["settlement_date"].strip() or row["event_date"].strip()

            if currency != home_currency and amt > 0:
                rate = get_exchange_rate(rates, settle_date, currency, home_currency)
                amt_in_home = round(amt * rate, 2)
            else:
                amt_in_home = amt

            min_amt = row["minimum_allowed_amount"].strip()
            min_allowed = float(min_amt) if min_amt else None
            if min_allowed is not None and currency != home_currency:
                rate = get_exchange_rate(rates, settle_date, currency, home_currency)
                min_allowed = round(min_allowed * rate, 2)

            event = {
                "event_id": ev_id,
                "user_id": user_id,
                "event_type": row["event_type"].strip(),
                "description": row["description"].strip(),
                "category": row["category"].strip(),
                "direction": row["direction"].strip(),
                "amount": amt_in_home,
                "original_amount": amt,
                "currency": currency,
                "home_currency": home_currency,
                "event_date": row["event_date"].strip(),
                "settlement_date": settle_date,
                "status": row["status"].strip(),
                "linked_event_id": row["linked_event_id"].strip(),
                "flexibility": row["flexibility"].strip(),
                "minimum_allowed_amount": min_allowed,
            }
            user_events[user_id].append(event)

    # Sort each user's events by settlement date
    for u in user_events:
        user_events[u].sort(key=lambda x: (x["settlement_date"], x["event_id"]))

    return user_events

def load_request_payment_options() -> Dict[str, List[Dict[str, Any]]]:
    """Loads payment options grouped by request_id."""
    options = {}
    path = DATASET_DIR / "request_payment_options.csv"
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            req_id = row["request_id"].strip()
            if req_id not in options:
                options[req_id] = []
            freq = row["payment_frequency_days"].strip()
            fee = row["financing_fee"].strip()
            options[req_id].append({
                "payment_option_id": row["payment_option_id"].strip(),
                "request_id": req_id,
                "payment_method": row["payment_method"].strip(),
                "payment_amount": float(row["payment_amount"]),
                "number_of_payments": int(row["number_of_payments"]),
                "first_payment_date": row["first_payment_date"].strip(),
                "payment_frequency_days": int(freq) if freq else None,
                "financing_fee": float(fee) if fee else 0.0,
                "total_payable_amount": float(row["total_payable_amount"]),
            })
    return options

def load_messages() -> List[Dict[str, Any]]:
    """Loads all messages."""
    messages = []
    path = DATASET_DIR / "messages.csv"
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            messages.append({
                "message_id": row["message_id"].strip(),
                "user_id": row["user_id"].strip(),
                "request_id": row["request_id"].strip(),
                "related_event_id": row["related_event_id"].strip(),
                "sent_at": row["sent_at"].strip(),
                "source_type": row["source_type"].strip(),
                "message_text": row["message_text"].strip(),
            })
    return messages

def load_requests(filename: str = "requests.csv") -> List[Dict[str, Any]]:
    """Loads evaluation requests or sample requests."""
    requests = []
    path = DATASET_DIR / filename
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            item = {
                "request_id": row["request_id"].strip(),
                "user_id": row["user_id"].strip(),
                "request_date": row["request_date"].strip(),
                "request_type": row["request_type"].strip(),
                "requested_amount": float(row["requested_amount"]),
                "desired_completion_date": row["desired_completion_date"].strip(),
                "allows_partial_payment": row["allows_partial_payment"].strip().lower() == "true",
                "request_text": row["request_text"].strip(),
            }
            # If sample_requests, also load ground-truth fields
            if "amount_safe_to_pay" in row:
                item["gt_amount_safe_to_pay"] = float(row["amount_safe_to_pay"])
                item["gt_affordability_status"] = row["affordability_status"].strip()
                item["gt_recommended_payment_method"] = row["recommended_payment_method"].strip()
                item["gt_payment_plan"] = row["payment_plan"].strip()
                item["gt_earliest_date_for_full_payment"] = row["earliest_date_for_full_payment"].strip()
                item["gt_spending_changes_needed"] = row["spending_changes_needed"].strip()
                item["gt_decision_explanation"] = row["decision_explanation"].strip()
            requests.append(item)
    return requests
