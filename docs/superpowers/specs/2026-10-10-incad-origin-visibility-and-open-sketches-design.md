# InCad — origin visibility, open sketches in the view, path points in Sweep/Loft

Status: implemented on 2026-10-10 (branch origin-visibility); plan `docs/superpowers/plans/2026-10-10-incad-origin-visibility-and-open-sketches.md`.

## 1. Intent

Three things the user asked for after trying the sketch tools on splines:

1. Hide and show **chosen** origin planes, axes and the centre point, and **unused sketches** (chosen in the model
   tree or in the 3D view), or all origin elements at once — from the context menu and from the ribbon's View group.
2. An **open-contour sketch** (lines, arcs, splines, no closed wire) stays visible in the part view until a feature
   consumes it, with its key points lit: a spline's control points, otherwise each segment's start and end.
3. In the **Sweep and Loft dialogs**, the picked path and sections show the same key points while the dialog is
   open (a closed section shows its vertices; a circle its centre).

## 2. Facts (probed on FreeCAD 1.1.3)

- Origin features (`App::Plane`, `App::Line`, `App::Point`) have their own `Visibility`, saved in the file. In the
  user's part they are all hidden; `incad.ui.sketch_session` shows them only while a sketch plane is picked and
  restores the saved state after.
- `incad.core.document.show_result` hides every sketch of the body after each refresh (profiles must not linger).
- Markers drawn on the view and never in the document already exist (`shell._PointPick`: an `SoAnnotation` with an
  `SoPointSet`), used by the section plane and the two-point revolve axis.
- A sketch's B-spline poles come from `geometry.getPoles()` (in sketch coordinates; the construction circles the
  tool adds at each pole are not part of the sketch shape).

## 3. Visibility (part 1)

- **Command `view.toggle_visibility`** "Hide / Show" (icon `visibility`), contexts `origin`, `browser` and `part`.
  Targets, in this order: the origin items and unused sketches selected in the model tree (the tree gets extended
  selection: Shift / Cmd-click); else the browser row the marking menu was opened on (`context.target()`); else the
  origin element or sketch selected in the 3D view. Hides when any target is visible, otherwise shows them all.
  Nothing to act on → "Select a plane, an axis, the centre point or an unused sketch first". A sketch a feature
  already consumes is refused: "Sketch3 belongs to Extrude2".
- **Unused sketches** (no feature consumes them, `features.common.consumers(sk)` empty) keep the user's choice in a
  sketch property `InCadShown` (bool, saved in the file; absent = default). `document.show_result` then shows an
  unused sketch when `InCadShown` is True, hides it when False, and without the property falls back to the default
  of §4: open contours shown, closed sketches hidden. Consumed sketches are hidden as today, whatever the property.
- **Commands `view.origin_show_all` / `view.origin_hide_all`** act on every origin feature of the primary body.
- **Where:** the origin marking menu (right-click on a plane/axis/point in the tree, and now also on a visible plane
  or axis in the 3D view: `_open_marking_menu` recognises `App::Plane`/`App::Line`/`App::Point` under the cursor
  as kind `origin`) gets Hide / Show in its ring; the part marking menu's list gets Show All / Hide All; the ribbon
  View group gets a split button Hide / Show with variants Show All Origin, Hide All Origin. No per-plane list on
  the ribbon (the user picks planes in the tree).
- **Tree:** hidden origin items and hidden unused sketches are drawn dimmed (`tree.Node.state == "hidden"`, colour
  `p["dim"]`), updated on refresh. Consumed sketches are not dimmed (they are hidden by design, not by choice).
- The sketch-plane pick keeps its temporary show-all-and-restore behaviour; a user's choice survives it.

## 4. Open sketches in the part view (part 2A)

- `incad.core.sketch.is_open_contour(sk)`: the sketch has edges, none of its wires is closed.
- `incad.core.sketch.key_points(sk)` → `[(kind, Vector)]` in global coordinates: for each non-construction
  geometry, a B-spline gives its poles (`"pole"`), a line or arc its start and end (`"end"`), a circle or ellipse its
  centre (`"centre"`), a point itself (`"end"`). Duplicates (shared vertices) are merged.
