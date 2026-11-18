"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    metrics = pr.get("metrics") or {}
    for name, value in metrics.items():
        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
            problems.append(f"metric {name} is not finite")

    manifest = pr.get("manifest") or {}
    rows = pr.get("rows") or []
    seeds = manifest.get("seeds") or []
    item_count = manifest.get("items")
    expected_rows = item_count * len(seeds) if isinstance(item_count, int) and item_count >= 0 else None
    if expected_rows is None or len(rows) != expected_rows:
        problems.append(f"row count {len(rows)} does not match manifest items × seeds ({expected_rows})")

    def row_keys(report: dict) -> list[tuple[str, Any]]:
        return [(str(row.get("item_id")), row.get("seed")) for row in report.get("rows") or []]

    pr_keys, base_keys = row_keys(pr), row_keys(base)
    if len(set(pr_keys)) != len(pr_keys):
        problems.append("duplicate (item_id, seed) rows in PR")
    if set(pr_keys) != set(base_keys):
        problems.append("PR (item_id, seed) set differs from baseline")

    if pr.get("evaluator_failures"):
        problems.append("PR has evaluator_failures")
    graded_ids = [m.get("id") for m in spec.get("metrics", []) if m.get("id") in GRADERS]
    for index, row in enumerate(rows):
        for metric in graded_ids:
            if row.get(metric) is None:
                problems.append(f"row {index} has missing graded metric {metric}")
                break

    def slices_by_item(report: dict) -> dict[str, frozenset[str]]:
        found: dict[str, frozenset[str]] = {}
        for row in report.get("rows") or []:
            item = str(row.get("item_id"))
            tags = frozenset(str(x) for x in (row.get("slices") or []))
            if item in found and found[item] != tags:
                problems.append(f"inconsistent slice tags across rows for {item}")
            found[item] = tags
        return found

    pr_slices, base_slices = slices_by_item(pr), slices_by_item(base)
    if pr_slices != base_slices:
        problems.append("PR item slice tags differ from baseline")

    same_eval_version = (base_spec is not None
                         and spec.get("eval_set_version") == base_spec.get("eval_set_version"))
    if same_eval_version:
        def indexed(entries: list[dict], key: str) -> dict[str, dict]:
            return {str(entry.get(key)): entry for entry in entries}

        current_metrics = indexed(spec.get("metrics", []), "id")
        original_metrics = indexed(base_spec.get("metrics", []), "id")
        for mid, old in original_metrics.items():
            if mid not in current_metrics:
                problems.append(f"ratchet removed metric {mid}")
                continue
            current = current_metrics[mid]
            if old.get("blocking") and not current.get("blocking"):
                problems.append(f"ratchet made metric {mid} non-blocking")
            old_th, new_th = old.get("threshold") or {}, current.get("threshold") or {}
            for key, old_value in old_th.items():
                if key not in new_th:
                    if key != "no_significant_drop" or old_value:
                        problems.append(f"ratchet removed {key} from metric {mid}")
                    continue
                new_value = new_th[key]
                if key in {"max", "max_increase"} and new_value > old_value:
                    problems.append(f"ratchet loosened {mid}.{key} ({old_value} -> {new_value})")
                elif key == "min" and new_value < old_value:
                    problems.append(f"ratchet loosened {mid}.min ({old_value} -> {new_value})")
                elif key == "no_significant_drop" and old_value and not new_value:
                    problems.append(f"ratchet removed {key} from metric {mid}")

        current_slices = {(str(s.get("name")), str(s.get("metric"))): s for s in spec.get("slices", [])}
        original_slices = {(str(s.get("name")), str(s.get("metric"))): s for s in base_spec.get("slices", [])}
        for key, old in original_slices.items():
            label = f"{key[0]}/{key[1]}"
            if key not in current_slices:
                problems.append(f"ratchet removed slice {label}")
                continue
            current = current_slices[key]
            if old.get("blocking") and not current.get("blocking"):
                problems.append(f"ratchet made slice {label} non-blocking")
            for threshold in ("min", "max"):
                if threshold not in old:
                    continue
                if threshold not in current:
                    problems.append(f"ratchet removed slice {label}.{threshold}")
                elif threshold == "min" and current[threshold] < old[threshold]:
                    problems.append(f"ratchet loosened slice {label}.min")
                elif threshold == "max" and current[threshold] > old[threshold]:
                    problems.append(f"ratchet loosened slice {label}.max")
            if old.get("no_significant_drop") and not current.get("no_significant_drop"):
                problems.append(f"ratchet removed no_significant_drop from slice {label}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for entry in spec.get("slices", []):
        name, metric = entry["name"], entry["metric"]
        key = f"slice:{name}/{metric}"
        current = per_item(pr, metric, slice_name=name)
        baseline = per_item(base, metric, slice_name=name)
        value = sum(current.values()) / len(current) if current else None
        reasons = []
        note = ""
        if value is None:
            reasons.append("no PR items in slice")
        elif "min" in entry and value < entry["min"]:
            reasons.append(f"below min {entry['min']}")
        elif "max" in entry and value > entry["max"]:
            reasons.append(f"above max {entry['max']}")

        if entry.get("no_significant_drop") and current and baseline:
            keys = sorted(set(current) & set(baseline))
            if not keys:
                reasons.append("no paired baseline items in slice")
            else:
                delta, lo, hi = stats.paired_bootstrap(
                    [current[k] for k in keys], [baseline[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {delta:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    reasons.append("significant paired drop")
        elif entry.get("no_significant_drop") and current and not baseline:
            reasons.append("no baseline items in slice")

        is_blocking = bool(entry.get("blocking")) and bool(reasons)
        if is_blocking:
            blocked.append(key)
        status = "BLOCK" if is_blocking else ("warn" if reasons else "ok")
        lines.append(f"  {key:<42} {value!s:<8} {note:<28} {status}"
                     + (f" ({'; '.join(reasons)})" if reasons else ""))
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
