"""FreeCAD-side half of the real-input robot (tests/real). Started by run_scenario.sh as
`FreeCAD -u <tmp>/user.cfg driver.py` with INCAD_REPO, FC_OUT (state/command file stem) and INCAD_SCENARIO set.

It opens InCad with a new part, then waits for commands from the runner in FC_OUT.cmd (one per file):
  cmd:<registry id>      run an InCad command
  setup:<name>           rect_sketch_open | block_with_top_sketch | empty_part | block
  py:<expression>        evaluate (App, Gui, shell, commands, document, sketches, ST in scope)
  where:<spots>          nothing to do: the state answers it
and after every command (and every 150 ms) writes FC_OUT.state: the model and UI facts the runner asserts on,
and the screen positions it clicks (dimension labels, ribbon buttons, model-tree rows, panel/dialog buttons,
3D points). All input itself comes from the runner's real mouse/keyboard tools."""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6 import QtCore, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs, safe, sketch as sketches  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

OUT = os.environ["FC_OUT"]
ST = {"points": {}, "ribbon_ids": [], "last_cmd": None, "error": ""}
RIBBON_DEFAULT = ["sketch.start", "sketch.dimension", "sketch.finish", "sketch.line", "sketch.circle",
                  "sketch.construction", "feature.extrude", "feature.hole", "feature.revolve", "view.look_at"]


# ----- screen positions -----
def _viewport():
    vs = [w for w in Gui.getMainWindow().findChildren(QtWidgets.QGraphicsView) if w.isVisible()]
    return vs[0].viewport() if vs else None


def screen_xy(p):
    """Global screen pixels of a global 3D point (what the real mouse tools take)."""
    view = Gui.ActiveDocument.ActiveView
    vp = _viewport()
    x, y = view.getPointOnViewport(p)
    r = vp.devicePixelRatioF()
    h = view.getSize()[1]
    g = vp.mapToGlobal(QtCore.QPoint(int(x / r), int((h - y) / r)))
    return [g.x(), g.y()]


def center(widget):
    try:
        if widget is None or not widget.isVisible():
            return None
        g = widget.mapToGlobal(widget.rect().center())
        return [g.x(), g.y()]
    except RuntimeError:
        return None


def editing_sketch():
    gdoc = Gui.ActiveDocument
    vp = gdoc.getInEdit() if gdoc is not None else None
    obj = getattr(vp, "Object", None)
    return obj if obj is not None and obj.TypeId == "Sketcher::SketchObject" else None


def sketch_for_points():
    """The sketch 3D points are given in: the one being edited, else the last setup sketch."""
    return editing_sketch() or ST.get("sketch")


def tree_rows(sh):
    rows = {}
    tree = sh.browser.tree
    for item in sh.browser._items():
        name = item.data(0, QtCore.Qt.UserRole)
        if not name:
            continue
        rect = tree.visualItemRect(item)
        if rect.isValid() and rect.height() > 0:
            g = tree.viewport().mapToGlobal(rect.center())
            rows[name] = [g.x(), g.y()]
    return rows


def state():
    sh = shell.instance()
    st = {"error": ST["error"], "last_cmd": ST["last_cmd"], "active_doc": App.ActiveDocument.Name if App.ActiveDocument else None,
          "busy": safe.busy(), "focus": None, "editing": None, "dims": [], "labels": {}, "box": None, "dialog": None,
          "menu": None, "ribbon": {}, "tree": {}, "plane_panel": {}, "points": {}, "incad_active": bool(sh and sh.active),
          "docs": list(App.listDocuments().keys()), "log": ""}
    fw = QtWidgets.QApplication.focusWidget()
    st["focus"] = type(fw).__name__ if fw else None
    sk = editing_sketch()
    if sk is not None:
        st["editing"] = sk.Name
        st["dims"] = [[c.Name, round(c.Value, 3)] for c in sk.Constraints if c.Name]
        for c in sk.Constraints:
            if c.Name:
                try:
                    p = sketches.label_point(sk, c.Name)
                    if p is not None:
                        st["labels"][c.Name] = screen_xy(p)
                except Exception:
                    pass
    psk = sketch_for_points()
    if psk is not None and Gui.ActiveDocument is not None:
        pl = psk.getGlobalPlacement()
        for name, (x, y, z) in ST["points"].items():
            try:
                st["points"][name] = screen_xy(pl.multVec(App.Vector(x, y, z)))
            except Exception:
                pass
    if sh is not None and sh.active:
        box = sh.value_box
        if box is not None:
            st["box"] = {"name": box.name, "text": box.edit.text(), "error": box.error_text(),
                         "apply": center(getattr(box, "apply_button", None)),
                         "cancel": center(getattr(box, "cancel_button", None))}
        fs = sh.feature_session
        if fs is not None and fs.dialog is not None:
            d = fs.dialog
            st["dialog"] = {"title": fs.kind.TITLE, "active_pick": d.active_pick(), "values": d.values(),
                            "error": d.error_text(), "feature": fs.feature.Name if fs.feature is not None else None,
                            "ok": center(d.ok_button), "cancel": center(d.cancel_button), "apply": center(d.apply_button),
                            "buttons": {}}
            for f in fs.kind.FIELDS:  # choice buttons, e.g. "operation.cut"
                try:
                    w = d.field(f.key)
                    for value, b in getattr(w, "_buttons", {}).items():
                        c = center(b)
                        if c:
                            st["dialog"]["buttons"]["%s.%s" % (f.key, value)] = c
                except Exception:
                    pass
        menu = sh.marking_menu
        if menu is not None:
            try:
                st["menu"] = {b.text(): center(b) for b in menu._list} if menu.isVisible() else None
            except RuntimeError:
                st["menu"] = None
        for cmd_id in RIBBON_DEFAULT + ST["ribbon_ids"]:
            c = center(sh.ribbon.button(cmd_id))
            if c:
                st["ribbon"][cmd_id] = c
        st["tree"] = tree_rows(sh)
        pp = sh.plane_panel
        if pp is not None and pp.isVisible():
            st["plane_panel"] = {r: center(pp.button(r)) for r in ("XY_Plane", "XZ_Plane", "YZ_Plane")}
    try:
        with open(os.environ.get("INCAD_LOG", ""), encoding="utf-8") as f:
            st["log"] = f.read()[-1500:]
    except Exception:
        pass
    body = document.primary_body(App.ActiveDocument) if App.ActiveDocument is not None else None
    if body is not None:
        try:
            st["tip"] = body.Tip.Name if body.Tip is not None else None
            st["volume"] = round(body.Shape.Volume, 3) if not body.Shape.isNull() else 0.0
            st["features"] = [o.Name for o in body.Group]
        except Exception:
            pass
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    w = mdi.activeSubWindow() if mdi is not None else None
    st["front_window"] = w.windowTitle() if w is not None else None
    return st


