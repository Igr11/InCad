# Assembly drag, degrees of freedom and constraint rows — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In an InCad assembly the user drags a free part with the mouse only along its own degrees of freedom, sees
"DOF n" on every component row and Inventor's DOF glyphs (on demand and as a hover tip), and edits, deletes,
suppresses and renames constraints from their rows.

**Architecture:** DOF is counted by probing FreeCAD's assembly solver (`core/dof.py`, pure model logic, cached against
a constraint signature, run in an aborted transaction). Dragging is FreeCAD's native assembly drag: the gesture
machine reports when a left press becomes a drag, a new `ui/asm_drag.py` puts the assembly in edit mode only for that
drag, inside InCad's own "Move part" step, with every other free part held by temporary grounds. Glyphs are
`SoAnnotation` view markers (`ui/dof_glyphs.py`). Constraint rows get their own marking menu and a core
`constraints.toggle_suppressed`.

**Tech Stack:** FreeCAD 1.1.3 (macOS) Python API, its Assembly workbench (`Assembly::AssemblyObject`,
`JointObject`), pivy/Coin, PySide (FreeCAD shim) / PySide6, numpy (bundled with FreeCAD), unittest.

**Spec:** `docs/superpowers/specs/2026-10-13-incad-assembly-drag-dof-design.md` (read it first). Spike scripts that
proved every FreeCAD behaviour used here: `docs/superpowers/spikes/2026-10-13-assembly-drag/` (findings in
`docs/superpowers/DECISIONS.md`, 2026-10-13 entries).

## Global Constraints

- UI text English (CLAUDE.md). Status messages exactly as in the spec: "<Part> is grounded", "<Part> is fully
  constrained", "Moved <Part>", "<Constraint> can't be met any more: it stays suppressed".
- Tests: bundled Python has no pytest — unittest only. Runners: `tests/run_widgets.sh <pattern>`,
  `tests/run_headless.sh <pattern>`, `tests/run_gui.sh <file>` (real FreeCAD window; nobody touches the Mac while it
  runs; an unlocked screen is needed — `tests/screen_locked.sh` tells). Run only the affected files per task; the full
  suites (`tests/run_all.sh`) at most once, in the last task.
- New documents have `UndoMode == 0`; anything that must be one undo step sets `doc.UndoMode = 1` first (as
  `safe.run_safely` does).
- Never recompute or solve while `doc.Restoring` (CLAUDE.md: the Sketcher crashes mid-load).
- Glyphs and markers are `SoAnnotation` nodes, never document objects (CLAUDE.md).
- FreeCAD facts from the spikes (do not re-derive):
  - FreeCAD drags only while the assembly is in edit: `Gui.getDocument(d).setEdit(asm.Name)`.
  - `resetEdit()` closes (commits) the transaction that was open at `setEdit()`: call `setEdit` **before**
    `doc.openTransaction("Move part")`, commit before `resetEdit()`.
  - `asm.ViewObject.MoveInCommand = False` stops FreeCAD's own "Move part" command.
  - FreeCAD's drag pulls free neighbours along unless they are grounded.
  - Probing a grounded part is meaningless (the solver leaves a moved grounded part where it is).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A sub-assembly as a component** (a link to another assembly file): the count and the drag must treat it as one
   rigid part and never crash — test in Task 3.
2. **A component whose part has no solid** (an empty part file, a broken link: null shape): "DOF ?" or a plain count,
   no exception out of the refresh, no drag started on it — test in Task 3 (count) and Task 7 (drag refuses).
3. **Nothing grounded** (every part free, or a single part): FreeCAD's solver needs one fixed part; the count must
   still say 6 for an unconstrained part and give relative counts for the rest — test in Task 3.
4. **Undo / Redo of a constraint** (Mate created, then ⌘Z): the rows must recount (the signature changes), not keep
   the stale "DOF 3" — test in Task 5.
5. **The count must not mark the file modified** (a user opens an assembly and closes it: no "save changes?" prompt
   because of the count) — test in Task 5 (GUI).

---

## File Structure

- Create `InCad/incad/core/dof.py` — counting (probe, compute, signature, cache) and glyph geometry. Pure model logic.
- Create `InCad/incad/ui/asm_drag.py` — `AssemblyDrag`: starts and ends a drag, holds the other parts.
- Create `InCad/incad/ui/dof_glyphs.py` — `DofGlyphs` (Coin rendering) and `HoverWatch` (preselection observer).
- Modify `InCad/incad/core/gestures.py` — `drag_start` / `drag_end` actions.
- Modify `InCad/incad/ui/nav.py` — `Navigator.drag_hook`.
- Modify `InCad/incad/core/safe.py` — the drag-edit flag read by `edit_open()`.
- Modify `InCad/incad/features/constraints.py` — `toggle_suppressed(j)`.
- Modify `InCad/incad/core/tree.py` — DOF text on component rows, suppressed state on constraint rows.
- Modify `InCad/incad/ui/marking_layout.py` — layout `joint`.
- Modify `InCad/incad/actions.py` — commands `constraint.suppress`, `view.dof`.
- Modify `InCad/incad/ui/ribbon_layout.py` — `view.dof` in the assembly View tab.
- Modify `InCad/incad/ui/shell.py` — wiring: joint menu kind, drag hook, DOF update after refresh, glyphs, hover.
- Tests: create `tests/headless/test_dof.py`, `tests/gui/test_constraint_rows.py`, `tests/gui/test_assembly_drag.py`;
  modify `tests/headless/test_constraints.py`, `tests/headless/test_tree.py`, `tests/widgets/test_gestures.py`,
  `tests/widgets/test_nav_hooks.py`, `tests/widgets/test_marking_layout.py`.

---

### Task 1: Suppress / Unsuppress a constraint (core)

**Files:**
- Modify: `InCad/incad/features/constraints.py` (add after `_met`, before `_make`)
- Test: `tests/headless/test_constraints.py`

**Interfaces:**
- Consumes: `constraints._placements`, `_settle`, `_met`, `_solve`, `KINDS`, each kind's `read(doc, j)` and
  `claims(j)`; `assembly.components`, `assembly.is_suppressed`.
- Produces: `constraints.toggle_suppressed(j) -> bool` (True when suppressed now); raises `ValueError` with the
  user message on refusal. `constraints.kind_of(j) -> spec | None`.

- [ ] **Step 1: Write the failing tests** — append to `ConstraintsTest` in `tests/headless/test_constraints.py`
  (its `setUp` places `self.plate` grounded and `self.block` free at a turned start; `face`, `z_is` exist there):

```python
    def _mate(self):
        return C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None),
                                                        first=face(self.plate, z_is(10)), second=face(self.block, z_is(0))))

    def test_suppress_keeps_the_parts_and_unsuppress_solves_again(self):
        from incad.core import safe
        j = self._mate()
        at = App.Placement(self.block.Placement)
        r = safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        self.assertTrue(r.ok and r.value, r.error)
        self.assertTrue(j.Suppressed)
        self.assertTrue(self.block.Placement.isSame(at, 1e-9), "the parts stay where they are")
        self.assertEqual(self.doc.UndoNames[0], "Suppress")
        self.block.Placement = App.Placement(App.Vector(5, 5, 40), App.Rotation())  # moved while it was off
        self.doc.recompute()
        r = safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        self.assertTrue(r.ok and r.value is False, r.error)
        self.assertFalse(j.Suppressed)
        self.assertAlmostEqual(self.block.Shape.BoundBox.ZMin, 10, places=4)  # solved onto the plate again

    def test_unsuppress_that_cannot_be_met_is_refused_and_stays_suppressed(self):
        from incad.core import safe
        j = self._mate()
        safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        C.FLUSH.create(self.doc, None, None, dict(C.FLUSH.defaults(self.doc, None),  # block top flush with plate top
                                                  first=face(self.plate, z_is(10)), second=face(self.block, z_is(10))))
        at = App.Placement(self.block.Placement)
        r = safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        self.assertFalse(r.ok)
        self.assertIn("can't be met any more: it stays suppressed", r.error)
        self.assertTrue(j.Suppressed)
        self.assertTrue(self.block.Placement.isSame(at, 1e-6))

    def test_a_constraint_of_a_suppressed_part_is_not_unsuppressed_alone(self):
        j = self._mate()
        assembly.toggle_suppressed(self.block)  # the part's constraints go off with it
        self.assertTrue(j.Suppressed)
        with self.assertRaises(ValueError) as e:
            C.toggle_suppressed(j)
        self.assertIn("Block is suppressed", str(e.exception))

    def test_grounding_is_not_a_constraint_to_suppress(self):
        g = [x for x in assembly.joints(self.doc) if hasattr(x, "ObjectToGround")][0]
        self.assertIsNone(C.kind_of(g))
        with self.assertRaises(ValueError):
            C.toggle_suppressed(g)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `tests/run_headless.sh test_constraints.py`
Expected: the four new tests ERROR with `AttributeError: module 'incad.features.constraints' has no attribute
'toggle_suppressed'` (or `kind_of`).

- [ ] **Step 3: Implement** — add to `InCad/incad/features/constraints.py` right after `_met`:

```python
def kind_of(j):
    """The InCad constraint kind of a joint, None for anything else (a grounding, an assembly Boolean's record)."""
    return next((k for k in KINDS if k.claims(j)), None) if j is not None else None


def toggle_suppressed(j):
    """Suppress (Inventor) a constraint: the solver ignores it, the parts stay where they are; again to bring it back,
    solved to meet it — refused (it stays suppressed, the parts back) when it can't be met any more. Returns True when
    it is suppressed now."""
    from incad.core import assembly
    spec = kind_of(j)
    if spec is None or "Suppressed" not in j.PropertiesList:
        raise ValueError("%s can't be suppressed" % getattr(j, "Label", j))
    doc = j.Document
    if not j.Suppressed:
        j.Suppressed = True
        doc.recompute()
        return True
    refs = [(getattr(j, p, None) or (None,))[0] for p in ("Reference1", "Reference2")]
    off = [c for c in assembly.components(doc) if c in refs and assembly.is_suppressed(c)]
    if off:
        raise ValueError("%s is suppressed: unsuppress the part first" % off[0].Label)
    before = _placements(doc)
    j.Suppressed = False
    values = spec.read(doc, j)
    result = _settle(doc, j, spec, values)
    if result != 0 or not _met(doc, j, spec, values):
        j.Suppressed = True
        for name, plc in before.items():
            doc.getObject(name).Placement = plc
        _solve(doc)
        raise ValueError("%s can't be met any more: it stays suppressed" % j.Label)
    doc.recompute()
    return False
