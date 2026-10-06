# InCad 2 — Threads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Real, printable threads: a Thread feature on any cylindrical face (external or internal) in ten profile
families, and modeled threads in Hole, both with a print clearance.

**Architecture:** Pure tables (`incad/threads/standards.py`) and pure groove geometry (`incad/threads/profile.py`)
are tested without FreeCAD; the Thread kind turns them into one hidden profile sketch (attached to the face's start
edge, `SectionOfRevolution`) and one `PartDesign::SubtractiveHelix`. Hole uses FreeCAD's modeled threads.

**Tech Stack:** FreeCAD 1.1.3 PartDesign (SubtractiveHelix, Hole), PySide6.

**Spec:** `docs/superpowers/specs/2026-10-06-incad-stage2-threads-design.md`

## Global Constraints

- Stage-1 constraints hold (one undo step per dialog, busy flag, plain-language errors, values as model parameters
  where they are user values, throwaway `user.cfg`, Qt via `incad.qt`, announce GUI runs).
- Thread data and groove geometry never import FreeCAD (unit-tested with the widgets runner's plain Python).
- Turns of a groove never touch: groove width ≤ pitch − 0.04 mm (or 0.9 × pitch for fine pitches).
- Default print clearance 0.2 mm diametral (Print-friendly family: 0.3 mm), preference `ThreadClearance`.

## Review Focus

1. A face that is not cylindrical (or a cone) is refused with a plain reason (Task 3 test).
2. The suggested size matches the picked diameter for shafts (nominal) and bores (minor + clearance) (Task 1 test).
3. Editing a thread (size, clearance, hand) regenerates the same feature, keeps its place and one undo step
   (Task 3 test).
4. Large clearance on a fine pitch still gives a valid solid (clamped groove) (Task 2/3 tests).
5. Threaded Hole switches back to plain cleanly (Task 4 test).

## Tasks

### Task 1: Standards tables
**Files:** Create `InCad/incad/threads/__init__.py`, `InCad/incad/threads/standards.py`, `tests/widgets/test_thread_standards.py`.
**Produces:** `STANDARDS` (ordered `[(key, label)]`: iso, iso_fine, unc, unf, g, npt, tr, acme, print, custom);
`sizes(std) -> [name]`; `spec(std, size, custom=None) -> ThreadSpec(major, pitch, angle, depth, crest_ext,
crest_int, taper, std, size)` (mm, degrees; `taper` = half-angle in degrees); `suggest(std, diameter, internal,
clearance) -> size`; `bore_diameter(spec, clearance) -> mm`; `default_clearance(std)`.
**Tests:** M8 pitch 1.25 and major 8; M10x1.25 in iso_fine; 1/4-20 UNC pitch 1.27, major 6.35; G1/4 major 13.157
pitch 1.337; NPT 1/4 pitch 1.411 taper 1.7899; Tr16x4 depth 2.5; ACME 1/2-10; suggest(iso, 10.0, False) = M10;
suggest(iso, 8.6, True, 0.2) = M10; every spec of every size has 0 < depth < pitch and width checks pass;
custom spec from (pitch, angle, depth, major).

### Task 2: Groove profile
**Files:** Create `InCad/incad/threads/profile.py`, `tests/widgets/test_thread_profile.py`.
**Produces:** `groove(spec, internal, clearance, runout=None) -> [(r, z)]` closed polygon (counter-clockwise, no
repeated first point), centred on z = 0; `max_width(spec)`.
**Tests:** external M10: points span r from 10/2 − depth − c/2 to beyond 5; width at r = 5 equals 7/8·P (c = 0)
and grows with clearance; internal: span reaches 5 + c/2; every horizontal width < pitch for every size of every
standard at clearance 0.6; polygon is simple (no self-intersection).

### Task 3: Thread feature
**Files:** Create `InCad/incad/features/thread.py`, `tests/headless/test_thread.py`; Modify `features/__init__.py`,
`features/common.py` (pick kind `cylinder`), `core/prefs.py` (`thread_clearance`).
**Produces:** kind `thread` (`TITLE "Thread"`, `ICON "thread"`, `TYPES ("PartDesign::SubtractiveHelix",)` — kind_for
only claims helices with the `InCadThread` property, `NEEDS_PROFILE False`, `PRESELECT {"face": "cylinder"}`,
fields face, standard, size, length_mode (full / distance), length, offset, hand, clearance; `options(key, values)`
for the size list; `defaults`, `create`, `read`, `update`, `_pad_of`).
**Tests:** M10 external on a Ø10×20 shaft: valid, removed volume within ±15 % of the analytic groove area × path;
internal M10 in a Ø8.6 bore of a block: valid, removes material outside the bore; left hand flag; NPT taper sets
Angle; length parameter drives Height; edit size → same object, volume changes; non-cylindrical face refused;
clearance 0.6 on M3 still valid; Tip is the thread.

### Task 4: Threaded Hole
**Files:** Modify `InCad/incad/features/hole.py`, `tests/headless/test_hole.py`.
**Produces:** Hole fields `threaded` (bool), `thread_standard` (iso, iso_fine, unc, unf, unef, npt, g, bsw, bsf),
`thread_size` (combo), `thread_depth` (hole/distance) + `thread_length`, `clearance`, `hand`; `options()`.
**Tests:** threaded M8 through: Threaded, ModelThread, ThreadSize "M8x1.25", custom clearance 0.2; read round
trip; switching back to plain clears Threaded and keeps the diameter parameter.

### Task 5: Combo fields
**Files:** Modify `InCad/incad/ui/feature_dialog.py`, `InCad/incad/ui/feature_session.py`,
`tests/widgets/test_feature_dialog.py`.
**Produces:** field kind `combo` (QComboBox; `values()` gives the item data); `set_options(key, [(value,label)])`
keeps the current value when still offered, else the first; the session calls `kind.options(key, values)` for
every combo after each change and at start.
**Tests:** options follow another field; value kept when still offered; `changed` emitted once per user change.

### Task 6: Command, icon, ribbon, GUI tests
**Files:** `tools/make_icons.py` (thread), `actions.py` (`feature.thread`), `ribbon_layout.py` (Modify group),
`marking_layout.py` (face list), `tests/gui/test_threads.py`, `tests/widgets/test_actions.py`.
**Tests:** pick a shaft face → Thread → size suggested → OK → one undo step, Tip is the thread; Hole ▸ Threaded M6
through → modeled; edit thread size from the browser (double-click path).

### Task 7: Look check, README.
