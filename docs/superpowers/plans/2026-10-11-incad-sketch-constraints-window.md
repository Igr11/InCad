# Sketch Constraints Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In a sketch, list, filter, highlight and delete constraints, from a ribbon window and from the right-click menu on a line or point.

**Architecture:** A pure model module (`incad/core/sketch_constraints.py`: rows, naming, filter, guards, delete) under a Qt
overlay panel (`incad/ui/constraints_panel.py`, the Section panel's pattern) that the shell opens, keeps in step with the
sketch selection and closes when the sketch ends. The marking menu gains extra callable items for the per-constraint
"Delete …" entries.

**Tech Stack:** FreeCAD 1.1.3 Sketcher Python API, PySide6 (`incad.qt`), unittest (no pytest in FreeCAD's Python).

**Spec:** `docs/superpowers/specs/2026-10-11-incad-sketch-constraints-window-design.md`

## Global Constraints

- UI text English, sentence-free labels as in the spec: "Constraints — <sketch label>", "Delete selected", "Select all",
  "Delete <Type> (<other>)", "Delete all constraints (N)", "Constraints…".
- Element names: "Line N" / "Arc N" / "Circle N" / "Ellipse N" / "Spline N" / "Point N" where N = the Edge number
  (geometry index + 1, what FreeCAD's `EdgeN` says); points of a curve "Line 3 start" / "end" / "centre";
  `-1` = "X axis" (its point 1 = "Origin"), `-2` = "Y axis", `-3…` = "Projected edge 1…"; construction adds " (construction)".
- Deletes go through `safe.run_safely("Delete Constraints", …)`: one undo step.
- Pattern ties (`sketch.is_pattern_name`) are never deleted; a dimension referenced by another expression is never deleted.
- Tests: `tests/run_headless.sh <file>`, `tests/run_widgets.sh <file>`, `tests/run_gui.sh tests/gui/<file>` (tell the user
  to keep hands off). Run only the affected files; the full suites once before the final commit.
- Restart FreeCAD to load code changes (the installed module is a symlink to the repo).

## Review Focus

1. A constraint whose tie is a projected edge or an axis (`First = -1/-2/-3…`): rows must name it, never crash. → Task 1 test.
2. Indices after deleting several rows: deleting rows 2 and 5 together must remove exactly those (highest first). → Task 2 test.
3. A constraint deleted outside the window (Delete key, undo) while the window is open: the list must refresh, not keep
   stale rows that delete the wrong constraint. → Task 5 refreshes on every sketch change and re-reads rows by index
   before deleting; GUI test deletes via the Delete key with the window open.
4. A redundant / conflicting sketch (FreeCAD refuses to solve): rows still list and delete works. → Task 2 test.
5. Right-click on empty sketch space or on a point with no constraints: no extra entries, menu still opens. → Task 5 GUI test.

---

## File structure

- Create `InCad/incad/core/sketch_constraints.py` — rows, element naming, filter by picked elements, guards, delete.
- Create `InCad/incad/ui/constraints_panel.py` — the window (list, filter header, buttons), no FreeCAD imports.
- Modify `InCad/incad/ui/marking_menu.py` — extra items `(label, icon, callable)`.
- Modify `InCad/incad/ui/shell.py` — open/close/refresh the panel, selection follow, highlight, delete, dynamic menu items.
- Modify `InCad/incad/actions.py`, `InCad/incad/ui/ribbon_layout.py`, `InCad/incad/ui/marking_layout.py`,
  `tools/make_icons.py` (+ generated `InCad/resources/icons/*/constraints_window.svg`) — the command and its icon.
- Tests: `tests/headless/test_sketch_constraints.py`, `tests/widgets/test_constraints_panel.py`,
  `tests/widgets/test_marking_menu.py` (add), `tests/widgets/test_actions.py` (expected ids), `tests/gui/test_constraints_window.py`.

---

### Task 1: Constraint rows, names and the filter

**Files:**
- Create: `InCad/incad/core/sketch_constraints.py`
- Test: `tests/headless/test_sketch_constraints.py`

**Interfaces:**
- Produces:
  - `Row` dataclass: `index: int, name: str, type: str, ties: list[tuple[int, int]], text: str, value: str, owner: str`
  - `rows(sk) -> list[Row]`
  - `element_name(sk, geo, pos) -> str`
  - `for_elements(sk, subs: list[str]) -> list[Row]` (subs are FreeCAD names: `Edge3`, `Vertex2`, `ExternalEdge1`, `H_Axis`, `V_Axis`, `RootPoint`; empty → all rows)

- [ ] **Step 1: Write the failing tests**

```python
"""Sketch constraints listed for the Constraints window: what each one is, what it ties, filtered by a pick."""
import unittest

import FreeCAD as App
import Part
import Sketcher
from incad.core import document, sketch_constraints as sc
from headless import util


def rect(sk):
    """A 60 x 45 rectangle: Lines 1-4, four corner coincidents, H/V, two dimensions d1, d2."""
    p = [App.Vector(0, 0, 0), App.Vector(60, 0, 0), App.Vector(60, 45, 0), App.Vector(0, 45, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(p[i], p[(i + 1) % 4]))
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    sk.addConstraint(Sketcher.Constraint("Horizontal", 0))
    sk.addConstraint(Sketcher.Constraint("Horizontal", 2))
    sk.addConstraint(Sketcher.Constraint("Vertical", 1))
    sk.addConstraint(Sketcher.Constraint("Vertical", 3))
    i = sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 60.0))
    sk.renameConstraint(i, "d1")
    i = sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 45.0))
    sk.renameConstraint(i, "d2")


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sc")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sk")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        rect(self.sk)
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_every_constraint_is_a_row_in_order(self):
        rs = sc.rows(self.sk)
        self.assertEqual([r.index for r in rs], list(range(10)))
        self.assertEqual([r.type for r in rs[:6]], ["Coincident"] * 4 + ["Horizontal"] * 2)
        self.assertEqual(rs[0].text, "Line 1 end ↔ Line 2 start")
        self.assertEqual(rs[4].text, "Line 1")
        self.assertEqual((rs[8].type, rs[8].name, rs[8].value), ("Horizontal Distance", "d1", "60 mm"))

    def test_a_formula_shows_as_written(self):
        self.sk.setExpression("Constraints.d2", "d1 / 2")
        self.doc.recompute()
        self.assertEqual(sc.rows(self.sk)[9].value, "d1 / 2")

    def test_axes_origin_projected_and_construction_are_named(self):
        sk = self.sk
        sk.addGeometry(Part.Point(App.Vector(10, 10, 0)), True)  # Point 5 (construction)
        sk.addConstraint(Sketcher.Constraint("PointOnObject", 4, 1, -1))
        sk.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        self.assertEqual(sc.element_name(sk, 4, 1), "Point 5 (construction)")
        self.assertEqual(sc.element_name(sk, -1, 0), "X axis")
        self.assertEqual(sc.element_name(sk, -1, 1), "Origin")
        self.assertEqual(sc.element_name(sk, -2, 0), "Y axis")
        self.assertEqual(sc.element_name(sk, -3, 0), "Projected edge 1")
        rs = sc.rows(sk)
        self.assertEqual(rs[-2].text, "Point 5 (construction) ↔ X axis")
        self.assertEqual(rs[-1].text, "Line 1 start ↔ Origin")

    def test_filter_by_an_edge_and_by_a_vertex(self):
        self.assertEqual([r.index for r in sc.for_elements(self.sk, ["Edge1"])], [0, 3, 4, 8])
        v = self.sk.getGeoVertexIndex  # which Vertex is Line 2's start: find it, FreeCAD numbers vertices itself
        name = next("Vertex%d" % (i + 1) for i in range(8) if v(i) == (1, 1))
        self.assertEqual([r.index for r in sc.for_elements(self.sk, [name])], [0, 9])
        self.assertEqual(len(sc.for_elements(self.sk, [])), 10)

    def test_a_pattern_tie_names_its_pattern(self):
        i = self.sk.addConstraint(Sketcher.Constraint("Equal", 0, 2))
        self.sk.renameConstraint(i, "pat3_0")
        self.assertEqual(sc.rows(self.sk)[i].owner, "Pattern3")
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_headless.sh test_sketch_constraints.py`
Expected: ERROR `ModuleNotFoundError: No module named 'incad.core.sketch_constraints'`

- [ ] **Step 3: Write the implementation**

```python
"""The constraints of a sketch as the Constraints window lists them: what each one is, what it ties (in the
user's words), its value; filtered by picked lines and points; refused or deleted. Pure model logic: no Qt."""
import dataclasses
import math

from incad.core import sketch as sketches, sketch_patterns as sp

UNDEF = -2000  # Sketcher's GeoUndef
_TYPES = {"PointOnObject": "Point on Object", "Block": "Fix", "DistanceX": "Horizontal Distance",
          "DistanceY": "Vertical Distance", "InternalAlignment": "Internal"}
_KINDS = (("Part::GeomLineSegment", "Line"), ("Part::GeomArcOfCircle", "Arc"), ("Part::GeomCircle", "Circle"),
          ("Part::GeomArcOfEllipse", "Arc"), ("Part::GeomEllipse", "Ellipse"), ("Part::GeomBSplineCurve", "Spline"),
          ("Part::GeomPoint", "Point"))
_POS = {1: "start", 2: "end", 3: "centre"}


@dataclasses.dataclass
class Row:
    index: int
    name: str
    type: str
    ties: list
    text: str
    value: str
    owner: str


def element_name(sk, geo, pos=0):
    if geo == -1:
        return "Origin" if pos == 1 else "X axis"
    if geo == -2:
        return "Y axis"
    if geo <= -3:
        return "Projected edge %d" % (-geo - 2)
    g = sk.Geometry[geo]
    kind = next((k for t, k in _KINDS if g.TypeId == t), "Curve")
    name = "%s %d" % (kind, geo + 1)
    if pos in _POS and kind != "Point":
        name += " " + _POS[pos]
    if sk.getConstruction(geo):
        name += " (construction)"
    return name


def _ties(c):
    out = []
    for geo, pos in ((c.First, int(c.FirstPos)), (c.Second, int(c.SecondPos)), (c.Third, int(c.ThirdPos))):
        if geo != UNDEF:
            out.append((geo, pos))
    return out


def _value(sk, c):
    if c.Type not in sketches.DIMENSIONAL:
        return ""
    if c.Name:
        for path, expr in sk.ExpressionEngine or []:
            if path.lstrip(".") == "Constraints." + c.Name:
                from incad.core import model
                return model.to_display(sk.Document, expr)
    if c.Type == "Angle":
        return "%g°" % round(math.degrees(c.Value), 6)
    return "%g mm" % round(c.Value, 6)


def _owner(c):
    if sketches.is_pattern_name(c.Name):
        return "Pattern" + c.Name[len(sketches.PATTERN_PREFIX):].split("_")[0]
    return ""


def rows(sk):
    out = []
    for i, c in enumerate(sk.Constraints):
        ties = _ties(c)
        out.append(Row(i, c.Name or "", _TYPES.get(c.Type, c.Type), ties,
                       " ↔ ".join(element_name(sk, g, p) for g, p in ties), _value(sk, c), _owner(c)))
    return out


def for_elements(sk, subs):
    """Rows that touch any picked element: an edge matches its geometry at any point, a vertex only that point."""
    picks = []
    for sub in subs or ():
        try:
            picks.append(sp.element(sk, sub) + (sub.startswith(("Edge", "ExternalEdge", "H_Axis", "V_Axis")),))
        except (ValueError, IndexError):
            continue
    all_rows = rows(sk)
    if not picks:
        return all_rows
    def hit(r):
        return any(g == pg and (whole or p == pp) for g, p in r.ties for pg, pp, whole in picks)
    return [r for r in all_rows if hit(r)]
```

Check `model.to_display(doc, expr)` returns `"d1 / 2"` for `"Sk.Constraints.d1 / 2"` (it rewrites refs to names; read `InCad/incad/core/model.py:134-143`). If FreeCAD normalises the stored expression to `d1 / 2` without spaces, compare against what `to_display` gives for the same input in the test instead of the literal.

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_headless.sh test_sketch_constraints.py`
Expected: `OK` (5 tests)

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/sketch_constraints.py tests/headless/test_sketch_constraints.py
git commit -m "Sketch constraints as rows: type, what each ties in the user's words, value; filtered by picked lines and points"
```

---

### Task 2: Guards and delete

**Files:**
- Modify: `InCad/incad/core/sketch_constraints.py`
- Test: `tests/headless/test_sketch_constraints.py`

**Interfaces:**
- Consumes: `rows(sk)`, `Row` (Task 1)
- Produces: `refusal(sk, indices) -> str | None`, `delete(sk, indices) -> int` (raises `ValueError(refusal)`; returns how many were deleted)

- [ ] **Step 1: Write the failing tests** (append to `RowsTest`)

```python
    def test_delete_several_highest_first(self):
        n = sc.delete(self.sk, [4, 1])  # Horizontal (Line 1) and the Line 2/3 coincident
        self.doc.recompute()
        self.assertEqual(n, 2)
        left = [(r.type, r.text) for r in sc.rows(self.sk)]
        self.assertNotIn(("Horizontal", "Line 1"), left)
        self.assertNotIn(("Coincident", "Line 2 end ↔ Line 3 start"), left)
        self.assertEqual(len(left), 8)

    def test_a_pattern_tie_is_refused(self):
        i = self.sk.addConstraint(Sketcher.Constraint("Equal", 0, 2))
        self.sk.renameConstraint(i, "pat3_0")
        with self.assertRaises(ValueError) as ctx:
            sc.delete(self.sk, [0, i])
        self.assertIn("Part of Pattern3", str(ctx.exception))
        self.assertEqual(len(self.sk.Constraints), 11)  # nothing deleted

    def test_a_dimension_used_by_a_formula_is_refused_a_free_one_deleted(self):
        self.sk.setExpression("Constraints.d2", "Sk.Constraints.d1 / 2")
        self.doc.recompute()
        self.assertEqual(sc.refusal(self.sk, [8]), "d1 is used by d2: change that first")
        self.assertIsNone(sc.refusal(self.sk, [9]))
        sc.delete(self.sk, [9])
        self.assertIsNone(sc.refusal(self.sk, [8]))

    def test_used_by_a_feature_value(self):
        pad = util.add_pad(self.body, self.sk, 5.0)
        pad.setExpression("Length", "Sk.Constraints.d1 / 10")
        self.doc.recompute()
        self.assertEqual(sc.refusal(self.sk, [8]), "d1 is used by %s: change that first" % pad.Label)

    def test_delete_works_on_a_conflicting_sketch(self):
        self.sk.addConstraint(Sketcher.Constraint("Vertical", 0))  # Line 1 horizontal and vertical: conflict
        self.doc.recompute()
        self.assertEqual(sc.delete(self.sk, [10]), 1)
        self.doc.recompute()
        self.assertFalse(self.sk.ConflictingConstraints)

    def test_undo_restores_a_delete(self):
        self.doc.UndoMode = 1
        self.doc.openTransaction("Delete Constraints")
        sc.delete(self.sk, [0, 5])
        self.doc.commitTransaction()
        self.doc.undo()
        self.assertEqual(len(self.sk.Constraints), 10)

    def test_a_delete_is_not_read_as_a_replaced_dimension(self):
        from incad.core import sketch
        known = sketch.dimension_snapshot(self.sk)
        sc.delete(self.sk, [9])
        self.assertIsNone(sketch.reconcile_replaced(self.sk, known))
        self.assertNotIn("d2", [c.Name for c in self.sk.Constraints])
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_sketch_constraints.py`
Expected: ERROR `AttributeError: module 'incad.core.sketch_constraints' has no attribute 'delete'`

- [ ] **Step 3: Write the implementation** (append to `sketch_constraints.py`)

```python
import re


def _users(sk, name):
    """Who uses dimension `name` of this sketch in a formula: other dimensions of it by name, other objects by
    label (feature values in the Model Parameters by their own name)."""
    from incad.core import model
    own = "Constraints." + name
    here = re.compile(r"(?:(?<![\w.])|%s\.)\.?Constraints\.%s(?!\w)" % (re.escape(sk.Name), re.escape(name)))
    there = re.compile(r"(?<![\w.])%s\.Constraints\.%s(?!\w)" % (re.escape(sk.Name), re.escape(name)))
    model_obj = sk.Document.getObject(model.MODEL_NAME)
    out = []
    for obj in sk.Document.Objects:
        for path, expr in getattr(obj, "ExpressionEngine", []) or []:
            if obj is sk:
                if path.lstrip(".") != own and here.search(expr):
                    out.append(path.lstrip(".").split(".", 1)[-1])
            elif there.search(expr):
                out.append(path.lstrip(".") if obj is model_obj else obj.Label)
                if obj is not model_obj:
                    break
    return list(dict.fromkeys(out))


def refusal(sk, indices):
    """Why these constraints can't be deleted (the first reason found), or None."""
    cs = sk.Constraints
    for i in sorted(set(indices)):
        c = cs[i]
        owner = _owner(c)
        if owner:
            return "Part of %s: edit or delete the pattern" % owner
        if c.Name and c.Type in sketches.DIMENSIONAL:
            users = _users(sk, c.Name)
            if users:
                return "%s is used by %s: change %s first" % (c.Name, ", ".join(users),
                                                              "that" if len(users) == 1 else "those")
    return None


def delete(sk, indices):
    """Delete these constraints (highest index first, so the others keep theirs). Refused as a whole when any
    of them is a pattern tie or a dimension a formula uses."""
    why = refusal(sk, indices)
    if why:
        raise ValueError(why)
    done = 0
    for i in sorted(set(indices), reverse=True):
        sk.delConstraint(i)
        done += 1
    return done
```

If the `here` regex also matches `Sk.Constraints.d1` inside the sketch's own expressions only through the second
alternative, keep both alternatives: FreeCAD may store a same-sketch reference as `.Constraints.d1`, `Constraints.d1`
or `Sk.Constraints.d1`.

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_sketch_constraints.py`
Expected: `OK` (12 tests)

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/sketch_constraints.py tests/headless/test_sketch_constraints.py
git commit -m "Delete sketch constraints: highest first; pattern ties and dimensions used by a formula are refused with the reason"
```

---

### Task 3: The Constraints panel widget

**Files:**
- Create: `InCad/incad/ui/constraints_panel.py`
- Test: `tests/widgets/test_constraints_panel.py`

**Interfaces:**
- Consumes: plain row tuples `(index, type, text, value, locked: bool)` (the shell converts `Row`; the panel has no FreeCAD import)
- Produces: `ConstraintsPanel(theme, parent=None)` with
  - `set_rows(title: str, header: str, rows: list[tuple])`, `set_message(text: str, ok: bool=False)`
  - `select_index(index | None)`, `checked() -> list[int]`, `selected() -> int | None`
  - Signals: `delete_requested(list)`, `highlight(int)` (−1 = none), `show_all()`, `closed()`
  - Esc inside the panel emits `show_all`; the ✕ button emits `closed`

- [ ] **Step 1: Write the failing tests**

```python
import unittest

from widgets import qtapp
from incad.ui.constraints_panel import ConstraintsPanel

ROWS = [(0, "Coincident", "Line 1 end ↔ Line 2 start", "", False),
        (4, "Horizontal", "Line 1", "", False),
        (8, "Horizontal Distance", "Line 1 start ↔ Line 1 end", "d1 = 60 mm", False),
        (11, "Equal", "Line 1 ↔ Line 3", "", True)]


class ConstraintsPanelTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.p = ConstraintsPanel("light")
        self.p.set_rows("Constraints — Sketch2", "All constraints (4)", ROWS)
        self.seen = {"delete": [], "hi": [], "all": 0, "closed": 0}
        self.p.delete_requested.connect(lambda ids: self.seen["delete"].append(ids))
        self.p.highlight.connect(lambda i: self.seen["hi"].append(i))
        self.p.show_all.connect(lambda: self.seen.__setitem__("all", self.seen["all"] + 1))
        self.p.closed.connect(lambda: self.seen.__setitem__("closed", self.seen["closed"] + 1))

    def test_rows_title_and_header(self):
        self.assertEqual(self.p.title_text(), "Constraints — Sketch2")
        self.assertEqual(self.p.header_text(), "All constraints (4)")
        self.assertEqual(self.p.row_texts()[2], ("Horizontal Distance", "Line 1 start ↔ Line 1 end", "d1 = 60 mm"))

    def test_selecting_a_row_asks_for_its_highlight(self):
        self.p.select_index(8)
        self.assertEqual(self.seen["hi"][-1], 8)
        self.assertEqual(self.p.selected(), 8)

    def test_delete_takes_the_checked_rows_else_the_selected_one(self):
        self.p.select_index(4)
        self.p.delete_button.click()
        self.assertEqual(self.seen["delete"][-1], [4])
        self.p.set_checked(0, True)
        self.p.set_checked(8, True)
        self.p.delete_button.click()
        self.assertEqual(self.seen["delete"][-1], [0, 8])

    def test_nothing_chosen_says_so(self):
        self.p.delete_button.click()
        self.assertEqual(self.seen["delete"], [])
        self.assertEqual(self.p.message_text(), "Check rows or select one first")

    def test_select_all_checks_the_listed_rows(self):
        self.p.select_all_button.click()
        self.assertEqual(self.p.checked(), [0, 4, 8, 11])

    def test_esc_shows_all_and_x_closes(self):
        from PySide6.QtTest import QTest
        from incad.qt import QtCore
        QTest.keyClick(self.p, QtCore.Qt.Key_Escape)
        self.assertEqual(self.seen["all"], 1)
        self.p.close_button.click()
        self.assertEqual(self.seen["closed"], 1)

    def test_set_rows_keeps_the_selection_when_the_row_is_still_there(self):
        self.p.select_index(8)
        self.p.set_rows("Constraints — Sketch2", "Picked: Line 1", ROWS[1:3])
        self.assertEqual(self.p.selected(), 8)
        self.p.set_rows("Constraints — Sketch2", "Picked: Line 2", ROWS[:1])
        self.assertIsNone(self.p.selected())
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_widgets.sh test_constraints_panel.py`
Expected: ERROR `ModuleNotFoundError: No module named 'incad.ui.constraints_panel'`

- [ ] **Step 3: Write the implementation**

```python
"""The sketch's Constraints window: the list (type, what it ties, value), a filter header, Select all / Delete
selected / close. Rows come in as plain tuples (index, type, text, value, locked); no FreeCAD here."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class ConstraintsPanel(QtWidgets.QFrame):
    delete_requested = Signal(list)
    highlight = Signal(int)  # -1: nothing
    show_all = Signal()
    closed = Signal()

    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadConstraintsPanel")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        col = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel("")
        self.title.setObjectName("InCadDialogTitle")
        top.addWidget(self.title, 1)
        self.close_button = QtWidgets.QToolButton(self)
        self.close_button.setText("✕")
        self.close_button.clicked.connect(self.closed.emit)
        top.addWidget(self.close_button)
        col.addLayout(top)
        self.header = QtWidgets.QLabel("")
        col.addWidget(self.header)
        self.table = QtWidgets.QTreeWidget(self)
        self.table.setColumnCount(3)
        self.table.setHeaderHidden(True)
        self.table.setRootIsDecorated(False)
        self.table.setMinimumSize(360, 240)
        self.table.currentItemChanged.connect(self._current_changed)
        col.addWidget(self.table, 1)
        self.message = QtWidgets.QLabel("")
        self.message.setWordWrap(True)
        col.addWidget(self.message)
        row = QtWidgets.QHBoxLayout()
        self.select_all_button = QtWidgets.QPushButton("Select all", self)
        self.delete_button = QtWidgets.QPushButton("Delete selected", self)
        self.select_all_button.clicked.connect(self._select_all)
        self.delete_button.clicked.connect(self._delete)
        row.addWidget(self.select_all_button)
        row.addStretch(1)
        row.addWidget(self.delete_button)
        col.addLayout(row)
        self._theme = theme
        self.set_theme(theme)

    def set_theme(self, theme):
        self._theme = theme
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadConstraintsPanel {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; font-size: 14px; }}"
            " QTreeWidget {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; }}"
            " QPushButton, QToolButton {{ background: {panel_alt}; color: {text}; border: 1px solid {border};"
            " border-radius: 6px; padding: 4px 12px; }}".format(**p))

    # ----- content -----
    def set_rows(self, title, header, rows):
        keep = self.selected()
        self.title.setText(title)
        self.header.setText(header)
        self.table.blockSignals(True)
        self.table.clear()
        current = None
        for index, kind, text, value, locked in rows:
            item = QtWidgets.QTreeWidgetItem([("🔒 " if locked else "") + kind, text, value])
            item.setData(0, QtCore.Qt.UserRole, index)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.Unchecked)
            self.table.addTopLevelItem(item)
            if index == keep:
                current = item
        for c in range(3):
            self.table.resizeColumnToContents(c)
        self.table.setCurrentItem(current)
        self.table.blockSignals(False)
        if keep is not None and current is None:
            self.highlight.emit(-1)

    def set_message(self, text, ok=False):
        p = themes.PALETTES[self._theme]
        self.message.setStyleSheet("color: %s;" % (p["text"] if ok else "#d9534f"))
        self.message.setText(text)

    # ----- reading -----
    def _items(self):
        return [self.table.topLevelItem(i) for i in range(self.table.topLevelItemCount())]

    def _item(self, index):
        return next((it for it in self._items() if it.data(0, QtCore.Qt.UserRole) == index), None)

    def selected(self):
        it = self.table.currentItem()
        return it.data(0, QtCore.Qt.UserRole) if it is not None else None

    def checked(self):
        return [it.data(0, QtCore.Qt.UserRole) for it in self._items() if it.checkState(0) == QtCore.Qt.Checked]

    def select_index(self, index):
        self.table.setCurrentItem(self._item(index) if index is not None else None)

    def set_checked(self, index, on):
        it = self._item(index)
        if it is not None:
            it.setCheckState(0, QtCore.Qt.Checked if on else QtCore.Qt.Unchecked)

    def title_text(self):
        return self.title.text()

    def header_text(self):
        return self.header.text()

    def message_text(self):
        return self.message.text()

    def row_texts(self):
        return [(it.text(0).replace("🔒 ", ""), it.text(1), it.text(2)) for it in self._items()]

    # ----- actions -----
    def _current_changed(self, item, _previous):
        self.highlight.emit(item.data(0, QtCore.Qt.UserRole) if item is not None else -1)

    def _select_all(self):
        for it in self._items():
            it.setCheckState(0, QtCore.Qt.Checked)

    def _delete(self):
        ids = self.checked() or ([self.selected()] if self.selected() is not None else [])
        if not ids:
            self.set_message("Check rows or select one first")
            return
        self.set_message("")
        self.delete_requested.emit(ids)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.show_all.emit()
            return
        super().keyPressEvent(event)
```

Check `themes.PALETTES[theme]` has the keys used (`panel`, `panel_alt`, `border`, `text`): `section_panel.py` uses the same ones.

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_widgets.sh test_constraints_panel.py`
Expected: `OK` (7 tests)

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/constraints_panel.py tests/widgets/test_constraints_panel.py
git commit -m "Constraints window widget: rows, filter header, select/check, Delete selected, Esc shows all"
```

---

### Task 4: Marking menu extra items

**Files:**
- Modify: `InCad/incad/ui/marking_menu.py:38-123`
- Test: `tests/widgets/test_marking_menu.py`

**Interfaces:**
- Produces: `MarkingMenu(registry, slots, items, theme="light", parent=None, extras=())` where `extras` is a list of
  `(label: str, icon: str, callable)`; they follow the list after a gap; choosing one closes the menu, emits
  `triggered("extra:<label>")` and calls the callable. `list_labels()` includes them.

- [ ] **Step 1: Write the failing test** (add to the existing test class in `tests/widgets/test_marking_menu.py`; reuse its registry/fixture names — read the file's `setUp` first)

```python
    def test_extra_items_follow_the_list_and_run_their_callable(self):
        ran = []
        slots, items = marking_layout.resolve("sketch", self.registry)
        menu = MarkingMenu(self.registry, slots, items, "light",
                           extras=[("Delete Horizontal", "delete", lambda: ran.append("h")),
                                   ("Delete all constraints (3)", "delete", lambda: ran.append("all"))])
        labels = menu.list_labels()
        self.assertEqual(labels[-2:], ["Delete Horizontal", "Delete all constraints (3)"])
        seen = []
        menu.triggered.connect(seen.append)
        menu.extra_button("Delete Horizontal").click()
        self.assertEqual(ran, ["h"])
        self.assertEqual(seen, ["extra:Delete Horizontal"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_widgets.sh test_marking_menu.py`
Expected: ERROR `TypeError: MarkingMenu.__init__() got an unexpected keyword argument 'extras'`

- [ ] **Step 3: Implement**

In `MarkingMenu.__init__` add the parameter `extras=()` and, right after the `for cmd in items:` loop:

```python
        self._extras = {}
        for label, icon, fn in extras:
            b = QtWidgets.QToolButton(self)
            b.setIcon(themes.icon(icon, self._theme))
            b.setIconSize(QtCore.QSize(20, 20))
            b.setText(label)
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            b.clicked.connect(lambda _=False, lb=label, f=fn: self._choose_extra(lb, f))
            b.setMinimumWidth(170)
            b.adjustSize()
            self._list.append(b)
            self._extras[label] = b
```

Before the layout loop `for b in self._list:` change the `y += b.height() + 2` step so the first extra starts 8 px
lower (a visual gap): keep a set `first_extra = next(iter(self._extras.values()), None)` and add `if b is first_extra: y += 8`
before moving it. Add the methods:

```python
    def extra_button(self, label):
        return self._extras.get(label)

    def _choose_extra(self, label, fn):
        self.close()
        self.triggered.emit("extra:" + label)
        fn()
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_widgets.sh test_marking_menu.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/marking_menu.py tests/widgets/test_marking_menu.py
git commit -m "Marking menu: extra items with their own action after the list (for per-element entries)"
```

---

### Task 5: The command, the shell wiring and the right-click entries

**Files:**
- Modify: `InCad/incad/actions.py` (command + handler), `InCad/incad/ui/ribbon_layout.py:38-40` (Constrain group),
  `InCad/incad/ui/marking_layout.py:20-23` (sketch list), `tools/make_icons.py` (icon `constraints_window`),
  `InCad/incad/ui/shell.py` (panel lifetime, selection follow, highlight, delete, menu extras),
  `tests/widgets/test_actions.py` (expected ids)
- Test: `tests/gui/test_constraints_window.py`

**Interfaces:**
- Consumes: `sketch_constraints.rows / for_elements / delete / refusal` (Tasks 1-2), `ConstraintsPanel` (Task 3),
  `MarkingMenu(..., extras=)` (Task 4)
- Produces: command `sketch.constraints_window` ("Constraints", icon `constraints_window`); shell methods
  `open_constraints_window(subs=None)`, `close_constraints_window()`, attribute `shell.constraints_panel`;
  module function `shell.open_constraints_window()` (like `shell.start_feature`).

- [ ] **Step 1: Write the failing GUI test** `tests/gui/test_constraints_window.py`

```python
"""Constraints window in a real FreeCAD window: ribbon, filter by pick, highlight, delete (window, right-click,
Delete key with the window open), closes with the sketch."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.core import sketch_constraints as sc  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_sketch_constraints import rect  # noqa: E402

ST = {}


def sk():
    return Gui.ActiveDocument.getInEdit().Object


def panel():
    return shell.instance().constraints_panel


def test_0_sketch_with_a_rectangle():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    shell.instance().plane_panel.button("XY_Plane").click()
    harness.pump(1200)
    rect(sk())
    App.ActiveDocument.recompute()
    harness.pump(500)


def test_1_ribbon_opens_the_window_with_every_constraint():
    b = shell.instance().ribbon.button("sketch.constraints_window")
    assert b is not None and b.isVisible()
    b.click()
    harness.pump(500)
    assert panel() is not None and panel().isVisible()
    assert panel().title_text() == "Constraints — %s" % sk().Label, panel().title_text()
    assert len(panel().row_texts()) == len(sk().Constraints) == 10


def test_2_picking_a_line_filters_and_a_row_highlights():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge1")
    harness.pump(500)
    assert panel().header_text().startswith("Picked: Line 1"), panel().header_text()
    assert [t for t, _, _ in panel().row_texts()] == ["Coincident", "Coincident", "Horizontal", "Horizontal Distance"]
    panel().select_index(4)
    harness.pump(300)
    subs = Gui.Selection.getSelectionEx(App.ActiveDocument.Name)[0].SubElementNames
    assert "Constraint5" in subs and "Edge1" in subs, subs


def test_3_delete_from_the_window_is_one_undo_step():
    doc = App.ActiveDocument
    before = len(doc.UndoNames)
    panel().set_checked(4, True)
    panel().delete_button.click()
    harness.pump(600)
    assert len(sk().Constraints) == 9
    assert doc.UndoNames[0] == "Delete Constraints" and len(doc.UndoNames) == before + 1, doc.UndoNames
    assert ("Horizontal", "Line 1", "") not in panel().row_texts()


def test_4_a_refused_delete_says_why_and_keeps_everything():
    sk().setExpression("Constraints.d2", "%s.Constraints.d1 / 2" % sk().Name)
    App.ActiveDocument.recompute()
    harness.pump(300)
    Gui.Selection.clearSelection()
    harness.pump(400)
    d1 = next(r.index for r in sc.rows(sk()) if r.name == "d1")
    panel().select_index(d1)
    panel().delete_button.click()
    harness.pump(400)
    assert "d1 is used by d2" in panel().message_text(), panel().message_text()
    assert any(r.name == "d1" for r in sc.rows(sk()))


def test_5_right_click_on_a_line_lists_its_constraints():
    s = shell.instance()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Edge2")
    harness.pump(300)
    menu = s.open_sketch_menu_for_test()
    labels = menu.list_labels()
    assert "Delete Vertical" in labels, labels
    assert any(lb.startswith("Delete all constraints (") for lb in labels), labels
    assert "Constraints…" in labels, labels
    n = len(sk().Constraints)
    menu.extra_button("Delete Vertical").click()
    harness.pump(600)
    assert len(sk().Constraints) == n - 1
    Gui.Selection.clearSelection()
    harness.pump(300)
    empty = s.open_sketch_menu_for_test()
    assert not [lb for lb in empty.list_labels() if lb.startswith("Delete ")], empty.list_labels()
    empty.close()


def test_6_delete_key_with_the_window_open_refreshes_the_list():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk().Name, "Constraint1")
    commands.REGISTRY.run("edit.delete")
    harness.pump(600)
    Gui.Selection.clearSelection()
    harness.pump(400)
    assert len(panel().row_texts()) == len(sk().Constraints), (panel().row_texts(), len(sk().Constraints))


def test_7_finish_sketch_closes_the_window():
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)
    assert shell.instance().constraints_panel is None


harness.run([test_0_sketch_with_a_rectangle, test_1_ribbon_opens_the_window_with_every_constraint,
             test_2_picking_a_line_filters_and_a_row_highlights, test_3_delete_from_the_window_is_one_undo_step,
             test_4_a_refused_delete_says_why_and_keeps_everything, test_5_right_click_on_a_line_lists_its_constraints,
             test_6_delete_key_with_the_window_open_refreshes_the_list, test_7_finish_sketch_closes_the_window])
```

- [ ] **Step 2: Run to verify it fails** (tell the user to keep hands off)

Run: `tests/run_gui.sh tests/gui/test_constraints_window.py`
Expected: `FAIL test_1_…` (no `sketch.constraints_window` button)

- [ ] **Step 3: Command, icon, ribbon, menu list**

`tools/make_icons.py`, in `ICONS` after `'constraints_toggle'`:

```python
    'constraints_window': '<rect x="5" y="5" width="22" height="22" rx="3" fill="{F}" stroke="{S}" stroke-width="1.6"/><path d="M9 11 H23 M9 16 H23 M9 21 H18" stroke="{S}" stroke-width="2"/><circle cx="23" cy="21" r="3" fill="{A}"/>',
```

Run `/Applications/FreeCAD.app/Contents/Resources/bin/python tools/make_icons.py` (writes both themes).

`InCad/incad/actions.py`: next to `sketch.constraints_toggle` (around line 789) add

```python
        Command(id="sketch.constraints_window", label="Constraints", icon="constraints_window",
                handler=open_constraints_window, contexts=frozenset({"sketch"}),
                tooltip="List the sketch's constraints: pick a line or point to see its own, delete the ones you check"),
```

and the handler near `constraints_visible`:

```python
def open_constraints_window():
    from incad.ui import shell
    _editing_sketch()  # "Open a sketch first"
    shell.open_constraints_window()
```

`ribbon_layout.py` Constrain group: append `"sketch.constraints_window"` after `"sketch.fix"`.
`marking_layout.py` sketch list: insert `"sketch.constraints_window"` after `"sketch.constraints_toggle"`.
`tests/widgets/test_actions.py` `EXPECTED`: add `"sketch.constraints_window"`.

- [ ] **Step 4: Shell wiring** (`InCad/incad/ui/shell.py`)

1. In `__init__` next to `self.section_panel = None` (line ~300): `self.constraints_panel = None`.
2. Add to the `_raise_overlays` tuple (line ~840): `self.constraints_panel`.
3. Methods (put them after the section-view methods):

```python
    # ----- sketch constraints window -----
    def open_constraints_window(self):
        from incad.ui.constraints_panel import ConstraintsPanel
        sk = self.sketches.editing()
        if sk is None:
            raise ValueError("Open a sketch first")
        if self.constraints_panel is None:
            parent = self._mdi().viewport() if self._mdi() is not None else self.mw
            p = ConstraintsPanel(self.theme, parent)
            p.delete_requested.connect(self._delete_constraints)
            p.highlight.connect(self._highlight_constraint)
            p.show_all.connect(lambda: self._constraints_filter_clear())
            p.closed.connect(self.close_constraints_window)
            p.move(16, 16)
            p.show()
            self.constraints_panel = p
        self._constraints_owner = (sk.Document.Name, sk.Name)
        self.refresh_constraints_window()
        self.constraints_panel.raise_()

    def close_constraints_window(self):
        if self.constraints_panel is not None:
            try:
                self.constraints_panel.close()
                dispose(self.constraints_panel)
            except RuntimeError:
                pass
            self.constraints_panel = None

    def _picked_sketch_elements(self, sk):
        import FreeCADGui as Gui
        subs = []
        for sel in Gui.Selection.getSelectionEx(sk.Document.Name):
            if sel.Object is sk:
                subs += [n for n in sel.SubElementNames if not n.startswith("Constraint")]
        return subs

    def refresh_constraints_window(self):
        from incad.core import sketch_constraints as sc
        p, sk = self.constraints_panel, self.sketches.editing()
        if p is None or sk is None:
            return
        if self._constraints_highlighting:
            return  # our own selection of a row's constraint: the filter stays
        subs = self._picked_sketch_elements(sk)
        rows = sc.for_elements(sk, subs)
        names = ", ".join(dict.fromkeys(sc.element_name(sk, *self._element(sk, s)) for s in subs[:3]))
        header = ("Picked: %s  ·  Esc shows all" % names) if subs else "All constraints (%d)" % len(sk.Constraints)
        p.set_rows("Constraints — %s" % sk.Label, header,
                   [(r.index, r.type, r.text, ("%s = %s" % (r.name, r.value)) if r.value else "", bool(r.owner))
                    for r in rows])

    @staticmethod
    def _element(sk, sub):
        from incad.core import sketch_patterns as sp
        return sp.element(sk, sub)

    def _constraints_filter_clear(self):
        import FreeCADGui as Gui
        Gui.Selection.clearSelection()
        self.refresh_constraints_window()

    def _highlight_constraint(self, index):
        import FreeCADGui as Gui
        from incad.core import sketch_constraints as sc
        sk = self.sketches.editing()
        if sk is None or index < 0 or index >= len(sk.Constraints):
            return
        row = sc.rows(sk)[index]
        self._constraints_highlighting = True
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(sk.Document.Name, sk.Name, "Constraint%d" % (index + 1))
            for geo, _pos in row.ties:
                if geo >= 0:
                    Gui.Selection.addSelection(sk.Document.Name, sk.Name, "Edge%d" % (geo + 1))
        finally:
            self._constraints_highlighting = False

    def _delete_constraints(self, indices):
        from incad.core import safe, sketch_constraints as sc
        sk = self.sketches.editing()
        if sk is None:
            return
        valid = [i for i in indices if 0 <= i < len(sk.Constraints)]
        why = sc.refusal(sk, valid)
        if why:
            if self.constraints_panel is not None:
                self.constraints_panel.set_message(why)
            return
        r = safe.run_safely("Delete Constraints", lambda: sc.delete(sk, valid), sk.Document)
        if self.constraints_panel is not None:
            self.constraints_panel.set_message(
                ("Deleted %d" % r.value) if r.ok else r.error, ok=r.ok)
        self.refresh_constraints_window()
```

   Initialise `self._constraints_highlighting = False` and `self._constraints_owner = None` in `__init__`.
   `_highlight_constraint` selects the constraint, so the selection watch fires; the `_constraints_highlighting` flag
   is checked in `refresh_constraints_window` — but the watch is deferred, so the flag is already False by then.
   Instead keep the filter while a `ConstraintN` is part of the selection: in `_picked_sketch_elements`, when the
   selection contains any `ConstraintN`, return the subs remembered at the last refresh (`self._constraints_subs`),
   and store `self._constraints_subs = subs` at the end of each normal refresh.
4. Follow the selection: at the end of `_on_model_selection_changed` add `self.refresh_constraints_window()`.
5. Follow sketch changes (deletes by the Delete key, undo): in `_sketch_changed(sk)` (line ~1161) add
   `self.refresh_constraints_window()` (deferred with the other scheduled work is fine).
6. Lifetime: in `_refresh`, next to the value-box rule (line ~2120):

```python
        if self.constraints_panel is not None and (editing is None or
                                                   (editing.Document.Name, editing.Name) != self._constraints_owner):
            self.close_constraints_window()
```

7. Theme and teardown: in `apply_theme` call `self.constraints_panel.set_theme(self.theme)` when it exists; in
   `_teardown` call `self.close_constraints_window()`.
8. Module-level function next to `start_feature` (line ~2838): 

```python
def open_constraints_window():
    if _shell is not None:
        _shell.open_constraints_window()
```

- [ ] **Step 5: Right-click entries**

In `_open_marking_menu` replace the first branch:

```python
        if self.sketches.editing() is not None:
            return self._show_marking_menu("sketch", global_pos, flick, extras=self._constraint_menu_items())
```

`_show_marking_menu(self, kind, global_pos, flick=False, extras=())` passes `extras=extras` to `MarkingMenu`. Add:

```python
    def _constraint_menu_items(self):
        """Per-constraint Delete entries for the line or point under the cursor (else the picked one)."""
        import FreeCADGui as Gui
        from incad.core import sketch_constraints as sc
        sk = self.sketches.editing()
        if sk is None:
            return []
        pre = Gui.Selection.getPreselection()
        subs = [pre.SubElementNames[0]] if pre is not None and pre.Object is sk and pre.SubElementNames \
            and not pre.SubElementNames[0].startswith("Constraint") else self._picked_sketch_elements(sk)
        if not subs:
            return []
        rows = sc.for_elements(sk, subs[:1])
        if not rows:
            return []
        geo, _pos = self._element(sk, subs[0])
        items = []
        if len(rows) <= 8:
            for r in rows:
                others = [sc.element_name(sk, g, p) for g, p in r.ties if g != geo]
                label = "Delete %s" % r.type + (" (%s)" % ", ".join(others) if others else "")
                if r.value:
                    label += " %s = %s" % (r.name, r.value)
                items.append((label, "delete", lambda i=r.index: self._delete_constraints([i])))
        items.append(("Delete all constraints (%d)" % len(rows), "delete",
                      lambda ids=[r.index for r in rows]: self._delete_constraints(ids)))
        items.append(("Constraints…", "constraints_window", self.open_constraints_window))
        return items

    def open_sketch_menu_for_test(self):
        """The sketch right-click menu at the view's centre, as a right click opens it (GUI tests)."""
        from incad.qt import QtCore
        view = self._mdi().viewport()
        return self._show_marking_menu("sketch", view.mapToGlobal(view.rect().center()), False,
                                       extras=self._constraint_menu_items())
```

   `_delete_constraints` already reports a refusal in the window; when the window is closed, report it with
   `log.report("warning", why)` instead (change the `if self.constraints_panel is not None` branches to fall back to
   `log.report`).

- [ ] **Step 6: Run the tests**

Run: `tests/run_widgets.sh test_actions.py` → `OK`; `tests/run_widgets.sh test_icons.py` → `OK`;
`tests/run_gui.sh tests/gui/test_constraints_window.py` → `8 passed, 0 failed`;
`tests/run_gui.sh tests/gui/test_sketch_tools.py` → all pass (right-click menu and Delete key unchanged).

- [ ] **Step 7: Commit**

```bash
git add InCad/incad/actions.py InCad/incad/ui/shell.py InCad/incad/ui/ribbon_layout.py InCad/incad/ui/marking_layout.py \
        tools/make_icons.py InCad/resources/icons tests/widgets/test_actions.py tests/gui/test_constraints_window.py
git commit -m "Sketch Constraints window (ribbon, right-click): filter by the picked line or point, highlight, delete in one undo step"
```

---

### Task 6: Release notes and project facts

**Files:**
- Modify: `scripts/dist/CHANGES.txt`, `scripts/dist/CHANGES_ru.txt`, `InCad/incad/__init__.py` (version),
  `tests/headless/test_smoke.py`, `CLAUDE.md`

- [ ] **Step 1:** Bump `__version__` to the next build (`0.1.2` if 0.1.1 was shipped) and the smoke test's expected value.
- [ ] **Step 2:** Add a section on top of both CHANGES files:

```
0.1.2
-----
Improvements
- Sketch: new Constraints window (Sketch > Constrain > Constraints, or right-click in a sketch). It lists the
  sketch's constraints; pick a line or point to see only its own; select a row to see it in the sketch; check rows
  and Delete selected (one undo step). Constraints of a sketch pattern and dimensions used in a formula are kept,
  with the reason.
- Sketch: right-click a line or point to delete one of its constraints, or all of them.
```

and the Russian section:

```
0.1.2
-----
Улучшения
- Эскиз: новое окно Constraints (Sketch > Constrain > Constraints или правая кнопка в эскизе). Оно показывает
  зависимости эскиза; выберите линию или точку, чтобы видеть только её зависимости; выберите строку, чтобы увидеть
  её в эскизе; отметьте строки и нажмите Delete selected (один шаг отмены). Зависимости массива эскиза и размеры,
  которые используются в формулах, не удаляются, и окно говорит почему.
- Эскиз: правой кнопкой на линии или точке можно удалить одну её зависимость или все сразу.
```

- [ ] **Step 3:** `CLAUDE.md`, Sketcher facts: add "the Constraints window (`incad.core.sketch_constraints`,
  `incad.ui.constraints_panel`) lists and deletes constraints; pattern ties and dimensions used by a formula are refused."
- [ ] **Step 4:** Run `tests/run_headless.sh` and `tests/run_widgets.sh` (full, once). Expected: `OK`.
- [ ] **Step 5: Commit**

```bash
git add scripts/dist/CHANGES.txt scripts/dist/CHANGES_ru.txt InCad/incad/__init__.py tests/headless/test_smoke.py CLAUDE.md
git commit -m "0.1.2: Constraints window in the release notes"
```
