# Dual-Core VCO Tank Seeds

`emx-dbs` includes a small parametric generator for the dual-core VCO tank family used as the first target structure class.

For an executable walkthrough with clean matplotlib visualizations, M9-only DBS-style corner-overlap trials, parameter sweeps, export, a custom objective skeleton, and a symmetry-aware optimization-loop skeleton, open `notebooks/dual_core_vco_tank_end_to_end.ipynb`.

The default generator emits an N16-oriented square-pixel seed:

- `m9`: GDS `39/60`
- `m8`: GDS `38/40`
- `v8`: GDS `58/60`
- ports: `PP`, `PN`, `SP`, `SN`
- port labels are placed on the outer feed edges
- top cell: `dual_core_vco_tank`

Generated configs make only `m9` mutable. The `m8` center trace and `v8` overlap trace remain represented in the rasterized masks and candidate GDS, but they are marked fixed so DBS cannot delete the lower stack while exploring M9 pixels. The M9 pixels directly under active V8 contacts are also fixed on, preserving via enclosure by construction.

Generate a default seed, local config, and preview:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/tanks/ring33_square.gds \
  --config-output local/tanks/ring33_square.local.yaml \
  --preview-output local/tanks/ring33_square.png
```

Inspect and preview the generated seed:

```bash
emx-dbs inspect-raw-gds local/tanks/ring33_square.gds --top-cell dual_core_vco_tank
emx-dbs inspect-gds local/tanks/ring33_square.local.yaml
emx-dbs preview-input local/tanks/ring33_square.local.yaml --output local/tanks/ring33_square_configured.png
```

The generated config is intentionally local. It uses the fake backend by default; for r8cad, edit the `emx` section to use the local N16 proc file, setup script, and key.

## Parameter Sweeps

Common geometry options:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/tanks/wide_ring.gds \
  --config-output local/tanks/wide_ring.local.yaml \
  --preview-output local/tanks/wide_ring.png \
  --core-width-um 350 \
  --core-height-um 350 \
  --pitch-um 10 \
  --m9-ring-width-um 30 \
  --center-gap-um 10 \
  --feed-spacing-um 20 \
  --feed-width-um 5 \
  --feed-length-um 26 \
  --m8-trace-width-um 10
```

To create an octagonal-pixel reference closer to older seed files:

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/tanks/ring33_oct.gds \
  --preview-output local/tanks/ring33_oct.png \
  --pixel-style octagon \
  --corner-patches
```

Add `--include-guard-ring` only when you intentionally want the extra fixed lower-metal guard frame. The default seed emits only `m9`, `m8`, and `v8`.

## Guard Ring

Use `--include-guard-ring` to add a fixed guard ring around the tank and feed edges. The default guard layer is N16 M1 GDS `31/0`, matching the included N16 process file's `metal1 = l31t0 + ...` mapping. Override `--guard-layer` and `--guard-datatype` for a different PDK's M1 mapping. The generated config maps it as logical layer `guard` but leaves it out of mutable regions, so candidate GDS exports preserve the guard ring without letting DBS edit it.

The north and south guard bars overlap the M9 feed edges by `--guard-feed-overlap-um` (`5 um` by default). This puts the guard metal under the launch labels in XY, which makes the overlap visible in previews and gives EMX a consistent reference location if you enable guard ports.

```bash
emx-dbs generate-dual-core-vco-tank \
  --output local/tanks/ring33_guard.gds \
  --config-output local/tanks/ring33_guard.local.yaml \
  --preview-output local/tanks/ring33_guard.png \
  --include-guard-ring \
  --guard-layer 31 \
  --guard-datatype 0 \
  --guard-offset-um 26 \
  --guard-width-um 10 \
  --guard-feed-overlap-um 5
```

Add `--include-guard-ports` when you want the generated GDS/config to include guard reference labels `GS` and `GN` on the south and north guard bars. These are static reference ports; they do not make the guard layer mutable.

`--include-ground-ring` remains accepted as a compatibility alias, but new configs should use `--include-guard-ring`.

## Corner Overlap

Generated configs enable `drc.allow_same_layer_diagonal_contact` and `drc.corner_overlap_bridge` by default. With both flags on, diagonal-only same-layer pixel contacts are considered connected during legality checks, and candidate GDS export adds a DRC-sized diamond patch at the shared pixel corner. The layout preview draws these patches as orange corner-overlap bridge markers on top of the pixel grid. The tank notebook includes deterministic M9-only trial candidates with M8 and V8 held fixed, plus layer legends, so the bridge patches and lower-stack context are easy to inspect.

## DBS Use

The generated square seed is meant to be used directly by the optimizer:

```bash
emx-dbs validate-env local/tanks/ring33_square.local.yaml
emx-dbs rasterize local/tanks/ring33_square.local.yaml
emx-dbs eval-one local/tanks/ring33_square.local.yaml
```

For real N16 EMX runs, keep process paths, setup scripts, and process keys in ignored local YAML files.
