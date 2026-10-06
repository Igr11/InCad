import unittest

from widgets import qtapp
from incad.ui.plane_panel import PlanePanel


class PlanePanelTest(unittest.TestCase):
    def test_buttons_emit_the_plane(self):
        qtapp.app()
        p = PlanePanel("dark")
        seen = []
        p.picked.connect(seen.append)
        p.cancelled.connect(lambda: seen.append("cancel"))
        p.button("XZ_Plane").click()
        p.findChildren(type(p.button("XY_Plane")))[-1].click()
        self.assertEqual(seen, ["XZ_Plane", "cancel"])
