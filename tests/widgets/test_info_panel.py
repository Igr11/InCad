import unittest

from widgets import qtapp
from incad.ui.info_panel import InfoPanel


class InfoPanelTest(unittest.TestCase):
    def test_rows_and_close(self):
        qtapp.app()
        p = InfoPanel("Measure", [("Distance", "10 mm"), ("Angle", "0°")], "light")
        p.show()
        self.assertEqual(p.rows(), [("Distance", "10 mm"), ("Angle", "0°")])
        p.close_button.click()
        self.assertFalse(p.isVisible())
