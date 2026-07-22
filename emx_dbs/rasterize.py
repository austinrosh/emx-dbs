from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

from .masks import LayerGrid, MaskSet, apply_fixed_masks
from .schemas import BBox, OptimizationConfig, RegionConfig


def _region_layers(region: RegionConfig, cfg: OptimizationConfig) -> List[str]:
    return region.layers if region.layers is not None else list(cfg.layers)


def _bbox_union(boxes: Sequence[BBox]) -> BBox:
    xs0, ys0, xs1, ys1 = zip(*boxes)
    return min(xs0), min(ys0), max(xs1), max(ys1)


def build_grids(cfg: OptimizationConfig) -> Dict[str, LayerGrid]:
    by_layer: Dict[str, List[BBox]] = defaultdict(list)
    for region in cfg.mutable_regions:
        for layer in _region_layers(region, cfg):
            by_layer[layer].append(region.bbox_um)
    if not by_layer:
        raise ValueError("At least one mutable region is required")

    grids: Dict[str, LayerGrid] = {}
    p = cfg.layout.pixel_size_um
    for layer, boxes in by_layer.items():
        xmin, ymin, xmax, ymax = _bbox_union(boxes)
        ncols = int(math.ceil((xmax - xmin) / p))
        nrows = int(math.ceil((ymax - ymin) / p))
        xmax = xmin + ncols * p
        ymax = ymin + nrows * p
        grids[layer] = LayerGrid(layer, (xmin, ymin, xmax, ymax), p, (nrows, ncols))
    return grids


def bbox_to_mask(grid: LayerGrid, bbox: BBox) -> np.ndarray:
    xmin, ymin, xmax, ymax = bbox
    rows, cols = grid.shape
    mask = np.zeros(grid.shape, dtype=bool)
    for row in range(rows):
        cy = grid.ymin + (row + 0.5) * grid.pixel_size_um
        if cy < ymin or cy > ymax:
            continue
        for col in range(cols):
            cx = grid.xmin + (col + 0.5) * grid.pixel_size_um
            if xmin <= cx <= xmax:
                mask[row, col] = True
    return mask


def _points_for_grid(grid: LayerGrid) -> np.ndarray:
    rows, cols = grid.shape
    xs = grid.xmin + (np.arange(cols) + 0.5) * grid.pixel_size_um
    ys = grid.ymin + (np.arange(rows) + 0.5) * grid.pixel_size_um
    xx, yy = np.meshgrid(xs, ys)
    return np.column_stack([xx.ravel(), yy.ravel()])


def _point_in_polygon(points: np.ndarray, polygon_points: np.ndarray) -> np.ndarray:
    x = points[:, 0]
    y = points[:, 1]
    poly = np.asarray(polygon_points, dtype=float)
    px = poly[:, 0]
    py = poly[:, 1]
    inside = np.zeros(points.shape[0], dtype=bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        yi = py[i]
        yj = py[j]
        xi = px[i]
        xj = px[j]
        crosses = ((yi > y) != (yj > y)) & (
            x < (xj - xi) * (y - yi) / ((yj - yi) if yj != yi else 1e-30) + xi
        )
        inside ^= crosses
        j = i
    return inside


def rasterize_polygons(polygons: Iterable[object], grid: LayerGrid) -> np.ndarray:
    points = _points_for_grid(grid)
    active = np.zeros(points.shape[0], dtype=bool)
    for polygon in polygons:
        polygon_points = getattr(polygon, "points", polygon)
        active |= _point_in_polygon(points, np.asarray(polygon_points, dtype=float))
    return active.reshape(grid.shape)


def rasterize_config(cfg: OptimizationConfig) -> MaskSet:
    from .gds_io import load_top_cell, polygons_by_config_layer

    top = load_top_cell(cfg)
    polygons_by_layer = polygons_by_config_layer(top, cfg)
    grids = build_grids(cfg)

    masks: Dict[str, np.ndarray] = {}
    mutable_masks: Dict[str, np.ndarray] = {}
    fixed_masks: Dict[str, np.ndarray] = {}
    fixed_region_masks: Dict[str, np.ndarray] = {}

    for layer, grid in grids.items():
        seed = rasterize_polygons(polygons_by_layer.get(layer, []), grid)
        mutable = np.zeros(grid.shape, dtype=bool)
        for region in cfg.mutable_regions:
            if layer in _region_layers(region, cfg):
                mutable |= bbox_to_mask(grid, region.bbox_um)

        fixed_region = np.zeros(grid.shape, dtype=bool)
        for region in cfg.fixed_regions:
            if layer in _region_layers(region, cfg):
                fixed_region |= bbox_to_mask(grid, region.bbox_um)

        masks[layer] = seed.copy()
        mutable_masks[layer] = mutable & ~fixed_region
        fixed_masks[layer] = seed & fixed_region
        fixed_region_masks[layer] = fixed_region

    if cfg.layout.seed_vias_from_overlap:
        _seed_vias_from_overlap(masks, grids, cfg)
        for layer, fixed_region in fixed_region_masks.items():
            fixed_masks[layer] = masks[layer] & fixed_region

    return apply_fixed_masks(MaskSet(masks, mutable_masks, fixed_masks, fixed_region_masks, grids))


def _seed_vias_from_overlap(
    masks: Dict[str, np.ndarray],
    grids: Dict[str, LayerGrid],
    cfg: OptimizationConfig,
) -> None:
    for via in cfg.connectivity.vias:
        if via.via_layer not in masks or via.lower_layer not in masks or via.upper_layer not in masks:
            continue
        via_mask = masks[via.via_layer]
        via_grid = grids[via.via_layer]
        lower_mask = masks[via.lower_layer]
        upper_mask = masks[via.upper_layer]
        lower_grid = grids[via.lower_layer]
        upper_grid = grids[via.upper_layer]
        rows, cols = np.indices(via_grid.shape)
        for row, col in zip(rows.ravel().tolist(), cols.ravel().tolist()):
            x, y = via_grid.index_center(row, col)
            lower_idx = lower_grid.xy_to_index(x, y)
            upper_idx = upper_grid.xy_to_index(x, y)
            if lower_idx is None or upper_idx is None:
                continue
            if lower_mask[lower_idx] and upper_mask[upper_idx]:
                via_mask[row, col] = True
