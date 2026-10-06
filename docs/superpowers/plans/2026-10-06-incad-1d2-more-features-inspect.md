# InCad 1d-2 — Hole, Fillet, Chamfer, Shell, Patterns, Mirror, Work Features, Inspect

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish stage 1's part modeling: Hole (from sketch points/circles or concentric to a circular edge;
simple / counterbore / countersink; distance or through all; flat or 118° tip), Fillet, Chamfer (equal distance,
two distances, distance + angle), Shell (inside / outside, faces to remove), Rectangular Pattern (two directions,
count + spacing), Circular Pattern, Mirror, Work Plane (offset / 3 points), Work Axis (through an edge / two
points), Work Point (at a vertex), and Inspect: Measure and Mass Properties. All through the 1d-1 feature dialog,
with selection fields that take picks from the 3D view (this also makes Extrude's "To face" usable).

**Architecture:** Each feature is a pure kind module in `incad/features/` (headless-tested) driving the native
PartDesign object, values bound to model parameters. The dialog gains selection fields (`pick` single, `picks`
multi); the FeatureSession becomes a selection observer that feeds the active selection field, and pre-fills it
from what was selected before the command (Inventor: select edges, then Fillet). Inspect is read-only and shows
results in an info panel.

**Tech Stack:** FreeCAD 1.1.3 PartDesign (Hole, Fillet, Chamfer, Thickness, LinearPattern, PolarPattern,
Mirrored, Plane, Line, Point), Part shape queries, PySide6.

**Spec:** `docs/superpowers/specs/2026-10-05-incad-stage1-design.md` §6 (features table, Inspect tab).
Base: plan 1d-1 (feature dialog, sessions, model parameters).

## Global Constraints

- Plans 1a–1d-1 constraints hold (one undo step per dialog, busy flag, OK disabled while invalid, plain-language
  errors, values as model parameters, Qt via `incad.qt`, throwaway `user.cfg`, announce GUI runs).
- Picks are stored as text `Object:Sub[,Object:Sub…]` (`Object` alone for whole features); a pick on a Body means
  its Tip feature (the Body shows the Tip's shape).
- Probed facts: Shell inside = `Thickness.Reversed = True`; a second Linear Pattern direction only works in
  `Mode2 = "Extent"` (so both directions use Extent with `Length = spacing × (count − 1)`); a datum axis through an
  edge needs `MapMode = "TwoPointLine"`; a datum point at a vertex uses `MapMode = "Vertex"`.
- Inspect never changes the model.

## Review Focus

1. Pre-selected edges/faces/features are taken over when the command starts and can be changed in the dialog
   (Task 7 GUI tests 1, 3).
2. A pick on a face of a Body (or of an older feature) resolves to the current Tip, so the new feature uses the
   current shape (Task 1 tests).
3. Counts and spacings are parameters too: changing the spacing parameter updates the pattern (Task 4 test).
4. A pick field never accepts the wrong kind of item (an edge for a face field); the dialog says what it needs
   (Task 1 test, Task 6 test).
5. Measure/Mass Properties with nothing or an unsupported selection explain what to select instead of failing
   (Task 5 tests).

## File Map

```
InCad/incad/features/common.py        + Field.pick, parse/format/resolve picks, pick filters
InCad/incad/features/__init__.py      + new kinds
InCad/incad/features/hole.py          Hole
InCad/incad/features/dressup.py       Fillet, Chamfer, Shell (three kinds in one module: FILLET, CHAMFER, SHELL)
InCad/incad/features/patterns.py      Rectangular, Circular, Mirror (RECT, CIRC, MIRROR)
InCad/incad/features/work.py          Work Plane, Axis, Point (PLANE, AXIS, POINT)
InCad/incad/core/inspect.py           measure(selection), mass_properties(body, density)
InCad/incad/ui/feature_dialog.py      + pick / picks fields with an active-pick state
InCad/incad/ui/feature_session.py     + selection observer, pre-selection, profile-less kinds
InCad/incad/ui/info_panel.py          small result panel for Inspect
InCad/incad/ui/shell.py               start kinds without a profile, Inspect commands
InCad/incad/actions.py                commands for every new feature and Inspect
InCad/incad/ui/ribbon_layout.py       3D Model: Create/Modify/Pattern/Work Features; Inspect tab
InCad/incad/ui/marking_layout.py      Hole/Fillet on face/edge menus
tools/make_icons.py                   + hole, fillet, chamfer, shell, rect_pattern3d, circ_pattern, mirror3d,
                                        work_plane, work_axis, work_point, measure, mass
```

---

### Task 1: Pick helpers

**Files:**
- Modify: `InCad/incad/features/common.py`
- Create: `tests/headless/test_picks.py`

**Interfaces:**
- Produces: `Field` gains `pick: str = ""` — one of `edge`, `face`, `feature`, `axis` (origin axis, datum line or
  straight edge), `plane` (origin plane, datum plane or planar face), `vertex`, `sketch`, `circular_edge`;
  `parse_picks(doc, text) -> [(obj, sub)]`; `format_picks(pairs) -> text`; `resolve(obj, sub) -> (obj, sub)` (Body →
  Tip; `Feature.Face3` style paths split); `accepts(kind, obj, sub) -> bool`; `pick_label(kind, text) -> str`
  (`"3 edges"`, `"Pad · Face6"`, `"Select…"`); `link_sub(pairs) -> (obj, [subs])` (all subs must be on one object).

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_picks.py`:
```python
import unittest

import FreeCAD as App
from incad.core import document
from incad.features import common
from headless import util


class PicksTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Pk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_format_and_parse(self):
        text = common.format_picks([(self.pad, "Edge1"), (self.pad, "Edge3")])
        self.assertEqual(text, "%s:Edge1,%s:Edge3" % (self.pad.Name, self.pad.Name))
        self.assertEqual(common.parse_picks(self.doc, text), [(self.pad, "Edge1"), (self.pad, "Edge3")])
        self.assertEqual(common.parse_picks(self.doc, ""), [])
        self.assertEqual(common.format_picks([(self.pad, "")]), self.pad.Name)

    def test_body_pick_means_tip(self):
        self.assertEqual(common.resolve(self.body, "Face6"), (self.pad, "Face6"))
        self.assertEqual(common.resolve(self.body, "%s.Face6" % self.pad.Name), (self.pad, "Face6"))

    def test_accepts(self):
        x = [o for o in self.body.Origin.OriginFeatures if o.Role == "X_Axis"][0]
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        self.assertTrue(common.accepts("edge", self.pad, "Edge1"))
        self.assertFalse(common.accepts("edge", self.pad, "Face%d" % top))
        self.assertTrue(common.accepts("face", self.pad, "Face%d" % top))
        self.assertTrue(common.accepts("axis", x, ""))
        self.assertTrue(common.accepts("axis", self.pad, "Edge1"))
        self.assertTrue(common.accepts("plane", xy, ""))
        self.assertTrue(common.accepts("plane", self.pad, "Face%d" % top))
        self.assertFalse(common.accepts("plane", x, ""))
        self.assertTrue(common.accepts("feature", self.pad, ""))
        self.assertTrue(common.accepts("vertex", self.pad, "Vertex1"))
        self.assertFalse(common.accepts("circular_edge", self.pad, "Edge1"))

    def test_labels(self):
        self.assertEqual(common.pick_label("edge", ""), "Select…")
        text = common.format_picks([(self.pad, "Edge1"), (self.pad, "Edge2"), (self.pad, "Edge3")])
        self.assertEqual(common.pick_label("edge", text), "3 edges")
        self.assertEqual(common.pick_label("face", "%s:Face6" % self.pad.Name), "%s · Face6" % self.pad.Label)

    def test_link_sub(self):
        self.assertEqual(common.link_sub([(self.pad, "Edge1"), (self.pad, "Edge2")]), (self.pad, ["Edge1", "Edge2"]))
        with self.assertRaises(ValueError):
            common.link_sub([])
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_picks.py` → Expected: AttributeError (`format_picks`).

- [ ] **Step 3: Implement (append to `InCad/incad/features/common.py`; add `pick: str = ""` as the last `Field` field)**

```python
_PLURAL = {"edge": "edges", "face": "faces", "feature": "features", "vertex": "points", "axis": "axes",
           "plane": "planes", "sketch": "sketches", "circular_edge": "edges"}


def resolve(obj, sub):
    """A pick on a Body means its Tip; 'Pad.Face6' style paths name the object and the element."""
    if "." in sub:
        parts = sub.split(".")
        child = obj.Document.getObject(parts[-2]) if len(parts) > 1 else None
        obj, sub = (child or obj), parts[-1]
    if obj is not None and obj.TypeId == "PartDesign::Body" and obj.Tip is not None:
        return obj.Tip, sub
    return obj, sub


def format_picks(pairs):
    return ",".join(o.Name if not s else "%s:%s" % (o.Name, s) for o, s in pairs)


def parse_picks(doc, text):
    out = []
    for item in (text or "").split(","):
        item = item.strip()
        if not item:
            continue
        name, _, sub = item.partition(":")
        obj = doc.getObject(name)
        if obj is not None:
            out.append((obj, sub))
    return out


def _element(obj, sub):
    try:
        return obj.getSubObject(sub) if sub else None
    except Exception:
        return None


def accepts(kind, obj, sub):
    if obj is None:
        return False
    tid = obj.TypeId
    if kind == "feature":
        return not sub and tid.startswith("PartDesign::") and tid not in ("PartDesign::Body",)
    if kind == "sketch":
        return not sub and tid == "Sketcher::SketchObject"
    el = _element(obj, sub)
    if kind == "edge":
        return sub.startswith("Edge") and el is not None
    if kind == "circular_edge":
        return sub.startswith("Edge") and el is not None and el.Curve.TypeId == "Part::GeomCircle"
    if kind == "face":
        return sub.startswith("Face") and el is not None
    if kind == "vertex":
        return sub.startswith("Vertex") and el is not None
    if kind == "axis":
        if not sub:
            return tid in ("App::Line", "PartDesign::Line")
        return sub.startswith("Edge") and el is not None and el.Curve.TypeId == "Part::GeomLine"
    if kind == "plane":
        if not sub:
            return tid in ("App::Plane", "PartDesign::Plane")
        return sub.startswith("Face") and el is not None and el.Surface.TypeId == "Part::GeomPlane"
    return False


def pick_label(kind, text):
    items = [i for i in (text or "").split(",") if i.strip()]
    if not items:
        return "Select…"
    if len(items) == 1:
        name, _, sub = items[0].partition(":")
        try:
            import FreeCAD as App
            obj = App.ActiveDocument.getObject(name) if App.ActiveDocument is not None else None
        except Exception:
            obj = None
        label = obj.Label if obj is not None else name
        return "%s · %s" % (label, sub) if sub else label
    return "%d %s" % (len(items), _PLURAL.get(kind, "items"))


def link_sub(pairs):
    """(obj, [subs]) for a PartDesign LinkSub: every pick must be on the same object."""
    if not pairs:
        raise ValueError("Select at least one item")
    obj = pairs[0][0]
    if any(o is not obj for o, _ in pairs):
        raise ValueError("Pick the items on one feature (the latest one)")
    return obj, [s for _, s in pairs]
```
Note `pick_label` for a single item uses `App.ActiveDocument` to find the label; tests run with the test document
active (`util.new_doc` activates it).

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_picks.py` → Expected: 5 tests OK; `tests/run_fast.sh` OK.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features/common.py tests/headless/test_picks.py && git commit -m "InCad 1d-2: pick helpers"
```

---

### Task 2: Hole

**Files:**
- Create: `InCad/incad/features/hole.py`, `tests/headless/test_hole.py`
- Modify: `InCad/incad/features/__init__.py` (add `hole` to `kinds()`)

**Interfaces:**
- Produces (`incad.features.hole`): kind module (`TITLE "Hole"`, `ICON "hole"`, `TYPES ("PartDesign::Hole",)`,
  `NEEDS_PROFILE = False`, `PROPS`, `FIELDS`, `defaults(doc, body, profile)`, `create`, `read`, `update`,
  `_pad_of`). Values: `placement` (`sketch` / `concentric`), `sketch` (pick sketch), `face` (pick plane), `edge`
  (pick circular_edge), `type` (`simple` / `counterbore` / `countersink`), `depth_type` (`distance` /
  `through_all`), `diameter`, `depth`, `cbore_diameter`, `cbore_depth`, `csink_diameter`, `csink_angle`, `tip`
  (`flat` / `angled`). Concentric placement makes a hidden helper sketch on the face with a point at the edge's
  centre (not associative to the edge — ledgered).

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_hole.py`:
```python
import math
import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import hole, kind_for
from headless import util


class HoleTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Ho")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def sketch_with_circle(self):
        sk = self.body.newObject("Sketcher::SketchObject", "Pts")
        sk.AttachmentSupport = [(self.pad, "Face%d" % self.top)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 1))
        self.doc.recompute()
        return sk

    def test_from_sketch_through_all(self):
        sk = self.sketch_with_circle()
        v = dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name, depth_type="through_all", diameter="4 mm")
        f = hole.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertEqual(f.TypeId, "PartDesign::Hole")
        self.assertAlmostEqual(self.body.Shape.Volume, 2000 - math.pi * 4 * 10, places=2)
        self.assertIs(kind_for(f), hole)
        self.assertEqual(hole.read(self.doc, f)["diameter"], "4 mm")

    def test_counterbore(self):
        sk = self.sketch_with_circle()
        v = dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name, type="counterbore", depth_type="through_all",
                 diameter="3 mm", cbore_diameter="6 mm", cbore_depth="2 mm")
        f = hole.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertEqual(f.HoleCutType, "Counterbore")
        self.assertAlmostEqual(2000 - self.body.Shape.Volume, math.pi * 1.5 ** 2 * 8 + math.pi * 9 * 2, places=1)

    def test_concentric_to_a_circular_edge(self):
        cyl_sk = self.body.newObject("Sketcher::SketchObject", "Boss")
        cyl_sk.AttachmentSupport = [(self.pad, "Face%d" % self.top)]
        cyl_sk.MapMode = "FlatFace"
        cyl_sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 3))
        boss = util.add_pad(self.body, cyl_sk, 5, name="BossPad")
        self.body.Tip = boss
        self.doc.recompute()
        top2 = [i + 1 for i, f in enumerate(boss.Shape.Faces) if abs(f.CenterOfMass.z - 15) < 1e-6][0]
        circle = [i + 1 for i, e in enumerate(boss.Shape.Edges)
                  if e.Curve.TypeId == "Part::GeomCircle" and abs(e.BoundBox.ZMax - 15) < 1e-6][0]
        v = dict(hole.defaults(self.doc, self.body, None), placement="concentric",
                 face="%s:Face%d" % (boss.Name, top2), edge="%s:Edge%d" % (boss.Name, circle),
                 diameter="2 mm", depth_type="distance", depth="4 mm")
        f = hole.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertEqual(f.State, ["Up-to-date"])
        c = f.Shape.BoundBox.Center
        self.assertLess(self.body.Shape.Volume, boss.Shape.Volume)
        self.assertAlmostEqual(hole.read(self.doc, f)["placement"], "concentric")

    def test_parameters(self):
        sk = self.sketch_with_circle()
        f = hole.create(self.doc, self.body, None, dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name))
        self.doc.recompute()
        name = model.bound_parameter(f, "Diameter")
        model.set_model_parameter(self.doc, name, "5 mm")
        self.assertAlmostEqual(f.Diameter.Value, 5)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_hole.py` → Expected: `cannot import name 'hole'`.

- [ ] **Step 3: Implement**

`InCad/incad/features/hole.py`:
```python
"""Hole (Inventor) = PartDesign Hole. Placement from a sketch's points/circle centres, or concentric to a circular
edge on a flat face (a hidden helper sketch holds the centre point)."""
import FreeCAD as App
import Part

from incad.features.common import Field, parse_picks, resolve, value_param, value_text

TITLE = "Hole"
ICON = "hole"
TYPES = ("PartDesign::Hole",)
NEEDS_PROFILE = False
PROPS = {"diameter": "Diameter", "depth": "Depth", "cbore_diameter": "HoleCutDiameter",
         "cbore_depth": "HoleCutDepth", "csink_diameter": "HoleCutDiameter", "csink_angle": "HoleCutCountersinkAngle"}
FIELDS = (
    Field("placement", "Placement", "choice", (("sketch", "From Sketch"), ("concentric", "Concentric")), "sketch"),
    Field("sketch", "Sketch", "pick", show_if=("placement", ("sketch",)), pick="sketch"),
    Field("face", "Face", "pick", show_if=("placement", ("concentric",)), pick="plane"),
    Field("edge", "Circular edge", "pick", show_if=("placement", ("concentric",)), pick="circular_edge"),
    Field("type", "Type", "choice", (("simple", "Simple"), ("counterbore", "Counterbore"),
                                     ("countersink", "Countersink")), "simple"),
    Field("diameter", "Diameter", "value_length", default="5 mm"),
    Field("depth_type", "Termination", "choice", (("distance", "Distance"), ("through_all", "Through All")),
          "through_all"),
    Field("depth", "Depth", "value_length", default="10 mm", show_if=("depth_type", ("distance",))),
    Field("tip", "Drill point", "choice", (("flat", "Flat"), ("angled", "118°")), "angled",
          show_if=("depth_type", ("distance",))),
    Field("cbore_diameter", "C'bore Ø", "value_length", default="10 mm", show_if=("type", ("counterbore",))),
    Field("cbore_depth", "C'bore depth", "value_length", default="3 mm", show_if=("type", ("counterbore",))),
    Field("csink_diameter", "C'sink Ø", "value_length", default="10 mm", show_if=("type", ("countersink",))),
    Field("csink_angle", "C'sink angle", "value_angle", default="90 °", show_if=("type", ("countersink",))),
)
_CUT = {"simple": "None", "counterbore": "Counterbore", "countersink": "Countersink"}


def defaults(doc, body, profile):
    values = {f.key: f.default for f in FIELDS}
    values.update(sketch="", face="", edge="")
    return values


def _helper_sketch(doc, body, values):
    """A hidden sketch on the face with a point at the circular edge's centre (fixed position)."""
    face_obj, face = parse_picks(doc, values.get("face"))[0]
    edge_obj, edge = parse_picks(doc, values.get("edge"))[0]
    centre = edge_obj.getSubObject(edge).Curve.Center
    sk = body.newObject("Sketcher::SketchObject", "HoleCentre")
    sk.AttachmentSupport = [resolve(face_obj, face)]
    sk.MapMode = "FlatFace"
    doc.recompute()
    local = sk.getGlobalPlacement().inverse().multVec(centre)
    sk.addGeometry(Part.Point(App.Vector(local.x, local.y, 0)))
    sk.Visibility = False
    doc.recompute()
    return sk


def _profile(doc, body, values):
    if values.get("placement") == "concentric":
        return _helper_sketch(doc, body, values)
    picks = parse_picks(doc, values.get("sketch"))
    if not picks:
        raise ValueError("Pick a sketch with points or circles for the hole centres")
    return picks[0][0]


def _apply(doc, f, values):
    f.HoleCutType = _CUT.get(values.get("type", "simple"), "None")
    f.DepthType = "ThroughAll" if values.get("depth_type") == "through_all" else "Dimension"
    f.DrillPoint = "Angled" if values.get("tip") == "angled" else "Flat"
    value_param(doc, f, "Diameter", values.get("diameter") or "5 mm", "length")
    if f.DepthType == "Dimension":
        value_param(doc, f, "Depth", values.get("depth") or "10 mm", "length")
    if values.get("type") == "counterbore":
        value_param(doc, f, "HoleCutDiameter", values.get("cbore_diameter") or "10 mm", "length")
        value_param(doc, f, "HoleCutDepth", values.get("cbore_depth") or "3 mm", "length")
    elif values.get("type") == "countersink":
        value_param(doc, f, "HoleCutDiameter", values.get("csink_diameter") or "10 mm", "length")
        value_param(doc, f, "HoleCutCountersinkAngle", values.get("csink_angle") or "90 °", "angle")


def create(doc, body, profile, values):
    sk = _profile(doc, body, values)
    f = body.newObject("PartDesign::Hole", "Hole")
    f.Profile = sk
    _apply(doc, f, values)
    return f


def read(doc, f):
    prof = f.Profile[0] if isinstance(f.Profile, (tuple, list)) else f.Profile
    concentric = prof is not None and prof.Name.startswith("HoleCentre")
    cut = {v: k for k, v in _CUT.items()}.get(f.HoleCutType, "simple")
    values = defaults(f.Document, None, None)
    values.update(placement="concentric" if concentric else "sketch", sketch="" if concentric else prof.Name,
                  type=cut, depth_type="through_all" if f.DepthType == "ThroughAll" else "distance",
                  tip="angled" if f.DrillPoint == "Angled" else "flat",
                  diameter=value_text(doc, f, "Diameter") or "5 mm", depth=value_text(doc, f, "Depth") or "10 mm")
    if cut == "counterbore":
        values.update(cbore_diameter=value_text(doc, f, "HoleCutDiameter") or "10 mm",
                      cbore_depth=value_text(doc, f, "HoleCutDepth") or "3 mm")
    if cut == "countersink":
        values.update(csink_diameter=value_text(doc, f, "HoleCutDiameter") or "10 mm",
                      csink_angle=value_text(doc, f, "HoleCutCountersinkAngle") or "90°")
    return values


def update(doc, f, values):
    if values.get("placement") == "sketch":
        picks = parse_picks(doc, values.get("sketch"))
        if picks and (f.Profile[0] if isinstance(f.Profile, (tuple, list)) else f.Profile) is not picks[0][0]:
            f.Profile = picks[0][0]
    _apply(doc, f, values)
    return f


def _pad_of(f):
    return f
```
Add `hole` to `kinds()` in `InCad/incad/features/__init__.py` (`from incad.features import extrude, hole, revolve`
and `return [extrude, revolve, hole]`).

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_hole.py` → Expected: 4 tests OK. If a Hole property name or volume differs in
1.1.3, probe it and fix the module (tests stay, except a measured volume formula proven wrong by a probe — ledger
that ruling).

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features tests/headless/test_hole.py && git commit -m "InCad 1d-2: Hole"
```

---

### Task 3: Fillet, Chamfer, Shell

**Files:**
- Create: `InCad/incad/features/dressup.py`, `tests/headless/test_dressup.py`
- Modify: `InCad/incad/features/__init__.py`

**Interfaces:**
- Produces (`incad.features.dressup`): three kind objects `FILLET`, `CHAMFER`, `SHELL` (simple namespaces with the
  kind interface: `TITLE`, `ICON`, `TYPES`, `NEEDS_PROFILE=False`, `PROPS`, `FIELDS`, `defaults`, `create`,
  `read`, `update`, `_pad_of`, `PRESELECT` (`{field key: pick kind}` taken from the selection at start)).
  Fillet: `edges` (picks edge), `radius`. Chamfer: `edges`, `type` (`equal`/`two`/`angle`), `size`, `size2`,
  `angle`, `flip`. Shell: `faces` (picks face, faces to remove), `thickness`, `direction` (`inside`/`outside`).
  `kinds()` includes them.

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_dressup.py`:
```python
import unittest

import FreeCAD as App
from incad.core import model
from incad.features import common, dressup, kind_for
from headless import util


class DressUpTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Du")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.top_edges = ["Edge%d" % (i + 1) for i, e in enumerate(self.pad.Shape.Edges)
                          if abs(e.BoundBox.ZMin - 10) < 1e-6 and abs(e.BoundBox.ZMax - 10) < 1e-6]
        self.top_face = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def edges(self):
        return common.format_picks([(self.pad, e) for e in self.top_edges])

    def test_fillet(self):
        k = dressup.FILLET
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=self.edges(),
                                                     radius="2 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 1951.56, places=1)
        self.assertIs(kind_for(f), k)
        self.assertEqual(k.read(self.doc, f)["radius"], "2 mm")
        model.set_model_parameter(self.doc, model.bound_parameter(f, "Radius"), "1 mm")
        self.assertGreater(f.Shape.Volume, 1951.56)

    def test_chamfer_types(self):
        k = dressup.CHAMFER
        for kind, volume in (("equal", 1971.33), ("two", 1945.33), ("angle", 1983.12)):
            f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=self.edges(),
                                                         type=kind, size="1 mm", size2="2 mm", angle="30"))
            self.doc.recompute()
            self.assertAlmostEqual(f.Shape.Volume, volume, places=1, msg=kind)
            self.assertEqual(k.read(self.doc, f)["type"], kind)
            self.body.removeObject(f)
            self.doc.removeObject(f.Name)
            self.body.Tip = self.pad
            self.doc.recompute()

    def test_shell_inside_and_outside(self):
        k = dressup.SHELL
        face = "%s:Face%d" % (self.pad.Name, self.top_face)
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), faces=face,
                                                     thickness="1 mm", direction="inside"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.XLength, 20, places=3)
        f = k.update(self.doc, f, dict(k.read(self.doc, f), direction="outside"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.XLength, 22, places=3)

    def test_needs_edges(self):
        k = dressup.FILLET
        with self.assertRaises(ValueError):
            k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_dressup.py` → Expected: `cannot import name 'dressup'`.

- [ ] **Step 3: Implement**

`InCad/incad/features/dressup.py`:
```python
"""Fillet, Chamfer and Shell (Inventor) = PartDesign Fillet, Chamfer, Thickness on picked edges/faces."""
from types import SimpleNamespace

from incad.features.common import Field, link_sub, parse_picks, resolve, value_param, value_text


def _base(doc, text):
    pairs = [resolve(o, s) for o, s in parse_picks(doc, text)]
    return link_sub(pairs)


def _picks_text(f, prop="Base"):
    link = getattr(f, prop)
    if not link or link[0] is None:
        return ""
    obj, subs = link[0], link[1]
    return ",".join("%s:%s" % (obj.Name, s) for s in subs)


# ----- Fillet -----
def _fillet_create(doc, body, profile, values):
    obj, subs = _base(doc, values.get("edges"))
    f = body.newObject("PartDesign::Fillet", "Fillet")
    f.Base = (obj, subs)
    value_param(doc, f, "Radius", values.get("radius") or "1 mm", "length")
    return f


def _fillet_read(doc, f):
    return {"edges": _picks_text(f), "radius": value_text(doc, f, "Radius") or "1 mm"}


def _fillet_update(doc, f, values):
    obj, subs = _base(doc, values.get("edges"))
    f.Base = (obj, subs)
    value_param(doc, f, "Radius", values.get("radius") or "1 mm", "length")
    return f


FILLET = SimpleNamespace(
    __name__="incad.features.fillet", TITLE="Fillet", ICON="fillet", TYPES=("PartDesign::Fillet",),
    NEEDS_PROFILE=False, PROPS={"radius": "Radius"}, PRESELECT={"edges": "edge"},
    FIELDS=(Field("edges", "Edges", "picks", pick="edge"),
            Field("radius", "Radius", "value_length", default="1 mm")),
    defaults=lambda doc, body, profile: {"edges": "", "radius": "1 mm"},
    create=_fillet_create, read=_fillet_read, update=_fillet_update, _pad_of=lambda f: f)


# ----- Chamfer -----
_CHAMFER = {"equal": "Equal distance", "two": "Two distances", "angle": "Distance and Angle"}


def _chamfer_apply(doc, f, values):
    obj, subs = _base(doc, values.get("edges"))
    f.Base = (obj, subs)
    kind = values.get("type", "equal")
    f.ChamferType = _CHAMFER.get(kind, "Equal distance")
    f.FlipDirection = bool(values.get("flip"))
    value_param(doc, f, "Size", values.get("size") or "1 mm", "length")
    if kind == "two":
        value_param(doc, f, "Size2", values.get("size2") or "1 mm", "length")
    if kind == "angle":
        value_param(doc, f, "Angle", values.get("angle") or "45 °", "angle")


def _chamfer_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Chamfer", "Chamfer")
    _chamfer_apply(doc, f, values)
    return f


def _chamfer_read(doc, f):
    kind = {v: k for k, v in _CHAMFER.items()}.get(f.ChamferType, "equal")
    return {"edges": _picks_text(f), "type": kind, "size": value_text(doc, f, "Size") or "1 mm",
            "size2": value_text(doc, f, "Size2") or "1 mm", "angle": value_text(doc, f, "Angle") or "45°",
            "flip": bool(f.FlipDirection)}


def _chamfer_update(doc, f, values):
    _chamfer_apply(doc, f, values)
    return f


CHAMFER = SimpleNamespace(
    __name__="incad.features.chamfer", TITLE="Chamfer", ICON="chamfer", TYPES=("PartDesign::Chamfer",),
    NEEDS_PROFILE=False, PROPS={"size": "Size", "size2": "Size2", "angle": "Angle"}, PRESELECT={"edges": "edge"},
    FIELDS=(Field("edges", "Edges", "picks", pick="edge"),
            Field("type", "Type", "choice", (("equal", "Distance"), ("two", "Two distances"),
                                             ("angle", "Distance + angle")), "equal"),
            Field("size", "Distance", "value_length", default="1 mm"),
            Field("size2", "Distance 2", "value_length", default="1 mm", show_if=("type", ("two",))),
            Field("angle", "Angle", "value_angle", default="45 °", show_if=("type", ("angle",))),
            Field("flip", "Flip", "bool", default=False, show_if=("type", ("two", "angle")))),
    defaults=lambda doc, body, profile: {"edges": "", "type": "equal", "size": "1 mm", "size2": "1 mm",
                                         "angle": "45 °", "flip": False},
    create=_chamfer_create, read=_chamfer_read, update=_chamfer_update, _pad_of=lambda f: f)


# ----- Shell -----
def _shell_apply(doc, f, values):
    obj, subs = _base(doc, values.get("faces"))
    f.Base = (obj, subs)
    f.Reversed = values.get("direction", "inside") == "inside"  # probed: Reversed=True keeps the outer size
    value_param(doc, f, "Value", values.get("thickness") or "1 mm", "length")


def _shell_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Thickness", "Shell")
    _shell_apply(doc, f, values)
    return f


def _shell_read(doc, f):
    return {"faces": _picks_text(f), "thickness": value_text(doc, f, "Value") or "1 mm",
            "direction": "inside" if f.Reversed else "outside"}


def _shell_update(doc, f, values):
    _shell_apply(doc, f, values)
    return f


SHELL = SimpleNamespace(
    __name__="incad.features.shell", TITLE="Shell", ICON="shell", TYPES=("PartDesign::Thickness",),
    NEEDS_PROFILE=False, PROPS={"thickness": "Value"}, PRESELECT={"faces": "face"},
    FIELDS=(Field("faces", "Remove faces", "picks", pick="face"),
            Field("thickness", "Thickness", "value_length", default="1 mm"),
            Field("direction", "Direction", "choice", (("inside", "Inside"), ("outside", "Outside")), "inside")),
    defaults=lambda doc, body, profile: {"faces": "", "thickness": "1 mm", "direction": "inside"},
    create=_shell_create, read=_shell_read, update=_shell_update, _pad_of=lambda f: f)
```
In `InCad/incad/features/__init__.py`: `from incad.features import dressup, extrude, hole, revolve` and
`return [extrude, revolve, hole, dressup.FILLET, dressup.CHAMFER, dressup.SHELL]`.
In `actions.start_feature`, the name lookup uses `k.__name__.rsplit(".", 1)[-1]`, so the kinds are reachable as
`"fillet"`, `"chamfer"`, `"shell"`.

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_dressup.py` → Expected: 4 tests OK. (The expected volumes are the probed values in
the ledger.)

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features tests/headless/test_dressup.py && git commit -m "InCad 1d-2: Fillet, Chamfer, Shell"
```

---

### Task 4: Patterns, Mirror, Work features

**Files:**
- Create: `InCad/incad/features/patterns.py`, `InCad/incad/features/work.py`, `tests/headless/test_patterns.py`,
  `tests/headless/test_work.py`
- Modify: `InCad/incad/features/__init__.py`

**Interfaces:**
- Produces (`incad.features.patterns`): `RECT` (fields `features` picks feature, `dir1` pick axis, `count1`,
  `spacing1`, `two_directions` bool, `dir2` pick axis, `count2`, `spacing2`), `CIRC` (`features`, `axis` pick axis,
  `count`, `angle`), `MIRROR` (`features`, `plane` pick plane). Counts are model parameters too (unit kind
  `"count"` — plain numbers stay unitless). Directions default to the origin X / Y axes, the circular axis to Z,
  the mirror plane to YZ; `features` defaults to the selected features or else the Tip.
- Produces (`incad.features.work`): `PLANE` (`mode` offset/three_points; `base` pick plane; `offset`; `points`
  picks vertex), `AXIS` (`mode` edge/two_points; `edge` pick axis; `points` picks vertex), `POINT` (`vertex` pick
  vertex). They create `PartDesign::Plane/Line/Point` with the probed map modes.
- `incad.core.model.new_feature_parameter(..., unit_kind="count")` keeps plain numbers unitless.

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_patterns.py`:
```python
import unittest

import FreeCAD as App
from incad.core import model
from incad.features import common, kind_for, patterns
from headless import util


class PatternsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Pt")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_rectangular_two_directions(self):
        k = patterns.RECT
        v = dict(k.defaults(self.doc, self.body, None), count1="3", spacing1="30 mm", two_directions=True,
                 count2="2", spacing2="20 mm")
        f = k.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 6 * 2000, places=1)
        self.assertIs(kind_for(f), k)
        r = k.read(self.doc, f)
        self.assertEqual((r["count1"], r["spacing1"], r["count2"], r["two_directions"]), ("3", "30 mm", "2", True))

    def test_spacing_parameter_drives_the_pattern(self):
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), count1="2",
                                                     spacing1="30 mm"))
        self.doc.recompute()
        name = model.bound_parameter(f, "Offset") or k.spacing_param(f, 1)
        model.set_model_parameter(self.doc, name, "10 mm")  # overlapping copies now
        self.assertLess(f.Shape.Volume, 2 * 2000 - 1)

    def test_circular(self):
        k = patterns.CIRC
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), count="4"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 8000, places=1)

    def test_mirror(self):
        k = patterns.MIRROR
        f = k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 4000, places=1)
        self.assertEqual(common.parse_picks(self.doc, k.read(self.doc, f)["features"]), [(self.pad, "")])
```

`tests/headless/test_work.py`:
```python
import unittest

import FreeCAD as App
from incad.features import work
from headless import util


class WorkTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Wk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_offset_plane(self):
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        k = work.PLANE
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), base=xy.Name,
                                                     offset="15 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Placement.Base.z, 15, places=6)
        self.assertEqual(k.read(self.doc, f)["offset"], "15 mm")

    def test_axis_through_an_edge(self):
        k = work.AXIS
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     edge="%s:Edge1" % self.pad.Name))
        self.doc.recompute()
        self.assertEqual(f.State, ["Up-to-date"])

    def test_point_at_a_vertex(self):
        k = work.POINT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     vertex="%s:Vertex1" % self.pad.Name))
        self.doc.recompute()
        v = self.pad.Shape.Vertexes[0].Point
        self.assertAlmostEqual((f.Placement.Base - v).Length, 0, places=6)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_patterns.py`, `tests/run_headless.sh test_work.py` → Expected: import errors.

- [ ] **Step 3: Implement**

In `InCad/incad/core/model.py` `_with_unit`: return `text` unchanged when `unit_kind == "count"` (first line of the
function: `if unit_kind == "count": return text`).

`InCad/incad/features/patterns.py`:
```python
"""Rectangular / Circular Pattern and Mirror (Inventor) = PartDesign LinearPattern (two directions, Extent mode:
probed — the second direction ignores Spacing mode), PolarPattern and Mirrored."""
from types import SimpleNamespace

from incad.core import document
from incad.features.common import Field, format_picks, parse_picks, resolve, value_param, value_text


def _origin(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def _features(doc, body, text):
    picks = [resolve(o, s)[0] for o, s in parse_picks(doc, text)]
    return picks or ([body.Tip] if body.Tip is not None else [])


def _dir_link(doc, body, text, default_role):
    picks = parse_picks(doc, text)
    if picks:
        obj, sub = resolve(*picks[0])
        return (obj, [sub])
    return (_origin(body, default_role), [""])


def _link_text(link):
    if not link or link[0] is None:
        return ""
    sub = link[1][0] if link[1] else ""
    return "%s:%s" % (link[0].Name, sub) if sub else link[0].Name


def _count(doc, f, prop, text):
    value_param(doc, f, prop, text or "2", "count")


def _length_from(doc, f, length_prop, count_prop, spacing_text, spacing_key):
    """Length = spacing × (count − 1), with spacing as its own parameter (shown in the dialog)."""
    from incad.core import model
    name = getattr(f, "_incad_" + spacing_key, None)
    spacing_name = spacing_param_from(f, spacing_key)
    if spacing_name is None:
        spacing_name = model.new_feature_parameter(doc, spacing_text or "10 mm", "length")
    elif model.parameter_text(doc, spacing_name) != spacing_text and spacing_text:
        model.set_model_parameter(doc, spacing_name, spacing_text)
    count_name = model.bound_parameter(f, count_prop)
    f.setExpression(length_prop, "%s.%s * (%s.%s - 1)" % (model.MODEL_NAME, spacing_name, model.MODEL_NAME,
                                                           count_name))
    return spacing_name


def spacing_param_from(f, key):
    """The spacing parameter is the first name in the Length formula ('InCadModel.dS * (…)')."""
    from incad.core import model
    prop = "Length" if key == "spacing1" else "Length2"
    for path, expr in f.ExpressionEngine:
        if path.lstrip(".") == prop and expr.startswith(model.MODEL_NAME + "."):
            return expr[len(model.MODEL_NAME) + 1:].split(" ", 1)[0]
    return None


def _rect_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"))
    f.Direction = _dir_link(doc, body, values.get("dir1"), "X_Axis")
    f.Mode = "Extent"
    _count(doc, f, "Occurrences", values.get("count1"))
    _length_from(doc, f, "Length", "Occurrences", values.get("spacing1") or "10 mm", "spacing1")
    if values.get("two_directions"):
        f.Direction2 = _dir_link(doc, body, values.get("dir2"), "Y_Axis")
        f.Mode2 = "Extent"
        _count(doc, f, "Occurrences2", values.get("count2"))
        _length_from(doc, f, "Length2", "Occurrences2", values.get("spacing2") or "10 mm", "spacing2")
    else:
        f.setExpression("Occurrences2", None)
        f.Occurrences2 = 1


def _rect_create(doc, body, profile, values):
    f = body.newObject("PartDesign::LinearPattern", "RectangularPattern")
    _rect_apply(doc, body, f, values)
    return f


def _rect_read(doc, f):
    from incad.core import model
    def spacing(key):
        name = spacing_param_from(f, key)
        return model.parameter_text(doc, name) if name else "10 mm"
    two = f.Occurrences2 > 1 or model.bound_parameter(f, "Occurrences2") is not None
    return {"features": format_picks([(o, "") for o in f.Originals]), "dir1": _link_text(f.Direction),
            "count1": value_text(doc, f, "Occurrences") or "2", "spacing1": spacing("spacing1"),
            "two_directions": bool(two), "dir2": _link_text(f.Direction2),
            "count2": value_text(doc, f, "Occurrences2") or "2", "spacing2": spacing("spacing2")}


def _rect_update(doc, f, values):
    _rect_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


RECT = SimpleNamespace(
    __name__="incad.features.rect_pattern", TITLE="Rectangular Pattern", ICON="rect_pattern3d",
    TYPES=("PartDesign::LinearPattern",), NEEDS_PROFILE=False, PROPS={"count1": "Occurrences", "count2": "Occurrences2"},
    PRESELECT={"features": "feature"}, spacing_param=lambda f, n: spacing_param_from(f, "spacing%d" % n),
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("dir1", "Direction 1", "pick", pick="axis"),
            Field("count1", "Count", "value_length", default="2"),
            Field("spacing1", "Spacing", "value_length", default="10 mm"),
            Field("two_directions", "Direction 2", "bool", default=False),
            Field("dir2", "Direction 2", "pick", pick="axis", show_if=("two_directions", (True,))),
            Field("count2", "Count 2", "value_length", default="2", show_if=("two_directions", (True,))),
            Field("spacing2", "Spacing 2", "value_length", default="10 mm", show_if=("two_directions", (True,)))),
    defaults=lambda doc, body, profile: {"features": "", "dir1": "", "count1": "2", "spacing1": "10 mm",
                                         "two_directions": False, "dir2": "", "count2": "2", "spacing2": "10 mm"},
    create=_rect_create, read=_rect_read, update=_rect_update, _pad_of=lambda f: f)


def _circ_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"))
    f.Axis = _dir_link(doc, body, values.get("axis"), "Z_Axis")
    f.Mode = "Extent"
    _count(doc, f, "Occurrences", values.get("count"))
    value_param(doc, f, "Angle", values.get("angle") or "360 °", "angle")


def _circ_create(doc, body, profile, values):
    f = body.newObject("PartDesign::PolarPattern", "CircularPattern")
    _circ_apply(doc, body, f, values)
    return f


def _circ_read(doc, f):
    return {"features": format_picks([(o, "") for o in f.Originals]), "axis": _link_text(f.Axis),
            "count": value_text(doc, f, "Occurrences") or "4", "angle": value_text(doc, f, "Angle") or "360°"}


def _circ_update(doc, f, values):
    _circ_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


CIRC = SimpleNamespace(
    __name__="incad.features.circ_pattern", TITLE="Circular Pattern", ICON="circ_pattern",
    TYPES=("PartDesign::PolarPattern",), NEEDS_PROFILE=False, PROPS={"count": "Occurrences", "angle": "Angle"},
    PRESELECT={"features": "feature"},
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("axis", "Axis", "pick", pick="axis"),
            Field("count", "Count", "value_length", default="4"),
            Field("angle", "Angle", "value_angle", default="360 °")),
    defaults=lambda doc, body, profile: {"features": "", "axis": "", "count": "4", "angle": "360 °"},
    create=_circ_create, read=_circ_read, update=_circ_update, _pad_of=lambda f: f)


def _mirror_apply(doc, body, f, values):
    f.Originals = _features(doc, body, values.get("features"))
    f.MirrorPlane = _dir_link(doc, body, values.get("plane"), "YZ_Plane")


def _mirror_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Mirrored", "Mirror")
    _mirror_apply(doc, body, f, values)
    return f


def _mirror_read(doc, f):
    return {"features": format_picks([(o, "") for o in f.Originals]), "plane": _link_text(f.MirrorPlane)}


def _mirror_update(doc, f, values):
    _mirror_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


MIRROR = SimpleNamespace(
    __name__="incad.features.mirror", TITLE="Mirror", ICON="mirror3d", TYPES=("PartDesign::Mirrored",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"features": "feature"},
    FIELDS=(Field("features", "Features", "picks", pick="feature"),
            Field("plane", "Mirror plane", "pick", pick="plane")),
    defaults=lambda doc, body, profile: {"features": "", "plane": ""},
    create=_mirror_create, read=_mirror_read, update=_mirror_update, _pad_of=lambda f: f)
```
Remove the unused `name = getattr(f, "_incad_" + spacing_key, None)` line and the unused `document` import when
typing the file (the spacing parameter is found through the Length formula).

`InCad/incad/features/work.py`:
```python
"""Work Plane, Work Axis, Work Point (Inventor) = PartDesign datum Plane / Line / Point (probed map modes)."""
from types import SimpleNamespace

import FreeCAD as App

from incad.features.common import Field, parse_picks, resolve, value_param, value_text


def _first(doc, text):
    picks = parse_picks(doc, text)
    if not picks:
        raise ValueError("Select what the work feature is based on")
    return resolve(*picks[0])


def _plane_apply(doc, body, f, values):
    if values.get("mode") == "three_points":
        pts = [resolve(o, s) for o, s in parse_picks(doc, values.get("points"))]
        if len(pts) != 3:
            raise ValueError("Pick three points")
        f.AttachmentSupport = pts
        f.MapMode = "ThreePointsPlane"
        return
    obj, sub = _first(doc, values.get("base"))
    f.AttachmentSupport = [(obj, sub)]
    f.MapMode = "FlatFace"
    name = value_param(doc, f, "AttachmentOffset.Base.z", values.get("offset") or "10 mm", "length") \
        if False else None
    from incad.core import model
    pname = model.bound_parameter(f, ".AttachmentOffset.Base.z") or model.bound_parameter(f, "AttachmentOffset.Base.z")
    text = values.get("offset") or "10 mm"
    if pname is None:
        pname = model.new_feature_parameter(doc, text, "length")
        f.setExpression(".AttachmentOffset.Base.z", "%s.%s" % (model.MODEL_NAME, pname))
    elif model.parameter_text(doc, pname) != text:
        model.set_model_parameter(doc, pname, text)


def _plane_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Plane", "WorkPlane")
    _plane_apply(doc, body, f, values)
    return f


def _plane_read(doc, f):
    from incad.core import model
    support = f.AttachmentSupport
    if f.MapMode == "ThreePointsPlane":
        return {"mode": "three_points", "base": "", "offset": "10 mm",
                "points": ",".join("%s:%s" % (o.Name, s[0] if isinstance(s, (tuple, list)) else s) for o, s in support)}
    obj, sub = support[0][0], support[0][1]
    sub = sub[0] if isinstance(sub, (tuple, list)) and sub else (sub or "")
    pname = model.bound_parameter(f, ".AttachmentOffset.Base.z") or model.bound_parameter(f, "AttachmentOffset.Base.z")
    return {"mode": "offset", "base": "%s:%s" % (obj.Name, sub) if sub else obj.Name, "points": "",
            "offset": model.parameter_text(doc, pname) if pname else "10 mm"}


def _plane_update(doc, f, values):
    _plane_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


PLANE = SimpleNamespace(
    __name__="incad.features.work_plane", TITLE="Work Plane", ICON="work_plane", TYPES=("PartDesign::Plane",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"base": "plane"},
    FIELDS=(Field("mode", "Type", "choice", (("offset", "Offset"), ("three_points", "3 points")), "offset"),
            Field("base", "From", "pick", pick="plane", show_if=("mode", ("offset",))),
            Field("offset", "Offset", "value_length", default="10 mm", show_if=("mode", ("offset",))),
            Field("points", "Points", "picks", pick="vertex", show_if=("mode", ("three_points",)))),
    defaults=lambda doc, body, profile: {"mode": "offset", "base": "", "offset": "10 mm", "points": ""},
    create=_plane_create, read=_plane_read, update=_plane_update, _pad_of=lambda f: f)


def _axis_apply(doc, body, f, values):
    if values.get("mode") == "two_points":
        pts = [resolve(o, s) for o, s in parse_picks(doc, values.get("points"))]
        if len(pts) != 2:
            raise ValueError("Pick two points")
        f.AttachmentSupport = pts
    else:
        f.AttachmentSupport = [_first(doc, values.get("edge"))]
    f.MapMode = "TwoPointLine"


def _axis_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Line", "WorkAxis")
    _axis_apply(doc, body, f, values)
    return f


def _axis_read(doc, f):
    items = ["%s:%s" % (o.Name, s[0] if isinstance(s, (tuple, list)) else s) for o, s in f.AttachmentSupport]
    if len(items) == 2:
        return {"mode": "two_points", "edge": "", "points": ",".join(items)}
    return {"mode": "edge", "edge": items[0] if items else "", "points": ""}


def _axis_update(doc, f, values):
    _axis_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


AXIS = SimpleNamespace(
    __name__="incad.features.work_axis", TITLE="Work Axis", ICON="work_axis", TYPES=("PartDesign::Line",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"edge": "axis"},
    FIELDS=(Field("mode", "Type", "choice", (("edge", "Through edge"), ("two_points", "2 points")), "edge"),
            Field("edge", "Edge", "pick", pick="axis", show_if=("mode", ("edge",))),
            Field("points", "Points", "picks", pick="vertex", show_if=("mode", ("two_points",)))),
    defaults=lambda doc, body, profile: {"mode": "edge", "edge": "", "points": ""},
    create=_axis_create, read=_axis_read, update=_axis_update, _pad_of=lambda f: f)


def _point_apply(doc, body, f, values):
    f.AttachmentSupport = [_first(doc, values.get("vertex"))]
    f.MapMode = "Vertex"


def _point_create(doc, body, profile, values):
    f = body.newObject("PartDesign::Point", "WorkPoint")
    _point_apply(doc, body, f, values)
    return f


def _point_read(doc, f):
    o, s = f.AttachmentSupport[0]
    return {"vertex": "%s:%s" % (o.Name, s[0] if isinstance(s, (tuple, list)) else s)}


def _point_update(doc, f, values):
    _point_apply(doc, f.getParentGeoFeatureGroup(), f, values)
    return f


POINT = SimpleNamespace(
    __name__="incad.features.work_point", TITLE="Work Point", ICON="work_point", TYPES=("PartDesign::Point",),
    NEEDS_PROFILE=False, PROPS={}, PRESELECT={"vertex": "vertex"},
    FIELDS=(Field("vertex", "Vertex", "pick", pick="vertex"),),
    defaults=lambda doc, body, profile: {"vertex": ""},
    create=_point_create, read=_point_read, update=_point_update, _pad_of=lambda f: f)
```
Remove the dead `name = value_param(... ) if False else None` statement in `_plane_apply` when typing the file.

In `InCad/incad/features/__init__.py` add `patterns, work` to the import and
`patterns.RECT, patterns.CIRC, patterns.MIRROR, work.PLANE, work.AXIS, work.POINT` to `kinds()`.

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_patterns.py`, `tests/run_headless.sh test_work.py` → Expected: all OK. Where the
datum `AttachmentOffset.Base.z` expression path differs in 1.1.3, probe the accepted path and use it (tests stay).

- [ ] **Step 5: Commit**

```bash
git add InCad/incad tests/headless/test_patterns.py tests/headless/test_work.py && git commit -m "InCad 1d-2: patterns, mirror, work features"
```

---

### Task 5: Inspect

**Files:**
- Create: `InCad/incad/core/inspect.py`, `InCad/incad/ui/info_panel.py`, `tests/headless/test_inspect.py`,
  `tests/widgets/test_info_panel.py`

**Interfaces:**
- Produces (`incad.core.inspect`): `measure(pairs) -> [(label, text)]` (pairs = resolved `(obj, sub)` picks; one
  circular edge → radius/diameter; one edge → length; one face → area; two items → minimum distance and, for two
  planar faces or two straight edges, the angle; raises `ValueError("Select …")` otherwise);
  `mass_properties(body, density_g_cm3=1.24) -> [(label, text)]` (volume, surface area, mass, bounding box).
- Produces (`incad.ui.info_panel.InfoPanel(title, rows, theme, parent)`): small closable panel; `rows()`.

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_inspect.py`:
```python
import unittest

import FreeCAD as App
from incad.core import inspect
from headless import util


class InspectTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("In")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        faces = self.pad.Shape.Faces
        self.top = "Face%d" % ([i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0])
        self.bottom = "Face%d" % ([i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z) < 1e-6][0])

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_face_area(self):
        self.assertEqual(inspect.measure([(self.pad, self.top)]), [("Area", "200 mm²")])

    def test_distance_and_angle_between_faces(self):
        rows = dict(inspect.measure([(self.pad, self.top), (self.pad, self.bottom)]))
        self.assertEqual(rows["Distance"], "10 mm")
        self.assertEqual(rows["Angle"], "0°")

    def test_nothing_selected(self):
        with self.assertRaises(ValueError):
            inspect.measure([])

    def test_mass_properties(self):
        rows = dict(inspect.mass_properties(self.body, 1.24))
        self.assertEqual(rows["Volume"], "2000 mm³")
        self.assertEqual(rows["Mass"], "2.48 g")
        self.assertEqual(rows["Size"], "20 × 10 × 10 mm")
```

`tests/widgets/test_info_panel.py`:
```python
import unittest

from widgets import qtapp
from incad.ui.info_panel import InfoPanel


class InfoPanelTest(unittest.TestCase):
    def test_rows_and_close(self):
        qtapp.app()
        p = InfoPanel("Measure", [("Distance", "10 mm"), ("Angle", "0°")], "light")
        p.show()
        self.assertEqual(p.rows(), [("Distance", "10 mm"), ("Angle", "0°")])
        p.close_button.click()
        self.assertFalse(p.isVisible())
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_inspect.py`, `tests/run_widgets.sh test_info_panel.py` → Expected: import errors.

- [ ] **Step 3: Implement**

`InCad/incad/core/inspect.py`:
```python
"""Inspect (Inventor): Measure and Mass Properties. Read-only."""
import math


def _num(value, unit, digits=3):
    text = ("%.*f" % (digits, value)).rstrip("0").rstrip(".")
    return "%s %s" % (text, unit) if unit != "°" else text + "°"


def _element(obj, sub):
    return obj.getSubObject(sub) if sub else obj.Shape


def measure(pairs):
    if not pairs:
        raise ValueError("Select a face, an edge, or two items to measure between")
    shapes = [_element(o, s) for o, s in pairs]
    if len(shapes) == 1:
        sh = shapes[0]
        if sh.ShapeType == "Face":
            return [("Area", _num(sh.Area, "mm²"))]
        if sh.ShapeType == "Edge":
            if sh.Curve.TypeId == "Part::GeomCircle":
                r = sh.Curve.Radius
                return [("Radius", _num(r, "mm")), ("Diameter", _num(2 * r, "mm"))]
            return [("Length", _num(sh.Length, "mm"))]
        raise ValueError("Select a face or an edge (or two items)")
    if len(shapes) == 2:
        rows = [("Distance", _num(shapes[0].distToShape(shapes[1])[0], "mm"))]
        a = _direction(shapes[0])
        b = _direction(shapes[1])
        if a is not None and b is not None:
            angle = math.degrees(a.getAngle(b))
            rows.append(("Angle", _num(min(angle, 180 - angle), "°")))
        return rows
    raise ValueError("Select one or two items")


def _direction(shape):
    if shape.ShapeType == "Face" and shape.Surface.TypeId == "Part::GeomPlane":
        return shape.normalAt(0, 0)
    if shape.ShapeType == "Edge" and shape.Curve.TypeId == "Part::GeomLine":
        return shape.Curve.Direction
    return None


def mass_properties(body, density_g_cm3=1.24):
    shape = body.Shape
    if shape.isNull():
        raise ValueError("The part is empty")
    bb = shape.BoundBox
    mass_g = shape.Volume / 1000.0 * density_g_cm3
    return [("Volume", _num(shape.Volume, "mm³")), ("Surface area", _num(shape.Area, "mm²")),
            ("Mass", _num(mass_g, "g", 2)),
            ("Size", "%s × %s × %s mm" % tuple(_num(v, "mm").split()[0] for v in (bb.XLength, bb.YLength, bb.ZLength)))]
```

`InCad/incad/ui/info_panel.py`:
```python
"""Small floating panel with label/value rows (Inspect results)."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes


class InfoPanel(QtWidgets.QFrame):
    def __init__(self, title, rows, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadInfoPanel")
        self._rows = list(rows)
        col = QtWidgets.QVBoxLayout(self)
        head = QtWidgets.QHBoxLayout()
        t = QtWidgets.QLabel(title)
        t.setObjectName("InCadDialogTitle")
        head.addWidget(t, 1)
        self.close_button = QtWidgets.QToolButton()
        self.close_button.setText("✕")
        self.close_button.clicked.connect(self.close)
        head.addWidget(self.close_button)
        col.addLayout(head)
        grid = QtWidgets.QGridLayout()
        for r, (label, value) in enumerate(self._rows):
            grid.addWidget(QtWidgets.QLabel(label), r, 0)
            v = QtWidgets.QLabel(value)
            v.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            grid.addWidget(v, r, 1)
        col.addLayout(grid)
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadInfoPanel {{ background: {panel}; border: 1px solid {border}; border-radius: 9px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; }}"
            " QToolButton {{ background: transparent; border: none; color: {text_dim}; }}".format(**p))

    def rows(self):
        return list(self._rows)
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_inspect.py`, `tests/run_widgets.sh test_info_panel.py` → Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/inspect.py InCad/incad/ui/info_panel.py tests/headless/test_inspect.py tests/widgets/test_info_panel.py && git commit -m "InCad 1d-2: Measure and Mass Properties"
```

---

### Task 6: Dialog selection fields and session picking

**Files:**
- Modify: `InCad/incad/ui/feature_dialog.py`, `InCad/incad/ui/feature_session.py`, `tests/widgets/test_feature_dialog.py`

**Interfaces:**
- Produces: dialog fields of kind `pick` / `picks` are checkable buttons showing `common.pick_label`; one at a time
  is the *active pick* (`active_pick() -> key|None`, `set_active_pick(key)`); `set_pick(key, text)` stores the
  value and relabels; a pick change emits `changed`. The session is a selection observer while open: selection
  changes feed the active pick field (filtered by `common.accepts(field.pick, …)`; `pick` keeps the last item,
  `picks` the whole matching selection; a wrong kind shows "Select <kind>" in the error line). At start, kinds with
  `PRESELECT` take matching items from the current selection, and the first pick field without a value becomes
  active. Profile-less kinds (`NEEDS_PROFILE = False`) start without a profile.

- [ ] **Step 1: Write the failing tests**

Append to `tests/widgets/test_feature_dialog.py`:
```python
PICK_FIELDS = (
    Field("edges", "Edges", "picks", pick="edge"),
    Field("plane", "Plane", "pick", pick="plane"),
    Field("radius", "Radius", "value_length", default="1 mm"),
)


class PickFieldsTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Fillet", "incad", PICK_FIELDS, {"edges": "", "plane": "", "radius": "1 mm"})
        self.seen = []
        self.d.changed.connect(lambda v: self.seen.append(dict(v)))

    def test_one_active_pick(self):
        self.d.set_active_pick("edges")
        self.assertEqual(self.d.active_pick(), "edges")
        self.d.field("plane").click()
        self.assertEqual(self.d.active_pick(), "plane")
        self.assertFalse(self.d.field("edges").isChecked())

    def test_set_pick_emits_and_labels(self):
        self.d.set_pick("edges", "Pad:Edge1,Pad:Edge2")
        self.assertEqual(self.seen[-1]["edges"], "Pad:Edge1,Pad:Edge2")
        self.assertEqual(self.d.field("edges").text(), "2 edges")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_feature_dialog.py` → Expected: AttributeError `set_active_pick`.

- [ ] **Step 3: Implement**

In `InCad/incad/ui/feature_dialog.py`:
- In `_make`, replace the final pick branch with:
```python
        w = QtWidgets.QPushButton("Select…", self)
        w.setObjectName("InCadPick")
        w.setCheckable(True)
        w.clicked.connect(lambda _=False, k=f.key: self._pick_clicked(k))
        return w
```
- `values()` for picks: `out[key] = w.property("pick") or ""` (unchanged for `pick`; also for `picks`).
- In `set_values` for pick kinds:
```python
                else:
                    w.setProperty("pick", value or "")
                    w.setText(self._pick_label(f, value))
```
- Add:
```python
    def _pick_label(self, f, value):
        from incad.features.common import pick_label
        return pick_label(f.pick or "item", value or "")

    def _pick_clicked(self, key):
        self.set_active_pick(key)
        self.pickRequested.emit(key)

    def set_active_pick(self, key):
        for k, f in self._fields.items():
            if f.kind in ("pick", "picks"):
                self._widgets[k].setChecked(k == key)
        self._active_pick = key

    def active_pick(self):
        return getattr(self, "_active_pick", None)

    def set_pick(self, key, text):
        w = self._widgets[key]
        w.setProperty("pick", text or "")
        w.setText(self._pick_label(self._fields[key], text))
        self._emit()

    def field_def(self, key):
        return self._fields[key]
```
- Remove `set_pick_text`/`pick_text` uses only if nothing else calls them; keep both methods (the 1d-1 test uses
  them).

In `InCad/incad/ui/feature_session.py`:
- In `start()`, after the dialog is built and before `show()`:
```python
        import FreeCADGui as Gui
        self._apply_preselection()
        first_empty = next((f.key for f in self.kind.FIELDS if f.kind in ("pick", "picks")
                            and not self.dialog.values().get(f.key)), None)
        if first_empty is not None:
            self.dialog.set_active_pick(first_empty)
        Gui.Selection.addObserver(self)
```
- In `_finish()`, before closing the dialog:
```python
        try:
            import FreeCADGui as Gui
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
```
- Add:
```python
    def _apply_preselection(self):
        import FreeCADGui as Gui
        from incad.features import common
        wanted = getattr(self.kind, "PRESELECT", {})
        if not self.creating or not wanted:
            return
        pairs = self._selection()
        for key, pick in wanted.items():
            ok = [p for p in pairs if common.accepts(pick, *p)]
            if ok:
                self.dialog.set_pick(key, common.format_picks(ok))

    def _selection(self):
        import FreeCADGui as Gui
        from incad.features import common
        pairs = []
        for sel in Gui.Selection.getSelectionEx(self.doc.Name):
            for sub in (sel.SubElementNames or ("",)):
                pairs.append(common.resolve(sel.Object, sub))
        return pairs

    # selection observer
    def addSelection(self, doc, obj, sub, pnt):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def removeSelection(self, doc, obj, sub):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def clearSelection(self, doc):
        QtCore.QTimer.singleShot(0, self._selection_changed)

    def _selection_changed(self):
        from incad.features import common
        if self._closed or self.dialog is None:
            return
        key = self.dialog.active_pick()
        if key is None:
            return
        f = self.dialog.field_def(key)
        pairs = self._selection()
        ok = [p for p in pairs if common.accepts(f.pick, *p)]
        if pairs and not ok:
            self.dialog.set_error("Select %s for %s" % (f.pick.replace("_", " "), f.label))
            return
        if not ok:
            return
        self.dialog.set_pick(key, common.format_picks(ok[-1:] if f.kind == "pick" else ok))
```

In `InCad/incad/ui/shell.py` `start_feature(kind)`: before looking for a profile add
```python
        if not getattr(kind, "NEEDS_PROFILE", True):
            self._open_session(kind, doc, document.primary_body(doc))
            return
```
and in `FeatureSession.start()` creating branch the kind's `create` receives `profile=None` (already the case).
Also `FeatureSession.start` must tolerate a `create` that raises because picks are still empty: when creating a
profile-less kind whose required picks are empty, do not call `create` yet — keep `self.feature = None`, show the
dialog, and create on the first `_preview` that has the picks (in `_preview`: `if self.feature is None:
self.feature = self.kind.create(...)` else `update`). Implement exactly that:
```python
            if self.creating:
                values = self.kind.defaults(doc, self.body, self.profile)
                if getattr(self.kind, "NEEDS_PROFILE", True):
                    self.feature = self.kind.create(doc, self.body, self.profile, values)
                    self._created_with = values.get("operation")
```
and at the start of `_preview`'s try block:
```python
            if self.feature is None:
                self.feature = self.kind.create(self.doc, self.body, self.profile, values)
                self.doc.recompute()
                self._check()
                self._label_params()
                return
```
OK must be disabled while `self.feature is None`: in `ok()`, `if self.feature is None: self.dialog.set_error("Select
what the feature needs first"); return`.

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_feature_dialog.py` → Expected: OK; `tests/run_fast.sh` OK.

- [ ] **Step 5: Commit**

```bash
git add InCad tests && git commit -m "InCad 1d-2: selection fields and picking in feature dialogs"
```

---

### Task 7: Commands, icons, layouts, GUI tests

**Files:**
- Modify: `tools/make_icons.py`, `InCad/incad/actions.py`, `InCad/incad/ui/ribbon_layout.py`,
  `InCad/incad/ui/marking_layout.py`, `InCad/incad/ui/shell.py`, `tests/widgets/test_actions.py`
- Create: `tests/gui/test_features2.py`

**Interfaces:**
- Produces: commands `feature.hole` (H), `feature.fillet` (F), `feature.chamfer`, `feature.shell`,
  `feature.rect_pattern`, `feature.circ_pattern`, `feature.mirror`, `work.plane`, `work.axis`, `work.point`,
  `inspect.measure`, `inspect.mass` (all context part); Inspect results shown in an `InfoPanel` over the 3D view
  (`Shell.info_panel`); ribbon: 3D Model ▸ Create [Extrude, Revolve, Hole], Modify [Fillet, Chamfer, Shell],
  Pattern [Rectangular, Circular, Mirror], Work Features [Plane, Axis, Point]; Inspect tab [Measure, Mass
  Properties]; marking menu: face list + Hole, Fillet; edge context E = Fillet, W = Chamfer.

- [ ] **Step 1: Write the failing tests**

In `tests/widgets/test_actions.py` extend `EXPECTED` with
`"feature.hole", "feature.fillet", "feature.chamfer", "feature.shell", "feature.rect_pattern", "feature.circ_pattern",
"feature.mirror", "work.plane", "work.axis", "work.point", "inspect.measure", "inspect.mass"` and append:
```python
    def test_hole_and_fillet_shortcuts(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual((r.get("feature.hole").shortcut, r.get("feature.fillet").shortcut), ("H", "F"))
```

`tests/gui/test_features2.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def ok():
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(700)


def top_edges(f, z):
    return ["Edge%d" % (i + 1) for i, e in enumerate(f.Shape.Edges)
            if abs(e.BoundBox.ZMin - z) < 1e-6 and abs(e.BoundBox.ZMax - z) < 1e-6]


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    sk = util.add_rect_sketch(body(), w=40, h=20)
    pad = util.add_pad(body(), sk, 10)
    body().Tip = pad
    doc().recompute()
    ST["pad"] = pad.Name
    harness.pump(300)


def test_1_fillet_takes_preselected_edges():
    pad = doc().getObject(ST["pad"])
    Gui.Selection.clearSelection()
    for e in top_edges(pad, 10):
        Gui.Selection.addSelection(doc().Name, pad.Name, e)
    commands.REGISTRY.run("feature.fillet")
    harness.pump(900)
    assert dialog() is not None
    assert dialog().field("edges").text() == "4 edges", dialog().field("edges").text()
    ok()
    assert body().Tip.TypeId == "PartDesign::Fillet", body().Tip.TypeId


def test_2_hole_from_sketch():
    fillet = body().Tip
    top = [i + 1 for i, f in enumerate(fillet.Shape.Faces)
           if abs(f.CenterOfMass.z - 10) < 1e-6 and f.Surface.TypeId == "Part::GeomPlane"][0]
    sk = body().newObject("Sketcher::SketchObject", "Holes")
    sk.AttachmentSupport = [(fillet, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(10, 10, 0), App.Vector(0, 0, 1), 1))
    sk.addGeometry(Part.Circle(App.Vector(30, 10, 0), App.Vector(0, 0, 1), 1))
    doc().recompute()
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.hole")
    harness.pump(800)
    assert dialog().active_pick() == "sketch"
    Gui.Selection.addSelection(doc().Name, sk.Name)
    harness.pump(800)
    ok()
    assert body().Tip.TypeId == "PartDesign::Hole", body().Tip.TypeId


def test_3_wrong_pick_kind_is_refused():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(800)
    tip = body().Tip
    top = [i + 1 for i, f in enumerate(tip.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    Gui.Selection.addSelection(doc().Name, tip.Name, "Face%d" % top)
    harness.pump(600)
    assert "Select edge" in dialog().error_text(), dialog().error_text()
    QTest.keyClick(dialog(), QtCore.Qt.Key_Escape)
    harness.pump(600)
    assert s().feature_session is None


def test_4_rectangular_pattern_of_the_hole():
    hole = body().Tip
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, hole.Name)
    commands.REGISTRY.run("feature.rect_pattern")
    harness.pump(900)
    w = dialog().field("spacing1")
    w.setText("5 mm")
    w.editingFinished.emit()
    harness.pump(600)
    ok()
    assert body().Tip.TypeId == "PartDesign::LinearPattern", body().Tip.TypeId


def test_5_measure_and_mass():
    tip = body().Tip
    faces = tip.Shape.Faces
    bottom = [i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, tip.Name, "Face%d" % bottom)
    commands.REGISTRY.run("inspect.measure")
    harness.pump(500)
    rows = dict(s().info_panel.rows())
    assert "Area" in rows, rows
    commands.REGISTRY.run("inspect.mass")
    harness.pump(500)
    rows = dict(s().info_panel.rows())
    assert "Mass" in rows and "Volume" in rows, rows
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("inspect.measure")
    harness.pump(400)
    assert "select" in s().status.texts()["message"].lower(), s().status.texts()


def test_6_extrude_to_face_pick_now_works():
    sk = body().newObject("Sketcher::SketchObject", "ToProfile")
    sk.AttachmentSupport = [(util.xy_plane(body()), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(-20, 0, 0), App.Vector(0, 0, 1), 2))
    plane = body().newObject("PartDesign::Plane", "Limit")
    plane.AttachmentSupport = [(util.xy_plane(body()), "")]
    plane.MapMode = "FlatFace"
    plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 7), App.Rotation())
    doc().recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(800)
    dialog().field("operation").button("new_solid").click()
    dialog().field("extent").button("to").click()
    harness.pump(500)
    dialog().field("to_face").click()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, plane.Name)
    harness.pump(800)
    assert dialog().values()["to_face"].startswith(plane.Name), dialog().values()
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)


