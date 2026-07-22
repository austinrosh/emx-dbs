from __future__ import annotations

from pathlib import Path

import numpy as np

from emx_dbs.schemas import ObjectiveResult
from emx_dbs.touchstone import read_touchstone


def objective(touchstone_path: Path, metadata: dict, params: dict) -> ObjectiveResult:
    sp = read_touchstone(touchstone_path)
    if sp.nports < 4:
        return ObjectiveResult(fom=-1e30, loss=1e30, valid=False, reason="transformer_example_requires_4_ports")
    band = sp.band_mask(params.get("band_start_ghz"), params.get("band_stop_ghz"))
    if not band.any():
        return ObjectiveResult(fom=-1e30, loss=1e30, valid=False, reason="empty_band")
    coupling = np.clip(0.5 * (sp.mag(3, 1) + sp.mag(4, 2)), 0.0, 1.0)
    leakage = np.clip(0.5 * (sp.mag(4, 1) + sp.mag(3, 2)), 0.0, 1.0)
    match = np.clip(0.25 * (sp.mag(1, 1) + sp.mag(2, 2) + sp.mag(3, 3) + sp.mag(4, 4)), 0.0, 1.0)
    mean_coupling = float(np.mean(coupling[band]))
    mean_leakage = float(np.mean(leakage[band]))
    mean_match = float(np.mean(match[band]))
    loss = -mean_coupling + 0.5 * mean_leakage + 0.25 * mean_match
    return ObjectiveResult(
        fom=-loss,
        loss=loss,
        valid=True,
        metrics={
            "mean_coupling": mean_coupling,
            "mean_leakage": mean_leakage,
            "mean_match": mean_match,
        },
    )
