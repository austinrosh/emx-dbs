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
