# InCad — decisions taken autonomously and deferred minors (2026-10-05 … 06)

Collected from the per-plan ledgers (`.superpowers/sdd/*/progress.md`). Every **Ruling** is a decision taken
on the user's behalf with what it costs if wrong; every **minor** is a review finding deliberately not fixed.

## 2026-10-05-incad-1a-foundation-shell

**Rulings**

- Setup: branch `stage-1a` in place instead of a git worktree — scripts/install.sh symlinks /Volumes/Docs/InCad/InCad into FreeCAD's Mod folder, a worktree elsewhere would test the wrong copy — cost if wrong: none beyond less isolation (repo is new, user consented to building).
- Task 5: unitless App::PropertyQuantity refuses direct assignment of '80 mm' ("Not matching Unit") — every parameter value, plain or formula, is now set through setExpression; list_parameters reports formula '' when the expression parses as a plain quantity — cost if wrong: a literal shows as formula in plain FreeCAD's VarSet (harmless).
- Task 5: FreeCAD pads values to the decimals setting ('80.00 mm') — list_parameters strips trailing zeros ('80 mm') — cost if wrong: cosmetic.
- Task 5: FreeCAD normalizes formula text ('Width/8' -> 'Width / 8') — test expectation changed to the normalized form; the Parameters table will show FreeCAD's spacing — cost if wrong: cosmetic.
- Task 5: names that parse as units ('A', 'mm', 'deg', 'm', 'g') cannot hold expressions — rejected with "is a unit symbol" (new test test_unit_symbol_names_rejected_without_leftovers, RED->GREEN); a property created for a failed formula is removed; cycle test renamed A/B -> Len/Twice — cost if wrong: users cannot name a parameter 'A' (Inventor has the same restriction for unit names).
- Task 6: added tests/run_fast.sh (widgets + headless) as the per-task completion command — the safety check blocks 'zsh -c' compound commands — cost if wrong: one extra script.
- Task 7: plan said 'wrote 25 icons', generator writes 24 — the plan miscounted ('close' is included, ALL_NAMES has 24); tests check the real list — cost if wrong: none. Icons eyeballed in both themes (contact sheet): clear.
- Task 13: run_gui.sh now stops at once with SCRIPT ERROR when FreeCAD reports 'Exception while processing file' (a test script that fails to import used to hang until the 180 s timeout) — cost if wrong: none.
- Task 13: FreeCAD 1.1.3 has no Std_DrawStyleFlatLines/Wireframe; styles are items of the group command Std_DrawStyle (probed: 6 'Flat lines', 2 'Wireframe') — actions.STD_INDEX added, run_std(name, index) — cost if wrong: wrong style item on a future FreeCAD that reorders the group.
- Task 13: FreeCAD saves toolbar visibility to "BaseApp/MainWindow/Toolbars" BEFORE calling Deactivated and re-applies it after (probed) — the takeover snapshot now includes that group (params.snapshot_group, new headless test RED->GREEN) and restore writes it back — cost if wrong: a toolbar the user toggled while InCad was active is reset (cannot happen: InCad hides them all).
- Task 13: restore only re-shows what InCad hid and never hides — FreeCAD itself hides workbench-specific toolbars and the Tasks panel; setting saved False on recovery hid PartDesign's toolbars after a crash (test_7 rewritten to simulate a real crash: RED->GREEN) — cost if wrong: none found.
- Task 13: GUI tests 5 and 8 run with the InCad workbench still active, so they now check "everything visible before the takeover is visible again" (assert_reshown) instead of comparing with the PartDesign baseline; test 8 records that state by wrapping _hide_freecad instead of _build — cost if wrong: weaker check of docks hidden-by-FreeCAD in those two tests only.
- Task 13: FreeCAD's menu bar holds an untitled separator; test_1 ignores separators when listing visible menus — cost if wrong: none.
- Final: re-graded Minor 1 (Parameters +/- add an invisible VarSet to a plain FreeCAD file) to Important — it silently changes the user's non-InCad file — cost if wrong: one small fix.
- Final: first guard version refused whenever HasPendingTransaction; in the GUI scripted changes leave an implicit pending transaction, so it blocked Convert (2 GUI tests red) — now refuse only when an edit/task dialog is open, otherwise commit the stray change as its own undo step first — cost if wrong: a stray change becomes a separate undo step.

**Deferred minors**

- Convert to InCad Part leaves no undo step (Meta/UnitSystem outside the transaction) and picks units from prefs without telling the user
- if the primary body was deleted in native FreeCAD and another exists, the browser shows an empty part (no fallback/Convert)
- run_safely's recompute inside the except path is unguarded and could raise
- some errors are raw FreeCAD text (e.g. removing a parameter still used by a formula)
- unit-symbol rule also rejects W, N, V, e, pi, in, ft as parameter names
- FreeCAD's Report view (its own error popup) can never appear while InCad is active
- ⌘N restore falls back to Ctrl+N even if the user had removed Std_New's shortcut
- a failed new parameter row loses what was typed (table rebuilt on refresh)
- Review Focus GUI tests use stand-ins (new doc vs Std_Open; units-only check on tab switch; direct eventFilter call)

## 2026-10-06-incad-1b-navigation-marking-menu

