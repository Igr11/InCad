"""What differs between the systems InCad runs on (macOS, Windows): where the log goes, where fonts are, the
freecadcmd executable, the name of the add-to-selection key. No FreeCAD import: usable from widget tests."""
import os
import subprocess
import sys

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
OS_NAME = "Windows" if WINDOWS else "macOS" if MAC else "system"
ADD_KEY = "Cmd" if MAC else "Ctrl"   # the key that adds to a selection (Qt's ControlModifier on every system)


def log_path():
    if WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "InCad", "InCad.log")
    if MAC:
        return os.path.expanduser("~/Library/Logs/InCad.log")
    return os.path.expanduser("~/.local/state/InCad/InCad.log")


def font_dirs():
    if WINDOWS:
        dirs = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
        local = os.environ.get("LOCALAPPDATA")
        if local:  # fonts installed "for me only"
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        return tuple(dirs)
    if MAC:
        return ("/System/Library/Fonts/Supplemental", "/System/Library/Fonts", "/Library/Fonts",
                os.path.expanduser("~/Library/Fonts"))
    return ("/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.local/share/fonts"),
            os.path.expanduser("~/.fonts"))


def freecadcmd(home):
    """The console FreeCAD next to this one (home: App.getHomePath()), or None."""
    names = ("FreeCADCmd.exe", "freecadcmd.exe") if WINDOWS else ("freecadcmd", "FreeCADCmd")
    for n in names:
        path = os.path.join(home, "bin", n)
        if os.path.exists(path):
            return path
    return None


def reveal(path):
    """Show the file in Explorer / Finder, selected."""
    if WINDOWS:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)], creationflags=quiet_process_flags())
    elif MAC:
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def quiet_process_flags():
    """Popen creationflags: on Windows a console program started from FreeCAD would flash a console window."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if WINDOWS else 0


def system_name():
    import platform
    if WINDOWS:
        build = platform.version().split(".")[-1]
        name = "11" if build.isdigit() and int(build) >= 22000 else platform.release()  # Python says 10 on 11
        return "Windows %s (build %s) %s" % (name, build, platform.machine())
    return "%s %s %s" % (platform.system(), platform.release(), platform.machine())


def opengl_renderer():
    """The graphics the 3D view draws with, from a throwaway OpenGL context: 'Microsoft Basic Render Driver',
    'GDI Generic' or 'llvmpipe' mean no real graphics driver (drawn by the CPU, slow)."""
    from incad.qt import QtGui
    surface = QtGui.QOffscreenSurface()
    surface.create()
    ctx = QtGui.QOpenGLContext()
    try:
        if not ctx.create() or not ctx.makeCurrent(surface):
            return "no context"
        f = ctx.functions()
        return "%s / %s / %s" % (f.glGetString(0x1F01), f.glGetString(0x1F02), f.glGetString(0x1F00))  # renderer,
    finally:                                                                                    # version, vendor
        ctx.doneCurrent()
        surface.destroy()


def describe():
    """One line for the log at startup: the system, FreeCAD, Python, Qt, the screens and what InCad needs of FreeCAD
    (a Windows test build is debugged from this line). Never raises."""
    import importlib.util
    import platform
    parts = []

    def add(label, get):
        try:
            parts.append("%s %s" % (label, get()))
        except Exception as e:
            parts.append("%s ? (%s)" % (label, e))

    import incad
    add("InCad", lambda: incad.__version__)
    add("on", system_name)
    add("FreeCAD", lambda: ".".join(__import__("FreeCAD").Version()[:3]))
    add("Python", lambda: platform.python_version())
    add("Qt", lambda: __import__("incad.qt", fromlist=["QtCore"]).QtCore.qVersion())

    def screens():
        from incad.qt import QtWidgets
        return ", ".join("%dx%d@%g" % (s.size().width(), s.size().height(), s.devicePixelRatio())
                         for s in QtWidgets.QApplication.screens())
    add("screens", screens)
    add("OpenGL", opengl_renderer)
    missing = []
    for name in ("Part", "Sketcher", "PartDesign", "MeshPart", "JointObject", "UtilsAssembly", "BOPTools", "numpy",
                 "pivy.coin"):
        try:
            found = importlib.util.find_spec(name) is not None  # found, not imported: no side effects at startup
        except Exception:
            found = False
        if not found:
            missing.append(name)
    parts.append("missing modules: " + (", ".join(missing) or "none"))
    add("fonts", lambda: len(__import__("incad.core.sketch_text", fromlist=["fonts"]).fonts()))
    add("freecadcmd", lambda: freecadcmd(__import__("FreeCAD").getHomePath()))
    return "; ".join(parts)
