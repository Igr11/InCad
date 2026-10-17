"""Emboss geometry (Inventor's Emboss / Engrave, with Wrap to face): a profile's faces (a Text's letters, a sketch's
regions) raised from or cut into a face of the part. On a cylinder or a cone the profile is wrapped: both unroll flat
without stretching, so a letter's outline maps exactly onto it — across the profile goes round the axis (arc length
= the flat distance), up it goes along the axis — and the letter is thickened along the radius. On a flat face it is
a straight emboss along the face's normal. The profile's plane must be parallel to the cylinder's axis (a plane
touching it, say); the profile lands on the side of the cylinder facing that plane. A sphere cannot be unrolled: the
profile is projected onto it along the sketch's normal (Inventor's emboss on a curved face), its walls along that
direction, its height along the radius."""
import math

import FreeCAD as App
import Part

ROUND_MSG = "Put the profile's sketch on a plane parallel to the cylinder's axis (a plane touching it, for example)"
FLAT_MSG = "Pick a flat face parallel to the profile's sketch, or a round (cylindrical) face"
FACE_MSG = "Pick a round (cylinder, cone or sphere) or a flat face of the part to emboss on"
SPHERE_EDGE_MSG = ("Some of the profile is past the sphere's edge as seen from the sketch: move it towards the sphere's "
                   "centre or shrink it")
SPHERE_SPREAD_MSG = "Evenly round works on a cylinder or a cone; on a sphere the profile is projected as drawn"
OFF_MSG = "Some of the profile is off the face (letters past its edge, or too deep): move or shrink it"
_TOL = 1e-7


def _unit(v):
    v = App.Vector(v)
    if v.Length < 1e-12:
        raise ValueError("Zero direction")
    v.normalize()
    return v


def is_round(face):
    """A cylinder or a cone: the faces a profile can be wrapped round."""
    return face.Surface.TypeId in ("Part::GeomCylinder", "Part::GeomCone")


def is_flat(face):
    return face.Surface.TypeId == "Part::GeomPlane"


def is_sphere(face):
    return face.Surface.TypeId == "Part::GeomSphere"


def _profile_normal(faces):
    n = faces[0].normalAt(*faces[0].Surface.parameter(faces[0].CenterOfMass)[:2]) if faces else None
    return _unit(n)


def _to2d(edge, uv):
    """The edge (in the profile's plane) as a 2D curve in the surface's parameters, through the linear map uv(point)
    -> (u, v): lines stay lines, everything else as its exact B-spline with mapped poles."""
    c = edge.Curve
    if type(c).__name__ in ("Line", "LineSegment"):
        a, b = uv(edge.Vertexes[0].Point), uv(edge.Vertexes[-1].Point)
        return Part.Geom2d.Line2dSegment(App.Base.Vector2d(*a), App.Base.Vector2d(*b))
    bs = c if isinstance(c, Part.BSplineCurve) else edge.toNurbs().Edges[0].Curve
    if abs(edge.FirstParameter - bs.FirstParameter) > 1e-12 or abs(edge.LastParameter - bs.LastParameter) > 1e-12:
        bs = bs.copy()
        bs.segment(edge.FirstParameter, edge.LastParameter)
    poles = [App.Base.Vector2d(*uv(p)) for p in bs.getPoles()]
    b2 = Part.Geom2d.BSplineCurve2d()
    b2.buildFromPolesMultsKnots(poles, bs.getMultiplicities(), bs.getKnots(), bs.isPeriodic(), bs.Degree,
                                bs.getWeights())
    return b2


def _face_on(surface, face, uv):
    """The profile face rebuilt on the surface: its outer wire and its holes mapped through uv."""
    def wire(w):
        return Part.Wire([_to2d(e, uv).toShape(surface) for e in w.OrderedEdges])
    outer = face.OuterWire
    made = Part.Face(surface, wire(outer))
    for w in face.Wires:
        if not w.isSame(outer):  # a hole (O, A, Р): cut out of the face on the surface
            made = made.cut(Part.Face(surface, wire(w)))
    made = made.Faces[0]
    made.validate()
    return made


def _on_the_face(letter, face):
    """Every letter lies wholly on the picked face (Inventor refuses a profile past the face's edge)."""
    try:
        inside = letter.common(face).Area
    except Part.OCCError:
        inside = 0.0
    if inside < letter.Area * (1 - 1e-6) - 1e-9:
        raise ValueError(OFF_MSG)