```

  `KINDS` is defined at the bottom of the module; `kind_of` only runs after import, so the forward reference is fine.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `tests/run_headless.sh test_constraints.py`
Expected: all tests in the file PASS (old ones included).

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features/constraints.py tests/headless/test_constraints.py
git commit -m "Constraints: Suppress / Unsuppress a constraint (parts stay; an Unsuppress that can't be met is refused)"
```

---

### Task 2: Constraint rows — own marking menu, Suppress command, suppressed look, Delete key

**Files:**
- Modify: `InCad/incad/ui/marking_layout.py` (the `LAYOUT` dict)
- Modify: `InCad/incad/actions.py` (new handler + `Command` in `commands()`, next to `browser.suppress`)
- Modify: `InCad/incad/core/tree.py:178-194` (`_assembly`: joint rows)
- Modify: `InCad/incad/ui/shell.py:1126-1137` (`_on_browser_marking_menu`)
- Test: `tests/widgets/test_marking_layout.py`, `tests/headless/test_tree.py`, create `tests/gui/test_constraint_rows.py`

**Interfaces:**
- Consumes: `constraints.toggle_suppressed`, `constraints.kind_of` (Task 1); existing `browser.edit`,
  `browser.delete`, `browser.rename` commands (they act on `context.target()`).
- Produces: command id `constraint.suppress`; marking-menu context `"joint"`; joint tree nodes with
  `state="suppressed"` when `j.Suppressed`.

- [ ] **Step 1: Write the failing widget test** — in `tests/widgets/test_marking_layout.py`, in `test_contexts` add
  `"joint"` to the expected set and append:

```python
        self.assertEqual({d: marking_layout.LAYOUT["joint"][d] for d in ("N", "S", "E", "W")},
                         {"N": "browser.edit", "S": "browser.delete", "E": "constraint.suppress", "W": "browser.rename"})
        self.assertEqual(marking_layout.LAYOUT["joint"]["list"],
                         ["browser.edit", "browser.delete", "constraint.suppress", "browser.rename"])
```

- [ ] **Step 2: Write the failing headless tree test** — in `tests/headless/test_tree.py` add a test class (reuse
  `save_part` from `headless.test_assembly`):

```python
class AssemblyRowsTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from headless.test_assembly import save_part
        from incad.core import assembly
        self.dir = tempfile.mkdtemp(prefix="incad_tree_asm_")
        _, plate = save_part(self.dir, "Plate", 40, 30, 10)
        _, block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))
        self.a, self.b = assembly.place(self.doc, plate), assembly.place(self.doc, block)

    def tearDown(self):
        import shutil
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_suppressed_constraint_row_says_so(self):
        from incad.core import tree
        from incad.features import constraints as C
        top = [i + 1 for i, f in enumerate(self.a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        bot = [i + 1 for i, f in enumerate(self.b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
        j = C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None), first="%s:Face%d" % (self.a.Name, top),
                                                     second="%s:Face%d" % (self.b.Name, bot)))
        C.toggle_suppressed(j)
        rel = [n for n in tree.build(self.doc)[0].children if n.kind == "relationships"][0]
        self.assertEqual([(n.name, n.state) for n in rel.children], [(j.Name, "suppressed")])
```

  (Add `import os` and `import FreeCAD as App` at the top of the file if they are not there yet.)

- [ ] **Step 3: Run both to verify they fail**

Run: `tests/run_widgets.sh test_marking_layout.py` → FAIL (`KeyError: 'joint'` / set mismatch).
Run: `tests/run_headless.sh test_tree.py` → FAIL (state `''` instead of `'suppressed'`).

- [ ] **Step 4: Implement**

  `InCad/incad/ui/marking_layout.py` — add to `LAYOUT`:

```python
    "joint": {"N": "browser.edit", "S": "browser.delete", "E": "constraint.suppress", "W": "browser.rename",
              "list": ["browser.edit", "browser.delete", "constraint.suppress", "browser.rename"]},
```

  `InCad/incad/actions.py` — handler next to `toggle_suppress`:

```python
def toggle_constraint_suppressed():
    """A constraint row's Suppress / Unsuppress (Inventor): the solver ignores it, the parts stay."""
    from incad.core import log
    from incad.features import constraints
    j = _target_object()
    on = constraints.toggle_suppressed(j)
    log.report("info", "%s %s" % (j.Label, "suppressed" if on else "back on"))
```

  and in `commands()` after the `browser.suppress` command:

```python
        Command(id="constraint.suppress", label="Suppress / Unsuppress", icon="suppress",
                handler=toggle_constraint_suppressed, transactional=True, contexts=frozenset({"browser"}),
                tooltip="Turn the constraint off (the parts stay where they are) or back on"),
```

  `InCad/incad/core/tree.py` `_assembly` — the joint rows:

```python
    root.children.append(Node("relationships", "Relationships (%d)" % len(rel),
                              children=[Node("joint", j.Label, j.Name,
                                             state="suppressed" if getattr(j, "Suppressed", False) else "")
                                        for j in rel]))
```

  `InCad/incad/ui/shell.py` `_on_browser_marking_menu` — before `self._show_marking_menu(kind, global_pos)`:

```python
        from incad.core import asm_cut, assembly
        if obj is not None and (obj in assembly.joints(App.ActiveDocument) or asm_cut.is_record(obj)):
            kind = "joint"  # a Relationships row: Edit, Delete, Suppress, Rename
```

  (An assembly Boolean's record is also a Relationships row; `constraint.suppress` refuses it with
  "<label> can't be suppressed" from Task 1.)

- [ ] **Step 5: Run the widget and headless tests to verify they pass**

Run: `tests/run_widgets.sh test_marking_layout.py` → PASS. Run: `tests/run_headless.sh test_tree.py` → PASS.

- [ ] **Step 6: Write the GUI test** — create `tests/gui/test_constraint_rows.py`:

```python
"""Relationships rows (Inventor's browser): their own marking menu, Suppress / Unsuppress, Rename and the Delete key."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, context, prefs, safe, tree  # noqa: E402
from incad.features import constraints as C  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["asm"])


def joint_rows():
    rel = [n for n in tree.build(doc())[0].children if n.kind == "relationships"][0]
    return {n.name: n for n in rel.children}


def click_row(label):
    b = s().browser
    item = b.item_by_label(label)
    parent = item.parent()
    while parent is not None:
        parent.setExpanded(True)
        parent = parent.parent()
    harness.pump(100)
    QTest.mouseClick(b.tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, b.tree.visualItemRect(item).center())
    harness.pump(400)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_rows_")
    for name, w, h, t in (("Plate", 40, 30, 10), ("Block", 10, 10, 10)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    d = actions.new_assembly("mm")
    d.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = d.Name
    a, b = s().assembly_place(ST["Plate"]), s().assembly_place(ST["Block"])
    top = [i + 1 for i, f in enumerate(a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    bot = [i + 1 for i, f in enumerate(b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
    r = safe.run_safely("Mate", lambda: C.MATE.create(d, None, None, dict(
        C.MATE.defaults(d, None), first="%s:Face%d" % (a.Name, top), second="%s:Face%d" % (b.Name, bot))), d)
    assert r.ok, r.error
    ST["j"], ST["b"] = r.value.Name, b.Name
    s().schedule_refresh()
    harness.pump(800)


def test_1_row_menu_is_the_constraint_menu():
    s()._on_browser_marking_menu(ST["j"], QtCore.QPoint(300, 300))
    harness.pump(300)
    assert s().menu_kind == "joint", s().menu_kind
    s().marking_menu.close()
    harness.pump(200)


def test_2_suppress_from_the_row_and_back():
    j = doc().getObject(ST["j"])
    context.set_target(j.Name)
    r = commands.REGISTRY.run("constraint.suppress")
    harness.pump(500)
    assert r.ok and j.Suppressed, (r.ok, r.error)
    assert joint_rows()[j.Name].state == "suppressed"
    assert doc().UndoNames[0] == "Suppress / Unsuppress", doc().UndoNames[:2]
    context.set_target(j.Name)
    r = commands.REGISTRY.run("constraint.suppress")
    harness.pump(500)
    assert r.ok and not j.Suppressed, (r.ok, r.error)


def test_3_rename_from_the_row():
    j = doc().getObject(ST["j"])
    context.set_target(j.Name)
    actions.rename(ask=lambda current: "Block on plate")
    harness.pump(300)
    assert j.Label == "Block on plate", j.Label


def test_4_delete_key_on_a_selected_row():
    j_name = ST["j"]
    s().schedule_refresh()
    harness.pump(500)
    click_row("Block on plate")
    n0 = len(doc().UndoNames)
    r = commands.REGISTRY.run("edit.delete")
    harness.pump(600)
    assert r.ok, r.error
    assert doc().getObject(j_name) is None
    assert doc().getObject(ST["b"]) is not None, "the part stays"
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Delete", doc().UndoNames[:2]
    commands.REGISTRY.run("edit.undo")
    harness.pump(600)
    assert doc().getObject(j_name) is not None, "Undo brings the constraint back"


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_setup, test_1_row_menu_is_the_constraint_menu, test_2_suppress_from_the_row_and_back,
             test_3_rename_from_the_row, test_4_delete_key_on_a_selected_row, test_9_cleanup])
```

- [ ] **Step 7: Run the GUI test**

Run: `tests/run_gui.sh tests/gui/test_constraint_rows.py`
Expected: 6 passed. If `test_4` fails because `edit.delete` found nothing selected, the tree click did not select the
joint in the model: check `_on_browser_select` (it calls `Gui.Selection.addSelection(doc.Name, n)` for objects
without faces) and fix there, not in the test.

- [ ] **Step 8: Commit**

```bash
git add InCad/incad/ui/marking_layout.py InCad/incad/actions.py InCad/incad/core/tree.py InCad/incad/ui/shell.py \
  tests/widgets/test_marking_layout.py tests/headless/test_tree.py tests/gui/test_constraint_rows.py
git commit -m "Relationships rows: their own menu (Edit, Delete, Suppress, Rename), a suppressed constraint is shown struck through"
```

