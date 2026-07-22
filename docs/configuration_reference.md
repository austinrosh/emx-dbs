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
- `vias`: explicit via rules connecting one via layer to two metal layers. Interlayer connectivity is never implicit.

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
