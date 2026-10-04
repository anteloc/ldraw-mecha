"""Analysis-only treatment of rounded LDraw placement frames.

pyldraw3 scales connector profiles with their placements. Even tiny anisotropic
scale from rounded rotation coefficients can invalidate axle metadata. Project
near-rigid frames onto the nearest orthogonal matrix using NumPy (also used by
pyldraw3). Never rewrite the source manifest, translations or GLB transforms.
Reflections retain their handedness; substantial scale/shear stays unsupported.
"""

from collections import Counter

import numpy as np

# Dimensionless maximum singular-value deviation from one. This accommodates
# common three-decimal rotations, but is an explicit assumption, not a proof
# that a small intentional scale was rounding. Raw mode permits comparison.
ROUNDING_LIMIT = 0.002
EXACT_LIMIT = 1e-8


def analysis_placement(node, *, normalize=True):
    world = np.array(node["world"], dtype=float)
    if world.shape != (4, 4) or not np.isfinite(world).all():
        raise ValueError(f"Invalid placement: {node['id']}")
    original = world[:3, :3].copy()
    u, values, vt = np.linalg.svd(original)
    error = float(np.max(np.abs(values - 1)))
    status = "unchanged"
    if error > ROUNDING_LIMIT:
        status = "unsupported"
    elif error > EXACT_LIMIT:
        status = "normalized" if normalize else "raw_near_rigid"
        if normalize:
            # U @ Vt preserves determinant sign; forcing +1 would mirror parts.
            world[:3, :3] = u @ vt
    return world.tolist(), dict(
        id=node["id"],
        status=status,
        reflected=bool(np.linalg.det(original) < 0),
        max_scale_error=error,
        max_coefficient_change=float(np.max(np.abs(world[:3, :3] - original))),
    )


def placement_report(records):
    return dict(
        policy="Nearest orthogonal analysis frame within rounding_limit; source translations and handedness preserved",
        rounding_limit=ROUNDING_LIMIT,
        counts=dict(Counter(r["status"] for r in records)),
        affected=[r for r in records if r["status"] != "unchanged" or r["reflected"]],
    )
