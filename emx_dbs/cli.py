from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import load_config, prepare_run_dir
from .dbs import eval_one as eval_one_run
from .dbs import resume_run, run_dbs
from .emx_runner import validate_emx_environment
from .gds_io import inspect_gds
from .masks import save_masks_npz
from .rasterize import rasterize_config
from .reporting import generate_report, write_layout_preview


app = typer.Typer(help="Standalone GDS-seeded EMX DBS optimizer.")


@app.command("validate-env")
def validate_env(config: Path) -> None:
    cfg = load_config(config)
    result = validate_emx_environment(cfg)
    typer.echo(json.dumps(result, indent=2, sort_keys=True, default=str))
    if not result.get("ok"):
        raise typer.Exit(code=1)


@app.command("inspect-gds")
def inspect_gds_cmd(config: Path) -> None:
    cfg = load_config(config)
    typer.echo(json.dumps(inspect_gds(cfg), indent=2, sort_keys=True, default=str))


@app.command("rasterize")
def rasterize_cmd(config: Path) -> None:
    cfg = load_config(config)
    run_dir = prepare_run_dir(cfg, config)
    maskset = rasterize_config(cfg)
    save_masks_npz(maskset, run_dir / "seed" / "masks.npz")
    write_layout_preview(maskset, run_dir / "seed" / "layout.png")
    typer.echo(str(run_dir / "seed" / "masks.npz"))


@app.command("eval-one")
def eval_one_cmd(config: Path) -> None:
    run_dir = eval_one_run(config)
    typer.echo(str(run_dir))


@app.command("run")
def run_cmd(config: Path) -> None:
    run_dir = run_dbs(config, resume=False)
    typer.echo(str(run_dir))


@app.command("resume")
def resume_cmd(run_dir: Path) -> None:
    resumed = resume_run(run_dir)
    typer.echo(str(resumed))


@app.command("report")
def report_cmd(run_dir: Path, summary_only: bool = typer.Option(False, "--summary-only")) -> None:
    summary = generate_report(run_dir, summary_only=summary_only)
    typer.echo(json.dumps(summary, indent=2, sort_keys=True, default=str))
