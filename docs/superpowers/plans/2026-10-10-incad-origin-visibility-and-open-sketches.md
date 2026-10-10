# Origin Visibility, Open Sketches and Path Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide/show chosen origin elements and unused sketches (tree, 3D view, ribbon), keep open-contour sketches visible with their key points lit, and show those points on the sketches picked in the Sweep and Loft dialogs.

**Architecture:** Pure model rules in `incad.core.sketch` (open contour, key points) and `incad.core.document` (visibility policy, `InCadShown`, toggle); the tree gets a `hidden` state the browser dims; three registry commands; one small Coin marker class (`incad.ui.point_markers`) driven by the shell on refresh and by `FeatureSession` for sketch picks.

**Tech Stack:** FreeCAD 1.1.3 Python (App, Gui, Part, pivy.coin), PySide6 via `incad.qt`, unittest (`tests/run_headless.sh`, `tests/run_widgets.sh`, `tests/run_gui.sh`).

**Spec:** `docs/superpowers/specs/2026-10-10-incad-origin-visibility-and-open-sketches-design.md`

## Global Constraints

- UI text English; chat with the user in Russian.
- Run only the test files a task touches; one `tests/run_fast.sh` before the final merge (memory: run-only-affected-tests).
- Verify on the frozen real part `tests/gui/data/p2_test_reordered.FCStd` (`Sketch006`, label `Sketch7`, two open chains) before saying done.
- Never `setGeometryId`; a Sketcher tool is visible to Python only as the viewport's bitmap cursor (CLAUDE.md).
- Every registry command needs `resources/icons/light/<icon>.svg` and `dark/<icon>.svg` (widget test `test_every_command_icon_exists`), and its id in `tests/widgets/test_actions.py: EXPECTED`.
- Markers are never document objects (`_PointPick` precedent): an `SoAnnotation` added to the view's scene graph and removed on clear.

## Review Focus

1. A sketch consumed by a feature must never become visible through the toggle or `InCadShown` (Task 2 test `test_consumed_sketch_stays_hidden_whatever_the_flag`).
2. Hide / Show with a mixed selection (one visible, one hidden) must hide all, and a second press shows all (Task 2 `test_toggle_mixed_hides_all_then_shows_all`).
3. Deleting a sketch that has markers must not leave stale Coin nodes or crash on refresh (Task 5 GUI test `test_3_deleted_sketch_drops_its_markers`).
4. Entering sketch edit mode must clear the part-view markers and leaving it must bring them back (Task 5 GUI test `test_2_sketch_edit_mode_hides_the_markers`).
5. The sketch-plane pick shows all origin planes temporarily and must restore a user's hidden choice after Esc (Task 4 GUI test `test_4_plane_pick_restores_the_choice`).

---

### Task 1: Open contours and key points (core)

**Files:**
- Modify: `InCad/incad/core/sketch.py` (append after `valid_support`)
- Test: `tests/headless/test_key_points.py` (new)

**Interfaces:**
- Produces: `sketch.is_open_contour(sk) -> bool`; `sketch.key_points(sk) -> list[(kind, App.Vector)]` with kind in `"pole" | "end" | "centre"`, global coordinates, duplicates within 1e-6 merged (first kind wins).

- [ ] **Step 1: Write the failing tests**

```python
"""Key points of a sketch for the view markers: spline poles, segment ends, circle centres."""
import unittest

import FreeCAD as App
import Part
from incad.core import sketch
import util


def _sketch(doc, name="S"):
    body = doc.addObject("PartDesign::Body", "Body")
    s = body.newObject("Sketcher::SketchObject", name)
    s.AttachmentSupport = [(util.xy_plane(body), "")]
    s.MapMode = "FlatFace"
    return s


class OpenContourTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Kp")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_chain_of_lines_is_open(self):
        s = _sketch(self.doc)
        s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        s.addGeometry(Part.LineSegment(App.Vector(10, 0, 0), App.Vector(10, 5, 0)))
        self.doc.recompute()
        self.assertTrue(sketch.is_open_contour(s))

    def test_rectangle_is_not_open(self):
        body = self.doc.addObject("PartDesign::Body", "Body")
        s = util.add_rect_sketch(body)
        self.doc.recompute()
        self.assertFalse(sketch.is_open_contour(s))

    def test_empty_sketch_is_not_open(self):
        s = _sketch(self.doc)
        self.doc.recompute()
        self.assertFalse(sketch.is_open_contour(s))

    def test_construction_only_is_not_open(self):
        s = _sketch(self.doc)
        s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)), True)
        self.doc.recompute()
        self.assertFalse(sketch.is_open_contour(s))


class KeyPointsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Kp2")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    @staticmethod
    def _xy(points):
        return sorted((k, round(p.x, 3), round(p.y, 3), round(p.z, 3)) for k, p in points)

    def test_line_chain_merges_the_shared_vertex(self):
        s = _sketch(self.doc)
        s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        s.addGeometry(Part.LineSegment(App.Vector(10, 0, 0), App.Vector(10, 5, 0)))
        self.doc.recompute()
        self.assertEqual(self._xy(sketch.key_points(s)),
                         [("end", 0.0, 0.0, 0.0), ("end", 10.0, 0.0, 0.0), ("end", 10.0, 5.0, 0.0)])

    def test_arc_gives_its_ends_and_circle_its_centre(self):
        import math
        s = _sketch(self.doc)
        s.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10), 0, math.pi / 2))
        s.addGeometry(Part.Circle(App.Vector(30, 0, 0), App.Vector(0, 0, 1), 3))
        self.doc.recompute()
        self.assertEqual(self._xy(sketch.key_points(s)),
                         [("centre", 30.0, 0.0, 0.0), ("end", 0.0, 10.0, 0.0), ("end", 10.0, 0.0, 0.0)])

    def test_spline_gives_its_poles_not_its_ends(self):
        s = _sketch(self.doc)
        poles = [App.Vector(0, 0, 0), App.Vector(5, 8, 0), App.Vector(10, 0, 0)]
        s.addGeometry(Part.BSplineCurve(poles, None, None, False, 2, None, False))
        self.doc.recompute()
        self.assertEqual(self._xy(sketch.key_points(s)),
                         [("pole", 0.0, 0.0, 0.0), ("pole", 5.0, 8.0, 0.0), ("pole", 10.0, 0.0, 0.0)])

    def test_construction_geometry_is_skipped(self):
        s = _sketch(self.doc)
        s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        s.addGeometry(Part.Circle(App.Vector(50, 50, 0), App.Vector(0, 0, 1), 2), True)
        self.doc.recompute()
        self.assertEqual([k for k, _ in sketch.key_points(s)], ["end", "end"])

    def test_points_are_global(self):
        s = _sketch(self.doc)
        s.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        s.AttachmentOffset = App.Placement(App.Vector(0, 0, 7), App.Rotation())
        self.doc.recompute()
        self.assertEqual(self._xy(sketch.key_points(s)), [("end", 0.0, 0.0, 7.0), ("end", 10.0, 0.0, 7.0)])

    def test_point_geometry_is_an_end(self):
        s = _sketch(self.doc)
        s.addGeometry(Part.Point(App.Vector(3, 4, 0)))
        self.doc.recompute()
        self.assertEqual(self._xy(sketch.key_points(s)), [("end", 3.0, 4.0, 0.0)])
```

