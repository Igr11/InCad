"""Make Assembly in a real window: a part with a box drawn away, the dialog's names, OK opens the assembly tab."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import assembly, commands, document, prefs  # noqa: E402

ST = {}


def test_0_part_with_two_pieces():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    part = document.primary_body(doc)
    a = part.newObject("PartDesign::AdditiveBox", "Plate")
    a.Length, a.Width, a.Height = 40, 20, 5
    b = part.newObject("PartDesign::AdditiveBox", "Block")
    b.Length = b.Width = b.Height = 10
    b.Placement = App.Placement(App.Vector(60, 0, 0), App.Rotation())
    part.Tip = b
    doc.recompute()
    folder = os.path.join(os.environ.get("FREECAD_USER_TEMP", tempfile.mkdtemp()), "mk")
    os.makedirs(folder, exist_ok=True)
    doc.saveAs(os.path.join(folder, "Bench.FCStd"))
    harness.pump(500)
    ST.update(folder=folder)


def test_1_dialog_then_ok_opens_the_assembly():
    def press_ok():
        dlg = QtWidgets.QApplication.activeModalWidget()
        assert dlg is not None and dlg.windowTitle() == "Make Assembly", dlg
        assert dlg.names() == ("Bench-Assembly", ["Bench-Solid1", "Bench-Solid2"]), dlg.names()
        dlg.ok_button.click()
    from incad.core import make_assembly as ma
    part0 = App.ActiveDocument
    Gui.getDocument(part0.Name).Modified = False  # as after a save from the window (App's saveAs leaves the flag)
    trace = [("start", Gui.getDocument(part0.Name).Modified)]
    real_make, real_open = ma.make, App.openDocument
    def make(*a, **kw):
        trace.append(("before make", Gui.getDocument(part0.Name).Modified))
        out = real_make(*a, **kw)
        trace.append(("after make", Gui.getDocument(part0.Name).Modified))
        return out
    def opened(*a, **kw):
        out = real_open(*a, **kw)
        trace.append(("after open", Gui.getDocument(part0.Name).Modified))
        return out
    ma.make, App.openDocument = make, opened
    ST["trace"] = trace
    QtCore.QTimer.singleShot(1500, press_ok)
    r = commands.REGISTRY.run("file.make_assembly")
    ma.make, App.openDocument = real_make, real_open
    harness.pump(3000)
    assert getattr(r, "ok", True), getattr(r, "error", "")
    for name in ("Bench-Assembly", "Bench-Solid1", "Bench-Solid2"):
        assert os.path.exists(os.path.join(ST["folder"], name + ".FCStd")), name
    asm_doc = App.ActiveDocument
    assert assembly.is_assembly(asm_doc), asm_doc.Label
    part = next(d for d in App.listDocuments().values() if d.Label == "Bench")
    assert not Gui.getDocument(part.Name).Modified, ("Make Assembly does not change the part (no save prompt for it)",
                                                     ST["trace"])
    assert len(assembly.components(asm_doc)) == 2


harness.run([test_0_part_with_two_pieces, test_1_dialog_then_ok_opens_the_assembly])
