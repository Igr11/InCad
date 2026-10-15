# Move Face on round walls — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Face offsets a straight round wall (a hole, a boss, an extruded ellipse / spline band) outward or
inward by a distance, with the Inventor / Step / Together neighbours, as an ordinary Move Face step.

**Architecture:** A new core module `incad/core/round_wall.py` finds the wall (all its pieces), cuts its section,
offsets that outline in 2D and builds a ring slab per mode (Together: a 3D offset of the slice of the part around the
wall and its blends); the slab is fused on or cut away by the same final step flat Move Face uses (extracted to
`move_face.combine`). `incad/features/move_face.py` tells flat picks from round walls, stores walls by geometry, and
routes recompute, the arrow and the dialog's choices.

**Tech Stack:** FreeCAD 1.1.3 (OCC via `Part`), Python 3.11 (FreeCAD's bundled), unittest; tests run through
`tests/run_headless.sh <file pattern>` (freecadcmd) and `tests/run_gui.sh <file>` (a real FreeCAD window).

**Spec:** `docs/superpowers/specs/2026-10-15-incad-move-round-face-design.md`

## Global Constraints

- UI text English; messages exactly as in the spec:
  - `MIXED_MSG = "Pick flat faces or round walls, not both"`
  - `NOT_STRAIGHT_MSG = "Pick a flat face or a straight round wall"`
  - `OPEN_MSG = "Pick a whole round wall (a ring); a part of one comes later"`
  - reuse `mf.TOO_LARGE_MSG`, `mf.ROUND_MSG`, `mf.WALLS_MSG`, `mf.GONE_MSG` from `incad.core.move_face` unchanged.
- Distance only for round walls ("To" greyed out); + outward from the material, − inward; starts at 0 mm.
- Straight-walled faces only: `Cylinder`, `SurfaceOfExtrusion`, or a B-spline / Bezier wall square to one direction
  everywhere. Closed walls only (the section is a closed wire).
- One click takes the whole wall: every piece of the same surface joined by shared edges.
- Never a raw OCC error to the user: any `Part.OCCError` in a round-wall move → `TOO_LARGE_MSG`.
- No face names stored: walls are stored and found by geometry, as flat faces are.
- FreeCAD facts (CLAUDE.md): no pytest (unittest only); a failed feature has `'Invalid'` in `obj.State` and the reason
  in `obj.getStatusString()`.
- Run only the affected test files while working; the full suites at most once before a commit.
- **Commits:** the user has asked not to commit until they have tested; main holds uncommitted fixes from 2026-10-14.
  Each task's "Commit" step is: ask the user once before the first commit whether to commit (and whether together
  with those fixes); if not, skip every commit step and leave the work uncommitted.

## Review Focus

1. A seam-split cylinder (OCC makes a full cylinder of one face with a seam edge; an imported or refined part of two
   halves): one click must take the whole ring either way — test both.
2. A hole (material outside the section) vs a boss (material inside): + must shrink the hole and grow the boss —
   the outward side comes from the face normal, never from the offset's own sign convention.
3. An inward move larger than a hole's / ellipse's smallest radius of curvature: a clean TOO_LARGE_MSG, never an
   invalid solid or a raw OCC error.
4. A round wall whose top is a slanted flat face (Inventor): the slab must reach the slanted plane, no gap or step.
5. A part with another wall inside the band's height (the user's hollow upper ring, an inner hole) in Together: that
   wall must be left exactly as it was.

---

## File Structure

- Create `InCad/incad/core/round_wall.py` — round walls: detection, pieces, section, signature / find, ring slab per
  mode, arrow point. One responsibility: the geometry of moving a round wall.
- Modify `InCad/incad/core/move_face.py` — extract the final fuse / cut / check of `_moved` into `combine(shape,
  adds, cuts)` used by both flat faces and round walls.
- Modify `InCad/incad/features/move_face.py` — picks classified (flat / round wall / mixed / not straight), wall
  signatures stored with `"kind": "wall"`, recompute, `read`, `_current_picks`, `arrow`, `unavailable`.
- Create `tests/headless/test_round_wall.py` — geometry tests on built shapes.
- Modify `tests/headless/test_move_face.py` — feature tests on round walls.
- Create `tests/headless/test_round_wall_user_body.py` — the user's body (a copy of their file).
- Modify `tests/gui/test_move_face.py` — picking the band in the real window.

---

### Task 1: Find a round wall, its pieces and its section

**Files:**
- Create: `InCad/incad/core/round_wall.py`
- Test: `tests/headless/test_round_wall.py`

**Interfaces:**
- Consumes: `incad.core.move_face` — `_is_plane(face)`, `_along(face, n)`.
- Produces:
  - `direction(face) -> App.Vector | None` — the wall's direction (unit), None when the face is no straight wall.
  - `is_round_wall(face) -> bool`
  - `pieces(shape, face) -> (list[Part.Face], App.Vector)` — all faces of the wall the picked face belongs to, and a.
  - `extent(faces, a) -> (float, float)` — h0, h1 along a.
  - `section(faces, a, h0, h1) -> Part.Wire` — the closed section at mid height (OPEN_MSG when not closed).
  - `material_inside(faces, wire, a) -> bool` — True for a boss (material inside the section), False for a hole.
  - constants `MIXED_MSG`, `NOT_STRAIGHT_MSG`, `OPEN_MSG`.

- [ ] **Step 1: Write the failing tests**

