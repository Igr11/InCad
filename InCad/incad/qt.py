"""Qt imports for InCad: FreeCAD's PySide shim inside FreeCAD, plain PySide6 in widget tests."""
try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction
Signal = QtCore.Signal


_NOW = [False]


def dispose(obj):
    """Delete a Qt object InCad made: later (deleteLater) normally, at once while FreeCAD quits — macOS ends the
    process from inside the window's close, where deferred deletes never run (probed crash)."""
    try:
        if _NOW[0]:
            import shiboken6
            if shiboken6.isValid(obj):
                shiboken6.delete(obj)
        else:
            obj.deleteLater()
    except (RuntimeError, ImportError):
        pass


def dispose_now(on=True):
    _NOW[0] = on


_GRAPHICS_VIEWS = {}  # viewport's C++ address -> the graphicsView wrapper that keeps the viewport wrapper valid


def viewport_of(view):
    """The 3D view's viewport widget. With PySide 6.11 (InnCad's runtime) a child wrapper dies as soon as the
    graphicsView wrapper FreeCAD returned is garbage-collected, so view.graphicsView().viewport() in one expression
    is dead at once (probed); keep that wrapper alive while its viewport exists. Harmless on PySide 6.8."""
    gv = view.graphicsView()
    vp = gv.viewport()
    try:
        import shiboken6
        key = shiboken6.getCppPointer(vp)[0]
    except (ImportError, TypeError):  # no shiboken, or not a Qt object (the tests' stand-in views)
        return vp
    if key not in _GRAPHICS_VIEWS:
        vp.destroyed.connect(lambda _=None, k=key: _GRAPHICS_VIEWS.pop(k, None))
    _GRAPHICS_VIEWS[key] = gv
    return vp
