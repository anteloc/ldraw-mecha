"""Closed-form linkage signals for plans (pure: no bpy, no pyldraw3).

Each helper writes ordinary plan signals (Blender simple expressions) and checks
its closed form against explicit rotations before returning. Frames are the
selected source frame (LDU); angles are radians about the stated axes using the
right-hand rule.
"""

from __future__ import annotations

import math

from .math3d import add, cross, dot, length, mul, sub, unit


def rotate(v, axis, angle):
    """Rodrigues rotation of vector v about unit axis."""
    k = unit(axis)
    c, s = math.cos(angle), math.sin(angle)
    return add(add(mul(v, c), mul(cross(k, v), s)), mul(k, dot(k, v) * (1 - c)))


def _num(v):
    return repr(float(v))


def _put(signals, name, expression, **variables):
    if len(expression) > 255:
        raise ValueError(f"Signal {name} exceeds the 255 character driver limit")
    signals[name] = dict(
        expression=expression,
        variables={k: v if ":" in v else "signal:" + v for k, v in variables.items()},
    )
    return name


def gear_pair(signals, prefix, driver, carrier, ratio):
    """Follower angle in the carrier's frame: b = c + ratio * (a - c).

    Inputs are absolute angles about consistently directed parallel axes.
    `ratio` includes the sign (external gears with equally directed axes use
    -Na/Nb). The caller must establish mesh, tooth counts and rigid shaft groups.
    Passing zero as a constant carrier signal describes a fixed-axis pair.
    """
    if not isinstance(ratio, (int, float)) or not math.isfinite(ratio) or ratio == 0:
        raise ValueError("Gear ratio must be finite and nonzero")
    return _put(signals, prefix + "_out", f"c+{_num(ratio)}*(a-c)", a=driver, c=carrier)


def differential(
    signals, prefix, side_a, side_b, *, side_teeth, planet_teeth, planet_sign=1
):
    """Equal-side-gear differential: carrier mean and planet spin relative to it.

    Both side angles use the SAME directed shaft axis, even when their part
    matrices face opposite ways. Planet sign depends on its chosen axis/contact.
    Parent the planet to the carrier and drive it with the returned relative
    spin. This is a relation, not automatic discovery of a differential.
    """
    if any(
        not isinstance(n, int) or isinstance(n, bool) or n <= 0
        for n in (side_teeth, planet_teeth)
    ) or planet_sign not in (-1, 1):
        raise ValueError(
            "Differential needs positive integer tooth counts and planet_sign +/-1"
        )
    carrier = _put(signals, prefix + "_carrier", "(a+b)/2", a=side_a, b=side_b)
    planet = _put(
        signals,
        prefix + "_planet",
        f"{_num(planet_sign * side_teeth / (2 * planet_teeth))}*(a-b)",
        a=side_a,
        b=side_b,
    )
    return carrier, planet


