import unittest

from incad import actions
from incad.core.commands import Command, Registry
from incad.ui import marking_layout


class MarkingLayoutTest(unittest.TestCase):
    def test_resolve_orders_and_skips_unknown(self):
        r = Registry()
        for i in ("a", "b", "c"):
            r.register(Command(id=i, label=i, icon="incad", handler=lambda: None))
        layout = {"ctx": {"S": "b", "N": "a", "E": "missing", "list": ["c", "missing"]}}
        slots, items = marking_layout.resolve("ctx", r, layout)
        self.assertEqual([(d, c.id) for d, c in slots], [("N", "a"), ("S", "b")])
        self.assertEqual([c.id for c in items], ["c"])
        self.assertEqual(marking_layout.resolve("nothing", r, layout), ([], []))

    def test_every_layout_command_exists(self):
        r = Registry()
        actions.register_all(r)
        for ctx, spec in marking_layout.LAYOUT.items():
            ids = [v for k, v in spec.items() if k != "list"] + spec.get("list", [])
            missing = [i for i in ids if not r.has(i)]
            self.assertEqual(missing, [], ctx)
            self.assertTrue(set(spec) <= set(marking_layout.DIRECTIONS) | {"list"}, ctx)

    def test_contexts(self):
        self.assertEqual(set(marking_layout.LAYOUT),
                         {"part", "face", "edge", "vertex", "empty", "browser", "origin", "sketch", "assembly",
                          "asm_face", "asm_edge", "solid", "joint", "asm_cut"})
        self.assertEqual(marking_layout.LAYOUT["origin"]["list"], ["sketch.start", "view.toggle_visibility"])  # planes/axes
        for ctx in ("part", "face", "edge", "vertex", "browser", "origin"):  # Hide / Show from any RMB in the view
            self.assertIn("view.toggle_visibility", marking_layout.LAYOUT[ctx]["list"], ctx)
        self.assertEqual(marking_layout.LAYOUT["sketch"]["list"][:2], ["sketch.stop", "edit.delete"])  # RMB: Stop Tool first
        self.assertEqual(marking_layout.LAYOUT["assembly"]["N"], "assembly.place")
        self.assertEqual(marking_layout.LAYOUT["asm_face"]["N"], "constrain.mate")
        for ctx in ("asm_face", "asm_edge"):  # Parallel / Perpendicular on a face or an edge: in the list
            self.assertIn("constrain.parallel", marking_layout.LAYOUT[ctx]["list"], ctx)
            self.assertIn("constrain.perpendicular", marking_layout.LAYOUT[ctx]["list"], ctx)
        self.assertEqual({d: marking_layout.LAYOUT["asm_face"][d] for d in ("N", "S", "E", "W")},
                         {"N": "constrain.mate", "S": "constrain.flush", "E": "constrain.angle", "W": "constrain.tangent"})
        self.assertIn("constrain.angle", marking_layout.LAYOUT["asm_edge"]["list"])  # Angle takes edges too
        self.assertEqual(marking_layout.LAYOUT["sketch"]["N"], "sketch.finish")
        self.assertEqual(marking_layout.LAYOUT["sketch"]["S"], "sketch.dimension")
        self.assertEqual(marking_layout.LAYOUT["part"]["N"], "sketch.start")
        self.assertEqual(marking_layout.LAYOUT["part"]["S"], "feature.extrude")
        self.assertEqual(marking_layout.LAYOUT["face"]["S"], "feature.extrude")
        self.assertEqual({d: marking_layout.LAYOUT["joint"][d] for d in ("N", "S", "E", "W")},
                         {"N": "browser.edit", "S": "browser.delete", "E": "constraint.suppress", "W": "browser.rename"})
        self.assertEqual(marking_layout.LAYOUT["joint"]["list"],
                         ["browser.edit", "browser.delete", "constraint.suppress", "browser.rename"])
        cut = marking_layout.LAYOUT["asm_cut"]  # an assembly cut's row: no Suppress (it is no constraint)
        self.assertNotIn("constraint.suppress", list(cut.values()) + cut["list"])
        self.assertEqual(cut["list"], ["browser.edit", "browser.delete", "browser.rename"])


class BrowserListTest(unittest.TestCase):
    def test_edit_is_first_in_the_model_tree_list(self):
        """RMB on a sketch or feature in the model tree: Edit in the plain list too, not only the radial slot."""
        self.assertEqual(marking_layout.LAYOUT["browser"]["list"][0], "browser.edit")