- [ ] **Step 2: Run to see them fail**

Run: `tests/run_headless.sh test_key_points.py`
Expected: FAIL / ERROR with `AttributeError: module 'incad.core.sketch' has no attribute 'is_open_contour'`

- [ ] **Step 3: Implement in `incad/core/sketch.py`** (append after `valid_support`)

```python
def is_open_contour(sk):
    """A sketch with normal geometry whose wires are all open (a path, a guide): shown in the part view."""
    try:
        wires = sk.Shape.Wires
        return bool(sk.Shape.Edges) and bool(wires) and not any(w.isClosed() for w in wires)
    except Exception:
        return False


def key_points(sk):
    """[(kind, global Vector)] the view marks on a sketch: a spline's poles ('pole'), a line's or arc's ends and
    a point ('end'), a circle's or ellipse's centre ('centre'). Construction geometry is skipped; points within
    1e-6 of an earlier one are merged (the first kind wins)."""
    pl = sk.getGlobalPlacement()
    out = []

    def add(kind, p):
        g = pl.multVec(p)
        if not any((g - q).Length < 1e-6 for _, q in out):
            out.append((kind, g))

    for i, geo in enumerate(sk.Geometry):
        try:
            if sk.getConstruction(i):
                continue
        except Exception:
            pass
        tid = geo.TypeId
        if tid == "Part::GeomBSplineCurve":
            for p in geo.getPoles():
                add("pole", p)
        elif tid in ("Part::GeomCircle", "Part::GeomEllipse"):
            add("centre", geo.Center)
        elif tid == "Part::GeomPoint":
            add("end", App.Vector(geo.X, geo.Y, geo.Z))
        elif hasattr(geo, "StartPoint") and hasattr(geo, "EndPoint"):
            add("end", geo.StartPoint)
            add("end", geo.EndPoint)
    return out
```

- [ ] **Step 4: Run the tests**

Run: `tests/run_headless.sh test_key_points.py`
Expected: `OK` (11 tests). If `Part.BSplineCurve(poles, None, None, False, 2, None, False)` raises, build it as `c = Part.BSplineCurve(); c.buildFromPoles(poles)` in the test instead.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/sketch.py tests/headless/test_key_points.py
git commit -m "Sketch core: is_open_contour and key_points (spline poles, segment ends, circle centres) for the view markers"
```

---

### Task 2: Visibility policy and toggle (core)

**Files:**
- Modify: `InCad/incad/core/document.py:84-112` (`show_result`) and append helpers
- Test: `tests/headless/test_document.py` (append a class)

**Interfaces:**
- Consumes: `sketch.is_open_contour` (Task 1), `features.common.consumers(sk)`.
- Produces: `document.SHOWN_PROP = "InCadShown"`; `document.is_unused_sketch(sk) -> bool`; `document.sketch_shown(sk) -> bool` (the policy: `InCadShown` if present else open contour); `document.origin_items(body) -> list` (the 7 origin features); `document.toggle_visibility(objects) -> bool` (new state; raises `ValueError("<Label> belongs to <Feature label>")` for a consumed sketch, `ValueError("Select a plane, an axis, the centre point or an unused sketch first")` for an empty or unsupported list); `document.set_visibility(objects, flag)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/headless/test_document.py`)

```python
class VisibilityTest(unittest.TestCase):
    """Unused sketches: open contours shown, closed ones hidden, the user's InCadShown choice wins; consumed
    sketches always hidden. Hide / Show on origin items and unused sketches."""

    def setUp(self):
        self.doc = util.new_doc("Vis")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.closed = util.add_rect_sketch(self.body, name="Closed")  # unused
        self.path = self.body.newObject("Sketcher::SketchObject", "Path")
        self.path.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.path.MapMode = "FlatFace"
        self.path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0)))
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_show_result_shows_an_open_unused_sketch_and_hides_a_closed_one(self):
        document.show_result(self.body)
        self.assertTrue(self.path.Visibility)
        self.assertFalse(self.closed.Visibility)
        self.assertFalse(self._profile().Visibility, "a consumed sketch is hidden")

    def _profile(self):
        p = self.pad.Profile
        return p[0] if isinstance(p, (tuple, list)) else p

    def test_the_users_choice_wins(self):
        document.set_visibility([self.path], False)
        document.set_visibility([self.closed], True)
        document.show_result(self.body)
        self.assertFalse(self.path.Visibility)
        self.assertTrue(self.closed.Visibility)
        self.assertFalse(getattr(self.path, document.SHOWN_PROP))
        self.assertTrue(getattr(self.closed, document.SHOWN_PROP))

    def test_consumed_sketch_stays_hidden_whatever_the_flag(self):
        prof = self._profile()
        prof.addProperty("App::PropertyBool", document.SHOWN_PROP, "InCad", "")
        setattr(prof, document.SHOWN_PROP, True)
        document.show_result(self.body)
        self.assertFalse(prof.Visibility)
        with self.assertRaises(ValueError) as cm:
            document.toggle_visibility([prof])
        self.assertIn("belongs to Pad", str(cm.exception))

    def test_toggle_mixed_hides_all_then_shows_all(self):
        xy, xz = [o for o in document.origin_items(self.body) if o.Role in ("XY_Plane", "XZ_Plane")]
        xy.Visibility, xz.Visibility = True, False
        self.assertFalse(document.toggle_visibility([xy, xz]))
        self.assertFalse(xy.Visibility or xz.Visibility)
        self.assertTrue(document.toggle_visibility([xy, xz]))
        self.assertTrue(xy.Visibility and xz.Visibility)

    def test_toggle_on_a_sketch_records_the_choice(self):
        self.assertFalse(document.toggle_visibility([self.path]))
        self.assertFalse(getattr(self.path, document.SHOWN_PROP))
        document.show_result(self.body)
        self.assertFalse(self.path.Visibility, "show_result keeps the hidden choice")

    def test_toggle_refuses_nothing_and_features(self):
        with self.assertRaises(ValueError):
            document.toggle_visibility([])
        with self.assertRaises(ValueError):
            document.toggle_visibility([self.pad])

    def test_origin_items_are_the_seven(self):
        self.assertEqual(sorted(o.Role for o in document.origin_items(self.body)),
                         ["Origin", "XY_Plane", "XZ_Plane", "X_Axis", "YZ_Plane", "Y_Axis", "Z_Axis"])
