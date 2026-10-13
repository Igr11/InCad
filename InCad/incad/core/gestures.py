"""Turns mouse events on a 3D view into InCad navigation actions. Pure logic (no Qt, no FreeCAD).
Buttons: LEFT=1, RIGHT=2, MIDDLE=4; `buttons` is what is held after the event.

feed(kind, button, buttons, x, y) -> actions; kind is 'press' | 'release' | 'move' | 'dblclick'.
('pass',) lets FreeCAD have the event, otherwise it is consumed. ('replay_press', x, y) hands FreeCAD the left
press InCad held back. ('orbit_start', x, y) / ('orbit', dx, dy) / ('orbit_end',); ('pan_start', x, y) /
('pan', dx, dy) / ('pan_end',) for the navigation-strip Pan tool; ('menu', x, y) right-click;
('flick_start', x, y) right-drag — the marking menu takes the mouse from there. ('drag_start', x, y) — the left press
became a drag (sent before its replay) and ('drag_end',) — that drag's release (or a lost one)."""
import math

LEFT, RIGHT, MIDDLE = 1, 2, 4
DRAG_PX = 4
PASS = ("pass",)


class Gestures:
    def __init__(self):
        self.mode = None  # None | 'orbit' | 'pan': a navigation-strip tool turns a left drag into orbit/pan
        self.reset()

    def reset(self):
        self.state = "idle"
        self.press = None
        self.last = None

    @staticmethod
    def _far(a, x, y):
        return math.hypot(x - a[0], y - a[1]) > DRAG_PX

    def feed(self, kind, button, buttons, x, y):
        if kind == "move" and buttons == 0 and self.state != "idle":
            # a release got lost (Cmd-Tab, Mission Control, a dialog): end whatever was going on
            ended = [("orbit_end",)] if self.state == "orbit" else [(self.mode + "_end",)] if self.state == "tool" \
                else [("drag_end",)] if self.state == "passthrough" else []
            self.reset()
            return ended + [PASS]
        actions = getattr(self, "_" + self.state)(kind, button, buttons, x, y)
        if button == RIGHT and PASS in actions:  # InCad owns the right button: FreeCAD would open its own menu
            actions = [a for a in actions if a != PASS]
        return actions

    def _idle(self, kind, button, buttons, x, y):
        if kind == "press" and button == LEFT and buttons == LEFT:
            if self.mode:
                self.state, self.last = "tool", (x, y)
                return [(self.mode + "_start", x, y)]
            self.state, self.press = "left_held", (x, y)
            return []
        if kind == "press" and button == RIGHT and buttons == RIGHT:
            self.state, self.press = "right_held", (x, y)
            return []
        if kind == "release" and button == RIGHT:
            return []  # a lone right release would open FreeCAD's own context menu
        return [PASS]

    def _left_held(self, kind, button, buttons, x, y):
        if kind == "press" and button == RIGHT:
            self.state, self.last = "orbit", (x, y)
            return [("orbit_start",) + self.press]
        if kind == "move" and self._far(self.press, x, y):
            self.state = "passthrough"
            return [("drag_start",) + self.press, ("replay_press",) + self.press, PASS]
        if kind == "release" and button == LEFT:
            press = self.press
            self.reset()
            return [("replay_press",) + press, PASS]
        return []

    def _passthrough(self, kind, button, buttons, x, y):
        if kind == "release" and buttons == 0:
            self.reset()
            return [("drag_end",), PASS]
        return [PASS]

    def _right_held(self, kind, button, buttons, x, y):
        if kind == "press" and button == LEFT:
            self.state, self.last = "orbit", (x, y)
            return [("orbit_start",) + self.press]
        if kind == "move" and self._far(self.press, x, y):
            press = self.press
            self.reset()
            return [("flick_start",) + press]
        if kind == "release" and button == RIGHT:
            press = self.press
            self.reset()
            return [("menu",) + press]
        return []

    def _orbit(self, kind, button, buttons, x, y):
        if kind == "move":
            dx, dy = x - self.last[0], y - self.last[1]
            self.last = (x, y)
            return [("orbit", dx, dy)] if (dx or dy) else []
        if kind == "release" and buttons == 0:
            self.reset()
            return [("orbit_end",)]
        return []

    def _tool(self, kind, button, buttons, x, y):
        if kind == "move":
            dx, dy = x - self.last[0], y - self.last[1]
            self.last = (x, y)
            return [(self.mode, dx, dy)] if (dx or dy) else []
        if kind == "release" and button == LEFT:
            mode = self.mode
            self.reset()
            return [(mode + "_end",)]
        return []