def universal_joint(signals, prefix, theta, d_in, d_out, f_in, f_out, samples=48):
    """Exact single universal (cardan) joint with arbitrary fork phase.

    `theta` names the input shaft angle (signal or control reference) about
    d_in. d_in points along the input shaft towards the joint, d_out along the
    output shaft away from it (d_in . d_out > 0). f_in / f_out are the rest
    fork pivot axes of the input and output yokes; they must be perpendicular
    to their shafts and to each other (the two arms of the centre cross).

    Adds `{prefix}_out`, the output angle about d_out (unwrapped, so it stays
    continuous over many turns), and `{prefix}_cross`, the centre-cross angle
    about f_in relative to the input yoke (parent the cross body to the input
    shaft). Returns (out_signal, cross_signal).
    """
    d_in, d_out, f_in, f_out = (unit(v) for v in (d_in, d_out, f_in, f_out))
    for a, b, what in (
        (d_in, f_in, "input fork / shaft"),
        (d_out, f_out, "output fork / shaft"),
        (f_in, f_out, "cross arms"),
    ):
        if abs(dot(a, b)) > 1e-2:
            raise ValueError(f"Universal joint {prefix}: {what} not perpendicular")
    # Rounded source matrices leave ~1e-4 errors; project to an exact cross.
    f_in = unit(sub(f_in, mul(d_in, dot(d_in, f_in))))
    exact = unit(cross(d_out, f_in))
    exact = exact if dot(exact, f_out) > 0 else mul(exact, -1)
    if dot(exact, f_out) < math.cos(math.radians(1)):
        raise ValueError(
            f"Universal joint {prefix}: output fork is more than 1 degree off"
        )
    f_out = exact
    if dot(d_in, d_out) <= 0.05:
        raise ValueError(f"Universal joint {prefix}: bend must stay below 87 degrees")
    h_in = cross(d_in, f_in)
    g_out = cross(d_out, f_out)
    a, b, c = dot(h_in, f_out), dot(f_in, g_out), dot(h_in, g_out)
    sb = 1.0 if b >= 0 else -1.0
    k = cross(f_in, f_out)

    def q_terms(v, w):
        # R(d_in, t) v . w = cos(t) A + sin(t) B + (1 - cos(t)) C
        return dot(v, w), dot(cross(d_in, v), w), dot(d_in, v) * dot(d_in, w)

    n_c, n_s = q_terms(k, f_out), q_terms(k, g_out)
    d_c, d_s = q_terms(f_out, f_out), q_terms(f_out, g_out)

    def output(t):
        wrapped = math.atan2(
            -a * math.sin(t) * sb, (b * math.cos(t) + c * math.sin(t)) * sb
        )
        return t + math.atan2(math.sin(wrapped - t), math.cos(wrapped - t))

    def qv(terms, t):
        return (
            math.cos(t) * terms[0]
            + math.sin(t) * terms[1]
            + (1 - math.cos(t)) * terms[2]
        )

    def cross_angle(t, o):
        n = math.cos(o) * qv(n_c, t) + math.sin(o) * qv(n_s, t)
        d = math.cos(o) * qv(d_c, t) + math.sin(o) * qv(d_s, t)
        return math.atan2(n, d)

    for i in range(-samples, samples + 1):
        t = 4 * math.pi * i / samples
        o = output(t)
        fi, fo = rotate(f_in, d_in, t), rotate(f_out, d_out, o)
        if abs(dot(fi, fo)) > 1e-9:
            raise ValueError(
                f"Universal joint {prefix}: output violates the cross constraint"
            )
        g = cross_angle(t, o)
        arm2 = rotate(rotate(f_out, f_in, g), d_in, t)
        if length(sub(arm2, fo)) > 1e-9:
            raise ValueError(
                f"Universal joint {prefix}: cross angle does not reach the output fork"
            )
    if abs(output(0.0)) > 1e-12:
        raise ValueError(f"Universal joint {prefix}: rest pose is not the zero branch")

    p = prefix
    _put(signals, p + "_c", "cos(t)", t=theta)
    _put(signals, p + "_s", "sin(t)", t=theta)
    _put(
        signals,
        p + "_w",
        f"atan2({_num(-a * sb)}*s,{_num(b * sb)}*c+{_num(c * sb)}*s)",
        c=p + "_c",
        s=p + "_s",
    )
    _put(signals, p + "_out", "t+atan2(sin(w-t),cos(w-t))", t=theta, w=p + "_w")
    _put(signals, p + "_co", "cos(o)", o=p + "_out")
    _put(signals, p + "_so", "sin(o)", o=p + "_out")

    def q_expr(terms):
        return f"(c*{_num(terms[0])}+s*{_num(terms[1])}+(1-c)*{_num(terms[2])})"

    four = dict(c=p + "_c", s=p + "_s", co=p + "_co", so=p + "_so")
    _put(signals, p + "_n", f"co*{q_expr(n_c)}+so*{q_expr(n_s)}", **four)
    _put(signals, p + "_d", f"co*{q_expr(d_c)}+so*{q_expr(d_s)}", **four)
    _put(signals, p + "_cross", "atan2(n,d)", n=p + "_n", d=p + "_d")
    return p + "_out", p + "_cross"


