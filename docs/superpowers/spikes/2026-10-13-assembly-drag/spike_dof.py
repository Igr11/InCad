import os, sys, tempfile, shutil, json
repo = os.environ["INCAD_REPO"]
sys.path.insert(0, os.path.join(repo, "InCad")); sys.path.insert(0, os.path.join(repo, "tests"))
import FreeCAD as App
from headless.test_assembly import save_part
from headless import util
from incad.core import assembly, document
from incad.features import constraints as C

out = {}
d0 = tempfile.mkdtemp()
pd, plate = save_part(d0, "Plate", 40, 30, 10)
bd, block = save_part(d0, "Block", 10, 10, 10)
d = util.new_doc("Pin"); body = document.make_part(d)
cyl = body.newObject("PartDesign::AdditiveCylinder", "Pin"); cyl.Radius, cyl.Height = 3, 20; body.Tip = cyl; d.recompute()
pin = os.path.join(d0, "Pin.FCStd"); d.saveAs(pin)
hb = document.primary_body(pd)
hole = hb.newObject("PartDesign::SubtractiveCylinder", "HoleCyl"); hole.Radius, hole.Height = 3, 10
hole.Placement = App.Placement(App.Vector(20, 15, 0), App.Rotation()); hb.Tip = hole; pd.recompute(); pd.save()

doc = App.newDocument("Asm"); doc.UndoMode = 1
assembly.make_assembly(doc, "mm"); doc.saveAs(os.path.join(d0, "Asm.FCStd"))
a = assembly.place(doc, plate); b = assembly.place(doc, block); p = assembly.place(doc, pin)
doc.recompute()
asm = assembly.assembly_of(doc)

STEP, TURN = 0.5, 1.0

def probe(link):
    """6 small moves; per move: share of the move the solver keeps (1 = free, 0 = blocked)."""
    import numpy  # noqa
    c = link.Shape.BoundBox.Center
    start = App.Placement(link.Placement)
    kept = []
    vecs = []
    for i in range(6):
        axis = App.Vector(*[1 if k == i % 3 else 0 for k in range(3)])
        if i < 3:
            delta = App.Placement(axis * STEP, App.Rotation())
        else:
            delta = App.Placement(App.Vector(), App.Rotation(axis, TURN), c)
        link.Placement = delta.multiply(start)
        asm.solve(); doc.recompute()
        after = link.Placement
        moved = after.Base - start.Base
        rel = after.multiply(start.inverse())
        ang = rel.Rotation.Angle * 180 / 3.14159265
        ax = rel.Rotation.Axis
        twist = [ax.x * ang, ax.y * ang, ax.z * ang]
        # motion of the part centre and the turn, normalised by the step
        v = [moved.x / STEP, moved.y / STEP, moved.z / STEP] + [t / TURN for t in twist]
        vecs.append(v)
        kept.append(round(v[i], 3))
        link.Placement = start
        asm.solve(); doc.recompute()
    import numpy as np
    rank = int(np.linalg.matrix_rank(np.array(vecs), tol=0.2))
    return kept, rank

def face_z(link, z):
    return [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - z) < 1e-6][0]
def face_x(link, x):
    return [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.x - x) < 1e-6][0]
def face_y(link, y):
    return [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.y - y) < 1e-6][0]

try:
    out["block_free"] = probe(b)
except Exception as e:
    out["block_free"] = "ERR %r" % e
C.MATE.create(doc, None, None, dict(C.MATE.defaults(doc, None), first="%s:Face%d" % (a.Name, face_z(a, 10)),
                                    second="%s:Face%d" % (b.Name, face_z(b, 0))))
out["block_mate"] = probe(b)
C.FLUSH.create(doc, None, None, dict(C.FLUSH.defaults(doc, None), first="%s:Face%d" % (a.Name, face_x(a, 0)),
                                     second="%s:Face%d" % (b.Name, face_x(b, 0))))
out["block_mate_flush"] = probe(b)
C.FLUSH.create(doc, None, None, dict(C.FLUSH.defaults(doc, None), first="%s:Face%d" % (a.Name, face_y(a, 0)),
                                     second="%s:Face%d" % (b.Name, face_y(b, 0))))
out["block_mate_flush_flush"] = probe(b)
mouth = [i + 1 for i, e in enumerate(a.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
         and abs(e.Curve.Radius - 3) < 1e-6 and abs(e.Curve.Center.z - 10) < 1e-6][0]
end = [i + 1 for i, e in enumerate(p.LinkedObject.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
       and abs(e.Curve.Center.z) < 1e-6][0]
C.INSERT.create(doc, None, None, dict(C.INSERT.defaults(doc, None), first="%s:Edge%d" % (p.Name, end),
                                      second="%s:Edge%d" % (a.Name, mouth)))
out["pin_insert"] = probe(p)
out["plate_grounded"] = probe(a)
import time
t = time.time(); probe(p); out["probe_seconds"] = round(time.time() - t, 3)
print("SPIKE", json.dumps(out))
shutil.rmtree(d0, ignore_errors=True)
