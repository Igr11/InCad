"""Starting, editing and finishing sketches the Inventor way (GUI side of incad.core.sketch)."""
from incad.core import document, log, safe, sketch
from incad.qt import QtCore


class SketchSession:
    def __init__(self, on_change=None, on_edit=None):
        self.picking = False
        self._on_change = on_change
        self._on_edit = on_edit      # called with the sketch when editing starts (baseline for the value-box rule)
        self._saved_vp = {}          # (doc, sketch) -> view-provider settings InCad changed, restored when done
        self._last_edited = None
        self._origin = None  # (view object, was visible) while picking
        self._datum_scale = None  # FreeCAD's DatumScale before the pick enlarged the planes (None: not changed)

    def _changed(self):
        if self._on_change is not None:
            self._on_change()

    @staticmethod
    def _resolve(obj, sub):
        """A pick on a Body means its Tip feature; 'Pad.Face6' style paths name the feature and the face."""
        if "." in sub:
            parts = sub.split(".")
            child = obj.Document.getObject(parts[-2]) if len(parts) > 1 else None
            return (child or obj), parts[-1]
        if obj is not None and obj.TypeId == "PartDesign::Body" and sub.startswith("Face") and obj.Tip is not None:
            return obj.Tip, sub
        return obj, sub

    def start(self):
        import FreeCAD as App
        import FreeCADGui as Gui
        doc = App.ActiveDocument
        if not document.is_incad_part(doc):
            raise ValueError("Create or open an InCad part first")
        for sel in Gui.Selection.getSelectionEx(doc.Name):
            for sub in (sel.SubElementNames or ("",)):
                support, face = self._resolve(sel.Object, sub)
                if sketch.valid_support(support, face):
                    Gui.Selection.clearSelection()
                    return self._create(support, face)
        self._begin_pick(doc)
        return None

    def _begin_pick(self, doc):
        import FreeCADGui as Gui
        self.cancel_pick()
        body = document.primary_body(doc)
        if body is not None:
            vos = [body.Origin.ViewObject] + [f.ViewObject for f in body.Origin.OriginFeatures]
            self._origin = [(v, v.Visibility) for v in vos]  # the planes themselves too (a saved file may hide them)
            gdoc = Gui.getDocument(doc.Name)
            view = gdoc.ActiveView if gdoc is not None else None
            if view is not None:
                self._datum_scale = _frame_planes(body, view)  # the size first: planes switched on below use it
            # FreeCAD applies a new datum size only when a plane is shown again (clicking Origin did that for the
            # user): switch them on fresh now, and once more when the size has surely arrived
            _show_fresh(vos, view)
            QtCore.QTimer.singleShot(300, lambda: self.picking and _show_fresh(vos[1:], view))
        self.picking = True
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        log.report("info", "Pick a plane or a flat face for the new sketch (Esc cancels)")
        self._changed()

    def cancel_pick(self):
        import FreeCADGui as Gui
        if not self.picking:
            return
        self.picking = False
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        if self._origin is not None:
            for vo, was in self._origin:
                try:
                    vo.Visibility = was
                except Exception:
                    pass
            self._origin = None
        if self._datum_scale is not None:
            _restore_datums(self._datum_scale)
            self._datum_scale = None
        self._changed()

    def addSelection(self, doc_name, obj_name, sub, pnt):
        import FreeCAD as App
        if not self.picking:
            return
        obj = App.getDocument(doc_name).getObject(obj_name)
        support, face = self._resolve(obj, sub)
        if sketch.valid_support(support, face):
            QtCore.QTimer.singleShot(0, lambda: self._picked(support, face))
        else:
            log.report("warning", "That is not flat: pick a plane or a flat face")

    def start_on(self, support, face=""):
        """New sketch straight on a plane or a flat face (browser double-click, right-click New Sketch)."""
        if not sketch.valid_support(support, face):
            raise ValueError("%s is not flat: pick a plane or a flat face" % support.Label)
        self.cancel_pick()
        return self._create(support, face)

    def pick_origin(self, role):
        """The plane panel's buttons: sketch on an origin plane of the main solid."""
        import FreeCAD as App
        body = document.primary_body(App.ActiveDocument)
        plane = next(o for o in body.Origin.OriginFeatures if o.Role == role)
        self._picked(plane, "")

    def _picked(self, support, face):
        import FreeCADGui as Gui
        self.cancel_pick()
        Gui.Selection.clearSelection()
        self._create(support, face)

    def _create(self, support, face):
        import FreeCAD as App
        doc = App.ActiveDocument
        body = document.primary_body(doc)
        r = safe.run_safely("New Sketch", lambda: sketch.make_sketch(body, support, face), doc)
        if r.ok:
            self.edit(r.value)
            return r.value
        return None

    def edit(self, sk):
        import FreeCADGui as Gui
        vo = sk.ViewObject
        key = (sk.Document.Name, sk.Name)
        if key not in self._saved_vp:
            self._saved_vp[key] = (vo.EditingWorkbench,
                                   vo.Autoconstraints if "Autoconstraints" in vo.PropertiesList else None)
        vo.EditingWorkbench = ""  # stay in InCad while sketching (restored when the sketch is finished)
        if "Autoconstraints" in vo.PropertiesList:
            vo.Autoconstraints = True
        if self._on_edit is not None:
            self._on_edit(sk)
        Gui.getDocument(sk.Document.Name).setEdit(sk.Name)
        self._last_edited = key
        self._changed()

    def restore(self, key):
        """Put back the view-provider settings of a sketch InCad edited (they are saved in the user's file)."""
        import FreeCAD as App
        saved = self._saved_vp.pop(key, None)
        if saved is None:
            return
        try:
            obj = App.getDocument(key[0]).getObject(key[1])
        except Exception:
            obj = None
        if obj is None:
            return
        vo = obj.ViewObject
        vo.EditingWorkbench = saved[0]
        if saved[1] is not None and "Autoconstraints" in vo.PropertiesList:
            vo.Autoconstraints = saved[1]

    def sync(self):
        """Called on every refresh: a sketch left by any route (✓, Esc, undo) gets its settings back."""
        editing = self.editing()
        key = (editing.Document.Name, editing.Name) if editing is not None else None
        for done in [k for k in self._saved_vp if k != key]:
            self.restore(done)

    def close_all(self):
        """Leaving InCad: finish any sketch edit and restore every sketch's settings."""
        import FreeCADGui as Gui
        self.cancel_pick()
        gdoc = Gui.ActiveDocument
        if self.editing() is not None and gdoc is not None:
            gdoc.resetEdit()
        for key in list(self._saved_vp):
            self.restore(key)

    def finish(self):
        import FreeCAD as App
        import FreeCADGui as Gui
        gdoc = Gui.ActiveDocument
        if gdoc is not None and gdoc.getInEdit() is not None:
            gdoc.resetEdit()
        if App.ActiveDocument is not None:
            App.ActiveDocument.recompute()
        self._changed()

    @staticmethod
    def editing():
        """The sketch being edited, or None."""
        import FreeCADGui as Gui
        gdoc = Gui.ActiveDocument
        vp = gdoc.getInEdit() if gdoc is not None else None
        obj = getattr(vp, "Object", None)
        return obj if sketch.is_sketch(obj) else None



