import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.ui.section_panel import SectionPanel


class SectionPanelTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.panel = SectionPanel("light", reach=30.0)
        self.seen = []
        self.panel.changed.connect(lambda o, f: self.seen.append((o, f)))

    def settle(self):
        from PySide6.QtTest import QTest
        QTest.qWait(200)

    def test_offset_from_the_field_and_the_slider_and_flip(self):
        self.panel.offset.setValue(12.5)
        self.settle()
        self.assertEqual(self.seen[-1], (12.5, False))
        self.assertEqual(self.panel.slider.value(), 125)
        self.panel.slider.setValue(-80)
        self.settle()
        self.assertEqual(self.seen[-1], (-8.0, False))
        self.panel.flip.setChecked(True)
        self.settle()
        self.assertEqual(self.seen[-1], (-8.0, True))
        self.assertEqual(self.panel.values(), (-8.0, True))

    def test_done_and_off(self):
        got = []
        self.panel.done.connect(lambda: got.append("done"))
        self.panel.off.connect(lambda: got.append("off"))
        self.panel.done_button.click()
        self.panel.off_button.click()
        self.assertEqual(got, ["done", "off"])
