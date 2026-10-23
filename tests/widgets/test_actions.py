import os
import unittest

from incad import actions
from incad.core.commands import Registry
from incad.ui import theme

EXPECTED = {"file.new", "file.open", "file.save", "file.save_as", "file.export", "file.close", "edit.undo", "edit.redo", "edit.update",
            "view.theme_toggle", "view.freecad", "view.zoom_all", "view.home", "view.style_shaded",
            "view.style_wireframe", "view.parameters", "view.look_at", "view.zoom_selection", "browser.edit",
            "view.toggle_visibility", "view.origin_show_all", "view.origin_hide_all",
            "browser.move_end_of_part", "browser.suppress", "browser.rename", "view.show_in_browser",
            "browser.show_in_window", "nav.orbit", "nav.pan",
            "sketch.start", "sketch.finish", "feature.extrude", "feature.revolve", "feature.hole", "feature.fillet", "feature.full_round", "feature.line3d", "view.screenshot", "view.screenshot_window", "picture.insert", "picture.scale", "picture.on_xy", "picture.on_xz", "picture.on_yz", "picture.turn", "picture.mirror", "picture.show_hide", "view.sketches_show_all", "view.sketches_hide_all",
            "feature.chamfer", "feature.shell", "feature.rect_pattern", "feature.circ_pattern", "feature.mirror",
            "work.plane", "work.axis", "work.point", "inspect.measure", "inspect.mass", "feature.thread", "feature.threads_toggle",
            "feature.combine", "feature.split", "feature.move_face", "feature.finish_move", "file.make_assembly", "assembly.threads_toggle", "assembly.suppress", "assembly.edit", "assembly.remove", "tools.ask_on_new", "file.new_assembly", "assembly.place", "assembly.create", "assembly.ground",
            "constrain.mate", "constrain.flush", "constrain.angle", "constrain.parallel", "constrain.perpendicular",
            "constrain.tangent", "constrain.insert",
            "joint.rigid", "joint.rotational", "joint.slider", "joint.cylindrical", "joint.ball", "assembly.combine", "feature.sweep", "feature.loft", "feature.coil", "feature.draft",
            "tools.material", "tools.appearance", "view.axes_show_all", "view.axes_hide_all", "assembly.open", "assembly.interference", "view.section", "browser.delete", "edit.delete", "edit.delete_key",
            "inspect.distance", "inspect.angle", "inspect.length", "inspect.area", "view.section_points", "sketch.constraints_toggle", "sketch.constraints_window",
            "sketch.constraints_show", "sketch.constraints_hide", "feature.emboss", "sketch.text", "sketch.offset", "sketch.dimension_overall", "sketch.mirror", "sketch.slot_overall",
            "sketch.slot_center", "sketch.construction", "file.quit", "sketch.rect_pattern", "sketch.circ_pattern",
            "sketch.path_pattern",
            "sketch.edit_pattern", "sketch.delete_pattern", "view.dof", "view.assembly_context", "constraint.suppress"} | set(actions.SKETCHER) | set(actions.SKETCH_VARIANTS)


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

    def test_parallel_and_perpendicular(self):
        r = Registry()
        actions.register_all(r)
        for cid, label, icon, tip in (
                ("constrain.parallel", "Parallel", "parallel_c", "Two faces or edges stay parallel; the distance stays free"),
                ("constrain.perpendicular", "Perpendicular", "perpendicular_c", "Two faces or edges stay at 90°")):
            c = r.get(cid)
            self.assertEqual((c.label, c.icon, c.tooltip, c.contexts), (label, icon, tip, frozenset({"assembly"})))
        self.assertNotEqual(r.get("constrain.parallel").icon, r.get("sketch.parallel").icon)  # not the sketch's

    def test_quit_shortcut(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual(r.get("file.quit").shortcut, "Ctrl+Q")
