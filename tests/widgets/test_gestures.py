import unittest

from incad.core.gestures import LEFT, MIDDLE, PASS, RIGHT, Gestures


class GesturesTest(unittest.TestCase):
    def setUp(self):
        self.g = Gestures()

    def feed(self, *events):
        out = []
        for e in events:
            out.append(self.g.feed(*e))
        return out

    def test_hover_passes(self):
        self.assertEqual(self.g.feed("move", 0, 0, 5, 5), [PASS])

    def test_left_click_is_replayed(self):
        a, b = self.feed(("press", LEFT, LEFT, 10, 10), ("release", LEFT, 0, 11, 10))
        self.assertEqual(a, [])
        self.assertEqual(b, [("replay_press", 10, 10), PASS])
        self.assertEqual(self.g.state, "idle")

    def test_left_drag_is_handed_to_freecad(self):
        a, b, c, d = self.feed(("press", LEFT, LEFT, 10, 10), ("move", 0, LEFT, 12, 10),
                               ("move", 0, LEFT, 30, 10), ("release", LEFT, 0, 30, 10))
        self.assertEqual((a, b), ([], []))
        self.assertEqual(c, [("replay_press", 10, 10), PASS])
        self.assertEqual(d, [PASS])
        self.assertEqual(self.g.state, "idle")

    def test_left_then_right_orbits_and_any_release_order_ends_it(self):
        for first, rest in ((LEFT, RIGHT), (RIGHT, LEFT)):
            g = Gestures()
            self.assertEqual(g.feed("press", LEFT, LEFT, 10, 10), [])
            self.assertEqual(g.feed("press", RIGHT, LEFT | RIGHT, 10, 10), [("orbit_start", 10, 10)])
            self.assertEqual(g.feed("move", 0, LEFT | RIGHT, 15, 7), [("orbit", 5, -3)])
            self.assertEqual(g.feed("release", first, rest, 15, 7), [])
            self.assertEqual(g.feed("move", 0, rest, 18, 7), [("orbit", 3, 0)])
            self.assertEqual(g.feed("release", rest, 0, 18, 7), [("orbit_end",)])
            self.assertEqual(g.state, "idle")

    def test_right_then_left_orbits(self):
        a, b = self.feed(("press", RIGHT, RIGHT, 50, 50), ("press", LEFT, LEFT | RIGHT, 51, 50))
        self.assertEqual(b, [("orbit_start", 50, 50)])

    def test_right_click_opens_menu(self):
        a, b = self.feed(("press", RIGHT, RIGHT, 40, 40), ("release", RIGHT, 0, 41, 40))
        self.assertEqual((a, b), ([], [("menu", 40, 40)]))

    def test_right_drag_flicks_and_hands_over(self):
        a, b, c = self.feed(("press", RIGHT, RIGHT, 40, 40), ("move", 0, RIGHT, 40, 20), ("release", RIGHT, 0, 40, 20))
        self.assertEqual(b, [("flick_start", 40, 40)])
        self.assertEqual(c, [])  # a lone right release never reaches FreeCAD

    def test_lone_right_release_is_swallowed(self):
        self.assertEqual(self.g.feed("release", RIGHT, 0, 1, 1), [])

    def test_middle_and_double_click_pass(self):
        self.assertEqual(self.g.feed("press", MIDDLE, MIDDLE, 1, 1), [PASS])
        self.assertEqual(self.g.feed("dblclick", LEFT, LEFT, 1, 1), [PASS])

    def test_tool_mode_left_drag(self):
        self.g.mode = "pan"
        a, b, c = self.feed(("press", LEFT, LEFT, 0, 0), ("move", 0, LEFT, 4, 2), ("release", LEFT, 0, 4, 2))
        self.assertEqual((a, b, c), ([("pan_start", 0, 0)], [("pan", 4, 2)], [("pan_end",)]))
        self.g.mode = "orbit"
        self.assertEqual(self.g.feed("press", LEFT, LEFT, 0, 0), [("orbit_start", 0, 0)])
