"""Suppress / Unsuppress. A feature goes off together with the pieces InCad made for it (a thread's fill, bore and
chamfer, a sweep's wall), so the part looks as it did before the feature; its profile sketch or one of those pieces
means the feature. Threads can also go off all at once (faster redraws while designing) and come back on at the end;
a thread that was off before stays off."""
from incad.core import document

OFF_MARK = "InCadThreadsOff"  # on a thread the 'all threads off' switch turned off


def _profile(feature):
    prof = getattr(feature, "Profile", None)
    if isinstance(prof, (tuple, list)):
        prof = prof[0] if prof else None
    return prof


def owner_of(obj):
    """The feature that Suppress acts on for this object (a helper -> its owner, a profile sketch -> its feature)."""
    name = getattr(obj, "InCadHelperOf", None)
    owner = obj.Document.getObject(name) if name else None
    if owner is not None:
        return owner
    if "Suppressed" not in obj.PropertiesList:
        users = {o.Name: o for o in obj.InList if "Suppressed" in o.PropertiesList and _profile(o) is obj}
        if len(users) == 1:  # (InList names a feature once per link: Profile and ReferenceAxis)
            return owner_of(next(iter(users.values())))
    return obj


def set_suppressed(feature, on):
    body = feature.getParentGeoFeatureGroup()
    pieces = document.helpers_of(body, feature) if body is not None else []
    for o in [feature] + pieces:
        if "Suppressed" in o.PropertiesList and o.Suppressed != on:
            o.Suppressed = on


def toggle(obj):
    feature = owner_of(obj)
    if "Suppressed" not in feature.PropertiesList:
        raise ValueError("%s cannot be suppressed" % feature.Label)
    set_suppressed(feature, not feature.Suppressed)
    return feature


def threads(doc):
    from incad.features import thread
    return [o for o in doc.Objects if thread.claims(o) and not getattr(o, "InCadHelperOf", None)]


def threads_off(doc):
    """True while the 'all threads off' switch holds threads off."""
    return any(getattr(t, OFF_MARK, False) and t.Suppressed for t in threads(doc))


def _mark(t, on):
    if OFF_MARK not in t.PropertiesList:
        if not on:
            return
        t.addProperty("App::PropertyBool", OFF_MARK, "InCad", "Turned off by Threads Off")
        t.setPropertyStatus(OFF_MARK, "Hidden")
    setattr(t, OFF_MARK, on)


def toggle_threads(doc):
    """Every thread off (those already off are left alone), or back on: 'off' or 'on'."""
    ts = threads(doc)
    if not ts:
        raise ValueError("This part has no threads")
    marked = [t for t in ts if getattr(t, OFF_MARK, False)]
    if marked:
        for t in marked:
            if t.Suppressed:
                set_suppressed(t, False)
            _mark(t, False)
        return "on"
    for t in ts:
        if not t.Suppressed:
            set_suppressed(t, True)
            _mark(t, True)
    return "off"
