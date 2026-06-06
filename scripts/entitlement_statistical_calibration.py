from __future__ import annotations

import math
from typing import Any


DEFAULT_PRIOR_ALPHA = 0.5
DEFAULT_PRIOR_BETA = 0.5
DEFAULT_INTERVAL_COVERAGES = (0.80, 0.95)


def _validate_binomial_count(label: str, successes: int, total: int) -> None:
    if total < 0:
        raise ValueError(f"{label} total must be non-negative")
    if successes < 0:
        raise ValueError(f"{label} successes must be non-negative")
    if successes > total:
        raise ValueError(f"{label} successes cannot exceed total")


def _rate(successes: int, total: int) -> float:
    return successes / total if total else 0.0


def _percent(successes: int, total: int) -> float:
    return round(_rate(successes, total) * 100, 1) if total else 0.0


def _log_beta(alpha: float, beta: float) -> float:
    return math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta)


def beta_binomial_pmf(successes: int, total: int, alpha: float, beta: float) -> float:
    """Probability of `successes` under Beta-Binomial(total, alpha, beta)."""
    _validate_binomial_count("beta-binomial", successes, total)
    if alpha <= 0 or beta <= 0:
        raise ValueError("alpha and beta must be positive")
    log_combination = (
        math.lgamma(total + 1)
        - math.lgamma(successes + 1)
        - math.lgamma(total - successes + 1)
    )
    log_probability = (
        log_combination
        + _log_beta(successes + alpha, total - successes + beta)
        - _log_beta(alpha, beta)
    )
    return math.exp(log_probability)


def beta_binomial_distribution(total: int, alpha: float, beta: float) -> list[float]:
    if total < 0:
        raise ValueError("total must be non-negative")
    probabilities = [beta_binomial_pmf(successes, total, alpha, beta) for successes in range(total + 1)]
    probability_sum = sum(probabilities)
    if probability_sum:
        probabilities = [probability / probability_sum for probability in probabilities]
    return probabilities


def _predictive_interval(probabilities: list[float], coverage: float) -> tuple[int, int]:
    if not 0 < coverage < 1:
        raise ValueError("coverage must be between 0 and 1")
    lower_tail = (1 - coverage) / 2
    upper_tail = 1 - lower_tail

    cumulative = 0.0
    lower = 0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if cumulative >= lower_tail:
            lower = index
            break

    cumulative = 0.0
    upper = len(probabilities) - 1
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if cumulative >= upper_tail:
            upper = index
            break

    return lower, upper


def baseline_prevalence_model(
    successes: int,
    total: int,
    *,
    metric: str,
    metric_label: str | None = None,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
) -> dict[str, Any]:
    """Turn the curated A-group observations into a posterior prevalence model."""
    _validate_binomial_count("baseline", successes, total)
    if prior_alpha <= 0 or prior_beta <= 0:
        raise ValueError("prior alpha and beta must be positive")
    posterior_alpha = successes + prior_alpha
    posterior_beta = total - successes + prior_beta
    posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta)
    return {
        "metric": metric,
        "metric_label": metric_label or metric.replace("_", " "),
        "observed_count": successes,
        "sample_size": total,
        "observed_rate": round(_rate(successes, total), 4),
        "observed_percent": _percent(successes, total),
        "posterior_alpha": round(posterior_alpha, 4),
        "posterior_beta": round(posterior_beta, 4),
        "posterior_mean": round(posterior_mean, 4),
        "posterior_mean_percent": round(posterior_mean * 100, 1),
    }


