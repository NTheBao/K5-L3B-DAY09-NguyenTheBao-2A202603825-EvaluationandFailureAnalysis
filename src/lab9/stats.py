"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence
import math

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge labels must have equal length")
    pairs = [(_label(h), _label(j)) for h, j in zip(human, judge)]
    return {
        "tp": sum(h == POS and j == POS for h, j in pairs),
        "fp": sum(h != POS and j == POS for h, j in pairs),
        "fn": sum(h == POS and j != POS for h, j in pairs),
        "tn": sum(h != POS and j != POS for h, j in pairs),
    }


def _label(value: str) -> str:
    label = str(value).strip().upper()
    if label not in {"PASS", "FAIL"}:
        raise ValueError(f"expected PASS or FAIL label, got {value!r}")
    return label


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    if len(human) != len(judge):
        raise ValueError("human and judge labels must have equal length")
    if not human:
        raise ValueError("kappa is undefined for an empty label set")
    h = [_label(x) for x in human]
    j = [_label(x) for x in judge]
    n = len(h)
    observed = sum(x == y for x, y in zip(h, j)) / n
    h_fail, j_fail = sum(x == POS for x in h) / n, sum(x == POS for x in j) / n
    expected = h_fail * j_fail + (1 - h_fail) * (1 - j_fail)
    if math.isclose(expected, 1.0):
        raise ValueError("kappa is undefined when expected agreement is 1")
    return (observed - expected) / (1 - expected)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    values = (observed_rate, sensitivity, specificity)
    if any(not math.isfinite(float(x)) or not 0 <= x <= 1 for x in values):
        raise ValueError("observed rate, sensitivity, and specificity must be in [0, 1]")
    denominator = sensitivity + specificity - 1
    if math.isclose(denominator, 0.0):
        raise ValueError("Rogan-Gladen correction is undefined when sensitivity + specificity = 1")
    estimate = (observed_rate + specificity - 1) / denominator
    return min(1.0, max(0.0, estimate))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    if len(a) != len(b):
        raise ValueError("paired samples must have equal length")
    if len(a) == 0:
        raise ValueError("paired bootstrap requires at least one item")
    if n_resamples < 1:
        raise ValueError("n_resamples must be positive")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be strictly between 0 and 1")
    av, bv = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if not np.all(np.isfinite(av)) or not np.all(np.isfinite(bv)):
        raise ValueError("paired samples must contain only finite values")
    differences = av - bv
    delta = float(np.mean(differences))
    if np.all(differences == 0):
        return 0.0, 0.0, 0.0

    def mean_difference(x, y, axis=-1):
        return np.mean(x - y, axis=axis)

    ci = bootstrap(
        (av, bv),
        mean_difference,
        paired=True,
        vectorized=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    ).confidence_interval
    return delta, float(ci.low), float(ci.high)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _validate_pass_k(n, c, k)
    return 1.0 - math.comb(n - c, k) / math.comb(n, k) if k <= n - c else 1.0


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _validate_pass_k(n, c, k)
    return math.comb(c, k) / math.comb(n, k) if k <= c else 0.0


def _validate_pass_k(n: int, c: int, k: int) -> None:
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (n, c, k)):
        raise ValueError("n, c, and k must be integers")
    if n < 1:
        raise ValueError("n must be positive")
    if not 0 <= c <= n:
        raise ValueError("c must be between 0 and n")
    if not 1 <= k <= n:
        raise ValueError("k must be between 1 and n")