```

Add `import Part` at the top of `tests/headless/test_document.py` if it is not there.

- [ ] **Step 2: Run to see them fail**

Run: `tests/run_headless.sh test_document.py`
Expected: FAIL with `AttributeError: module 'incad.core.document' has no attribute 'set_visibility'`

- [ ] **Step 3: Implement in `incad/core/document.py`**

Replace the sketch loop at the end of `show_result` (lines 105-111):

```python
    for o in body.Group:  # profile sketches shouldn't linger in the model view after a tip move; an unused
        if o.TypeId == "Sketcher::SketchObject":  # sketch follows the user's choice, else its shape
            try:
                o.Visibility = sketch_shown(o)
            except Exception:
                pass
    return shown
```

Append:

```python
SHOWN_PROP = "InCadShown"  # a sketch the user hid or showed by hand (absent: the default of sketch_shown)
ORIGIN_TYPES = ("App::Plane", "App::Line", "App::Point")


def is_unused_sketch(sk):
    from incad.features import common
    return getattr(sk, "TypeId", "") == "Sketcher::SketchObject" and not common.consumers(sk)


def sketch_shown(sk):
    """Whether the part view shows this sketch: never when a feature uses it; else the user's InCadShown
    choice; else an open contour (a path) is shown and a closed sketch hidden."""
    from incad.core import sketch as sketches
    if not is_unused_sketch(sk):
        return False
    if SHOWN_PROP in sk.PropertiesList:
        return bool(getattr(sk, SHOWN_PROP))
    return sketches.is_open_contour(sk)


def origin_items(body):
    return list(body.Origin.OriginFeatures)


def _consumer_label(sk):
    from incad.features import common
    users = common.consumers(sk)
    return users[0].Label if users else ""


def set_visibility(objects, flag):
    """Show or hide origin items and unused sketches (a sketch remembers the choice in InCadShown)."""
    for o in objects:
        if o.TypeId == "Sketcher::SketchObject":
            if SHOWN_PROP not in o.PropertiesList:
                o.addProperty("App::PropertyBool", SHOWN_PROP, "InCad", "Shown in the part view by choice")
            setattr(o, SHOWN_PROP, bool(flag))
        o.Visibility = bool(flag)


def toggle_visibility(objects):
    """Hide / Show: hides when any target is visible, else shows them all. Returns the new state."""
    targets = []
    for o in objects:
        if o.TypeId == "Sketcher::SketchObject":
            if not is_unused_sketch(o):
                raise ValueError("%s belongs to %s" % (o.Label, _consumer_label(o)))
            targets.append(o)
        elif o.TypeId in ORIGIN_TYPES:
            targets.append(o)
    if not targets:
        raise ValueError("Select a plane, an axis, the centre point or an unused sketch first")
    flag = not any(o.Visibility for o in targets)
    set_visibility(targets, flag)
    return flag
```

- [ ] **Step 4: Run the tests**

Run: `tests/run_headless.sh test_document.py`
Expected: `OK`. If `common.consumers` of the pad's profile is empty in `test_consumed_sketch_stays_hidden_whatever_the_flag`, check `features.common._profile` handles a tuple `Profile`; the test's `prof` must be the pad's sketch.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/document.py tests/headless/test_document.py
git commit -m "Document: unused sketches follow the user's InCadShown choice (open contours shown by default); Hide / Show toggle for origin items and unused sketches"
```

---

### Task 3: Hidden rows in the tree, multi-selection in the browser

**Files:**
- Modify: `InCad/incad/core/tree.py:35-45` (`_obj_node`), `100-104` (`_origin`); `InCad/incad/core/nodes.py:9` (comment)
- Modify: `InCad/incad/ui/browser.py:117-123` (tree setup), `176-185` (`_item` colours), append `selected_names()`
- Test: `tests/headless/test_tree.py` (append), `tests/widgets/test_browser.py` (append)

**Interfaces:**
- Produces: `Node.state == "hidden"` for hidden origin items and hidden unused sketches; `Browser.selected_names() -> list[str]` (NAME_ROLE of every selected row, in tree order).

