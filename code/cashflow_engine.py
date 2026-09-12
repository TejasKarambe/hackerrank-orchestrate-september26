"""
Cashflow simulation and 90-day balance projection engine.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Set
from collections import defaultdict
import calendar

try:
    from code.config import FORECAST_DAYS
except (ImportError, ModuleNotFoundError):
    from config import FORECAST_DAYS


def parse_date(d_str: str) -> datetime:
    return datetime.strptime(d_str, "%Y-%m-%d")

def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def add_days(d_str: str, days: int) -> str:
    dt = parse_date(d_str) + timedelta(days=days)
    return format_date(dt)

def get_day_of_month(d_str: str) -> int:
    return parse_date(d_str).day

class CashflowEngine:
    def __init__(
        self,
        profiles: Dict[str, Dict[str, Any]],
        user_events: Dict[str, List[Dict[str, Any]]],
        messages_by_user: Dict[str, List[Dict[str, Any]]],
    ):
        self.profiles = profiles
        self.user_events = user_events
        self.messages_by_user = messages_by_user

    def analyze_user_recurring(
        self,
        user_id: str,
        request_date: str,
        msg_adjustments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Identifies recurring income and expenses for user_id based on historical events
        prior to request_date, amended by message adjustments.
        """
        events = self.user_events.get(user_id, [])
        past_events = [e for e in events if (e["settlement_date"] or e["event_date"]) <= request_date]

        # Group by description and category (or by category for flexible categories)
        flexible_cats = {"dining", "streaming", "cloud_storage", "delivery_membership", "music_subscription", "gym", "shopping", "entertainment"}
        desc_groups = defaultdict(list)
        for e in past_events:
            key = (e["category"], e["category"], e["direction"]) if e["category"] in flexible_cats else (e["category"], e["description"], e["direction"])
            desc_groups[key].append(e)


        monthly_expenses = []
        weekly_expenses = []
        salary_info = None

        # Check for upcoming scheduled salary in events
        upcoming_salaries = [
            e for e in events
            if e["category"] == "salary" and e["direction"] == "credit"
            and (e["settlement_date"] or e["event_date"]) >= request_date
            and e["status"] in ["scheduled", "settled"]
        ]
        if upcoming_salaries:
            sal = upcoming_salaries[0]
            salary_info = {
                "amount": sal["amount"],
                "pay_day": get_day_of_month(sal["settlement_date"]),
                "first_date": sal["settlement_date"],
            }
        else:
            # Look at past salaries
            past_salaries = [e for e in past_events if e["category"] == "salary" and e["direction"] == "credit" and e["status"] == "settled"]
            if past_salaries:
                reg_sal = [s for s in past_salaries if any(w in s["description"].lower() for w in ["payroll", "base salary", "primary", "net salary"])]
                if not reg_sal:
                    reg_sal = past_salaries
                last_sal = reg_sal[-1]
                if "final" not in last_sal["description"].lower():
                    days = [get_day_of_month(s["settlement_date"]) for s in reg_sal]
                    mode_day = max(set(days), key=days.count)
                    salary_info = {
                        "amount": last_sal["amount"],
                        "pay_day": mode_day,
                        "first_date": last_sal["settlement_date"],
                    }

        # Apply message salary adjustments
        if msg_adjustments.get("contract_ended"):
            salary_info = None
        else:
            if msg_adjustments.get("new_recurring_salary") is not None:
                if salary_info is None:
                    salary_info = {
                        "amount": msg_adjustments["new_recurring_salary"],
                        "pay_day": 15,
                        "first_date": f"{request_date[:7]}-15",
                    }
                else:
                    salary_info["amount"] = msg_adjustments["new_recurring_salary"]
            elif msg_adjustments.get("salary_override_amount") is not None:
                if salary_info is None:
                    salary_info = {
                        "amount": msg_adjustments["salary_override_amount"],
                        "pay_day": 15,
                        "first_date": f"{request_date[:7]}-15",
                    }
                else:
                    salary_info["amount"] = msg_adjustments["salary_override_amount"]

            if salary_info is not None and msg_adjustments.get("salary_override_date") is not None:
                salary_info["first_date"] = msg_adjustments["salary_override_date"]
                salary_info["pay_day"] = get_day_of_month(msg_adjustments["salary_override_date"])
        if salary_info is None and msg_adjustments.get("confirmed_inflow_events"):
            for inf in msg_adjustments["confirmed_inflow_events"]:
                if inf.get("category") == "salary":
                    salary_info = {
                        "amount": inf["amount"],
                        "pay_day": get_day_of_month(inf["date"]),
                        "first_date": inf["date"],
                    }


        # Identify monthly recurring expenses
        for (cat, desc, direction), ev_list in desc_groups.items():
            if direction != "debit" or cat == "salary":
                continue

            # Check settled events
            settled = [e for e in ev_list if e["status"] == "settled"]
            if not settled:
                continue

            # Check frequency
            dates = [parse_date(e["settlement_date"]) for e in settled]
            dates.sort()
            latest_ev = settled[-1]
            days_since_last = (parse_date(request_date) - dates[-1]).days

            if len(dates) >= 2:
                diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                avg_diff = sum(diffs) / len(diffs)

                # Monthly or ~3-week expense (~18 to 35 days)
                if 18 <= avg_diff <= 35:
                    amt = latest_ev["amount"]
                    if cat == "rent" and msg_adjustments.get("rent_increase_percent", 0.0) > 0:
                        amt = round(amt * (1.0 + msg_adjustments["rent_increase_percent"] / 100.0), 2)

                    monthly_expenses.append({
                        "event_id": latest_ev["event_id"],
                        "category": cat,
                        "description": latest_ev["description"],
                        "amount": amt,
                        "pay_day": min(d.day for d in dates[-2:]) if len(dates) >= 2 and (dates[-1] - dates[-2]).days <= 25 else dates[-1].day,
                        "flexibility": latest_ev["flexibility"],
                        "minimum_allowed_amount": latest_ev["minimum_allowed_amount"],
                        "last_date": format_date(dates[-1]),
                    })

                # Weekly expense (~5 to 10 days) e.g. groceries, transport
                elif 5 <= avg_diff <= 10:
                    amts = [e["amount"] for e in settled[-4:]] # last month
                    avg_amt = sum(amts) / len(amts)
                    weekly_expenses.append({
                        "event_id": latest_ev["event_id"],
                        "category": cat,
                        "description": desc,
                        "avg_amount": avg_amt,
                        "day_of_week": dates[-1].weekday(),
                        "last_date": format_date(dates[-1]),
                    })

        return {
            "salary": salary_info,
            "monthly_expenses": monthly_expenses,
            "weekly_expenses": weekly_expenses,
        }

    def generate_projected_cashflows(
        self,
        user_id: str,
        request_date: str,
        msg_adjustments: Dict[str, Any],
        spending_changes: Optional[Dict[str, Tuple[str, Optional[float]]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates daily cash flows from request_date to request_date + 90 days.
        spending_changes: dict mapping event_id -> ('stop', None) or ('reduce_to', new_amount)
        """
        if spending_changes is None:
            spending_changes = {}

        req_dt = parse_date(request_date)
        end_dt = req_dt + timedelta(days=FORECAST_DAYS)
        events = self.user_events.get(user_id, [])

        recurring_info = self.analyze_user_recurring(user_id, request_date, msg_adjustments)
        cashflows = []

        # 1. Add pending and scheduled debits explicitly present in dataset
        ignore_ids = msg_adjustments.get("ignore_event_ids", set())
        for e in events:
            dt_str = e["settlement_date"] or e["event_date"]
            if not dt_str:
                continue
            ev_dt = parse_date(dt_str)
            if req_dt <= ev_dt <= end_dt:
                if e["event_id"] in ignore_ids:
                    continue
                # Pending debits
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

        # 2. Add message confirmed inflows (e.g. invoices)
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

        # 3. Project recurring monthly salary
        sal = recurring_info.get("salary")
        if sal and sal["amount"] > 0:
            cur_dt = req_dt
            while cur_dt <= end_dt:
                _, max_d = calendar.monthrange(cur_dt.year, cur_dt.month)
                pay_day = min(sal["pay_day"], max_d)
                sal_date = cur_dt.replace(day=pay_day)
                if req_dt <= sal_date <= end_dt:
                    cashflows.append({
                        "date": format_date(sal_date),
                        "amount": sal["amount"],
                        "type": "salary",
                        "event_id": None,
                        "category": "salary",
                    })
                # Advance to next month
                next_month = cur_dt.month + 1 if cur_dt.month < 12 else 1
                next_year = cur_dt.year + (1 if cur_dt.month == 12 else 0)
                cur_dt = cur_dt.replace(year=next_year, month=next_month, day=1)

        # 4. Project recurring monthly expenses
        for exp in recurring_info.get("monthly_expenses", []):
            ev_id = exp["event_id"]
            amt = exp["amount"]

            # Check spending change
            if ev_id in spending_changes:
                action, new_amt = spending_changes[ev_id]
                if action == "stop":
                    continue
                elif action == "reduce_to" and new_amt is not None:
                    amt = new_amt

            cur_dt = req_dt
            while cur_dt <= end_dt:
                _, max_d = calendar.monthrange(cur_dt.year, cur_dt.month)
                pay_day = min(exp["pay_day"], max_d)
                exp_date = cur_dt.replace(day=pay_day)

                if req_dt <= exp_date <= end_dt:
                    cashflows.append({
                        "date": format_date(exp_date),
                        "amount": -amt,
                        "type": "recurring_monthly",
                        "event_id": ev_id,
                        "category": exp["category"],
                    })
                next_month = cur_dt.month + 1 if cur_dt.month < 12 else 1
                next_year = cur_dt.year + (1 if cur_dt.month == 12 else 0)
                cur_dt = cur_dt.replace(year=next_year, month=next_month, day=1)

        # 5. Project recurring weekly expenses (only if category not already in monthly expenses)
        monthly_cats = set(exp["category"] for exp in recurring_info.get("monthly_expenses", []))
        for wexp in recurring_info.get("weekly_expenses", []):
            if wexp["category"] in monthly_cats:
                continue
            cur_dt = req_dt
            target_weekday = wexp["day_of_week"]
            while cur_dt <= end_dt:
                if cur_dt.weekday() == target_weekday and cur_dt >= req_dt:
                    cashflows.append({
                        "date": format_date(cur_dt),
                        "amount": -wexp["avg_amount"],
                        "type": "recurring_weekly",
                        "event_id": wexp["event_id"],
                        "category": wexp["category"],
                    })
                cur_dt += timedelta(days=1)


        # Sort all cash flows chronologically
        cashflows.sort(key=lambda x: (x["date"], 0 if x["amount"] < 0 else 1))
        return cashflows

    def simulate_balance(
        self,
        user_id: str,
        request_date: str,
        initial_balance: float,
        minimum_balance: float,
        base_cashflows: List[Dict[str, Any]],
        extra_payments: List[Tuple[str, float]]
    ) -> Tuple[float, List[Tuple[str, float]], bool]:
        """
        Simulates daily balance over 90 days given initial balance, cashflows, and extra payments.
        Returns (lowest_balance, daily_balances, is_safe).
        """
        all_flows = defaultdict(float)
        for cf in base_cashflows:
            all_flows[cf["date"]] += cf["amount"]
        for p_date, p_amt in extra_payments:
            all_flows[p_date] -= p_amt

        req_dt = parse_date(request_date)
        end_dt = req_dt + timedelta(days=FORECAST_DAYS)

        cur_balance = initial_balance
        lowest_balance = cur_balance
        daily_balances = []

        cur_dt = req_dt
        while cur_dt <= end_dt:
            d_str = format_date(cur_dt)
            if d_str in all_flows:
                cur_balance += all_flows[d_str]

            if cur_balance < lowest_balance:
                lowest_balance = cur_balance

            daily_balances.append((d_str, cur_balance))
            cur_dt += timedelta(days=1)

        is_safe = lowest_balance >= minimum_balance
        return lowest_balance, daily_balances, is_safe
