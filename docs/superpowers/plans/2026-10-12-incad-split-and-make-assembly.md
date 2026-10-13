# Split by Sketch and Make Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut a part along surfaces made from sketch lines (Split / Cut), and turn a part's separate pieces into an
assembly of part files that keep their history (Inventor's Make Components); Move Solid is dropped.

**Architecture:** First the useful work of branch `move-solid` (Boolean Keep tool, clearance labels, dialog fixes,
`detach_lump` fixes) is brought onto a new branch `make-assembly` cut from `main`, without Move Solid. Split is a
`PartDesign::FeaturePython` (proxy `SplitFeature`, like Hole ▸ Chamfer) that slices the shape before it with knife
faces extruded from the sketch's edges. Make Assembly saves one copy of the part file per piece, removes the other
pieces from each copy (`detach_lump` for separate pieces, the Split set to Cut for split pieces), then builds a stage-4
assembly that links every part where it was.

**Tech Stack:** FreeCAD 1.1.3 (PartDesign, Part, BOPTools.SplitAPI, Assembly), PySide6 via `incad.qt`, unittest.

**Spec:** `docs/superpowers/specs/2026-10-12-incad-make-assembly-design.md`

## Global Constraints

- Everything in the repo in English (code, comments, UI text); the user is answered in Russian.
- Tests: `tests/run_headless.sh <file pattern>`, `tests/run_widgets.sh <file pattern>`, `tests/run_gui.sh tests/gui/<file>`
  (tell the user to keep hands off the test window). Run only the files a task touches; full suites at most once, in
  Task 6. Never poll a running suite's log: wait for its notification.
- Branch `make-assembly` from `main` (Task 1). `move-solid` is not merged and stays as it is.
- Make Assembly needs at least two pieces; touching features that fused are one piece.
- Names: assembly `<Part>-Assembly`, pieces `<Part>-Solid1`, `-Solid2`, … largest first; files in the part's folder;
  an existing file is never overwritten.
- Each part file keeps its history and all model parameters; the original part file is not changed.
- Every new build: version bump + CHANGES.txt / CHANGES_ru.txt section (done in Task 6 only if a build is asked for).

## Review Focus

1. A sketch line that ends inside the part (does not cross it fully): FreeCAD's slice leaves the part whole → "The
   sketch does not cut the part", never a silent no-op. → Task 2 `test_a_line_ending_inside_refuses`.
2. A Cut whose kept point lands on the knife after a sketch edit: the nearest piece stays, never nothing. → Task 2
   `test_cut_follows_a_changed_sketch`.
3. A part whose primary Solid is not the largest piece (the block is Solid1): each copy's remaining Solid becomes its
   primary body, or the part opens empty. → Task 4 `test_each_copy_is_an_incad_part_with_its_piece_as_primary`.
4. A name typed twice in the dialog (two pieces, one file): refused before anything is written. → Task 4
   `test_duplicate_names_are_refused`.
5. Thread helpers (prep fills, chamfer grooves) on a piece: they travel with their owner, the copy has no feature in
   error. → Task 6 (Thread_1 check: Thread002 and its helpers stay in the main part).

---

## File structure

- `InCad/incad/features/split.py` (create) — the Split kind and its proxy `SplitFeature`.
- `InCad/incad/core/make_assembly.py` (create) — pieces, default names, `make(doc, names)`.
- `InCad/incad/ui/make_assembly_dialog.py` (create) — the names dialog; `InCad/incad/ui/piece_marker.py` (create) —
  a piece's edges drawn on the view (SoAnnotation) for row hover.
- `InCad/incad/core/assembly.py` (modify) — `place(doc, path, beside=True)`.
- `InCad/incad/features/__init__.py`, `features/common.py`, `ui/feature_session.py` (modify) — register split; pick
  kind `piece`; `PICKS_ON_SELF`; the kind hook `picking(feature, active)`.
- `InCad/incad/actions.py`, `ui/ribbon_layout.py`, `ui/marking_layout.py`, `tools/make_icons.py` (modify) — commands
  `feature.split`, `file.make_assembly`, icons `split`, `make_assembly`.
- Tests: `tests/headless/test_split.py`, `tests/headless/test_make_assembly.py`, `tests/gui/test_split.py`,
  `tests/gui/test_make_assembly.py`.

---

### Task 1: Bring the useful work of `move-solid` onto `make-assembly` (no Move Solid)

**Files:**
- Take from `move-solid`: `InCad/incad/features/combine.py`, `features/hole.py`, `features/thread.py`,
  `core/tree.py`, `core/model.py`, `core/document.py`, `ui/shell.py`, `ui/feature_dialog.py`,
  `ui/feature_session.py`, `features/common.py`; tests `tests/headless/test_combine.py`, `test_tree.py`,
  `test_document.py`, `test_model.py`, `tests/gui/test_open_units.py`, `tests/widgets/test_feature_dialog.py`.
- Modify after taking: `core/tree.py`, `features/common.py`, `ui/feature_session.py`, `tests/headless/test_combine.py`,
  `scripts/dist/CHANGES.txt`, `CHANGES_ru.txt`.

**Interfaces:**
- Produces: `combine.used_up_tools(f)`, `combine.used_up_names(doc)`, `document.lump_at(body, point)`,
  `document.detach_lump(feature)` (fixed), `common.Field.optional`, kind hook `pending(values) -> str`,
  `ChoiceField.PER_ROW = 4`.

- [ ] **Step 1: Branch and take the files**

```bash
git checkout main
git checkout -b make-assembly
git checkout move-solid -- InCad/incad/features/combine.py InCad/incad/features/hole.py InCad/incad/features/thread.py \
  InCad/incad/core/tree.py InCad/incad/core/model.py InCad/incad/core/document.py InCad/incad/ui/shell.py \
  InCad/incad/ui/feature_dialog.py InCad/incad/ui/feature_session.py InCad/incad/features/common.py \
  tests/headless/test_combine.py tests/headless/test_tree.py tests/headless/test_document.py \
  tests/headless/test_model.py tests/gui/test_open_units.py tests/widgets/test_feature_dialog.py
```

- [ ] **Step 2: Strip what only Move Solid used**

In `InCad/incad/core/tree.py` delete the block:

```python
    if kind == "feature" and getattr(obj, "TargetLost", False) and hasattr(obj, "InCadMove"):
        node.detail = "⚠ target lost"
        node.tooltip = "Follow target lost: the solid stays where it last was (edit the Move to pick a new target)"
```

In `InCad/incad/features/common.py` delete the `solid_element` branch of `accepts`:

```python
    if kind == "solid_element":  # a point, an edge or a face of the solid being moved (its shape before the move)
        return sub.startswith(("Face", "Edge", "Vertex")) and el is not None
```

and change the `optional` comment to `# pick fields: an empty one has a default: never made active by itself`.

In `InCad/incad/ui/feature_session.py`: remove `"solid_element"` from `_GEOMETRY`; delete the line
`self._pivot_marker = None  # Move Solid's pivot, on the view`, the call `self._sync_pivot_marker()` (two places: after
`self._check()` in `_preview_now` and in `start` after `_seen_waiting`), the whole method `_sync_pivot_marker`, and in
`_finish` the block

```python
        if self._pivot_marker is not None:
            self._pivot_marker.remove()
            self._pivot_marker = None
```

Reword two docstrings: `_activate_revealed_pick` → "A choice that brings pick fields into view (Extrude's To face)
makes the first of them the active pick…"; `ChoiceField` in `feature_dialog.py` → "Segment buttons, at most PER_ROW in
a row, so a long list of choices does not make the dialog too wide."

In `tests/headless/test_combine.py` delete the test that imports `incad.features.move`
(`test_moving_a_used_up_tool_moves_the_cut`).

- [ ] **Step 3: Check nothing still names Move**

Run: `grep -rn "move_math\|features import move\|features.move\|pivot_marker\|solid_element\|InCadMove" InCad tests`
Expected: no output.

- [ ] **Step 4: Release notes**

In `scripts/dist/CHANGES.txt` (section 0.1.2) delete the "New Move Solid …" paragraph (including the pivot sentence
added on 2026-10-12) and add under Improvements:

```
- Dialogs: long choice lists wrap four buttons per row; choosing an option that needs a pick starts that pick, and a
  click on the field the dialog already made active keeps picking (it no longer stops it).
```

and under Bug fixes:

```
- A box drawn away from the part and split off into its own Solid no longer takes along what was built on the part
  after it, and sketches left on the part stay attached.
```

In `CHANGES_ru.txt` the same: delete the Move Solid paragraph, add

```
- Окна: длинные списки вариантов переносятся по четыре кнопки в ряд; выбор варианта, которому нужен выбор на модели,
  сразу включает этот выбор, а клик по уже активному полю больше его не выключает.
```

```
- Отдельный кусок, вынесенный в свой Solid, больше не забирает с собой то, что построено на основной детали после
  него, а эскизы на основной детали остаются привязанными.
```

- [ ] **Step 5: Run the affected tests**

Run: `tests/run_headless.sh "test_combine.py"`, `tests/run_headless.sh "test_tree.py"`,
`tests/run_headless.sh "test_document.py"`, `tests/run_headless.sh "test_model.py"`,
`tests/run_widgets.sh test_feature_dialog.py`, `tests/run_gui.sh tests/gui/test_open_units.py tests/gui/test_features2.py tests/gui/test_revolve_axes.py`
Expected: all pass (`tests/gui/test_open_sketches.py` test 9 fails on `main` too — not this task's).

- [ ] **Step 6: Commit**

```bash
git add -A InCad tests scripts/dist
git commit -m "Bring Boolean Keep tool, clearance labels, dialog and split-off fixes from move-solid (without Move Solid)"
```

---

### Task 2: Split feature (model)

**Files:**
- Create: `InCad/incad/features/split.py`
- Modify: `InCad/incad/features/__init__.py` (add `split` to `kinds()` after `combine`)
- Test: `tests/headless/test_split.py`

**Interfaces:**
- Produces: `split.create(doc, body, profile, values) -> feature`, `split.update(doc, f, values)`,
  `split.read(doc, f) -> values`, `split.claims(f)`, `split.pieces(f) -> [Part.Solid]` (all pieces, largest first,
  before Cut), `split.keep_piece(f, point)` (switch to Cut keeping the piece nearest `point`), proxy class
  `SplitFeature` with properties `Sketch` (Link), `Mode` (String "split"/"cut"), `Keep` (VectorList), `ShowAll`
  (Bool, transient: True shows every piece while Keep is picked). Values keys: `sketch`, `mode`, `keep`.

- [ ] **Step 1: Write the failing tests**

```python
"""Split by sketch: sketch lines extruded into zero-thickness knives cut the part."""
import os
import tempfile
import unittest

import FreeCAD as App
import Part

from incad.core import document
from incad.features import split
from headless import util


def line_sketch(body, *segments, name="Knife"):
    """A sketch on XY with the given segments ((x1, y1), (x2, y2)); arcs as (centre, r, a0, a1)."""
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    for seg in segments:
        if len(seg) == 2:
            (x1, y1), (x2, y2) = seg
            sk.addGeometry(Part.LineSegment(App.Vector(x1, y1, 0), App.Vector(x2, y2, 0)))
        else:
            (cx, cy), r, a0, a1 = seg
            sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(cx, cy, 0), App.Vector(0, 0, 1), r), a0, a1))
    return sk


class SplitTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sp")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, sk, **kw):
        values = dict(split.defaults(self.doc, self.body, None), sketch=sk.Name)
        values.update(kw)
        f = split.create(self.doc, self.body, None, values)
        self.doc.recompute()
        return f

    def test_a_line_through_the_box_gives_two_pieces(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        vols = sorted(round(s.Volume, 6) for s in f.Shape.Solids)
        self.assertEqual(vols, [500.0, 1500.0])
        self.assertIs(self.body.Tip, f)
        self.assertNotIn("Invalid", f.State)

    def test_an_arc_cuts_a_curved_face(self):
        import math
        f = self.make(line_sketch(self.body, ((0, 5), 8, -math.pi / 2, math.pi / 2)))
        self.assertEqual(len(f.Shape.Solids), 2)
        self.assertTrue(any(face.Surface.TypeId == "Part::GeomCylinder" for face in f.Shape.Faces))
        self.assertAlmostEqual(sum(s.Volume for s in f.Shape.Solids), 2000, places=6)

    def test_two_lines_give_three_pieces(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15)), ((15, -5), (15, 15))))
        self.assertEqual(len(f.Shape.Solids), 3)

    def test_cut_keeps_the_picked_piece(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))), mode="cut", keep="2 1 5")
        self.assertEqual(len(f.Shape.Solids), 1)
        self.assertAlmostEqual(f.Shape.Volume, 500, places=6)

    def test_cut_follows_a_changed_sketch(self):
        sk = line_sketch(self.body, ((5, -5), (5, 15)))
        f = self.make(sk, mode="cut", keep="4.9 1 5")  # near the knife
        sk.movePoint(0, 1, App.Vector(4, -5, 0))
        sk.movePoint(0, 2, App.Vector(4, 15, 0))
        self.doc.recompute()
        self.assertEqual(len(f.Shape.Solids), 1)
        self.assertAlmostEqual(f.Shape.Volume, 400, places=6)

    def test_a_sketch_missing_the_part_refuses(self):
        with self.assertRaises(ValueError) as ctx:
            self.make(line_sketch(self.body, ((50, -5), (50, 15))))
        self.assertIn("does not cut", str(ctx.exception))
        self.assertIs(self.body.Tip, self.pad)

    def test_a_line_ending_inside_refuses(self):
        with self.assertRaises(ValueError):
            self.make(line_sketch(self.body, ((5, -5), (5, 5))))  # stops in the middle

    def test_keep_piece_switches_to_cut(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        split.keep_piece(f, App.Vector(15, 5, 5))
        self.doc.recompute()
        self.assertEqual(f.Mode, "cut")
        self.assertAlmostEqual(f.Shape.Volume, 1500, places=6)

    def test_save_and_reopen(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        path = os.path.join(tempfile.mkdtemp(), "split.FCStd")
        self.doc.saveAs(path)
        name = f.Name
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        g = self.doc.getObject(name)
        g.touch()
        self.doc.recompute()
        self.assertEqual(len(g.Shape.Solids), 2)
        self.assertTrue(split.claims(g))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail**

Run: `tests/run_headless.sh "test_split.py"`
Expected: ERROR `ImportError: cannot import name 'split'`.

- [ ] **Step 3: Write the kind**

```python
"""Split by sketch: each line of a sketch (segment, arc, spline) is extruded along the sketch's normal, both ways,
through the whole part into a surface of zero thickness; these knives divide the shape before this step. Split keeps
every piece (they touch but are separate solids: Make Assembly makes a part of each); Cut keeps the pieces at the
stored points (a spot picked on each), the nearest piece to each point on every recompute."""
import json

import FreeCAD as App

from incad.features.common import Field, parse_picks

TITLE = "Split"
ICON = "split"
TYPES = ("PartDesign::FeaturePython",)
NEEDS_PROFILE = False
STRUCTURAL = ()
PICKS_ON_SELF = ("keep",)
_STORE = "InCadSplit"

FIELDS = (
    Field("sketch", "Sketch", "pick", pick="sketch"),
    Field("mode", "Mode", "choice", (("split", "Split"), ("cut", "Cut")), "split"),
    Field("keep", "Keep", "picks", pick="piece", show_if=("mode", ("cut",))),
)


def _knives(sk, body, bb):
    """The knife faces in the body's frame: every edge of the sketch swept along its normal past the part."""
    pl = sk.getGlobalPlacement()
    if body is not None:
        pl = body.getGlobalPlacement().inverse().multiply(pl)
    n = pl.Rotation.multVec(App.Vector(0, 0, 1))
    reach = bb.DiagonalLength + (pl.Base - bb.Center).Length + 10.0
    faces = []
    for e in sk.Shape.Edges:  # sk.Shape is already placed (body frame); pl only gives the normal
        edge = e.copy()
        edge.translate(n * -reach)
        faces.append(edge.extrude(n * (2 * reach)))
    return faces


def _slice(base, knives):
    from BOPTools import SplitAPI
    out = SplitAPI.slice(base, knives, "Split")
    return sorted(out.Solids, key=lambda s: -s.Volume)


class SplitFeature:
    """The proxy. FreeCAD saves its module path (incad.features.split) and class name in the file."""
    def __init__(self, obj):
        for prop, kind in (("Sketch", "App::PropertyLink"), ("Mode", "App::PropertyString"),
                           ("Keep", "App::PropertyVectorList"), ("ShowAll", "App::PropertyBool")):
            if prop not in obj.PropertiesList:
                obj.addProperty(kind, prop, "Split", "")
        obj.setPropertyStatus("ShowAll", ["Hidden", "Transient"])
        obj.Proxy = self

    def execute(self, obj):
        base = obj.BaseFeature
        if base is None or base.Shape.isNull() or obj.Sketch is None:
            return
        before = len(base.Shape.Solids)
        pieces = _slice(base.Shape, _knives(obj.Sketch, obj.getParentGeoFeatureGroup(), base.Shape.BoundBox))
        if len(pieces) <= before:
            raise ValueError("The sketch does not cut the part")
        import Part
        if obj.Mode == "cut" and obj.Keep and not obj.ShowAll:
            kept = []
            for p in obj.Keep:
                probe = Part.Vertex(p)
                best = min(pieces, key=lambda s: s.distToShape(probe)[0])
                if best not in kept:
                    kept.append(best)
            pieces = kept
        obj.Shape = pieces[0] if len(pieces) == 1 else Part.makeCompound(pieces)

    def dumps(self):
        return None

    def loads(self, state):
        return None


def claims(feature):
    return hasattr(feature, _STORE)


def defaults(doc, body, profile=None):
    values = {f.key: f.default for f in FIELDS}
    values.update(sketch=profile.Name if profile is not None else "", keep="")
    return values


def _points(doc, text):
    """Keep: picks on the Split's own pieces ('Split:Face7') or plain 'x y z' triples; each becomes a point."""
    out = []
    for part in [p for p in (text or "").split(",") if p.strip()]:
        nums = part.split()
        if len(nums) == 3:
            try:
                out.append(App.Vector(*[float(v) for v in nums]))
                continue
            except ValueError:
                pass
        for obj, sub in parse_picks(doc, part):
            if sub:
                out.append(obj.Shape.getElement(sub).CenterOfMass)
    return out


def _store(f, data):
    if not hasattr(f, _STORE):
        f.addProperty("App::PropertyString", _STORE, "InCad", "InCad split settings")
        f.setPropertyStatus(_STORE, "Hidden")
    setattr(f, _STORE, json.dumps(data, sort_keys=True))


def _load(f):
    try:
        return json.loads(getattr(f, _STORE, "") or "{}")
    except ValueError:
        return {}


def _build(doc, f, values):
    sk = doc.getObject((values.get("sketch") or "").split(":")[0])
    if sk is None or sk.TypeId != "Sketcher::SketchObject":
        raise ValueError("Pick the sketch whose lines cut the part")
    if not sk.Shape.Edges:
        raise ValueError("The sketch has no lines")
    f.Sketch = sk
    f.Mode = values.get("mode") or "split"
    f.Keep = _points(doc, values.get("keep")) if f.Mode == "cut" else []
    _store(f, {"sketch": sk.Name, "mode": f.Mode})
    return f


def create(doc, body, profile, values):
    tip = body.Tip
    f = body.newObject("PartDesign::FeaturePython", "Split")
    SplitFeature(f)
    f.BaseFeature = tip
    try:
        _build(doc, f, values)
        body.Tip = f
        sk = f.Sketch
        doc.recompute()
        if "Invalid" in f.State:
            raise ValueError(f.getStatusString() or "The sketch does not cut the part")
        sk.Visibility = False
    except Exception:
        body.removeObject(f)
        doc.removeObject(f.Name)
        body.Tip = tip
        doc.recompute()
        raise
    return f


def read(doc, f):
    data = _load(f)
    values = defaults(doc, f.getParentGeoFeatureGroup(), None)
    values.update(sketch=data.get("sketch", getattr(f.Sketch, "Name", "")), mode=data.get("mode", "split"),
                  keep=", ".join("%g %g %g" % (p.x, p.y, p.z) for p in f.Keep))
    return values


def update(doc, f, values):
    _build(doc, f, values)
    doc.recompute()
    if "Invalid" in f.State:
        raise ValueError(f.getStatusString() or "The sketch does not cut the part")
    return f


def pieces(f):
    base = f.BaseFeature
    return _slice(base.Shape, _knives(f.Sketch, f.getParentGeoFeatureGroup(), base.Shape.BoundBox))


def keep_piece(f, point):
    f.Mode = "cut"
    f.Keep = [point]
    data = _load(f)
    data["mode"] = "cut"
    _store(f, data)
    f.touch()


def picking(f, active):
    """While Keep is picked every piece shows (a removed one can be picked back)."""
    if f.ShowAll != active:
        f.ShowAll = active
        f.touch()


def param_names(f):
    return {}
```

Note for the implementer: probe once in freecadcmd that `SplitAPI.slice(box, [face], "Split").Solids` gives two solids for a plane through a box
before relying on it; if `"Split"` returns one compsolid, use `"CompSolid"` and take `.Solids`.

- [ ] **Step 4: Register and run**

In `InCad/incad/features/__init__.py` import `split` and put it after `combine` in the list.
Run: `tests/run_headless.sh "test_split.py"`
Expected: 9 tests OK.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features/split.py InCad/incad/features/__init__.py tests/headless/test_split.py
git commit -m "Split by sketch: sketch lines become zero-thickness knives; Split keeps every piece, Cut the picked ones"
```

---

### Task 3: Split in the window (command, icon, picks on its own pieces)

**Files:**
- Modify: `InCad/incad/actions.py`, `ui/ribbon_layout.py`, `tools/make_icons.py`, `features/common.py`,
  `ui/feature_session.py`, `tests/widgets/test_actions.py`
- Test: `tests/gui/test_split.py`

**Interfaces:**
- Consumes: `split.PICKS_ON_SELF`, `split.picking(f, active)` (Task 2).
- Produces: command `feature.split`; pick kind `piece` (`common.accepts("piece", obj, sub)` is True for a `Face`);
  the session lets a kind with `PICKS_ON_SELF` take picks on its own feature for those fields and calls
  `kind.picking(feature, active)` when such a field becomes active / inactive.

- [ ] **Step 1: Write the failing GUI test**

```python
"""Split in a real window: pick the sketch, Split shows two pieces; Cut keeps the piece clicked."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
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


def test_0_box_and_a_knife():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    part = document.primary_body(doc())
    box = part.newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 20, 10, 10
    part.Tip = box
    sk = part.newObject("Sketcher::SketchObject", "Knife")
    sk.AttachmentSupport = [([o for o in part.Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(App.Vector(5, -5, 0), App.Vector(5, 15, 0)))
    doc().recompute()
    harness.pump(400)
    ST.update(part=part.Name, sk=sk.Name)


def test_1_split_then_cut_by_a_click():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, ST["sk"])
    commands.REGISTRY.run("feature.split")
    harness.pump(1500)
    assert dialog() is not None and dialog().values()["sketch"].startswith(ST["sk"]), dialog() and dialog().values()
    fs = shell.instance().feature_session
    assert len(fs.feature.Shape.Solids) == 2, fs.feature.Shape.Solids
    dialog().field("mode").button("cut").click()
    harness.pump(800)
    assert dialog().active_pick() == "keep", dialog().active_pick()
    big = max(fs.feature.Shape.Solids, key=lambda s: s.Volume)
    face = next(i + 1 for i, f in enumerate(fs.feature.Shape.Faces) if big.isInside(f.CenterOfMass, 1e-6, True)
                and f.CenterOfMass.x > 12)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, fs.feature.Name, "Face%d" % face)
    harness.pump(1200)
    assert dialog().values()["keep"], (dialog().values(), dialog().error_text())
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    tip = doc().getObject(ST["part"]).Tip
    assert abs(tip.Shape.Volume - 1500) < 1e-6, tip.Shape.Volume
    assert doc().UndoNames[0] == "Split", doc().UndoNames


harness.run([test_0_box_and_a_knife, test_1_split_then_cut_by_a_click])
```

- [ ] **Step 2: Run it to see it fail**

Run: `tests/run_gui.sh tests/gui/test_split.py` (tell the user to keep hands off)
Expected: FAIL in test_1 — command `feature.split` not found.

- [ ] **Step 3: Command, icon, ribbon**

In `InCad/incad/actions.py` next to `feature.combine`:

```python
        Command(id="feature.split", label="Split", icon="split", handler=lambda: start_feature("split"),
                contexts=frozenset({"part"}),
                tooltip="Cut the part along a sketch's lines (made into thin surfaces): keep every piece, or the ones you click"),
```

In `ui/ribbon_layout.py` the Modify group becomes
`"feature.thread", "feature.threads_toggle", "feature.combine", "feature.split"]]`.
In `tests/widgets/test_actions.py` add `"feature.split"` to the expected ids.
In `tools/make_icons.py` add to `ICONS`:

```python
    'split': '<rect x="4" y="8" width="24" height="16" fill="{F}" stroke="{S}" stroke-width="1.6"/><path d="M14 4 C18 12 12 20 16 28" stroke="{A}" stroke-width="2.2" fill="none"/>',
```

Run: `/Applications/FreeCAD.app/Contents/Resources/bin/python tools/make_icons.py`
Expected: `wrote N icons per theme`.

- [ ] **Step 4: Pick kind `piece`, picks on the feature itself, the picking hook**

In `features/common.py` `accepts(kind, obj, sub)` add before the final return:

```python
    if kind == "piece":  # a face of one of the feature's own pieces (Split ▸ Cut ▸ Keep)
        return sub.startswith("Face")
```

In `ui/feature_session.py` `_selection` change the condition

```python
                if obj is not None and (obj is not self.feature or getattr(self.kind, "IN_SKETCH", False)):
```

to

```python
                own = self.dialog is not None and self.dialog.active_pick() in getattr(self.kind, "PICKS_ON_SELF", ())
                if obj is not None and (obj is not self.feature or own or getattr(self.kind, "IN_SKETCH", False)):
```

and at the end of `_sync_pick_view` add:

```python
        hook = getattr(self.kind, "picking", None)
        if hook is not None and self.feature is not None and _feature_alive(self.feature):
            active = bool(key) and key in getattr(self.kind, "PICKS_ON_SELF", ())
            hook(self.feature, active)
            self.doc.recompute()
```

- [ ] **Step 5: Run the affected tests**

Run: `tests/run_widgets.sh test_actions.py`, `tests/run_widgets.sh test_ribbon.py`,
`tests/run_gui.sh tests/gui/test_split.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add InCad/incad/actions.py InCad/incad/ui/ribbon_layout.py tools/make_icons.py InCad/incad/resources/icons \
  InCad/incad/features/common.py InCad/incad/ui/feature_session.py tests/widgets/test_actions.py tests/gui/test_split.py
git commit -m "Split in the ribbon: pick a sketch; Cut keeps the pieces clicked on the preview"
```

---

### Task 4: Make Assembly (model)

**Files:**
- Create: `InCad/incad/core/make_assembly.py`
- Modify: `InCad/incad/core/assembly.py` (`place(doc, path, beside=True)`)
- Test: `tests/headless/test_make_assembly.py`

**Interfaces:**
- Consumes: `document.lump_at`, `document.detach_lump`, `document.is_detached_lump`, `document.bodies`,
  `document.primary_body`, `document._meta_set`, `document.PRIMARY_KEY`, `split.claims`, `split.keep_piece`,
  `assembly.make_assembly`, `assembly.place`.
- Produces: `Piece` namedtuple `(body_name, point, volume)`; `pieces(doc) -> [Piece]` largest first;
  `default_names(doc, n) -> (assembly_name, [part names])`; `check_names(doc, asm_name, names) -> str` ("" = ok);
  `make(doc, asm_name, names) -> assembly path`.

- [ ] **Step 1: Write the failing tests**

```python
"""Make Assembly: a part's separate pieces become part files with their history, linked by an assembly."""
import os
import tempfile
import unittest

import FreeCAD as App
import Part

from incad.core import assembly, document, make_assembly as ma
from headless import util


def _close_all():
    for name in list(App.listDocuments()):
        App.closeDocument(name)


class MakeAssemblyTest(unittest.TestCase):
    def setUp(self):
        _close_all()
        self.dir = tempfile.mkdtemp()
        self.doc = util.new_doc("Mk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10 = 2000
        far = util.add_rect_sketch(self.body, w=10, h=10, name="FarSk")
        far.AttachmentOffset = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        self.box = util.add_pad(self.body, far, 5, name="Box")  # 500, separate
        self.body.Tip = self.box
        self.doc.recompute()
        self.path = os.path.join(self.dir, "Plate.FCStd")
        self.doc.saveAs(self.path)

    def tearDown(self):
        _close_all()

    def test_pieces_largest_first(self):
        found = ma.pieces(self.doc)
        self.assertEqual([round(p.volume) for p in found], [2000, 500])

    def test_default_names(self):
        self.assertEqual(ma.default_names(self.doc, 2), ("Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))

    def test_two_part_files_with_history_and_an_assembly(self):
        asm_path = ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertEqual(asm_path, os.path.join(self.dir, "Plate-Assembly.FCStd"))
        _close_all()
        vols = []
        for name, has in (("Plate-Solid1", "Pad"), ("Plate-Solid2", "Box")):
            d = App.openDocument(os.path.join(self.dir, name + ".FCStd"))
            d.recompute()
            body = document.primary_body(d)
            self.assertIsNotNone(body, name)
            self.assertEqual(len(body.Shape.Solids), 1, name)
            self.assertFalse([o.Name for o in d.Objects if "Invalid" in o.State], name)
            self.assertIsNotNone(d.getObject(has), "history kept in %s" % name)
            vols.append(round(body.Shape.Volume))
            App.closeDocument(d.Name)
        self.assertEqual(vols, [2000, 500])
        a = App.openDocument(asm_path)
        a.recompute()
        comps = assembly.components(a)
        self.assertEqual(len(comps), 2)
        self.assertTrue(assembly.is_grounded(comps[0]))
        self.assertAlmostEqual(comps[1].Shape.BoundBox.XMin, 50, places=6)  # where it was

    def test_the_original_file_is_unchanged(self):
        before = os.path.getmtime(self.path)
        ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertEqual(os.path.getmtime(self.path), before)
        self.assertEqual(len(self.body.Shape.Solids), 2)

    def test_each_copy_is_an_incad_part_with_its_piece_as_primary(self):
        ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        _close_all()
        d = App.openDocument(os.path.join(self.dir, "Plate-Solid2.FCStd"))
        self.assertTrue(document.is_incad_part(d))
        self.assertEqual(len(document.bodies(d)), 1)
        self.assertIs(document.primary_body(d), document.bodies(d)[0])

    def test_an_existing_file_is_refused(self):
        open(os.path.join(self.dir, "Plate-Solid2.FCStd"), "w").close()
        self.assertIn("exists", ma.check_names(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))
        with self.assertRaises(ValueError):
            ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "Plate-Solid1.FCStd")))

    def test_duplicate_names_are_refused(self):
        self.assertIn("twice", ma.check_names(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid1"]))

    def test_a_one_piece_part_is_refused(self):
        d = util.new_doc("One")
        util.padded_part(d, 10, incad=True)
        d.recompute()
        d.saveAs(os.path.join(self.dir, "One.FCStd"))
        with self.assertRaises(ValueError) as ctx:
            ma.make(d, "One-Assembly", ["One-Solid1"])
        self.assertIn("one piece", str(ctx.exception))

    def test_an_unsaved_part_is_refused(self):
        d = util.new_doc("Unsaved")
        util.padded_part(d, 10, incad=True)
        with self.assertRaises(ValueError) as ctx:
            ma.pieces_or_refuse(d)
        self.assertIn("Save", str(ctx.exception))

    def test_a_failure_removes_the_files_made(self):
        original = ma._finish_copy
        def broken(*a, **kw):
            raise ValueError("boom")
        ma._finish_copy = broken
        try:
            with self.assertRaises(ValueError):
                ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        finally:
            ma._finish_copy = original
        self.assertEqual(sorted(os.listdir(self.dir)), ["Plate.FCStd"])

    def test_a_split_box_gives_two_parts_each_keeping_one_piece(self):
        from incad.features import split
        d = util.new_doc("Sb")
        body, pad = util.padded_part(d, 10, incad=True)
        sk = body.newObject("Sketcher::SketchObject", "Knife")
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.LineSegment(App.Vector(5, -5, 0), App.Vector(5, 15, 0)))
        d.recompute()
        split.create(d, body, None, dict(split.defaults(d, body, None), sketch=sk.Name))
        d.recompute()
        d.saveAs(os.path.join(self.dir, "Sb.FCStd"))
        ma.make(d, "Sb-Assembly", ["Sb-Solid1", "Sb-Solid2"])
        _close_all()
        vols = []
        for name in ("Sb-Solid1", "Sb-Solid2"):
            p = App.openDocument(os.path.join(self.dir, name + ".FCStd"))
            p.recompute()
            b = document.primary_body(p)
            self.assertEqual(len(b.Shape.Solids), 1)
            vols.append(round(b.Shape.Volume))
            App.closeDocument(p.Name)
        self.assertEqual(vols, [1500, 500])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to see them fail**

Run: `tests/run_headless.sh "test_make_assembly.py"`
Expected: ERROR `ImportError: cannot import name 'make_assembly'`.

- [ ] **Step 3: `assembly.place` keeps a component where it is on request**

In `InCad/incad/core/assembly.py` change the signature to `def place(doc, path, beside=True):` and the branch to:

```python
    if not existing:
        ground(link)
    elif beside:
        boxes = [c.Shape.BoundBox for c in existing if not c.Shape.isNull()]
        right = max(bb.XMax for bb in boxes) if boxes else 0.0
        left = link.Shape.BoundBox.XMin if not link.Shape.isNull() else 0.0
        link.Placement = App.Placement(App.Vector(right + GAP - left, 0, 0), App.Rotation())
        doc.recompute()
    return link
```

- [ ] **Step 4: Write `make_assembly.py`**

```python
"""Make Assembly (Inventor's Make Components): every piece of a part — each Solid, and each solid of a Solid's
shape (a box drawn away from the part, the pieces of a Split) — becomes a part file with its history, and an
assembly links them where they were, the largest grounded. The original part file is not changed."""
import os
from collections import namedtuple

import FreeCAD as App
import Part

from incad.core import assembly, document

Piece = namedtuple("Piece", "body_name point volume")


def _inside(solid):
    """A point inside the solid (its centre of mass when that is inside, else a face's centre)."""
    c = solid.CenterOfMass
    if solid.isInside(c, 1e-6, False):
        return c
    return solid.Faces[0].CenterOfMass


def pieces(doc):
    out = []
    for body in document.bodies(doc):
        if body.Shape.isNull():
            continue
        for s in body.Shape.Solids:
            out.append(Piece(body.Name, _inside(s), s.Volume))
    return sorted(out, key=lambda p: -p.volume)


def pieces_or_refuse(doc):
    if not document.is_incad_part(doc):
        raise ValueError("Make Assembly works on an InCad part")
    if not doc.FileName:
        raise ValueError("Save the part first: its folder takes the new files")
    found = pieces(doc)
    if len(found) < 2:
        raise ValueError("This part is one piece: nothing to assemble")
    return found


def _stem(doc):
    return os.path.splitext(os.path.basename(doc.FileName))[0] if doc.FileName else doc.Label


def default_names(doc, n):
    stem = _stem(doc)
    return "%s-Assembly" % stem, ["%s-Solid%d" % (stem, i + 1) for i in range(n)]


def _path(doc, name):
    return os.path.join(os.path.dirname(doc.FileName), name + ".FCStd")


def check_names(doc, asm_name, names):
    """Why these names can't be used, or ''."""
    every = [asm_name] + list(names)
    if any(not n.strip() or any(ch in n for ch in '/\\:') for n in every):
        return "A name is empty or has / \\ :"
    if len({n.lower() for n in every}) < len(every):
        return "A name is used twice"
    for n in every:
        if os.path.exists(_path(doc, n)):
            return "%s.FCStd exists in this folder (pick another name)" % n
    return ""


def _remove_body(d, body):
    for o in list(body.Group):
        if d.getObject(o.Name) is not None and o.TypeId != "App::Origin":
            body.removeObject(o)
            d.removeObject(o.Name)
    d.removeObject(body.Name)


def _detach_all(d):
    """Every separate piece left in a Solid by an older file goes to a Solid of its own."""
    for _ in range(100):
        lump = next((f for b in document.bodies(d) for f in b.Group if document.is_detached_lump(f)), None)
        if lump is None:
            return
        document.detach_lump(lump)
        d.recompute()


def _finish_copy(path, point):
    """Open the copy, keep only the piece at `point`, save it. Raises with the reason when the piece's copy is not
    one clean solid."""
    d = App.openDocument(path, hidden=True)
    try:
        d.recompute()
        _detach_all(d)
        probe = Part.Vertex(point)
        keep = min((b for b in document.bodies(d) if not b.Shape.isNull()),
                   key=lambda b: b.Shape.distToShape(probe)[0])
        for b in document.bodies(d):
            if b is not keep:
                _remove_body(d, b)
        if len(keep.Shape.Solids) > 1:
            from incad.features import split
            last = next((f for f in reversed(keep.Group) if split.claims(f)), None)
            if last is None:
                raise ValueError("%s: its pieces could not be separated" % os.path.basename(path))
            split.keep_piece(last, point)
        document._meta_set(d, **{document.PRIMARY_KEY: keep.Name})
        d.recompute()
        bad = [o.Label for o in d.Objects if "Invalid" in o.State]
        if bad or len(keep.Shape.Solids) != 1:
            raise ValueError("%s: %s" % (os.path.basename(path), ", ".join(bad) or "not one piece"))
        d.save()
    finally:
        App.closeDocument(d.Name)


def make(doc, asm_name, names):
    found = pieces_or_refuse(doc)
    if len(names) != len(found):
        raise ValueError("One name per piece")
    reason = check_names(doc, asm_name, names)
    if reason:
        raise ValueError(reason)
    made = []
    try:
        for piece, name in zip(found, names):
            path = _path(doc, name)
            doc.saveCopy(path)
            made.append(path)
            _finish_copy(path, piece.point)
        asm_path = _path(doc, asm_name)
        a = App.newDocument(asm_name, hidden=True)
        try:
            assembly.make_assembly(a, document.part_units(doc) or "mm")
            a.saveAs(asm_path)
            made.append(asm_path)
            for path in made[:-1]:  # largest first: the first placed is grounded
                assembly.place(a, path, beside=False)
            a.recompute()
            a.save()
        finally:
            App.closeDocument(a.Name)
        return asm_path
    except Exception:
        for path in made:
            for d in list(App.listDocuments().values()):
                if d.FileName and os.path.abspath(d.FileName) == os.path.abspath(path):
                    App.closeDocument(d.Name)
            if os.path.exists(path):
                os.remove(path)
        raise
```

- [ ] **Step 5: Run the tests**

Run: `tests/run_headless.sh "test_make_assembly.py"`
Expected: 11 tests OK. If a placed part file stays open (FreeCAD opens linked files), `_close_all` in the tests handles
it; `make` must not leave the copies open: check `App.listDocuments()` after `make` has only the part.
Also run `tests/run_headless.sh "test_assembly*.py"` (place's new argument).

- [ ] **Step 6: Commit**

```bash
git add InCad/incad/core/make_assembly.py InCad/incad/core/assembly.py tests/headless/test_make_assembly.py
git commit -m "Make Assembly: each piece a part file with its history, an assembly linking them where they were"
```

---

### Task 5: Make Assembly in the window (dialog, command, piece highlight)

**Files:**
- Create: `InCad/incad/ui/make_assembly_dialog.py`, `InCad/incad/ui/piece_marker.py`
- Modify: `InCad/incad/actions.py`, `ui/ribbon_layout.py`, `ui/marking_layout.py`, `tools/make_icons.py`,
  `tests/widgets/test_actions.py`
- Test: `tests/widgets/test_make_assembly_dialog.py`, `tests/gui/test_make_assembly.py`

**Interfaces:**
- Consumes: `make_assembly.pieces_or_refuse`, `default_names`, `check_names`, `make` (Task 4).
- Produces: `MakeAssemblyDialog(asm_name, rows, check)` — `rows` = `[(name, volume_text)]`, `check(asm, names) -> str`;
  signals `hovered(int)` (-1 = none); `names() -> (asm, [names])`; `ok_button`; command `file.make_assembly`.

- [ ] **Step 1: Write the failing widget test**

```python
"""The Make Assembly names dialog: filled names, a refused name disables OK and says why, hover reports the row."""
import unittest

from widgets import qtapp
from incad.ui.make_assembly_dialog import MakeAssemblyDialog


class MakeAssemblyDialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = MakeAssemblyDialog("Plate-Assembly", [("Plate-Solid1", "2000 mm³"), ("Plate-Solid2", "500 mm³")],
                                    lambda asm, names: "A name is used twice" if len(set(names)) < len(names) else "")

    def test_names_are_filled(self):
        self.assertEqual(self.d.names(), ("Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))
        self.assertTrue(self.d.ok_button.isEnabled())

    def test_a_refused_name_disables_ok(self):
        self.d.name_field(1).setText("Plate-Solid1")
        self.assertFalse(self.d.ok_button.isEnabled())
        self.assertIn("twice", self.d.error_text())

    def test_hover_reports_the_row(self):
        seen = []
        self.d.hovered.connect(seen.append)
        self.d.hover_row(1)
        self.d.hover_row(-1)
        self.assertEqual(seen, [1, -1])
```

(`widgets/qtapp.py` exists for the other widget tests.)

- [ ] **Step 2: Run it to see it fail**

Run: `tests/run_widgets.sh test_make_assembly_dialog.py`
Expected: ERROR `No module named 'incad.ui.make_assembly_dialog'`.

- [ ] **Step 3: Write the dialog**

```python
"""Make Assembly: one dialog with the names of the assembly and of each piece (filled in), each piece's volume;
hovering a row highlights that piece on the view (the shell connects `hovered`)."""
from incad.qt import QtCore, QtWidgets, Signal


class _Row(QtWidgets.QWidget):
    entered = Signal()
    left = Signal()

    def enterEvent(self, event):
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.left.emit()
        super().leaveEvent(event)


class MakeAssemblyDialog(QtWidgets.QDialog):
    hovered = Signal(int)

    def __init__(self, asm_name, rows, check, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Make Assembly")
        self._check = check
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Each piece becomes a part file (with its history) in the part's folder;\n"
                                       "the assembly links them where they are. This part stays as it is."))
        form = QtWidgets.QFormLayout()
        self._asm = QtWidgets.QLineEdit(asm_name)
        form.addRow("Assembly", self._asm)
        self._fields = []
        for i, (name, volume) in enumerate(rows):
            row = _Row(self)
            h = QtWidgets.QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            field = QtWidgets.QLineEdit(name)
            h.addWidget(field, 1)
            h.addWidget(QtWidgets.QLabel(volume))
            row.entered.connect(lambda i=i: self.hover_row(i))
            row.left.connect(lambda: self.hover_row(-1))
            form.addRow("Piece %d%s" % (i + 1, " (grounded)" if i == 0 else ""), row)
            self._fields.append(field)
        lay.addLayout(form)
        self._error = QtWidgets.QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet("color: #c0392b;")
        lay.addWidget(self._error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.ok_button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        for f in [self._asm] + self._fields:
            f.textChanged.connect(self._validate)
        self._validate()

    def name_field(self, i):
        return self._fields[i]

    def names(self):
        return self._asm.text().strip(), [f.text().strip() for f in self._fields]

    def error_text(self):
        return self._error.text()

    def hover_row(self, i):
        self.hovered.emit(i)

    def _validate(self):
        reason = self._check(*self.names())
        self._error.setText(reason)
        self.ok_button.setEnabled(not reason)
```

- [ ] **Step 4: The piece marker and the command**

`InCad/incad/ui/piece_marker.py`:

```python
"""One piece of the part drawn on the view while the Make Assembly dialog hovers its row: its edges as lines over
the model (an SoAnnotation, never in the document)."""


class PieceMarker:
    def __init__(self, view):
        from pivy import coin
        self.view = view
        self.node = coin.SoAnnotation()
        self.node.setName("InCadPiece")
        view.getSceneGraph().addChild(self.node)

    def show(self, solid):
        from pivy import coin
        self.node.removeAllChildren()
        if solid is None:
            return
        color = coin.SoBaseColor()
        color.rgb.setValue(1.0, 0.55, 0.1)
        style = coin.SoDrawStyle()
        style.lineWidth = 3
        self.node.addChild(color)
        self.node.addChild(style)
        for e in solid.Edges:
            pts = e.discretize(Deflection=0.05)
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, len(pts), [(p.x, p.y, p.z) for p in pts])
            line = coin.SoLineSet()
            sep = coin.SoSeparator()
            sep.addChild(coords)
            sep.addChild(line)
            self.node.addChild(sep)

    def remove(self):
        self.node.removeAllChildren()
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass
```

In `InCad/incad/actions.py`:

```python
def make_assembly():
    """The part's pieces become part files and an assembly (names asked first); the assembly opens."""
    import FreeCAD as App
    import FreeCADGui as Gui
    import Part
    from incad.core import make_assembly as ma
    from incad.ui.make_assembly_dialog import MakeAssemblyDialog
    from incad.ui.piece_marker import PieceMarker
    doc = App.ActiveDocument
    found = ma.pieces_or_refuse(doc)
    asm, names = ma.default_names(doc, len(found))
    rows = [(n, "%.0f mm³" % p.volume) for n, p in zip(names, found)]
    dlg = MakeAssemblyDialog(asm, rows, lambda a, ns: ma.check_names(doc, a, ns), Gui.getMainWindow())
    view = Gui.getDocument(doc.Name).ActiveView
    marker = PieceMarker(view)
    solids = []
    for p in found:
        body = doc.getObject(p.body_name)
        probe = Part.Vertex(p.point)
        solids.append(min(body.Shape.Solids, key=lambda s: s.distToShape(probe)[0]))
    dlg.hovered.connect(lambda i: marker.show(solids[i] if i >= 0 else None))
    try:
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return None
    finally:
        marker.remove()
    asm_name, part_names = dlg.names()
    path = ma.make(doc, asm_name, part_names)
    App.openDocument(path)
    return path
```

(import `QtWidgets` from `incad.qt` at the top of the function if `actions.py` has no module-level import of it), and
the command:

```python
        Command(id="file.make_assembly", label="Make Assembly", icon="make_assembly", handler=make_assembly,
                contexts=frozenset({"part"}),
                tooltip="Each separate piece of this part becomes a part file (with its history), linked by a new assembly"),
```

Ribbon: in `ui/ribbon_layout.py` add a group after "Work Features": `["Assemble", ["file.make_assembly"]]`.
Marking menu: in `ui/marking_layout.py`, the empty-space list gets `"file.make_assembly"` (put it after the existing
`view.*` entries of the empty-space list). `tests/widgets/test_actions.py`: add `"file.make_assembly"`.
Icon in `tools/make_icons.py`:

```python
    'make_assembly': '<rect x="3" y="14" width="11" height="11" fill="{F}" stroke="{S}" stroke-width="1.6"/><rect x="18" y="7" width="11" height="11" fill="{F}" stroke="{S}" stroke-width="1.6"/><path d="M14 19 H18" stroke="{A}" stroke-width="2.2"/>',
```

then run `/Applications/FreeCAD.app/Contents/Resources/bin/python tools/make_icons.py`.

- [ ] **Step 5: GUI test**

`tests/gui/test_make_assembly.py`:

```python
"""Make Assembly in a real window: a part with a box drawn away, the dialog's names, OK opens the assembly tab."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import assembly, commands, document, prefs  # noqa: E402

ST = {}


def test_0_part_with_two_pieces():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    part = document.primary_body(doc)
    a = part.newObject("PartDesign::AdditiveBox", "Plate")
    a.Length, a.Width, a.Height = 40, 20, 5
    b = part.newObject("PartDesign::AdditiveBox", "Block")
    b.Length = b.Width = b.Height = 10
    b.Placement = App.Placement(App.Vector(60, 0, 0), App.Rotation())
    part.Tip = b
    doc.recompute()
    folder = os.path.join(os.environ.get("FREECAD_USER_TEMP", tempfile.mkdtemp()), "mk")
    os.makedirs(folder, exist_ok=True)
    doc.saveAs(os.path.join(folder, "Bench.FCStd"))
    harness.pump(500)
    ST.update(folder=folder)


def test_1_dialog_then_ok_opens_the_assembly():
    def press_ok():
        dlg = QtWidgets.QApplication.activeModalWidget()
        assert dlg is not None and dlg.windowTitle() == "Make Assembly", dlg
        assert dlg.names() == ("Bench-Assembly", ["Bench-Solid1", "Bench-Solid2"]), dlg.names()
        dlg.ok_button.click()
    QtCore.QTimer.singleShot(1500, press_ok)
    r = commands.REGISTRY.run("file.make_assembly")
    harness.pump(3000)
    assert getattr(r, "ok", True), getattr(r, "error", "")
    for name in ("Bench-Assembly", "Bench-Solid1", "Bench-Solid2"):
        assert os.path.exists(os.path.join(ST["folder"], name + ".FCStd")), name
    asm_doc = App.ActiveDocument
    assert assembly.is_assembly(asm_doc), asm_doc.Label
    assert len(assembly.components(asm_doc)) == 2


harness.run([test_0_part_with_two_pieces, test_1_dialog_then_ok_opens_the_assembly])
```

- [ ] **Step 6: Run the affected tests**

Run: `tests/run_widgets.sh test_make_assembly_dialog.py`, `tests/run_widgets.sh test_actions.py`,
`tests/run_widgets.sh test_ribbon.py`, `tests/run_widgets.sh test_marking_layout.py`,
`tests/run_gui.sh tests/gui/test_make_assembly.py`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add InCad/incad/ui/make_assembly_dialog.py InCad/incad/ui/piece_marker.py InCad/incad/actions.py \
  InCad/incad/ui/ribbon_layout.py InCad/incad/ui/marking_layout.py tools/make_icons.py InCad/incad/resources/icons \
  tests/widgets/test_actions.py tests/widgets/test_make_assembly_dialog.py tests/gui/test_make_assembly.py
git commit -m "Make Assembly in the ribbon: names dialog (hover shows the piece), OK opens the assembly"
```

---

### Task 6: The user's Thread_1, release notes, one full run

**Files:**
- Modify: `scripts/dist/CHANGES.txt`, `scripts/dist/CHANGES_ru.txt`
- Test: a one-off script on a copy of `/Volumes/Docs/Plasticity_projects/Thread_1.FCStd` (never the file itself)

- [ ] **Step 1: Thread_1 check (headless, on a copy)**

```bash
T=$(mktemp -d); cp /Volumes/Docs/Plasticity_projects/Thread_1.FCStd "$T/"
cat > "$T/check.py" <<EOF
import sys
sys.path.insert(0, "$PWD/InCad")
import FreeCAD as App, os
from incad.core import make_assembly as ma, document
out = open("$T/out.txt", "w")
d = App.openDocument("$T/Thread_1.FCStd")
asm, names = ma.default_names(d, len(ma.pieces(d)))
path = ma.make(d, asm, names)
for n in names:
    p = App.openDocument(os.path.join("$T", n + ".FCStd")); p.recompute()
    b = document.primary_body(p)
    out.write("%s pieces=%d vol=%.1f bad=%s groups=%s\n" % (n, len(b.Shape.Solids), b.Shape.Volume,
              [o.Name for o in p.Objects if "Invalid" in o.State], [g.Name for g in b.Group if g.TypeId.startswith("PartDesign")]))
out.close()
EOF
FREECAD_USER_TEMP="$T" /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -u "$T/user.cfg" -c "exec(open('$T/check.py').read())" >/dev/null 2>&1; cat "$T/out.txt"
```

Expected: `Thread_1-Solid1` one piece ≈ 2254.8 with `Thread002` and `ThreadChamfer001` in its features and no `bad`;
`Thread_1-Solid2` one piece ≈ 1076.1 (the block, `Extrude002`, `Hole001`) and no `bad`.

- [ ] **Step 2: Release notes**

Add under 0.1.2 Improvements in `CHANGES.txt`:

```
- New Split (3D Model > Modify): the lines of a sketch become thin surfaces that cut the part; Split keeps every
  piece, Cut only the pieces you click.
- New Make Assembly (3D Model > Assemble): every separate piece of the part becomes a part file with its history,
  and a new assembly links them where they were (the largest grounded). Names are asked first; files go next to the
  part, nothing is overwritten, the part itself stays as it was.
```

and in `CHANGES_ru.txt`:

```
- Новая команда Split (3D Model > Modify): линии эскиза становятся тонкими поверхностями и режут деталь; Split
  оставляет все куски, Cut - только те, по которым вы кликнули.
- Новая команда Make Assembly (3D Model > Assemble): каждый отдельный кусок детали становится файлом детали с
  историей, а новая сборка связывает их на прежних местах (самый большой закреплён). Сначала спрашиваются имена;
  файлы сохраняются рядом с деталью, ничего не перезаписывается, сама деталь не меняется.
```

- [ ] **Step 3: One full run before the last commit**

Run: `tests/run_all.sh` in the background; wait for its notification (do not read the log meanwhile); read only the
summary. Expected: all pass except `test_open_sketches.py` test 9 (fails on `main` too). Rerun only files that failed.

- [ ] **Step 4: Commit**

```bash
git add scripts/dist/CHANGES.txt scripts/dist/CHANGES_ru.txt
git commit -m "Release notes: Split and Make Assembly"
```
