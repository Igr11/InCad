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
    assert not s().browser.add_button.isEnabled(), "parameters must be locked in a plain FreeCAD file"
    s().browser.actionTriggered.emit("convert")
    harness.pump(800)
    assert document.is_incad_part(d)
    assert s().browser.add_button.isEnabled()
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
