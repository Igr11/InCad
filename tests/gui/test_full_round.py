"""Fillet ▸ Full Round Fillet (the user: two fillets on a rectangle meeting on its face, picked by its edges): the two
long edges of a plate's end picked in the dialog make the end a half cylinder across its thickness; OK keeps it at
the end of the history; it opens again for edit with its two edges."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.features import full_round  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def fs():
    return s().feature_session


def body():
    return document.primary_body(App.ActiveDocument)


def test_0_plate():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    pad = util.add_pad(body(), util.add_rect_sketch(body(), 40, 20, "Plate"), 6)
    body().Tip = pad
    App.ActiveDocument.recompute()
    harness.pump(500)
    ST["volume"] = pad.Shape.Volume
    ST["pad"] = pad.Name


def test_1_pick_the_end_and_ok():
    Gui.Selection.clearSelection()
    r = commands.REGISTRY.run("feature.full_round")
    harness.pump(1200)
    assert r.ok, r.error
    assert fs() is not None and fs().kind is full_round, fs()
    pad = App.ActiveDocument.getObject(ST["pad"])  # the part before the new step: shown while picking
    ends = [i + 1 for i, e in enumerate(pad.Shape.Edges) if abs(e.CenterOfMass.x - 40) < 1e-9
            and abs(abs((e.Vertexes[-1].Point - e.Vertexes[0].Point).normalize().y) - 1) < 1e-9]
    assert len(ends) == 2, ends  # the end's two long edges, 6 apart
    for i in ends:
        Gui.Selection.addSelection(App.ActiveDocument.Name, pad.Name, "Edge%d" % i)
        harness.pump(600)
    harness.pump(1800)
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, (f and f.getStatusString(), fs().dialog.error_text())
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    assert fs() is None
    tip = body().Tip
    assert full_round.claims(tip) and "Invalid" not in tip.State, tip.getStatusString()
    cut = 2 * (9 - math.pi * 9 / 4) * 20
    assert abs(ST["volume"] - tip.Shape.Volume - cut) < 1e-3, (ST["volume"], tip.Shape.Volume)
    ST["f"] = tip.Name


def test_2_edit_opens_with_its_face():
    f = App.ActiveDocument.getObject(ST["f"])
    s().edit_feature(f)
    harness.pump(1200)
    assert fs() is not None and len(fs().dialog.values()["edges"].split(",")) == 2, fs() and fs().dialog.values()
    QTest.mouseClick(fs().dialog.cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    if fs() is not None:
        fs().cancel()
        harness.pump(400)
    assert "Invalid" not in f.State


def test_9_cleanup():
    App.closeDocument(App.ActiveDocument.Name)


harness.run([test_0_plate, test_1_pick_the_end_and_ok, test_2_edit_opens_with_its_face, test_9_cleanup])
