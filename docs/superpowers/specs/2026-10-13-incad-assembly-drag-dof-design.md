# InCad — Assembly: drag parts, degrees of freedom, constraint rows (design)

Agreed with the user on 2026-10-13 (Inventor's assembly drag, DOF and the browser's constraint menu). Built on
FreeCAD's native Assembly drag and solver; the spike that proved both is in DECISIONS.md ("assembly drag + DOF
spike", 2026-10-13) with its scripts in `docs/superpowers/spikes/2026-10-13-assembly-drag/`.

## 1. Constraint rows (Relationships)

- Already there: a double-click or the menu's **Edit** opens the constraint's dialog (8bf6053); `delete.delete` removes
  a constraint as one undo step "Delete", the parts staying where they are.
- A constraint row gets **its own marking menu** (layout `joint`, instead of the part-feature `browser` one):
  N **Edit**, S **Delete**, E **Suppress** / **Unsuppress**, W **Rename**; the list holds the same four.
- The **Delete key** removes the constraint whose row is selected.
- **Suppress**: the joint's `Suppressed` is set; the solver ignores it, the row stays (greyed and struck through, as a
  suppressed component), its picks and value are kept, the parts do not move — they only become freer.
  **Unsuppress**: it acts again and the parts are solved to meet it; if it can't be met any more the step is refused
  with the existing "can't be met" message, the constraint stays suppressed and the placements are restored.
- Every one of these is one undo step; the DOF numbers (section 3) follow.
- Picking a constraint's glyph in the 3D view is out of scope: the tree row is the way to a constraint.

## 2. Dragging a part

### 2.1 Behaviour

- In an assembly tab, a **left drag that starts on a free component** moves it as FreeCAD's solver allows: a free part
  moves in the screen plane, a Mated part slides on its face, an Inserted pin turns or slides in its hole.
- A drag that starts on a **grounded** part or on **empty space** is what it is today (FreeCAD's own handling); on a
  grounded part the status line says "<Part> is grounded".
- A plain **click** still selects; LMB+RMB still orbits; the right button stays InCad's.
- Every drag is **one undo step "Move part"**; InCad's Undo puts the part back. After the drag the selection is empty
  (FreeCAD clears it) and the status line says "Moved <Part>".

### 2.2 How it works

- The assembly is in FreeCAD's edit mode (`Gui.getDocument(d).setEdit(asm.Name)`) **only during the drag** — FreeCAD
  drags nothing in an assembly that is not in edit; the rest of the time InCad's commands (refused while an edit is
  open) work as now.
- `core/gestures.py`: the left press that becomes a drag (moved more than `DRAG_PX`) gets its own action,
  `('drag_start', x, y)`, sent before `('replay_press', x, y)`; the press that ends as a click replays as now with no
  `drag_start`. The machine stays pure (no Qt, no FreeCAD).
