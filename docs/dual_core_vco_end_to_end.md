# End-to-End Dual-Core VCO Tank Inverse Design

This guide walks a new collaborator from a clean checkout to a working dual-core VCO tank inverse-design run with `emx-dbs`. It covers installation, seed generation, GDS inspection, EMX setup, objective configuration, DBS execution, monitoring, and post-processing.

The dual-core VCO tank flow currently assumes this default stack:

- `m9`: GDS `39/60`, top metal, mutable DBS layer.
- `m8`: GDS `38/40`, fixed equator trace.
- `v8`: GDS `58/60`, fixed via stack between M8 and M9.
- `guard`: GDS `31/0`, optional fixed lower-metal guard ring.

The optimizer edits only `m9` for this structure. M8, V8, port feeds, and M9 pixels underneath active V8 are fixed so the lower stack is preserved and active V8 pixels always have both lower and upper metal.

## 1. Clone And Install

Use Python 3.8 or newer. Python 3.6 is not supported because the packaging and dependency versions require a newer interpreter.

```bash
git clone https://github.com/austinrosh/emx-dbs.git
cd emx-dbs

python3 --version
python3 -m venv .venv
source .venv/bin/activate
python --version

python -m pip install -U pip
python -m pip install -e ".[dev]"
pytest -q
```

If your system `python3` is older than 3.8, create the virtual environment with an explicit newer interpreter:

```bash
python3.8 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For notebooks:

```bash
python -m pip install -e ".[dev,notebook]"
python -m ipykernel install --user --name emx-dbs --display-name "Python 3 (emx-dbs)"
jupyter notebook
```

## 2. Choose A Local Study Directory

Keep generated GDS, private YAML files, EMX logs, and run artifacts out of git. The repository ignores `local/`, `runs/`, `*.local.yaml`, `.venv/`, `setup_emx_env.sh`, and `docs/private/`.

Create a local study directory:

```bash
mkdir -p local/dual_core_vco_ring33
```

The examples below use:

```text
local/dual_core_vco_ring33/
  seed.gds
  seed_preview.png
  config.local.yaml
  config.real.local.yaml
  vco_tank_objectives.py
  runs/
```

## 3. Generate The Starting Tank GDS

Generate a square-pixel tank seed, local config, and preview:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/dual_core_vco_ring33/seed.gds \
  --config-output local/dual_core_vco_ring33/config.local.yaml \
  --preview-output local/dual_core_vco_ring33/seed_preview.png \
  --top-cell dual_core_vco_tank_ring33 \
  --run-id dual_core_vco_ring33_fake \
  --include-guard-ring \
  --include-guard-ports
```

Generated files:

- `seed.gds`: the starting layout.
- `config.local.yaml`: a complete `emx-dbs` config using the fake backend.
- `seed_preview.png`: a matplotlib preview of the generated GDS and configured regions.

The default generator emits:

- A rectangular M9 tank loop with north/south feed fingers.
- Port labels `PP`, `PN`, `SP`, and `SN` at the feed edges.
- A continuous M8 equator trace across the tank.
- V8 at the M8/M9 overlap locations.
- Optional guard ring on lower metal with optional `GS` and `GN` labels.

Useful geometry knobs:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/dual_core_vco_ring33/seed_wide.gds \
  --config-output local/dual_core_vco_ring33/config_wide.local.yaml \
  --preview-output local/dual_core_vco_ring33/seed_wide_preview.png \
  --top-cell dual_core_vco_tank_ring33 \
  --run-id dual_core_vco_ring33_wide \
  --core-width-um 330 \
  --core-height-um 330 \
  --pitch-um 10 \
  --m9-ring-width-um 20 \
  --center-gap-um 10 \
  --feed-spacing-um 20 \
  --feed-width-um 5 \
  --feed-length-um 26 \
  --m8-trace-width-um 10 \
  --include-guard-ring \
  --include-guard-ports
```

For an octagonal-pixel reference seed:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/dual_core_vco_ring33/seed_oct.gds \
  --preview-output local/dual_core_vco_ring33/seed_oct_preview.png \
  --pixel-style octagon \
  --corner-patches
```

For DBS, start with square pixels. Corner-overlap bridges are added during candidate export when diagonal same-layer contacts need a small patch at the shared corner.

## 4. Inspect The Generated GDS

Inspect raw GDS contents:

```bash
emx-dbs inspect-raw-gds \
  local/dual_core_vco_ring33/seed.gds \
  --top-cell dual_core_vco_tank_ring33
```

Inspect the same GDS through the YAML config:

