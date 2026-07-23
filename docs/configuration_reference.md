# Configuration Reference

The YAML file is authoritative. `emx-dbs` does not infer nets from arbitrary GDS.

## Required Sections

`run`

- `run_id`: output run name.
- `output_root`: parent directory for run artifacts.

`layout`

- `seed_gds`: input GDS.
- `top_cell`: top cell to flatten/import.
- `pixel_size_um`: DBS pixel size.
- `preserve_unconfigured_layers`: keep GDS layers that are not listed in `layers` when exporting candidates. Defaults to `true`; set to `false` for strict studies that should emit only configured layers.
- `seed_vias_from_overlap`: initialize configured via masks anywhere their lower and upper metal masks overlap. Defaults to `false`; useful when an input seed has adjacent metals but omits the via layer.

`layers`

Maps logical names to `[layer, datatype]`, for example:

```yaml
layers:
  metal6: [126, 0]
  via5: [225, 0]
```

`mutable_regions`

Physical windows in microns where pixels may be changed. If `layers` is omitted on a region, all configured layers are included.

`fixed_regions`

Physical windows restored after every mutation. Fixed geometry is raster-preserved in mutable windows; non-mutable seed geometry is copied through during GDS export.

`ports`

Named ports with logical layer and physical coordinate. Port coordinates are used for explicit connectivity checks, GDS label export, and EMX command generation. If `width_um` is set, `emx-dbs` emits an EMX internal-port option such as `--internal=P1,4`.

`connectivity`

- `required`: groups of port names that must be connected.
- `forbidden_shorts`: groups of port names that must not be shorted.
- `vias`: explicit via rules connecting one via layer to two metal layers. Interlayer connectivity is never implicit. Every active via pixel must also have active lower and upper metal at the via center; otherwise legality rejects the candidate with `via_not_enclosed`.

`drc`

Pixel-space proxy checks:

- `min_width_um`
- `min_spacing_um`
- `allow_same_layer_diagonal_contact`
- `corner_overlap_bridge`

When diagonal contact and bridges are enabled, same-layer diagonal-only pixel contacts are considered connected and a DRC-sized diamond bridge is added at the shared corner during GDS export.

`emx`

- `backend`: `fake` or `real`.
- `executable`: EMX command or absolute path.
- `proc_file`: EMX process file.
- `env_script`: optional shell script sourced before EMX.
- `freq_start_ghz`, `freq_stop_ghz`, `freq_step_ghz`
- `timeout_s`, `retries`
- `key`: optional EMX process decryption key. When set, the generated EMX command includes `--key=<value>`. Use only in ignored local configs.
- `extra_args`: appended to the generated EMX command.

`dbs`

- `max_evaluations`
- `max_rejections_in_a_row`
- `move_style`
- `metal_flip_count_weights`
- `metal_flip_count_values`
- `symmetry_axes`: optional list containing `x`, `y`, or both. `x` mirrors flips across the horizontal line `y = symmetry_center_um[1]`; `y` mirrors flips across the vertical line `x = symmetry_center_um[0]`.
- `symmetry_center_um`: optional `[x, y]` center in microns. If omitted, each layer grid's own center is used. For multi-layer structures, set this explicitly.
- `random_seed`

`objective`

The objective plugin is imported as `module:function` and called as:

```python
from pathlib import Path
from emx_dbs.schemas import ObjectiveResult

def objective(touchstone_path: Path, metadata: dict, params: dict) -> ObjectiveResult:
    ...
```

`ObjectiveResult.fom` is maximized. `loss` is minimized for reporting.

## Artifacts

```text
runs/RUN_ID/
  config.yaml
  state.json
  state_masks.npz
  best.json
  events.jsonl
  history.parquet
  seed/
  evaluations/
    eval_0000/
      design/candidate.gds
      design/masks.npz
      design/layout.png
      emx/run_emx.sh
      emx/stdout.log
      emx/stderr.log
      results/result.sNp
      results/metrics.json
  report/
```

`design/layout.png` is a diagnostic preview of the generated candidate. It shows active pixels by logical layer, GDS layer/datatype in the legend, fixed/feed geometry with hatching, mutable and fixed region outlines, configured port names/locations, and corner-overlap bridge patches when that DRC mode is enabled.

## Useful GDS Utilities

Inspect any raw GDS without a config:

```bash
emx-dbs inspect-raw-gds path/to/layout.gds --top-cell TOP
```

Preview any raw GDS:

```bash
emx-dbs preview-gds path/to/layout.gds --top-cell TOP --output local/previews/input.png
```

Preview the configured input seed with logical layer names, regions, and ports overlaid:

```bash
emx-dbs preview-input my_study.local.yaml --output local/previews/configured_input.png
```

Export a rasterized square-pixel seed GDS without running EMX:

```bash
emx-dbs export-square-seed my_study.local.yaml \
  --output local/square_seed.gds \
  --preview-output local/square_seed.png
```

For seeds that contain M8/M9 but no V8, use `layout.seed_vias_from_overlap: true` in the config, or pass `--synthesize-vias-from-overlap` to `export-square-seed`.

Generate a parametric dual-core VCO tank seed:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/tanks/ring33_square.gds \
  --config-output local/tanks/ring33_square.local.yaml \
  --preview-output local/tanks/ring33_square.png
```

Guard-ring options for that generator:

- `--include-guard-ring`: add a fixed lower-metal guard ring.
- `--guard-layer`, `--guard-datatype`: select the guard GDS layer/datatype. Defaults to N16 M1 `31/0`.
- `--guard-feed-overlap-um`: overlap the north/south guard bars with the M9 feed edges. Defaults to `5`.
- `--include-guard-ports`: add static guard reference ports `GS` and `GN`.
