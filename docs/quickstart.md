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

## Fake Solver Smoke Test

```bash
emx-dbs validate-env examples/generic_nport/config.yaml
emx-dbs inspect-gds examples/generic_nport/config.yaml
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

## Resume

```bash
emx-dbs resume runs/generic_nport_demo
```

Resume uses `runs/RUN_ID/config.yaml`, `state.json`, and `state_masks.npz`.
