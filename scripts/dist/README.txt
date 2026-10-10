InCad for FreeCAD
=================

Build: VERSION

InCad is a workbench for FreeCAD that gives it an Autodesk Inventor / Alibre style
interface: a ribbon, a model browser with one history and End of Part, feature dialogs
with live preview, right-click marking menus and Inventor-like sketching.
Your files stay ordinary FreeCAD files (.FCStd).

This is an early test build. Please save your work often and report anything odd
(see "Reporting a problem" below).

Assemblies have not been tested yet in this build: please test parts (Part).
If you try an Assembly anyway, expect problems and work on copies of your files.


Requirements
------------
- A Mac with Apple Silicon (M1, M2, M3, M4 ...).
- FreeCAD 1.1 for macOS Apple Silicon (tested with FreeCAD 1.1.3),
  from https://www.freecad.org/downloads.php
Other systems (Intel Macs, Windows, Linux) are not supported in this build.


Install (with FreeCAD's Addon Manager)
--------------------------------------
1. Unzip the archive. You get a folder with this README and a folder named "InCad".
   Put it somewhere it can stay for now, e.g. in Downloads.
2. Copy the path of the "InCad" folder (the one INSIDE the unzipped folder):
   select it in Finder and press Option+Cmd+C ("Copy as Pathname").
   The path ends in .../InCad - not in .zip and not in ...-macOS-arm64.
3. Start FreeCAD and open FreeCAD > Settings... (Preferences...).
   Choose "Addon Manager" in the list on the left.
4. Under "Custom repositories" click "+". In "Repository URL" paste the path from
   step 2. Leave "Branch" as it is. Click OK, then OK again to close Settings.
5. Open Tools > Addon Manager. Find "InCad" in the list, select it and click Install.
6. Restart FreeCAD and choose "InCad" in the workbench selector.
   The first time, InCad asks Part or Assembly and the units: choose Part (Assembly
   is not tested yet) and click OK.

After the install the unzipped folder is no longer needed.

To get FreeCAD's own interface back at any time, use "Return to FreeCAD"
(the FreeCAD button at the top right of the window).


Install by hand (if the Addon Manager way does not work)
--------------------------------------------------------
1. Quit FreeCAD.
2. In Finder choose Go > Go to Folder... (Shift+Cmd+G) and paste:
       ~/Library/Application Support/FreeCAD/v1-1/Mod
   If the "Mod" folder does not exist, go to ".../FreeCAD/v1-1" and create a folder
   named "Mod" there.
3. Copy the "InCad" folder from the unzipped archive into that "Mod" folder.
   The result must be:  .../FreeCAD/v1-1/Mod/InCad/InitGui.py
   (not .../Mod/InCad/InCad/InitGui.py).
4. Start FreeCAD and choose "InCad" in the workbench selector.


Update to a new build
---------------------
1. Tools > Addon Manager > select "InCad" > Uninstall. Quit FreeCAD.
2. Unzip the new build and copy the path of its "InCad" folder (Option+Cmd+C).
3. FreeCAD > Settings... > Addon Manager > Custom repositories: select the old path,
   remove it with "-", and add the new path with "+".
4. Tools > Addon Manager > "InCad" > Install, then restart FreeCAD.
(Installed by hand: quit FreeCAD, replace the "Mod/InCad" folder, start FreeCAD.)


Uninstall
---------
Tools > Addon Manager > select "InCad" > Uninstall, then restart FreeCAD.
(Installed by hand: quit FreeCAD and delete the "Mod/InCad" folder.)
You may also delete the log file ~/Library/Logs/InCad.log.


Reporting a problem" below).


Requirements
------------
- A Mac with Apple Silicon (M1, M2, M3, M4 ...).
- FreeCAD 1.1 for macOS Apple Silicon (tested with FreeCAD 1.1.3),
  from https://www.freecad.org/downloads.php
Other systems (Intel Macs, Windows, Linux) are not supported in this build.


Install
-------
1. Quit FreeCAD.
2. Unzip the archive. You get a folder named "InCad" next to this README.
3. In Finder choose Go > Go to Folder... (Shift+Cmd+G) and paste:
       ~/Library/Application Support/FreeCAD/v1-1/Mod
   If the "Mod" folder does not exist, go to ".../FreeCAD/v1-1" and create a folder
   named "Mod" there.
4. Copy the "InCad" folder into that "Mod" folder.
   The result must be:  .../FreeCAD/v1-1/Mod/InCad/InitGui.py
   (not .../Mod/InCad/InCad/InitGui.py).
5. Start FreeCAD and choose "InCad" in the workbench selector.

To get FreeCAD's own interface back at any time, use "Return to FreeCAD"
(the FreeCAD button at the top right of the window).


Update
------
Quit FreeCAD, delete the old "Mod/InCad" folder, copy the new one in its place,
start FreeCAD.


Uninstall
---------
Quit FreeCAD and delete the "Mod/InCad" folder. Nothing else is left behind except
the log file ~/Library/Logs/InCad.log, which you may delete too.


Reporting a problem
-------------------
Please send:
- what you did, step by step, and what you expected instead;
- the build name (the name of the zip file, e.g. VERSION);
- your macOS version and FreeCAD version (FreeCAD > About FreeCAD);
- the log file: ~/Library/Logs/InCad.log
  (Finder > Go > Go to Folder... > ~/Library/Logs);
- if you can, the .FCStd file you were working on;
- a screenshot if something looks wrong.
If FreeCAD crashed, macOS shows a crash report: please copy its text as well.