def double_cardan(signals, prefix, theta, d_in, d_out, fork):
    """Phased equal-bend Cardan pair at a fixed articulation.

    `fork` is the common input/output fork axis at rest, perpendicular to both
    shaft directions. The intermediate shaft is the vector angle bisector;
    its two forks share the returned `middle_fork` direction. Each joint is
    solved separately, so the nonuniform intermediate rotation remains visible.
    This helper does not infer that a real assembly enforces the bisector, and
    cannot substitute for its centring linkage or differential closure checks.
    """
    a, b, f = unit(d_in), unit(d_out), unit(fork)
    if dot(a, b) <= -0.99 or abs(dot(a, f)) > 1e-6 or abs(dot(b, f)) > 1e-6:
        raise ValueError(
            "Double Cardan needs a common perpendicular fork and non-opposed shafts"
        )
    middle = unit(add(a, b))
    middle_fork = unit(cross(middle, f))
    mid, cross_a = universal_joint(
        signals, prefix + "_a", theta, a, middle, f, middle_fork
    )
    out, cross_b = universal_joint(
        signals, prefix + "_b", mid, middle, b, middle_fork, f
    )
    return dict(
        middle_axis=middle,
        middle_fork=middle_fork,
        middle=mid,
        output=out,
        cross_a=cross_a,
        cross_b=cross_b,
    )


def ball_link(signals, prefix, slide, pivot, axis, ball, socket, direction, length_ldu):
    """Knuckle angle that keeps a rigid ball link closed.

    A knuckle turns about `axis` through `pivot`; its ball starts at `ball`.
    The other link end (`socket`) translates by `slide` (a signal, LDU) along
    `direction`. Adds `{prefix}_angle`, the knuckle angle on the branch through
    the rest pose, and returns its name. The link length is checked at rest.
    """
    k = unit(axis)
    u = unit(direction)
    r = sub(ball, pivot)
    r_par = mul(k, dot(r, k))
    r_perp = sub(r, r_par)
    rho2 = dot(r_perp, r_perp)
    kr = cross(k, r_perp)
    w0 = sub(add(pivot, r_par), socket)
    if abs(length(sub(ball, socket)) - length_ldu) > 0.05:
        raise ValueError(f"Ball link {prefix}: rest length differs from {length_ldu}")
    # A cos + B sin = C, all linear/quadratic in the slide s; w = w0 - s u.
    a0, a1 = 2 * dot(w0, r_perp), -2 * dot(u, r_perp)
    b0, b1 = 2 * dot(w0, kr), -2 * dot(u, kr)
    ww0, ww1, ww2 = dot(w0, w0), -2 * dot(w0, u), 1.0
    c0 = length_ldu**2 - rho2 - ww0
    sigma = -1.0 if b0 > 0 else 1.0

    def angle(s):
        A, B = a0 + a1 * s, b0 + b1 * s
        C = c0 - ww1 * s - ww2 * s * s
        R = math.hypot(A, B)
        return math.atan2(B, A) + sigma * math.acos(max(-1.0, min(1.0, C / R)))

    if abs(angle(0.0)) > 1e-7:
        raise ValueError(f"Ball link {prefix}: rest pose not on the chosen branch")
    for s in (-20.0, -10.0, 10.0, 20.0):
        phi = angle(s)
        kb = add(pivot, rotate(r, k, phi))
        if abs(length(sub(kb, add(socket, mul(u, s)))) - length_ldu) > 1e-6:
            raise ValueError(f"Ball link {prefix}: closure check failed at slide {s}")
    p = prefix
    _put(signals, p + "_A", f"{_num(a0)}+{_num(a1)}*s", s=slide)
    _put(signals, p + "_B", f"{_num(b0)}+{_num(b1)}*s", s=slide)
    _put(signals, p + "_C", f"{_num(c0)}-{_num(ww1)}*s-s*s", s=slide)
    _put(
        signals,
        p + "_angle",
        f"atan2(b,a)+{_num(sigma)}*acos(clamp(c/sqrt(a*a+b*b),-1,1))",
        a=p + "_A",
        b=p + "_B",
        c=p + "_C",
    )
    return p + "_angle", angle
