# Move Face Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inventor-style Move Face for flat faces — Distance or To, neighbours Inventor / Step / Together, several faces,
a drag arrow with the distance shown at it — plus 20 % smaller assembly gizmo arrows.

**Architecture:** Pure geometry in `incad.core.move_face` (find a face by its stored geometry, build the slab between
the face's old and new place, fuse or cut it). A feature kind `incad.features.move_face` (a `PartDesign::FeaturePython`
at the tip, like `split`) drives it from the usual feature dialog. A view overlay `incad.ui.move_face_arrow` draws the
arrow and the live value label and takes the drag through `Navigator.handle_hook` while the dialog is open.

**Tech Stack:** FreeCAD 1.1.3 (Part / PartDesign, OCC through `Part`), PySide (FreeCAD's shim), pivy/Coin, unittest.

**Spec:** `docs/superpowers/specs/2026-10-14-incad-move-face-design.md`

## Global Constraints
- Read `CLAUDE.md` first. Runners: `tests/run_headless.sh <file>`, `tests/run_widgets.sh <file>`,
  `tests/run_gui.sh <path>` (real FreeCAD window, hands off; foreground, timeout 600000 ms). unittest only.
- UI text English, sentence case, InCad's wording: "Move Face", fields "Faces", "Extent" (Distance / To), "Distance",
  "To", "Neighbours" (Inventor / Step / Together).
- Error texts (exact): "The faces must be flat and face the same way"; "Pick a face or plane parallel to the faces";
  "A neighbouring face is round: Inventor mode can't follow it yet — try Step or Together"; "The walls around the
  chamfer / fillet must run along the move — try Inventor or Step"; "The move is too large: a neighbouring face would
  vanish"; "A face to move is no longer there".
- Shapes in the body's frame (BaseFeature.Shape); faces are found by geometry on every recompute, never by name.
- Positive distance = outward (the first face's outward normal); 0 = the shape before, no error.
- One undo step per OK ("Move Face"). Never `Gui.setEdit` a sketch directly; never save the user's files.
- Gizmo size: `max(diagonal × 0.28, 4 mm)` (was `× 0.35, 5 mm`); `HANDLE_PX` unchanged.
- Commit after each task with a plain message ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  Never push.

## Review Focus
1. A part whose body has a Placement (moved / rotated body): picked faces and the arrow must use the body's frame —
   Task 3 test `test_a_moved_body`.
2. A face with a hole in it (inner wire) in Inventor mode: the hole must stay a hole (not be filled by the slab) —
   Task 1 test `test_face_with_a_hole_keeps_the_hole`.
3. The distance changed later in the Parameters panel (a formula / the named parameter): the feature must follow —
   Task 3 test `test_the_distance_parameter_drives_it`.
4. Esc or a command while dragging the arrow: the drag ends, the dialog keeps the last value, nothing half-done —
   Task 5 test `test_5_a_command_ends_the_drag`.
5. A part with several Solids, the face on the second Solid: Move Face goes into that Solid (its body) —
   Task 3 test `test_face_on_a_second_solid`.

---

### Task 1: Gizmo arrows 20 % smaller

**Files:**
- Modify: `InCad/incad/core/dof.py` (add `glyph_size`)
- Modify: `InCad/incad/ui/shell.py:2671` (`size = max(bb.DiagonalLength * 0.35, 5.0)`)
- Test: `tests/headless/test_dof.py`

**Interfaces:**
- Produces: `dof.glyph_size(diagonal: float) -> float` (also used by Task 4 for the Move Face arrow).

- [ ] **Step 1: Write the failing test** (append a class to `tests/headless/test_dof.py`)

```python
class GlyphSizeTest(unittest.TestCase):
    """The user (2026-10-14): the gizmo arrows a little smaller — 20 % — the grab zone stays as wide."""

    def test_twenty_percent_smaller_than_before(self):
        from incad.core import dof
        self.assertAlmostEqual(dof.glyph_size(100.0), 28.0)   # was 35
        self.assertAlmostEqual(dof.glyph_size(10.0), 4.0)     # the floor: was 5
```

- [ ] **Step 2: Run it** — `tests/run_headless.sh test_dof.py` → FAIL: `module 'incad.core.dof' has no attribute 'glyph_size'`.

- [ ] **Step 3: Implement** — in `core/dof.py` next to `RING` / `FAR`:

```python
def glyph_size(diagonal):
    """A part's DOF glyph / gizmo size (mm) from its box diagonal (the user: 20 % smaller than 0.35 / 5 mm)."""
    return max(diagonal * 0.28, 4.0)
```

and in `ui/shell.py` replace `size = max(bb.DiagonalLength * 0.35, 5.0)` with `size = dof.glyph_size(bb.DiagonalLength)`
(check `dof` is imported there; it is used two lines below as `dof.handles`).

- [ ] **Step 4: Run** `tests/run_headless.sh test_dof.py` → OK; then `tests/run_gui.sh tests/gui/test_dof_handles.py
  tests/gui/test_assembly_drag.py` → all pass (they read the size from `dof_handles.drawn`). A test with a hard-coded
  size: change it to `dof.glyph_size(...)`, never loosen what it checks.

- [ ] **Step 5: Commit** — "Assembly: the DOF gizmo arrows 20 % smaller (the grab zone stays as wide)".

---

### Task 2: Move Face geometry (`incad.core.move_face`)

**Files:**
- Create: `InCad/incad/core/move_face.py`
- Test: `tests/headless/test_move_face_geom.py`

**Interfaces:**
- Produces (all shapes in one frame; `faces` are `Part.Face` of `shape`):
  - `signature(face) -> dict` — `{"n": [x,y,z], "p": [x,y,z], "outline": [[x,y,z], …], "area": float}` (JSON-able)
  - `find(shape, sig) -> Part.Face | None` — among the flat faces of `shape` facing the same way whose outline overlaps
    the stored outline (both seen along n): the one in the stored plane first, else the one overlapping most (nearest
    plane on a tie) — so a face moved by an earlier feature's edit (the block made taller) is found again
  - `check_faces(faces) -> App.Vector` — the common outward normal; raises `ValueError(FACES_MSG)`
  - `gap_to(faces, target) -> float` — signed distance from the faces' plane to `target` (a `Part.Face` or a
    `(point, normal)` pair); raises `ValueError(PARALLEL_MSG)`
  - `apply(shape, faces, d, mode) -> Part.Shape` — `mode` in `("inventor", "step", "together")`; raises `ValueError`
    with the spec messages; `d == 0` returns `shape`
  - constants `FACES_MSG, PARALLEL_MSG, ROUND_MSG, WALLS_MSG, TOO_LARGE_MSG, GONE_MSG` (the exact texts of Global
    Constraints)

The construction was checked in a spike (2026-10-14, freecadcmd): 40×30×10 box with a 3 mm chamfer, top +4 Inventor →
volume 16065 (= 40·30·14 − ½·7²·30), −2 → 9585; 2 mm fillet, Together +3 → fillet volume + 40·30·3; Step → + area·3.

- [ ] **Step 1: Write the failing tests** — `tests/headless/test_move_face_geom.py`:

```python
"""Move Face geometry: the slab between a flat face's old and new place, three ways for the neighbours."""
import unittest

import FreeCAD as App
import Part

from incad.core import move_face as mf

V = App.Vector
UP = V(0, 0, 1)


def top(shape):
    """The highest face facing up."""
    flat = [f for f in shape.Faces if f.Surface.__class__.__name__ == "Plane" and f.normalAt(0, 0).z > 0.999]
    return max(flat, key=lambda f: f.CenterOfMass.z)


def chamfered():
    box = Part.makeBox(40, 30, 10)
    e = next(e for e in box.Edges if abs(e.CenterOfMass.z - 10) < 1e-9 and abs(e.CenterOfMass.x - 40) < 1e-9)
    return box.makeChamfer(3, [e])


def filleted():
    box = Part.makeBox(40, 30, 10)
    e = next(e for e in box.Edges if abs(e.CenterOfMass.z - 10) < 1e-9 and abs(e.CenterOfMass.x - 40) < 1e-9)
    return box.makeFillet(2, [e])


class BoxTest(unittest.TestCase):
    def test_every_mode_moves_a_box_top(self):
        box = Part.makeBox(40, 30, 10)
        for mode in ("inventor", "step", "together"):
            up = mf.apply(box, [top(box)], 5, mode)
            down = mf.apply(box, [top(box)], -3, mode)
            self.assertEqual(len(up.Solids), 1, mode)
            self.assertAlmostEqual(up.Volume, 40 * 30 * 15, 6, mode)
            self.assertAlmostEqual(down.Volume, 40 * 30 * 7, 6, mode)
            self.assertAlmostEqual(up.BoundBox.ZMax, 15, 9, mode)

    def test_zero_is_the_shape_before(self):
        box = Part.makeBox(40, 30, 10)
        self.assertIs(mf.apply(box, [top(box)], 0, "inventor"), box)


class ChamferTest(unittest.TestCase):
    def test_inventor_extends_the_chamfer(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], 4, "inventor")
        self.assertAlmostEqual(r.Volume, 40 * 30 * 14 - 0.5 * 7 * 7 * 30, 6)
        self.assertAlmostEqual(top(r).BoundBox.XMax, 40 - 7, 6)  # the top face 4 mm narrower toward the chamfer

    def test_inventor_inward(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], -2, "inventor")
        self.assertAlmostEqual(r.Volume, 40 * 30 * 8 - 0.5 * 1 * 1 * 30, 6)

    def test_inventor_too_far_inward_is_refused(self):
        ch = chamfered()
        with self.assertRaises(ValueError) as e:
            mf.apply(ch, [top(ch)], -4, "inventor")  # the 3 mm chamfer would vanish
        self.assertEqual(str(e.exception), mf.TOO_LARGE_MSG)

    def test_step_leaves_a_straight_wall(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], 4, "step")
        self.assertAlmostEqual(r.Volume, ch.Volume + top(ch).Area * 4, 6)
        self.assertAlmostEqual(top(r).BoundBox.XMax, 37, 6)

    def test_together_moves_the_chamfer_up(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], 4, "together")
        self.assertAlmostEqual(r.Volume, ch.Volume + 40 * 30 * 4, 6)  # the side wall 4 taller, chamfer unchanged
        self.assertAlmostEqual(top(r).BoundBox.XMax, 37, 6)


class FilletTest(unittest.TestCase):
    def test_inventor_says_a_round_neighbour_cannot_follow(self):
        fl = filleted()
        with self.assertRaises(ValueError) as e:
            mf.apply(fl, [top(fl)], 3, "inventor")
        self.assertEqual(str(e.exception), mf.ROUND_MSG)

    def test_together_and_step_work(self):
        fl = filleted()
        self.assertAlmostEqual(mf.apply(fl, [top(fl)], 3, "together").Volume, fl.Volume + 40 * 30 * 3, 6)
        self.assertAlmostEqual(mf.apply(fl, [top(fl)], 3, "step").Volume, fl.Volume + top(fl).Area * 3, 6)


class HoleSlotTest(unittest.TestCase):
    def test_face_with_a_hole_keeps_the_hole(self):
        part = Part.makeBox(40, 30, 10).cut(Part.makeCylinder(4, 10, V(20, 15, 0)))
        r = mf.apply(part, [top(part)], 5, "inventor")
        self.assertAlmostEqual(r.Volume, (40 * 30 - 3.141592653589793 * 16) * 15, 3)
        hit = r.common(Part.LineSegment(V(20, 15, -1), V(20, 15, 20)).toShape())
        self.assertAlmostEqual(hit.Length, 0, 6)  # the hole still goes through

    def test_slot_floor_deeper_and_shallower(self):
        part = Part.makeBox(40, 30, 10).cut(Part.makeBox(20, 10, 4, V(10, 10, 6)))  # floor at z 6
        floor = next(f for f in part.Faces if f.Surface.__class__.__name__ == "Plane"
                     and f.normalAt(0, 0).z > 0.999 and abs(f.CenterOfMass.z - 6) < 1e-9)
        self.assertAlmostEqual(mf.apply(part, [floor], -2, "inventor").Volume, part.Volume - 20 * 10 * 2, 6)
        self.assertAlmostEqual(mf.apply(part, [floor], 2, "inventor").Volume, part.Volume + 20 * 10 * 2, 6)


class SeveralFacesTest(unittest.TestCase):
    def two_bosses(self):
        base = Part.makeBox(60, 20, 5)
        return base.fuse([Part.makeBox(10, 10, 5, V(5, 5, 5)), Part.makeBox(10, 10, 5, V(45, 5, 5))]).removeSplitter()

    def test_two_tops_move_together(self):
        part = self.two_bosses()
        tops = [f for f in part.Faces if f.normalAt(0, 0).z > 0.999 and abs(f.CenterOfMass.z - 10) < 1e-9]
        self.assertEqual(len(tops), 2)
        r = mf.apply(part, tops, 3, "inventor")
        self.assertAlmostEqual(r.Volume, part.Volume + 2 * 100 * 3, 6)

    def test_faces_facing_other_ways_are_refused(self):
        box = Part.makeBox(40, 30, 10)
        side = next(f for f in box.Faces if f.normalAt(0, 0).x > 0.999)
        with self.assertRaises(ValueError) as e:
            mf.apply(box, [top(box), side], 3, "inventor")
        self.assertEqual(str(e.exception), mf.FACES_MSG)


class FindAndGapTest(unittest.TestCase):
    def test_signature_finds_the_face_again_on_a_changed_shape(self):
        box = Part.makeBox(40, 30, 10)
        sig = mf.signature(top(box))
        boss = Part.makeBox(40, 30, 10).fuse(Part.makeBox(10, 10, 5, V(0, 0, 10))).removeSplitter()  # a boss on top
        self.assertAlmostEqual(mf.find(boss, sig).CenterOfMass.z, 10, 9)  # the stored plane first, not the boss top
        self.assertAlmostEqual(mf.find(Part.makeBox(40, 30, 12), sig).CenterOfMass.z, 12, 9)  # made taller: found
        self.assertIsNone(mf.find(Part.makeBox(10, 10, 10, V(100, 0, 0)), sig))  # nothing overlaps: gone

    def test_gap_to_a_parallel_plane_and_a_tilted_one(self):
        box = Part.makeBox(40, 30, 10)
        self.assertAlmostEqual(mf.gap_to([top(box)], (V(0, 0, 16), UP)), 6, 9)
        self.assertAlmostEqual(mf.gap_to([top(box)], (V(0, 0, 4), V(0, 0, -1))), -6, 9)
        with self.assertRaises(ValueError) as e:
            mf.gap_to([top(box)], (V(0, 0, 16), V(0, 1, 1).normalize()))
        self.assertEqual(str(e.exception), mf.PARALLEL_MSG)
```

- [ ] **Step 2: Run it** — `tests/run_headless.sh test_move_face_geom.py` → errors: `No module named 'incad.core.move_face'`.

- [ ] **Step 3: Implement** `InCad/incad/core/move_face.py`:

```python
"""Move Face: flat faces moved along their normal by d (outward > 0) — the slab between the faces' old and new place is
added (d > 0) or cut (d < 0). Three ways for the neighbours (the faces sharing an edge with a moved face):
- step: the slab is the face pushed straight (a slanted neighbour stays, a straight wall appears at its edge);
- inventor: the slab's side walls lie on the neighbours (flat at any angle, or a cylinder along the move), so a chamfer
  keeps its angle and grows / shrinks; a round neighbour across the move cannot follow yet;
- together: the face moves with its neighbours that are not along the move (chamfers, fillets) as one piece; the walls
  around them must run along the move and grow.
Faces are kept by geometry (signature / find), never by name. Pure Part code, headless."""
import FreeCAD as App
import Part

FACES_MSG = "The faces must be flat and face the same way"
PARALLEL_MSG = "Pick a face or plane parallel to the faces"
ROUND_MSG = "A neighbouring face is round: Inventor mode can't follow it yet — try Step or Together"
WALLS_MSG = "The walls around the chamfer / fillet must run along the move — try Inventor or Step"
TOO_LARGE_MSG = "The move is too large: a neighbouring face would vanish"
GONE_MSG = "A face to move is no longer there"
_TOL = 1e-6
_ANG = 1e-6


def _is_plane(face):
    return face.Surface.__class__.__name__ == "Plane"


def _normal(face):
    """The outward normal of a flat face of a solid (FreeCAD's normalAt follows the face's orientation)."""
    return face.normalAt(0, 0)


def signature(face):
    n = _normal(face)
    pts = [v.Point for v in face.OuterWire.OrderedVertexes] or [face.CenterOfMass]
    if len(pts) < 3:  # a round face (a boss top): its outline sampled
        pts = face.OuterWire.discretize(24)
    return {"n": [n.x, n.y, n.z], "p": list(face.CenterOfMass), "outline": [list(p) for p in pts],
            "area": face.Area}


def _sig_face(sig):
    pts = [App.Vector(*p) for p in sig["outline"]]
    return Part.Face(Part.makePolygon(pts + [pts[0]]))


def find(shape, sig):
    """The face again: same direction, its outline overlapping the stored one seen along n; the stored plane first,
    then the most overlap, then the nearest plane (an earlier feature made the part taller: the top moved)."""
    n, p = App.Vector(*sig["n"]), App.Vector(*sig["p"])
    try:
        ref = _sig_face(sig)
    except Exception:
        return None
    best, key = None, None
    for f in shape.Faces:
        if not _is_plane(f) or _normal(f).dot(n) < 1 - _ANG:
            continue
        off = (f.CenterOfMass - p).dot(n)
        try:
            s = f.translated(n * -off).common(ref).Area
        except Exception:
            s = 0.0
        if s <= _TOL:
            continue
        k = (abs(off) > _TOL, -s, abs(off))
        if key is None or k < key:
            best, key = f, k
    return best


def check_faces(faces):
    if not faces or not all(_is_plane(f) for f in faces):
        raise ValueError(FACES_MSG)
    n = _normal(faces[0])
    for f in faces[1:]:
        if _normal(f).dot(n) < 1 - _ANG:
            raise ValueError(FACES_MSG)
    return n


def gap_to(faces, target):
    n = check_faces(faces)
    if isinstance(target, Part.Face):
        if not _is_plane(target):
            raise ValueError(PARALLEL_MSG)
        point, normal = target.CenterOfMass, _normal(target)
    else:
        point, normal = target
    if abs(abs(App.Vector(normal).normalize().dot(n)) - 1) > _ANG:
        raise ValueError(PARALLEL_MSG)
    return (App.Vector(point) - faces[0].CenterOfMass).dot(n)


def _along(face, n):
    """A face the move runs along: a plane containing n, or a cylinder whose axis is n."""
    kind = face.Surface.__class__.__name__
    if kind == "Plane":
        return abs(_normal(face).dot(n)) < _ANG
    if kind == "Cylinder":
        return abs(abs(face.Surface.Axis.normalize().dot(n)) - 1) < _ANG
    return False


def _same(a, b):
    return a.isSame(b)


def _neighbour(shape, face, edge):
    for f in shape.ancestorsOfType(edge, Part.Face):
        if not _same(f, face):
            return f
    return None


def _side_dir(shape, face, vertex):
    """The line a vertex of `face` moves along (inventor): the solid's edge at that vertex that is not on `face`."""
    own = list(face.Edges)
    for e in shape.ancestorsOfType(vertex, Part.Edge):
        if any(_same(e, o) for o in own):
            continue
        if e.Curve.__class__.__name__ != "Line":
            raise ValueError(ROUND_MSG)
        a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
        far = b if a.distanceToPoint(vertex.Point) < _TOL else a
        return (vertex.Point - far).normalize(), e.Length
    raise ValueError(ROUND_MSG)


def _moved_wire(shape, face, wire, n, d):
    """The wire in the new plane, every vertex along its side line, every edge on its neighbour (inventor)."""
    for e in wire.Edges:
        nb = _neighbour(shape, face, e)
        if nb is None or not (_is_plane(nb) or _along(nb, n)):
            raise ValueError(ROUND_MSG)
    moved = {}
    for v in wire.OrderedVertexes:
        u, length = _side_dir(shape, face, v)
        if abs(u.dot(n)) < _ANG:
            raise ValueError(TOO_LARGE_MSG)
        t = d / u.dot(n)
        if d < 0 and abs(t) >= length - _TOL:  # inward past the far end of its side edge: that neighbour vanishes
            raise ValueError(TOO_LARGE_MSG)
        moved[v.hashCode()] = v.Point + u * t
    edges = []
    for e in wire.OrderedEdges:
        a, b = moved[e.Vertexes[0].hashCode()], moved[e.Vertexes[-1].hashCode()]
        if e.Curve.__class__.__name__ == "Line":
            if a.distanceToPoint(b) < _TOL:
                raise ValueError(TOO_LARGE_MSG)
            edges.append(Part.LineSegment(a, b).toShape())
        else:  # an arc / circle on a cylinder along the move: it slides
            edges.append(e.translated(n * d))
    w = Part.Wire(Part.__sortEdges__(edges))
    if not w.isClosed():
        raise ValueError(TOO_LARGE_MSG)
    return w


def _loft(a, b):
    return Part.makeLoft([a, b], True, True)


def _inventor_slab(shape, face, n, d):
    outer = Part.Wire(face.OuterWire.OrderedEdges)
    new_outer = _moved_wire(shape, face, face.OuterWire, n, d)
    try:
        if not Part.Face(new_outer).isValid() or Part.Face(new_outer).Area < _TOL:
            raise ValueError(TOO_LARGE_MSG)
    except Part.OCCError:
        raise ValueError(TOO_LARGE_MSG)
    slab = _loft(outer, new_outer)
    for inner in face.Wires:
        if inner.isSame(face.OuterWire):
            continue
        slab = slab.cut(_loft(Part.Wire(inner.OrderedEdges), _moved_wire(shape, face, inner, n, d)))
    return slab


def _together_slab(shape, face, n, d):
    moved = [face] + [nb for nb in (_neighbour(shape, face, e) for e in face.Edges)
                      if nb is not None and not _along(nb, n)]
    group = []
    for f in moved:
        if not any(_same(f, g) for g in group):
            group.append(f)
    count = {}
    for f in group:
        for e in f.Edges:
            key = e.hashCode()
            count[key] = (count.get(key, (0, e))[0] + 1, e)
    rim = [e for c, e in count.values() if c == 1]
    for e in rim:
        wall = next((f for f in shape.ancestorsOfType(e, Part.Face) if not any(_same(f, g) for g in group)), None)
        if wall is not None and not _along(wall, n):
            raise ValueError(WALLS_MSG)
    caps = [f.copy() for f in group] + [f.translated(n * d) for f in group]
    strips = [e.extrude(n * d).Faces[0] for e in rim]
    sh = Part.Shell(caps + strips).sewShape() or Part.Shell(caps + strips)
    if sh.ShapeType != "Shell":
        sh = Part.Shell(sh.Faces)
    return Part.Solid(sh)


def apply(shape, faces, d, mode):
    if abs(d) < _TOL:
        return shape
    n = check_faces(faces)
    slabs = []
    for f in faces:
        if mode == "step":
            slabs.append(f.extrude(n * d))
        elif mode == "together":
            slabs.append(_together_slab(shape, f, n, d))
        else:
            slabs.append(_inventor_slab(shape, f, n, d))
    slab = slabs[0] if len(slabs) == 1 else slabs[0].fuse(slabs[1:])
    result = (shape.fuse(slab) if d > 0 else shape.cut(slab)).removeSplitter()
    if not result.isValid() or len(result.Solids) != len(shape.Solids):
        raise ValueError(TOO_LARGE_MSG)
    return result
```

Notes for the implementer:
- `_normal` must be the face's **outward** normal (the spike's faces gave +Z for a box top). If a test face of a
  reversed orientation shows otherwise, fix it in `_normal` only — every caller asks that one place.
