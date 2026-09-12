"""
Message analyzer for extracting financial signal adjustments from messages.
"""
import re
from datetime import datetime
from typing import Dict, List, Any, Optional

def analyze_messages_for_user(
    user_id: str,
    user_messages: List[Dict[str, Any]],
    request_date: str
) -> Dict[str, Any]:
    """
    Parses messages sent to or relevant for user_id to extract adjustments
    to salary, contract status, rent, and one-off confirmed payments.
    """
    adjustments = {
        "contract_ended": False,
        "salary_override_amount": None,
        "salary_override_date": None,
        "new_salary_effective_date": None,
        "new_recurring_salary": None,
        "rent_increase_percent": 0.0,
        "new_recurring_expenses": [],
        "confirmed_inflow_events": [],
        "ignore_event_ids": set(),
    }

    # Sort messages by sent_at
    sorted_msgs = sorted(user_messages, key=lambda m: m["sent_at"])

    for m in sorted_msgs:
        txt = m["message_text"]
        source = m["source_type"]
        rel_ev = m["related_event_id"]

        # 1. Contract ended / Seasonal ended
        if re.search(r"contract has ended|employment record has ended|no off-season income", txt, re.IGNORECASE):
            if "remaining confirmed" in txt.lower():
                # Extract remaining confirmed salary, e.g. "remaining confirmed monthly salary is INR 148000"
                match = re.search(r"remaining confirmed monthly salary is [A-Z]{3}\s*([\d,]+)", txt, re.IGNORECASE)
                if match:
                    amt = float(match.group(1).replace(",", ""))
                    adjustments["new_recurring_salary"] = amt
            else:
                adjustments["contract_ended"] = True

        # 2. Salary replacement date
        date_match = re.search(r"salary is now expected on (\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE)
        if date_match:
            adjustments["salary_override_date"] = date_match.group(1)

        # 3. Base salary confirmed (Indonesian & English)
        if "belum disetujui" not in txt.lower() and "unapproved" not in txt.lower():
            base_sal_match = re.search(r"(?:Gaji pokok yang dikonfirmasi adalah|confirmed base salary is|confirmed monthly salary is)\s*[A-Z]{3}\s*([\d,]+(?:\.\d+)?)", txt, re.IGNORECASE)
            if base_sal_match:
                adjustments["new_recurring_salary"] = float(base_sal_match.group(1).replace(",", ""))

        # 4. Next salary reduced / adjusted to specific amount
        next_sal_match = re.search(r"(?:next salary is reduced to|temporary monthly pay is|Your first salary will be)\s*[A-Z]{3}\s*([\d,]+(?:\.\d+)?)", txt, re.IGNORECASE)
        if next_sal_match:
            adjustments["salary_override_amount"] = float(next_sal_match.group(1).replace(",", ""))

        # 5. Salary increase / change starting from a date
        # English or Indonesian: "Gaji bulanan Anda naik menjadi IDR 42750000. Perubahan ini berlaku mulai 2025-08-15"

        # "monthly salary has increased to USD 2988. The change applies from 2026-07-15"
        sal_inc_match = re.search(r"(?:naik menjadi|increased to|salary of)\s*[A-Z]{3}\s*([\d,]+(?:\.\d+)?).*?(?:berlaku mulai|applies from|resumes on)\s*(\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE | re.DOTALL)
        if sal_inc_match:
            new_sal = float(sal_inc_match.group(1).replace(",", ""))
            eff_date = sal_inc_match.group(2)
            adjustments["new_recurring_salary"] = new_sal
            adjustments["new_salary_effective_date"] = eff_date

        # First salary with confirmed credit date:
        # "Your first salary will be EUR 1661. The confirmed credit date is 2026-01-15."
        first_sal = re.search(r"first salary will be\s*[A-Z]{3}\s*([\d,]+(?:\.\d+)?).*?confirmed credit date is (\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE | re.DOTALL)
        if first_sal:
            sal_amt = float(first_sal.group(1).replace(",", ""))
            sal_dt = first_sal.group(2)
            adjustments["confirmed_inflow_events"].append({
                "category": "salary",
                "amount": sal_amt,
                "date": sal_dt,
                "description": "Confirmed first salary"
            })

        # 5. Rent increase
        # "The renewed lease increases monthly rent by 12%."
        rent_inc = re.search(r"increases monthly rent by (\d+(?:\.\d+)?)%", txt, re.IGNORECASE)
        if rent_inc:
            adjustments["rent_increase_percent"] = float(rent_inc.group(1))

        # 6. Confirmed client invoice
        # "Klien menyetujui pembayaran faktur sebesar IDR 30780000. Penyelesaian diperkirakan pada 2025-08-15"
        inv_match = re.search(r"(?:menyetujui pembayaran faktur|approved an invoice payment) (?:sebesar|of)\s*[A-Z]{3}\s*([\d,]+).*?(?:Penyelesaian diperkirakan pada|Settlement is expected on)\s*(\d{4}-\d{2}-\d{2})", txt, re.IGNORECASE | re.DOTALL)
        if inv_match:
            inv_amt = float(inv_match.group(1).replace(",", ""))
            inv_dt = inv_match.group(2)
            adjustments["confirmed_inflow_events"].append({
                "category": "invoice",
                "amount": inv_amt,
                "date": inv_dt,
                "description": "Confirmed invoice payment"
            })

        # 7. Untrusted / pending credits to ignore
        if rel_ev:
            if re.search(r"has not reached your account|refund has been initiated|still in payment processing|balance isn't withdrawable|payout is still pending|no cash proceeds", txt, re.IGNORECASE):
                adjustments["ignore_event_ids"].add(rel_ev)

    return adjustments
