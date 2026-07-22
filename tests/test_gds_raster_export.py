from __future__ import annotations

import gdstk

from emx_dbs.config import load_config
from emx_dbs.dbs import eval_one
from emx_dbs.gds_io import export_candidate_gds, inspect_gds
from emx_dbs.rasterize import rasterize_config

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


def test_eval_one_fake_emx_writes_artifacts(tmp_path, simple_seed):
    config = write_config(tmp_path, simple_seed)
    run_dir = eval_one(config)
    assert (run_dir / "evaluations" / "eval_0000" / "design" / "candidate.gds").exists()
    assert (run_dir / "evaluations" / "eval_0000" / "results" / "result.s2p").exists()
    assert (run_dir / "best.json").exists()
