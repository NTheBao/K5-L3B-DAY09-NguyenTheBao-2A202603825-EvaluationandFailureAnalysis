# Judge audit — replay labels

Run from `src/` with `python -m lab9.judge --csv ... --audit 5`. FAIL is the
positive class. Calibration floors are κ ≥ 0.6, precision ≥ 0.8, recall ≥ 0.7.

| Criterion | n | κ | Precision | Recall | Floors met? | Decision |
|---|---:|---:|---:|---:|---|---|
| Tone (`judge_tone_public.csv`) | 100 | 0.757 | 0.857 | 0.800 | Yes | Use for exploratory tone review only |
| Helpful (`judge_helpful_public.csv`) | 100 | 0.375 | 1.000 | 0.300 | No | Reject; misses 21/30 human-labeled failures |

The CLI reports observed fail rates of 0.28 (tone) and 0.09 (helpful), with
Rogan–Gladen corrected rates 0.30 for each. Do not use the helpful estimate:
its judge fails the calibration floors. These are replay-set estimates, not
population rates.

## Manual disagreement audit

The five cases below were checked against the CSV notes and the stated rubric.
The CSV's human annotation remains the reference for reported confusion metrics.

| # | Case | Judge | Human | Audit finding |
|---:|---|---|---|---|
| 1 | H-017 | PASS | FAIL | False negative: “bạn ơi” is too familiar for the customer context; judge treats it as friendly. |
| 2 | H-029 | PASS | FAIL | False negative: “không cần nhắn thêm” sounds commanding; judge focuses on the polite opening. |
| 3 | H-042 | FAIL | PASS | False positive: concise status and payment timing are sufficient; judge expects an apology. |
| 4 | H-081 | FAIL | PASS | Human label is marked incorrect in the CSV note (ticket was misread); judge is right for this row. Keep raw counts unchanged pending relabeling. |
| 5 | H-088 | FAIL | PASS | False positive: repeated “Dạ” is a typo, while the human annotation accepts the reply. |

## Decision and limits

Use the tone judge only as a review aid; it does not grade refunds, money, or
approval. Reject helpfulness because low recall makes it unsafe as a release
grader. Both CSVs are public replay data, and at least one tone label is known
to be wrong. Recalibrate on independently labeled, held-out examples before
using either judge for a release decision.
