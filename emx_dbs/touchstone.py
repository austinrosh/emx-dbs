from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

import numpy as np


_EXT_RE = re.compile(r"\.s(\d+)p$", re.IGNORECASE)


@dataclass
class SParameters:
    frequency_hz: np.ndarray
    s: np.ndarray
    z0: float = 50.0

    @property
    def nports(self) -> int:
        return int(self.s.shape[1])

    def band_mask(self, start_ghz: float | None = None, stop_ghz: float | None = None) -> np.ndarray:
        freq_ghz = self.frequency_hz / 1e9
        mask = np.ones(freq_ghz.shape, dtype=bool)
        if start_ghz is not None:
            mask &= freq_ghz >= start_ghz
        if stop_ghz is not None:
            mask &= freq_ghz <= stop_ghz
        return mask

    def mag(self, to_port: int, from_port: int) -> np.ndarray:
        return np.abs(self.s[:, to_port - 1, from_port - 1])

    def mag_db(self, to_port: int, from_port: int) -> np.ndarray:
        return 20.0 * np.log10(np.maximum(self.mag(to_port, from_port), 1e-30))


def nports_from_path(path: str | Path) -> int:
    match = _EXT_RE.search(str(path))
    if not match:
        raise ValueError(f"Cannot infer Touchstone port count from {path}")
    return int(match.group(1))


def _unit_scale(unit: str) -> float:
    return {
        "hz": 1.0,
        "khz": 1e3,
        "mhz": 1e6,
        "ghz": 1e9,
    }.get(unit.lower(), 1.0)


def _to_complex(a: float, b: float, fmt: str) -> complex:
    fmt = fmt.upper()
    if fmt == "RI":
        return complex(a, b)
    if fmt == "MA":
        return a * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
    if fmt == "DB":
        mag = 10 ** (a / 20.0)
        return mag * complex(math.cos(math.radians(b)), math.sin(math.radians(b)))
    raise ValueError(f"Unsupported Touchstone data format {fmt!r}")


def read_touchstone(path: str | Path) -> SParameters:
    path = Path(path)
    n = nports_from_path(path)
    unit = "ghz"
    fmt = "MA"
    z0 = 50.0
    values = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.split("!", 1)[0].strip()
            if not line:
                continue
            if line.startswith("#"):
                parts = line[1:].strip().split()
                if parts:
                    unit = parts[0]
                for idx, part in enumerate(parts):
                    if part.upper() in {"RI", "MA", "DB"}:
                        fmt = part.upper()
                    if part.upper() == "R" and idx + 1 < len(parts):
                        z0 = float(parts[idx + 1])
                continue
            values.extend(float(part) for part in line.split())

    record_len = 1 + 2 * n * n
    if len(values) % record_len != 0:
        raise ValueError(f"{path} has {len(values)} numeric values, not a multiple of {record_len}")

    records = np.asarray(values, dtype=float).reshape((-1, record_len))
    freqs = records[:, 0] * _unit_scale(unit)
    s = np.zeros((records.shape[0], n, n), dtype=complex)
    for k, rec in enumerate(records):
        pairs = rec[1:].reshape((n * n, 2))
        entries = [_to_complex(a, b, fmt) for a, b in pairs]
        if n == 2:
            order = [(0, 0), (1, 0), (0, 1), (1, 1)]
        else:
            order = [(row, col) for row in range(n) for col in range(n)]
        for (row, col), value in zip(order, entries):
            s[k, row, col] = value
    return SParameters(freqs, s, z0=z0)


def write_touchstone(path: str | Path, frequencies_ghz: Iterable[float], s: np.ndarray, z0: float = 50.0) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    s = np.asarray(s, dtype=complex)
    n = int(s.shape[1])
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# GHZ S RI R {z0:g}\n")
        for idx, freq in enumerate(frequencies_ghz):
            if n == 2:
                order = [(0, 0), (1, 0), (0, 1), (1, 1)]
            else:
                order = [(row, col) for row in range(n) for col in range(n)]
            vals = [f"{float(freq):.12g}"]
            for row, col in order:
                val = s[idx, row, col]
                vals.extend([f"{val.real:.12g}", f"{val.imag:.12g}"])
            f.write(" ".join(vals) + "\n")
    return path
