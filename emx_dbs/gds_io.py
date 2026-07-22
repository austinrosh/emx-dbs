from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .masks import MaskSet, save_masks_npz
from .schemas import BBox, OptimizationConfig


def _require_gdstk():
    try:
        import gdstk  # type: ignore
    except ImportError as exc:
        raise RuntimeError("gdstk is required for GDS import/export. Install emx-dbs with its dependencies.") from exc
    return gdstk


def load_top_cell(cfg: OptimizationConfig):
    gdstk = _require_gdstk()
    lib = gdstk.read_gds(str(cfg.layout.seed_gds))
    cells = {cell.name: cell for cell in lib.cells}
    if cfg.layout.top_cell not in cells:
        raise ValueError(f"Top cell {cfg.layout.top_cell!r} not found in {cfg.layout.seed_gds}")
    top = cells[cfg.layout.top_cell].copy(cfg.layout.top_cell + "__FLAT")
    top.flatten()
    return top


def polygons_by_config_layer(top_cell, cfg: OptimizationConfig) -> Dict[str, List[object]]:
    by_layer: Dict[str, List[object]] = {name: [] for name in cfg.layers}
    layer_lookup = {tuple(spec): name for name, spec in cfg.layers.items()}
    for poly in top_cell.polygons:
        key = (int(poly.layer), int(poly.datatype))
        name = layer_lookup.get(key)
        if name is not None:
            by_layer[name].append(poly)
    return by_layer


def inspect_gds(cfg: OptimizationConfig) -> Dict[str, object]:
    gdstk = _require_gdstk()
    lib = gdstk.read_gds(str(cfg.layout.seed_gds))
    cells = [cell.name for cell in lib.cells]
    top = {cell.name: cell for cell in lib.cells}.get(cfg.layout.top_cell)
    layers: Dict[Tuple[int, int], int] = {}
    if top is not None:
        flat = top.copy(top.name + "__INSPECT")
        flat.flatten()
        for poly in flat.polygons:
            key = (int(poly.layer), int(poly.datatype))
            layers[key] = layers.get(key, 0) + 1
    return {
        "cells": cells,
        "top_cell_found": top is not None,
        "polygon_counts": {f"{layer}/{datatype}": count for (layer, datatype), count in layers.items()},
    }


def _mutable_window_rectangles(cfg: OptimizationConfig, layer_name: str):
    gdstk = _require_gdstk()
    rects = []
    for region in cfg.mutable_regions:
        layers = region.layers if region.layers is not None else list(cfg.layers)
        if layer_name in layers:
            xmin, ymin, xmax, ymax = region.bbox_um
            layer, datatype = cfg.layers[layer_name]
            rects.append(gdstk.rectangle((xmin, ymin), (xmax, ymax), layer=layer, datatype=datatype))
    return rects


def _copy_polygon(poly):
    gdstk = _require_gdstk()
    return gdstk.Polygon(poly.points.copy(), layer=int(poly.layer), datatype=int(poly.datatype))


def preserved_seed_polygons(cfg: OptimizationConfig) -> List[object]:
    gdstk = _require_gdstk()
    top = load_top_cell(cfg)
    layer_lookup = {tuple(spec): name for name, spec in cfg.layers.items()}
    preserved: List[object] = []
    for poly in top.polygons:
        key = (int(poly.layer), int(poly.datatype))
        layer_name = layer_lookup.get(key)
        if layer_name is None:
            preserved.append(_copy_polygon(poly))
            continue
        windows = _mutable_window_rectangles(cfg, layer_name)
        if not windows:
            preserved.append(_copy_polygon(poly))
            continue
        try:
            remaining = gdstk.boolean([poly], windows, "not", precision=1e-3, layer=poly.layer, datatype=poly.datatype)
        except Exception:
            remaining = []
        preserved.extend(remaining)
    return preserved


def _pixel_rectangles(maskset: MaskSet, layer_name: str, layer: int, datatype: int) -> List[object]:
    gdstk = _require_gdstk()
    grid = maskset.grids[layer_name]
    rects = []
    rows, cols = maskset.masks[layer_name].nonzero()
    for row, col in zip(rows.tolist(), cols.tolist()):
        x0, y0, x1, y1 = grid.index_bbox(row, col)
        rects.append(gdstk.rectangle((x0, y0), (x1, y1), layer=layer, datatype=datatype))
    return rects


def _bridge_rectangles(maskset: MaskSet, cfg: OptimizationConfig, layer_name: str, layer: int, datatype: int) -> List[object]:
    if not (cfg.drc.allow_same_layer_diagonal_contact and cfg.drc.corner_overlap_bridge):
        return []
    gdstk = _require_gdstk()
    from .corner_overlap import bridge_polygons

    grid = maskset.grids[layer_name]
    polygons = []
    for points in bridge_polygons(maskset.masks[layer_name], grid, cfg.drc.min_width_um):
        polygons.append(gdstk.Polygon(points, layer=layer, datatype=datatype))
    return polygons


def export_candidate_gds(maskset: MaskSet, cfg: OptimizationConfig, eval_dir: Path) -> Path:
    gdstk = _require_gdstk()
    design_dir = eval_dir / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    save_masks_npz(maskset, design_dir / "masks.npz")

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell(cfg.layout.top_cell)
    for poly in preserved_seed_polygons(cfg):
        cell.add(poly)

    for layer_name in maskset.masks:
        layer, datatype = cfg.layers[layer_name]
        shapes = _pixel_rectangles(maskset, layer_name, layer, datatype)
        shapes.extend(_bridge_rectangles(maskset, cfg, layer_name, layer, datatype))
        if shapes:
            try:
                shapes = gdstk.boolean(shapes, [], "or", precision=1e-3, layer=layer, datatype=datatype)
            except Exception:
                pass
            cell.add(*shapes)

    out = design_dir / "candidate.gds"
    lib.write_gds(str(out))
    return out


def create_rectangle_seed_gds(path: str | Path, top_cell: str, rectangles: Iterable[Tuple[BBox, int, int]]) -> Path:
    gdstk = _require_gdstk()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell(top_cell)
    for bbox, layer, datatype in rectangles:
        xmin, ymin, xmax, ymax = bbox
        cell.add(gdstk.rectangle((xmin, ymin), (xmax, ymax), layer=layer, datatype=datatype))
    lib.write_gds(str(path))
    return path
