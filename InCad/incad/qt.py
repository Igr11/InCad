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