```python
"""Round walls for Move Face (incad.core.round_wall): which faces, their pieces, the section and the material side."""
import math
import unittest

import FreeCAD as App
import Part

from incad.core import round_wall as rw

V = App.Vector
UP = V(0, 0, 1)


def boss():
    """A 40 x 30 x 5 block with a cylinder boss r 5, 10 high, on top at (20, 15)."""
    return Part.makeBox(40, 30, 5).fuse(Part.makeCylinder(5, 10, V(20, 15, 5))).removeSplitter()


def holed():
    """A 40 x 30 x 10 block with a through hole r 5 at (20, 15)."""
    return Part.makeBox(40, 30, 10).cut(Part.makeCylinder(5, 10, V(20, 15, 0)))


def ellipse_pad(h=10):
    """The user's band shape: a 3-point ellipse (20 x 10) extruded h; its wall is a SurfaceOfExtrusion."""
    ring = Part.Ellipse(V(20, 0, 0), V(0, 10, 0), V(0, 0, 0)).toShape()
    return Part.Face(Part.Wire(ring)).extrude(V(0, 0, h))


def wall_of(shape, kind):
    return next(f for f in shape.Faces if type(f.Surface).__name__ == kind)


class Detection(unittest.TestCase):
    def test_cylinder_and_extruded_ellipse_are_round_walls(self):
        self.assertTrue(rw.is_round_wall(wall_of(boss(), "Cylinder")))
        self.assertTrue(rw.is_round_wall(wall_of(ellipse_pad(), "SurfaceOfExtrusion")))
        self.assertTrue(abs(abs(rw.direction(wall_of(ellipse_pad(), "SurfaceOfExtrusion")).dot(UP)) - 1) < 1e-9)

    def test_flat_faces_cones_and_spheres_are_not(self):
        self.assertFalse(rw.is_round_wall(next(f for f in boss().Faces if rw.mf._is_plane(f))))
        self.assertFalse(rw.is_round_wall(Part.makeCone(5, 2, 10).Faces[0]))
        self.assertFalse(rw.is_round_wall(Part.makeSphere(5).Faces[0]))


class Pieces(unittest.TestCase):
    def test_a_one_face_cylinder_is_its_own_wall(self):
        shape = boss()
        faces, a = rw.pieces(shape, wall_of(shape, "Cylinder"))
        self.assertEqual(len(faces), 1)

    def test_a_wall_split_in_two_halves_is_taken_whole(self):
        """Review focus 1: a seam-split ring (two half-cylinders) — one click takes both halves."""
        half = Part.makeCylinder(5, 10, V(0, 0, 0), UP, 180)
        other = Part.makeCylinder(5, 10, V(0, 0, 0), UP, 180).rotated(V(0, 0, 0), UP, 180)
        shape = half.fuse(other)  # no removeSplitter: two cylinder faces stay
        cyl = [f for f in shape.Faces if type(f.Surface).__name__ == "Cylinder"]
        self.assertEqual(len(cyl), 2)
        faces, _ = rw.pieces(shape, cyl[0])
        self.assertEqual(len(faces), 2)


class Section(unittest.TestCase):
    def test_section_of_the_boss_is_its_circle_at_mid_height(self):
        shape = boss()
        faces, a = rw.pieces(shape, wall_of(shape, "Cylinder"))
        h0, h1 = rw.extent(faces, a)
        self.assertAlmostEqual(h0, 5, 6)
        self.assertAlmostEqual(h1, 15, 6)
        wire = rw.section(faces, a, h0, h1)
        self.assertTrue(wire.isClosed())
        self.assertAlmostEqual(wire.Length, 2 * math.pi * 5, 4)
        self.assertAlmostEqual(wire.BoundBox.ZMin, 10, 6)

    def test_material_side_boss_inside_hole_outside(self):
        """Review focus 2: + grows a boss and shrinks a hole — the side comes from the face normal."""
        for shape, inside in ((boss(), True), (holed(), False)):
            faces, a = rw.pieces(shape, wall_of(shape, "Cylinder"))
            wire = rw.section(faces, a, *rw.extent(faces, a))
            self.assertEqual(rw.material_inside(faces, wire, a), inside)

    def test_an_open_wall_is_refused(self):
        """A rounded end between flat faces (half a cylinder on a box): not a ring."""
        shape = Part.makeBox(10, 10, 10).fuse(Part.makeCylinder(5, 10, V(10, 5, 0), UP, 180)
                                              .rotated(V(10, 5, 0), UP, -90)).removeSplitter()
        face = wall_of(shape, "Cylinder")
        faces, a = rw.pieces(shape, face)
        with self.assertRaises(ValueError) as e:
            rw.section(faces, a, *rw.extent(faces, a))
        self.assertEqual(str(e.exception), rw.OPEN_MSG)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_round_wall.py`
Expected: ERROR — `ImportError: cannot import name 'round_wall'`.

- [ ] **Step 3: Write the module**

```python
"""Round walls for Move Face: a cylinder or a curve extruded straight along one direction (a hole, a boss, an extruded
ellipse), offset along its own surface by a ring slab fused on or cut away (closed walls: the section is a ring)."""
import FreeCAD as App
import Part

from incad.core import move_face as mf

MIXED_MSG = "Pick flat faces or round walls, not both"
NOT_STRAIGHT_MSG = "Pick a flat face or a straight round wall"
OPEN_MSG = "Pick a whole round wall (a ring); a part of one comes later"
_TOL = 1e-6


def direction(face):
    """The unit direction a straight round wall runs along, or None (a flat face, a cone, a sphere, a free form)."""
    if mf._is_plane(face):
        return None
    s = face.Surface
    kind = type(s).__name__
    if kind == "Cylinder":
        return App.Vector(s.Axis).normalize()
    if kind == "SurfaceOfExtrusion":
        return App.Vector(s.Direction).normalize()
    if kind in ("BSplineSurface", "BezierSurface"):  # a straight B-spline wall (FreeCAD's refine makes them)
        u0, u1, v0, v1 = face.ParameterRange
        n1 = face.normalAt(u0 + (u1 - u0) * 0.25, (v0 + v1) / 2)
        n2 = face.normalAt(u0 + (u1 - u0) * 0.75, (v0 + v1) / 2)
        a = n1.cross(n2)
        if a.Length < 1e-9:
            return None
        a.normalize()
        return a if mf._along(face, a) else None
    return None


def is_round_wall(face):
    return direction(face) is not None


def _same_surface(face, other, a):
    d = direction(other)
    if d is None or abs(abs(d.dot(a)) - 1) > 1e-6:
        return False
    u0, u1, v0, v1 = other.ParameterRange
    p = other.valueAt((u0 + u1) / 2, (v0 + v1) / 2)
    try:
        return face.Surface.projectPoint(p, "LowerDistance") < 1e-6
    except Exception:
        return False


def pieces(shape, face):
    """Every face of the wall `face` belongs to: the faces of the same surface joined to it by shared edges."""
    a = direction(face)
    if a is None:
        raise ValueError(NOT_STRAIGHT_MSG)
    group, todo = [face], [face]
    while todo:
        f = todo.pop()
        for e in f.Edges:
            for g in shape.ancestorsOfType(e, Part.Face):
                if not any(g.isSame(x) for x in group) and _same_surface(face, g, a):
                    group.append(g)
                    todo.append(g)
    return group, a


def extent(faces, a):
    hs = [p.dot(a) for f in faces for e in f.Edges for p in e.discretize(16)]
    return min(hs), max(hs)


def section(faces, a, h0, h1):
    """The wall cut square to a at mid height: a closed wire, else OPEN_MSG."""
    mid = (h0 + h1) / 2
    edges = []
    for f in faces:
        for w in f.slice(a, mid):
            edges += w.Edges
    try:
        wire = Part.Wire(Part.__sortEdges__(edges))
    except Exception:
        raise ValueError(OPEN_MSG)
    if not wire.isClosed():
        raise ValueError(OPEN_MSG)
    return wire


def _middle(face):
    u0, u1, v0, v1 = face.ParameterRange
    return face.valueAt((u0 + u1) / 2, (v0 + v1) / 2), face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)


def material_inside(faces, wire, a):
    """True when the material is inside the section (a boss), False when outside (a hole): a step off the wall along
    its outward normal (FreeCAD's normalAt follows the solid's face orientation) lands outside or inside it."""
    p, n = _middle(faces[0])
    probe = p + n * 0.01
    probe = probe - a * (probe.dot(a) - wire.Vertexes[0].Point.dot(a))  # onto the section's plane
    return not Part.Face(wire).isInside(probe, 1e-7, True)
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_round_wall.py`
Expected: `OK` (7 tests). If `test_a_wall_split_in_two_halves_is_taken_whole` finds one face only, OCC merged the
halves: build the halves with `Part.makeCompound` + `Part.Solid(Part.Shell(...))` from `half.Faces + other.Faces`
minus the shared flat faces instead, keeping two cylinder faces.

