from __future__ import annotations

from typing import Iterable, List, Tuple

import numpy as np

from .masks import LayerGrid


def diagonal_bridge_centers(mask: np.ndarray, grid: LayerGrid) -> List[Tuple[float, float]]:
    centers: List[Tuple[float, float]] = []
    rows, cols = mask.shape
    p = grid.pixel_size_um
    for row in range(rows - 1):
        for col in range(cols - 1):
            nw = mask[row, col]
            ne = mask[row, col + 1]
            sw = mask[row + 1, col]
            se = mask[row + 1, col + 1]
            if nw and se and not ne and not sw:
                centers.append((grid.xmin + (col + 1) * p, grid.ymin + (row + 1) * p))
            if ne and sw and not nw and not se:
                centers.append((grid.xmin + (col + 1) * p, grid.ymin + (row + 1) * p))
    return centers


def diamond_points(center: Tuple[float, float], min_width_um: float) -> List[Tuple[float, float]]:
    x, y = center
    h = min_width_um / 2.0
    return [(x, y + h), (x + h, y), (x, y - h), (x - h, y)]


def bridge_polygons(mask: np.ndarray, grid: LayerGrid, min_width_um: float) -> Iterable[List[Tuple[float, float]]]:
    for center in diagonal_bridge_centers(mask, grid):
        yield diamond_points(center, min_width_um)
