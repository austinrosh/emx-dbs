from __future__ import annotations

import json

import numpy as np

from emx_dbs.config import load_config
from emx_dbs.corner_overlap import bridge_polygons, diagonal_bridge_centers
from emx_dbs.dbs import run_dbs
from emx_dbs.emx_runner import FakeEmxRunner
from emx_dbs.masks import LayerGrid
from emx_dbs.objectives import maximize_coupling
from emx_dbs.rasterize import rasterize_config
from emx_dbs.touchstone import write_touchstone

from .conftest import write_config


def test_diagonal_corner_overlap_patch_generation():
    grid = LayerGrid("metal6", (0, 0, 10, 10), 5.0, (2, 2))
    mask = np.array([[True, False], [False, True]])
    centers = diagonal_bridge_centers(mask, grid)
    bridges = list(bridge_polygons(mask, grid, 5.0))
    assert centers == [(5.0, 5.0)]
    assert len(bridges) == 1
    assert len(bridges[0]) == 4


def test_objective_with_synthetic_touchstone(tmp_path):
    s = np.zeros((2, 2, 2), dtype=complex)
    s[:, 1, 0] = 0.5
    path = write_touchstone(tmp_path / "result.s2p", [1, 2], s)
    result = maximize_coupling(path, {}, {"from_port": 1, "to_port": 2, "band_start_ghz": 1, "band_stop_ghz": 2})
    assert result.valid
    assert result.fom == 0.5


def test_fake_emx_backend(tmp_path, simple_seed):
    cfg = load_config(write_config(tmp_path, simple_seed))
    maskset = rasterize_config(cfg)
    result = FakeEmxRunner().run(cfg, tmp_path / "eval", tmp_path / "candidate.gds", maskset, {})
    assert result.success
    assert result.touchstone_path is not None
    assert result.touchstone_path.exists()


def test_dbs_resume_state(tmp_path, simple_seed):
    config = write_config(tmp_path, simple_seed, dbs={"max_evaluations": 2, "random_seed": 3})
    run_dir = run_dbs(config)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["next_eval_index"] == 2
    assert (run_dir / "state_masks.npz").exists()
    assert (run_dir / "events.jsonl").exists()
