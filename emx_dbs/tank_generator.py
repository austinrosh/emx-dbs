from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union

import yaml

from .gds_io import _require_gdstk


LayerSpec = Tuple[int, int]
Tile = Tuple[int, int]


@dataclass(frozen=True)
class DualCoreVcoTankGeometry:
    top_cell: str = "dual_core_vco_tank"
    core_width_um: float = 330.0
    core_height_um: float = 330.0
    pitch_um: float = 10.0
    m9_ring_width_um: float = 20.0
    center_gap_um: float = 10.0
    feed_spacing_um: float = 20.0
    feed_width_um: float = 5.0
    feed_length_um: float = 26.0
    m8_trace_width_um: float = 10.0
    pixel_style: str = "square"
    octagon_chamfer_um: Optional[float] = None
    include_octagon_corner_patches: bool = False
    emit_v8: bool = True
    include_guard_ring: bool = False
    include_ground_ring: bool = False
    m9_layer: LayerSpec = (39, 60)
    m8_layer: LayerSpec = (38, 40)
    v8_layer: LayerSpec = (58, 60)
    guard_layer: LayerSpec = (31, 0)
    guard_offset_um: float = 26.0
    guard_width_um: float = 10.0
    guard_feed_overlap_um: float = 5.0
    guard_label: str = "G"
    include_guard_ports: bool = False
    guard_south_port_name: str = "GS"
    guard_north_port_name: str = "GN"
    ground_layer: LayerSpec = (31, 0)
    ground_offset_um: float = 26.0
    ground_width_um: float = 10.0


def generate_dual_core_vco_tank_gds(
    path: Union[str, Path],
    geometry: Optional[DualCoreVcoTankGeometry] = None,
) -> Path:
    geom = geometry or DualCoreVcoTankGeometry()
    _validate_geometry(geom)
    gdstk = _require_gdstk()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    cell = lib.new_cell(geom.top_cell)

    m9_tiles = _m9_tiles(geom)
    m8_tiles = _m8_tiles(geom)
    v8_tiles = _v8_tiles(m9_tiles, m8_tiles) if geom.emit_v8 else set()

    _add_tiles(cell, m9_tiles, geom.m9_layer, geom, style=geom.pixel_style)
    _add_tiles(cell, m8_tiles, geom.m8_layer, geom, style=geom.pixel_style)
    _add_tiles(cell, v8_tiles, geom.v8_layer, geom, style="square")

    if geom.pixel_style == "octagon" and geom.include_octagon_corner_patches:
        _add_corner_patches(cell, m9_tiles, geom.m9_layer, geom)

    _add_port_feeds_and_labels(cell, geom)
    if _has_guard_ring(geom):
        _add_guard_ring(cell, geom)

    lib.write_gds(str(path))
    return path


