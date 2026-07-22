from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from .config import load_config, load_objective, prepare_run_dir, run_dir_for_config
from .emx_runner import BaseEmxRunner, select_runner
from .gds_io import export_candidate_gds
from .legality import check_legality
from .masks import MaskSet, apply_fixed_masks, load_masks_npz, save_masks_npz
from .mutate import apply_flips, sample_flip_group
from .rasterize import rasterize_config
from .reporting import append_event, generate_report, read_events, write_history, write_layout_preview
from .schemas import ObjectiveResult, OptimizationConfig, model_to_dict


def evaluate_masks(
    cfg: OptimizationConfig,
    maskset: MaskSet,
    run_dir: Path,
    eval_index: int,
    runner: BaseEmxRunner | None = None,
    incumbent_fom: float | None = None,
) -> Dict[str, object]:
    runner = runner or select_runner(cfg)
    eval_dir = run_dir / "evaluations" / f"eval_{eval_index:04d}"
    eval_dir.mkdir(parents=True, exist_ok=True)
    apply_fixed_masks(maskset)
    legality = check_legality(maskset, cfg)
    event: Dict[str, object] = {
        "kind": "evaluation",
        "eval_index": eval_index,
        "timestamp": time.time(),
        "legality_valid": legality.valid,
        "reason": ";".join(legality.reasons) if legality.reasons else None,
    }
    save_masks_npz(maskset, eval_dir / "design" / "masks.npz")
    if not legality.valid:
        (eval_dir / "results").mkdir(exist_ok=True)
        (eval_dir / "results" / "metrics.json").write_text(json.dumps({"legality": model_to_dict(legality)}, indent=2), encoding="utf-8")
        event.update({"emx_success": False, "objective_valid": False, "accepted": False})
        append_event(run_dir, event)
        return event

    gds_path = export_candidate_gds(maskset, cfg, eval_dir)
    write_layout_preview(maskset, eval_dir / "design" / "layout.png")
    emx_result = runner.run(cfg, eval_dir, gds_path, maskset, {"eval_index": eval_index})
    event.update({"emx_success": emx_result.success, "emx_reason": emx_result.reason, "emx_attempts": emx_result.attempts})
    if not emx_result.success or emx_result.touchstone_path is None:
        event.update({"objective_valid": False, "accepted": False, "reason": emx_result.reason or "emx_failed"})
        append_event(run_dir, event)
        return event

    objective_fn = load_objective(cfg.objective.plugin)
    objective: ObjectiveResult = objective_fn(emx_result.touchstone_path, {"eval_index": eval_index}, cfg.objective.params)
    accepted = False
    if objective.valid and incumbent_fom is not None:
        accepted = objective.fom > incumbent_fom or (cfg.dbs.accept_equal and objective.fom == incumbent_fom)
    event.update(
        {
            "touchstone_path": str(emx_result.touchstone_path),
            "objective_valid": objective.valid,
            "fom": objective.fom,
            "loss": objective.loss,
            "metrics": objective.metrics,
            "reason": objective.reason,
            "accepted": accepted,
        }
    )
    (eval_dir / "results").mkdir(exist_ok=True)
    (eval_dir / "results" / "metrics.json").write_text(json.dumps(model_to_dict(objective), indent=2, sort_keys=True), encoding="utf-8")
    append_event(run_dir, event)
    return event


def run_dbs(config_path: str | Path, resume: bool = False) -> Path:
    config_path = Path(config_path)
    cfg = load_config(config_path)
    run_dir = prepare_run_dir(cfg, config_path if not resume else None)
    runner = select_runner(cfg)
    state_path = run_dir / "state.json"
    masks_path = run_dir / "state_masks.npz"
    rng = np.random.default_rng(cfg.dbs.random_seed)

    if resume and state_path.exists() and masks_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        current = load_masks_npz(masks_path)
        best_fom = float(state.get("best_fom", -1e30))
        next_eval = int(state.get("next_eval_index", 0))
        best_eval = state.get("best_eval")
        rejections_in_a_row = int(state.get("rejections_in_a_row", 0))
    else:
        current = rasterize_config(cfg)
        save_masks_npz(current, run_dir / "seed" / "masks.npz")
        write_layout_preview(current, run_dir / "seed" / "layout.png")
        best_fom = -1e30
        best_eval = None
        rejections_in_a_row = 0
        seed_event = evaluate_masks(cfg, current.copy(), run_dir, 0, runner=runner, incumbent_fom=best_fom)
        next_eval = 1
        if seed_event.get("objective_valid"):
            best_fom = float(seed_event.get("fom", -1e30))
            best_eval = 0
            _save_best(run_dir, best_eval, best_fom, seed_event)
        _write_state(state_path, masks_path, current, next_eval, best_eval, best_fom, rejections_in_a_row)

    while next_eval < cfg.dbs.max_evaluations and rejections_in_a_row < cfg.dbs.max_rejections_in_a_row:
        flips = sample_flip_group(current, cfg.dbs, rng)
        candidate = apply_flips(current, flips)
        event = evaluate_masks(cfg, candidate, run_dir, next_eval, runner=runner, incumbent_fom=best_fom)
        if event.get("objective_valid") and event.get("accepted"):
            current = candidate
            best_fom = float(event["fom"])
            best_eval = next_eval
            rejections_in_a_row = 0
            _save_best(run_dir, best_eval, best_fom, event)
        else:
            rejections_in_a_row += 1
        _write_state(state_path, masks_path, current, next_eval + 1, best_eval, best_fom, rejections_in_a_row)
        next_eval += 1

    write_history(run_dir, read_events(run_dir))
    generate_report(run_dir, summary_only=True, top_n=cfg.report.top_n)
    return run_dir


def eval_one(config_path: str | Path) -> Path:
    cfg = load_config(config_path)
    run_dir = prepare_run_dir(cfg, config_path)
    maskset = rasterize_config(cfg)
    save_masks_npz(maskset, run_dir / "seed" / "masks.npz")
    event = evaluate_masks(cfg, maskset, run_dir, 0, runner=select_runner(cfg), incumbent_fom=-1e30)
    if event.get("objective_valid"):
        _save_best(run_dir, 0, float(event.get("fom", -1e30)), event)
    write_history(run_dir, read_events(run_dir))
    return run_dir


def resume_run(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    config_path = run_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Cannot resume without {config_path}")
    return run_dbs(config_path, resume=True)


def _write_state(
    state_path: Path,
    masks_path: Path,
    current: MaskSet,
    next_eval: int,
    best_eval: object,
    best_fom: float,
    rejections_in_a_row: int,
) -> None:
    save_masks_npz(current, masks_path)
    state = {
        "next_eval_index": next_eval,
        "best_eval": best_eval,
        "best_fom": best_fom,
        "rejections_in_a_row": rejections_in_a_row,
        "state_masks": str(masks_path),
        "updated_at": time.time(),
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _save_best(run_dir: Path, best_eval: object, best_fom: float, event: Dict[str, object]) -> None:
    best = {"best_eval": best_eval, "best_fom": best_fom, "event": event}
    (run_dir / "best.json").write_text(json.dumps(best, default=str, indent=2, sort_keys=True), encoding="utf-8")
    eval_dir = run_dir / "evaluations" / f"eval_{int(best_eval):04d}" if best_eval is not None else None
    if eval_dir and eval_dir.exists():
        best_dir = run_dir / "best"
        best_dir.mkdir(exist_ok=True)
        for rel in ("design/candidate.gds", "design/layout.png", "results/metrics.json"):
            src = eval_dir / rel
            if src.exists():
                dst = best_dir / Path(rel).name
                shutil.copy2(src, dst)
