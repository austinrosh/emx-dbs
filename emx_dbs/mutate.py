from __future__ import annotations

from typing import List, Optional, Set, Tuple

import numpy as np

from .masks import LayerGrid, MaskSet, apply_fixed_masks
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

    groups = _symmetry_flip_groups(maskset, dbs) if dbs.symmetry_axes else _independent_flip_groups(maskset)
    if not groups:
        raise ValueError("No mutable pixels are available for DBS moves")
    count = max(1, min(count, len(groups)))
    idx = rng.choice(len(groups), size=count, replace=False)
    flips: List[Flip] = []
    seen: Set[Flip] = set()
    for group_idx in idx.tolist():
        for flip in groups[int(group_idx)]:
            if flip not in seen:
                flips.append(flip)
                seen.add(flip)
    return flips


def _independent_flip_groups(maskset: MaskSet) -> List[List[Flip]]:
    candidates: List[List[Flip]] = []
    for layer, mutable in maskset.mutable_masks.items():
        rows, cols = np.nonzero(mutable)
        candidates.extend([(layer, int(row), int(col))] for row, col in zip(rows, cols))
    if not candidates:
        return []
    return candidates


def _symmetry_flip_groups(maskset: MaskSet, dbs: DBSConfig) -> List[List[Flip]]:
    groups_by_key = {}
    for layer, mutable in maskset.mutable_masks.items():
        rows, cols = np.nonzero(mutable)
        for row, col in zip(rows.tolist(), cols.tolist()):
            orbit = _symmetry_orbit(maskset, dbs, layer, int(row), int(col))
            if orbit is None:
                continue
            groups_by_key.setdefault(tuple(orbit), orbit)
    return list(groups_by_key.values())


def _symmetry_orbit(maskset: MaskSet, dbs: DBSConfig, layer: str, row: int, col: int) -> Optional[List[Flip]]:
    grid = maskset.grids[layer]
    center_x, center_y = _symmetry_center(grid, dbs)
    x, y = grid.index_center(row, col)
    points = {(x, y)}

    if "y" in dbs.symmetry_axes:
        points |= {(2.0 * center_x - px, py) for px, py in list(points)}
    if "x" in dbs.symmetry_axes:
        points |= {(px, 2.0 * center_y - py) for px, py in list(points)}

    orbit: Set[Flip] = set()
    mutable = maskset.mutable_masks[layer]
    for px, py in points:
        idx = grid.xy_to_index(px, py)
        if idx is None:
            return None
        mirror_row, mirror_col = idx
        if not mutable[mirror_row, mirror_col]:
            return None
        orbit.add((layer, int(mirror_row), int(mirror_col)))
    return sorted(orbit)


def _symmetry_center(grid: LayerGrid, dbs: DBSConfig) -> Tuple[float, float]:
    if dbs.symmetry_center_um is not None:
        return float(dbs.symmetry_center_um[0]), float(dbs.symmetry_center_um[1])
    return (grid.xmin + grid.xmax) / 2.0, (grid.ymin + grid.ymax) / 2.0


def apply_flips(maskset: MaskSet, flips: List[Flip]) -> MaskSet:
    candidate = maskset.copy()
    for layer, row, col in flips:
        if candidate.mutable_masks[layer][row, col]:
            candidate.masks[layer][row, col] = ~candidate.masks[layer][row, col]
    return apply_fixed_masks(candidate)