**Rulings**

- Setup: branch stage-1b in place (same reason as 1a: FreeCAD loads InCad from this folder) — cost if wrong: none.
- Setup: pan and wheel zoom stay FreeCAD's own (CAD style + ZoomAtCursor forced while active, restored on exit) after probing that both exist; InCad only handles LMB+RMB orbit and the right button — cost if wrong: Inventor-exact pan/zoom feel may differ slightly.
- Task 1: suppressing the only feature makes FreeCAD mark the Body 'Tip shape is empty' (Invalid) and the guard rolled it back — an empty part is normal in Inventor, so safe._broken exempts exactly that Body status (test_an_empty_part_is_not_broken RED->GREEN) — cost if wrong: an empty body is never reported as an error.
- Task 8: nav-strip buttons showed macOS native dark backgrounds (Mac in dark appearance, InCad light) — explicit 'background: transparent' in the strip QSS; offscreen cannot reproduce macOS styling, so test_buttons_have_an_explicit_background pins the rule (RED->GREEN) and the real look was verified by screenshot in both themes — cost if wrong: none.
- Final: reviewer #6 (replay uses the release-time modifiers) — probed plain FreeCAD: it reads the modifier at the RELEASE (ctrl_press_only -> replaces selection even without InCad), so InCad already matches FreeCAD; kept storing press-time modifiers for the replayed press (more faithful), test_13 checks Cmd held through the click — cost if wrong: none (identical to FreeCAD).
- Final: no separate app-deactivate reset — a lost release now ends any gesture on the next buttonless move — cost if wrong: one stale event at most.

**Deferred minors**

- menu.destroyed may clear the reference to a newer marking menu (guard with identity)
- right-click on a face replaces a multi-selection (Inventor keeps it when the item is already selected)
- a pick without sub-element is treated as a face and selects the whole object
- split/quad views and views created between refreshes get no InCad navigation until the next refresh
- Orbit/Pan strip tools stay clickable while navigation is off
- left then middle press (FreeCAD-CAD rotate habit) is swallowed while the left press is held back
- marking menu is not clamped to the screen near edges
- shell eventFilter calls _mdi() (findChild) on every event — cache the viewport
- test_nav uses sendEvent (no real mouse grab / popup routing); a real-mouse flick needs the user's hands-on check

## 2026-10-06-incad-1c-sketch

**Rulings**

