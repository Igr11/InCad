import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.core.commands import Command, Registry
from incad.ui.marking_menu import DEAD_ZONE, MarkingMenu, direction_for


class DirectionTest(unittest.TestCase):
    def test_directions(self):
        cases = {(0, -50): "N", (40, -40): "NE", (50, 0): "E", (40, 40): "SE", (0, 50): "S",
                 (-40, 40): "SW", (-50, 0): "W", (-40, -40): "NW"}
        for (dx, dy), d in cases.items():
            self.assertEqual(direction_for(dx, dy), d, (dx, dy))
        self.assertIsNone(direction_for(DEAD_ZONE - 1, 0))


class MarkingMenuTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.reg = Registry()
        for i in ("n", "e", "s", "w", "x"):
            self.reg.register(Command(id=i, label="Cmd " + i, icon="incad", handler=lambda i=i: self.ran.append(i)))
        slots = [("N", self.reg.get("n")), ("E", self.reg.get("e")), ("S", self.reg.get("s")), ("W", self.reg.get("w"))]
        self.menu = MarkingMenu(self.reg, slots, [self.reg.get("x")], "light")
        self.menu.show_at(QtCore.QPoint(600, 500))
        self.c = self.menu.center_global()

    def tearDown(self):
        self.menu.close()

    def test_ring_layout(self):
        def center(d):
            b = self.menu.button(d)
            return b.mapToGlobal(b.rect().center())
        self.assertLess(center("N").y(), self.c.y() - 40)
        self.assertGreater(center("S").y(), self.c.y() + 40)
        self.assertGreater(center("E").x(), self.c.x() + 40)
        self.assertLess(center("W").x(), self.c.x() - 40)
        self.assertIsNone(self.menu.button("NE"))
        self.assertEqual(self.menu.list_labels(), ["Cmd x"])

    def test_click_runs_and_closes(self):
        seen = []
        self.menu.triggered.connect(seen.append)
        self.menu.button("E").click()
        self.assertEqual((self.ran, seen), (["e"], ["e"]))
        self.assertFalse(self.menu.isVisible())

    def test_flick(self):
        self.menu.start_flick()
        self.menu.flick_move(self.c + QtCore.QPoint(0, -60))
        self.assertEqual(self.menu.hot_direction(), "N")
        self.menu.flick_end(self.c + QtCore.QPoint(0, -60))
        self.assertEqual(self.ran, ["n"])
        self.assertFalse(self.menu.isVisible())

    def test_flick_to_empty_slot_or_dead_zone_runs_nothing(self):
        self.menu.start_flick()
        self.menu.flick_end(self.c + QtCore.QPoint(40, -40))  # NE has no command
        self.assertEqual(self.ran, [])
        self.assertFalse(self.menu.isVisible())

    def test_list_item(self):
        [b for b in self.menu.findChildren(type(self.menu.button("N"))) if b.text() == "Cmd x"][0].click()
        self.assertEqual(self.ran, ["x"])

    def test_escape_closes(self):
        from PySide6.QtTest import QTest
        QTest.keyClick(self.menu, QtCore.Qt.Key_Escape)
        self.assertFalse(self.menu.isVisible())
        self.assertEqual(self.ran, [])


class RingSpacingTest(unittest.TestCase):
    def test_eight_long_labels_never_overlap(self):
        qtapp.app()
        reg = Registry()
        from incad.ui.marking_layout import DIRECTIONS
        slots = []
        for d in DIRECTIONS:
            cmd = reg.register(Command(id=d, label="Zoom Selection " + d, icon="incad", handler=lambda: None))
            slots.append((d, cmd))
        menu = MarkingMenu(reg, slots, [], "light")
        menu.show_at(QtCore.QPoint(600, 500))
        rects = {d: menu.button(d).geometry() for d in DIRECTIONS}
        clashes = [(a, b) for i, a in enumerate(DIRECTIONS) for b in DIRECTIONS[i + 1:] if rects[a].intersects(rects[b])]
        menu.close()
        self.assertEqual(clashes, [])
        for d, r in rects.items():
            self.assertTrue(menu.rect().contains(r), d)
