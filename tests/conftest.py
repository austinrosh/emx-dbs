from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from emx_dbs.gds_io import create_rectangle_seed_gds


@pytest.fixture
def simple_seed(tmp_path: Path) -> Path:
    return create_rectangle_seed_gds(
        tmp_path / "seed.gds",
        "TOP",
        [
            ((0, 0, 10, 10), 126, 0),
            ((10, 0, 20, 10), 126, 0),
        ],
    )


def write_config(tmp_path: Path, seed: Path, **overrides) -> Path:
    data = {
        "run": {"run_id": "test_run", "output_root": str(tmp_path / "runs")},
        "layout": {"seed_gds": str(seed), "top_cell": "TOP", "pixel_size_um": 5.0},
        "layers": {"metal6": [126, 0]},
        "mutable_regions": [{"name": "window", "layers": ["metal6"], "bbox_um": [0, 0, 20, 10]}],
        "fixed_regions": [],
        "ports": [
            {"name": "P1", "layer": "metal6", "xy_um": [2.5, 2.5], "edge": "left"},
            {"name": "P2", "layer": "metal6", "xy_um": [17.5, 2.5], "edge": "right"},
        ],
        "connectivity": {"required": [["P1", "P2"]], "forbidden_shorts": [], "vias": []},
        "drc": {
            "min_width_um": 5.0,
            "min_spacing_um": 5.0,
            "allow_same_layer_diagonal_contact": False,
            "corner_overlap_bridge": False,
        },
        "emx": {
            "backend": "fake",
            "executable": "emx",
            "proc_file": "/path/to/process.proc",
            "env_script": None,
            "freq_start_ghz": 1,
            "freq_stop_ghz": 5,
            "freq_step_ghz": 1,
            "timeout_s": 10,
            "retries": 1,
        },
        "dbs": {
            "max_evaluations": 3,
            "max_rejections_in_a_row": 10,
            "move_style": "probabilistic_independent_layer_flips",
            "metal_flip_count_weights": [1.0],
            "metal_flip_count_values": [1],
            "random_seed": 1,
        },
        "objective": {
            "plugin": "emx_dbs.objectives:maximize_coupling",
            "params": {"from_port": 1, "to_port": 2, "band_start_ghz": 1, "band_stop_ghz": 5},
        },
    }
    _deep_update(data, overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _deep_update(dst: dict, src: dict) -> None:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_update(dst[key], value)
        else:
            dst[key] = value
