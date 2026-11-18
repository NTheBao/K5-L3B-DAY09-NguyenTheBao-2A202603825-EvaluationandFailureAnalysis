# Trace case: ticket overrides the order record

Reproduce from `src/`:

```powershell
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
```

| Field | Finding |
|---|---|
| Trial | `seeded_regression`, C-002 at seed 11 |
| Symptom | The ticket says 5 late days, while the database order says 2. The regressed shape uses the ticket value; the fixed shape uses the database value and the expected denied result. |
| First incorrect step | Event 3, `model_override`, records `{"delay_days": 5}` before the quote. |
| Why it is first | Events 1–2 perform handoff and read-only order lookup. Event 2 contains the authoritative 2-day order. The quote and refund follow the bad replacement. |
| Failure mode | FM-03 `ticket_trust` |
| Regression assertion | `DbFactKept` fails for any `model_override`; `RefundAmountCorrect` and `TrialPass` compare the final ledger/result with the label. |
| Fixed comparison | Same C-002@11, with no `model_override` event and no refund. |
| Limitation | This deterministic public case demonstrates one mismatch; it does not estimate the bug's frequency on real tickets or models. |

Executable checks live in `tests/test_lab9_graders.py`; the eval-set case is
E-002 with provenance to T02 / C-002. The trace itself is written in a temporary
directory and is not committed.