- [ ] **Step 5: Commit** (see Global Constraints: ask first)

```bash
git add InCad/incad/core/round_wall.py tests/headless/test_round_wall.py
git commit -m "Move Face: round walls found with all their pieces, their section and material side"
```

---

### Task 2: Offset a round wall — Step and Inventor

**Files:**
- Modify: `InCad/incad/core/move_face.py` (`_moved`: extract `combine`)
- Modify: `InCad/incad/core/round_wall.py`
- Test: `tests/headless/test_round_wall.py`

**Interfaces:**
- Consumes: Task 1's `pieces`, `extent`, `section`, `material_inside`.
- Produces:
  - `mf.combine(shape, adds, cuts) -> Part.Shape` — fuse adds, cut cuts, removeSplitter, valid + same solid count
    else `ValueError(TOO_LARGE_MSG)`.
  - `rw.offset(shape, walls, d, mode) -> Part.Shape` — `walls`: list of picked faces (one per wall, pieces found
    inside); `mode` in `("inventor", "step", "together")` (together: Task 3; here it raises NotImplementedError
    until Task 3).

- [ ] **Step 1: Write the failing tests** (append to `tests/headless/test_round_wall.py`)

```python
def ring_area(r_out, r_in):
    return math.pi * (r_out ** 2 - r_in ** 2)


class StepAndInventor(unittest.TestCase):
    def test_boss_grows_and_shrinks_exactly(self):
        for mode in ("step", "inventor"):
            for d in (1.0, -1.0):
                shape = boss()
                moved = rw.offset(shape, [wall_of(shape, "Cylinder")], d, mode)
                self.assertTrue(moved.isValid(), (mode, d))
                self.assertAlmostEqual(moved.Volume - shape.Volume, math.copysign(ring_area(5 + max(d, 0), 5 + min(d, 0)), d) * 10, 3)
                cyl = wall_of(moved, "Cylinder")
                self.assertAlmostEqual(cyl.Surface.Radius, 5 + d, 6, (mode, d))

    def test_plus_makes_a_hole_smaller(self):
        shape = holed()
        moved = rw.offset(shape, [wall_of(shape, "Cylinder")], 1.0, "step")
        self.assertAlmostEqual(wall_of(moved, "Cylinder").Surface.Radius, 4, 6)
        self.assertAlmostEqual(moved.Volume - shape.Volume, ring_area(5, 4) * 10, 3)
        bigger = rw.offset(shape, [wall_of(shape, "Cylinder")], -1.0, "step")
        self.assertAlmostEqual(wall_of(bigger, "Cylinder").Surface.Radius, 6, 6)

    def test_ellipse_band_offset_by_the_exact_outline(self):
        shape = ellipse_pad()
        wall = wall_of(shape, "SurfaceOfExtrusion")
        base = Part.Face(Part.Wire(Part.Ellipse(V(20, 0, 0), V(0, 10, 0), V(0, 0, 0)).toShape()))
        for d in (1.0, -1.0):
            moved = rw.offset(shape, [wall], d, "step")
            grown = Part.Face(base.OuterWire.makeOffset2D(d))
            self.assertTrue(moved.isValid())
            self.assertAlmostEqual(moved.Volume - shape.Volume, (grown.Area - base.Area) * 10, 2)

    def test_inventor_reaches_a_slanted_top(self):
        """Review focus 4: a cylinder cut by a slanted plane at the top — the slab reaches that plane."""
        cyl = Part.makeCylinder(5, 20)
        cutter = Part.makeBox(40, 40, 40, V(-20, -20, 10)).rotated(V(0, 0, 10), V(1, 0, 0), 20)
        shape = cyl.cut(cutter)
        moved = rw.offset(shape, [wall_of(shape, "Cylinder")], 1.0, "inventor")
        self.assertTrue(moved.isValid())
        top = next(f for f in moved.Faces if rw.mf._is_plane(f) and f.normalAt(0, 0).z > 0.5)
        self.assertEqual(len(moved.Solids), 1)
        for v in moved.Vertexes:  # nothing sticks out above the slanted top plane
            self.assertLess((v.Point - top.CenterOfMass).dot(top.normalAt(0, 0)), 1e-6)

    def test_inventor_refuses_a_fillet_next_to_the_wall(self):
        shape = ellipse_pad()
        top_ring = next(e for e in shape.Edges if abs(e.CenterOfMass.z - 10) < 1e-9)
        shape = shape.makeFillet(2, [top_ring])
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "inventor")
        self.assertEqual(str(e.exception), rw.mf.ROUND_MSG)

    def test_step_leaves_ledges_next_to_a_fillet(self):
        shape = ellipse_pad()
        top_ring = next(e for e in shape.Edges if abs(e.CenterOfMass.z - 10) < 1e-9)
        shape = shape.makeFillet(2, [top_ring])
        moved = rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "step")
        self.assertTrue(moved.isValid())
        self.assertGreater(moved.Volume, shape.Volume)

    def test_too_large_inward_is_refused_cleanly(self):
        """Review focus 3: more than the radius — a clean refusal."""
        shape = boss()
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "Cylinder")], -6.0, "step")
        self.assertEqual(str(e.exception), rw.mf.TOO_LARGE_MSG)
        shape = ellipse_pad()
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], -11.0, "step")
        self.assertEqual(str(e.exception), rw.mf.TOO_LARGE_MSG)

    def test_two_walls_picked_both_grow(self):
        shape = Part.makeBox(40, 20, 5).fuse([Part.makeCylinder(3, 6, V(10, 10, 5)),
                                              Part.makeCylinder(3, 6, V(30, 10, 5))]).removeSplitter()
        walls = [f for f in shape.Faces if type(f.Surface).__name__ == "Cylinder"]
        moved = rw.offset(shape, walls, 1.0, "inventor")
        self.assertTrue(moved.isValid())
        radii = sorted(round(f.Surface.Radius, 6) for f in moved.Faces if type(f.Surface).__name__ == "Cylinder")
        self.assertEqual(radii, [4.0, 4.0])
        self.assertAlmostEqual(moved.Volume - shape.Volume, 2 * ring_area(4, 3) * 6, 3)

    def test_zero_changes_nothing(self):
        shape = boss()
        self.assertIs(rw.offset(shape, [wall_of(shape, "Cylinder")], 0.0, "step"), shape)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_round_wall.py`