```bash
emx-dbs inspect-gds local/dual_core_vco_ring33/config.local.yaml
```

Render a configured input preview:

```bash
emx-dbs preview-input \
  local/dual_core_vco_ring33/config.local.yaml \
  --output local/dual_core_vco_ring33/configured_input.png
```

Review the preview before running EMX. Confirm:

- M9, M8, V8, and guard layers appear in the legend when enabled.
- M8 is continuous across the equator.
- V8 lies only where M8 and M9 overlap.
- Port labels are at the feed edges.
- The guard ring, if enabled, is outside the tank and overlaps the north/south feed edge area in XY.
- Mutable region outlines cover only the area you intend to explore.

## 5. Edit The Local Config

Open `local/dual_core_vco_ring33/config.local.yaml`. The generated config is safe for a fake-backend smoke run. Before serious runs, edit these fields.

Set a local output root:

```yaml
run:
  run_id: dual_core_vco_ring33_fake
  output_root: local/dual_core_vco_ring33/runs
```

Confirm the layout section:

```yaml
layout:
  seed_gds: local/dual_core_vco_ring33/seed.gds
  top_cell: dual_core_vco_tank_ring33
  pixel_size_um: 10.0
  preserve_unconfigured_layers: false
  seed_vias_from_overlap: false
```

Confirm the layer mapping matches your process file:

```yaml
layers:
  m9: [39, 60]
  m8: [38, 40]
  v8: [58, 60]
  guard: [31, 0]
```

The generated mutable regions include M9, M8, and V8 windows, but the fixed regions lock M8 and V8 back to the seed after every mutation. For this tank, the effective DBS layer is M9:

```yaml
mutable_regions:
  - name: m9_core_and_feeds
    layers: [m9]
    bbox_um: [0.0, -26.0, 330.0, 356.0]
  - name: m8_center_trace
    layers: [m8]
    bbox_um: [0.0, 160.0, 330.0, 170.0]
  - name: v8_overlap_trace
    layers: [v8]
    bbox_um: [0.0, 160.0, 330.0, 170.0]
```

Do not remove these fixed regions unless you intentionally want DBS to edit the stack:

```yaml
fixed_regions:
  - name: fixed_m8_center_trace
    layers: [m8]
    bbox_um: [0.0, 160.0, 330.0, 170.0]
  - name: fixed_v8_overlap_trace
    layers: [v8]
    bbox_um: [0.0, 160.0, 330.0, 170.0]
```

The important legality rule is the V8 enclosure rule:

```yaml
connectivity:
  required: []
  forbidden_shorts: []
  vias:
    - name: v8_stack
      via_layer: v8
      lower_layer: m8
      upper_layer: m9
```

This rejects candidates where an active V8 pixel is not backed by active M8 and active M9 at the same coordinate. For this generated tank, broad `forbidden_shorts` are intentionally empty because the current baseline should not open the M8 equator or overconstrain the port terminals. Add terminal-local constraints only after you have a precise rule for the feed geometry.

Corner-overlap support should stay enabled for pixelated M9 exploration:

```yaml
drc:
  min_width_um: 5.0
  min_spacing_um: 5.0
  allow_same_layer_diagonal_contact: true
  corner_overlap_bridge: true
```

## 6. Run The Fake-Backend Smoke Flow

Before involving EMX, make sure the config can be parsed, rasterized, exported, evaluated, and reported:

```bash
emx-dbs validate-env local/dual_core_vco_ring33/config.local.yaml
emx-dbs inspect-gds local/dual_core_vco_ring33/config.local.yaml
emx-dbs preview-input local/dual_core_vco_ring33/config.local.yaml \
  --output local/dual_core_vco_ring33/input_fake.png
emx-dbs rasterize local/dual_core_vco_ring33/config.local.yaml
emx-dbs eval-one local/dual_core_vco_ring33/config.local.yaml
emx-dbs report local/dual_core_vco_ring33/runs/dual_core_vco_ring33_fake --summary-only
```

Expected result:

- `validate-env` reports `backend: fake` and `ok: true`.
- `rasterize` writes `seed/masks.npz` and `seed/layout.png`.
- `eval-one` writes `evaluations/eval_0000/`.
- `report --summary-only` shows one evaluation.

Inspect the first evaluation:

```bash
RUN_DIR=local/dual_core_vco_ring33/runs/dual_core_vco_ring33_fake
find "$RUN_DIR/evaluations/eval_0000" -maxdepth 3 -type f | sort
```

Important files:

```text
evaluations/eval_0000/design/candidate.gds
evaluations/eval_0000/design/layout.png
evaluations/eval_0000/design/masks.npz
evaluations/eval_0000/emx/run_emx.sh
evaluations/eval_0000/emx/stdout.log
evaluations/eval_0000/emx/stderr.log
evaluations/eval_0000/results/result.sNp
evaluations/eval_0000/results/metrics.json
```

## 7. Prepare The Real EMX Environment

Create a local setup script. Do not commit this file.

```bash
cat > setup_emx_env.sh <<'EOF'
#!/usr/bin/env bash
# Source-safe local EMX setup.
# Keep this file free of `set -euo pipefail`; it is sourced by generated run scripts.

# Example site setup. Replace these with your local EMX/Cadence setup.
# module load <cadence-or-emx-module>
# source /path/to/site/cadence_setup.sh
# export CDS_LIC_FILE=<license-server>
# export LM_LICENSE_FILE=<license-server>
# export PATH=/path/to/emx/bin:$PATH

command -v emx >/dev/null
EOF
chmod +x setup_emx_env.sh
```

Test the environment:

```bash
bash -lc 'source setup_emx_env.sh && command -v emx && emx -h | head -n 40'
```

If this fails, fix the local site setup before editing the YAML.

Copy the fake config to a real-EMX config:

```bash
cp local/dual_core_vco_ring33/config.local.yaml \
   local/dual_core_vco_ring33/config.real.local.yaml
```

Edit `local/dual_core_vco_ring33/config.real.local.yaml`:

```yaml
run:
  run_id: dual_core_vco_ring33_real
  output_root: local/dual_core_vco_ring33/runs

emx:
  backend: real
  executable: emx
  proc_file: /absolute/path/to/process_file.proc
  env_script: /absolute/path/to/emx-dbs/setup_emx_env.sh
  key: null
  freq_start_ghz: 9
  freq_stop_ghz: 13
  freq_step_ghz: 1
  timeout_s: 900
  retries: 1
  extra_args: []
  touchstone_glob: "*.s*p"
```

If your process file is encrypted, set the key only in this ignored local YAML:

```yaml
emx:
  key: EMXkey
```

That emits `--key=EMXkey` in each generated `run_emx.sh`.

Confirm the EMX process file maps the GDS layers used by the generated tank:

- M9 top metal: `39/60`.
- M8 lower metal: `38/40`.
- V8 via: `58/60`.
- Optional guard/M1: `31/0`.

If your PDK uses different GDS numbers, the seed GDS and YAML must change together. Editing only the YAML is not enough because the generated polygons would still be on the old layers. The CLI exposes guard-layer overrides; for M9/M8/V8 overrides, use the Python API:

```bash
python - <<'PY'
from pathlib import Path

from emx_dbs.tank_generator import (
    DualCoreVcoTankGeometry,
    generate_dual_core_vco_tank_gds,
    write_dual_core_vco_tank_config,
)

study = Path("local/dual_core_vco_custom_layers")
study.mkdir(parents=True, exist_ok=True)

geom = DualCoreVcoTankGeometry(
    top_cell="dual_core_vco_tank_custom",
    m9_layer=(39, 60),    # replace for your top metal
    m8_layer=(38, 40),    # replace for your adjacent lower metal
    v8_layer=(58, 60),    # replace for your M8/M9 via
    guard_layer=(31, 0),  # replace for your guard layer if used
    include_guard_ring=True,
    include_guard_ports=True,
)

gds = generate_dual_core_vco_tank_gds(study / "seed.gds", geom)
write_dual_core_vco_tank_config(
    study / "config.local.yaml",
    gds,
    geom,
    run_id="dual_core_vco_custom_layers",
    output_root=study / "runs",
)
PY
```

EMX must see the same GDS layer/datatype values that `emx-dbs` exports.

Validate the real setup:

```bash
emx-dbs validate-env local/dual_core_vco_ring33/config.real.local.yaml
emx-dbs inspect-gds local/dual_core_vco_ring33/config.real.local.yaml
emx-dbs preview-input local/dual_core_vco_ring33/config.real.local.yaml \
  --output local/dual_core_vco_ring33/input_real.png
```

`validate-env` should report:

```json
{
  "backend": "real",
  "ok": true,
  "proc_file_exists": true,
  "env_script_exists": true
}
```

## 8. Define The Dual-Core VCO Objective

For this block, a practical first objective is to maximize differential-mode Q at a target design frequency, for both primary and secondary tanks. The scalar FoM should improve only when both sides improve, so use the minimum of primary Q and secondary Q by default.

Because the generated tank is highly symmetric, primary and secondary Q should be close when the geometry, port definitions, and EMX setup are symmetric. The objective below records both Q values plus balance metrics on every evaluation:

- `q_primary`: differential-mode Q from `PP/PN`.
- `q_secondary`: differential-mode Q from `SP/SN`.
- `q_balance_abs`: `abs(q_primary - q_secondary)`.
- `q_balance_rel`: `q_balance_abs / mean(q_primary, q_secondary)`.
- `q_limited`: `min(q_primary, q_secondary)`.

The default FoM is `q_limited`. Set `balance_weight` above zero if you want to explicitly penalize imbalance:

```text
FoM = q_limited - balance_weight * q_balance_abs
```

Keep `balance_weight: 0.0` for the first real runs. Once EMX port order and symmetry behavior are verified, a small value such as `0.05` to `0.2` can discourage asymmetric solutions without dominating Q.

Create a local objective module:

```bash
cat > local/dual_core_vco_ring33/vco_tank_objectives.py <<'PY'
from pathlib import Path

import numpy as np

from emx_dbs.schemas import ObjectiveResult
from emx_dbs.touchstone import read_touchstone


def _nearest_index(freq_hz, target_ghz):
    target_hz = float(target_ghz) * 1e9
    return int(np.argmin(np.abs(np.asarray(freq_hz, dtype=float) - target_hz)))


def _s_to_z(s_matrix, z0):
    s_matrix = np.asarray(s_matrix, dtype=complex)
    ident = np.eye(s_matrix.shape[0], dtype=complex)
    return float(z0) * (ident + s_matrix) @ np.linalg.inv(ident - s_matrix)


def _differential_impedance(z_matrix, positive_port, negative_port):
    p = int(positive_port) - 1
    n = int(negative_port) - 1
    drive = np.zeros(z_matrix.shape[0], dtype=complex)
    drive[p] = 1.0
    drive[n] = -1.0
    voltage = z_matrix @ drive
    return voltage[p] - voltage[n]


def _q_from_impedance(z_diff, min_real_ohm):
    real = float(np.real(z_diff))
    imag = float(np.imag(z_diff))
    if not np.isfinite(real) or not np.isfinite(imag):
        return float("nan")
    if abs(real) < float(min_real_ohm):
        return float("nan")
    return abs(imag / real)


def differential_q_at_target(touchstone_path: Path, metadata: dict, params: dict) -> ObjectiveResult:
    sp = read_touchstone(touchstone_path)
    primary_ports = params.get("primary_ports", [1, 2])
    secondary_ports = params.get("secondary_ports", [3, 4])
    target_freq_ghz = float(params.get("target_freq_ghz", 11.0))
    aggregate = str(params.get("aggregate", "min"))
    min_real_ohm = float(params.get("min_real_ohm", 1.0e-3))
    balance_weight = float(params.get("balance_weight", 0.0))

    needed_ports = max(max(primary_ports), max(secondary_ports))
    if sp.nports < needed_ports:
        return ObjectiveResult(
            fom=-1e30,
            loss=1e30,
            valid=False,
            reason="requires_configured_differential_ports",
            metrics={"nports": sp.nports, "needed_ports": needed_ports},
        )

    idx = _nearest_index(sp.frequency_hz, target_freq_ghz)
    freq_ghz = float(sp.frequency_hz[idx] / 1e9)
    z = _s_to_z(sp.s[idx], sp.z0)

    z_primary = _differential_impedance(z, primary_ports[0], primary_ports[1])
    z_secondary = _differential_impedance(z, secondary_ports[0], secondary_ports[1])
    q_primary = _q_from_impedance(z_primary, min_real_ohm)
    q_secondary = _q_from_impedance(z_secondary, min_real_ohm)
    q_mean = float(np.nanmean([q_primary, q_secondary]))
    q_balance_abs = abs(float(q_primary) - float(q_secondary))
    q_balance_rel = q_balance_abs / max(abs(q_mean), 1.0e-30)

    if aggregate == "mean":
        base_q = q_mean
    else:
        base_q = float(np.nanmin([q_primary, q_secondary]))

    fom = base_q - balance_weight * q_balance_abs

    valid = bool(np.isfinite(fom))
    return ObjectiveResult(
        fom=fom if valid else -1e30,
        loss=-fom if valid else 1e30,
        valid=valid,
        reason=None if valid else "invalid_differential_q",
        metrics={
            "target_freq_ghz": target_freq_ghz,
            "actual_freq_ghz": freq_ghz,
            "q_primary": float(q_primary),
            "q_secondary": float(q_secondary),
            "q_limited": float(np.nanmin([q_primary, q_secondary])),
            "q_mean": q_mean,
            "q_balance_abs": q_balance_abs,
            "q_balance_rel": q_balance_rel,
            "balance_weight": balance_weight,
            "z_primary_real": float(np.real(z_primary)),
            "z_primary_imag": float(np.imag(z_primary)),
            "z_secondary_real": float(np.real(z_secondary)),
            "z_secondary_imag": float(np.imag(z_secondary)),
            "aggregate": aggregate,
        },
    )
PY
```

