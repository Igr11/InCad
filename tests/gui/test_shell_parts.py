import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
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


def _editor():
    """The open cell editor (the window may not have keyboard focus while tests run)."""
    b = s().browser
    return QtWidgets.QApplication.focusWidget() if isinstance(QtWidgets.QApplication.focusWidget(), QtWidgets.QLineEdit) \
        else b.params.findChild(QtWidgets.QLineEdit)


def test_3b_typing_a_parameter_like_a_user():
    from PySide6.QtTest import QTest
    from incad.qt import QtCore
    b = s().browser
    QTest.mouseClick(b.add_button, QtCore.Qt.LeftButton)
    harness.pump(300)
    assert _editor() is not None, "+ must open the name cell for typing"
    QTest.keyClicks(_editor(), "Depth")
    QTest.keyClick(_editor(), QtCore.Qt.Key_Tab)
    harness.pump(300)
    QTest.keyClicks(_editor(), "5 mm")
    QTest.keyClick(_editor(), QtCore.Qt.Key_Return)
    harness.pump(800)
    assert ("Depth", "", "5 mm") in document.list_parameters(App.ActiveDocument), document.list_parameters(App.ActiveDocument)
    assert ("Depth", "5 mm", "5 mm") in b.parameter_rows(), b.parameter_rows()


def test_4_plain_file():
    """A file made outside InCad (a bare Body) is an InCad part as soon as it is in front (the user: such parts get
    every tool) — no Convert button to find first."""
    d = App.newDocument("Plain")
    d.addObject("PartDesign::Body", "Body")
    d.recompute()
    s().schedule_refresh()
    harness.pump(1200)
    assert document.is_incad_part(d)
    assert s().browser.add_button.isEnabled(), "parameters locked in a file made an InCad part"
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
    s().ribbon.set_size("medium")
    assert prefs.ribbon_size() == "medium"
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


def test_8b_real_cmd_z_undoes():
    from PySide6.QtTest import QTest
    doc = App.ActiveDocument
    safe.run_safely("Set Keys", lambda: document.set_parameter(doc, "Keys", "2 mm"), doc)
    harness.pump(300)
    mw.raise_()
    mw.activateWindow()
    harness.pump(500)
    target = QtWidgets.QApplication.focusWidget() or mw
    QTest.keyClick(target, QtCore.Qt.Key_Z, QtCore.Qt.ControlModifier)
    harness.pump(600)
    assert "Keys" not in [p[0] for p in document.list_parameters(doc)], "⌘Z did not undo"


def test_8c_quit_is_in_incads_file_menu():
    from incad.ui import shell as sh
    menus = [m for m in s()._menus if m.title() == "File"]
    acts = [a for a in menus[0].actions() if a.text() == "Quit"]
    assert acts, [a.text() for a in menus[0].actions()]
    assert acts[0].shortcut().toString() in ("Ctrl+Q", "Meta+Q"), acts[0].shortcut().toString()
    assert acts[0].menuRole() == QtGui.QAction.NoRole
    assert "Std_Quit" in sh.TAKEN_SHORTCUTS
    # the app menu's Quit is InCad's: FreeCAD's Exit sits in a hidden menu where a real click never arrives
    roles = [a.objectName() for a in Gui.getMainWindow().findChildren(QtGui.QAction)
             if a.menuRole() == QtGui.QAction.QuitRole]
    assert roles == ["InCadAppQuit"], roles


def test_8d_cmd_w_uses_incads_save_dialog():
    from incad.ui import shell as sh
    doc = App.ActiveDocument
    document.set_parameter(doc, "Spare", "1 mm")
    Gui.getDocument(doc.Name).Modified = True
    asked = []
    sh.SAVE_ASK = lambda files: (asked.append(files), ("cancel", []))[1]
    commands.REGISTRY.run("file.close")
    harness.pump(400)
    assert asked and asked[0][0][0] == doc.Label, asked
    assert doc.Name in App.listDocuments(), "Cancel keeps the file open"
    sh.SAVE_ASK = lambda files: ("discard", [])
    name = doc.Name
    commands.REGISTRY.run("file.close")
    harness.pump(600)
    sh.SAVE_ASK = None
    assert name not in App.listDocuments()


def test_9_close_all_documents():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    harness.pump(800)
    assert s().ribbon.tab_names() == ["Get Started", "View"], s().ribbon.tab_names()
    assert s().browser.tree_rows() == []
    assert s().status.texts()["prompt"] == "Create or open a part"
    with open(os.environ["INCAD_LOG"]) as f:
        assert "could not update its panels" not in f.read()


def test_8e_event_filter_ignores_teardown_events():
    """Widgets being destroyed on quit send events through InCad's filter: it must not search for widgets then
    (a findChild on half-destroyed widgets aborted FreeCAD at exit)."""
    sh = s()
    calls = []
    real = sh._mdi
    sh._mdi = lambda: (calls.append(1), real())[1]
    try:
        vp = real().viewport()
        for etype in (QtCore.QEvent.ChildRemoved, QtCore.QEvent.Destroy, QtCore.QEvent.Paint,
                      QtCore.QEvent.Hide, QtCore.QEvent.DeferredDelete):
            sh.eventFilter(vp, QtCore.QEvent(etype))
            sh.eventFilter(Gui.getMainWindow(), QtCore.QEvent(etype))
    finally:
        del sh._mdi
    assert not calls, len(calls)


harness.run([test_0_activate, test_1_new_part, test_2_switching_documents_updates_panels, test_3_parameters, test_3b_typing_a_parameter_like_a_user,
             test_4_plain_file, test_5_theme_toggle, test_6_ribbon_size_persists, test_7_std_commands_exist,
             test_8_failed_command_then_undo, test_8b_real_cmd_z_undoes, test_8c_quit_is_in_incads_file_menu,
             test_8d_cmd_w_uses_incads_save_dialog, test_8e_event_filter_ignores_teardown_events, test_9_close_all_documents])
