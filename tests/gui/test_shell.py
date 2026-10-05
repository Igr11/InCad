import json
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


def assert_common_restored():
    assert view_params() == BASE["view"], (view_params(), BASE["view"])
    assert std_new_shortcut() == BASE["new"], std_new_shortcut()
    assert not prefs.takeover_snapshot()


def assert_restored():
    """Back in PartDesign: everything exactly as in the baseline."""
    now = state()
    for key in ("toolbars", "docks", "menus"):
        diff = {k: (BASE["state"][key].get(k), v) for k, v in now[key].items() if BASE["state"][key].get(k, v) != v}
        assert not diff, (key, diff)
    assert now["statusbar"] == BASE["state"]["statusbar"]
    assert_common_restored()


def assert_reshown(before):
    """Still in the InCad workbench: everything visible before the takeover is visible again
    (FreeCAD itself keeps PartDesign's toolbars and the Tasks panel hidden in other workbenches)."""
    now = state()
    for key in ("toolbars", "docks", "menus"):
        missing = [k for k, v in before[key].items() if v and not now[key].get(k, False)]
        assert not missing, (key, missing)
    assert now["statusbar"] == before["statusbar"]
    assert_common_restored()


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
    titles = [a.text() for a in mw.menuBar().actions() if a.isVisible() and not a.isSeparator()]
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
    before = json.loads(prefs.takeover_snapshot())
    s.eventFilter(mw, QtGui.QCloseEvent())
    assert not s.active
    assert_reshown(before)
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
    hidden_by_incad = [name for name, visible in json.loads(snap)["toolbars"].items() if visible]
    for t in mw.findChildren(QtWidgets.QToolBar):  # what a crash leaves behind: the toolbars InCad had hidden
        if t.parent() is mw and t.objectName() in hidden_by_incad:
            t.hide()
    prefs.set_takeover_snapshot(snap)
    shell.recover_after_crash()
    harness.pump(300)
    assert_restored()


def test_8_activation_failure_restores():
    s = shell.instance()
    original = s._hide_freecad
    before = {}

    def broken():
        before.update(state())  # FreeCAD's own UI for the InCad workbench, just before InCad hides anything
        original()
        raise RuntimeError("simulated")

    s._hide_freecad = broken
    try:
        Gui.activateWorkbench("InCadWorkbench")
        harness.pump(800)
        assert not s.active
        assert before, "takeover never started"
        assert_reshown(before)
    finally:
        s._hide_freecad = original
        Gui.activateWorkbench("PartDesignWorkbench")
        harness.pump(800)


harness.run([test_0_baseline_in_partdesign, test_1_activate_takes_over, test_2_new_shortcut_moves_to_incad,
             test_3_reshown_toolbar_is_hidden_again, test_4_return_to_freecad_restores_everything,
             test_5_quit_path_restores_then_reactivates, test_6_restore_from_saved_snapshot_when_memory_lost,
             test_7_recover_after_crash_at_startup, test_8_activation_failure_restores])
