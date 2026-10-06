"""Section view plane from a selection: three points, a flat face or a work/origin plane (XZ when nothing)."""
import FreeCAD as App


def _rotation_to(normal):
    return App.Rotation(App.Vector(0, 0, 1), normal)


def placement(pairs):
    """Placement whose Z is the section normal, from resolved (obj, sub) picks."""
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