harness.run([test_0_setup, test_1_fillet_takes_preselected_edges, test_2_hole_from_sketch,
             test_3_wrong_pick_kind_is_refused, test_4_rectangular_pattern_of_the_hole, test_5_measure_and_mass,
             test_6_extrude_to_face_pick_now_works])
```
Also in `InCad/incad/features/extrude.py` give the `to_face` field `pick="plane"` (a flat face or a plane).

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_actions.py`; announce the window; `tests/run_gui.sh tests/gui/test_features2.py`
→ Expected: failures (commands missing).

- [ ] **Step 3: Implement**

`tools/make_icons.py` — add to `ICONS`:
```python
    "hole": ('<path d="M5 12 L16 6 L27 12 L27 22 L16 28 L5 22 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
             '<ellipse cx="16" cy="12" rx="5" ry="2.6" fill="{N}"/><path d="M11 12 V19 M21 12 V19" stroke="{N}" '
             'stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "fillet": ('<path d="M5 27 V14 Q5 6 13 6 H27" fill="none" stroke="{S}" stroke-width="2.4"/>'
               '<path d="M5 27 H27 V6" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "chamfer": ('<path d="M5 27 V13 L12 6 H27" fill="none" stroke="{S}" stroke-width="2.4"/>'
                '<path d="M5 27 H27 V6" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "shell": ('<path d="M5 10 V26 H27 V10" fill="none" stroke="{S}" stroke-width="3"/>'
              '<path d="M9 10 V22 H23 V10" fill="{F}" stroke="{S}" stroke-width="1"/>'),
    "rect_pattern3d": ('<g fill="{F}" stroke="{S}" stroke-width="1.3"><path d="M3 9 L9 6 L15 9 L9 12 Z"/>'
                       '<path d="M17 9 L23 6 L29 9 L23 12 Z"/><path d="M3 21 L9 18 L15 21 L9 24 Z"/>'
                       '<path d="M17 21 L23 18 L29 21 L23 24 Z"/></g>'),
    "circ_pattern": ('<circle cx="16" cy="16" r="10" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="3 2"/>'
                     '<g fill="{F}" stroke="{S}" stroke-width="1.3"><circle cx="16" cy="6" r="3"/>'
                     '<circle cx="26" cy="16" r="3"/><circle cx="16" cy="26" r="3"/><circle cx="6" cy="16" r="3"/></g>'),
    "mirror3d": ('<path d="M16 3 V29" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 2"/>'
                 '<path d="M4 10 L10 7 L13 9 V22 L7 25 L4 23 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                 '<path d="M28 10 L22 7 L19 9 V22 L25 25 L28 23 Z" fill="none" stroke="{A}" stroke-width="1.4"/>'),
    "work_plane": '<path d="M3 20 L13 26 L29 17 L19 11 Z" fill="{D}" fill-opacity=".45" stroke="{D}" stroke-width="1.6"/><path d="M24 4 V12 M20 8 H28" stroke="{A}" stroke-width="2.2"/>',
    "work_axis": '<path d="M5 27 L23 9" stroke="{D}" stroke-width="2.4" stroke-linecap="round"/><path d="M24 2 V10 M20 6 H28" stroke="{A}" stroke-width="2.2"/>',
    "work_point": '<circle cx="14" cy="18" r="4.5" fill="{D}"/><path d="M24 4 V12 M20 8 H28" stroke="{A}" stroke-width="2.2"/>',
    "measure": ('<path d="M4 22 L22 4 L28 10 L10 28 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M9 17 L12 20 M12 14 L14 16 M15 11 L18 14 M18 8 L20 10" stroke="{S}" stroke-width="1.4"/>'),
    "mass": ('<path d="M8 12 H24 L28 28 H4 Z" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
             '<circle cx="16" cy="8" r="3.5" fill="none" stroke="{S}" stroke-width="1.8"/>'
             '<text x="16" y="25" font-family="Helvetica" font-size="9" font-weight="bold" text-anchor="middle" '
             'fill="{A}">kg</text>'),
```

