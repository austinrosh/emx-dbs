from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

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
    configured = {
        name: layers.get((int(layer), int(datatype)), 0)
        for name, (layer, datatype) in cfg.layers.items()
    }
    return {
        "cells": cells,
        "top_cell_found": top is not None,
        "polygon_counts": {f"{layer}/{datatype}": count for (layer, datatype), count in layers.items()},
        "configured_layer_counts": configured,
    }


def inspect_raw_gds(gds_path: Union[str, Path], top_cell: Optional[str] = None) -> Dict[str, object]:
    gdstk = _require_gdstk()
    gds_path = Path(gds_path)
    lib = gdstk.read_gds(str(gds_path))
    cells = [cell.name for cell in lib.cells]
    selected = _select_cell(lib, top_cell)
    layers: Dict[Tuple[int, int], int] = {}
    vertex_counts: Dict[int, int] = {}
    layer_stats: Dict[Tuple[int, int], Dict[str, object]] = {}
    label_counts: Dict[Tuple[int, int, str], int] = {}
    bbox = None
    if selected is not None:
        flat = selected.copy(selected.name + "__INSPECT")
        flat.flatten()
        bbox = _bbox_to_list(flat.bounding_box())
        for poly in flat.polygons:
            key = (int(poly.layer), int(poly.datatype))
            layers[key] = layers.get(key, 0) + 1
            vertex_count = len(poly.points)
            vertex_counts[vertex_count] = vertex_counts.get(vertex_count, 0) + 1
            _update_layer_stats(layer_stats, key, poly)
        for label in flat.labels:
            key = (int(label.layer), int(label.texttype), str(label.text))
            label_counts[key] = label_counts.get(key, 0) + 1
    return {
        "gds": str(gds_path),
        "cells": cells,
        "top_cell": selected.name if selected is not None else None,
        "top_cell_found": selected is not None,
        "bbox_um": bbox,
        "polygon_counts": {f"{layer}/{datatype}": count for (layer, datatype), count in sorted(layers.items())},
        "vertex_counts": {str(vertices): count for vertices, count in sorted(vertex_counts.items())},
        "label_counts": {
            f"{layer}/{texttype}:{text}": count
            for (layer, texttype, text), count in sorted(label_counts.items())
        },
        "layer_stats": _format_layer_stats(layer_stats),
    }


def _select_cell(lib, top_cell: Optional[str]):
    if top_cell is not None:
        return {cell.name: cell for cell in lib.cells}.get(top_cell)
    top_levels = lib.top_level()
    if top_levels:
        return top_levels[0]
    return lib.cells[0] if lib.cells else None


def _bbox_to_list(bbox) -> Optional[List[List[float]]]:
    if bbox is None:
        return None
    return [[float(bbox[0][0]), float(bbox[0][1])], [float(bbox[1][0]), float(bbox[1][1])]]


def _update_layer_stats(stats: Dict[Tuple[int, int], Dict[str, object]], key: Tuple[int, int], poly) -> None:
    xs = poly.points[:, 0]
    ys = poly.points[:, 1]
    bbox = [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]
    entry = stats.setdefault(key, {"area_um2": 0.0, "bbox_um": bbox})
    entry["area_um2"] = float(entry["area_um2"]) + abs(float(poly.area()))
    existing = entry["bbox_um"]
    entry["bbox_um"] = [
        min(float(existing[0]), bbox[0]),
        min(float(existing[1]), bbox[1]),
        max(float(existing[2]), bbox[2]),
        max(float(existing[3]), bbox[3]),
    ]


def _format_layer_stats(stats: Dict[Tuple[int, int], Dict[str, object]]) -> Dict[str, object]:
    return {
        f"{layer}/{datatype}": {
            "area_um2": round(float(entry["area_um2"]), 6),
            "bbox_um": [round(float(value), 6) for value in entry["bbox_um"]],
        }
        for (layer, datatype), entry in sorted(stats.items())
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
            if cfg.layout.preserve_unconfigured_layers:
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


def write_candidate_gds(maskset: MaskSet, cfg: OptimizationConfig, path: Union[str, Path]) -> Path:
    gdstk = _require_gdstk()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

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

    for label in _port_labels(cfg):
        cell.add(label)

    lib.write_gds(str(path))
    return path


def export_candidate_gds(maskset: MaskSet, cfg: OptimizationConfig, eval_dir: Path) -> Path:
    design_dir = eval_dir / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    save_masks_npz(maskset, design_dir / "masks.npz")
    return write_candidate_gds(maskset, cfg, design_dir / "candidate.gds")


def _port_labels(cfg: OptimizationConfig) -> List[object]:
    gdstk = _require_gdstk()
    labels = []
    for port in cfg.ports:
        if port.layer not in cfg.layers:
            continue
        layer, datatype = cfg.layers[port.layer]
        labels.append(
            gdstk.Label(
                port.name,
                port.xy_um,
                anchor="o",
                layer=layer,
                texttype=datatype,
            )
        )
    return labels


def create_rectangle_seed_gds(path: Union[str, Path], top_cell: str, rectangles: Iterable[Tuple[BBox, int, int]]) -> Path:
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
