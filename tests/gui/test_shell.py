import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
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


TAKEN = {"Std_New": "Ctrl+N", "Std_Open": "Ctrl+O", "Std_Save": "Ctrl+S", "Std_SaveAs": "Ctrl+Shift+S",
         "Std_CloseActiveWindow": "Ctrl+W", "Std_Undo": "Ctrl+Z", "Std_Redo": "Ctrl+Shift+Z"}


def std_new_shortcut():
    return Gui.Command.get("Std_New").getAction()[0].shortcut().toString()


def std_shortcuts():
    return {c: Gui.Command.get(c).getAction()[0].shortcut().toString() for c in TAKEN}


def assert_common_restored():
    assert view_params() == BASE["view"], (view_params(), BASE["view"])
    assert std_new_shortcut() == BASE["new"], std_new_shortcut()
    assert std_shortcuts() == BASE["shortcuts"], (std_shortcuts(), BASE["shortcuts"])
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
    BASE.update(state=state(), tb=toolbar_params(), view=view_params(), new=std_new_shortcut(), shortcuts=std_shortcuts())
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
    assert all(v == "" for v in std_shortcuts().values()), std_shortcuts()
    incad = {a.text(): a.shortcut().toString() for a in mw.menuBar().actions() if a.menu()
             and a.menu().objectName().startswith("InCadMenu_") for a in a.menu().actions()}
    for label, seq in (("Open", "Ctrl+O"), ("Save", "Ctrl+S"), ("Save As", "Ctrl+Shift+S"), ("Close", "Ctrl+W"),
                       ("Undo", "Ctrl+Z"), ("Redo", "Ctrl+Shift+Z")):
        assert incad.get(label) == seq, (label, incad)
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
    assert shell.instance() is None or not shell.instance().active
    assert_reshown(before)
    harness.pump(800)
    assert shell.instance() is not None and shell.instance().active, "the window stayed open: InCad comes back"


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


def test_9_no_reactivation_while_a_dialog_is_open():
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    s = shell.instance()
    assert s.active
    box = QtWidgets.QMessageBox(mw)
    box.setText("Save changes?")
    box.setWindowModality(QtCore.Qt.ApplicationModal)
    box.open()
    harness.pump(300)
    s.eventFilter(mw, QtGui.QCloseEvent())  # what quitting with unsaved changes does first
    harness.pump(800)
    assert shell.instance() is None or not shell.instance().active, "InCad came back behind the dialog"
    QtWidgets.QApplication.activeModalWidget().reject()  # quit cleanup released old Python references
    harness.pump(1000)
    assert shell.instance() is not None and shell.instance().active, "InCad should come back once the dialog is gone"


def test_10_takeover_waits_for_an_open_edit():
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    doc = App.newDocument("Edit")
    body = doc.addObject("PartDesign::Body", "Body")
    sketch = body.newObject("Sketcher::SketchObject", "Sketch")
    doc.recompute()
    Gui.ActiveDocument.setEdit(sketch.Name)
    harness.pump(1000)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(800)
    s = shell.instance()
    assert not s.active, "took over while a sketch was being edited"
    assert mw.findChild(QtWidgets.QToolBar, "InCadTop") is None
    Gui.ActiveDocument.resetEdit()
    harness.pump(1500)
    assert s.active, "InCad should open once the edit is finished"
    App.closeDocument(doc.Name)
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)


harness.run([test_0_baseline_in_partdesign, test_1_activate_takes_over, test_2_new_shortcut_moves_to_incad,
             test_3_reshown_toolbar_is_hidden_again, test_4_return_to_freecad_restores_everything,
             test_5_quit_path_restores_then_reactivates, test_6_restore_from_saved_snapshot_when_memory_lost,
             test_7_recover_after_crash_at_startup, test_8_activation_failure_restores,
             test_9_no_reactivation_while_a_dialog_is_open, test_10_takeover_waits_for_an_open_edit])