- [ ] **Step 1: Failing headless test** (append to `tests/headless/test_tree.py`; follow its existing imports)

```python
class HiddenRowsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Th")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.path = self.body.newObject("Sketcher::SketchObject", "Path")
        self.path.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.path.MapMode = "FlatFace"
        self.path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0)))
        self.doc.recompute()
        document.show_result(self.body)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _state(self, label):
        return next(n.state for _, n in nodes.flatten(tree.build(self.doc)) if n.label == label)

    def test_hidden_origin_items_and_unused_sketches_are_marked(self):
        self.assertEqual(self._state("XY Plane"), "hidden")
        xy = [o for o in document.origin_items(self.body) if o.Role == "XY_Plane"][0]
        xy.Visibility = True
        self.assertEqual(self._state("XY Plane"), "")
        self.assertEqual(self._state("Path"), "", "an open contour is shown")
        document.set_visibility([self.path], False)
        self.assertEqual(self._state("Path"), "hidden")

    def test_consumed_sketch_is_not_marked(self):
        self.assertEqual(self._state("Sketch"), "")
```

- [ ] **Step 2: Failing widget test** (append to `tests/widgets/test_browser.py`)

```python
    def test_hidden_rows_are_dimmed_and_multi_selection_reports_names(self):
        b = Browser("light")
        b.set_nodes([Node("part", "P", "Body", children=[
            Node("origin", "Origin", "Origin", children=[Node("origin_item", "XY Plane", "XY_Plane", "hidden"),
                                                         Node("origin_item", "XZ Plane", "XZ_Plane")]),
            Node("sketch", "Path", "Path", "hidden")])])
        self.assertEqual(b.item_by_label("XY Plane").foreground(0).color(), QtGui.QColor(theme.PALETTES["light"]["text_dim"]))
        self.assertEqual(b.item_by_label("Path").foreground(0).color(), QtGui.QColor(theme.PALETTES["light"]["text_dim"]))
        self.assertEqual(b.tree.selectionMode(), QtWidgets.QAbstractItemView.ExtendedSelection)
        b.item_by_label("XY Plane").setSelected(True)
        b.item_by_label("Path").setSelected(True)
        self.assertEqual(b.selected_names(), ["XY_Plane", "Path"])
```