---

### Task 3: Counting degrees of freedom (`core/dof.py`)

**Files:**
- Create: `InCad/incad/core/dof.py`
- Test: create `tests/headless/test_dof.py`

**Interfaces:**
- Consumes: `assembly.components/joints/is_grounded/is_suppressed/ground/unground/assembly_of`.
- Produces:
  - `dof.Freedom` — namedtuple `(n, slides, turns, error)`: `n` int 0..6 or `None` when the count failed;
    `slides` list of unit `App.Vector` in the **part's own frame**; `turns` list of `(App.Vector point,
    App.Vector axis)` in the part's own frame; `error` str.
  - `dof.compute(doc) -> {link_name: Freedom}` (free, unsuppressed components only). Raises `dof.Busy` while
    `doc.Restoring` or `doc.HasPendingTransaction`.
  - `dof.signature(doc) -> tuple`, `dof.cached(doc) -> dict | None` (only when the signature matches),
    `dof.last(doc) -> dict | None` (whatever was counted last), `dof.ensure(doc) -> (dict | None, computed: bool)`.

- [ ] **Step 1: Write the failing tests** — create `tests/headless/test_dof.py`:

```python
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from incad.core import assembly, document, dof
from incad.features import constraints as C
from headless import util
from headless.test_assembly import save_part


def fz(link, z):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z - z) < 1e-6][0])


def fx(link, x):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.x - x) < 1e-6][0])


def fy(link, y):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.y - y) < 1e-6][0])


def make(doc, kind, first, second):
    return kind.create(doc, None, None, dict(kind.defaults(doc, None), first=first, second=second))


class DofTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_dof_")
        _, self.plate_path = save_part(self.dir, "Plate", 40, 30, 10)
        _, self.block_path = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))
        self.a = assembly.place(self.doc, self.plate_path)
        self.b = assembly.place(self.doc, self.block_path)
        dof._CACHE.clear()

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def n(self, link):
        return dof.compute(self.doc)[link.Name].n

    def test_free_part_has_six(self):
        f = dof.compute(self.doc)[self.b.Name]
        self.assertEqual((f.n, len(f.slides), len(f.turns), f.error), (6, 3, 3, ""))

    def test_grounded_part_is_not_counted(self):
        self.assertNotIn(self.a.Name, dof.compute(self.doc))

    def test_mate_leaves_two_slides_in_the_face_and_one_turn_about_its_normal(self):
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        f = dof.compute(self.doc)[self.b.Name]
        self.assertEqual(f.n, 3)
        self.assertEqual(len(f.slides), 2)
        for d in f.slides:
            self.assertAlmostEqual(d.z, 0, places=3)  # in the plate's plane (block unturned: own frame = global)
        self.assertEqual(len(f.turns), 1)
        self.assertAlmostEqual(abs(f.turns[0][1].z), 1, places=3)

    def test_mate_and_flushes(self):
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        make(self.doc, C.FLUSH, fx(self.a, 0), fx(self.b, 0))
        self.assertEqual(self.n(self.b), 1)
        make(self.doc, C.FLUSH, fy(self.a, 0), fy(self.b, 0))
        self.assertEqual(self.n(self.b), 0)

    def test_insert_turns_about_the_pin_axis(self):
        d = util.new_doc("Pin")
        body = document.make_part(d)
        cyl = body.newObject("PartDesign::AdditiveCylinder", "Pin")
        cyl.Radius, cyl.Height = 3, 20
        body.Tip = cyl
        d.recompute()
        pin_path = os.path.join(self.dir, "Pin.FCStd")
        d.saveAs(pin_path)
        hd = App.getDocument("Plate")  # save_part leaves the part open (named after it)
        hb = document.primary_body(hd)
        hole = hb.newObject("PartDesign::SubtractiveCylinder", "HoleCyl")
        hole.Radius, hole.Height = 3, 10
        hole.Placement = App.Placement(App.Vector(20, 15, 0), App.Rotation())
        hb.Tip = hole
        hd.recompute()
        hd.save()
        self.doc.recompute()
        p = assembly.place(self.doc, pin_path)
        mouth = [i + 1 for i, e in enumerate(self.a.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
                 and abs(e.Curve.Radius - 3) < 1e-6 and abs(e.Curve.Center.z - 10) < 1e-6][0]
        end = [i + 1 for i, e in enumerate(p.LinkedObject.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
               and abs(e.Curve.Center.z) < 1e-6][0]
        make(self.doc, C.INSERT, "%s:Edge%d" % (p.Name, end), "%s:Edge%d" % (self.a.Name, mouth))
        f = dof.compute(self.doc)[p.Name]
        self.assertEqual((f.n, len(f.slides), len(f.turns)), (1, 0, 1))
        point, axis = f.turns[0]
        self.assertAlmostEqual(abs(axis.z), 1, places=3)  # the pin's own axis (its frame: z along the pin)
        self.assertLess(App.Vector(point.x, point.y, 0).Length, 1e-3)  # through the pin's centre line

    def test_count_is_relative_to_what_holds_it(self):
        _, mid_path = save_part(self.dir, "Mid", 20, 20, 10)
        m = assembly.place(self.doc, mid_path)  # free, no constraints
        make(self.doc, C.MATE, fz(m, 10), fz(self.b, 0))  # Block held only by the free Mid
        counts = dof.compute(self.doc)
        self.assertEqual(counts[self.b.Name].n, 3)
        self.assertEqual(counts[m.Name].n, 6)

    def test_nothing_grounded(self):
        assembly.unground(self.a)
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        counts = dof.compute(self.doc)
        self.assertEqual(counts[self.b.Name].n, 3)
        self.assertEqual(counts[self.a.Name].n, 3)
        single = App.newDocument("Solo")
        single.UndoMode = 1
        assembly.make_assembly(single, "mm")
        single.saveAs(os.path.join(self.dir, "Solo.FCStd"))
        only = assembly.place(single, self.block_path)
        assembly.unground(only)
        self.assertEqual(dof.compute(single)[only.Name].n, 6)

    def test_count_leaves_no_trace(self):
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        names = sorted(o.Name for o in self.doc.Objects)
        undo = list(self.doc.UndoNames)
        at = {c.Name: App.Placement(c.Placement) for c in assembly.components(self.doc)}
        dof.compute(self.doc)
        self.assertEqual(sorted(o.Name for o in self.doc.Objects), names)
        self.assertEqual(list(self.doc.UndoNames), undo)
        for c in assembly.components(self.doc):
            self.assertTrue(c.Placement.isSame(at[c.Name], 1e-9), c.Name)
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_busy_while_a_step_is_open(self):
        self.doc.openTransaction("Mate")
        with self.assertRaises(dof.Busy):
            dof.compute(self.doc)
        self.doc.abortTransaction()

    def test_cache_follows_constraints_not_placements(self):
        counts, computed = dof.ensure(self.doc)
        self.assertTrue(computed)
        self.assertEqual(counts[self.b.Name].n, 6)
        self.b.Placement = App.Placement(App.Vector(1, 2, 3), App.Rotation(10, 0, 0))
        self.assertEqual(dof.ensure(self.doc)[1], False, "a move does not recount")
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        self.assertIsNone(dof.cached(self.doc))
        self.assertEqual(dof.last(self.doc)[self.b.Name].n, 6, "the last numbers stay until the recount")
        counts, computed = dof.ensure(self.doc)
        self.assertTrue(computed)
        self.assertEqual(counts[self.b.Name].n, 3)

    def test_suppressed_part_is_not_counted(self):
        assembly.toggle_suppressed(self.b)
        self.assertNotIn(self.b.Name, dof.compute(self.doc))

    def test_sub_assembly_counts_as_one_part(self):
        sub = App.newDocument("Sub")
        sub.UndoMode = 1
        assembly.make_assembly(sub, "mm")
        sub_path = os.path.join(self.dir, "Sub.FCStd")
        sub.saveAs(sub_path)
        assembly.place(sub, self.block_path)
        sub.save()
        s = assembly.place(self.doc, sub_path)
        f = dof.compute(self.doc)[s.Name]
        self.assertEqual(f.n, 6, f.error)

    def test_part_without_a_solid_does_not_break_the_count(self):
        d = util.new_doc("Empty")
        document.make_part(d)
        d.recompute()
        path = os.path.join(self.dir, "Empty.FCStd")
        d.saveAs(path)
        e = assembly.place(self.doc, path)
        counts = dof.compute(self.doc)  # no exception
        self.assertIn(e.Name, counts)
        self.assertEqual(counts[self.b.Name].n, 6)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_dof.py`
Expected: ERROR `ModuleNotFoundError: No module named 'incad.core.dof'`.

- [ ] **Step 3: Implement** — create `InCad/incad/core/dof.py`:

```python
"""Degrees of freedom of assembly components (Inventor), counted by probing FreeCAD's solver: six small test moves
of a part, each solved; what the solver keeps is a freedom. Relative to what holds the part: every other free part
is held still (temporary grounds) while it is counted. The count runs in a transaction that is aborted, so it leaves
no undo step and nothing in the file. Pure model logic."""
import math
from collections import namedtuple

import FreeCAD as App

from incad.core import assembly

STEP, TURN = 0.5, 1.0  # mm, degrees
TOL = 0.2              # share of a step below which a kept motion counts as none

Freedom = namedtuple("Freedom", "n slides turns error")  # slides / turns in the part's own frame
_CACHE = {}            # doc name -> (signature, {link name: Freedom})


class Busy(Exception):
    """The document is loading or a dialog's step is open: no count now."""


def _num(v):
    return round(float(getattr(v, "Value", v) or 0), 9)


def signature(doc):
    """What the count depends on: every joint's kind, picks, value and suppressed state, the grounded and the
    suppressed parts. Placements are not in it (a drag does not change the freedoms)."""
    out = []
    for j in assembly.joints(doc):
        refs = []
        for p in ("Reference1", "Reference2"):
            ref = getattr(j, p, None)
            refs.append((ref[0].Name, tuple(ref[1])) if ref and ref[0] is not None else None)
        ground = getattr(j, "ObjectToGround", None)
        out.append((j.Name, str(getattr(j, "JointType", "")), tuple(refs), _num(getattr(j, "Distance", 0)),
                    _num(getattr(j, "Angle", 0)), bool(getattr(j, "Suppressed", False)),
                    ground.Name if ground is not None else None))
    out.append(tuple((c.Name, assembly.is_suppressed(c)) for c in assembly.components(doc)))
    return tuple(out)


def cached(doc):
    entry = _CACHE.get(doc.Name)
    return entry[1] if entry is not None and entry[0] == signature(doc) else None


def last(doc):
    entry = _CACHE.get(doc.Name)
    return entry[1] if entry is not None else None


def ensure(doc):
    """(counts, computed): the cached counts, or a fresh count when the constraints changed; the last counts (or
    None) while the document is busy."""
    counts = cached(doc)
    if counts is not None:
        return counts, False
    try:
        counts = compute(doc)
    except Busy:
        return last(doc), False
    _CACHE[doc.Name] = (signature(doc), counts)
    return counts, True


def _held_by_a_joint(doc, link):
    for j in assembly.joints(doc):
        if getattr(j, "Suppressed", False) or hasattr(j, "ObjectToGround"):
            continue
        if link in [(getattr(j, p, None) or (None,))[0] for p in ("Reference1", "Reference2")]:
            return True
    return False


def _centre(link):
    shape = getattr(link, "Shape", None)
    if shape is None or shape.isNull():
        return App.Vector(link.Placement.Base)
    return shape.BoundBox.Center


def _local(link, slides, turns):
    """Global directions / axes -> the part's own frame (so a drag that moves or turns it keeps them right)."""
    inv = link.Placement.inverse()
    rot = inv.Rotation
    return ([rot.multVec(d) for d in slides], [(inv.multVec(p), rot.multVec(a)) for p, a in turns])


def _all_free(link):
    c = _centre(link)
    axes = [App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)]
    return Freedom(6, *_local(link, list(axes), [(c, a) for a in axes]), error="")


def _probe(doc, asm, link, start):
    """The six test moves of one part (every other part held): Freedom in the part's own frame."""
    import numpy as np
    c = _centre(link)
    rows, motions = [], []
    for i in range(6):
        axis = App.Vector(*[1 if k == i % 3 else 0 for k in range(3)])
        if i < 3:
            delta = App.Placement(axis * STEP, App.Rotation())
        else:
            delta = App.Placement(App.Vector(), App.Rotation(axis, TURN), c)
        link.Placement = delta.multiply(start[link.Name])
        if asm.solve() != 0:
            raise ValueError("the solver failed")
        rel = App.Placement(link.Placement).multiply(start[link.Name].inverse())
        for name, plc in start.items():
            doc.getObject(name).Placement = plc
        moved = rel.multVec(c) - c
        angle = math.degrees(rel.Rotation.Angle)
        ax = rel.Rotation.Axis
        rows.append([moved.x / STEP, moved.y / STEP, moved.z / STEP,
                     ax.x * angle / TURN, ax.y * angle / TURN, ax.z * angle / TURN])
        motions.append(rel)
    m = np.array(rows)
    n = int(np.linalg.matrix_rank(m, tol=TOL)) if m.any() else 0
    trans = np.array([r[:3] for r in rows[:3] if np.linalg.norm(r[3:]) < TOL and np.linalg.norm(r[:3]) > TOL])
    slides = []
    if len(trans):
        _, s, vt = np.linalg.svd(trans)
        slides = [App.Vector(*vt[k]).normalize() for k in range(int((s > TOL).sum()))]
    turns = []
    for r, rel in zip(rows[3:], motions[3:]):
        if np.linalg.norm(r[3:]) < TOL:
            continue
        axis = App.Vector(rel.Rotation.Axis).normalize()
        if any(abs(axis.dot(a)) > 0.99 for _, a in turns):
            continue
        rot = np.array(rel.Rotation.toMatrix().A).reshape(4, 4)[:3, :3]
        t = np.array([rel.Base.x, rel.Base.y, rel.Base.z])
        p = np.linalg.lstsq(np.eye(3) - rot, t, rcond=None)[0]  # the line the part turned about
        point = App.Vector(*p)
        point = point + axis * (c - point).dot(axis)  # its point level with the part's centre
        turns.append((point, axis))
    return Freedom(n, *_local(link, slides, turns), error="")


def compute(doc):
    """{link name: Freedom} for every free, unsuppressed component."""
    if getattr(doc, "Restoring", False) or doc.HasPendingTransaction:
        raise Busy()
    asm = assembly.assembly_of(doc)
    comps = assembly.components(doc)
    free = [c for c in comps if not assembly.is_grounded(c) and not assembly.is_suppressed(c)]
    start = {c.Name: App.Placement(c.Placement) for c in comps}
    gdoc = None
    if App.GuiUp:
        import FreeCADGui as Gui
        gdoc = Gui.getDocument(doc.Name)
    modified = gdoc.Modified if gdoc is not None else None
    out, held = {}, []
    opened = bool(doc.UndoMode)
    if opened:
        doc.openTransaction("InCad DOF count")
    try:
        for c in free:
            if not _held_by_a_joint(doc, c):
                out[c.Name] = _all_free(c)  # nothing holds it (the solver would need a fixed part to say so)
        counted = [c for c in free if c.Name not in out]
        for c in counted:
            assembly.ground(c)
            held.append(c)
        for c in counted:
            assembly.unground(c)
            try:
                out[c.Name] = _probe(doc, asm, c, start)
            except Exception as e:
                out[c.Name] = Freedom(None, [], [], "Could not count: %s" % e)
            finally:
                for name, plc in start.items():
                    doc.getObject(name).Placement = plc
                assembly.ground(c)
    finally:
        for c in held:
            if doc.getObject(c.Name) is not None:
                assembly.unground(c)
        for name, plc in start.items():
            if doc.getObject(name) is not None:
                doc.getObject(name).Placement = plc
        if opened:
            doc.abortTransaction()
        doc.recompute()
        if gdoc is not None:
            gdoc.Modified = modified
    return out
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_dof.py`
Expected: all 13 PASS. If `test_insert_turns_about_the_pin_axis` finds the axis point off the centre line, print
`f.turns` and check `_probe`'s fixed-line solve: `rel.Base` is the translation of the relative placement, and
`(I - R)·p = t` holds for any point `p` on the turn axis.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/dof.py tests/headless/test_dof.py
git commit -m "DOF: count each assembly part's degrees of freedom by probing the solver (relative, cached, leaves no trace)"
```

---

### Task 4: Glyph geometry (pure)

**Files:**
- Modify: `InCad/incad/core/dof.py` (append)
- Test: `tests/headless/test_dof.py` (append a class)

**Interfaces:**
- Consumes: `Freedom` (Task 3).
- Produces: `dof.glyph(freedom, placement, centre, size) -> (lines, heads)`: `lines` list of point lists (global
  `App.Vector`), `heads` list of `(tip App.Vector, direction App.Vector unit)`. A slide gives one line with a head
  at each end; a turn gives a 270° arc (25 points) with one head at its end.

- [ ] **Step 1: Write the failing test** — append to `tests/headless/test_dof.py`:

```python
class GlyphTest(unittest.TestCase):
    def test_slides_are_double_arrows_and_turns_are_arcs_on_their_axis(self):
        z = App.Vector(0, 0, 1)
        f = dof.Freedom(3, [App.Vector(1, 0, 0), App.Vector(0, 1, 0)], [(App.Vector(0, 0, 0), z)], "")
        plc = App.Placement(App.Vector(10, 0, 0), App.Rotation(z, 90))  # the part moved and turned since the count
        lines, heads = dof.glyph(f, plc, App.Vector(10, 0, 5), 4.0)
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(heads), 5)
        a, b = lines[0]
        self.assertAlmostEqual((b - a).normalize().dot(App.Vector(0, 1, 0)), 1, places=6)  # own X turned to global Y
        arc = lines[2]
        self.assertEqual(len(arc), 25)
        for p in arc:
            self.assertAlmostEqual(p.z, 5, places=6)  # level with the centre
            self.assertAlmostEqual((p - App.Vector(10, 0, 5)).Length, 4.0 * 0.6, places=6)  # around the moved axis

    def test_no_freedom_no_glyph(self):
        self.assertEqual(dof.glyph(dof.Freedom(0, [], [], ""), App.Placement(), App.Vector(), 4.0), ([], []))
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_headless.sh test_dof.py` → the two new tests ERROR (`no attribute 'glyph'`).

- [ ] **Step 3: Implement** — append to `InCad/incad/core/dof.py`:

```python
def glyph(freedom, placement, centre, size):
    """Inventor's DOF glyph for a part now at `placement`: a double arrow per slide through `centre`, a 270° arc per
    turn around its axis (level with the centre). ([[Vector…]…] polylines, [(tip, direction)…] arrow heads)."""
    lines, heads = [], []
    rot = placement.Rotation
    for d in freedom.slides:
        g = rot.multVec(d).normalize()
        a, b = centre - g * size, centre + g * size
        lines.append([a, b])
        heads += [(b, g), (a, g * -1)]
    for point, axis in freedom.turns:
        ax = rot.multVec(axis).normalize()
        p = placement.multVec(point)
        base = p + ax * (centre - p).dot(ax)
        u = ax.cross(App.Vector(1, 0, 0))
        if u.Length < 1e-6:
            u = ax.cross(App.Vector(0, 1, 0))
        u.normalize()
        w = ax.cross(u)
        r = size * 0.6
        ts = [1.5 * math.pi * k / 24 for k in range(25)]
        pts = [base + (u * math.cos(t) + w * math.sin(t)) * r for t in ts]
        lines.append(pts)
        end = ts[-1]
        heads.append((pts[-1], (u * -math.sin(end) + w * math.cos(end)).normalize()))
    return lines, heads
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_headless.sh test_dof.py` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/dof.py tests/headless/test_dof.py
git commit -m "DOF: glyph geometry (double arrows for slides, arcs on the turn axes), following the part's placement"
```

---

### Task 5: DOF on the component rows, recounted after constraint changes

**Files:**
- Modify: `InCad/incad/core/tree.py:178-194` (`_assembly`)
- Modify: `InCad/incad/ui/shell.py` (`__init__` fields near line 321; end of `_refresh`; new methods next to
  `assembly_ground`)
- Test: `tests/headless/test_tree.py` (class from Task 2), create `tests/gui/test_assembly_drag.py` (first tests)

**Interfaces:**
- Consumes: `dof.last`, `dof.ensure`, `Freedom` (Task 3).
- Produces: component node `detail` = `"grounded" | "DOF n" | "DOF ?" | ""`, tooltip = the count's error when
  `"DOF ?"` (else the part file path as now); `shell.dof_display_changed()` (no-op until Task 8 fills it in);
  `shell._dof_pending`.

- [ ] **Step 1: Write the failing headless test** — append to `AssemblyRowsTest` in `tests/headless/test_tree.py`:

```python
    def test_component_rows_show_the_last_count(self):
        from incad.core import dof, tree
        dof._CACHE.clear()
        detail = lambda: {n.name: n.detail for n in tree.build(self.doc)[0].children if n.kind == "component"}
        self.assertEqual(detail(), {self.a.Name: "grounded", self.b.Name: ""})  # not counted yet: nothing shown
        dof.ensure(self.doc)
        self.assertEqual(detail(), {self.a.Name: "grounded", self.b.Name: "DOF 6"})
        dof._CACHE[self.doc.Name] = (dof.signature(self.doc),
                                     {self.b.Name: dof.Freedom(None, [], [], "Could not count: the solver failed")})
        node = [n for n in tree.build(self.doc)[0].children if n.name == self.b.Name][0]
        self.assertEqual((node.detail, node.tooltip), ("DOF ?", "Could not count: the solver failed"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_headless.sh test_tree.py` → FAIL (`'' != 'DOF 6'`).

- [ ] **Step 3: Implement the rows** — in `InCad/incad/core/tree.py` `_assembly`, replace the component loop:

```python
    from incad.core import dof
    counts = dof.last(doc) or {}
    for c in assembly.components(doc):
        f = counts.get(c.Name)
        detail = "grounded" if assembly.is_grounded(c) else "" if assembly.is_suppressed(c) or f is None else \
            "DOF ?" if f.n is None else "DOF %d" % f.n
        tip = f.error if f is not None and f.n is None else (c.LinkedObject.Document.FileName if c.LinkedObject else "")
        root.children.append(Node("component", c.Label, c.Name,
                                  state="suppressed" if assembly.is_suppressed(c) else
                                  ("" if document.is_shown(c) else "hidden"),
                                  detail=detail, tooltip=tip, children=_component_rows(c)))
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_headless.sh test_tree.py` → PASS.

- [ ] **Step 5: Implement the deferred count in the shell** — in `Shell.__init__` (next to `self._wait_notice = None`):

```python
        self._dof_pending = False
```

  At the very end of `_refresh` (after the ribbon / panels are updated; `doc` and `is_asm` are already local there):

```python
        if is_asm and fs is None:
            self._schedule_dof(doc)
```

  New methods next to `assembly_ground`:

```python
    def _schedule_dof(self, doc):
        """Count the parts' degrees of freedom after the refresh (never inside it): the rows fill in when done."""
        if self._dof_pending:
            return
        self._dof_pending = True
        QtCore.QTimer.singleShot(0, lambda name=doc.Name: self._update_dof(name))

    def _update_dof(self, name):
        import FreeCAD as App
        from incad.core import dof
        self._dof_pending = False
        if name not in App.listDocuments() or self.feature_session is not None:
            return
        drag = getattr(self, "asm_drag", None)
        if drag is not None and drag.active():
            return
        try:
            _, computed = dof.ensure(App.getDocument(name))
        except Exception as e:
            log.logger().warning("DOF count: %s", e)
            return
        if computed:
            self.schedule_refresh()  # the rows read the new counts (cached now: no second count)
        self.dof_display_changed()

    def dof_display_changed(self):
        """Redraw the DOF glyphs (Task 8)."""
```

- [ ] **Step 6: Write the GUI tests** — create `tests/gui/test_assembly_drag.py` with setup, the rows test and the
  two Review Focus tests (undo recount, file not modified). Later tasks append to this file and to its
  `harness.run` list:

```python
"""Assembly: DOF on the rows, dragging a part along its own freedoms (FreeCAD's native drag), DOF glyphs."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, prefs, safe, tree  # noqa: E402
from incad.features import constraints as C  # noqa: E402
from incad.ui import shell  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["asm"])


def obj(key):
    return doc().getObject(ST[key])


def rows():
    return {n.name: n.detail for n in tree.build(doc())[0].children if n.kind == "component"}


def fz(link, z):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if abs(f.CenterOfMass.z - z) < 1e-6][0])


def constrain(kind, first, second):
    r = safe.run_safely(kind.TITLE, lambda: kind.create(doc(), None, None, dict(kind.defaults(doc(), None),
                                                                               first=first, second=second)), doc())
    assert r.ok, r.error
    s().schedule_refresh()
    harness.pump(1200)
    return r.value


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_drag_")
    for name, w, h, t in (("Plate", 60, 40, 10), ("Mid", 20, 20, 10), ("Top", 8, 8, 6)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    d = actions.new_assembly("mm")
    d.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = d.Name
    for key, name in (("p", "Plate"), ("m", "Mid"), ("t", "Top")):
        ST[key] = s().assembly_place(ST[name]).Name
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1500)


def test_1_rows_show_dof():
    assert rows() == {ST["p"]: "grounded", ST["m"]: "DOF 6", ST["t"]: "DOF 6"}, rows()
    constrain(C.MATE, fz(obj("m"), 10), fz(obj("t"), 0))  # Top on the free Mid
    assert rows()[ST["t"]] == "DOF 3", rows()


def test_2_undo_of_a_constraint_recounts():
    commands.REGISTRY.run("edit.undo")
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 6", rows()
    commands.REGISTRY.run("edit.redo")
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 3", rows()


def test_3_count_does_not_mark_the_file_modified():
    doc().save()
    gdoc = Gui.getDocument(ST["asm"])
    assert not gdoc.Modified
    from incad.core import dof
    dof._CACHE.clear()
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["t"]] == "DOF 3", rows()  # it did recount
    assert not gdoc.Modified, "a count is no change to save"


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


TESTS = [test_0_setup, test_1_rows_show_dof, test_2_undo_of_a_constraint_recounts,
         test_3_count_does_not_mark_the_file_modified]
harness.run(TESTS + [test_9_cleanup])
```

- [ ] **Step 7: Run the GUI test**

Run: `tests/run_gui.sh tests/gui/test_assembly_drag.py`
Expected: 5 passed. If `test_3` fails on `Modified`, `abortTransaction` or the temporary grounds' view providers set
the flag after `compute` returned: reset `gdoc.Modified = modified` again in `_update_dof` after `dof.ensure` (keep
the one in `compute`).

- [ ] **Step 8: Commit**

```bash
git add InCad/incad/core/tree.py InCad/incad/ui/shell.py tests/headless/test_tree.py tests/gui/test_assembly_drag.py
git commit -m "Assembly rows show each part's DOF (grounded / DOF n / DOF ?), recounted after constraint changes"
```

---

### Task 6: Gesture rules report a drag; the navigator calls a drag hook

**Files:**
- Modify: `InCad/incad/core/gestures.py` (docstring, `feed`, `_left_held`, `_passthrough`)
- Modify: `InCad/incad/ui/nav.py` (`Navigator.__init__`, `_do`)
- Test: `tests/widgets/test_gestures.py`, `tests/widgets/test_nav_hooks.py`

**Interfaces:**
- Produces: gesture actions `("drag_start", x, y)` (the left press that became a drag, before its
  `("replay_press", x, y)`) and `("drag_end",)` (its release, or a lost release); `Navigator.drag_hook` — any object
  with `begin(view, viewport, x, y)` and `end()`; exceptions inside the hook are logged and never stop the replay.

- [ ] **Step 1: Write the failing widget tests** — in `tests/widgets/test_gestures.py` replace
  `test_left_drag_is_handed_to_freecad` with:

```python
    def test_left_drag_is_handed_to_freecad_and_reported(self):
        a, b, c, d = self.feed(("press", LEFT, LEFT, 10, 10), ("move", 0, LEFT, 12, 10),
                               ("move", 0, LEFT, 30, 10), ("release", LEFT, 0, 30, 10))
        self.assertEqual((a, b), ([], []))
        self.assertEqual(c, [("drag_start", 10, 10), ("replay_press", 10, 10), PASS])
        self.assertEqual(d, [("drag_end",), PASS])
        self.assertEqual(self.g.state, "idle")

    def test_a_click_is_no_drag(self):
        out = self.feed(("press", LEFT, LEFT, 10, 10), ("release", LEFT, 0, 11, 10))
        self.assertNotIn(("drag_start", 10, 10), out[1])

    def test_a_lost_release_ends_the_drag(self):
        self.feed(("press", LEFT, LEFT, 10, 10), ("move", 0, LEFT, 30, 10))
        self.assertEqual(self.g.feed("move", 0, 0, 40, 10), [("drag_end",), PASS])
        self.assertEqual(self.g.state, "idle")
```

  In `tests/widgets/test_nav_hooks.py` add to `HooksTest`:

```python
    def test_drag_hook_begins_before_the_replay_and_ends_on_release(self):
        L = QtCore.Qt.LeftButton
        seen = []

        class Hook:
            def begin(self, view, viewport, x, y):
                seen.append(("begin", x, y))

            def end(self):
                seen.append(("end",))

        self.nav.drag_hook = Hook()
        self.nav._replay = lambda *a, **k: seen.append(("replay",))
        move = lambda x: QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(x, 10), QtCore.QPointF(x, 10),
                                           QtCore.Qt.NoButton, L, QtCore.Qt.NoModifier)
        self.nav.eventFilter(self.w, ev("press", L, L))
        self.nav.eventFilter(self.w, move(40))
        self.nav.eventFilter(self.w, ev("release", L, QtCore.Qt.NoButton))
        self.assertEqual(seen, [("begin", 10.0, 10.0), ("replay",), ("end",)])

    def test_a_failing_drag_hook_still_replays(self):
        L = QtCore.Qt.LeftButton
        seen = []

        class Hook:
            def begin(self, *a):
                raise RuntimeError("boom")

            def end(self):
                pass

        self.nav.drag_hook = Hook()
        self.nav._replay = lambda *a, **k: seen.append("replay")
        move = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(40, 10), QtCore.QPointF(40, 10),
                                 QtCore.Qt.NoButton, L, QtCore.Qt.NoModifier)
        self.nav.eventFilter(self.w, ev("press", L, L))
        self.nav.eventFilter(self.w, move)
        self.assertEqual(seen, ["replay"])
```

  Any other test in `test_gestures.py` that expects `[PASS]` on the release of a left drag now gets
  `[("drag_end",), PASS]`: update it the same way (the drag's release is reported, nothing else changes).

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_gestures.py` and `tests/run_widgets.sh test_nav_hooks.py`
Expected: the new / changed tests FAIL (no `drag_start` / `drag_end`; the hook is never called).

- [ ] **Step 3: Implement the gesture rules** — `InCad/incad/core/gestures.py`:
  - docstring: add `('drag_start', x, y)` — the left press became a drag (sent before its replay) and
    `('drag_end',)` — that drag's release (or a lost one).
  - in `feed`, the lost-release branch:

```python
            ended = [("orbit_end",)] if self.state == "orbit" else [(self.mode + "_end",)] if self.state == "tool" \
                else [("drag_end",)] if self.state == "passthrough" else []
```

  - in `_left_held`, the far move:

```python
        if kind == "move" and self._far(self.press, x, y):
            self.state = "passthrough"
            return [("drag_start",) + self.press, ("replay_press",) + self.press, PASS]
```

  - `_passthrough`:

```python
    def _passthrough(self, kind, button, buttons, x, y):
        if kind == "release" and buttons == 0:
            self.reset()
            return [("drag_end",), PASS]
        return [PASS]
```

- [ ] **Step 4: Implement the hook** — `InCad/incad/ui/nav.py`:
  - `__init__`: after `self.dblclick_hook = None` add
    `self.drag_hook = None      # begin(view, viewport, x, y) on a left drag, end() on its release`
  - `_do`, first branches:

```python
        if name in ("drag_start", "drag_end"):
            if self.drag_hook is not None:
                try:
                    if name == "drag_start":
                        self.drag_hook.begin(view, viewport, action[1], action[2])
                    else:
                        self.drag_hook.end()
                except Exception:
                    log.logger().exception("InCad drag")
            return
```

- [ ] **Step 5: Run to verify they pass**

Run: `tests/run_widgets.sh test_gestures.py` and `tests/run_widgets.sh test_nav_hooks.py` → all PASS.

- [ ] **Step 6: Commit**

```bash
git add InCad/incad/core/gestures.py InCad/incad/ui/nav.py tests/widgets/test_gestures.py tests/widgets/test_nav_hooks.py
git commit -m "Navigation: a left press that becomes a drag is reported (drag_start / drag_end) to a drag hook"
```

---

### Task 7: Drag a part along its own DOF (`ui/asm_drag.py`)

**Files:**
- Create: `InCad/incad/ui/asm_drag.py`
- Modify: `InCad/incad/core/safe.py` (flag + `edit_open`)
- Modify: `InCad/incad/ui/shell.py` (`_edit_open`, navigator wiring near line 640, `_teardown`)
- Test: `tests/gui/test_assembly_drag.py` (append), `tests/headless/test_safe.py` (append)

**Interfaces:**
- Consumes: `Navigator.drag_hook` (Task 6), `dof.last` (Task 3), `assembly.*`, `incad.ui.nav.to_coin`.
- Produces: `safe.set_drag_edit(on: bool)`, `safe.drag_edit() -> bool`; `AssemblyDrag(shell)` with
  `begin(view, viewport, x, y) -> bool`, `end()` (deferred finish), `finish()`, `active() -> bool`,
  `link_name: str | None`; `shell.asm_drag`.

- [ ] **Step 1: Write the failing headless test** — append to `tests/headless/test_safe.py` (inside its test class;
  add the import of `safe` if the file imports it differently):

```python
    def test_a_drag_edit_is_no_open_task(self):
        from incad.core import safe
        safe.set_drag_edit(True)
        try:
            self.assertTrue(safe.drag_edit())
            self.assertFalse(safe.edit_open())
        finally:
            safe.set_drag_edit(False)
        self.assertFalse(safe.drag_edit())
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_headless.sh test_safe.py` → ERROR (`no attribute 'set_drag_edit'`).

- [ ] **Step 3: Implement the flag** — `InCad/incad/core/safe.py`, above `edit_open`:

```python
_drag_edit = False


def set_drag_edit(on):
    """An assembly is in FreeCAD's edit only for a drag of one of its parts (incad.ui.asm_drag): that is no FreeCAD
    task, InCad's commands and refreshes go on."""
    global _drag_edit
    _drag_edit = bool(on)


def drag_edit():
    return _drag_edit
```

  and the first line of `edit_open`'s body: `if _drag_edit: return False`.

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_headless.sh test_safe.py` → PASS.

- [ ] **Step 5: Write the failing GUI tests** — append to `tests/gui/test_assembly_drag.py` (before
  `test_9_cleanup`), and extend `TESTS`:

```python
def view():
    return Gui.getDocument(ST["asm"]).ActiveView


def viewport():
    return view().graphicsView().viewport()


def screen_of(point):
    vp = viewport()
    x, y = view().getPointOnViewport(point)
    dpr = vp.devicePixelRatioF()
    return QtCore.QPointF(x / dpr, vp.height() - y / dpr)


def send(kind, pos, button, buttons):
    vp = viewport()
    glob = QtCore.QPointF(vp.mapToGlobal(pos.toPoint()))
    QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, pos, glob, button, buttons, QtCore.Qt.NoModifier))


def drag(start, dx, dy, steps=12):
    L = QtCore.Qt.LeftButton
    send(QtCore.QEvent.MouseMove, start, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
    harness.pump(300)
    send(QtCore.QEvent.MouseButtonPress, start, L, L)
    harness.pump(100)
    for i in range(1, steps + 1):
        send(QtCore.QEvent.MouseMove, QtCore.QPointF(start.x() + dx * i / steps, start.y() + dy * i / steps),
             QtCore.Qt.NoButton, L)
        harness.pump(60)
    send(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(start.x() + dx, start.y() + dy), L, QtCore.Qt.NoButton)
    harness.pump(800)


def top_of(key):
    bb = obj(key).Shape.BoundBox
    return screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))


def same(a, b):
    return a.isSame(b, 1e-7)


def test_4_drag_moves_only_along_its_own_dof():
    m, t = obj("m"), obj("t")
    bm, bt = App.Placement(m.Placement), App.Placement(t.Placement)
    n0 = len(doc().UndoNames)
    drag(top_of("t"), 70, -60)
    assert not same(t.Placement, bt), "Top moved"
    assert same(m.Placement, bm), "the free Mid it is Mated to stays put"
    assert abs(t.Shape.BoundBox.ZMin - m.Shape.BoundBox.ZMax) < 1e-6, "still on Mid's face"
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Move part", doc().UndoNames[:3]
    assert not [j for j in assembly.joints(doc()) if getattr(j, "ObjectToGround", None) is m], "no ground left"
    assert Gui.getDocument(ST["asm"]).getInEdit() is None and not safe.drag_edit()
    ST["moved_from"] = bt


def test_5_undo_and_redo_of_a_drag():
    t = obj("t")
    moved_to = App.Placement(t.Placement)
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    assert same(t.Placement, ST["moved_from"]), t.Placement
    commands.REGISTRY.run("edit.redo")
    harness.pump(800)
    assert same(t.Placement, moved_to)
    assert len([j for j in assembly.joints(doc()) if hasattr(j, "ObjectToGround")]) == 1, "only Plate's ground"


def test_6_grounded_part_stays_and_says_so():
    p = obj("p")
    bp = App.Placement(p.Placement)
    bb = p.Shape.BoundBox
    drag(screen_of(App.Vector(bb.XMin + 3, bb.YMin + 3, bb.ZMax)), -50, 20)
    assert same(p.Placement, bp)
    assert "Plate is grounded" in s().status.texts()["message"], s().status.texts()


def test_7_a_click_selects_without_edit():
    Gui.Selection.clearSelection()
    pos = top_of("t")
    L = QtCore.Qt.LeftButton
    send(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
    harness.pump(300)
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    harness.pump(60)
    send(QtCore.QEvent.MouseButtonRelease, pos, L, QtCore.Qt.NoButton)
    harness.pump(600)
    assert Gui.Selection.getSelectionEx("", 0), "the click selected"
    assert Gui.getDocument(ST["asm"]).getInEdit() is None
    Gui.Selection.clearSelection()


def test_8_fully_constrained_part_is_not_dragged():
    p, m = obj("p"), obj("m")
    def fx(link, x):
        return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                          if abs(f.CenterOfMass.x - x) < 1e-6][0])
    def fy(link, y):
        return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                          if abs(f.CenterOfMass.y - y) < 1e-6][0])
    constrain(C.MATE, fz(p, 10), fz(m, 0))
    constrain(C.FLUSH, fx(p, 0), fx(m, 0))
    constrain(C.FLUSH, fy(p, 0), fy(m, 0))
    assert rows()[ST["m"]] == "DOF 0", rows()
    bm = App.Placement(m.Placement)
    n0 = len(doc().UndoNames)
    bb = m.Shape.BoundBox
    drag(screen_of(App.Vector(bb.XMax - 2, bb.YMax - 2, bb.ZMax)), 60, 40)
    assert same(m.Placement, bm)
    assert len(doc().UndoNames) == n0, "no empty step"
    assert "Mid is fully constrained" in s().status.texts()["message"], s().status.texts()


def test_8b_no_drag_while_a_constraint_dialog_is_open():
    t = obj("t")
    bt = App.Placement(t.Placement)
    commands.REGISTRY.run("constrain.flush")
    harness.pump(800)
    assert s().feature_session is not None
    drag(top_of("t"), 60, 30)
    assert same(t.Placement, bt), "the part does not move while the dialog is open"
    s()._close_feature_session(cancel=True)
    harness.pump(800)
```

  and set `TESTS = [test_0_setup, test_1_rows_show_dof, test_2_undo_of_a_constraint_recounts,
  test_3_count_does_not_mark_the_file_modified, test_4_drag_moves_only_along_its_own_dof,
  test_5_undo_and_redo_of_a_drag, test_6_grounded_part_stays_and_says_so, test_7_a_click_selects_without_edit,
  test_8_fully_constrained_part_is_not_dragged, test_8b_no_drag_while_a_constraint_dialog_is_open]`.

  (`s().status.texts()["message"]` is how `tests/gui/test_assembly.py` reads the status line;
  `_close_feature_session(cancel=True)` is how the shell itself cancels a dialog.)

- [ ] **Step 6: Run to verify they fail**

Run: `tests/run_gui.sh tests/gui/test_assembly_drag.py`
Expected: `test_4` FAILS (Top did not move: nothing puts the assembly in edit), `test_6` / `test_8` fail on the
status message.

- [ ] **Step 7: Implement** — create `InCad/incad/ui/asm_drag.py`:

```python
"""Drag a free assembly part with the mouse along its own degrees of freedom (Inventor). FreeCAD's native drag,
which works only while the assembly is in edit: the edit is held for the drag alone, inside InCad's own "Move part"
step, with every other free part held by a temporary ground so the solver moves the dragged part only (FreeCAD's
drag pulls free neighbours along). Order matters: resetEdit closes the transaction that was open at setEdit, so
setEdit comes before the step opens and the step is committed before resetEdit."""
import FreeCAD as App

from incad.core import assembly, dof, log, safe
from incad.qt import QtCore


class AssemblyDrag:
    def __init__(self, shell):
        self.shell = shell
        self.doc_name = None
        self.link_name = None
        self._held = []
        self._start = None

    def active(self):
        return self.link_name is not None

    def _component_at(self, view, viewport, x, y):
        from incad.ui.nav import to_coin
        doc = App.ActiveDocument
        if not assembly.is_assembly(doc):
            return None, None
        info = view.getObjectInfo(to_coin(viewport, x, y))
        name = (info.get("SubName") or "").split(".")[0] if info else ""
        link = doc.getObject(name) if name else None
        return doc, (link if link is not None and link in assembly.components(doc) else None)

    def begin(self, view, viewport, x, y):
        """On a left press that became a drag: start FreeCAD's drag of the free part under it, else nothing."""
        sh = self.shell
        if self.active() or sh.feature_session is not None or any(
                getattr(sh, a, None) is not None for a in ("_point_pick", "_region_pick", "_profile_pick")):
            return False  # a dialog, a tool or a pick owns the mouse
        doc, link = self._component_at(view, viewport, x, y)
        if link is None or assembly.is_suppressed(link):
            return False
        shape = getattr(link, "Shape", None)
        if shape is None or shape.isNull():
            return False
        if assembly.is_grounded(link):
            log.report("info", "%s is grounded" % link.Label)
            return False
        known = (dof.last(doc) or {}).get(link.Name)
        if known is not None and known.n == 0:
            log.report("info", "%s is fully constrained" % link.Label)
            return False
        import FreeCADGui as Gui
        asm = assembly.assembly_of(doc)
        if doc.HasPendingTransaction:  # a stray change: its own step, apart from the drag
            doc.commitTransaction()
        if not doc.UndoMode:
            doc.UndoMode = 1
        self.doc_name, self.link_name = doc.Name, link.Name
        self._start = App.Placement(link.Placement)
        try:
            asm.ViewObject.MoveInCommand = False
            safe.set_drag_edit(True)
            Gui.getDocument(doc.Name).setEdit(asm.Name)
            doc.openTransaction("Move part")
            self._held = [c.Name for c in assembly.components(doc) if c is not link
                          and not assembly.is_grounded(c) and not assembly.is_suppressed(c)]
            for name in self._held:
                assembly.ground(doc.getObject(name))
        except Exception as e:
            log.report("warning", "Can't drag %s: %s" % (link.Label, e))
            self.finish(moved_ok=False)
            return False
        self.shell.dof_display_changed()
        return True

    def end(self):
        """The drag's release: finished once FreeCAD has handled the release itself."""
        if self.active():
            QtCore.QTimer.singleShot(0, self.finish)

    def finish(self, moved_ok=True):
        if not self.active():
            return
        import FreeCADGui as Gui
        doc_name, link_name, held, start = self.doc_name, self.link_name, self._held, self._start
        self.doc_name = self.link_name = self._start = None
        self._held = []
        doc = App.getDocument(doc_name) if doc_name in App.listDocuments() else None
        moved, label = False, link_name
        try:
            if doc is not None:
                for name in held:
                    o = doc.getObject(name)
                    if o is not None:
                        assembly.unground(o)
                link = doc.getObject(link_name)
                label = link.Label if link is not None else link_name
                moved = moved_ok and link is not None and not link.Placement.isSame(start, 1e-9)
                if doc.HasPendingTransaction:
                    doc.commitTransaction() if moved else doc.abortTransaction()
        finally:
            try:
                gdoc = Gui.getDocument(doc_name) if doc is not None else None
                if gdoc is not None and gdoc.getInEdit() is not None:
                    gdoc.resetEdit()
                asm = assembly.assembly_of(doc) if doc is not None else None
                if asm is not None:
                    asm.ViewObject.MoveInCommand = True
            finally:
                safe.set_drag_edit(False)
                self.shell.schedule_refresh()
                self.shell.dof_display_changed()
        if moved:
            log.report("info", "Moved %s" % label)
```

  `InCad/incad/ui/shell.py`:
  - `_edit_open`: last line becomes `return (vp is not None or safe.edit_open()) and not safe.drag_edit()`.
  - after `self.navigator.dblclick_hook = self._dblclick_hook` (line ~641):

```python
        from incad.ui.asm_drag import AssemblyDrag
        self.asm_drag = AssemblyDrag(self)
        self.navigator.drag_hook = self.asm_drag
```

  - in `Shell.__init__` (next to `_dof_pending`): `self.asm_drag = None`.
  - in `_teardown`, before `self.stop_slot_tool()`:

```python
        if self.asm_drag is not None and self.asm_drag.active():
            self.asm_drag.finish(moved_ok=False)
```

- [ ] **Step 8: Run to verify they pass**

Run: `tests/run_gui.sh tests/gui/test_assembly_drag.py`
Expected: all pass. If `test_4` shows two undo steps, something opened a transaction before `setEdit` (check
`doc.HasPendingTransaction` right before `setEdit` in `begin`); if Mid moves, the grounds were added before
`setEdit` or `MoveInCommand` stayed True.

- [ ] **Step 9: Commit**

```bash
git add InCad/incad/ui/asm_drag.py InCad/incad/core/safe.py InCad/incad/ui/shell.py tests/headless/test_safe.py \
  tests/gui/test_assembly_drag.py
git commit -m "Assembly: drag a free part with the mouse along its own DOF (FreeCAD's drag, others held, one Move part step)"
```

---

### Task 8: DOF glyphs — View ▸ Degrees of Freedom and the hover / drag tip

**Files:**
- Create: `InCad/incad/ui/dof_glyphs.py`
- Modify: `InCad/incad/actions.py` (handlers + `view.dof` command)
- Modify: `InCad/incad/ui/ribbon_layout.py:59-61` (assembly View ▸ Visual Style)
- Modify: `InCad/incad/ui/shell.py` (fields, `dof_display_changed`, `toggle_dof`, `dof_shown`, `_on_dof_hover`,
  hover observer in `_install_hooks` / `_remove_hooks`, module functions)
- Test: `tests/gui/test_assembly_drag.py` (append), `tests/widgets/test_ribbon.py` only if it pins the assembly
  layout (run it)

**Interfaces:**
- Consumes: `dof.last`, `dof.glyph`, `Freedom` (Tasks 3–4); `asm_drag.link_name` (Task 7).
- Produces: `DofGlyphs(view, theme)` with `set(items)` where items are `[(lines, heads, size, highlight)]`,
  `clear()`, `remove()`, `count` (number of parts drawn), node name `"InCadDOF"`; `HoverWatch(callback)` — a
  selection observer calling `callback(link_name | None)` on preselection changes; command `view.dof`;
  `shell.toggle_dof()`, `shell.dof_shown() -> bool`.

- [ ] **Step 1: Write the failing GUI tests** — append to `tests/gui/test_assembly_drag.py` and to `TESTS`:

```python
def glyph_parts():
    g = s()._dof_glyphs
    return 0 if g is None else g.count


def test_9a_view_button_draws_only_available_freedoms():
    from incad.core import dof
    assert glyph_parts() == 0
    commands.REGISTRY.run("view.dof")
    harness.pump(800)
    free = [n for n, f in (dof.last(doc()) or {}).items() if f.n]
    assert glyph_parts() == len(free) and ST["t"] in free and ST["m"] not in free, (glyph_parts(), free)  # Mid is DOF 0
    lines, heads = s()._dof_glyphs.parts[ST["t"]]
    assert (lines, heads) == (3, 5), (lines, heads)  # Top on Mid: two slides (double arrows) and one turn
    commands.REGISTRY.run("view.dof")
    harness.pump(500)
    assert glyph_parts() == 0


def test_9b_hover_tip_on_a_free_part_only():
    s()._on_dof_hover(ST["t"])
    harness.pump(300)
    assert glyph_parts() == 1 and s()._dof_glyphs.highlighted == [ST["t"]]
    s()._on_dof_hover(ST["m"])  # DOF 0: no tip
    harness.pump(300)
    assert glyph_parts() == 0
    s()._on_dof_hover(None)
    harness.pump(300)
    assert glyph_parts() == 0


def test_9c_hover_from_real_preselection():
    pos = top_of("t")
    send(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
    harness.pump(600)
    assert glyph_parts() == 1, glyph_parts()
    vp = viewport()
    send(QtCore.QEvent.MouseMove, QtCore.QPointF(5, 5), QtCore.Qt.NoButton, QtCore.Qt.NoButton)  # empty corner
    harness.pump(600)
    assert glyph_parts() == 0, glyph_parts()
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_gui.sh tests/gui/test_assembly_drag.py`
Expected: `test_9a` FAILS (`unknown command view.dof` / no `_dof_glyphs`).

- [ ] **Step 3: Implement the renderer** — create `InCad/incad/ui/dof_glyphs.py`:

```python
"""Inventor's DOF glyphs on the 3D view (never in the document): a double arrow per direction a part can slide, an
arc per axis it can turn about. Not clickable (SoAnnotation outside the document). HoverWatch tells which assembly
part the pointer rests on (FreeCAD's preselection), for the tip."""
from incad.ui import theme as themes


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class DofGlyphs:
    def __init__(self, view, theme="light"):
        from pivy import coin
        self.view, self.theme = view, theme
        self.count, self.parts, self.highlighted = 0, {}, []
        self.node = coin.SoAnnotation()
        self.node.setName("InCadDOF")
        view.getSceneGraph().addChild(self.node)

    def set(self, items):
        """items: [(name, lines, heads, size, highlight)] — dof.glyph output per part, its size, the tip colour."""
        from pivy import coin
        self.clear()
        palette = themes.PALETTES[self.theme]
        for name, lines, heads, size, highlight in items:
            sep = coin.SoSeparator()
            color = coin.SoBaseColor()
            color.rgb.setValue(*_rgb(palette["accent" if highlight else "marker_end"]))
            style = coin.SoDrawStyle()
            style.lineWidth = 3
            sep.addChild(color)
            sep.addChild(style)
            for pts in lines:
                coords = coin.SoCoordinate3()
                coords.point.setValues(0, len(pts), [(p.x, p.y, p.z) for p in pts])
                sep.addChild(coords)
                sep.addChild(coin.SoLineSet())
            h = size * 0.25
            for tip, d in heads:
                head = coin.SoSeparator()
                t = coin.SoTransform()
                base = tip - d * (h / 2)
                t.translation.setValue(base.x, base.y, base.z)
                t.rotation.setValue(coin.SbRotation(coin.SbVec3f(0, 1, 0), coin.SbVec3f(d.x, d.y, d.z)))
                cone = coin.SoCone()
                cone.height, cone.bottomRadius = h, size * 0.1
                head.addChild(t)
                head.addChild(cone)
                sep.addChild(head)
            self.node.addChild(sep)
            self.parts[name] = (len(lines), len(heads))
            if highlight:
                self.highlighted.append(name)
        self.count = len(items)

    def clear(self):
        self.node.removeAllChildren()
        self.count, self.parts, self.highlighted = 0, {}, []

    def remove(self):
        self.clear()
        try:
            self.view.getSceneGraph().removeChild(self.node)
        except Exception:
            pass


class HoverWatch:
    """Selection observer: callback(component name | None) when FreeCAD's preselection enters or leaves an
    assembly part (a preselection in an assembly is the Assembly object with 'Link.Body.Face6')."""

    def __init__(self, callback):
        self.callback = callback
        self.current = None

    def _set(self, name):
        if name != self.current:
            self.current = name
            self.callback(name)

    def setPreselection(self, doc, obj, sub):
        import FreeCAD as App
        from incad.core import assembly
        d = App.getDocument(doc) if doc in App.listDocuments() else None
        asm = assembly.assembly_of(d) if assembly.is_assembly(d) else None
        name = (sub or "").split(".")[0] if asm is not None and obj == asm.Name else ""
        link = d.getObject(name) if name else None
        self._set(link.Name if link is not None and link in assembly.components(d) else None)

    def removePreselection(self, doc, obj, sub):
        self._set(None)
```

- [ ] **Step 4: Implement the command and the shell side**

  `InCad/incad/actions.py` — handlers:

```python
def toggle_dof():
    from incad.ui import shell
    shell.toggle_dof()


def dof_shown():
    from incad.ui import shell
    return shell.dof_shown()
```

  command (next to `view.toggle_visibility`):

```python
        Command(id="view.dof", label="Degrees of Freedom", icon="rotational", handler=toggle_dof,
                checkable=True, is_checked=dof_shown, contexts=frozenset({"assembly"}),
                tooltip="Show how each part can still move: arrows for slides, arcs for turns"),
```

  (`rotational` is an existing icon; `tests/widgets/test_icons.py` checks icon names exist — run it.)

  `InCad/incad/ui/ribbon_layout.py` — assembly View ▸ Visual Style list gets `"view.dof"` after
  `"view.toggle_visibility"`.

  `InCad/incad/ui/shell.py`:
  - `__init__` fields (next to `self.asm_drag = None`):

```python
        self._dof_glyphs = None   # DofGlyphs on the active assembly view
        self._dof_on = set()      # assemblies whose View > Degrees of Freedom is on
        self._dof_hover = None    # the free part under the pointer (the tip)
        self._hover_watch = None
```

  - replace the Task 5 stub `dof_display_changed` and add the rest next to it:

```python
    def dof_display_changed(self):
        """Redraw the DOF glyphs: every free part while View > Degrees of Freedom is on, else the part under the
        pointer or being dragged (highlighted). Only the freedoms a part has; none for DOF 0."""
        import FreeCAD as App
        import FreeCADGui as Gui
        from incad.core import assembly, dof
        from incad.ui.dof_glyphs import DofGlyphs
        doc = App.ActiveDocument
        view = Gui.ActiveDocument.ActiveView if assembly.is_assembly(doc) and Gui.ActiveDocument else None
        if self._dof_glyphs is not None and (view is None or self._dof_glyphs.view is not view):
            self._dof_glyphs.remove()
            self._dof_glyphs = None
        if view is None or not hasattr(view, "getSceneGraph"):
            return
        counts = dof.last(doc) or {}
        tip = self.asm_drag.link_name if self.asm_drag is not None and self.asm_drag.active() else self._dof_hover
        names = list(counts) if doc.Name in self._dof_on else [tip] if tip else []
        items = []
        for name in names:
            f, link = counts.get(name), doc.getObject(name)
            if f is None or not f.n or link is None or link.Shape.isNull():
                continue
            bb = link.Shape.BoundBox
            size = max(bb.DiagonalLength * 0.35, 5.0)
            lines, heads = dof.glyph(f, link.Placement, bb.Center, size)
            items.append((name, lines, heads, size, name == tip))
        if self._dof_glyphs is None:
            if not items:
                return
            self._dof_glyphs = DofGlyphs(view, self.theme)
        self._dof_glyphs.set(items)

    def toggle_dof(self):
        import FreeCAD as App
        from incad.core import assembly
        doc = App.ActiveDocument
        if not assembly.is_assembly(doc):
            raise ValueError("Open an assembly first")
        self._dof_on ^= {doc.Name}
        self.dof_display_changed()
        self.schedule_refresh()  # the ribbon button's checked state

    def dof_shown(self):
        import FreeCAD as App
        return App.ActiveDocument is not None and App.ActiveDocument.Name in self._dof_on

    def _on_dof_hover(self, name):
        self._dof_hover = name
        self.dof_display_changed()
```

  - `_install_hooks`, after the `_SelectionWatch` lines:

```python
        if self._hover_watch is None:
            from incad.ui.dof_glyphs import HoverWatch
            self._hover_watch = HoverWatch(self._on_dof_hover)
            Gui.Selection.addObserver(self._hover_watch)
```

  - `_teardown`, next to the `_sel_watch` removal (same try / except shape it uses):

```python
        if self._hover_watch is not None:
            try:
                import FreeCADGui as Gui
                Gui.Selection.removeObserver(self._hover_watch)
            except Exception:
                pass
            self._hover_watch = None
        if self._dof_glyphs is not None:
            self._dof_glyphs.remove()
            self._dof_glyphs = None
```

  - module-level functions next to `assembly_remove`:

```python
def toggle_dof():
    return _active().toggle_dof()


def dof_shown():
    sh = _shell
    return bool(sh is not None and sh.active and sh.dof_shown())
```

  - at the end of `_refresh` (after the Task 5 lines): `self.dof_display_changed()` so a tab switch, an undo or a
    finished drag redraws the glyphs at the parts' new placements.

- [ ] **Step 5: Run to verify they pass**

Run: `tests/run_gui.sh tests/gui/test_assembly_drag.py`, `tests/run_widgets.sh test_icons.py`,
`tests/run_widgets.sh test_ribbon.py`, `tests/run_widgets.sh test_commands.py`
Expected: all pass. If `test_9c` fails because the synthetic move gives no preselection, check that the view got the
move (`send` goes to the viewport, InCad's filter passes a hover); do not drive the real mouse.

- [ ] **Step 6: Commit**

```bash
git add InCad/incad/ui/dof_glyphs.py InCad/incad/actions.py InCad/incad/ui/ribbon_layout.py InCad/incad/ui/shell.py \
  tests/gui/test_assembly_drag.py
git commit -m "View > Degrees of Freedom: Inventor's DOF glyphs (only the freedoms a part has); the part under the pointer or being dragged shows its glyph as a tip"
```

---

### Task 9: The user's assembly, the full suites, notes

**Files:**
- Modify: `docs/superpowers/DECISIONS.md` (one Status entry), `CHANGES` section per the release-notes rule only when
  a build is made (not in this plan).

- [ ] **Step 1: Verify on a copy of the user's assembly** — copy, never the originals:

```bash
mkdir -p /tmp/incad_real && cp /Volumes/Docs/Plasticity_projects/Thread_1-Assembly.FCStd \
  /Volumes/Docs/Plasticity_projects/Thread_1-Solid*.FCStd /tmp/incad_real/
```

  Write a throwaway GUI script (in the scratchpad, run with `tests/run_gui.sh <script>`) that opens
  `/tmp/incad_real/Thread_1-Assembly.FCStd`, waits for the refresh, prints `rows()` (every component's DOF text) and
  `dof.last(doc)`, turns View ▸ Degrees of Freedom on and prints `s()._dof_glyphs.parts`, then drags one free part
  with the `drag()` helper and prints its placement before / after and `doc.UndoNames[:2]`. Expected: no exception
  in `INCAD_LOG`, a DOF number on every free part, one "Move part" step, the grounded part unmoved.

- [ ] **Step 2: Run the full suites once**

Run: `tests/run_all.sh`
Expected: everything passes (screen unlocked). Any failure: read it, fix it in the task that owns the code, rerun
only that file, then this step once more.

- [ ] **Step 3: Note the outcome** — append a Status line to `docs/superpowers/DECISIONS.md`: what the real-file run
  showed (counts, glyph parts, drag result) and the suite totals.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/DECISIONS.md
git commit -m "Assembly drag + DOF: checked on the user's Thread_1 assembly; full suites green"
```
