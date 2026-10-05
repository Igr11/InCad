"""One QApplication for all widget tests (offscreen)."""
from incad.qt import QtWidgets


def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
