"""Solids made of an STL's triangles (STL → STEP, a mesh turned into a solid): thousands of flat three-edged faces.
A Boolean with one can run for hours and freeze the program (the user's ProstoCAD stood 30 minutes on an AI's cut of
such a solid and had to be force quit), so Booleans refuse them with a way round. No FreeCAD import at module level:
usable from widget tests."""

LEAST = 2000  # faces: fewer is an ordinary part, however detailed
SHARE = 0.9   # of the faces looked at, at least this many flat triangles
LOOK = 400    # faces looked at (evenly spread): counting them all took long on big meshes


def is_faceted(shape, least=LEAST):
    """True for a shape of at least `least` faces that are nearly all flat triangles."""
    try:
        faces = shape.Faces
    except Exception:
        return False
    n = len(faces)
    if n < least:
        return False
    step = max(1, n // LOOK)
    seen = flat = 0
    for f in faces[::step]:
        seen += 1
        try:
            if len(f.Edges) == 3 and f.Surface.TypeId == "Part::GeomPlane":
                flat += 1
        except Exception:
            pass
    return seen > 0 and flat >= SHARE * seen


def refusal(label, shape):
    return ("%s is made of an STL's triangles (%d faces): a Boolean with it can run for hours and freeze the program. "
            "Rebuild it as features first (Smooth, or by hand from sections), then combine."
            % (label, len(shape.Faces)))