def dual_core_vco_tank_config(
    seed_gds: Union[str, Path],
    geometry: Optional[DualCoreVcoTankGeometry] = None,
    run_id: str = "dual_core_vco_tank",
    output_root: Union[str, Path] = "runs",
) -> Dict[str, object]:
    geom = geometry or DualCoreVcoTankGeometry()
    top_y = geom.core_height_um + geom.feed_length_um
    bottom_y = -geom.feed_length_um
    layers = {
        "m9": list(geom.m9_layer),
        "m8": list(geom.m8_layer),
        "v8": list(geom.v8_layer),
    }
    if _has_guard_ring(geom):
        layers["guard"] = list(_guard_layer(geom))

    return {
        "run": {"run_id": run_id, "output_root": str(output_root)},
        "layout": {
            "seed_gds": str(seed_gds),
            "top_cell": geom.top_cell,
            "pixel_size_um": geom.pitch_um,
            "preserve_unconfigured_layers": False,
            "seed_vias_from_overlap": False,
        },
        "layers": layers,
        "mutable_regions": [
            {
                "name": "m9_core_and_feeds",
                "layers": ["m9"],
                "bbox_um": [0.0, bottom_y, geom.core_width_um, top_y],
            },
            {
                "name": "m8_center_trace",
                "layers": ["m8"],
                "bbox_um": _m8_region_bbox(geom),
            },
            {
                "name": "v8_overlap_trace",
                "layers": ["v8"],
                "bbox_um": _m8_region_bbox(geom),
            },
        ],
        "fixed_regions": [
            {
                "name": "bottom_m9_port_feeds",
                "layers": ["m9"],
                "bbox_um": [_left_feed_x(geom) - geom.pitch_um, bottom_y, _right_feed_x(geom) + geom.pitch_um, 0.0],
            },
            {
                "name": "top_m9_port_feeds",
                "layers": ["m9"],
                "bbox_um": [
                    _left_feed_x(geom) - geom.pitch_um,
                    geom.core_height_um,
                    _right_feed_x(geom) + geom.pitch_um,
                    top_y,
                ],
            },
            {
                "name": "fixed_m9_left_v8_enclosure",
                "layers": ["m9"],
                "bbox_um": _left_v8_enclosure_bbox(geom),
            },
            {
                "name": "fixed_m9_right_v8_enclosure",
                "layers": ["m9"],
                "bbox_um": _right_v8_enclosure_bbox(geom),
            },
            {
                "name": "fixed_m8_center_trace",
                "layers": ["m8"],
                "bbox_um": _m8_region_bbox(geom),
            },
            {
                "name": "fixed_v8_overlap_trace",
                "layers": ["v8"],
                "bbox_um": _m8_region_bbox(geom),
            },
        ],
        "ports": _config_ports(geom),
        "connectivity": {
            "required": [],
            "forbidden_shorts": [],
            "vias": [{"name": "v8_stack", "via_layer": "v8", "lower_layer": "m8", "upper_layer": "m9"}],
        },
        "drc": {
            "min_width_um": geom.feed_width_um,
            "min_spacing_um": geom.feed_width_um,
            "allow_same_layer_diagonal_contact": True,
            "corner_overlap_bridge": True,
        },
        "emx": {
            "backend": "fake",
            "executable": "emx",
            "proc_file": "/path/to/process.proc",
            "env_script": None,
            "freq_start_ghz": 1,
            "freq_stop_ghz": 20,
            "freq_step_ghz": 1,
            "timeout_s": 120,
            "retries": 1,
        },
        "dbs": {
            "max_evaluations": 10,
            "max_rejections_in_a_row": 20,
            "move_style": "probabilistic_independent_layer_flips",
            "metal_flip_count_weights": [0.5, 0.3, 0.2],
            "metal_flip_count_values": [1, 2, 3],
            "random_seed": 33,
        },
        "objective": {
            "plugin": "emx_dbs.objectives:differential_transformer",
            "params": {
                "primary_ports": [1, 2],
                "secondary_ports": [3, 4],
                "band_start_ghz": 1,
                "band_stop_ghz": 20,
            },
        },
    }


