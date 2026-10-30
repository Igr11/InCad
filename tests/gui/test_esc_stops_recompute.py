"""Esc stops a long recompute (the user: Escape must cancel any operation): FreeCAD's progress bar takes Esc between
features; InCad's own Esc shortcut must not swallow it."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import commands, prefs  # noqa: E402

RUNS = []


class _Slow:
    def __init__(self, obj):
        obj.Proxy = self

    def execute(self, obj):
        RUNS.append(obj.Name)
        end = time.time() + 0.3
        while time.time() < end:
            pass


def doc():
    return App.ActiveDocument


def test_0_slow_objects():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    for i in range(20):
        o = doc().addObject("Part::FeaturePython", "Slow%02d" % i)
        _Slow(o)
    harness.pump(300)


def _recompute_with_esc_at(ms):
    del RUNS[:]
    for o in doc().Objects:
        if o.Name.startswith("Slow"):
            o.touch()
    seen = []

    def press():
        w = QtWidgets.QApplication.focusWidget() or Gui.getMainWindow()
        QTest.keyClick(w, QtCore.Qt.Key_Escape)

    def left_open():  # a question nobody answered
        m = QtWidgets.QApplication.activeModalWidget()
        if m is not None:
            seen.append(getattr(m, "text", lambda: "")())
            yes = m.button(QtWidgets.QMessageBox.Yes) if isinstance(m, QtWidgets.QMessageBox) else None
            yes.click() if yes is not None else m.close()
        if len(seen) < 3:
            QtCore.QTimer.singleShot(1500, left_open)
    QtCore.QTimer.singleShot(ms, press)
    QtCore.QTimer.singleShot(ms + 1500, left_open)
    doc().recompute()
    left = [o.Name for o in doc().Objects if o.Name.startswith("Slow") and "Touched" in o.State]
    return left, seen


def test_1_esc_during_the_recompute_stops_it():
    left, seen = _recompute_with_esc_at(1500)
    assert len(RUNS) < 20 and left, ("ran %d of 20" % len(RUNS), left)
    assert not seen, "the abort question was left to the user: %s" % seen


def test_2_with_a_dialog_open_esc_still_stops_the_recompute():
    from incad.ui import shell
    commands.REGISTRY.run("work.plane")
    harness.pump(1200)
    assert shell.instance().feature_session is not None
    left, seen = _recompute_with_esc_at(1500)
    assert len(RUNS) < 20 and left and not seen, ("ran %d of 20" % len(RUNS), left, seen)
    shell.instance().feature_session.cancel()
    harness.pump(600)


def test_3_a_long_loop_stops_on_esc():
    from incad import host
    from incad.core import safe
    safe.watch_esc()
    real = host.esc_down
    host.esc_down = lambda: True
    try:
        safe.stop_if_esc("the test")
        raise AssertionError("not stopped")
    except safe.Stopped as e:
        assert "Esc" in str(e)
    finally:
        host.esc_down = real
    safe.stop_if_esc("the test")  # Esc not down any more: goes on


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_slow_objects, test_1_esc_during_the_recompute_stops_it,
             test_2_with_a_dialog_open_esc_still_stops_the_recompute, test_3_a_long_loop_stops_on_esc, test_9_cleanup])