- Setup: spec 'line drag-back tangent arc' -> Sketcher polyline (M switches line/arc) — FreeCAD has no drag-back; cost if wrong: different gesture from Inventor.
- Setup: spec 'fx: prefix' on driven dimensions -> FreeCAD's expression-dimension color (ExprBasedConstrDimColor) + Dimension Display modes (Value/Name/Expression via DimensionalStringFormat) — Sketcher cannot prefix per constraint; cost if wrong: no literal 'fx:' text.
- Setup: 'Ctrl suppresses auto-constraints' and F8/F9 show/hide constraints deferred (no direct Sketcher hook found) — cost if wrong: two Inventor habits missing.
- Task 1: new sketch Point icon collided with the origin 'point' icon (dict key overwrite) — renamed to sk_point; plan said 64 icons, real count is 63 (32 new, plan miscounted) — cost if wrong: none.
- Task 7: the sketch-edit exemption in safe.edit_open also made the shell take over during a sketch edit in a PLAIN FreeCAD file (1a test_10 red) — shell._edit_open now exempts only sketches in InCad parts — cost if wrong: none.
- Task 7: 1b test_6 (flick N) now runs New Sketch, which correctly used a face still selected by an earlier test and stayed in sketch mode, breaking later tests — test clears the selection first and checks no sketch is left in edit — cost if wrong: none (behaviour is Inventor's: New Sketch uses the pre-selected face).
- Final: reviewer Important 6 (click-to-insert / double-click only with InCad navigation on) regraded Minor — navigation-off is an explicit fallback mode; FreeCAD's own behaviour applies there — cost if wrong: modal datum dialog on double-click in that mode.

**Deferred minors**

- to_display shows raw paths for formulas that reference a deleted dimension
- naming runs a full-document scan per constraint change (coalesce per sketch)
- a sketch deleted before the queued naming runs shows a warning
- pick mode not cancelled on document switch / other commands
- dimensions in older files are named only on the next sketch change (outside an undo step)
- crash snapshot written by 1b has no Sketcher settings to restore
- safe.edit_open exempts sketches in plain FreeCAD files too
- no GUI test sends a real key to prove shortcuts fire / are not ambiguous with Sketcher accelerators
- diameter/radius toggling in the Dimension tool burns d-numbers
- click-to-insert/double-click need InCad navigation on (regraded from Important)

## 2026-10-06-incad-1d1-feature-framework-extrude-revolve

**Rulings**

- Setup: plan 1d split into 1d-1 (framework, Extrude, Revolve) and 1d-2 (Hole, Fillet, Chamfer, Shell, patterns, Mirror, work features, Inspect) — each usable on its own — cost if wrong: none.
- Setup: drag handles (arrows/rings) in the 3D view deferred; dialog fields + live preview give the same control — cost if wrong: one Inventor convenience missing for now.
- Setup: Extrude 'Between' extent and changing Intersect/New Solid on an existing feature deferred (operation buttons for those are disabled when editing) — cost if wrong: re-create the feature instead.
- Task 1: FreeCAD formats angles as '30°' (no space) — test expectations use FreeCAD's form (also patched in the plan for Task 3 tests) — cost if wrong: cosmetic.
- Merge: stage-1c review fixes merged in; naming conflict resolved with model.claim_name (counter in doc.Meta) used by both sketch dimensions and feature parameters — cost if wrong: none.
- Task 3: plan's extrude.update read the replaced (deleted) Pad to choose its return value — decide 'is Boolean' before replacing (RED: ReferenceError → GREEN) — cost if wrong: none.
- Task 4: widget tests import incad.features.common without FreeCAD — common.py imports model/sketch lazily and features/__init__ loads kinds on first use (KINDS via module __getattr__) — cost if wrong: none.
- Task 6: FreeCAD quirk (probed): an object restored by undo/abort loses its formula dependency link (model.InList empty), so it stops following its parameters; clearing+setting the formula re-links and keeps redo intact — model.relink(doc) runs after run_safely rollback, dialog Cancel, InCad Undo/Redo and FreeCAD undo events (tests test_relink_restores_live_formulas, test_rollback_relinks_by_itself, GUI test_12 RED→GREEN) — cost if wrong: an extra recompute after undo.
- Task 6: while creating, switching Operation to/from New Solid or Intersect aborts and re-creates the feature (different structure); Join<->Cut still switches in place (GUI test_7 RED→GREEN) — cost if wrong: none.
- Task 6: InCad Undo/Redo act on the active document directly (Sketcher's command while a sketch is edited) — FreeCAD's Std_Undo talks to the active view and did nothing with the Start tab active — cost if wrong: none found.
- Task 6: Parameters-panel edits/renames of feature values were routed to user parameters (created a duplicate d0) — routed through model.set_model_parameter / rename_model_parameter; set_parameter refuses any model-parameter name (test_user_parameter_cannot_take_a_feature_parameter_name RED→GREEN).
- Final: GUI test_12 moved to a fresh Tip Extrude — the old Pad now carries test 6's sketch, so the switch is (correctly) refused — cost if wrong: none, the undo/relink path is still exercised
- Final: "To face" pick (Important 4) is wired in plan 1d-2 Task 6 (selection fields) with GUI test_6 there, not here — 1d-2 builds the general pick machinery; merging with "To" unusable for one plan — cost if wrong: one plan's window where "To" errors visibly (OK disabled)
- Final: orphaned parameters are removable by hand (− button), not auto-pruned — auto-prune after Delete would be a separate undo step and break undo of the delete — cost if wrong: users clean up rows manually

**Deferred minors**

- preview validity check runs on every PartDesign shape (pass only recomputed objects)
- Esc cancels the dialog only when the dialog has focus
- Join/Cut stay enabled on Intersect/New Solid edits
- relink regex misses <<Label>> targets, may over-repair Doc#Obj; runs twice per InCad Undo
- plain values displayed rounded via UserString (0.123 in → 3.12 mm)
- Revolve Full overwrites a user formula with 360°
- exceptions inside start() after set_busy skip cleanup; singleShot restarts unguarded
- shortcut takeover restores only the primary key
- non-VarSet object named InCadModel would be used; unit kinds in user-editable Label2
- dialog doesn't follow document switches
- profile from another body uses primary_body

## 2026-10-06-incad-1d2-more-features-inspect

**Rulings**

- Task 6: while a geometry pick is active the session shows the base feature instead of the preview (picks on the preview's own edges would name the wrong topology) — clicking the pick again or focusing a value ends picking — cost if wrong: user sees no preview while picking multiple edges
- Task 6: profile-less kinds try a first preview right at start (defaults/preselection); a missing pick shows its plain reason in the error line; selections on the feature being made map to its BaseFeature or are ignored — cost if wrong: an error line visible until the first pick
- Task 6: Extrude "To" accepts datum planes (whole object) too: to_face parsing uses partition, read() keeps "Obj" without sub — test_up_to_a_work_plane RED→GREEN
- Task 6: Hole concentric with empty picks raises a plain reason instead of IndexError
- Task 7: probed — body.newObject leaves the Tip on the previous feature for LinearPattern/PolarPattern/Mirrored in 1.1.3; pattern kinds set body.Tip explicitly — test_new_pattern_becomes_the_tip RED→GREEN
- Task 7: a create that fails half-way (e.g. Chamfer without edges) is rolled back at once by the session (_drop_partial) so no broken object becomes the Tip — GUI test_3 RED→GREEN
- Task 7: make_icons ALL_NAMES computed after the new ICONS.update block (stale-icon test)
- Task 7: edge marking menu gets its own dict (E Fillet, W Chamfer; shaded/wireframe in its list); vertex keeps the old one
- Task 8: Hole without a sketch shows its reason in red at start — the error line is the guidance; OK disabled until a sketch is picked — cost if wrong: looks alarming on first open
- Final: GUI test_9 was RED by cascade (test_8's open dialog), not on its own assertions — it now pins the visibility and selection behaviour — cost if wrong: the visibility bug's RED was not observed separately

**Deferred minors**

- active pick can stay on a field hidden by show_if
- "feature" pick accepts non-patternable features; features can't be picked by clicking a face in 3D
- pattern counts not validated (2.5, "3 mm", 0)
- Two directions off→on leaves an unused count parameter
- Hole has no PRESELECT (selected sketch ignored); 3-point plane ignores selected vertices; face marking menu Hole/Fillet ignore the face
- Work Plane Offset→3 points keeps the AttachmentOffset expression
- queued _selection_changed after a document close may log a traceback
- wording "Select at least one item" / "Select circular edge for Circular edge"
- Hole switched Sketch→Concentric in edit creates the helper sketch after the Hole in the body order

## 2026-10-06-incad-2-threads

**Rulings**

- spec and plan written autonomously (user asked for the full roadmap without check-ins); plan lists tests and interfaces per task, code is written test-first during execution — cost if wrong: less upfront review of code shape
- stage-2 branches from stage-1d2 (Hole, picks, dialog) before 1d-2's review fixes; those fixes are merged into stage-2 afterwards — cost if wrong: a merge
- Task 1: Tr16x4 depth is 2.25 (ISO 2904 ac = 0.25 for P 2..5), the plan's 2.5 was wrong; bore uses depth_int (ISO D1) — tests corrected
- Task 3: probed — Refine=True on a SubtractiveHelix silently corrupts the solid (1161 vs 1294 mm³, isValid True); threads always set Refine=False — cost if wrong: unrefined faces on threaded features (harmless)
- Task 3: only the Distance length is a model parameter; standard/size/clearance/offset/hand/flip are stored JSON on the helix and regenerate the profile — full-length threads don't follow a later change of the shaft length until edited — cost if wrong: user re-opens the thread after lengthening a shaft
- Task 3: start end = the face's end edge highest along the cylinder axis, "Start at other end" flips it; profile placed with the probed SectionOfRevolution attachment on that edge (associative)
- Task 3: internal NPT cuts a tapered groove into whatever bore exists (the bore itself is not tapered) — cost if wrong: NPT internal threads print with a straight minor diameter
- Task 4: probed — a bound Diameter overrides the thread size and unthreading resets Diameter; threaded mode releases the binding and remembers the parameter (InCadPlainDiameter), plain mode rebinds it
- Task 4: thread size names come from FreeCAD itself (hidden probe document, cached) so they always match its enumeration
- Task 4: thread_length uses a two-condition show_if (threaded AND depth) — the dialog gains AND conditions in Task 5
- Task 5: size combos start with an 'Auto' entry (value '') that suggests from the face / Diameter, so a new thread never defaults to the first size of the table
- Task 6: found in GUI — the hidden probe document (thread size names) left FreeCAD with no active document; it now restores the active one (headless assert RED→GREEN)
- Task 6: FreeCAD names coarse sizes like "M6x1.0" — GUI test uses its names; the Auto entry maps our "M6" to it by prefix
- Task 6: test_actions EXPECTED was extended together with the command (no separate RED run) — mechanical registry list
- Final: a size clearly smaller than the shaft (e.g. M6 on Ø10) is refused rather than cut with a long run-out (probed: the tall narrow helical slot gives an invalid solid) — cost if wrong: user must turn the shaft down first

**Deferred minors**

- ACME depth for <10 TPI (0.5P + 0.020")
- Tr/ACME internal depth (ISO 2904 D1 = d − P, root at d + 2ac)
- Hole Auto size mapping for fractional UN sizes and UNEF/BSW/BSF
- Auto size frozen after create (stored resolved size)
- unparseable clearance/offset text silently replaced by defaults in Thread

## 2026-10-06-incad-3-combine

**Rulings**

- spec/plan written autonomously; 'clearance on the target' interpreted as on the cavity (the target's hole), 'on the tool' as a shrunk fit copy (the original tool is kept untouched), 'both' as split — cost if wrong: option labels/semantics change
- stage-3 branches from stage-2 before its review fixes; those merge in afterwards
- Task 1: no tree change needed — the browser lists every Body (fit copies included) and never root Part::Offset helpers
- Task 2: GUI tests were written with the command and passed on the first run (no RED observed for the GUI path; headless kind tests had RED)
- Final: deleting a Combine with FreeCAD's own Delete leaves its hidden helpers (no InCad delete hook yet) — deferred to stage 6 (delete command + unused-parameter cleanup) — cost if wrong: invisible offsets keep a parameter "in use"

**Deferred minors**

- a tool removed from the list on edit stays hidden
- negative clearance silently treated as none; parameter names not accepted in Clearance
- helpers tracked by object name only (name reuse could confuse an edit)
- empty base silently falls back to the active solid; duplicate validation in create/_build

## 2026-10-06-incad-4-assemblies

**Rulings**

- spec/plan written autonomously; Create opens the new part in its own tab (no in-place editing context) — cost if wrong: user switches tabs to model the new part
- component dragging deferred (FreeCAD drag needs its own edit mode, which conflicts with InCad's navigation) — cost if wrong: components move only through constraints/placement
- stage-4 branches from stage-3 (unmerged, review pending)
- Task 1: RED for Task 1 was the missing module (import error), not observed per test
- Task 2: Mate/Flush direction enforced after solving by checking the face normals and flipping (FreeCAD's pre-solve picks the nearest orientation)
- Task 2: with nothing grounded the first picked component is held still for the solve (FreeCAD needs a fixed part); Inventor-like
- Task 2: a constraint is 'met' only when the solve succeeds and (Mate/Flush) the faces end parallel at the offset; otherwise the joint is removed and placements restored
- Task 3: part files are opened hidden when placed; double-click on a component re-opens its file in its own tab (open_component)
- Task 3: Mate = C, Rigid joint = J, Place = P (assembly context only)
- Task 4: GUI tests passed first run apart from those two findings

## 2026-10-06-incad-5-assembly-combine

**Rulings**

- Cut only across files; fit copies live in the base part file; positions re-synced by InCad (cross-document expressions make a cycle, probed)
- Task 3: the feature session opens the dialog's undo step in every document the kind names (documents hook); FreeCAD links them ('-> Combine')
- Task 3: the recreate path in the session now always clears the feature first (it could update a removed object)
- Task 3: cuts re-sync on every assembly refresh outside dialogs; deleting a cut record from the browser is not offered yet (asm_cut.remove exists) — deferred
- Final: opening a component saves its file's pending changes (assembly cuts) — cost if wrong: a part file saved without the user pressing Save

**Deferred minors**

- ungrounded assembly ignores offset changes silently (suggest "Ground a component")
- Insert has no explicit direction rule
- hidden modified part files and quit prompts not verified in the GUI
- "already depends on" wording in assemblies; open_component on a broken link raises a raw error
- Create (new part file) is not undone on failure (file stays on disk)
- sketch Tangent shares the redrawn tangent icon
- seeding the Combine "With" field selection on nested links may not highlight
- test gaps — Tangent/Insert/Slider/Cylindrical/Ball, save-close-reopen lifecycle (probed OK by the reviewer)

## 2026-10-06-incad-6-polish

**Rulings**

- Rib and Split deferred (no native PartDesign feature in 1.1.3)
- Join/Cut of Sweep/Loft/Coil fixed after creation
- stage-6 branches from stage-5 (stages 4-5 review pending)
- Task 4: Delete is on the browser marking menu (no Delete-key shortcut: it would fire while a parameter cell is edited) — cost if wrong: one more click
- Final: linked undo matches steps by name across open files ("-> name" marker) — cost if wrong: an unrelated same-named step in another open file could be undone too (only when one of the two carries FreeCAD's linked marker)

**Deferred minors**

- Delete refusals show raw FreeCAD text (sketch used by a pad, body used as a Combine tool, Draft neutral plane on its own face)
- Delete allowed while a sketch is being edited
- deleting a body holding a Combine leaves the tool hidden; deleting a fit copy leaves its hidden offset
- deleting the tool component of an assembly cut keeps the cut (by design, for a decision)
- material colour only on bodies existing at the time; repeated/open loft section picks give raw messages
- test_delete imports CombineTest (Combine tests run twice); Mass test doesn't check the density


## Hands-on session 2026-10-06 (user testing, fixes on main)

**Rulings**

- New parts / sketch picks frame the origin at ~40 mm (FreeCAD's fit on an empty scene left the view a few mm across).
- Sketch tool variants are Inventor split buttons; rectangle 3-point/center modes are set in FreeCAD's hidden tool widget after starting the tool (FreeCAD remembers the last method, so every variant sets its own).
- Overall and Center Point slots are InCad's own 3-click tool (FreeCAD's slot is center-to-center only); built from two arcs + two lines with tangent/equal constraints.
- Construction is an InCad-tracked drawing mode (FreeCAD's own construction mode can't be read back); new geometry is converted while it is on.
- Hide constraints = move constraint symbols to FreeCAD's virtual space; dimensions always stay (Inventor F8/F9).
- Threads run out one pitch past free ends; a picked Start face names the start end; shoulders/floors still stop the groove short.
- Work features: midplane, angle-around-edge, parallel-through-point on a face, and axis parallel-through-point are computed when created/edited (no FreeCAD attachment mode follows them).
- Section view cuts at the selection (3 points / flat face / plane), XZ otherwise; unusable picks are ignored.
- Quitting: InCad asks its own Save dialog (Inventor style), cancels open tools, tears down and deletes its Qt objects inside the main window's close, and releases PySide's markers on all Qt objects (probed: macOS ends the process from inside the close; destroying marked objects after Python is gone crashed). If FreeCAD ever cancelled a quit after that, Python references taken earlier would be stale — cost if wrong: an add-on keeping a widget reference could misbehave after a cancelled quit.
- ⌘Q is InCad's own File ▸ Quit (no QuitRole: macOS keeps FreeCAD's Quit in the app menu); Quit and ⌘W cancel an open feature dialog instead of refusing.
- Hole: Simple / Clearance (FreeCAD's ThreadFit sizes the clearance) / Tapped; spotface = shallow counterbore; "To" face depth is computed when created/edited (FreeCAD's Hole has no up-to-face).
- FreeCAD's overlay containers (OverlayLeft/Right/Top/Bottom) are hidden with the docks while InCad is active.

**Known test limitation**

- GUI tests that send real key events or need keyboard focus (parameter click into a focused field, real ⌘Z, real ⌘Q quit) fail while the screen is locked or another app holds focus; they pass with an unlocked screen.
- Ruling (2026-10-06): switching to InCad while a FreeCAD sketch (not an InCad part's) is in edit closes that edit and takes over at once (sketch changes are already in the model); other FreeCAD tasks keep their OK/Cancel and a visible notice says InCad opens when they close; when the closing task switches back to its own workbench, InCad is activated again. Replaces the earlier "wait for any edit" rule (status-bar notice was easy to miss: user saw "the FreeCAD interface" in InCad).
- Ruling (2026-10-06): FreeCAD's Start page is never closed or hidden by InCad — closing it crashes FreeCAD while its own setup timer is pending (seen >2 s after opening), hiding it breaks the MDI tabbed layout (new documents open as small floating windows). Instead, while InCad is active, whenever the Start tab becomes active InCad re-activates the previous view (activation history). The Start page is recognised by its tab title and no Python handle on FreeCAD's subwindows is kept (kept handles made the app-quit path crash intermittently at exit).
- Ruling (2026-10-06): in dimension and feature-value formulas a plain number added or subtracted takes the part's unit (deg for angles) — 'd16+2' = d16 + 2 mm; next to * / ^ it stays unitless ('d3*2'). Formulas are then shown with the units ('d0 + 2 mm'), as Inventor does. User parameters (Parameters table) are unchanged.
- Ruling (2026-10-06, after two code audits of the dimension flow): FreeCAD's on-view value field is off under InCad (OnViewParameterVisibility 0) — InCad's box is the one place to type; LeaveSketchWithEscape off — Esc cancels the box, then picks/tools, then a feature dialog, then the running Sketcher tool, never the sketch (Finish Sketch leaves). The Dimension tool's replacement of a dimension at the placing click is tracked by a per-sketch snapshot (core/sketch.reconcile_replaced): name and typed value/formula survive, no dN burned, inside an undo step; a box whose dimension vanished closes. A box closed by moving on (next dimension, Finish Sketch, tab switch) applies what was typed. A click in the model tree only selects when a pick is waiting. Origin rows get a reduced RMB menu (New Sketch).
- Ruling (2026-10-06): Thread gets a Chamfer option (None / Start / Both ends, size default 1 mm): a 45° revolve cut (PartDesign::Groove) of a triangle on the thread's own section plane at the free end(s) — no face names involved, so it survives edits; it is a helper object (InCadHelperOf = the thread) shown under the thread in the model tree and removed with it; no chamfer on a shoulder (not a free end).
- Ruling (2026-10-06): Inventor profiles — sketch lines may cross or dangle. A sketch FreeCAD can't pad as it is uses its areas (core/regions: the sketch plane split by its edges, bounded pieces): one area is used at once; several are shown as translucent "Area N" objects inside a transaction that is aborted on the pick (no undo step) and the user clicks one. The chosen area becomes a hidden profile sketch (InCadRegion: source + a point inside) rebuilt whenever the source sketch changes; the model tree shows the user's sketch under the feature; Delete of the feature removes the area copy, the sketch stays and can't be deleted while in use.
- Ruling (2026-10-07): Section view has no drag handle (FreeCAD crashes destroying it); instead a Section panel (Offset slider/field, Flip, Done keeps the cut, Off removes it; Esc = Done; Section again = off). The plane comes from the pick (plane, flat face, three points, XZ by default).
- Ruling (2026-10-07, night): the section's cut face is computed from a triangle mesh of the solid (MeshPart, meshed once per sectioning session): the plane is intersected with the mesh's own triangles (Mesh.crossSections glues separate loops into one polyline and must not be used), the segments are chained into loops (both directions, seams joined within a wider reach), projected onto the plane and made into faces (Bullseye; per-loop faces; raw polygons as the last resort). Verified headless: 117 positions through a threaded, chamfered shaft, 0 empty, ~25 ms each; the solid slice remains the fallback. The on-screen render and the GUI suite for this change still have to be run (screen was locked).
- Status (2026-10-07 02:10): the real-input robot (tests/real) runs the user's workflow with real mouse/keyboard — 12 scenarios, all passing (dimension place/type/Enter, click another dimension into a formula, own label ignored, Enter before placing, Esc in box then view, RMB Edit from the tree, Hole picks its sketch in the tree, Extrude Cut from a tree selection, Delete from RMB, Move End of Part via the radial menu, Finish Sketch keeps the part view, real ⌘Q quits clean). Lessons: park the real pointer after a run; keyboard-focus tests need an unlocked screen.
- Status (2026-10-07 02:40): tests/run_robot.sh runs the 16 real-input scenarios (all passing); tests/run_all.sh (widgets, headless, 19 GUI files, 6 quit modes) all green. Robot lessons folded in: atomic command handoff (the driver polls a file), roomier view after the sketch setup, pointer parked after each run. Extrude takes the sketch clicked in the model tree even without a 3D selection (crossed sketches included).
- Ruling (2026-10-07, night): a click on OK / Apply / Cancel while a feature preview computes (seconds for a thread with a chamfer) is dropped by FreeCAD itself — its recompute progress bar filters mouse and key events — not by InCad; this matches Inventor (busy cursor, click ignored). Verified with the robot by counting the button's clicked signals: 0 during the compute, 1 after it. The feature session keeps a re-entrancy guard anyway (a press that FreeCAD does deliver while the preview runs is taken when the preview ends). The robot waits for an idle dialog before clicking (state 'dialog.preview' + a fresh state file: a stale one points at where a widget was before the dialog grew, e.g. the Chamfer size row).
- Ruling (2026-10-07, night, found by the robot): Start 2D Sketch shows the big origin planes (and frames the origin) only while the part has no solid — Inventor's empty-part pick. With a solid, the faces are what gets picked: the planes drawn in front took a real click meant for the top face (the sketch landed on XZ), and reframing threw the user's view away. Origin planes stay one click away in the plane panel and the browser. New real-input scenarios: sketch on a face by a 3D click, fillet by an edge click + ⌘Z, rectangle drawn with real clicks.
- Ruling (2026-10-07, night, after a fresh code review of the night's diff): feature previews never let an exception out of the timer slot (the dialog shows it), a deferred OK/Apply/Cancel is dropped when its preview fails instead of firing on the next value change, a value changed while a preview runs is previewed right after it, Apply pressed twice during a preview starts the next feature once, and Esc/OK during the first preview of a Fillet/Thread (preview straight from a preselection) closes the session without touching the closed dialog or leaving a selection observer. Section hatch is vectorised (numpy, 20 000-point loop well under 0.4 s) and reuses the loops the cut face was just built from (one slice per slider move); a failed hatch clears the previous one.
- Ruling (2026-10-07, night, second review): Apply chains the next dialog of the same kind only after a real commit — an Esc that lands during Apply's preview means stop (Inventor). The feature session stops its preview timer on every close, marks the selection observer only when it was really added, and forgets the feature right after an aborted re-create.
- Ruling (2026-10-07, morning, user: "I do not see sketch drawing" after a night of changes — not reproduced by the scripted, the user-settings, or the real-input robot runs, all drawing the slot on a face): Start 2D Sketch offers the origin planes with a solid in the part too (the 03:42 rule hid them, which read as "nothing to click"); the view stays where it is, and a face under the cursor wins over a plane drawn in front of it (sketch_session._face_under: the pick point projected back to the screen, FreeCAD's hit list, nearest valid face) — a pick made from code (no point) is taken as it is. Cost if wrong: a plane under a face can only be clicked beside the model or from the plane panel / browser.
- Ruling (2026-10-07, morning): Update button (Inventor's) right after Redo in the title row — recompute, InCad refresh, view redraw. Asked for after "move End of Part: nothing happens"; the drag itself passes a synthetic-mouse GUI test, and the user's FreeCAD had been started 3 minutes before the repo moved to /Volumes/Docs/Claude projects/InCad (lazy imports from the old path fail silently until a restart).
- Ruling (2026-10-07, afternoon, user: "moving up End of Part still does nothing" in a fresh FreeCAD; the drag passed a synthetic-mouse GUI test and a real-mouse robot drag onto a feature two rows up): a drop onto a row used to mean "after that feature" — dragged up one row onto the last feature (or its sketch) it landed where it already was. Now the drop position decides, Inventor's between-rows way: upper half of a feature's own row = before it (the feature above, or the start), lower half or one of its child rows = after it; a drop line is drawn while dragging. Status line says where End of Part went; Update says what it recomputed (and names failed features). Robot gets `drag:<from>,<to>` (real button-held drag) and `tree.<name>.top` spots.
- Ruling (2026-10-07, 15:00, root cause of "moving End of Part does nothing", from the user's log and p2_test.FCStd: Tip = Extrude while ThreadChamfer was the shown feature): set_end_of_part only set body.Tip — FreeCAD's Move Tip also switches which feature is displayed, so the 3D view kept showing the last feature it showed whatever End of Part did. Now only the tip feature is visible (sketches untouched), "after Thread" means after its helpers too (the chamfer InCad made, shown under it; Tip = last helper, End of Part drawn after the owner as before), and a drop onto the feature right above the marker (any half, or its sketch) means before it, since "after" is where it already is — except the first feature of a secondary solid (no "before" there, "" would move the main solid's marker). Headless, widget, GUI (mouse events, visibility asserted) and real-mouse robot tests.
- Ruling (2026-10-07, 15:40, user: Revolve Cut "not cut" + "revolve around line, axis, construction line, two points"): the axis was always the sketch's own V/H axis — for a sketch on a face that axis runs through the projection of the global origin, so a full-turn cut either removed nothing useful or the whole part (FreeCAD calls an empty result valid; the user saw "produced invalid geometry" and the uncut part). Revolve now has an Axis method: Sketch vertical / horizontal, Construction line (drop-down — user's choice over auto-pick; the only construction line is the default, Inventor's centerline), Line/axis/edge (pick: a sketch line 'EdgeN', an origin/work axis, a straight solid edge), Two points (the section view's markers, 2 clicks → a hidden PartDesign::Line 'Revolve axis' placed through them, InCadHelperOf = the revolve, inserted before it, shown under it, re-placed on edit, removed when the axis changes or the revolve is deleted). FreeCAD stores the first construction line as 'Axis' (index 0 dropped) — read back as 'Axis0'. Plain messages: "The axis crosses the profile…", "<feature> cuts away the whole part…". The shell's 3-point section pick is now an n-point pick with callbacks (start_point_pick).
- Ruling (2026-10-07, 16:10, user: Revolve "Cannot access attribute 'TypeId' of deleted object"): toggling Join<->Cut while the axis was not yet valid (Two points chosen, none picked) crashed. The Join<->Cut type swap (extrude._replace) deletes the old feature and builds a new one; revolve.update then called _apply, whose axis resolution raised on the unset axis BEFORE update returned the new feature, so the feature session kept a deleted-object wrapper and every later preview hit .TypeId on it. Fix: revolve.validate_axis() checks the axis choice (construction line present, a pick made, two distinct points) BEFORE the swap, so a bad axis stays a plain non-fatal message and the feature is never deleted. Defense-in-depth: FeatureSession._recover_deleted_feature() — if any update() leaves self.feature deleted, it resets to None while creating (next preview recreates) or aborts and re-fetches the original by name while editing. Also: "perpendicular to the sketch" axis message made plain. GUI regression test (toggle Cut/Join with an invalid two-point axis, then a valid axis, OK commits clean).
- Ruling (2026-10-07, 16:30, user: Construction turns a normal line into construction but not back): toggle_construction read the direction from the whole chain (the picked edge expanded along coincidence joins), so a construction line joined to normal profile geometry gave a mixed chain that always read as "make construction" and never flipped to normal. The direction now comes from the edges the user actually picked (all picked are construction -> make them normal, else construction); the change still applies to the whole chain. Standalone and uniform-profile toggles are unchanged; a construction line joined to normal geometry now toggles back without disturbing the normal lines. Headless regression tests added.
- Ruling (2026-10-07, 17:00, user: "use a projected construction line as the revolve axis"; projected/external geometry can't be toggled to normal — FreeCAD keeps external geometry construction, setConstruction on a negative GeoId is ignored, and this build exposes no "defining" setter): the Revolve "Construction line" axis is now "Construction / projected line" and lists the sketch's projected (external) straight edges alongside its own construction lines (revolve.projected_lines from sk.ExternalGeometry). A projected line can't be referenced as 'ExternalEdgeN' (FreeCAD: "Invalid shape name"), so it resolves to its SOURCE edge (obj, "EdgeN"), which revolves correctly; read() maps that reference back to the projected choice. A single construction-or-projected line is the default axis. Headless + GUI tests (project an edge, revolve around it, round-trip).
- Ruling (2026-10-07, evening, user: "End of Part doesn't work for the last revolve", with a screenshot showing End of Part ABOVE a Revolve that was never applied): the revolve was rolled back (below the marker); dragging End of Part back down onto it landed on the upper half, which the "upper half = before it" rule read as "before the revolve" — where the marker already was, so nothing happened. Now a drop on any feature BELOW the marker (browser._rolled_back, by position relative to the End of Part node) applies it, whichever half; the before/after-by-half rule only governs an already-applied feature. Also: "sketch after moving End of Part is visible" — set_end_of_part now calls document.show_result, which shows only the tip feature (falling back to the nearest earlier feature with a shape when the tip is invalid, so the view never goes blank) and hides the body's sketches; the Update button runs show_result for every body too, so it reliably re-syncs a drifted display. The End of Part GUI tests drive drop_end_of_part_on directly with a per-test fresh part — a synthetic QTest marker drag is timing-flaky in the offscreen harness and the real drag path is covered by tests/real.
- Ruling (2026-10-07, night, user: "can't choose 2 points — points don't appear every time"): the two-point axis markers sit on the solid's corners/edges/centres, which fall off screen when the user is zoomed into the sketch, so they seemed to not appear. Starting a point pick now fits the view (shell._fit_points_in_view: fitAll + a 15% zoom-out) so every marker is on screen; it only zooms out when a marker is outside the viewport. Point pick hardened too: start_point_pick clears a replaced pick's on_cancel before cancelling (no spurious deactivation), and the feature session re-shows the markers if the pick should be active but they were lost (sh._point_pick is None). GUI test zooms hard into the sketch and asserts all markers on screen. The separate "cut revolve doesn't work" report is NOT reproduced (cut works on a face with V/H/two-point axes in every scripted run) — pending the user's exact steps or file.
- Ruling (2026-10-07, night, user: a projected line/edge used as a revolve axis gives "axis must not be perpendicular to the sketch plane" — "it's a logical mistake, a projection lies in the sketch plane"): correct. The bug was that a projected choice resolved to the 3D SOURCE edge (which can be perpendicular), not the in-plane projection. projected_lines now reads the PROJECTED geometry (sk.ExternalGeo, in the sketch's local frame, skipping the two sketch axes), lists only non-degenerate line segments (a perpendicular edge projects to a point and is dropped), and resolves each to a helper PartDesign::Line through the projection's global endpoints — the same helper mechanism as the two-point axis, so it is guaranteed in-plane and revolves. read() maps such a helper back to the two-point axis (same line). Headless tests: in-plane projection revolves (XZ sketch), a perpendicular source edge on a top-face sketch is not offered and the in-plane edge cuts cleanly.
