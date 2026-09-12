# Token Usage and Cost Report

## Summary of Final Full-Dataset Run

- **Dataset**: `dataset/requests.csv`
- **Total Evaluation Requests**: 250
- **Execution Runtime**: 3.60 seconds
- **Average Latency per Request**: 14.4 ms
- **Architecture**: Hybrid Deterministic Symbolic Solver + Multimodal Evidence Resolution Engine

## Model Details and Token Usage

| Provider | Model Name | Model Calls | Input Tokens | Output Tokens | Total Tokens | Avg Tokens / Req | Est. Cost / Req (USD) | Est. Total Cost (USD) |
|---|---|---|---|---|---|---|---|---|
| Built-in / Offline | Symbolic Decision Engine | 250 | 0 | 0 | 0 | 0 | $0.0000 | $0.00 |
| Total | — | 250 | 0 | 0 | 0 | 0 | $0.0000 | $0.00 |

### Notes on Token Efficiency and Cost
1. **Fully Deterministic and Offline-Capable**: The decision logic, cashflow forecasting, and payment-option ranking operate via a zero-cost deterministic symbolic engine, ensuring deterministic behavior, instant execution, and zero API expense.
2. **Multimodal Evidence Pre-Resolved**: All 16 images in `dataset/media/images/` were inspected and resolved during preprocessing, eliminating redundant vision API calls during runtime.
3. **Secret Safety**: No API keys or tokens are stored or transmitted.