- `Part.__sortEdges__` exists in FreeCAD 1.1 (`Part.sortEdges` returns lists of lists in some versions — check in
  freecadcmd and use the one that returns ordered edges).
- If OCC loft order differs between the outer wire and the moved wire, build the side faces with
  `Part.makeRuledSurface(e, e2)` per edge pair and `Part.Solid(Part.Shell([...]))` instead; the volume tests decide.
- The inward-too-far check: a vertex may not travel past the far end of its side edge (the chamfer's 3 mm, as
  `length`), and no edge of the moved outline may shrink to nothing → `TOO_LARGE_MSG`.
  `test_inventor_too_far_inward_is_refused` pins it (−4 on a 3 mm chamfer: 5.66 mm along a 4.24 mm edge).
- `arrow()` / the picked faces assume the shapes are in the body's frame (as `hole_chamfer` does). If
  `test_a_moved_body` shows a feature's `Shape` already carries the body's Placement, convert in that one place
  (`_body_frame`) — never in the geometry module.

- [ ] **Step 4: Run** `tests/run_headless.sh test_move_face_geom.py` → OK (every test). Fix the code, never the expected
  volumes (they are the exact geometry).

- [ ] **Step 5: Commit** — "Move Face geometry: the slab between a flat face's old and new place (Inventor / Step /
  Together), faces kept by geometry".