(Use the test class's existing way of building a Browser; `Node` is `incad.core.nodes.Node`.)

- [ ] **Step 3: Run both to see them fail**

Run: `tests/run_headless.sh test_tree.py` and `tests/run_widgets.sh test_browser.py`
Expected: FAIL (`''` instead of `'hidden'`; `AttributeError: selected_names`).

- [ ] **Step 4: Implement**

`tree.py`, in `_obj_node`, after `node = Node(...)`:

```python
    if kind == "sketch" and document.is_unused_sketch(obj) and not obj.Visibility and state == "":
        node.state = "hidden"
```

`tree.py`, `_origin`:

```python
def _origin(body):
    origin = body.Origin
    items = [Node("origin_item", ROLE_LABELS.get(getattr(f, "Role", ""), f.Label), f.Name,
                  "" if f.Visibility else "hidden")
             for f in origin.OriginFeatures]
    return Node("origin", "Origin", origin.Name, children=items)
```

`nodes.py` line 9 comment: `'' | 'error' | 'suppressed' | 'rolled_back' | 'hidden'`.

`browser.py` tree setup (after `self.tree.setHeaderHidden(True)`): `self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)`.
In `_item`, after the `rolled_back`/`suppressed` branch: `elif node.state == "hidden": color = p["text_dim"]`.
Append to the class:

```python
    def selected_names(self):
        """FreeCAD names of the selected rows, tree order (Hide / Show acts on them)."""
        return [i.data(0, NAME_ROLE) for i in self._items() if i.isSelected() and i.data(0, NAME_ROLE)]
```

Check `_on_click`'s `self.tree.setCurrentItem` paths still work with extended selection (a plain click selects one row, Shift/Cmd extend; `select_row` keeps working).

- [ ] **Step 5: Run the tests**

Run: `tests/run_headless.sh test_tree.py`, `tests/run_widgets.sh test_browser.py`
Expected: `OK` both.

- [ ] **Step 6: Commit**

```bash
git add InCad/incad/core/tree.py InCad/incad/core/nodes.py InCad/incad/ui/browser.py tests/headless/test_tree.py tests/widgets/test_browser.py
git commit -m "Model tree: hidden origin items and hidden unused sketches are dimmed; rows can be multi-selected (Hide / Show acts on them)"
```

---

### Task 4: Hide / Show commands, menus, ribbon, 3D-view origin context

**Files:**
- Create: `InCad/incad/resources/icons/{light,dark}/visibility.svg`, `show_all.svg`, `hide_all.svg`
- Modify: `InCad/incad/actions.py` (new handlers near `toggle_suppress`, registration near `view.look_at`, `SHORT`)
- Modify: `InCad/incad/ui/marking_layout.py` (`part` list, `origin`, `browser`)
- Modify: `InCad/incad/ui/ribbon_layout.py:18-21` (part View group)
- Modify: `InCad/incad/ui/shell.py:827-846` (`_open_marking_menu`)
- Test: `tests/widgets/test_actions.py` (EXPECTED), `tests/gui/test_origin_visibility.py` (new)

**Interfaces:**
- Consumes: `document.toggle_visibility`, `document.set_visibility`, `document.origin_items`, `Browser.selected_names()`, `context.target()`.
- Produces: commands `view.toggle_visibility` ("Hide / Show"), `view.origin_show_all` ("Show All Origin"), `view.origin_hide_all` ("Hide All Origin").

- [ ] **Step 1: Icons.** Three SVGs, 32×32 like `show_dof.svg`, same in both theme folders (eye outline: `<path d="M3 16 C8 8 24 8 29 16 C24 24 8 24 3 16 Z" fill="none" stroke="#0a64d6" stroke-width="2"/><circle cx="16" cy="16" r="4" fill="#0a64d6"/>`; `show_all`: the eye plus a small "+" at the bottom right; `hide_all`: the eye with a diagonal line `<path d="M6 26 L26 6" stroke="#b00020" stroke-width="2"/>`). Dark theme: stroke `#5aa2ff` / `#ff6b7f`.

- [ ] **Step 2: Inventory test.** Add `"view.toggle_visibility", "view.origin_show_all", "view.origin_hide_all"` to `EXPECTED` in `tests/widgets/test_actions.py`. Run `tests/run_widgets.sh test_actions.py` → FAIL (`test_register_all`).

- [ ] **Step 3: Handlers in `actions.py`** (after `toggle_suppress`):

```python
def _visibility_targets():
    """What Hide / Show acts on: the tree's selected rows, else the row the menu was opened on, else the
    origin items and sketches selected in the 3D view."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from incad.core import context
    from incad.ui import shell
    doc = App.ActiveDocument
    if doc is None:
        raise ValueError("Open a part first")
    inst = shell.instance()
    names = inst.browser.selected_names() if inst is not None else []
    if not names and context.target():
        names = [context.target()]
    objs = [doc.getObject(n) for n in names]
    objs = [o for o in objs if o is not None]
    if not objs:
        objs = [s.Object for s in Gui.Selection.getSelectionEx(doc.Name)]
    return objs


def toggle_visibility():
    from incad.core import document, log
    from incad.ui import shell
    flag = document.toggle_visibility(_visibility_targets())
    log.report("info", "Shown" if flag else "Hidden")
    inst = shell.instance()
    if inst is not None:
        inst.schedule_refresh()


def origin_visibility(flag):
    import FreeCAD as App
    from incad.core import document
    from incad.ui import shell
    body = document.primary_body(App.ActiveDocument) if App.ActiveDocument is not None else None
    if body is None:
        raise ValueError("Open a part first")
    document.set_visibility(document.origin_items(body), flag)
    inst = shell.instance()
    if inst is not None:
        inst.schedule_refresh()
```

Register (near `view.look_at`):

```python
        Command(id="view.toggle_visibility", label="Hide / Show", icon="visibility", handler=toggle_visibility,
                contexts=frozenset({"part", "origin", "browser"}), transactional=True,
                tooltip="Hide or show the selected origin planes, axes, centre point and unused sketches"),
        Command(id="view.origin_show_all", label="Show All Origin", icon="show_all", handler=lambda: origin_visibility(True),
                contexts=frozenset({"part"}), transactional=True),
        Command(id="view.origin_hide_all", label="Hide All Origin", icon="hide_all", handler=lambda: origin_visibility(False),
                contexts=frozenset({"part"}), transactional=True),
```

`SHORT`: `"view.toggle_visibility": "Hide / Show", "view.origin_show_all": "Show All", "view.origin_hide_all": "Hide All"`.

Check `transactional=True` runs the handler inside `safe.run_safely` with the active document (grep `transactional` in `incad/core/commands.py` / `shell.py` to confirm the wrapper) so the toggle is one undo step; if `run_safely` needs a document and none is open, the "Open a part first" error must still surface.

- [ ] **Step 4: Menus and ribbon.**

`marking_layout.py`:
- `"part"`: list → `["view.zoom_all", "view.home", "view.freecad", "view.origin_show_all", "view.origin_hide_all"]`.
- `"origin"`: `{"N": "sketch.start", "S": "view.toggle_visibility", "list": ["sketch.start", "view.toggle_visibility"]}`.
- `"browser"`: list → `["browser.edit", "sketch.start", "browser.delete", "view.toggle_visibility"]`.

`ribbon_layout.py` part View group: `["Visual Style", ["view.style_shaded", "view.style_wireframe", ["view.section", "view.section_points"], ["view.toggle_visibility", "view.origin_show_all", "view.origin_hide_all"]]]`.

`shell._open_marking_menu`: after `info = ...`, before `context.set_target(None)`:

```python
        if info:
            obj = doc.getObject(info["Object"])
            if obj is not None and obj.TypeId in document.ORIGIN_TYPES:
                context.set_target(obj.Name)
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(doc.Name, obj.Name)
                return self._show_marking_menu("origin", global_pos, flick)
```

- [ ] **Step 5: GUI test `tests/gui/test_origin_visibility.py`** (copy the header of `tests/gui/test_sketch_tools.py`; `harness.run([...])` at the end)

```python
def _xy():
    from incad.core import document
    return [o for o in document.origin_items(document.primary_body(App.ActiveDocument)) if o.Role == "XY_Plane"][0]


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    from incad.core import document
    import headless.util as util
    body, pad = util.padded_part(App.ActiveDocument, 10, incad=False)  # file.new made the part; add a pad to it
    App.ActiveDocument.recompute()
    shell.instance().schedule_refresh()
    harness.pump(500)


def test_1_tree_menu_hide_show_on_a_plane():
    sh = shell.instance()
    xy = _xy()
    assert not xy.Visibility
    sh.browser.markingMenuRequested.emit(xy.Name, QtCore.QPoint(400, 400))
    harness.pump(300)
    assert sh.menu_kind == "origin", sh.menu_kind
    sh.marking_menu.close()
    commands.REGISTRY.run("view.toggle_visibility")  # the target is the row the menu was opened on
    harness.pump(400)
    assert xy.Visibility
    assert sh.browser.item_by_label("XY Plane").data(0, STATE_ROLE) == ""
    commands.REGISTRY.run("view.toggle_visibility")
    harness.pump(400)
    assert not xy.Visibility
    assert sh.browser.item_by_label("XY Plane").data(0, STATE_ROLE) == "hidden"


def test_2_two_selected_axes_toggle_together():
    sh = shell.instance()
    from incad.core import context
    context.set_target(None)
    sh.browser.item_by_label("X Axis").setSelected(True)
    sh.browser.item_by_label("Y Axis").setSelected(True)
    commands.REGISTRY.run("view.toggle_visibility")
    harness.pump(400)
    doc = App.ActiveDocument
    assert doc.getObject("X_Axis").Visibility and doc.getObject("Y_Axis").Visibility
    assert not doc.getObject("Z_Axis").Visibility


def test_3_show_all_and_hide_all():
    from incad.core import document
    commands.REGISTRY.run("view.origin_show_all")
    harness.pump(300)
    items = document.origin_items(document.primary_body(App.ActiveDocument))
    assert all(o.Visibility for o in items)
    commands.REGISTRY.run("view.origin_hide_all")
    harness.pump(300)
    assert not any(o.Visibility for o in items)


def test_4_plane_pick_restores_the_choice():
    sh = shell.instance()
    xy = _xy()
    from incad.core import document
    document.set_visibility([xy], True)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    assert all(o.Visibility for o in document.origin_items(document.primary_body(App.ActiveDocument)))
    sh._on_escape()
    harness.pump(600)
    items = document.origin_items(document.primary_body(App.ActiveDocument))
    assert xy.Visibility and not any(o.Visibility for o in items if o is not xy)


def test_5_consumed_sketch_is_refused():
    from incad.core import context
    sh = shell.instance()
    sh.browser.tree.clearSelection()
    context.set_target("Sketch")
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert not r.ok and "belongs to Pad" in r.error, (r.ok, r.error)
    assert not App.ActiveDocument.getObject("Sketch").Visibility


def test_6_right_click_on_a_visible_plane_in_the_view_opens_the_origin_menu():
    from incad.core import document
    sh = shell.instance()
    xy = _xy()
    document.set_visibility([xy], True)
    harness.pump(300)
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(300)
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    sx, sy = view.getPointOnViewport(App.Vector(-15, 15, 0))  # on the XY plane, off the pad
    dpr = vp.devicePixelRatioF()
    pos = QtCore.QPointF(sx / dpr, vp.height() - sy / dpr)
    _send("press", pos, QtCore.Qt.RightButton, QtCore.Qt.RightButton)
    _send("release", pos, QtCore.Qt.RightButton, QtCore.Qt.NoButton)
    harness.pump(300)
    assert sh.menu_kind == "origin", sh.menu_kind
    sh.marking_menu.close()
    harness.pump(200)
```

`_send` as in `tests/gui/test_sketch_tools.py`; `STATE_ROLE` from `incad.ui.browser`. If `REGISTRY.run` does not return a result object, use `try/except ValueError` with the message check. In test_6, if `getObjectInfo` at that point hits nothing (the plane's drawn size may be small), pick a point nearer the origin such as `(-3, 3, 0)` and assert the kind.

- [ ] **Step 6: Run** `tests/run_widgets.sh test_actions.py test_marking_layout.py` and `tests/run_gui.sh tests/gui/test_origin_visibility.py tests/gui/test_nav.py`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add InCad/incad/actions.py InCad/incad/ui/marking_layout.py InCad/incad/ui/ribbon_layout.py InCad/incad/ui/shell.py InCad/incad/resources/icons tests/widgets/test_actions.py tests/gui/test_origin_visibility.py
git commit -m "Hide / Show for chosen origin items and unused sketches (tree, 3D view, menus, ribbon); Show All / Hide All Origin"
```

---

### Task 5: Point markers on shown unused sketches

**Files:**
- Create: `InCad/incad/ui/point_markers.py`
- Modify: `InCad/incad/ui/shell.py` (`_refresh` after `self.browser.set_nodes(...)`; `_close_document`/view teardown)
- Test: `tests/gui/test_open_sketches.py` (new)

**Interfaces:**
- Consumes: `sketch.key_points`, `document.sketch_shown`.
- Produces: `PointMarkers(view, theme)` with `set(points: list[(kind, Vector)])`, `clear()`, `remove()`, attribute `count`; `Shell.sketch_markers: dict[view -> PointMarkers]`; `Shell._sync_sketch_markers(doc, editing)`.

- [ ] **Step 1: `incad/ui/point_markers.py`**

```python
"""Small points drawn on the 3D view (never in the document) at a sketch's key points: spline poles, segment
ends, circle centres. Not clickable: FreeCAD never sees them in picks (an SoAnnotation outside the document)."""
from incad.ui import theme as themes

SIZE = 9
KIND_COLOR = {"pole": "accent", "centre": "accent", "end": "marker_end"}


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class PointMarkers:
    def __init__(self, view, theme="light"):
        from pivy import coin
        self.view, self.theme, self.count = view, theme, 0
        self.node = coin.SoAnnotation()
        self.node.setName("InCadSketchPoints")
        view.getSceneGraph().addChild(self.node)

    def set(self, points):
        from pivy import coin
        self.clear()
        p = themes.PALETTES[self.theme]
        for kind in ("end", "pole", "centre"):
            pts = [v for k, v in points if k == kind]
            if not pts:
                continue
            sep = coin.SoSeparator()
            color = coin.SoBaseColor()
            color.rgb.setValue(*_rgb(p[KIND_COLOR[kind]]))
            style = coin.SoDrawStyle()
            style.pointSize = SIZE
            coords = coin.SoCoordinate3()
            coords.point.setValues(0, len(pts), [(v.x, v.y, v.z) for v in pts])
            for n in (color, style, coords, coin.SoPointSet()):
                sep.addChild(n)
            self.node.addChild(sep)
        self.count = len(points)

    def clear(self):
        self.node.removeAllChildren()
        self.count = 0

    def remove(self):
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass
```

Add `marker_end="#e67e22"` to the light palette and `marker_end="#f39c4a"` to the dark one in `theme.PALETTES` (same orange as `CreateLineColor`).

- [ ] **Step 2: Shell integration.** In `_refresh`, right after `self.browser.set_nodes(tree.build(doc))`:

```python
        self._sync_sketch_markers(doc if is_part else None, editing)
```

Add to `Shell`:

```python
    def _sync_sketch_markers(self, doc, editing):
        """Key points of every shown unused sketch, on the part view; none while a sketch is edited or a feature
        dialog shows its own."""
        import FreeCADGui as Gui
        from incad.core import document, sketch as sketches
        from incad.ui.point_markers import PointMarkers
        if not hasattr(self, "sketch_markers"):
            self.sketch_markers = {}
        points = []
        view = None
        if doc is not None and editing is None and self.feature_session is None:
            gdoc = Gui.getDocument(doc.Name)
            view = gdoc.ActiveView if gdoc is not None else None
            body = document.primary_body(doc)
            if body is not None and view is not None:
                for sk in body.Group:
                    if sk.TypeId == "Sketcher::SketchObject" and document.sketch_shown(sk):
                        try:
                            points.extend(sketches.key_points(sk))
                        except Exception as e:
                            log.logger().warning("Key points of %s: %s", sk.Name, e)
        for v, m in list(self.sketch_markers.items()):
            if v is not view:
                m.remove()
                del self.sketch_markers[v]
        if view is None:
            return
        try:
            m = self.sketch_markers.get(view)
            if m is None:
                m = self.sketch_markers[view] = PointMarkers(view, self.theme)
            m.set(points)
        except Exception as e:
            log.logger().warning("Sketch markers: %s", e)
```

`sketch_markers` keys are view objects: `Gui.Document.ActiveView` returns a new Python wrapper each call, so key by `doc.Name` instead and keep `(view, markers)`: `self.sketch_markers = {doc.Name: (view, m)}`; remove entries whose document is gone (`doc.Name not in App.listDocuments()`). Rewrite the dict handling accordingly before running the test. Also clear them in the theme toggle (recreate with the new theme: just `remove()` all and let the next `_refresh` rebuild) and in `_release_python_markers` at shutdown (`shell.py:2436`, add the sketch markers' `remove()` there).

- [ ] **Step 3: GUI test `tests/gui/test_open_sketches.py`**

```python
def _markers():
    sh = shell.instance()
    entry = sh.sketch_markers.get(App.ActiveDocument.Name)
    return entry[1] if entry else None


def test_0_part_with_a_path():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    from incad.core import document
    import Part
    body = document.primary_body(App.ActiveDocument)
    import headless.util as util
    sk = body.newObject("Sketcher::SketchObject", "Path")
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0)))
    poles = [App.Vector(30, 0, 0), App.Vector(40, 10, 0), App.Vector(50, 0, 0)]
    c = Part.BSplineCurve(); c.buildFromPoles(poles)
    sk.addGeometry(c)
    App.ActiveDocument.recompute()
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(600)
    assert sk.Visibility, "an open contour stays visible"
    m = _markers()
    assert m is not None and m.count == 4, (m and m.count)  # 0,0  30,0 (shared)  40,10  50,0


