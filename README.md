# emx-dbs

`emx-dbs` is a standalone Python tool for direct-binary-search optimization of passive EM layouts from arbitrary GDS seeds. 

The YAML configuration is the source of physical and electrical intent: it defines editable layers and windows, fixed regions, ports, required connectivity, forbidden shorts, EMX setup, DBS move policy, and the objective plugin.

## Install From GitHub

Use Python 3.8 or newer. Check this before creating the virtual environment:

```bash
python3 --version
```

If `python3` is older than 3.8, load or select a newer interpreter first, for example `python3.8`, `python3.10`, `python3.11`, a site module, or a conda environment. A failure like `No matching distribution found for setuptools>=61` usually means the venv was created with an old Python such as 3.6.

For normal collaborator use, clone the repository so examples, docs, and scripts are available:

```bash
git clone https://github.com/austinrosh/emx-dbs.git
cd emx-dbs

python3.8 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

For CLI-only use without examples:

```bash
python3.8 -m venv emx-dbs-venv
source emx-dbs-venv/bin/activate
python -m pip install -U pip
python -m pip install "emx-dbs @ git+https://github.com/austinrosh/emx-dbs.git"
```

Run the tests after a source checkout:

```bash
pytest -q
```

To use the example notebooks from the same virtual environment:

```bash
python -m pip install -e ".[dev,notebook]"
python -m ipykernel install --user --name emx-dbs --display-name "Python 3 (emx-dbs)"
jupyter notebook
```

## Quick Start With The Fake Solver

```bash
emx-dbs validate-env examples/generic_nport/config.yaml
emx-dbs inspect-gds examples/generic_nport/config.yaml
emx-dbs eval-one examples/generic_nport/config.yaml
emx-dbs run examples/generic_nport/config.yaml
emx-dbs report runs/generic_nport_demo
```

The bundled examples use the fake EMX backend by default so the end-to-end flow can be tested without Cadence/EMX. Set `emx.backend: real` and provide valid local EMX paths for actual solver runs.

## Copy To An EMX Server With rsync

If the solver host cannot clone from GitHub, copy the checkout from your workstation:

```bash
rsync -av \
  --exclude .git \
  --exclude .venv \
  --exclude runs \
  --exclude __pycache__ \
  ./ <user>@<emx-host>:<workspace-dir>/emx-dbs/
```

Then set up the server-side virtual environment:

```bash
ssh <user>@<emx-host>
cd <workspace-dir>/emx-dbs

python3.8 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -U pip
python -m pip install -e ".[dev]"
pytest -q
```

If the EMX server has no internet access, build or copy a local wheelhouse and install from it:

```bash
python -m pip install --no-index --find-links <wheelhouse-dir> -e ".[dev]"
```

If the EMX server only has an older system Python, create a user-space Python 3.8+ environment with conda, micromamba, Miniforge, or your site's module system before running the venv/install commands. Python 3.6 is not supported.

## Real EMX Setup

Create a local, untracked setup script for site modules, paths, and license variables:

```bash
cat > setup_emx_env.sh <<'EOF'
#!/usr/bin/env bash
# Source-safe local setup. Avoid `set -euo pipefail` here because this file
# may be sourced by interactive shells and generated EMX run scripts.
# module load <cadence-or-emx-module>
# source <site-cadence-setup.sh>
# export CDS_LIC_FILE=<license-server>
# export LM_LICENSE_FILE=<license-server>
EOF
chmod +x setup_emx_env.sh
```

Create a private local study config from an example:

```bash
cp examples/generic_nport/config.yaml my_study.local.yaml
```

Set the real backend and local EMX paths:

```yaml
emx:
  backend: real
  executable: emx
  proc_file: <absolute-path-to-process-file.proc>
  env_script: <absolute-path-to-setup_emx_env.sh>
```

If your process file is encrypted, put the process key only in an ignored local config:

```yaml
emx:
  key: <process-file-key>  # emits --key=<process-file-key>
```

Validate and run one candidate before launching a long DBS job:

```bash
emx-dbs validate-env my_study.local.yaml
emx-dbs inspect-gds my_study.local.yaml
emx-dbs preview-input my_study.local.yaml
emx-dbs rasterize my_study.local.yaml
emx-dbs eval-one my_study.local.yaml
```

Useful GDS review/conversion helpers:

```bash
emx-dbs inspect-raw-gds path/to/layout.gds --top-cell TOP
emx-dbs preview-gds path/to/layout.gds --top-cell TOP --output local/previews/input.png
emx-dbs export-square-seed my_study.local.yaml --output local/square_seed.gds --preview-output local/square_seed.png
```

For the first supported structure family, generate a dual-core VCO tank seed:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/tanks/ring33_square.gds \
  --config-output local/tanks/ring33_square.local.yaml \
  --preview-output local/tanks/ring33_square.png
```

Use `--include-guard-ring` to add a fixed lower-metal guard ring around the generated tank and feeds. For the included N16-oriented generator, the guard defaults to M1 GDS `31/0`, overlaps the north/south M9 feed edges by `5 um`, and can add optional `GS`/`GN` guard reference labels with `--include-guard-ports`. Override `--guard-layer`/`--guard-datatype` when your PDK uses a different M1 mapping.

For an end-to-end notebook covering generation, clean matplotlib visualization, M9-only DBS-style corner-overlap trials, export, objective skeletons, and symmetry-aware DBS loop scaffolding, open `notebooks/dual_core_vco_tank_end_to_end.ipynb`.

For a background run:

```bash
nohup emx-dbs run my_study.local.yaml > /tmp/emx_dbs_run.log 2>&1 & echo $!
emx-dbs report runs/<RUN_ID> --summary-only
emx-dbs resume runs/<RUN_ID>
```

## What Not To Commit

The repository is configured to ignore virtual environments, run artifacts, local study configs, local setup scripts, logs, and private site notes. Keep these files local:

- `.venv/`
- `runs/`
- `*.local.yaml`
- `setup_emx_env.sh`
- `docs/private/`
- process files, license values, and site-specific host paths

See:

- GitHub: https://github.com/austinrosh/emx-dbs
- `docs/quickstart.md`
- `docs/configuration_reference.md`
- `docs/setup_for_emx.md`
- `docs/dual_core_vco_tanks.md`
- `notebooks/dual_core_vco_tank_end_to_end.ipynb`
