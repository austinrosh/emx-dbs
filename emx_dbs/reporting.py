from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import numpy as np

from .corner_overlap import bridge_polygons
from .gds_io import _require_gdstk, _select_cell
from .masks import MaskSet
from .schemas import OptimizationConfig, RegionConfig


_LAYER_COLORS = {
    "m8": "#cf4b4b",
    "m9": "#8b4dd3",
    "v8": "#d7d7d7",
    "guard": "#2f855a",
    "ground": "#2f855a",
}
_FALLBACK_COLORS = ["#cf4b4b", "#8b4dd3", "#e59f5a", "#2f855a", "#17becf", "#7f7f7f"]


def write_layout_preview(
    maskset: MaskSet,
    path: Union[str, Path],
    cfg: Optional[OptimizationConfig] = None,
    *,
    annotate_geometry: bool = True,
    show_legend: bool = True,
    show_title: bool = True,
    show_fixed_overlay: Optional[bool] = None,
    show_ports: bool = True,
    bounds_um: Optional[Tuple[float, float, float, float]] = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _configure_matplotlib_cache()
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon, Rectangle
    except ImportError:
        path.with_suffix(".txt").write_text("matplotlib not installed; layout preview skipped\n", encoding="utf-8")
        return path

    fig, ax = plt.subplots(figsize=(8, 8))
    for idx, (layer, mask) in enumerate(maskset.masks.items()):
        grid = maskset.grids[layer]
        color = _preview_color(layer, idx)
        rows, cols = np.nonzero(mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            x0, y0, x1, y1 = grid.index_bbox(row, col)
            if _is_via_layer(layer, cfg):
                pad = 0.18 * grid.pixel_size_um
                ax.add_patch(
                    Rectangle(
                        (x0 + pad, y0 + pad),
                        x1 - x0 - 2.0 * pad,
                        y1 - y0 - 2.0 * pad,
                        facecolor=color,
                        alpha=0.72,
                        edgecolor="#8a8a8a",
                        linewidth=0.55,
                        hatch="xx",
                    )
                )
            else:
                ax.add_patch(
                    Rectangle(
                        (x0, y0),
                        x1 - x0,
                        y1 - y0,
                        facecolor=color,
                        alpha=0.82,
                        edgecolor=color,
                        linewidth=0.45,
                    )
                )

        fixed = maskset.fixed_region_masks.get(layer)
        fixed_values = maskset.fixed_masks.get(layer)
        draw_fixed_overlay = annotate_geometry if show_fixed_overlay is None else show_fixed_overlay
        if draw_fixed_overlay and fixed is not None and fixed_values is not None:
            fixed_rows, fixed_cols = np.nonzero(fixed & fixed_values)
            for row, col in zip(fixed_rows.tolist(), fixed_cols.tolist()):
                x0, y0, x1, y1 = grid.index_bbox(row, col)
                ax.add_patch(
                    Rectangle(
                        (x0, y0),
                        x1 - x0,
                        y1 - y0,
                        facecolor=color,
                        alpha=0.90,
                        edgecolor="#111111",
                        linewidth=0.7,
                        hatch="///",
                    )
                )

        if cfg is not None and cfg.drc.allow_same_layer_diagonal_contact and cfg.drc.corner_overlap_bridge:
            for points in bridge_polygons(mask, grid, cfg.drc.min_width_um):
                ax.add_patch(
                    Polygon(
                        points,
                        closed=True,
                        facecolor="#f6ad55",
                        edgecolor="#9c4221",
                        linewidth=0.8,
                        alpha=0.75,
                    )
                )

        ax.plot([], [], color=color, linewidth=6, alpha=0.55, label=_layer_label(layer, cfg))

    if cfg is not None:
        _draw_static_seed_polygons(ax, cfg, maskset, hatch_static=annotate_geometry, add_legend=show_legend)
        if annotate_geometry:
            _draw_regions(ax, cfg.mutable_regions, "#475569", "mutable", linestyle="--")
            _draw_regions(ax, cfg.fixed_regions, "#b45309", "fixed/feed", linestyle="-")
        if show_ports:
            _draw_ports(ax, cfg)

        if annotate_geometry and cfg.drc.allow_same_layer_diagonal_contact and cfg.drc.corner_overlap_bridge:
            ax.plot([], [], color="#f6ad55", marker="D", linestyle="", markersize=6, label="corner overlap bridge")
        if annotate_geometry and any(mask.any() for mask in maskset.fixed_region_masks.values()):
            ax.plot([], [], color="#111111", linewidth=1.0, label="hatched fixed feed geometry")

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    if show_title and cfg is not None:
        ax.set_title(f"{cfg.run.run_id} / {cfg.layout.top_cell}")
    if bounds_um is not None:
        x0, y0, x1, y1 = bounds_um
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
    else:
        _set_axis_limits(ax, maskset, cfg)
    if cfg is not None:
        _draw_pixel_grid(ax, cfg.layout.pixel_size_um)
    else:
        ax.grid(True, linewidth=0.3, alpha=0.4)
    if show_legend:
        _dedupe_legend(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def write_gds_preview(
    gds_path: Union[str, Path],
    path: Union[str, Path],
    top_cell: Optional[str] = None,
    cfg: Optional[OptimizationConfig] = None,
    *,
    annotate_geometry: bool = True,
    show_legend: bool = True,
    show_title: bool = True,
    show_ports: bool = True,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        gdstk = _require_gdstk()
        _configure_matplotlib_cache()
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon
    except ImportError:
        path.with_suffix(".txt").write_text("matplotlib or gdstk not installed; GDS preview skipped\n", encoding="utf-8")
        return path

    lib = gdstk.read_gds(str(gds_path))
    selected = _select_cell(lib, top_cell)
    if selected is None:
        raise ValueError(f"No top cell found in {gds_path}")
    flat = selected.copy(selected.name + "__PREVIEW")
    flat.flatten()

    fig, ax = plt.subplots(figsize=(8, 8))
    layer_order = sorted({(int(poly.layer), int(poly.datatype)) for poly in flat.polygons})
    layer_lookup = _configured_layer_lookup(cfg)
    layer_colors = {
        key: _preview_color(layer_lookup[key], idx) if key in layer_lookup else _FALLBACK_COLORS[idx % len(_FALLBACK_COLORS)]
        for idx, key in enumerate(layer_order)
    }
    for poly in flat.polygons:
        key = (int(poly.layer), int(poly.datatype))
        color = layer_colors[key]
        ax.add_patch(Polygon(poly.points, closed=True, facecolor=color, edgecolor=color, linewidth=0.35, alpha=0.42))

    for key in layer_order:
        layer_name = layer_lookup.get(key)
        label = _layer_label(layer_name, cfg) if layer_name is not None else f"{key[0]}/{key[1]}"
        ax.plot([], [], color=layer_colors[key], linewidth=6, alpha=0.55, label=label)

    config_port_names = {port.name for port in cfg.ports} if cfg is not None else set()
    for label in flat.labels:
        if str(label.text) in config_port_names:
            continue
        x, y = label.origin
        key = (int(label.layer), int(label.texttype))
        color = layer_colors.get(key, "#111111")
        ax.scatter([x], [y], marker="o", s=40, facecolor="white", edgecolor=color, linewidth=1.2, zorder=10)
        ax.annotate(
            str(label.text),
            xy=(x, y),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
            color="#111827",
            weight="bold",
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": color, "alpha": 0.88},
            zorder=11,
        )

    if cfg is not None:
        if annotate_geometry:
            _draw_regions(ax, cfg.mutable_regions, "#475569", "mutable", linestyle="--")
            _draw_regions(ax, cfg.fixed_regions, "#b45309", "fixed/feed", linestyle="-")
        if show_ports:
            _draw_ports(ax, cfg)

    bbox = flat.bounding_box()
    if bbox is not None:
        xmin, ymin = float(bbox[0][0]), float(bbox[0][1])
        xmax, ymax = float(bbox[1][0]), float(bbox[1][1])
        span = max(xmax - xmin, ymax - ymin, 1.0)
        margin = 0.06 * span
        ax.set_xlim(xmin - margin, xmax + margin)
        ax.set_ylim(ymin - margin, ymax + margin)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    title = f"{Path(gds_path).name} / {selected.name}"
    if cfg is not None:
        title = f"{cfg.run.run_id} input / {selected.name}"
    if show_title:
        ax.set_title(title)
    if cfg is not None:
        _draw_pixel_grid(ax, cfg.layout.pixel_size_um)
    else:
        ax.grid(True, linewidth=0.3, alpha=0.35)
    if show_legend:
        _dedupe_legend(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def _configured_layer_lookup(cfg: Optional[OptimizationConfig]) -> Dict[Tuple[int, int], str]:
    if cfg is None:
        return {}
    return {
        (int(layer), int(datatype)): name
        for name, (layer, datatype) in cfg.layers.items()
    }


def _layer_label(layer: str, cfg: Optional[OptimizationConfig]) -> str:
    if cfg is None or layer not in cfg.layers:
        return layer
    gds_layer, datatype = cfg.layers[layer]
    return f"{layer} ({gds_layer}/{datatype})"


def _preview_color(layer: str, idx: int = 0) -> str:
    return _LAYER_COLORS.get(layer.lower(), _FALLBACK_COLORS[idx % len(_FALLBACK_COLORS)])


def _is_via_layer(layer: str, cfg: Optional[OptimizationConfig]) -> bool:
    if layer.lower().startswith("v"):
        return True
    if cfg is None:
        return False
    return any(via.via_layer == layer for via in cfg.connectivity.vias)


def _draw_static_seed_polygons(
    ax,
    cfg: OptimizationConfig,
    maskset: MaskSet,
    *,
    hatch_static: bool = True,
    add_legend: bool = True,
) -> None:
    from matplotlib.patches import Polygon

    try:
        gdstk = _require_gdstk()
        lib = gdstk.read_gds(str(cfg.layout.seed_gds))
        selected = _select_cell(lib, cfg.layout.top_cell)
    except Exception:
        return
    if selected is None:
        return

    flat = selected.copy(selected.name + "__STATIC_PREVIEW")
    flat.flatten()
    layer_lookup = {tuple(spec): name for name, spec in cfg.layers.items()}
    active_layers = set(maskset.masks)
    drawn: Dict[str, str] = {}
    for poly in flat.polygons:
        key = (int(poly.layer), int(poly.datatype))
        layer_name = layer_lookup.get(key)
        if layer_name in active_layers:
            continue
        if layer_name is None and not cfg.layout.preserve_unconfigured_layers:
            continue
        label = _layer_label(layer_name, cfg) if layer_name is not None else f"static seed ({key[0]}/{key[1]})"
        color = _preview_color(layer_name or "static", len(drawn))
        ax.add_patch(
            Polygon(
                poly.points,
                closed=True,
                facecolor=color,
                edgecolor=color,
                linewidth=0.9,
                alpha=0.22 if layer_name != "guard" else 0.34,
                hatch="//" if hatch_static and layer_name in {"guard", "ground"} else None,
            )
        )
        drawn[label] = color
    if add_legend:
        for label, color in drawn.items():
            ax.plot([], [], color=color, linewidth=6, alpha=0.55, label=label)


def _draw_regions(ax, regions: Iterable[RegionConfig], color: str, prefix: str, linestyle: str) -> None:
    from matplotlib.patches import Rectangle

    for region in regions:
        x0, y0, x1, y1 = region.bbox_um
        ax.add_patch(
            Rectangle(
                (x0, y0),
                x1 - x0,
                y1 - y0,
                facecolor="none",
                edgecolor=color,
                linestyle=linestyle,
                linewidth=1.2,
                alpha=0.9,
            )
        )
        ax.text(
            x0,
            y1,
            f"{prefix}: {region.name}",
            fontsize=7,
            color=color,
            ha="left",
            va="bottom",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 1.5},
        )


def _draw_ports(ax, cfg: OptimizationConfig) -> None:
    for port in cfg.ports:
        x, y = port.xy_um
        color = "#111111"
        ax.plot([x], [y], marker="x", color=color, markersize=9, markeredgewidth=2.0, linestyle="", zorder=12)
        label = port.name
        dx, dy = _port_text_offset(port.edge, port.layer)
        ax.annotate(
            label,
            xy=(x, y),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=9,
            color=color,
            weight="bold",
            ha="center" if port.edge in {"top", "bottom"} else ("right" if port.edge == "left" else "left"),
            va="bottom" if port.edge == "top" else ("top" if port.edge == "bottom" else "center"),
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 0.8},
            zorder=13,
        )


def _port_text_offset(edge: Optional[str], layer: Optional[str] = None) -> Tuple[float, float]:
    static_reference = layer in {"guard", "ground"}
    if edge == "left":
        return -5.0, 2.0
    if edge == "right":
        return 5.0, 2.0
    if edge == "top":
        return 0.0, 19.0 if static_reference else 5.0
    if edge == "bottom":
        return 0.0, -19.0 if static_reference else -5.0
    return 5.0, 5.0


def _draw_pixel_grid(ax, pixel_size_um: float) -> None:
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x_start = np.floor(xmin / pixel_size_um) * pixel_size_um
    x_stop = np.ceil(xmax / pixel_size_um) * pixel_size_um + 0.5 * pixel_size_um
    y_start = np.floor(ymin / pixel_size_um) * pixel_size_um
    y_stop = np.ceil(ymax / pixel_size_um) * pixel_size_um + 0.5 * pixel_size_um
    ax.set_xticks(np.arange(x_start, x_stop, pixel_size_um), minor=True)
    ax.set_yticks(np.arange(y_start, y_stop, pixel_size_um), minor=True)
    ax.grid(which="minor", color="#d0d7de", linewidth=0.35, alpha=0.75)
    ax.grid(which="major", color="#9ca3af", linewidth=0.5, alpha=0.25)


def _set_axis_limits(ax, maskset: MaskSet, cfg: Optional[OptimizationConfig]) -> None:
    bounds = _preview_bounds(maskset, cfg)
    if bounds is None:
        return
    xmin, ymin, xmax, ymax = bounds
    span = max(xmax - xmin, ymax - ymin, 1.0)
    margin = 0.06 * span
    ax.set_xlim(xmin - margin, xmax + margin)
    ax.set_ylim(ymin - margin, ymax + margin)


def _preview_bounds(maskset: MaskSet, cfg: Optional[OptimizationConfig]) -> Optional[Tuple[float, float, float, float]]:
    xs: List[float] = []
    ys: List[float] = []
    for grid in maskset.grids.values():
        xs.extend([grid.xmin, grid.xmax])
        ys.extend([grid.ymin, grid.ymax])
    if cfg is not None:
        seed_bbox = _seed_bbox(cfg)
        if seed_bbox is not None:
            x0, y0, x1, y1 = seed_bbox
            xs.extend([x0, x1])
            ys.extend([y0, y1])
        for region in list(cfg.mutable_regions) + list(cfg.fixed_regions):
            x0, y0, x1, y1 = region.bbox_um
            xs.extend([x0, x1])
            ys.extend([y0, y1])
        for port in cfg.ports:
            x, y = port.xy_um
            xs.append(x)
            ys.append(y)
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _seed_bbox(cfg: OptimizationConfig) -> Optional[Tuple[float, float, float, float]]:
    try:
        gdstk = _require_gdstk()
        lib = gdstk.read_gds(str(cfg.layout.seed_gds))
        selected = _select_cell(lib, cfg.layout.top_cell)
    except Exception:
        return None
    if selected is None:
        return None
    flat = selected.copy(selected.name + "__BOUNDS")
    flat.flatten()
    bbox = flat.bounding_box()
    if bbox is None:
        return None
    return float(bbox[0][0]), float(bbox[0][1]), float(bbox[1][0]), float(bbox[1][1])


def _dedupe_legend(ax) -> None:
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    unique_handles = []
    unique_labels = []
    for handle, label in zip(handles, labels):
        if label in seen:
            continue
        seen.add(label)
        unique_handles.append(handle)
        unique_labels.append(label)
    if unique_handles:
        ax.legend(unique_handles, unique_labels, loc="upper right", fontsize=8, framealpha=0.9)


def append_event(run_dir: Path, event: Dict[str, object]) -> None:
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str, sort_keys=True) + "\n")


def read_events(run_dir: Path) -> List[Dict[str, object]]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    events: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def write_history(run_dir: Path, events: Iterable[Dict[str, object]]) -> Path:
    path = run_dir / "history.parquet"
    rows = [event for event in events if event.get("kind") == "evaluation"]
    if not rows:
        return path
    try:
        import pandas as pd

        pd.DataFrame(rows).to_parquet(path, index=False)
    except Exception:
        fallback = run_dir / "history.csv"
        try:
            import pandas as pd

            pd.DataFrame(rows).to_csv(fallback, index=False)
        except Exception:
            fallback.write_text(json.dumps(rows, default=str, indent=2), encoding="utf-8")
    return path


def generate_report(run_dir: Union[str, Path], summary_only: bool = False, top_n: int = 5) -> Dict[str, object]:
    run_dir = Path(run_dir)
    report_dir = run_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    events = read_events(run_dir)
    evals = [event for event in events if event.get("kind") == "evaluation"]
    accepted = [event for event in evals if event.get("accepted")]
    rejected = [event for event in evals if not event.get("objective_valid", False) or event.get("legality_valid") is False or event.get("emx_success") is False]
    reasons = Counter(str(event.get("reason", "none")) for event in rejected)
    best = max((event for event in evals if event.get("objective_valid")), key=lambda e: float(e.get("fom", -1e30)), default=None)
    summary = {
        "run_dir": str(run_dir),
        "evaluations": len(evals),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "best_eval": best.get("eval_index") if best else None,
        "best_fom": best.get("fom") if best else None,
        "rejection_reasons": dict(reasons),
    }
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if not summary_only:
        _plot_convergence(report_dir / "convergence.png", evals)
        _plot_rejections(report_dir / "rejection_reasons.png", reasons)
    return summary


def _plot_convergence(path: Path, evals: List[Dict[str, object]]) -> None:
    try:
        _configure_matplotlib_cache()
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError:
        return
    xs = []
    ys = []
    best = []
    incumbent = -1e30
    for event in evals:
        if event.get("objective_valid"):
            x = int(event.get("eval_index", len(xs)))
            y = float(event.get("fom", -1e30))
            incumbent = max(incumbent, y)
            xs.append(x)
            ys.append(y)
            best.append(incumbent)
    if not xs:
        return
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(xs, ys, ".", markersize=4, label="candidate")
    ax.plot(xs, best, "-", linewidth=1.5, label="best")
    ax.set_xlabel("evaluation")
    ax.set_ylabel("FOM")
    ax.grid(True, alpha=0.35)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _plot_rejections(path: Path, reasons: Counter) -> None:
    if not reasons:
        return
    try:
        _configure_matplotlib_cache()
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError:
        return
    labels, counts = zip(*reasons.most_common())
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(range(len(labels)), counts)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right")
    ax.set_ylabel("count")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _configure_matplotlib_cache() -> None:
    cache_dir = Path(tempfile.gettempdir()) / "emx_dbs_matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