def test_1_hidden_path_has_no_markers():
    from incad.core import document
    sk = App.ActiveDocument.getObject("Path")
    document.set_visibility([sk], False)
    shell.instance().schedule_refresh()
    harness.pump(500)
    assert _markers().count == 0
    document.set_visibility([sk], True)
    shell.instance().schedule_refresh()
    harness.pump(500)
    assert _markers().count == 4


def test_2_sketch_edit_mode_hides_the_markers():
    sh = shell.instance()
    Gui.ActiveDocument.setEdit("Path")
    harness.pump(800)
    assert _markers() is None or _markers().count == 0
    Gui.ActiveDocument.resetEdit()
    harness.pump(800)
    assert _markers().count == 4


def test_3_deleted_sketch_drops_its_markers():
    App.ActiveDocument.removeObject("Path")
    App.ActiveDocument.recompute()
    shell.instance().schedule_refresh()
    harness.pump(500)
    assert _markers().count == 0


def test_4_real_part_sketch7_is_shown_with_its_ends():
    import os
    path = os.environ.get("INCAD_REAL_PART", os.path.join(os.environ["INCAD_REPO"], "tests", "gui", "data", "p2_test_reordered.FCStd"))
    App.openDocument(path)
    harness.pump(1500)
    sk = App.ActiveDocument.getObject("Sketch006")
    assert sk.Visibility, "Sketch7 (two open chains) is shown"
    assert _markers().count >= 4
