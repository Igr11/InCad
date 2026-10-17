@echo off
rem Runs uninstall.ps1 next to this file. Arguments are passed on, e.g.  uninstall.bat -ModDir "D:\FreeCAD\Mod"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
echo.
pause
