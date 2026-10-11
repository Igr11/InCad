# Move Solid, Boolean Keep Tool, Clearance Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a solid into position as an editable history step (From → To snap, pivot, offset, rotate), let a Boolean
keep or use up its tool, and say how each clearance is measured.

**Architecture:** Pure placement maths in `incad/core/move_math.py` (snap pairs, pivot frames, composition) under a new
feature kind `incad/features/move.py` whose step is a `PartDesign::FeaturePython` with a proxy (`MoveFeature`) that
bakes `Snap ∘ pivot-frame offset/rotation` into an exact rigid copy of the base shape (probed 2026-10-11:
`shape.transformShape(m, True)` keeps true cylinders/planes and exact volumes; `Shape.Placement` is reset on
assignment, so the move must be baked). Offsets, angles and the gap are feature properties bound to model parameters,
so formulas drive them live; the snap and the pivot frame are stored as Placement properties (applied once). Boolean
gets a `keep_tool` field; the tree shows used-up tools under their Boolean.

**Tech Stack:** FreeCAD 1.1.3 (PartDesign, Part), PySide6 via `incad.qt`, unittest (no pytest in FreeCAD's Python).

**Spec:** `docs/superpowers/specs/2026-10-11-incad-move-solid-keep-tool-design.md`

## Global Constraints

- Everything in the repo in English (code, comments, UI text, docs); the user is answered in Russian in chat.
- Dialog order: Snap → Pivot → Offset → Rotate. Snap pairs exactly as the spec's table (six rows).
- Keep tool **off** when the dialog opens; old Booleans (no setting) read as off.
- Clearance labels: Boolean "Clearance (per side)", Thread and Hole ▸ Tapped "Print clearance (on diameter)" — meaning
  unchanged.
- Snaps and the pivot are applied once (stored as numbers); offsets/angles/gap are model parameters.
- Tests: `tests/run_headless.sh <file>`, `tests/run_widgets.sh <file>`, `tests/run_gui.sh tests/gui/<file>` (tell the
  user to keep hands off). Only affected files per task; full suites once before the last commit.
- Branch: `move-solid`, cut from `main` after `constraints-window` is merged (else from `constraints-window`).
- Every new build: version bump + a section in `scripts/dist/CHANGES.txt` and `CHANGES_ru.txt` (Improvements / Bug fixes).

## Review Focus

1. Snap with parallel or anti-parallel directions (rotation of 0° or 180°: `App.Rotation(a, b)` with b = −a) must give a
   valid 180° turn, not a no-op or NaN. → Task 1 test `test_antiparallel_turns_half`.
2. Editing a Move after the solid's earlier features changed (the snap was applied once): the solid stays where the
   stored placement puts it, no error. → Task 2 test `test_snap_is_stored_not_followed`.
3. A Move on a solid that is a used-up Boolean tool: the Boolean follows (the cut moves). → Task 4 test
   `test_moving_a_used_up_tool_moves_the_cut`.
4. Deleting the Move (or the solid's last feature before it) leaves the solid valid and the Tip right. → Task 2 test
   `test_delete_puts_the_solid_back`.
5. Opening a file with a Move: the proxy is found (module path `incad.features.move`) and the shape recomputes.
   → Task 2 test `test_save_and_reopen`.

---

## File structure

- Create `InCad/incad/core/move_math.py` — pure placement maths: element classification, the six snap pairs, pivot
  frames, composition. FreeCAD `App`/`Part` types only, no document changes.
- Create `InCad/incad/features/move.py` — the Move kind (fields, create/read/update, claims, summary) and the proxy class
  `MoveFeature` (properties, `execute`).
- Modify `InCad/incad/features/__init__.py` — register `move` in `kinds()`.
- Modify `InCad/incad/ui/feature_session.py` — the pick filter `solid_element` joins `_GEOMETRY` (picks on the unmoved
  base, base shown while picking).
- Modify `InCad/incad/features/common.py` — `accepts("solid_element", …)`.
- Modify `InCad/incad/actions.py`, `InCad/incad/ui/ribbon_layout.py`, `InCad/incad/ui/marking_layout.py`,
  `tools/make_icons.py` — command `feature.move_solid`, icon `move_solid`.
- Modify `InCad/incad/features/combine.py` — `keep_tool`.
- Modify `InCad/incad/core/tree.py` — used-up tools under their Boolean, out of Solid Bodies and the main history.
- Modify `InCad/incad/features/thread.py`, `InCad/incad/features/hole.py` — labels.
- Tests: `tests/headless/test_move_math.py`, `tests/headless/test_move.py`, `tests/headless/test_combine.py` (add),
  `tests/headless/test_tree.py` (add), `tests/widgets/test_actions.py` (ids), `tests/gui/test_move_solid.py`.

---

### Task 1: Placement maths (snap pairs, pivot frames, composition)

**Files:**
- Create: `InCad/incad/core/move_math.py`
- Test: `tests/headless/test_move_math.py`

**Interfaces:**
- Produces:
  - `classify(shape) -> Elem` where `Elem` is a namedtuple `(kind, point, direction)`, kind ∈ `"point"`, `"line"`,
    `"circle"`, `"plane"`, `"cylinder"`; `shape` is a `Part.Vertex`/`Part.Edge`/`Part.Face`. Raises `ValueError` for
    other elements ("Pick a point, a straight or round edge, a flat face or a cylinder").
  - `snap(src: Elem, dst: Elem, flip=False, gap=0.0, src_shape=None, dst_shape=None) -> App.Placement` (moves the
    solid so src meets dst; `dst_shape` is used by point → edge/face for the nearest spot). Refusal: `ValueError`
    "Pick matching items: point → point, edge or face; circle → circle; edge → edge; face → face; cylinder → cylinder".
  - `pivot_frame(elem: Elem | None, centre: App.Vector, world_axes=False) -> App.Placement`
  - `compose(snap_pl, frame, offset: App.Vector, angles_deg: (rx, ry, rz)) -> App.Placement`
    (total = M · snap where M = F' · T(offset) · R(rz, ry, rx) · F'⁻¹ and F' = snap · frame).

- [ ] **Step 1: Write the failing tests** `tests/headless/test_move_math.py`

```python
"""Move Solid maths: what an element is, the six snap pairs, pivot frames, offset/rotation in the pivot's axes."""
import math
import unittest

import FreeCAD as App
import Part
from incad.core import move_math as mm

V = App.Vector


def close(a, b, tol=1e-7):
    return (a - b).Length < tol


class ClassifyTest(unittest.TestCase):
    def test_kinds(self):
        box = Part.makeBox(10, 10, 10)
        cyl = Part.makeCylinder(3, 10)
        self.assertEqual(mm.classify(box.Vertexes[0]).kind, "point")
        self.assertEqual(mm.classify(box.Edges[0]).kind, "line")
        self.assertEqual(mm.classify(box.Faces[0]).kind, "plane")
        circle = [e for e in cyl.Edges if e.Curve.TypeId == "Part::GeomCircle"][0]
        self.assertEqual(mm.classify(circle).kind, "circle")
        side = [f for f in cyl.Faces if f.Surface.TypeId == "Part::GeomCylinder"][0]
        e = mm.classify(side)
        self.assertEqual(e.kind, "cylinder")
        self.assertTrue(close(e.point, V(0, 0, 0)) or abs(e.point.x) + abs(e.point.y) < 1e-7)

    def test_a_sphere_is_refused(self):
        with self.assertRaises(ValueError):
            mm.classify(Part.makeSphere(2).Faces[0])


class SnapTest(unittest.TestCase):
    def test_point_to_point(self):
        pl = mm.snap(mm.Elem("point", V(1, 2, 3), None), mm.Elem("point", V(5, 5, 5), None))
        self.assertTrue(close(pl.multVec(V(1, 2, 3)), V(5, 5, 5)))

    def test_point_onto_a_face_lands_on_the_nearest_spot(self):
        face = Part.makeBox(10, 10, 1).Faces[5]  # the top, z = 1
        dst = mm.classify(face)
        pl = mm.snap(mm.Elem("point", V(3, 4, 7), None), dst, dst_shape=face)
        self.assertTrue(close(pl.multVec(V(3, 4, 7)), V(3, 4, 1)))

    def test_insert_circle_into_circle_with_gap_and_flip(self):
        src = mm.Elem("circle", V(0, 0, 0), V(1, 0, 0))   # a pin's end circle, axis along X
        dst = mm.Elem("circle", V(10, 10, 5), V(0, 0, 1))  # a hole's edge, axis along Z
        pl = mm.snap(src, dst)
        self.assertTrue(close(pl.multVec(V(0, 0, 0)), V(10, 10, 5)))
        self.assertTrue(close(pl.Rotation.multVec(V(1, 0, 0)), V(0, 0, 1)))
        pl = mm.snap(src, dst, flip=True, gap=2.0)
        self.assertTrue(close(pl.Rotation.multVec(V(1, 0, 0)), V(0, 0, -1)))
        self.assertTrue(close(pl.multVec(V(0, 0, 0)), V(10, 10, 7)))  # the gap along the target axis

    def test_collinear_edges(self):
        src = mm.Elem("line", V(0, 0, 0), V(0, 1, 0))
        dst = mm.Elem("line", V(5, 5, 5), V(1, 0, 0))
        pl = mm.snap(src, dst)
        self.assertTrue(close(pl.multVec(V(0, 0, 0)), V(5, 5, 5)))
        self.assertTrue(close(pl.Rotation.multVec(V(0, 1, 0)), V(1, 0, 0)))

    def test_mate_and_flush_faces(self):
        src = mm.Elem("plane", V(0, 0, 0), V(0, 0, 1))   # the solid's top face, out = +Z
        dst = mm.Elem("plane", V(3, 3, 10), V(0, 0, 1))  # the part's top, out = +Z
        pl = mm.snap(src, dst)  # mate: facing each other
        self.assertTrue(close(pl.Rotation.multVec(V(0, 0, 1)), V(0, 0, -1)))
        self.assertAlmostEqual(pl.multVec(V(0, 0, 0)).z, 10.0, places=7)
        pl = mm.snap(src, dst, flip=True, gap=1.5)  # flush, 1.5 above
        self.assertTrue(close(pl.Rotation.multVec(V(0, 0, 1)), V(0, 0, 1)))
        self.assertAlmostEqual(pl.multVec(V(0, 0, 0)).z, 11.5, places=7)

    def test_concentric_cylinders_keep_the_position_along_the_axis(self):
        src = mm.Elem("cylinder", V(0, 0, 4), V(0, 0, 1))
        dst = mm.Elem("cylinder", V(20, 0, 0), V(0, 0, 1))
        pl = mm.snap(src, dst)
        self.assertTrue(close(pl.multVec(V(0, 0, 4)), V(20, 0, 4)))

    def test_antiparallel_turns_half(self):
        src = mm.Elem("circle", V(0, 0, 0), V(0, 0, 1))
        dst = mm.Elem("circle", V(0, 0, 0), V(0, 0, -1))
        pl = mm.snap(src, dst)
        self.assertTrue(close(pl.Rotation.multVec(V(0, 0, 1)), V(0, 0, -1)))
        self.assertFalse(any(math.isnan(x) for x in pl.Rotation.Q))

    def test_mismatched_pairs_are_refused(self):
        with self.assertRaises(ValueError) as ctx:
            mm.snap(mm.Elem("circle", V(0, 0, 0), V(0, 0, 1)), mm.Elem("plane", V(0, 0, 0), V(0, 0, 1)))
        self.assertIn("Pick matching items", str(ctx.exception))


class PivotTest(unittest.TestCase):
    def test_frames(self):
        c = V(1, 1, 1)
        self.assertTrue(close(mm.pivot_frame(None, c).Base, c))
        edge = mm.pivot_frame(mm.Elem("line", V(5, 0, 0), V(0, 1, 0)), c)
        self.assertTrue(close(edge.Rotation.multVec(V(1, 0, 0)), V(0, 1, 0)))  # X along the edge
        face = mm.pivot_frame(mm.Elem("plane", V(0, 0, 9), V(1, 0, 0)), c)
        self.assertTrue(close(face.Rotation.multVec(V(0, 0, 1)), V(1, 0, 0)))  # Z out of the face
        world = mm.pivot_frame(mm.Elem("plane", V(0, 0, 9), V(1, 0, 0)), c, world_axes=True)
        self.assertTrue(close(world.Base, V(0, 0, 9)) and close(world.Rotation.multVec(V(0, 0, 1)), V(0, 0, 1)))

    def test_hinge_about_an_edge_keeps_the_edge(self):
        frame = mm.pivot_frame(mm.Elem("line", V(0, 0, 0), V(1, 0, 0)), V(5, 5, 5))
        total = mm.compose(App.Placement(), frame, V(0, 0, 0), (90, 0, 0))
        self.assertTrue(close(total.multVec(V(7, 0, 0)), V(7, 0, 0)))   # on the hinge: stays
        self.assertTrue(close(total.multVec(V(0, 1, 0)), V(0, 0, 1)))   # off it: turns about X

    def test_offset_along_the_face_normal(self):
        frame = mm.pivot_frame(mm.Elem("plane", V(0, 0, 0), V(1, 0, 0)), V(0, 0, 0))
        total = mm.compose(App.Placement(), frame, V(0, 0, 3), (0, 0, 0))
        self.assertTrue(close(total.multVec(V(0, 0, 0)), V(3, 0, 0)))  # Z of the pivot = the face normal

    def test_the_pivot_rides_with_the_snap(self):
        snap_pl = App.Placement(V(10, 0, 0), App.Rotation())
        frame = mm.pivot_frame(mm.Elem("point", V(0, 0, 0), None), V(0, 0, 0))
        total = mm.compose(snap_pl, frame, V(0, 0, 0), (0, 0, 90))
        self.assertTrue(close(total.multVec(V(0, 0, 0)), V(10, 0, 0)))  # turned about the moved pivot
        self.assertTrue(close(total.multVec(V(1, 0, 0)), V(10, 1, 0)))
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_headless.sh test_move_math.py`
Expected: ERROR `cannot import name 'move_math' from 'incad.core'`

- [ ] **Step 3: Write the implementation** `InCad/incad/core/move_math.py`

```python
"""Move Solid maths: what a picked element is, the placement that snaps one element onto another, the pivot's frame
and the offset/rotation in that frame. Pure geometry: FreeCAD vectors and placements, no document changes."""
import collections

import FreeCAD as App
import Part

Elem = collections.namedtuple("Elem", "kind point direction")
_MATCH = "Pick matching items: point → point, edge or face; circle → circle; edge → edge; face → face; " \
         "cylinder → cylinder"


def _unit(v):
    v = App.Vector(v)
    return v.normalize() if v.Length > 1e-12 else v


def classify(shape):
    if shape.ShapeType == "Vertex":
        return Elem("point", App.Vector(shape.Point), None)
    if shape.ShapeType == "Edge":
        c = shape.Curve
        if c.TypeId in ("Part::GeomLine", "Part::GeomLineSegment"):
            a, b = shape.valueAt(shape.FirstParameter), shape.valueAt(shape.LastParameter)
            return Elem("line", (a + b) * 0.5, _unit(b - a))
        if c.TypeId in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
            return Elem("circle", App.Vector(c.Center), _unit(c.Axis))
    if shape.ShapeType == "Face":
        s = shape.Surface
        if s.TypeId == "Part::GeomPlane":
            u0, u1, v0, v1 = shape.ParameterRange
            return Elem("plane", App.Vector(shape.CenterOfMass), _unit(shape.normalAt((u0 + u1) / 2, (v0 + v1) / 2)))
        if s.TypeId == "Part::GeomCylinder":
            return Elem("cylinder", App.Vector(s.Center), _unit(s.Axis))
    raise ValueError("Pick a point, a straight or round edge, a flat face or a cylinder")


def _turn(a, b):
    """The rotation taking direction a to direction b (a half turn about any perpendicular when opposite)."""
    a, b = _unit(a), _unit(b)
    if (a + b).Length < 1e-9:
        perp = a.cross(App.Vector(1, 0, 0))
        if perp.Length < 1e-6:
            perp = a.cross(App.Vector(0, 1, 0))
        return App.Rotation(_unit(perp), 180)
    return App.Rotation(a, b)


def _about(rot, centre):
    """A placement that turns by rot about centre."""
    return App.Placement(centre - rot.multVec(centre), rot)


def snap(src, dst, flip=False, gap=0.0, src_shape=None, dst_shape=None):
    pair = (src.kind, dst.kind)
    if src.kind == "point" and dst.kind == "point" or pair in (("circle", "point"), ("line", "point")):
        return App.Placement(dst.point - src.point, App.Rotation())
    if src.kind == "point" and dst.kind in ("line", "circle", "plane", "cylinder"):
        if dst_shape is None:
            raise ValueError(_MATCH)
        nearest = dst_shape.distToShape(Part.Vertex(src.point))[1][0][0]
        return App.Placement(nearest - src.point, App.Rotation())
    if pair in (("circle", "circle"), ("line", "line"), ("cylinder", "cylinder"), ("plane", "plane")):
        if pair == ("plane", "plane"):  # faces face each other (mate) unless Flip (flush)
            target = dst.direction if flip else -dst.direction
        else:  # circles, edges, cylinders point the same way unless Flip
            target = -dst.direction if flip else dst.direction
        turned = _about(_turn(src.direction, target), src.point)
        p = turned.multVec(src.point)
        if pair == ("cylinder", "cylinder"):  # onto the target axis, keeping the position along it
            along = (p - dst.point).dot(dst.direction)
            shift = (dst.point + dst.direction * along) - p
        elif pair == ("plane", "plane"):  # onto the target plane only (in-plane position kept), then the gap
            shift = dst.direction * ((dst.point - p).dot(dst.direction) + gap)
            return App.Placement(shift, App.Rotation()).multiply(turned)
        else:
            shift = dst.point - p
        shift = shift + dst.direction * gap
        return App.Placement(shift, App.Rotation()).multiply(turned)
    raise ValueError(_MATCH)


def pivot_frame(elem, centre, world_axes=False):
    if elem is None:
        return App.Placement(App.Vector(centre), App.Rotation())
    rot = App.Rotation()
    if not world_axes:
        if elem.kind == "line":
            rot = _turn(App.Vector(1, 0, 0), elem.direction)
        elif elem.kind in ("circle", "plane", "cylinder"):
            rot = _turn(App.Vector(0, 0, 1), elem.direction)
    return App.Placement(App.Vector(elem.point), rot)


def compose(snap_pl, frame, offset, angles_deg):
    rx, ry, rz = angles_deg
    f = App.Placement(snap_pl).multiply(frame)
    local = App.Placement(App.Vector(offset), App.Rotation(rz, ry, rx))
    return f.multiply(local).multiply(f.inverse()).multiply(snap_pl)
```

A circle edge's `Curve.Axis` may point either way on a real solid (OpenCascade does not orient it by the material);
the Insert test in Task 2 shows which way the pin ends up — if it points into the part instead of out of the hole,
that is what Flip is for, and the test then states `flip=True` for that edge (record it as a ruling).

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_headless.sh test_move_math.py`
Expected: `OK` (14 tests)

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/move_math.py tests/headless/test_move_math.py
git commit -m "Move Solid maths: element kinds, the six snap pairs, pivot frames, offset/rotation in the pivot's axes"
```

---

### Task 2: The Move step (proxy feature) and the Move kind

**Files:**
- Create: `InCad/incad/features/move.py`
- Modify: `InCad/incad/features/__init__.py` (`kinds()`)
- Test: `tests/headless/test_move.py`

**Interfaces:**
- Consumes: `move_math.classify/snap/pivot_frame/compose` (Task 1)
- Produces:
  - `MoveFeature(obj)` proxy: properties `Snap` (`App::PropertyPlacement`), `Frame` (`App::PropertyPlacement`),
    `OffsetX/Y/Z` (`App::PropertyDistance`), `RotateX/Y/Z` (`App::PropertyAngle`), `Gap` (`App::PropertyDistance`);
    `execute` bakes `compose(Snap', Frame, offset, angles)` into an exact copy of `BaseFeature.Shape`.
    `Snap'` = `Snap` with the gap re-applied (the stored `Snap` is the zero-gap placement; `SnapAxis` vector property =
    the direction the gap moves along).
  - Kind module: `TITLE = "Move Solid"`, `ICON = "move_solid"`, `TYPES = ("PartDesign::FeaturePython",)`,
    `NEEDS_PROFILE = False`, `STRUCTURAL = ()`, `RECREATE_ON = ("solid",)`, `PROPS` (field → property), `FIELDS`,
    `claims(f)` (has `InCadMove`), `defaults`, `preselect(pairs)`, `create`, `read`, `update`, `param_names`, `_pad_of`.
  - Field keys: `solid` (pick `body`), `snap_from` (pick `solid_element`), `snap_to` (pick `element`), `flip` (bool),
    `gap` (value_length), `pivot` (pick `solid_element`), `world_axes` (bool), `dx`,`dy`,`dz` (value_length),
    `rx`,`ry`,`rz` (value_angle).

- [ ] **Step 1: Write the failing tests** `tests/headless/test_move.py`

```python
"""Move Solid: a history step that moves a solid's result (snap, pivot, offset, rotate), driven by parameters."""
import os
import tempfile
import unittest

import FreeCAD as App
import Part
from incad.core import document
from incad.features import combine, kind_for, move
from headless import util


class MoveTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Mv")
        self.part = document.make_part(self.doc)
        box = self.part.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 20
        self.part.Tip = box
        self.tool = document.new_solid(self.doc)
        pin = self.tool.newObject("PartDesign::AdditiveCylinder", "Pin")
        pin.Radius, pin.Height = 3, 40
        pin.Placement = App.Placement(App.Vector(-50, 0, -10), App.Rotation())
        self.tool.Tip = pin
        self.pin = pin
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def values(self, **kw):
        v = dict(move.defaults(self.doc, self.tool, None), solid=self.tool.Name)
        v.update(kw)
        return v

    def make(self, **kw):
        f = move.create(self.doc, self.tool, None, self.values(**kw))
        self.doc.recompute()
        return f

    def cut(self):
        c = combine.create(self.doc, self.part, None, dict(combine.defaults(self.doc, self.part), tools=self.tool.Name,
                                                           operation="cut", clearance="0 mm"))
        self.doc.recompute()
        return c

    def test_offset_moves_the_result_exactly_and_is_the_tip(self):
        f = self.make(dx="60 mm", dy="10 mm")
        self.assertIs(self.tool.Tip, f)
        self.assertIs(kind_for(f), move)
        self.cut()
        self.assertAlmostEqual(self.part.Shape.Volume, 8000 - 3.14159265 * 9 * 20, places=2)

    def test_insert_snap_circle_to_circle(self):
        hole = self.part.newObject("PartDesign::SubtractiveCylinder", "Hole")
        hole.Radius, hole.Height = 3, 20
        hole.Placement = App.Placement(App.Vector(10, 10, 0), App.Rotation())
        self.part.Tip = hole
        self.doc.recompute()
        src = next("Edge%d" % (i + 1) for i, e in enumerate(self.pin.Shape.Edges)
                   if e.Curve.TypeId == "Part::GeomCircle" and abs(e.Curve.Center.z + 10) < 1e-6)
        dst = next("Edge%d" % (i + 1) for i, e in enumerate(hole.Shape.Edges)
                   if e.Curve.TypeId == "Part::GeomCircle" and abs(e.Curve.Center.z - 20) < 1e-6
                   and abs(e.Curve.Radius - 3) < 1e-6)
        f = self.make(snap_from="%s:%s" % (self.pin.Name, src), snap_to="%s:%s" % (hole.Name, dst))
        bottom = min(f.Shape.Faces, key=lambda fc: fc.CenterOfMass.z)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMin, 20.0, places=6)  # the pin's end on the hole's top circle
        self.assertAlmostEqual(bottom.CenterOfMass.x, 10.0, places=6)

    def test_parameters_drive_it(self):
        from incad.core import model
        f = self.make(dx="60 mm")
        name = move.param_names(f)["dx"]
        model.set_model_parameter(self.doc, name, "70 mm")
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.XMin, -50 + 70 - 3, places=6)

    def test_hinge_rotation_about_an_edge(self):
        box2 = document.new_solid(self.doc)
        b = box2.newObject("PartDesign::AdditiveBox", "Plate")
        b.Length, b.Width, b.Height = 10, 2, 10
        box2.Tip = b
        self.doc.recompute()
        edge = next("Edge%d" % (i + 1) for i, e in enumerate(b.Shape.Edges)
                    if e.Curve.TypeId in ("Part::GeomLine", "Part::GeomLineSegment")
                    and abs(e.Vertexes[0].Point.z) < 1e-6 and abs(e.Vertexes[1].Point.z) < 1e-6
                    and abs(e.Vertexes[0].Point.y) < 1e-6 and abs(e.Vertexes[1].Point.y) < 1e-6)
        f = move.create(self.doc, box2, None, dict(move.defaults(self.doc, box2, None), solid=box2.Name,
                                                    pivot="%s:%s" % (b.Name, edge), rx="90 °"))
        self.doc.recompute()
        bb = f.Shape.BoundBox  # +90° about X through the bottom front edge: Y -> Z, Z -> -Y
        self.assertAlmostEqual(bb.ZMin, 0.0, places=6)
        self.assertAlmostEqual(bb.ZMax, 2.0, places=6)
        self.assertAlmostEqual(bb.YMin, -10.0, places=6)
        self.assertAlmostEqual(bb.YMax, 0.0, places=6)

    def test_snap_is_stored_not_followed(self):
        hole = self.part.newObject("PartDesign::SubtractiveCylinder", "Hole")
        hole.Radius, hole.Height = 3, 20
        self.part.Tip = hole
        self.doc.recompute()
        top = next("Edge%d" % (i + 1) for i, e in enumerate(hole.Shape.Edges)
                   if e.Curve.TypeId == "Part::GeomCircle" and abs(e.Curve.Center.z - 20) < 1e-6
                   and abs(e.Curve.Radius - 3) < 1e-6)
        src = next("Edge%d" % (i + 1) for i, e in enumerate(self.pin.Shape.Edges)
                   if e.Curve.TypeId == "Part::GeomCircle" and abs(e.Curve.Center.z + 10) < 1e-6)
        f = self.make(snap_from="%s:%s" % (self.pin.Name, src), snap_to="%s:%s" % (hole.Name, top))
        before = f.Shape.BoundBox
        hole.Placement = App.Placement(App.Vector(5, 0, 0), App.Rotation())
        self.doc.recompute()
        self.assertFalse("Invalid" in f.State)
        self.assertAlmostEqual(f.Shape.BoundBox.XMin, before.XMin, places=6)

    def test_delete_puts_the_solid_back(self):
        from incad.core import delete
        f = self.make(dx="60 mm")
        delete.delete(f)
        self.doc.recompute()
        self.assertIs(self.tool.Tip, self.pin)
        self.assertAlmostEqual(self.tool.Shape.BoundBox.XMin, -53.0, places=6)

    def test_end_of_part_rolls_it_back(self):
        f = self.make(dx="60 mm")
        document.set_end_of_part(self.tool, self.pin)
        self.assertAlmostEqual(self.tool.Shape.BoundBox.XMin, -53.0, places=6)
        document.set_end_of_part(self.tool, f)
        self.assertAlmostEqual(self.tool.Shape.BoundBox.XMin, 7.0, places=6)

    def test_save_and_reopen(self):
        f = self.make(dx="60 mm", rz="45 °")
        path = os.path.join(tempfile.mkdtemp(), "mv.FCStd")
        self.doc.saveAs(path)
        name = self.doc.Name
        App.closeDocument(name)
        self.doc = App.openDocument(path)
        g = self.doc.getObject(f.Name)
        g.touch()
        self.doc.recompute()
        self.assertFalse("Invalid" in g.State)
        self.assertIs(kind_for(g), move)
        self.assertEqual(move.read(self.doc, g)["dx"], "60 mm")

    def test_read_round_trip_and_a_second_move(self):
        f = self.make(dx="60 mm", rz="30 °", world_axes=True)
        v = move.read(self.doc, f)
        self.assertEqual((v["dx"], v["rz"], v["world_axes"]), ("60 mm", "30 °", True))
        g = self.make(dz="5 mm")
        self.assertIs(g.BaseFeature, f)
        self.assertIs(self.tool.Tip, g)

    def test_a_to_pick_on_the_moving_solid_is_refused(self):
        circle = next("Edge%d" % (i + 1) for i, e in enumerate(self.pin.Shape.Edges)
                      if e.Curve.TypeId == "Part::GeomCircle")
        with self.assertRaises(ValueError) as ctx:
            self.make(snap_from="%s:%s" % (self.pin.Name, circle), snap_to="%s:%s" % (self.pin.Name, circle))
        self.assertIn("another solid", str(ctx.exception))
        self.assertIs(self.tool.Tip, self.pin)
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_headless.sh test_move.py`
Expected: ERROR `cannot import name 'move' from 'incad.features'`

- [ ] **Step 3: Write the implementation** `InCad/incad/features/move.py`

```python
"""Move Solid (Inventor's Move Bodies, Fusion's Move with a pivot): a step at the end of a solid's history that moves
its result. The solid's own sketches and features stay where they are; the step bakes the placement into an exact
copy of the shape before it (Shape.Placement is reset when a feature's Shape is assigned).

Snap (From -> To) and the pivot are applied once and stored as placements; offsets, angles and the gap are feature
properties bound to model parameters. Picks are kept in InCadMove (JSON) only to show them on edit."""
import json

import FreeCAD as App

from incad.core import move_math as mm
from incad.features.common import Field, format_picks, parse_picks, resolve, value_param, value_text

TITLE = "Move Solid"
ICON = "move_solid"
TYPES = ("PartDesign::FeaturePython",)
NEEDS_PROFILE = False
STRUCTURAL = ()
RECREATE_ON = ("solid",)
_STORE = "InCadMove"
PROPS = {"dx": "OffsetX", "dy": "OffsetY", "dz": "OffsetZ", "rx": "RotateX", "ry": "RotateY", "rz": "RotateZ",
         "gap": "Gap"}
_UNIT = {"dx": "length", "dy": "length", "dz": "length", "gap": "length", "rx": "angle", "ry": "angle",
         "rz": "angle"}

FIELDS = (
    Field("solid", "Solid", "pick", pick="body"),
    Field("snap_from", "Snap from", "pick", pick="solid_element"),
    Field("snap_to", "Snap to", "pick", pick="element"),
    Field("flip", "Flip", "bool", default=False),
    Field("gap", "Gap", "value_length", default="0 mm"),
    Field("pivot", "Pivot", "pick", pick="solid_element"),
    Field("world_axes", "World axes", "bool", default=False),
    Field("dx", "Offset X", "value_length", default="0 mm"),
    Field("dy", "Offset Y", "value_length", default="0 mm"),
    Field("dz", "Offset Z", "value_length", default="0 mm"),
    Field("rx", "Rotate X", "value_angle", default="0 °"),
    Field("ry", "Rotate Y", "value_angle", default="0 °"),
    Field("rz", "Rotate Z", "value_angle", default="0 °"),
)


class MoveFeature:
    """The proxy: FreeCAD stores the module path (incad.features.move) and the class name in the file."""
    def __init__(self, obj):
        for prop, kind, doc in (("Snap", "App::PropertyPlacement", "Where the snap put the solid"),
                                ("Frame", "App::PropertyPlacement", "The pivot: its point and axes"),
                                ("SnapAxis", "App::PropertyVector", "The direction the gap moves along"),
                                ("OffsetX", "App::PropertyDistance", ""), ("OffsetY", "App::PropertyDistance", ""),
                                ("OffsetZ", "App::PropertyDistance", ""), ("RotateX", "App::PropertyAngle", ""),
                                ("RotateY", "App::PropertyAngle", ""), ("RotateZ", "App::PropertyAngle", ""),
                                ("Gap", "App::PropertyDistance", "")):
            if prop not in obj.PropertiesList:
                obj.addProperty(kind, prop, "Move", doc)
        obj.Proxy = self

    def execute(self, obj):
        base = obj.BaseFeature
        if base is None or base.Shape.isNull():
            return
        snap_pl = App.Placement(obj.SnapAxis * obj.Gap.Value, App.Rotation()).multiply(obj.Snap)
        total = mm.compose(snap_pl, obj.Frame, App.Vector(obj.OffsetX.Value, obj.OffsetY.Value, obj.OffsetZ.Value),
                           (obj.RotateX.Value, obj.RotateY.Value, obj.RotateZ.Value))
        shape = base.Shape.copy()
        pl = total.multiply(shape.Placement)
        shape.Placement = App.Placement()
        shape.transformShape(pl.toMatrix(), True)  # an exact rigid copy (true cylinders, exact volumes)
        obj.Shape = shape

    def dumps(self):
        return None

    def loads(self, state):
        return None


def claims(feature):
    return hasattr(feature, _STORE)


def defaults(doc, body, profile=None):
    values = {f.key: f.default for f in FIELDS}
    values.update(solid=body.Name if body is not None else "", snap_from="", snap_to="", pivot="")
    return values


def preselect(pairs):
    from incad.features.combine import body_of
    for obj, sub in pairs:
        b = body_of(obj, sub)
        if b is not None:
            return {"solid": b.Name}
    return {}


def _store(f, data):
    if not hasattr(f, _STORE):
        f.addProperty("App::PropertyString", _STORE, "InCad", "InCad move settings")
        f.setPropertyStatus(_STORE, "Hidden")
    setattr(f, _STORE, json.dumps(data, sort_keys=True))


def _load(f):
    try:
        return json.loads(getattr(f, _STORE, "") or "{}")
    except ValueError:
        return {}


def _element(doc, text):
    """(object, sub, shape) of a pick; a pick on a Move step means the same element before it (rigid copy: same
    sub-element numbers)."""
    picks = parse_picks(doc, text)
    if not picks:
        return None
    obj, sub = resolve(*picks[0])
    while claims(obj) and obj.BaseFeature is not None:
        obj = obj.BaseFeature
    if not sub:
        raise ValueError("Pick a point, an edge or a face")
    return obj, sub, obj.Shape.getElement(sub)


def _body(obj):
    b = obj.getParentGeoFeatureGroup() if obj is not None else None
    return b if b is not None and b.TypeId == "PartDesign::Body" else None


def _build(doc, body, f, values):
    src = _element(doc, values.get("snap_from"))
    dst = _element(doc, values.get("snap_to"))
    snap_pl, axis = App.Placement(), App.Vector()
    if src and dst:
        if _body(dst[0]) is body:
            raise ValueError("Snap to: pick on another solid (or the part)")
        a, b = mm.classify(src[2]), mm.classify(dst[2])
        snap_pl = mm.snap(a, b, flip=bool(values.get("flip")), gap=0.0, src_shape=src[2], dst_shape=dst[2])
        axis = App.Vector(b.direction) if b.direction is not None else App.Vector()
    elif src or dst:
        raise ValueError("Pick both Snap from and Snap to (or neither)")
    piv = _element(doc, values.get("pivot"))
    centre = (f.BaseFeature or body.Tip).Shape.CenterOfMass if (f.BaseFeature or body.Tip) is not None else App.Vector()
    frame = mm.pivot_frame(mm.classify(piv[2]) if piv else None, centre, bool(values.get("world_axes")))
    f.Snap, f.Frame, f.SnapAxis = snap_pl, frame, axis
    for key, prop in PROPS.items():
        value_param(doc, f, prop, values.get(key) or ("0 °" if _UNIT[key] == "angle" else "0 mm"), _UNIT[key])
    _store(f, {k: values.get(k) for k in ("solid", "snap_from", "snap_to", "flip", "pivot", "world_axes")})
    return f


def create(doc, body, profile, values):
    from incad.features.combine import _bodies
    solids = _bodies(doc, values.get("solid"))
    target = solids[0] if solids else body
    if target is None:
        raise ValueError("Pick the solid to move")
    tip = target.Tip
    f = target.newObject("PartDesign::FeaturePython", "Move")
    MoveFeature(f)
    f.BaseFeature = tip
    try:
        _build(doc, target, f, values)
        target.Tip = f
        doc.recompute()
        if f.Shape.isNull() or not f.Shape.isValid():
            raise ValueError("The solid can't be moved like that")
    except Exception:
        target.removeObject(f)
        doc.removeObject(f.Name)
        target.Tip = tip
        doc.recompute()
        raise
    return f


def read(doc, f):
    data = _load(f)
    values = defaults(doc, f.getParentGeoFeatureGroup(), None)
    values.update({k: v for k, v in data.items() if k in values})
    for key, prop in PROPS.items():
        values[key] = value_text(doc, f, prop) or values[key]
    return values


def update(doc, f, values):
    return _build(doc, f.getParentGeoFeatureGroup(), f, values)


def param_names(f):
    from incad.core import model
    return {k: model.bound_parameter(f, p) for k, p in PROPS.items() if model.bound_parameter(f, p)}


def _pad_of(f):
    return f
```

Register the kind: in `InCad/incad/features/__init__.py` `kinds()`, add `move` after `combine` (import it in the
same way as the others there).

Check during Step 4: `value_param` with an angle text "45 °" — `model.new_feature_parameter(doc, text, "angle")`
must accept `"angle"` (read `model.py:187` `_with_unit`); if it only knows "length", pass `"angle"` through the same
path `revolve.py` uses for its Angle (grep `value_param(` in `revolve.py`) and use that unit-kind string.

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_headless.sh test_move.py`
Expected: `OK` (10 tests)

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features/move.py InCad/incad/features/__init__.py tests/headless/test_move.py
git commit -m "Move Solid step: snap, pivot, offset and rotation baked into an exact copy; values are parameters"
```

---

### Task 3: Command, icon, picking in the view, GUI test

**Files:**
- Modify: `InCad/incad/features/common.py` (`accepts`), `InCad/incad/ui/feature_session.py` (`_GEOMETRY`),
  `InCad/incad/actions.py`, `InCad/incad/ui/ribbon_layout.py`, `InCad/incad/ui/marking_layout.py`,
  `tools/make_icons.py`, `tests/widgets/test_actions.py`
- Test: `tests/gui/test_move_solid.py`

**Interfaces:**
- Consumes: the Move kind (Task 2)
- Produces: command `feature.move_solid` ("Move Solid", icon `move_solid`); pick filter `solid_element` (a vertex,
  edge or face of the base being moved — the session shows the unmoved base while it is active and refuses picks off
  it, as for other geometry picks).

- [ ] **Step 1: Write the failing GUI test** `tests/gui/test_move_solid.py`

```python
"""Move Solid in a real window: start on a picked face of a second solid, Insert snap by picks, OK = one step."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def doc():
    return App.ActiveDocument


def dialog():
    fs = shell.instance().feature_session
    return fs.dialog if fs is not None else None


def _circle(feature, z, r):
    return "Edge%d" % next(i + 1 for i, e in enumerate(feature.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
                           and abs(e.Curve.Center.z - z) < 1e-6 and abs(e.Curve.Radius - r) < 1e-6)


def test_0_part_with_a_hole_and_a_pin():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    part = document.primary_body(doc())
    box = part.newObject("PartDesign::AdditiveBox", "Box")
    box.Length = box.Width = box.Height = 20
    hole = part.newObject("PartDesign::SubtractiveCylinder", "Hole")
    hole.Radius, hole.Height = 3, 20
    hole.Placement = App.Placement(App.Vector(10, 10, 0), App.Rotation())
    part.Tip = hole
    tool = document.new_solid(doc())
    pin = tool.newObject("PartDesign::AdditiveCylinder", "Pin")
    pin.Radius, pin.Height = 3, 30
    pin.Placement = App.Placement(App.Vector(-40, 0, 0), App.Rotation())
    tool.Tip = pin
    doc().recompute()
    harness.pump(500)
    ST.update(part=part.Name, hole=hole.Name, tool=tool.Name, pin=pin.Name)


def test_1_move_solid_on_a_picked_face_then_insert():
    pin = doc().getObject(ST["pin"])
    hole = doc().getObject(ST["hole"])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, pin.Name, "Face1")
    before = len(doc().UndoNames)
    commands.REGISTRY.run("feature.move_solid")
    harness.pump(1200)
    assert dialog() is not None and dialog().values()["solid"] == ST["tool"], dialog().values()
    dialog().set_pick("snap_from", "%s:%s" % (pin.Name, _circle(pin, 0, 3)))
    harness.pump(600)
    dialog().set_pick("snap_to", "%s:%s" % (hole.Name, _circle(hole, 20, 3)))
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    tool = doc().getObject(ST["tool"])
    assert tool.Tip.Name.startswith("Move"), tool.Tip.Name
    assert abs(tool.Shape.BoundBox.ZMin - 20) < 1e-6 and abs(tool.Shape.BoundBox.Center.x - 10) < 1e-6, tool.Shape.BoundBox
    assert doc().UndoNames[0] == "Move Solid" and len(doc().UndoNames) == before + 1, doc().UndoNames
    from incad.core import tree
    labels = [n.label for n in tree.build(doc())[0].children]
    assert any(lb.startswith("Move") for lb in labels), labels


def test_2_without_a_picked_solid_it_says_what_to_do():
    Gui.Selection.clearSelection()
    harness.pump(300)
    r = commands.REGISTRY.run("feature.move_solid")
    harness.pump(500)
    assert dialog() is None
    assert "Select a face of the solid to move" in str(getattr(r, "error", "")), r


harness.run([test_0_part_with_a_hole_and_a_pin, test_1_move_solid_on_a_picked_face_then_insert,
             test_2_without_a_picked_solid_it_says_what_to_do])
```

(Read `feature_dialog.py` for the exact names of `set_pick` / `values` / `error_text` / `ok_button`, and
`commands.Registry.run`'s return value; adjust the test to them — they exist for the other GUI tests.)

- [ ] **Step 2: Run to verify it fails** (hands off)

Run: `tests/run_gui.sh tests/gui/test_move_solid.py`
Expected: `FAIL test_1…` (unknown command `feature.move_solid`)

- [ ] **Step 3: Implement**

`tools/make_icons.py` `ICONS`:

```python
    'move_solid': '<rect x="4" y="14" width="12" height="12" fill="{F}" stroke="{S}" stroke-width="1.6"/><path d="M16 14 L26 4 M26 4 H20 M26 4 V10" stroke="{A}" stroke-width="2.2" fill="none"/><path d="M10 8 V2 M7 5 L10 2 L13 5" stroke="{S}" stroke-width="1.6" fill="none"/>',
```

Run `/Applications/FreeCAD.app/Contents/Resources/bin/python tools/make_icons.py`.

`common.accepts`: add the branch (next to `element`):

```python
    if kind == "solid_element":  # a point, an edge or a face of the solid being moved (its shape before the move)
        return sub.startswith(("Vertex", "Edge", "Face"))
```

`feature_session.py`: add `"solid_element"` to `_GEOMETRY` (the session then shows the unmoved base while that pick is
active and accepts picks only on it).

`actions.py`:

```python
def start_move_solid():
    """Move Solid starts on the solid of the picked face (or tree row): the picks of the moving solid go on it."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from incad.features.combine import body_of
    doc = App.ActiveDocument
    picked = [body_of(s.Object, (s.SubElementNames or [""])[0]) for s in Gui.Selection.getSelectionEx(doc.Name)] \
        if doc is not None else []
    if not [b for b in picked if b is not None]:
        raise ValueError("Select a face of the solid to move first")
    start_feature("move")
```

and the command next to `feature.combine`:

```python
        Command(id="feature.move_solid", label="Move Solid", icon="move_solid", handler=start_move_solid,
                contexts=frozenset({"part"}), tooltip="Move a solid: snap it onto another, then offset or turn it about a pivot"),
```

`ribbon_layout.py` Modify group: `"feature.thread", "feature.threads_toggle", "feature.move_solid", "feature.combine"`.
`marking_layout.py` `face` list: add `"feature.move_solid"` after `"feature.thread"`.
`tests/widgets/test_actions.py` `EXPECTED`: add `"feature.move_solid"`.

- [ ] **Step 4: Run the tests**

Run: `tests/run_widgets.sh test_actions.py` → `OK`; `tests/run_widgets.sh test_icons.py` → `OK`;
`tests/run_gui.sh tests/gui/test_move_solid.py` → `3 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features/common.py InCad/incad/ui/feature_session.py InCad/incad/actions.py \
        InCad/incad/ui/ribbon_layout.py InCad/incad/ui/marking_layout.py tools/make_icons.py \
        InCad/incad/resources/icons tests/widgets/test_actions.py tests/gui/test_move_solid.py
git commit -m "Move Solid command: ribbon and face menu, picks on the unmoved solid, one undo step"
```

---

### Task 4: Boolean "Keep tool"

**Files:**
- Modify: `InCad/incad/features/combine.py`
- Test: `tests/headless/test_combine.py` (add a class)

**Interfaces:**
- Produces: field `keep_tool` (`bool`, default False), store key `keep_tool`; `combine.used_up_tools(f) -> [Body]`
  (the tools of `f` when Keep tool is off — read by the tree in Task 5); `combine.is_used_up(body) -> bool`.

- [ ] **Step 1: Write the failing tests** (append to `tests/headless/test_combine.py`; reuse its `CombineTest` setup —
  read it first for the names of the base/tool solids and its `make` helper)

```python
class KeepToolTest(CombineTest):
    def test_off_by_default_the_tool_is_used_up(self):
        f = self.make(operation="cut", clearance="0 mm")
        self.assertFalse(combine.read(self.doc, f)["keep_tool"])
        self.assertFalse(self.tool.Visibility)
        self.assertEqual(combine.used_up_tools(f), [self.tool])
        self.assertTrue(combine.is_used_up(self.tool))

    def test_on_the_tool_stays_a_visible_solid_and_can_switch(self):
        f = self.make(operation="cut", clearance="0 mm", keep_tool=True)
        self.assertTrue(self.tool.Visibility)
        self.assertEqual(combine.used_up_tools(f), [])
        self.assertFalse(combine.is_used_up(self.tool))
        combine.update(self.doc, f, dict(combine.read(self.doc, f), keep_tool=False))
        self.doc.recompute()
        self.assertFalse(self.tool.Visibility)

    def test_the_fit_copy_stays_visible_when_the_tool_is_used_up(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="tool")
        fit = self.doc.getObject(combine._load(f)["helpers"][self.tool.Name]["fit"])
        self.assertTrue(fit.Visibility)
        self.assertFalse(self.tool.Visibility)

    def test_delete_brings_the_tool_back(self):
        from incad.core import delete
        f = self.make(operation="cut", clearance="0 mm")
        delete.delete(f)
        self.assertTrue(self.tool.Visibility)
        self.assertFalse(combine.is_used_up(self.tool))

    def test_an_old_boolean_reads_as_used_up(self):
        f = self.make(operation="cut", clearance="0 mm", keep_tool=True)
        data = combine._load(f)
        del data["keep_tool"]
        combine._store(f, data)
        self.assertFalse(combine.read(self.doc, f)["keep_tool"])
        self.assertTrue(combine.is_used_up(self.tool))

    def test_moving_a_used_up_tool_moves_the_cut(self):
        from incad.features import move
        f = self.make(operation="cut", clearance="0 mm")
        v = self.base.Shape.Volume
        move.create(self.doc, self.tool, None, dict(move.defaults(self.doc, self.tool, None), solid=self.tool.Name,
                                                     dx="1000 mm"))
        self.doc.recompute()
        self.assertGreater(self.base.Shape.Volume, v)  # the tool moved away: less is cut
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_combine.py`
Expected: FAIL/ERROR (`keep_tool` unknown, no `used_up_tools`)

- [ ] **Step 3: Implement** in `combine.py`

Add the field after `apply_to`:

```python
    Field("keep_tool", "Keep tool", "bool", default=False),
```

In `_build`: replace `tool.Visibility = False` with `tool.Visibility = bool(values.get("keep_tool"))` and add
`"keep_tool": bool(values.get("keep_tool"))` to the `_store` dict. In `read`: `"keep_tool": bool(data.get("keep_tool", False))`.
Add:

```python
def used_up_tools(f):
    """The tools this Boolean uses up (Keep tool off; older Booleans had no setting and hid their tools)."""
    data = _load(f)
    if data.get("keep_tool"):
        return []
    return [t for t in (f.Document.getObject(n) for n in data.get("tools", [])) if t is not None]


def is_used_up(body):
    return any(body in used_up_tools(f) for f in body.Document.Objects if claims(f))
```

`delete` already shows the tools again.

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_combine.py` and `tests/run_headless.sh test_delete.py`
Expected: `OK` both

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features/combine.py tests/headless/test_combine.py
git commit -m "Boolean Keep tool: off uses the tool up (hidden), on keeps it a visible solid; old Booleans read as off"
```

---

### Task 5: Used-up tools in the model tree

**Files:**
- Modify: `InCad/incad/core/tree.py`
- Test: `tests/headless/test_tree.py` (add)

**Interfaces:**
- Consumes: `combine.used_up_tools(f)`, `combine.is_used_up(body)` (Task 4)
- Produces: a Boolean row with Keep tool off has one child `Node("body", tool.Label, tool.Name)` per used-up tool,
  whose children are the tool's history rows (features and their sketches as elsewhere); those rows are not in the
  main history; the Solid Bodies folder lists only solids that are not used up (`"Solid Bodies (N)"` counts those).

- [ ] **Step 1: Write the failing tests** (append to `tests/headless/test_tree.py`; read its helpers first)

```python
class UsedUpToolTreeTest(unittest.TestCase):
    def setUp(self):
        from incad.features import combine
        self.doc = util.new_doc("Ut")
        self.part = document.make_part(self.doc)
        box = self.part.newObject("PartDesign::AdditiveBox", "Box")
        self.part.Tip = box
        self.tool = document.new_solid(self.doc)
        pin = self.tool.newObject("PartDesign::AdditiveCylinder", "Pin")
        pin.Radius, pin.Height = 2, 30
        self.tool.Tip = pin
        self.doc.recompute()
        self.f = combine.create(self.doc, self.part, None, dict(combine.defaults(self.doc, self.part),
                                                                tools=self.tool.Name, operation="cut",
                                                                clearance="0 mm"))
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def rows(self):
        return tree.build(self.doc)[0].children

    def test_a_used_up_tool_sits_under_its_boolean(self):
        rows = self.rows()
        names = [n.name for n in rows]
        self.assertNotIn("Pin", names)  # not in the main history
        node = next(n for n in rows if n.name == self.f.Name)
        tool = next(c for c in node.children if c.kind == "body")
        self.assertEqual(tool.name, self.tool.Name)
        self.assertIn("Pin", [c.name for c in tool.children])
        solids = next((n for n in rows if n.kind == "solids"), None)
        self.assertIsNone(solids)  # one solid left that is not used up: no folder

    def test_keep_tool_on_puts_it_back_in_the_list(self):
        from incad.features import combine
        combine.update(self.doc, self.f, dict(combine.read(self.doc, self.f), keep_tool=True))
        self.doc.recompute()
        rows = self.rows()
        self.assertIn("Pin", [n.name for n in rows])
        solids = next(n for n in rows if n.kind == "solids")
        self.assertEqual(solids.label, "Solid Bodies (2)")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_tree.py`
Expected: FAIL (Pin still in the main history)

- [ ] **Step 3: Implement** in `tree.py`

In `build`: `listed = [b for b in all_bodies if not combine.is_used_up(b)]`; the Solid Bodies folder uses `listed`
(shown when `len(listed) > 1`, label `"Solid Bodies (%d)" % len(listed)`).

In `_history`: before the loop, `used = {b.Name for b in document.bodies(doc) if combine.is_used_up(b)}`; in the loop,
`continue` for rows whose body `b.Name in used` — but collect them: `tool_rows.setdefault(b.Name, []).append(node)`
(build the node exactly as for other rows, with its sketch and helper children). After a Boolean row's node is built,
for each `t in combine.used_up_tools(obj)` append `Node("body", t.Label, t.Name, children=tool_rows.get(t.Name, []))`.
Because a tool's rows can come later in the history than its Boolean (a Move added afterwards), build all tool rows in
a first pass over `hist`, then build the visible list in a second pass. Import `combine` lazily inside the functions
(`from incad.features import combine`).

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_tree.py` → `OK`; `tests/run_gui.sh tests/gui/test_combine.py` → all pass;
`tests/run_gui.sh tests/gui/test_solids.py` → all pass.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/tree.py tests/headless/test_tree.py
git commit -m "Model tree: a used-up Boolean tool sits under its Boolean with its features, out of Solid Bodies"
```

---

### Task 6: Clearance labels, release notes, project facts

**Files:**
- Modify: `InCad/incad/features/combine.py:29`, `InCad/incad/features/thread.py:38`, `InCad/incad/features/hole.py:51`,
  `InCad/incad/__init__.py`, `tests/headless/test_smoke.py`, `scripts/dist/CHANGES.txt`, `scripts/dist/CHANGES_ru.txt`,
  `CLAUDE.md`
- Test: `tests/widgets/test_feature_dialog.py` (add)

- [ ] **Step 1: Write the failing test** (append to `tests/widgets/test_feature_dialog.py`'s test class or a new one)

```python
class ClearanceLabelTest(unittest.TestCase):
    def test_each_clearance_says_how_it_is_measured(self):
        from incad.features import combine, hole, thread
        label = {k.__name__.rsplit(".", 1)[-1]: next(f.label for f in k.FIELDS if f.key == "clearance")
                 for k in (combine, hole, thread)}
        self.assertEqual(label, {"combine": "Clearance (per side)", "hole": "Print clearance (on diameter)",
                                 "thread": "Print clearance (on diameter)"})
```

(These modules import FreeCAD; if the widgets runner can't import them, put this test in
`tests/headless/test_combine.py` instead.)

- [ ] **Step 2: Run to verify it fails** — Expected: FAIL (labels differ)
- [ ] **Step 3:** Change the three `Field(... "clearance", "<label>" ...)` labels. Bump `__version__` to the next build
  (and `test_smoke.py`). Add on top of both CHANGES files (above the newest section):

```
0.1.3
-----
Improvements
- New Move Solid (3D Model > Modify > Move Solid, or right-click a face). Pick a face of the solid to move,
  then snap a point, edge, circle, face or cylinder of it onto one of another solid (point to point, pin into
  hole, edge on edge, face against face, concentric), choose a pivot (a point, an edge as a hinge, a face),
  and offset or turn it. The move is a step in the solid's history: edit it, delete it or roll it back with
  End of Part; its values are parameters.
- Boolean: new "Keep tool" option. Off (as it opens): the tool is used up and shows under the Boolean in the
  model tree. On: the tool stays a separate visible solid (print the pin and the box).
- Clearance fields say how they are measured: Boolean "Clearance (per side)", Thread and Hole
  "Print clearance (on diameter)".
```

```
0.1.3
-----
Улучшения
- Новая команда Move Solid (3D Model > Modify > Move Solid или правая кнопка на грани). Выберите грань
  тела, которое нужно переместить, затем совместите его точку, ребро, окружность, грань или цилиндр с
  элементом другого тела (точка к точке, штифт в отверстие, ребро на ребро, грань к грани, соосно),
  выберите опорную точку (точка, ребро как шарнир, грань) и сдвиньте или поверните. Перемещение - это шаг
  в истории тела: его можно изменить, удалить или откатить маркером End of Part; значения - параметры.
- Boolean: новая опция "Keep tool". Выключена (по умолчанию): инструмент расходуется и показывается под
  Boolean в дереве. Включена: инструмент остаётся отдельным видимым телом (печатаете и штифт, и коробку).
- Поля зазора подписаны: Boolean "Clearance (per side)" (на сторону), Thread и Hole
  "Print clearance (on diameter)" (по диаметру).
```

`CLAUDE.md`: add "Move Solid (`incad.features.move`) is the first Python-proxy feature (`PartDesign::FeaturePython`,
proxy class `MoveFeature`, module path saved in files); it bakes its placement into an exact copy
(`transformShape(m, True)`) because a feature's `Shape.Placement` is reset on assignment."

- [ ] **Step 4:** Run the full suites once: `tests/run_headless.sh`, `tests/run_widgets.sh` → `OK`;
  `tests/run_gui.sh tests/gui/test_move_solid.py tests/gui/test_combine.py tests/gui/test_threads.py` → all pass.
- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features/combine.py InCad/incad/features/thread.py InCad/incad/features/hole.py \
        InCad/incad/__init__.py tests/headless/test_smoke.py scripts/dist/CHANGES.txt scripts/dist/CHANGES_ru.txt \
        CLAUDE.md tests/widgets/test_feature_dialog.py
git commit -m "Clearance labels say per side / on diameter; release notes for Move Solid and Keep tool"
```