Expose that local module to Python:

```bash
export PYTHONPATH="$PWD/local/dual_core_vco_ring33:$PYTHONPATH"
```

Edit the objective section in `config.real.local.yaml`:

```yaml
objective:
  plugin: vco_tank_objectives:differential_q_at_target
  params:
    primary_ports: [1, 2]
    secondary_ports: [3, 4]
    target_freq_ghz: 11.0
    aggregate: min
    min_real_ohm: 1.0e-3
    balance_weight: 0.0
```

Port-order convention:

- The generated YAML lists ports in this order: `PP`, `PN`, `SP`, `SN`, then optional guard ports.
- The objective above assumes primary differential ports are `PP/PN` and secondary differential ports are `SP/SN`.
- Check the generated EMX command and EMX output on your site to confirm real Touchstone port ordering before trusting production FoMs.

## 9. Run One Real EMX Evaluation

Run one candidate before launching DBS:

```bash
export PYTHONPATH="$PWD/local/dual_core_vco_ring33:$PYTHONPATH"
emx-dbs eval-one local/dual_core_vco_ring33/config.real.local.yaml
```

Inspect the generated EMX command:

```bash
RUN_DIR=local/dual_core_vco_ring33/runs/dual_core_vco_ring33_real
sed -n '1,220p' "$RUN_DIR/evaluations/eval_0000/emx/run_emx.sh"
```

The command should include:

- `--touchstone`
- `--s-file=<...>/result.sNp`
- `--include-command-line`
- `--verbose=2`
- `--key=<key>` if `emx.key` is set.
- `--internal=PP,5`, `--internal=PN,5`, `--internal=SP,5`, `--internal=SN,5` for 5 um feeds.
- `candidate.gds`, top cell, process file, and frequency points in Hz.

Inspect logs and outputs:

```bash
tail -n 120 "$RUN_DIR/evaluations/eval_0000/emx/stdout.log"
tail -n 120 "$RUN_DIR/evaluations/eval_0000/emx/stderr.log"
find "$RUN_DIR/evaluations/eval_0000/results" -maxdepth 1 -type f -print -exec ls -lh {} \;
cat "$RUN_DIR/evaluations/eval_0000/results/metrics.json"
emx-dbs report "$RUN_DIR" --summary-only
```

Common failures:

- `encrypted data in process file requires --key`: set `emx.key` in the ignored real config.
- `proc_file_exists: false`: fix `emx.proc_file`.
- `env_script_exists: false`: fix `emx.env_script`.
- `missing_touchstone`: EMX ran, but the output file pattern was not found. Check `emx.touchstone_glob`, EMX output flags, and logs.
- `port_not_on_active_pixel`: a port coordinate no longer lands on active metal. Check `ports[].xy_um`, `ports[].edge`, and the preview.
- `via_not_enclosed`: active V8 lacks active M8 or M9 at that coordinate. For the generated tank, this usually means a fixed V8/M9 enclosure rule was edited incorrectly.

## 10. Configure A DBS Run

Once one real evaluation works, create a DBS config:

```bash
cp local/dual_core_vco_ring33/config.real.local.yaml \
   local/dual_core_vco_ring33/config.dbs.local.yaml
```

Edit the run and DBS sections:

```yaml
run:
  run_id: dual_core_vco_ring33_m9_dbs_001
  output_root: local/dual_core_vco_ring33/runs
  resume: true

dbs:
  max_evaluations: 50
  max_rejections_in_a_row: 25
  move_style: probabilistic_independent_layer_flips
  metal_flip_count_weights: [0.65, 0.25, 0.10]
  metal_flip_count_values: [1, 2, 4]
  symmetry_axes: [x, y]
  symmetry_center_um: [165.0, 165.0]
  random_seed: 33
  accept_equal: false
```

The generated ring33 config already sets `symmetry_axes: [x, y]` and `symmetry_center_um: [165.0, 165.0]`. Keep those values unless you intentionally want unconstrained DBS moves.

Symmetry conventions:

