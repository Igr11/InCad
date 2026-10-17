# Run by install.ps1 inside FreeCADCmd (with throwaway settings): where FreeCAD keeps add-ons, and what of FreeCAD
# InCad needs is there. Writes "key=value" lines to the file named by INCAD_PROBE_OUT (FreeCADCmd does not show
# print()); changes nothing else.
import importlib.util
import os
import platform
import sys

import FreeCAD as App


lines = []


def say(key, value):
    lines.append("%s=%s" % (key, value))


say("freecad", ".".join(App.Version()[:3]))
say("python", platform.python_version())
say("system", "%s %s %s" % (platform.system(), platform.version(), platform.machine()))
say("home", App.getHomePath())
say("userdata", App.getUserAppDataDir())
mods = os.path.join(App.getUserAppDataDir(), "Mod")
say("mod", mods)
missing = []
for name in ("Part", "Sketcher", "PartDesign", "MeshPart", "JointObject", "UtilsAssembly", "BOPTools", "numpy"):
    try:
        found = importlib.util.find_spec(name) is not None
    except Exception:
        found = False
    if not found:
        missing.append(name)
say("missing", ", ".join(missing) or "none")
with open(os.environ["INCAD_PROBE_OUT"], "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
sys.exit(0)