- `ui/asm_drag.py` (new), used by the navigator through a hook as `click_hook` is (`Navigator.drag_hook`), so
  `nav.py` stays generic:
  - `begin(view, viewport, x, y)` on `drag_start`: the active document is an assembly, no InCad tool or pick is
    waiting, and `view.getObjectInfo(to_coin(...))` hits a component (first name of its `SubName`) that is not grounded
    and not suppressed → `setEdit(assembly)` right before the press is replayed (no event pump needed, spike);
    otherwise nothing (and "<Part> is grounded" for a grounded hit).
  - `end()` on the release of that drag, deferred (`QTimer.singleShot(0)`) so FreeCAD handles the release first →
    `resetEdit()`, refresh, status line. Also on a lost release (the gesture machine's "buttons gone" rule), and before
    the assembly's tab or document closes.
- While the drag's edit is open, `safe.edit_open()` and `shell._edit_open()` do not count it as "a FreeCAD task is
  open" (a flag in `asm_drag` both read): a refresh timer firing mid-drag must not show the wait notice.

### 2.3 Dragging inside a constraint dialog

- With a constraint dialog open (Mate, Flush, Angle, Tangent, Insert, Rigid, Rotational, Slider, Cylindrical, Ball), a
  left **drag** on a free part moves it; a **click** stays a pick for First / Second.
- Before both picks are made the drag respects the existing constraints (turn the part so the face you need shows);
  once the preview constraint exists it respects that too (try the motion before OK).
- **OK** keeps the constraint and where the part was dragged, as one undo step named as the dialog ("Mate");
  **Cancel** puts every part back where it was when the dialog opened, drags included.
- How: the dialog already holds an open transaction (`feature_session`); during a dialog the assembly's view provider
  runs the drag with `MoveInCommand = False`, so FreeCAD opens no "Move part" command and the moves join the dialog's
  step (Cancel's abort undoes them). After a drag the next preview update starts from where the part was left: the
  constraint's pre-align ("bring the free part near the answer") runs only when the constraint is not met from the
  current placement.
- **First task of the plan**: verify that a drag with `MoveInCommand = False` leaves the dialog's transaction intact
  (one step on OK, everything back on Cancel). If it does not, no drag while a dialog is open (a drag there orbits /
  selects as now) and this section is dropped.

## 3. Degrees of freedom

### 3.1 What the user sees

- Every **component row** shows its freedom in the row's detail: **grounded**, **DOF 0**, **DOF 1** … **DOF 6**;
  **DOF ?** when the count failed (the reason in the tooltip); nothing for a suppressed component.
- **View ▸ Degrees of Freedom** (`view.dof`, on/off, assembly context; also in the assembly ribbon's view group):
  while on, every free part shows Inventor's glyph at its centre — a straight **double arrow** for each direction it
  can slide, an **arc with an arrowhead** for each axis it can turn about, drawn on that axis (an Inserted pin's arc
  is around the pin's axis). The glyphs are view markers (`SoAnnotation`, as `ui/point_markers`), never document
  objects, sized to the part, in the theme's colours, rebuilt after every change while on. Off by default; switching
  tabs keeps the choice per assembly view.

### 3.2 How it is counted (`core/dof.py`, pure model logic)

- Per free (not grounded, not suppressed) component, **relative to what holds it** (Inventor): every other free part
  is held still with a temporary ground during its count.
- Six small test moves of the part about its centre — 0.5 mm along X, Y, Z and 1° about X, Y, Z — each followed by
  `asm.solve()`; what the solver keeps of each move is a freedom. The DOF number is the rank of the kept moves
  (numpy, tolerance 0.2 of a step); their directions give the arrows, and the rotations' fixed lines (from the kept
  rotation's placement) give the arcs' axes.
- The whole count runs inside a transaction that is **aborted** at the end, in a `finally`, and every placement is
  restored exactly: no undo step, no leftover ground, nothing in the file.
- `dof.compute(doc) -> {link_name: Freedom(n, slides=[Vector…], turns=[(point, axis)…], error="")}`; grounded parts
  are not probed (the solver keeps a moved grounded part where it is).

### 3.3 When it is counted

- Not inside `tree.build` (pure, every refresh): a deferred step after the refresh computes it and the rows fill in.
- Cached per document against a **signature of the constraints**: each joint's kind, picks, value and suppressed state,
  plus the grounded and suppressed components. Moving or dragging parts does not recount; adding, editing, deleting
  or suppressing a constraint, grounding or suppressing a part does.
- Never while the document is loading (`doc.Restoring`) or while a dialog's transaction is open: the rows keep the
  last numbers until the dialog closes.
- Cost ~60 ms per free part (spike), about 1 s for 15 free parts, only after a constraint change.

## 4. Errors

- Drag: `setEdit` failing or FreeCAD refusing the drag → the press goes to FreeCAD as a plain press (as today) and the
  status line says why; a lost release ends the edit; closing the tab or document resets the edit first.
- DOF: a failed solve in a probe → that part's **DOF ?** (reason in the tooltip); an exception is logged, the tree keeps
  working, no glyphs are drawn for that part.
- Constraint rows: an Unsuppress that can't be met is refused, placements restored (section 1).

## 5. Testing

Only the affected files while working; the full suites at most once before a commit.

- **Headless** `tests/headless/test_dof.py`: free 6, Mate 3, Mate+Flush 1, Mate+2×Flush 0, Insert 1 with its turn
  axis on the pin's axis; B held only by a free C counts 3; grounded and suppressed parts; no undo step and no
  leftover object after a count; a move does not recount, a constraint edit does.
- **Headless** constraint rows: Delete, Suppress / Unsuppress (DOF changes; an unmeetable Unsuppress refused, parts
  back), Rename — each one undo step.
- **Widgets / pure**: the gesture machine's `drag_start` on a drag, none on a click.
- **GUI** `tests/gui/test_assembly_drag.py` (from the spike): free part moves, grounded stays, a Mated part slides,
  one "Move part" step, Undo; a click selects without entering edit; orbit works; a drag inside the Mate dialog,
  Cancel puts the part back, OK keeps it as one "Mate" step; DOF text on the rows; View ▸ Degrees of Freedom adds and
  removes the glyphs (counted as `SoAnnotation` nodes); the constraint-row menu and the Delete key.
- **The user's file**: DOF and drag on a copy of `Thread_1-Assembly.FCStd` (with its part files) from
  `/Volumes/Docs/Plasticity_projects`, never the originals, before saying done.

## Out of scope

Picking a constraint in the 3D view; drag with collision detection; Inventor's "Drive constraint" animation; DOF
analysis dialogs (over-/redundant constraints); dragging a sub-assembly's inner parts (a sub-assembly moves as one
component).
