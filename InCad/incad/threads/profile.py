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




# ---- the outline drawn in the thread's sketch: lines and arcs, never a row of short segments -------------------
# (the user: a sketch of dots and segments made a thread of dozens of strips that took long and hung the program)
# A side of a groove or tooth is z(r) along r in pieces: ("L", r0, z0, r1, z1) a line, ("A", cr, cz, rad, s, r0, r1)
# an arc z = cz + s * sqrt(rad² - (r - cr)²) (every arc here is one-valued in r).

def _ev(p, r):
    if p[0] == "L":
        _, r0, z0, r1, z1 = p
        return z0 if r1 - r0 < 1e-15 else z0 + (z1 - z0) * (r - r0) / (r1 - r0)
    _, cr, cz, rad, sg, _r0, _r1 = p
    return cz + sg * math.sqrt(max(rad * rad - (r - cr) ** 2, 0.0))


def _lo(p):
    return p[1] if p[0] == "L" else p[5]


def _hi(p):
    return p[3] if p[0] == "L" else p[6]


def _cut(p, a, b):
    """The piece between a and b."""
    if p[0] == "L":
        return ("L", a, _ev(p, a), b, _ev(p, b))
    return p[:5] + (a, b)


def _at(side, r):
    if r <= _lo(side[0]):
        return _ev(side[0], _lo(side[0]))
    for p in side:
        if r <= _hi(p):
            return _ev(p, r)
    return _ev(side[-1], _hi(side[-1]))


def _const(r0, r1, z):
    return ("L", r0, z, r1, z)


def _shift(side, dr, dz):
    out = []
    for p in side:
        if p[0] == "L":
            out.append(("L", p[1] + dr, p[2] + dz, p[3] + dr, p[4] + dz))
        else:
            out.append(("A", p[1] + dr, p[2] + dz, p[3], p[4], p[5] + dr, p[6] + dr))
    return out


def _reflect(side, k):
    """z -> k - z."""
    out = []
    for p in side:
        if p[0] == "L":
            out.append(("L", p[1], k - p[2], p[3], k - p[4]))
        else:
            out.append(("A", p[1], k - p[2], p[3], -p[4], p[5], p[6]))
    return out


def _span(side, a, b):
    """The side between a and b, held at its end values beyond its own ends."""
    out = []
    first, last = _lo(side[0]), _hi(side[-1])
    if a < first:
        out.append(_const(a, min(first, b), _ev(side[0], first)))
    for p in side:
        x, y = max(_lo(p), a), min(_hi(p), b)
        if y - x > 1e-12:
            out.append(_cut(p, x, y))
    if b > last:
        out.append(_const(max(last, a), b, _ev(side[-1], last)))
    return out


def _breaks(*sides):
    rs = sorted({_lo(p) for s in sides for p in s} | {_hi(p) for s in sides for p in s})
    out = []
    for r in rs:
        if not out or r - out[-1] > 1e-12:
            out.append(r)
    return out


def _piece_at(side, a, b):
    m = 0.5 * (a + b)
    for p in side:
        if _lo(p) - 1e-12 <= m <= _hi(p) + 1e-12:
            return _cut(p, a, b)
    return _const(a, b, _at(side, m))


def _clip(side, bound, upper):
    """min(side, bound) (upper) or max(side, bound), over the side's span."""
    a0, b0 = _lo(side[0]), _hi(side[-1])
    bound = _span(bound, a0, b0)
    rs = _breaks(side, bound)
    out = []
    for a, b in zip(rs, rs[1:]):
        p, q = _piece_at(side, a, b), _piece_at(bound, a, b)
        f = lambda r: _ev(p, r) - _ev(q, r)
        cuts = [a]
        n = 32
        xs = [a + (b - a) * k / n for k in range(n + 1)]
        for x, y in zip(xs, xs[1:]):
            fx, fy = f(x), f(y)
            if fx * fy < 0:
                for _ in range(60):
                    m = 0.5 * (x + y)
                    if f(m) * fx > 0:
                        x, fx = m, f(m)
                    else:
                        y = m
                cuts.append(0.5 * (x + y))
        cuts.append(b)
        for x, y in zip(cuts, cuts[1:]):
            if y - x < 1e-12:
                continue
            m = 0.5 * (x + y)
            over = f(m) > 0
            take = q if over == upper else p
            out.append(_cut(take, x, y))
    return out