def beta_binomial_predictive_calibration(
    baseline_successes: int,
    baseline_total: int,
    target_successes: int,
    target_total: int,
    *,
    metric: str,
    target_label: str,
    metric_label: str | None = None,
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
    interval_coverages: tuple[float, ...] = DEFAULT_INTERVAL_COVERAGES,
) -> dict[str, Any]:
    """Predict a target-group count from an A-group prevalence posterior."""
    _validate_binomial_count("baseline", baseline_successes, baseline_total)
    _validate_binomial_count("target", target_successes, target_total)

    posterior_alpha = baseline_successes + prior_alpha
    posterior_beta = baseline_total - baseline_successes + prior_beta
    posterior_total = posterior_alpha + posterior_beta
    posterior_mean = posterior_alpha / posterior_total
    probabilities = beta_binomial_distribution(target_total, posterior_alpha, posterior_beta)
    expected_count = target_total * posterior_mean
    variance = (
        target_total
        * posterior_alpha
        * posterior_beta
        * (posterior_total + target_total)
        / ((posterior_total**2) * (posterior_total + 1))
    )

    intervals: dict[str, dict[str, Any]] = {}
    for coverage in interval_coverages:
        lower, upper = _predictive_interval(probabilities, coverage)
        key = f"{int(round(coverage * 100))}_percent"
        intervals[key] = {
            "coverage": round(coverage, 2),
            "count": [lower, upper],
            "percent": [
                _percent(lower, target_total),
                _percent(upper, target_total),
            ],
        }

    exact_probability = probabilities[target_successes] if probabilities else 1.0
    lower_tail_probability = sum(probabilities[: target_successes + 1])
    upper_tail_probability = sum(probabilities[target_successes:])
    two_sided_tail_probability = min(1.0, 2 * min(lower_tail_probability, upper_tail_probability))

    return {
        "target_label": target_label,
        "metric": metric,
        "metric_label": metric_label or metric.replace("_", " "),
        "observed_count": target_successes,
        "sample_size": target_total,
        "observed_rate": round(_rate(target_successes, target_total), 4),
        "observed_percent": _percent(target_successes, target_total),
        "expected_count": round(expected_count, 2),
        "expected_percent": round(posterior_mean * 100, 1),
        "variance": round(variance, 4),
        "standard_deviation": round(math.sqrt(variance), 2),
        "predictive_intervals": intervals,
        "inside_80_predictive_interval": _inside_interval(target_successes, intervals.get("80_percent")),
        "inside_95_predictive_interval": _inside_interval(target_successes, intervals.get("95_percent")),
        "exact_predictive_probability": round(exact_probability, 4),
        "lower_tail_probability": round(lower_tail_probability, 4),
        "upper_tail_probability": round(upper_tail_probability, 4),
        "two_sided_tail_probability": round(two_sided_tail_probability, 4),
        "fit_confidence": round(two_sided_tail_probability, 4),
        "surprise_score": round(1 - two_sided_tail_probability, 4),
    }


def _inside_interval(successes: int, interval: dict[str, Any] | None) -> bool:
    if not interval:
        return False
    lower, upper = interval["count"]
    return lower <= successes <= upper


def calibrate_binary_metric_groups(
    baseline_summary: dict[str, Any],
    target_summaries: dict[str, dict[str, Any]],
    *,
    metric: str,
    metric_label: str | None = None,
    total_field: str = "councils",
    baseline_label: str = "A: original 10-council comparator seed",
    prior_alpha: float = DEFAULT_PRIOR_ALPHA,
    prior_beta: float = DEFAULT_PRIOR_BETA,
) -> dict[str, Any]:
    baseline_successes = int(baseline_summary.get(metric) or 0)
    baseline_total = int(baseline_summary.get(total_field) or 0)
    baseline = baseline_prevalence_model(
        baseline_successes,
        baseline_total,
        metric=metric,
        metric_label=metric_label,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
    )
    return {
        "model": "beta_binomial_predictive",
        "metric": metric,
        "metric_label": metric_label or metric.replace("_", " "),
        "baseline_label": baseline_label,
        "prior": {
            "name": "Jeffreys beta(0.5, 0.5)",
            "alpha": prior_alpha,
            "beta": prior_beta,
        },
        "baseline": baseline,
        "groups": {
            key: beta_binomial_predictive_calibration(
                baseline_successes,
                baseline_total,
                int(summary.get(metric) or 0),
                int(summary.get(total_field) or 0),
                metric=metric,
                target_label=key,
                metric_label=metric_label,
                prior_alpha=prior_alpha,
                prior_beta=prior_beta,
            )
            for key, summary in target_summaries.items()
        },
        "confidence_definition": (
            "fit_confidence is the two-sided beta-binomial predictive tail probability for the observed target count. "
            "Low values mean the target group is statistically surprising under the A-group prevalence posterior."
        ),
    }