Expected: the new tests ERROR with `AttributeError: module 'incad.core.round_wall' has no attribute 'offset'`.

- [ ] **Step 3: Extract `combine` in `InCad/incad/core/move_face.py`**

Replace the tail of `_moved` (from `result = shape` to `return result`) with a call, and add the function:

```python
def combine(shape, adds, cuts):
    """The moved part: the slabs fused on and cut away, the split faces merged; a broken or split part is refused."""
    result = shape
    if adds:
        result = result.fuse(adds)
    if cuts:
        result = result.cut(cuts)
    result = result.removeSplitter()
    if not result.isValid() or len(result.Solids) != len(shape.Solids):
        raise ValueError(TOO_LARGE_MSG)
    return result
```

and in `_moved`: `return combine(shape, adds, cuts)` after the loop.

- [ ] **Step 4: Add the offset to `InCad/incad/core/round_wall.py`**

```python
def _ring(wire, d, inside):
    """The region between the section and its offset by d away from (d > 0: into the room beside) the material."""
    s = 1 if inside else -1
    try:
        moved = wire.makeOffset2D(s * d, 2)  # join 2: intersection (a smooth outline stays smooth)
        a, b = Part.Face(wire), Part.Face(moved)
    except Exception:
        raise ValueError(mf.TOO_LARGE_MSG)
    if not b.isValid() or b.Area < _TOL:
        raise ValueError(mf.TOO_LARGE_MSG)
    ring = b.cut(a) if s * d > 0 else a.cut(b)
    if ring.Area < _TOL:
        raise ValueError(mf.TOO_LARGE_MSG)
    return ring


def _rim_neighbours(shape, faces):
    """The faces across the wall's top and bottom edges (not its own pieces)."""
    out = []
    for f in faces:
        for e in f.Edges:
            for g in shape.ancestorsOfType(e, Part.Face):
                if not any(g.isSame(x) for x in faces) and not any(g.isSame(x) for x in out):
                    out.append(g)
    return out


def _half_space(plane_face, toward, size):
    """A big solid on the side of a flat face's plane where `toward` (a point of the wall) is: a boss's top keeps
    what is below it, the block's face the boss stands on keeps what is above it."""
    n = mf._normal(plane_face)
    c = plane_face.CenterOfMass
    side = n if (toward - c).dot(n) > 0 else n * -1
    u = n.cross(App.Vector(1, 0, 0) if abs(n.x) < 0.9 else App.Vector(0, 1, 0)).normalize()
    v = n.cross(u)
    sheet = Part.Face(Part.makePolygon([c + (u * x + v * y) * size for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1),
                                                                               (-1, -1))]))
    return sheet.extrude(side * 2 * size)


def _slab(shape, faces, a, d, mode):
    h0, h1 = extent(faces, a)
    wire = section(faces, a, h0, h1)
    inside = material_inside(faces, wire, a)
    ring = _ring(wire, d, inside)
    mid = (h0 + h1) / 2
    if mode == "step":
        return ring.translated(a * (h0 - mid)).extrude(a * (h1 - h0))
    if mode == "inventor":
        ends = _rim_neighbours(shape, faces)
        if any(not mf._is_plane(g) for g in ends):
            raise ValueError(mf.ROUND_MSG)
        size = shape.BoundBox.DiagonalLength + abs(d) + 1
        slab = ring.translated(a * (h0 - mid - size)).extrude(a * (h1 - h0 + 2 * size))
        toward = wire.Vertexes[0].Point  # a point of the wall at mid height
        for g in ends:  # trimmed / extended to the planes of the flat ends (slanted ones too)
            slab = slab.common(_half_space(g, toward, size))
        return slab
    raise NotImplementedError(mode)


def offset(shape, walls, d, mode):
    """The part with every picked wall offset by d (+ away from the material, i.e. more material)."""
    if abs(d) < _TOL:
        return shape
    adds, cuts = [], []
    try:
        for picked in walls:
            faces, a = pieces(shape, picked)
            slab = _slab(shape, faces, a, d, mode)
            if d < 0:
                if slab.cut(shape).Volume > 1e-6:  # the cut must lie inside the material
                    raise ValueError(mf.TOO_LARGE_MSG)
                cuts.append(slab)
            else:
                adds.append(slab)
        return mf.combine(shape, adds, cuts)
    except Part.OCCError:
        raise ValueError(mf.TOO_LARGE_MSG)
```

Note `_half_space` for a flat end square to a (a boss's top, the block's top face it stands on) keeps the wall's side
of that plane, which equals Step there — the planes only matter when slanted. The side is taken from where the wall
is, never from the face's normal alone: the block's top face around a boss points up, yet the boss is above it.

