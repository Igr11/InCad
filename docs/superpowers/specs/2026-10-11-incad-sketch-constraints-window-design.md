# InCad — Sketch Constraints window and right-click delete (design)

## 1. Intent

In a sketch the user must be able to see and delete constraints, including those with no icon to click
(coincident points, point on a line), as in Inventor's "Show Constraints". Today a dimension or a constraint icon
can be clicked and deleted, but InCad hides FreeCAD's constraint list, so the rest can't be reached. Agreed with
the user (2026-10-11):

- A **Constraints window** opened from the ribbon: the sketch's constraints in a list. **Picking a line or point in
  the sketch filters the list** to that element's constraints (Esc / clearing the pick shows all again). Rows are
  checkable; **Delete selected** removes them.
- **Selecting a row highlights it in the sketch**: the constraint (its icon or dimension) and the lines/points it ties.
- **Right-click on a line or point**: below the marking ring, one entry per constraint on it ("Delete Horizontal",
  "Delete Coincident (Line 2)", "Delete Distance 20 mm"), then "Delete all constraints (N)" and "Constraints…"
  (opens the window filtered to that element).

## 2. The window

```
Constraints — Sketch2                 [×]
[ Picked: Line 3 ]   (Esc: show all)
-----------------------------------------
☐ Coincident    Line 3 ↔ Line 2
☐ Horizontal    Line 3
☐ Distance      Line 3          d4 = 20 mm
-----------------------------------------
[Select all]  [Delete selected]  [Close]
```

- A `QFrame` overlay on the 3D view like the Section panel (`incad/ui/section_panel.py` pattern: created on demand,
  parented to the MDI viewport, top-left, themed, kept raised by `_raise_overlays`). Not modal: the user keeps
  drawing while it is open. It lives only while a sketch is in edit; finishing the sketch or editing another closes
  it (handled in `Shell._refresh`, as the value box is).
- One row per constraint: **type** (FreeCAD names: Coincident, Point on Object, Horizontal, Vertical, Parallel,
  Perpendicular, Tangent, Equal, Symmetric, Block (Fix), Distance, Horizontal Distance, Vertical Distance, Radius,
  Diameter, Angle, …), **what it ties** in the user's words (Line 3, Arc 1, Circle 2, Point 5, "Line 3 start",
  Origin, X axis, Projected edge 1), and for a dimension its **name and value** (`d4 = 20 mm`, a formula shown as
  written). Construction geometry is named the same, with "(construction)".
- **Filter**: the window follows the sketch selection (the shell's `_SelectionWatch` already reports every
  selection change). Elements picked → only constraints that touch any of them; nothing picked → all. The header
  says what the filter is. Esc in the window clears the pick.
- **Row → sketch**: selecting a row selects that constraint in the sketch (`ConstraintN`) and adds the geometry it
  ties, so FreeCAD highlights them. A constraint whose symbol is hidden (Hide Constraints / virtual space) is still
  listed; selecting it shows the tied geometry only.
- **Delete selected**: all checked rows (or the selected row when none is checked) in **one undo step**
  ("Delete Constraints"), highest index first so indices stay valid. The list refreshes; DoF in the status bar
  follows.
- **Ribbon**: Sketch tab ▸ Constrain group, a new button **Constraints** (`sketch.constraints_window`, its own icon
  in `tools/make_icons.py`). Also in the sketch marking-menu list.

## 3. Right-click entries

- In sketch edit, `Shell._open_marking_menu` today opens the "sketch" menu without looking at what is under the
  cursor. It will read the element under the cursor (preselection) — else the current sketch selection — before
  opening the menu, and pass extra **dynamic items** to the menu.
- The marking menu only knows registered command ids today. It gets a small extension: extra items given as
  `(label, icon, callable)` shown at the end of the list (after a separator), run through the same safe/undo path as
  commands. Static layout and flick slots are unchanged.
- Entries for the element: "Delete <Type> (<other element>)" per constraint (at most 8; more → only "Delete all"
  and "Constraints…"), "Delete all constraints (N)", "Constraints…". Nothing under the cursor → no extra items.

## 4. Constraints InCad owns (guards)

- **Sketch pattern ties** (named `pat<n>_<i>`, `incad.core.sketch_patterns`): listed under their pattern
  ("Pattern 1 tie"), but deleting one is refused with "Part of Pattern 1: edit or delete the pattern" — deleting
  a tie would silently free a copy and break the pattern's parameter links.
- **Dimensions used by formulas** (`dN` referenced by another expression — a feature value, another dimension, a
  model parameter): deleting is refused with "d4 is used by Extrude1 (Distance), d7: change those first". A plain
  dimension deletes freely, and its value box closes (as today when a dimension vanishes).
- InCad's own pins (polygon centre pins, slot constraints) are ordinary constraints and can be deleted.
- `reconcile_replaced` (dimension renaming) must not misread a delete as a replacement: a delete from the window or
  menu never adds a dimension in the same change, so it is safe; a test proves it.

## 5. Code

- `incad/core/sketch_constraints.py` (no Qt): `rows(sk) -> [Row(index, name, type, ties, text, owner)]`,
  `for_elements(sk, subs)`, `describe_element(sk, geo, pos)`, `guard(sk, indices) -> refusal or None`,
  `delete(sk, indices)`. Element naming reuses `sketch_patterns.element`.
- `incad/ui/constraints_panel.py`: the window (list, filter header, buttons, theme), signals `delete(indices)`,
  `highlight(index)`, `closed`.
- `incad/ui/shell.py`: open/close, selection-follow, lifetime, dynamic marking-menu items.
- `incad/ui/marking_menu.py`: extra callable items.
- `incad/actions.py`, `ribbon_layout.py`, `marking_layout.py`, `tools/make_icons.py`: the command and icon.

## 6. Testing

- Headless (`tests/headless/test_sketch_constraints.py`): row text for each constraint kind, filter by line / point
  / external edge, delete several in one undo step (undo restores them), pattern tie refused, formula-used dimension
  refused, plain dimension deleted, hidden (virtual space) constraints listed, `reconcile_replaced` not fooled.
- Widgets: the panel lists rows, filter header, Select all, Delete emits the checked indices; marking menu shows
  and runs extra callable items.
- GUI (real window): open from the ribbon in a sketch; pick a line → list filtered; select a row → constraint and
  geometry selected; delete a coincident via the window and via right-click → gone, one undo step, DoF updated;
  window closes on Finish Sketch.

## 7. Out of scope

Editing a constraint from the window (double-click a dimension already edits it in the sketch), adding constraints
from the window, suppressing/deactivating constraints, reordering.
