from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple

import numpy as np

from .schemas import ObjectiveResult
from .touchstone import read_touchstone


def _band(params: dict) -> Tuple[Optional[float], Optional[float]]:
    return params.get("band_start_ghz"), params.get("band_stop_ghz")


def _mean_band(values: np.ndarray, mask: np.ndarray) -> float:
    selected = values[mask]
    if selected.size == 0:
        return float("nan")
    return float(np.mean(selected))


def maximize_coupling(touchstone_path: Path, metadata: dict, params: dict) -> ObjectiveResult:
    sp = read_touchstone(touchstone_path)
    to_port = int(params.get("to_port", 2 if sp.nports >= 2 else 1))
    from_port = int(params.get("from_port", 1))
    start, stop = _band(params)
    mask = sp.band_mask(start, stop)
    coupling = np.clip(sp.mag(to_port, from_port), 0.0, 1.0)
    mean_coupling = _mean_band(coupling, mask)
    valid = bool(np.isfinite(mean_coupling))
    return ObjectiveResult(
        fom=mean_coupling if valid else -1e30,
        loss=-mean_coupling if valid else 1e30,
        valid=valid,
        reason=None if valid else "empty_or_invalid_band",
        metrics={
            "mean_coupling": mean_coupling,
            "to_port": to_port,
            "from_port": from_port,
        },
    )


def passive_match_transfer_isolation(touchstone_path: Path, metadata: dict, params: dict) -> ObjectiveResult:
    sp = read_touchstone(touchstone_path)
    start, stop = _band(params)
    mask = sp.band_mask(start, stop)
    transfer = tuple(params.get("transfer", [2, 1]))
    returns = params.get("return_ports", list(range(1, sp.nports + 1)))
    isolation_pairs = params.get("isolation_pairs", [])
    target_transfer = float(params.get("target_transfer", 0.7))
    max_return = float(params.get("max_return", 0.25))
    max_isolation = float(params.get("max_isolation", 0.1))

    transfer_mag = _mean_band(np.clip(sp.mag(int(transfer[0]), int(transfer[1])), 0.0, 1.0), mask)
    return_penalty = 0.0
    return_metrics = {}
    for port in returns:
        mag = _mean_band(np.clip(sp.mag(int(port), int(port)), 0.0, 1.0), mask)
        return_metrics[f"mean_s{port}{port}"] = mag
        return_penalty += max(0.0, mag - max_return)

    isolation_penalty = 0.0
    isolation_metrics = {}
    for pair in isolation_pairs:
        to_port, from_port = int(pair[0]), int(pair[1])
        mag = _mean_band(np.clip(sp.mag(to_port, from_port), 0.0, 1.0), mask)
        isolation_metrics[f"mean_s{to_port}{from_port}"] = mag
        isolation_penalty += max(0.0, mag - max_isolation)

    transfer_penalty = abs(target_transfer - transfer_mag)
    loss = transfer_penalty + return_penalty + isolation_penalty
    valid = bool(np.isfinite(loss))
    metrics = {
        "mean_transfer": transfer_mag,
        "transfer_penalty": transfer_penalty,
        "return_penalty": return_penalty,
        "isolation_penalty": isolation_penalty,
        **return_metrics,
        **isolation_metrics,
    }
    return ObjectiveResult(fom=-loss, loss=loss, metrics=metrics, valid=valid, reason=None if valid else "invalid_metric")


def differential_transformer(touchstone_path: Path, metadata: dict, params: dict) -> ObjectiveResult:
    sp = read_touchstone(touchstone_path)
    if sp.nports < 4:
        return ObjectiveResult(fom=-1e30, loss=1e30, valid=False, reason="requires_at_least_4_ports")
    start, stop = _band(params)
    mask = sp.band_mask(start, stop)
    primary = params.get("primary_ports", [1, 2])
    secondary = params.get("secondary_ports", [3, 4])
    p1, p2 = int(primary[0]), int(primary[1])
    s1, s2 = int(secondary[0]), int(secondary[1])
    coupling = 0.5 * (sp.mag(s1, p1) + sp.mag(s2, p2))
    reverse = 0.5 * (sp.mag(s1, p2) + sp.mag(s2, p1))
    coupling = np.clip(coupling, 0.0, 1.0)
    reverse = np.clip(reverse, 0.0, 1.0)
    mean_coupling = _mean_band(coupling, mask)
    mean_reverse = _mean_band(reverse, mask)
    balance = abs(_mean_band(sp.mag(s1, p1), mask) - _mean_band(sp.mag(s2, p2), mask))
    loss = -mean_coupling + mean_reverse + balance
    valid = bool(np.isfinite(loss))
    return ObjectiveResult(
        fom=-loss,
        loss=loss,
        valid=valid,
        reason=None if valid else "invalid_transformer_metrics",
        metrics={
            "mean_coupling": mean_coupling,
            "mean_reverse_coupling": mean_reverse,
            "balance_error": balance,
        },
    )
