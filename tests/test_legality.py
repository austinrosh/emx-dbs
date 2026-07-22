from __future__ import annotations

import numpy as np

from emx_dbs.legality import check_legality
from emx_dbs.masks import LayerGrid, MaskSet, apply_fixed_masks
from emx_dbs.schemas import OptimizationConfig


def _cfg(diagonal: bool = False, forbidden=None) -> OptimizationConfig:
    return OptimizationConfig(
        run={"run_id": "x", "output_root": "runs"},
        layout={"seed_gds": "seed.gds", "top_cell": "TOP", "pixel_size_um": 5.0},
        layers={"metal6": [126, 0]},
        mutable_regions=[{"name": "w", "layers": ["metal6"], "bbox_um": [0, 0, 10, 10]}],
        ports=[
            {"name": "P1", "layer": "metal6", "xy_um": [2.5, 2.5]},
            {"name": "P2", "layer": "metal6", "xy_um": [7.5, 7.5]},
        ],
        connectivity={"required": [["P1", "P2"]], "forbidden_shorts": forbidden or [], "vias": []},
        drc={
            "min_width_um": 5.0,
            "min_spacing_um": 5.0,
            "allow_same_layer_diagonal_contact": diagonal,
            "corner_overlap_bridge": diagonal,
        },
        emx={"backend": "fake", "freq_start_ghz": 1, "freq_stop_ghz": 2, "freq_step_ghz": 1},
        dbs={"max_evaluations": 2},
        objective={"plugin": "emx_dbs.objectives:maximize_coupling"},
    )


def _diag_maskset() -> MaskSet:
    mask = np.array([[True, False], [False, True]])
    grid = LayerGrid("metal6", (0, 0, 10, 10), 5.0, (2, 2))
    zeros = np.zeros_like(mask, dtype=bool)
    return MaskSet(
        masks={"metal6": mask.copy()},
        mutable_masks={"metal6": np.ones_like(mask, dtype=bool)},
        fixed_masks={"metal6": zeros.copy()},
        fixed_region_masks={"metal6": zeros.copy()},
        grids={"metal6": grid},
    )


def test_fixed_region_preservation():
    mask = np.array([[False, False], [False, False]])
    fixed_values = np.array([[True, False], [False, False]])
    fixed_region = np.array([[True, False], [False, False]])
    grid = LayerGrid("metal6", (0, 0, 10, 10), 5.0, (2, 2))
    maskset = MaskSet(
        masks={"metal6": mask},
        mutable_masks={"metal6": ~fixed_region},
        fixed_masks={"metal6": fixed_values},
        fixed_region_masks={"metal6": fixed_region},
        grids={"metal6": grid},
    )
    apply_fixed_masks(maskset)
    assert maskset.masks["metal6"][0, 0]


def test_connectivity_without_diagonal_contact_rejects():
    result = check_legality(_diag_maskset(), _cfg(diagonal=False))
    assert not result.valid
    assert any(reason.startswith("required_connectivity") for reason in result.reasons)


def test_connectivity_with_diagonal_contact_accepts():
    result = check_legality(_diag_maskset(), _cfg(diagonal=True))
    assert result.valid


def test_forbidden_short_rejects_connected_ports():
    maskset = _diag_maskset()
    maskset.masks["metal6"][:] = True
    cfg = _cfg(diagonal=False, forbidden=[["P1", "P2"]])
    result = check_legality(maskset, cfg)
    assert not result.valid
    assert any(reason.startswith("forbidden_short") for reason in result.reasons)


def _via_stack_cfg() -> OptimizationConfig:
    return OptimizationConfig(
        run={"run_id": "via", "output_root": "runs"},
        layout={"seed_gds": "seed.gds", "top_cell": "TOP", "pixel_size_um": 10.0},
        layers={"m8": [38, 40], "v8": [58, 60], "m9": [39, 60]},
        mutable_regions=[{"name": "w", "layers": ["m8", "v8", "m9"], "bbox_um": [0, 0, 10, 10]}],
        ports=[],
        connectivity={
            "required": [],
            "forbidden_shorts": [],
            "vias": [{"name": "v8_stack", "via_layer": "v8", "lower_layer": "m8", "upper_layer": "m9"}],
        },
        drc={
            "min_width_um": 10.0,
            "min_spacing_um": 10.0,
            "allow_same_layer_diagonal_contact": False,
            "corner_overlap_bridge": False,
        },
        emx={"backend": "fake", "freq_start_ghz": 1, "freq_stop_ghz": 2, "freq_step_ghz": 1},
        dbs={"max_evaluations": 2},
        objective={"plugin": "emx_dbs.objectives:maximize_coupling"},
    )


def _via_stack_maskset(*, m8: bool = True, v8: bool = True, m9: bool = True) -> MaskSet:
    grid = LayerGrid("stack", (0, 0, 10, 10), 10.0, (1, 1))
    mutable = np.ones((1, 1), dtype=bool)
    fixed = np.zeros((1, 1), dtype=bool)
    return MaskSet(
        masks={
            "m8": np.array([[m8]], dtype=bool),
            "v8": np.array([[v8]], dtype=bool),
            "m9": np.array([[m9]], dtype=bool),
        },
        mutable_masks={"m8": mutable.copy(), "v8": mutable.copy(), "m9": mutable.copy()},
        fixed_masks={"m8": fixed.copy(), "v8": fixed.copy(), "m9": fixed.copy()},
        fixed_region_masks={"m8": fixed.copy(), "v8": fixed.copy(), "m9": fixed.copy()},
        grids={
            "m8": LayerGrid("m8", grid.bbox_um, grid.pixel_size_um, grid.shape),
            "v8": LayerGrid("v8", grid.bbox_um, grid.pixel_size_um, grid.shape),
            "m9": LayerGrid("m9", grid.bbox_um, grid.pixel_size_um, grid.shape),
        },
    )


def test_via_requires_lower_and_upper_metal():
    cfg = _via_stack_cfg()

    enclosed = check_legality(_via_stack_maskset(), cfg)
    assert enclosed.valid

    missing_upper = check_legality(_via_stack_maskset(m9=False), cfg)
    assert not missing_upper.valid
    assert any("via_not_enclosed:v8_stack:v8:0,0:missing=m9" == reason for reason in missing_upper.reasons)

    missing_lower = check_legality(_via_stack_maskset(m8=False), cfg)
    assert not missing_lower.valid
    assert any("via_not_enclosed:v8_stack:v8:0,0:missing=m8" == reason for reason in missing_lower.reasons)
