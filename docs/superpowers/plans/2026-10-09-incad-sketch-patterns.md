# Sketch Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rectangular and Circular patterns inside a sketch, driven by InCad's own feature dialog, whose copies follow the original and can be edited or deleted as a pattern later.

**Architecture:** A pure model module `incad.core.sketch_patterns` builds, rebuilds and removes a pattern's copies and constraints in a `Sketcher::SketchObject` and keeps a JSON record on the sketch (`InCadPatterns`). Two feature kinds in `incad.features.sketch_patterns` expose that model to `FeatureSession` (the same session the 3D feature dialogs use), which gets a small `IN_SKETCH` path: the "feature" it holds is the sketch itself, picks come from the sketch's own elements, nothing is hidden or shown. Shell and actions add the two commands, Edit/Delete Pattern, and the double-click.

**Tech Stack:** FreeCAD 1.1.3 Python API (Sketcher constraints with expressions, `setGeometryId`, virtual space), PySide (FreeCAD's shim), InCad's model parameters (`incad.core.model`), unittest headless runner (`tests/run_headless.sh`), GUI runner (`tests/run_gui.sh`).

**Spec:** `docs/superpowers/specs/2026-10-09-incad-sketch-patterns-design.md`

## Global Constraints

- FreeCAD 1.1.3 on macOS; bundled Python has no pytest: tests are `unittest` classes run by `tests/run_headless.sh test_sketch_patterns.py` and plain functions run by `tests/run_gui.sh tests/gui/<file>.py` (a real window: keep hands off).
- UI text in English. Error messages are sentences a user can act on (the spec lists the exact ones).
- Sketch expressions may use `InCadModel.dN` and driving constraints only; never reference constraints of the same sketch.
- Pattern constraint names start with `pat` + number + `_` (e.g. `pat1_3`); model parameters are claimed through `incad.core.model` (`dN` names).
- Everything a dialog does happens inside the session's one undo step; the model functions never open transactions themselves.
- Run only the test files a task touches (`run_headless.sh test_sketch_patterns.py`, the named GUI files); the full suites once before the final commit.

## Review Focus

Inputs the spec implies but no test exercised before this plan was written; each now has a test in the task that owns the code:

1. A line whose two ends coincide with other geometry of the pattern (a closed rectangle): the copy's shared corner must get ONE tie per point, not two conflicting ones → Task 3 `test_a_closed_rectangle_is_tied_once_per_corner`.
2. Count reduced below the previous value on edit (5 → 3): the surplus copies and their constraints must go → Task 4 `test_edit_with_fewer_copies_removes_the_surplus`.
3. The user deleted a copy by hand before editing: rebuild must not fail on a missing geometry id → Task 4 `test_a_hand_deleted_copy_does_not_break_edit`.
4. The axis point of a circular pattern is a point OF the picked geometry (a circle's own centre): the spoke would be zero length → Task 3 `test_axis_on_the_geometry_is_refused`.
5. Equal spacing with From and To picked as the same line → Task 3 `test_coinciding_limits_are_refused`.

---

### Task 1: Geometry ids, records and element mapping (`incad.core.sketch_patterns`)

**Files:**
- Create: `InCad/incad/core/sketch_patterns.py`
- Modify: `InCad/incad/core/sketch.py:10-12` (pattern prefix) and the four functions listed in Step 3
- Test: `tests/headless/test_sketch_patterns.py`

**Interfaces:**
- Produces:
  - `PREFIX = "pat"`; `is_pattern_name(name) -> bool` in `incad.core.sketch`
  - `records(sk) -> list[dict]`, `save_records(sk, recs)`, `find(sk, name) -> dict | None`, `next_name(sk) -> str` ("Pattern1", "Pattern2", …, never reused)
  - `ensure_id(sk, index) -> int`, `index_of(sk, gid) -> int | None`
  - `element(sk, sub) -> (geo, pos)`: `"Edge3"` → `(2, 0)`, `"Vertex2"` → `(geo, pos)` via `getGeoVertexIndex`, `"H_Axis"` → `(-1, 0)`, `"V_Axis"` → `(-2, 0)`, `"RootPoint"` → `(-1, 1)`
  - `ref_points(sk, geo) -> list[int]`: the PointPos values a copy is tied by: line `[1, 2]`, arc `[1, 2]`, circle `[3]`, point `[1]`; raises `ValueError("Pattern repeats lines, arcs, circles and points")` for anything else
  - `point_of(sk, geo, pos) -> App.Vector`

- [ ] **Step 1: Write the failing tests**

```python
# tests/headless/test_sketch_patterns.py
import json
import math
import unittest

import FreeCAD as App
import Part
import Sketcher
from incad.core import document, model, sketch, sketch_patterns as sp
from headless import util


def circle(sk, x, y, r, construction=False):
    return sk.addGeometry(Part.Circle(App.Vector(x, y, 0), App.Vector(0, 0, 1), r), construction)


def line(sk, x1, y1, x2, y2, construction=False):
    return sk.addGeometry(Part.LineSegment(App.Vector(x1, y1, 0), App.Vector(x2, y2, 0)), construction)


class RecordsAndIdsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sp")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_ids_are_given_once_and_found_after_other_geometry_is_deleted(self):
        a, b = circle(self.sk, 0, 0, 1), circle(self.sk, 5, 0, 1)
        gid = sp.ensure_id(self.sk, b)
        self.assertEqual(sp.ensure_id(self.sk, b), gid)
        self.sk.delGeometry(a)
        self.assertEqual(sp.index_of(self.sk, gid), 0)
        self.assertIsNone(sp.index_of(self.sk, 999999))

    def test_records_round_trip_and_names_are_never_reused(self):
        self.assertEqual(sp.records(self.sk), [])
        n1 = sp.next_name(self.sk)
        sp.save_records(self.sk, [{"name": n1, "kind": "rect"}])
        self.assertEqual(sp.find(self.sk, n1)["kind"], "rect")
        sp.save_records(self.sk, [])
        self.assertNotEqual(sp.next_name(self.sk), n1)
        self.assertEqual(sp.next_name(self.sk), "Pattern2")
        self.assertEqual(json.loads(self.sk.InCadPatterns)["patterns"], [])

    def test_elements_map_to_geometry_and_positions(self):
        c = circle(self.sk, 2, 3, 1)
        ln = line(self.sk, 0, 0, 4, 0)
        self.doc.recompute()
        self.assertEqual(sp.element(self.sk, "Edge1"), (c, 0))
        self.assertEqual(sp.element(self.sk, "H_Axis"), (-1, 0))
        self.assertEqual(sp.element(self.sk, "V_Axis"), (-2, 0))
        self.assertEqual(sp.element(self.sk, "RootPoint"), (-1, 1))
        geo, pos = sp.element(self.sk, "Vertex1")  # the circle's centre is its first vertex: (geo, PointPos 3)
        self.assertEqual((geo, pos), (c, 3))
        self.assertEqual(sp.element(self.sk, "Vertex2"), (ln, 1))  # the line's start
        with self.assertRaises(ValueError):
            sp.element(self.sk, "Vertex99")
        self.assertEqual(sp.ref_points(self.sk, ln), [1, 2])
        self.assertEqual(sp.ref_points(self.sk, c), [3])
        p = sp.point_of(self.sk, ln, 2)
        self.assertAlmostEqual((p.x, p.y), (4.0, 0.0))
        e = self.sk.addGeometry(Part.Ellipse(App.Vector(0, 0, 0), 3, 2))
        with self.assertRaises(ValueError) as cm:
            sp.ref_points(self.sk, e)
        self.assertIn("lines, arcs, circles and points", str(cm.exception))

    def test_pattern_constraint_names_are_not_dimensions_or_symbols(self):
        c = circle(self.sk, 2, 3, 1)
        i = self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 2.0))
        self.sk.renameConstraint(i, "pat1_0")
        j = self.sk.addConstraint(Sketcher.Constraint("Radius", c, 1.0))
        self.sk.renameConstraint(j, "d3")
        self.assertTrue(sketch.is_pattern_name("pat1_0"))
        self.assertFalse(sketch.is_pattern_name("d3"))
        self.assertFalse(sketch.is_pattern_name("pattern"))
        self.assertEqual([n for n, _, _ in sketch.dimensions(self.doc)], ["d3"])
        self.assertEqual(list(sketch.dimension_snapshot(self.sk)), ["d3"])
        k = self.sk.addConstraint(Sketcher.Constraint("Coincident", c, 3, -1, 1))
        self.sk.renameConstraint(k, "pat1_1")
        self.assertNotIn(k, sketch._symbol_constraints(self.sk))
        self.assertEqual(sketch.name_new_dimensions(self.doc), [])  # ours are named: nothing to name
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: FAIL with `ImportError: cannot import name 'sketch_patterns'`

- [ ] **Step 3: Teach `incad.core.sketch` the pattern prefix**

In `InCad/incad/core/sketch.py` add after `_DNAME` (line 11):

```python
PATTERN_PREFIX = "pat"
_PATNAME = re.compile(r"^pat\d+_\d+$")


def is_pattern_name(name):
    """Constraints a sketch pattern added (pat<n>_<i>): never dimensions, never symbols, never auto-named."""
    return bool(name) and _PATNAME.match(name) is not None
```

and change these four functions so pattern constraints are skipped:

```python
def dimensions(doc):
    """[(name, sketch, index)] for every named dimension, in document order."""
    out = []
    for sk in _sketches(doc):
        for i, c in enumerate(sk.Constraints):
            if c.Type in DIMENSIONAL and c.Name and not is_pattern_name(c.Name):
                out.append((c.Name, sk, i))
    return out


def _symbol_constraints(sk):
    return [i for i, c in enumerate(sk.Constraints) if c.Type not in DIMENSIONAL and not is_pattern_name(c.Name)]


def dimension_snapshot(sk):
    out = {}
    for c in sk.Constraints:
        if c.Name and c.Type in DIMENSIONAL and c.Driving and not is_pattern_name(c.Name):
            out[c.Name] = {"type": c.Type, "value": c.Value, "expr": _expression_of(sk, "Constraints." + c.Name)}
    return out


def vanished_dimensions(sk, known):
    names = {c.Name for c in sk.Constraints if c.Name}
    return [n for n in known if n not in names and not is_pattern_name(n)]
```

(`name_new_dimensions` and `_fresh_dimensions` only look at unnamed constraints: the pattern names its own at creation, so they need no change.)

- [ ] **Step 4: Write the model module**

```python
# InCad/incad/core/sketch_patterns.py
"""Sketch patterns: copies of sketch geometry tied to the original by constraints, remembered on the sketch
(InCadPatterns, JSON) so they can be edited or deleted as one thing. Pure model: no transactions, no UI.
Geometry is addressed by permanent ids (setGeometryId), never by index."""
import json
import math

import FreeCAD as App
import Part
import Sketcher

from incad.core import sketch as sketches

RECORD_PROP = "InCadPatterns"
SUPPORTED = ("Part::GeomLineSegment", "Part::GeomArcOfCircle", "Part::GeomCircle", "Part::GeomPoint")
_ID_BASE = 100000  # ids we hand out start here: FreeCAD's own ids (when any) are small


# ----- records -----
def _load(sk):
    text = getattr(sk, RECORD_PROP, "") or ""
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    data.setdefault("patterns", [])
    data.setdefault("next", 1)
    data.setdefault("next_id", _ID_BASE)
    return data


def _store(sk, data):
    if RECORD_PROP not in sk.PropertiesList:
        sk.addProperty("App::PropertyString", RECORD_PROP, "InCad", "Sketch patterns (JSON)")
    setattr(sk, RECORD_PROP, json.dumps(data))


def records(sk):
    return list(_load(sk)["patterns"])


def save_records(sk, recs):
    data = _load(sk)
    data["patterns"] = list(recs)
    _store(sk, data)


def find(sk, name):
    for r in records(sk):
        if r.get("name") == name:
            return r
    return None


def next_name(sk):
    """'Pattern<n>', never handed out twice (the counter lives in the record)."""
    data = _load(sk)
    name = "Pattern%d" % data["next"]
    data["next"] += 1
    _store(sk, data)
    return name


# ----- geometry ids -----
def ensure_id(sk, index):
    gid = sk.getGeometryId(index)
    if gid is None or gid < _ID_BASE:
        data = _load(sk)
        gid = data["next_id"]
        data["next_id"] += 1
        _store(sk, data)
        sk.setGeometryId(index, gid)
    return gid


def index_of(sk, gid):
    for i in range(sk.GeometryCount):
        if sk.getGeometryId(i) == gid:
            return i
    return None


# ----- elements -----
def element(sk, sub):
    """(geo, pos) of a sketch sub-element name: 'Edge3' -> (2, 0); 'Vertex2' -> the geometry and its PointPos;
    'H_Axis' -> (-1, 0); 'V_Axis' -> (-2, 0); 'RootPoint' -> (-1, 1)."""
    if sub == "H_Axis":
        return -1, 0
    if sub == "V_Axis":
        return -2, 0
    if sub == "RootPoint":
        return -1, 1
    if sub.startswith("Edge"):
        return int(sub[4:]) - 1, 0
    if sub.startswith("Vertex"):
        geo, pos = sk.getGeoVertexIndex(int(sub[6:]) - 1)
        if geo < -2:  # FreeCAD answers (-2000, 0) for a vertex that does not exist
            raise ValueError("Not a sketch element: %s" % sub)
        return geo, pos
    raise ValueError("Not a sketch element: %s" % sub)


def geometry_type(sk, geo):
    return sk.Geometry[geo].TypeId


def ref_points(sk, geo):
    """The PointPos values a copy is tied by (exactly the copy's degrees of freedom together with Equal for
    round geometry): line and arc ends, a circle's centre, a point."""
    t = geometry_type(sk, geo)
    if t == "Part::GeomLineSegment" or t == "Part::GeomArcOfCircle":
        return [1, 2]
    if t == "Part::GeomCircle":
        return [3]
    if t == "Part::GeomPoint":
        return [1]
    raise ValueError("Pattern repeats lines, arcs, circles and points")


def point_of(sk, geo, pos):
    return sk.getPoint(geo, pos)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: `Ran 4 tests … OK`. Also run `tests/run_headless.sh test_sketch.py` (dimension helpers changed): OK.

- [ ] **Step 6: Commit**

```bash
git add InCad/incad/core/sketch_patterns.py InCad/incad/core/sketch.py tests/headless/test_sketch_patterns.py
git commit -m "Sketch patterns: records, permanent geometry ids, element mapping; pat<n>_<i> constraints are neither dimensions nor symbols"
```

---

### Task 2: Rectangular copies tied by hidden DistanceX/DistanceY expressions

**Files:**
- Modify: `InCad/incad/core/sketch_patterns.py`
- Test: `tests/headless/test_sketch_patterns.py`

**Interfaces:**
- Consumes: Task 1 (`ensure_id`, `index_of`, `ref_points`, `point_of`, `next_name`, `save_records`, `find`).
- Produces:
  - `build_rect(doc, sk, rec) -> rec`: `rec` has `name`, `originals` (geometry ids), `count` (int ≥ 2), `spacing_param` (model parameter name, length), `angle` (degrees, float), `flip` (bool), optional `count2`, `spacing_param2`, `angle2`. Adds copies and constraints, fills `rec["copies"]` (list of lists of geometry ids) and `rec["constraints"]` (names), saves the record, returns it.
  - `remove(doc, sk, name)`: deletes the pattern's copies and constraints (by id/name; missing ones are skipped), drops the record.
  - `copies_of(sk, name) -> list[int]` geometry indexes of all copies now in the sketch.
  - `_translation(rec, k, j) -> (expr_x, expr_y)` the expression strings.

- [ ] **Step 1: Write the failing tests**

```python
class RectangularTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sr")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _rect(self, originals, count=3, spacing="12 mm", angle=0.0, flip=False, **more):
        name = sp.next_name(self.sk)
        rec = {"name": name, "kind": "rect", "originals": [sp.ensure_id(self.sk, g) for g in originals],
               "count": count, "spacing_param": model.new_feature_parameter(self.doc, spacing, "length"),
               "angle": angle, "flip": flip}
        rec.update(more)
        rec = sp.build_rect(self.doc, self.sk, rec)
        self.doc.recompute()
        return rec

    def _xy(self, geo, pos):
        p = sp.point_of(self.sk, geo, pos)
        return round(p.x, 3), round(p.y, 3)

    def test_a_circle_is_copied_along_x_with_equal_radius_and_hidden_ties(self):
        c = circle(self.sk, 2, 3, 1)
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 2.0))  # pin the original
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 3.0))
        self.sk.addConstraint(Sketcher.Constraint("Radius", c, 1.0))
        rec = self._rect([c])
        self.assertEqual(len(rec["copies"]), 2)  # count 3 = the original + 2 copies
        k1, k2 = (sp.index_of(self.sk, ids[0]) for ids in rec["copies"])
        self.assertEqual(self._xy(k1, 3), (14.0, 3.0))
        self.assertEqual(self._xy(k2, 3), (26.0, 3.0))
        self.assertAlmostEqual(self.sk.Geometry[k2].Radius, 1.0)
        self.assertEqual(self.sk.solve(), 0)
        names = [c.Name for c in self.sk.Constraints if sketch.is_pattern_name(c.Name)]
        self.assertEqual(sorted(names), sorted(rec["constraints"]))
        self.assertTrue(all(self.sk.getVirtualSpace(i) for i, c in enumerate(self.sk.Constraints)
                            if sketch.is_pattern_name(c.Name)))
        self.assertEqual([n for n, _, _ in sketch.dimensions(self.doc)], [])  # none of ours is a dimension

    def test_copies_follow_the_original_and_the_spacing_parameter(self):
        c = circle(self.sk, 2, 3, 1)
        dx = self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 2.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 3.0))
        rec = self._rect([c], count=2, spacing="10 mm", angle=90.0)
        k1 = sp.index_of(self.sk, rec["copies"][0][0])
        self.assertEqual(self._xy(k1, 3), (2.0, 13.0))
        self.sk.setDatum(dx, App.Units.Quantity("7 mm"))
        self.doc.recompute()
        self.assertEqual(self._xy(k1, 3), (7.0, 13.0))
        model.set_model_parameter(self.doc, rec["spacing_param"], "25 mm")
        self.doc.recompute()
        self.assertEqual(self._xy(k1, 3), (7.0, 28.0))

    def test_flip_and_two_directions(self):
        c = circle(self.sk, 0, 0, 1)
        self.sk.addConstraint(Sketcher.Constraint("Coincident", c, 3, -1, 1))
        rec = self._rect([c], count=2, spacing="10 mm", angle=0.0, flip=True, count2=2,
                         spacing_param2=model.new_feature_parameter(self.doc, "5 mm", "length"), angle2=90.0)
        got = sorted(self._xy(sp.index_of(self.sk, ids[0]), 3) for ids in rec["copies"])
        self.assertEqual(got, [(-10.0, 0.0), (-10.0, 5.0), (0.0, 5.0)])

    def test_a_line_an_arc_and_a_construction_line_keep_their_kind_and_shape(self):
        ln = line(self.sk, 0, 0, 4, 0)
        arc = self.sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(6, 0, 0), App.Vector(0, 0, 1), 2),
                                                   0.0, math.pi / 2))
        con = line(self.sk, 0, 5, 1, 5, construction=True)
        self.sk.addConstraint(Sketcher.Constraint("Coincident", ln, 1, -1, 1))
        self.sk.addConstraint(Sketcher.Constraint("PointOnObject", ln, 2, -1))
        for g, pos, x, y in ((arc, 3, 6.0, 0.0), (con, 1, 0.0, 5.0)):  # pin the originals: the copies' places
            self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, g, pos, x))  # below are absolute
            self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, g, pos, y))
        rec = self._rect([ln, arc, con], count=2, spacing="20 mm", angle=30.0)
        dx, dy = 20 * math.cos(math.radians(30)), 20 * math.sin(math.radians(30))
        l2, a2, c2 = (sp.index_of(self.sk, g) for g in rec["copies"][0])
        self.assertEqual(self._xy(l2, 2), (round(4 + dx, 3), round(dy, 3)))
        self.assertEqual(self.sk.Geometry[a2].TypeId, "Part::GeomArcOfCircle")
        self.assertAlmostEqual(self.sk.Geometry[a2].Radius, 2.0, places=6)
        self.assertEqual(self._xy(a2, 1), (round(8 + dx, 3), round(dy, 3)))
        self.assertTrue(self.sk.getConstruction(c2))
        self.assertEqual(self.sk.solve(), 0)

    def test_a_closed_rectangle_is_tied_once_per_corner(self):
        ids = [line(self.sk, 0, 0, 4, 0), line(self.sk, 4, 0, 4, 2), line(self.sk, 4, 2, 0, 2), line(self.sk, 0, 2, 0, 0)]
        for i in range(4):
            self.sk.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[(i + 1) % 4], 1))
        self.sk.addConstraint(Sketcher.Constraint("Coincident", ids[0], 1, -1, 1))
        self.sk.addConstraint(Sketcher.Constraint("Horizontal", ids[0]))
        self.doc.recompute()
        before = self.sk.solve()
        rec = self._rect(ids, count=2, spacing="10 mm")
        self.assertEqual(self.sk.solve(), before)  # not over-constrained: 8 ties for 4 corners, not 16
        copy = [sp.index_of(self.sk, g) for g in rec["copies"][0]]
        self.assertEqual(self._xy(copy[2], 1), (14.0, 2.0))

    def test_remove_takes_copies_and_constraints_and_leaves_the_original(self):
        c = circle(self.sk, 2, 3, 1)
        rec = self._rect([c], count=4)
        n_geo, n_con = self.sk.GeometryCount, len(self.sk.Constraints)
        self.assertEqual(n_geo, 4)
        sp.remove(self.doc, self.sk, rec["name"])
        self.doc.recompute()
        self.assertEqual(self.sk.GeometryCount, 1)
        self.assertEqual([c.Name for c in self.sk.Constraints if sketch.is_pattern_name(c.Name)], [])
        self.assertIsNone(sp.find(self.sk, rec["name"]))
        self.assertEqual(sp.copies_of(self.sk, rec["name"]), [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: FAIL with `AttributeError: module 'incad.core.sketch_patterns' has no attribute 'build_rect'`

- [ ] **Step 3: Implement copies, ties and removal**

Append to `InCad/incad/core/sketch_patterns.py`:

```python
# ----- copies -----
def _copy_geometry(sk, geo, offset=None, rotate=None):
    """A new geometry equal to sk.Geometry[geo], translated by `offset` (Vector) or rotated by `rotate`
    (centre Vector, angle in radians); construction flag kept."""
    g = sk.Geometry[geo].copy()
    if offset is not None:
        g.translate(offset)
    if rotate is not None:
        _rotate_in_place(g, *rotate)
    return sk.addGeometry(g, sk.getConstruction(geo))


def _rotate_in_place(g, centre, angle):
    pl = App.Placement(centre, App.Rotation(App.Vector(0, 0, 1), math.degrees(angle))) \
        .multiply(App.Placement(-centre, App.Rotation()))
    g.transform(pl.toMatrix())


def _name_constraint(sk, rec, index):
    name = "%s_%d" % (rec["_prefix"], rec["_next"])
    rec["_next"] += 1
    sk.renameConstraint(index, name)
    rec["constraints"].append(name)
    return name


def _add(sk, rec, constraint, expression=None, hidden=True):
    i = sk.addConstraint(constraint)
    if expression is not None:
        sk.setExpression("Constraints[%d]" % i, expression)
    if hidden:
        sk.setVirtualSpace(i, True)
    return _name_constraint(sk, rec, i)


def _begin(sk, rec):
    rec.setdefault("copies", [])
    rec.setdefault("constraints", [])
    rec["_prefix"] = PREFIX_OF(rec["name"])
    rec["_next"] = 0
    rec["_points"] = {}  # (orig geo, pos) -> True once tied for this copy: shared corners are tied once


def PREFIX_OF(name):
    """'Pattern3' -> 'pat3': the constraint name prefix of a pattern."""
    return sketches.PATTERN_PREFIX + name[len("Pattern"):]


def _end(sk, rec):
    for key in ("_prefix", "_next", "_points"):
        rec.pop(key, None)
    recs = [r for r in records(sk) if r.get("name") != rec["name"]]
    recs.append(rec)
    save_records(sk, recs)
    return rec


def _originals(sk, rec):
    out = []
    for gid in rec["originals"]:
        i = index_of(sk, gid)
        if i is None:
            raise ValueError("The pattern's original geometry is gone: delete the pattern")
        ref_points(sk, i)  # raises for unsupported types
        out.append(i)
    return out


def _coincident_points(sk, geos):
    """{(geo, pos): (geo0, pos0)}: for every point of `geos` that is coincident with an earlier point of the
    same set, the earlier one (a closed rectangle's corners are tied once)."""
    alias = {}
    seen = []
    for g in geos:
        for pos in ref_points(sk, g):
            p = point_of(sk, g, pos)
            for (g0, pos0, q) in seen:
                if (p - q).Length < 1e-7:
                    alias[(g, pos)] = (g0, pos0)
                    break
            else:
                seen.append((g, pos, p))
    return alias


def _translation(rec, k, j):
    """Expressions of a copy's offset: k steps along direction 1, j along direction 2 (0 when single)."""
    sign = -1 if rec.get("flip") else 1
    terms_x = ["%d * InCadModel.%s * cos(%s deg)" % (sign * k, rec["spacing_param"], repr(float(rec["angle"])))]
    terms_y = ["%d * InCadModel.%s * sin(%s deg)" % (sign * k, rec["spacing_param"], repr(float(rec["angle"])))]
    if j:
        terms_x.append("%d * InCadModel.%s * cos(%s deg)" % (j, rec["spacing_param2"], repr(float(rec["angle2"]))))
        terms_y.append("%d * InCadModel.%s * sin(%s deg)" % (j, rec["spacing_param2"], repr(float(rec["angle2"]))))
    return " + ".join(terms_x), " + ".join(terms_y)


def _offset_vector(rec, k, j):
    sign = -1 if rec.get("flip") else 1
    s1 = _param_value(rec["_doc"], rec["spacing_param"])
    a1 = math.radians(rec["angle"])
    v = App.Vector(sign * k * s1 * math.cos(a1), sign * k * s1 * math.sin(a1), 0)
    if j:
        s2 = _param_value(rec["_doc"], rec["spacing_param2"])
        a2 = math.radians(rec["angle2"])
        v += App.Vector(j * s2 * math.cos(a2), j * s2 * math.sin(a2), 0)
    return v


def _param_value(doc, name):
    from incad.core import model
    return float(getattr(model._model_obj(doc), name).getValueAs("mm"))


def build_rect(doc, sk, rec):
    """Copies of the originals at k steps along direction 1 (and j along direction 2), each point tied to the
    original's by DistanceX/DistanceY with expressions, round geometry Equal to the original."""
    rec["_doc"] = doc
    _begin(sk, rec)
    originals = _originals(sk, rec)
    alias = _coincident_points(sk, originals)
    count, count2 = int(rec["count"]), int(rec.get("count2") or 1)
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    for j in range(count2):
        for k in range(count):
            if k == 0 and j == 0:
                continue
            offset = _offset_vector(rec, k, j)
            if offset.Length < 1e-9:
                raise ValueError("The copies would land on the original: give the pattern a spacing")
            ex, ey = _translation(rec, k, j)
            copy_ids = []
            new = {}
            for g in originals:
                c = _copy_geometry(sk, g, offset=offset)
                new[g] = c
                copy_ids.append(ensure_id(sk, c))
            for g in originals:
                c = new[g]
                for pos in ref_points(sk, g):
                    src = alias.get((g, pos), (g, pos))
                    if (src, k, j) in rec["_points"]:
                        _add(sk, rec, Sketcher.Constraint("Coincident", c, pos, new[src[0]], src[1]))
                        continue
                    rec["_points"][(src, k, j)] = True
                    _add(sk, rec, Sketcher.Constraint("DistanceX", g, pos, c, pos, offset.x), ex)
                    _add(sk, rec, Sketcher.Constraint("DistanceY", g, pos, c, pos, offset.y), ey)
                if geometry_type(sk, g) in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
                    _add(sk, rec, Sketcher.Constraint("Equal", g, c))
            rec["copies"].append(copy_ids)
    rec.pop("_doc", None)
    return _end(sk, rec)


def copies_of(sk, name):
    rec = find(sk, name)
    if rec is None:
        return []
    return [i for ids in rec.get("copies", []) for i in [index_of(sk, g) for g in ids] if i is not None]


def remove(doc, sk, name):
    """Delete a pattern's copies (spokes included) and constraints; the original stays. Missing pieces (deleted
    by hand) are skipped."""
    rec = find(sk, name)
    if rec is None:
        return
    names = set(rec.get("constraints", []))
    for i in sorted([i for i, c in enumerate(sk.Constraints) if c.Name in names], reverse=True):
        sk.delConstraint(i)
    for i in sorted(copies_of(sk, name), reverse=True):
        sk.delGeometry(i)
    save_records(sk, [r for r in records(sk) if r.get("name") != name])
```

`_rotate_in_place` is used by Task 3; `Part.Geometry.transform(Matrix)` exists on every geometry type.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: `Ran 10 tests … OK`. If `test_a_closed_rectangle_is_tied_once_per_corner` reports a changed `solve()` result, the coincident-corner aliasing is wrong: print `alias` and check the four corners map to two originals each.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/sketch_patterns.py tests/headless/test_sketch_patterns.py
git commit -m "Sketch patterns: rectangular copies tied to the original by hidden DistanceX/DistanceY expressions on the spacing parameter"
```

---

### Task 3: Circular copies on construction spokes, equal spacing, and the checks

**Files:**
- Modify: `InCad/incad/core/sketch_patterns.py`
- Test: `tests/headless/test_sketch_patterns.py`

**Interfaces:**
- Consumes: Task 2 (`_copy_geometry`, `_add`, `_begin`, `_end`, `_originals`, `_coincident_points`, `remove`, `copies_of`).
- Produces:
  - `build_circ(doc, sk, rec) -> rec`: `rec` has `name`, `originals`, `count`, `axis` (`[geo, pos]`, geo may be -1 with pos 1 for the origin), `angle_param` (model parameter name, angle: the STEP angle), `flip`. Fills `copies` (each copy's ids, its spokes included), `constraints`.
  - `step_angle(total_deg, count, fitted) -> float`: Fitted: `total/count` when `total == 360`, else `total/(count-1)`; not fitted: `total`.
  - `equal_spacing(sk, originals, start, end) -> (spacing_mm, angle_deg)` from two limits (`(geo, pos)` each: a line → its direction's normal is the pattern direction, a point → the vector between the limits), the part's rules: From is the start, equal margins, "no room", "pick the other end as From", coinciding limits refused.
  - `check_axis(sk, originals, axis)`: raises `ValueError("Pick the axis point away from the geometry being repeated")` when the axis point coincides with a point of the originals.

- [ ] **Step 1: Write the failing tests**

```python
class CircularTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sc")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _circ(self, originals, count=4, step="90 deg", axis=(-1, 1), flip=False):
        name = sp.next_name(self.sk)
        rec = {"name": name, "kind": "circ", "originals": [sp.ensure_id(self.sk, g) for g in originals],
               "count": count, "axis": list(axis), "flip": flip,
               "angle_param": model.new_feature_parameter(self.doc, step, "angle")}
        rec = sp.build_circ(self.doc, self.sk, rec)
        self.doc.recompute()
        return rec

    def _xy(self, geo, pos):
        p = sp.point_of(self.sk, geo, pos)
        return round(p.x, 3), round(p.y, 3)

    def test_a_circle_goes_round_the_origin_on_spokes(self):
        c = circle(self.sk, 10, 0, 1)
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 10.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 0.0))
        rec = self._circ([c], count=4, step="90 deg")
        self.assertEqual(len(rec["copies"]), 3)
        centres = sorted(self._xy(sp.index_of(self.sk, ids[0]), 3) for ids in rec["copies"])
        self.assertEqual(centres, [(-10.0, 0.0), (0.0, -10.0), (0.0, 10.0)])
        spokes = [i for ids in rec["copies"] for i in map(lambda g: sp.index_of(self.sk, g), ids)
                  if self.sk.getConstruction(i)]
        self.assertEqual(len(spokes), 3)  # one per copy; the original's own spoke is listed too
        self.assertEqual(len([i for i in range(self.sk.GeometryCount) if self.sk.getConstruction(i)]), 4)
        self.assertEqual(self.sk.solve(), 0)
        self.assertTrue(all(self.sk.getVirtualSpace(i) for i, k in enumerate(self.sk.Constraints)
                            if sketch.is_pattern_name(k.Name)))

    def test_copies_follow_the_original_the_axis_and_the_angle(self):
        c = circle(self.sk, 10, 0, 1)
        dx = self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 10.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 0.0))
        rec = self._circ([c], count=2, step="90 deg")
        k = sp.index_of(self.sk, [g for g in rec["copies"][0] if not self.sk.getConstruction(sp.index_of(self.sk, g))][0])
        self.assertEqual(self._xy(k, 3), (0.0, 10.0))
        self.sk.setDatum(dx, App.Units.Quantity("5 mm"))
        self.doc.recompute()
        self.assertEqual(self._xy(k, 3), (0.0, 5.0))
        model.set_model_parameter(self.doc, rec["angle_param"], "180 deg")
        self.doc.recompute()
        self.assertEqual(self._xy(k, 3), (-5.0, 0.0))

    def test_axis_on_a_sketch_point_and_flip(self):
        c = circle(self.sk, 10, 0, 1)
        p = self.sk.addGeometry(Part.Point(App.Vector(4, 0, 0)))
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, p, 1, 4.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, p, 1, 0.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 10.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 0.0))
        rec = self._circ([c], count=2, step="90 deg", axis=(p, 1), flip=True)
        k = sp.index_of(self.sk, rec["copies"][0][0])
        self.assertEqual(self._xy(k, 3), (4.0, -6.0))  # 6 mm from the point, turned the other way

    def test_a_line_and_an_arc_turn_with_their_shape(self):
        ln = line(self.sk, 10, 0, 14, 0)
        arc = self.sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(20, 0, 0), App.Vector(0, 0, 1), 2),
                                                   0.0, math.pi / 2))
        for g, pos, x, y in ((ln, 1, 10.0, 0.0), (ln, 2, 14.0, 0.0), (arc, 3, 20.0, 0.0)):
            self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, g, pos, x))
            self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, g, pos, y))
        self.sk.addConstraint(Sketcher.Constraint("Radius", arc, 2.0))
        rec = self._circ([ln, arc], count=2, step="90 deg")
        l2, a2 = [sp.index_of(self.sk, g) for g in rec["copies"][0] if not self.sk.getConstruction(sp.index_of(self.sk, g))]
        self.assertEqual(self._xy(l2, 1), (0.0, 10.0))
        self.assertEqual(self._xy(l2, 2), (0.0, 14.0))
        self.assertEqual(self._xy(a2, 1), (0.0, 22.0))  # the arc's start (22, 0) turned by 90°
        self.assertAlmostEqual(self.sk.Geometry[a2].Radius, 2.0, places=6)
        self.assertEqual(self.sk.solve(), 0)

    def test_step_angle_and_closed_ring(self):
        self.assertAlmostEqual(sp.step_angle(360.0, 4, True), 90.0)
        self.assertAlmostEqual(sp.step_angle(180.0, 4, True), 60.0)
        self.assertAlmostEqual(sp.step_angle(30.0, 4, False), 30.0)

    def test_axis_on_the_geometry_is_refused(self):
        c = circle(self.sk, 10, 0, 1)
        with self.assertRaises(ValueError) as cm:
            self._circ([c], count=3, axis=(c, 3))
        self.assertIn("away from the geometry", str(cm.exception))
        self.assertEqual(self.sk.GeometryCount, 1)  # nothing half-built is left behind

    def test_remove_takes_the_spokes_too(self):
        c = circle(self.sk, 10, 0, 1)
        rec = self._circ([c], count=5)
        sp.remove(self.doc, self.sk, rec["name"])
        self.doc.recompute()
        self.assertEqual(self.sk.GeometryCount, 1)
        self.assertEqual([k.Name for k in self.sk.Constraints if sketch.is_pattern_name(k.Name)], [])


class EqualSpacingTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Se")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.left = line(self.sk, 0, 0, 0, 10, construction=True)    # x = 0
        self.right = line(self.sk, 40, 0, 40, 10, construction=True)  # x = 40
        self.hole = circle(self.sk, 6, 5, 2)                           # x 4..8, near the left limit
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_from_the_near_line_toward_the_far_one_leaves_equal_margins(self):
        spacing, angle = sp.equal_spacing(self.sk, [self.hole], (self.left, 0), (self.right, 0), 3)
        self.assertAlmostEqual(spacing, 14.0, places=6)   # 4 mm margins: holes at 4..8, 18..22, 32..36
        self.assertAlmostEqual(angle, 0.0, places=6)

    def test_from_the_far_line_says_to_pick_the_other_end(self):
        with self.assertRaises(ValueError) as cm:
            sp.equal_spacing(self.sk, [self.hole], (self.right, 0), (self.left, 0), 3)
        self.assertIn("pick the other end as From", str(cm.exception))

    def test_no_room_names_the_sizes(self):
        with self.assertRaises(ValueError) as cm:
            sp.equal_spacing(self.sk, [self.hole], (self.left, 0), (self.right, 0), 12)
        self.assertIn("no room", str(cm.exception).lower())
        self.assertIn("4.0 mm wide", str(cm.exception))

    def test_points_as_limits_set_the_direction(self):
        a = self.sk.addGeometry(Part.Point(App.Vector(0, 0, 0)))
        b = self.sk.addGeometry(Part.Point(App.Vector(0, 30, 0)))
        c = circle(self.sk, 0, 3, 1)  # y 2..4
        self.doc.recompute()
        spacing, angle = sp.equal_spacing(self.sk, [c], (a, 1), (b, 1), 2)
        self.assertAlmostEqual(angle, 90.0, places=6)
        self.assertAlmostEqual(spacing, 24.0, places=6)  # 2 mm margins: 2..4 and 26..28

    def test_coinciding_limits_are_refused(self):
        with self.assertRaises(ValueError) as cm:
            sp.equal_spacing(self.sk, [self.hole], (self.left, 0), (self.left, 0), 3)
        self.assertIn("From and To", str(cm.exception))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: FAIL with `AttributeError: … has no attribute 'build_circ'`

- [ ] **Step 3: Implement circular copies, step angle, equal spacing, axis check**

Append to `InCad/incad/core/sketch_patterns.py`:

```python
# ----- circular -----
def step_angle(total_deg, count, fitted):
    """The angle between neighbouring copies. Fitted spreads the copies within `total`; a full 360° ring
    closes without a copy on the original."""
    if not fitted:
        return float(total_deg)
    if abs(total_deg - 360.0) < 1e-9:
        return 360.0 / count
    return float(total_deg) / (count - 1)


def check_axis(sk, originals, axis):
    centre = point_of(sk, axis[0], axis[1])
    for g in originals:
        for pos in ref_points(sk, g):
            if (point_of(sk, g, pos) - centre).Length < 1e-7:
                raise ValueError("Pick the axis point away from the geometry being repeated")


def _spoke(sk, rec, axis, geo, pos, hidden_coincidence=True):
    """A construction line from the axis point to (geo, pos), both ends coincident."""
    a = point_of(sk, axis[0], axis[1])
    b = point_of(sk, geo, pos)
    s = sk.addGeometry(Part.LineSegment(a, b), True)
    _add(sk, rec, Sketcher.Constraint("Coincident", s, 1, axis[0], axis[1]))
    _add(sk, rec, Sketcher.Constraint("Coincident", s, 2, geo, pos))
    return s


def build_circ(doc, sk, rec):
    """Copies turned about the axis point: every reference point of a copy sits at the end of a construction
    spoke Equal to the original's spoke and at k × step angle from it (an expression on the angle parameter);
    lines add Equal + Angle to the original, circles and arcs Equal."""
    _begin(sk, rec)
    originals = _originals(sk, rec)
    axis = tuple(rec["axis"])
    check_axis(sk, originals, axis)
    count = int(rec["count"])
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    from incad.core import model
    step = float(getattr(model._model_obj(doc), rec["angle_param"]).getValueAs("deg"))
    sign = -1 if rec.get("flip") else 1
    alias = _coincident_points(sk, originals)
    centre = point_of(sk, axis[0], axis[1])
    spoke0 = {}
    for g in originals:
        for pos in ref_points(sk, g):
            src = alias.get((g, pos), (g, pos))
            if src not in spoke0:
                spoke0[src] = _spoke(sk, rec, axis, src[0], src[1])
    rec["spokes0"] = [ensure_id(sk, s) for s in spoke0.values()]
    for k in range(1, count):
        angle = math.radians(sign * k * step)
        new, copy_ids = {}, []
        for g in originals:
            c = _copy_geometry(sk, g, rotate=(centre, angle))
            new[g] = c
            copy_ids.append(ensure_id(sk, c))
        done = {}
        for g in originals:
            c = new[g]
            for pos in ref_points(sk, g):
                src = alias.get((g, pos), (g, pos))
                if src in done:
                    _add(sk, rec, Sketcher.Constraint("Coincident", c, pos, new[src[0]], src[1]))
                    continue
                s = _spoke(sk, rec, axis, c, pos)
                done[src] = s
                copy_ids.append(ensure_id(sk, s))
                _add(sk, rec, Sketcher.Constraint("Equal", spoke0[src], s))
                _add(sk, rec, Sketcher.Constraint("Angle", spoke0[src], s, angle),
                     "%d * InCadModel.%s" % (sign * k, rec["angle_param"]))
            t = geometry_type(sk, g)
            if t == "Part::GeomLineSegment":
                _add(sk, rec, Sketcher.Constraint("Equal", g, c))
                _add(sk, rec, Sketcher.Constraint("Angle", g, c, angle), "%d * InCadModel.%s" % (sign * k, rec["angle_param"]))
            elif t in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
                _add(sk, rec, Sketcher.Constraint("Equal", g, c))
        rec["copies"].append(copy_ids)
    return _end(sk, rec)
```

A line copy is tied by its start spoke (2 DOF) + Equal (1) + Angle (1) = 4; so `ref_points` for lines must give only the START point in the circular case. Make that explicit: in `build_circ` use `_circ_points(sk, g)` instead of `ref_points`:

```python
def _circ_points(sk, geo):
    """Points a circular copy is tied by: a line's start (its direction and length come from Equal + Angle),
    an arc's two ends, a circle's centre, a point."""
    t = geometry_type(sk, geo)
    return [1] if t == "Part::GeomLineSegment" else ref_points(sk, geo)
```

and use `_circ_points` in the two loops of `build_circ` (both the `spoke0` loop and the copies loop) and in `check_axis`. `_coincident_points` keeps using `ref_points` (all points), which is right for aliasing.

`remove()` must also delete `rec["spokes0"]`: extend `copies_of` to include them:

```python
def copies_of(sk, name):
    rec = find(sk, name)
    if rec is None:
        return []
    ids = [g for ids in rec.get("copies", []) for g in ids] + list(rec.get("spokes0", []))
    return [i for i in (index_of(sk, g) for g in ids) if i is not None]
```

Equal spacing (2D version of the part's rule):

```python
# ----- equal spacing between two limits -----
def _limit(sk, limit):
    """(point, normal) of a limit: a line gives a point on it and its normal; a point gives itself and None."""
    geo, pos = limit
    if geo >= 0 and geometry_type(sk, geo) == "Part::GeomLineSegment" and pos == 0:
        a, b = point_of(sk, geo, 1), point_of(sk, geo, 2)
        d = b - a
        return a, App.Vector(-d.y, d.x, 0).normalize()
    if geo == -1 and pos == 0:
        return App.Vector(0, 0, 0), App.Vector(0, 1, 0)
    if geo == -2 and pos == 0:
        return App.Vector(0, 0, 0), App.Vector(1, 0, 0)
    return point_of(sk, geo, pos), None


def _extent(sk, originals, direction):
    lo = hi = None
    for g in originals:
        shape = sk.Geometry[g].toShape()
        for v in shape.Vertexes:
            t = v.Point.dot(direction)
            lo = t if lo is None else min(lo, t)
            hi = t if hi is None else max(hi, t)
        if geometry_type(sk, g) in ("Part::GeomCircle", "Part::GeomArcOfCircle"):
            c = sk.Geometry[g].Center.dot(direction)
            r = sk.Geometry[g].Radius
            lo, hi = min(lo if lo is not None else c - r, c - r), max(hi if hi is not None else c + r, c + r)
    return lo, hi


def equal_spacing(sk, originals, start, end, count):
    """(spacing in mm, direction angle in degrees) that puts the first copy as far from the From limit as the
    last is from the To limit. From is the start; the copies run toward To."""
    p0, n0 = _limit(sk, start)
    p1, n1 = _limit(sk, end)
    direction = n0 if n0 is not None else (n1 if n1 is not None else (p1 - p0))
    if direction.Length < 1e-9:
        raise ValueError("From and To coincide: pick two different limits")
    direction = App.Vector(direction).normalize()
    t0, t1 = p0.dot(direction), p1.dot(direction)
    if abs(t1 - t0) < 1e-9:
        raise ValueError("From and To coincide: pick two different limits")
    if t1 < t0:
        direction, t0, t1 = -direction, -t0, -t1
    lo, hi = _extent(sk, originals, direction)
    width, margin, room = hi - lo, lo - t0, t1 - t0
    if count < 2:
        raise ValueError("Use a count of 2 or more to space the copies between the limits")
    if margin < -1e-6:
        raise ValueError("The picked geometry lies %.1f mm behind the start (the From pick): pick the other end "
                         "as From, or move the limit" % -margin)
    spacing = (t1 - margin - hi) / (count - 1)  # the part's rule: (end - margin - far edge) / (count - 1)
    if spacing < width - 1e-6:
        raise ValueError("There is no room: the picked geometry is %.1f mm wide and %.1f mm from the start, so %d "
                         "copies need %.1f mm, but only %.1f mm lie between the limits. Use fewer copies, move "
                         "the limits, or pick the other end as From" % (width, margin, count,
                                                                       count * width + 2 * margin, room))
    return spacing, math.degrees(math.atan2(direction.y, direction.x))
```

(It mirrors the part's `_fit_spacing` in `incad/features/patterns.py`: `margin = u_lo - s`, `spacing = (e - margin - u_hi) / (count - 1)`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: `Ran 22 tests … OK`. The Angle constraint between two lines is signed; if a copy lands mirrored, the spoke's direction (axis → point) is reversed somewhere: both spokes must run from the axis point.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/sketch_patterns.py tests/headless/test_sketch_patterns.py
git commit -m "Sketch patterns: circular copies on construction spokes (Equal + Angle on the angle parameter), equal spacing between two limits, axis check"
```

---

### Task 4: Edit (rebuild), broken patterns, and the feature kinds

**Files:**
- Create: `InCad/incad/features/sketch_patterns.py`
- Modify: `InCad/incad/core/sketch_patterns.py` (rebuild), `InCad/incad/features/common.py` (pick kinds, labels)
- Test: `tests/headless/test_sketch_patterns.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces (model): `rebuild(doc, sk, rec) -> rec` (remove then build by `rec["kind"]`); `is_broken(sk, name) -> bool` (some copy id no longer in the sketch); `pattern_of(sk, index) -> str | None` (the pattern a geometry index belongs to, original or copy or spoke); `is_copy(sk, index) -> bool`.
- Produces (kinds, in `incad.features.sketch_patterns`): `SKETCH_RECT`, `SKETCH_CIRC` with `__name__` `"incad.features.sketch_rect"` / `"incad.features.sketch_circ"`, `TITLE`, `ICON`, `TYPES=()`, `IN_SKETCH=True`, `NEEDS_PROFILE=False`, `FIELDS`, `defaults(doc, body, profile)`, `create(doc, body, profile, values) -> sketch`, `read(doc, sketch)` (reads `sketch.InCadEditing` — the pattern name the shell put there for an edit), `update(doc, sketch, values) -> sketch`, `param_names(sketch) -> {key: dN}`, `PRESELECT = {"geometry": "sketch_geometry"}`. Values: see the spec's tables; picks are stored as `"Sketch:Edge3"` texts (`format_picks`).
- Produces (common): pick kinds `sketch_geometry`, `sketch_direction`, `sketch_point`, `sketch_limit` in `accepts`; `_EMPTY_HINT` entries; `pick_label` texts "Line 3", "Circle 2 centre", "X axis", "Origin".

- [ ] **Step 1: Write the failing tests**

```python
class EditAndKindsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sk")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.hole = circle(self.sk, 6, 5, 2)
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, self.hole, 3, 6.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, self.hole, 3, 5.0))
        self.doc.recompute()
        from incad.features import sketch_patterns as kinds
        self.kinds = kinds

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _pick(self, sub):
        return "%s:%s" % (self.sk.Name, sub)

    def test_rect_kind_creates_reads_and_updates(self):
        k = self.kinds.SKETCH_RECT
        v = dict(k.defaults(self.doc, self.body, self.sk), geometry=self._pick("Edge1"), count1="3", spacing1="12 mm")
        f = k.create(self.doc, self.body, self.sk, v)
        self.doc.recompute()
        self.assertIs(f, self.sk)
        name = self.sk.InCadEditing
        rec = sp.find(self.sk, name)
        self.assertEqual(len(rec["copies"]), 2)
        back = k.read(self.doc, self.sk)
        self.assertEqual((back["geometry"], back["count1"], back["spacing1"], back["fit1"], back["dir1"]),
                         (self._pick("Edge1"), "3", "12 mm", "spacing", self._pick("H_Axis")))
        self.assertIn("spacing1", k.param_names(self.sk))
        k.update(self.doc, self.sk, dict(back, count1="5"))
        self.doc.recompute()
        self.assertEqual(len(sp.find(self.sk, name)["copies"]), 4)
        self.assertEqual(self.sk.GeometryCount, 5)
        self.assertEqual(self.sk.solve(), 0)

    def test_edit_with_fewer_copies_removes_the_surplus(self):
        k = self.kinds.SKETCH_RECT
        v = dict(k.defaults(self.doc, self.body, self.sk), geometry=self._pick("Edge1"), count1="5", spacing1="12 mm")
        k.create(self.doc, self.body, self.sk, v)
        k.update(self.doc, self.sk, dict(k.read(self.doc, self.sk), count1="3"))
        self.doc.recompute()
        self.assertEqual(self.sk.GeometryCount, 3)
        self.assertEqual(len([c for c in self.sk.Constraints if sketch.is_pattern_name(c.Name)]), 2 * 2 + 2)

    def test_a_hand_deleted_copy_does_not_break_edit(self):
        k = self.kinds.SKETCH_RECT
        v = dict(k.defaults(self.doc, self.body, self.sk), geometry=self._pick("Edge1"), count1="4", spacing1="12 mm")
        k.create(self.doc, self.body, self.sk, v)
        name = self.sk.InCadEditing
        gone = sp.index_of(self.sk, sp.find(self.sk, name)["copies"][1][0])
        self.sk.delGeometry(gone)  # FreeCAD drops that geometry's constraints with it
        self.doc.recompute()
        self.assertTrue(sp.is_broken(self.sk, name))
        k.update(self.doc, self.sk, dict(k.read(self.doc, self.sk), count1="4"))
        self.doc.recompute()
        self.assertFalse(sp.is_broken(self.sk, name))
        self.assertEqual(self.sk.GeometryCount, 4)
        self.assertEqual(self.sk.solve(), 0)

    def test_equal_spacing_in_the_rect_kind_stores_the_spacing_and_direction(self):
        left = line(self.sk, 0, 0, 0, 10, construction=True)
        right = line(self.sk, 40, 0, 40, 10, construction=True)
        self.doc.recompute()
        k = self.kinds.SKETCH_RECT
        v = dict(k.defaults(self.doc, self.body, self.sk), geometry=self._pick("Edge1"), fit1="faces", count1="3",
                 from1=self._pick("Edge%d" % (left + 1)), to1=self._pick("Edge%d" % (right + 1)))
        k.create(self.doc, self.body, self.sk, v)
        self.doc.recompute()
        back = k.read(self.doc, self.sk)
        self.assertEqual(back["spacing1"], "14 mm")
        rec = sp.find(self.sk, self.sk.InCadEditing)
        last = sp.index_of(self.sk, rec["copies"][-1][0])
        self.assertAlmostEqual(sp.point_of(self.sk, last, 3).x, 34.0, places=3)
        with self.assertRaises(ValueError) as cm:
            k.update(self.doc, self.sk, dict(back, from1=back["to1"], to1=back["from1"]))
        self.assertIn("pick the other end as From", str(cm.exception))

    def test_circ_kind_with_fitted_ring_and_axis_on_the_origin(self):
        k = self.kinds.SKETCH_CIRC
        v = dict(k.defaults(self.doc, self.body, self.sk), geometry=self._pick("Edge1"), count="4", angle="360 °")
        k.create(self.doc, self.body, self.sk, v)
        self.doc.recompute()
        back = k.read(self.doc, self.sk)
        self.assertEqual((back["axis"], back["count"], back["angle"], back["fit"]), (self._pick("RootPoint"), "4", "360 °", "fitted"))
        rec = sp.find(self.sk, self.sk.InCadEditing)
        self.assertEqual(len(rec["copies"]), 3)
        self.assertEqual(model.parameter_text(self.doc, rec["angle_param"]), "90 deg")
        k.update(self.doc, self.sk, dict(back, fit="between", angle="30 °", count="3"))
        self.doc.recompute()
        rec = sp.find(self.sk, self.sk.InCadEditing)
        self.assertEqual(model.parameter_text(self.doc, rec["angle_param"]), "30 deg")

    def test_nothing_picked_asks_for_geometry_and_a_copy_cannot_be_patterned(self):
        k = self.kinds.SKETCH_RECT
        with self.assertRaises(ValueError) as cm:
            k.create(self.doc, self.body, self.sk, k.defaults(self.doc, self.body, self.sk))
        self.assertIn("Click the geometry to repeat", str(cm.exception))
        v = dict(k.defaults(self.doc, self.body, self.sk), geometry=self._pick("Edge1"), count1="2", spacing1="12 mm")
        k.create(self.doc, self.body, self.sk, v)
        self.doc.recompute()
        self.assertTrue(sp.is_copy(self.sk, 1))
        self.assertEqual(sp.pattern_of(self.sk, 1), self.sk.InCadEditing)
        self.assertEqual(sp.pattern_of(self.sk, 0), self.sk.InCadEditing)  # the original belongs to it too
        self.sk.InCadEditing = ""
        with self.assertRaises(ValueError) as cm:
            k.create(self.doc, self.body, self.sk, dict(v, geometry=self._pick("Edge2")))
        self.assertIn("Pattern the original, not a copy", str(cm.exception))

    def test_picks_accept_the_right_elements(self):
        from incad.features import common
        ln = line(self.sk, 0, 0, 4, 0)
        e = self.sk.addGeometry(Part.Ellipse(App.Vector(20, 20, 0), 3, 2))
        self.doc.recompute()
        self.assertTrue(common.accepts("sketch_geometry", self.sk, "Edge1"))
        self.assertFalse(common.accepts("sketch_geometry", self.sk, "Edge%d" % (e + 1)))
        self.assertTrue(common.accepts("sketch_direction", self.sk, "Edge%d" % (ln + 1)))
        self.assertFalse(common.accepts("sketch_direction", self.sk, "Edge1"))  # a circle is no direction
        self.assertTrue(common.accepts("sketch_direction", self.sk, "H_Axis"))
        self.assertTrue(common.accepts("sketch_point", self.sk, "RootPoint"))
        self.assertTrue(common.accepts("sketch_point", self.sk, "Vertex1"))
        self.assertTrue(common.accepts("sketch_limit", self.sk, "Edge%d" % (ln + 1)))
        self.assertTrue(common.accepts("sketch_limit", self.sk, "Vertex1"))
        self.assertFalse(common.accepts("sketch_limit", self.sk, "Edge1"))
        self.assertEqual(common.pick_label("sketch_direction", self._pick("H_Axis")), "X axis")
        self.assertEqual(common.pick_label("sketch_point", self._pick("RootPoint")), "Origin")
        self.assertEqual(common.pick_label("sketch_geometry", ""), "Click the geometry to repeat…")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: FAIL with `ImportError: cannot import name 'sketch_patterns' from 'incad.features'`

- [ ] **Step 3: Model additions (rebuild, broken, membership)**

Append to `InCad/incad/core/sketch_patterns.py`:

```python
# ----- edit -----
def is_broken(sk, name):
    rec = find(sk, name)
    if rec is None:
        return False
    ids = [g for ids in rec.get("copies", []) for g in ids] + list(rec.get("spokes0", []))
    return any(index_of(sk, g) is None for g in ids)


def rebuild(doc, sk, rec):
    """Remove the pattern's copies (whatever is left of them) and build them again from `rec`."""
    remove(doc, sk, rec["name"])
    rec = dict(rec, copies=[], constraints=[], spokes0=[])
    return build_rect(doc, sk, rec) if rec["kind"] == "rect" else build_circ(doc, sk, rec)


def pattern_of(sk, index):
    """The pattern a geometry belongs to (original, copy or spoke), or None."""
    gid = sk.getGeometryId(index)
    if gid is None:
        return None
    for r in records(sk):
        if gid in r.get("originals", []) or gid in r.get("spokes0", []) or any(gid in ids for ids in r.get("copies", [])):
            return r["name"]
    return None


def is_copy(sk, index):
    gid = sk.getGeometryId(index)
    return gid is not None and any(gid in ids for r in records(sk) for ids in r.get("copies", []))
```

- [ ] **Step 4: Pick kinds and labels in `common.py`**

In `accepts(kind, obj, sub)` add before `el = _element(obj, sub)`:

```python
    if kind.startswith("sketch_"):
        return _accepts_sketch(kind, obj, sub)
```

and the helper (module level):

```python
def _accepts_sketch(kind, sk, sub):
    """Picks inside the sketch being edited: its own lines/arcs/circles/points, axes and origin."""
    from incad.core import sketch_patterns as sp
    if sk is None or sk.TypeId != "Sketcher::SketchObject" or not sub:
        return False
    try:
        geo, pos = sp.element(sk, sub)
    except (ValueError, IndexError):
        return False
    if kind == "sketch_point":
        return pos != 0  # any vertex, the origin ('RootPoint' is (-1, 1))
    if geo < 0:  # H_Axis / V_Axis / RootPoint
        return kind == "sketch_direction" and pos == 0
    t = sp.geometry_type(sk, geo)
    if kind == "sketch_geometry":
        return pos == 0 and t in sp.SUPPORTED
    if kind == "sketch_direction":
        return pos == 0 and t == "Part::GeomLineSegment"
    if kind == "sketch_limit":
        return pos != 0 or t == "Part::GeomLineSegment"
    return False
```

Extend the hints and labels:

```python
_EMPTY_HINT = {"feature": "Click a feature (tree or view)…", "plane": "Click a face or work plane…",
               "limit": "Click a face, edge or work plane…", "sketch_geometry": "Click the geometry to repeat…",
               "sketch_direction": "Click a line (or the X/Y axis)…", "sketch_point": "Click a point…",
               "sketch_limit": "Click a line or a point…"}
_PLURAL.update({"sketch_geometry": "items", "sketch_limit": "items"})
_SKETCH_NAMES = {"H_Axis": "X axis", "V_Axis": "Y axis", "RootPoint": "Origin"}
```

and in `pick_label`, in the single-item branch, before `label = obj.Label …`:

```python
        if kind.startswith("sketch_") and sub:
            return _sketch_element_label(obj, sub)
```

with

```python
def _sketch_element_label(sk, sub):
    from incad.core import sketch_patterns as sp
    if sub in _SKETCH_NAMES:
        return _SKETCH_NAMES[sub]
    try:
        geo, pos = sp.element(sk, sub)
        kind = {"Part::GeomLineSegment": "Line", "Part::GeomArcOfCircle": "Arc", "Part::GeomCircle": "Circle",
                "Part::GeomPoint": "Point"}.get(sp.geometry_type(sk, geo), "Curve")
    except Exception:
        return sub
    if pos == 3:
        return "%s %d centre" % (kind, geo + 1)
    if pos in (1, 2):
        return "%s %d %s" % (kind, geo + 1, "start" if pos == 1 else "end")
    return "%s %d" % (kind, geo + 1)
```

- [ ] **Step 5: The kinds**

```python
# InCad/incad/features/sketch_patterns.py
"""Rectangular and Circular patterns inside a sketch: the part's pattern dialogs, on sketch geometry. The
'feature' these kinds hand the session is the sketch itself; the pattern being made or edited is named in
sketch.InCadEditing (the shell sets it for an edit; create sets it for the new one)."""
import math
from types import SimpleNamespace

from incad.core import sketch_patterns as sp
from incad.features.common import Field, format_picks, parse_picks

EDITING_PROP = "InCadEditing"


def _editing(sk):
    return getattr(sk, EDITING_PROP, "") or ""


def _set_editing(sk, name):
    if EDITING_PROP not in sk.PropertiesList:
        sk.addProperty("App::PropertyString", EDITING_PROP, "InCad", "Pattern open in the dialog")
    setattr(sk, EDITING_PROP, name)


def _picks(doc, sk, text, kind):
    pairs = [(o, s) for o, s in parse_picks(doc, text) if o is sk and s]
    out = []
    for _, s in pairs:
        geo, pos = sp.element(sk, s)
        out.append((geo, pos))
    return out


def _geometry(doc, sk, text):
    picks = _picks(doc, sk, text, "sketch_geometry")
    if not picks:
        raise ValueError("Click the geometry to repeat")
    geos = []
    for geo, _ in picks:
        if geo < 0:
            continue
        if sp.is_copy(sk, geo) and sp.pattern_of(sk, geo) != _editing(sk):
            raise ValueError("Pattern the original, not a copy")
        sp.ref_points(sk, geo)  # raises for splines/ellipses
        if geo not in geos:
            geos.append(geo)
    if not geos:
        raise ValueError("Click the geometry to repeat")
    return geos


def _direction_angle(doc, sk, text):
    picks = _picks(doc, sk, text, "sketch_direction")
    if not picks:
        return 0.0
    geo, _ = picks[0]
    if geo == -1:
        return 0.0
    if geo == -2:
        return 90.0
    a, b = sp.point_of(sk, geo, 1), sp.point_of(sk, geo, 2)
    return math.degrees(math.atan2(b.y - a.y, b.x - a.x))


def _count(text, key="count"):
    t = (text or "").strip()
    if not t.isdigit() or int(t) < 1:
        raise ValueError("Count must be a whole number of 1 or more")
    return int(t)


def _param(doc, rec, key, text, unit_kind):
    """The pattern's model parameter for `key` (spacing_param / angle_param): made once, then updated."""
    from incad.core import model
    name = rec.get(key)
    if name and model.is_model_parameter(doc, name):
        if model.parameter_text(doc, name) != text:
            model.set_model_parameter(doc, name, text)
        return name
    return model.new_feature_parameter(doc, text, unit_kind)


# ----- rectangular -----
RECT_FIELDS = (
    Field("geometry", "Geometry", "picks", pick="sketch_geometry"),
    Field("fit1", "Distribution", "choice", (("spacing", "By spacing"), ("faces", "Equal spacing")), default="spacing"),
    Field("dir1", "Direction 1", "pick", pick="sketch_direction", show_if=("fit1", ("spacing",))),
    Field("flip1", "Flip direction", "bool", default=False),
    Field("count1", "Count", "value_length", default="2"),
    Field("spacing1", "Spacing", "value_length", default="10 mm", show_if=("fit1", ("spacing",))),
    Field("from1", "From", "pick", pick="sketch_limit", show_if=("fit1", ("faces",))),
    Field("to1", "To", "pick", pick="sketch_limit", show_if=("fit1", ("faces",))),
    Field("two_directions", "Two directions", "bool", default=False, show_if=("fit1", ("spacing",))),
    Field("dir2", "Direction 2", "pick", pick="sketch_direction", show_if=(("two_directions", (True,)), ("fit1", ("spacing",)))),
    Field("count2", "Count 2", "value_length", default="2", show_if=(("two_directions", (True,)), ("fit1", ("spacing",)))),
    Field("spacing2", "Spacing 2", "value_length", default="10 mm", show_if=(("two_directions", (True,)), ("fit1", ("spacing",)))),
)


def _rect_defaults(doc, body, sk):
    return {"geometry": "", "fit1": "spacing", "dir1": "%s:H_Axis" % sk.Name if sk is not None else "", "flip1": False,
            "count1": "2", "spacing1": "10 mm", "from1": "", "to1": "", "two_directions": False,
            "dir2": "%s:V_Axis" % sk.Name if sk is not None else "", "count2": "2", "spacing2": "10 mm"}


def _rect_record(doc, sk, name, old, values):
    geos = _geometry(doc, sk, values.get("geometry"))
    count = _count(values.get("count1"), "count1")
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    rec = {"name": name, "kind": "rect", "values": dict(values), "originals": [sp.ensure_id(sk, g) for g in geos],
           "count": count, "flip": bool(values.get("flip1"))}
    if values.get("fit1") == "faces":
        start = _picks(doc, sk, values.get("from1"), "sketch_limit")
        end = _picks(doc, sk, values.get("to1"), "sketch_limit")
        if not start or not end:
            raise ValueError("Pick the From and To limits: where the first and last copies are spaced from")
        spacing, angle = sp.equal_spacing(sk, geos, start[0], end[0], count)
        rec["spacing_param"] = _param(doc, old, "spacing_param", "%.6g mm" % spacing, "length")
        rec["angle"] = angle
        rec["values"]["spacing1"] = "%.6g mm" % spacing
    else:
        rec["spacing_param"] = _param(doc, old, "spacing_param", (values.get("spacing1") or "10 mm").strip(), "length")
        rec["angle"] = _direction_angle(doc, sk, values.get("dir1"))
        if values.get("two_directions"):
            rec["count2"] = _count(values.get("count2"), "count2")
            rec["spacing_param2"] = _param(doc, old, "spacing_param2", (values.get("spacing2") or "10 mm").strip(), "length")
            rec["angle2"] = _direction_angle(doc, sk, values.get("dir2"))
    return rec


def _rect_create(doc, body, sk, values):
    if sk is None:
        raise ValueError("Open a sketch first")
    name = sp.next_name(sk)
    _set_editing(sk, name)
    rec = _rect_record(doc, sk, name, {}, values)
    sp.build_rect(doc, sk, rec)
    return sk


def _rect_update(doc, sk, values):
    name = _editing(sk)
    old = sp.find(sk, name) or {}
    rec = _rect_record(doc, sk, name, old, values)
    sp.rebuild(doc, sk, rec)
    return sk


def _rect_read(doc, sk):
    rec = sp.find(sk, _editing(sk))
    if rec is None:
        return _rect_defaults(doc, None, sk)
    from incad.core import model
    values = dict(_rect_defaults(doc, None, sk), **rec.get("values", {}))
    values["spacing1"] = model.parameter_text(doc, rec["spacing_param"])
    if rec.get("spacing_param2"):
        values["spacing2"] = model.parameter_text(doc, rec["spacing_param2"])
    values["count1"] = str(rec["count"])
    return values


def _rect_params(sk):
    rec = sp.find(sk, _editing(sk)) if sk is not None else None
    if rec is None:
        return {}
    out = {"spacing1": rec.get("spacing_param")}
    if rec.get("spacing_param2"):
        out["spacing2"] = rec["spacing_param2"]
    return out


SKETCH_RECT = SimpleNamespace(
    __name__="incad.features.sketch_rect", TITLE="Rectangular Pattern", ICON="rect_pattern", TYPES=(),
    IN_SKETCH=True, NEEDS_PROFILE=False, FIELDS=RECT_FIELDS, PRESELECT={"geometry": "sketch_geometry"},
    defaults=_rect_defaults, create=_rect_create, read=_rect_read, update=_rect_update, param_names=_rect_params)


# ----- circular -----
CIRC_FIELDS = (
    Field("geometry", "Geometry", "picks", pick="sketch_geometry"),
    Field("axis", "Axis", "pick", pick="sketch_point"),
    Field("count", "Count", "value_length", default="4"),
    Field("angle", "Angle", "value_angle", default="360 °"),
    Field("fit", "Distribution", "choice", (("fitted", "Fitted"), ("between", "Between copies")), default="fitted"),
    Field("flip", "Flip", "bool", default=False),
)


def _circ_defaults(doc, body, sk):
    return {"geometry": "", "axis": "%s:RootPoint" % sk.Name if sk is not None else "", "count": "4",
            "angle": "360 °", "fit": "fitted", "flip": False}


def _angle_deg(text):
    import FreeCAD as App
    try:
        return float(App.Units.Quantity((text or "360 °").replace("°", "deg")).getValueAs("deg"))
    except Exception:
        raise ValueError("Angle must be a number of degrees")


def _circ_record(doc, sk, name, old, values):
    geos = _geometry(doc, sk, values.get("geometry"))
    count = _count(values.get("count"))
    if count < 2:
        raise ValueError("Use a count of 2 or more")
    axis = _picks(doc, sk, values.get("axis"), "sketch_point")
    if not axis:
        raise ValueError("Pick the axis point")
    total = _angle_deg(values.get("angle"))
    step = sp.step_angle(total, count, values.get("fit", "fitted") == "fitted")
    if abs(step) < 1e-9:
        raise ValueError("The copies would land on the original: give the pattern an angle")
    rec = {"name": name, "kind": "circ", "values": dict(values), "originals": [sp.ensure_id(sk, g) for g in geos],
           "count": count, "axis": list(axis[0]), "flip": bool(values.get("flip")),
           "angle_param": _param(doc, old, "angle_param", "%.6g deg" % step, "angle")}
    return rec


def _circ_create(doc, body, sk, values):
    if sk is None:
        raise ValueError("Open a sketch first")
    name = sp.next_name(sk)
    _set_editing(sk, name)
    sp.build_circ(doc, sk, _circ_record(doc, sk, name, {}, values))
    return sk


def _circ_update(doc, sk, values):
    name = _editing(sk)
    old = sp.find(sk, name) or {}
    sp.rebuild(doc, sk, _circ_record(doc, sk, name, old, values))
    return sk


def _circ_read(doc, sk):
    rec = sp.find(sk, _editing(sk))
    if rec is None:
        return _circ_defaults(doc, None, sk)
    values = dict(_circ_defaults(doc, None, sk), **rec.get("values", {}))
    values["count"] = str(rec["count"])
    return values


def _circ_params(sk):
    rec = sp.find(sk, _editing(sk)) if sk is not None else None
    return {"angle": rec["angle_param"]} if rec else {}


SKETCH_CIRC = SimpleNamespace(
    __name__="incad.features.sketch_circ", TITLE="Circular Pattern", ICON="circ_pattern", TYPES=(),
    IN_SKETCH=True, NEEDS_PROFILE=False, FIELDS=CIRC_FIELDS, PRESELECT={"geometry": "sketch_geometry"},
    defaults=_circ_defaults, create=_circ_create, read=_circ_read, update=_circ_update, param_names=_circ_params)

KINDS = (SKETCH_RECT, SKETCH_CIRC)
```

Register them in `InCad/incad/features/__init__.py` so `actions.start_feature("sketch_rect")` finds them:

```python
def kinds():
    from incad.features import (asm_combine, combine, constraints, dressup, extrude, hole, patterns, revolve, shapes,
                                sketch_patterns, thread, work)
    return [extrude, revolve, hole, dressup.FILLET, dressup.CHAMFER, dressup.SHELL, patterns.RECT, patterns.CIRC,
            patterns.MIRROR, work.PLANE, work.AXIS, work.POINT, thread, combine] + list(constraints.KINDS) \
        + [asm_combine] + list(shapes.KINDS) + list(sketch_patterns.KINDS)
```

(`kind_for` matches on `TYPES`, which is empty: a sketch never resolves to these kinds; `edit_feature` on a sketch row keeps opening the sketch.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `tests/run_headless.sh test_sketch_patterns.py`
Expected: `Ran 30 tests … OK`. Also `tests/run_headless.sh test_patterns.py` and `tests/run_widgets.sh` (common.py changed): OK.

- [ ] **Step 7: Commit**

```bash
git add InCad/incad/core/sketch_patterns.py InCad/incad/features/sketch_patterns.py InCad/incad/features/common.py InCad/incad/features/__init__.py tests/headless/test_sketch_patterns.py
git commit -m "Sketch patterns: Rectangular and Circular kinds (create/read/update on the sketch), rebuild on edit, broken-pattern repair, sketch pick kinds"
```

---

### Task 5: The session in sketch mode, the commands, the ribbon

**Files:**
- Modify: `InCad/incad/ui/feature_session.py` (IN_SKETCH path), `InCad/incad/ui/shell.py` (start in sketch, parent, stop tools), `InCad/incad/actions.py` (commands, SHORT), `InCad/incad/ui/ribbon_layout.py:35`
- Test: `tests/gui/test_sketch_patterns.py`

**Interfaces:**
- Consumes: Task 4 kinds (`IN_SKETCH`, `create(doc, body, sketch, values)`), `shell.instance().sketches.editing()` (the sketch in edit, or None), `shell.stop_slot_tool()`, `Gui.runCommand("Sketcher_StopOperation")`.
- Produces: commands `sketch.rect_pattern`, `sketch.circ_pattern` (contexts `{"sketch"}`, handlers `start_feature("sketch_rect")` / `("sketch_circ")`); `shell.start_feature(kind)` for `IN_SKETCH` kinds opens the session with `profile=<the sketch being edited>`.

- [ ] **Step 1: Write the failing GUI test**

```python
# tests/gui/test_sketch_patterns.py
"""The sketch's Pattern group: InCad's own Rectangular and Circular Pattern dialogs on sketch geometry, picks
made in the sketch, live copies, Cancel leaving the sketch as it was."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, prefs, sketch_patterns as sp  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def sk():
    return Gui.ActiveDocument.getInEdit().Object


def pick(key, sub):
    if dialog().active_pick() != key:
        dialog().field(key).click()
        harness.pump(400)
    assert dialog().active_pick() == key, dialog().active_pick()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, sub)
    harness.pump(900)


def test_0_sketch_with_a_hole_and_two_limits():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    s().plane_panel.button("XY_Plane").click()
    harness.pump(1200)
    k = sk()
    ST["hole"] = k.addGeometry(Part.Circle(App.Vector(6, 5, 0), App.Vector(0, 0, 1), 2))
    k.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, ST["hole"], 3, 6.0))
    k.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, ST["hole"], 3, 5.0))
    ST["left"] = k.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0)), True)
    ST["right"] = k.addGeometry(Part.LineSegment(App.Vector(40, 0, 0), App.Vector(40, 10, 0)), True)
    App.ActiveDocument.recompute()
    harness.pump(300)
    ST["geo"] = k.GeometryCount


def test_1_rectangular_pattern_from_the_ribbon_with_picks_in_the_sketch():
    Gui.Selection.clearSelection()
    res = commands.REGISTRY.run("sketch.rect_pattern")
    harness.pump(1200)
    assert res.ok, res.error
    assert dialog() is not None and dialog().windowTitle() in ("", "Rectangular Pattern")
    assert dialog().values()["geometry"] == "", dialog().values()
    assert "Click the geometry to repeat" in dialog().error_text(), dialog().error_text()
    assert not dialog().ok_button.isEnabled()
    pick("geometry", "Edge%d" % (ST["hole"] + 1))
    w = dialog().field("count1")
    w.setText("3")
    w.editingFinished.emit()
    harness.pump(900)
    assert not dialog().error_text(), dialog().error_text()
    assert sk().GeometryCount == ST["geo"] + 2, sk().GeometryCount  # the preview is real geometry
    assert Gui.ActiveDocument.getInEdit() is not None, "the sketch stays open under the dialog"
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert dialog() is None
    assert len(sp.records(sk())) == 1
    ST["pattern"] = sp.records(sk())[0]["name"]
    assert sk().GeometryCount == ST["geo"] + 2


def test_2_cancel_leaves_the_sketch_as_it_was():
    before = sk().GeometryCount
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge%d" % (ST["hole"] + 1))
    commands.REGISTRY.run("sketch.circ_pattern")
    harness.pump(1200)
    assert dialog().values()["geometry"].endswith("Edge%d" % (ST["hole"] + 1)), "the selection is seeded"
    assert not dialog().error_text(), dialog().error_text()
    assert sk().GeometryCount > before
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert sk().GeometryCount == before, (sk().GeometryCount, before)
    assert len(sp.records(sk())) == 1


def test_3_equal_spacing_between_the_two_lines():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("sketch.rect_pattern")
    harness.pump(1000)
    pick("geometry", "Edge%d" % (ST["hole"] + 1))
    dialog().set_values({"fit1": "faces", "count1": "3"})
    harness.pump(500)
    assert dialog().field("from1").isVisible() and not dialog().field("dir1").isVisible()
    pick("from1", "Edge%d" % (ST["left"] + 1))
    pick("to1", "Edge%d" % (ST["right"] + 1))
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    rec = sp.records(sk())[-1]
    last = sp.index_of(sk(), rec["copies"][-1][0])
    assert abs(sp.point_of(sk(), last, 3).x - 34.0) < 1e-3, sp.point_of(sk(), last, 3)


def test_4_the_ribbon_has_both_next_to_mirror():
    rb = s().ribbon
    for cid in ("sketch.rect_pattern", "sketch.circ_pattern", "sketch.mirror"):
        assert rb.button(cid) is not None, cid


harness.run([test_0_sketch_with_a_hole_and_two_limits, test_1_rectangular_pattern_from_the_ribbon_with_picks_in_the_sketch,
             test_2_cancel_leaves_the_sketch_as_it_was, test_3_equal_spacing_between_the_two_lines,
             test_4_the_ribbon_has_both_next_to_mirror])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `tests/run_gui.sh tests/gui/test_sketch_patterns.py`
Expected: `test_1` FAIL (`res.ok` false: unknown command, or the FreeCAD RectangularArray tool opens and no dialog exists).

- [ ] **Step 3: Commands and ribbon**

In `InCad/incad/actions.py` remove the two pass-through rows (`"sketch.mirror"` stays):

```python
    "sketch.rect_pattern": ("Rectangular Pattern", "rect_pattern", "Sketcher_RectangularArray", ""),
```

and add to `commands()` next to the feature patterns:

```python
        Command(id="sketch.rect_pattern", label="Rectangular", icon="rect_pattern",
                handler=lambda: start_feature("sketch_rect"), contexts=frozenset({"sketch"}),
                tooltip="Repeat sketch geometry along a direction, or equally between two limits"),
        Command(id="sketch.circ_pattern", label="Circular", icon="circ_pattern",
                handler=lambda: start_feature("sketch_circ"), contexts=frozenset({"sketch"}),
                tooltip="Repeat sketch geometry around a point"),
```

In `SHORT` add `"sketch.circ_pattern": "Pattern"` (keep `"sketch.rect_pattern": "Pattern"`). In `InCad/incad/ui/ribbon_layout.py` line 35:

```python
                    ["Pattern", ["sketch.rect_pattern", "sketch.circ_pattern", "sketch.mirror"]],
```

- [ ] **Step 4: The shell starts an in-sketch kind on the sketch being edited**

In `shell.py` `start_feature(kind)`, after the assembly branch and the InCad-part check, before `if self.feature_session is not None`:

```python
        if getattr(kind, "IN_SKETCH", False):
            editing = self.sketches.editing()
            if editing is None:
                raise ValueError("Open a sketch first")
            if self.feature_session is not None:
                raise self._dialog_first()
            self.stop_slot_tool()
            import FreeCADGui as Gui
            Gui.runCommand("Sketcher_StopOperation")  # no Sketcher tool fighting for the clicks
            self._open_session(kind, doc, document.primary_body(doc), profile=editing)
            return
```

Finish Sketch is `actions.finish_sketch()` → `shell.sketch_session().finish()` (`InCad/incad/ui/sketch_session.py:189`); the shell also calls `self.sketches.finish()` at `shell.py:1395` and `shell.py:2256`. Add at the top of `SketchSession.finish()` (the one place all three go through), before `gdoc.resetEdit()`:

```python
        from incad.ui import shell as shells
        sh = shells.instance()
        fs = sh.feature_session if sh is not None else None
        if fs is not None and getattr(fs.kind, "IN_SKETCH", False):
            fs.cancel()  # the pattern dialog cannot outlive its sketch
```

- [ ] **Step 5: The session's IN_SKETCH path**

In `feature_session.py`:

1. `start()`: when `getattr(self.kind, "IN_SKETCH", False)` the "feature" is the profile (the sketch) from the beginning, so `read`/`update` have it, but it is only *created* at the first preview:

```python
        in_sketch = getattr(self.kind, "IN_SKETCH", False)
        if in_sketch and self.creating:
            self.feature = None  # create() runs at the first preview with the picks; the sketch is self.profile
```

(nothing else changes in `start`: `NEEDS_PROFILE=False` already skips the create at start; `_preview_now` creates on the first preview, `self.feature = self.kind.create(...)` returns the sketch.)

2. `_expected_base()`: return `None` for in-sketch kinds (no "on the current shape" check, no base to show):

```python
        if getattr(self.kind, "IN_SKETCH", False):
            return None
```

3. `_sync_pick_view()`: the first line becomes

```python
        if getattr(self.kind, "IN_SKETCH", False):
            if seed and key:
                self._seed_selection(key)
            return
```

4. `_show_base_while_broken()` and `_fill_empty_picks()`: return at once for in-sketch kinds (`if getattr(self.kind, "IN_SKETCH", False): return`).

5. `_selection()`: a pick on the sketch being edited is `(sketch, "Edge3")`; `common.resolve` leaves it alone. The line `obj is not self.feature` would drop every pick once the sketch IS the feature: change it to

```python
                if obj is not None and (obj is not self.feature or getattr(self.kind, "IN_SKETCH", False)):
```

6. `_label_params()`: already calls `kind.param_names(self.feature)`; for in-sketch kinds pass the sketch even while creating: `target = self.feature if self.feature is not None else (self.profile if getattr(self.kind, "IN_SKETCH", False) else None)` and call `param_names(target)` when `target` is not None.

7. `_finish()`: in-sketch kinds leave `InCadEditing` behind: after the commit/abort add

```python
        if getattr(self.kind, "IN_SKETCH", False) and self.profile is not None and _feature_alive(self.profile):
            try:
                self.profile.InCadEditing = ""
            except Exception:
                pass
```

(On abort FreeCAD restores the property itself; clearing it again is harmless.)

- [ ] **Step 6: Run the GUI test and the pattern GUI tests**

Run: `tests/run_gui.sh tests/gui/test_sketch_patterns.py tests/gui/test_pattern_pick.py tests/gui/test_features2.py`
Expected: all PASS. If `test_1` finds `GeometryCount` unchanged after the count edit, the preview did not run: check that the dialog's `changed` fires on `editingFinished` and that `create()` was called with `profile` = the sketch (log `InCad.log` shows "Rectangular Pattern preview: …" on failures).

- [ ] **Step 7: Commit**

```bash
git add InCad/incad/ui/feature_session.py InCad/incad/ui/shell.py InCad/incad/actions.py InCad/incad/ui/ribbon_layout.py tests/gui/test_sketch_patterns.py
git commit -m "Sketch patterns: the feature session runs in a sketch (picks on the sketch, no base, preview as real geometry); Rectangular/Circular Pattern on the sketch ribbon"
```

---

### Task 6: Edit Pattern, Delete Pattern, double-click, marking menu

**Files:**
- Modify: `InCad/incad/ui/shell.py` (`_dblclick_hook`, `edit_sketch_pattern`, `delete_sketch_pattern`), `InCad/incad/actions.py` (commands), `InCad/incad/ui/marking_layout.py` (sketch list)
- Test: `tests/gui/test_sketch_patterns.py`

**Interfaces:**
- Consumes: `sp.pattern_of(sk, index)`, `sp.is_copy`, `sp.find`, `sp.remove`, `sp.is_broken`, the kinds' `read` through `InCadEditing`.
- Produces: `shell.edit_sketch_pattern(sk, name)` opens the right kind with `feature=sk` (an edit session: `read` → dialog → `update`); `shell.delete_sketch_pattern(sk, name)` (one undo step via `safe.run_safely`); commands `sketch.edit_pattern`, `sketch.delete_pattern` (contexts `{"sketch"}`, enabled when the selection holds a pattern's geometry) in the sketch marking-menu list.

- [ ] **Step 1: Write the failing GUI tests** (append to `tests/gui/test_sketch_patterns.py`, before `harness.run`, and add them to the run list)

```python
def test_5_double_click_on_a_copy_opens_edit_pattern_and_count_changes():
    k = sk()
    rec = sp.find(k, ST["pattern"])
    copy = sp.index_of(k, rec["copies"][0][0])
    Gui.Selection.clearSelection()
    # a double-click in the view lands on a preselected element: emulate FreeCAD's preselection, then the hook
    Gui.Selection.setPreselection(k, "Edge%d" % (copy + 1))  # setPreselection(obj, subName, x=0, y=0, z=0, type=1)
    harness.pump(200)
    view = Gui.ActiveDocument.ActiveView
    handled = s()._dblclick_hook(view, None, 10, 10)
    harness.pump(1200)
    assert handled, "the double-click on a copy is taken"
    assert dialog() is not None and dialog().values()["count1"] == "3", dialog().values()
    w = dialog().field("count1")
    w.setText("5")
    w.editingFinished.emit()
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert len(sp.find(k, ST["pattern"])["copies"]) == 4


def test_6_delete_pattern_leaves_the_original():
    k = sk()
    rec = sp.find(k, ST["pattern"])
    copy = sp.index_of(k, rec["copies"][0][0])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, k.Name, "Edge%d" % (copy + 1))
    harness.pump(300)
    res = commands.REGISTRY.run("sketch.delete_pattern")
    harness.pump(800)
    assert res.ok, res.error
    assert sp.find(k, ST["pattern"]) is None
    assert k.getGeometryId(ST["hole"]) is not None and k.Geometry[ST["hole"]].TypeId == "Part::GeomCircle"
    App.ActiveDocument.undo()
    harness.pump(500)
    assert sp.find(k, ST["pattern"]) is not None, "Delete Pattern is one undo step"
    App.ActiveDocument.redo()
    harness.pump(500)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `tests/run_gui.sh tests/gui/test_sketch_patterns.py`
Expected: `test_5` FAIL (`handled` false), `test_6` FAIL (unknown command).

- [ ] **Step 3: Shell: edit, delete, double-click**

In `shell.py`, next to `edit_feature`:

```python
    def edit_sketch_pattern(self, sk, name):
        from incad.features import sketch_patterns as kinds
        from incad.core import sketch_patterns as sp
        rec = sp.find(sk, name)
        if rec is None:
            raise ValueError("No pattern named %s in %s" % (name, sk.Label))
        if self.feature_session is not None:
            raise self._dialog_first()
        kind = kinds.SKETCH_RECT if rec["kind"] == "rect" else kinds.SKETCH_CIRC
        kinds._set_editing(sk, name)
        if sp.is_broken(sk, name):
            log.report("warning", "Some copies of %s were deleted; the pattern will be rebuilt" % name)
        self.stop_slot_tool()
        import FreeCADGui as Gui
        Gui.runCommand("Sketcher_StopOperation")
        self._open_session(kind, sk.Document, document.primary_body(sk.Document), profile=sk, feature=sk)

    def delete_sketch_pattern(self, sk, name):
        from incad.core import safe, sketch_patterns as sp
        if self.feature_session is not None:
            raise self._dialog_first()
        r = safe.run_safely("Delete Pattern", lambda: sp.remove(sk.Document, sk, name), sk.Document)
        if not r.ok:
            raise ValueError(r.error)
        sk.Document.recompute()
        self.schedule_refresh()

    def selected_sketch_pattern(self):
        """(sketch, pattern name) of the pattern whose geometry is selected in the sketch being edited."""
        import FreeCADGui as Gui
        from incad.core import sketch_patterns as sp
        sk = self.sketches.editing()
        if sk is None:
            return None, None
        for sel in Gui.Selection.getSelectionEx(sk.Document.Name):
            if sel.Object is not sk:
                continue
            for sub in sel.SubElementNames or ():
                try:
                    geo, _ = sp.element(sk, sub)
                except ValueError:
                    continue
                if geo >= 0:
                    name = sp.pattern_of(sk, geo)
                    if name:
                        return sk, name
        return None, None
```

`_dblclick_hook` takes a copy first (a pattern's original keeps its usual double-click meaning):

```python
    def _dblclick_hook(self, view, viewport, x, y):
        if self.sketches.editing() is None:
            return False
        sk, name = self._preselected_pattern_copy()
        if name is not None:
            try:
                self.edit_sketch_pattern(sk, name)
            except ValueError as e:
                log.report("warning", str(e))
            return True
        sk, name = self._preselected_dimension()
        ...  # unchanged below

    @staticmethod
    def _preselected_pattern_copy():
        import FreeCADGui as Gui
        from incad.core import sketch_patterns as sp
        try:
            pre = Gui.Selection.getPreselection()
            obj = getattr(pre, "Object", None)
            subs = getattr(pre, "SubElementNames", ()) or ()
            if obj is None or obj.TypeId != "Sketcher::SketchObject":
                return None, None
        except RuntimeError:
            return None, None
        for sub in subs:
            try:
                geo, _ = sp.element(obj, sub)
            except ValueError:
                continue
            if geo >= 0 and sp.is_copy(obj, geo):
                return obj, sp.pattern_of(obj, geo)
        return None, None
```

In `FeatureSession.start()` an edit of an in-sketch kind must not `_join_documents`/`read` before `InCadEditing` is set: the shell sets it first (above), so `read` works; nothing to change.

- [ ] **Step 4: Commands and marking menu**

In `actions.py`:

```python
def _edit_sketch_pattern():
    from incad.ui import shell
    sk, name = shell.instance().selected_sketch_pattern()
    if name is None:
        raise ValueError("Select a copy of a pattern first")
    shell.instance().edit_sketch_pattern(sk, name)


def _delete_sketch_pattern():
    from incad.ui import shell
    sk, name = shell.instance().selected_sketch_pattern()
    if name is None:
        raise ValueError("Select a copy of a pattern first")
    shell.instance().delete_sketch_pattern(sk, name)
```

and in `commands()`:

```python
        Command(id="sketch.edit_pattern", label="Edit Pattern", icon="rect_pattern", handler=_edit_sketch_pattern,
                contexts=frozenset({"sketch"}), tooltip="Change the selected pattern (or double-click a copy)"),
        Command(id="sketch.delete_pattern", label="Delete Pattern", icon="delete", handler=_delete_sketch_pattern,
                contexts=frozenset({"sketch"}), tooltip="Remove the copies; the original stays"),
```

In `marking_layout.py` the sketch list gains both: `"list": ["sketch.stop", "edit.delete", "sketch.constraints_toggle", "view.look_at", "sketch.construction", "sketch.project", "sketch.edit_pattern", "sketch.delete_pattern"]`.

- [ ] **Step 5: Run the GUI test**

Run: `tests/run_gui.sh tests/gui/test_sketch_patterns.py`
Expected: 7 passed (`setPreselection(obj, subName, x=0, y=0, z=0, type=1)` is in this build's `libFreeCADGui.dylib`).

- [ ] **Step 6: Commit**

```bash
git add InCad/incad/ui/shell.py InCad/incad/actions.py InCad/incad/ui/marking_layout.py tests/gui/test_sketch_patterns.py
git commit -m "Sketch patterns: Edit Pattern (double-click a copy, marking menu) rebuilds; Delete Pattern keeps the original"
```

---

### Task 7: The real part: holes patterned in a sketch, cut by Extrude

**Files:**
- Modify: `tests/gui/test_pattern_real_part.py` (two tests appended)

**Interfaces:**
- Consumes: everything above; `commands.REGISTRY.run("sketch.start")`, `shell.sketches.start_on(face)` or the plane panel; `feature.extrude` dialog with `operation` "cut".

- [ ] **Step 1: Append the tests** (the file's `test_0` opens a copy of the user's part; these run after `test_3`, on the part with no pattern)

```python
def top_face(shape_obj):
    return "Face%d" % ([i + 1 for i, f in enumerate(shape_obj.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"
                        and abs(f.CenterOfMass.z - 10) < 0.05 and f.Area > 100][0])


def test_4_a_hole_sketched_on_the_top_is_patterned_four_times_in_the_sketch():
    import Part
    import Sketcher
    from incad.core import sketch_patterns as sp
    base = doc().getObject(ST["base"])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, base.Name, top_face(base))
    commands.REGISTRY.run("sketch.start")
    harness.pump(1500)
    sk = Gui.ActiveDocument.getInEdit().Object
    hole = sk.addGeometry(Part.Circle(App.Vector(-9, 3, 0), App.Vector(0, 0, 1), 1.0))  # near the left end
    sk.addConstraint(Sketcher.Constraint("Radius", hole, 1.0))
    doc().recompute()
    harness.pump(300)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name, "Edge%d" % (hole + 1))
    commands.REGISTRY.run("sketch.rect_pattern")
    harness.pump(1200)
    assert dialog() is not None and dialog().values()["geometry"].endswith("Edge%d" % (hole + 1)), dialog().values()
    dialog().set_values({"count1": "4", "spacing1": "6 mm"})
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    assert len(sp.records(sk)) == 1 and len(sp.records(sk)[0]["copies"]) == 3
    ST["sketch"], ST["hole"] = sk.Name, hole


def test_5_edit_to_five_then_cut_gives_five_holes_in_the_solid():
    from incad.core import sketch_patterns as sp
    sk = doc().getObject(ST["sketch"])
    name = sp.records(sk)[0]["name"]
    shell.instance().edit_sketch_pattern(sk, name)
    harness.pump(1200)
    w = dialog().field("count1")
    w.setText("5")
    w.editingFinished.emit()
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    assert len(sp.find(sk, name)["copies"]) == 4
    commands.REGISTRY.run("sketch.finish")
    harness.pump(1000)
    before = tip().Shape.Volume
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(1500)
    dialog().set_values({"operation": "cut", "extent": "through_all"})  # incad/features/extrude.py FIELDS
    harness.pump(1500)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    cut = tip()
    assert cut.TypeId == "PartDesign::Pocket", cut.TypeId
    assert "Invalid" not in cut.State, cut.getStatusString()
    removed = before - cut.Shape.Volume
    import math
    assert abs(removed - 5 * math.pi * 1.0 ** 2 * 10) < 5.0, removed  # five Ø2 holes through 10 mm
```

Add both to `harness.run([...])`.

- [ ] **Step 2: Run it** (hands off the machine)

Run: `tests/run_gui.sh tests/gui/test_pattern_real_part.py`
Expected: 6 passed. A failure in `test_5` at the volume check with `removed` ≈ 4 holes means the fifth copy lies outside the block (the sketch's local x runs along the face: check the face's local axes with `sk.getGlobalPlacement()` and pick the spacing/direction so all five stay on the 30 mm block).

- [ ] **Step 3: Commit**

```bash
git add tests/gui/test_pattern_real_part.py
git commit -m "Real part: a hole sketched on the block is patterned 4x in the sketch, edited to 5, and cut: five holes in the solid"
```

---

### Task 8: Full run, memory, docs

**Files:**
- Modify: `CLAUDE.md` (one line under FreeCAD facts), `docs/superpowers/specs/2026-10-09-incad-sketch-patterns-design.md` (status line)

- [ ] **Step 1: Full suites once**

Run: `tests/run_fast.sh` then `tests/run_gui.sh tests/gui/test_sketch_patterns.py tests/gui/test_pattern_real_part.py tests/gui/test_sketch_tools.py tests/gui/test_features2.py tests/gui/test_pattern_pick.py`
Expected: `FAST SUITES PASSED`, every GUI file `0 failed`.

- [ ] **Step 2: Record the FreeCAD facts**

Add to `CLAUDE.md` under "FreeCAD facts":

```
- Sketcher facts: a constraint expression may use `InCadModel.dN` and driving constraints, never a reference
  constraint of the same sketch; `setGeometryId` ids survive deletions and reload; virtual space hides
  constraints, never geometry (sketch patterns: `incad.core.sketch_patterns`).
```

Add to the spec's header: `Status: implemented (phase 1: rectangular + circular); phase 2 (along path) open.`

- [ ] **Step 3: Commit and push**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-10-09-incad-sketch-patterns-design.md
git commit -m "Sketch patterns: phase 1 done; Sketcher facts recorded"
git push
```

---

## Phase 2 (Along path) — not in this plan

Written as its own plan when phase 1 has shipped: `sketch_path` pick kind (a curve or a chain of lines/arcs), stations by arc length, `Orientation` Identical/Follow path, translation ties on line segments and spoke ties on arc segments, exact placement only on splines/ellipses, and the "follows it when the pattern is edited, not live" hint.
