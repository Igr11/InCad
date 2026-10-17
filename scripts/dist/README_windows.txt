InCad for FreeCAD - Windows test build (UNTESTED)
=================================================

Build: VERSION

InCad is developed and tested on macOS; on Windows it has been tried on one PC only.
Expect problems, work only on copies of files, and send the log (see "Reporting a problem").

New in this build (as on the Mac): Construction switches only the selected sketch lines;
Emboss and Engrave on a sphere (a Text or any closed
sketch), and Settings (the gear) > Display Quality - Normal is the default on Windows; Fine
draws round faces smoother but takes more drawing time on built-in graphics.
Earlier: big parts work much faster, and a slot can be dimensioned by its overall length
(Sketch > Dimension > Overall Dimension, or Centers / Overall / Gap in a dimension's value box).

What changed: CHANGES.txt. How to use every feature: InCad-manual.pdf (the user manual).
A short tour: InCad-presentation.pdf


Requirements
------------
- Windows 10 or Windows 11, 64-bit (x64).
- FreeCAD 1.1 for Windows (InCad is made for FreeCAD 1.1.3),
  from https://www.freecad.org/downloads.php


Install
-------
1. Quit FreeCAD.
2. Unzip the archive (right-click > Extract All...). Do not run anything from inside the zip.
3. In the unzipped folder double-click install.bat.
   It finds FreeCAD, asks it where its add-ons go, and copies the "InCad" folder there.
   A previous InCad in that place is moved to "InCad-backups" first, nothing is deleted.
   If Windows asks whether to run it ("Windows protected your PC"): More info > Run anyway.
4. Start FreeCAD and choose "InCad" in the workbench selector.
   The first time, InCad asks Part or Assembly and the units: choose and click Create.

FreeCAD installed somewhere unusual? In a Command Prompt in the unzipped folder:
    install.bat -FreeCAD "D:\Apps\FreeCAD 1.1"
Or give the add-on folder yourself:
    install.bat -ModDir "%APPDATA%\FreeCAD\v1-1\Mod"
In PowerShell the same is:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -FreeCAD "D:\Apps\FreeCAD 1.1"

Install by hand (if install.bat does not work): quit FreeCAD and copy the "InCad" folder
into %APPDATA%\FreeCAD\v1-1\Mod (create "Mod" if it is missing). The result must be
...\Mod\InCad\InitGui.py (not ...\Mod\InCad\InCad\InitGui.py).

To get FreeCAD's own interface back at any time, use "Return to FreeCAD"
(the FreeCAD button at the top right of the window).


What to try first
-----------------
Please note what works and what does not, step by step:
1. InCad appears in the workbench selector; choosing it shows the ribbon and the model browser.
2. New (Part) > Start 2D Sketch on a plane > rectangle > a dimension > Finish Sketch > Extrude.
   Do clicks land where the pointer is? (Windows display scale: Settings > System > Display > Scale.)
3. Right-click in the 3D view (marking menu); orbit, pan and zoom with the mouse.
4. Sketch > Text: does the font list show Windows fonts (Arial, Calibri ...)?
5. Save, close, open again. Make an assembly of two parts and add a constraint.
6. File > Export > STEP and STL.
7. The gear button at the top right > Theme > "Match Windows", with Windows in dark and in light mode.
8. Quit FreeCAD with an unsaved change: InCad must ask to save.


Uninstall
---------
Quit FreeCAD and double-click uninstall.bat. The InCad folder is moved to "InCad-backups"
next to the Mod folder (delete it yourself when you no longer need it).
InCad's log folder is %LOCALAPPDATA%\InCad (you may delete it too).


Reporting a problem
-------------------
Please send:
- what you did, step by step, and what you expected instead;
- the build name (the name of the zip file);
- the folder %LOCALAPPDATA%\InCad with InCad.log and install.log: in InCad, the gear at the
  top right > Show Log File opens it in the File Explorer with the log selected (Windows search
  does not look into this hidden folder);
  InCad.log starts every session with a "Started:" line describing your system;
- the text of FreeCAD's Report view if it shows errors (View > Panels > Report view,
  under "Return to FreeCAD");
- if you can, the .FCStd file you were working on and a screenshot.