`InCad/incad/actions.py` — add helpers before `def _std(`:
```python
def inspect_measure():
    from incad.ui import shell
    shell.inspect("measure")


def inspect_mass():
    from incad.ui import shell
    shell.inspect("mass")
```
and to the `commands()` list:
```python
        Command(id="feature.hole", label="Hole", icon="hole", handler=lambda: start_feature("hole"), shortcut="H",
                contexts=frozenset({"part"})),
        Command(id="feature.fillet", label="Fillet", icon="fillet", handler=lambda: start_feature("fillet"),
                shortcut="F", contexts=frozenset({"part"})),
        Command(id="feature.chamfer", label="Chamfer", icon="chamfer", handler=lambda: start_feature("chamfer"),
                contexts=frozenset({"part"})),
        Command(id="feature.shell", label="Shell", icon="shell", handler=lambda: start_feature("shell"),
                contexts=frozenset({"part"})),
        Command(id="feature.rect_pattern", label="Rectangular", icon="rect_pattern3d",
                handler=lambda: start_feature("rect_pattern"), contexts=frozenset({"part"})),
        Command(id="feature.circ_pattern", label="Circular", icon="circ_pattern",
                handler=lambda: start_feature("circ_pattern"), contexts=frozenset({"part"})),
        Command(id="feature.mirror", label="Mirror", icon="mirror3d", handler=lambda: start_feature("mirror"),
                contexts=frozenset({"part"})),
        Command(id="work.plane", label="Plane", icon="work_plane", handler=lambda: start_feature("work_plane"),
                contexts=frozenset({"part"})),
        Command(id="work.axis", label="Axis", icon="work_axis", handler=lambda: start_feature("work_axis"),
                contexts=frozenset({"part"})),
        Command(id="work.point", label="Point", icon="work_point", handler=lambda: start_feature("work_point"),
                contexts=frozenset({"part"})),
        Command(id="inspect.measure", label="Measure", icon="measure", handler=inspect_measure,
                contexts=frozenset({"part"}), tooltip="Select a face, an edge, or two items"),
        Command(id="inspect.mass", label="Mass Properties", icon="mass", handler=inspect_mass,
                contexts=frozenset({"part"})),
```
(`start_feature` looks the kind up by the last part of `__name__`: `hole`, `fillet`, `chamfer`, `shell`,
`rect_pattern`, `circ_pattern`, `mirror`, `work_plane`, `work_axis`, `work_point`.)

