from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from .masks import MaskSet
from .schemas import LegalityResult, OptimizationConfig, PortConfig


Node = Tuple[str, int, int]


@dataclass
class _DSU:
    parent: Dict[Node, Node]

    def find(self, x: Node) -> Node:
        self.parent.setdefault(x, x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a: Node, b: Node) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _active_node(maskset: MaskSet, layer: str, row: int, col: int) -> Optional[Node]:
    mask = maskset.masks.get(layer)
    if mask is None:
        return None
    if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1] and mask[row, col]:
        return (layer, row, col)
    return None


def _xy_node(maskset: MaskSet, layer: str, x: float, y: float) -> Optional[Node]:
    grid = maskset.grids.get(layer)
    if grid is None:
        return None
    idx = grid.xy_to_index(x, y)
    if idx is None:
        return None
    return _active_node(maskset, layer, idx[0], idx[1])


def _has_patchable_diagonal(mask: np.ndarray, row: int, col: int, drow: int, dcol: int) -> bool:
    nr = row + drow
    nc = col + dcol
    if not (0 <= nr < mask.shape[0] and 0 <= nc < mask.shape[1]):
        return False
    if not mask[row, col] or not mask[nr, nc]:
        return False
    return not mask[row, nc] and not mask[nr, col]


def _build_connectivity(maskset: MaskSet, cfg: OptimizationConfig) -> _DSU:
    dsu = _DSU(parent={})
    for layer, mask in maskset.masks.items():
        rows, cols = np.nonzero(mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            node = (layer, row, col)
            dsu.find(node)
            for drow, dcol in ((1, 0), (0, 1)):
                nbr = _active_node(maskset, layer, row + drow, col + dcol)
                if nbr is not None:
                    dsu.union(node, nbr)
            if cfg.drc.allow_same_layer_diagonal_contact and cfg.drc.corner_overlap_bridge:
                for drow, dcol in ((1, 1), (1, -1)):
                    nbr = _active_node(maskset, layer, row + drow, col + dcol)
                    if nbr is not None and _has_patchable_diagonal(mask, row, col, drow, dcol):
                        dsu.union(node, nbr)

    for via in cfg.connectivity.vias:
        via_mask = maskset.masks.get(via.via_layer)
        via_grid = maskset.grids.get(via.via_layer)
        if via_mask is None or via_grid is None:
            continue
        rows, cols = np.nonzero(via_mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            via_node = (via.via_layer, row, col)
            x, y = via_grid.index_center(row, col)
            for metal_layer in (via.lower_layer, via.upper_layer):
                metal_node = _xy_node(maskset, metal_layer, x, y)
                if metal_node is not None:
                    dsu.union(via_node, metal_node)
    return dsu


def _port_nodes(maskset: MaskSet, cfg: OptimizationConfig) -> Dict[str, Optional[Node]]:
    return {
        port.name: _port_node(maskset, port)
        for port in cfg.ports
    }


def _port_node(maskset: MaskSet, port: PortConfig) -> Optional[Node]:
    node = _xy_node(maskset, port.layer, port.xy_um[0], port.xy_um[1])
    if node is not None or port.edge is None:
        return node

    grid = maskset.grids.get(port.layer)
    if grid is None:
        return None
    x, y = port.xy_um
    inward = grid.pixel_size_um / 2.0
    edge_offsets = {
        "left": (inward, 0.0),
        "right": (-inward, 0.0),
        "bottom": (0.0, inward),
        "top": (0.0, -inward),
    }
    dx, dy = edge_offsets[port.edge]
    return _xy_node(maskset, port.layer, x + dx, y + dy)


def _check_fixed(maskset: MaskSet) -> List[str]:
    reasons: List[str] = []
    for layer, fixed_region in maskset.fixed_region_masks.items():
        if not fixed_region.any():
            continue
        fixed_values = maskset.fixed_masks[layer]
        if not np.array_equal(maskset.masks[layer][fixed_region], fixed_values[fixed_region]):
            reasons.append(f"fixed_region_changed:{layer}")
    return reasons


def _check_min_width(maskset: MaskSet, cfg: OptimizationConfig) -> List[str]:
    min_pixels = max(1, math.ceil(cfg.drc.min_width_um / cfg.layout.pixel_size_um))
    if min_pixels <= 1:
        return []
    reasons: List[str] = []
    for layer, mask in maskset.masks.items():
        rows, cols = np.nonzero(mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            h = 1
            c = col - 1
            while c >= 0 and mask[row, c]:
                h += 1
                c -= 1
            c = col + 1
            while c < mask.shape[1] and mask[row, c]:
                h += 1
                c += 1
            v = 1
            r = row - 1
            while r >= 0 and mask[r, col]:
                v += 1
                r -= 1
            r = row + 1
            while r < mask.shape[0] and mask[r, col]:
                v += 1
                r += 1
            if max(h, v) < min_pixels:
                reasons.append(f"min_width:{layer}:{row},{col}")
                break
    return reasons


def _gap_violations_1d(values: Iterable[int], min_gap: int) -> bool:
    ordered = sorted(values)
    for a, b in zip(ordered, ordered[1:]):
        gap = b - a - 1
        if 0 < gap < min_gap:
            return True
    return False


def _check_min_spacing(maskset: MaskSet, cfg: OptimizationConfig) -> List[str]:
    min_gap = max(1, math.ceil(cfg.drc.min_spacing_um / cfg.layout.pixel_size_um))
    if min_gap <= 1:
        return []
    reasons: List[str] = []
    for layer, mask in maskset.masks.items():
        for row in range(mask.shape[0]):
            if _gap_violations_1d(np.nonzero(mask[row, :])[0].tolist(), min_gap):
                reasons.append(f"min_spacing:{layer}:row{row}")
                break
        else:
            for col in range(mask.shape[1]):
                if _gap_violations_1d(np.nonzero(mask[:, col])[0].tolist(), min_gap):
                    reasons.append(f"min_spacing:{layer}:col{col}")
                    break
    return reasons


def _check_via_enclosure(maskset: MaskSet, cfg: OptimizationConfig) -> List[str]:
    reasons: List[str] = []
    for via in cfg.connectivity.vias:
        via_mask = maskset.masks.get(via.via_layer)
        via_grid = maskset.grids.get(via.via_layer)
        if via_mask is None or via_grid is None:
            continue
        rows, cols = np.nonzero(via_mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            x, y = via_grid.index_center(row, col)
            missing: List[str] = []
            if _xy_node(maskset, via.lower_layer, x, y) is None:
                missing.append(via.lower_layer)
            if _xy_node(maskset, via.upper_layer, x, y) is None:
                missing.append(via.upper_layer)
            if missing:
                reasons.append(
                    f"via_not_enclosed:{via.name}:{via.via_layer}:{row},{col}:missing={','.join(missing)}"
                )
    return reasons


def check_legality(maskset: MaskSet, cfg: OptimizationConfig) -> LegalityResult:
    reasons: List[str] = []
    reasons.extend(_check_fixed(maskset))
    reasons.extend(_check_min_width(maskset, cfg))
    reasons.extend(_check_min_spacing(maskset, cfg))
    reasons.extend(_check_via_enclosure(maskset, cfg))

    dsu = _build_connectivity(maskset, cfg)
    ports = _port_nodes(maskset, cfg)
    port_cfgs = {port.name: port for port in cfg.ports}
    for port_name, node in ports.items():
        if node is None:
            port = port_cfgs.get(port_name)
            if port is not None and port.layer not in maskset.grids:
                continue
            reasons.append(f"port_not_on_active_pixel:{port_name}")

    for group in cfg.connectivity.required:
        existing = [ports.get(name) for name in group]
        if any(node is None for node in existing):
            continue
        roots = {dsu.find(node) for node in existing if node is not None}
        if len(roots) > 1:
            reasons.append("required_connectivity:" + ",".join(group))

    for group in cfg.connectivity.forbidden_shorts:
        existing = [ports.get(name) for name in group]
        if any(node is None for node in existing):
            continue
        roots = [dsu.find(node) for node in existing if node is not None]
        if len(set(roots)) < len(roots):
            reasons.append("forbidden_short:" + ",".join(group))

    return LegalityResult(valid=not reasons, reasons=reasons, details={"ports": {k: str(v) for k, v in ports.items()}})