def _mix(s1, s2, k1, k2, k0):
    """k1·s1 + k2·s2 + k0 for sides of lines."""
    a0, b0 = _lo(s1[0]), _hi(s1[-1])
    s2 = _span(s2, a0, b0)
    out = []
    rs = _breaks(s1, s2)
    for a, b in zip(rs, rs[1:]):
        p, q = _piece_at(s1, a, b), _piece_at(s2, a, b)
        assert p[0] == "L" and q[0] == "L"
        out.append(("L", a, k1 * p[2] + k2 * q[2] + k0, b, k1 * p[4] + k2 * q[4] + k0))
    return out


def _flip_r(side, k):
    """r -> k - r."""
    out = []
    for p in reversed(side):
        if p[0] == "L":
            out.append(("L", k - p[3], p[4], k - p[1], p[2]))
        else:
            out.append(("A", k - p[1], p[2], p[3], p[4], k - p[6], k - p[5]))
    return out


def _until_zero(side, outward):
    """The side up to where it comes down to z = 0 (a tooth's flanks meet: its tip), going out (outward) or in."""
    pieces = side if outward else list(reversed(side))
    out = []
    for p in pieces:
        a, b = (_lo(p), _hi(p)) if outward else (_hi(p), _lo(p))
        za, zb = _ev(p, a), _ev(p, b)
        if za <= 1e-9:
            break
        if zb > 1e-9:
            out.append(p)
            continue
        x, y = a, b
        for _ in range(80):
            m = 0.5 * (x + y)
            if _ev(p, m) > 0:
                x = m
            else:
                y = m
        out.append(_cut(p, min(a, y), max(a, y)))
        break
    return out if outward else list(reversed(out))


def _poly_sides(poly):
    """A groove polygon of lines symmetric about z = 0 ([(r, z)], the left chain up then the right one down) as its
    (left, right) sides."""
    pts = []
    for r, z in sorted(poly):  # the widest point at each radius (a sharp root is one point, z a hair off 0)
        z = abs(z)
        if pts and abs(r - pts[-1][0]) < 1e-12:
            pts[-1] = (pts[-1][0], max(z, pts[-1][1]))
        else:
            pts.append((r, z))
    side = [("L", a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])]
    return _reflect(side, 0.0), side


def _ext_pieces(spec):
    """(left, right) of the external groove (nominal, z = 0 its middle at the crest) from its root to the major."""
    P, R, shape = spec.pitch, spec.major / 2.0, spec.shape
    if shape == "semicircle":
        rr = spec.radius
        right = [("A", R, 0.0, rr, 1.0, R - rr, R)]
        return _reflect(right, 0.0), right
    if shape == "buttress":
        r0 = R - spec.depth
        a1, a2 = math.tan(math.radians(spec.angle / 2.0)), math.tan(math.radians(spec.back))
        mid = 0.5 * spec.depth * (a2 - a1)
        return ([("L", r0, -mid, R, -spec.depth * a1 - mid)], [("L", r0, -mid, R, spec.depth * a2 - mid)])
    # round (DIN 405): root arc, 30° flanks, crest arcs (of the teeth either side)
    R0 = spec.radius
    s15, c15 = math.sin(math.radians(15)), math.cos(math.radians(15))
    r0 = R - spec.depth
    cr, cc = r0 + R0, R - R0
    rt1, rt2 = cr - R0 * s15, cc + R0 * s15
    crest = ("A", cc, P / 2.0, R0, -1.0, rt2, R)
    right = [("A", cr, 0.0, R0, 1.0, r0, rt1), ("L", rt1, R0 * c15, rt2, _ev(crest, rt2)), crest]
    return _reflect(right, 0.0), right


def _symmetric(spec):
    return getattr(spec, "shape", "v") != "buttress"