PICK_DATUM_SCALE = 350.0  # percent; FreeCAD's 100 draws the origin planes a few mm on a new part
_VIEW = "User parameter:BaseApp/Preferences/View"


def _set_datum_scale(scale):
    """Draw datums (the origin planes) at `scale` percent, never smaller than the user's own setting; returns
    the user's value to restore ("" when they had none)."""
    import FreeCAD as App
    g = App.ParamGet(_VIEW)
    old = g.GetFloat("DatumScale", -1.0)
    g.SetFloat("DatumScale", max(scale, old))
    return "" if old < 0 else old


def _restore_datums(old):
    import FreeCAD as App
    g = App.ParamGet(_VIEW)
    if old == "":
        g.RemFloat("DatumScale")
    else:
        g.SetFloat("DatumScale", old)


def screen_box(view, view_objects):
    """World bounding box of view objects as drawn now (origin planes keep a fixed size on screen, so their
    ViewObject.getBoundingBox, taken without the real viewport, is wrong)."""
    import FreeCAD as App
    from pivy import coin
    viewer = view.getViewer()
    manager = viewer.getSoRenderManager()
    box = App.BoundBox()
    for vo in view_objects:
        sa = coin.SoSearchAction()
        sa.setNode(vo.RootNode)
        sa.setInterest(coin.SoSearchAction.FIRST)
        sa.apply(manager.getSceneGraph())
        if sa.getPath() is None:
            continue
        ba = coin.SoGetBoundingBoxAction(manager.getViewportRegion())
        ba.apply(sa.getPath())
        bb = ba.getBoundingBox()
        if not bb.isEmpty():
            box.add(App.BoundBox(App.Vector(*bb.getMin().getValue()), App.Vector(*bb.getMax().getValue())))
    return box


def _frame_planes(body, view):
    """Origin in the middle of the view, the origin planes big enough to see and click and the whole part in view;
    returns the user's DatumScale to restore after the pick.

    FreeCAD draws datums a fixed share of the view whatever the zoom (at PICK_DATUM_SCALE they reach about half
    the view height from the origin, measured on 1.1), so the zoom only has to fit the part."""
    import FreeCAD as App
    from incad.core import camera
    radius = 0.0
    if not body.Shape.isNull():
        bb = body.Shape.BoundBox
        radius = max(App.Vector(x, y, z).Length for x in (bb.XMin, bb.XMax) for y in (bb.YMin, bb.YMax)
                     for z in (bb.ZMin, bb.ZMax))
    old = _set_datum_scale(PICK_DATUM_SCALE)
    camera.frame(view.getCameraNode(), (0, 0, 0), max(40.0, radius * 2.3))
    return old


def _show_fresh(vos, view):
    for v in vos:
        try:
            v.Visibility = False
            v.Visibility = True
        except Exception:
            pass
    _redraw(view)


def _redraw(view):
    try:
        view.redraw()
    except Exception:
        pass
