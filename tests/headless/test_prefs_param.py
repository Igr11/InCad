import unittest

import FreeCAD as App
from incad.core import prefs


class PrefsParamTest(unittest.TestCase):
    def test_stored_in_freecad_parameters(self):
        prefs._store = None  # force the FreeCAD backend
        prefs.set_theme("light")
        prefs.set_remember_new_choice(True)
        p = App.ParamGet(prefs.GROUP)
        self.assertEqual(p.GetString("Theme"), "light")
        self.assertTrue(p.GetBool("RememberNewChoice"))
        prefs.set_takeover_snapshot("x")
        prefs.clear_takeover_snapshot()
        self.assertEqual(p.GetString("TakeoverSnapshot", ""), "")
