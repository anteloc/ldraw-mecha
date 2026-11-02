"""Body boundaries must sit on joints: contacts elsewhere reveal misplaced parts."""

import pytest

from ldraw_mechanisms import mechanisms, plan, workflow
from ldraw_mechanisms.audit import boundary
from ldraw_mechanisms.source import Document

# A slewing turret (vertical axis through x=0) carrying a hinged boom (axis X at
# y=-40) and a telescope sliding along Z; a fixed bracket rides on the boom.
BODIES = {
    "turret": dict(kind="revolute", instances=["10", "11"], origin=[0, 0, 0], axis=[0, 1, 0]),
    "boom": dict(kind="revolute", instances=["20"], origin=[0, -40, 0], axis=[1, 0, 0], parent="turret"),
    "bracket": dict(kind="fixed", instances=["21"], origin=[0, 0, 0], axis=[1, 0, 0], parent="boom"),
    "tele": dict(kind="prismatic", instances=["30"], origin=[0, -40, 0], axis=[0, 0, 1], parent="boom"),
    "rod": dict(kind="rod", instances=["40"], start="s", end="e", x_hint=[1, 0, 0]),
}


def contact(a, b, kinds=("pin", "pin_hole"), position=(0, 0, 0), axis=(0, 1, 0)):
    return dict(
        a=a,
        b=b,
        kind="contact",
        status="candidate",
        evidence="fixture contact",
        measurements=dict(
            first_kind=kinds[0], second_kind=kinds[1], position=list(position), axis=list(axis)
        ),
    )


def flagged(*contacts, declared=()):
    found = boundary(BODIES, {str(i): c for i, c in enumerate(contacts)}, declared)
    return [(g["reason"], g["bodies"], g["pairs"]) for g in found["flagged"]], found["info"]


def test_joint_contacts_and_rigid_neighbours_pass():
    assert flagged(
        contact("0", "10", position=(0, -8, 0)),  # turntable pin on the slew axis
        contact("10", "20", position=(5, -40, 0), axis=(-1, 0, 0)),  # boom hinge pin
        contact("20", "21", position=(30, -60, 9)),  # bracket fixed to the boom
        contact("20", "30", position=(0, -40, 15), axis=(0, 0, -1)),  # slide guide
    ) == ([], [])


def test_misplaced_parts_are_flagged_with_their_bodies():
    found, _ = flagged(
        contact("1", "11", position=(40, 0, 0)),  # static frame pinned off the slew axis
        contact("2", "10", ("axle", "axle_hole"), position=(0, 0, -100)),  # gear riding off its axle
        contact("20", "30", position=(0, -40, 15), axis=(1, 0, 0)),  # pin across the slide
        contact("3", "21"),  # static part pinned to a part two joints away
    )
    assert found == [
        ("bridges 2 joints", ["bracket", "static"], [["21", "3"]]),
        ("crosses the slide", ["boom", "tele"], [["20", "30"]]),
        ("keyed off the joint axis", ["static", "turret"], [["10", "2"]]),
        ("pin off the joint axis", ["static", "turret"], [["1", "11"]]),
    ]


def test_linkages_shafts_and_declared_joints_are_not_warnings():
    found, info = flagged(
        contact("10", "30"),  # moving bodies across boom and tele: a linkage to declare
        contact("0", "10", ("axle", "axle_hole")),  # shaft keyed on the axis: rides one side
        contact("0", "40"),  # rod endpoint on the frame
        contact("0", "11", ("generic", "generic"), position=(40, 0, 0)),
        contact("1", "11", position=(40, 0, 0)),
        declared=[{"1", "11"}],
    )
    assert found == []
    assert sorted(g["reason"] for g in info) == [
        "bridges 2 joints",
        "generic/generic contact across a body boundary",
        "keyed axle on the joint axis",
        "rod body boundary",
    ]


@pytest.fixture
def hinge(tmp_path):
    source = tmp_path / "hinge.ldr"
    source.write_text(
        "0 Hinge\n"
        "1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n"
        "1 1 0 -24 0 1 0 0 0 1 0 0 0 1 3001.dat\n"
        "1 1 40 -24 0 1 0 0 0 1 0 0 0 1 3001.dat\n"
    )
    p = plan.draft(Document(source).manifest(), name="hinge")
    p.update(
        status="ready",
        controls={"open": dict(min=0, max=1, default=0, unit="radian", description="open")},
        signals={"open": dict(expression="a", variables={"a": "control:open"})},
        bodies={
            "lid": dict(kind="revolute", instances=["1"], origin=[0, -24, 0], axis=[0, 1, 0], signal="open")
        },
    )
    p["mechanisms"] = mechanisms.motion_views(p)
    p["connections"] = {"hinge": contact("0", "1", position=(0, -12, 0))}
    return p


def test_strict_check_blocks_until_membership_is_fixed(hinge):
    assert workflow.check(hinge, require_reviewed=True)["passed"]
    hinge["connections"]["latch"] = contact("1", "2", position=(40, -24, 0))
    report = workflow.check(hinge, require_reviewed=True)
    assert not report["passed"]
    warning = next(w for w in report["warnings"] if w["code"] == "body_boundary")
    assert warning["bodies"] == ["lid", "static"] and warning["pairs"] == [["1", "2"]]
    assert workflow.check(hinge)["passed"]  # Informational without --require-reviewed.
    hinge["bodies"]["lid"]["instances"].append("2")
    assert workflow.check(hinge, require_reviewed=True)["passed"]
