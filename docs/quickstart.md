# Quickstart

This project is intentionally standalone. It imports a configured GDS seed, rasterizes configured editable windows into pixel masks, mutates those masks with DBS, exports candidate GDS files, runs an EM solver backend, parses Touchstone, scores a plugin objective, and persists restartable run state.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python scripts/make_example_gds.py
```

For notebook workflows, install the optional notebook extra and register the kernel:

```bash
python -m pip install -e ".[dev,notebook]"
python -m ipykernel install --user --name emx-dbs --display-name "Python 3 (emx-dbs)"
jupyter notebook
```

## Fake Solver Smoke Test

```bash
emx-dbs validate-env examples/generic_nport/config.yaml
emx-dbs inspect-gds examples/generic_nport/config.yaml
emx-dbs preview-input examples/generic_nport/config.yaml
emx-dbs rasterize examples/generic_nport/config.yaml
emx-dbs eval-one examples/generic_nport/config.yaml
emx-dbs run examples/generic_nport/config.yaml
emx-dbs report runs/generic_nport_demo
```

The fake backend writes synthetic S-parameters and exercises the full artifact path without Cadence/EMX.

## Real EMX

Set:

```yaml
emx:
  backend: real
  executable: /path/to/emx
  proc_file: /path/to/process.proc
  env_script: /path/to/setup_emx.sh
```

The generated `evaluations/eval_XXXX/emx/run_emx.sh` is deliberately explicit. If your EMX site wrapper uses different command-line flags, put stable setup in `emx.env_script` and site-specific flags in `emx.extra_args`, or adjust `emx_dbs.emx_runner._write_emx_script`.

For collaborator-facing setup instructions, see `docs/setup_for_emx.md`. Keep site hostnames, license servers, internal paths, and private process-file locations in ignored local docs or local YAML files.

To inspect a candidate seed before running EMX:

```bash
emx-dbs inspect-raw-gds path/to/layout.gds --top-cell TOP
emx-dbs preview-gds path/to/layout.gds --top-cell TOP --output local/previews/input.png
emx-dbs preview-input my_study.local.yaml --output local/previews/configured_input.png
```

To convert an input seed into the same square-pixel/corner-overlap representation that `emx-dbs` will optimize:

```bash
emx-dbs export-square-seed my_study.local.yaml \
  --output local/square_seed.gds \
  --preview-output local/square_seed.png
```

To generate a new dual-core VCO tank seed from parameters:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/tanks/ring33_square.gds \
  --config-output local/tanks/ring33_square.local.yaml \
  --preview-output local/tanks/ring33_square.png
```

Add `--include-guard-ring` when the seed should include a fixed lower-metal guard ring in exported candidate GDS. Use `--include-guard-ports` when EMX should see north/south guard reference labels. The included N16-oriented generator defaults to M1 GDS `31/0`; override `--guard-layer`/`--guard-datatype` if your PDK uses a different M1 mapping.

See `docs/dual_core_vco_tanks.md` for the available geometry parameters.

The notebook `notebooks/dual_core_vco_tank_end_to_end.ipynb` walks through the same tank flow with clean visualization, M9-only DBS-style corner-overlap trials, export, objective-plugin scaffolding, and symmetry-aware DBS loop scaffolding.

## Resume

```bash
emx-dbs resume runs/generic_nport_demo
```

Resume uses `runs/RUN_ID/config.yaml`, `state.json`, and `state_masks.npz`.