- `x` mirrors a flip across the horizontal x-axis line, so `(x, y)` maps to `(x, 2*y0 - y)`.
- `y` mirrors a flip across the vertical y-axis line, so `(x, y)` maps to `(2*x0 - x, y)`.
- `[x, y]` enforces four-way symmetry about `(x0, y0)`.
- `symmetry_center_um` is the physical center `[x0, y0]` in microns.

For the default tank, the center is:

```text
x0 = core_width_um / 2 = 165 um
y0 = core_height_um / 2 = 165 um
```

One sampled DBS move now means one independent symmetry orbit. With `[x, y]`, a requested one-pixel move can flip up to four M9 pixels: the original pixel, its left/right mirror, its top/bottom mirror, and its diagonal mirror. If a mirrored counterpart is fixed or outside the mutable window, that orbit is skipped so fixed M8, V8, port feeds, guard ring, and M9 under V8 remain protected.

Start with a small number of evaluations. Increase `max_evaluations` only after:

- One real EMX evaluation works.
- The objective metrics look physically reasonable.
- Candidate previews preserve M8, V8, feeds, and port locations.
- EMX runtime and license behavior are acceptable.

## 11. Run DBS

For an interactive run:

```bash
export PYTHONPATH="$PWD/local/dual_core_vco_ring33:$PYTHONPATH"
emx-dbs run local/dual_core_vco_ring33/config.dbs.local.yaml
```

For a background run:

```bash
export PYTHONPATH="$PWD/local/dual_core_vco_ring33:$PYTHONPATH"
nohup emx-dbs run local/dual_core_vco_ring33/config.dbs.local.yaml \
  > local/dual_core_vco_ring33/dbs_001.log 2>&1 &
echo $!
```

Monitor progress:

```bash
RUN_DIR=local/dual_core_vco_ring33/runs/dual_core_vco_ring33_m9_dbs_001
tail -f local/dual_core_vco_ring33/dbs_001.log
emx-dbs report "$RUN_DIR" --summary-only
tail -n 20 "$RUN_DIR/events.jsonl"
```

Resume an interrupted run:

```bash
emx-dbs resume local/dual_core_vco_ring33/runs/dual_core_vco_ring33_m9_dbs_001
```

To enforce only left/right symmetry, use:

```yaml
dbs:
  symmetry_axes: [y]
  symmetry_center_um: [165.0, 165.0]
```

To enforce only top/bottom symmetry, use:

```yaml
dbs:
  symmetry_axes: [x]
  symmetry_center_um: [165.0, 165.0]
```

To disable symmetry for an exploratory run:

```yaml
dbs:
  symmetry_axes: []
  symmetry_center_um: null
```

For the VCO tank, `[x, y]` is the recommended production setting because the primary/secondary and left/right halves are intended to be highly symmetric. If Q balance gets worse even with `[x, y]`, inspect port order, feed geometry, EMX meshing, and process-file layer interpretation before trusting the result.

## 12. Understand The Run Directory

Each run writes:

```text
local/dual_core_vco_ring33/runs/<RUN_ID>/
  config.yaml
  state.json
  state_masks.npz
  best.json
  events.jsonl
  history.parquet
  seed/
    masks.npz
    layout.png
  evaluations/
    eval_0000/
      design/
        candidate.gds
        layout.png
        masks.npz
      emx/
        run_emx.sh
        stdout.log
        stderr.log
      results/
        result.sNp
        metrics.json
  best/
    candidate.gds
    layout.png
    metrics.json
  report/
```

The most useful files during development are:

- `seed/layout.png`: baseline rasterized seed.
- `evaluations/eval_XXXX/design/layout.png`: exact candidate sent to EMX.
- `evaluations/eval_XXXX/design/candidate.gds`: exact candidate GDS.
- `evaluations/eval_XXXX/emx/run_emx.sh`: generated solver command.
- `evaluations/eval_XXXX/emx/stderr.log`: EMX errors.
- `evaluations/eval_XXXX/results/result.sNp`: raw S-parameter output.
- `evaluations/eval_XXXX/results/metrics.json`: objective result for that evaluation.
- `events.jsonl`: append-only run ledger.
- `history.parquet`: tabular history generated from events.
- `best/`: best accepted candidate artifacts.

## 13. Generate Reports

Generate the full report:

```bash
RUN_DIR=local/dual_core_vco_ring33/runs/dual_core_vco_ring33_m9_dbs_001
emx-dbs report "$RUN_DIR"
```

Generate a JSON summary only:

```bash
emx-dbs report "$RUN_DIR" --summary-only
```

Inspect the best result:

```bash
cat "$RUN_DIR/best.json"
cat "$RUN_DIR/best/metrics.json"
ls -lh "$RUN_DIR/best"
```

