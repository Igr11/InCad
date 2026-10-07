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
        obj.removeObjectsFromDocument()
        doc.removeObject(obj.Name)
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
        helpers = [o for o in body.Group if getattr(o, "InCadHelperOf", None) == obj.Name
                   and o.TypeId in ("PartDesign::Line", "PartDesign::Plane", "PartDesign::Point")]
        _remove_feature(obj)
        for h in helpers:  # work features InCad made for it (a revolve's two-point axis)
            if doc.getObject(h.Name) is not None:
                body.removeObject(h)
                doc.removeObject(h.Name)
        if prof is not None and regions.is_profile(prof) and doc.getObject(prof.Name) is not None:
            body = prof.getParentGeoFeatureGroup()
            if body is not None:
                body.removeObject(prof)
            doc.removeObject(prof.Name)  # the area copy goes with the feature; the user's sketch stays
        return
    doc.removeObject(obj.Name)
