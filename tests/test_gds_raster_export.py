from __future__ import annotations

import gdstk
import numpy as np

from emx_dbs.config import load_config
from emx_dbs.dbs import eval_one
from emx_dbs.gds_io import create_rectangle_seed_gds, export_candidate_gds, inspect_gds, inspect_raw_gds, write_candidate_gds
from emx_dbs.masks import LayerGrid, MaskSet
from emx_dbs.rasterize import rasterize_config
from emx_dbs.reporting import write_gds_preview, write_layout_preview

from .conftest import write_config


def test_rasterization_correctness(tmp_path, simple_seed):
    cfg = load_config(write_config(tmp_path, simple_seed))
    maskset = rasterize_config(cfg)
    assert maskset.masks["metal6"].shape == (2, 4)
    assert maskset.masks["metal6"].all()


def test_gds_export_round_trip(tmp_path, simple_seed):
    cfg = load_config(write_config(tmp_path, simple_seed))
    maskset = rasterize_config(cfg)
    out = export_candidate_gds(maskset, cfg, tmp_path / "eval_0000")
    lib = gdstk.read_gds(str(out))
    assert "TOP" in {cell.name for cell in lib.cells}
    top = {cell.name: cell for cell in lib.cells}["TOP"]
    assert {label.text for label in top.labels} == {"P1", "P2"}
    info = inspect_gds(cfg)
    assert info["top_cell_found"] is True
    assert info["configured_layer_counts"]["metal6"] == 2


def test_raw_gds_inspection_and_preview(tmp_path, simple_seed):
    info = inspect_raw_gds(simple_seed)

    assert info["top_cell"] == "TOP"
    assert info["polygon_counts"]["126/0"] == 2
    assert info["vertex_counts"]["4"] == 2

    out = write_gds_preview(simple_seed, tmp_path / "input.png")

    assert out.exists()
    assert out.stat().st_size > 1000


def test_layout_preview_writes_config_overlays(tmp_path, simple_seed):
    cfg = load_config(
        write_config(
            tmp_path,
            simple_seed,
            fixed_regions=[{"name": "left_feed", "layers": ["metal6"], "bbox_um": [0, 0, 5, 5]}],
            drc={
                "allow_same_layer_diagonal_contact": True,
                "corner_overlap_bridge": True,
            },
        )
    )
    maskset = rasterize_config(cfg)
    maskset.masks["metal6"][:] = False
    maskset.masks["metal6"][0, 0] = True
    maskset.masks["metal6"][1, 1] = True

    out = write_layout_preview(maskset, tmp_path / "layout.png", cfg)

    assert out.exists()
    assert out.stat().st_size > 1000


def test_candidate_export_writes_corner_overlap_bridge(tmp_path, simple_seed):
    cfg = load_config(
        write_config(
            tmp_path,
            simple_seed,
            mutable_regions=[{"name": "window", "layers": ["metal6"], "bbox_um": [0, 0, 10, 10]}],
            fixed_regions=[],
            ports=[],
            connectivity={"required": [], "forbidden_shorts": [], "vias": []},
            drc={
                "allow_same_layer_diagonal_contact": True,
                "corner_overlap_bridge": True,
            },
        )
    )
    mask = np.array([[True, False], [False, True]])
    zeros = np.zeros_like(mask, dtype=bool)
    maskset = MaskSet(
        masks={"metal6": mask},
        mutable_masks={"metal6": np.ones_like(mask, dtype=bool)},
        fixed_masks={"metal6": zeros.copy()},
        fixed_region_masks={"metal6": zeros.copy()},
        grids={"metal6": LayerGrid("metal6", (0.0, 0.0, 10.0, 10.0), 5.0, (2, 2))},
    )

    out = write_candidate_gds(maskset, cfg, tmp_path / "corner_bridge.gds")
    info = inspect_raw_gds(out, top_cell="TOP")

    assert info["layer_stats"]["126/0"]["area_um2"] > 50.0


def test_export_can_drop_unconfigured_layers(tmp_path):
    seed = create_rectangle_seed_gds(
        tmp_path / "seed.gds",
        "TOP",
        [
            ((0, 0, 10, 10), 126, 0),
            ((20, 0, 30, 10), 999, 0),
        ],
    )
    cfg = load_config(
        write_config(
            tmp_path,
            seed,
            layout={"preserve_unconfigured_layers": False},
            mutable_regions=[{"name": "window", "layers": ["metal6"], "bbox_um": [0, 0, 10, 10]}],
            fixed_regions=[],
            ports=[],
        )
    )
    maskset = rasterize_config(cfg)
    out = write_candidate_gds(maskset, cfg, tmp_path / "square_seed.gds")
    lib = gdstk.read_gds(str(out))
    top = {cell.name: cell for cell in lib.cells}["TOP"]

    assert {(int(poly.layer), int(poly.datatype)) for poly in top.polygons} == {(126, 0)}


def test_rasterize_can_seed_vias_from_overlap(tmp_path):
    seed = create_rectangle_seed_gds(
        tmp_path / "seed.gds",
        "TOP",
        [
            ((0, 0, 10, 10), 39, 60),
            ((0, 0, 10, 10), 38, 40),
        ],
    )
    cfg = load_config(
        write_config(
            tmp_path,
            seed,
            layout={"pixel_size_um": 10.0, "seed_vias_from_overlap": True},
            layers={"m9": [39, 60], "m8": [38, 40], "v8": [58, 60]},
            mutable_regions=[{"name": "window", "layers": ["m9", "m8", "v8"], "bbox_um": [0, 0, 10, 10]}],
            fixed_regions=[],
            ports=[],
            connectivity={
                "required": [],
                "forbidden_shorts": [],
                "vias": [{"name": "v8_stack", "via_layer": "v8", "lower_layer": "m8", "upper_layer": "m9"}],
            },
        )
    )

    maskset = rasterize_config(cfg)

    assert maskset.masks["m9"][0, 0]
    assert maskset.masks["m8"][0, 0]
    assert maskset.masks["v8"][0, 0]


def test_eval_one_fake_emx_writes_artifacts(tmp_path, simple_seed):
    config = write_config(tmp_path, simple_seed)
    run_dir = eval_one(config)
    assert (run_dir / "evaluations" / "eval_0000" / "design" / "candidate.gds").exists()
    assert (run_dir / "evaluations" / "eval_0000" / "results" / "result.s2p").exists()
    assert (run_dir / "best.json").exists()