def _letters(faces, w, origin):
    """The faces grouped into letters by where they lie across the profile (an i's dot, a Ж's parts are one
    letter): [(centre across, [faces])] in reading order."""
    spans = []
    for f in faces:
        b = [(v.Point - origin).dot(w) for v in f.Vertexes] or [0.0]
        spans.append((min(b), max(b), f))
    spans.sort(key=lambda t: t[0])
    groups = []
    for lo, hi, f in spans:
        if groups and lo < groups[-1][1] - 1e-9:
            g = groups[-1]
            groups[-1] = (g[0], max(g[1], hi), g[2] + [f])
        else:
            groups.append((lo, hi, [f]))
    return [((lo + hi) / 2.0, fs) for lo, hi, fs in groups]


def _spread(faces, w, origin, circumference):
    """Evenly round: the letters keep their widths, their spacing grows so they go once round the whole face (the
    gap after the last letter as the others), centred where the profile faces the part."""
    letters = _letters(faces, w, origin)
    if len(letters) < 2:
        return faces
    first, last = letters[0][0], letters[-1][0]
    pitch = (last - first) / (len(letters) - 1)
    if pitch <= 1e-9:
        return faces
    f = circumference / ((last - first) + pitch)
    mid = (first + last) / 2.0
    out = []
    for c, fs in letters:
        shift = (c - mid) * f - c  # its new centre, measured from the profile's centre
        for face in fs:
            g = face.copy()
            g.translate(w * shift)
            out.append(g)
    return out


def _wrap_round(profile_faces, round_face, depth, spread=False, normal=None):
    """The profile's faces wrapped on the cylinder or cone and thickened `depth` along its normal (outward > 0,
    inward < 0). Both unroll flat without stretching: across the profile goes round the axis (arc length = the flat
    distance, at the profile's centre), up it goes along the surface (a cone: along its slant). spread: the letters
    evenly round the whole face."""
    surface = round_face.Surface.copy()
    a, centre, r = _unit(surface.Axis), App.Vector(surface.Center), surface.Radius
    cone = surface.TypeId == "Part::GeomCone"
    alpha = surface.SemiAngle if cone else 0.0
    n_sk = _unit(normal) if normal is not None else _profile_normal(profile_faces)
    if abs(n_sk.dot(a)) > 1e-6:
        raise ValueError(ROUND_MSG)
    bb = Part.makeCompound(profile_faces).BoundBox
    pc = App.Vector(bb.Center)  # the profile's centre: it lands on the face where the face meets the profile's side
    zc = (pc - centre).dot(a)
    vc = zc / math.cos(alpha)
    rc = r + vc * math.sin(alpha)  # the face's radius at the profile's height
    if rc <= 1e-6:
        raise ValueError("The profile sits past the cone's tip: move it to where the cone is round")
    off = pc - (centre + a * zc)
    d = off.dot(n_sk)  # the profile plane's distance from the axis, along its normal
    n = n_sk if d >= 0 else n_sk * -1  # from the axis towards the plane (a plane through the axis: its own side)
    w = a.cross(n)  # across the profile = round the axis (seen from outside, to the right)
    base = centre + a * zc + n * rc
    u0, v0 = surface.parameter(base)
    probe = surface.value(u0 + 1e-3, v0) - surface.value(u0, v0)
    su = 1.0 if probe.dot(w) > 0 else -1.0
    sv = 1.0 if (surface.value(u0, v0 + 1.0) - surface.value(u0, v0)).dot(a) > 0 else -1.0
    if spread:
        profile_faces = _spread(profile_faces, w, pc, 2 * math.pi * rc)

    def uv(p):
        q = p - pc
        return (u0 + su * q.dot(w) / rc, v0 + sv * q.dot(a))  # up the profile = along the surface (its slant)

    out = []
    for f in profile_faces:
        on = _face_on(surface, f, uv)
        _on_the_face(on, round_face)
        # outward is away from the axis: a part's surface may point inward (its face is then the reversed one)
        p = on.CenterOfMass
        uu, vv = on.Surface.parameter(p)[:2]
        radial = p - (centre + a * (p - centre).dot(a))
        sign = 1.0 if on.normalAt(uu, vv).dot(radial) > 0 else -1.0
        out.append(on.makeOffsetShape(depth * sign, 1e-6, fill=True))
    return out


