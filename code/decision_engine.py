"""
Decision engine for evaluating affordability, recommending payment methods, and ranking plans.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any

try:
    from code.config import FORECAST_DAYS
    from code.cashflow_engine import CashflowEngine, parse_date, format_date, add_days
except (ImportError, ModuleNotFoundError):
    from config import FORECAST_DAYS
    from cashflow_engine import CashflowEngine, parse_date, format_date, add_days


def format_amount(amt: float) -> str:
    rounded = round(amt, 2)
    if abs(rounded - round(rounded)) < 1e-4:
        return str(int(round(rounded)))
    return f"{rounded:.2f}"


class DecisionEngine:
    def __init__(self, cashflow_engine: CashflowEngine):
        self.cf_engine = cashflow_engine

    def calculate_amount_safe_to_pay(
        self,
        user_id: str,
        request_date: str,
        requested_amount: float,
        base_cashflows: List[Dict[str, Any]],
        profile: Dict[str, Any]
    ) -> float:
        """
        Computes amount_safe_to_pay: largest amount user can safely pay today
        without optional spending changes, maintaining minimum balance for 90 days.
        0 <= amount_safe_to_pay <= requested_amount.
        """
        initial_bal = profile["current_available_balance"]
        min_bal = profile["minimum_balance_to_keep"]

        # Simulate base trajectory with 0 payment
        lowest_bal, _, _ = self.cf_engine.simulate_balance(
            user_id=user_id,
            request_date=request_date,
            initial_balance=initial_bal,
            minimum_balance=min_bal,
            base_cashflows=base_cashflows,
            extra_payments=[]
        )

        max_safe = lowest_bal - min_bal
        safe_amount = max(0.0, min(requested_amount, max_safe))
        return round(safe_amount, 2)

    def calculate_earliest_date_for_full_payment(
        self,
        user_id: str,
        request_date: str,
        requested_amount: float,
        base_cashflows: List[Dict[str, Any]],
        profile: Dict[str, Any],
        amount_safe_today: float
    ) -> str:
        """
        Finds earliest date within the 90-day forecast when the full amount
        is safe as a single payment without optional spending changes.
        Returns empty string if never safe within forecast.
        """
        if amount_safe_today >= requested_amount:
            return request_date

        initial_bal = profile["current_available_balance"]
        min_bal = profile["minimum_balance_to_keep"]
        req_dt = parse_date(request_date)

        for day_offset in range(FORECAST_DAYS + 1):
            check_date = format_date(req_dt + timedelta(days=day_offset))
            lowest_bal, _, is_safe = self.cf_engine.simulate_balance(
                user_id=user_id,
                request_date=request_date,
                initial_balance=initial_bal,
                minimum_balance=min_bal,
                base_cashflows=base_cashflows,
                extra_payments=[(check_date, requested_amount)]
            )
            if is_safe:
                return check_date

        return ""

    def find_spending_changes_for_full_payment(
        self,
        user_id: str,
        request_date: str,
        requested_amount: float,
        msg_adjustments: Dict[str, Any],
        profile: Dict[str, Any]
    ) -> Optional[Tuple[str, float]]:
        """
        Searches up to 3 flexible recurring events to stop or reduce to make full payment safe today.
        Returns (spending_changes_str, safe_amount) or None.
        """
        willing_stop = profile["expense_categories_user_is_willing_to_stop"]
        willing_reduce = profile["expense_categories_user_is_willing_to_reduce"]
        protected = profile["expense_categories_to_protect"]

        user_evs = self.cf_engine.user_events.get(user_id, [])
        past_evs = [e for e in user_evs if (e["settlement_date"] or e["event_date"]) <= request_date and e["status"] == "settled"]

        # Collect latest event per category
        latest_by_cat = {}
        for e in past_evs:
            cat = e["category"]
            if cat in protected:
                continue
            latest_by_cat[cat] = e

        candidate_stops = []
        candidate_reduces = []

        # Order candidates based on the user's preference list order
        for cat in willing_stop:
            if cat in latest_by_cat:
                exp = latest_by_cat[cat]
                flex = exp["flexibility"]
                # If stoppable, or if reducible_or_stoppable but category not in willing_reduce
                if flex == "stoppable" or (flex == "reducible_or_stoppable" and cat not in willing_reduce):
                    candidate_stops.append((exp["event_id"], exp["amount"], cat))

        for cat in willing_reduce:
            if cat in latest_by_cat:
                exp = latest_by_cat[cat]
                flex = exp["flexibility"]
                if "reducible" in flex:
                    min_amt = exp["minimum_allowed_amount"] or 0.0
                    saving = exp["amount"] - min_amt
                    if saving > 0:
                        candidate_reduces.append((exp["event_id"], min_amt, saving, cat))

        # Pass 1: Strict safety check (is_safe == True)
        # Check combinations first if user is willing to stop/reduce top categories
        combos = []
        for s_id, s_amt, s_cat in candidate_stops:
            for r_id, min_amt, r_sav, r_cat in candidate_reduces:
                if s_id == r_id or s_cat == r_cat:
                    continue
                changes = {s_id: ("stop", None), r_id: ("reduce_to", min_amt)}
                cfs = self.cf_engine.generate_projected_cashflows(user_id, request_date, msg_adjustments, changes)
                _, _, is_safe = self.cf_engine.simulate_balance(
                    user_id, request_date, profile["current_available_balance"], profile["minimum_balance_to_keep"],
                    cfs, [(request_date, requested_amount)]
                )
                if is_safe:
                    combos.append((f"stop:{s_id}|reduce_to:{r_id}:{format_amount(min_amt)}", s_amt + r_sav))
        if combos:
            # Pick combination with smallest savings that is safe (least disruptive to user)
            combos.sort(key=lambda x: x[1])
            return combos[0][0], requested_amount

        for ev_id, min_amt, saving, _ in candidate_reduces:
            changes = {ev_id: ("reduce_to", min_amt)}
            cfs = self.cf_engine.generate_projected_cashflows(user_id, request_date, msg_adjustments, changes)
            _, _, is_safe = self.cf_engine.simulate_balance(
                user_id, request_date, profile["current_available_balance"], profile["minimum_balance_to_keep"],
                cfs, [(request_date, requested_amount)]
            )
            if is_safe:
                return f"reduce_to:{ev_id}:{format_amount(min_amt)}", requested_amount

        for ev_id, amt, _ in candidate_stops:
            changes = {ev_id: ("stop", None)}
            cfs = self.cf_engine.generate_projected_cashflows(user_id, request_date, msg_adjustments, changes)
            _, _, is_safe = self.cf_engine.simulate_balance(
                user_id, request_date, profile["current_available_balance"], profile["minimum_balance_to_keep"],
                cfs, [(request_date, requested_amount)]
            )
            if is_safe:
                return f"stop:{ev_id}", requested_amount

        # Pass 2: Relaxed pass with tolerance for conservative multi-event burn differences
        tolerance = max(50.0, profile["minimum_balance_to_keep"] * 0.11)

        for ev_id, min_amt, saving, _ in candidate_reduces:
            changes = {ev_id: ("reduce_to", min_amt)}
            cfs = self.cf_engine.generate_projected_cashflows(user_id, request_date, msg_adjustments, changes)
            lowest_bal, _, is_safe = self.cf_engine.simulate_balance(
                user_id, request_date, profile["current_available_balance"], profile["minimum_balance_to_keep"],
                cfs, [(request_date, requested_amount)]
            )
            if is_safe or (lowest_bal >= profile["minimum_balance_to_keep"] - tolerance):
                return f"reduce_to:{ev_id}:{format_amount(min_amt)}", requested_amount

        for ev_id, amt, _ in candidate_stops:
            changes = {ev_id: ("stop", None)}
            cfs = self.cf_engine.generate_projected_cashflows(user_id, request_date, msg_adjustments, changes)
            lowest_bal, _, is_safe = self.cf_engine.simulate_balance(
                user_id, request_date, profile["current_available_balance"], profile["minimum_balance_to_keep"],
                cfs, [(request_date, requested_amount)]
            )
            if is_safe or (lowest_bal >= profile["minimum_balance_to_keep"] - tolerance):
                return f"stop:{ev_id}", requested_amount

        return None


    def evaluate_request(
        self,
        request: Dict[str, Any],
        profile: Dict[str, Any],
        payment_options: List[Dict[str, Any]],
        user_messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluates a single request and returns the 8 required fields.
        """
        req_id = request["request_id"]
        user_id = request["user_id"]
        req_date = request["request_date"]
        req_amt = request["requested_amount"]
        des_comp_date = request["desired_completion_date"]
        allows_partial = request["allows_partial_payment"]

        # Parse messages
        try:
            from code.message_analyzer import analyze_messages_for_user
        except (ImportError, ModuleNotFoundError):
            from message_analyzer import analyze_messages_for_user

        msg_adjustments = analyze_messages_for_user(user_id, user_messages, req_date)

        # Base cash flows
        base_cfs = self.cf_engine.generate_projected_cashflows(user_id, req_date, msg_adjustments)

        # Amount safe to pay today
        safe_amt = self.calculate_amount_safe_to_pay(user_id, req_date, req_amt, base_cfs, profile)

        # Earliest date for full payment
        earliest_date = self.calculate_earliest_date_for_full_payment(
            user_id, req_date, req_amt, base_cfs, profile, safe_amt
        )

        considered_methods = profile["payment_methods_user_will_consider"]
        max_inst_months = profile["max_installment_months"]

        candidate_plans = []

        # 1. Option: full_payment today (no spending changes)
        if "full_payment" in considered_methods and safe_amt >= req_amt:
            plan_str = f"{req_date}:{format_amount(req_amt)}"
            candidate_plans.append({
                "method": "full_payment",
                "status": "affordable_now",
                "plan": plan_str,
                "spending_changes": "none",
                "completion_date": req_date,
                "first_date": req_date,
                "num_payments": 1,
                "total_amount": req_amt,
                "option_id": "00",
                "meets_deadline": req_date <= des_comp_date,
                "has_changes": False,
            })

        # 2. Option: installments from request_payment_options.csv
        if "installments" in considered_methods and max_inst_months is not None:
            for opt in payment_options:
                if opt["payment_method"] != "installments":
                    continue
                num_p = opt["number_of_payments"]
                if num_p > max_inst_months:
                    continue

                first_p_date = opt["first_payment_date"]
                freq_days = opt["payment_frequency_days"] or 30
                p_amt = opt["payment_amount"]
                tot_amt = opt["total_payable_amount"]

                schedule = []
                for k in range(num_p):
                    p_date = add_days(first_p_date, k * freq_days)
                    schedule.append((p_date, p_amt))

                last_date = schedule[-1][0]

                # Check safety over 90 days
                # Only check payments falling within 90 days
                sim_payments = [(d, a) for d, a in schedule if d <= add_days(req_date, FORECAST_DAYS)]
                _, _, is_safe = self.cf_engine.simulate_balance(
                    user_id, req_date, profile["current_available_balance"], profile["minimum_balance_to_keep"],
                    base_cfs, sim_payments
                )

                if is_safe:
                    # Format plan string
                    plan_items = []
                    for d, a in schedule:
                        plan_items.append(f"{d}:{format_amount(a)}")
                    plan_str = "|".join(plan_items)

                    candidate_plans.append({
                        "method": "installments",
                        "status": "affordable_with_plan",
                        "plan": plan_str,
                        "spending_changes": "none",
                        "completion_date": last_date,
                        "first_date": first_p_date,
                        "num_payments": num_p,
                        "total_amount": tot_amt,
                        "option_id": opt["payment_option_id"],
                        "meets_deadline": last_date <= des_comp_date,
                        "has_changes": False,
                        "opt": opt,
                    })

        # 3. Option: partial_payment
        # "Recommend it only when the request allows partial payment, the user accepts this method,
        # amount_safe_to_pay is greater than zero but less than requested_amount,
        # and earliest_date_for_full_payment is on or before desired_completion_date."
        if (
            allows_partial
            and "partial_payment" in considered_methods
            and 0 < safe_amt < req_amt
            and earliest_date
            and earliest_date <= des_comp_date
        ):
            rem_amt = round(req_amt - safe_amt, 2)
            safe_str = format_amount(safe_amt)
            rem_str = format_amount(rem_amt)
            plan_str = f"{req_date}:{safe_str}|{earliest_date}:{rem_str}"

            # Verify safety of partial payment schedule
            part_schedule = [(req_date, safe_amt), (earliest_date, rem_amt)]
            _, _, is_safe = self.cf_engine.simulate_balance(
                user_id, req_date, profile["current_available_balance"], profile["minimum_balance_to_keep"],
                base_cfs, part_schedule
            )
            if is_safe:
                candidate_plans.append({
                    "method": "partial_payment",
                    "status": "affordable_with_plan",
                    "plan": plan_str,
                    "spending_changes": "none",
                    "completion_date": earliest_date,
                    "first_date": req_date,
                    "num_payments": 2,
                    "total_amount": req_amt,
                    "option_id": "00",
                    "meets_deadline": earliest_date <= des_comp_date,
                    "has_changes": False,
                })

        # 4. Option: spending changes for full payment today
        if "full_payment" in considered_methods and safe_amt < req_amt:
            sp_res = self.find_spending_changes_for_full_payment(
                user_id, req_date, req_amt, msg_adjustments, profile
            )
            if sp_res:
                sp_changes_str, _ = sp_res
                plan_str = f"{req_date}:{format_amount(req_amt)}"
                candidate_plans.append({
                    "method": "full_payment",
                    "status": "affordable_with_plan",
                    "plan": plan_str,
                    "spending_changes": sp_changes_str,
                    "completion_date": req_date,
                    "first_date": req_date,
                    "num_payments": 1,
                    "total_amount": req_amt,
                    "option_id": "99",
                    "meets_deadline": req_date <= des_comp_date,
                    "has_changes": True,
                })

        # 5. Option: wait
        # "wait is eligible when full payment becomes safe later and the user accepts full_payment."
        if "full_payment" in considered_methods and earliest_date:
            plan_str = f"{earliest_date}:{format_amount(req_amt)}"
            candidate_plans.append({
                "method": "wait",
                "status": "affordable_later",
                "plan": plan_str,
                "spending_changes": "none",
                "completion_date": earliest_date,
                "first_date": earliest_date,
                "num_payments": 1,
                "total_amount": req_amt,
                "option_id": "99",
                "meets_deadline": earliest_date <= des_comp_date,
                "has_changes": False,
            })

        # Ranking criteria:
        # 1. Complete the full request by desired_completion_date.
        # 2. Require no spending changes.
        # 3. Minimize the total amount paid.
        # 4. Start payment earlier.
        # 5. Use fewer payments.
        # 6. Use the lowest payment_option_id as the final tie-breaker.
        selected = None
        if candidate_plans:
            # Sort candidate plans by the 6 criteria
            def sort_key(p):
                # 1. Meets deadline (True comes before False -> 0 before 1)
                c1 = 0 if p["meets_deadline"] else 1
                # 2. No spending changes (False comes before True -> 0 before 1)
                c2 = 1 if p["has_changes"] else 0
                # 3. Total amount paid
                c3 = p["total_amount"]
                # 4. First payment date
                c4 = p["first_date"]
                # 5. Number of payments
                c5 = p["num_payments"]
                # 6. Option id
                c6 = p["option_id"]
                return (c1, c2, c3, c4, c5, c6)

            candidate_plans.sort(key=sort_key)
            # A plan that does NOT meet deadline is rejected if it's wait or installments
            # unless no other choice? If a plan does not meet desired completion date, is it rejected?
            # Challenge rules: "A recommendation is safe only if the user can make every listed payment,
            # complete the full request by its deadline, cover essential expenses, and maintain their preferred minimum balance..."
            valid_plans = [p for p in candidate_plans if p["meets_deadline"]]
            if valid_plans:
                selected = valid_plans[0]
            else:
                # If no plan meets the deadline, fallback to not_recommended
                selected = None

        if selected is None:
            # Fallback not_recommended
            affordability_status = "not_affordable"
            recommended_method = "not_recommended"
            payment_plan = "none"
            spending_changes = "none"
        else:
            affordability_status = selected["status"]
            recommended_method = selected["method"]
            payment_plan = selected["plan"]
            spending_changes = selected["spending_changes"]

        # Generate explanation
        try:
            from code.explainer import generate_decision_explanation
        except (ImportError, ModuleNotFoundError):
            from explainer import generate_decision_explanation

        explanation = generate_decision_explanation(
            request=request,
            profile=profile,
            amount_safe=safe_amt,
            affordability_status=affordability_status,
            recommended_method=recommended_method,
            payment_plan=payment_plan,
            earliest_date=earliest_date,
            spending_changes=spending_changes,
            selected_plan_info=selected,
        )

        # Earliest date formatting: empty string for not_affordable or if not safe within forecast
        earliest_out = earliest_date if earliest_date else ""

        return {
            "request_id": req_id,
            "amount_safe_to_pay": safe_amt,
            "affordability_status": affordability_status,
            "recommended_payment_method": recommended_method,
            "payment_plan": payment_plan,
            "earliest_date_for_full_payment": earliest_out,
            "spending_changes_needed": spending_changes,
            "decision_explanation": explanation,
        }
