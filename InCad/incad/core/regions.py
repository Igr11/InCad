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


def _guides(sk):
    """Geometry indexes that are guides, not profile lines: a sketch pattern's path (Inventor: it never splits an
    area — a path through a row of polygons cut each one in pieces)."""
    out = set()
    try:
        from incad.core import sketch_patterns as sp
        for rec in sp.records(sk):
            for gid in rec.get("path", []) or []:
                i = sp.index_of(sk, gid)
                if i is not None:
                    out.add(i)
    except Exception:
        pass
    return out


def _profile_edges(sk):
    """The sketch's normal geometry as edges in its own coordinates, guides left out."""
    guides = _guides(sk)
    if not guides:
        return _local_shape(sk).Edges
    edges = []
    for i, g in enumerate(sk.Geometry):
        if i in guides or sk.getConstruction(i) or type(g).__name__ == "Point":
            continue
        try:
            edges.append(g.toShape())
        except Exception:
            pass
    return edges


def islands(faces):
    """True when the areas are separate (none touches another): they can all be one profile, as FreeCAD's Pad
    takes every closed shape of a plain sketch."""
    for i, a in enumerate(faces):
        for b in faces[i + 1:]:
            try:
                if a.distToShape(b)[0] < 1e-6:
                    return False
            except Exception:
                return False
    return len(faces) > 1


def regions(sk):
    """The bounded areas of the sketch (faces in the sketch's own coordinates, z = 0), largest first."""
    edges = _profile_edges(sk)
    if not edges:
        return []
    bb = Part.Compound(edges).BoundBox
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
    """The area's closed loops only: a line that dangles inside an area is no part of its outline (FreeCAD keeps
    it on the split face as an open wire)."""
    geos = []
    for wire in face.Wires:
        if not wire.isClosed() or len(wire.Edges) < 1:
            continue
        seen = []
        for e in wire.Edges:
            if any(e.isSame(o) for o in seen):
                continue  # an edge walked twice (both sides of a dangling line)
            seen.append(e)
            geos.append(_geometry(e))
    return geos


def _attach_like(profile, source):
    profile.AttachmentSupport = source.AttachmentSupport
    profile.MapMode = source.MapMode
    profile.AttachmentOffset = source.AttachmentOffset
    if source.MapMode == "Deactivated":
        profile.Placement = source.Placement


def fill(profile, faces):
    profile.deleteAllGeometry()
    geos = []
    for face in (faces if isinstance(faces, (list, tuple)) else [faces]):
        geos += outline(face)
    profile.addGeometry(geos)


def make_profile(doc, body, source, face):
    """A hidden profile sketch for one area of `source` (or several separate ones: a list), kept in step with it
    (see update)."""
    sk = body.newObject("Sketcher::SketchObject", source.Name + "Area")
    sk.Label = source.Label + " area"
    _attach_like(sk, source)
    sk.addProperty("App::PropertyString", REGION, "InCad", "The sketch and area this profile is built from")
    sk.setPropertyStatus(REGION, "Hidden")
    faces = face if isinstance(face, (list, tuple)) else [face]
    pts = [inner_point(f) for f in faces]
    data = {"source": source.Name, "point": [pts[0].x, pts[0].y]}
    if len(pts) > 1:
        data["points"] = [[p.x, p.y] for p in pts]
    setattr(sk, REGION, json.dumps(data))
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
    faces = []
    for x, y in data.get("points") or [data["point"]]:
        face = region_at(source, App.Vector(x, y, 0))
        if face is None:
            return False
        faces.append(face)
    _attach_like(profile, source)
    fill(profile, faces)
    return True


def users(profile):
    """The features built on this area copy (none: an orphan, its feature deleted outside InCad)."""
    out = []
    for o in profile.InList:
        prof = getattr(o, "Profile", None)
        prof = prof[0] if isinstance(prof, (tuple, list)) and prof else prof
        if prof is profile:
            out.append(o)
    return out


def follow(source, warned):
    """Bring the area copies of `source` in step with it; returns the warnings to show. A lost area is reported
    once (its name stays in `warned` until the area is back), with the features that use it; an orphan copy is
    never reported."""
    out = []
    for p in profiles_of(source):
        if update(p):
            warned.discard(p.Name)
            continue
        who = users(p)
        if not who or p.Name in warned:
            continue
        warned.add(p.Name)
        out.append("The area of %s used by %s is gone: it keeps its previous outline"
                   % (source.Label, ", ".join(o.Label for o in who)))
    return out


def purge_orphans(doc):
    """Remove the area copies no feature uses (left behind when a feature was deleted outside InCad); the
    user's sketches stay. Returns how many went."""
    gone = 0
    for p in [o for o in doc.Objects if is_profile(o) and not users(o)]:
        body = p.getParentGeoFeatureGroup()
        if body is not None:
            body.removeObject(p)
        doc.removeObject(p.Name)
        gone += 1
    return gone
