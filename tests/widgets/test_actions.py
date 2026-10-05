import os
import unittest

from incad import actions
from incad.core.commands import Registry
from incad.ui import theme

EXPECTED = {"file.new", "file.open", "file.save", "file.save_as", "file.close", "edit.undo", "edit.redo",
            "view.theme_toggle", "view.freecad", "view.zoom_all", "view.home", "view.style_shaded",
            "view.style_wireframe", "view.parameters", "view.look_at", "view.zoom_selection", "browser.edit",
            "browser.move_end_of_part", "browser.suppress", "browser.rename", "nav.orbit", "nav.pan"}


class ActionsTest(unittest.TestCase):
    def test_register_all(self):
        r = Registry()
        actions.register_all(r)
        actions.register_all(r)  # idempotent
        self.assertEqual(set(r.ids()), EXPECTED)
        self.assertEqual(r.get("file.new").shortcut, "Ctrl+N")

    def test_every_command_icon_exists(self):
        for cmd in actions.commands():
            for t in ("light", "dark"):
                self.assertTrue(os.path.isfile(theme.icon_path(cmd.icon, t)), (cmd.id, t))

    def test_std_commands_cover_wrappers(self):
        self.assertTrue(set(actions.STD_COMMANDS) <= EXPECTED)
