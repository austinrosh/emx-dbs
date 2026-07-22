from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np

from .masks import MaskSet


def write_layout_preview(maskset: MaskSet, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _configure_matplotlib_cache()
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ImportError:
        path.with_suffix(".txt").write_text("matplotlib not installed; layout preview skipped\n", encoding="utf-8")
        return path

    fig, ax = plt.subplots(figsize=(7, 7))
    colors = ["#2b6cb0", "#c53030", "#2f855a", "#805ad5", "#b7791f"]
    for idx, (layer, mask) in enumerate(maskset.masks.items()):
        grid = maskset.grids[layer]
        color = colors[idx % len(colors)]
        rows, cols = np.nonzero(mask)
        for row, col in zip(rows.tolist(), cols.tolist()):
            x0, y0, x1, y1 = grid.index_bbox(row, col)
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=color, alpha=0.35, edgecolor=color, linewidth=0.2))
        ax.plot([], [], color=color, linewidth=6, alpha=0.5, label=layer)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (um)")
    ax.set_ylabel("y (um)")
    ax.legend(loc="best")
    ax.grid(True, linewidth=0.3, alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


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


def generate_report(run_dir: str | Path, summary_only: bool = False, top_n: int = 5) -> Dict[str, object]:
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
