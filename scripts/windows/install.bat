@echo off
rem Runs install.ps1 next to this file. Arguments are passed on, e.g.  install.bat -ModDir "D:\FreeCAD\Mod"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