def _groove_sides(spec, internal, c, run):
    """(left, right, lo, hi) of the groove a thread cuts, as groove() draws it but exact."""
    P, R, half = spec.pitch, spec.major / 2.0, _wmax(spec.pitch) / 2.0
    if not _shaped(spec):
        left, right = _poly_sides(groove(spec, internal, 2 * c, run))
        return left, right, _lo(right[0]), _hi(right[-1])
    if internal and spec.shape == "semicircle":  # a jar lid's groove: its own semicircle out of the bore wall
        rr, r_min = spec.radius, R - spec.depth_int
        lo, hi = r_min - run, R + c
        right = [_const(lo, r_min, rr + c), ("A", r_min, c, rr, 1.0, r_min, r_min + rr)]
        if hi > r_min + rr + 1e-12:
            right.append(_const(r_min + rr, hi, c))
        right = _clip(right, [_const(lo, hi, half)], True)
        return _reflect(right, 0.0), right, lo, hi
    a, b = _ext_pieces(spec)
    if internal:  # the nut's groove is the bolt's tooth: what the pitch leaves of the bolt's groove
        r_min = R - spec.depth_int
        lo, hi = r_min - run, R + c
        a, b = _span(_span(a, r_min, R), lo, hi), _span(_span(b, r_min, R), lo, hi)
        left, right = _shift(b, 0.0, -P), a
    else:  # the shaft made thinner by the clearance: the groove reaches deeper
        lo, hi = R - spec.depth - c, R + run
        a, b = _shift(_span(a, lo + c, hi + c), -c, 0.0), _shift(_span(b, lo + c, hi + c), -c, 0.0)
        left, right = a, b
    if _symmetric(spec):
        mid = [_const(lo, hi, 0.5 * (_at(left, lo) + _at(right, lo)))]
    else:
        mid = _mix(left, right, 0.5, 0.5, 0.0)
    left = _clip(_shift(left, 0.0, -c), _shift(mid, 0.0, -half), False)
    right = _clip(_shift(right, 0.0, c), _shift(mid, 0.0, half), True)
    return left, right, lo, hi


def _tooth_sides(spec, internal, c, base, overlap):
    """(left, right, lo, hi) of the tooth a helix grows onto a surface at radius base, a hair into it so the two
    join. A semicircle grows as the bead it is (the user: "a thread like that does not exist, it won't work" of the
    hollow-flanked tooth what a pitch leaves beside a semicircle groove); every other profile grows the tooth what
    one pitch leaves beside its groove (the bolt's / the nut's tooth)."""
    P, R = spec.pitch, spec.major / 2.0
    top = (P - GAP) / 2.0
    if spec.std == "custom" and spec.shape != "semicircle":  # a triangle / trapezoid grows as the groove it cuts
        gl, gr, glo, ghi = _groove_sides(spec, internal, 0.0, 0.0)
        mid = 0.5 * (_at(gl, glo) + _at(gr, glo))
        gr = _shift(gr, 0.0, -mid)
        if internal:  # the groove widest at the bore wall (glo): the tooth from the wall b in towards the axis
            b = base if base is not None else glo
            t = _flip_r(gr, glo + b)
            lo, hi = b - (ghi - glo), b + overlap
        else:  # widest at the surface (ghi): the tooth from the rod's surface b out
            b = base if base is not None else ghi
            t = _flip_r(gr, ghi + b)
            lo, hi = b - overlap, b + (ghi - glo)
        t = _until_zero(_span(_shift(t, 0.0, -c), lo, hi), not internal)
        lo, hi = _lo(t[0]), _hi(t[-1])
        t = _clip(t, [_const(lo, hi, top)], True)
        return _reflect(t, 0.0), t, lo, hi
    if spec.shape == "semicircle":
        rr = max(spec.radius - c, 0.02)
        b = base if base is not None else (R if internal else R - spec.depth)
        if internal:  # from the bore wall in towards the axis
            lo, hi = b - rr, b + overlap
            right = [("A", b, 0.0, rr, 1.0, lo, b), _const(b, hi, rr)]
        else:
            lo, hi = b - overlap, b + rr
            right = [_const(lo, b, rr), ("A", b, 0.0, rr, 1.0, b, hi)]
        right = _clip(right, [_const(lo, hi, top)], True)
        return _reflect(right, 0.0), right, lo, hi
    gl, gr, glo, ghi = _groove_sides(spec, internal, 0.0, 0.0)
    if internal:
        b = base if base is not None else R
        lo, hi, ref = b - spec.depth_int + c, b + overlap, R
    else:
        b = base if base is not None else R - spec.depth
        lo, hi, ref = b - overlap, b + spec.depth - c, R - spec.depth
    if _symmetric(spec):
        mid = 0.5 * (_at(gl, glo) + _at(gr, glo))
        t = _reflect(_shift(gr, 0.0, -mid), P / 2.0 - c)  # (P − the groove's width) / 2 − c
    else:
        t = _mix(gr, gl, -0.5, 0.5, P / 2.0 - c)
    if hi - lo < 0.02:
        raise ValueError("The clearance is too big for this thread: make it smaller")
    t = _span(_shift(t, b - ref, 0.0), lo, hi)
    t = _clip(_clip(t, [_const(lo, hi, top)], True), [_const(lo, hi, 0.01)], False)
    return _reflect(t, 0.0), t, lo, hi


