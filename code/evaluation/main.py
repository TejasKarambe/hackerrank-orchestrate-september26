"""
Evaluation script to benchmark the agent against dataset/sample_requests.csv.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CODE_DIR = ROOT_DIR / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from data_loader import load_requests
    from main import run_pipeline
except (ImportError, ModuleNotFoundError):
    from code.data_loader import load_requests
    from code.main import run_pipeline


def evaluate_samples():
    temp_output = ROOT_DIR / "code" / "evaluation" / "sample_predictions.csv"
    predictions = run_pipeline(input_file="sample_requests.csv", output_file=temp_output, is_benchmark=True)
    ground_truth = load_requests("sample_requests.csv")

    total = len(ground_truth)
    correct_status = 0
    correct_method = 0
    correct_plan = 0
    correct_earliest = 0
    correct_changes = 0
    safe_amount_diffs = []

    print("\n" + "=" * 80)
    print(f"BENCHMARK EVALUATION RESULTS ({total} Solved Samples)")
    print("=" * 80)

    for pred, gt in zip(predictions, ground_truth):
        req_id = gt["request_id"]
        status_match = pred["affordability_status"] == gt["gt_affordability_status"]
        method_match = pred["recommended_payment_method"] == gt["gt_recommended_payment_method"]
        plan_match = pred["payment_plan"] == gt["gt_payment_plan"]
        earliest_match = pred["earliest_date_for_full_payment"] == gt["gt_earliest_date_for_full_payment"]
        changes_match = pred["spending_changes_needed"] == gt["gt_spending_changes_needed"]
        diff = abs(pred["amount_safe_to_pay"] - gt["gt_amount_safe_to_pay"])
        safe_amount_diffs.append(diff)

        if status_match:
            correct_status += 1
        if method_match:
            correct_method += 1
        if plan_match:
            correct_plan += 1
        if earliest_match:
            correct_earliest += 1
        if changes_match:
            correct_changes += 1

        all_match = status_match and method_match and (plan_match or earliest_match)
        status_icon = "PASS" if all_match else "DIFF"
        print(f"[{status_icon}] {req_id}: Status={pred['affordability_status']} (GT: {gt['gt_affordability_status']}), Method={pred['recommended_payment_method']} (GT: {gt['gt_recommended_payment_method']})")

    avg_mae = sum(safe_amount_diffs) / len(safe_amount_diffs)

    print("\n" + "-" * 80)
    print("ACCURACY SCORECARD")
    print("-" * 80)
    print(f"Affordability Status Accuracy:    {correct_status}/{total} ({correct_status/total*100:.1f}%)")
    print(f"Recommended Method Accuracy:      {correct_method}/{total} ({correct_method/total*100:.1f}%)")
    print(f"Payment Plan Accuracy:            {correct_plan}/{total} ({correct_plan/total*100:.1f}%)")
    print(f"Earliest Date Match:              {correct_earliest}/{total} ({correct_earliest/total*100:.1f}%)")
    print(f"Spending Changes Match:           {correct_changes}/{total} ({correct_changes/total*100:.1f}%)")
    print(f"Safe Amount Mean Absolute Error:  {avg_mae:.2f}")
    print("=" * 80)

if __name__ == "__main__":
    evaluate_samples()