- [ ] **Step 5: Run to verify they pass, and the flat Move Face tests still pass**

Run: `tests/run_headless.sh test_round_wall.py` then `tests/run_headless.sh "test_move_face*.py"`
Expected: both `OK`. If `makeOffset2D(..., 2)` gives a slightly different ellipse area than the test's
`makeOffset2D(d)`, make the test call `makeOffset2D(d, 2)` too (the same join), never loosen the tolerance.

- [ ] **Step 6: Commit** (ask first)

```bash
git add InCad/incad/core/move_face.py InCad/incad/core/round_wall.py tests/headless/test_round_wall.py
git commit -m "Move Face: round walls offset by a ring slab, Step and Inventor"
```

---

### Task 3: Together — the wall with its fillets and chamfers

**Files:**
- Modify: `InCad/incad/core/round_wall.py` (`_slab` mode "together")
- Test: `tests/headless/test_round_wall.py`

**Interfaces:**
- Consumes: Task 2's `_ring`, `_rim_neighbours`, `offset`.
- Produces: `offset(shape, walls, d, "together")` working.

- [ ] **Step 1: Write the failing tests** (append)

```python
def user_like():
    """The user's kind of part: the ellipse pad, its top ring filleted 2, its bottom ring chamfered 1."""
    shape = ellipse_pad()
    top_ring = next(e for e in shape.Edges if abs(e.CenterOfMass.z - 10) < 1e-9)
    shape = shape.makeFillet(2, [top_ring])
    bottom_ring = next(e for e in shape.Edges if "Ellipse" in type(e.Curve).__name__ and abs(e.CenterOfMass.z) < 1e-9)
    return shape.makeChamfer(1, [bottom_ring])


class Together(unittest.TestCase):
    def test_the_band_and_its_blends_move_exactly_d(self):
        shape = user_like()
        wall = wall_of(shape, "SurfaceOfExtrusion")
        for d in (1.0, -1.0):
            moved = rw.offset(shape, [wall], d, "together")
            self.assertTrue(moved.isValid(), d)
            new_wall = next(f for f in moved.Faces if type(f.Surface).__name__ != "Plane"
                            and rw.direction(f) is not None and abs(f.CenterOfMass.z - 5) < 3)
            for e in wall.Edges:  # every sampled point of the old wall is d from the new one
                for p in e.discretize(8):
                    if 2.5 < p.z < 7.5:
                        self.assertAlmostEqual(new_wall.distToShape(Part.Vertex(p))[0], abs(d), 3)
            self.assertAlmostEqual(moved.BoundBox.ZMax, 10, 6)  # the top stays where it was
            self.assertAlmostEqual(moved.BoundBox.ZMin, 0, 6)

    def test_another_wall_inside_the_band_height_stays(self):
        """Review focus 5: an inner hole through the part is left exactly as it was."""
        shape = user_like().cut(Part.makeCylinder(3, 10))
        hole = wall_of(shape, "Cylinder")
        moved = rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "together")
        self.assertTrue(moved.isValid())
        self.assertAlmostEqual(wall_of(moved, "Cylinder").Surface.Radius, hole.Surface.Radius, 9)

    def test_faces_beyond_that_do_not_fit_are_refused(self):
        """A cone above the fillet (neither flat nor along the wall): WALLS_MSG."""
        shape = user_like().fuse(Part.makeCone(4, 1, 5, V(0, 0, 10))).removeSplitter()
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "together")
        self.assertIn(str(e.exception), (rw.mf.WALLS_MSG,))
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_round_wall.py`
Expected: the Together tests ERROR with `NotImplementedError: together`.

- [ ] **Step 3: Implement Together** — in `_slab`, before `raise NotImplementedError(mode)`:

```python
    if mode == "together":
        return _together(shape, faces, a, d, wire, inside)
```

and add:

```python
def _plan_basis(a):
    u = a.cross(App.Vector(1, 0, 0) if abs(a.x) < 0.9 else App.Vector(0, 1, 0)).normalize()
    return u, a.cross(u)


def _prism(region, a, h_from, h_to, mid):
    return region.translated(a * (h_from - mid)).extrude(a * (h_to - h_from))


def _together(shape, faces, a, d, wire, inside):
    """The wall and the fillets / chamfers chained to its top and bottom edges offset as one piece: the slice of the
    part over their height offset by d in 3D, kept inside a ring around the wall only (other walls at that height
    stay); the faces beyond the blends must be flat or run along a."""
    group = list(faces)
    todo = list(faces)
    while todo:
        f = todo.pop()
        for g in _rim_neighbours(shape, [f]):
            if any(g.isSame(x) for x in group) or mf._is_plane(g) or mf._along(g, a):
                continue
            group.append(g)
            todo.append(g)
    for g in _rim_neighbours(shape, group):
        if not (mf._is_plane(g) or mf._along(g, a)):
            raise ValueError(mf.WALLS_MSG)
    m0, m1 = extent(group, a)
    h0, h1 = extent(faces, a)
    mid = (h0 + h1) / 2
    plane_pt = wire.Vertexes[0].Point
    depth = 0.0
    for g in group[len(faces):]:  # how far, seen along a, the blends reach in from the wall's outline
        for e in g.Edges:
            for p in e.discretize(12):
                q = p - a * (p.dot(a) - plane_pt.dot(a))
                depth = max(depth, wire.distToShape(Part.Vertex(q))[0])
    depth += 0.1
    s = 1 if inside else -1
    size = shape.BoundBox.DiagonalLength + abs(d) + 1
    u, v = _plan_basis(a)
    c = wire.CenterOfMass
    big = Part.Face(Part.makePolygon([c + (u * x + v * y) * size for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1),
                                                                             (-1, -1))]))
    piece = shape.common(_prism(big, a, m0, m1, mid))
    grown = piece.makeOffsetShape(d, 1e-6, join=2)  # + more material: the solid grows (holes and bosses alike)
    try:
        into = Part.Face(wire.makeOffset2D(-s * (depth + max(-d, 0)), 2))
        out = Part.Face(wire.makeOffset2D(s * (max(d, 0) + 0.1), 2))
    except Exception:
        raise ValueError(mf.TOO_LARGE_MSG)
    zone_region = out.cut(into) if inside else into.cut(out)
    zone = _prism(zone_region, a, m0, m1, mid)
    if d > 0:
        return grown.common(zone)
    return piece.common(zone).cut(grown)
```

