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
