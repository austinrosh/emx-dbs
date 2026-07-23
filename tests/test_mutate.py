from __future__ import annotations

import numpy as np

from emx_dbs.masks import LayerGrid, MaskSet
from emx_dbs.mutate import sample_flip_group
from emx_dbs.schemas import DBSConfig


def _maskset(shape=(4, 4), mutable=None):
    mask = np.zeros(shape, dtype=bool)
    mutable_mask = np.ones(shape, dtype=bool) if mutable is None else mutable
    return MaskSet(
        masks={"m9": mask},
        mutable_masks={"m9": mutable_mask},
        fixed_masks={"m9": np.zeros(shape, dtype=bool)},
        fixed_region_masks={"m9": np.zeros(shape, dtype=bool)},
        grids={"m9": LayerGrid("m9", (0.0, 0.0, 40.0, 40.0), 10.0, shape)},
    )


def test_sample_flip_group_expands_xy_symmetry_orbit():
    dbs = DBSConfig(
        metal_flip_count_values=[1],
        metal_flip_count_weights=[1.0],
        symmetry_axes=["x", "y"],
        symmetry_center_um=(20.0, 20.0),
    )

    flips = sample_flip_group(_maskset(), dbs, np.random.default_rng(1))

    assert len(flips) == 4
    assert set(flips) in (
        {("m9", 0, 0), ("m9", 0, 3), ("m9", 3, 0), ("m9", 3, 3)},
        {("m9", 0, 1), ("m9", 0, 2), ("m9", 3, 1), ("m9", 3, 2)},
        {("m9", 1, 0), ("m9", 1, 3), ("m9", 2, 0), ("m9", 2, 3)},
        {("m9", 1, 1), ("m9", 1, 2), ("m9", 2, 1), ("m9", 2, 2)},
    )


def test_sample_flip_group_rejects_incomplete_symmetry_orbits():
    mutable = np.ones((4, 4), dtype=bool)
    mutable[3, 3] = False
    maskset = _maskset(mutable=mutable)
    dbs = DBSConfig(
        metal_flip_count_values=[1],
        metal_flip_count_weights=[1.0],
        symmetry_axes=["x", "y"],
        symmetry_center_um=(20.0, 20.0),
    )

    for _ in range(20):
        flips = sample_flip_group(maskset, dbs, np.random.default_rng(_))
        assert ("m9", 0, 0) not in flips
        assert ("m9", 3, 3) not in flips
