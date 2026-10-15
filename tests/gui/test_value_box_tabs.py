"""InCad closing a sketch while FreeCAD's Dimension tool runs crashed FreeCAD (DrawSketchHandlerDimension::deactivated
-> ViewProviderSketch::slotSolverUpdate). The user's crash: Enter in the dimension box, the closing box handed the
keyboard to another document's tab, that tab's own workbench (SaveWBbyTab, on in the user's FreeCAD) took over and
InCad left with the tool still running. Here: Enter in the box with another tab open, Finish Sketch and leaving InCad
with the tool running."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs, sketch as sketches  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["doc"])


def editing():
    gdoc = Gui.getDocument(ST["doc"])
    v = gdoc.getInEdit() if gdoc is not None else None
    return v.Object if v is not None else None


def active_tab():
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    sub = mdi.activeSubWindow() if mdi is not None else None
    return sub.windowTitle() if sub is not None else None


def test_0_setup():
    App.ParamGet("User parameter:BaseApp/Preferences/View").SetBool("SaveWBbyTab", True)
    prefs.set_remember_new_choice(True)
    other = App.newDocument("OtherTab")  # a plain FreeCAD document in Part Design: its tab remembers that
    ST["other"] = other.Name
    harness.pump(500)
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    ST["doc"] = App.ActiveDocument.Name
    assert ST["doc"] != ST["other"]
    body = document.primary_body(doc())
    sk = util.add_rect_sketch(body, name="SketchA")
    sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
    sk.addGeometry(Part.Ellipse(App.Vector(40, 0, 0), App.Vector(30, 0, 0), App.Vector(30, 5, 0)), False)
    doc().recompute()
    sketches.name_new_dimensions(doc())
    ST["sk"] = sk.Name
    ST["dim"] = next(c.Name for c in sk.Constraints if c.Name)
    harness.pump(300)
    s().sketches.edit(sk)
    harness.pump(1200)
    assert editing() is not None and editing().Name == sk.Name, editing()
    ST["tab"] = active_tab()


def test_1_enter_in_the_box_with_the_dimension_tool_running_keeps_the_sketch():
    sk = doc().getObject(ST["sk"])
    Gui.runCommand("Sketcher_Dimension")
    harness.pump(600)
    s().open_value_box(sk, ST["dim"])
    harness.pump(500)
    edit = s().value_box.edit
    assert QtWidgets.QApplication.focusWidget() is edit, ("the box has the keyboard", QtWidgets.QApplication.focusWidget(),
                                                          "(screen locked?)")
    QTest.keyClicks(edit, "15")
    QTest.keyClick(edit, QtCore.Qt.Key_Return)
    harness.pump(1500)
    assert s().value_box is None, "Enter closes the box"
    assert abs(sk.getDatum(ST["dim"]).Value - 15) < 1e-6, sk.getDatum(ST["dim"])
    assert active_tab() == ST["tab"], ("the keyboard stays in this tab", active_tab(), ST["tab"])
    assert Gui.activeWorkbench().name() == "InCadWorkbench", Gui.activeWorkbench().name()
    assert editing() is not None and editing().Name == ST["sk"], editing()


def test_2_finish_sketch_with_the_dimension_tool_running():
    """Finish Sketch while FreeCAD's Dimension tool runs (it is restarted after a value, as Inventor keeps
    dimensioning): resetEdit under the tool crashed FreeCAD every time."""
    harness.pump(600)  # the tool restarted after the value
    Gui.runCommand("Sketcher_Dimension")
    harness.pump(600)
    s().sketches.finish()
    harness.pump(800)
    assert editing() is None, editing()


def test_3_leaving_incad_with_the_dimension_tool_running():
    """Another workbench (another tab's, a menu) while the tool runs: InCad closes the sketch on the way out."""
    s().sketches.edit(doc().getObject(ST["sk"]))
    harness.pump(1200)
    assert editing() is not None
    Gui.runCommand("Sketcher_Dimension")
    harness.pump(600)
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert editing() is None, editing()
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)


def test_4_cleanup():
    for name in (ST["doc"], ST["other"]):
        App.closeDocument(name)
        harness.pump(400)


harness.run([test_0_setup, test_1_enter_in_the_box_with_the_dimension_tool_running_keeps_the_sketch,
             test_2_finish_sketch_with_the_dimension_tool_running, test_3_leaving_incad_with_the_dimension_tool_running,
             test_4_cleanup])
