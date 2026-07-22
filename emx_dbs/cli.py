from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .config import load_config, prepare_run_dir
from .dbs import eval_one as eval_one_run
from .dbs import resume_run, run_dbs
from .emx_runner import validate_emx_environment
from .gds_io import inspect_gds, inspect_raw_gds, write_candidate_gds
from .masks import save_masks_npz
from .rasterize import rasterize_config
from .reporting import generate_report, write_gds_preview, write_layout_preview
from .tank_generator import DualCoreVcoTankGeometry, generate_dual_core_vco_tank_gds, write_dual_core_vco_tank_config


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


@app.command("inspect-raw-gds")
def inspect_raw_gds_cmd(gds: Path, top_cell: Optional[str] = typer.Option(None, "--top-cell")) -> None:
    typer.echo(json.dumps(inspect_raw_gds(gds, top_cell=top_cell), indent=2, sort_keys=True, default=str))


@app.command("preview-gds")
def preview_gds_cmd(
    gds: Path,
    top_cell: Optional[str] = typer.Option(None, "--top-cell"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
) -> None:
    out = output or Path("local") / "previews" / f"{gds.stem}_input.png"
    typer.echo(str(write_gds_preview(gds, out, top_cell=top_cell)))


@app.command("preview-input")
def preview_input_cmd(config: Path, output: Optional[Path] = typer.Option(None, "--output", "-o")) -> None:
    cfg = load_config(config)
    run_dir = prepare_run_dir(cfg, config)
    out = output or run_dir / "input" / "layout.png"
    typer.echo(str(write_gds_preview(cfg.layout.seed_gds, out, top_cell=cfg.layout.top_cell, cfg=cfg)))


@app.command("rasterize")
def rasterize_cmd(config: Path) -> None:
    cfg = load_config(config)
    run_dir = prepare_run_dir(cfg, config)
    maskset = rasterize_config(cfg)
    save_masks_npz(maskset, run_dir / "seed" / "masks.npz")
    write_layout_preview(maskset, run_dir / "seed" / "layout.png", cfg)
    typer.echo(str(run_dir / "seed" / "masks.npz"))


@app.command("export-square-seed")
def export_square_seed_cmd(
    config: Path,
    output: Path = typer.Option(..., "--output", "-o"),
    preview_output: Optional[Path] = typer.Option(None, "--preview-output"),
    synthesize_vias_from_overlap: bool = typer.Option(False, "--synthesize-vias-from-overlap"),
    drop_unconfigured_layers: bool = typer.Option(False, "--drop-unconfigured-layers"),
) -> None:
    cfg = load_config(config)
    if synthesize_vias_from_overlap:
        cfg.layout.seed_vias_from_overlap = True
    if drop_unconfigured_layers:
        cfg.layout.preserve_unconfigured_layers = False
    maskset = rasterize_config(cfg)
    out = write_candidate_gds(maskset, cfg, output)
    if preview_output is not None:
        write_layout_preview(maskset, preview_output, cfg)
    typer.echo(str(out))


@app.command("generate-dual-core-vco-tank")
def generate_dual_core_vco_tank_cmd(
    output: Path = typer.Option(..., "--output", "-o"),
    config_output: Optional[Path] = typer.Option(None, "--config-output"),
    preview_output: Optional[Path] = typer.Option(None, "--preview-output"),
    top_cell: str = typer.Option("dual_core_vco_tank", "--top-cell"),
    run_id: str = typer.Option("dual_core_vco_tank", "--run-id"),
    core_width_um: float = typer.Option(330.0, "--core-width-um"),
    core_height_um: float = typer.Option(330.0, "--core-height-um"),
    pitch_um: float = typer.Option(10.0, "--pitch-um"),
    m9_ring_width_um: float = typer.Option(20.0, "--m9-ring-width-um"),
    center_gap_um: float = typer.Option(10.0, "--center-gap-um"),
    feed_spacing_um: float = typer.Option(20.0, "--feed-spacing-um"),
    feed_width_um: float = typer.Option(5.0, "--feed-width-um"),
    feed_length_um: float = typer.Option(26.0, "--feed-length-um"),
    m8_trace_width_um: float = typer.Option(10.0, "--m8-trace-width-um"),
    pixel_style: str = typer.Option("square", "--pixel-style"),
    octagon_chamfer_um: Optional[float] = typer.Option(None, "--octagon-chamfer-um"),
    include_octagon_corner_patches: bool = typer.Option(False, "--corner-patches/--no-corner-patches"),
    emit_v8: bool = typer.Option(True, "--emit-v8/--no-emit-v8"),
    include_guard_ring: bool = typer.Option(False, "--include-guard-ring/--no-guard-ring"),
    guard_layer: int = typer.Option(31, "--guard-layer"),
    guard_datatype: int = typer.Option(0, "--guard-datatype"),
    guard_offset_um: float = typer.Option(26.0, "--guard-offset-um"),
    guard_width_um: float = typer.Option(10.0, "--guard-width-um"),
    guard_feed_overlap_um: float = typer.Option(5.0, "--guard-feed-overlap-um"),
    include_guard_ports: bool = typer.Option(False, "--include-guard-ports/--no-guard-ports"),
    include_ground_ring: bool = typer.Option(False, "--include-ground-ring/--no-ground-ring"),
) -> None:
    geom = DualCoreVcoTankGeometry(
        top_cell=top_cell,
        core_width_um=core_width_um,
        core_height_um=core_height_um,
        pitch_um=pitch_um,
        m9_ring_width_um=m9_ring_width_um,
        center_gap_um=center_gap_um,
        feed_spacing_um=feed_spacing_um,
        feed_width_um=feed_width_um,
        feed_length_um=feed_length_um,
        m8_trace_width_um=m8_trace_width_um,
        pixel_style=pixel_style,
        octagon_chamfer_um=octagon_chamfer_um,
        include_octagon_corner_patches=include_octagon_corner_patches,
        emit_v8=emit_v8,
        include_guard_ring=include_guard_ring,
        include_ground_ring=include_ground_ring,
        guard_layer=(guard_layer, guard_datatype),
        guard_offset_um=guard_offset_um,
        guard_width_um=guard_width_um,
        guard_feed_overlap_um=guard_feed_overlap_um,
        include_guard_ports=include_guard_ports,
    )
    gds = generate_dual_core_vco_tank_gds(output, geom)
    config = write_dual_core_vco_tank_config(config_output, gds, geom, run_id=run_id) if config_output else None
    preview_cfg = load_config(config) if config is not None else None
    preview = write_gds_preview(gds, preview_output, top_cell=geom.top_cell, cfg=preview_cfg) if preview_output else None
    typer.echo(
        json.dumps(
            {
                "gds": str(gds),
                "config": str(config) if config is not None else None,
                "preview": str(preview) if preview is not None else None,
            },
            indent=2,
        )
    )


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
