"""Safe command guard. Every model change runs in one undo transaction; on an exception or an invalid result
the transaction is aborted, the model recomputed back to its previous state, and the user told why."""
import traceback
from dataclasses import dataclass

from incad.core import log

_depth = 0


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
        return bool(Gui.Control.activeDialog()) or (gdoc is not None and gdoc.getInEdit() is not None)
    except Exception:
        return False


def run_safely(label, fn, doc=None):
    """Run fn() as one undo step named `label`. Never raises at the outermost level."""
    global _depth
    if _depth > 0:
        return SafeResult(True, fn())  # nested: the outer guard owns the transaction and catches errors
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
    broken_before = {o.Name for o in doc.Objects if _broken(o, False)}
    names_before = {o.Name for o in doc.Objects}
    _depth += 1
    doc.openTransaction(label)
    try:
        value = fn()
        touched = {o.Name for o in doc.Objects if "Touched" in o.State or o.Name not in names_before}
        doc.recompute()
        problems = [_broken(o, o.Name in touched) for o in doc.Objects if o.Name not in broken_before]
        problems = [p for p in problems if p]
        if problems:
            raise _InvalidResult("; ".join(problems))
    except Exception as e:
        doc.abortTransaction()
        doc.recompute()
        invalid = isinstance(e, _InvalidResult)
        msg = str(e) if invalid else "%s failed: %s" % (label, e)
        log.report("error", msg, "" if invalid else traceback.format_exc())
        return SafeResult(False, error=msg)
    finally:
        _depth -= 1
    doc.commitTransaction()
    return SafeResult(True, value)
