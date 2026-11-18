# Eval card — LogiX-VN refund agent

## Evaluation identity

- **Baseline run:** `E-swarm-20261118-4994`
- **Eval set:** v1, 14 public Lab 8 items × 5 fixed seeds (11, 22, 33, 44, 55)
- **Eval set SHA-12:** `49948bd13bb7`
- **Metric spec:** `config/metric_spec.yaml`, version 1.0
- **Runner / graders:** `lab9.eval` / `lab9.graders.GRADERS`; MockLLM, offline

## Baseline and gate outcomes

| Metric | Blocking threshold | Swarm baseline | Fixed | Seeded regression |
|---|---:|---:|---:|---:|
| `approval_bypass` | max 0 | 0 | 0 | 0 |
| `secret_leak` | max 0 | 0 | 0 | 0 |
| `db_fact_kept` | min 0.95 (warning) | 0.9857 | 1.0000 | 0.9286 |
| `refund_amount_correct` | min 0.95; no significant drop | 0.9857 | 1.0000 | 0.8571 |
| `reply_amount_correct` (FM-08) | min 0.95 | 1.0000 | 1.0000 | 0.7857 |
| `pass_rate` | min 0.85; no significant drop | 0.9857 | 1.0000 | 0.7143 |
| `pass_5` | min 0.80 (warning) | 0.9286 | 1.0000 | 0.7143 |
| `cost_per_success` | max increase 10% (warning) | 49.5670 | 48.7157 | 81.2020 |

The paired bootstrap compares per-item means over the same 14 items (1,000
resamples, percentile 95% CI, RNG 2027). Fixed vs baseline: `pass_rate` Δ
+0.014, CI [+0.000, +0.043]; exit 0. Seeded regression vs baseline: Δ −0.271,
CI [−0.500, −0.057]; the gate exits 1 and blocks on `refund_amount_correct`,
`reply_amount_correct`, and `pass_rate`.

## Judge and failure analysis

- Tone judge: κ 0.757, precision 0.857, recall 0.800; passes calibration, review aid only.
- Helpful judge: κ 0.375, precision 1.000, recall 0.300; rejected.
- Trace case: [C-002 ticket override](trace_case.md). The first bad event is step 3 `model_override` (`delay_days: 5`) despite the database's 2-day order. `DbFactKept` asserts against this regression.
- Gate owner: maintainer of the evaluation workflow; investigate grader or agent changes, then regenerate reports. Any exception needs an explicit, documented review in the PR.

## Pilot scope and limitations

The pilot covers public refund claims using a deterministic MockLLM and the
provided order/policy fixtures. It does not measure production model behavior,
customer experience, or rare failures reliably. Fourteen items provide limited
power; a bug occurring on one of three or one of five seeds can be missed. Judge
calibration uses public replay labels, including one known incorrect tone label.

Increase the eval-set version when adding trace-derived or adversarial cases;
regenerate the baseline for the new set and retain labels outside item records.

## Advanced v2 (M5–M7)

- **v2 baseline:** `E-swarm-20261118-75bb`, SHA-12 `75bbf1132d8e`, 28 items × 5 seeds.
- **A/A pass^5:** `pass_hat_5` was 0.8929 on both the spec seeds and the alternate
  set 66/77/88/99/110 (Δ 0.0000). The blocking floor is 0.88, 0.0129 below the
  observed A/A value, so the measured same-agent run clears it.
- **Slice gate:** the `slice_regression` variant is blocked on
  `money_movement/pass_rate`; the overall average alone is 0.9357 and does not
  expose the concentrated regression. `adversarial/pass_rate` is also gated.
- **Mutation scorecard:** 3/3 regressions blocked; 0 false alarms. `fixed` and
  `honest_refactor` pass.
- **Integrity traps:** all four public traps are blocked: NaN/missing evaluator
  rows, dropped failing rows, cherry-picked seeds, and loosened spec.
- **Sample limitation:** v2 has 28 items, only 14 from the public matrix; this
  remains a small synthetic set and does not establish rare-failure detection
  rates. Five seeds can still miss a failure that appears on one of three seeds.
