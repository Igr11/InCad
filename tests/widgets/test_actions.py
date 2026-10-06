import os
import unittest

from incad import actions
from incad.core.commands import Registry
from incad.ui import theme

EXPECTED = {"file.new", "file.open", "file.save", "file.save_as", "file.close", "edit.undo", "edit.redo",
            "view.theme_toggle", "view.freecad", "view.zoom_all", "view.home", "view.style_shaded",
            "view.style_wireframe", "view.parameters", "view.look_at", "view.zoom_selection", "browser.edit",
            "browser.move_end_of_part", "browser.suppress", "browser.rename", "nav.orbit", "nav.pan",
            "sketch.start", "sketch.finish", "feature.extrude", "feature.revolve", "feature.hole", "feature.fillet",
            "feature.chamfer", "feature.shell", "feature.rect_pattern", "feature.circ_pattern", "feature.mirror",
            "work.plane", "work.axis", "work.point", "inspect.measure", "inspect.mass", "feature.thread",
            "feature.combine", "file.new_assembly", "assembly.place", "assembly.create", "assembly.ground",
            "constrain.mate", "constrain.flush", "constrain.angle", "constrain.tangent", "constrain.insert",
            "joint.rigid", "joint.rotational", "joint.slider", "joint.cylindrical", "joint.ball", "assembly.combine", "feature.sweep", "feature.loft", "feature.coil", "feature.draft",
            "tools.material", "view.section", "browser.delete"} | set(actions.SKETCHER)


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

    def test_sketch_shortcuts(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual(r.get("sketch.start").shortcut, "S")
        self.assertEqual({i: r.get(i).shortcut for i in ("sketch.line", "sketch.circle", "sketch.arc",
                          "sketch.rectangle", "sketch.dimension", "sketch.trim")},
                         {"sketch.line": "L", "sketch.circle": "C", "sketch.arc": "A", "sketch.rectangle": "R",
                          "sketch.dimension": "D", "sketch.trim": "X"})
        self.assertEqual(r.get("sketch.line").contexts, frozenset({"sketch"}))

    def test_feature_shortcuts(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual((r.get("feature.extrude").shortcut, r.get("feature.revolve").shortcut), ("E", "R"))
        self.assertEqual(r.get("feature.extrude").contexts, frozenset({"part"}))

    def test_hole_and_fillet_shortcuts(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual((r.get("feature.hole").shortcut, r.get("feature.fillet").shortcut), ("H", "F"))

    def test_assembly_shortcuts(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual((r.get("assembly.place").shortcut, r.get("constrain.mate").shortcut,
                          r.get("joint.rigid").shortcut), ("P", "C", "J"))
        self.assertEqual(r.get("constrain.mate").contexts, frozenset({"assembly"}))