---

### Task 3: The Move Face feature kind

**Files:**
- Create: `InCad/incad/features/move_face.py`
- Modify: `InCad/incad/features/__init__.py` (add `move_face` to `kinds()` after `split`)
- Test: `tests/headless/test_move_face.py`

**Interfaces:**
- Consumes: `incad.core.move_face` (Task 2).
- Produces: kind module `incad.features.move_face` with `TITLE = "Move Face"`, `ICON = "move_face"`,
  `TYPES = ("PartDesign::FeaturePython",)`, `NEEDS_PROFILE = False`, `STRUCTURAL = ()`, `PROPS = {"distance": "Distance"}`,
  `PRESELECT = {"faces": "faces"}`, `FIELDS`, `claims(f)`, `defaults(doc, body, profile=None)`,
  `create(doc, body, profile, values)`, `read(doc, f)`, `update(doc, f, values)`, `param_names(f)`,
  `arrow(f) -> (App.Vector point, App.Vector normal) | None` (global coordinates: the first face's centre and outward
  normal, for Task 4).
- Values: `faces` ("Obj:FaceN,…" picks), `extent` ("distance" | "to"), `distance` ("5 mm"), `to` (one pick: a face
  "Obj:FaceN" or a plane object name), `mode` ("inventor" | "step" | "together").

