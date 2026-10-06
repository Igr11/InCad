"""Section view plane from a selection: three points, a flat face or a work/origin plane (XZ when nothing)."""
import FreeCAD as App


def _rotation_to(normal):
    return App.Rotation(App.Vector(0, 0, 1), normal)


def _usable(obj, sub):
    if sub:
        return sub.startswith(("Vertex", "Face"))
    return obj.TypeId in ("App::Plane", "PartDesign::Plane")


def placement(pairs):
    """Placement whose Z is the section normal, from resolved (obj, sub) picks."""
    pairs = [(o, s) for o, s in pairs if _usable(o, s)]  # edges, whole solids… can't define a plane: ignored
    if not pairs:
        return App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), -90))  # XZ through the origin
    shapes = [o.getSubObject(s) if s else getattr(o, "Shape", None) for o, s in pairs]
    if len(pairs) == 3 and all(sh is not None and sh.ShapeType == "Vertex" for sh in shapes):
        a, b, c = (sh.Point for sh in shapes)
        n = (b - a).cross(c - a)
        if n.Length < 1e-9:
            raise ValueError("Pick three different points that are not in a line")
        n.normalize()
        return App.Placement(a, _rotation_to(n))
    if len(pairs) == 1:
        sh = shapes[0]
        face = sh if sh is not None and sh.ShapeType == "Face" else \
            (sh.Faces[0] if sh is not None and sh.Faces and len(sh.Faces) == 1 else None)
        if face is not None and face.Surface.TypeId == "Part::GeomPlane":
            return App.Placement(face.CenterOfMass, _rotation_to(face.normalAt(0, 0)))
    raise ValueError("For a section, select three points, a flat face or a plane (or nothing for XZ)")


def adjusted(base, offset=0.0, flip=False):
    """`base` moved `offset` along its normal; flipped = the other side is cut away."""
    normal = base.Rotation.multVec(App.Vector(0, 0, 1))
    rot = base.Rotation.multiply(App.Rotation(App.Vector(1, 0, 0), 180)) if flip else base.Rotation
    return App.Placement(base.Base + normal * offset, rot)


def through_points(a, b, c):
    n = (b - a).cross(c - a)
    if n.Length < 1e-9:
        raise ValueError("Pick three different points that are not in a line")
    n.normalize()
    return App.Placement(a, _rotation_to(n))


def snap_points(shape):
    """Points worth cutting through: corners, edge middles, circle/arc centres (no duplicates)."""
    out = []

    def add(kind, p):
        if not any((p - q).Length < 1e-6 for _, q in out):
            out.append((kind, App.Vector(p)))
    for v in shape.Vertexes:
        add("corner", v.Point)
    for e in shape.Edges:
        if e.Curve.TypeId == "Part::GeomCircle":
            add("centre", e.Curve.Center)
        try:
            add("middle", e.valueAt((e.FirstParameter + e.LastParameter) / 2.0))
        except Exception:
            pass
    return out


def purge_markers(doc):
    """Remove section markers an earlier InCad build left in the file (Part::Feature balls outside any body,
    named MarkN with a Corner/Middle/Centre label). Returns how many were removed."""
    import re
    gone = 0
    for o in list(doc.Objects):
        if o.TypeId == "Part::Feature" and re.match(r"^Mark\d+$", o.Name) and \
                re.match(r"^(Corner|Middle|Centre) \d+$", o.Label) and o.getParentGeoFeatureGroup() is None \
                and not o.InList:
            doc.removeObject(o.Name)
            gone += 1
    return gone
