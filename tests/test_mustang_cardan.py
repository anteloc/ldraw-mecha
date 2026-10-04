import importlib.util
import math
from pathlib import Path

import pytest

from ldraw_mechanisms import plan
from ldraw_mechanisms.math3d import unit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_mustang_rig.py"
spec = importlib.util.spec_from_file_location("build_mustang_rig", SCRIPT)
rig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rig)


def shafts(bend):
    d_in = [0.0, math.sin(bend / 2), -math.cos(bend / 2)]
    d_out = [0.0, -math.sin(bend / 2), -math.cos(bend / 2)]
    return unit(d_in), unit(d_out)


@pytest.mark.parametrize("bend", [0.2, 0.51, 0.9])
def test_cardan_cross_is_verified_and_nonuniform(bend):
    d_in, d_out = shafts(bend)
    signals = {}
    rig.cardan_cross(signals, d_in, d_out, [1.0, 0.0, 0.0])
    controls = {"a": dict(default=0.0, min=-1.3, max=1.3, unit="radian", description="x")}
    signals["column_in"] = dict(expression="clamp(v,-1.3,1.3)", variables=dict(v="control:a"))
    cos_beta = sum(x * y for x, y in zip(d_in, d_out))
    signals["pinion_fwd"] = dict(
        expression=f"atan2({cos_beta!r}*sin(s),cos(s))", variables=dict(s="signal:column_in")
    )
    p = dict(controls=controls, signals=signals)
    # Evaluate through the portable expression evaluator with nonzero input.
    base = dict(version=1, name="uj", status="draft", source=dict(nodes=[]), bodies={}, anchors={}, checks=[], notes=[])
    result = plan.evaluate(dict(base, **p), {"a": 0.8})["signals"]
    assert result["pinion_fwd"] == pytest.approx(math.atan2(cos_beta * math.sin(0.8), math.cos(0.8)))
    assert abs(result["cross_angle"]) > 1e-3
    assert result["pinion_fwd"] != pytest.approx(0.8, abs=1e-3)


def test_cardan_rejects_a_pivot_not_normal_to_the_bend_plane():
    d_in, d_out = shafts(0.5)
    with pytest.raises(ValueError):
        rig.cardan_cross({}, d_in, d_out, unit([1.0, 0.3, 0.0]))