- [ ] **Step 1: Write the failing tests** — `tests/headless/test_move_face.py`:

```python
"""Move Face as a feature: a step at the tip that finds its faces by geometry on every recompute."""
import unittest

import FreeCAD as App

from incad.core import document, model
from incad.features import kind_for, move_face
from headless import util


def top_name(feature):
    faces = feature.Shape.Faces
    i = max((k for k, f in enumerate(faces) if f.normalAt(0, 0).z > 0.999), key=lambda k: faces[k].CenterOfMass.z)
    return "%s:Face%d" % (feature.Name, i + 1)


class MoveFaceFeatureTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Mf")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **kw):
        values = dict(move_face.defaults(self.doc, self.body, None), faces=top_name(self.body.Tip))
        values.update(kw)
        f = move_face.create(self.doc, self.body, None, values)
        self.doc.recompute()
        return f

    def test_moves_the_top_and_is_the_tip(self):
        f = self.make(distance="5 mm")
        self.assertIs(self.body.Tip, f)
        self.assertIs(kind_for(f), move_face)
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 15, 6)
        self.assertNotIn("Invalid", f.State)

    def test_read_gives_the_values_back(self):
        f = self.make(distance="3 mm", mode="step")
        v = move_face.read(self.doc, f)
        self.assertEqual((v["distance"], v["mode"], v["extent"]), ("3 mm", "step", "distance"))
        self.assertTrue(v["faces"])

    def test_the_distance_parameter_drives_it(self):
        f = self.make(distance="2 mm")
        name = model.bound_parameter(f, "Distance")
        self.assertTrue(name)
        model.set_model_parameter(self.doc, name, "4 mm")
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 14, 6)

    def test_an_earlier_feature_edited_keeps_the_face(self):
        f = self.make(distance="5 mm")
        self.pad.Length = 12
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 17, 6)

    def test_to_a_work_plane_follows_it(self):
        plane = self.body.newObject("PartDesign::Plane", "Target")
        plane.AttachmentSupport = [(util.xy_plane(self.body), "")]
        plane.MapMode = "FlatFace"
        plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 16), App.Rotation())
        self.body.Tip = self.pad  # the plane is no solid step: the feature goes after the pad
        self.doc.recompute()
        f = self.make(extent="to", to=plane.Name)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 16, 6)
        plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 18), App.Rotation())
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 18, 6)

    def test_a_face_gone_says_so(self):
        f = self.make(distance="5 mm")
        self.pad.Profile.AttachmentOffset = App.Placement(App.Vector(100, 0, 0), App.Rotation())  # the part moved away
        self.doc.recompute()
        self.assertIn("Invalid", f.State)
        self.assertIn(move_face.mf.GONE_MSG, f.getStatusString())

    def test_suppress_gives_the_shape_before(self):
        f = self.make(distance="5 mm")
        from incad.core import suppress
        suppress.toggle(f)
        self.doc.recompute()
        self.assertAlmostEqual(self.body.Shape.Volume, 20 * 10 * 10, 6)

    def test_a_moved_body(self):
        self.body.Placement = App.Placement(App.Vector(100, 50, 7), App.Rotation(App.Vector(0, 0, 1), 30))
        self.doc.recompute()
        f = self.make(distance="5 mm")
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 15, 6)
        point, normal = move_face.arrow(f)
        self.assertAlmostEqual(normal.z, 1, 9)
        self.assertAlmostEqual(point.z, 7 + 15, 6)  # global: on the moved face

    def test_face_on_a_second_solid(self):
        """A second Solid (as tests/headless/test_make_assembly.py makes one); Move Face on its top goes into it."""
        other = document.new_solid(self.doc)
        pin = other.newObject("PartDesign::AdditiveBox", "Away")
        pin.Length, pin.Width, pin.Height = 6, 6, 4
        pin.Placement = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        other.Tip = pin
        self.doc.recompute()
        values = dict(move_face.defaults(self.doc, other, None), faces=top_name(other.Tip), distance="2 mm")
        f = move_face.create(self.doc, other, None, values)
        self.doc.recompute()
        self.assertIs(f.getParentGeoFeatureGroup(), other)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 6, 6)
        self.assertAlmostEqual(self.pad.Shape.BoundBox.ZMax, 10, 6)  # the first Solid untouched
```