`offset` already fuses a + slab and cuts a − slab; for Together the − slab is `(Q ∩ Z) − Q'`, which lies inside the
material, so the inside check passes.

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_round_wall.py`
Expected: `OK`. If `makeOffsetShape` fails on the filleted slice (an OCCError → TOO_LARGE_MSG in the test), try
`join=0` (arc) before anything else and keep the one that passes both `d = 1` and `d = -1`.

- [ ] **Step 5: Commit** (ask first)

```bash
git add InCad/incad/core/round_wall.py tests/headless/test_round_wall.py
git commit -m "Move Face: round walls Together with their fillets and chamfers"
```

---

### Task 4: Stored by geometry, found again; the feature uses round walls

**Files:**
- Modify: `InCad/incad/core/round_wall.py` (signature / find / arrow point)
- Modify: `InCad/incad/features/move_face.py`
- Test: `tests/headless/test_move_face.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `rw.signature(shape, face) -> dict` — `{"kind": "wall", "a": [x, y, z], "pts": [[x, y, z], ...]}`.
  - `rw.find(shape, sig) -> Part.Face | None` — a face of the wall (pieces are gathered by `offset`).
  - `rw.arrow(shape, face, d) -> (App.Vector, App.Vector)` — the point on the wall at mid height moved by d, and the
    outward normal there (body frame).
  - `features.move_face.unavailable(values) -> {"extent": {"to"}}` when a picked face is a round wall, else `{}`.

- [ ] **Step 1: Write the failing tests** (append to `tests/headless/test_move_face.py`)

```python
class RoundWallFeatureTest(unittest.TestCase):
    """Move Face on a round wall as a feature: the boss of a pad grows, stored by geometry, To unavailable."""

    def setUp(self):
        import Part
        self.doc = util.new_doc("MfRound")
        self.body, self.pad = util.padded_part(self.doc, 5, incad=True)  # 20 x 10 x 5
        sk = self.body.newObject("Sketcher::SketchObject", "Circle")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.AttachmentOffset = App.Placement(App.Vector(0, 0, 5), App.Rotation())
        sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 3))
        self.boss = util.add_pad(self.body, sk, 6, name="Boss")
        self.body.Tip = self.boss
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def cyl(self, feature):
        return "%s:Face%d" % (feature.Name, next(i for i, f in enumerate(feature.Shape.Faces, 1)
                                                 if type(f.Surface).__name__ == "Cylinder"))

    def make(self, **kw):
        values = dict(move_face.defaults(self.doc, self.body, None), faces=self.cyl(self.boss), distance="1 mm")
        values.update(kw)
        f = move_face.create(self.doc, self.body, None, values)
        self.doc.recompute()
        return f

    def test_the_boss_grows(self):
        f = self.make()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        cyl = next(g for g in f.Shape.Faces if type(g.Surface).__name__ == "Cylinder")
        self.assertAlmostEqual(cyl.Surface.Radius, 4, 6)
        self.assertEqual(json.loads(f.Signatures)[0]["kind"], "wall")

    def test_to_is_unavailable_for_a_round_wall(self):
        self.assertEqual(move_face.unavailable({"faces": self.cyl(self.boss)}), {"extent": {"to"}})
        self.assertEqual(move_face.unavailable({"faces": top_name(self.boss)}), {})

    def test_a_flat_face_and_a_round_wall_are_refused(self):
        from incad.core import round_wall as rw
        with self.assertRaises(ValueError) as e:
            self.make(faces="%s, %s" % (self.cyl(self.boss), top_name(self.boss)))
        self.assertEqual(str(e.exception), rw.MIXED_MSG)

    def test_a_cone_face_is_refused(self):
        """A chamfer on the boss's top edge makes a cone: not a straight round wall."""
        from incad.core import round_wall as rw
        top_ring = next(i for i, e in enumerate(self.boss.Shape.Edges, 1)
                        if type(e.Curve).__name__ == "Circle" and abs(e.CenterOfMass.z - 11) < 1e-6)
        ch = self.body.newObject("PartDesign::Chamfer", "Chamfer")
        ch.Base = (self.boss, ["Edge%d" % top_ring])
        ch.Size = 1
        self.body.Tip = ch
        self.doc.recompute()
        cone = next(i for i, g in enumerate(ch.Shape.Faces, 1) if type(g.Surface).__name__ == "Cone")
        with self.assertRaises(ValueError) as e:
            self.make(faces="%s:Face%d" % (ch.Name, cone))
        self.assertEqual(str(e.exception), rw.NOT_STRAIGHT_MSG)

    def test_found_again_after_the_block_under_it_changed(self):
        f = self.make()
        self.pad.Length = 8  # the block under the boss grows into it: the wall is shorter, still the same surface
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())

    def test_read_and_save_reopen(self):
        f = self.make(mode="step")
        values = move_face.read(self.doc, f)
        self.assertEqual((values["mode"], values["extent"], values["distance"]), ("step", "distance", "1 mm"))
        self.assertTrue(values["faces"].startswith(self.boss.Name + ":Face"))
        path = os.path.join(tempfile.mkdtemp(), "round.FCStd")
        self.doc.saveAs(path)
        name = self.doc.Name
        App.closeDocument(name)
        self.doc = App.openDocument(path)
        self.doc.recompute()
        f2 = self.doc.getObject(f.Name)
        self.assertNotIn("Invalid", f2.State, f2.getStatusString())
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)

    def test_the_arrow_points_out_of_the_wall(self):
        f = self.make()
        point, normal = move_face.arrow(f)
        self.assertAlmostEqual(normal.z, 0, 6)
        self.assertAlmostEqual(App.Vector(point.x - 10, point.y - 5, 0).Length, 4, 4)  # on the grown wall
```

(Add `import json` at the top of `tests/headless/test_move_face.py` next to `import os` if it is not there.)

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_move_face.py`
Expected: the RoundWallFeatureTest tests FAIL / ERROR (`FACES_MSG` raised by `_build`, no `unavailable`).

- [ ] **Step 3: Signature, find and arrow in `round_wall.py`**

```python
def signature(shape, face):
    """The wall by geometry: its direction and points of its section (the mid height ring, sampled)."""
    faces, a = pieces(shape, face)
    h0, h1 = extent(faces, a)
    wire = section(faces, a, h0, h1)
    return {"kind": "wall", "a": [a.x, a.y, a.z], "pts": [list(p) for p in wire.discretize(16)]}


