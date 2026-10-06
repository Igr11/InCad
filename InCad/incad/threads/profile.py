"""The groove a helix cuts: a closed polygon [(r, z)] (r = radius, z = along the axis, centred on z = 0).

External thread: the gap between teeth of a shaft of major radius R, from the root (R − depth) out past R.
Internal thread: the gap between teeth of a nut, from inside the bore out to the root (R).
The print clearance (diametral) moves the flanks by half of it: into the shaft, out into the nut.
Widths are clamped below the pitch so neighbouring turns never touch (this also trims sharp crests)."""
import math


def _wmax(pitch):
    return pitch - min(0.04, 0.1 * pitch)


def _width_fn(spec, internal, c):
    t = math.tan(math.radians(spec.angle / 2.0))
    R, wm = spec.major / 2.0, _wmax(spec.pitch)
    if internal:
        r_min = R - spec.depth_int
        base = spec.pitch - spec.crest_int
        return (lambda r: min(wm, base - 2.0 * (r - (r_min + c)) * t)), t, base, r_min
    base = spec.pitch - spec.crest_ext
    return (lambda r: min(wm, base - 2.0 * (R - c - r) * t)), t, base, R


def groove(spec, internal, clearance=0.0, runout=None):
    c = clearance / 2.0
    run = runout if runout is not None else max(0.5, 0.3 * spec.pitch)
    R, wm = spec.major / 2.0, _wmax(spec.pitch)
    width, t, base, ref = _width_fn(spec, internal, c)
    if internal:
        lo, hi = ref - run, R + c
        knee = ref + c + (base - wm) / (2.0 * t)  # where the flank leaves the clamp, going outward
    else:
        lo, hi = R - spec.depth - c, R + run
        knee = R - c - (base - wm) / (2.0 * t)  # where the flank reaches the clamp, going outward
    rs = [lo] + ([knee] if lo < knee < hi else []) + [hi]
    left = [(r, -max(width(r), 0.0) / 2.0) for r in rs]
    right = [(r, max(width(r), 0.0) / 2.0) for r in reversed(rs)]
    pts = []
    for p in left + right:
        if not pts or abs(p[0] - pts[-1][0]) > 1e-9 or abs(p[1] - pts[-1][1]) > 1e-9:
            pts.append(p)
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts.pop()
    return pts


def width_at(poly, r):
    """Axial width of the polygon at radius r."""
    zs = []
    for i in range(len(poly)):
        (r1, z1), (r2, z2) = poly[i], poly[(i + 1) % len(poly)]
        if (r1 - r) * (r2 - r) <= 0 and abs(r2 - r1) > 1e-12:
            zs.append(z1 + (z2 - z1) * (r - r1) / (r2 - r1))
    return max(zs) - min(zs) if zs else 0.0


def max_width(poly):
    return max(z for _, z in poly) - min(z for _, z in poly)
