from __future__ import annotations

import gdstk

from emx_dbs.config import load_config
from emx_dbs.gds_io import inspect_raw_gds, write_candidate_gds
from emx_dbs.legality import check_legality
from emx_dbs.rasterize import rasterize_config
from emx_dbs.reporting import write_layout_preview
from emx_dbs.tank_generator import (
    DualCoreVcoTankGeometry,
    generate_dual_core_vco_tank_gds,
    write_dual_core_vco_tank_config,
)


def _top_cell(path, name):
    lib = gdstk.read_gds(str(path))
    return {cell.name: cell for cell in lib.cells}[name]


def _bbox(poly):
    xs = poly.points[:, 0]
    ys = poly.points[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def _overlap_area(a, b):
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def test_dual_core_vco_tank_generator_default_layers_and_ports(tmp_path):
    gds = generate_dual_core_vco_tank_gds(tmp_path / "tank.gds")
    info = inspect_raw_gds(gds, top_cell="dual_core_vco_tank")

    assert info["polygon_counts"]["39/60"] == 248
    assert info["polygon_counts"]["38/40"] == 33
    assert info["polygon_counts"]["58/60"] == 4
    assert "31/0" not in info["polygon_counts"]
    assert set(info["label_counts"]) == {"39/60:PN", "39/60:PP", "39/60:SN", "39/60:SP"}


def test_dual_core_vco_tank_config_rasterizes_generated_seed(tmp_path):
    gds = generate_dual_core_vco_tank_gds(tmp_path / "tank.gds")
    config = write_dual_core_vco_tank_config(tmp_path / "tank.local.yaml", gds, run_id="tank_test")
    cfg = load_config(config)
    maskset = rasterize_config(cfg)

    assert cfg.run.run_id == "tank_test"
    assert maskset.masks["m9"].any()
    assert maskset.masks["m8"].any()
    assert maskset.masks["v8"].any()


def test_dual_core_vco_tank_ports_are_on_feed_edges_and_legal(tmp_path):
    geom = DualCoreVcoTankGeometry()
    gds = generate_dual_core_vco_tank_gds(tmp_path / "tank.gds", geom)
    config = write_dual_core_vco_tank_config(tmp_path / "tank.local.yaml", gds, geom)
    cfg = load_config(config)
    ports = {port.name: port for port in cfg.ports}

    assert ports["PP"].xy_um == (155.0, -geom.feed_length_um)
    assert ports["PN"].xy_um == (175.0, -geom.feed_length_um)
    assert ports["SP"].xy_um == (155.0, geom.core_height_um + geom.feed_length_um)
    assert ports["SN"].xy_um == (175.0, geom.core_height_um + geom.feed_length_um)
    assert ports["PP"].edge == "bottom"
    assert ports["SP"].edge == "top"
    assert check_legality(rasterize_config(cfg), cfg).valid


def test_dual_core_vco_tank_generator_octagon_mode(tmp_path):
    geom = DualCoreVcoTankGeometry(pixel_style="octagon", include_octagon_corner_patches=True)
    gds = generate_dual_core_vco_tank_gds(tmp_path / "tank_oct.gds", geom)
    info = inspect_raw_gds(gds, top_cell="dual_core_vco_tank")

    assert int(info["vertex_counts"]["8"]) > 0
    assert int(info["vertex_counts"]["4"]) > 0


def test_dual_core_vco_tank_geometry_is_parameterized(tmp_path):
    geom = DualCoreVcoTankGeometry(core_width_um=220.0, core_height_um=240.0, feed_spacing_um=20.0)
    gds = generate_dual_core_vco_tank_gds(tmp_path / "small_tank.gds", geom)
    lib = gdstk.read_gds(str(gds))
    top = {cell.name: cell for cell in lib.cells}[geom.top_cell]

    assert top.bounding_box() == ((0.0, -26.0), (220.0, 266.0))


def test_dual_core_vco_tank_guard_ring_is_preserved_and_previewed(tmp_path):
    geom = DualCoreVcoTankGeometry(include_guard_ring=True)
    gds = generate_dual_core_vco_tank_gds(tmp_path / "tank_guard.gds", geom)
    info = inspect_raw_gds(gds, top_cell=geom.top_cell)

    assert info["polygon_counts"]["31/0"] == 4
    assert info["label_counts"]["31/0:G"] == 1

    config = write_dual_core_vco_tank_config(tmp_path / "tank_guard.local.yaml", gds, geom)
    cfg = load_config(config)
    assert cfg.layers["guard"] == (31, 0)

    maskset = rasterize_config(cfg)
    preview = write_layout_preview(maskset, tmp_path / "guard_preview.png", cfg)
    candidate = write_candidate_gds(maskset, cfg, tmp_path / "candidate.gds")
    candidate_info = inspect_raw_gds(candidate, top_cell=geom.top_cell)

    assert preview.exists()
    assert preview.stat().st_size > 0
    assert candidate_info["polygon_counts"]["31/0"] == 4


def test_dual_core_vco_tank_guard_ring_overlaps_north_south_feeds(tmp_path):
    geom = DualCoreVcoTankGeometry(include_guard_ring=True, guard_feed_overlap_um=5.0)
    gds = generate_dual_core_vco_tank_gds(tmp_path / "tank_guard.gds", geom)
    top = _top_cell(gds, geom.top_cell)
    guard_polys = [poly for poly in top.polygons if (int(poly.layer), int(poly.datatype)) == geom.guard_layer]
    m9_feed_polys = [
        poly
        for poly in top.polygons
        if (int(poly.layer), int(poly.datatype)) == geom.m9_layer
        and (_bbox(poly)[1] < 0.0 or _bbox(poly)[3] > geom.core_height_um)
    ]
    south_feeds = [poly for poly in m9_feed_polys if _bbox(poly)[1] < 0.0]
    north_feeds = [poly for poly in m9_feed_polys if _bbox(poly)[3] > geom.core_height_um]

    assert any(_overlap_area(_bbox(feed), _bbox(ring)) > 0.0 for feed in south_feeds for ring in guard_polys)
    assert any(_overlap_area(_bbox(feed), _bbox(ring)) > 0.0 for feed in north_feeds for ring in guard_polys)


def test_dual_core_vco_tank_optional_guard_ports_are_static_references(tmp_path):
    geom = DualCoreVcoTankGeometry(include_guard_ring=True, include_guard_ports=True)
    gds = generate_dual_core_vco_tank_gds(tmp_path / "tank_guard_ports.gds", geom)
    info = inspect_raw_gds(gds, top_cell=geom.top_cell)

    assert info["label_counts"]["31/0:GS"] == 1
    assert info["label_counts"]["31/0:GN"] == 1

    config = write_dual_core_vco_tank_config(tmp_path / "tank_guard_ports.local.yaml", gds, geom)
    cfg = load_config(config)
    ports = {port.name: port for port in cfg.ports}

    assert ports["GS"].layer == "guard"
    assert ports["GN"].layer == "guard"
    assert ports["GS"].edge == "bottom"
    assert ports["GN"].edge == "top"
    assert ports["GS"].xy_um == (geom.core_width_um / 2.0, -geom.feed_length_um)
    assert ports["GN"].xy_um == (geom.core_width_um / 2.0, geom.core_height_um + geom.feed_length_um)
    assert check_legality(rasterize_config(cfg), cfg).valid