`InCad/incad/ui/ribbon_layout.py` — part ▸ "3D Model" becomes
`[["Sketch", ["sketch.start"]], ["Create", ["feature.extrude", "feature.revolve", "feature.hole"]],
["Modify", ["feature.fillet", "feature.chamfer", "feature.shell"]], ["Pattern", ["feature.rect_pattern",
"feature.circ_pattern", "feature.mirror"]], ["Work Features", ["work.plane", "work.axis", "work.point"]]]`, and
"Inspect": `[["Measure", ["inspect.measure", "inspect.mass"]]]`.

`InCad/incad/ui/marking_layout.py` — face `list`: `["view.zoom_selection", "feature.hole", "feature.fillet"]`;
`_EDGE`: `"E": "feature.fillet"`, `"W": "feature.chamfer"` (style_shaded/wireframe move to its list).

`InCad/incad/ui/shell.py`:
- import `from incad.ui.info_panel import InfoPanel`; `__init__`: `self.info_panel = None`; `_teardown`: close it.
- add:
```python
    def inspect(self, what):
        import FreeCADGui as Gui
        from incad.core import document, inspect
        from incad.features import common
        doc = self._doc()
        if not document.is_incad_part(doc):
            raise ValueError("Open an InCad part first")
        if what == "measure":
            pairs = [common.resolve(sel.Object, sub) for sel in Gui.Selection.getSelectionEx(doc.Name)
                     for sub in (sel.SubElementNames or ("",))]
            rows, title = inspect.measure(pairs), "Measure"
        else:
            rows, title = inspect.mass_properties(document.primary_body(doc)), "Mass Properties (PLA 1.24 g/cm³)"
        if self.info_panel is not None:
            try:
                self.info_panel.close()
            except RuntimeError:
                pass
        parent = self._mdi().viewport() if self._mdi() is not None else self.mw
        self.info_panel = InfoPanel(title, rows, self.theme, parent)
        self.info_panel.adjustSize()
        self.info_panel.move(16, parent.height() - self.info_panel.height() - 16)
        self.info_panel.show()
```
  and a module function `def inspect(what):` raising `ValueError("InCad is not active")` when inactive, else
  `_shell.inspect(what)`. (A `ValueError` from `measure` reaches the user through the registry's error report in
  the status bar — that is the "say what to select" path the test checks.)

