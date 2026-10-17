InCad for FreeCAD
=================

Build: VERSION
What changed in this build (improvements and bug fixes): CHANGES.txt
How to use every feature: InCad-manual.pdf (the user manual). A short tour: InCad-presentation.pdf

InCad is a workbench for FreeCAD that gives it an Autodesk Inventor / Alibre style
interface: a ribbon, a model browser with one history and End of Part, feature dialogs
with live preview, right-click marking menus and Inventor-like sketching.
Your files stay ordinary FreeCAD files (.FCStd).

This is an early test build. Please save your work often and report anything odd
(see "Reporting a problem" below).

New in 0.5.4: Emboss and Engrave on a sphere (a Text or any closed sketch, projected along the
sketch's normal), and Settings (the gear) > Display Quality - Fine draws round faces smoother.
New in 0.5.2 and 0.5.3: big parts work much faster, and a slot can be dimensioned by its overall
length - Sketch > Dimension > Overall Dimension, or the Centers / Overall / Gap buttons in a
dimension's value box.
Work on copies of files that matter to you.


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
   The first time, InCad asks Part or Assembly and the units: choose and click Create.
   To make InCad the workbench FreeCAD starts with: FreeCAD > Settings... > Workbenches >
   Available Workbenches > Startup > Default workbench: InCad.

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


Reporting a problem
-------------------
Please send:
- what you did, step by step, and what you expected instead;
- the build name (the name of the zip file, e.g. VERSION);
- your macOS version and FreeCAD version (FreeCAD > About FreeCAD);
- the log file: ~/Library/Logs/InCad.log
  (the gear at the top right > Show Log File shows it in the Finder);
- if you can, the .FCStd file you were working on;
- a screenshot if something looks wrong.
If FreeCAD crashed, macOS shows a crash report: please copy its text as well.
