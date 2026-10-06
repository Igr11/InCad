"""Inventor profiles: sketch lines may cross; the areas between them are what gets extruded. An area becomes a
hidden profile sketch (a copy of the area's outline on the source sketch's plane) that is rebuilt whenever the
source sketch changes, choosing the area that contains the remembered pick point."""
import json

import FreeCAD as App
import Part

REGION = "InCadRegion"   # on a profile sketch: {"source": sketch name, "point": [x, y]} (sketch coordinates)
MARGIN = 10.0


def _local_shape(sk):
    sh = sk.Shape.copy()
    sh.Placement = App.Placement()  # the sketch's own coordinates
    return sh


def needs_regions(sk):
    """FreeCAD's Pad can't use this sketch as it is (lines cross or end mid-way — an open wire — or its closed
    wires make no face): the areas between the lines are the profiles instead."""
    try:
        sh = _local_shape(sk)
        if not sh.Edges:
            return False
        if any(not w.isClosed() for w in sh.Wires):
            return True
        Part.makeFace(sh.Wires, "Part::FaceMakerBullseye")
        return False
    except Exception:
        return True


def regions(sk):
    """The bounded areas of the sketch (faces in the sketch's own coordinates, z = 0), largest first."""
    sh = _local_shape(sk)
    edges = sh.Edges
    if not edges:
        return []
    bb = sh.BoundBox
    big = Part.makePlane(bb.XLength + 2 * MARGIN, bb.YLength + 2 * MARGIN,
                         App.Vector(bb.XMin - MARGIN, bb.YMin - MARGIN, 0))
    try:
        fused, _ = big.generalFuse(edges)
    except Exception:
        return []
    out = []
    for f in fused.Faces:
        b = f.BoundBox
        if b.XMin > bb.XMin - MARGIN / 2 and b.XMax < bb.XMax + MARGIN / 2 and \
                b.YMin > bb.YMin - MARGIN / 2 and b.YMax < bb.YMax + MARGIN / 2:
            out.append(f)
    return sorted(out, key=lambda f: -f.Area)


def to_local(sk, point):
    """A global point (a 3D click) in the sketch's coordinates."""
    p = sk.getGlobalPlacement().inverse().multVec(point)
    return App.Vector(p.x, p.y, 0)


def region_at(sk, local_point, faces=None):
    for f in (regions(sk) if faces is None else faces):
        if f.isInside(App.Vector(local_point.x, local_point.y, 0), 1e-6, True):
            return f
    return None


def inner_point(face):
    """A point inside the face (its centre of mass when that is inside, else a point near the first vertex)."""
    c = face.CenterOfMass
    if face.isInside(c, 1e-6, True):
        return App.Vector(c.x, c.y, 0)
    s = face.Surface
    u0, u1, v0, v1 = face.ParameterRange
    for i in range(1, 10):
        for j in range(1, 10):
            p = s.value(u0 + (u1 - u0) * i / 10.0, v0 + (v1 - v0) * j / 10.0)
            if face.isInside(p, 1e-6, True):
                return App.Vector(p.x, p.y, 0)
    return App.Vector(c.x, c.y, 0)


def _geometry(edge):
    """Sketch geometry for one edge of an area (lines, arcs, circles; anything else as a B-spline)."""
    curve = edge.Curve
    if curve.TypeId == "Part::GeomLine":
        return Part.LineSegment(edge.Vertexes[0].Point, edge.Vertexes[-1].Point)
    if curve.TypeId == "Part::GeomCircle":
        if edge.isClosed():
            return Part.Circle(curve.Center, App.Vector(0, 0, 1), curve.Radius)
        a, b = edge.FirstParameter, edge.LastParameter
        return Part.ArcOfCircle(edge.valueAt(a), edge.valueAt((a + b) / 2), edge.valueAt(b))
    return curve.toBSpline(edge.FirstParameter, edge.LastParameter)


def outline(face):
    geos = []
    for wire in face.Wires:
        for e in wire.Edges:
            geos.append(_geometry(e))
    return geos


def _attach_like(profile, source):
    profile.AttachmentSupport = source.AttachmentSupport
    profile.MapMode = source.MapMode
    profile.AttachmentOffset = source.AttachmentOffset
    if source.MapMode == "Deactivated":
        profile.Placement = source.Placement


def fill(profile, face):
    profile.deleteAllGeometry()
    profile.addGeometry(outline(face))


def make_profile(doc, body, source, face):
    """A hidden profile sketch for one area of `source`, kept in step with it (see update)."""
    sk = body.newObject("Sketcher::SketchObject", source.Name + "Area")
    sk.Label = source.Label + " area"
    _attach_like(sk, source)
    sk.addProperty("App::PropertyString", REGION, "InCad", "The sketch and area this profile is built from")
    sk.setPropertyStatus(REGION, "Hidden")
    p = inner_point(face)
    setattr(sk, REGION, json.dumps({"source": source.Name, "point": [p.x, p.y]}))
    fill(sk, face)
    sk.Visibility = False
    doc.recompute()
    return sk


def is_profile(obj):
    return hasattr(obj, REGION)


def source_of(profile):
    try:
        data = json.loads(getattr(profile, REGION) or "{}")
        return profile.Document.getObject(data.get("source", ""))
    except Exception:
        return None


def profiles_of(source):
    return [o for o in source.Document.Objects if is_profile(o) and source_of(o) is source]


def update(profile):
    """Rebuild the profile from its source's current areas: the one holding the remembered point. False when
    that area is gone (the profile is left as it was)."""
    source = source_of(profile)
    if source is None:
        return False
    data = json.loads(getattr(profile, REGION))
    x, y = data["point"]
    face = region_at(source, App.Vector(x, y, 0))
    if face is None:
        return False
    _attach_like(profile, source)
    fill(profile, face)
    return True
