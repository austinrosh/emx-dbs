# Setup For A Local EMX Environment

This v1 workflow runs `emx-dbs` directly on the machine that has access to EMX, the process files, and the required license environment. Remote job orchestration is intentionally out of scope.

## 1. Log Into The EMX Host

Use the login method for your lab or company environment:

```bash
ssh <emx-host>
cd <workspace-dir>
```

Examples of `<workspace-dir>` include a project scratch area, shared simulation workspace, or local disk with enough room for GDS, EMX logs, Touchstone results, and run artifacts.

## 2. Clone Or Copy The Project

From GitHub:

```bash
git clone https://github.com/austinrosh/emx-dbs.git emx-dbs
cd emx-dbs
```

If the solver host cannot clone from GitHub, copy a local checkout with `rsync`:

```bash
rsync -av \
  --exclude .git \
  --exclude .venv \
  --exclude runs \
  --exclude __pycache__ \
  ./ <user>@<emx-host>:<workspace-dir>/emx-dbs/
```

Then log into the host:

```bash
ssh <user>@<emx-host>
cd <workspace-dir>/emx-dbs
```

## 3. Create A Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## 4. Verify EMX And Process Files

Find the EMX executable and the process file used for your technology:

```bash
which emx
ls -l <process-file.proc>
```

If EMX requires modules, license variables, or site shell initialization, put those commands in a local wrapper that is not committed:

```bash
cat > setup_emx_env.sh <<'EOF'
#!/usr/bin/env bash
# module load <cadence-or-emx-module>
# export CDS_LIC_FILE=<license-server>
# export LM_LICENSE_FILE=<license-server>
EOF
chmod +x setup_emx_env.sh
```

Reference that wrapper from your study config:

```yaml
emx:
  backend: real
  executable: emx
  proc_file: <absolute-path-to-process-file.proc>
  env_script: <absolute-path-to-setup_emx_env.sh>
```

Keep real hostnames, internal process paths, and license server values in local files covered by `.gitignore`.

## 5. Create A Study Config

Start from an example:

```bash
cp examples/generic_nport/config.yaml my_study.local.yaml
```

Edit at least:

- `run.run_id`
- `layout.seed_gds`
- `layout.top_cell`
- `layers`
- `mutable_regions`
- `fixed_regions`
- `ports`
- `connectivity`
- `drc`
- `emx.backend`
- `emx.proc_file`
- `objective.plugin`

For real solver runs:

```yaml
emx:
  backend: real
```

## 6. Validate The Study

```bash
emx-dbs validate-env my_study.local.yaml
emx-dbs inspect-gds my_study.local.yaml
emx-dbs rasterize my_study.local.yaml
```

## 7. Run One EMX Evaluation

```bash
emx-dbs eval-one my_study.local.yaml
```

Inspect the generated command and logs:

```bash
sed -n '1,160p' runs/<RUN_ID>/evaluations/eval_0000/emx/run_emx.sh
tail -n 80 runs/<RUN_ID>/evaluations/eval_0000/emx/stdout.log
tail -n 80 runs/<RUN_ID>/evaluations/eval_0000/emx/stderr.log
```

If your site wrapper uses different EMX flags, configure `emx.extra_args`, use `emx.env_script`, or adapt the command template in `emx_dbs.emx_runner`.

## 8. Launch A Background DBS Run

With `nohup`:

```bash
nohup emx-dbs run my_study.local.yaml > /tmp/emx_dbs_run.log 2>&1 & echo $!
```

With `tmux`:

```bash
tmux new -s emx-dbs
source .venv/bin/activate
emx-dbs run my_study.local.yaml
```

With `screen`:

```bash
screen -S emx-dbs
source .venv/bin/activate
emx-dbs run my_study.local.yaml
```

## 9. Monitor Progress

```bash
emx-dbs report runs/<RUN_ID> --summary-only
tail -n 80 /tmp/emx_dbs_run.log
```

A simple local helper is fine, but keep it untracked if it contains site-specific paths:

```bash
cat > monitor_progress.local.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
RUN_DIR="${1:-runs/<RUN_ID>}"
emx-dbs report "$RUN_DIR" --summary-only
tail -n 80 /tmp/emx_dbs_run.log
EOF
chmod +x monitor_progress.local.sh
```

## 10. Resume

```bash
emx-dbs resume runs/<RUN_ID>
```

Resume uses the copied `runs/<RUN_ID>/config.yaml`, `state.json`, and `state_masks.npz`.