def write_dual_core_vco_tank_config(
    path: Union[str, Path],
    seed_gds: Union[str, Path],
    geometry: Optional[DualCoreVcoTankGeometry] = None,
    run_id: str = "dual_core_vco_tank",
    output_root: Union[str, Path] = "runs",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dual_core_vco_tank_config(seed_gds, geometry, run_id=run_id, output_root=output_root)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _validate_geometry(geom: DualCoreVcoTankGeometry) -> None:
    for name, value in (
        ("core_width_um", geom.core_width_um),
        ("core_height_um", geom.core_height_um),
        ("pitch_um", geom.pitch_um),
        ("m9_ring_width_um", geom.m9_ring_width_um),
        ("center_gap_um", geom.center_gap_um),
        ("feed_spacing_um", geom.feed_spacing_um),
        ("feed_width_um", geom.feed_width_um),
        ("feed_length_um", geom.feed_length_um),
        ("m8_trace_width_um", geom.m8_trace_width_um),
        ("guard_offset_um", _guard_offset_um(geom)),
        ("guard_width_um", _guard_width_um(geom)),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if geom.guard_feed_overlap_um < 0:
        raise ValueError("guard_feed_overlap_um must be nonnegative")
    if geom.pixel_style not in {"square", "octagon"}:
        raise ValueError("pixel_style must be 'square' or 'octagon'")
    _count_cells(geom.core_width_um, geom.pitch_um, "core_width_um")
    _count_cells(geom.core_height_um, geom.pitch_um, "core_height_um")
    _count_cells(geom.m9_ring_width_um, geom.pitch_um, "m9_ring_width_um")
    _count_cells(geom.center_gap_um, geom.pitch_um, "center_gap_um")
    _count_cells(geom.m8_trace_width_um, geom.pitch_um, "m8_trace_width_um")
    if geom.center_gap_um >= geom.core_width_um:
        raise ValueError("center_gap_um must be smaller than core_width_um")
    if geom.feed_spacing_um <= geom.center_gap_um:
        raise ValueError("feed_spacing_um should be larger than center_gap_um")
    if geom.feed_width_um >= geom.feed_spacing_um:
        raise ValueError("feed_width_um must be smaller than feed_spacing_um")


def _count_cells(length_um: float, pitch_um: float, name: str) -> int:
    count = length_um / pitch_um
    rounded = int(round(count))
    if not math.isclose(count, rounded, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError(f"{name} must be an integer multiple of pitch_um")
    return rounded


def _m9_tiles(geom: DualCoreVcoTankGeometry) -> Set[Tile]:
    ncols = _count_cells(geom.core_width_um, geom.pitch_um, "core_width_um")
    nrows = _count_cells(geom.core_height_um, geom.pitch_um, "core_height_um")
    trace_cols = _count_cells(geom.m9_ring_width_um, geom.pitch_um, "m9_ring_width_um")
    trace_rows = trace_cols
    gap_cols = _count_cells(geom.center_gap_um, geom.pitch_um, "center_gap_um")
    gap_start = (ncols - gap_cols) // 2
    gap = set(range(gap_start, gap_start + gap_cols))

    tiles: Set[Tile] = set()
    for row in range(nrows):
        for col in list(range(trace_cols)) + list(range(ncols - trace_cols, ncols)):
            tiles.add((row, col))
    for col in range(ncols):
        if col in gap:
            continue
        for row in list(range(trace_rows)) + list(range(nrows - trace_rows, nrows)):
            tiles.add((row, col))
    return tiles


def _m8_tiles(geom: DualCoreVcoTankGeometry) -> Set[Tile]:
    ncols = _count_cells(geom.core_width_um, geom.pitch_um, "core_width_um")
    nrows = _count_cells(geom.core_height_um, geom.pitch_um, "core_height_um")
    trace_rows = _count_cells(geom.m8_trace_width_um, geom.pitch_um, "m8_trace_width_um")
    row_start = (nrows - trace_rows) // 2
    return {(row, col) for row in range(row_start, row_start + trace_rows) for col in range(ncols)}


def _v8_tiles(m9_tiles: Set[Tile], m8_tiles: Set[Tile]) -> Set[Tile]:
    return m9_tiles & m8_tiles


def _add_tiles(cell, tiles: Iterable[Tile], layer: LayerSpec, geom: DualCoreVcoTankGeometry, style: str) -> None:
    for row, col in sorted(tiles):
        cell.add(_tile_polygon(row, col, layer, geom, style))


def _tile_polygon(row: int, col: int, layer: LayerSpec, geom: DualCoreVcoTankGeometry, style: str):
    gdstk = _require_gdstk()
    x0 = col * geom.pitch_um
    y0 = row * geom.pitch_um
    x1 = x0 + geom.pitch_um
    y1 = y0 + geom.pitch_um
    if style == "square":
        return gdstk.rectangle((x0, y0), (x1, y1), layer=layer[0], datatype=layer[1])

    cut = geom.octagon_chamfer_um if geom.octagon_chamfer_um is not None else geom.pitch_um / 4.0
    cut = min(cut, geom.pitch_um / 2.0)
    points = [
        (x0 + cut, y0),
        (x1 - cut, y0),
        (x1, y0 + cut),
        (x1, y1 - cut),
        (x1 - cut, y1),
        (x0 + cut, y1),
        (x0, y1 - cut),
        (x0, y0 + cut),
    ]
    return gdstk.Polygon(points, layer=layer[0], datatype=layer[1])


def _add_corner_patches(cell, tiles: Set[Tile], layer: LayerSpec, geom: DualCoreVcoTankGeometry) -> None:
    gdstk = _require_gdstk()
    patch = geom.pitch_um - 2.0 * (geom.octagon_chamfer_um if geom.octagon_chamfer_um is not None else geom.pitch_um / 4.0)
    if patch <= 0:
        return
    half = patch / 2.0
    vertices = _shared_vertices(tiles)
    for col, row in sorted(vertices):
        x = col * geom.pitch_um
        y = row * geom.pitch_um
        cell.add(gdstk.rectangle((x - half, y - half), (x + half, y + half), layer=layer[0], datatype=layer[1]))


def _shared_vertices(tiles: Set[Tile]) -> Set[Tuple[int, int]]:
    counts: Dict[Tuple[int, int], int] = {}
    for row, col in tiles:
        for vertex in ((col, row), (col + 1, row), (col, row + 1), (col + 1, row + 1)):
            counts[vertex] = counts.get(vertex, 0) + 1
    return {vertex for vertex, count in counts.items() if count >= 2}


def _add_port_feeds_and_labels(cell, geom: DualCoreVcoTankGeometry) -> None:
    gdstk = _require_gdstk()
    left_x = _left_feed_x(geom)
    right_x = _right_feed_x(geom)
    for x in (left_x, right_x):
        cell.add(
            gdstk.rectangle(
                (x - geom.feed_width_um / 2.0, -geom.feed_length_um),
                (x + geom.feed_width_um / 2.0, 0.0),
                layer=geom.m9_layer[0],
                datatype=geom.m9_layer[1],
            )
        )
        cell.add(
            gdstk.rectangle(
                (x - geom.feed_width_um / 2.0, geom.core_height_um),
                (x + geom.feed_width_um / 2.0, geom.core_height_um + geom.feed_length_um),
                layer=geom.m9_layer[0],
                datatype=geom.m9_layer[1],
            )
        )

    for name, x, y in _port_label_locations(geom):
        cell.add(gdstk.Label(name, (x, y), anchor="o", layer=geom.m9_layer[0], texttype=geom.m9_layer[1]))


def _add_guard_ring(cell, geom: DualCoreVcoTankGeometry) -> None:
    gdstk = _require_gdstk()
    layer = _guard_layer(geom)
    offset = _guard_offset_um(geom)
    width = _guard_width_um(geom)
    overlap = min(geom.guard_feed_overlap_um, width)
    inner_x0 = -offset
    inner_x1 = geom.core_width_um + offset
    inner_y0 = -geom.feed_length_um + overlap
    inner_y1 = geom.core_height_um + geom.feed_length_um - overlap
    outer_x0 = inner_x0 - width
    outer_x1 = inner_x1 + width
    outer_y0 = inner_y0 - width
    outer_y1 = inner_y1 + width
    cell.add(gdstk.rectangle((outer_x0, outer_y0), (outer_x1, inner_y0), layer=layer[0], datatype=layer[1]))
    cell.add(gdstk.rectangle((outer_x0, inner_y1), (outer_x1, outer_y1), layer=layer[0], datatype=layer[1]))
    cell.add(gdstk.rectangle((outer_x0, inner_y0), (inner_x0, inner_y1), layer=layer[0], datatype=layer[1]))
    cell.add(gdstk.rectangle((inner_x1, inner_y0), (outer_x1, inner_y1), layer=layer[0], datatype=layer[1]))
    cell.add(gdstk.Label(geom.guard_label, (outer_x0 + width / 2.0, geom.core_height_um / 2.0), anchor="o", layer=layer[0], texttype=layer[1]))
    if geom.include_guard_ports:
        for name, x, y in _guard_port_label_locations(geom):
            cell.add(gdstk.Label(name, (x, y), anchor="o", layer=layer[0], texttype=layer[1]))


def _left_feed_x(geom: DualCoreVcoTankGeometry) -> float:
    return geom.core_width_um / 2.0 - geom.feed_spacing_um / 2.0


def _right_feed_x(geom: DualCoreVcoTankGeometry) -> float:
    return geom.core_width_um / 2.0 + geom.feed_spacing_um / 2.0


def _port_label_locations(geom: DualCoreVcoTankGeometry) -> List[Tuple[str, float, float]]:
    left_x = _left_feed_x(geom)
    right_x = _right_feed_x(geom)
    bottom_y = -geom.feed_length_um
    top_y = geom.core_height_um + geom.feed_length_um
    return [
        ("PP", left_x, bottom_y),
        ("PN", right_x, bottom_y),
        ("SP", left_x, top_y),
        ("SN", right_x, top_y),
    ]


def _guard_port_label_locations(geom: DualCoreVcoTankGeometry) -> List[Tuple[str, float, float]]:
    x = geom.core_width_um / 2.0
    return [
        (geom.guard_south_port_name, x, -geom.feed_length_um),
        (geom.guard_north_port_name, x, geom.core_height_um + geom.feed_length_um),
    ]


def _config_ports(geom: DualCoreVcoTankGeometry) -> List[Dict[str, object]]:
    edges = {"PP": "bottom", "PN": "bottom", "SP": "top", "SN": "top"}
    ports = [
        {
            "name": name,
            "layer": "m9",
            "xy_um": [x, y],
            "edge": edges[name],
            "width_um": geom.feed_width_um,
        }
        for name, x, y in _port_label_locations(geom)
    ]
    if geom.include_guard_ports and _has_guard_ring(geom):
        guard_edges = {geom.guard_south_port_name: "bottom", geom.guard_north_port_name: "top"}
        ports.extend(
            {
                "name": name,
                "layer": "guard",
                "xy_um": [x, y],
                "edge": guard_edges[name],
                "width_um": _guard_width_um(geom),
            }
            for name, x, y in _guard_port_label_locations(geom)
        )
    return ports


def _m8_region_bbox(geom: DualCoreVcoTankGeometry) -> List[float]:
    y0 = geom.core_height_um / 2.0 - geom.m8_trace_width_um / 2.0
    y1 = y0 + geom.m8_trace_width_um
    return [0.0, y0, geom.core_width_um, y1]


def _left_v8_enclosure_bbox(geom: DualCoreVcoTankGeometry) -> List[float]:
    y0 = geom.core_height_um / 2.0 - geom.m8_trace_width_um / 2.0
    y1 = y0 + geom.m8_trace_width_um
    return [0.0, y0, geom.m9_ring_width_um, y1]


def _right_v8_enclosure_bbox(geom: DualCoreVcoTankGeometry) -> List[float]:
    y0 = geom.core_height_um / 2.0 - geom.m8_trace_width_um / 2.0
    y1 = y0 + geom.m8_trace_width_um
    return [geom.core_width_um - geom.m9_ring_width_um, y0, geom.core_width_um, y1]


def _has_guard_ring(geom: DualCoreVcoTankGeometry) -> bool:
    return bool(geom.include_guard_ring or geom.include_ground_ring)


def _guard_layer(geom: DualCoreVcoTankGeometry) -> LayerSpec:
    return geom.guard_layer if geom.include_guard_ring else geom.ground_layer


def _guard_offset_um(geom: DualCoreVcoTankGeometry) -> float:
    return geom.guard_offset_um if geom.include_guard_ring else geom.ground_offset_um


def _guard_width_um(geom: DualCoreVcoTankGeometry) -> float:
    return geom.guard_width_um if geom.include_guard_ring else geom.ground_width_um
