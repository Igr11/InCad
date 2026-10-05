# InCad 1b — Navigation + Marking Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inventor-style mouse handling in InCad's 3D view — LMB+RMB drag orbits around the point under the cursor,
a right-click opens InCad's radial marking menu instead of FreeCAD's context menu (right-drag flicks it), left
clicks still select, middle-drag pans and the wheel zooms at the cursor — plus the marking menu in the Model
Browser, a navigation strip on the 3D view, and a ViewCube in InCad's colors.

**Architecture:** Pure logic first: `incad.core.gestures` (mouse events → navigation actions) and `incad.core.camera`
(orbit/pan on a Coin camera via pivy) are unit-tested without FreeCAD. `incad.ui.marking_menu`, `incad.ui.nav_strip`
are PySide widgets tested offscreen. `incad.ui.nav.Navigator` is an event filter on FreeCAD's 3D viewports that feeds
the gesture machine and performs its actions; the shell installs it, forces FreeCAD's CAD navigation style with
zoom-at-cursor (pan/zoom stay FreeCAD's own) and restores every changed setting on exit, as in plan 1a.

**Tech Stack:** FreeCAD 1.1.3, PySide6 6.8.3, pivy (Coin) — importable in FreeCAD's bundled Python without FreeCAD.

**Spec:** `docs/superpowers/specs/2026-10-05-incad-stage1-design.md` — §3.2 nav/navigation, §4 marking menu,
3D view (ViewCube, navigation strip), shortcuts; plan 1a is the base (branch `stage-1a`).

## Global Constraints

- Everything from plan 1a's Global Constraints still holds (Qt only through `incad.qt`, `run_safely` for model
  changes, throwaway `user.cfg` for every FreeCAD run, English UI, announce GUI test runs).
- Navigation: LMB+RMB drag = orbit (no Shift); MMB drag = pan; wheel = zoom at cursor; LMB = select;
  RMB press+release with no LMB and no movement = marking menu; RMB drag = flick the marking menu.
- FreeCAD must never show its own 3D-view context menu while InCad navigation is on.
- Navigation can be switched off (⚙ → Mouse Navigation); then FreeCAD's own navigation applies.
- Every FreeCAD setting InCad changes (NavigationStyle, ZoomAtCursor, NaviCube BaseColor) is in the takeover
  snapshot and restored exactly on exit / crash recovery.
- Coin pixel positions are device pixels with a bottom-left origin (Retina: ×2): `nav.to_coin()` converts.

## Review Focus

1. A left click on the model after InCad held the press back must still select exactly what FreeCAD would select;
   a left drag must still reach FreeCAD (Task 7 GUI tests 2, 3).
2. Releasing the buttons in any order after an orbit (left first or right first) must end the orbit and never
   select or open a menu (Task 3 tests, Task 7 GUI test 3).
3. A lone right-button release reaching FreeCAD would open FreeCAD's menu — idle must swallow it (Task 3 test,
   Task 7 GUI test 4).
4. Right-click on a face selects that face and offers face commands; on empty space offers part commands; with no
   InCad part offers New/Open (Task 7 GUI tests 4, 5).
5. Leaving InCad (or turning navigation off) leaves FreeCAD's navigation exactly as before (Task 7 GUI tests 10, 11).

## File Map

```
InCad/incad/core/context.py        target of a context command (browser row)
InCad/incad/core/gestures.py       mouse events -> navigation actions (pure)
InCad/incad/core/camera.py         orbit / pan on a Coin camera (pivy)
InCad/incad/core/document.py       + owning_feature()
InCad/incad/core/prefs.py          + navigation_enabled()
InCad/incad/actions.py             + Look At, Zoom Selection, browser commands, Orbit/Pan tools
InCad/incad/ui/marking_layout.py   which commands the marking menu shows per context
InCad/incad/ui/marking_menu.py     radial marking menu widget
InCad/incad/ui/nav_strip.py        navigation strip widget
InCad/incad/ui/nav.py              Navigator: event filter on FreeCAD's 3D viewports
InCad/incad/ui/browser.py          right-click -> markingMenuRequested (replaces the QMenu)
InCad/incad/ui/ribbon_layout.py    + Look At / Zoom Selection on View ▸ Navigate
InCad/incad/ui/theme.py            + NaviCube colors
InCad/incad/ui/shell.py            wiring, snapshot/restore of navigation settings
tools/make_icons.py                + look_at zoom_selection edit suppress rename orbit pan
```

---

### Task 1: Commands, icons, context target, marking-menu layout

**Files:**
- Create: `InCad/incad/core/context.py`, `InCad/incad/ui/marking_layout.py`, `tests/widgets/test_marking_layout.py`,
  `tests/headless/test_actions_1b.py`
- Modify: `tools/make_icons.py`, `InCad/incad/core/prefs.py`, `InCad/incad/core/document.py`, `InCad/incad/actions.py`,
  `InCad/incad/ui/theme.py`, `InCad/incad/ui/ribbon_layout.py`, `tests/widgets/test_actions.py`,
  `tests/widgets/test_prefs.py`, `tests/widgets/test_theme.py`

**Interfaces:**
- Produces: `context.set_target(name|None)`, `context.target() -> str|None`; `document.owning_feature(obj)`;
  `prefs.navigation_enabled()/set_navigation_enabled(bool)` (default True); `theme.NAVICUBE_GROUP`,
  `theme.NAVICUBE_KEYS = {"BaseColor": "Unsigned"}`, `theme.navicube_params(theme)`; palette key `cube`;
  `marking_layout.DIRECTIONS = ("N","NE","E","SE","S","SW","W","NW")`, `marking_layout.LAYOUT`,
  `marking_layout.resolve(context, registry, layout=None) -> (list[(direction, Command)], list[Command])`;
  commands `view.look_at`, `view.zoom_selection`, `browser.edit`, `browser.move_end_of_part`, `browser.suppress`,
  `browser.rename`, `nav.orbit`, `nav.pan`; `actions.rename(ask=None)`, `actions.toggle_suppress()`,
  `actions.move_end_of_part_here()`. `nav.orbit/nav.pan` call `shell.toggle_nav_mode(mode)` and
  `shell.nav_mode()` (Task 7).

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_marking_layout.py`:
```python
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
        self.assertEqual(set(marking_layout.LAYOUT), {"part", "face", "edge", "vertex", "empty", "browser"})
```

Append to `tests/widgets/test_prefs.py` (inside `PrefsMemoryTest`):
```python
    def test_navigation_flag(self):
        self.assertTrue(prefs.navigation_enabled())
        prefs.set_navigation_enabled(False)
        self.assertFalse(prefs.navigation_enabled())
```

Append to `tests/widgets/test_theme.py` (inside `ThemeTest`):
```python
    def test_navicube_params(self):
        self.assertEqual(theme.navicube_params("dark"), {"BaseColor": ("Unsigned", 0x3D4450FF)})
        self.assertEqual(set(theme.navicube_params("light")), set(theme.NAVICUBE_KEYS))
```

In `tests/widgets/test_actions.py` replace the `EXPECTED` set with:
```python
EXPECTED = {"file.new", "file.open", "file.save", "file.save_as", "file.close", "edit.undo", "edit.redo",
            "view.theme_toggle", "view.freecad", "view.zoom_all", "view.home", "view.style_shaded",
            "view.style_wireframe", "view.parameters", "view.look_at", "view.zoom_selection", "browser.edit",
            "browser.move_end_of_part", "browser.suppress", "browser.rename", "nav.orbit", "nav.pan"}
```

`tests/headless/test_actions_1b.py`:
```python
import unittest

import FreeCAD as App
from incad import actions
from incad.core import context, document, safe
from headless import util


class BrowserCommandsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Cmd")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.sketch = self.doc.getObject("Sketch")

    def tearDown(self):
        context.set_target(None)
        App.closeDocument(self.doc.Name)

    def test_owning_feature(self):
        self.assertIs(document.owning_feature(self.sketch), self.pad)
        self.assertIs(document.owning_feature(self.pad), self.pad)

    def test_suppress_toggles(self):
        context.set_target(self.pad.Name)
        self.assertTrue(safe.run_safely("S", actions.toggle_suppress, self.doc).ok)
        self.assertTrue(self.pad.Suppressed)
        actions.toggle_suppress()
        self.assertFalse(self.pad.Suppressed)

    def test_rename(self):
        context.set_target(self.pad.Name)
        actions.rename(ask=lambda current: "Base Plate")
        self.assertEqual(self.pad.Label, "Base Plate")
        actions.rename(ask=lambda current: "")
        self.assertEqual(self.pad.Label, "Base Plate")

    def test_move_end_of_part_on_a_sketch_uses_its_feature(self):
        document.set_end_of_part(self.body, None)
        context.set_target(self.sketch.Name)
        actions.move_end_of_part_here()
        self.assertIs(self.body.Tip, self.pad)

    def test_no_target(self):
        context.set_target(None)
        with self.assertRaises(ValueError):
            actions.toggle_suppress()
        context.set_target("Nope")
        with self.assertRaises(ValueError):
            actions.rename(ask=lambda c: "x")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_marking_layout.py`, `tests/run_widgets.sh test_prefs.py`, `tests/run_widgets.sh test_theme.py`,
`tests/run_widgets.sh test_actions.py`, `tests/run_headless.sh test_actions_1b.py`
Expected: import errors / AttributeError (`marking_layout`, `navigation_enabled`, `navicube_params`, `context`), and
`test_register_all` failing on the missing ids.

- [ ] **Step 3: Implement**

`tools/make_icons.py` — add before `ICONS = {`:
```python
FEATURE = ('<path d="M6 22 L6 12 L16 8 L26 11 L26 21 L14 25 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
           '<path d="M6 12 L14 15 L26 11 M14 15 L14 25" fill="none" stroke="{S}" stroke-width="1.2"/>')
```
replace the `"feature": (...)` entry with `"feature": FEATURE,` and add these entries to `ICONS`:
```python
    "look_at": ('<path d="M4 22 L14 27 L28 19 L18 14 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M16 4 V18" stroke="{A}" stroke-width="2.4" stroke-linecap="round"/>'
                '<path d="M11 13 L16 19 L21 13" fill="none" stroke="{A}" stroke-width="2.4" stroke-linecap="round" '
                'stroke-linejoin="round"/>'),
    "zoom_selection": ('<circle cx="13" cy="13" r="8" fill="none" stroke="{S}" stroke-width="2.4"/>'
                       '<path d="M19 19 L27 27" stroke="{S}" stroke-width="3" stroke-linecap="round"/>'
                       '<rect x="9.5" y="9.5" width="7" height="7" fill="{A}"/>'),
    "edit": ('<path d="M6 26 L8 19 L21 6 L26 11 L13 24 Z" fill="{F}" stroke="{S}" stroke-width="1.6" '
             'stroke-linejoin="round"/><path d="M18 9 L23 14" stroke="{S}" stroke-width="1.6"/>'
             '<path d="M6 26 L8 19 L13 24 Z" fill="{A}"/>'),
    "suppress": FEATURE + '<path d="M5 27 L27 5" stroke="{R}" stroke-width="2.6" stroke-linecap="round"/>',
    "rename": ('<rect x="4" y="10" width="24" height="12" rx="2" fill="none" stroke="{N}" stroke-width="1.6"/>'
               '<path d="M9 16 H17" stroke="{S}" stroke-width="2.2" stroke-linecap="round"/>'
               '<path d="M21 7 V25 M19 7 H23 M19 25 H23" stroke="{A}" stroke-width="1.8"/>'),
    "orbit": ('<ellipse cx="16" cy="16" rx="12" ry="5" fill="none" stroke="{S}" stroke-width="2"/>'
              '<path d="M24 9 L28 12 L23 14" fill="none" stroke="{S}" stroke-width="2" stroke-linejoin="round"/>'
              '<circle cx="16" cy="16" r="3.5" fill="{A}"/>'),
    "pan": ('<path d="M16 4 V28 M4 16 H28" stroke="{S}" stroke-width="2.2"/>'
            '<path d="M12 8 L16 4 L20 8 M12 24 L16 28 L20 24 M8 12 L4 16 L8 20 M24 12 L28 16 L24 20" fill="none" '
            'stroke="{S}" stroke-width="2.2" stroke-linejoin="round"/>'),
```
Run `python3 tools/make_icons.py` → Expected `wrote 31 icons per theme …`.

`InCad/incad/core/context.py`:
```python
"""What a context command acts on: the browser row the marking menu was opened on."""
_target = None


def set_target(name):
    global _target
    _target = name or None


def target():
    return _target
```

`InCad/incad/core/prefs.py` — append:
```python
def navigation_enabled():
    return bool(_s().get("bool", "NavigationEnabled", True))


def set_navigation_enabled(value):
    _s().set("bool", "NavigationEnabled", bool(value))
```

`InCad/incad/core/document.py` — append:
```python
def owning_feature(obj):
    """The feature that uses `obj` as its profile (a sketch's Extrude); obj itself otherwise."""
    for user in obj.InList:
        prof = getattr(user, "Profile", None)
        if isinstance(prof, (tuple, list)):
            prof = prof[0] if prof else None
        if prof is obj:
            return user
    return obj
```

`InCad/incad/ui/theme.py` — add `cube="#e3e7ec"` to the light palette and `cube="#3d4450"` to the dark palette, and
append:
```python
NAVICUBE_GROUP = "User parameter:BaseApp/Preferences/NaviCube"
NAVICUBE_KEYS = {"BaseColor": "Unsigned"}


def navicube_params(theme):
    """FreeCAD NaviCube (ViewCube) settings for InCad's look."""
    return {"BaseColor": ("Unsigned", _rgba(PALETTES[theme]["cube"]))}
```

`InCad/incad/ui/ribbon_layout.py` — in the `part` layout change the View tab's Navigate group to
`["Navigate", ["view.zoom_all", "view.home", "view.look_at", "view.zoom_selection", "nav.orbit", "nav.pan"]]`.

`InCad/incad/ui/marking_layout.py`:
```python
"""Which commands the right-click marking menu shows, per context. Slots N…NW sit around the cursor (flick
directions); 'list' is the short list below the ring. Later plans move sketch/feature commands into the slots."""
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

_GEOMETRY = {"N": "view.look_at", "S": "view.zoom_selection", "E": "view.style_shaded", "W": "view.style_wireframe",
             "NW": "edit.undo", "NE": "edit.redo", "SW": "view.zoom_all", "SE": "view.home", "list": []}

LAYOUT = {
    "part": {"N": "view.home", "NE": "edit.redo", "E": "view.style_shaded", "SE": "view.parameters",
             "S": "view.zoom_all", "SW": "view.theme_toggle", "W": "view.style_wireframe", "NW": "edit.undo",
             "list": ["view.freecad"]},
    "face": dict(_GEOMETRY),
    "edge": dict(_GEOMETRY),
    "vertex": dict(_GEOMETRY),
    "empty": {"N": "file.new", "S": "file.open", "E": "view.theme_toggle", "W": "view.freecad", "list": []},
    "browser": {"N": "browser.edit", "S": "browser.move_end_of_part", "E": "browser.suppress",
                "W": "browser.rename", "list": []},
}


def resolve(context, registry, layout=None):
    """([(direction, Command)] in N…NW order, [Command] for the list); unknown command ids are skipped."""
    spec = (LAYOUT if layout is None else layout).get(context, {})
    slots = [(d, registry.get(spec[d])) for d in DIRECTIONS if spec.get(d) and registry.has(spec[d])]
    items = [registry.get(i) for i in spec.get("list", []) if registry.has(i)]
    return slots, items
```

`InCad/incad/actions.py` — add to `STD_COMMANDS`: `"view.look_at": "Std_AlignToSelection", "view.zoom_selection":
"Std_ViewFitSelection",` and add before `def _std(`:
```python
def _target_object():
    import FreeCAD as App
    from incad.core import context
    doc = App.ActiveDocument
    name = context.target()
    obj = doc.getObject(name) if doc is not None and name else None
    if obj is None:
        raise ValueError("Pick a feature in the Model Browser first")
    return obj


def toggle_suppress():
    obj = _target_object()
    if "Suppressed" not in obj.PropertiesList:
        raise ValueError("%s cannot be suppressed" % obj.Label)
    obj.Suppressed = not obj.Suppressed


def _ask_name(current):
    from incad.qt import QtWidgets
    text, ok = QtWidgets.QInputDialog.getText(_gui().getMainWindow(), "Rename", "New name:", text=current)
    return text.strip() if ok else ""


def rename(ask=None):
    obj = _target_object()
    name = (ask or _ask_name)(obj.Label)
    if name:
        obj.Label = name


def move_end_of_part_here():
    from incad.core import document
    obj = document.owning_feature(_target_object())
    body = obj.getParentGeoFeatureGroup()
    if body is None or body.TypeId != "PartDesign::Body":
        raise ValueError("%s is not part of a solid" % obj.Label)
    document.set_end_of_part(body, obj)


def edit_feature():
    from incad.core import log
    log.report("info", "Editing features arrives with the feature tools (plan 1d)")


def toggle_nav_mode(mode):
    from incad.ui import shell
    shell.toggle_nav_mode(mode)


def nav_mode_is(mode):
    from incad.ui import shell
    return shell.nav_mode() == mode
```
and add to the list returned by `commands()` (before the closing bracket):
```python
        _std("view.look_at", "Look At", "look_at"),
        _std("view.zoom_selection", "Zoom Selection", "zoom_selection"),
        Command(id="browser.edit", label="Edit", icon="edit", handler=edit_feature, contexts=frozenset({"browser"})),
        Command(id="browser.move_end_of_part", label="Move End of Part Here", icon="end_of_part",
                handler=move_end_of_part_here, transactional=True, contexts=frozenset({"browser"})),
        Command(id="browser.suppress", label="Suppress / Unsuppress", icon="suppress", handler=toggle_suppress,
                transactional=True, contexts=frozenset({"browser"})),
        Command(id="browser.rename", label="Rename", icon="rename", handler=rename, transactional=True,
                contexts=frozenset({"browser"})),
        Command(id="nav.orbit", label="Orbit", icon="orbit", handler=lambda: toggle_nav_mode("orbit"),
                checkable=True, is_checked=lambda: nav_mode_is("orbit"), tooltip="Left-drag orbits; click again to stop"),
        Command(id="nav.pan", label="Pan", icon="pan", handler=lambda: toggle_nav_mode("pan"),
                checkable=True, is_checked=lambda: nav_mode_is("pan"), tooltip="Left-drag pans; click again to stop"),
```

- [ ] **Step 4: Run to verify they pass**

Run the five commands from Step 2 and `tests/run_fast.sh` → Expected: all `OK`, `FAST SUITES PASSED`.
(Ribbon/marking-menu `is_checked` for nav tools calls `shell.nav_mode()`, added in Task 7; until then the ribbon
never evaluates it in tests because the shell is not built.)

- [ ] **Step 5: Commit**

```bash
git add tools InCad tests && git commit -m "InCad 1b: browser/view commands, icons, marking-menu layout, navigation pref"
```

---

### Task 2: Camera moves (orbit, pan)

**Files:**
- Create: `InCad/incad/core/camera.py`, `tests/widgets/test_camera.py`

**Interfaces:**
- Produces: `camera.ORBIT_RAD_PER_PX = 0.008`; `focal_point(cam) -> SbVec3f`; `orbit(cam, pivot, dx, dy, rad_per_px=…)`
  (pivot = 3-sequence or SbVec3f; dx/dy in Qt pixels, dy positive downward); `units_per_px(cam, viewport_height_px)`;
  `pan_pixels(cam, dx, dy, viewport_height_px)`. Dragging right/down turns or moves the model right/down.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_camera.py`:
```python
import math
import unittest

from pivy import coin
from incad.core import camera


def ortho(z=10.0):
    c = coin.SoOrthographicCamera()
    c.position.setValue(0, 0, z)
    c.orientation.setValue(coin.SbRotation())
    c.focalDistance.setValue(z)
    c.height.setValue(20)
    return c


def local(cam, p):
    rel = coin.SbVec3f(*p) - cam.position.getValue()
    return cam.orientation.getValue().inverse().multVec(rel)


class CameraTest(unittest.TestCase):
    def test_focal_point(self):
        p = camera.focal_point(ortho())
        self.assertAlmostEqual(p[2], 0, places=5)

    def test_drag_right_turns_model_right(self):
        c = ortho()
        camera.orbit(c, (0, 0, 0), 20, 0)
        self.assertLess(c.position.getValue()[0], 0)

    def test_drag_down_turns_model_down(self):
        c = ortho()
        camera.orbit(c, (0, 0, 0), 0, 20)
        self.assertGreater(c.position.getValue()[1], 0)

    def test_pivot_stays_put_on_screen_and_distance_kept(self):
        c = ortho()
        pivot = (3.0, 2.0, 1.0)
        before = local(c, pivot)
        dist = (c.position.getValue() - coin.SbVec3f(*pivot)).length()
        camera.orbit(c, pivot, 37, -18)
        after = local(c, pivot)
        for i in range(3):
            self.assertAlmostEqual(before[i], after[i], places=4)
        self.assertAlmostEqual((c.position.getValue() - coin.SbVec3f(*pivot)).length(), dist, places=4)

    def test_units_per_px(self):
        self.assertAlmostEqual(camera.units_per_px(ortho(), 200), 0.1)
        p = coin.SoPerspectiveCamera()
        p.focalDistance.setValue(10)
        p.heightAngle.setValue(math.pi / 4)
        self.assertAlmostEqual(camera.units_per_px(p, 100), 2 * 10 * math.tan(math.pi / 8) / 100, places=6)

    def test_pan_moves_model_with_the_mouse(self):
        c = ortho()
        camera.pan_pixels(c, 100, 0, 200)
        self.assertAlmostEqual(c.position.getValue()[0], -10, places=4)
        c = ortho()
        camera.pan_pixels(c, 0, 100, 200)
        self.assertAlmostEqual(c.position.getValue()[1], 10, places=4)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_camera.py` → Expected: `cannot import name 'camera'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/camera.py`:
```python
"""Camera moves for InCad's navigation on a Coin camera (pivy only, no FreeCAD): orbit about a point, pan."""
import math

from pivy import coin

ORBIT_RAD_PER_PX = 0.008


def _v(p):
    return coin.SbVec3f(float(p[0]), float(p[1]), float(p[2]))


def focal_point(cam):
    direction = cam.orientation.getValue().multVec(coin.SbVec3f(0, 0, -1))
    return cam.position.getValue() + direction * cam.focalDistance.getValue()


def orbit(cam, pivot, dx, dy, rad_per_px=ORBIT_RAD_PER_PX):
    """Inventor free orbit: dragging right/down turns the model right/down around `pivot` (a world point)."""
    rot = cam.orientation.getValue()
    up = rot.multVec(coin.SbVec3f(0, 1, 0))
    right = rot.multVec(coin.SbVec3f(1, 0, 0))
    turn = coin.SbRotation(up, -dx * rad_per_px) * coin.SbRotation(right, -dy * rad_per_px)
    p = _v(pivot)
    cam.position.setValue(p + turn.multVec(cam.position.getValue() - p))
    cam.orientation.setValue(rot * turn)


def units_per_px(cam, viewport_height_px):
    if cam.isOfType(coin.SoOrthographicCamera.getClassTypeId()):
        visible = cam.height.getValue()
    else:
        visible = 2 * cam.focalDistance.getValue() * math.tan(cam.heightAngle.getValue() / 2)
    return visible / max(1, viewport_height_px)


def pan_pixels(cam, dx, dy, viewport_height_px):
    """Dragging right/down moves the model right/down (the camera the opposite way)."""
    s = units_per_px(cam, viewport_height_px)
    rot = cam.orientation.getValue()
    right = rot.multVec(coin.SbVec3f(1, 0, 0))
    up = rot.multVec(coin.SbVec3f(0, 1, 0))
    cam.position.setValue(cam.position.getValue() - right * (dx * s) + up * (dy * s))
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_camera.py` → Expected: 6 tests `OK`. If the pivot test fails, Coin's `SbRotation`
product order is the other way round: use `turn * rot` for the orientation and re-run (the test is the judge).

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/camera.py tests/widgets/test_camera.py && git commit -m "InCad 1b: orbit and pan camera moves"
```

---

### Task 3: Gesture rules

**Files:**
- Create: `InCad/incad/core/gestures.py`, `tests/widgets/test_gestures.py`

**Interfaces:**
- Produces: `LEFT=1, RIGHT=2, MIDDLE=4`, `DRAG_PX=4`, `PASS=("pass",)`; class `Gestures` with `mode` (None/"orbit"/"pan"),
  `reset()`, `feed(kind, button, buttons, x, y) -> list[tuple]` (`buttons` = held after the event). Actions:
  `("pass",)`, `("replay_press", x, y)`, `("orbit_start", x, y)`, `("orbit", dx, dy)`, `("orbit_end",)`,
  `("pan_start", x, y)`, `("pan", dx, dy)`, `("pan_end",)`, `("menu", x, y)`, `("flick_start", x, y)`.
  An event whose actions lack `("pass",)` is consumed.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_gestures.py`:
```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_gestures.py` → Expected: `cannot import name 'gestures'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/gestures.py`:
```python
"""Turns mouse events on a 3D view into InCad navigation actions. Pure logic (no Qt, no FreeCAD).
Buttons: LEFT=1, RIGHT=2, MIDDLE=4; `buttons` is what is held after the event.

feed(kind, button, buttons, x, y) -> actions; kind is 'press' | 'release' | 'move' | 'dblclick'.
('pass',) lets FreeCAD have the event, otherwise it is consumed. ('replay_press', x, y) hands FreeCAD the left
press InCad held back. ('orbit_start', x, y) / ('orbit', dx, dy) / ('orbit_end',); ('pan_start', x, y) /
('pan', dx, dy) / ('pan_end',) for the navigation-strip Pan tool; ('menu', x, y) right-click;
('flick_start', x, y) right-drag — the marking menu takes the mouse from there."""
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
        return getattr(self, "_" + self.state)(kind, button, buttons, x, y)

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
            return [("replay_press",) + self.press, PASS]
        if kind == "release" and button == LEFT:
            press = self.press
            self.reset()
            return [("replay_press",) + press, PASS]
        return []

    def _passthrough(self, kind, button, buttons, x, y):
        if kind == "release" and buttons == 0:
            self.reset()
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_gestures.py` → Expected: 10 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/gestures.py tests/widgets/test_gestures.py && git commit -m "InCad 1b: gesture rules for 3D-view mouse events"
```

---

### Task 4: Marking menu widget

**Files:**
- Create: `InCad/incad/ui/marking_menu.py`, `tests/widgets/test_marking_menu.py`

**Interfaces:**
- Consumes: `marking_layout.DIRECTIONS`, `theme.icon/PALETTES`, `Registry.run`.
- Produces: `RADIUS = 92`, `DEAD_ZONE = 18`, `direction_for(dx, dy, dead_zone=DEAD_ZONE) -> str|None` (dy down);
  `MarkingMenu(registry, slots, items, theme="light", parent=None)` (a `Qt.Popup`): signal `triggered(str)`,
  `show_at(global_pos)`, `start_flick()`, `flick_move(global_pos)`, `flick_end(global_pos)`, `choose(cmd_id)`,
  `button(direction)`, `list_labels()`, `center_global()`, `hot_direction()`. Choosing closes the menu, emits
  `triggered`, then runs the command. Esc closes.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_marking_menu.py`:
```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_marking_menu.py` → Expected: `ModuleNotFoundError: No module named 'incad.ui.marking_menu'`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/marking_menu.py`:
```python
"""Inventor-style marking menu: up to 8 commands in a ring around the cursor plus a short list below it.
Right-click opens it for hover-and-click; a right-drag (flick) picks the slot in the drag direction on release."""
import math

from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes
from incad.ui.marking_layout import DIRECTIONS

RADIUS = 92
DEAD_ZONE = 18


def direction_for(dx, dy, dead_zone=DEAD_ZONE):
    """Screen vector (dy positive downward) -> 'N'…'NW', or None inside the dead zone."""
    if math.hypot(dx, dy) < dead_zone:
        return None
    angle = math.degrees(math.atan2(dx, -dy)) % 360
    return DIRECTIONS[int((angle + 22.5) // 45) % 8]


class MarkingMenu(QtWidgets.QWidget):
    triggered = Signal(str)

    def __init__(self, registry, slots, items, theme="light", parent=None):
        super().__init__(parent, QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint)
        self.setObjectName("InCadMarkingMenu")
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self._registry, self._theme = registry, theme
        self._buttons, self._slot_ids, self._list = {}, {}, []
        self._flick, self._flick_to, self._hot = False, None, None
        width = 2 * RADIUS + 220
        self._center = QtCore.QPoint(width // 2, RADIUS + 40)
        self.resize(width, self._center.y() + RADIUS + 50 + 30 * len(items))
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QToolButton {{ background: {panel}; color: {text}; border: 1px solid {border}; border-radius: 8px;"
            " padding: 4px 10px; }} QToolButton:hover, QToolButton[hot=\"true\"] {{ background: {accent};"
            " color: {selection_text}; }}".format(**p))
        for direction, cmd in slots:
            b = self._make_button(cmd)
            a = math.radians(DIRECTIONS.index(direction) * 45)
            x = self._center.x() + RADIUS * math.sin(a)
            y = self._center.y() - RADIUS * math.cos(a)
            b.move(int(x - b.width() / 2), int(y - b.height() / 2))
            self._buttons[direction] = b
            self._slot_ids[direction] = cmd.id
        y = self._center.y() + RADIUS + 34
        for cmd in items:
            b = self._make_button(cmd)
            b.setMinimumWidth(170)
            b.adjustSize()
            b.move(self._center.x() - b.width() // 2, y)
            y += b.height() + 2
            self._list.append(b)

    def _make_button(self, cmd):
        b = QtWidgets.QToolButton(self)
        b.setIcon(themes.icon(cmd.icon, self._theme))
        b.setIconSize(QtCore.QSize(20, 20))
        b.setText(cmd.label)
        b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        b.clicked.connect(lambda _=False, i=cmd.id: self.choose(i))
        b.adjustSize()
        return b

    # ----- public -----
    def show_at(self, global_pos):
        self.move(global_pos - self._center)
        self.show()
        self.raise_()

    def center_global(self):
        return self.mapToGlobal(self._center)

    def button(self, direction):
        return self._buttons.get(direction)

    def list_labels(self):
        return [b.text() for b in self._list]

    def hot_direction(self):
        return self._hot

    def choose(self, cmd_id):
        self.close()
        self.triggered.emit(cmd_id)
        self._registry.run(cmd_id)

    def start_flick(self):
        self._flick = True

    def flick_move(self, global_pos):
        d = global_pos - self.center_global()
        self._set_hot(direction_for(d.x(), d.y()))
        self._flick_to = self.mapFromGlobal(global_pos)
        self.update()

    def flick_end(self, global_pos):
        d = global_pos - self.center_global()
        cmd_id = self._slot_ids.get(direction_for(d.x(), d.y()))
        if cmd_id:
            self.choose(cmd_id)
        else:
            self.close()

    # ----- internals -----
    def _set_hot(self, direction):
        self._hot = direction if direction in self._buttons else None
        for d, b in self._buttons.items():
            b.setProperty("hot", d == self._hot)
            b.style().unpolish(b)
            b.style().polish(b)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pal = themes.PALETTES[self._theme]
        pen = QtGui.QPen(QtGui.QColor(pal["accent"]))
        pen.setWidth(2)
        painter.setPen(pen)
        fill = QtGui.QColor(pal["accent"])
        fill.setAlpha(40)
        painter.setBrush(fill)
        painter.drawEllipse(self._center, DEAD_ZONE, DEAD_ZONE)
        if self._flick_to is not None:
            painter.drawLine(self._center, self._flick_to)
        painter.end()

    def mouseMoveEvent(self, event):
        if self._flick:
            self.flick_move(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._flick and event.button() == QtCore.Qt.RightButton:
            self.flick_end(event.globalPosition().toPoint())
            return
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        self.close()  # a click on the empty area around the ring

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_marking_menu.py` → Expected: 7 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/marking_menu.py tests/widgets/test_marking_menu.py && git commit -m "InCad 1b: radial marking menu with flick"
```

---

### Task 5: Navigation strip widget

**Files:**
- Create: `InCad/incad/ui/nav_strip.py`, `tests/widgets/test_nav_strip.py`

**Interfaces:**
- Produces: `STRIP` (command ids), `NavStrip(registry, theme="light", parent=None)`: `button(cmd_id)`,
  `refresh_checks()`, `set_theme(theme)`, `place(area_rect)` (top-right of `area_rect`, below the ViewCube).

- [ ] **Step 1: Write the failing test**

`tests/widgets/test_nav_strip.py`:
```python
import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.core.commands import Command, Registry
from incad.ui.nav_strip import NavStrip


class NavStripTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.mode = None
        self.reg = Registry()
        self.reg.register(Command(id="view.zoom_all", label="Zoom All", icon="zoom_all",
                                  handler=lambda: self.ran.append("zoom")))
        self.reg.register(Command(id="nav.orbit", label="Orbit", icon="orbit", handler=self.toggle,
                                  checkable=True, is_checked=lambda: self.mode == "orbit"))
        self.strip = NavStrip(self.reg, "light")

    def toggle(self):
        self.mode = None if self.mode == "orbit" else "orbit"

    def test_only_registered_commands(self):
        self.assertIsNotNone(self.strip.button("view.zoom_all"))
        self.assertIsNone(self.strip.button("view.home"))

    def test_click_runs(self):
        self.strip.button("view.zoom_all").click()
        self.assertEqual(self.ran, ["zoom"])

    def test_checkable_follows_state(self):
        self.strip.button("nav.orbit").click()
        self.assertTrue(self.strip.button("nav.orbit").isChecked())
        self.strip.button("nav.orbit").click()
        self.assertFalse(self.strip.button("nav.orbit").isChecked())

    def test_place(self):
        self.strip.adjustSize()
        self.strip.place(QtCore.QRect(0, 0, 1000, 700))
        self.assertEqual(self.strip.x() + self.strip.width(), 1000 - 14)
        self.assertGreaterEqual(self.strip.y(), 140)
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_widgets.sh test_nav_strip.py` → Expected: `ModuleNotFoundError: No module named 'incad.ui.nav_strip'`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/nav_strip.py`:
```python
"""Navigation strip floating at the right edge of the 3D view, below the ViewCube (Inventor's navigation bar)."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes

STRIP = ("view.zoom_all", "view.home", "view.look_at", "nav.orbit", "nav.pan", "view.style_shaded",
         "view.style_wireframe")


class NavStrip(QtWidgets.QFrame):
    def __init__(self, registry, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadNavStrip")
        self._registry = registry
        self._buttons = {}
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(4, 4, 4, 4)
        col.setSpacing(2)
        for cmd_id in STRIP:
            if not registry.has(cmd_id):
                continue
            cmd = registry.get(cmd_id)
            b = QtWidgets.QToolButton(self)
            b.setIconSize(QtCore.QSize(20, 20))
            b.setToolTip(cmd.label + ("\n" + cmd.tooltip if cmd.tooltip else ""))
            b.setAutoRaise(True)
            b.setCheckable(cmd.checkable)
            b.clicked.connect(lambda _=False, i=cmd_id: self._run(i))
            col.addWidget(b)
            self._buttons[cmd_id] = b
        self.set_theme(theme)

    def button(self, cmd_id):
        return self._buttons.get(cmd_id)

    def _run(self, cmd_id):
        self._registry.run(cmd_id)
        self.refresh_checks()

    def refresh_checks(self):
        for cmd_id, b in self._buttons.items():
            cmd = self._registry.get(cmd_id)
            if cmd.checkable:
                b.setChecked(bool(cmd.is_checked and cmd.is_checked()))

    def set_theme(self, theme):
        p = themes.PALETTES[theme]
        for cmd_id, b in self._buttons.items():
            b.setIcon(themes.icon(self._registry.get(cmd_id).icon, theme))
        self.setStyleSheet(
            "QFrame#InCadNavStrip {{ background: {panel}; border: 1px solid {border}; border-radius: 8px; }}"
            " QToolButton {{ border: none; border-radius: 5px; padding: 3px; }}"
            " QToolButton:hover, QToolButton:checked {{ background: {accent_soft}; }}".format(**p))

    def place(self, area_rect):
        self.adjustSize()
        self.move(area_rect.right() + 1 - self.width() - 14, area_rect.top() + 150)
        self.raise_()
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_widgets.sh test_nav_strip.py` → Expected: 4 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/nav_strip.py tests/widgets/test_nav_strip.py && git commit -m "InCad 1b: navigation strip widget"
```

---

### Task 6: Browser right-click asks for the marking menu

**Files:**
- Modify: `InCad/incad/ui/browser.py`, `tests/widgets/test_browser.py`

**Interfaces:**
- Produces: `ModelBrowser.markingMenuRequested(str name, QPoint global_pos)` emitted on right-click on a feature or
  sketch row (and that row becomes current); `context_actions()` and the QMenu are removed.

- [ ] **Step 1: Change the tests**

In `tests/widgets/test_browser.py` replace `test_context_actions` with:
```python
    def test_right_click_requests_marking_menu(self):
        seen = []
        self.b.markingMenuRequested.connect(lambda name, pos: seen.append(name))
        self.b.resize(260, 500)
        self.b.show()
        qtapp.app().processEvents()
        for label in ("Fillet1", "Origin"):
            rect = self.b.tree.visualItemRect(self.b.item_by_label(label))
            self.b._on_context_menu(rect.center())
        self.b.hide()
        self.assertEqual(seen, ["Fillet"])
        self.assertEqual(self.b.tree.currentItem().text(0), "Fillet1")
```
and in `MultiSolidTest` delete the line
`dict(b.context_actions(b.item_by_label("Pad001")))["Move End of Part Here"]()` and change its expected list to
`["Pad001", "Pad001"]`.

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_widgets.sh test_browser.py` → Expected: `AttributeError: … 'markingMenuRequested'`.

- [ ] **Step 3: Implement**

In `InCad/incad/ui/browser.py`: add the signal `markingMenuRequested = Signal(str, QtCore.QPoint)` next to the other
signals, delete the `context_actions` method, and replace `_on_context_menu` with:
```python
    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None or item.data(0, KIND_ROLE) not in ("feature", "sketch"):
            return
        self.tree.setCurrentItem(item)
        self.markingMenuRequested.emit(item.data(0, NAME_ROLE), self.tree.viewport().mapToGlobal(pos))
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_widgets.sh test_browser.py` → Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/browser.py tests/widgets/test_browser.py && git commit -m "InCad 1b: browser right-click requests the marking menu"
```

---

### Task 7: Navigator and shell wiring

**Files:**
- Create: `InCad/incad/ui/nav.py`, `tests/gui/test_nav.py`
- Modify: `InCad/incad/ui/shell.py`

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces (`incad.ui.nav`): `to_coin(viewport, x, y) -> (int, int)`; `Navigator(open_menu, on_mode_changed=None,
  parent=None)` with `attach_all()`, `detach_all()`, `attached() -> list`, `set_mode(mode)`, `mode`;
  `open_menu(view, viewport, local QPointF, global QPoint, flick: bool)`.
- Produces (`incad.ui.shell`): `Shell.navigator`, `Shell.strip`, `Shell.menu_kind`, `Shell.marking_menu`,
  `Shell.set_navigation(enabled)`; module `toggle_nav_mode(mode)`, `nav_mode() -> str|None`.

- [ ] **Step 1: Write the failing GUI tests**

`tests/gui/test_nav.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401  (getCameraNode needs pivy loaded)
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, context, document, params, prefs  # noqa: E402
from incad.ui import shell, theme  # noqa: E402
from incad.ui.marking_menu import MarkingMenu  # noqa: E402

mw = Gui.getMainWindow()
L, R = QtCore.Qt.LeftButton, QtCore.Qt.RightButton
BASE = {}
NAV_KEYS = {"NavigationStyle": "String", "ZoomAtCursor": "Bool"}


def view():
    return Gui.ActiveDocument.ActiveView


def vp():
    return view().graphicsView().viewport()


def s():
    return shell.instance()


def qt_pos_of(point):
    x, y = view().getPointOnScreen(App.Vector(*point))
    dpr = vp().devicePixelRatioF()
    return QtCore.QPointF(x / dpr, vp().height() - y / dpr)


def empty_pos():
    return QtCore.QPointF(vp().width() * 0.2, vp().height() * 0.8)


def send(kind, pos, button, buttons, target=None):
    target = target or vp()
    types = {"press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease,
             "move": QtCore.QEvent.MouseMove}
    glob = QtCore.QPointF(target.mapToGlobal(pos.toPoint()))
    ev = QtGui.QMouseEvent(types[kind], pos, glob, button, buttons, QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(target, ev)
    harness.pump(40)


def close_menu():
    m = s().marking_menu
    if m is not None and m.isVisible():
        m.close()
    harness.pump(100)


def nav_params():
    return (params.snapshot(theme.VIEW_GROUP, NAV_KEYS), params.snapshot(theme.NAVICUBE_GROUP, theme.NAVICUBE_KEYS))


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    BASE["params"] = nav_params()
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = App.ActiveDocument.addObject("Part::Box", "Box")
    App.ActiveDocument.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(800)
    assert box.Shape.isValid()


def test_1_navigation_installed():
    assert vp() in s().navigator.attached()
    assert view().getNavigationType() == "Gui::CADNavigationStyle", view().getNavigationType()
    assert App.ParamGet(theme.VIEW_GROUP).GetBool("ZoomAtCursor", False)


def test_2_left_click_still_selects():
    Gui.Selection.clearSelection()
    p = qt_pos_of((5, 5, 10))
    send("press", p, L, L)
    send("release", p, L, QtCore.Qt.NoButton)
    names = [o.ObjectName for o in Gui.Selection.getSelectionEx()]
    assert names == ["Box"], names


def test_3_left_right_drag_orbits_without_selecting():
    Gui.Selection.clearSelection()
    before = view().getCameraOrientation()
    p = qt_pos_of((5, 5, 10))
    pivot_before = view().getPointOnScreen(App.Vector(5, 5, 10))
    send("press", p, L, L)
    send("press", p, R, L | R)
    for i in range(1, 5):
        send("move", p + QtCore.QPointF(10 * i, 0), QtCore.Qt.NoButton, L | R)
    send("release", p + QtCore.QPointF(40, 0), L, R)
    send("release", p + QtCore.QPointF(40, 0), R, QtCore.Qt.NoButton)
    after = view().getCameraOrientation()
    assert not after.isSame(before, 1e-4), "camera did not orbit"
    pivot_after = view().getPointOnScreen(App.Vector(5, 5, 10))
    assert abs(pivot_after[0] - pivot_before[0]) < 6 and abs(pivot_after[1] - pivot_before[1]) < 6, (pivot_before, pivot_after)
    assert Gui.Selection.getSelectionEx() == [], "an orbit must not select"
    assert s().marking_menu is None or not s().marking_menu.isVisible()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(300)


def test_4_right_click_on_face():
    Gui.Selection.clearSelection()
    p = qt_pos_of((5, 5, 10))
    send("press", p, R, R)
    send("release", p, R, QtCore.Qt.NoButton)
    harness.pump(200)
    assert isinstance(QtWidgets.QApplication.activePopupWidget(), MarkingMenu), QtWidgets.QApplication.activePopupWidget()
    assert s().menu_kind == "face", s().menu_kind
    assert [o.ObjectName for o in Gui.Selection.getSelectionEx()] == ["Box"]
    close_menu()


def test_5_right_click_on_empty_space():
    send("press", empty_pos(), R, R)
    send("release", empty_pos(), R, QtCore.Qt.NoButton)
    harness.pump(200)
    assert s().menu_kind == "part", s().menu_kind
    assert isinstance(QtWidgets.QApplication.activePopupWidget(), MarkingMenu)
    close_menu()


def test_6_flick_north_runs_home_view():
    ran = []
    original = commands.REGISTRY.run
    commands.REGISTRY.run = lambda i: (ran.append(i), original(i))[1]
    try:
        p = empty_pos()
        send("press", p, R, R)
        send("move", p + QtCore.QPointF(0, -10), QtCore.Qt.NoButton, R)
        harness.pump(200)
        menu = s().marking_menu
        assert menu is not None and menu.isVisible(), "flick did not open the menu"
        end = menu.mapFromGlobal(menu.center_global() + QtCore.QPoint(0, -70))
        send("move", QtCore.QPointF(end), QtCore.Qt.NoButton, R, target=menu)
        send("release", QtCore.QPointF(end), R, QtCore.Qt.NoButton, target=menu)
        harness.pump(300)
    finally:
        commands.REGISTRY.run = original
    assert ran == ["view.home"], ran


def test_7_browser_marking_menu_suppress():
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    import headless.util as util
    sketch = util.add_rect_sketch(body)
    pad = util.add_pad(body, sketch, 5)
    doc.recompute()
    harness.pump(500)
    s().browser.markingMenuRequested.emit(pad.Name, QtCore.QPoint(400, 400))
    harness.pump(200)
    assert s().menu_kind == "browser" and context.target() == pad.Name
    s().marking_menu.choose("browser.suppress")
    harness.pump(400)
    assert pad.Suppressed
    s().browser.markingMenuRequested.emit(pad.Name, QtCore.QPoint(400, 400))
    harness.pump(200)
    s().marking_menu.choose("browser.suppress")
    harness.pump(400)
    assert not pad.Suppressed


def test_8_strip_orbit_tool():
    strip = s().strip
    assert strip is not None and not strip.isHidden()
    strip.button("nav.orbit").click()
    assert shell.nav_mode() == "orbit" and strip.button("nav.orbit").isChecked()
    before = view().getCameraOrientation()
    p = empty_pos()
    send("press", p, L, L)
    send("move", p + QtCore.QPointF(30, 10), QtCore.Qt.NoButton, L)
    send("release", p + QtCore.QPointF(30, 10), L, QtCore.Qt.NoButton)
    assert not view().getCameraOrientation().isSame(before, 1e-4)
    strip.button("nav.orbit").click()
    assert shell.nav_mode() is None and not strip.button("nav.orbit").isChecked()


def test_9_navicube_follows_theme():
    got = App.ParamGet(theme.NAVICUBE_GROUP).GetUnsigned("BaseColor")
    assert got == theme.navicube_params(s().theme)["BaseColor"][1], hex(got)


def test_10_navigation_off_and_on():
    s().set_navigation(False)
    assert s().navigator.attached() == [] and not prefs.navigation_enabled()
    s().set_navigation(True)
    assert vp() in s().navigator.attached()


def test_11_leaving_incad_restores_navigation():
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert nav_params() == BASE["params"], (nav_params(), BASE["params"])
    assert s().navigator is None or s().navigator.attached() == []


harness.run([test_0_setup, test_1_navigation_installed, test_2_left_click_still_selects,
             test_3_left_right_drag_orbits_without_selecting, test_4_right_click_on_face,
             test_5_right_click_on_empty_space, test_6_flick_north_runs_home_view, test_7_browser_marking_menu_suppress,
             test_8_strip_orbit_tool, test_9_navicube_follows_theme, test_10_navigation_off_and_on,
             test_11_leaving_incad_restores_navigation])
```

- [ ] **Step 2: Run to verify they fail**

Announce the FreeCAD window. Run: `tests/run_gui.sh tests/gui/test_nav.py`
Expected: `test_1` fails (`'Shell' object has no attribute 'navigator'`) and later tests fail.

- [ ] **Step 3: Implement the navigator**

`InCad/incad/ui/nav.py`:
```python
"""InCad mouse navigation on FreeCAD's 3D views (rules in incad.core.gestures): LMB+RMB drag orbits around the
point under the cursor, right-click opens the marking menu, right-drag flicks it, left clicks still select.
Middle-drag pan and wheel zoom stay FreeCAD's own (the shell sets the CAD style with zoom-at-cursor)."""
from incad.core import camera, gestures, log
from incad.qt import QtCore, QtGui, QtWidgets

QT_BUTTONS = ((QtCore.Qt.LeftButton, gestures.LEFT), (QtCore.Qt.RightButton, gestures.RIGHT),
              (QtCore.Qt.MiddleButton, gestures.MIDDLE))
KINDS = {QtCore.QEvent.MouseButtonPress: "press", QtCore.QEvent.MouseButtonRelease: "release",
         QtCore.QEvent.MouseMove: "move", QtCore.QEvent.MouseButtonDblClick: "dblclick"}


def to_coin(viewport, x, y):
    """Qt viewport position (logical px, top-left origin) -> Coin position (device px, bottom-left origin)."""
    dpr = viewport.devicePixelRatioF()
    return (int(round(x * dpr)), int(round((viewport.height() - y) * dpr)))


def _button(qt_button):
    for q, g in QT_BUTTONS:
        if qt_button == q:
            return g
    return 0


def _held(qt_buttons):
    held = 0
    for q, g in QT_BUTTONS:
        if qt_buttons & q:
            held |= g
    return held


class Navigator(QtCore.QObject):
    def __init__(self, open_menu, on_mode_changed=None, parent=None):
        super().__init__(parent)
        self._open_menu = open_menu
        self._on_mode_changed = on_mode_changed
        self._attached = {}  # viewport -> [view, Gestures]
        self._replaying = False
        self._pivot = None
        self.mode = None

    def attached(self):
        return list(self._attached)

    def attach_all(self):
        import FreeCAD as App
        import FreeCADGui as Gui
        for name in App.listDocuments():
            gdoc = Gui.getDocument(name)
            if gdoc is None:
                continue
            for view in gdoc.mdiViewsOfType("Gui::View3DInventor"):
                try:
                    viewport = view.graphicsView().viewport()
                except Exception:
                    continue
                if viewport in self._attached:
                    continue
                machine = gestures.Gestures()
                machine.mode = self.mode
                self._attached[viewport] = [view, machine]
                viewport.installEventFilter(self)
                viewport.destroyed.connect(lambda _=None, v=viewport: self._attached.pop(v, None))

    def detach_all(self):
        for viewport in list(self._attached):
            try:
                viewport.removeEventFilter(self)
            except RuntimeError:
                pass
        self._attached.clear()

    def set_mode(self, mode):
        self.mode = mode
        for entry in self._attached.values():
            entry[1].mode = mode
            entry[1].reset()
        if self._on_mode_changed is not None:
            self._on_mode_changed(mode)

    def eventFilter(self, obj, event):
        if self._replaying:
            return False
        entry = self._attached.get(obj)
        kind = KINDS.get(event.type())
        if entry is None or kind is None:
            return False
        view, machine = entry
        try:
            pos = event.position()
            actions = machine.feed(kind, _button(event.button()), _held(event.buttons()), pos.x(), pos.y())
            for action in actions:
                self._do(obj, view, action, event)
            return gestures.PASS not in actions
        except Exception:
            log.logger().exception("InCad navigation")
            machine.reset()
            return False

    def _do(self, viewport, view, action, event):
        name = action[0]
        if name == "replay_press":
            self._replay(viewport, action[1], action[2], event)
        elif name == "orbit_start":
            self._pivot = self._pivot_at(view, viewport, action[1], action[2])
        elif name == "orbit":
            cam = view.getCameraNode()
            camera.orbit(cam, self._pivot if self._pivot is not None else camera.focal_point(cam), action[1], action[2])
        elif name == "orbit_end":
            self._pivot = None
        elif name == "pan":
            camera.pan_pixels(view.getCameraNode(), action[1], action[2], viewport.height())
        elif name in ("menu", "flick_start"):
            local = QtCore.QPointF(action[1], action[2])
            self._open_menu(view, viewport, local, viewport.mapToGlobal(local.toPoint()), name == "flick_start")

    def _replay(self, viewport, x, y, event):
        local = QtCore.QPointF(x, y)
        press = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, local,
                                  QtCore.QPointF(viewport.mapToGlobal(local.toPoint())),
                                  QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, event.modifiers())
        self._replaying = True
        try:
            QtWidgets.QApplication.sendEvent(viewport, press)
        finally:
            self._replaying = False

    @staticmethod
    def _pivot_at(view, viewport, x, y):
        info = view.getObjectInfo(to_coin(viewport, x, y))
        if info:
            return (info["x"], info["y"], info["z"])
        return None
```

- [ ] **Step 4: Wire it into the shell**

In `InCad/incad/ui/shell.py`:

1. Imports — add:
```python
from incad.ui import marking_layout
from incad.ui.marking_menu import MarkingMenu
from incad.ui.nav import Navigator, to_coin
from incad.ui.nav_strip import NavStrip
```
and constants below `TOOLBAR_GROUP`:
```python
NAV_KEYS = {"NavigationStyle": "String", "ZoomAtCursor": "Bool"}
NAV_VALUES = {"NavigationStyle": ("String", "Gui::CADNavigationStyle"), "ZoomAtCursor": ("Bool", True)}
```
2. `__init__` — add `self.navigator = None`, `self.strip = None`, `self.marking_menu = None`, `self.menu_kind = None`.
3. `_capture()` — add entries
`"nav": params.snapshot(themes.VIEW_GROUP, NAV_KEYS),` and
`"navicube": params.snapshot(themes.NAVICUBE_GROUP, themes.NAVICUBE_KEYS),`.
4. `_restore()` — add steps after the "3D view colors" step:
```python
            ("navigation", lambda: params.restore(themes.VIEW_GROUP, snap["nav"]) if "nav" in snap else None),
            ("ViewCube colors", lambda: params.restore(themes.NAVICUBE_GROUP, snap["navicube"])
             if "navicube" in snap else None),
```
5. End of `_build()` — add:
```python
        self.navigator = Navigator(self._open_marking_menu, self._on_nav_mode_changed, self)
        self.browser.markingMenuRequested.connect(self._on_browser_marking_menu)
        mdi = self._mdi()
        if mdi is not None:
            self.strip = NavStrip(self.registry, self.theme, mdi.viewport())
            self.strip.place(mdi.viewport().rect())
            self.strip.show()
```
6. `_teardown()` — before `self._widgets = []` add:
```python
        if self.marking_menu is not None:
            try:
                self.marking_menu.close()
            except RuntimeError:
                pass
            self.marking_menu = None
        if self.navigator is not None:
            self.navigator.detach_all()
            self.navigator = None
        if self.strip is not None:
            try:
                self.strip.deleteLater()
            except RuntimeError:
                pass
            self.strip = None
```
7. `_install_hooks()` — add at the end:
```python
        from incad.core import params
        params.write(themes.VIEW_GROUP, NAV_VALUES)
        mdi = self._mdi()
        if mdi is not None:
            mdi.viewport().installEventFilter(self)
        if prefs.navigation_enabled():
            self.navigator.attach_all()
```
8. `_remove_hooks()` — add at the start:
```python
        mdi = self._mdi()
        if mdi is not None:
            try:
                mdi.viewport().removeEventFilter(self)
            except RuntimeError:
                pass
        if self.navigator is not None:
            self.navigator.detach_all()
```
9. `apply_theme()` — before `params.write(themes.VIEW_GROUP, …)` add:
```python
        if self.strip is not None:
            self.strip.set_theme(self.theme)
        params.write(themes.NAVICUBE_GROUP, themes.navicube_params(self.theme))
```
10. `eventFilter()` — at the top of the `try:` block add:
```python
            mdi = self._mdi()
            if self.strip is not None and mdi is not None and obj is mdi.viewport() \
                    and event.type() == QtCore.QEvent.Resize:
                self.strip.place(mdi.viewport().rect())
                return False
```
11. End of `_refresh()` — add:
```python
        if self.navigator is not None and prefs.navigation_enabled():
            self.navigator.attach_all()
        if self.strip is not None:
            self.strip.refresh_checks()
```
12. `_settings_menu()` — before `return menu` add:
```python
        nav_act = menu.addAction("Mouse Navigation (LMB+RMB orbit, right-click menu)")
        nav_act.setCheckable(True)
        nav_act.setChecked(prefs.navigation_enabled())
        nav_act.triggered.connect(lambda checked: self.set_navigation(checked))
```
13. New methods in `Shell`:
```python
    def set_navigation(self, enabled):
        prefs.set_navigation_enabled(enabled)
        if self.navigator is None:
            return
        if enabled:
            self.navigator.attach_all()
        else:
            self.navigator.set_mode(None)
            self.navigator.detach_all()

    def _on_nav_mode_changed(self, mode):
        if self.strip is not None:
            self.strip.refresh_checks()
        if self.status is not None:
            hints = {"orbit": "Orbit: drag with the left button (click Orbit again to stop)",
                     "pan": "Pan: drag with the left button (click Pan again to stop)"}
            self.status.set_prompt(hints.get(mode, "Ready"))

    def _show_marking_menu(self, kind, global_pos, flick=False):
        slots, items = marking_layout.resolve(kind, self.registry)
        if not slots and not items:
            return None
        if self.marking_menu is not None:
            try:
                self.marking_menu.close()
            except RuntimeError:
                pass
        menu = MarkingMenu(self.registry, slots, items, self.theme, self.mw)
        menu.destroyed.connect(lambda _=None: setattr(self, "marking_menu", None))
        self.marking_menu, self.menu_kind = menu, kind
        menu.show_at(global_pos)
        if flick:
            menu.start_flick()
        return menu

    def _open_marking_menu(self, view, viewport, local, global_pos, flick):
        import FreeCAD as App
        import FreeCADGui as Gui
        from incad.core import context, document
        doc = App.ActiveDocument
        info = view.getObjectInfo(to_coin(viewport, local.x(), local.y())) if doc is not None else None
        context.set_target(None)
        if info:
            comp = info.get("Component", "")
            kind = "edge" if comp.startswith("Edge") else "vertex" if comp.startswith("Vertex") else "face"
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(info["Document"], info["Object"], comp)
        else:
            kind = "part" if document.is_incad_part(doc) else "empty"
        return self._show_marking_menu(kind, global_pos, flick)

    def _on_browser_marking_menu(self, name, global_pos):
        from incad.core import context
        context.set_target(name)
        self._show_marking_menu("browser", global_pos)
```
14. Module functions at the end:
```python
def toggle_nav_mode(mode):
    if _shell is not None and _shell.active and _shell.navigator is not None:
        _shell.navigator.set_mode(None if _shell.navigator.mode == mode else mode)


def nav_mode():
    if _shell is not None and _shell.active and _shell.navigator is not None:
        return _shell.navigator.mode
    return None
```

- [ ] **Step 5: Run the GUI tests until they pass**

Announce the FreeCAD window. Run: `tests/run_gui.sh tests/gui/test_nav.py` → Expected: `12 passed, 0 failed`.
If `test_4`/`test_2` miss the box, `to_coin` has the wrong origin or scale: compare
`view().getObjectInfo(to_coin(vp(), p.x(), p.y()))` with `view().getPointOnScreen(...)` in a probe and fix `to_coin`
(the tests stay as they are).

- [ ] **Step 6: Run every suite**

Run: `tests/run_all.sh` → Expected: `ALL SUITES PASSED`.

- [ ] **Step 7: Commit**

```bash
git add InCad tests && git commit -m "InCad 1b: LMB+RMB orbit, marking menu in view and browser, navigation strip, ViewCube colors"
```

---

### Task 8: Look check, docs

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Screenshots**

With a probe script (not committed) in a throwaway FreeCAD: open an InCad part with a box, open the marking menu on
a face and on empty space, grab `mw` and `View.saveImage` in light and dark; look at them. Fix anything that looks
wrong (overlap with the ViewCube, unreadable labels, clipped ring) with a widget test first.

- [ ] **Step 2: Docs**

README.md — add a section:
```markdown
## Mouse
- Left click: select. Left + right button drag: orbit around the point under the cursor.
- Middle drag: pan. Wheel: zoom at the cursor.
- Right click: marking menu (also in the Model Browser). Right drag: flick a marking-menu command.
- ⚙ → Mouse Navigation switches InCad's mouse handling off (FreeCAD's own navigation then applies).
```
CLAUDE.md — add one bullet:
```markdown
- 1b facts: `view.getCameraNode()` needs `from pivy import coin` first; Coin pixel positions are device px with a
  bottom-left origin (`incad.ui.nav.to_coin`); FreeCAD opens its 3D context menu on the right-button release, so
  InCad's gesture rules never pass a lone right release.
```

- [ ] **Step 3: Full run and commit**

Run: `tests/run_all.sh` → Expected: `ALL SUITES PASSED`.
```bash
git add README.md CLAUDE.md && git commit -m "InCad 1b: README mouse section, CLAUDE.md navigation facts"
```