def _project_sphere(profile_faces, sphere_face, depth, spread=False, normal=None):
    """The profile projected onto the sphere along the sketch's normal, on the half that faces the sketch, and given
    `depth` along the radius (out of the material > 0, into it < 0): each letter is its prism along the normal cut
    by the spherical shell between the face and `depth` from it."""
    if spread:
        raise ValueError(SPHERE_SPREAD_MSG)
    s = sphere_face.Surface
    c, r = App.Vector(s.Center), s.Radius
    n_sk = _unit(normal) if normal is not None else _profile_normal(profile_faces)
    pc = App.Vector(Part.makeCompound(profile_faces).BoundBox.Center)
    toward = n_sk if (pc - c).dot(n_sk) >= 0 else n_sk * -1  # from the centre towards the sketch's side
    p0 = c + toward * r
    u0, v0 = s.parameter(p0)[:2]
    out_of_material = 1.0 if sphere_face.normalAt(u0, v0).dot(toward) > 0 else -1.0  # a ball: outward; a hollow: in
    lo, hi = sorted((r, r + depth * out_of_material))
    if lo <= 1e-6:
        raise ValueError("Too deep for this sphere: make the depth smaller than its radius")
    shell = Part.makeSphere(hi, c).cut(Part.makeSphere(lo, c))
    full = Part.makeSphere(r, c).Faces[0]
    reach = r + abs(depth) + 1.0
    out = []
    for f in profile_faces:
        for v in f.Vertexes:  # the sphere's outline seen along the normal: a letter past it hangs off
            q = v.Point - c
            if (q - toward * q.dot(toward)).Length >= min(lo, r) * (1 - 1e-6):
                raise ValueError(SPHERE_EDGE_MSG)
        g = f.copy()
        g.translate(toward * -((g.Vertexes[0].Point - c).dot(toward)))  # onto the plane through the centre
        prism = g.extrude(toward * reach)
        on = sphere_face.common(prism).Area
        if on < full.common(prism).Area * (1 - 1e-4) - 1e-9:  # past the picked face's own edge (a dome's rim)
            raise ValueError(OFF_MSG)
        out.append(prism.common(shell))
    return out


def _straight(profile_faces, flat_face, depth):
    """The profile moved onto the flat face (along its normal) and extruded `depth` along it (out > 0, in < 0)."""
    n = _unit(flat_face.normalAt(*flat_face.Surface.parameter(flat_face.CenterOfMass)[:2]))
    if abs(abs(_profile_normal(profile_faces).dot(n)) - 1) > 1e-6:
        raise ValueError(FLAT_MSG)
    gap = (flat_face.CenterOfMass - profile_faces[0].Vertexes[0].Point).dot(n)
    out = []
    for f in profile_faces:
        g = f.copy()
        g.translate(n * gap)
        _on_the_face(g, flat_face)
        out.append(g.extrude(n * depth))
    return out


def tools(profile_faces, face, depth, spread=False, normal=None):
    """The solids an emboss (depth > 0) adds or an engrave (depth < 0) removes."""
    if not profile_faces:
        raise ValueError("The profile has no closed shapes to emboss")
    if is_round(face):
        return _wrap_round(profile_faces, face, depth, spread, normal)
    if is_flat(face):
        return _straight(profile_faces, face, depth)
    if is_sphere(face):
        return _project_sphere(profile_faces, face, depth, spread, normal)
    raise ValueError(FACE_MSG)


def apply(shape, profile_faces, face, depth, engrave, spread=False, normal=None):
    """The part with the profile embossed on (or engraved into) the face; refused when letters hang off it. An
    engrave may go right through a thin wall: the loose letter middles are dropped."""
    if depth <= 0:
        raise ValueError("Depth must be more than 0")
    cut = tools(profile_faces, face, -depth if engrave else depth, spread, normal)
    before = len(shape.Solids)
    result = shape.cut(cut) if engrave else shape.fuse(cut)
    result = result.removeSplitter()
    if engrave and len(result.Solids) > before:
        # cut right through a thin wall (a stencil): the middles of O, A, D come loose — they would fall out; the part
        # keeps its own pieces, the largest ones
        keep = sorted(result.Solids, key=lambda x: x.Volume, reverse=True)[:before]
        result = keep[0] if len(keep) == 1 else Part.makeCompound(keep)
    if not result.isValid() or len(result.Solids) != before:
        raise ValueError(OFF_MSG)
    if engrave and abs(result.Volume - shape.Volume) < 1e-9:
        raise ValueError(OFF_MSG)
    return result
