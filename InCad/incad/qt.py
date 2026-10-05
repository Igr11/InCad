"""Qt imports for InCad: FreeCAD's PySide shim inside FreeCAD, plain PySide6 in widget tests."""
try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction
Signal = QtCore.Signal
