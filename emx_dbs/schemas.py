from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


BBox = Tuple[float, float, float, float]
XY = Tuple[float, float]
LayerSpec = Tuple[int, int]


if hasattr(BaseModel, "model_validate"):
    from pydantic import ConfigDict

    class StrictModel(BaseModel):
        model_config = ConfigDict(extra="forbid")

else:

    class StrictModel(BaseModel):
        class Config:
            extra = "forbid"


class RunConfig(StrictModel):
    run_id: str
    output_root: Path = Path("runs")
    resume: bool = True


class LayoutConfig(StrictModel):
    seed_gds: Path
    top_cell: str
    pixel_size_um: float
    preserve_unconfigured_layers: bool = True
    seed_vias_from_overlap: bool = False


class RegionConfig(StrictModel):
    name: str
    bbox_um: BBox
    layers: Optional[List[str]] = None


class PortConfig(StrictModel):
    name: str
    layer: str
    xy_um: XY
    edge: Optional[Literal["left", "right", "top", "bottom"]] = None
    width_um: Optional[float] = None


class ViaRule(StrictModel):
    name: str
    via_layer: str
    lower_layer: str
    upper_layer: str


class ConnectivityConfig(StrictModel):
    required: List[List[str]] = Field(default_factory=list)
    forbidden_shorts: List[List[str]] = Field(default_factory=list)
    vias: List[ViaRule] = Field(default_factory=list)


class DRCConfig(StrictModel):
    min_width_um: float
    min_spacing_um: float
    allow_same_layer_diagonal_contact: bool = False
    corner_overlap_bridge: bool = False


class EMXConfig(StrictModel):
    executable: str = "emx"
    proc_file: Optional[Path] = None
    env_script: Optional[Path] = None
    key: Optional[str] = None
    freq_start_ghz: float
    freq_stop_ghz: float
    freq_step_ghz: float
    timeout_s: int = 120
    retries: int = 3
    backend: Literal["real", "fake"] = "real"
    extra_args: List[str] = Field(default_factory=list)
    touchstone_glob: str = "*.s*p"


class DBSConfig(StrictModel):
    max_evaluations: int = 1000
    max_rejections_in_a_row: int = 400
    move_style: str = "probabilistic_independent_layer_flips"
    metal_flip_count_weights: List[float] = Field(default_factory=lambda: [1.0])
    metal_flip_count_values: List[int] = Field(default_factory=lambda: [1])
    symmetry_axes: List[Literal["x", "y"]] = Field(default_factory=list)
    symmetry_center_um: Optional[XY] = None
    random_seed: Optional[int] = None
    accept_equal: bool = False


class ObjectiveConfig(StrictModel):
    plugin: str
    params: Dict[str, Any] = Field(default_factory=dict)


class ReportConfig(StrictModel):
    top_n: int = 5


class OptimizationConfig(StrictModel):
    run: RunConfig
    layout: LayoutConfig
    layers: Dict[str, LayerSpec]
    mutable_regions: List[RegionConfig]
    fixed_regions: List[RegionConfig] = Field(default_factory=list)
    ports: List[PortConfig] = Field(default_factory=list)
    connectivity: ConnectivityConfig = Field(default_factory=ConnectivityConfig)
    drc: DRCConfig
    emx: EMXConfig
    dbs: DBSConfig
    objective: ObjectiveConfig
    report: ReportConfig = Field(default_factory=ReportConfig)


class ObjectiveResult(StrictModel):
    fom: float
    loss: float
    metrics: Dict[str, Any] = Field(default_factory=dict)
    valid: bool = True
    reason: Optional[str] = None


class LegalityResult(StrictModel):
    valid: bool
    reasons: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class EmxRunResult(StrictModel):
    success: bool
    touchstone_path: Optional[Path] = None
    reason: Optional[str] = None
    attempts: int = 0
    elapsed_s: float = 0.0


def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")  # type: ignore[attr-defined]
    return model.dict()
