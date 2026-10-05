"""Helpers that build small real models for headless tests."""
import FreeCAD as App
import Part
import Sketcher


def new_doc(name="T"):
    doc = App.newDocument(name)
    doc.UndoMode = 1
    return doc


def xy_plane(body):
    return [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]


def add_rect_sketch(body, w=20, h=10, name="Sketch"):
    s = body.newObject("Sketcher::SketchObject", name)
    s.AttachmentSupport = [(xy_plane(body), "")]
    s.MapMode = "FlatFace"
    pts = [App.Vector(0, 0, 0), App.Vector(w, 0, 0), App.Vector(w, h, 0), App.Vector(0, h, 0)]
    for i in range(4):
        s.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    for i in range(4):
        s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    return s


def add_pad(body, sketch, length=5, name="Pad"):
    pad = body.newObject("PartDesign::Pad", name)
    pad.Profile = sketch
    pad.Length = length
    return pad


def padded_part(doc, length=10, incad=False):
    """A body with a 20x10 rectangle padded by `length`, committed as one undo step."""
    doc.openTransaction("setup")
    if incad:
        from incad.core import document  # Task 4; Task 3's tests only use incad=False
        body = document.make_part(doc)
    else:
        body = doc.addObject("PartDesign::Body", "Body")
    sketch = add_rect_sketch(body)
    pad = add_pad(body, sketch, length)
    body.Tip = pad
    doc.recompute()
    doc.commitTransaction()
    return body, pad
