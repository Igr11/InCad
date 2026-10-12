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
REFRESH = "edit.update"


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


def test_2_back_in_the_assembly_it_asks_and_a_no_shows_the_sign_until_refresh():
    """The user: no update by itself — ask; declined, show that it needs an update; Refresh clears it."""
    from incad.core import tree
    from incad.ui import shell
    asm_doc = next(d for d in App.listDocuments().values() if assembly.is_assembly(d))
    block = assembly.components(asm_doc)[1]
    part = block.LinkedObject.Document
    App.setActiveDocument(part.Name)
    harness.pump(500)
    box = next(o for o in part.Objects if o.TypeId == "PartDesign::AdditiveBox")
    box.Height = 25
    part.recompute()
    harness.pump(300)
    asked = []
    shell.UPDATE_ASK = lambda label: (asked.append(label), False)[1]
    try:
        App.setActiveDocument(asm_doc.Name)
        harness.pump(1500)
    finally:
        shell.UPDATE_ASK = None
    assert asked, "it asks"
    # (a link always shows its part as it is now; the update is the assembly's own recompute: constraints, cuts)
    assert "needs update" in tree.build(asm_doc)[0].detail.lower()
    commands.REGISTRY.run(REFRESH)
    harness.pump(1000)
    assert abs(block.Shape.BoundBox.ZLength - 25) < 1e-6, block.Shape.BoundBox
    assert "needs update" not in tree.build(asm_doc)[0].detail.lower()


def test_3_place_into_a_new_unsaved_assembly():
    """The user: Place in a new assembly showed 'Save the assembly first' (a save dialog: the part files greyed out),
    so no part could be chosen. Now the part is chosen first and the assembly is saved next to it."""
    from incad.ui import shell
    from incad.core import prefs
    seen_modals = []

    def close_modal():
        w = QtWidgets.QApplication.activeModalWidget()
        if w is not None:
            seen_modals.append((w.windowTitle(), w.metaObject().className(),
                                getattr(w, "text", lambda: "")() if hasattr(w, "text") else ""))
            w.reject() if hasattr(w, "reject") else w.close()
    timer = QtCore.QTimer()
    timer.timeout.connect(close_modal)
    timer.start(300)
    ST["modals"] = seen_modals
    ST["timer"] = timer
    commands.REGISTRY.run("file.new_assembly")
    harness.pump(1000)
    asm_doc = App.ActiveDocument
    assert assembly.is_assembly(asm_doc) and not asm_doc.FileName
    part = os.path.join(ST["folder"], "Bench-Solid1.FCStd")
    link = shell.assembly_place(part)
    harness.pump(1500)
    timer.stop()
    assert not seen_modals, seen_modals
    assert link is not None, "placed"
    assert asm_doc.FileName == os.path.join(ST["folder"], asm_doc.Label + ".FCStd"), asm_doc.FileName
    assert len(assembly.components(asm_doc)) == 1


harness.run([test_0_part_with_two_pieces, test_1_dialog_then_ok_opens_the_assembly,
             test_2_back_in_the_assembly_it_asks_and_a_no_shows_the_sign_until_refresh,
             test_3_place_into_a_new_unsaved_assembly])
