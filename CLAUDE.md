# InCad

Inventor/Alibre-style workbench for FreeCAD 1.1.3 (macOS). Spec: docs/superpowers/specs/, plans: docs/superpowers/plans/.

- Module: `InCad/` (package `incad`), installed by `scripts/install.sh` as a symlink in
  `~/Library/Application Support/FreeCAD/v1-1/Mod/InCad`. Restart FreeCAD to load code changes.
- Tests: `tests/run_widgets.sh` (offscreen PySide6), `tests/run_headless.sh` (freecadcmd),
  `tests/run_gui.sh` (real FreeCAD window — tell the user to keep hands off), `tests/run_all.sh`.
  Every FreeCAD run uses `-u <temp>/user.cfg`, so the user's settings are never touched.
- FreeCAD facts: bundled Python has no pytest (use unittest); `PySide` is FreeCAD's shim (PySide6 outside);
  new documents have `UndoMode == 0` — `incad.core.safe` turns it on; a failed feature has `'Invalid'` in
  `obj.State` and the reason in `obj.getStatusString()`; `Document.restore` pumps the Qt event loop (progress bar)
  on files that take long to load, so a deferred timer that recomputes runs mid-load and crashes the Sketcher —
  check `doc.Restoring` first (`tests/gui/test_open_during_restore.py`).
- UI text English. Chat with the user in any language.
- 1b facts: `view.getCameraNode()` needs `from pivy import coin` first; Coin pixel positions are device px with a
  bottom-left origin (`incad.ui.nav.to_coin`); FreeCAD opens its 3D context menu on the right-button release, so
  InCad's gesture rules never pass a lone right release.
- Sketcher facts: a constraint expression may use `InCadModel.dN` and driving constraints, never a reference
  constraint of the same sketch; FreeCAD gives every geometry a permanent id (`getGeometryId`) that survives
  deletions and reload and that the pad's element names derive from, so never `setGeometryId` on existing
  geometry; virtual space hides constraints, never geometry (sketch patterns: `incad.core.sketch_patterns`).
  A running Sketcher tool is visible to Python only as the bitmap cursor on the viewport; FreeCAD's spline
  and polyline tools finish on a right click (press+release), which `incad.ui.nav` replays while that cursor shows.
- Visibility: a new part's origin planes say Visible while their App::Origin group is hidden (`document.is_shown` is the
  effective state); unused sketches follow `InCadShown` (`document.sketch_shown`: open contours shown by default);
  view markers (`incad.ui.point_markers`) are SoAnnotation nodes, never document objects; a raw `Gui.setEdit` on a
  sketch switches workbenches and crashed in a test, open sketches through `shell.sketches.edit`.
- Sketch patterns Along Path (`core/sketch_patterns.build_path`) place copies exactly and tie them with constant
  constraints (re-placed on edit); a Sweep's Wall is an inner `PartDesign::SubtractivePipe` of the offset profile plus cap Pads (helpers with
  `InCadHelperOf`; `kind_for` claims none, their rows open the owner); a body-wide Thickness hollows the whole part.
