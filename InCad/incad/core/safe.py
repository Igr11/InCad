"""Safe command guard. Every model change runs in one undo transaction; on an exception or an invalid result
the transaction is aborted, the model recomputed back to its previous state, and the user told why."""
import traceback
from dataclasses import dataclass

from incad.core import log

_depth = 0
_busy = None


@dataclass
class SafeResult:
    ok: bool
    value: object = None
    error: str = ""


class _InvalidResult(Exception):
    pass


def _status(obj):
    try:
        return obj.getStatusString()
    except Exception:
        return ""


def _broken(obj, check_shape):
    """Reason text if obj failed to compute or (check_shape) has invalid PartDesign geometry, else ''."""
    state = getattr(obj, "State", [])
    if "Invalid" in state or "Error" in state:
        status = _status(obj)
        if obj.TypeId == "PartDesign::Body" and status == "Tip shape is empty":
            return ""  # an empty part (everything suppressed / rolled back) is a normal state
        return "%s: %s" % (obj.Label, status) if status and status not in ("Valid", "Touched") \
            else "%s failed to compute" % obj.Label
    if check_shape and obj.TypeId.startswith("PartDesign::"):
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull() and not shape.isValid():
            return "%s produced invalid geometry" % obj.Label
    return ""


def edit_open():
    """True while FreeCAD has a sketch or feature task dialog open (GUI only)."""
    try:
        import FreeCAD as App
        if not App.GuiUp:
            return False
        import FreeCADGui as Gui
        gdoc = Gui.ActiveDocument
        vp = gdoc.getInEdit() if gdoc is not None else None
        if vp is not None and getattr(getattr(vp, "Object", None), "TypeId", "") == "Sketcher::SketchObject":
            return False  # InCad's own sketch editing: Sketcher commits each tool step itself
        return bool(Gui.Control.activeDialog()) or vp is not None
    except Exception:
        return False


def set_busy(label):
    """A feature dialog is open (label) or closed (None): no other model change may start meanwhile."""
    global _busy
    _busy = label


def busy():
    return _busy


_on_refused = None  # shows the open dialog when a command is refused because of it (set by the shell)


def set_refused_hook(fn):
    global _on_refused
    _on_refused = fn


def refused():
    """A command was refused because a dialog is open: make sure the user sees that dialog."""
    if _on_refused is not None:
        try:
            _on_refused()
        except Exception:
            pass


def snapshot_broken(doc):
    return {o.Name for o in doc.Objects if _broken(o, False)}


def problems(doc, broken_before, touched):
    """Reasons why objects that were fine (not in broken_before) are now broken; shapes checked for `touched`."""
    found = [_broken(o, o.Name in touched) for o in doc.Objects if o.Name not in broken_before]
    return [p for p in found if p]


def _relink(doc):
    try:
        from incad.core import model
        model.relink(doc)  # objects restored by the abort lose their formula links (FreeCAD quirk)
    except Exception as e:
        log.report("warning", "Could not repair formula links: %s" % e, traceback.format_exc())


def run_safely(label, fn, doc=None):
    """Run fn() as one undo step named `label`. Never raises at the outermost level."""
    global _depth
    if _depth > 0:
        return SafeResult(True, fn())  # nested: the outer guard owns the transaction and catches errors
    if _busy:
        msg = "Finish the %s dialog first" % _busy
        refused()
        log.report("warning", msg)
        return SafeResult(False, error=msg)
    import FreeCAD as App
    doc = doc or App.ActiveDocument
    if doc is None:
        try:
            return SafeResult(True, fn())
        except Exception as e:
            msg = "%s failed: %s" % (label, e)
            log.report("error", msg, traceback.format_exc())
            return SafeResult(False, error=msg)
    if edit_open():  # the open edit owns the pending transaction and its OK/Cancel
        msg = "Finish or cancel the current edit before %s" % label
        log.report("warning", msg)
        return SafeResult(False, error=msg)
    if doc.HasPendingTransaction:  # a stray (implicit) change: keep it as its own undo step, apart from ours
        doc.commitTransaction()
    if not doc.UndoMode:
        doc.UndoMode = 1
    broken_before = snapshot_broken(doc)
    names_before = {o.Name for o in doc.Objects}
    _depth += 1
    doc.openTransaction(label)
    try:
        value = fn()
        touched = {o.Name for o in doc.Objects if "Touched" in o.State or o.Name not in names_before}
        doc.recompute()
        found = problems(doc, broken_before, touched)
        if found:
            raise _InvalidResult("; ".join(found))
    except Exception as e:
        doc.abortTransaction()
        doc.recompute()
        _relink(doc)
        invalid = isinstance(e, _InvalidResult)
        msg = str(e) if invalid else "%s failed: %s" % (label, e)
        log.report("error", msg, "" if invalid else traceback.format_exc())
        return SafeResult(False, error=msg)
    finally:
        _depth -= 1
    doc.commitTransaction()
    return SafeResult(True, value)
