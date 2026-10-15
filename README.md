# InCad

An Inventor/Alibre-style workbench for FreeCAD 1.1.3 on macOS: ribbon, Model Browser with End of Part and
Parameters, light/dark in one click, ⇄ back to FreeCAD in one click. Files stay normal `.FCStd`.

Current version: 0.4.0 (what changed: [scripts/dist/CHANGES.txt](scripts/dist/CHANGES.txt)).

## Install
    scripts/install.sh        # symlinks InCad/ into FreeCAD's Mod folder; restart FreeCAD
Then pick **InCad** in FreeCAD's workbench list. To start FreeCAD in InCad: Settings ▸ Workbenches ▸ Available
Workbenches ▸ Startup ▸ Default workbench: InCad.

## Test build
    scripts/make_dist.sh      # Distrib/InCad-<version>-<date>-<commit>-macOS-arm64.zip (module, README, CHANGES)
Bump `__version__` in `InCad/incad/__init__.py` and add its section to both CHANGES files first.

## Tests
    tests/run_all.sh          # widgets (offscreen) + headless (freecadcmd) + GUI (opens FreeCAD windows)

Your FreeCAD settings are never used by the tests (each run gets a throwaway user.cfg).
Logs: ~/Library/Logs/InCad.log

## Mouse
- Left click: select. Left + right button drag: orbit around the point under the cursor.
- Middle drag: pan. Wheel: zoom at the cursor.
- Right click: marking menu (also in the Model Browser). Right drag: flick a marking-menu command.
- ⚙ → Mouse Navigation switches InCad's mouse handling off (FreeCAD's own navigation then applies).

## Sketching
- S (or right-click → New Sketch) on a plane or a flat face; with nothing selected InCad shows the origin planes
  to pick from. Esc or ✓ Finish Sketch returns to the model.
- L line (M switches to arc while drawing), C circle, A arc, R rectangle, X trim, D dimension.
- While drawing, type lengths and angles directly (Tab moves between fields).
- Every dimension gets a name (d0, d1 …) shown under Parameters; rename it there. In a value box, click another
  dimension or a parameter to use its name in a formula (d0/2, Width - 2*d3).
- Projected edges are normal lines (as in Inventor), ready to be part of a profile; Construction switches them
  to construction and back. Construction geometry is drawn orange and dashed, thinner than the normal lines; in the
  dark theme the part is drawn darker while a sketch is open.