def outline(spec, internal, clearance=0.0, runout=None, grow=False, base=None, overlap=0.1):
    """The closed outline of the groove (cut) or the tooth (grown) in the (r, z) plane, z = 0 its middle:
    [("line", p, q) | ("arc", p, mid, q)] with points (r, z), joined end to start."""
    c = clearance / 2.0
    if grow:
        left, right, lo, hi = _tooth_sides(spec, internal, c, base, overlap)
    else:
        run = runout if runout is not None else max(0.5, 0.3 * spec.pitch)
        left, right, lo, hi = _groove_sides(spec, internal, c, run)
    return _path(left, right, lo, hi)


def _path(left, right, lo, hi):
    pieces = [(p, False) for p in left] + [(p, True) for p in reversed(right)]
    segs = []
    pen = (lo, _at(left, lo))
    start = pen

    def line_to(q):
        nonlocal pen
        if abs(q[0] - pen[0]) < 1e-9 and abs(q[1] - pen[1]) < 1e-9:
            return
        if segs and segs[-1][0] == "line":  # one line on from the last one where they run on straight
            a = segs[-1][1]
            cross = (pen[0] - a[0]) * (q[1] - a[1]) - (pen[1] - a[1]) * (q[0] - a[0])
            if abs(cross) < 1e-12 and (pen[0] - a[0]) * (q[0] - pen[0]) + (pen[1] - a[1]) * (q[1] - pen[1]) > 0:
                segs[-1] = ("line", a, q)
                pen = q
                return
        segs.append(("line", pen, q))
        pen = q

    for n, (p, back) in enumerate(pieces):
        if n == len(left):  # across the top
            line_to((hi, _at(right, hi)))
        r0, r1 = (_hi(p), _lo(p)) if back else (_lo(p), _hi(p))
        q = (r1, _ev(p, r1))
        if p[0] == "A":
            m = 0.5 * (r0 + r1)
            mid = (m, _ev(p, m))
            # sagitta: an arc that is all but straight is drawn as a line
            dx, dz = q[0] - pen[0], q[1] - pen[1]
            ln = math.hypot(dx, dz)
            sag = abs((mid[0] - pen[0]) * dz - (mid[1] - pen[1]) * dx) / ln if ln > 1e-12 else 0.0
            if ln > 1e-9 and sag > 1e-7:
                segs.append(("arc", pen, mid, q))
                pen = q
                continue
        line_to(q)
    line_to(start)
    return _without_crumbs(segs)


def _without_crumbs(segs, tol=1e-6):
    """A line shorter than tol (where a clip meets a tip: 4e-8 mm) dropped, its neighbours joined at its middle: a
    sweep along a helix fails on it."""
    out = list(segs)
    i = 0
    while i < len(out) and len(out) > 3:
        s = out[i]
        if s[0] == "line" and math.hypot(s[2][0] - s[1][0], s[2][1] - s[1][1]) < tol:
            m = (0.5 * (s[1][0] + s[2][0]), 0.5 * (s[1][1] + s[2][1]))
            prev, nxt = out[i - 1], out[(i + 1) % len(out)]
            out[i - 1] = prev[:-1] + (m,)
            out[(i + 1) % len(out)] = (nxt[0], m) + nxt[2:]
            del out[i]
            continue
        i += 1
    return out


def outline_width(segs):
    zs = [pt[1] for s in segs for pt in s[1:]]
    return max(zs) - min(zs)