- [ ] **Step 4: Run until they pass**

Run: `python3 tools/make_icons.py`, `tests/run_widgets.sh test_actions.py`, announce the window,
`tests/run_gui.sh tests/gui/test_features2.py` → Expected: `7 passed`. Then `tests/run_all.sh` → ALL SUITES PASSED.

- [ ] **Step 5: Commit**

```bash
git add tools InCad tests && git commit -m "InCad 1d-2: commands, ribbon, marking menu and GUI tests for the new features and Inspect"
```

---

### Task 8: Look check and docs

- [ ] **Step 1:** Probe screenshots (not committed): Fillet dialog with edges picked, Hole dialog (counterbore),
Rectangular Pattern dialog with two directions, Measure panel, in light and dark; and the ribbon's 3D Model tab.
Fix what looks wrong with a test first where possible.
- [ ] **Step 2:** README — add to the Features section:
```markdown
- H Hole (from sketch points/circles or concentric to a round edge; counterbore, countersink, through all),
  F Fillet, Chamfer, Shell (inside/outside), Rectangular / Circular Pattern, Mirror, Work Plane / Axis / Point.
- Select edges or faces first, then the command, or pick them while the dialog is open (the highlighted
  field takes the picks).
- Inspect: Measure (a face, an edge, or two items) and Mass Properties (PLA density).
```
- [ ] **Step 3:** `tests/run_all.sh` → `ALL SUITES PASSED`; commit README.
