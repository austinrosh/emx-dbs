from __future__ import annotations

from pathlib import Path

from emx_dbs.config import load_config
from emx_dbs.emx_runner import _write_emx_script

from .conftest import write_config


def test_real_emx_script_uses_integrand_positional_cli(tmp_path, simple_seed):
    config = write_config(
        tmp_path,
        simple_seed,
        emx={
            "backend": "real",
            "executable": "emx",
            "proc_file": str(tmp_path / "process.proc"),
            "env_script": str(tmp_path / "setup_emx_env.sh"),
            "freq_start_ghz": 1,
            "freq_stop_ghz": 3,
            "freq_step_ghz": 1,
            "timeout_s": 10,
            "retries": 1,
        },
    )
    cfg = load_config(config)
    script = tmp_path / "run_emx.sh"
    _write_emx_script(script, cfg, Path("candidate.gds"), tmp_path / "results")
    text = script.read_text(encoding="utf-8")
    assert "--touchstone" in text
    assert "--s-file=" in text
    assert "candidate.gds TOP" in text
    assert "1000000000 2000000000 3000000000" in text
    assert "--proc" not in text
    assert "--gds" not in text
    assert "--top" not in text
    assert "--freq-start-ghz" not in text