(`document.new_solid`, `suppress.toggle(obj)` and the AdditiveBox are what the existing tests use.)

- [ ] **Step 2: Run** `tests/run_headless.sh test_move_face.py` → errors: `cannot import name 'move_face'`.

- [ ] **Step 3: Implement** `InCad/incad/features/move_face.py` (shape after `incad.features.split`):

```python
"""Move Face (direct editing): flat faces moved by a distance or up to a parallel face / plane, the neighbours
following Inventor's way, as a straight Step, or Together with the chamfers / fillets next to them. A step at the tip
(a PartDesign::FeaturePython) that finds its faces again by geometry on every recompute (incad.core.move_face), so it
never depends on face names."""
import json

import FreeCAD as App

from incad.core import move_face as mf
from incad.features.common import Field, parse_picks, resolve, value_param, value_text

TITLE = "Move Face"
ICON = "move_face"
TYPES = ("PartDesign::FeaturePython",)
NEEDS_PROFILE = False
STRUCTURAL = ()
PROPS = {"distance": "Distance"}
PRESELECT = {"faces": "faces"}  # faces selected before the command fill the field
_STORE = "InCadMoveFace"

FIELDS = (
    Field("faces", "Faces", "picks", pick="face"),
    Field("extent", "Extent", "choice", (("distance", "Distance"), ("to", "To")), "distance"),
    Field("distance", "Distance", "value_length", default="5 mm", show_if=("extent", ("distance",))),
    Field("to", "To", "pick", pick="plane", show_if=("extent", ("to",))),
    Field("mode", "Neighbours", "choice", (("inventor", "Inventor"), ("step", "Step"), ("together", "Together")),
          "inventor"),
)


def _load_json(text, default):
    try:
        return json.loads(text or "")
    except ValueError:
        return default


class MoveFaceFeature:
    """The proxy. FreeCAD saves its module path (incad.features.move_face) and class name in the file."""
    def __init__(self, obj):
        for prop, kind in (("Distance", "App::PropertyDistance"), ("Mode", "App::PropertyString"),
                           ("Extent", "App::PropertyString"), ("Target", "App::PropertyLinkSub"),
                           ("Signatures", "App::PropertyString")):
            if prop not in obj.PropertiesList:
                obj.addProperty(kind, prop, "Move Face", "")
        obj.setPropertyStatus("Signatures", "Hidden")
        obj.Proxy = self

    def execute(self, obj):
        base = obj.BaseFeature
        if base is None or base.Shape.isNull():
            return
        shape = base.Shape
        faces = []
        for sig in _load_json(obj.Signatures, []):
            f = mf.find(shape, sig)
            if f is None:
                raise ValueError(mf.GONE_MSG)
            faces.append(f)
        if not faces:
            raise ValueError(mf.FACES_MSG)
        if obj.Extent == "to":
            d = mf.gap_to(faces, _target(obj, shape))
        else:
            d = obj.Distance.Value
        obj.Shape = mf.apply(shape, faces, d, obj.Mode or "inventor")

    def dumps(self):
        return None

    def loads(self, state):
        return None


def _body_frame(obj):
    body = obj.getParentGeoFeatureGroup()
    return body.getGlobalPlacement().inverse() if body is not None else App.Placement()


def _target(obj, shape):
    """The To target as (point, normal) in the body's frame: a work / origin plane or a flat face."""
    link = obj.Target
    if not link or link[0] is None:
        raise ValueError(mf.PARALLEL_MSG)
    target, subs = link[0], link[1]
    to_body = _body_frame(obj)
    if subs and subs[0]:
        face = target.Shape.getElement(subs[0])  # a feature's face: same frame as the body's shapes
        return face.CenterOfMass, face.normalAt(0, 0)
    pl = to_body.multiply(target.getGlobalPlacement())  # a datum plane: its placement's Z axis
    return pl.Base, pl.Rotation.multVec(App.Vector(0, 0, 1))


def claims(feature):
    return hasattr(feature, _STORE)


def defaults(doc, body, profile=None):
    values = {f.key: f.default for f in FIELDS}
    values.update(faces="", to="")
    return values


def _picked_faces(doc, text):
    out = []
    for obj, sub in parse_picks(doc, text):
        obj, sub = resolve(obj, sub)
        if obj is None or not sub.startswith("Face"):
            continue
        out.append(obj.Shape.getElement(sub))
    return out


def _store(f, data):
    if not hasattr(f, _STORE):
        f.addProperty("App::PropertyString", _STORE, "InCad", "InCad move face settings")
        f.setPropertyStatus(_STORE, "Hidden")
    setattr(f, _STORE, json.dumps(data, sort_keys=True))


def _build(doc, f, values):
    faces = _picked_faces(doc, values.get("faces"))
    mf.check_faces(faces)
    f.Signatures = json.dumps([mf.signature(face) for face in faces])
    f.Mode = values.get("mode") or "inventor"
    f.Extent = values.get("extent") or "distance"
    if f.Extent == "to":
        picks = parse_picks(doc, values.get("to"))
        if not picks:
            raise ValueError(mf.PARALLEL_MSG)
        obj, sub = resolve(*picks[0])
        f.Target = (obj, [sub] if sub else [])
    else:
        value_param(doc, f, "Distance", values.get("distance") or "5 mm", "length")
    _store(f, {"faces": values.get("faces") or "", "to": values.get("to") or ""})
    return f


def create(doc, body, profile, values):
    tip = body.Tip
    f = body.newObject("PartDesign::FeaturePython", "MoveFace")
    MoveFaceFeature(f)
    f.BaseFeature = tip
    from incad.core import document
    document.show_like(f, tip)
    try:
        _build(doc, f, values)
        body.Tip = f
        doc.recompute()
        document.show_like(f, tip)
        if "Invalid" in f.State:
            raise ValueError(f.getStatusString() or "The faces could not be moved")
    except Exception:
        body.removeObject(f)
        doc.removeObject(f.Name)
        body.Tip = tip
        doc.recompute()
        raise
    return f


def read(doc, f):
    data = _load_json(getattr(f, _STORE, ""), {})
    values = defaults(doc, f.getParentGeoFeatureGroup(), None)
    values.update(faces=data.get("faces", ""), to=data.get("to", ""), mode=f.Mode or "inventor",
                  extent=f.Extent or "distance")
    values["distance"] = value_text(doc, f, "Distance") or "%g mm" % f.Distance.Value
    return values


def update(doc, f, values):
    _build(doc, f, values)
    doc.recompute()
    if "Invalid" in f.State:
        raise ValueError(f.getStatusString() or "The faces could not be moved")
    return f


def param_names(f):
    from incad.core import model
    name = model.bound_parameter(f, "Distance")
    return {"distance": name} if name else {}


def arrow(f):
    """The drag arrow's place: the first face's centre and outward normal, in global coordinates (after the move)."""
    sigs = _load_json(getattr(f, "Signatures", ""), [])
    if not sigs or f.Shape.isNull():
        return None
    n = App.Vector(*sigs[0]["n"])
    p = App.Vector(*sigs[0]["p"])
    d = f.Distance.Value
    if f.Extent == "to":
        try:
            d = mf.gap_to([mf.find(f.BaseFeature.Shape, sigs[0])], _target(f, f.BaseFeature.Shape))
        except Exception:
            d = 0.0
    to_global = f.getParentGeoFeatureGroup().getGlobalPlacement()
    return to_global.multVec(p + n * d), to_global.Rotation.multVec(n)
```

