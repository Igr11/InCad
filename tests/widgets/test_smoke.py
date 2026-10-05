import unittest

from widgets import qtapp


class SmokeTest(unittest.TestCase):
    def test_qt_offscreen(self):
        qtapp.app()
        from incad.qt import QtWidgets
        b = QtWidgets.QToolButton()
        b.setText("x")
        self.assertGreater(b.sizeHint().width(), 0)

    def test_freecad_not_importable_here(self):
        with self.assertRaises(ImportError):
            import FreeCAD  # noqa: F401
