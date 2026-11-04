# Verification record

Validated on 2026-11-04 with Python 3.12, Node 24 and headless Chromium. These are local results; this document does not claim GitHub Actions or public hosting succeeded.

- Clean virtual-environment dependency installation completed with `backend/requirements-dev.txt`.
- Regenerated the full deterministic data and trained both real XGBoost models.
- 13 Python pipeline and API tests passed, including chronological split, feature leakage exclusions, lag history, constrained allocation, unsafe food, route delay, original-plan counterfactual, session isolation, input validation and Telegram authentication/freshness.
- 14 existing JavaScript engine, Worker and interface tests passed.
- JavaScript syntax checks passed, including the new decision-lab interface.
- Real Chromium test passed: full flow, independent manual flow, deterministic reset, weekly forecast, model validation screen, no console exceptions, and no page overflow at 390px width. Screenshots are in `docs/screenshots/`.

## Measured model results (synthetic test data)

| Metric | XGBoost | Historical-average baseline |
|---|---:|---:|
| Demand MAE | 10.954 portions | 13.936 portions |
| Demand RMSE | 15.352 portions | 19.660 portions |

Intraday final-sales MAE: 2.331 portions. The nominal 90% interval covered 87.96% of held-out demand observations; it is not a guarantee.

## Browser-tested default scenario

| Calculated result | Portions / value |
|---|---:|
| Preparation prevented | 17 portions |
| Additional sales from intervention simulation | 10 portions |
| Final surplus | 51 portions |
| Human-consumption allocation | 45 portions |
| Organic recovery | 6 portions |
| Disposal | 0 portions |
| Late arrival continuing old plan | 6 portions |
| Late arrival with ReOPT | 0 portions |
| Avoided preparation value | ₪146 |
| Early discount sales value | ₪54 |
| Allocation discount sales value | ₪135 |
| Logistics | ₪20 |
| Estimated net value | ₪315 |

Values come from actual model/solver outputs for the default seeded scenario. They are neither UI constants nor field-observed impact. The original brief's approximate presentation targets were not forced into the results.

Not validated: a real NNU pilot, a live Telegram bot, public application hosting, the supplied author's existing Cloudflare deployment, or the supplied Dockerfile in a built container. Telegram's inbound contract was exercised using authenticated synthetic updates.