def find(shape, sig):
    """A face of the stored wall in `shape`: a straight round wall along a on which the stored points lie (the part
    may have moved it along a: points of the ring slid along a still lie on an extruded wall's surface)."""
    a = App.Vector(*sig["a"])
    pts = [App.Vector(*p) for p in sig["pts"]]
    for f in shape.Faces:
        d = direction(f)
        if d is None or abs(abs(d.dot(a)) - 1) > 1e-6:
            continue
        try:
            if all(f.Surface.projectPoint(p, "LowerDistance") < 1e-5 for p in pts[:4]):
                return f
        except Exception:
            continue
    return None


def arrow(shape, face, d):
    """The arrow's place: a point of the wall at mid height (on its section) moved by d along the outward normal."""
    faces, a = pieces(shape, face)
    h0, h1 = extent(faces, a)
    p = section(faces, a, h0, h1).Vertexes[0].Point
    owner = min(faces, key=lambda f: f.distToShape(Part.Vertex(p))[0])
    u, v = owner.Surface.parameter(p)
    n = owner.normalAt(u, v)
    return p + n * d, n
```

- [ ] **Step 4: The feature in `InCad/incad/features/move_face.py`**

Add `from incad.core import round_wall as rw` to the imports, and:

```python
def _is_wall_sig(sig):
    return isinstance(sig, dict) and sig.get("kind") == "wall"


def _walls(obj, shape):
    """The stored round walls found again in `shape` (one face of each)."""
    out = []
    for sig in _load_json(obj.Signatures, []):
        if _is_wall_sig(sig):
            f = rw.find(shape, sig)
            if f is None:
                raise ValueError(mf.GONE_MSG)
            out.append(f)
    return out


def unavailable(values):
    """'To' is greyed out while a round wall is picked (Distance only for round walls)."""
    doc = App.ActiveDocument
    if doc is None:
        return {}
    for obj, sub in parse_picks(doc, values.get("faces")):
        obj, sub = resolve(obj, sub)
        if obj is not None and sub.startswith("Face"):
            try:
                if rw.is_round_wall(obj.Shape.getElement(sub)):
                    return {"extent": {"to"}}
            except Exception:
                pass
    return {}
```

In `MoveFaceFeature.execute`, before `faces = _faces(obj, shape)`:

```python
        walls = _walls(obj, shape)
        if walls:
            obj.Shape = rw.offset(shape, walls, obj.Distance.Value, obj.Mode or "inventor")
            return
```

In `_faces`, skip wall signatures: `for sig in _load_json(obj.Signatures, []):` → add
`if _is_wall_sig(sig): continue` as its first line.

In `_build`, replace its first four lines (from `faces = _picked_faces(...)` to `f.Signatures = ...`) with:

```python
    picked = _picked_faces(doc, values.get("faces"), f.getParentGeoFeatureGroup())
    shape = _picked_shape(doc, values.get("faces"))
    walls = [x for x in picked if rw.is_round_wall(x)]
    if walls:
        if any(mf._is_plane(x) for x in picked):
            raise ValueError(rw.MIXED_MSG)
        if len(walls) != len(picked):
            raise ValueError(rw.NOT_STRAIGHT_MSG)
        sigs, seen = [], []
        for w in walls:  # one signature per wall (two clicked pieces of one ring are one wall)
            faces, _ = rw.pieces(shape, w)
            if any(any(x.isSame(y) for y in seen) for x in faces):
                continue
            seen += faces
            sigs.append(rw.signature(shape, w))
        f.Signatures = json.dumps(sigs)
        f.Mode = values.get("mode") or "inventor"
        f.Extent = "distance"
        f.Target = None
        value_param(doc, f, "Distance", values.get("distance") or "0 mm", "length")
        _store(f, {"faces": values.get("faces") or "", "to": ""})
        return f
    if picked and not any(mf._is_plane(x) for x in picked):
        raise ValueError(rw.NOT_STRAIGHT_MSG)
    faces, blends = mf.split_blends(shape, picked)
    mf.check_faces(faces)
    f.Signatures = json.dumps([mf.signature(face) for face in faces])
```

In `_current_picks`, before `try: faces = _faces(f, base.Shape)`:

```python
    try:
        walls = _walls(f, base.Shape)
    except ValueError:
        return None
    if walls:
        names = []
        for w in walls:
            i = next((k for k, g in enumerate(base.Shape.Faces) if g.isSame(w)), None)
            if i is None:
                return None
            names.append("%s:Face%d" % (base.Name, i + 1))
        return ",".join(names)
```

In `arrow(f, distance=None)`, after the `sigs`/`base` check:

```python
    if _is_wall_sig(sigs[0]):
        face = rw.find(base.Shape, sigs[0])
        if face is None:
            return None
        d = f.Distance.Value if distance is None else distance
        point, n = rw.arrow(base.Shape, face, d)
        to_global = _frame(f)
        return to_global.multVec(point), to_global.Rotation.multVec(n)
```

- [ ] **Step 5: Run to verify they pass**

Run: `tests/run_headless.sh "test_move_face*.py"` and `tests/run_headless.sh test_round_wall.py`
Expected: all `OK` (the flat Move Face tests unchanged).

- [ ] **Step 6: Commit** (ask first)

```bash
git add InCad/incad/core/round_wall.py InCad/incad/features/move_face.py tests/headless/test_move_face.py
git commit -m "Move Face: round walls as a feature (stored by geometry, To unavailable, arrow on the wall)"
```

---

### Task 5: The user's body

**Files:**
- Create: `tests/headless/test_round_wall_user_body.py`
- Create: `tests/gui/data/ellipse_band.FCStd` (a copy of the file the user sends)

**Interfaces:**
- Consumes: Task 4's feature (`move_face.create`).

- [ ] **Step 1: Copy the user's file** — the user saves their body (File ▸ Save As) and sends the path; copy it
  (never use the original):

```bash
cp "/the/path/the/user/sent.FCStd" "tests/gui/data/ellipse_band.FCStd"
```

- [ ] **Step 2: Write the test**

```python
"""Move Face on the user's own body (tests/gui/data/ellipse_band.FCStd, a copy of their file): its elliptic band —
the largest straight round wall of the part — offset ± in every mode, valid, the band at exactly d."""
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part