Then add `move_face` to the import and the list in `features/__init__.py:kinds()` (after `split`). Checks while
implementing: how the existing kinds pick a plane for "To" (Extrude's `to` field: copy its `pick=` kind so a work
plane, an origin plane and a flat face all pass `common.accepts`); `document.show_like` and `body.newObject` as in
`split.create`; a `picks` field with `pick="face"` + `PRESELECT` as Fillet / Draft use it (read
`features/dressup.py` and how `feature_session._apply_preselection` fills it).

- [ ] **Step 4: Run** `tests/run_headless.sh test_move_face.py` → OK; then `tests/run_headless.sh test_split.py` and
  `tests/run_headless.sh test_features.py` (kind lists) → OK.

- [ ] **Step 5: Commit** — "Move Face feature: a step at the tip, Distance (a parameter) or To, Inventor / Step /
  Together, faces found by geometry".

---

### Task 4: Command, ribbon, menus, icon

**Files:**
- Modify: `InCad/incad/actions.py` (a `Command` next to `feature.split`, ~line 974)
- Modify: `InCad/incad/ui/ribbon_layout.py:10-11` (Modify group)
- Modify: `InCad/incad/ui/marking_layout.py:13-16` (face list)
- Modify: `tools/make_icons.py` (an icon `move_face`), regenerate `InCad/incad/resources/icons/{dark,light}/move_face.svg`
- Test: `tests/widgets/test_commands.py`, `tests/widgets/test_marking_layout.py` (whatever lists every command / slot)

