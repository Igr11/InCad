# Sweep Wall and Sketch Pattern Along a Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Sweep gets a Wall option (thickness, inside/outside, which ends stay open) built as a helper Thickness under the Sweep; (2) a third sketch pattern, Along Path: copies of sketch geometry at stations along a chain of this sketch's lines, arcs and splines, orientation Identical or Follow path, By spacing or Fit to path.

**Architecture:** Sweep wall = `features/shapes.py` adds the fields and a helper `PartDesign::Thickness` (`InCadHelperOf`, like the thread's chamfer) whose removed faces are the pipe's end caps found by the spine's end points. Path pattern = `core/sketch_patterns.py` gains `build_path` (stations by arc length on an ordered chain, copies placed exactly, tied to the original rigidly: constant DistanceX/DistanceY for Identical, a locked construction centre with Equal+Angle spokes for Follow path); `features/sketch_patterns.py` gains kind `SKETCH_PATH`; pick kind `sketch_path`.

**Tech Stack:** FreeCAD 1.1.3 (PartDesign, Sketcher, Part edges `getParameterByLength/valueAt/tangentAt`), unittest; tests via `tests/run_headless.sh`, `tests/run_widgets.sh`, `tests/run_gui.sh`.

**Spec:** sweep wall: agreed in chat 2026-10-10 (dialog block Wall: Thickness, Side, Ends; one tree row, helper under it); path pattern: `docs/superpowers/specs/2026-10-09-incad-sketch-patterns-design.md` §7 with this plan's rulings: copies are placed exactly at creation and re-placed on edit; count/spacing live in the record (no model parameter in v1); orientation Follow path = rigid rotation by the tangent change, as a rotation about a per-copy locked construction centre.

## Global Constraints

- UI text English; chat in Russian. Run only affected test files; `tests/run_fast.sh` once before the merge.
- Verify on the frozen real part `tests/gui/data/p2_test_reordered.FCStd` (Sketch006 = two open chains is a path candidate) before saying done.
- Never `setGeometryId`; pattern constraints are named `pat<n>_<i>` and hidden in virtual space; all constraints of a build added in ONE `addConstraint(list)`.
- Every new command needs icons in both themes from `tools/make_icons.py` and its id in `tests/widgets/test_actions.py: EXPECTED`.

## Review Focus

1. Deleting a Sweep deletes its wall helper (Task 2 headless test).
2. Editing an existing Sweep that has a wall and clearing the thickness removes the helper and the tip moves back to the Sweep (Task 1 test).
3. A path whose picked segments are not connected is refused with "The path's segments must join end to end" (Task 4 test).
4. Count × spacing longer than the path is refused with the room available (Task 4 test).
5. A copy that would land on a spline still gets its rigid ties (Task 5 test with a spline path).

---

### Task 1: Sweep wall — core (apply/read/update) with helper Thickness

**Files:** Modify `InCad/incad/features/shapes.py` (Sweep section), `InCad/incad/features/dressup.py` (SHELL.claims); Test `tests/headless/test_shapes.py` (append class `SweepWallTest`).

**Interfaces produced:** values keys `hollow` (bool), `wall` ("1 mm"), `side` ("inside"|"outside"), `ends` ("both_open"|"start_closed"|"end_closed"|"both_closed"); `shapes.wall_of(f)` → helper Thickness or None; `shapes._end_faces(f)` → (start "FaceN", end "FaceN").

- [ ] Test (RED): a circle profile on YZ (r 5) swept along a 40 mm line on XY; `SWEEP.create(... {"profile":"Prof","path":"Path","operation":"join","hollow":True,"wall":"1 mm","side":"inside","ends":"both_open"})` → `wall_of(f)` is a `PartDesign::Thickness` with `InCadHelperOf == f.Name`, `body.Tip is helper`, volume ≈ π(5²−4²)·40 within 2 %; `ends="both_closed"` → volume ≈ π25·40 − π16·38; `SWEEP.read` returns the wall values; `update` with `hollow=False` removes the helper and `body.Tip is f`; `SHELL.claims(helper)` is False (kind_for(helper) is SWEEP via `claims`).
- [ ] Implement: `FIELDS += (Field("hollow","Wall","bool",default=False), Field("wall","Thickness","value_length",default="1 mm",show_if=("hollow",(True,))), Field("side","Side","choice",(("inside","Inside"),("outside","Outside")),"inside",show_if=...), Field("ends","Ends","choice",(("both_open","Both open"),("start_closed","Start closed"),("end_closed","End closed"),("both_closed","Both closed")),"both_open",show_if=...))`; `PROPS={"wall": ...}` not needed (value_param on the helper handles the parameter name `Sweep_wall`? keep plain `Value`). `_sweep_apply`: after setting Profile/Spine, `doc.recompute()`, then `_wall_apply(doc, body, f, values)`: if not hollow → `_remove_wall(f)`; else find/create helper `body.newObject("PartDesign::Thickness","SweepWall")` with `InCadHelperOf` (addProperty App::PropertyString), `Base=(f, faces)` where faces = ends by `_end_faces(f)` (both_open → both; start_closed → [end]; end_closed → [start]; both_closed → []), `Value` via `value_param(doc, helper, "Value", wall, "length")`, `Reversed = side == "inside"`, `Mode="Skin"`, `body.Tip = helper`. `_end_faces(f)`: spine sketch shape → `Part.Wire(sorted edges)` or `f.Spine[0].Shape.Wires[0]`; `v0, v1 = wire.OrderedVertexes[0].Point, [-1].Point`; among `f.Shape.Faces` with `Surface.TypeId == "Part::GeomPlane"` pick the face with the smallest `distToShape(Part.Vertex(v))[0]` for each end (must be < 1e-3 or raise "The sweep's end faces were not found"). `_sweep_read` adds the wall values from the helper. `SWEEP.claims = lambda f: True`; `SHELL.claims = lambda f: not getattr(f, "InCadHelperOf", None)`; `kind_for` must try SWEEP before SHELL for a helper: `kind_for` iterates kinds in registration order — add `claims` to SHELL only (a helper never matches SHELL, and nothing else claims Thickness, so `kind_for(helper)` is None: fine, the tree row of a helper is not editable, Thread's chamfer behaves the same).
- [ ] Run `tests/run_headless.sh test_shapes.py` → OK. Commit "Sweep: Wall option (thickness, side, open ends) as a helper Thickness under the Sweep".

### Task 2: Sweep wall — deletion, tree and dialog

**Files:** `InCad/incad/core/delete.py` (verify helpers removed: line 88 already collects `InCadHelperOf`), `InCad/incad/ui/feature_session.py` (nothing expected: `_finish` restores; `_pad_of` is the Sweep), Test `tests/headless/test_delete.py` (append: deleting the Sweep removes the wall), `tests/gui/test_features2.py` or new `tests/gui/test_sweep_wall.py`.

- [ ] Headless test: create a hollow sweep, `delete.delete_feature(doc, sweep)` (whatever `core.delete` exposes; grep `def `) → no Thickness left, tip = previous feature.
- [ ] GUI test `tests/gui/test_sweep_wall.py`: new part; Prof (circle r 5 on YZ) + Path (line 40 on XY); `feature.sweep`; set picks; `set_values({"hollow": True, "wall": "1 mm", "ends": "both_open"})`; OK → tip is Thickness with `InCadHelperOf == "Sweep"`; tree shows "SweepWall" under "Sweep" (`browser.tree_rows()` depth); double-click row "Sweep" (`browser.featureActivated.emit("Sweep")`) → dialog opens with hollow True and wall "1 mm"; set `ends` to `both_closed`, OK → volume grows by ≈ 2·π·16·1; Undo → back.
- [ ] Run both; commit "Sweep wall: deleted with its Sweep, edited from the Sweep's row".

### Task 3: Path chain, stations and placement (core, no constraints yet)

**Files:** `InCad/incad/core/sketch_patterns.py` (new section "along a path"), Test `tests/headless/test_sketch_patterns.py` (append `PathChainTest`).

**Interfaces produced:** `path_chain(sk, geos) -> [(geo, edge, reversed)]` ordered end to end, raises "The path's segments must join end to end"; `path_length(chain)`; `path_point(chain, s) -> (Vector, tangent Vector)` for 0 ≤ s ≤ L (edges in sketch coordinates: `sk.Geometry[g].toShape()`); `path_station(chain, point) -> s` (nearest point on the chain); `stations(rec, chain, s0) -> [s_k]` (`fit`: s0 + k·(L−s0)/(count−1); spacing: s0 + k·d, raising "No room: N copies at D mm need X mm, the path has Y mm after the original"); `flip` runs the chain backwards (reverse order and directions) before everything.

- [ ] Tests: chain of line (0,0)-(20,0), arc centre (20,10) r 10 from (20,0) to (30,10), line (30,10)-(30,40) picked in shuffled order → ordered, length 20 + 5π + 30; `path_point` at s = 20 + 5π/2 → (≈27.07, 2.93) tangent ≈ (0.707, 0.707); disconnected segments → ValueError; `stations` fit with count 3 from s0 = 0 → [0, L/2, L]; spacing 25 mm × 4 copies from s0 = 0 on L = 65.7 → [0, 25, 50] + error for count 4 ("No room"); flip reverses.
- [ ] Implement with `Part.__sortEdges__` / `Part.sortEdges` for ordering (keep a map edge → geo by matching vertex points, tolerance 1e-6), `edge.getParameterByLength(s - s_start)`, `edge.valueAt`, `edge.tangentAt`; reversed edges invert.
- [ ] Run, commit "Sketch patterns: path chain, stations, points and tangents along a path".

### Task 4: build_path — copies with rigid ties

**Files:** `InCad/incad/core/sketch_patterns.py` (`build_path`, `rebuild` dispatch, `SUPPORTED` unchanged), Test `tests/headless/test_sketch_patterns.py` (`PathBuildTest`).

**Record:** `{"name","kind":"path","values",...,"originals":[ids],"path":[ids],"count","spacing" (mm or None),"fit":bool,"orientation":"identical"|"follow","flip":bool,"copies":[[ids]],"constraints":[names],"centres":[ids]}`.

- [ ] Tests: originals = a circle r 2 at (0,−5); path = the chain of Task 3; identical, fit, count 3 → copies' centres at path_point(L/2) − (0,0)… precisely: original station s0 = nearest point of the circle's centre on the path = (0,0), offset_k = P(s_k) − P(s0); copy centres at (0,−5) + offset; moving the original (set the circle centre via `sk.movePoint`/`moveGeometry`) moves the copies the same way (DistanceX/Y ties); `follow` with a line original (0,−5)-(4,−5): the copy at s = 20 + 5π/2 is rotated by 45° (its direction ≈ (0.707,0.707)); DOF of the sketch unchanged by the pattern (copies fully tied); spline path: `Part.BSplineCurve` through 4 poles as a single-segment path, 3 copies, no error; delete via `remove` leaves originals and the path; `rebuild` with count 5 gives 4 copies.
- [ ] Implement: identical → for each copy, each ref point `DistanceX/DistanceY` constants (offset) like `build_rect` without expressions (`_add(... , None)`), circles Equal, arcs one centre equation; follow → rotation angle α_k = atan2(tangent_k) − atan2(tangent_0); rigid motion x' = R(α)(x − S0) + S_k; its centre C = solve (I−R)C = S_k − R·S0 (for |α| < 1e-9 fall back to identical ties); add a construction point at C (`Part.Point`), lock it with `DistanceX`/`DistanceY` to the origin point (-1,1) constants (hidden), then the circ scheme: for every ref point a construction spoke from C to the original point (shared per copy via `spoke0` cache keyed by (copy, src)) and to the copy point, `Equal` + `Angle(α)` constants; circles Equal; arcs: centre spoke Equal or Angle by `_bisector`. All copies' ids (points, spokes) go to `rec["copies"][k]` so `remove` deletes them.
- [ ] Run, commit "Sketch patterns: Along Path builds copies at stations, Identical or Follow path, rigidly tied to the original".

### Task 5: Kind `SKETCH_PATH`, pick kind, command, ribbon, icon

**Files:** `InCad/incad/features/sketch_patterns.py` (`PATH_FIELDS`, `_path_record/_create/_read/_update`, `KINDS`), `InCad/incad/features/common.py` (`sketch_path` in `_accepts_sketch`: `pos == 0 and geo >= 0 and t in ("Part::GeomLineSegment","Part::GeomArcOfCircle","Part::GeomBSplineCurve")`; `_EMPTY_HINT["sketch_path"] = "Click the path's lines, arcs or splines…"`; `_PLURAL`), `InCad/incad/actions.py` (command `sketch.path_pattern` "Along Path", icon `path_pattern`, contexts {"sketch"}; `SHORT`), `InCad/incad/ui/ribbon_layout.py` (`["sketch.rect_pattern","sketch.circ_pattern","sketch.path_pattern"]`), `tools/make_icons.py` (icon: a wavy path with three dots), `tests/widgets/test_actions.py` EXPECTED, `tests/headless/test_sketch_patterns.py` (`PathKindTest`: create via kind with values, read round-trips, update count).

PATH_FIELDS: geometry (picks sketch_geometry), path (picks sketch_path), count ("3"), fit (choice `spacing`/"By spacing", `fit`/"Fit to path", default spacing), spacing ("10 mm", show_if fit == spacing), orientation (choice identical/follow, default identical), flip (bool). `_path_record` refuses a path geometry that is also an original ("The path can't be part of the geometry to repeat").

- [ ] Tests RED → implement → `tests/run_headless.sh test_sketch_patterns.py`, `tests/run_widgets.sh test_actions.py test_icons.py test_ribbon.py` → commit "Sketch patterns: Along Path dialog, pick kind, ribbon button".

### Task 6: GUI + real part

**Files:** `tests/gui/test_sketch_patterns.py` (append tests 12–14): ribbon button opens "Along Path"; picks in the sketch (geometry = a circle, path = two lines + arc), count 4 fit → 3 copies in the sketch, preview updates on typing spacing; OK; Edit Pattern on a copy opens with the path text; delete pattern. Real part: open the frozen fixture, edit Sketch006, pattern a small circle (add one) along its first chain, 3 copies, OK, copies exist and the sketch solves.
- [ ] Run `tests/run_gui.sh tests/gui/test_sketch_patterns.py tests/gui/test_sketch_delete.py`; commit.

### Task 7: Finish

- [ ] Spec §7 status line → implemented with this plan's rulings; CLAUDE.md one line (path pattern ties are constants, re-placed on edit); `tests/run_fast.sh` once; merge/push on the user's word.
