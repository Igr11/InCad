"""InCad Delete: removes a feature with what InCad made for it (helpers, hidden profiles, cuts in other files).
Call inside safe.run_safely for one undo step."""
import FreeCAD as App

_ORIGIN = ("App::Origin", "App::Line", "App::Plane", "App::Point")


def _remove_feature(f):
    doc = f.Document
    body = f.getParentGeoFeatureGroup()
    if body is not None and body.TypeId == "PartDesign::Body":
        if body.Tip is f:
            body.Tip = f.BaseFeature
        body.removeObject(f)  # the next feature is relinked to f's base: the chain is kept
    doc.removeObject(f.Name)


def documents(obj):
    """Other documents a delete changes (an assembly cut lives in its part file)."""
    from incad.core import asm_cut
    if asm_cut.is_record(obj):
        data, target = asm_cut._target_of(obj)
        return [target] if target is not None and target is not obj.Document else []
    return []


def delete(obj):
    """Delete obj with what InCad made for it, then show the part's new End of Part (FreeCAD shows only the newest
    feature, so the one before it was hidden and the view went blank when the newest was deleted)."""
    body = obj.getParentGeoFeatureGroup() if obj is not None else None
    _delete(obj)
    from incad.core import document
    if body is not None and body.TypeId == "PartDesign::Body" and body.Document.getObject(body.Name) is not None:
        try:
            body.Document.recompute()
            document.show_result(body)
        except Exception:
            pass


def _delete(obj):
    from incad import features
    from incad.core import asm_cut, assembly, document
    from incad.features import combine, thread
    doc = obj.Document
    if obj.TypeId in _ORIGIN:
        raise ValueError("Origin planes and axes can't be deleted")
    if asm_cut.is_record(obj):
        asm_cut.remove(obj)
        return
    kind = features.kind_for(obj)
    if kind is combine:
        combine.delete(doc, obj)
        return
    from incad.features import split
    if kind is split:
        sk = getattr(obj, "Sketch", None)  # read before the feature goes
        split.delete(doc, obj)
        _remove_feature(obj)
        if sk is not None and doc.getObject(sk.Name) is not None:
            sk.Visibility = True  # the knife is a plain sketch again
        return
    if kind is thread:
        profile = obj.Profile[0] if isinstance(obj.Profile, (tuple, list)) and obj.Profile else None
        body = obj.getParentGeoFeatureGroup()
        if body is not None:
            thread._remove_helpers(doc, body, obj)
        _remove_feature(obj)
        if profile is not None and doc.getObject(profile.Name) is not None:
            body = profile.getParentGeoFeatureGroup()
            if body is not None:
                body.removeObject(profile)
            doc.removeObject(profile.Name)
        return
    if obj.TypeId == "PartDesign::Body":
        if obj is document.primary_body(doc):
            raise ValueError("The main solid can't be deleted (delete its features instead)")
        piece = obj.BaseFeature
        obj.removeObjectsFromDocument()
        doc.removeObject(obj.Name)
        from incad.features import split
        if piece is not None and doc.getObject(piece.Name) is not None and split.is_piece(piece):
            doc.removeObject(piece.Name)  # a Split's piece lives outside the Solid made on it
        return
    if obj.TypeId == "App::Link" and obj in assembly.components(doc):
        for j in assembly.joints(doc):  # its grounding and the constraints that use it go with it
            refs = [getattr(j, "ObjectToGround", None)] + \
                [(getattr(j, p, None) or (None,))[0] for p in ("Reference1", "Reference2")]
            if obj in refs:
                doc.removeObject(j.Name)
        doc.removeObject(obj.Name)
        return
    from incad.core import regions
    if obj.TypeId == "Sketcher::SketchObject" and any(
            o for p in regions.profiles_of(obj) for o in p.InList if getattr(o, "Profile", None) is not None):
        raise ValueError("%s is used by a feature: delete that feature first" % obj.Label)
    if obj.getParentGeoFeatureGroup() is not None and obj.getParentGeoFeatureGroup().TypeId == "PartDesign::Body":
        prof = obj.Profile[0] if isinstance(getattr(obj, "Profile", None), (tuple, list)) and obj.Profile else None
        body = obj.getParentGeoFeatureGroup()
        datum_types = ("PartDesign::Line", "PartDesign::Plane", "PartDesign::Point")
        helpers = [o for o in body.Group if getattr(o, "InCadHelperOf", None) == obj.Name]
        walls = [h.Name for h in helpers if h.TypeId not in datum_types]
        others = [h.Name for h in helpers if h.TypeId in datum_types]
        for name in reversed(walls):  # a sweep's wall (sketch, pipe, caps) sits after its sweep: it goes first,
            h = doc.getObject(name)   # last piece first, so the tip falls back cleanly
            if h is not None:
                if body.Tip is h:
                    body.Tip = obj
                body.removeObject(h)
                doc.removeObject(name)
        _remove_feature(obj)
        for name in others:  # work features InCad made for it (a revolve's two-point axis)
            h = doc.getObject(name)
            if h is not None:
                body.removeObject(h)
                doc.removeObject(name)
        if prof is not None and regions.is_profile(prof) and doc.getObject(prof.Name) is not None:
            body = prof.getParentGeoFeatureGroup()
            if body is not None:
                body.removeObject(prof)
            doc.removeObject(prof.Name)  # the area copy goes with the feature; the user's sketch stays
        return
    doc.removeObject(obj.Name)
