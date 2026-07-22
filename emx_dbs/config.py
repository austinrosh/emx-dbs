from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any, Callable

import yaml

from .schemas import OptimizationConfig


ObjectiveFn = Callable[[Path, dict, dict], Any]


def _resolve_path(path: Path | None, config_dir: Path, *, prefer_existing_cwd: bool = True) -> Path | None:
    if path is None or path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if prefer_existing_cwd and cwd_path.exists():
        return cwd_path.resolve()
    return (config_dir / path).resolve()


def _resolve_output_root(path: Path, config_dir: Path) -> Path:
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def load_config(path: str | Path) -> OptimizationConfig:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = OptimizationConfig(**raw)
    config_dir = config_path.parent
    cfg.layout.seed_gds = _resolve_path(cfg.layout.seed_gds, config_dir)  # type: ignore[assignment]
    cfg.run.output_root = _resolve_output_root(cfg.run.output_root, config_dir)  # type: ignore[assignment]
    cfg.emx.proc_file = _resolve_path(cfg.emx.proc_file, config_dir)  # type: ignore[assignment]
    cfg.emx.env_script = _resolve_path(cfg.emx.env_script, config_dir)  # type: ignore[assignment]
    return cfg


def run_dir_for_config(cfg: OptimizationConfig) -> Path:
    return Path(cfg.run.output_root) / cfg.run.run_id


def prepare_run_dir(cfg: OptimizationConfig, config_path: str | Path | None = None) -> Path:
    run_dir = run_dir_for_config(cfg)
    run_dir.mkdir(parents=True, exist_ok=True)
    for rel in ("seed", "evaluations", "report"):
        (run_dir / rel).mkdir(exist_ok=True)
    if config_path is not None:
        shutil.copy2(config_path, run_dir / "config.yaml")
    return run_dir


def load_objective(import_path: str) -> ObjectiveFn:
    if ":" not in import_path:
        raise ValueError(f"Objective plugin must be 'module:function', got {import_path!r}")
    module_name, fn_name = import_path.split(":", 1)
    module = importlib.import_module(module_name)
    fn = getattr(module, fn_name)
    if not callable(fn):
        raise TypeError(f"Objective target {import_path!r} is not callable")
    return fn