from incad.core import document, round_wall as rw
from incad.features import move_face

DATA = os.path.join(os.environ["INCAD_REPO"], "tests", "gui", "data", "ellipse_band.FCStd")


class UserBody(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "body.FCStd")
        shutil.copy(DATA, path)
        self.doc = App.openDocument(path)
        self.doc.recompute()
        self.body = document.primary_body(self.doc)
        self.tip = self.body.Tip

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def band(self):
        walls = [(i, f) for i, f in enumerate(self.tip.Shape.Faces, 1) if rw.is_round_wall(f)]
        i, f = max(walls, key=lambda w: w[1].Area)
        return i, f

    def test_every_mode_both_ways(self):
        i, wall = self.band()
        for mode in ("step", "together", "inventor"):
            for d in ("1 mm", "-1 mm"):
                values = dict(move_face.defaults(self.doc, self.body, None), faces="%s:Face%d" % (self.tip.Name, i),
                              distance=d, mode=mode)
                try:
                    f = move_face.create(self.doc, self.body, None, values)
                except ValueError as e:
                    self.assertEqual((mode, str(e)), ("inventor", rw.mf.ROUND_MSG))  # blends next to the band
                    continue
                self.doc.recompute()
                self.assertNotIn("Invalid", f.State, (mode, d, f.getStatusString()))
                self.assertTrue(f.Shape.isValid(), (mode, d))
                moved = max((g for g in f.Shape.Faces if rw.is_round_wall(g)), key=lambda g: g.Area)
                for e in wall.Edges:
                    for p in e.discretize(6):
                        if abs(p.z - wall.CenterOfMass.z) < 0.25 * wall.BoundBox.ZLength:
                            self.assertAlmostEqual(moved.distToShape(Part.Vertex(p))[0], 1.0, 3, (mode, d))
                self.body.removeObject(f)
                self.doc.removeObject(f.Name)
                self.body.Tip = self.tip
                self.doc.recompute()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it**

Run: `tests/run_headless.sh test_round_wall_user_body.py`
Expected: `OK`. A failure here is a real gap: reproduce it in `tests/headless/test_round_wall.py` on a built shape of
the same kind first (TDD), fix it in `round_wall.py`, then rerun both files.

- [ ] **Step 4: Commit** (ask first)

```bash
git add tests/headless/test_round_wall_user_body.py tests/gui/data/ellipse_band.FCStd
git commit -m "Move Face: round walls tested on the user's elliptic band"
```

---

### Task 6: In the real window — pick the band, preview, arrow, To greyed

**Files:**
- Modify: `tests/gui/test_move_face.py`

**Interfaces:**
- Consumes: Task 4 (feature, `unavailable`, `arrow`); the existing test helpers in `tests/gui/test_move_face.py`
  (`s()`, `doc()`, `body()`, `dialog()`, `click(pos)`, `screen_of(point)`, `clear_selection()`, `harness.pump`).

- [ ] **Step 1: Write the failing test** (before `test_9_cleanup`, and add it to the `harness.run([...])` list
  before `test_9_cleanup`)

```python
def test_8d_a_round_wall_offsets_from_a_click():
    """Round walls: a click on a boss's wall picks the whole wall, the preview grows it, To is greyed out, the arrow
    points out of the wall."""
    import Part
    if s().feature_session is not None:
        s().feature_session.cancel()
        harness.pump(900)
    b = body()
    sk = b.newObject("Sketcher::SketchObject", "BossCircle")
    sk.AttachmentSupport = [(util.xy_plane(b), "")]
    sk.MapMode = "FlatFace"
    zmax = b.Shape.BoundBox.ZMax
    sk.AttachmentOffset = App.Placement(App.Vector(0, 0, zmax), App.Rotation())
    sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 3))
    boss = util.add_pad(b, sk, 6, name="RoundBoss")
    b.Tip = boss
    doc().recompute()
    harness.pump(800)
    view().viewIsometric()
    view().fitAll()
    harness.pump(600)
    clear_selection()
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1200)
    assert dialog() is not None and dialog().active_pick() == "faces", dialog() and dialog().active_pick()
    click(screen_of(App.Vector(10, 2, zmax + 3)))  # the front of the boss's wall
    harness.pump(1200)
    faces = dialog().values()["faces"]
    assert faces.startswith(boss.Name + ":Face"), (faces, dialog().error_text())
    assert "to" in s().feature_session.kind.unavailable(dialog().values()).get("extent", set())
    dialog().set_values({"distance": "1 mm"})
    s().feature_session._changed(dialog().values())
    harness.pump(1500)
    f = s().feature_session.feature
    assert f is not None and "Invalid" not in f.State, dialog().error_text()
    cyl = next(g for g in f.Shape.Faces if type(g.Surface).__name__ == "Cylinder")
    assert abs(cyl.Surface.Radius - 4) < 1e-6, cyl.Surface.Radius
    point, normal = s().feature_session.kind.arrow(f)
    assert abs(normal.z) < 1e-6, normal
    s().feature_session.cancel()
    harness.pump(900)
```

(If `util` / `commands` are not imported in that file, they are: `import headless.util as util` and
`from incad.core import commands` are at its top.)

- [ ] **Step 2: Run to verify it passes** (it uses Tasks 1–4, so it should pass at once; a failure is a real gap)

Run: `tests/run_gui.sh tests/gui/test_move_face.py`
Expected: `13 passed, 0 failed`. Tell the user to keep hands off the mouse and keyboard while it runs (CLAUDE.md);
GUI tests that need hover or keyboard focus fail while the user's own FreeCAD is in front.

- [ ] **Step 3: The affected suites once**

Run: `tests/run_headless.sh "test_move_face*.py"`, `tests/run_headless.sh "test_round_wall*.py"`,
`tests/run_gui.sh tests/gui/test_move_face.py tests/gui/test_dressup_preview.py tests/gui/test_picks.py`
Expected: all pass.

- [ ] **Step 4: Commit** (ask first)

```bash
git add tests/gui/test_move_face.py
git commit -m "Move Face: round walls in the real window"
```
