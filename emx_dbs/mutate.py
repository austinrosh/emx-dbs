from __future__ import annotations

from typing import List, Tuple

import numpy as np

from .masks import MaskSet, apply_fixed_masks
from .schemas import DBSConfig


Flip = Tuple[str, int, int]


def _normalized_weights(weights: List[float], n: int) -> np.ndarray:
    if len(weights) != n:
        return np.ones(n, dtype=float) / n
    arr = np.asarray(weights, dtype=float)
    total = arr.sum()
    if total <= 0:
        return np.ones(n, dtype=float) / n
    return arr / total


def sample_flip_group(maskset: MaskSet, dbs: DBSConfig, rng: np.random.Generator) -> List[Flip]:
    counts = dbs.metal_flip_count_values
    weights = _normalized_weights(dbs.metal_flip_count_weights, len(counts))
    count = int(rng.choice(np.asarray(counts, dtype=int), p=weights))

    candidates: List[Flip] = []
    for layer, mutable in maskset.mutable_masks.items():
        rows, cols = np.nonzero(mutable)
        candidates.extend((layer, int(row), int(col)) for row, col in zip(rows, cols))
    if not candidates:
        raise ValueError("No mutable pixels are available for DBS moves")
    count = max(1, min(count, len(candidates)))
    idx = rng.choice(len(candidates), size=count, replace=False)
    return [candidates[int(i)] for i in idx]


def apply_flips(maskset: MaskSet, flips: List[Flip]) -> MaskSet:
    candidate = maskset.copy()
    for layer, row, col in flips:
        if candidate.mutable_masks[layer][row, col]:
            candidate.masks[layer][row, col] = ~candidate.masks[layer][row, col]
    return apply_fixed_masks(candidate)