```

If the Sketcher's edit mode (`setEdit`) is not the way InCad opens a sketch, use `commands.REGISTRY.run("sketch.edit")`-equivalent from `test_sketch.py` (grep how `test_sketch.py` enters and leaves a sketch) so the shell's `editing` is set.

- [ ] **Step 4: Run** `tests/run_gui.sh tests/gui/test_open_sketches.py tests/gui/test_features.py`
Expected: PASS; `test_features.py` guards that showing unused open sketches did not break feature creation.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/point_markers.py InCad/incad/ui/shell.py InCad/incad/ui/theme.py tests/gui/test_open_sketches.py
git commit -m "Part view: unused open sketches stay visible with their key points marked (spline poles, segment ends, circle centres)"
```

---

### Task 6: Points on the sketches picked in Sweep and Loft

**Files:**
- Modify: `InCad/incad/ui/feature_session.py` (`start`, `_selection_changed` end, `_changed`, `_finish`)
- Test: `tests/gui/test_open_sketches.py` (append two tests)

**Interfaces:**
- Consumes: `PointMarkers`, `sketch.key_points`, `common.parse_picks`.
- Produces: `FeatureSession._sync_sketch_markers()`; attribute `_markers` (PointMarkers or None).

- [ ] **Step 1: Failing GUI tests** (append to `tests/gui/test_open_sketches.py`, before `harness.run`; register them)

