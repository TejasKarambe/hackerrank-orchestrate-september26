"""
Configuration and constants for Buy or Wait financial decision agent.
"""
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
MEDIA_DIR = DATASET_DIR / "media" / "images"
OUTPUT_CSV = REPO_ROOT / "output.csv"
USAGE_REPORT = REPO_ROOT / "code" / "evaluation" / "usage_report.md"

# 16 Missing event amounts resolved from media/images/*.png
IMAGE_EXTRACTED_AMOUNTS = {
    "event_253": 4365000.0,    # image_01: IDR Pay Slip Net Pay
    "event_1442": 100000.0,    # image_02: INR Rent Receipt Balance Due
    "event_1545": 41272.0,     # image_03: INR Bill of Supply Net Amount
    "event_1700": 2854.0,      # image_04: INR Delivered grocery order item bill
    "event_1786": 704.05,      # image_05: INR Telecom Bill Total
    "event_3051": 1995.0,      # image_06: INR Blinkit Grocery Tax Invoice Total
    "event_3231": 8528.0,      # image_07: INR Restaurant Tax Invoice Grand Total
    "event_4535": 15339.0,     # image_08: INR Property Maintenance Receipt Total
    "event_5170": 723.0,       # image_09: INR Water Bill Receipt Total
    "event_6033": 79679.26,    # image_10: INR Large Grocery Tax Invoice Balance Due
    "event_6859": 3650.0,      # image_11: INR Hospital Provisional Bill Amount Payable
    "event_7307": 33.50,       # image_12: USD Taxi Fare Total
    "event_7941": 2298.0,      # image_13: INR Tote Bag Order Total Paid
    "event_9421": 4543.0,      # image_14: INR Pharmacy Bill Total
    "event_9806": 9968.0,      # image_15: INR Airline Ticket Grand Total
    "event_10521": 393.22,     # image_16: INR EV Charging Wallet Payment Total
}

# Output schema
OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

# Allowed values
AFFORDABILITY_STATUSES = [
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
]

RECOMMENDED_PAYMENT_METHODS = [
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
]

FORECAST_DAYS = 90
