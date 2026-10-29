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
    R = R - spec.crest_drop
    return (lambda r: min(wm, base - 2.0 * (R - c - r) * t)), t, base, R


def _shaped(spec):
    return getattr(spec, "shape", "v") in ("round", "semicircle", "buttress")


def _ext_sides(spec, r):
    """(left, right) z of the external groove at radius r (z = 0 its middle), nominal (no clearance): DIN 405 round,
    a semicircle, a buttress. Past the crest (r above the major) the groove keeps its width there."""
    P, R = spec.pitch, spec.major / 2.0
    shape = spec.shape
    if shape == "semicircle":
        rr = spec.radius
        d = min(max(R - r, 0.0), rr)
        w = math.sqrt(max(rr * rr - d * d, 0.0))
        return -w, w
    if shape == "buttress":
        r0 = R - spec.depth
        a1, a2 = math.tan(math.radians(spec.angle / 2.0)), math.tan(math.radians(spec.back))
        h = min(max(r - r0, 0.0), spec.depth)
        mid = 0.5 * spec.depth * (a2 - a1)  # the groove centred on z = 0 at the crest
        return -h * a1 - mid, h * a2 - mid
    # round (DIN 405): root arc, 30° flanks, crest arcs (of the teeth either side)
    R0, s15, c15, t15 = spec.radius, math.sin(math.radians(15)), math.cos(math.radians(15)), math.tan(math.radians(15))
    r0 = R - spec.depth
    cr = r0 + R0                      # the root arc's centre (z = 0)
    cc = R - R0                       # the crest arcs' centres (z = ±P/2)
    rt1, wt1 = cr - R0 * s15, R0 * c15
    rt2 = cc + R0 * s15
    rr = min(max(r, r0), R)
    if rr <= rt1:
        w = math.sqrt(max(R0 * R0 - (rr - cr) ** 2, 0.0))
    elif rr < rt2:
        w = wt1 + (rr - rt1) * t15
    else:
        w = P / 2.0 - math.sqrt(max(R0 * R0 - (rr - cc) ** 2, 0.0))
    return -w, w


def _shaped_groove(spec, internal, c, run):
    """The groove of a round, semicircle or buttress thread as a polygon, sampled finely on its curves."""
    P, R, wm = spec.pitch, spec.major / 2.0, _wmax(spec.pitch)
    half = wm / 2.0
    if internal:
        r_min = R - spec.depth_int
        lo, hi = r_min - run, R + c
        if spec.shape == "semicircle":  # a jar lid's groove: its own semicircle out of the bore wall
            def sides(r):
                d = min(max(r - r_min, 0.0), spec.radius)
                w = math.sqrt(max(spec.radius ** 2 - d * d, 0.0)) + c
                return -min(w, half), min(w, half)
        else:  # the nut's groove is the bolt's tooth: what the pitch leaves of the bolt's groove
            def sides(r):
                a, b = _ext_sides(spec, min(r, R))
                if r <= r_min:
                    a, b = _ext_sides(spec, r_min)
                left, right = b - P, a  # between this turn's groove and the next one's
                mid = 0.5 * (left + right)
                w = 0.5 * (right - left) + c
                return mid - min(w, half), mid + min(w, half)
    else:
        lo, hi = R - spec.depth - c, R + run

        def sides(r):
            a, b = _ext_sides(spec, r + c)  # the shaft made thinner by the clearance: the groove reaches deeper
            mid = 0.5 * (a + b)
            w = 0.5 * (b - a) + c
            return mid - min(w, half), mid + min(w, half)
    n = 24
    rs = [lo + (hi - lo) * k / n for k in range(n + 1)]
    left = [(r, sides(r)[0]) for r in rs]
    right = [(r, sides(r)[1]) for r in reversed(rs)]
    pts = []
    for q in left + right:
        if not pts or abs(q[0] - pts[-1][0]) > 1e-9 or abs(q[1] - pts[-1][1]) > 1e-9:
            pts.append(q)
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts.pop()
    return pts


def knee(spec, internal, clearance=0.0):
    """The radius where the groove reaches its full width (the pitch less a hair). Past it, towards the surface, a
    hair-thin fin would stay between the turns: an external thread's rod is turned down to it, a hole bored out."""
    c = clearance / 2.0
    if _shaped(spec):  # no flank reaches the pitch's width: no fin; a rod stays as it is to the major
        R = spec.major / 2.0
        return R - spec.depth_int + c if internal else R - c
    _, t, base, ref = _width_fn(spec, internal, c)
    wm = _wmax(spec.pitch)
    return ref + c + (base - wm) / (2.0 * t) if internal else ref - c - (base - wm) / (2.0 * t)


def groove(spec, internal, clearance=0.0, runout=None):
    c = clearance / 2.0
    run = runout if runout is not None else max(0.5, 0.3 * spec.pitch)
    if _shaped(spec):
        return _shaped_groove(spec, internal, c, run)
    R, wm = spec.major / 2.0, _wmax(spec.pitch)
    width, t, base, ref = _width_fn(spec, internal, c)
    if internal:
        lo, hi = ref - run, R + c
        knee = ref + c + (base - wm) / (2.0 * t)  # where the flank leaves the clamp, going outward
    else:
        R = ref  # the external crest (nominal major less any crest drop)
        lo, hi = R - spec.depth - c, R + spec.crest_drop + run
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


GAP = 0.05  # mm (axial) left between two turns of grown teeth: touching turns make the helix fail


def tooth(spec, internal, clearance=0.0, base=None, overlap=0.1):
    """The tooth a helix GROWS onto a surface (the user: a thread either cut into it or grown onto it, as a jar's
    bead): what one pitch leaves beside the groove, from the surface (base radius, a hair into it so the two join)
    out to the crest (a shaft) or in to it (a bore). Polygon [(r, z)] centred on z = 0."""
    P = spec.pitch
    c = clearance / 2.0
    g = groove(spec, internal, 0.0, runout=0.0)
    if internal:
        R = spec.major / 2.0
        b = base if base is not None else R
        lo, hi = b - spec.depth_int + c, b + overlap
        to_profile = lambda r: r - b + R  # the nut's root (major) at the bore wall
    else:
        R = spec.major / 2.0
        b = base if base is not None else R - spec.depth
        lo, hi = b - overlap, b + spec.depth - c
        to_profile = lambda r: r - b + (R - spec.depth)  # the bolt's root at the rod
    n = 24
    rs = [lo + (hi - lo) * k / n for k in range(n + 1)]
    widths = []
    for r in rs:
        q = min(max(to_profile(r), min(x for x, _ in g) + 1e-9), max(x for x, _ in g) - 1e-9)
        w = P - width_at(g, q) - 2 * c
        widths.append(max(min(w, P - GAP), 0.02))
    left = [(r, -w / 2.0) for r, w in zip(rs, widths)]
    right = [(r, w / 2.0) for r, w in zip(reversed(rs), reversed(widths))]
    pts = []
    for q in left + right:
        if not pts or abs(q[0] - pts[-1][0]) > 1e-9 or abs(q[1] - pts[-1][1]) > 1e-9:
            pts.append(q)
    return pts