Inspect recent events:

```bash
tail -n 30 "$RUN_DIR/events.jsonl"
```

Read the history table:

```bash
python - <<'PY'
from pathlib import Path
import pandas as pd

run = Path("local/dual_core_vco_ring33/runs/dual_core_vco_ring33_m9_dbs_001")
hist = pd.read_parquet(run / "history.parquet")
cols = [c for c in ["eval_index", "fom", "loss", "accepted", "reason"] if c in hist.columns]
print(hist[cols].tail(20).to_string(index=False))
PY
```

Extract best metrics:

```bash
python - <<'PY'
from pathlib import Path
import json

run = Path("local/dual_core_vco_ring33/runs/dual_core_vco_ring33_m9_dbs_001")
best = json.loads((run / "best.json").read_text())
metrics = json.loads((run / "best" / "metrics.json").read_text())

print("best_eval:", best.get("best_eval"))
print("best_fom:", best.get("best_fom"))
print(json.dumps(metrics.get("metrics", metrics), indent=2, sort_keys=True))
PY
```

Copy out the best GDS for downstream layout review:

```bash
cp "$RUN_DIR/best/candidate.gds" local/dual_core_vco_ring33/best_candidate.gds
cp "$RUN_DIR/best/layout.png" local/dual_core_vco_ring33/best_candidate.png
```

## 14. Post-Process Touchstone Data

The objective writes the target-frequency Q metrics into `metrics.json`. For a deeper check, inspect the Touchstone file directly:

```bash
python - <<'PY'
from pathlib import Path
import numpy as np

from emx_dbs.touchstone import read_touchstone

run = Path("local/dual_core_vco_ring33/runs/dual_core_vco_ring33_m9_dbs_001")
best_eval = "eval_0000"  # replace with the best eval from best.json if needed
touchstone = next((run / "evaluations" / best_eval / "results").glob("*.s*p"))
sp = read_touchstone(touchstone)

print("touchstone:", touchstone)
print("nports:", sp.nports)
print("freq_ghz:", sp.frequency_hz / 1e9)
print("|S11|:", np.abs(sp.s[:, 0, 0]))
PY
```

For production analysis, compare:

- Primary and secondary differential Q at the target frequency.
- Absolute and relative Q balance between primary and secondary.
- Differential inductance at the target frequency.
- Port ordering and sign convention.
- Self-resonance relative to the design band.
- EMX convergence warnings.
- Geometry legality in layout viewer.
- Whether the best candidate preserves desired symmetry.

## 15. Export A Square-Pixel Seed Without Running DBS

If you want a clean square-pixel GDS representation of the configured input:

```bash
emx-dbs export-square-seed \
  local/dual_core_vco_ring33/config.real.local.yaml \
  --output local/dual_core_vco_ring33/square_seed.gds \
  --preview-output local/dual_core_vco_ring33/square_seed.png
```

If an imported seed has M8/M9 overlap but omits V8, enable via synthesis only for that conversion:

```bash
emx-dbs export-square-seed \
  local/dual_core_vco_ring33/config.real.local.yaml \
  --output local/dual_core_vco_ring33/square_seed_with_v8.gds \
  --preview-output local/dual_core_vco_ring33/square_seed_with_v8.png \
  --synthesize-vias-from-overlap
```

Do not use via synthesis blindly on production layouts. Confirm the generated V8 mask matches the process intent.

## 16. Notebook Workflow

Use the public notebooks when you want interactive visual checks or symmetry-aware DBS scaffolding:

```bash
python -m pip install -e ".[dev,notebook]"
python -m ipykernel install --user --name emx-dbs --display-name "Python 3 (emx-dbs)"
jupyter notebook notebooks/dual_core_vco_tank_end_to_end.ipynb
```

The VCO tank notebook covers:

- Parametric tank generation.
- Matplotlib layer visualization.
- Guard ring visualization.
- Port labels and feed locations.
- M9-only DBS-style trial candidates.
- Corner-overlap bridge visualization.
- X/y symmetry scaffolding.
- Objective and config skeletons for EMX-backed DBS.

The GDS import notebook covers:

- Importing and inspecting an existing GDS.
- Viewing raw GDS layers.
- Generating a custom tank GDS.
- Exporting candidate GDS.
- EMX port naming conventions.
- Mapping configured layers to process-file layers and EMX CLI commands.

## 17. Troubleshooting Checklist

Use this sequence when something fails.

1. Confirm the venv is active:

   ```bash
   which python
   python --version
   which emx-dbs
   ```

