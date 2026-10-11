"""Readable wireframe: FreeCAD draws Wireframe with each object's own line color and width (thin and nearly black,
invisible on the dark theme's background). While Wireframe is on, InCad gives the shown objects thick lines in the
theme's line color, keeping each object's own lines on its view (a hidden property), and Shaded puts them back. A
file saved in Wireframe keeps that property, so InCad puts the normal lines back when it is opened again."""
import json

import FreeCAD as App

WIRE = {"light": ((0.10, 0.10, 0.12), 3.0), "dark": ((0.86, 0.89, 0.93), 3.0)}
KEEP = "InCadNormalLines"  # on a view provider: [color, width] before Wireframe

_active = set()  # document names shown in Wireframe


def _views(doc):
    for o in doc.Objects:
        vo = getattr(o, "ViewObject", None)
        if vo is not None and "LineColor" in vo.PropertiesList and "LineWidth" in vo.PropertiesList:
            yield o, vo


def _same(stored, color):
    """A color as FreeCAD stores it (32-bit floats: 0.86 reads 0.8600000143) is the same as `color`."""
    return all(abs(a - b) < 1e-3 for a, b in zip(tuple(stored)[:3], color))


def _put_wire(doc, theme):
    color, width = WIRE.get(theme, WIRE["light"])
    views = list(_views(doc))
    for o, vo in views:  # every object's own lines first: a Body passes its line settings on to its features
        if KEEP not in vo.PropertiesList:
            vo.addProperty("App::PropertyString", KEEP, "InCad", "The object's lines before Wireframe")
            vo.setPropertyStatus(KEEP, "Hidden")
            setattr(vo, KEEP, json.dumps([list(vo.LineColor), vo.LineWidth]))
    for o, vo in views:
        if not _same(vo.LineColor, color) or abs(vo.LineWidth - width) > 1e-6:
            vo.LineColor = color
            vo.LineWidth = width


def _put_back(doc):
    views = [(o, vo) for o, vo in _views(doc) if KEEP in vo.PropertiesList]
    views.sort(key=lambda ov: ov[0].TypeId != "PartDesign::Body")  # Bodies first: they pass theirs on to features
    for o, vo in views:
        try:
            color, width = json.loads(getattr(vo, KEEP))
            vo.LineColor, vo.LineWidth = tuple(color), width
        except (ValueError, TypeError):
            pass
    for o, vo in views:
        vo.removeProperty(KEEP)


def set_wireframe(doc, on, theme):
    """Called when the draw style changes in the view of `doc`."""
    if doc is None:
        return
    if on:
        _active.add(doc.Name)
        _put_wire(doc, theme)
    else:
        _active.discard(doc.Name)
        _put_back(doc)


def refresh(doc, theme):
    """New objects (or a theme change) while Wireframe is on get the wireframe lines too; a document that is not in
    Wireframe (a file saved in it and opened again) gets its normal lines back."""
    for name in [n for n in _active if n not in App.listDocuments()]:  # closed documents
        _active.discard(name)
    if doc is None:
        return
    if doc.Name in _active:
        _put_wire(doc, theme)
    elif any(KEEP in vo.PropertiesList for _, vo in _views(doc)):
        _put_back(doc)