```python
def test_5_sweep_dialog_marks_the_picked_path_and_profile():
    from incad.core import document
    import Part, headless.util as util
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(App.ActiveDocument)
    path = body.newObject("Sketcher::SketchObject", "Path")
    path.AttachmentSupport = [(util.xy_plane(body), "")]; path.MapMode = "FlatFace"
    path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(40, 0, 0)))
    prof = body.newObject("Sketcher::SketchObject", "Prof")
    prof.AttachmentSupport = [(next(o for o in body.Origin.OriginFeatures if o.Role == "YZ_Plane"), "")]; prof.MapMode = "FlatFace"
    prof.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 3))
    App.ActiveDocument.recompute()
    sh = shell.instance()
    commands.REGISTRY.run("feature.sweep")
    harness.pump(600)
    fs = sh.feature_session
    assert fs is not None
    fs.dialog.set_pick("profile", "Prof")
    fs.dialog.set_pick("path", "Path")
    harness.pump(900)
    assert prof.Visibility and path.Visibility, "picked sketches are shown for the dialog"
    assert fs._markers is not None and fs._markers.count == 3, fs._markers and fs._markers.count  # centre + 2 ends
    assert _markers() is None or _markers().count == 0, "the part-view markers wait while the dialog shows its own"
    fs.cancel()
    harness.pump(600)
    assert sh.feature_session is None


def test_6_loft_dialog_marks_every_section():
    from incad.core import document
    import Part
    body = document.primary_body(App.ActiveDocument)
    sh = shell.instance()
    top = body.newObject("Sketcher::SketchObject", "Top")
    top.AttachmentSupport = [(next(o for o in body.Origin.OriginFeatures if o.Role == "YZ_Plane"), "")]; top.MapMode = "FlatFace"
    top.AttachmentOffset = App.Placement(App.Vector(0, 0, 20), App.Rotation())
    top.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
    App.ActiveDocument.recompute()
    commands.REGISTRY.run("feature.loft")
    harness.pump(600)
    fs = sh.feature_session
    fs.dialog.set_pick("sections", "Prof,Top")
    harness.pump(900)
    assert fs._markers.count == 2, fs._markers.count
    fs.cancel()
    harness.pump(600)
```

(Check `dialog.set_pick`'s exact signature in `feature_dialog.py` and the picks text format `common.format_picks`; adjust the strings.)

- [ ] **Step 2: Run** `tests/run_gui.sh tests/gui/test_open_sketches.py` → the two new tests FAIL (`AttributeError: _markers`).

- [ ] **Step 3: Implement in `feature_session.py`**

In `__init__`: `self._markers = None`.
Add:

```python
    def _sync_sketch_markers(self):
        """The sketches picked in `sketch` fields (Sweep's profile and path, Loft's sections) are shown with
        their key points while the dialog is open."""
        import FreeCADGui as Gui
        from incad.core import sketch as sketches
        from incad.features import common
        from incad.ui.point_markers import PointMarkers
        if self._closed or self.dialog is None:
            return
        picked = []
        for f in self.kind.FIELDS:
            if getattr(f, "pick", None) == "sketch":
                for obj, _ in common.parse_picks(self.doc, self.dialog.values().get(f.key)):
                    if obj.TypeId == "Sketcher::SketchObject" and obj not in picked:
                        picked.append(obj)
        for sk in picked:
            if not sk.Visibility:
                self._saved_sketches = getattr(self, "_saved_sketches", []) + [sk]
                self._set_visible(sk, True)
        points = []
        for sk in picked:
            try:
                points.extend(sketches.key_points(sk))
            except Exception:
                pass
        if not points:
            if self._markers is not None:
                self._markers.clear()
            return
        if self._markers is None:
            gdoc = Gui.getDocument(self.doc_name)
            view = gdoc.ActiveView if gdoc is not None else None
            if view is None:
                return
            self._markers = PointMarkers(view, self.theme)
        self._markers.set(points)
```

Call it at the end of `_changed` (after `self._timer.start()`) and once at the end of `start()`. In `_finish`, right after `self._show_base(False)`:

```python
        for sk in getattr(self, "_saved_sketches", []):
            self._set_visible(sk, False)
        self._saved_sketches = []
        if self._markers is not None:
            self._markers.remove()
            self._markers = None
```

(`self.theme` exists in `__init__`'s parameters; keep it as `self.theme = theme` if it is not stored yet.) After `_finish`, the shell's `_refresh` restores the part-view markers (`feature_session` is None again) and `show_result` restores the sketches' visibility policy on the next tip change; make `_finish` call `document.show_result(self.body)` only if it already does (grep) — otherwise set the saved sketches back to `document.sketch_shown(sk)` instead of `False`.

- [ ] **Step 4: Run** `tests/run_gui.sh tests/gui/test_open_sketches.py tests/gui/test_features2.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/feature_session.py tests/gui/test_open_sketches.py
git commit -m "Sweep and Loft dialogs: the picked sketches are shown with their key points while the dialog is open"
```

---

### Task 7: Real part check, full run, finish

- [ ] **Step 1:** `tests/run_gui.sh tests/gui/test_open_sketches.py` already opens the frozen part in `test_4`; also open it by hand in a headless script and print `document.sketch_shown` for every sketch: only `Sketch006` True.
- [ ] **Step 2:** `tests/run_fast.sh` once (widgets + headless), then `tests/run_gui.sh tests/gui/test_origin_visibility.py tests/gui/test_open_sketches.py tests/gui/test_sketch_tools.py tests/gui/test_nav.py tests/gui/test_features.py tests/gui/test_pattern_real_part.py`.
- [ ] **Step 3:** Update `CLAUDE.md` Sketcher facts with one line: unused sketches follow `InCadShown` (document.sketch_shown); view markers live in `incad.ui.point_markers`.
- [ ] **Step 4:** Spec status line → "implemented"; commit; tell the user to restart FreeCAD and try: tree right-click on XY Plane → Hide / Show; draw an open spline path, see its poles; Sweep dialog.