- Offset (InCad's own): a click on one line takes its whole shape (Cmd-click adds more), the copy follows the
  pointer, a click places it; sharp corners, a single line gives a parallel line, a circle or ellipse a ring; one
  dimension drives it. Mirror and the sketch patterns also take the whole shape from one side.
- Concentric (Constrain, after Coincident): two circles, arcs or ellipses get one centre.
- Constraint List (Sketch ▸ Constrain ▸ List, or right-click): every constraint of the sketch, filtered by the
  picked line or point; check rows and Delete selected. Right-click a line or point to delete one of its
  constraints, or all. Pattern ties and dimensions used in a formula are kept.

## Features
- E Extrude, R Revolve (also on the ribbon and the right-click menu). The only finished sketch is picked
  automatically; otherwise select one. The preview updates as you type; OK, Apply + (one more), Cancel/Esc.
- Revolve axis: the sketch's vertical or horizontal axis, a construction or projected line of the sketch (listed;
  the only one is the default — project an in-plane edge of the solid into the sketch to revolve around it; an edge
  perpendicular to the sketch projects to a point and isn't offered), a line / axis / edge picked in the view (a
  sketch line, an origin or work axis, a straight edge), or two points clicked on the part's corners, edge middles
  and circle centres (projected onto the profile's plane, so the axis is always in that plane). The projected-line
  and two-point axes are held by a hidden Revolve axis under the feature, deleted with it.
- Values accept units, names and formulas (Width/2, d3*2); click a dimension or a parameter to insert its name.
- Every value becomes a named parameter (d0, d1 …) in the Parameters panel. Double-click a feature to edit it.
- H Hole (from sketch points/circles or concentric to a round edge; counterbore, countersink, through all),
  F Fillet, Chamfer, Shell (inside/outside), Rectangular / Circular Pattern, Mirror, Work Plane / Axis / Point.
- Select edges or faces first, then the command, or pick them while the dialog is open (the highlighted
  field takes the picks; while picking, the shape before the feature is shown with the result drawn over it as
  orange outlines). Fillet / Chamfer: a click on an edge takes its smooth chain, a click on a face all its edges.
- Circular Pattern axis: any origin or work axis, a sketch line, a straight or circular edge, a round face, or two
  points clicked on the part (a hidden work axis, drawn dashed while the dialog is open).
- Inspect: Measure (a face, an edge, or two items) and Mass Properties (PLA density).
- Unused values of deleted features can be removed with − in the Parameters panel.
- Sweep (profile + path sketch), Loft (two or more sections in order), Coil (springs: profile + axis, pitch,
  height), Draft (tilt faces by an angle).
- Move Face (direct editing): push or pull flat faces (or offset a straight round wall) by a distance, or To a parallel face / plane, an edge running
  parallel to them or a point (also on another Solid); the neighbours follow as in Inventor, as a straight Step, or
  Together with their chamfers / fillets. A drag arrow on the face shows the distance live; Finish move is on top of
  the right-click menu.
- Tools ▸ Material sets the part material (PLA, PETG, ABS, ASA, TPU, Nylon, Resin, Aluminium, Steel): Mass
  Properties uses its density. View ▸ Section cuts the view open (toggle).
- Delete (right-click in the browser) removes a feature with everything InCad made for it (Combine helpers, thread
  profiles, assembly cuts); one undo step.
- Thread: select the outside of a shaft or the inside of a hole, then Thread. Real helical geometry in ISO metric,
  ISO fine, UNC, UNF, G/BSP, NPT (tapered), Trapezoidal, ACME, Print-friendly (flat crests) or Custom; the size is
  suggested from the face; a print clearance (default 0.2 mm, 0.3 mm print-friendly) makes printed parts fit.
- Hole ▸ Threaded: modeled ISO / UNC / UNF / UNEF / NPT / G / BSW / BSF threads with the same print clearance.
  For Trapezoidal, ACME, print-friendly or custom threads in a hole, drill the hole, then use Thread on its face.
- Combine: select the base solid, then the tool solid(s), then Combine — Join, Cut or Intersect. Tools are always
  kept (hidden, editable; editing them updates the result). Cut has a print clearance (a parameter) on the Cavity
  (hole grown), on the Tool (a shrunk "<Tool> fit" copy to print) or Split (half each). Keep tool leaves the tool
  as a visible solid of its own. Click anywhere on a solid to pick it.
- Hole ▸ Chamfer: None / Start / Both ends, a 45° lead-in (from the thread's diameter on a tapped hole).
- Split (3D Model ▸ Modify): a sketch's lines cut the part. Keep all (each other piece a Solid of its own,
  following the sketch) or Keep picked.
- Threads (3D Model ▸ Modify): all threads off for fast work, on again with a second click.
- Make Assembly (3D Model ▸ Assemble, or right-click): every separate piece becomes a part file with its history,
  and a new assembly links them where they were (the largest grounded). Running it again can replace the files
  it made before.
- A Solid sketched on another Solid's face holds only its own piece; it follows that face only when its sketch
  projects edges of the other Solid (otherwise the face was just a plane).

## Assemblies
- File ▸ New Assembly (or New, which remembers Part or Assembly; Tools ▸ Ask on New asks again). Place (P) links a
  saved part or assembly file (choose the part first); the first one is grounded, the next ones are put beside it.
  Create makes a new part file next to the assembly.
- Constrain (C = Mate; Flush, Angle, Tangent, Insert, Parallel, Perpendicular) and Joints (J = Rigid; Rotational,
  Slider, Cylindrical, Ball): pick faces or edges on the components in the 3D view; the preview moves the part.
  Flip turns it over (Mate / Flush facing, Tangent outside or inside, Insert and joint direction). Angle,
  Parallel and Perpendicular take faces or straight edges. Offsets and angles are parameters (Mate1, Angle1 …).
- Relationships rows: double-click to edit; right-click for Edit, Delete, Suppress / Unsuppress, Rename (a
  suppressed constraint is struck through, its parts stay put).
- Degrees of freedom: each component row shows Grounded / DOF n, counted against what holds it. View ▸ Degrees of
  Freedom draws Inventor's DOF symbols; otherwise the part under the pointer shows its symbol as a tip.
- Move: drag a free part with the mouse, or click it for its gizmo (an arrow per free slide, an arc per free turn;
  the first arrow is up and down) and drag a handle. A part moves only along its own DOF, the others stay put, a
  fully held part never moves; one drag is one undo step. A click on empty space hides the gizmo.
- Ground / unground, Hide / Show, Suppress, Remove from the ribbon or the right-click menu. The browser shows each
  component's part history.
- Edit (or double-click a component) opens the part in its tab with the other parts around it, grey and
  semi-transparent at their real places (view only; View ▸ Assembly Context turns them off). Back in the
  assembly tab InCad asks before updating it; declined, the tree says Needs update until Update.
- An assembly is saved before the first part is placed (FreeCAD links need a file). Save the part files with the
  assembly.
- Boolean (Assemble ▸ Component): cut a component by others with a print clearance. The pocket is written into
  the cut part's own file and follows the tools when they move or change. Threads Off / On acts on every part.
