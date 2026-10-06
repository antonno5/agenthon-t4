"""Small numerical forecast library; selection uses completed in-corpus windows."""
from __future__ import annotations

import math
import statistics as stats


def level_point(values, method):
    if method == 'last':
        return values[-1]
    if method.startswith('mean'):
        return stats.mean(values[-int(method[4:]):])
    if method.startswith('median'):
        return stats.median(values[-int(method[6:]):])
    if method == 'damped':
        recent = stats.mean(values[-3:])
        previous = stats.mean(values[-6:-3]) if len(values) >= 6 else recent
        return recent + .5 * (recent - previous)
    raise ValueError(method)


def change_point(values, oi, horizon, method):
    if method == 'zero':
        return 0.
    if method == 'revert12':
        return (stats.mean(values[-12:]) - values[-1]) / oi[-1] * 100
    shrink = .5 if method == 'half_momentum4' else 1.
    lag = 4 if method == 'half_momentum4' else int(method[len('momentum'):])
    lag = min(lag, len(values) - 1)
    return shrink * (values[-1] - values[-1-lag]) / oi[-1] * 100 * horizon / lag


def choose(errors: dict[str, list[float]], baseline: str):
    """Conservative one-standard-error gate on chronological paired losses.

    This is a runtime engineering guard, not a multiple-testing significance test.
    All candidate errors cover the same completed origins.
    """
    n = len(errors[baseline])
    if n < 4:
        return baseline, dict(origins=n, selected=baseline, reason='short-history')
    best = min(errors, key=lambda m: (stats.mean(abs(x) for x in errors[m]), m != baseline, m))
    improvement = [abs(a)-abs(b) for a,b in zip(errors[baseline], errors[best])]
    se = stats.stdev(improvement) / math.sqrt(n) if n > 1 else float('inf')
    selected = best if stats.mean(improvement) > max(se, 1e-12) else baseline
    return selected, dict(origins=n, selected=selected, best=best,
                          baseline_mae=stats.mean(abs(x) for x in errors[baseline]),
                          selected_mae=stats.mean(abs(x) for x in errors[selected]),
                          paired_improvement_se=se, reason='historical-paired-errors')


def level_forecast(values, baseline, fallback_width):
    methods = list(dict.fromkeys([baseline, 'last', 'mean3', 'mean6', 'median3', 'median6', 'damped']))
    start = 6 if baseline == 'mean6' else 3
    errors = {m: [values[i] - level_point(values[:i], m) for i in range(start, len(values))]
              for m in methods}
    selected, trace = choose(errors, baseline)
    # Keep V6's interval when the selector cannot justify changing its point rule.
    if selected == baseline:
        return None, trace
    from agent_submit.cli import half_width
    return (level_point(values, selected), half_width(errors[selected], fallback_width)), trace


def positioning_forecast(values, oi, horizon):
    baseline = 'momentum4'
    methods = [baseline, 'half_momentum4', 'momentum2', 'momentum8', 'revert12', 'zero']
    # Non-overlapping target windows reduce pseudo-replication at a multi-week horizon.
    origins = list(range(8, len(values)-horizon, horizon))
    errors = {m: [(values[i+horizon]-values[i]) / oi[i] * 100
                  - change_point(values[:i+1], oi[:i+1], horizon, m) for i in origins]
              for m in methods}
    selected, trace = choose(errors, baseline)
    if selected == baseline:
        return None, trace
    from agent_submit.cli import half_width
    return (change_point(values, oi, horizon, selected), half_width(errors[selected], 20.)), trace
