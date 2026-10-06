# InCad 4 — Assemblies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Inventor-style assemblies: separate part files placed as links, first grounded, constraints and joints
through native FreeCAD Assembly joints, values as parameters.

**Architecture:** `incad/core/assembly.py` (pure model functions, headless-tested) wraps Assembly objects and joint
creation; constraint/joint kinds reuse the feature dialog/session; the shell gains an "assembly" mode (ribbon,
browser, marking menu).

**Tech Stack:** FreeCAD 1.1.3 Assembly workbench (AssemblyObject, JointObject), App::Link, PySide6.

**Spec:** `docs/superpowers/specs/2026-10-06-incad-stage4-assemblies-design.md`

## Global Constraints

- Stage-1..3 constraints hold. Joints are created with FreeCAD's own JointObject classes.
- Picks in an assembly are stored as `Link:Element` (the component and its element).

## Review Focus

1. Place/Create on an unsaved assembly asks for its file instead of failing (Task 4 test).
2. A constraint between two ungrounded components still solves (one moves) (Task 2 test).
3. Undo of a constraint restores the component's placement (Task 4 GUI test).
4. Over-constraining shows a plain reason and leaves the previous placement (Task 2 test).
5. Picks on the assembly in the 3D view resolve to `Link:Element` (Task 1 test).

### Task 1: Assembly model (headless)
Files: `InCad/incad/core/assembly.py`, `InCad/incad/features/common.py` (resolve assembly paths),
`tests/headless/test_assembly.py`.
Produces: `make_assembly(doc, units)`, `is_assembly(doc)`, `assembly_of(doc)`, `components(doc)`,
`place(doc, path) -> link`, `ground(link)`, `unground(link)`, `is_grounded(link)`, `create_part(doc, path, units)`,
`joints(doc)`.
Tests: marker; place grounds first; second placed beside (no overlap of bounding boxes); same file twice → two
links; unground/ground; create_part saves a new part file with a body and links it; unsaved assembly → ValueError
"Save the assembly first"; resolve((assembly, "Block.Body.Pad.Face5")) → (link, "Face5").

### Task 2: Constraint and joint kinds (headless)
Files: `InCad/incad/features/constraints.py`, `features/__init__.py`, `tests/headless/test_constraints.py`.
Produces: kinds MATE, FLUSH, ANGLE, TANGENT, INSERT, RIGID, ROTATIONAL, SLIDER, CYLINDRICAL, BALL (fields first,
second picks + offset/angle value; `create/read/update` on joint objects; `kind_for` claims joints by
`InCadConstraint`).
Tests: Mate puts the block on the plate (zmin 10); offset parameter 2 mm → zmin 12; Flush aligns top faces
(zmax equal); Angle 90° between side faces; Insert aligns a pin axis with a hole; Rigid fixes relative placement;
two ungrounded components: one moves; conflicting second Mate → ValueError with a plain reason and placement kept.

### Task 3: Shell assembly mode
Files: `actions.py` (`file.new_assembly`, `assembly.place` P, `assembly.create`, `assembly.ground`, constraint and
joint commands), `ui/ribbon_layout.py` (assembly mode), `ui/marking_layout.py` (assembly contexts),
`core/tree.py` (components + Relationships), `ui/new_dialog.py` (Assembly tile enabled), `ui/shell.py` (mode,
file dialogs), `tools/make_icons.py` (assembly, place, create_component, mate, flush, angle_c, tangent, insert,
rigid, rotational, slider, cylindrical, ball, ground), widget tests.

### Task 4: GUI tests, look check, README
Files: `tests/gui/test_assembly.py`, README.
Tests: new assembly (saved to a temp folder) → place two saved parts → first grounded → Mate via dialog → one undo
step; undo restores the placement; browser lists components and the Mate.
