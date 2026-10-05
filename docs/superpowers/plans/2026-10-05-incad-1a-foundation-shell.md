# InCad 1a — Foundation + Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FreeCAD 1.1.3 workbench "InCad" that installs from the repo, takes over FreeCAD's whole UI with an
Inventor-style title strip, ribbon, Model Browser (with Parameters) and status bar, creates InCad Parts (mm/in),
switches light/dark and ribbon size in one click, returns to native FreeCAD with one click, and never leaves
FreeCAD's UI or a model in a broken state.

**Architecture:** Pure-Python FreeCAD module in `InCad/` (symlinked into FreeCAD's Mod folder). `incad/core`
holds model logic with no Qt (document, safe guard, commands, prefs, tree); `incad/ui` holds PySide widgets
that never import FreeCAD (so they are tested offscreen with plain PySide6) plus `shell.py`, the only UI module
that talks to FreeCAD's main window. Native FreeCAD objects underneath: a hidden `PartDesign::Body`, `doc.Meta`
markers, an `App::VarSet` for parameters.

**Tech Stack:** FreeCAD 1.1.3 (`/Applications/FreeCAD.app`), its bundled Python and PySide6 6.8.3 (Qt 6.8.3),
`unittest` (no pytest in the bundle), zsh scripts.

**Spec:** `docs/superpowers/specs/2026-10-05-incad-stage1-design.md` (this plan = stage 1, part a: §3 Architecture,
§4 Interface shell, §7 Stability, §8 Testing). Later plans: 1b navigation + marking menu, 1c sketch workflow
(starts with the dynamic-input prototype), 1d part features.

## Global Constraints

- FreeCAD 1.1.3 only; module root `InCad/`, Python package `incad`; installed by symlink
  `~/Library/Application Support/FreeCAD/v1-1/Mod/InCad → /Volumes/Docs/InCad/InCad`.
- Files stay standard `.FCStd` and must open and edit in plain FreeCAD.
- UI text in English. macOS only (Qt shows `Ctrl+…` shortcuts as ⌘).
- No third-party dependencies; only what FreeCAD's bundle ships.
- Qt imports only through `incad.qt` (`from PySide import …` inside FreeCAD, `PySide6` in widget tests).
- `incad/ui/*` widgets must not import FreeCAD at module level (`shell.py` and `new_dialog`'s caller excepted).
- Every model-changing action goes through `incad.core.safe.run_safely`; headless documents start with
  `UndoMode == 0`, so `run_safely` must switch it to 1 or rollback silently does nothing.
- Tests never touch the user's FreeCAD settings: every FreeCAD run uses `-u <temp>/user.cfg`.
- Ribbon sizes: Small 16 px (no labels) / Medium 24 px / Large 32 px (default). Theme: auto (follows macOS) /
  light / dark. Units: `mm` → `Standard (mm, kg, s, °)`, `in` → `Imperial decimal (in, lb)`.
- Say when a GUI test run starts (a FreeCAD window appears; mouse/keyboard off-limits) and when it ends.

## Review Focus

1. Quitting FreeCAD, or FreeCAD crashing, while InCad is active → on the next run and on leaving InCad,
   FreeCAD's toolbars/docks/menus/status bar/3D colors/⌘N are exactly as before (Task 13 tests 5–7).
2. Opening a plain FreeCAD file while InCad is active → the browser says "Not an InCad part" and offers
   Convert / Open in FreeCAD, no exception (Task 10 test, Task 13 GUI test_4).
3. Several documents open: switching tabs updates browser, units and ribbon; closing the last one leaves an
   empty, working InCad (Task 13 GUI test_2, test_8).
4. Bad parameter input — invalid names, unknown names in formulas, circular formulas → readable error, model
   unchanged (Task 5 tests, Task 13 GUI test_3).
5. A failed command followed by Undo/Redo → no transaction left open, undo history intact (Task 3 test, Task 13
   GUI test_7).

## File Map

```
InCad/Init.py                      headless init (empty)
InCad/InitGui.py                   workbench class, startup hooks
InCad/incad/__init__.py            version
InCad/incad/qt.py                  Qt import shim
InCad/incad/actions.py             stage-1a commands + register_all()
InCad/incad/core/log.py            log file + user-facing reporter
InCad/incad/core/prefs.py          InCad preferences
InCad/incad/core/params.py         snapshot/write/restore FreeCAD parameters
InCad/incad/core/safe.py           safe command guard
InCad/incad/core/document.py       InCad Part, units, bodies, End of Part, parameters
InCad/incad/core/commands.py       command registry
InCad/incad/core/nodes.py          browser tree node data
InCad/incad/core/tree.py           document → nodes
InCad/incad/ui/theme.py            palettes, stylesheet, icons, view colors
InCad/incad/ui/ribbon_layout.py    which commands go on which tab/group
InCad/incad/ui/ribbon.py           ribbon widget
InCad/incad/ui/titlebar.py         title strip widget
InCad/incad/ui/statusbar.py        status bar widget
InCad/incad/ui/browser.py          Model Browser + Parameters widget
InCad/incad/ui/new_dialog.py       New: Part/Assembly + mm/in
InCad/incad/ui/shell.py            takeover / restore
InCad/incad/resources/icons/{light,dark}/*.svg   generated by tools/make_icons.py
tools/make_icons.py                icon generator
scripts/install.sh                 symlink into FreeCAD's Mod folder
tests/run_headless.sh, tests/headless_main.py, tests/headless/*.py      freecadcmd tests
tests/run_widgets.sh, tests/widgets/*.py                                offscreen PySide6 tests
tests/run_gui.sh, tests/gui/harness.py, tests/gui/test_*.py              real FreeCAD window tests
tests/run_all.sh
CLAUDE.md, README.md
```

---

### Task 1: Scaffold, test runners, install, empty workbench

**Files:**
- Create: `InCad/Init.py`, `InCad/InitGui.py`, `InCad/incad/__init__.py`, `InCad/incad/qt.py`,
  `InCad/incad/core/__init__.py`, `InCad/incad/ui/__init__.py`, `InCad/incad/resources/icons/light/incad.svg`,
  `InCad/incad/resources/icons/dark/incad.svg`
- Create: `scripts/install.sh`, `tests/run_headless.sh`, `tests/headless_main.py`, `tests/headless/__init__.py`,
  `tests/headless/test_smoke.py`, `tests/run_widgets.sh`, `tests/widgets/__init__.py`, `tests/widgets/qtapp.py`,
  `tests/widgets/test_smoke.py`, `tests/run_gui.sh`, `tests/gui/harness.py`, `tests/gui/test_smoke.py`,
  `tests/run_all.sh`, `CLAUDE.md`

**Interfaces:**
- Produces: `import incad` (`incad.__version__ == "0.1.0"`); `from incad.qt import QtCore, QtGui, QtWidgets, QAction, Signal`;
  workbench registered as `"InCadWorkbench"`; `tests/gui/harness.py`: `pump(ms=150)`, `run(tests, delay_ms=2000)`;
  `tests/widgets/qtapp.py`: `app()`; runners `tests/run_headless.sh [pattern]`, `tests/run_widgets.sh [pattern]`,
  `tests/run_gui.sh [files…]`, `tests/run_all.sh`.

- [ ] **Step 1: Write the module skeleton**

`InCad/Init.py`:
```python
# InCad: Inventor-style part and assembly modeling for FreeCAD. Nothing to set up for headless use.
```

`InCad/incad/__init__.py`:
```python
"""InCad: an Inventor/Alibre-style workbench for FreeCAD."""
__version__ = "0.1.0"
```

`InCad/incad/core/__init__.py` and `InCad/incad/ui/__init__.py`: empty files.

`InCad/incad/qt.py`:
```python
"""Qt imports for InCad: FreeCAD's PySide shim inside FreeCAD, plain PySide6 in widget tests."""
try:
    from PySide import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction
Signal = QtCore.Signal
```

`InCad/InitGui.py`:
```python
import FreeCADGui as Gui


class InCadWorkbench(Gui.Workbench):
    """Inventor/Alibre-style modeling. The whole UI is built by incad.ui.shell when the workbench activates."""

    MenuText = "InCad"
    ToolTip = "Inventor-style part and assembly modeling"

    def __init__(self):
        import os
        import incad
        self.__class__.Icon = os.path.join(os.path.dirname(incad.__file__), "resources", "icons", "light", "incad.svg")

    def Initialize(self):
        pass

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(InCadWorkbench())
```

`InCad/incad/resources/icons/light/incad.svg` and `.../dark/incad.svg` (same content for now; Task 7's generator
overwrites both):
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32"><path d="M4 11 L16 5 L28 11 L16 17 Z" fill="#9cc6f3" stroke="#0a64d6" stroke-width="1.5"/><path d="M4 11 V21 L16 27 V17 Z" fill="#5a9ae6" stroke="#0a64d6" stroke-width="1.5"/><path d="M28 11 V21 L16 27 V17 Z" fill="#0a64d6" stroke="#0a64d6" stroke-width="1.5"/></svg>
```

- [ ] **Step 2: Write the install script and test runners**

`scripts/install.sh`:
```zsh
#!/bin/zsh
# Links the InCad module into FreeCAD 1.1's user Mod folder (once). FreeCAD picks up code changes on restart.
set -e
REPO="${0:A:h:h}"
MOD="$HOME/Library/Application Support/FreeCAD/v1-1/Mod"
LINK="$MOD/InCad"
mkdir -p "$MOD"
if [[ -L "$LINK" ]]; then
  [[ "$(readlink "$LINK")" == "$REPO/InCad" ]] && { echo "Already installed: $LINK"; exit 0; }
  echo "❌ $LINK points elsewhere: $(readlink "$LINK")"; exit 1
elif [[ -e "$LINK" ]]; then
  echo "❌ $LINK exists and is not a link; not touching it."; exit 1
fi
ln -s "$REPO/InCad" "$LINK"
echo "Installed: $LINK -> $REPO/InCad"
```

`tests/run_headless.sh`:
```zsh
#!/bin/zsh
# Model tests inside FreeCAD without a window (freecadcmd), with throwaway settings.
# Optional argument: file pattern, e.g. test_safe.py
REPO="${0:A:h:h}"
TMP="$(mktemp -d)"
INCAD_REPO="$REPO" INCAD_TEST_PATTERN="${1:-test_*.py}" INCAD_LOG="$TMP/incad.log" PYTHONDONTWRITEBYTECODE=1 \
  /Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd -u "$TMP/user.cfg" "$REPO/tests/headless_main.py"
```

`tests/headless_main.py`:
```python
"""Runs tests/headless/test_*.py inside freecadcmd. Started by tests/run_headless.sh."""
import os
import sys
import unittest

repo = os.environ["INCAD_REPO"]
sys.path.insert(0, os.path.join(repo, "InCad"))
sys.path.insert(0, os.path.join(repo, "tests"))
suite = unittest.defaultTestLoader.discover(
    os.path.join(repo, "tests", "headless"),
    pattern=os.environ.get("INCAD_TEST_PATTERN", "test_*.py"),
    top_level_dir=os.path.join(repo, "tests"),
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
```

`tests/run_widgets.sh`:
```zsh
#!/bin/zsh
# Widget tests: plain PySide6 in FreeCAD's bundled Python, offscreen (no window, no FreeCAD).
REPO="${0:A:h:h}"
TMP="$(mktemp -d)"
cd "$REPO/tests" || exit 1
QT_QPA_PLATFORM=offscreen PYTHONPATH="$REPO/InCad:$REPO/tests" PYTHONDONTWRITEBYTECODE=1 INCAD_LOG="$TMP/incad.log" \
  /Applications/FreeCAD.app/Contents/Resources/bin/python -m unittest discover -s widgets -t . -p "${1:-test_*.py}" -v
```

`tests/run_gui.sh`:
```zsh
#!/bin/zsh
# GUI tests in a real FreeCAD window with throwaway settings (the user's user.cfg is never touched).
# Usage: tests/run_gui.sh tests/gui/test_shell.py   (no argument = every tests/gui/test_*.py)
REPO="${0:A:h:h}"
FC=/Applications/FreeCAD.app/Contents/MacOS/FreeCAD
PY=/Applications/FreeCAD.app/Contents/Resources/bin/python
files=("$@"); (( $#files )) || files=("$REPO"/tests/gui/test_*.py)
rc=0
for f in $files; do
  TMP="$(mktemp -d)"; OUT="$TMP/result.json"
  echo "== ${f:t}"
  INCAD_REPO="$REPO" INCAD_GUI_OUT="$OUT" INCAD_LOG="$TMP/incad.log" PYTHONDONTWRITEBYTECODE=1 \
    "$FC" -u "$TMP/user.cfg" "${f:A}" >"$TMP/fc.log" 2>&1 &
  pid=$!
  for i in {1..180}; do kill -0 $pid 2>/dev/null || break; sleep 1; done
  if kill -0 $pid 2>/dev/null; then
    kill $pid; pkill -f "$TMP/user.cfg"; echo "TIMEOUT — log: $TMP/fc.log"; rc=1; continue
  fi
  if [[ ! -f "$OUT" ]]; then echo "NO RESULT — log: $TMP/fc.log"; tail -20 "$TMP/fc.log"; rc=1; continue; fi
  "$PY" - "$OUT" <<'PY' || rc=1
import json, sys
res = json.load(open(sys.argv[1]))
bad = [r for r in res if not r["ok"]]
for r in res:
    print(("PASS " if r["ok"] else "FAIL ") + r["name"])
    if not r["ok"]:
        print(r["detail"])
print("%d passed, %d failed" % (len(res) - len(bad), len(bad)))
sys.exit(1 if bad or not res else 0)
PY
done
exit $rc
```

`tests/run_all.sh`:
```zsh
#!/bin/zsh
# Every test suite. GUI tests open FreeCAD windows: keep hands off mouse and keyboard while they run.
HERE="${0:A:h}"
rc=0
echo "### widgets";  "$HERE/run_widgets.sh"  || rc=1
echo "### headless"; "$HERE/run_headless.sh" || rc=1
echo "### gui";      "$HERE/run_gui.sh"      || rc=1
(( rc == 0 )) && echo "ALL SUITES PASSED" || echo "SOME SUITES FAILED"
exit $rc
```

`tests/headless/__init__.py`, `tests/widgets/__init__.py`: empty files.

`tests/widgets/qtapp.py`:
```python
"""One QApplication for all widget tests (offscreen)."""
from incad.qt import QtWidgets


def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
```

`tests/gui/harness.py`:
```python
"""GUI test harness: runs inside a real FreeCAD window started by tests/run_gui.sh and writes a JSON result."""
import json
import os
import time
import traceback

from PySide import QtCore, QtWidgets


def pump(ms=150):
    """Let Qt process events (including deferred deletes) for about `ms` milliseconds."""
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        time.sleep(0.01)


def _close_modals():
    for _ in range(5):
        w = QtWidgets.QApplication.activeModalWidget()
        if w is None:
            return
        if hasattr(w, "reject"):
            w.reject()
        else:
            w.close()
        pump(200)


def run(tests, delay_ms=2000):
    """Run test functions in order once FreeCAD is up, write results to $INCAD_GUI_OUT, exit FreeCAD."""
    def go():
        results = []
        _close_modals()
        for t in tests:
            try:
                t()
                results.append({"name": t.__name__, "ok": True, "detail": ""})
            except Exception:
                results.append({"name": t.__name__, "ok": False, "detail": traceback.format_exc()})
            pump()
        with open(os.environ["INCAD_GUI_OUT"], "w") as f:
            json.dump(results, f, indent=1)
        os._exit(0)

    QtCore.QTimer.singleShot(delay_ms, go)
```

`chmod +x scripts/install.sh tests/run_*.sh`

- [ ] **Step 3: Write the failing smoke tests**

`tests/headless/test_smoke.py`:
```python
import unittest


class SmokeTest(unittest.TestCase):
    def test_import_incad(self):
        import incad
        self.assertEqual(incad.__version__, "0.1.0")

    def test_freecad_available(self):
        import FreeCAD
        self.assertEqual(FreeCAD.Version()[:2], ["1", "1"])
```

`tests/widgets/test_smoke.py`:
```python
import unittest

from widgets import qtapp


class SmokeTest(unittest.TestCase):
    def test_qt_offscreen(self):
        qtapp.app()
        from incad.qt import QtWidgets
        b = QtWidgets.QToolButton()
        b.setText("x")
        self.assertGreater(b.sizeHint().width(), 0)

    def test_freecad_not_importable_here(self):
        with self.assertRaises(ImportError):
            import FreeCAD  # noqa: F401
```

`tests/gui/test_smoke.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCADGui as Gui  # noqa: E402


def test_workbench_registered():
    assert "InCadWorkbench" in Gui.listWorkbenches(), sorted(Gui.listWorkbenches())


harness.run([test_workbench_registered])
```

- [ ] **Step 4: Run the headless and widget smoke tests (they pass: no InCad code under test yet besides import)**

Run: `tests/run_headless.sh` → Expected: `test_import_incad ... ok`, `test_freecad_available ... ok`, `OK`.
Run: `tests/run_widgets.sh` → Expected: 2 tests `OK`.

- [ ] **Step 5: Run the GUI smoke test before installing (it fails)**

Tell the user: "FreeCAD window opening for a test — hands off mouse/keyboard for ~15 s."
Run: `tests/run_gui.sh tests/gui/test_smoke.py`
Expected: `FAIL test_workbench_registered` (InCad not installed yet).

- [ ] **Step 6: Install and re-run**

Run: `scripts/install.sh` → Expected: `Installed: …/Mod/InCad -> /Volumes/Docs/InCad/InCad`
Run: `tests/run_gui.sh tests/gui/test_smoke.py` → Expected: `PASS test_workbench_registered`, `1 passed, 0 failed`.
Tell the user the mouse/keyboard are free again.

- [ ] **Step 7: Write CLAUDE.md**

`CLAUDE.md`:
```markdown
# InCad

Inventor/Alibre-style workbench for FreeCAD 1.1.3 (macOS). Spec: docs/superpowers/specs/, plans: docs/superpowers/plans/.

- Module: `InCad/` (package `incad`), installed by `scripts/install.sh` as a symlink in
  `~/Library/Application Support/FreeCAD/v1-1/Mod/InCad`. Restart FreeCAD to load code changes.
- Tests: `tests/run_widgets.sh` (offscreen PySide6), `tests/run_headless.sh` (freecadcmd),
  `tests/run_gui.sh` (real FreeCAD window — tell the user to keep hands off), `tests/run_all.sh`.
  Every FreeCAD run uses `-u <temp>/user.cfg`, so the user's settings are never touched.
- FreeCAD facts: bundled Python has no pytest (use unittest); `PySide` is FreeCAD's shim (PySide6 outside);
  new documents have `UndoMode == 0` — `incad.core.safe` turns it on; a failed feature has `'Invalid'` in
  `obj.State` and the reason in `obj.getStatusString()`.
- UI text English. Chat with the user in any language.
```

- [ ] **Step 8: Commit**

```bash
git add InCad scripts tests CLAUDE.md
git commit -m "InCad: module skeleton, install script, three test runners, empty workbench"
```

---

### Task 2: Log and preferences

**Files:**
- Create: `InCad/incad/core/log.py`, `InCad/incad/core/prefs.py`
- Test: `tests/widgets/test_log.py`, `tests/widgets/test_prefs.py`, `tests/headless/test_prefs_param.py`

**Interfaces:**
- Produces (`incad.core.log`): `log_path() -> str`, `logger() -> logging.Logger`, `set_reporter(fn | None)` where
  `fn(level: str, message: str)`, `report(level: str, message: str, detail: str = "")` (level `'info'|'warning'|'error'`),
  `_reset_for_tests()`.
- Produces (`incad.core.prefs`): `THEMES`, `RIBBON_SIZES`, `UNITS`; `use_memory_backend()`;
  `theme()/set_theme(v)`, `ribbon_size()/set_ribbon_size(v)`, `default_units()/set_default_units(v)`,
  `remember_new_choice()/set_remember_new_choice(bool)`, `last_workbench()/set_last_workbench(name)`,
  `takeover_snapshot()/set_takeover_snapshot(text)/clear_takeover_snapshot()`. Setters raise `ValueError` for
  values outside the allowed set.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_log.py`:
```python
import os
import tempfile
import unittest

from incad.core import log


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("INCAD_LOG")
        os.environ["INCAD_LOG"] = os.path.join(self.tmp, "sub", "incad.log")
        log._reset_for_tests()

    def tearDown(self):
        log._reset_for_tests()
        if self.old is None:
            os.environ.pop("INCAD_LOG", None)
        else:
            os.environ["INCAD_LOG"] = self.old

    def test_report_writes_log_file(self):
        log.report("error", "Fillet failed", "Traceback: details")
        with open(log.log_path()) as f:
            text = f.read()
        self.assertIn("ERROR Fillet failed", text)
        self.assertIn("Traceback: details", text)

    def test_reporter_receives_level_and_message(self):
        seen = []
        log.set_reporter(lambda level, msg: seen.append((level, msg)))
        log.report("warning", "Careful")
        self.assertEqual(seen, [("warning", "Careful")])

    def test_broken_reporter_does_not_raise(self):
        def bad(level, msg):
            raise RuntimeError("reporter broke")
        log.set_reporter(bad)
        log.report("info", "still fine")
        with open(log.log_path()) as f:
            self.assertIn("reporter failed", f.read())
```

`tests/widgets/test_prefs.py`:
```python
import unittest

from incad.core import prefs


class PrefsMemoryTest(unittest.TestCase):
    def setUp(self):
        prefs.use_memory_backend()

    def test_defaults(self):
        self.assertEqual(prefs.theme(), "auto")
        self.assertEqual(prefs.ribbon_size(), "large")
        self.assertEqual(prefs.default_units(), "mm")
        self.assertFalse(prefs.remember_new_choice())
        self.assertEqual(prefs.last_workbench(), "PartDesignWorkbench")
        self.assertEqual(prefs.takeover_snapshot(), "")

    def test_roundtrip(self):
        prefs.set_theme("dark")
        prefs.set_ribbon_size("small")
        prefs.set_default_units("in")
        prefs.set_remember_new_choice(True)
        prefs.set_last_workbench("SketcherWorkbench")
        prefs.set_takeover_snapshot('{"a": 1}')
        self.assertEqual(
            (prefs.theme(), prefs.ribbon_size(), prefs.default_units(), prefs.remember_new_choice(),
             prefs.last_workbench(), prefs.takeover_snapshot()),
            ("dark", "small", "in", True, "SketcherWorkbench", '{"a": 1}'))
        prefs.clear_takeover_snapshot()
        self.assertEqual(prefs.takeover_snapshot(), "")

    def test_invalid_values_rejected(self):
        for setter, bad in ((prefs.set_theme, "blue"), (prefs.set_ribbon_size, "huge"), (prefs.set_default_units, "cm")):
            with self.assertRaises(ValueError):
                setter(bad)
```

`tests/headless/test_prefs_param.py`:
```python
import unittest

import FreeCAD as App
from incad.core import prefs


class PrefsParamTest(unittest.TestCase):
    def test_stored_in_freecad_parameters(self):
        prefs._store = None  # force the FreeCAD backend
        prefs.set_theme("light")
        prefs.set_remember_new_choice(True)
        p = App.ParamGet(prefs.GROUP)
        self.assertEqual(p.GetString("Theme"), "light")
        self.assertTrue(p.GetBool("RememberNewChoice"))
        prefs.set_takeover_snapshot("x")
        prefs.clear_takeover_snapshot()
        self.assertEqual(p.GetString("TakeoverSnapshot", ""), "")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_log.py` and `tests/run_widgets.sh test_prefs.py` and `tests/run_headless.sh test_prefs_param.py`
Expected: errors `ModuleNotFoundError: No module named 'incad.core.log'` / `'incad.core.prefs'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/log.py`:
```python
"""InCad logging and user-facing messages. No FreeCAD import: usable from widget tests."""
import logging
import os

_logger = None
_reporter = None


def log_path():
    return os.environ.get("INCAD_LOG") or os.path.expanduser("~/Library/Logs/InCad.log")


def logger():
    global _logger
    if _logger is None:
        _logger = logging.getLogger("InCad")
        _logger.setLevel(logging.INFO)
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(handler)
        _logger.propagate = False
    return _logger


def set_reporter(fn):
    """fn(level, message) shows a message to the user (status bar). None = log only."""
    global _reporter
    _reporter = fn


def report(level, message, detail=""):
    """level: 'info' | 'warning' | 'error'. Always logged; shown to the user when a reporter is set."""
    log = logger()
    write = {"info": log.info, "warning": log.warning}.get(level, log.error)
    write(message + ("\n" + detail if detail else ""))
    if _reporter is not None:
        try:
            _reporter(level, message)
        except Exception:
            log.exception("reporter failed")


def _reset_for_tests():
    global _logger, _reporter
    if _logger is not None:
        for h in list(_logger.handlers):
            _logger.removeHandler(h)
            h.close()
    _logger = None
    _reporter = None
```

`InCad/incad/core/prefs.py`:
```python
"""InCad preferences, stored in FreeCAD's parameters (User parameter:BaseApp/Preferences/Mod/InCad).
Falls back to an in-memory store when FreeCAD is not importable (widget tests)."""

GROUP = "User parameter:BaseApp/Preferences/Mod/InCad"

THEMES = ("auto", "light", "dark")
RIBBON_SIZES = ("small", "medium", "large")
UNITS = ("mm", "in")


class _MemoryStore:
    def __init__(self):
        self.data = {}

    def get(self, kind, key, default):
        return self.data.get((kind, key), default)

    def set(self, kind, key, value):
        self.data[(kind, key)] = value

    def remove(self, kind, key):
        self.data.pop((kind, key), None)


class _ParamStore:
    def __init__(self):
        import FreeCAD
        self.p = FreeCAD.ParamGet(GROUP)

    def get(self, kind, key, default):
        return {"str": self.p.GetString, "bool": self.p.GetBool}[kind](key, default)

    def set(self, kind, key, value):
        {"str": self.p.SetString, "bool": self.p.SetBool}[kind](key, value)

    def remove(self, kind, key):
        {"str": self.p.RemString, "bool": self.p.RemBool}[kind](key)


_store = None


def _s():
    global _store
    if _store is None:
        try:
            _store = _ParamStore()
        except ImportError:
            _store = _MemoryStore()
    return _store


def use_memory_backend():
    global _store
    _store = _MemoryStore()


def _choice(key, allowed, default):
    value = _s().get("str", key, default)
    return value if value in allowed else default


def _set_choice(key, allowed, value):
    if value not in allowed:
        raise ValueError("%s must be one of %s, got %r" % (key, ", ".join(allowed), value))
    _s().set("str", key, value)


def theme():
    return _choice("Theme", THEMES, "auto")


def set_theme(value):
    _set_choice("Theme", THEMES, value)


def ribbon_size():
    return _choice("RibbonSize", RIBBON_SIZES, "large")


def set_ribbon_size(value):
    _set_choice("RibbonSize", RIBBON_SIZES, value)


def default_units():
    return _choice("DefaultUnits", UNITS, "mm")


def set_default_units(value):
    _set_choice("DefaultUnits", UNITS, value)


def remember_new_choice():
    return bool(_s().get("bool", "RememberNewChoice", False))


def set_remember_new_choice(value):
    _s().set("bool", "RememberNewChoice", bool(value))


def last_workbench():
    return _s().get("str", "LastWorkbench", "") or "PartDesignWorkbench"


def set_last_workbench(name):
    _s().set("str", "LastWorkbench", name)


def takeover_snapshot():
    return _s().get("str", "TakeoverSnapshot", "")


def set_takeover_snapshot(text):
    _s().set("str", "TakeoverSnapshot", text)


def clear_takeover_snapshot():
    _s().remove("str", "TakeoverSnapshot")
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_log.py`, `tests/run_widgets.sh test_prefs.py`, `tests/run_headless.sh test_prefs_param.py`
Expected: all `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/log.py InCad/incad/core/prefs.py tests/widgets/test_log.py tests/widgets/test_prefs.py tests/headless/test_prefs_param.py
git commit -m "InCad: log file + user reporter, preferences"
```

---

### Task 3: Safe command guard

**Files:**
- Create: `InCad/incad/core/safe.py`, `tests/headless/util.py`
- Test: `tests/headless/test_safe.py`

**Interfaces:**
- Consumes: `incad.core.log.report`.
- Produces (`incad.core.safe`): `SafeResult(ok: bool, value=None, error: str = "")`;
  `run_safely(label: str, fn: Callable[[], Any], doc=None) -> SafeResult` — never raises at the outermost
  level; nested calls run `fn` directly so the outermost call owns the single transaction.
- Produces (`tests/headless/util.py`): `new_doc(name) -> Document` (UndoMode 1), `xy_plane(body)`,
  `add_rect_sketch(body, w=20, h=10, name="Sketch")`, `add_pad(body, sketch, length=5, name="Pad")`,
  `padded_part(doc, length=10, incad=False) -> (body, pad)` (committed, recomputed).

- [ ] **Step 1: Write the test helper and failing tests**

`tests/headless/util.py`:
```python
"""Helpers that build small real models for headless tests."""
import FreeCAD as App
import Part
import Sketcher


def new_doc(name="T"):
    doc = App.newDocument(name)
    doc.UndoMode = 1
    return doc


def xy_plane(body):
    return [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]


def add_rect_sketch(body, w=20, h=10, name="Sketch"):
    s = body.newObject("Sketcher::SketchObject", name)
    s.AttachmentSupport = [(xy_plane(body), "")]
    s.MapMode = "FlatFace"
    pts = [App.Vector(0, 0, 0), App.Vector(w, 0, 0), App.Vector(w, h, 0), App.Vector(0, h, 0)]
    for i in range(4):
        s.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    for i in range(4):
        s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    return s


def add_pad(body, sketch, length=5, name="Pad"):
    pad = body.newObject("PartDesign::Pad", name)
    pad.Profile = sketch
    pad.Length = length
    return pad


def padded_part(doc, length=10, incad=False):
    """A body with a 20x10 rectangle padded by `length`, committed as one undo step."""
    doc.openTransaction("setup")
    if incad:
        from incad.core import document  # Task 4; Task 3's tests only use incad=False
        body = document.make_part(doc)
    else:
        body = doc.addObject("PartDesign::Body", "Body")
    sketch = add_rect_sketch(body)
    pad = add_pad(body, sketch, length)
    body.Tip = pad
    doc.recompute()
    doc.commitTransaction()
    return body, pad
```

`tests/headless/test_safe.py`:
```python
import unittest

import FreeCAD as App
from incad.core import log, safe
from headless import util


class SafeTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Safe")
        self.messages = []
        log.set_reporter(lambda level, msg: self.messages.append((level, msg)))

    def tearDown(self):
        log.set_reporter(None)
        App.closeDocument(self.doc.Name)

    def test_success_commits_one_undo_step(self):
        r = safe.run_safely("Add body", lambda: self.doc.addObject("PartDesign::Body", "Body"), self.doc)
        self.assertTrue(r.ok)
        self.assertIsNotNone(self.doc.getObject("Body"))
        self.assertIn("Add body", self.doc.UndoNames)

    def test_turns_undo_on(self):
        doc = App.newDocument("NoUndo")
        try:
            self.assertEqual(doc.UndoMode, 0)
            def boom():
                doc.addObject("PartDesign::Body", "Body")
                raise RuntimeError("boom")
            safe.run_safely("Boom", boom, doc)
            self.assertIsNone(doc.getObject("Body"))
        finally:
            App.closeDocument(doc.Name)

    def test_exception_rolls_back_and_reports(self):
        def boom():
            self.doc.addObject("PartDesign::Body", "Body")
            raise RuntimeError("boom")
        r = safe.run_safely("Boom", boom, self.doc)
        self.assertFalse(r.ok)
        self.assertIn("boom", r.error)
        self.assertIsNone(self.doc.getObject("Body"))
        self.assertEqual(self.messages[-1][0], "error")
        with open(log.log_path()) as f:
            self.assertIn("boom", f.read())

    def test_invalid_result_rolls_back(self):
        body, pad = util.padded_part(self.doc, length=10)
        volume = pad.Shape.Volume
        r = safe.run_safely("Zero pad", lambda: setattr(pad, "Length", 0), self.doc)
        self.assertFalse(r.ok)
        self.assertIn("Pad", r.error)
        self.assertAlmostEqual(pad.Length.Value, 10)
        self.assertAlmostEqual(pad.Shape.Volume, volume, places=6)
        self.assertNotIn("Invalid", pad.State)

    def test_nested_failure_rolls_back_outer(self):
        def inner():
            raise ValueError("inner")

        def outer():
            self.doc.addObject("PartDesign::Body", "Body")
            safe.run_safely("Inner", inner, self.doc)

        r = safe.run_safely("Outer", outer, self.doc)
        self.assertFalse(r.ok)
        self.assertIsNone(self.doc.getObject("Body"))

    def test_undo_works_after_a_rollback(self):
        safe.run_safely("Boom", lambda: 1 / 0, self.doc)
        self.assertFalse(self.doc.HasPendingTransaction)
        safe.run_safely("Add body", lambda: self.doc.addObject("PartDesign::Body", "Body"), self.doc)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject("Body"))
        self.doc.redo()
        self.assertIsNotNone(self.doc.getObject("Body"))

    def test_existing_broken_object_does_not_block(self):
        body, pad = util.padded_part(self.doc, length=10)
        pad.Length = 0
        self.doc.recompute()
        r = safe.run_safely("Add body", lambda: self.doc.addObject("PartDesign::Body", "Body001"), self.doc)
        self.assertTrue(r.ok)

    def test_no_document_still_catches(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        try:
            r = safe.run_safely("No doc", lambda: 1 / 0)
            self.assertFalse(r.ok)
            self.assertIn("division", r.error)
        finally:
            self.doc = util.new_doc("Safe")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_safe.py`
Expected: `ModuleNotFoundError: No module named 'incad.core.safe'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/safe.py`:
```python
"""Safe command guard. Every model change runs in one undo transaction; on an exception or an invalid result
the transaction is aborted, the model recomputed back to its previous state, and the user told why."""
import traceback
from dataclasses import dataclass

from incad.core import log

_depth = 0


@dataclass
class SafeResult:
    ok: bool
    value: object = None
    error: str = ""


class _InvalidResult(Exception):
    pass


def _status(obj):
    try:
        return obj.getStatusString()
    except Exception:
        return ""


def _broken(obj, check_shape):
    """Reason text if obj failed to compute or (check_shape) has invalid PartDesign geometry, else ''."""
    state = getattr(obj, "State", [])
    if "Invalid" in state or "Error" in state:
        status = _status(obj)
        return "%s: %s" % (obj.Label, status) if status and status not in ("Valid", "Touched") \
            else "%s failed to compute" % obj.Label
    if check_shape and obj.TypeId.startswith("PartDesign::"):
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull() and not shape.isValid():
            return "%s produced invalid geometry" % obj.Label
    return ""


def run_safely(label, fn, doc=None):
    """Run fn() as one undo step named `label`. Never raises at the outermost level."""
    global _depth
    if _depth > 0:
        return SafeResult(True, fn())  # nested: the outer guard owns the transaction and catches errors
    import FreeCAD as App
    doc = doc or App.ActiveDocument
    if doc is None:
        try:
            return SafeResult(True, fn())
        except Exception as e:
            msg = "%s failed: %s" % (label, e)
            log.report("error", msg, traceback.format_exc())
            return SafeResult(False, error=msg)
    if not doc.UndoMode:
        doc.UndoMode = 1
    broken_before = {o.Name for o in doc.Objects if _broken(o, False)}
    names_before = {o.Name for o in doc.Objects}
    _depth += 1
    doc.openTransaction(label)
    try:
        value = fn()
        touched = {o.Name for o in doc.Objects if "Touched" in o.State or o.Name not in names_before}
        doc.recompute()
        problems = [_broken(o, o.Name in touched) for o in doc.Objects if o.Name not in broken_before]
        problems = [p for p in problems if p]
        if problems:
            raise _InvalidResult("; ".join(problems))
    except Exception as e:
        doc.abortTransaction()
        doc.recompute()
        invalid = isinstance(e, _InvalidResult)
        msg = str(e) if invalid else "%s failed: %s" % (label, e)
        log.report("error", msg, "" if invalid else traceback.format_exc())
        return SafeResult(False, error=msg)
    finally:
        _depth -= 1
    doc.commitTransaction()
    return SafeResult(True, value)
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_safe.py`
Expected: 8 tests `OK`. If `HasPendingTransaction` is missing in 1.1.3, the attribute error shows here: replace
that assertion with `self.assertEqual(self.doc.UndoNames, [])` (a pending transaction would appear there) and
note it in CLAUDE.md.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/safe.py tests/headless/util.py tests/headless/test_safe.py
git commit -m "InCad: safe command guard with rollback on exceptions and invalid geometry"
```

---

### Task 4: InCad Part document model

**Files:**
- Create: `InCad/incad/core/document.py`
- Test: `tests/headless/test_document.py`

**Interfaces:**
- Produces (`incad.core.document`): constants `TYPE_KEY="InCadType"`, `UNITS_KEY="InCadUnits"`,
  `PRIMARY_KEY="InCadPrimaryBody"`, `UNIT_SCHEMES={"mm": "Standard (mm, kg, s, °)", "in": "Imperial decimal (in, lb)"}`,
  `PARAMS_NAME="InCadParameters"`; functions `is_incad_part(doc) -> bool`, `part_units(doc) -> "mm"|"in"|None`,
  `set_units(doc, units)`, `bodies(doc) -> list`, `primary_body(doc) -> Body|None`,
  `make_part(doc, units="mm") -> Body` (label `Solid1`), `convert_to_part(doc, units="mm") -> Body`,
  `new_solid(doc) -> Body` (label `Solid<n>`), `end_of_part(body)`, `set_end_of_part(body, feature_or_None)`.
  All raise `ValueError` with a user-readable message on misuse. (Parameters come in Task 5.)

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_document.py`:
```python
import os
import tempfile
import unittest

import FreeCAD as App
from incad.core import document
from headless import util


class DocumentTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Doc")

    def tearDown(self):
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def test_make_part_marks_and_sets_units(self):
        body = document.make_part(self.doc, "in")
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertEqual(document.part_units(self.doc), "in")
        self.assertEqual(self.doc.UnitSystem, "Imperial decimal (in, lb)")
        self.assertIs(document.primary_body(self.doc), body)
        self.assertEqual(body.Label, "Solid1")

    def test_plain_document_is_not_a_part(self):
        self.assertFalse(document.is_incad_part(self.doc))
        self.assertIsNone(document.part_units(self.doc))
        self.assertIsNone(document.primary_body(self.doc))
        self.assertFalse(document.is_incad_part(None))

    def test_make_part_twice_fails(self):
        document.make_part(self.doc)
        with self.assertRaises(ValueError):
            document.make_part(self.doc)

    def test_bad_units(self):
        with self.assertRaises(ValueError):
            document.make_part(self.doc, "cm")

    def test_marker_survives_save_and_reopen(self):
        document.make_part(self.doc, "mm")
        path = os.path.join(tempfile.mkdtemp(), "part.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertEqual(document.part_units(self.doc), "mm")
        self.assertIsNotNone(document.primary_body(self.doc))

    def test_convert_plain_file_with_one_body(self):
        self.doc.addObject("PartDesign::Body", "Body")
        body = document.convert_to_part(self.doc, "in")
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertIs(document.primary_body(self.doc), body)
        self.assertEqual(document.part_units(self.doc), "in")

    def test_convert_refuses_zero_or_many_bodies(self):
        with self.assertRaises(ValueError):
            document.convert_to_part(self.doc)
        self.doc.addObject("PartDesign::Body", "Body")
        self.doc.addObject("PartDesign::Body", "Body001")
        with self.assertRaises(ValueError):
            document.convert_to_part(self.doc)

    def test_new_solid(self):
        document.make_part(self.doc)
        b2 = document.new_solid(self.doc)
        self.assertEqual(len(document.bodies(self.doc)), 2)
        self.assertEqual(b2.Label, "Solid2")
        self.assertIsNot(document.primary_body(self.doc), b2)

    def test_new_solid_requires_part(self):
        with self.assertRaises(ValueError):
            document.new_solid(self.doc)

    def test_end_of_part_rolls_back_and_forward(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        self.assertIs(document.end_of_part(body), pad)
        document.set_end_of_part(body, None)
        self.assertIsNone(body.Tip)
        self.assertTrue(body.Shape.isNull())
        document.set_end_of_part(body, pad)
        self.assertAlmostEqual(body.Shape.Volume, 20 * 10 * 10, places=3)

    def test_end_of_part_rejects_foreign_feature(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        other = self.doc.addObject("PartDesign::Body", "Other")
        with self.assertRaises(ValueError):
            document.set_end_of_part(other, pad)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_document.py` → Expected: `ModuleNotFoundError: No module named 'incad.core.document'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/document.py`:
```python
"""An InCad Part is a normal FreeCAD document holding PartDesign Bodies. InCad marks it in doc.Meta and keeps
the Body concept away from the user. Pure model logic: no Qt, no GUI."""
import re

import FreeCAD as App

TYPE_KEY = "InCadType"
UNITS_KEY = "InCadUnits"
PRIMARY_KEY = "InCadPrimaryBody"
UNIT_SCHEMES = {"mm": "Standard (mm, kg, s, °)", "in": "Imperial decimal (in, lb)"}
PARAMS_NAME = "InCadParameters"


def _meta_set(doc, **items):
    meta = dict(doc.Meta)
    meta.update(items)
    doc.Meta = meta


def is_incad_part(doc):
    return doc is not None and doc.Meta.get(TYPE_KEY) == "Part"


def part_units(doc):
    units = doc.Meta.get(UNITS_KEY) if doc is not None else None
    return units if units in UNIT_SCHEMES else None


def set_units(doc, units):
    if units not in UNIT_SCHEMES:
        raise ValueError("Units must be 'mm' or 'in', got %r" % (units,))
    _meta_set(doc, **{UNITS_KEY: units})
    if "UnitSystem" in doc.PropertiesList:
        doc.UnitSystem = UNIT_SCHEMES[units]


def bodies(doc):
    return [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]


def primary_body(doc):
    if doc is None:
        return None
    name = doc.Meta.get(PRIMARY_KEY)
    body = doc.getObject(name) if name else None
    return body if body is not None and body.TypeId == "PartDesign::Body" else None


def make_part(doc, units="mm"):
    if units not in UNIT_SCHEMES:
        raise ValueError("Units must be 'mm' or 'in', got %r" % (units,))
    if is_incad_part(doc):
        raise ValueError("%s is already an InCad part" % doc.Label)
    if bodies(doc):
        raise ValueError("This file already has bodies; use Convert to InCad Part")
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = "Solid1"
    _meta_set(doc, **{TYPE_KEY: "Part", PRIMARY_KEY: body.Name})
    set_units(doc, units)
    return body


def convert_to_part(doc, units="mm"):
    found = bodies(doc)
    if len(found) != 1:
        raise ValueError("Only a file with exactly one Body can be converted (this one has %d)" % len(found))
    _meta_set(doc, **{TYPE_KEY: "Part", PRIMARY_KEY: found[0].Name})
    set_units(doc, units)
    return found[0]


def new_solid(doc):
    if not is_incad_part(doc):
        raise ValueError("New Solid needs an InCad part")
    body = doc.addObject("PartDesign::Body", "Body")
    body.Label = "Solid%d" % len(bodies(doc))
    return body


def end_of_part(body):
    return body.Tip


def set_end_of_part(body, feature):
    """Put End of Part right after `feature`; None puts it before the first feature."""
    if feature is not None and feature not in body.Group:
        raise ValueError("%s is not part of %s" % (feature.Label, body.Label))
    body.Tip = feature
    body.Document.recompute()
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_document.py` → Expected: 11 tests `OK`.
Also re-run `tests/run_headless.sh` (all) → Expected: all `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/document.py tests/headless/test_document.py
git commit -m "InCad: InCad Part model (marker, units, bodies, End of Part)"
```

---

### Task 5: Parameters (named values and formulas)

**Files:**
- Modify: `InCad/incad/core/document.py` (append)
- Test: `tests/headless/test_parameters.py`

**Interfaces:**
- Consumes: Task 4 `document` module, Task 3 `safe.run_safely`.
- Produces (`incad.core.document`): `parameters(doc, create=True) -> App::VarSet|None` (name `InCadParameters`,
  label `Parameters`), `list_parameters(doc) -> list[tuple[name, expression or "", value_text]]`,
  `set_parameter(doc, name, text)` (quantity like `"80 mm"` / `"12"`, or formula like `"Width/8"`),
  `remove_parameter(doc, name)`. Errors raise `ValueError`; callers wrap in `safe.run_safely` so a failing
  formula is rolled back.

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_parameters.py`:
```python
import unittest

import FreeCAD as App
from incad.core import document, safe
from headless import util


def rows(doc):
    return {name: (expr, value) for name, expr, value in document.list_parameters(doc)}


class ParametersTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Params")
        document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_empty_without_creating(self):
        self.assertEqual(document.list_parameters(self.doc), [])
        self.assertIsNone(document.parameters(self.doc, create=False))

    def test_quantity(self):
        document.set_parameter(self.doc, "Width", "80 mm")
        self.assertEqual(rows(self.doc)["Width"], ("", "80 mm"))
        self.assertEqual(document.parameters(self.doc).Label, "Parameters")

    def test_formula_follows_source(self):
        document.set_parameter(self.doc, "Width", "80 mm")
        document.set_parameter(self.doc, "HoleD", "Width/8")
        self.assertEqual(rows(self.doc)["HoleD"], ("Width/8", "10 mm"))
        document.set_parameter(self.doc, "Width", "160 mm")
        self.assertEqual(rows(self.doc)["HoleD"][1], "20 mm")

    def test_formula_replaced_by_value(self):
        document.set_parameter(self.doc, "Width", "80 mm")
        document.set_parameter(self.doc, "HoleD", "Width/8")
        document.set_parameter(self.doc, "HoleD", "5 mm")
        self.assertEqual(rows(self.doc)["HoleD"], ("", "5 mm"))

    def test_invalid_names(self):
        for bad in ("", "2x", "a b", "Width-1", "Label"):
            with self.assertRaises(ValueError, msg=bad):
                document.set_parameter(self.doc, bad, "1")

    def test_empty_value(self):
        with self.assertRaises(ValueError):
            document.set_parameter(self.doc, "Gap", "  ")

    def test_unknown_name_in_formula_is_rolled_back(self):
        r = safe.run_safely("Set", lambda: document.set_parameter(self.doc, "Gap", "Nope*2"), self.doc)
        self.assertFalse(r.ok)
        self.assertNotIn("Gap", rows(self.doc))

    def test_cycle_is_rolled_back(self):
        document.set_parameter(self.doc, "A", "1")
        document.set_parameter(self.doc, "B", "A*2")
        r = safe.run_safely("Cycle", lambda: document.set_parameter(self.doc, "A", "B*2"), self.doc)
        self.assertFalse(r.ok)
        self.assertEqual(rows(self.doc)["A"], ("", "1"))

    def test_remove(self):
        document.set_parameter(self.doc, "Gap", "0.2 mm")
        document.remove_parameter(self.doc, "Gap")
        self.assertNotIn("Gap", rows(self.doc))
        with self.assertRaises(ValueError):
            document.remove_parameter(self.doc, "Gap")

    def test_undo_after_failed_formula(self):
        safe.run_safely("Bad", lambda: document.set_parameter(self.doc, "Gap", "Nope*2"), self.doc)
        safe.run_safely("Good", lambda: document.set_parameter(self.doc, "Gap", "0.2 mm"), self.doc)
        self.doc.undo()
        self.assertNotIn("Gap", rows(self.doc))
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_parameters.py` → Expected: `AttributeError: module 'incad.core.document' has no attribute 'list_parameters'`.

- [ ] **Step 3: Implement (append to `InCad/incad/core/document.py`)**

```python
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GROUP = "Parameters"


def parameters(doc, create=True):
    obj = doc.getObject(PARAMS_NAME)
    if obj is None and create:
        obj = doc.addObject("App::VarSet", PARAMS_NAME)
        obj.Label = "Parameters"
    return obj


def _is_param(obj, name):
    return name in obj.PropertiesList and obj.getGroupOfProperty(name) == _GROUP


def list_parameters(doc):
    """[(name, formula or '', value as text)] in the order FreeCAD lists the properties."""
    obj = parameters(doc, create=False) if doc is not None else None
    if obj is None:
        return []
    formulas = {path.lstrip("."): expr for path, expr in obj.ExpressionEngine}
    return [(name, formulas.get(name, ""), getattr(obj, name).UserString)
            for name in obj.PropertiesList if obj.getGroupOfProperty(name) == _GROUP]


def set_parameter(doc, name, text):
    """Create or update a parameter: a quantity ('80 mm', '12') or a formula ('Width/8').
    Call inside safe.run_safely: a formula that fails to evaluate raises and must be rolled back."""
    if not _NAME_RE.match(name or ""):
        raise ValueError("A parameter name starts with a letter or _ and has only letters, digits and _ (got %r)" % name)
    text = (text or "").strip()
    if not text:
        raise ValueError("Parameter %s needs a value" % name)
    obj = parameters(doc)
    if name in obj.PropertiesList and not _is_param(obj, name):
        raise ValueError("%r is a reserved name" % name)
    if name not in obj.PropertiesList:
        obj.addProperty("App::PropertyQuantity", name, _GROUP)
    try:
        quantity = App.Units.Quantity(text)
    except Exception:
        quantity = None
    if quantity is not None:
        obj.setExpression(name, None)
        setattr(obj, name, quantity)
    else:
        try:
            obj.setExpression(name, text)
        except Exception as e:
            raise ValueError("Invalid formula for %s: %s" % (name, e))
    doc.recompute()
    if "Invalid" in obj.State or "Error" in obj.State:
        raise ValueError("Formula for %s cannot be evaluated: %s" % (name, obj.getStatusString()))


def remove_parameter(doc, name):
    obj = parameters(doc, create=False)
    if obj is None or not _is_param(obj, name):
        raise ValueError("No parameter named %r" % name)
    obj.setExpression(name, None)
    obj.removeProperty(name)
    doc.recompute()
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_parameters.py` → Expected: 10 tests `OK`.
If `test_cycle_is_rolled_back` fails because FreeCAD accepted the cycle without marking the VarSet invalid,
print `obj.State` and `obj.getStatusString()` after `doc.recompute()` in a scratch run; add the extra state
FreeCAD reports to the check in `set_parameter` (the test must keep its expectations).

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/document.py tests/headless/test_parameters.py
git commit -m "InCad: parameters with formulas stored in a VarSet"
```

---

### Task 6: Command registry

**Files:**
- Create: `InCad/incad/core/commands.py`
- Test: `tests/widgets/test_commands.py`

**Interfaces:**
- Consumes: `incad.core.log.report`, `incad.core.safe.SafeResult` / `run_safely` (imported lazily).
- Produces (`incad.core.commands`): `ANY = "any"`; frozen dataclass `Command(id, label, icon, handler, tooltip="",
  shortcut="", contexts=frozenset({"any"}), transactional=False, checkable=False, is_checked=None)`;
  class `Registry` with `register(cmd) -> cmd` (ValueError on duplicate id or a shortcut clash in overlapping
  contexts), `get(id)`, `has(id)`, `ids()`, `for_context(ctx) -> list[Command]`, `run(id) -> SafeResult`
  (never raises); module singleton `REGISTRY`.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_commands.py`:
```python
import unittest

from incad.core import log
from incad.core.commands import ANY, Command, Registry


def cmd(i, **kw):
    kw.setdefault("handler", lambda: i)
    return Command(id=i, label=i.title(), icon="incad", **kw)


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.r = Registry()
        self.messages = []
        log.set_reporter(lambda level, msg: self.messages.append((level, msg)))

    def tearDown(self):
        log.set_reporter(None)

    def test_register_and_get(self):
        c = self.r.register(cmd("file.new"))
        self.assertIs(self.r.get("file.new"), c)
        self.assertTrue(self.r.has("file.new"))
        self.assertEqual(self.r.ids(), ["file.new"])

    def test_duplicate_id(self):
        self.r.register(cmd("a"))
        with self.assertRaises(ValueError):
            self.r.register(cmd("a"))

    def test_shortcut_clash_only_in_overlapping_contexts(self):
        self.r.register(cmd("line", shortcut="L", contexts=frozenset({"sketch"})))
        self.r.register(cmd("loft", shortcut="L", contexts=frozenset({"part"})))
        with self.assertRaises(ValueError):
            self.r.register(cmd("look", shortcut="L", contexts=frozenset({ANY})))

    def test_for_context(self):
        self.r.register(cmd("a"))
        self.r.register(cmd("b", contexts=frozenset({"sketch"})))
        self.r.register(cmd("c", contexts=frozenset({"part"})))
        self.assertEqual([c.id for c in self.r.for_context("sketch")], ["a", "b"])

    def test_run_returns_value(self):
        self.r.register(cmd("a", handler=lambda: 42))
        res = self.r.run("a")
        self.assertTrue(res.ok)
        self.assertEqual(res.value, 42)

    def test_run_never_raises(self):
        self.r.register(cmd("bad", handler=lambda: 1 / 0))
        res = self.r.run("bad")
        self.assertFalse(res.ok)
        self.assertEqual(self.messages[-1][0], "error")
        self.assertFalse(self.r.run("missing").ok)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_commands.py` → Expected: `ModuleNotFoundError: No module named 'incad.core.commands'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/commands.py`:
```python
"""One registry for every InCad command: the ribbon, marking menu, menus and shortcuts all read it."""
import traceback
from dataclasses import dataclass

from incad.core import log

ANY = "any"


@dataclass(frozen=True)
class Command:
    id: str
    label: str
    icon: str                      # icon name in resources/icons/<theme>/<icon>.svg
    handler: object                # callable() -> anything
    tooltip: str = ""
    shortcut: str = ""             # Qt key sequence text, e.g. "Ctrl+N" (shown as ⌘N on macOS)
    contexts: frozenset = frozenset({ANY})
    transactional: bool = False    # True: runs inside safe.run_safely (one undo step, rollback on failure)
    checkable: bool = False
    is_checked: object = None      # callable() -> bool, for checkable commands


class Registry:
    def __init__(self):
        self._cmds = {}

    def register(self, cmd):
        if cmd.id in self._cmds:
            raise ValueError("duplicate command id %r" % cmd.id)
        if cmd.shortcut:
            for other in self._cmds.values():
                if other.shortcut == cmd.shortcut and self._overlap(other.contexts, cmd.contexts):
                    raise ValueError("shortcut %s of %s clashes with %s" % (cmd.shortcut, cmd.id, other.id))
        self._cmds[cmd.id] = cmd
        return cmd

    @staticmethod
    def _overlap(a, b):
        return ANY in a or ANY in b or bool(a & b)

    def get(self, cmd_id):
        return self._cmds[cmd_id]

    def has(self, cmd_id):
        return cmd_id in self._cmds

    def ids(self):
        return list(self._cmds)

    def for_context(self, ctx):
        return [c for c in self._cmds.values() if ANY in c.contexts or ctx in c.contexts]

    def run(self, cmd_id):
        """Run a command. Never raises; returns safe.SafeResult."""
        from incad.core.safe import SafeResult
        cmd = self._cmds.get(cmd_id)
        if cmd is None:
            log.report("error", "Unknown command %s" % cmd_id)
            return SafeResult(False, error="unknown command %s" % cmd_id)
        if cmd.transactional:
            from incad.core import safe
            return safe.run_safely(cmd.label, cmd.handler)
        try:
            return SafeResult(True, cmd.handler())
        except Exception as e:
            log.report("error", "%s failed: %s" % (cmd.label, e), traceback.format_exc())
            return SafeResult(False, error=str(e))


REGISTRY = Registry()
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_commands.py` → Expected: 6 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/commands.py tests/widgets/test_commands.py
git commit -m "InCad: command registry"
```

---

### Task 7: Icons, theme and 3D-view colors

**Files:**
- Create: `tools/make_icons.py`, generated `InCad/incad/resources/icons/{light,dark}/*.svg`,
  `InCad/incad/ui/theme.py`, `InCad/incad/core/params.py`
- Test: `tests/widgets/test_icons.py`, `tests/widgets/test_theme.py`, `tests/headless/test_params.py`

**Interfaces:**
- Produces (`tools/make_icons.py`): `ALL_NAMES` (sorted icon names), `main()`. Icon names: `incad part new open close save
  undo redo theme_toggle freecad settings zoom_all home_view style_shaded style_wireframe parameters origin plane
  axis point sketch feature end_of_part solids`. `theme_toggle` is a moon in light and a sun in dark.
- Produces (`incad.ui.theme`): `PALETTES` (`light`/`dark` dicts with keys `window panel panel_alt border text
  text_dim accent accent_soft selection_text error rolled_back eop view_top view_bottom`), `ICON_PX`,
  `ICON_DIR`, `resolve(pref, system_dark) -> "light"|"dark"`, `system_is_dark() -> bool`,
  `current() -> "light"|"dark"`, `toggled(theme) -> theme`, `icon_path(name, theme)`, `icon(name, theme) -> QIcon`,
  `stylesheet(theme) -> str`, `VIEW_GROUP`, `VIEW_KEYS` (`{name: kind}`), `view_params(theme) -> {name: (kind, value)}`.
- Produces (`incad.core.params`): `snapshot(group, names_kinds) -> {name: [kind, existed, value]}`,
  `write(group, values)`, `restore(group, snapshot)`. Kinds: `"Bool" | "Unsigned" | "String" | "Int" | "Float"`.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_icons.py`:
```python
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
```

`tests/widgets/test_theme.py`:
```python
import unittest

from incad.core import prefs
from incad.ui import theme


class ThemeTest(unittest.TestCase):
    def setUp(self):
        prefs.use_memory_backend()

    def test_resolve(self):
        self.assertEqual(theme.resolve("auto", True), "dark")
        self.assertEqual(theme.resolve("auto", False), "light")
        self.assertEqual(theme.resolve("light", True), "light")
        self.assertEqual(theme.resolve("dark", False), "dark")

    def test_toggled(self):
        self.assertEqual(theme.toggled("light"), "dark")
        self.assertEqual(theme.toggled("dark"), "light")

    def test_current_uses_pref(self):
        prefs.set_theme("dark")
        self.assertEqual(theme.current(), "dark")

    def test_stylesheet_filled_in(self):
        for t in ("light", "dark"):
            qss = theme.stylesheet(t)
            self.assertIn(theme.PALETTES[t]["panel"], qss)
            self.assertIn("#InCadRibbon", qss)
            self.assertNotIn("{panel}", qss)

    def test_palettes_have_same_keys(self):
        self.assertEqual(set(theme.PALETTES["light"]), set(theme.PALETTES["dark"]))

    def test_view_params(self):
        v = theme.view_params("dark")
        self.assertEqual(v["Gradient"], ("Bool", True))
        self.assertEqual(v["BackgroundColor2"], ("Unsigned", 0x2B3440FF))
        self.assertEqual(set(v), set(theme.VIEW_KEYS))

    def test_icon_px(self):
        self.assertEqual(theme.ICON_PX, {"small": 16, "medium": 24, "large": 32})
```

`tests/headless/test_params.py`:
```python
import unittest

import FreeCAD as App
from incad.core import params

GROUP = "User parameter:BaseApp/Preferences/Mod/InCadTest"


class ParamsTest(unittest.TestCase):
    def test_snapshot_write_restore(self):
        p = App.ParamGet(GROUP)
        p.SetBool("Flag", True)
        p.SetUnsigned("Color", 0x112233FF)
        snap = params.snapshot(GROUP, {"Flag": "Bool", "Color": "Unsigned", "New": "String"})
        self.assertEqual(snap["Flag"], ["Bool", True, True])
        self.assertEqual(snap["New"], ["String", False, None])
        params.write(GROUP, {"Flag": ("Bool", False), "Color": ("Unsigned", 0xAABBCCFF), "New": ("String", "x")})
        self.assertFalse(p.GetBool("Flag", True))
        params.restore(GROUP, snap)
        self.assertTrue(p.GetBool("Flag", False))
        self.assertEqual(p.GetUnsigned("Color", 0), 0x112233FF)
        names = {c[1] for c in (p.GetContents() or [])}
        self.assertNotIn("New", names)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_icons.py`, `tests/run_widgets.sh test_theme.py`, `tests/run_headless.sh test_params.py`
Expected: `ModuleNotFoundError` for `make_icons`, `incad.ui.theme`, `incad.core.params`.

- [ ] **Step 3: Write the icon generator and generate**

`tools/make_icons.py`:
```python
"""Generates InCad's SVG icons in light and dark variants into InCad/incad/resources/icons/{light,dark}/.
Run: python3 tools/make_icons.py   (any Python 3; no dependencies)"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "InCad", "incad", "resources", "icons")

# S stroke/main, F fill, A accent (orange), N neutral, D datum/origin (amber), R red (End of Part)
PALETTE = {
    "light": dict(S="#0a64d6", F="#9cc6f3", A="#e67e22", N="#555555", D="#c07a00", R="#b00020"),
    "dark": dict(S="#5aa2ff", F="#2a5d99", A="#f39c4a", N="#cccccc", D="#e0a030", R="#ff6b7f"),
}

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">%s</svg>\n'

BLOCK = ('<path d="M4 11 L16 5 L28 11 L16 17 Z" fill="{F}" stroke="{S}" stroke-width="1.5"/>'
         '<path d="M4 11 V21 L16 27 V17 Z" fill="{S}" fill-opacity=".55" stroke="{S}" stroke-width="1.5"/>'
         '<path d="M28 11 V21 L16 27 V17 Z" fill="{S}" stroke="{S}" stroke-width="1.5"/>')
SUN = ('<circle cx="16" cy="16" r="6" fill="{A}"/><path d="M16 3 V6 M16 26 V29 M3 16 H6 M26 16 H29 '
       'M6.8 6.8 L9 9 M23 23 L25.2 25.2 M6.8 25.2 L9 23 M23 9 L25.2 6.8" stroke="{A}" stroke-width="2.2" '
       'stroke-linecap="round"/>')
MOON = '<path d="M20 4 A12 12 0 1 0 28 20 A9 9 0 0 1 20 4 Z" fill="{S}"/>'

ICONS = {
    "incad": BLOCK + '<ellipse cx="16" cy="11" rx="4" ry="2" fill="{N}"/>',
    "part": BLOCK,
    "new": ('<path d="M8 3 H19 L25 9 V29 H8 Z" fill="none" stroke="{N}" stroke-width="1.6"/>'
            '<path d="M19 3 V9 H25" fill="none" stroke="{N}" stroke-width="1.6"/>'
            '<path d="M16.5 14 V24 M11.5 19 H21.5" stroke="{A}" stroke-width="2.4" stroke-linecap="round"/>'),
    "open": ('<path d="M3 9 H12 L14 11 H27 V26 H3 Z" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
             '<path d="M3 14 H29 L26 26 H3 Z" fill="{S}" fill-opacity=".35" stroke="{S}" stroke-width="1.6"/>'),
    "close": '<path d="M9 9 L23 23 M23 9 L9 23" stroke="{N}" stroke-width="2.6" stroke-linecap="round"/>',
    "save": ('<rect x="5" y="5" width="22" height="22" rx="2" fill="none" stroke="{S}" stroke-width="1.8"/>'
             '<rect x="10" y="5" width="12" height="8" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
             '<rect x="9" y="18" width="14" height="9" fill="{S}" fill-opacity=".3"/>'),
    "undo": ('<path d="M12 8 L5 14 L12 20" fill="none" stroke="{S}" stroke-width="2.4" stroke-linecap="round" '
             'stroke-linejoin="round"/><path d="M5 14 H19 A7 7 0 0 1 19 28 H14" fill="none" stroke="{S}" '
             'stroke-width="2.4" stroke-linecap="round"/>'),
    "redo": ('<path d="M20 8 L27 14 L20 20" fill="none" stroke="{S}" stroke-width="2.4" stroke-linecap="round" '
             'stroke-linejoin="round"/><path d="M27 14 H13 A7 7 0 0 0 13 28 H18" fill="none" stroke="{S}" '
             'stroke-width="2.4" stroke-linecap="round"/>'),
    "freecad": ('<path d="M5 11 H25 M20 6 L25 11 L20 16" fill="none" stroke="{S}" stroke-width="2.4" '
                'stroke-linecap="round" stroke-linejoin="round"/><path d="M27 21 H7 M12 16 L7 21 L12 26" '
                'fill="none" stroke="{A}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'),
    "settings": ('<circle cx="16" cy="16" r="10" fill="none" stroke="{N}" stroke-width="5" stroke-dasharray="4 3.85"/>'
                 '<circle cx="16" cy="16" r="7.5" fill="none" stroke="{N}" stroke-width="2.5"/>'
                 '<circle cx="16" cy="16" r="3" fill="{N}"/>'),
    "zoom_all": ('<rect x="8" y="8" width="16" height="16" fill="none" stroke="{N}" stroke-width="1.5" '
                 'stroke-dasharray="3 2"/><path d="M4 10 V4 H10 M22 4 H28 V10 M28 22 V28 H22 M10 28 H4 V22" '
                 'fill="none" stroke="{S}" stroke-width="2.4"/>'),
    "home_view": ('<path d="M4 16 L16 5 L28 16" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/>'
                  '<path d="M8 14 V27 H24 V14" fill="{F}" stroke="{S}" stroke-width="2"/>'
                  '<rect x="13" y="19" width="6" height="8" fill="{S}"/>'),
    "style_shaded": ('<path d="M5 11 L16 5 L27 11 L16 17 Z" fill="{F}" stroke="{N}" stroke-width="1.4"/>'
                     '<path d="M5 11 V22 L16 28 V17 Z" fill="{S}" fill-opacity=".6" stroke="{N}" stroke-width="1.4"/>'
                     '<path d="M27 11 V22 L16 28 V17 Z" fill="{S}" stroke="{N}" stroke-width="1.4"/>'),
    "style_wireframe": ('<path d="M5 11 L16 5 L27 11 L16 17 Z M5 11 V22 L16 28 V17 M27 11 V22 L16 28" fill="none" '
                        'stroke="{S}" stroke-width="1.6"/><path d="M5 22 L16 16 L27 22 M16 5 V16" fill="none" '
                        'stroke="{N}" stroke-width="1" stroke-dasharray="2 2"/>'),
    "parameters": ('<text x="4" y="23" font-family="Georgia, serif" font-style="italic" font-size="18" '
                   'fill="{S}">f</text><text x="13" y="23" font-family="Helvetica" font-size="13" fill="{A}">(x)</text>'),
    "origin": '<path d="M3 9 H12 L14 11 H29 V26 H3 Z" fill="{D}" fill-opacity=".35" stroke="{D}" stroke-width="1.6"/>',
    "plane": '<path d="M3 21 L14 27 L29 18 L18 12 Z" fill="{D}" fill-opacity=".45" stroke="{D}" stroke-width="1.6"/>',
    "axis": '<path d="M5 27 L27 5" stroke="{D}" stroke-width="2.4" stroke-linecap="round"/>',
    "point": '<circle cx="16" cy="16" r="4.5" fill="{D}"/>',
    "sketch": ('<rect x="5" y="9" width="20" height="16" fill="none" stroke="{S}" stroke-width="1.6"/>'
               '<path d="M5 25 L25 9" stroke="{S}" stroke-width="1.2"/><circle cx="25" cy="9" r="3" fill="{A}"/>'),
    "feature": ('<path d="M6 22 L6 12 L16 8 L26 11 L26 21 L14 25 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M6 12 L14 15 L26 11 M14 15 L14 25" fill="none" stroke="{S}" stroke-width="1.2"/>'),
    "end_of_part": '<rect x="6" y="6" width="20" height="20" rx="2" fill="{R}"/><rect x="11" y="11" width="10" height="10" fill="#ffffff"/>',
    "solids": '<path d="M3 9 H12 L14 11 H29 V26 H3 Z" fill="{F}" stroke="{S}" stroke-width="1.6"/>',
}

PER_THEME = {"theme_toggle": {"light": MOON, "dark": SUN}}  # shows what a click switches to

ALL_NAMES = sorted(list(ICONS) + list(PER_THEME))


def render(body, theme):
    return SVG % body.format(**PALETTE[theme])


def main():
    for theme in PALETTE:
        folder = os.path.join(OUT, theme)
        os.makedirs(folder, exist_ok=True)
        bodies = dict(ICONS)
        bodies.update({name: variants[theme] for name, variants in PER_THEME.items()})
        for name, body in bodies.items():
            with open(os.path.join(folder, name + ".svg"), "w") as f:
                f.write(render(body, theme))
    print("wrote %d icons per theme to %s" % (len(ALL_NAMES), OUT))


if __name__ == "__main__":
    main()
```

Run: `python3 tools/make_icons.py` → Expected: `wrote 25 icons per theme to …/InCad/incad/resources/icons`.
Run: `find InCad/incad/resources -name '._*' -delete` (macOS metadata files on the exFAT volume).

- [ ] **Step 4: Implement theme and params**

`InCad/incad/ui/theme.py`:
```python
"""Light/dark palettes, the InCad Qt stylesheet, icons and the 3D-view background colors."""
import os

from incad.core import prefs

PALETTES = {
    "light": dict(window="#ececec", panel="#f7f7f7", panel_alt="#f3f3f3", border="#c8c8c8", text="#1d1d1f",
                  text_dim="#888888", accent="#0a64d6", accent_soft="#dbe9fb", selection_text="#ffffff",
                  error="#b00020", rolled_back="#999999", eop="#b00020",
                  view_top="#cfd8e3", view_bottom="#f4f6f9"),
    "dark": dict(window="#1e1e1e", panel="#323234", panel_alt="#262628", border="#111111", text="#e6e6e6",
                 text_dim="#888888", accent="#5aa2ff", accent_soft="#1f3b5e", selection_text="#ffffff",
                 error="#ff6b7f", rolled_back="#777777", eop="#ff6b7f",
                 view_top="#2b3440", view_bottom="#14181e"),
}
ICON_PX = {"small": 16, "medium": 24, "large": 32}
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "icons")

STYLE = """
QWidget#InCadTitle {{ background: {window}; color: {text}; border-bottom: 1px solid {border}; }}
QLabel#InCadDocName {{ color: {text}; font-weight: 600; }}
QWidget#InCadRibbon {{ background: {panel}; color: {text}; border-bottom: 1px solid {border}; }}
QTabBar#InCadRibbonTabs {{ background: {window}; }}
QTabBar#InCadRibbonTabs::tab {{ background: {window}; color: {text}; padding: 5px 14px; border: none; }}
QTabBar#InCadRibbonTabs::tab:selected {{ background: {panel}; color: {accent}; font-weight: 600; }}
QFrame#InCadRibbonGroup {{ border: none; border-right: 1px solid {border}; }}
QLabel#InCadRibbonGroupLabel {{ color: {text_dim}; font-size: 10px; }}
QToolButton {{ color: {text}; border: none; border-radius: 6px; padding: 3px; background: transparent; }}
QToolButton:hover {{ background: {accent_soft}; }}
QToolButton:checked {{ background: {accent_soft}; }}
QWidget#InCadBrowser {{ background: {panel_alt}; color: {text}; }}
QTreeWidget#InCadTree, QTableWidget#InCadParams {{ background: {panel_alt}; color: {text}; border: none; }}
QTreeWidget#InCadTree::item:selected {{ background: {accent}; color: {selection_text}; }}
QLabel#InCadPanelHeader {{ color: {text_dim}; font-weight: 600; font-size: 11px; padding: 6px 8px; }}
QHeaderView::section {{ background: {panel}; color: {text_dim}; border: none; padding: 2px 6px; }}
QWidget#InCadStatus {{ background: {window}; color: {text_dim}; border-top: 1px solid {border}; }}
QWidget#InCadStatus QLabel {{ color: {text_dim}; padding: 0 8px; }}
QDialog#InCadNewDialog {{ background: {panel}; color: {text}; }}
QDialog#InCadNewDialog QLabel, QDialog#InCadNewDialog QCheckBox {{ color: {text}; }}
QPushButton#InCadTile {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 9px; padding: 12px; }}
QPushButton#InCadTile:checked {{ border: 2px solid {accent}; }}
QPushButton#InCadTile:disabled {{ color: {text_dim}; }}
"""

VIEW_GROUP = "User parameter:BaseApp/Preferences/View"
VIEW_KEYS = {"Simple": "Bool", "Gradient": "Bool", "RadialGradient": "Bool", "UseBackgroundColorMid": "Bool",
             "BackgroundColor2": "Unsigned", "BackgroundColor3": "Unsigned"}


def resolve(pref, system_dark):
    if pref in ("light", "dark"):
        return pref
    return "dark" if system_dark else "light"


def system_is_dark():
    from incad.qt import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None:
        return False
    return app.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark


def current():
    return resolve(prefs.theme(), system_is_dark())


def toggled(theme):
    return "light" if theme == "dark" else "dark"


def icon_path(name, theme):
    return os.path.join(ICON_DIR, theme, name + ".svg")


def icon(name, theme):
    from incad.qt import QtGui
    return QtGui.QIcon(icon_path(name, theme))


def stylesheet(theme):
    return STYLE.format(**PALETTES[theme])


def _rgba(hex_color):
    return (int(hex_color.lstrip("#"), 16) << 8) | 0xFF


def view_params(theme):
    """FreeCAD 'View' parameters that give the 3D view InCad's gradient background."""
    p = PALETTES[theme]
    return {"Simple": ("Bool", False), "Gradient": ("Bool", True), "RadialGradient": ("Bool", False),
            "UseBackgroundColorMid": ("Bool", False),
            "BackgroundColor2": ("Unsigned", _rgba(p["view_top"])),
            "BackgroundColor3": ("Unsigned", _rgba(p["view_bottom"]))}
```

`InCad/incad/core/params.py`:
```python
"""Save, write and restore FreeCAD parameter values (InCad changes a few 'View' colors while active)."""
import FreeCAD as App


def _names(p):
    return {c[1] for c in (p.GetContents() or [])}


def snapshot(group, names_kinds):
    """{name: [kind, existed, value]} for each name in names_kinds ({name: kind})."""
    p = App.ParamGet(group)
    present = _names(p)
    return {name: [kind, name in present, getattr(p, "Get" + kind)(name) if name in present else None]
            for name, kind in names_kinds.items()}


def write(group, values):
    """values: {name: (kind, value)}"""
    p = App.ParamGet(group)
    for name, (kind, value) in values.items():
        getattr(p, "Set" + kind)(name, value)


def restore(group, snap):
    p = App.ParamGet(group)
    for name, (kind, existed, value) in snap.items():
        if existed:
            getattr(p, "Set" + kind)(name, value)
        else:
            getattr(p, "Rem" + kind)(name)
```

- [ ] **Step 5: Run to verify they pass**

Run: `tests/run_widgets.sh test_icons.py`, `tests/run_widgets.sh test_theme.py`, `tests/run_headless.sh test_params.py`
Expected: all `OK`. Open two icons to eyeball them: `qlmanage -p InCad/incad/resources/icons/light/feature.svg`.

- [ ] **Step 6: Commit**

```bash
git add tools/make_icons.py InCad/incad/resources InCad/incad/ui/theme.py InCad/incad/core/params.py tests/widgets/test_icons.py tests/widgets/test_theme.py tests/headless/test_params.py
git commit -m "InCad: icon set (light/dark), theme palettes and stylesheet, parameter snapshots"
```

---

### Task 8: Ribbon

**Files:**
- Create: `InCad/incad/ui/ribbon_layout.py`, `InCad/incad/ui/ribbon.py`
- Test: `tests/widgets/test_ribbon.py`

**Interfaces:**
- Consumes: `commands.Registry`/`Command` (Task 6), `theme.icon`, `theme.ICON_PX` (Task 7).
- Produces (`incad.ui.ribbon_layout`): `LAYOUT = {mode: [[tab, [[group, [cmd_ids]]]]]}` with modes `"part"` and
  `"empty"`; `add_group(mode, tab, group, cmd_ids, layout=None)`.
- Produces (`incad.ui.ribbon.Ribbon(registry, layout, mode="part", size="large", theme="light", parent=None)`):
  signal `sizeChanged(str)`; `set_mode(mode)`, `set_size(size)` (ValueError if unknown), `set_theme(theme)`,
  `rebuild()`, `refresh_checks()`, `tab_names() -> list[str]`, `current_tab() -> str`, `button(cmd_id) -> QToolButton|None`,
  `current_size() -> str`, `size_menu(parent) -> QMenu` (Small/Medium/Large, checkable). Tabs or groups whose
  commands are all unregistered are not shown. Right-click on the ribbon opens the size menu.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_ribbon.py`:
```python
import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.core.commands import Command, Registry
from incad.ui import ribbon_layout
from incad.ui.ribbon import Ribbon


class RibbonTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.checked = False
        self.reg = Registry()
        for i in ("a", "b", "c"):
            self.reg.register(Command(id=i, label=i.upper(), icon="incad", handler=lambda i=i: self.ran.append(i)))
        self.reg.register(Command(id="t", label="Toggle", icon="incad", handler=lambda: None,
                                  checkable=True, is_checked=lambda: self.checked))
        self.layout = {
            "part": [["Model", [["G1", ["a", "missing"]], ["Empty", ["missing"]]]],
                     ["Nothing", [["G", ["missing"]]]],
                     ["View", [["G2", ["b", "c", "t"]]]]],
            "empty": [["Start", [["New", ["a"]]]]],
        }
        self.rb = Ribbon(self.reg, self.layout, mode="part", size="large", theme="light")

    def test_tabs_skip_empty(self):
        self.assertEqual(self.rb.tab_names(), ["Model", "View"])

    def test_buttons_and_click(self):
        self.rb.button("a").click()
        self.assertEqual(self.ran, ["a"])
        self.assertIsNone(self.rb.button("missing"))

    def test_sizes(self):
        cases = (("small", 16, QtCore.Qt.ToolButtonIconOnly),
                 ("medium", 24, QtCore.Qt.ToolButtonTextUnderIcon),
                 ("large", 32, QtCore.Qt.ToolButtonTextUnderIcon))
        for size, px, style in cases:
            self.rb.set_size(size)
            b = self.rb.button("a")
            self.assertEqual(b.iconSize().width(), px, size)
            self.assertEqual(b.toolButtonStyle(), style, size)
            self.assertEqual(self.rb.current_size(), size)

    def test_size_signal_once_per_change(self):
        seen = []
        self.rb.sizeChanged.connect(seen.append)
        self.rb.set_size("small")
        self.rb.set_size("small")
        self.assertEqual(seen, ["small"])

    def test_bad_size(self):
        with self.assertRaises(ValueError):
            self.rb.set_size("huge")

    def test_theme_rebuild_keeps_tab(self):
        self.rb._tabs.setCurrentIndex(1)
        self.rb.set_theme("dark")
        self.assertEqual(self.rb.current_tab(), "View")

    def test_mode_switch(self):
        self.rb.set_mode("empty")
        self.assertEqual(self.rb.tab_names(), ["Start"])
        self.rb.set_mode("sketch")
        self.assertEqual(self.rb.tab_names(), [])

    def test_size_menu(self):
        m = self.rb.size_menu(None)
        acts = m.actions()
        self.assertEqual([a.text() for a in acts], ["Small", "Medium", "Large"])
        self.assertEqual([a.isChecked() for a in acts], [False, False, True])
        acts[0].trigger()
        self.assertEqual(self.rb.current_size(), "small")

    def test_checkable_reflects_state(self):
        self.assertFalse(self.rb.button("t").isChecked())
        self.checked = True
        self.rb.refresh_checks()
        self.assertTrue(self.rb.button("t").isChecked())

    def test_add_group(self):
        layout = {"part": [["Model", []]]}
        ribbon_layout.add_group("part", "Model", "Sketch", ["a"], layout)
        ribbon_layout.add_group("part", "Inspect", "Measure", ["b"], layout)
        self.assertEqual(layout, {"part": [["Model", [["Sketch", ["a"]]]], ["Inspect", [["Measure", ["b"]]]]]})
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_ribbon.py` → Expected: `ModuleNotFoundError: No module named 'incad.ui.ribbon_layout'`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/ribbon_layout.py`:
```python
"""Which commands sit on which ribbon tab and group, per mode. Later plans add groups with add_group().
Modes: 'part' (an InCad Part is active), 'empty' (no document, or a file not made in InCad);
'sketch' and 'assembly' arrive with later plans."""

LAYOUT = {
    "part": [
        ["3D Model", []],
        ["Sketch", []],
        ["Inspect", []],
        ["Tools", [["Options", ["view.freecad"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]],
                  ["Navigate", ["view.zoom_all", "view.home"]],
                  ["Visual Style", ["view.style_shaded", "view.style_wireframe"]],
                  ["Windows", ["view.parameters"]]]],
    ],
    "empty": [
        ["Get Started", [["New", ["file.new", "file.open"]]]],
        ["View", [["Appearance", ["view.theme_toggle"]]]],
    ],
}


def add_group(mode, tab, group, cmd_ids, layout=None):
    """Append a group of commands to a tab (the tab is created at the end if missing)."""
    layout = LAYOUT if layout is None else layout
    tabs = layout.setdefault(mode, [])
    for name, groups in tabs:
        if name == tab:
            groups.append([group, list(cmd_ids)])
            return
    tabs.append([tab, [[group, list(cmd_ids)]]])
```

`InCad/incad/ui/ribbon.py`:
```python
"""The ribbon: a tab bar over a row of command groups, drawn from the command registry and a layout."""
from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes

SIZES = ("small", "medium", "large")


class Ribbon(QtWidgets.QWidget):
    sizeChanged = Signal(str)

    def __init__(self, registry, layout, mode="part", size="large", theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadRibbon")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        if size not in SIZES:
            raise ValueError("unknown ribbon size %r" % size)
        self._registry, self._layout = registry, layout
        self._mode, self._size, self._theme = mode, size, theme
        self._buttons = {}
        self._tabs = QtWidgets.QTabBar(self)
        self._tabs.setObjectName("InCadRibbonTabs")
        self._tabs.setDrawBase(False)
        self._tabs.setExpanding(False)
        self._stack = QtWidgets.QStackedWidget(self)
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._tabs)
        col.addWidget(self._stack)
        self._tabs.currentChanged.connect(self._stack.setCurrentIndex)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.rebuild()

    # ----- public -----
    def set_mode(self, mode):
        if mode != self._mode:
            self._mode = mode
            self.rebuild()

    def set_size(self, size):
        if size not in SIZES:
            raise ValueError("unknown ribbon size %r" % size)
        if size != self._size:
            self._size = size
            self.rebuild()
            self.sizeChanged.emit(size)

    def set_theme(self, theme):
        if theme != self._theme:
            self._theme = theme
            self.rebuild()

    def current_size(self):
        return self._size

    def tab_names(self):
        return [self._tabs.tabText(i) for i in range(self._tabs.count())]

    def current_tab(self):
        i = self._tabs.currentIndex()
        return self._tabs.tabText(i) if i >= 0 else ""

    def button(self, cmd_id):
        return self._buttons.get(cmd_id)

    def refresh_checks(self):
        for cmd_id, b in self._buttons.items():
            cmd = self._registry.get(cmd_id)
            if cmd.checkable:
                b.setChecked(bool(cmd.is_checked and cmd.is_checked()))

    def size_menu(self, parent):
        menu = QtWidgets.QMenu("Ribbon Size", parent)
        for size in SIZES:
            act = menu.addAction(size.capitalize())
            act.setCheckable(True)
            act.setChecked(size == self._size)
            act.triggered.connect(lambda _=False, s=size: self.set_size(s))
        return menu

    def rebuild(self):
        keep = self.current_tab()
        self._tabs.blockSignals(True)
        while self._tabs.count():
            self._tabs.removeTab(0)
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        self._buttons = {}
        for tab_name, groups in self._layout.get(self._mode, []):
            page = self._build_page(groups)
            if page is not None:
                self._stack.addWidget(page)
                self._tabs.addTab(tab_name)
        self._tabs.blockSignals(False)
        names = self.tab_names()
        index = names.index(keep) if keep in names else 0
        if names:
            self._tabs.setCurrentIndex(index)
            self._stack.setCurrentIndex(index)

    # ----- internals -----
    def _build_page(self, groups):
        page = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(page)
        row.setContentsMargins(6, 4, 6, 0)
        row.setSpacing(0)
        count = 0
        for group_name, ids in groups:
            cmds = [self._registry.get(i) for i in ids if self._registry.has(i)]
            if cmds:
                row.addWidget(self._build_group(group_name, cmds))
                count += 1
        if not count:
            page.deleteLater()
            return None
        row.addStretch(1)
        return page

    def _build_group(self, name, cmds):
        frame = QtWidgets.QFrame()
        frame.setObjectName("InCadRibbonGroup")
        col = QtWidgets.QVBoxLayout(frame)
        col.setContentsMargins(6, 0, 6, 0)
        col.setSpacing(2)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(2)
        px = themes.ICON_PX[self._size]
        for cmd in cmds:
            b = QtWidgets.QToolButton(frame)
            b.setIcon(themes.icon(cmd.icon, self._theme))
            b.setIconSize(QtCore.QSize(px, px))
            b.setText(cmd.label)
            b.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if self._size == "small"
                                 else QtCore.Qt.ToolButtonTextUnderIcon)
            tip = cmd.label
            if cmd.shortcut:
                tip += " (%s)" % QtGui.QKeySequence(cmd.shortcut).toString(QtGui.QKeySequence.NativeText)
            if cmd.tooltip:
                tip += "\n" + cmd.tooltip
            b.setToolTip(tip)
            b.setAutoRaise(True)
            if cmd.checkable:
                b.setCheckable(True)
                b.setChecked(bool(cmd.is_checked and cmd.is_checked()))
            b.clicked.connect(lambda _=False, i=cmd.id: self._run(i))
            row.addWidget(b)
            self._buttons[cmd.id] = b
        col.addLayout(row)
        if self._size != "small":
            label = QtWidgets.QLabel(name)
            label.setObjectName("InCadRibbonGroupLabel")
            label.setAlignment(QtCore.Qt.AlignHCenter)
            col.addWidget(label)
        return frame

    def _run(self, cmd_id):
        self._registry.run(cmd_id)
        self.refresh_checks()

    def _context_menu(self, pos):
        self.size_menu(self).exec(self.mapToGlobal(pos))
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_ribbon.py` → Expected: 10 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/ribbon_layout.py InCad/incad/ui/ribbon.py tests/widgets/test_ribbon.py
git commit -m "InCad: ribbon widget with layout, sizes and theme"
```

---

### Task 9: Title strip and status bar

**Files:**
- Create: `InCad/incad/ui/titlebar.py`, `InCad/incad/ui/statusbar.py`
- Test: `tests/widgets/test_titlebar_status.py`

**Interfaces:**
- Consumes: `commands.Registry`, `theme.icon`, `theme.PALETTES`.
- Produces (`incad.ui.titlebar.TitleStrip(registry, theme="light", settings_menu=None, parent=None)`):
  `QUICK = ("file.new", "file.open", "file.save", "edit.undo", "edit.redo")`, `RIGHT = ("view.theme_toggle", "view.freecad")`;
  `button(cmd_id)`, `settings_button`, `set_document_name(text)`, `document_name()`, `set_theme(theme)`,
  `build_settings_menu() -> QMenu|None` (calls `settings_menu(parent)`). Unregistered command ids are skipped.
- Produces (`incad.ui.statusbar.StatusBar(theme="light", parent=None)`): `set_prompt(text)`,
  `show_message(level, text, timeout_ms=8000)`, `clear_message()`, `set_units("mm"|"in"|None)`,
  `set_dof(int|None)`, `set_stats(solids|None, features|None)`, `set_theme(theme)`,
  `texts() -> {"prompt", "message", "units", "dof", "stats"}` (hidden parts are "").

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_titlebar_status.py`:
```python
import unittest

from widgets import qtapp
from incad.core.commands import Command, Registry
from incad.ui.statusbar import StatusBar
from incad.ui.titlebar import TitleStrip


class TitleStripTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.reg = Registry()
        for i in ("file.new", "file.save", "view.freecad", "view.theme_toggle"):
            self.reg.register(Command(id=i, label=i, icon="incad", handler=lambda i=i: self.ran.append(i)))
        self.made = []

        def factory(parent):
            from incad.qt import QtWidgets
            m = QtWidgets.QMenu(parent)
            m.addAction("Theme")
            self.made.append(m)
            return m

        self.ts = TitleStrip(self.reg, "light", factory)

    def test_buttons_run_commands(self):
        self.ts.button("file.save").click()
        self.ts.button("view.freecad").click()
        self.assertEqual(self.ran, ["file.save", "view.freecad"])
        self.assertIsNone(self.ts.button("file.open"))

    def test_freecad_button_has_text(self):
        self.assertEqual(self.ts.button("view.freecad").text(), "FreeCAD")

    def test_document_name(self):
        self.ts.set_document_name("Bracket")
        self.assertEqual(self.ts.document_name(), "Bracket")

    def test_settings_menu(self):
        m = self.ts.build_settings_menu()
        self.assertEqual([a.text() for a in m.actions()], ["Theme"])

    def test_theme_switch_keeps_buttons(self):
        self.ts.set_theme("dark")
        self.assertFalse(self.ts.button("file.new").icon().isNull())


class StatusBarTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.sb = StatusBar("light")

    def test_initial(self):
        self.assertEqual(self.sb.texts(), {"prompt": "", "message": "", "units": "", "dof": "", "stats": ""})

    def test_fields(self):
        self.sb.set_prompt("Select a plane")
        self.sb.set_units("in")
        self.sb.set_dof(3)
        self.sb.set_stats(2, 5)
        self.assertEqual(self.sb.texts(), {"prompt": "Select a plane", "message": "", "units": "in · deg",
                                           "dof": "DOF: 3", "stats": "2 solids · 5 features"})
        self.sb.set_dof(0)
        self.assertEqual(self.sb.texts()["dof"], "Fully constrained ✓")
        self.sb.set_stats(1, 1)
        self.assertEqual(self.sb.texts()["stats"], "1 solid · 1 feature")
        self.sb.set_dof(None)
        self.sb.set_stats(None, None)
        self.sb.set_units(None)
        self.assertEqual((self.sb.texts()["dof"], self.sb.texts()["stats"], self.sb.texts()["units"]), ("", "", ""))

    def test_message_and_clear(self):
        self.sb.show_message("error", "Fillet failed")
        self.assertEqual(self.sb.texts()["message"], "Fillet failed")
        self.sb.clear_message()
        self.assertEqual(self.sb.texts()["message"], "")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_titlebar_status.py` → Expected: `ModuleNotFoundError: No module named 'incad.ui.statusbar'`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/titlebar.py`:
```python
"""Title strip under the macOS title bar: quick-access buttons, document name, theme toggle, ⇄ FreeCAD, ⚙."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes


class TitleStrip(QtWidgets.QWidget):
    QUICK = ("file.new", "file.open", "file.save", "edit.undo", "edit.redo")
    RIGHT = ("view.theme_toggle", "view.freecad")

    def __init__(self, registry, theme="light", settings_menu=None, parent=None):
        super().__init__(parent)
        self.setObjectName("InCadTitle")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._registry, self._theme, self._settings_menu = registry, theme, settings_menu
        self._buttons = {}
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(8, 3, 8, 3)
        row.setSpacing(4)
        for cmd_id in self.QUICK:
            self._add(row, cmd_id, with_text=False)
        row.addStretch(1)
        self._name = QtWidgets.QLabel("")
        self._name.setObjectName("InCadDocName")
        row.addWidget(self._name)
        row.addStretch(1)
        for cmd_id in self.RIGHT:
            self._add(row, cmd_id, with_text=(cmd_id == "view.freecad"))
        self.settings_button = QtWidgets.QToolButton(self)
        self.settings_button.setAutoRaise(True)
        self.settings_button.setToolTip("InCad settings")
        self.settings_button.setIcon(themes.icon("settings", theme))
        self.settings_button.setIconSize(QtCore.QSize(18, 18))
        self.settings_button.clicked.connect(self._open_settings)
        row.addWidget(self.settings_button)

    def _add(self, row, cmd_id, with_text):
        if not self._registry.has(cmd_id):
            return
        cmd = self._registry.get(cmd_id)
        b = QtWidgets.QToolButton(self)
        b.setAutoRaise(True)
        b.setIcon(themes.icon(cmd.icon, self._theme))
        b.setIconSize(QtCore.QSize(18, 18))
        b.setToolTip(cmd.label)
        if with_text:
            b.setText("FreeCAD")
            b.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        b.clicked.connect(lambda _=False, i=cmd_id: self._registry.run(i))
        row.addWidget(b)
        self._buttons[cmd_id] = b

    def button(self, cmd_id):
        return self._buttons.get(cmd_id)

    def set_document_name(self, text):
        self._name.setText(text)

    def document_name(self):
        return self._name.text()

    def set_theme(self, theme):
        self._theme = theme
        for cmd_id, b in self._buttons.items():
            b.setIcon(themes.icon(self._registry.get(cmd_id).icon, theme))
        self.settings_button.setIcon(themes.icon("settings", theme))

    def build_settings_menu(self):
        return self._settings_menu(self) if self._settings_menu else None

    def _open_settings(self):
        menu = self.build_settings_menu()
        if menu is not None:
            menu.exec(self.settings_button.mapToGlobal(QtCore.QPoint(0, self.settings_button.height())))
```

`InCad/incad/ui/statusbar.py`:
```python
"""InCad status bar: next-step prompt, messages, units, sketch DOF, part statistics."""
from incad.qt import QtCore, QtWidgets
from incad.ui import theme as themes

UNIT_TEXT = {"mm": "mm · deg", "in": "in · deg"}


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


class StatusBar(QtWidgets.QWidget):
    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadStatus")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._theme = theme
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(4, 2, 4, 2)
        self._prompt = QtWidgets.QLabel("")
        self._message = QtWidgets.QLabel("")
        self._units = QtWidgets.QLabel("")
        self._dof = QtWidgets.QLabel("")
        self._stats = QtWidgets.QLabel("")
        row.addWidget(self._prompt)
        row.addWidget(self._message)
        row.addStretch(1)
        for w in (self._units, self._dof, self._stats):
            row.addWidget(w)
        for w in (self._message, self._units, self._dof, self._stats):
            w.hide()
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear_message)

    def set_prompt(self, text):
        self._prompt.setText(text)

    def show_message(self, level, text, timeout_ms=8000):
        p = themes.PALETTES[self._theme]
        color = {"error": p["error"], "warning": p["accent"]}.get(level, p["text"])
        self._message.setStyleSheet("color: %s; font-weight: 600;" % color)
        self._message.setText(text)
        self._message.setToolTip(text)
        self._message.show()
        self._timer.start(timeout_ms)

    def clear_message(self):
        self._message.setText("")
        self._message.hide()

    def _show(self, label, text):
        label.setText(text)
        label.setVisible(bool(text))

    def set_units(self, units):
        self._show(self._units, UNIT_TEXT.get(units, ""))

    def set_dof(self, dof):
        self._show(self._dof, "" if dof is None else ("Fully constrained ✓" if dof == 0 else "DOF: %d" % dof))

    def set_stats(self, solids, features):
        text = "" if solids is None else "%s · %s" % (_plural(solids, "solid"), _plural(features, "feature"))
        self._show(self._stats, text)

    def set_theme(self, theme):
        self._theme = theme

    def texts(self):
        def t(label):
            return "" if label.isHidden() else label.text()
        return {"prompt": self._prompt.text(), "message": t(self._message), "units": t(self._units),
                "dof": t(self._dof), "stats": t(self._stats)}
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_titlebar_status.py` → Expected: 8 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/titlebar.py InCad/incad/ui/statusbar.py tests/widgets/test_titlebar_status.py
git commit -m "InCad: title strip and status bar"
```

---

### Task 10: Browser tree model (document → nodes)

**Files:**
- Create: `InCad/incad/core/nodes.py`, `InCad/incad/core/tree.py`
- Test: `tests/headless/test_tree.py`

**Interfaces:**
- Consumes: Task 4/5 `document` functions; `tests/headless/util.py`.
- Produces (`incad.core.nodes`): dataclass `Node(kind, label, name="", state="", tooltip="", children=[])` —
  kinds `part origin origin_item solids body feature sketch end_of_part message action`; states
  `"" | "error" | "suppressed" | "rolled_back"`; `flatten(nodes) -> [(depth, Node)]`. No FreeCAD import.
- Produces (`incad.core.tree`): `ROLE_LABELS`, `build(doc) -> list[Node]`:
  - `None` → `[]`;
  - not an InCad part → `message "Not an InCad part"`, then `action "Convert to InCad Part"` (name `convert`) when
    the file has exactly one Body, then `action "Open in FreeCAD"` (name `freecad`);
  - InCad part → one `part` root whose children are: `origin` (with `origin_item`s labelled `X Axis`, `XY Plane`,
    `Center Point`…), `solids "Solid Bodies (n)"` when n > 1 (children `body` nodes, each holding that body's
    features), then the primary body's features in order with each feature's profile sketch nested under it,
    an `end_of_part` node right after the Tip (first when Tip is None), features after it `rolled_back`.
    The Parameters VarSet never appears.

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_tree.py`:
```python
import unittest

import FreeCAD as App
from incad.core import document, nodes, tree
from headless import util


def rows(doc):
    return [(d, n.kind, n.label, n.state) for d, n in nodes.flatten(tree.build(doc))]


def body_rows(doc):
    return [r for r in rows(doc) if r[1] not in ("part", "origin", "origin_item")]


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Tree")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_none(self):
        self.assertEqual(tree.build(None), [])

    def test_part_tree(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        util.add_rect_sketch(body, name="Loose")
        body.Tip = pad
        self.doc.recompute()
        r = rows(self.doc)
        self.assertEqual(r[0], (0, "part", self.doc.Label, ""))
        self.assertEqual(r[1][:3], (1, "origin", "Origin"))
        self.assertIn("XY Plane", [x[2] for x in r])
        self.assertEqual([x[:3] for x in body_rows(self.doc)],
                         [(1, "feature", "Pad"), (2, "sketch", "Sketch"), (1, "end_of_part", "End of Part"),
                          (1, "sketch", "Loose")])
        self.assertEqual(body_rows(self.doc)[-1][3], "rolled_back")

    def test_end_of_part_at_top(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        document.set_end_of_part(body, None)
        b = body_rows(self.doc)
        self.assertEqual(b[0][1], "end_of_part")
        self.assertEqual(b[1][:3] + (b[1][3],), (1, "feature", "Pad", "rolled_back"))

    def test_error_state_and_reason(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        pad.Length = 0
        self.doc.recompute()
        pad_node = [n for d, n in nodes.flatten(tree.build(self.doc)) if n.label == "Pad"][0]
        self.assertEqual(pad_node.state, "error")
        self.assertIn("zero", pad_node.tooltip.lower())

    def test_suppressed(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        pad.Suppressed = True
        self.doc.recompute()
        pad_node = [n for d, n in nodes.flatten(tree.build(self.doc)) if n.label == "Pad"][0]
        self.assertEqual(pad_node.state, "suppressed")

    def test_parameters_hidden(self):
        document.make_part(self.doc)
        document.set_parameter(self.doc, "Width", "80 mm")
        self.assertNotIn("Parameters", [x[2] for x in rows(self.doc)])

    def test_multi_body(self):
        document.make_part(self.doc)
        document.new_solid(self.doc)
        r = rows(self.doc)
        self.assertIn((1, "solids", "Solid Bodies (2)", ""), r)
        self.assertIn((2, "body", "Solid2", ""), r)

    def test_plain_file_with_one_body(self):
        self.doc.addObject("PartDesign::Body", "Body")
        self.assertEqual([(n.kind, n.label, n.name) for n in tree.build(self.doc)],
                         [("message", "Not an InCad part", ""), ("action", "Convert to InCad Part", "convert"),
                          ("action", "Open in FreeCAD", "freecad")])

    def test_plain_empty_file(self):
        self.assertEqual([n.kind for n in tree.build(self.doc)], ["message", "action"])
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_tree.py` → Expected: `ModuleNotFoundError: No module named 'incad.core.nodes'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/nodes.py`:
```python
"""Model Browser tree nodes: plain data built by incad.core.tree and drawn by incad.ui.browser."""
from dataclasses import dataclass, field


@dataclass
class Node:
    kind: str          # part | origin | origin_item | solids | body | feature | sketch | end_of_part | message | action
    label: str
    name: str = ""     # FreeCAD object name; for 'action' nodes the action id
    state: str = ""    # '' | 'error' | 'suppressed' | 'rolled_back'
    tooltip: str = ""
    children: list = field(default_factory=list)


def flatten(nodes, depth=0):
    """[(depth, node)] depth-first."""
    out = []
    for n in nodes:
        out.append((depth, n))
        out.extend(flatten(n.children, depth + 1))
    return out
```

`InCad/incad/core/tree.py`:
```python
"""Builds the Model Browser tree from a document (Inventor-style: sketches under the feature that uses them,
an End of Part marker after the Tip)."""
from incad.core import document
from incad.core.nodes import Node

ROLE_LABELS = {"X_Axis": "X Axis", "Y_Axis": "Y Axis", "Z_Axis": "Z Axis", "XY_Plane": "XY Plane",
               "XZ_Plane": "XZ Plane", "YZ_Plane": "YZ Plane", "Origin": "Center Point"}


def _profile(feature):
    prof = getattr(feature, "Profile", None)
    if isinstance(prof, (tuple, list)):
        prof = prof[0] if prof else None
    return prof


def _state(obj, rolled_back):
    st = obj.State
    if "Invalid" in st or "Error" in st:
        return "error"
    if getattr(obj, "Suppressed", False):
        return "suppressed"
    return "rolled_back" if rolled_back else ""


def _tooltip(obj, state):
    if state != "error":
        return ""
    try:
        return obj.getStatusString()
    except Exception:
        return "Failed to compute"


def _obj_node(obj, rolled_back):
    state = _state(obj, rolled_back)
    kind = "sketch" if obj.TypeId == "Sketcher::SketchObject" else "feature"
    return Node(kind, obj.Label, obj.Name, state, _tooltip(obj, state))


def _features(body):
    group = list(body.Group)
    tip = body.Tip
    tip_index = group.index(tip) if tip in group else -1
    consumed = {p.Name for p in (_profile(o) for o in group) if p is not None}
    out = []
    if tip_index == -1:
        out.append(Node("end_of_part", "End of Part"))
    for i, obj in enumerate(group):
        if obj.TypeId == "Sketcher::SketchObject" and obj.Name in consumed:
            continue
        node = _obj_node(obj, i > tip_index)
        prof = _profile(obj)
        if prof is not None and prof in group:
            node.children.append(_obj_node(prof, group.index(prof) > tip_index))
        out.append(node)
        if obj is tip or (prof is not None and prof is tip):
            out.append(Node("end_of_part", "End of Part"))
    return out


def _origin(body):
    origin = body.Origin
    items = [Node("origin_item", ROLE_LABELS.get(getattr(f, "Role", ""), f.Label), f.Name)
             for f in origin.OriginFeatures]
    return Node("origin", "Origin", origin.Name, children=items)


def build(doc):
    if doc is None:
        return []
    if not document.is_incad_part(doc):
        out = [Node("message", "Not an InCad part", tooltip="This file was made outside InCad.")]
        if len(document.bodies(doc)) == 1:
            out.append(Node("action", "Convert to InCad Part", "convert"))
        out.append(Node("action", "Open in FreeCAD", "freecad"))
        return out
    primary = document.primary_body(doc)
    all_bodies = document.bodies(doc)
    root = Node("part", doc.Label)
    if primary is not None:
        root.children.append(_origin(primary))
    if len(all_bodies) > 1:
        root.children.append(Node("solids", "Solid Bodies (%d)" % len(all_bodies), children=[
            Node("body", b.Label, b.Name, children=[] if b is primary else _features(b)) for b in all_bodies]))
    if primary is not None:
        root.children.extend(_features(primary))
    return [root]
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_tree.py` → Expected: 9 tests `OK`.
If `test_part_tree` shows the Origin inside `body.Group` (an extra row), filter `App::Origin` out of `group` in
`_features` and re-run.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/nodes.py InCad/incad/core/tree.py tests/headless/test_tree.py
git commit -m "InCad: Model Browser tree model with End of Part and nested sketches"
```

---

### Task 11: Model Browser widget (tree + Parameters)

**Files:**
- Create: `InCad/incad/ui/browser.py`
- Test: `tests/widgets/test_browser.py`

**Interfaces:**
- Consumes: `incad.core.nodes.Node`, `theme.icon`, `theme.PALETTES`.
- Produces (`incad.ui.browser.ModelBrowser(theme="light", parent=None)`): signals
  `featureActivated(str name)`, `endOfPartMoved(str name)` (`""` = before the first feature),
  `actionTriggered(str action_id)`, `parameterSet(str name, str text)`, `parameterRemoved(str name)`;
  methods `set_nodes(nodes)`, `tree_rows() -> [(depth, label, kind, state)]`, `item_by_label(label)`,
  `drop_end_of_part_on(item)`, `context_actions(item) -> [(text, callable)]`, `set_parameters(rows)`,
  `parameter_rows() -> [(name, value_cell, result_cell)]`, `add_parameter_row() -> int`,
  `remove_selected_parameter()`, `focus_parameters()`, `set_theme(theme)`; attributes `tree`, `params`.
  Item data roles: `NAME_ROLE = Qt.UserRole`, `KIND_ROLE = Qt.UserRole + 1`, `STATE_ROLE = Qt.UserRole + 2`.

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_browser.py`:
```python
import unittest

from widgets import qtapp
from incad.qt import QtCore, QtGui
from incad.core.nodes import Node
from incad.ui import theme
from incad.ui.browser import ModelBrowser


def sample():
    return [Node("part", "Bracket", children=[
        Node("origin", "Origin", "Origin", children=[Node("origin_item", "XY Plane", "XY_Plane")]),
        Node("feature", "Extrusion1", "Pad", children=[Node("sketch", "Sketch1", "Sketch")]),
        Node("end_of_part", "End of Part"),
        Node("feature", "Fillet1", "Fillet", "rolled_back"),
        Node("feature", "Broken", "Pocket", "error", "Pocket: nothing to cut"),
    ])]


class BrowserTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.b = ModelBrowser("light")
        self.b.set_nodes(sample())
        self.events = []
        for sig in ("featureActivated", "endOfPartMoved", "actionTriggered", "parameterRemoved"):
            getattr(self.b, sig).connect(lambda v, s=sig: self.events.append((s, v)))
        self.b.parameterSet.connect(lambda n, t: self.events.append(("parameterSet", n, t)))

    def test_rows(self):
        self.assertEqual(self.b.tree_rows(), [
            (0, "Bracket", "part", ""), (1, "Origin", "origin", ""), (2, "XY Plane", "origin_item", ""),
            (1, "Extrusion1", "feature", ""), (2, "Sketch1", "sketch", ""), (1, "End of Part", "end_of_part", ""),
            (1, "Fillet1", "feature", "rolled_back"), (1, "Broken", "feature", "error")])

    def test_error_color_and_tooltip(self):
        item = self.b.item_by_label("Broken")
        self.assertEqual(item.foreground(0).color(), QtGui.QColor(theme.PALETTES["light"]["error"]))
        self.assertEqual(item.toolTip(0), "Pocket: nothing to cut")

    def test_origin_collapsed_features_expanded(self):
        self.assertFalse(self.b.item_by_label("Origin").isExpanded())
        self.assertTrue(self.b.item_by_label("Extrusion1").isExpanded())

    def test_double_click(self):
        self.b.tree.itemDoubleClicked.emit(self.b.item_by_label("Sketch1"), 0)
        self.assertEqual(self.events, [("featureActivated", "Sketch")])

    def test_drop_end_of_part(self):
        self.b.drop_end_of_part_on(self.b.item_by_label("Fillet1"))
        self.b.drop_end_of_part_on(self.b.item_by_label("Sketch1"))
        self.b.drop_end_of_part_on(self.b.item_by_label("XY Plane"))
        self.assertEqual(self.events, [("endOfPartMoved", "Fillet"), ("endOfPartMoved", "Pad"),
                                       ("endOfPartMoved", "")])

    def test_context_actions(self):
        texts = [t for t, _ in self.b.context_actions(self.b.item_by_label("Fillet1"))]
        self.assertEqual(texts, ["Edit", "Move End of Part Here"])
        dict(self.b.context_actions(self.b.item_by_label("Fillet1")))["Move End of Part Here"]()
        self.assertEqual(self.events, [("endOfPartMoved", "Fillet")])
        self.assertEqual(self.b.context_actions(self.b.item_by_label("Origin")), [])

    def test_actions_for_plain_file(self):
        self.b.set_nodes([Node("message", "Not an InCad part"), Node("action", "Convert to InCad Part", "convert")])
        self.b.tree.itemDoubleClicked.emit(self.b.item_by_label("Convert to InCad Part"), 0)
        self.assertEqual(self.events, [("actionTriggered", "convert")])

    def test_parameters_show_formula_and_result(self):
        self.b.set_parameters([("Width", "", "80 mm"), ("HoleD", "Width/8", "10 mm")])
        self.assertEqual(self.b.parameter_rows(), [("Width", "80 mm", "80 mm"), ("HoleD", "Width/8", "10 mm")])
        self.assertEqual(self.events, [])

    def test_edit_value_emits(self):
        self.b.set_parameters([("Width", "", "80 mm")])
        self.b.params.item(0, 1).setText("90 mm")
        self.assertEqual(self.events, [("parameterSet", "Width", "90 mm")])

    def test_add_row_emits_when_complete(self):
        r = self.b.add_parameter_row()
        self.b.params.item(r, 0).setText("Gap")
        self.assertEqual(self.events, [])
        self.b.params.item(r, 1).setText("0.2 mm")
        self.assertEqual(self.events, [("parameterSet", "Gap", "0.2 mm")])

    def test_remove(self):
        self.b.set_parameters([("Width", "", "80 mm")])
        self.b.params.setCurrentCell(0, 0)
        self.b.remove_selected_parameter()
        self.assertEqual(self.events, [("parameterRemoved", "Width")])
        r = self.b.add_parameter_row()
        self.b.params.setCurrentCell(r, 0)
        self.b.remove_selected_parameter()
        self.assertEqual(self.b.params.rowCount(), 1)

    def test_theme_redraw(self):
        self.b.set_theme("dark")
        self.assertEqual(self.b.item_by_label("Broken").foreground(0).color(),
                         QtGui.QColor(theme.PALETTES["dark"]["error"]))
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_browser.py` → Expected: `ModuleNotFoundError: No module named 'incad.ui.browser'`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/browser.py`:
```python
"""Model Browser: the feature tree (with a draggable End of Part marker) and the Parameters table."""
from incad.qt import QtCore, QtGui, QtWidgets, Signal
from incad.ui import theme as themes

NAME_ROLE = QtCore.Qt.UserRole
KIND_ROLE = QtCore.Qt.UserRole + 1
STATE_ROLE = QtCore.Qt.UserRole + 2

KIND_ICONS = {"part": "part", "origin": "origin", "feature": "feature", "sketch": "sketch",
              "end_of_part": "end_of_part", "solids": "solids", "body": "part"}


class _Tree(QtWidgets.QTreeWidget):
    """Tree that lets the user drag the End of Part marker onto another row."""

    def __init__(self, browser):
        super().__init__(browser)
        self._browser = browser
        self._dragging = False

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        self._dragging = item is not None and item.data(0, KIND_ROLE) == "end_of_part"
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            target = self.itemAt(event.position().toPoint())
            if target is not None and target.data(0, KIND_ROLE) != "end_of_part":
                self._browser.drop_end_of_part_on(target)
        super().mouseReleaseEvent(event)


class ModelBrowser(QtWidgets.QWidget):
    featureActivated = Signal(str)
    endOfPartMoved = Signal(str)
    actionTriggered = Signal(str)
    parameterSet = Signal(str, str)
    parameterRemoved = Signal(str)

    def __init__(self, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadBrowser")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._theme = theme
        self._nodes = []
        self._loading = False
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        header = QtWidgets.QLabel("MODEL")
        header.setObjectName("InCadPanelHeader")
        col.addWidget(header)
        self.tree = _Tree(self)
        self.tree.setObjectName("InCadTree")
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        col.addWidget(self.tree, 3)
        bar = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 4, 0)
        label = QtWidgets.QLabel("PARAMETERS")
        label.setObjectName("InCadPanelHeader")
        row.addWidget(label, 1)
        self.add_button = QtWidgets.QToolButton()
        self.add_button.setText("+")
        self.add_button.setToolTip("Add parameter")
        self.add_button.clicked.connect(self.add_parameter_row)
        self.remove_button = QtWidgets.QToolButton()
        self.remove_button.setText("−")
        self.remove_button.setToolTip("Remove selected parameter")
        self.remove_button.clicked.connect(self.remove_selected_parameter)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        col.addWidget(bar)
        self.params = QtWidgets.QTableWidget(0, 3)
        self.params.setObjectName("InCadParams")
        self.params.setHorizontalHeaderLabels(["Name", "Value", "Result"])
        self.params.verticalHeader().hide()
        self.params.horizontalHeader().setStretchLastSection(True)
        self.params.itemChanged.connect(self._on_param_changed)
        col.addWidget(self.params, 1)

    # ----- tree -----
    def set_nodes(self, nodes):
        self._nodes = nodes
        self.tree.clear()
        for node in nodes:
            self.tree.addTopLevelItem(self._item(node))
        self.tree.expandAll()
        for item in self._items():
            if item.data(0, KIND_ROLE) == "origin":
                item.setExpanded(False)

    def _item(self, node):
        item = QtWidgets.QTreeWidgetItem([node.label])
        item.setData(0, NAME_ROLE, node.name)
        item.setData(0, KIND_ROLE, node.kind)
        item.setData(0, STATE_ROLE, node.state)
        icon = self._icon_name(node)
        if icon:
            item.setIcon(0, themes.icon(icon, self._theme))
        p = themes.PALETTES[self._theme]
        color = None
        if node.state == "error":
            color = p["error"]
        elif node.state in ("rolled_back", "suppressed"):
            color = p["rolled_back"]
        if node.kind == "end_of_part":
            color = p["eop"]
        elif node.kind == "action":
            color = p["accent"]
        if color:
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
        font = item.font(0)
        font.setStrikeOut(node.state == "suppressed")
        font.setBold(node.kind == "end_of_part")
        item.setFont(0, font)
        if node.tooltip:
            item.setToolTip(0, node.tooltip)
        for child in node.children:
            item.addChild(self._item(child))
        return item

    @staticmethod
    def _icon_name(node):
        if node.kind == "origin_item":
            return "plane" if "Plane" in node.label else "axis" if "Axis" in node.label else "point"
        return KIND_ICONS.get(node.kind)

    def _items(self):
        out = []

        def walk(item):
            out.append(item)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return out

    def _depth(self, item):
        d = 0
        while item.parent() is not None:
            item = item.parent()
            d += 1
        return d

    def tree_rows(self):
        return [(self._depth(i), i.text(0), i.data(0, KIND_ROLE), i.data(0, STATE_ROLE)) for i in self._items()]

    def item_by_label(self, label):
        for item in self._items():
            if item.text(0) == label:
                return item
        return None

    def _top_feature(self, item):
        while item.parent() is not None and item.parent().data(0, KIND_ROLE) != "part":
            item = item.parent()
        return item

    def drop_end_of_part_on(self, item):
        """End of Part goes after the row's feature; origin/solids/part rows put it before the first feature."""
        top = self._top_feature(item)
        kind = top.data(0, KIND_ROLE)
        if kind in ("feature", "sketch"):
            self.endOfPartMoved.emit(top.data(0, NAME_ROLE))
        elif kind in ("origin", "solids", "part"):
            self.endOfPartMoved.emit("")

    def context_actions(self, item):
        kind = item.data(0, KIND_ROLE)
        if kind not in ("feature", "sketch"):
            return []
        name = item.data(0, NAME_ROLE)
        return [("Edit", lambda: self.featureActivated.emit(name)),
                ("Move End of Part Here", lambda: self.drop_end_of_part_on(item))]

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        actions = self.context_actions(item) if item is not None else []
        if not actions:
            return
        menu = QtWidgets.QMenu(self)
        for text, fn in actions:
            menu.addAction(text).triggered.connect(lambda _=False, f=fn: f())
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _on_double_click(self, item, _column=0):
        kind = item.data(0, KIND_ROLE)
        if kind in ("feature", "sketch"):
            self.featureActivated.emit(item.data(0, NAME_ROLE))
        elif kind == "action":
            self.actionTriggered.emit(item.data(0, NAME_ROLE))

    # ----- parameters -----
    def _readonly(self, text):
        item = QtWidgets.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
        return item

    def set_parameters(self, rows):
        self._loading = True
        try:
            self.params.setRowCount(0)
            for name, formula, value in rows:
                r = self.params.rowCount()
                self.params.insertRow(r)
                self.params.setItem(r, 0, self._readonly(name))
                self.params.setItem(r, 1, QtWidgets.QTableWidgetItem(formula or value))
                self.params.setItem(r, 2, self._readonly(value))
        finally:
            self._loading = False

    def parameter_rows(self):
        def text(r, c):
            item = self.params.item(r, c)
            return item.text() if item else ""
        return [(text(r, 0), text(r, 1), text(r, 2)) for r in range(self.params.rowCount())]

    def add_parameter_row(self):
        self._loading = True
        try:
            r = self.params.rowCount()
            self.params.insertRow(r)
            self.params.setItem(r, 0, QtWidgets.QTableWidgetItem(""))
            self.params.setItem(r, 1, QtWidgets.QTableWidgetItem(""))
            self.params.setItem(r, 2, self._readonly(""))
        finally:
            self._loading = False
        self.params.setCurrentCell(r, 0)
        return r

    def _on_param_changed(self, item):
        if self._loading:
            return
        r = item.row()
        name_item, value_item = self.params.item(r, 0), self.params.item(r, 1)
        name = name_item.text().strip() if name_item else ""
        value = value_item.text().strip() if value_item else ""
        if name and value:
            self.parameterSet.emit(name, value)

    def remove_selected_parameter(self):
        r = self.params.currentRow()
        if r < 0:
            return
        item = self.params.item(r, 0)
        saved = item is not None and not bool(item.flags() & QtCore.Qt.ItemIsEditable)
        if saved:
            self.parameterRemoved.emit(item.text())
        else:
            self.params.removeRow(r)

    def focus_parameters(self):
        self.params.setFocus()

    def set_theme(self, theme):
        self._theme = theme
        self.set_nodes(self._nodes)
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_browser.py` → Expected: 12 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/browser.py tests/widgets/test_browser.py
git commit -m "InCad: Model Browser widget with End of Part drag and Parameters table"
```

---

### Task 12: New dialog and the stage-1a commands

**Files:**
- Create: `InCad/incad/ui/new_dialog.py`, `InCad/incad/actions.py`
- Test: `tests/widgets/test_new_dialog.py`, `tests/widgets/test_actions.py`, `tests/headless/test_new_part.py`

**Interfaces:**
- Consumes: `prefs`, `commands.Command/REGISTRY`, `document.make_part`, `theme.current/stylesheet/icon_path`.
- Produces (`incad.ui.new_dialog.NewDialog(units="mm", remember=False, theme="light", parent=None)`): attributes
  `part`, `assembly` (disabled), `mm`, `inch`, `remember`, `create_button`; `choice() -> ("part", "mm"|"in", bool)`.
- Produces (`incad.actions`): `STD_COMMANDS` (`{cmd_id: FreeCAD command name}`), `new_part(ask=None) -> Document|None`,
  `ask_new()`, `toggle_theme()`, `return_to_freecad()`, `focus_parameters()`, `commands() -> list[Command]`,
  `register_all(registry=REGISTRY)` (idempotent). Command ids: `file.new` (shortcut `Ctrl+N`), `file.open`,
  `file.save`, `file.save_as`, `file.close`, `edit.undo`, `edit.redo`, `view.theme_toggle`, `view.freecad`,
  `view.zoom_all`, `view.home`, `view.style_shaded`, `view.style_wireframe`, `view.parameters`.
  `toggle_theme`/`focus_parameters` call `incad.ui.shell.apply_theme()` / `shell.focus_parameters()` (Task 13).

- [ ] **Step 1: Write the failing tests**

`tests/widgets/test_new_dialog.py`:
```python
import unittest

from widgets import qtapp
from incad.qt import QtWidgets
from incad.ui.new_dialog import NewDialog


class NewDialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()

    def test_defaults(self):
        d = NewDialog()
        self.assertEqual(d.choice(), ("part", "mm", False))
        self.assertFalse(d.assembly.isEnabled())
        self.assertTrue(d.part.isChecked())

    def test_inch_and_remember(self):
        d = NewDialog(units="in", remember=True, theme="dark")
        self.assertEqual(d.choice(), ("part", "in", True))
        d.mm.click()
        self.assertEqual(d.choice(), ("part", "mm", True))
        self.assertFalse(d.inch.isChecked())

    def test_create_accepts(self):
        d = NewDialog()
        d.create_button.click()
        self.assertEqual(d.result(), QtWidgets.QDialog.Accepted)
```

`tests/widgets/test_actions.py`:
```python
import os
import unittest

from incad import actions
from incad.core.commands import Registry
from incad.ui import theme

EXPECTED = {"file.new", "file.open", "file.save", "file.save_as", "file.close", "edit.undo", "edit.redo",
            "view.theme_toggle", "view.freecad", "view.zoom_all", "view.home", "view.style_shaded",
            "view.style_wireframe", "view.parameters"}


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
```

`tests/headless/test_new_part.py`:
```python
import unittest

import FreeCAD as App
from incad import actions
from incad.core import document, prefs


class NewPartTest(unittest.TestCase):
    def setUp(self):
        prefs.use_memory_backend()

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def test_asks_then_remembers(self):
        doc = actions.new_part(ask=lambda: ("part", "in", True))
        self.assertTrue(document.is_incad_part(doc))
        self.assertEqual(document.part_units(doc), "in")
        self.assertEqual((prefs.default_units(), prefs.remember_new_choice()), ("in", True))
        doc2 = actions.new_part(ask=lambda: self.fail("must not ask when remembered"))
        self.assertEqual(document.part_units(doc2), "in")

    def test_cancel_creates_nothing(self):
        self.assertIsNone(actions.new_part(ask=lambda: None))
        self.assertEqual(App.listDocuments(), {})

    def test_creation_is_not_an_undo_step(self):
        doc = actions.new_part(ask=lambda: ("part", "mm", False))
        self.assertEqual(doc.UndoNames, [])
        self.assertEqual(doc.UndoMode, 1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_new_dialog.py`, `tests/run_widgets.sh test_actions.py`, `tests/run_headless.sh test_new_part.py`
Expected: `ModuleNotFoundError` for `incad.ui.new_dialog` and `incad.actions`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/new_dialog.py`:
```python
"""New file dialog: Part / Assembly and Millimeters / Inches, with 'Remember my choice'."""
from incad.qt import QtWidgets
from incad.ui import theme as themes


class NewDialog(QtWidgets.QDialog):
    def __init__(self, units="mm", remember=False, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadNewDialog")
        self.setWindowTitle("New")
        self.setStyleSheet(themes.stylesheet(theme))
        col = QtWidgets.QVBoxLayout(self)
        self.part = self._tile("Part", "One part file")
        self.assembly = self._tile("Assembly", "Arrives in a later InCad stage")
        self.assembly.setEnabled(False)
        self.part.setChecked(True)
        self.mm = self._tile("Millimeters", "mm · deg · ISO threads first")
        self.inch = self._tile("Inches", "in · deg · UNC/UNF threads first")
        (self.inch if units == "in" else self.mm).setChecked(True)
        for first, second in ((self.part, self.assembly), (self.mm, self.inch)):
            group = QtWidgets.QButtonGroup(self)
            group.setExclusive(True)
            group.addButton(first)
            group.addButton(second)
            row = QtWidgets.QHBoxLayout()
            row.addWidget(first)
            row.addWidget(second)
            col.addLayout(row)
        self.remember = QtWidgets.QCheckBox("Remember my choice")
        self.remember.setChecked(remember)
        col.addWidget(self.remember)
        buttons = QtWidgets.QDialogButtonBox()
        self.create_button = buttons.addButton("Create", QtWidgets.QDialogButtonBox.AcceptRole)
        buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.create_button.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        col.addWidget(buttons)

    @staticmethod
    def _tile(title, subtitle):
        b = QtWidgets.QPushButton("%s\n%s" % (title, subtitle))
        b.setObjectName("InCadTile")
        b.setCheckable(True)
        b.setMinimumSize(180, 64)
        return b

    def choice(self):
        return ("part", "in" if self.inch.isChecked() else "mm", self.remember.isChecked())
```

`InCad/incad/actions.py`:
```python
"""InCad's stage-1a commands and their handlers. FreeCAD is imported inside handlers, so this module also
loads in widget tests."""
from incad.core import prefs
from incad.core.commands import REGISTRY, Command

STD_COMMANDS = {
    "file.open": "Std_Open", "file.save": "Std_Save", "file.save_as": "Std_SaveAs",
    "file.close": "Std_CloseActiveWindow", "edit.undo": "Std_Undo", "edit.redo": "Std_Redo",
    "view.zoom_all": "Std_ViewFitAll", "view.home": "Std_ViewHome",
    "view.style_shaded": "Std_DrawStyleFlatLines", "view.style_wireframe": "Std_DrawStyleWireframe",
}


def _gui():
    import FreeCADGui
    return FreeCADGui


def run_std(name):
    _gui().runCommand(name, 0)


def ask_new():
    """Show the New dialog; (kind, units, remember) or None when cancelled."""
    from incad.ui import theme
    from incad.ui.new_dialog import NewDialog
    dlg = NewDialog(units=prefs.default_units(), remember=prefs.remember_new_choice(),
                    theme=theme.current(), parent=_gui().getMainWindow())
    return dlg.choice() if dlg.exec() else None


def new_part(ask=None):
    """Create an InCad Part in a new document. ask() -> (kind, units, remember) | None (default: the New
    dialog). With 'Remember my choice' on, nothing is asked and the saved units are used."""
    import FreeCAD as App
    from incad.core import document
    if prefs.remember_new_choice():
        units = prefs.default_units()
    else:
        answer = (ask or ask_new)()
        if answer is None:
            return None
        _kind, units, remember = answer
        prefs.set_default_units(units)
        prefs.set_remember_new_choice(remember)
    doc = App.newDocument("Part")
    doc.UndoMode = 1
    body = document.make_part(doc, units)
    doc.recompute()
    doc.clearUndos()
    if App.GuiUp:
        view = _gui().getDocument(doc.Name).ActiveView
        view.setActiveObject("pdbody", body)
        view.viewIsometric()
        view.fitAll()
    return doc


def toggle_theme():
    from incad.ui import shell, theme
    prefs.set_theme(theme.toggled(theme.current()))
    shell.apply_theme()


def return_to_freecad():
    _gui().activateWorkbench(prefs.last_workbench())


def focus_parameters():
    from incad.ui import shell
    shell.focus_parameters()


def _std(cmd_id, label, icon):
    name = STD_COMMANDS[cmd_id]
    return Command(id=cmd_id, label=label, icon=icon, handler=lambda: run_std(name))


def commands():
    return [
        Command(id="file.new", label="New", icon="new", handler=new_part, shortcut="Ctrl+N",
                tooltip="New part (asks for mm or inch)"),
        _std("file.open", "Open", "open"),
        _std("file.save", "Save", "save"),
        _std("file.save_as", "Save As", "save"),
        _std("file.close", "Close", "close"),
        _std("edit.undo", "Undo", "undo"),
        _std("edit.redo", "Redo", "redo"),
        Command(id="view.theme_toggle", label="Light / Dark", icon="theme_toggle", handler=toggle_theme,
                tooltip="Switch between light and dark"),
        Command(id="view.freecad", label="Return to FreeCAD", icon="freecad", handler=return_to_freecad,
                tooltip="Show FreeCAD's own interface"),
        _std("view.zoom_all", "Zoom All", "zoom_all"),
        _std("view.home", "Home View", "home_view"),
        _std("view.style_shaded", "Shaded", "style_shaded"),
        _std("view.style_wireframe", "Wireframe", "style_wireframe"),
        Command(id="view.parameters", label="Parameters", icon="parameters", handler=focus_parameters),
    ]


def register_all(registry=REGISTRY):
    for cmd in commands():
        if not registry.has(cmd.id):
            registry.register(cmd)
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_widgets.sh test_new_dialog.py`, `tests/run_widgets.sh test_actions.py`, `tests/run_headless.sh test_new_part.py`
Expected: all `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/new_dialog.py InCad/incad/actions.py tests/widgets/test_new_dialog.py tests/widgets/test_actions.py tests/headless/test_new_part.py
git commit -m "InCad: New dialog (Part, mm/in) and stage-1a commands"
```

---

### Task 13: Shell takeover and workbench wiring

**Files:**
- Create: `InCad/incad/ui/shell.py`
- Modify: `InCad/InitGui.py` (replace whole file)
- Test: `tests/gui/test_shell.py`, `tests/gui/test_shell_parts.py`

**Interfaces:**
- Consumes: everything above.
- Produces (`incad.ui.shell`): class `Shell(mw, registry)` with `active`, `ribbon`, `title`, `browser`, `status`,
  `activate() -> bool`, `deactivate()`, `apply_theme()`, `refresh()`, `schedule_refresh()`; module functions
  `instance()`, `activate()`, `deactivate()`, `apply_theme()`, `focus_parameters()`, `recover_after_crash()`.
  Widget object names: toolbars `InCadTop`, `InCadStatusBar`, dock `InCadBrowserDock`, menus `InCadMenu_File/Edit/View`.

- [ ] **Step 1: Write the failing GUI tests**

`tests/gui/test_shell.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtGui, QtWidgets  # noqa: E402
from incad.core import commands, params, prefs  # noqa: E402
from incad.ui import shell, theme  # noqa: E402

mw = Gui.getMainWindow()
BASE = {}


def state():
    return {
        "toolbars": {t.objectName(): not t.isHidden() for t in mw.findChildren(QtWidgets.QToolBar)
                     if t.parent() is mw and t.objectName() and not t.objectName().startswith("InCad")},
        "docks": {d.objectName(): not d.isHidden() for d in mw.findChildren(QtWidgets.QDockWidget)
                  if d.objectName() and not d.objectName().startswith("InCad")},
        "menus": {a.text(): a.isVisible() for a in mw.menuBar().actions()
                  if a.text() and not (a.menu() and a.menu().objectName().startswith("InCadMenu_"))},
        "statusbar": not mw.statusBar().isHidden(),
    }


def toolbar_params():
    return App.ParamGet("User parameter:BaseApp/MainWindow/Toolbars").GetContents()


def view_params():
    return params.snapshot(theme.VIEW_GROUP, theme.VIEW_KEYS)


def std_new_shortcut():
    return Gui.Command.get("Std_New").getAction()[0].shortcut().toString()


def assert_restored():
    now = state()
    for key in ("toolbars", "docks", "menus"):
        diff = {k: (BASE["state"][key].get(k), v) for k, v in now[key].items() if BASE["state"][key].get(k, v) != v}
        assert not diff, (key, diff)
    assert now["statusbar"] == BASE["state"]["statusbar"]
    assert view_params() == BASE["view"], (view_params(), BASE["view"])
    assert std_new_shortcut() == BASE["new"], std_new_shortcut()
    assert not prefs.takeover_snapshot()


def test_0_baseline_in_partdesign():
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    BASE.update(state=state(), tb=toolbar_params(), view=view_params(), new=std_new_shortcut())
    assert any(BASE["state"]["toolbars"].values()), "expected visible FreeCAD toolbars"
    assert BASE["new"], "Std_New should have a shortcut"


def test_1_activate_takes_over():
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    s = shell.instance()
    assert s is not None and s.active
    st = state()
    assert not [k for k, v in st["toolbars"].items() if v], st["toolbars"]
    assert not [k for k, v in st["docks"].items() if v], st["docks"]
    assert not [k for k, v in st["menus"].items() if v], st["menus"]
    assert not st["statusbar"]
    for name in ("InCadTop", "InCadStatusBar"):
        assert not mw.findChild(QtWidgets.QToolBar, name).isHidden(), name
    assert not mw.findChild(QtWidgets.QDockWidget, "InCadBrowserDock").isHidden()
    titles = [a.text() for a in mw.menuBar().actions() if a.isVisible()]
    assert titles == ["File", "Edit", "View"], titles
    assert prefs.takeover_snapshot()
    assert prefs.last_workbench() == "PartDesignWorkbench", prefs.last_workbench()


def test_2_new_shortcut_moves_to_incad():
    assert std_new_shortcut() == "", std_new_shortcut()
    file_menu = [a.menu() for a in mw.menuBar().actions()
                 if a.menu() and a.menu().objectName() == "InCadMenu_File"][0]
    new = [a for a in file_menu.actions() if a.text() == "New"][0]
    assert new.shortcut().toString() == "Ctrl+N", new.shortcut().toString()


def test_3_reshown_toolbar_is_hidden_again():
    tb = [t for t in mw.findChildren(QtWidgets.QToolBar)
          if t.parent() is mw and t.objectName() and not t.objectName().startswith("InCad")][0]
    tb.show()
    harness.pump(300)
    assert tb.isHidden(), tb.objectName()


def test_4_return_to_freecad_restores_everything():
    commands.REGISTRY.run("view.freecad")
    harness.pump(1000)
    assert Gui.activeWorkbench().name() == "PartDesignWorkbench"
    assert_restored()
    assert toolbar_params() == BASE["tb"]
    assert mw.findChild(QtWidgets.QToolBar, "InCadTop") is None


def test_5_quit_path_restores_then_reactivates():
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    s = shell.instance()
    s.eventFilter(mw, QtGui.QCloseEvent())
    assert not s.active
    assert_restored()
    harness.pump(500)
    assert s.active, "the window stayed open, so InCad must come back"


def test_6_restore_from_saved_snapshot_when_memory_lost():
    s = shell.instance()
    assert s.active
    s._snapshot = None
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert_restored()


def test_7_recover_after_crash_at_startup():
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    snap = prefs.takeover_snapshot()
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    for t in mw.findChildren(QtWidgets.QToolBar):
        if t.parent() is mw and t.objectName():
            t.hide()
    prefs.set_takeover_snapshot(snap)
    shell.recover_after_crash()
    harness.pump(300)
    assert_restored()


def test_8_activation_failure_restores():
    s = shell.instance()
    original = s._build

    def broken():
        raise RuntimeError("simulated")

    s._build = broken
    try:
        Gui.activateWorkbench("InCadWorkbench")
        harness.pump(800)
        assert not s.active
        assert_restored()
    finally:
        s._build = original
        Gui.activateWorkbench("PartDesignWorkbench")
        harness.pump(800)


harness.run([test_0_baseline_in_partdesign, test_1_activate_takes_over, test_2_new_shortcut_moves_to_incad,
             test_3_reshown_toolbar_is_hidden_again, test_4_return_to_freecad_restores_everything,
             test_5_quit_path_restores_then_reactivates, test_6_restore_from_saved_snapshot_when_memory_lost,
             test_7_recover_after_crash_at_startup, test_8_activation_failure_restores])
```

`tests/gui/test_shell_parts.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, document, prefs, safe  # noqa: E402
from incad.ui import shell, theme  # noqa: E402

mw = Gui.getMainWindow()
DOCS = {}


def s():
    return shell.instance()


def activate_doc(name):
    mdi = mw.findChild(QtWidgets.QMdiArea)
    for w in mdi.subWindowList():
        mdi.setActiveSubWindow(w)
        harness.pump(300)
        if App.ActiveDocument is not None and App.ActiveDocument.Name == name:
            return
    raise AssertionError("could not activate %s" % name)


def test_0_activate():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    assert s().active
    assert s().ribbon.tab_names() == ["Get Started", "View"], s().ribbon.tab_names()


def test_1_new_part():
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    doc = App.ActiveDocument
    assert document.is_incad_part(doc) and document.part_units(doc) == "mm"
    labels = [r[1] for r in s().browser.tree_rows()]
    assert "Origin" in labels and "End of Part" in labels, labels
    assert {"Tools", "View"} <= set(s().ribbon.tab_names()), s().ribbon.tab_names()
    assert s().status.texts()["units"] == "mm · deg"
    assert s().title.document_name() == doc.Label
    DOCS["mm"] = doc.Name


def test_2_switching_documents_updates_panels():
    prefs.set_default_units("in")
    commands.REGISTRY.run("file.new")
    harness.pump(1000)
    DOCS["in"] = App.ActiveDocument.Name
    assert s().status.texts()["units"] == "in · deg"
    activate_doc(DOCS["mm"])
    assert s().status.texts()["units"] == "mm · deg"


def test_3_parameters():
    s().browser.parameterSet.emit("Width", "80 mm")
    harness.pump(500)
    assert ("Width", "", "80 mm") in document.list_parameters(App.ActiveDocument)
    assert ("Width", "80 mm", "80 mm") in s().browser.parameter_rows(), s().browser.parameter_rows()
    s().browser.parameterSet.emit("2bad", "1")
    harness.pump(500)
    assert "2bad" not in [p[0] for p in document.list_parameters(App.ActiveDocument)]
    assert "parameter name" in s().status.texts()["message"].lower(), s().status.texts()


def test_4_plain_file():
    d = App.newDocument("Plain")
    d.addObject("PartDesign::Body", "Body")
    d.recompute()
    harness.pump(800)
    labels = [r[1] for r in s().browser.tree_rows()]
    assert labels[:2] == ["Not an InCad part", "Convert to InCad Part"], labels
    s().browser.actionTriggered.emit("convert")
    harness.pump(800)
    assert document.is_incad_part(d)
    assert "Origin" in [r[1] for r in s().browser.tree_rows()]


def test_5_theme_toggle():
    before = theme.current()
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    after = theme.current()
    assert after != before
    top = mw.findChild(QtWidgets.QToolBar, "InCadTop")
    assert theme.PALETTES[after]["panel"] in top.styleSheet()
    got = App.ParamGet(theme.VIEW_GROUP).GetUnsigned("BackgroundColor2")
    assert got == theme.view_params(after)["BackgroundColor2"][1], hex(got)
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    assert theme.current() == before


def test_6_ribbon_size_persists():
    s().ribbon.set_size("small")
    assert prefs.ribbon_size() == "small"
    s().ribbon.set_size("large")
    assert prefs.ribbon_size() == "large"


def test_7_std_commands_exist():
    missing = [c for c in actions.STD_COMMANDS.values() if c not in Gui.listCommands()]
    assert not missing, missing


def test_8_failed_command_then_undo():
    doc = App.ActiveDocument
    r = safe.run_safely("Boom", lambda: 1 / 0, doc)
    assert not r.ok
    harness.pump(200)
    assert "Boom failed" in s().status.texts()["message"], s().status.texts()
    r = safe.run_safely("Set Gap", lambda: document.set_parameter(doc, "Gap", "0.2 mm"), doc)
    assert r.ok
    doc.undo()
    harness.pump(300)
    assert "Gap" not in [p[0] for p in document.list_parameters(doc)]


def test_9_close_all_documents():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    harness.pump(800)
    assert s().ribbon.tab_names() == ["Get Started", "View"], s().ribbon.tab_names()
    assert s().browser.tree_rows() == []
    assert s().status.texts()["prompt"] == "Create or open a part"
    with open(os.environ["INCAD_LOG"]) as f:
        assert "could not update its panels" not in f.read()


harness.run([test_0_activate, test_1_new_part, test_2_switching_documents_updates_panels, test_3_parameters,
             test_4_plain_file, test_5_theme_toggle, test_6_ribbon_size_persists, test_7_std_commands_exist,
             test_8_failed_command_then_undo, test_9_close_all_documents])
```

- [ ] **Step 2: Run to verify they fail**

Tell the user: "FreeCAD windows opening for tests — hands off mouse/keyboard for ~1 minute."
Run: `tests/run_gui.sh tests/gui/test_shell.py tests/gui/test_shell_parts.py`
Expected: failures from `test_1_activate_takes_over` on (`shell` has no `instance`), `0 passed` for parts after test_0.

- [ ] **Step 3: Implement the shell**

`InCad/incad/ui/shell.py`:
```python
"""Full UI takeover. While InCad is active FreeCAD's menus, toolbars, docks and status bar are hidden and InCad's
title strip, ribbon, Model Browser and status bar are shown. Everything is restored on exit, also after a quit or
a crash with InCad active: the snapshot stays in InCad's preferences until the restore has been done."""
import json
import traceback

from incad.core import commands, log, prefs
from incad.qt import QtCore, QtGui, QtWidgets
from incad.ui import ribbon_layout
from incad.ui import theme as themes
from incad.ui.browser import ModelBrowser
from incad.ui.ribbon import Ribbon
from incad.ui.statusbar import StatusBar
from incad.ui.titlebar import TitleStrip

OURS = ("InCadTop", "InCadBrowserDock", "InCadStatusBar")
MENU_PREFIX = "InCadMenu_"
MENUS = [("File", ["file.new", "file.open", "file.save", "file.save_as", "file.close"]),
         ("Edit", ["edit.undo", "edit.redo"]),
         ("View", ["view.theme_toggle", "view.zoom_all", "view.home", "view.style_shaded",
                   "view.style_wireframe", "view.parameters", None, "view.freecad"])]

_shell = None


def _std_new_actions():
    import FreeCADGui as Gui
    try:
        return list(Gui.Command.get("Std_New").getAction())
    except Exception:
        return []


class _DocObserver:
    """FreeCAD document observer: any change schedules one (coalesced) panel refresh."""

    def __init__(self, callback):
        self.callback = callback

    def slotCreatedDocument(self, doc):
        self.callback()

    def slotDeletedDocument(self, doc):
        self.callback()

    def slotRelabelDocument(self, doc):
        self.callback()

    def slotActivateDocument(self, doc):
        self.callback()

    def slotCreatedObject(self, obj):
        self.callback()

    def slotDeletedObject(self, obj):
        self.callback()

    def slotChangedObject(self, obj, prop):
        self.callback()

    def slotRecomputedDocument(self, doc):
        self.callback()


class Shell(QtCore.QObject):
    def __init__(self, mw, registry):
        super().__init__(mw)
        self.mw, self.registry = mw, registry
        self.active = False
        self.theme = "light"
        self.ribbon = self.title = self.browser = self.status = None
        self._snapshot = None
        self._hidden_by_us = set()
        self._widgets = []
        self._menus = []
        self._observer = None
        self._refresh_pending = False

    # ----- FreeCAD's own UI -----
    def _mdi(self):
        return self.mw.findChild(QtWidgets.QMdiArea)

    def _freecad_toolbars(self):
        return [t for t in self.mw.findChildren(QtWidgets.QToolBar)
                if t.parent() is self.mw and t.objectName() and t.objectName() not in OURS]

    def _freecad_docks(self):
        return [d for d in self.mw.findChildren(QtWidgets.QDockWidget)
                if d.objectName() and d.objectName() not in OURS]

    def _freecad_menu_actions(self):
        return [a for a in self.mw.menuBar().actions()
                if a.text() and not (a.menu() is not None and a.menu().objectName().startswith(MENU_PREFIX))]

    def _capture(self):
        from incad.core import params
        new = _std_new_actions()
        mdi = self._mdi()
        return {
            "toolbars": {t.objectName(): not t.isHidden() for t in self._freecad_toolbars()},
            "docks": {d.objectName(): not d.isHidden() for d in self._freecad_docks()},
            "menus": {a.text(): a.isVisible() for a in self._freecad_menu_actions()},
            "statusbar": not self.mw.statusBar().isHidden(),
            "view": params.snapshot(themes.VIEW_GROUP, themes.VIEW_KEYS),
            "std_new": new[0].shortcut().toString() if new else "",
            "mdi": [mdi.viewMode().name, mdi.tabPosition().name] if mdi is not None else None,
        }

    def _hide_freecad(self):
        for w in self._freecad_toolbars() + self._freecad_docks():
            if not w.isHidden():
                self._hidden_by_us.add(w.objectName())
            w.hide()
        for a in self._freecad_menu_actions():
            a.setVisible(False)
        self.mw.statusBar().hide()
        for a in _std_new_actions():
            a.setShortcut(QtGui.QKeySequence())
        mdi = self._mdi()
        if mdi is not None:
            mdi.setViewMode(QtWidgets.QMdiArea.TabbedView)
            mdi.setTabPosition(QtWidgets.QTabWidget.South)

    def _restore_widgets(self, widgets, saved):
        for w in widgets:
            name = w.objectName()
            if name in saved:
                w.setVisible(saved[name])
            elif name in self._hidden_by_us:
                w.show()

    def _restore_mdi(self, saved):
        mdi = self._mdi()
        if mdi is not None and saved:
            mdi.setViewMode(getattr(QtWidgets.QMdiArea.ViewMode, saved[0]))
            mdi.setTabPosition(getattr(QtWidgets.QTabWidget.TabPosition, saved[1]))

    def _restore(self, snap):
        from incad.core import params
        steps = [
            ("toolbars", lambda: self._restore_widgets(self._freecad_toolbars(), snap.get("toolbars", {}))),
            ("panels", lambda: self._restore_widgets(self._freecad_docks(), snap.get("docks", {}))),
            ("menus", lambda: [a.setVisible(snap.get("menus", {}).get(a.text(), True))
                               for a in self._freecad_menu_actions()]),
            ("status bar", lambda: self.mw.statusBar().setVisible(snap.get("statusbar", True))),
            ("3D view colors", lambda: params.restore(themes.VIEW_GROUP, snap["view"]) if "view" in snap else None),
            ("New shortcut", lambda: [a.setShortcut(QtGui.QKeySequence(snap.get("std_new") or "Ctrl+N"))
                                      for a in _std_new_actions()]),
            ("document tabs", lambda: self._restore_mdi(snap.get("mdi"))),
        ]
        for name, step in steps:
            try:
                step()
            except Exception as e:
                log.report("warning", "Could not restore FreeCAD's %s: %s" % (name, e), traceback.format_exc())
        self._hidden_by_us = set()

    # ----- activate / deactivate -----
    def activate(self):
        if self.active:
            return True
        stale = prefs.takeover_snapshot()
        try:
            self._snapshot = json.loads(stale) if stale else self._capture()
        except ValueError:
            self._snapshot = self._capture()
        prefs.set_takeover_snapshot(json.dumps(self._snapshot))
        try:
            self._hide_freecad()
            self._build()
            self._install_hooks()
            self.apply_theme()
            self.active = True
            self.refresh()
        except Exception as e:
            log.report("error", "InCad could not start its interface: %s" % e, traceback.format_exc())
            self.active = False
            self._teardown()
            self._restore(self._snapshot)
            prefs.clear_takeover_snapshot()
            self._snapshot = None
            return False
        return True

    def deactivate(self):
        if not self.active:
            return
        self.active = False
        self._teardown()
        snap = self._snapshot
        if snap is None:
            text = prefs.takeover_snapshot()
            snap = json.loads(text) if text else None
        if snap is not None:
            self._restore(snap)
        prefs.clear_takeover_snapshot()
        self._snapshot = None

    def _reactivate_if_still_open(self):
        import FreeCADGui as Gui
        wb = Gui.activeWorkbench()
        if self.mw.isVisible() and wb is not None and wb.name() == "InCadWorkbench":
            self.activate()

    # ----- InCad's UI -----
    @staticmethod
    def _setup_bar(bar):
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.toggleViewAction().setVisible(False)

    def _build(self):
        mw = self.mw
        self.theme = themes.current()
        top = QtWidgets.QToolBar("InCad", mw)
        top.setObjectName("InCadTop")
        self._setup_bar(top)
        self._widgets.append(top)
        box = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.title = TitleStrip(self.registry, self.theme, self._settings_menu)
        self.ribbon = Ribbon(self.registry, ribbon_layout.LAYOUT, mode="empty", size=prefs.ribbon_size(),
                             theme=self.theme)
        self.ribbon.sizeChanged.connect(prefs.set_ribbon_size)
        col.addWidget(self.title)
        col.addWidget(self.ribbon)
        box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        top.addWidget(box)
        mw.addToolBar(QtCore.Qt.TopToolBarArea, top)
        dock = QtWidgets.QDockWidget("Model", mw)
        dock.setObjectName("InCadBrowserDock")
        dock.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        dock.setTitleBarWidget(QtWidgets.QWidget())
        dock.setMinimumWidth(230)
        self._widgets.append(dock)
        self.browser = ModelBrowser(self.theme)
        dock.setWidget(self.browser)
        mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        bottom = QtWidgets.QToolBar("InCad Status", mw)
        bottom.setObjectName("InCadStatusBar")
        self._setup_bar(bottom)
        self._widgets.append(bottom)
        self.status = StatusBar(self.theme)
        self.status.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        bottom.addWidget(self.status)
        mw.addToolBar(QtCore.Qt.BottomToolBarArea, bottom)
        self.browser.featureActivated.connect(self._on_feature_activated)
        self.browser.endOfPartMoved.connect(self._on_end_of_part_moved)
        self.browser.actionTriggered.connect(self._on_browser_action)
        self.browser.parameterSet.connect(self._on_parameter_set)
        self.browser.parameterRemoved.connect(self._on_parameter_removed)

    def _build_menus(self):
        bar = self.mw.menuBar()
        for title, ids in MENUS:
            menu = QtWidgets.QMenu(title, bar)
            menu.setObjectName(MENU_PREFIX + title)
            for cmd_id in ids:
                if cmd_id is None:
                    menu.addSeparator()
                    continue
                if not self.registry.has(cmd_id):
                    continue
                cmd = self.registry.get(cmd_id)
                act = menu.addAction(themes.icon(cmd.icon, self.theme), cmd.label)
                if cmd.shortcut:
                    act.setShortcut(QtGui.QKeySequence(cmd.shortcut))
                act.triggered.connect(lambda _=False, i=cmd_id: self.registry.run(i))
            if title == "View":
                menu.addMenu(self.ribbon.size_menu(menu))
            bar.addAction(menu.menuAction())
            self._menus.append(menu)

    def _remove_menus(self):
        for menu in self._menus:
            self.mw.menuBar().removeAction(menu.menuAction())
            menu.deleteLater()
        self._menus = []

    def _teardown(self):
        self._remove_hooks()
        self._remove_menus()
        for w in self._widgets:
            try:
                if isinstance(w, QtWidgets.QToolBar):
                    self.mw.removeToolBar(w)
                else:
                    self.mw.removeDockWidget(w)
                w.deleteLater()
            except RuntimeError:
                pass
        self._widgets = []
        self.ribbon = self.title = self.browser = self.status = None

    def _settings_menu(self, parent):
        menu = QtWidgets.QMenu(parent)
        themes_menu = menu.addMenu("Theme")
        for value, label in (("auto", "Match macOS"), ("light", "Light"), ("dark", "Dark")):
            act = themes_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(prefs.theme() == value)
            act.triggered.connect(lambda _=False, v=value: self._set_theme_pref(v))
        menu.addMenu(self.ribbon.size_menu(menu))
        units = menu.addMenu("Units for New Files")
        current = prefs.default_units() if prefs.remember_new_choice() else "ask"
        for value, label in (("ask", "Ask every time"), ("mm", "Always millimeters"), ("in", "Always inches")):
            act = units.addAction(label)
            act.setCheckable(True)
            act.setChecked(current == value)
            act.triggered.connect(lambda _=False, v=value: self._set_new_units(v))
        return menu

    def _set_theme_pref(self, value):
        prefs.set_theme(value)
        self.apply_theme()

    @staticmethod
    def _set_new_units(value):
        if value == "ask":
            prefs.set_remember_new_choice(False)
        else:
            prefs.set_default_units(value)
            prefs.set_remember_new_choice(True)

    def apply_theme(self):
        from incad.core import params
        if self.ribbon is None:
            return
        self.theme = themes.current()
        qss = themes.stylesheet(self.theme)
        for w in self._widgets:
            w.setStyleSheet(qss)
        self.ribbon.set_theme(self.theme)
        self.title.set_theme(self.theme)
        self.browser.set_theme(self.theme)
        self.status.set_theme(self.theme)
        self._remove_menus()
        self._build_menus()
        params.write(themes.VIEW_GROUP, themes.view_params(self.theme))

    # ----- hooks -----
    def _install_hooks(self):
        import FreeCAD as App
        log.set_reporter(self._report)
        self.mw.installEventFilter(self)
        for w in self._freecad_toolbars() + self._freecad_docks():
            w.installEventFilter(self)
        self._observer = _DocObserver(self.schedule_refresh)
        App.addDocumentObserver(self._observer)
        QtWidgets.QApplication.instance().styleHints().colorSchemeChanged.connect(self._on_system_scheme)

    def _remove_hooks(self):
        import FreeCAD as App
        log.set_reporter(None)
        for w in [self.mw] + self._freecad_toolbars() + self._freecad_docks():
            try:
                w.removeEventFilter(self)
            except RuntimeError:
                pass
        if self._observer is not None:
            try:
                App.removeDocumentObserver(self._observer)
            except Exception:
                pass
            self._observer = None
        try:
            QtWidgets.QApplication.instance().styleHints().colorSchemeChanged.disconnect(self._on_system_scheme)
        except (RuntimeError, TypeError):
            pass

    def eventFilter(self, obj, event):
        try:
            etype = event.type()
            if obj is self.mw:
                if etype == QtCore.QEvent.Close and self.active:
                    self.deactivate()  # FreeCAD saves its window layout right after this
                    QtCore.QTimer.singleShot(0, self._reactivate_if_still_open)
                elif etype == QtCore.QEvent.ChildAdded and self.active:
                    child = event.child()
                    if isinstance(child, (QtWidgets.QToolBar, QtWidgets.QDockWidget)):
                        QtCore.QTimer.singleShot(0, lambda c=child: self._adopt(c))
            elif etype == QtCore.QEvent.Show and self.active and obj.objectName() not in OURS:
                QtCore.QTimer.singleShot(0, lambda o=obj: self._rehide(o))
        except Exception:
            log.logger().exception("InCad event filter")
        return False

    def _adopt(self, widget):
        try:
            if not self.active or widget.objectName() in OURS or widget.parent() is not self.mw:
                return
            if not widget.isHidden():
                self._hidden_by_us.add(widget.objectName())
            widget.hide()
            widget.installEventFilter(self)
        except RuntimeError:
            pass

    def _rehide(self, widget):
        try:
            if self.active and not widget.isHidden():
                self._hidden_by_us.add(widget.objectName())
                widget.hide()
        except RuntimeError:
            pass

    def _on_system_scheme(self, *_):
        if prefs.theme() == "auto":
            self.apply_theme()

    def _report(self, level, message):
        if self.status is not None:
            self.status.show_message(level, message)

    # ----- panels -----
    def schedule_refresh(self):
        if self._refresh_pending or self.ribbon is None:
            return
        self._refresh_pending = True
        QtCore.QTimer.singleShot(0, self.refresh)

    def refresh(self):
        self._refresh_pending = False
        if self.ribbon is None:
            return
        try:
            self._refresh()
        except Exception as e:
            log.report("warning", "InCad could not update its panels: %s" % e, traceback.format_exc())

    def _refresh(self):
        import FreeCAD as App
        from incad.core import document, tree
        doc = App.ActiveDocument
        is_part = document.is_incad_part(doc)
        self.ribbon.set_mode("part" if is_part else "empty")
        self.title.set_document_name(doc.Label if doc is not None else "")
        self.browser.set_nodes(tree.build(doc))
        self.browser.set_parameters(document.list_parameters(doc) if is_part else [])
        self.status.set_units(document.part_units(doc) if is_part else None)
        if is_part:
            bodies = document.bodies(doc)
            features = sum(1 for b in bodies for o in b.Group if o.TypeId != "Sketcher::SketchObject")
            self.status.set_stats(len(bodies), features)
            self.status.set_prompt("Ready")
        else:
            self.status.set_stats(None, None)
            self.status.set_prompt("Create or open a part" if doc is None else "This file was not made in InCad")

    # ----- browser actions -----
    @staticmethod
    def _doc():
        import FreeCAD as App
        return App.ActiveDocument

    def _on_feature_activated(self, name):
        self.status.show_message("info", "Editing features arrives with the feature tools (next InCad stage).")

    def _on_end_of_part_moved(self, name):
        from incad.core import document, safe
        doc = self._doc()
        if doc is None:
            return
        obj = doc.getObject(name) if name else None
        body = obj.getParentGeoFeatureGroup() if obj is not None else document.primary_body(doc)
        if body is None or body.TypeId != "PartDesign::Body":
            return
        safe.run_safely("Move End of Part", lambda: document.set_end_of_part(body, obj), doc)
        self.schedule_refresh()

    def _on_browser_action(self, action):
        from incad.core import document, safe
        doc = self._doc()
        if action == "convert" and doc is not None:
            safe.run_safely("Convert to InCad Part",
                            lambda: document.convert_to_part(doc, prefs.default_units()), doc)
            self.schedule_refresh()
        elif action == "freecad":
            self.registry.run("view.freecad")

    def _on_parameter_set(self, name, text):
        from incad.core import document, safe
        doc = self._doc()
        if doc is not None:
            safe.run_safely("Set %s" % name, lambda: document.set_parameter(doc, name, text), doc)
        self.schedule_refresh()

    def _on_parameter_removed(self, name):
        from incad.core import document, safe
        doc = self._doc()
        if doc is not None:
            safe.run_safely("Remove %s" % name, lambda: document.remove_parameter(doc, name), doc)
        self.schedule_refresh()


# ----- module API -----
def instance():
    return _shell


def activate():
    global _shell
    import FreeCADGui as Gui
    if _shell is None:
        _shell = Shell(Gui.getMainWindow(), commands.REGISTRY)
    return _shell.activate()


def deactivate():
    if _shell is not None:
        _shell.deactivate()


def apply_theme():
    if _shell is not None and _shell.active:
        _shell.apply_theme()


def focus_parameters():
    if _shell is not None and _shell.active:
        _shell.browser.focus_parameters()


def recover_after_crash():
    """At startup: if a snapshot survived (quit or crash while InCad was active) and InCad is not the active
    workbench, put FreeCAD's interface back the way it was."""
    import FreeCADGui as Gui
    text = prefs.takeover_snapshot()
    if not text:
        return
    wb = Gui.activeWorkbench()
    if wb is not None and wb.name() == "InCadWorkbench":
        return  # activate() reuses the saved snapshot
    try:
        Shell(Gui.getMainWindow(), commands.REGISTRY)._restore(json.loads(text))
        log.report("info", "InCad restored FreeCAD's interface after an unexpected exit")
    except Exception as e:
        log.report("warning", "InCad could not restore FreeCAD's interface: %s" % e, traceback.format_exc())
    finally:
        prefs.clear_takeover_snapshot()
```

- [ ] **Step 4: Wire the workbench (replace `InCad/InitGui.py`)**

```python
import FreeCADGui as Gui


class InCadWorkbench(Gui.Workbench):
    """Inventor/Alibre-style modeling. The whole UI is built by incad.ui.shell when the workbench activates."""

    MenuText = "InCad"
    ToolTip = "Inventor-style part and assembly modeling"

    def __init__(self):
        import os
        import incad
        self.__class__.Icon = os.path.join(os.path.dirname(incad.__file__), "resources", "icons", "light", "incad.svg")

    def Initialize(self):
        from incad import actions
        actions.register_all()

    def Activated(self):
        from incad import actions
        from incad.ui import shell
        actions.register_all()
        shell.activate()

    def Deactivated(self):
        from incad.ui import shell
        shell.deactivate()

    def GetClassName(self):
        return "Gui::PythonWorkbench"


def _incad_startup():
    """Remember the last non-InCad workbench (for ⇄ FreeCAD) and repair FreeCAD's UI after a crash."""
    try:
        from incad.core import prefs
        from incad.qt import QtCore
        from incad.ui import shell

        def remember(name):
            if name != "InCadWorkbench":
                prefs.set_last_workbench(name)

        Gui.getMainWindow().workbenchActivated.connect(remember)
        QtCore.QTimer.singleShot(1500, shell.recover_after_crash)
    except Exception as e:
        import FreeCAD
        FreeCAD.Console.PrintWarning("InCad startup hooks failed: %s\n" % e)


Gui.addWorkbench(InCadWorkbench())
_incad_startup()
```

- [ ] **Step 5: Run the GUI tests until they pass**

Tell the user: "FreeCAD windows opening for tests — hands off mouse/keyboard for ~1 minute."
Run: `tests/run_gui.sh tests/gui/test_shell.py tests/gui/test_shell_parts.py`
Expected: `9 passed, 0 failed` and `10 passed, 0 failed`. Then tell the user the mouse/keyboard are free.
Known adjustments if a test fails, keeping the test's intent:
- `Std_ViewHome` missing in `test_7_std_commands_exist` → map `view.home` to `Std_ViewIsometric` in `actions.STD_COMMANDS`.
- `workbenchActivated` not exposed (test_1 `last_workbench` assertion fails, FreeCAD log shows "InCad startup
  hooks failed") → in `_incad_startup` use
  `QtCore.QObject.connect(Gui.getMainWindow(), QtCore.SIGNAL("workbenchActivated(QString)"), remember)`.
- A FreeCAD toolbar re-appears after activation (test_1 lists it) → it is created after `Activated()`; the
  `ChildAdded`/`Show` filter must catch it — check that it is a direct child of `mw` and that its objectName is
  set by then (`_adopt` runs one event-loop turn later).

- [ ] **Step 6: Run every suite**

Run: `tests/run_all.sh` → Expected: `ALL SUITES PASSED`.

- [ ] **Step 7: Commit**

```bash
git add InCad/incad/ui/shell.py InCad/InitGui.py tests/gui/test_shell.py tests/gui/test_shell_parts.py
git commit -m "InCad: full UI takeover with exact restore, crash recovery, menus, ⌘N, theme and panels"
```

---

### Task 14: README, hands-on acceptance with the user

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the whole stage 1a.

- [ ] **Step 1: Write README.md**

```markdown
# InCad

An Inventor/Alibre-style workbench for FreeCAD 1.1.3 on macOS: ribbon, Model Browser with End of Part and
Parameters, light/dark in one click, ⇄ back to FreeCAD in one click. Files stay normal `.FCStd`.

## Install
    scripts/install.sh        # symlinks InCad/ into FreeCAD's Mod folder; restart FreeCAD
Then pick **InCad** in FreeCAD's workbench list.

## Tests
    tests/run_all.sh          # widgets (offscreen) + headless (freecadcmd) + GUI (opens FreeCAD windows)

Your FreeCAD settings are never used by the tests (each run gets a throwaway user.cfg).
Logs: ~/Library/Logs/InCad.log
```

- [ ] **Step 2: Full run**

Run: `tests/run_all.sh` → Expected: `ALL SUITES PASSED`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "InCad: README"
```

- [ ] **Step 4: Hands-on check with the user (their real FreeCAD)**

Ask the user to quit FreeCAD if it is open, then go through this list and report what differs:
1. Start FreeCAD, choose **InCad** in the workbench list → FreeCAD's toolbars, panels and menus disappear;
   InCad's title strip, ribbon, Model Browser and status bar appear; the menu bar shows File / Edit / View.
2. Click ☾ in the title strip → dark; click ☀︎ → light. ⚙ → Theme → Match macOS.
3. Right-click the ribbon → Small / Medium / Large.
4. ⌘N → the New dialog asks Part + Millimeters/Inches → a part appears; the browser shows Origin and End of Part;
   the status bar shows the units.
5. Parameters "+" → `Width` = `80 mm`; "+" → `HoleD` = `Width/8` → Result `10 mm`. Try `2x` as a name → red message.
6. Click **⇄ FreeCAD** → FreeCAD looks exactly as before. Switch back to InCad.
7. With InCad active, quit FreeCAD (⌘Q), start it again → FreeCAD's interface is normal.
8. While InCad is active: ⌘Q still quits, FreeCAD ▸ Settings… still opens.

- [ ] **Step 5: Record the outcome**

Update the memory file `incad-project.md` (status: plan 1a done, what the user reported) and, if the user found
issues, add them as tasks at the top of plan 1b before writing it.