- `document.show_result` keeps an open-contour sketch visible when no feature consumes it
  (`features.common.consumers(sk)` is empty) and `InCadShown` is not False; consumed sketches, and closed unused
  sketches without `InCadShown` True, are hidden as today.
- `incad.ui.point_markers.PointMarkers(view)`: `set(points)` / `clear()`; one `SoAnnotation` per view, colours from
  the theme (poles and centres accent blue, ends orange), point size 9 (smaller than the clickable pick markers).
  The shell keeps one per document view and, on every `_refresh`, sets it to the key points of all shown unused
  sketches (open contours by default, closed ones the user showed; none → cleared). Markers are not clickable and do not affect selection.
- The sketch edit mode clears them (FreeCAD's own editing display takes over); leaving the sketch brings them back.

## 5. Sweep and Loft dialogs (part 2B)

- `FeatureSession` keeps a `PointMarkers` of its own: whenever a pick field of kind `sketch` changes (any field
  of the kind, so Sweep's profile and path, Loft's sections), the picked sketches are made visible for the dialog
  (the existing saved-visibility mechanism) and the markers show `key_points` of all of them. OK and Cancel clear
  the markers and restore visibility, as today.
- Open-contour markers of §4 stay off while a dialog shows its own (one set of points at a time).

## 6. Testing

- Headless (`tests/headless/test_sketch.py` or a new `test_key_points.py`): `is_open_contour` on closed, open and
  empty sketches; `key_points` on a line chain (shared vertex merged), an arc, a circle, a B-spline (poles in global
  coordinates after a placement); `show_result` keeps an unconsumed open sketch visible and hides it once a
  Sweep uses it; `InCadShown` False hides an unused open sketch and True shows an unused closed one, a consumed
  sketch stays hidden either way; visibility toggle helper (`core.document.set_visible(objects, flag)`).
- Widgets (`tests/widgets/test_actions.py`): the new command ids in the inventory; marking layouts resolve.
- GUI (`tests/gui/test_origin_visibility.py`): tree right-click on XY Plane → Hide / Show shows the plane in the
  view (`Visibility` True) and the row is undimmed; Shift-select two axes → one command toggles both; Show All /
  Hide All from the ribbon; the sketch-plane pick restores the user's choice; Hide / Show on an unused sketch row
  hides it and dims the row, a consumed sketch row is refused with the feature's name. `tests/gui/test_open_sketches.py`:
  a sketch with an open polyline + spline stays visible after refresh with markers at the poles and ends; after a
  Sweep on it the sketch and markers disappear; the Sweep dialog shows markers on the picked path. Real part:
  `Sketch7` (two open chains) of the frozen fixture is visible with its ends lit.

## 6a. Added after the user's first try (2026-10-10)

- **One selection for the tree and the view.** A click on a tree row (plane, axis, centre point, sketch, feature,
  part) selects the object in the model and the view highlights it; Shift/Cmd-clicks keep the others. A 3D pick
  highlights the row (opening Origin if needed). The tree keeps its selected rows and an Origin the user opened
  across refreshes. A hidden plane, axis, point or consumed sketch is **shown while its row is selected** (a
  peek: nothing saved; the next selection, Esc or a cleared selection puts it back). Hide / Show acts on the
  model's selection, ends a peek first, and names what was selected when nothing qualifies.
- The part's Combine button and dialog are named **Boolean** (the assembly's Combine keeps its name).
- **Hide / Show on any sketch**, a feature's too (asked after the first try): a consumed sketch is hidden by
  default and shown when the user chooses; the choice (`InCadShown`) outlives tip moves and undo/redo.
- **Work planes, axes and points** are planes and axes too: Hide / Show from the tree and from the RMB menu on
  them in the view; the view's part/face/edge/vertex menus list Hide / Show.
- **Undo is exact:** the targets get `InCadShown` with their current state before the step (outside it), the
  step changes the value, Undo/Redo restore it and re-apply the recorded choices; a document's saved choices
  are applied once when it is first shown.

## 7. Out of scope

Hiding bodies, features or consumed sketches by command (Inventor's Visibility on features), per-plane ribbon
list, markers inside the sketch editor, clickable markers.
