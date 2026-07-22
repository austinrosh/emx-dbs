from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np


@dataclass(frozen=True)
class LayerGrid:
    layer_name: str
    bbox_um: Tuple[float, float, float, float]
    pixel_size_um: float
    shape: Tuple[int, int]

    @property
    def xmin(self) -> float:
        return self.bbox_um[0]

    @property
    def ymin(self) -> float:
        return self.bbox_um[1]

    @property
    def xmax(self) -> float:
        return self.bbox_um[2]

    @property
    def ymax(self) -> float:
        return self.bbox_um[3]

    def xy_to_index(self, x_um: float, y_um: float) -> Tuple[int, int] | None:
        col = int(np.floor((x_um - self.xmin) / self.pixel_size_um))
        row = int(np.floor((y_um - self.ymin) / self.pixel_size_um))
        if 0 <= row < self.shape[0] and 0 <= col < self.shape[1]:
            return row, col
        return None

    def index_center(self, row: int, col: int) -> Tuple[float, float]:
        p = self.pixel_size_um
        return self.xmin + (col + 0.5) * p, self.ymin + (row + 0.5) * p

    def index_bbox(self, row: int, col: int) -> Tuple[float, float, float, float]:
        p = self.pixel_size_um
        x0 = self.xmin + col * p
        y0 = self.ymin + row * p
        return x0, y0, x0 + p, y0 + p


@dataclass
class MaskSet:
    masks: Dict[str, np.ndarray]
    mutable_masks: Dict[str, np.ndarray]
    fixed_masks: Dict[str, np.ndarray]
    fixed_region_masks: Dict[str, np.ndarray]
    grids: Dict[str, LayerGrid]

    def copy(self) -> "MaskSet":
        return MaskSet(
            masks={k: v.copy() for k, v in self.masks.items()},
            mutable_masks={k: v.copy() for k, v in self.mutable_masks.items()},
            fixed_masks={k: v.copy() for k, v in self.fixed_masks.items()},
            fixed_region_masks={k: v.copy() for k, v in self.fixed_region_masks.items()},
            grids=dict(self.grids),
        )


def apply_fixed_masks(maskset: MaskSet) -> MaskSet:
    for layer, mask in maskset.masks.items():
        fixed_region = maskset.fixed_region_masks.get(layer)
        fixed_values = maskset.fixed_masks.get(layer)
        if fixed_region is None or fixed_values is None:
            continue
        mask[fixed_region] = fixed_values[fixed_region]
    return maskset


def iter_active_pixels(maskset: MaskSet, layer: str) -> Iterable[Tuple[int, int]]:
    rows, cols = np.nonzero(maskset.masks[layer])
    return zip(rows.tolist(), cols.tolist())


def save_masks_npz(maskset: MaskSet, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {}
    for prefix, mapping in (
        ("mask", maskset.masks),
        ("mutable", maskset.mutable_masks),
        ("fixed", maskset.fixed_masks),
        ("fixed_region", maskset.fixed_region_masks),
    ):
        for layer, arr in mapping.items():
            arrays[f"{prefix}__{layer}"] = arr.astype(np.bool_)
    metadata = {"grids": {layer: asdict(grid) for layer, grid in maskset.grids.items()}}
    arrays["__metadata__"] = np.array(json.dumps(metadata))
    np.savez_compressed(path, **arrays)


def load_masks_npz(path: str | Path) -> MaskSet:
    data = np.load(Path(path), allow_pickle=False)
    metadata = json.loads(str(data["__metadata__"]))
    grids = {
        layer: LayerGrid(
            layer_name=grid["layer_name"],
            bbox_um=tuple(grid["bbox_um"]),
            pixel_size_um=float(grid["pixel_size_um"]),
            shape=tuple(grid["shape"]),
        )
        for layer, grid in metadata["grids"].items()
    }
    groups: Dict[str, Dict[str, np.ndarray]] = {
        "mask": {},
        "mutable": {},
        "fixed": {},
        "fixed_region": {},
    }
    for key in data.files:
        if key == "__metadata__":
            continue
        prefix, layer = key.split("__", 1)
        groups[prefix][layer] = data[key].astype(bool)
    return MaskSet(
        masks=groups["mask"],
        mutable_masks=groups["mutable"],
        fixed_masks=groups["fixed"],
        fixed_region_masks=groups["fixed_region"],
        grids=grids,
    )
