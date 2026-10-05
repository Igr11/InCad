import os
import sys
import unittest
import xml.etree.ElementTree as ET

from widgets import qtapp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools"))
import make_icons  # noqa: E402
from incad.ui import theme  # noqa: E402


class IconsTest(unittest.TestCase):
    def test_every_icon_exists_in_both_themes_and_parses(self):
        for t in ("light", "dark"):
            for name in make_icons.ALL_NAMES:
                path = theme.icon_path(name, t)
                self.assertTrue(os.path.isfile(path), path)
                ET.parse(path)

    def test_no_stale_icons(self):
        for t in ("light", "dark"):
            files = sorted(f[:-4] for f in os.listdir(os.path.join(theme.ICON_DIR, t))
                           if f.endswith(".svg") and not f.startswith("._"))
            self.assertEqual(files, make_icons.ALL_NAMES)

    def test_icons_render(self):
        qtapp.app()
        for name in make_icons.ALL_NAMES:
            self.assertFalse(theme.icon(name, "dark").pixmap(32, 32).isNull(), name)

    def test_theme_toggle_differs_by_theme(self):
        with open(theme.icon_path("theme_toggle", "light")) as a, open(theme.icon_path("theme_toggle", "dark")) as b:
            self.assertNotEqual(a.read(), b.read())
