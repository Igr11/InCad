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
                         {"part", "face", "edge", "vertex", "empty", "browser", "sketch"})
        self.assertEqual(marking_layout.LAYOUT["sketch"]["N"], "sketch.finish")
        self.assertEqual(marking_layout.LAYOUT["sketch"]["S"], "sketch.dimension")
        self.assertEqual(marking_layout.LAYOUT["part"]["N"], "sketch.start")
        self.assertEqual(marking_layout.LAYOUT["part"]["S"], "feature.extrude")
        self.assertEqual(marking_layout.LAYOUT["face"]["S"], "feature.extrude")
