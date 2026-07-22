from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

from .masks import MaskSet
from .schemas import EmxRunResult, OptimizationConfig
from .touchstone import write_touchstone


class BaseEmxRunner(ABC):
    @abstractmethod
    def run(self, cfg: OptimizationConfig, eval_dir: Path, gds_path: Path, maskset: MaskSet, metadata: dict) -> EmxRunResult:
        raise NotImplementedError


def frequency_sweep_ghz(cfg: OptimizationConfig) -> np.ndarray:
    start = cfg.emx.freq_start_ghz
    stop = cfg.emx.freq_stop_ghz
    step = cfg.emx.freq_step_ghz
    if step <= 0:
        raise ValueError("emx.freq_step_ghz must be positive")
    count = int(np.floor((stop - start) / step)) + 1
    return start + np.arange(count) * step


class FakeEmxRunner(BaseEmxRunner):
    def run(self, cfg: OptimizationConfig, eval_dir: Path, gds_path: Path, maskset: MaskSet, metadata: dict) -> EmxRunResult:
        started = time.time()
        emx_dir = eval_dir / "emx"
        results_dir = eval_dir / "results"
        emx_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        nports = max(1, len(cfg.ports))
        freqs = frequency_sweep_ghz(cfg)
        density = _mask_density(maskset)
        smooth = 0.5 + 0.5 * np.sin((freqs - freqs.min()) / max(float(np.ptp(freqs)), 1e-9) * np.pi)
        coupling = np.clip(0.15 + 0.7 * density * smooth, 0.0, 0.95)
        s = np.zeros((len(freqs), nports, nports), dtype=complex)
        for k in range(len(freqs)):
            for port in range(nports):
                s[k, port, port] = 0.12 + 0.02j
            for src in range(nports):
                for dst in range(nports):
                    if src != dst:
                        phase = -0.03 * freqs[k] * (abs(dst - src) + 1)
                        mag = coupling[k] / (abs(dst - src) + 1)
                        s[k, dst, src] = mag * np.exp(1j * phase)
        touchstone = results_dir / f"result.s{nports}p"
        write_touchstone(touchstone, freqs, s)
        (emx_dir / "stdout.log").write_text("fake EMX completed\n", encoding="utf-8")
        (emx_dir / "stderr.log").write_text("", encoding="utf-8")
        (emx_dir / "run_emx.sh").write_text("#!/usr/bin/env bash\n# fake backend: no external EMX invocation\n", encoding="utf-8")
        return EmxRunResult(success=True, touchstone_path=touchstone, attempts=1, elapsed_s=time.time() - started)


class LocalEmxRunner(BaseEmxRunner):
    def run(self, cfg: OptimizationConfig, eval_dir: Path, gds_path: Path, maskset: MaskSet, metadata: dict) -> EmxRunResult:
        started = time.time()
        emx_dir = eval_dir / "emx"
        results_dir = eval_dir / "results"
        emx_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        script = emx_dir / "run_emx.sh"
        stdout_path = emx_dir / "stdout.log"
        stderr_path = emx_dir / "stderr.log"
        _write_emx_script(script, cfg, gds_path, results_dir)

        last_reason = "not_run"
        for attempt in range(1, cfg.emx.retries + 1):
            with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
                try:
                    proc = subprocess.run(
                        ["bash", str(script)],
                        cwd=emx_dir,
                        stdout=stdout,
                        stderr=stderr,
                        timeout=cfg.emx.timeout_s,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    last_reason = "timeout"
                    continue
            if proc.returncode != 0:
                last_reason = f"nonzero_exit:{proc.returncode}"
                continue
            touchstone = _locate_touchstone(results_dir, eval_dir, cfg.emx.touchstone_glob)
            if touchstone is not None:
                return EmxRunResult(success=True, touchstone_path=touchstone, attempts=attempt, elapsed_s=time.time() - started)
            last_reason = "missing_touchstone"
        return EmxRunResult(success=False, reason=last_reason, attempts=cfg.emx.retries, elapsed_s=time.time() - started)


def _mask_density(maskset: MaskSet) -> float:
    total = 0
    active = 0
    for layer, mask in maskset.masks.items():
        mutable = maskset.mutable_masks[layer] | maskset.fixed_region_masks[layer]
        total += int(mutable.sum())
        active += int((mask & mutable).sum())
    if total == 0:
        return 0.0
    return active / total


def _write_emx_script(script: Path, cfg: OptimizationConfig, gds_path: Path, results_dir: Path) -> None:
    proc = cfg.emx.proc_file
    if proc is None:
        raise ValueError("emx.proc_file is required when emx.backend is real")
    nports = max(1, len(cfg.ports))
    touchstone = results_dir / f"result.s{nports}p"
    internal_args = []
    for port in cfg.ports:
        if port.width_um is not None:
            internal_args.append(f"--internal={port.name},{port.width_um:g}")
    key_args = [f"--key={cfg.emx.key}"] if cfg.emx.key else []
    extra_args = list(cfg.emx.extra_args)
    freqs_hz = [freq_ghz * 1e9 for freq_ghz in frequency_sweep_ghz(cfg)]
    cmd_parts = [
        cfg.emx.executable,
        "--touchstone",
        f"--s-file={touchstone}",
        "--include-command-line",
        "--verbose=2",
        *key_args,
        *internal_args,
        *extra_args,
        str(gds_path),
        cfg.layout.top_cell,
        str(proc),
        *[f"{freq_hz:.12g}" for freq_hz in freqs_hz],
    ]
    command = " ".join(shlex.quote(str(part)) for part in cmd_parts)
    env_line = f"source {shlex.quote(str(cfg.emx.env_script))}\n" if cfg.emx.env_script else ""
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"mkdir -p {shlex.quote(str(results_dir))}\n"
        f"{env_line}"
        f"{command}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _locate_touchstone(results_dir: Path, eval_dir: Path, pattern: str) -> Optional[Path]:
    for root in (results_dir, eval_dir):
        matches = sorted(root.rglob(pattern))
        if matches:
            best = matches[0]
            if best.parent != results_dir:
                copied = results_dir / best.name
                shutil.copy2(best, copied)
                return copied
            return best
    return None


def select_runner(cfg: OptimizationConfig) -> BaseEmxRunner:
    if cfg.emx.backend == "fake":
        return FakeEmxRunner()
    return LocalEmxRunner()


def validate_emx_environment(cfg: OptimizationConfig) -> Dict[str, object]:
    if cfg.emx.backend == "fake":
        return {"backend": "fake", "ok": True, "reason": "fake backend does not require EMX"}
    executable = _resolve_executable(cfg)
    proc_ok = cfg.emx.proc_file is not None and Path(cfg.emx.proc_file).exists()
    env_ok = cfg.emx.env_script is None or Path(cfg.emx.env_script).exists()
    return {
        "backend": "real",
        "ok": bool(executable and proc_ok and env_ok),
        "executable": executable,
        "proc_file_exists": proc_ok,
        "env_script_exists": env_ok,
    }


def _resolve_executable(cfg: OptimizationConfig) -> Optional[str]:
    if "/" in cfg.emx.executable:
        return cfg.emx.executable if Path(cfg.emx.executable).exists() else None

    found = shutil.which(cfg.emx.executable)
    if found:
        return found

    if cfg.emx.env_script is None or not Path(cfg.emx.env_script).exists():
        return None

    cmd = (
        f"source {shlex.quote(str(cfg.emx.env_script))} >/dev/null 2>&1 "
        f"&& command -v {shlex.quote(cfg.emx.executable)}"
    )
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return None
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().splitlines()[-1]
    return None
