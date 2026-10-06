# InCad

An Inventor/Alibre-style workbench for FreeCAD 1.1.3 on macOS: ribbon, Model Browser with End of Part and
Parameters, light/dark in one click, ⇄ back to FreeCAD in one click. Files stay normal `.FCStd`.

## Install
    scripts/install.sh        # symlinks InCad/ into FreeCAD's Mod folder; restart FreeCAD
Then pick **InCad** in FreeCAD's workbench list.

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

## Features
- E Extrude, R Revolve (also on the ribbon and the right-click menu). The only finished sketch is picked
  automatically; otherwise select one. The preview updates as you type; OK, Apply + (one more), Cancel/Esc.
- Values accept units, names and formulas (Width/2, d3*2); click a dimension or a parameter to insert its name.
- Every value becomes a named parameter (d0, d1 …) in the Parameters panel. Double-click a feature to edit it.
- H Hole (from sketch points/circles or concentric to a round edge; counterbore, countersink, through all),
  F Fillet, Chamfer, Shell (inside/outside), Rectangular / Circular Pattern, Mirror, Work Plane / Axis / Point.
- Select edges or faces first, then the command, or pick them while the dialog is open (the highlighted
  field takes the picks; while picking, the shape before the feature is shown).
- Inspect: Measure (a face, an edge, or two items) and Mass Properties (PLA density).
- Unused values of deleted features can be removed with − in the Parameters panel.
- Thread: select the outside of a shaft or the inside of a hole, then Thread. Real helical geometry in ISO metric,
  ISO fine, UNC, UNF, G/BSP, NPT (tapered), Trapezoidal, ACME, Print-friendly (flat crests) or Custom; the size is
  suggested from the face; a print clearance (default 0.2 mm, 0.3 mm print-friendly) makes printed parts fit.
- Hole ▸ Threaded: modeled ISO / UNC / UNF / UNEF / NPT / G / BSW / BSF threads with the same print clearance.
  For Trapezoidal, ACME, print-friendly or custom threads in a hole, drill the hole, then use Thread on its face.
- Combine: select the base solid, then the tool solid(s), then Combine — Join, Cut or Intersect. Tools are always
  kept (hidden, editable; editing them updates the result). Cut has a print clearance (a parameter) on the Cavity
  (hole grown), on the Tool (a shrunk "<Tool> fit" copy to print) or Split (half each).
