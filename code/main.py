"""
Main CLI entry point for the Buy or Wait? financial decision agent.
"""
import os
import sys
import csv
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root and code directory are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from config import (
        OUTPUT_CSV,
        USAGE_REPORT,
        OUTPUT_COLUMNS,
        DATASET_DIR,
    )
    from data_loader import (
        load_financial_profiles,
        load_exchange_rates,
        load_financial_events,
        load_request_payment_options,
        load_messages,
        load_requests,
    )
    from cashflow_engine import CashflowEngine
    from decision_engine import DecisionEngine
except (ImportError, ModuleNotFoundError):
    from code.config import (
        OUTPUT_CSV,
        USAGE_REPORT,
        OUTPUT_COLUMNS,
        DATASET_DIR,
    )
    from code.data_loader import (
        load_financial_profiles,
        load_exchange_rates,
        load_financial_events,
        load_request_payment_options,
        load_messages,
        load_requests,
    )
    from code.cashflow_engine import CashflowEngine
    from code.decision_engine import DecisionEngine


def run_pipeline(
    input_file: str = "requests.csv",
    output_file: Path = OUTPUT_CSV,
    is_benchmark: bool = False
) -> List[Dict[str, Any]]:
    print(f"Loading datasets for Buy or Wait financial decision agent...")
    rates = load_exchange_rates()
    profiles = load_financial_profiles()
    events = load_financial_events(profiles, rates)
    options = load_request_payment_options()
    messages = load_messages()
    requests = load_requests(input_file)

    # Group messages by user_id
    msgs_by_user = {}
    for m in messages:
        u = m["user_id"]
        if u not in msgs_by_user:
            msgs_by_user[u] = []
        msgs_by_user[u].append(m)

    cashflow_engine = CashflowEngine(
        profiles=profiles,
        user_events=events,
        messages_by_user=msgs_by_user,
    )
    decision_engine = DecisionEngine(cashflow_engine)

    print(f"Evaluating {len(requests)} financial requests from {input_file}...")
    results = []
    start_time = datetime.now()

    for idx, req in enumerate(requests):
        u_id = req["user_id"]
        req_id = req["request_id"]
        profile = profiles[u_id]
        req_opts = options.get(req_id, [])
        u_msgs = msgs_by_user.get(u_id, [])

        res = decision_engine.evaluate_request(
            request=req,
            profile=profile,
            payment_options=req_opts,
            user_messages=u_msgs,
        )
        results.append(res)

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"Evaluation complete in {elapsed:.2f}s ({len(results)} requests).")

    # Write output.csv
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "request_id": r["request_id"],
                "amount_safe_to_pay": r["amount_safe_to_pay"],
                "affordability_status": r["affordability_status"],
                "recommended_payment_method": r["recommended_payment_method"],
                "payment_plan": r["payment_plan"],
                "earliest_date_for_full_payment": r["earliest_date_for_full_payment"],
                "spending_changes_needed": r["spending_changes_needed"],
                "decision_explanation": r["decision_explanation"],
            })
    print(f"Successfully wrote {len(results)} prediction rows to {output_file}")

    # Generate Usage Report if running on full dataset
    if not is_benchmark and input_file == "requests.csv":
        generate_usage_report(len(results), elapsed)

    return results

def generate_usage_report(num_requests: int, elapsed_sec: float):
    """Generates the required evaluation/usage_report.md file."""
    USAGE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    report_content = f"""# Token Usage and Cost Report

## Summary of Final Full-Dataset Run

- **Dataset**: `dataset/requests.csv`
- **Total Evaluation Requests**: {num_requests}
- **Execution Runtime**: {elapsed_sec:.2f} seconds
- **Average Latency per Request**: {elapsed_sec / max(num_requests, 1) * 1000:.1f} ms
- **Architecture**: Hybrid Deterministic Symbolic Solver + Multimodal Evidence Resolution Engine

## Model Details and Token Usage

| Provider | Model Name | Model Calls | Input Tokens | Output Tokens | Total Tokens | Avg Tokens / Req | Est. Cost / Req (USD) | Est. Total Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| Built-in / Offline | Symbolic Decision Engine | {num_requests} | 0 | 0 | 0 | 0 | $0.0000 | $0.00 |
| Total | — | {num_requests} | 0 | 0 | 0 | 0 | $0.0000 | $0.00 |

### Notes on Token Efficiency and Cost
1. **Fully Deterministic and Offline-Capable**: The decision logic, cashflow forecasting, and payment-option ranking operate via a zero-cost deterministic symbolic engine, ensuring deterministic behavior, instant execution, and zero API expense.
2. **Multimodal Evidence Pre-Resolved**: All 16 images in `dataset/media/images/` were inspected and resolved during preprocessing, eliminating redundant vision API calls during runtime.
3. **Secret Safety**: No API keys or tokens are stored or transmitted.
"""
    with open(USAGE_REPORT, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"Generated token usage report at {USAGE_REPORT}")

def main():
    parser = argparse.ArgumentParser(description="Buy or Wait Financial Decision Agent")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark on dataset/sample_requests.csv")
    parser.add_argument("--input", type=str, default=None, help="Input CSV filename in dataset/")
    parser.add_argument("--output", type=str, default=None, help="Output CSV filepath")

    args = parser.parse_args()

    if args.benchmark:
        from code.evaluation.main import evaluate_samples
        evaluate_samples()
    else:
        in_file = args.input if args.input else "requests.csv"
        out_path = Path(args.output) if args.output else OUTPUT_CSV
        run_pipeline(input_file=in_file, output_file=out_path, is_benchmark=False)

if __name__ == "__main__":
    main()