2. Confirm installation and tests:

   ```bash
   python -m pip install -e ".[dev]"
   pytest -q
   ```

3. Confirm the config parses:

   ```bash
   emx-dbs inspect-gds local/dual_core_vco_ring33/config.dbs.local.yaml
   ```

4. Confirm previews look right:

   ```bash
   emx-dbs preview-input local/dual_core_vco_ring33/config.dbs.local.yaml \
     --output local/dual_core_vco_ring33/debug_preview.png
   ```

5. Confirm EMX environment:

   ```bash
   emx-dbs validate-env local/dual_core_vco_ring33/config.dbs.local.yaml
   bash -lc 'source setup_emx_env.sh && command -v emx'
   ```

6. Confirm the generated EMX command:

   ```bash
   sed -n '1,220p' "$RUN_DIR/evaluations/eval_0000/emx/run_emx.sh"
   ```

7. Confirm EMX logs:

   ```bash
   tail -n 120 "$RUN_DIR/evaluations/eval_0000/emx/stdout.log"
   tail -n 120 "$RUN_DIR/evaluations/eval_0000/emx/stderr.log"
   ```

8. Confirm objective import:

   ```bash
   export PYTHONPATH="$PWD/local/dual_core_vco_ring33:$PYTHONPATH"
   python - <<'PY'
   from vco_tank_objectives import differential_q_at_target
   print(differential_q_at_target)
   PY
   ```

9. Confirm legality failures:

   ```bash
   tail -n 20 "$RUN_DIR/events.jsonl"
   cat "$RUN_DIR/evaluations/eval_0000/results/metrics.json"
   ```

Common fixes:

- `pytest: command not found`: use `python -m pytest -q` or reinstall `".[dev]"`.
- `No matching distribution found for setuptools>=61`: recreate the venv with Python 3.8+.
- `No mutable pixels are available for DBS moves`: check `mutable_regions`, `fixed_regions`, and `layers`.
- `port_not_on_active_pixel`: move the port coordinate or set the correct `edge`.
- `via_not_enclosed`: restore fixed M8/V8/M9 enclosure regions or adjust V8 geometry.
- EMX requires `--key`: set `emx.key` in an ignored local config.
- The center M8 equator is opened: restore the generated M8 fixed region and regenerate candidates.
- The best GDS lacks expected layers: check `layout.preserve_unconfigured_layers` and the `layers` map.

## 18. What To Commit

Commit reusable source, docs, tests, and public notebooks.

Do not commit:

- `.venv/`
- `local/`
- `runs/`
- `*.local.yaml`
- `setup_emx_env.sh`
- process files
- license values
- host-specific paths
- private notebooks under `docs/private/`

For public collaboration, the clean path is:

```bash
git status -sb
pytest -q
git add README.md docs/dual_core_vco_end_to_end.md docs/dual_core_vco_tanks.md
git commit -m "Add dual-core VCO tank end-to-end guide"
git push
```

## 19. Minimal Command Recap

From a clean checkout:

```bash
git clone https://github.com/austinrosh/emx-dbs.git
cd emx-dbs
python3.8 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
pytest -q

mkdir -p local/dual_core_vco_ring33
emx-dbs generate-dual-core-vco-tank \
  --output local/dual_core_vco_ring33/seed.gds \
  --config-output local/dual_core_vco_ring33/config.local.yaml \
  --preview-output local/dual_core_vco_ring33/seed_preview.png \
  --top-cell dual_core_vco_tank_ring33 \
  --run-id dual_core_vco_ring33_fake \
  --include-guard-ring \
  --include-guard-ports

emx-dbs preview-input local/dual_core_vco_ring33/config.local.yaml \
  --output local/dual_core_vco_ring33/input_fake.png
emx-dbs eval-one local/dual_core_vco_ring33/config.local.yaml
emx-dbs report local/dual_core_vco_ring33/runs/dual_core_vco_ring33_fake --summary-only

cp local/dual_core_vco_ring33/config.local.yaml \
   local/dual_core_vco_ring33/config.real.local.yaml
# Edit config.real.local.yaml: output_root, real EMX paths, process file, key, objective, DBS counts.

export PYTHONPATH="$PWD/local/dual_core_vco_ring33:$PYTHONPATH"
emx-dbs validate-env local/dual_core_vco_ring33/config.real.local.yaml
emx-dbs eval-one local/dual_core_vco_ring33/config.real.local.yaml
emx-dbs run local/dual_core_vco_ring33/config.real.local.yaml
emx-dbs report local/dual_core_vco_ring33/runs/<RUN_ID>
```
