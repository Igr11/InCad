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
