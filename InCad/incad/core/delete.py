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


def _hand_over_main(body):
    """Before the main Solid goes: the Solids split from it keep their shape (frozen, their Split goes with it),
    and the next Solid becomes the main one."""
    from incad.core import document
    from incad.features import split
    doc = body.Document
    if body is not document.primary_body(doc):
        return
    nxt = main_successor(body)
    if nxt is None:
        raise ValueError("The only solid can't be deleted (delete its features instead)")
    for f in [o for o in body.Group if split.claims(o)]:
        split.freeze_pieces(doc, f)
    document._meta_set(doc, **{document.PRIMARY_KEY: nxt.Name})


def documents(obj):
    """Other documents a delete changes (an assembly cut lives in its part file)."""
    from incad.core import asm_cut
    if asm_cut.is_record(obj):
        data, target = asm_cut._target_of(obj)
        return [target] if target is not None and target is not obj.Document else []
    return []


def target_for(obj):
    """What Delete removes for a pick: a Split piece's base (the stand-in FeatureBase of the Solid made on it, or the
    SplitPiece outside it) means that Solid — the base alone is nothing to delete."""
    from incad.core import document
    if obj is not None and (obj.TypeId == "PartDesign::FeatureBase" or getattr(obj, "InCadSplitPiece", False)):
        solid = document._solid_of(obj)
        if solid is not None:
            return solid
    return obj


def users_of(body):
    """The Booleans that use this Solid as a tool (deleting it alone would break them)."""
    from incad.features import combine
    return [f for f in body.Document.Objects if combine.claims(f) and body.Name in combine._load(f).get("tools", [])]


def main_successor(body):
    """The Solid that becomes the main one when the main `body` is deleted: the largest other Solid that is no
    Boolean's used-up tool; None when there is none."""
    from incad.core import document
    from incad.features import combine
    used = combine.used_up_names(body.Document)
    others = [b for b in document.bodies(body.Document) if b is not body and b.Name not in used
              and not b.Shape.isNull()]
    return max(others, key=lambda b: b.Shape.Volume) if others else None


def delete(obj, with_users=False, replace_main=False):
    """Delete obj with what InCad made for it, then show the part's new End of Part (FreeCAD shows only the newest
    feature, so the one before it was hidden and the view went blank when the newest was deleted).
    with_users: a Solid's Booleans that use it as a tool go first. replace_main: the main Solid may go, another
    becomes the main one (main_successor)."""
    body = obj.getParentGeoFeatureGroup() if obj is not None else None
    if obj is not None and obj.TypeId == "PartDesign::Body":
        if with_users:
            for f in users_of(obj):
                _delete(f)
        if replace_main:
            _hand_over_main(obj)
    doc = obj.Document
    from incad.features import gear
    if gear.is_gear(obj):  # a set's first gear (or worm): its second goes with it, with the Solid it had
        second = gear.second_of(obj)
        if second is not None:
            gear._remove_gear(doc, second)
    _delete(obj)
    from incad.core import document
    try:  # every Solid shows its End of Part again (a Boolean that went with a tool Solid lived in another Solid)
        doc.recompute()
        for b in document.bodies(doc):
            document.show_result(b)
    except Exception:
        pass


def delete_all(objects):
    """Delete several (a feature and what is built on it), the latest first, each with what InCad made for it."""
    doc = objects[0].Document
    names = [o.Name for o in objects]
    order = {o.Name: i for i, o in enumerate(doc.Objects)}
    for name in sorted(names, key=lambda n: order.get(n, 0), reverse=True):
        obj = doc.getObject(name)
        if obj is not None:  # gone with an earlier one (a helper)
            delete(obj)


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
    from incad.core import image_reference
    if image_reference.is_picture(obj):  # nothing of the model hangs on it
        doc.removeObject(obj.Name)
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
        users = [f for f in doc.Objects if combine.claims(f) and obj.Name in combine._load(f).get("tools", [])]
        if users:  # its Boolean would lose its tool ('No source shape linked')
            raise ValueError("%s is used by %s (Boolean): delete or edit that first"
                             % (obj.Label, ", ".join(f.Label for f in users)))
        from incad.features import solid_mirror
        for m in solid_mirror.users_of(obj):  # its mirrored copies keep their shape (nothing left to follow)
            solid_mirror.break_link(m)
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
    from incad.features import solid_mirror
    if solid_mirror.is_mirror_solid(obj):  # the copy was its Solid: the Solid goes with it, unless built on
        body = obj.getParentGeoFeatureGroup()
        _remove_feature(obj)
        origin = [body.Origin] + list(body.Origin.OriginFeatures) if body is not None and body.Origin else []
        if body is not None and not [o for o in body.Group if o not in origin] \
                and body is not document.primary_body(doc):
            body.removeObjectsFromDocument()
            doc.removeObject(body.Name)
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
