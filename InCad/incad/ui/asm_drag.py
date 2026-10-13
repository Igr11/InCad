"""Drag a free assembly part with the mouse along its own degrees of freedom (Inventor). FreeCAD's native drag,
which works only while the assembly is in edit: the edit is held for the drag alone, inside InCad's own "Move part"
step, with every other free part held by a temporary ground so the solver moves the dragged part only (FreeCAD's
drag pulls free neighbours along). Order matters: resetEdit closes the transaction that was open at setEdit, so
setEdit comes before the step opens and the step is committed before resetEdit."""
import FreeCAD as App

from incad.core import assembly, dof, log, safe
from incad.qt import QtCore


class AssemblyDrag:
    def __init__(self, shell):
        self.shell = shell
        self.doc_name = None
        self.link_name = None
        self._held = []
        self._start = None
        self._serial = 0  # which drag a deferred finish belongs to

    def active(self):
        if self.link_name is not None and self.doc_name not in App.listDocuments():
            self.finish(moved_ok=False, closing=True)  # its document went without telling us
        return self.link_name is not None

    def _component_at(self, view, viewport, x, y):
        """(doc, link): the component under the pointer, looking through joint markers (drawn on top of the parts)."""
        from incad.ui.nav import to_coin
        doc = App.ActiveDocument
        if not assembly.is_assembly(doc):
            return None, None
        joints = assembly.joints(doc)
        for hit in view.getObjectsInfo(to_coin(viewport, x, y)) or []:
            name = (hit.get("SubName") or "").split(".")[0]
            o = doc.getObject(name) if name else None
            if o is not None and o in joints:
                continue
            return doc, (o if o is not None and o in assembly.components(doc) else None)
        return doc, None

    @staticmethod
    def _markers_pickable(doc, on):
        """FreeCAD's joint markers are picked on top of the parts: off during a drag, so FreeCAD's press picks the
        dragged part (FreeCAD's own joint task does the same)."""
        for j in assembly.joints(doc):
            proxy = getattr(getattr(j, "ViewObject", None), "Proxy", None)
            if hasattr(proxy, "setPickableState"):
                proxy.setPickableState(on)

    def begin(self, view, viewport, x, y):
        """On a left press that became a drag: start FreeCAD's drag of the free part under it, else nothing."""
        sh = self.shell
        if self.active():  # the last drag's end never came (the navigator can reset without one): finish it now
            self.finish(moved_ok=True)
        if sh.feature_session is not None or any(
                getattr(sh, a, None) is not None for a in ("_point_pick", "_region_pick", "_profile_pick")):
            return False  # a dialog, a tool or a pick owns the mouse
        doc, link = self._component_at(view, viewport, x, y)
        if link is None or assembly.is_suppressed(link):
            return False
        shape = getattr(link, "Shape", None)
        if shape is None or shape.isNull():
            return False
        if assembly.is_grounded(link):
            log.report("info", "%s is grounded" % link.Label)
            return False
        known = (dof.last(doc) or {}).get(link.Name)
        if known is not None and known.n == 0:
            log.report("info", "%s is fully constrained" % link.Label)
            return False
        import FreeCADGui as Gui
        asm = assembly.assembly_of(doc)
        if doc.HasPendingTransaction:  # a stray change: its own step, apart from the drag
            doc.commitTransaction()
        if not doc.UndoMode:
            doc.UndoMode = 1
        self._serial += 1
        self.doc_name, self.link_name = doc.Name, link.Name
        self._start = App.Placement(link.Placement)
        try:
            asm.ViewObject.MoveInCommand = False
            safe.set_drag_edit(True)
            Gui.getDocument(doc.Name).setEdit(asm.Name)
            self._markers_pickable(doc, False)
            doc.openTransaction("Move part")
            self._held = [c.Name for c in assembly.components(doc) if c is not link
                          and not assembly.is_grounded(c) and not assembly.is_suppressed(c)]
            for name in self._held:
                assembly.ground(doc.getObject(name))
        except Exception as e:
            log.report("warning", "Can't drag %s: %s" % (link.Label, e))
            self.finish(moved_ok=False)
            return False
        self.shell.dof_display_changed()
        return True

    def end(self):
        """The drag's release: finished once FreeCAD has handled the release itself."""
        if self.active():
            serial = self._serial
            QtCore.QTimer.singleShot(0, lambda: self._serial == serial and self.finish())

    def finish(self, moved_ok=True, closing=False):
        """End the drag: grounds off, its step committed when the part moved (else aborted), edit closed. closing:
        the document is going (or gone): it and its window are left alone, only InCad's own state is reset."""
        if self.link_name is None:
            return
        import FreeCADGui as Gui
        doc_name, link_name, held, start = self.doc_name, self.link_name, self._held, self._start
        self.doc_name = self.link_name = self._start = None
        self._held = []
        doc = App.getDocument(doc_name) if not closing and doc_name in App.listDocuments() else None
        moved, label = False, link_name
        try:
            if doc is not None:
                for name in held:
                    o = doc.getObject(name)
                    if o is not None:
                        assembly.unground(o)
                link = doc.getObject(link_name)
                label = link.Label if link is not None else link_name
                moved = moved_ok and link is not None and not link.Placement.isSame(start, 1e-9)
                if doc.HasPendingTransaction:
                    doc.commitTransaction() if moved else doc.abortTransaction()
        finally:
            try:
                gdoc = Gui.getDocument(doc_name) if doc is not None else None
                if gdoc is not None and gdoc.getInEdit() is not None:
                    gdoc.resetEdit()
                asm = assembly.assembly_of(doc) if doc is not None else None
                if asm is not None:
                    asm.ViewObject.MoveInCommand = True
                    self._markers_pickable(doc, True)
            finally:
                safe.set_drag_edit(False)
                self.shell.schedule_refresh()
                self.shell.dof_display_changed()
        if moved:
            log.report("info", "Moved %s" % label)