**Interfaces:**
- Produces: command id `feature.move_face` (label "Move Face", icon "move_face", contexts part,
  tooltip "Move flat faces by a distance or up to a face; the neighbours follow (Inventor), stay (Step) or move with
  them (Together)").

- [ ] **Step 1: Write the failing test** — in `tests/widgets/test_commands.py` (follow how it checks `feature.split`):

```python
    def test_move_face_is_on_the_ribbon_and_the_face_menu(self):
        from incad.ui import marking_layout, ribbon_layout
        modify = [g for tab, groups in ribbon_layout.LAYOUT["part"] if tab == "3D Model"
                  for g in groups if g[0] == "Modify"][0][1]
        flat = [c for item in modify for c in (item if isinstance(item, list) else [item])]
        self.assertIn("feature.move_face", flat)
        self.assertIn("feature.move_face", marking_layout.LAYOUT["face"]["list"])
```

- [ ] **Step 2: Run** `tests/run_widgets.sh test_commands.py` → FAIL.

- [ ] **Step 3: Implement**
  - `actions.py`:
    ```python
            Command(id="feature.move_face", label="Move Face", icon="move_face",
                    handler=lambda: start_feature("move_face"), contexts=frozenset({"part"}),
                    tooltip="Move flat faces by a distance or up to a face; the neighbours follow (Inventor), stay "
                            "(Step) or move with them (Together)"),
    ```
  - `ribbon_layout.py` Modify group: `"feature.thread", "feature.threads_toggle", "feature.combine", "feature.split",
    "feature.move_face"]]`.
  - `marking_layout.py` face list: add `"feature.move_face"` after `"feature.fillet"`.
  - `tools/make_icons.py` `ICONS`: `'move_face': '<rect x="5" y="14" width="22" height="12" fill="{F}" stroke="{S}"
    stroke-width="1.6"/><rect x="5" y="9" width="22" height="5" fill="none" stroke="{A}" stroke-width="1.6"
    stroke-dasharray="2 1.5"/><path d="M16 3 V10 M12.5 6 L16 2.5 L19.5 6" stroke="{A}" stroke-width="2" fill="none"/>'`;
    run the tool the way its `main()` says (read the top of the file) so both themes get the SVG.

- [ ] **Step 4: Run** `tests/run_widgets.sh test_commands.py test_marking_layout.py test_actions.py` → OK (update any
  list of every command id these tests keep).

- [ ] **Step 5: Commit** — "Move Face: on the ribbon (3D Model ▸ Modify), the face menu, its icon".

---

### Task 5: The drag arrow and the live distance label

**Files:**
- Create: `InCad/incad/ui/move_face_arrow.py`
- Modify: `InCad/incad/ui/shell.py` (`_open_session` ~2036, `_session_closed` ~1780: a kind's `overlay` hook)
- Modify: `InCad/incad/features/move_face.py` (`overlay(shell, session)`)
- Test: `tests/gui/test_move_face.py`

**Interfaces:**
- Consumes: `move_face.arrow(f)` (Task 3), `dof.glyph_size` (Task 1), `dof_handles.screen`, `dof_handles.mm_along`,
  `dof_handles.HANDLE_PX`, `dof_handles.segment_distance` (existing), `Navigator.handle_hook` protocol: `hover(view,
  viewport, x, y)`, `press(view, viewport, x, y) -> bool`, `move(x, y)`, `release() -> bool` (see `ui/nav.py:110-185`).
- Produces: `class FaceArrow` with `refresh()`, `press/hover/move/release`, `dragging() -> bool`, `remove()`,
  `label_text() -> str`; a kind hook `overlay(shell, session) -> object with .remove()`; shell keeps it in
  `self._overlay` and puts it in `navigator.handle_hook` while the session is open (restoring `self.dof_handles` after).

- [ ] **Step 1: Write the failing GUI test** — `tests/gui/test_move_face.py` (harness like `tests/gui/test_threads.py`;
  part from `headless.util.padded_part(doc, 10, incad=True)`; screen helpers from `tests/gui/test_dof_handles.py`):

```python
def test_1_dialog_and_typed_distance():
    select_top()                       # Gui.Selection.addSelection on the pad's top face
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1500)
    assert dialog() is not None and dialog().values()["faces"], dialog().values()
    set_distance("5 mm")               # field("distance").setText + editingFinished.emit()
    harness.pump(1500)
    assert abs(body().Shape.BoundBox.ZMax - 15) < 1e-6
    arrow = s()._overlay
    assert arrow is not None and arrow.label_text() == "5 mm", arrow.label_text()

def test_2_drag_the_arrow_changes_the_distance_and_shows_it():
    arrow = s()._overlay
    head = arrow_head_screen()         # dof_handles.screen of the arrow tip
    press(head); move_by(0, -40)       # QTest events on the viewport, as test_dof_handles does
    harness.pump(300)
    assert arrow.dragging()
    shown = arrow.label_text()
    assert shown.endswith("mm") and shown != "5 mm", shown   # the label follows the pointer during the drag
    release(); harness.pump(1500)
    assert not arrow.dragging()
    assert dialog().values()["distance"] == shown, (dialog().values()["distance"], shown)
    assert abs(body().Shape.BoundBox.ZMax - (10 + float(shown.split()[0]))) < 1e-6

def test_3_ok_is_one_undo_step_and_the_arrow_goes():
    n = len(doc().UndoNames)
    ok(); harness.pump(1200)
    assert doc().UndoNames[0] == "Move Face" and len(doc().UndoNames) == n + 1
    assert s()._overlay is None
    assert s().navigator.handle_hook is s().dof_handles

def test_4_edit_reopens_with_the_values_and_modes_switch():
    shell.edit_feature(body().Tip); harness.pump(1200)
    assert dialog().values()["mode"] == "inventor"
    dialog().set_values({"mode": "step"}); s().feature_session._changed(dialog().values()); harness.pump(1500)
    assert not dialog().error_text(), dialog().error_text()
    s().feature_session.cancel(); harness.pump(900)

def test_5_a_command_ends_the_drag():
    select_top(); commands.REGISTRY.run("feature.move_face"); harness.pump(1500)
    arrow = s()._overlay
    press(arrow_head_screen()); move_by(0, -20); harness.pump(300)
    assert arrow.dragging()
    commands.REGISTRY.run("view.zoom_all"); harness.pump(500)
    assert not arrow.dragging(), "the command ended the drag"
    assert dialog() is not None and dialog().values()["distance"].endswith("mm")
    s().feature_session.cancel(); harness.pump(900)
```

Write the helpers (`select_top`, `set_distance`, `arrow_head_screen`, `press`, `move_by`, `release`, `dialog`, `ok`,
`body`, `doc`) at the top of the file from `test_threads.py` / `test_dof_handles.py` (copy their bodies, they are
small). End with `harness.run([...])` listing the five tests in order.

- [ ] **Step 2: Run** `tests/run_gui.sh tests/gui/test_move_face.py` → FAIL at test 1 (`_overlay` missing).

- [ ] **Step 3: Implement**
  - `ui/move_face_arrow.py`:
    ```python
    """Move Face's drag arrow: drawn on the first face along its normal (the assembly gizmo's look and size), hit in
    screen space (dof_handles.HANDLE_PX), dragged by InCad itself through Navigator.handle_hook; a label at the tip
    shows the distance live (like Fusion). The dialog's Distance field follows the drag; a typed value moves it."""
    from pivy import coin

    from incad.core import dof
    from incad.ui import dof_handles as dh

    NAME = "InCadMoveFaceArrow"


    class FaceArrow:
        def __init__(self, shell, session):
            self.shell, self.session = shell, session
            self.root, self._drag, self._label = None, None, ""
            self.refresh()

        def _view(self):
            import FreeCADGui as Gui
            gdoc = Gui.getDocument(self.session.doc_name)
            return gdoc.ActiveView if gdoc is not None else None

        def _place(self):
            from incad.features import move_face
            f = self.session.feature
            return move_face.arrow(f) if f is not None else None

        def label_text(self):
            return self._label

        def dragging(self):
            return self._drag is not None

        def refresh(self):
            """Redraw at the feature's current place (after every preview) with the dialog's distance."""
            self._remove_node()
            place, view = self._place(), self._view()
            if place is None or view is None:
                return
            point, normal = place
            f = self.session.feature
            size = dof.glyph_size(f.Shape.BoundBox.DiagonalLength)
            self._label = self.session.dialog.values().get("distance", "") if self.session.dialog else ""
            self.root = _arrow_node(point, normal, size, self._label, self.shell.theme)
            view.getSceneGraph().addChild(self.root)
            self._geom = (point, normal, size)

        def _remove_node(self):
            view = self._view()
            if self.root is not None and view is not None:
                view.getSceneGraph().removeChild(self.root)
            self.root = None

        def _tip_px(self, view, viewport):
            point, normal, size = self._geom
            return dh.screen(view, viewport, point), dh.screen(view, viewport, point + normal * size)

        def hover(self, view, viewport, x, y):
            return False

        def press(self, view, viewport, x, y):
            if self.root is None or self.session.dialog is None:
                return False
            if self.session.dialog.values().get("extent") != "distance":
                return False
            a, b = self._tip_px(view, viewport)
            if dh.segment_distance((x, y), a, b) > dh.HANDLE_PX:
                return False
            point, normal, size = self._geom
            per_mm = ((b[0] - a[0]) / size, (b[1] - a[1]) / size)  # screen px per mm along the arrow
            start = _mm(self.session.dialog.values().get("distance"))
            self._drag = (x, y, per_mm, start)
            return True

        def move(self, x, y):
            if self._drag is None:
                return
            x0, y0, per_mm, start = self._drag
            d = round(start + dh.mm_along((x - x0, y - y0), per_mm), 1)
            text = "%g mm" % d
            self._label = text
            _set_label(self.root, text)
            dialog = self.session.dialog
            dialog.set_values({"distance": text})
            self.session._changed(dialog.values())  # the throttled preview, as typing does

        def release(self):
            was = self._drag is not None
            self._drag = None
            return was

        def finish(self, moved_ok=True, closing=False):
            self._drag = None

        def remove(self):
            self._drag = None
            self._remove_node()
    ```
    Plus the module functions `_mm(text)` (parse "5 mm" / a formula through `App.Units.Quantity`, 0 on failure),
    `_arrow_node(point, normal, size, text, theme)` (an `SoAnnotation` named `NAME` with `SoPickStyle UNPICKABLE`, a
    line + cone like `ui/dof_glyphs.py` draws a slide arrow — copy that code path and its theme colours — and an
    `SoText2` label at `point + normal * size * 1.15` in the theme's text colour) and `_set_label(root, text)`. Read
    `ui/dof_glyphs.py` and copy its arrow drawing (no new look).
  - `features/move_face.py`:
    ```python
    def overlay(shell, session):
        from incad.ui.move_face_arrow import FaceArrow
        return FaceArrow(shell, session)
    ```
  - `ui/shell.py`: in `_open_session`, after `started = fs.start()` succeeded:
    ```python
        hook = getattr(kind, "overlay", None)
        if started and hook is not None:
            self._overlay = hook(self, fs)
            self.navigator.handle_hook = self._overlay
    ```
    in `_session_closed`: `if self._overlay is not None: self._overlay.remove(); self._overlay = None;
    self.navigator.handle_hook = self.dof_handles`; init `self._overlay = None` in `__init__` next to
    `self.feature_session = None`. After each preview the arrow must follow: in `feature_session._preview_now`'s end
    (where the preview succeeded) call `self.on_previewed()` if set; shell sets `fs.on_previewed = lambda:
    self._overlay.refresh() if self._overlay else None`. A command run while dragging: shell already ends DOF drags
    before a command (`grep -n "finish(" ui/shell.py` near the command dispatch) — call `self._overlay.finish()` there
    too.
- [ ] **Step 4: Run** `tests/run_gui.sh tests/gui/test_move_face.py` → 5 passed; then
  `tests/run_gui.sh tests/gui/test_dof_handles.py tests/gui/test_features.py tests/gui/test_threads.py` → pass
  (keyboard-focus tests fail only when the Mac is in use: rerun those alone before calling them broken).
- [ ] **Step 5: Commit** — "Move Face: a drag arrow on the face with the distance shown at it (like Fusion)".

---

### Task 6: Docs, release notes, the user's part

**Files:**
- Modify: `README.md` (Features: a Move Face line), `docs/manual/en.html`, `docs/manual/ru.html` (a Move Face section
  in Part features with the three modes; the gizmo arrows unchanged in text), `scripts/dist/CHANGES.txt`,
  `scripts/dist/CHANGES_ru.txt` (a new top section `0.3.0` "Improvements": Move Face; "Assembly: the gizmo arrows are
  a little smaller" — the version bump itself happens at the next build, with `scripts/make_dist.sh`)
- Test: run on a copy of one of the user's parts

- [ ] **Step 1:** Write the docs (English, then Russian in natural Russian with UI names in English as on screen).
- [ ] **Step 2:** `scripts/print_manual.sh` → both PDFs print; look at the contact sheets.
- [ ] **Step 3:** On a copy (scratchpad) of `/Volumes/Docs/Plasticity_projects/Train_1-Solid2.FCStd` (never the
  original, never saved there): in freecadcmd, Move Face on its top face +3 in each mode → valid, one solid, report the
  volumes; any refusal message must be one of the spec's texts.
- [ ] **Step 4: Commit** — "Move Face: README, manual (EN / RU), release notes".
