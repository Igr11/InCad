"""The ribbon's Parameters button opens the Parameters window (the user: the button did nothing): every parameter with
what uses it; a value typed there drives the part, a feature value renamed, Delete Unused removes what nothing uses
(one undo step), the panel under the browser stays in step; Close, then the button again."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import commands, document, model, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def win():
    return s().parameters_window


def names():
    return [t[0] for t in win().row_texts()]


def row(name):
    return dict((t[0], t) for t in win().row_texts())[name]


def type_into(name, column, text):
    """A double-click on the cell, the text typed, Enter (the user's way)."""
    w = win()
    r = names().index(name)
    w.table.setCurrentCell(r, column)
    w.table.editItem(w.table.item(r, column))
    harness.pump(200)
    editor = w.table.findChild(QtWidgets.QLineEdit)
    assert editor is not None, "no cell editor"
    editor.selectAll()
    QTest.keyClicks(editor, text)
    QTest.keyClick(editor, QtCore.Qt.Key_Return)
    harness.pump(1200)


def test_0_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    from incad.features import extrude
    from headless import util
    body = document.primary_body(doc())
    sk = util.add_rect_sketch(body)
    doc().recompute()
    f = extrude.create(doc(), body, sk, extrude.defaults(doc(), body, sk))
    doc().recompute()
    ST["pad"], ST["depth"] = f.Name, model.bound_parameter(f, "Length")
    assert ST["depth"], "the Extrude has no named Distance"
    ST["spare"] = model.new_feature_parameter(doc(), "3 mm")  # a deleted feature's value
    document.set_parameter(doc(), "Width", "40 mm")
    doc().recompute()
    s().schedule_refresh()
    harness.pump(800)


def test_1_the_button_opens_the_window():
    button = s().ribbon.button("view.parameters")
    assert button is not None, "no Parameters button on the ribbon"
    QTest.mouseClick(button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert win() is not None and win().isVisible(), "the Parameters button opened nothing"
    assert {ST["depth"], ST["spare"], "Width"} <= set(names()), names()
    assert doc().getObject(ST["pad"]).Label in row(ST["depth"])[3], row(ST["depth"])
    assert row(ST["spare"])[3] == "— not used", row(ST["spare"])
    if os.environ.get("INNCAD_SHOT"):
        win().grab().save(os.environ["INNCAD_SHOT"])


def test_2_a_value_typed_drives_the_part():
    type_into(ST["depth"], 1, "14 mm")
    pad = doc().getObject(ST["pad"])
    assert abs(pad.Length.Value - 14) < 1e-6, pad.Length
    assert row(ST["depth"])[2] == "14 mm", row(ST["depth"])
    assert (ST["depth"], "14 mm", "14 mm") in s().browser.parameter_rows(), "the panel is not in step"


def test_3_a_bad_formula_is_said_in_the_window():
    type_into("Width", 1, "Nope * 2")
    assert win().message.text(), "no message for a bad formula"
    assert row("Width")[2] == "40 mm", row("Width")


def test_4_rename_a_feature_value():
    type_into(ST["depth"], 0, "Depth")
    assert "Depth" in names() and ST["depth"] not in names(), names()
    assert model.bound_parameter(doc().getObject(ST["pad"]), "Length") == "Depth"


def test_5_delete_unused_in_one_undo_step():
    QTest.mouseClick(win().unused_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert ST["spare"] not in names() and "Width" not in names(), names()
    assert "Depth" in names()
    assert "Deleted 2" in win().message.text(), win().message.text()
    commands.REGISTRY.run("edit.undo")
    harness.pump(1200)
    assert ST["spare"] in names() and "Width" in names(), names()


def test_6_close_and_open_again():
    win().close()
    harness.pump(500)
    assert s().parameters_window is None
    commands.REGISTRY.run("view.parameters")
    harness.pump(800)
    assert win() is not None and win().isVisible()
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    assert "Depth" in names()
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    win().close()
    harness.pump(300)


def test_9_cleanup():
    App.closeDocument(doc().Name)
    harness.pump(300)


harness.run([test_0_part, test_1_the_button_opens_the_window, test_2_a_value_typed_drives_the_part,
             test_3_a_bad_formula_is_said_in_the_window, test_4_rename_a_feature_value,
             test_5_delete_unused_in_one_undo_step, test_6_close_and_open_again, test_9_cleanup])