def write_state():
    try:
        s = state()
    except Exception:
        s = {"error": "state: " + traceback.format_exc()[-800:]}
    tmp = OUT + ".state.tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.replace(tmp, OUT + ".state")  # atomic: the runner never reads a half-written file


# ----- setups -----
def setup(name):
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    if name == "empty_part":
        return
    if name in ("rect_sketch_open", "rect_sketch"):
        sk = util.add_rect_sketch(body, name="SketchA")
        doc.recompute()
        ST["sketch"] = sk
        ST["points"].update({"bottom": (10, 0, 0), "bottom_place": (10, -6, 0), "right": (20, 5, 0),
                             "right_place": (27, 5, 0), "top": (10, 10, 0), "top_place": (10, 16, 0),
                             "left": (0, 5, 0), "left_place": (-7, 5, 0), "inside": (10, 5, 0), "away": (40, 30, 0)})
        if name == "rect_sketch_open":
            shell.sketch_session().edit(sk)
            QtCore.QTimer.singleShot(800, lambda: Gui.SendMsgToActiveView("ViewFit"))
        return
    if name in ("block", "block_with_top_sketch"):
        pad = util.add_pad(body, util.add_rect_sketch(body, name="SketchA"), 10)
        body.Tip = pad
        doc.recompute()
        ST["pad"] = pad
        if name == "block_with_top_sketch":
            import Part
            top = [i + 1 for i, fc in enumerate(pad.Shape.Faces) if abs(fc.CenterOfMass.z - 10) < 1e-6][0]
            sk = body.newObject("Sketcher::SketchObject", "TopSketch")
            sk.AttachmentSupport = [(pad, "Face%d" % top)]
            sk.MapMode = "FlatFace"
            sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
            doc.recompute()
            ST["sketch"] = sk
            ST["points"].update({"circle_edge": (12, 5, 0), "inside": (10, 5, 0), "away": (40, 30, 0)})
        Gui.SendMsgToActiveView("ViewFit")
        return
    raise ValueError("unknown setup %r" % name)


def run_command(line):
    ST["last_cmd"], ST["error"] = line, ""
    kind, _, arg = line.partition(":")
    try:
        if kind == "cmd":
            r = commands.REGISTRY.run(arg)
            if r is not None and not getattr(r, "ok", True):
                ST["error"] = str(getattr(r, "error", ""))
        elif kind == "setup":
            setup(arg)
        elif kind == "py":
            ST["py"] = repr(eval(arg, {"App": App, "Gui": Gui, "shell": shell, "commands": commands, "document": document,
                                       "sketches": sketches, "ST": ST, "prefs": prefs, "safe": safe, "util": util}))
        elif kind == "point":  # point:name=x,y,z  (sketch coordinates of the edited/setup sketch)
            name, _, xyz = arg.partition("=")
            ST["points"][name] = tuple(float(v) for v in xyz.split(","))
        elif kind == "ribbon":  # ribbon:id1,id2 — more buttons to report
            ST["ribbon_ids"] = [i for i in arg.split(",") if i]
        elif kind == "quit_discard":  # answer InCad's Save dialog with Don't Save, for quit scenarios
            shell.SAVE_ASK = lambda files: ("discard", [])
        elif kind == "where":
            pass
        else:
            ST["error"] = "unknown command %r" % line
    except Exception:
        ST["error"] = traceback.format_exc()[-800:]


def poll():
    cmd = OUT + ".cmd"
    if os.path.exists(cmd):
        with open(cmd) as f:
            line = f.read().strip()
        os.remove(cmd)
        run_command(line)
        write_state()
        with open(OUT + ".done", "w") as f:
            f.write(line)
    else:
        write_state()
    QtCore.QTimer.singleShot(150, poll)


def start():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")

    def after_wb():
        commands.REGISTRY.run("file.new")

        def ready():
            mw = Gui.getMainWindow()
            mw.raise_()
            mw.activateWindow()
            write_state()
            with open(OUT + ".ready", "w") as f:
                f.write("ready")
            poll()
        QtCore.QTimer.singleShot(1200, ready)
    QtCore.QTimer.singleShot(1500, after_wb)


QtCore.QTimer.singleShot(1000, start)
