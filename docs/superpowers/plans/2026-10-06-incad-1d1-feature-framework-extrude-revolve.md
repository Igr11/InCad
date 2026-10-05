# InCad 1d-1 — Feature Dialogs, Extrude, Revolve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inventor-style feature creation and editing in InCad: a floating feature dialog with live preview,
OK / Apply / Cancel, value fields that accept units, parameter names and formulas (click a dimension or a
parameter to insert its name), and every feature value stored as a named model parameter (`d0, d1…`). First two
features: Extrude (E) — Join / Cut / Intersect / New Solid; Distance, To Next, Through All, To face; one side,
flip, symmetric, two sides; taper — and Revolve — Join / Cut; sketch axis; Full / Angle / Two angles.

**Architecture:** `incad.core.model` unifies model parameters: sketch dimensions (named constraints) and feature
values (properties of a hidden `App::VarSet` "InCadModel", bound to feature properties by FreeCAD expressions —
probed: `renameProperty` keeps the bound formulas). Each feature kind is a pure module under `incad/features/`
(`FIELDS`, `create`, `read`, `update`) tested headless. `incad.ui.feature_dialog` is the widget (offscreen-tested);
`incad.ui.feature_session` runs one dialog: it opens one undo transaction, creates or edits the native feature,
recomputes on every change (live preview), checks validity, and commits on OK or aborts on Cancel. While a session
is open, `safe.run_safely` refuses other model changes.

**Tech Stack:** FreeCAD 1.1.3 PartDesign (Pad, Pocket, Revolution, Groove, Boolean, Body), PySide6.

**Spec:** `docs/superpowers/specs/2026-10-05-incad-stage1-design.md` §6 (part features) and §5a (named values,
click-to-insert). Plan 1d-2 adds Hole, Fillet, Chamfer, Shell, patterns, Mirror, work features and Inspect.

## Global Constraints

- Plans 1a–1c constraints hold (Qt via `incad.qt`, throwaway `user.cfg` for FreeCAD runs, English UI, announce
  GUI runs, every changed FreeCAD setting restored).
- One feature dialog at a time; while it is open no other model change may start (`safe` busy flag).
- A dialog's whole life (create/edit + previews) is one undo step; Cancel leaves the model exactly as before.
- OK is disabled while the preview is invalid; the reason is shown in plain words.
- Every value field accepts `40`, `40 mm`, `1.5 in`, `d3*2`, `Width/2`; a plain number uses the part's units
  (degrees for angles).
- Feature values are model parameters named `d<N>`, unique per document together with sketch dimensions and user
  parameters; renamable in the Parameters panel.

## Review Focus

1. Cancel after several previews (including a Join→Cut switch that replaced the feature) restores the model and
   the undo history exactly (Task 6 tests 4, 6).
2. Changing the operation between Join and Cut on an existing feature keeps its parameters and its place in the
   history (Task 3 test).
3. Extrude "New Solid" moves the profile sketch into the new body; Cancel moves it back (Task 3 test, Task 6 test 7).
4. A formula naming an unknown parameter shows an error and disables OK instead of raising (Task 6 test 5).
5. The dialog never leaves the busy flag set (closed by OK, Cancel, Esc, document closed, InCad left) (Task 6
   tests 10, 11).

## File Map

```
InCad/incad/core/model.py              model parameters: dims + feature values, names, formulas
InCad/incad/core/sketch.py             naming/formula helpers delegate to model
InCad/incad/core/safe.py               + problems(), busy flag
InCad/incad/features/__init__.py       KINDS registry (TypeId -> feature module)
InCad/incad/features/common.py         profile helpers, value helpers
InCad/incad/features/extrude.py        Extrude kind
InCad/incad/features/revolve.py        Revolve kind
InCad/incad/ui/feature_dialog.py       floating feature dialog widget
InCad/incad/ui/feature_session.py      one dialog's transaction, preview, OK/Apply/Cancel
InCad/incad/ui/shell.py                start/edit features, insert target, picks
InCad/incad/actions.py                 feature.extrude (E), feature.revolve (R), browser.edit dispatch
InCad/incad/ui/ribbon_layout.py        3D Model ▸ Create
InCad/incad/ui/marking_layout.py       Extrude on the part/face menus
tools/make_icons.py                    + extrude, revolve
```

---

### Task 1: Unified model parameters

**Files:**
- Create: `InCad/incad/core/model.py`, `tests/headless/test_model.py`
- Modify: `InCad/incad/core/sketch.py`

**Interfaces:**
- Produces (`incad.core.model`): `MODEL_NAME = "InCadModel"`; `used_names(doc)`; `next_name(doc) -> "d<N>"`;
  `refs(doc) -> {name: expression path}`; `to_expression(doc, text)`; `to_display(doc, expr)`;
  `feature_parameters(doc) -> [(name, formula, value)]`; `model_parameters(doc)` (dimensions then feature values);
  `is_model_parameter(doc, name)`; `new_feature_parameter(doc, text, unit_kind="length") -> name`;
  `bind(feature, prop, name)`; `bound_parameter(feature, prop) -> name|None`; `parameter_text(doc, name)`
  (formula with plain names, or value text); `set_model_parameter(doc, name, text)`;
  `rename_model_parameter(doc, old, new)`. `unit_kind`: `"length"` or `"angle"` (plain numbers get mm/in or deg).
- `incad.core.sketch`: `to_expression`, `to_display`, `model_parameters`, `name_new_dimensions` keep their
  signatures but use `model` (so dimension names also avoid feature-parameter names).

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_model.py`:
```python
import unittest

import FreeCAD as App
from incad.core import document, model, sketch
from headless import util


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("M")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_feature_parameter_drives_the_feature(self):
        name = model.new_feature_parameter(self.doc, "25 mm")
        self.assertEqual(name, "d0")
        model.bind(self.pad, "Length", name)
        self.doc.recompute()
        self.assertAlmostEqual(self.pad.Length.Value, 25)
        self.assertEqual(model.bound_parameter(self.pad, "Length"), "d0")
        self.assertEqual(model.parameter_text(self.doc, "d0"), "25 mm")

    def test_plain_numbers_use_part_units_and_degrees(self):
        a = model.new_feature_parameter(self.doc, "12")
        b = model.new_feature_parameter(self.doc, "30", unit_kind="angle")
        self.assertEqual(model.parameter_text(self.doc, a), "12 mm")
        self.assertEqual(model.parameter_text(self.doc, b), "30 °")

    def test_names_shared_with_dimensions_and_user_parameters(self):
        document.set_parameter(self.doc, "d2", "1 mm")
        self.assertEqual(model.new_feature_parameter(self.doc, "5 mm"), "d3")
        sk = self.doc.getObject("Sketch")
        import Sketcher
        sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        self.doc.recompute()
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d4"])
        self.assertEqual([n for n, _, _ in model.model_parameters(self.doc)], ["d4", "d3"])

    def test_formulas_and_rename(self):
        n = model.new_feature_parameter(self.doc, "20 mm")
        m = model.new_feature_parameter(self.doc, "1 mm")
        model.set_model_parameter(self.doc, m, "%s / 4" % n)
        self.assertEqual(model.parameter_text(self.doc, m), "%s / 4" % n)
        model.rename_model_parameter(self.doc, n, "Depth")
        self.assertEqual(model.parameter_text(self.doc, m), "Depth / 4")
        self.assertTrue(model.is_model_parameter(self.doc, "Depth"))
        self.assertFalse(model.is_model_parameter(self.doc, n))
        with self.assertRaises(ValueError):
            model.rename_model_parameter(self.doc, "Depth", "mm")
        with self.assertRaises(ValueError):
            model.set_model_parameter(self.doc, "Depth", "Nope * 2")

    def test_model_object_is_hidden_from_the_browser(self):
        model.new_feature_parameter(self.doc, "1 mm")
        from incad.core import nodes, tree
        self.assertNotIn("InCadModel", [n.label for _, n in nodes.flatten(tree.build(self.doc))])
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_model.py` → Expected: `cannot import name 'model'`.

- [ ] **Step 3: Implement**

`InCad/incad/core/model.py`:
```python
"""Model parameters, Inventor style: every sketch dimension and every feature value has a name (d0, d1, …) that
formulas can use. Dimensions are named Sketcher constraints; feature values are properties of a hidden VarSet
("InCadModel") bound to the feature properties by FreeCAD expressions."""
import re

import FreeCAD as App

from incad.core import document

MODEL_NAME = "InCadModel"
_GROUP = "Model"
_DNAME = re.compile(r"^d(\d+)$")
_TOKEN = re.compile(r"(?<![\w.<>])([A-Za-z_][A-Za-z0-9_]*)(?![\w(.])")


def _model_obj(doc, create=False):
    obj = doc.getObject(MODEL_NAME)
    if obj is None and create:
        obj = doc.addObject("App::VarSet", MODEL_NAME)
        obj.Label = "Model Parameters"
    return obj


def _feature_names(doc):
    obj = _model_obj(doc)
    return [p for p in obj.PropertiesList if obj.getGroupOfProperty(p) == _GROUP] if obj is not None else []


def _dimension_entries(doc):
    from incad.core import sketch
    return sketch.dimensions(doc)


def used_names(doc):
    from incad.core import sketch
    names = {c.Name for sk in doc.Objects if sketch.is_sketch(sk) for c in sk.Constraints if c.Name}
    names |= set(_feature_names(doc))
    return names | {n for n, _, _ in document.list_parameters(doc)}


def next_name(doc, taken=()):
    numbers = [int(m.group(1)) for m in (_DNAME.match(n) for n in used_names(doc) | set(taken)) if m]
    return "d%d" % (max(numbers) + 1 if numbers else 0)


def refs(doc):
    out = {n: "%s.%s" % (document.PARAMS_NAME, n) for n, _, _ in document.list_parameters(doc)}
    for name, sk, _ in _dimension_entries(doc):
        out[name] = "%s.Constraints.%s" % (sk.Name, name)
    for name in _feature_names(doc):
        out[name] = "%s.%s" % (MODEL_NAME, name)
    return out


def to_expression(doc, text):
    r = refs(doc)
    return _TOKEN.sub(lambda m: r.get(m.group(1), m.group(1)), text)


def to_display(doc, expr):
    for path, name in sorted(((p, n) for n, p in refs(doc).items()), key=lambda pn: -len(pn[0])):
        expr = expr.replace(path, name)
    return re.sub(r"(?<![\w])\.Constraints\.([A-Za-z_]\w*)", r"\1", expr)


def _expression(obj, path):
    for p, e in obj.ExpressionEngine:
        if p.lstrip(".") == path:
            return e
    return ""


def feature_parameters(doc):
    obj = _model_obj(doc)
    if obj is None:
        return []
    return [(n, parameter_text(doc, n) if not document._is_literal(_expression(obj, n)) else "",
             document._format(getattr(obj, n))) for n in _feature_names(doc)]


def model_parameters(doc):
    from incad.core import sketch
    return sketch.dimension_parameters(doc) + feature_parameters(doc)


def is_model_parameter(doc, name):
    from incad.core import sketch
    return name in _feature_names(doc) or sketch.find_dimension(doc, name)[0] is not None


def _with_unit(doc, text, unit_kind):
    try:
        q = App.Units.Quantity(text)
    except Exception:
        return text
    if q.Unit == App.Units.Quantity("1").Unit:
        return "%s %s" % (q.Value, "deg" if unit_kind == "angle" else (document.part_units(doc) or "mm"))
    return text


def new_feature_parameter(doc, text, unit_kind="length"):
    obj = _model_obj(doc, create=True)
    name = next_name(doc)
    obj.addProperty("App::PropertyQuantity", name, _GROUP)
    try:
        obj.setExpression(name, to_expression(doc, _with_unit(doc, text, unit_kind)))
    except Exception as e:
        obj.removeProperty(name)
        raise ValueError("Invalid value %r: %s" % (text, e))
    _remember_kind(obj, name, unit_kind)
    doc.recompute()
    return name


def _remember_kind(obj, name, unit_kind):
    kinds = dict(item.split("=", 1) for item in obj.Label2.split(";") if "=" in item) if obj.Label2 else {}
    kinds[name] = unit_kind
    obj.Label2 = ";".join("%s=%s" % kv for kv in sorted(kinds.items()))


def _unit_kind(obj, name):
    kinds = dict(item.split("=", 1) for item in obj.Label2.split(";") if "=" in item) if obj.Label2 else {}
    return kinds.get(name, "length")


def bind(feature, prop, name):
    feature.setExpression(prop, "%s.%s" % (MODEL_NAME, name))


def bound_parameter(feature, prop):
    expr = _expression(feature, prop)
    prefix = MODEL_NAME + "."
    return expr[len(prefix):] if expr.startswith(prefix) else None


def parameter_text(doc, name):
    """What the user typed: the formula with plain names, or the value."""
    from incad.core import sketch
    obj = _model_obj(doc)
    if obj is not None and name in _feature_names(doc):
        expr = _expression(obj, name)
        return to_display(doc, expr) if expr and not document._is_literal(expr) else document._format(getattr(obj, name))
    sk, _ = sketch.find_dimension(doc, name)
    if sk is not None:
        expr = _expression(sk, "Constraints." + name)
        return to_display(doc, expr) if expr else document._format(sk.getDatum(name))
    raise ValueError("No parameter named %r" % name)


def set_model_parameter(doc, name, text):
    """Set a dimension or a feature value. Call inside safe.run_safely or a feature session's transaction."""
    from incad.core import sketch
    if sketch.find_dimension(doc, name)[0] is not None:
        return sketch.set_dimension(doc, name, text)
    obj = _model_obj(doc)
    if obj is None or name not in _feature_names(doc):
        raise ValueError("No parameter named %r" % name)
    text = (text or "").strip()
    if not text:
        raise ValueError("%s needs a value" % name)
    try:
        obj.setExpression(name, to_expression(doc, _with_unit(doc, text, _unit_kind(obj, name))))
    except Exception as e:
        raise ValueError("Invalid formula for %s: %s" % (name, e))
    doc.recompute()
    if "Invalid" in obj.State or "Error" in obj.State:
        raise ValueError("%s cannot be evaluated: %s" % (name, obj.getStatusString()))


def rename_model_parameter(doc, old, new):
    from incad.core import sketch
    if sketch.find_dimension(doc, old)[0] is not None:
        return sketch.rename_dimension(doc, old, new)
    obj = _model_obj(doc)
    if obj is None or old not in _feature_names(doc):
        raise ValueError("No parameter named %r" % old)
    if not document._NAME_RE.match(new or ""):
        raise ValueError("A name starts with a letter or _ and has only letters, digits and _ (got %r)" % new)
    if document._is_literal(new):
        raise ValueError("%r is a unit symbol; choose another name" % new)
    if new != old and new in used_names(doc):
        raise ValueError("%r is already used" % new)
    kind = _unit_kind(obj, old)
    obj.renameProperty(old, new)
    _remember_kind(obj, new, kind)
    doc.recompute()
```
In `InCad/incad/core/sketch.py`:
- replace `_used_names(doc)` body with `from incad.core import model` / `return model.used_names(doc)`;
- in `name_new_dimensions` keep the logic but compute the next number with `model.next_name(doc, added)` for each
  new dimension (`name = model.next_name(doc, added)`), removing the local `numbers`/`nxt` code;
- replace `to_expression` and `to_display` bodies with delegation to `model.to_expression` / `model.to_display`;
- rename the existing `model_parameters` to `dimension_parameters` and add
  `def model_parameters(doc):` / `from incad.core import model` / `return model.model_parameters(doc)`;
- in `rename_dimension` keep using `_used_names` (now model-wide).

In `InCad/incad/core/tree.py` `build()`: the browser lists only bodies, so the `InCadModel` VarSet never appears —
no change needed (the test pins it).

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_model.py`, `tests/run_headless.sh test_sketch.py` → Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core tests/headless/test_model.py && git commit -m "InCad 1d-1: model parameters for feature values, shared d-names"
```

---

### Task 2: Guard pieces — problems() and busy flag

**Files:**
- Modify: `InCad/incad/core/safe.py`, `tests/headless/test_safe.py`

**Interfaces:**
- Produces: `safe.problems(doc, broken_before, touched) -> [reason]` (the check `run_safely` uses);
  `safe.snapshot_broken(doc) -> set`; `safe.set_busy(label|None)`, `safe.busy() -> str|None`; `run_safely` refuses
  with `"Finish the <label> dialog first"` while busy (nested calls are unaffected).

- [ ] **Step 1: Write the failing tests**

Append to `SafeTest` in `tests/headless/test_safe.py`:
```python
    def test_busy_refuses_new_changes(self):
        safe.set_busy("Extrude")
        try:
            r = safe.run_safely("Add", lambda: self.doc.addObject("PartDesign::Body", "Body"), self.doc)
            self.assertFalse(r.ok)
            self.assertIn("Extrude", r.error)
            self.assertIsNone(self.doc.getObject("Body"))
        finally:
            safe.set_busy(None)
        self.assertIsNone(safe.busy())

    def test_problems_reports_invalid_features(self):
        body, pad = util.padded_part(self.doc, length=10)
        before = safe.snapshot_broken(self.doc)
        pad.Length = 0
        self.doc.recompute()
        found = safe.problems(self.doc, before, {pad.Name})
        self.assertTrue(any("Pad" in p for p in found), found)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_safe.py` → Expected: AttributeError `set_busy` / `snapshot_broken`.

- [ ] **Step 3: Implement**

In `InCad/incad/core/safe.py` add below `_depth = 0`: `_busy = None`, and add:
```python
def set_busy(label):
    """A feature dialog is open (label) or closed (None): no other model change may start meanwhile."""
    global _busy
    _busy = label


def busy():
    return _busy


def snapshot_broken(doc):
    return {o.Name for o in doc.Objects if _broken(o, False)}


def problems(doc, broken_before, touched):
    """Reasons why objects that were fine (not in broken_before) are now broken; shapes checked for `touched`."""
    found = [_broken(o, o.Name in touched) for o in doc.Objects if o.Name not in broken_before]
    return [p for p in found if p]
```
In `run_safely`, right after the `if _depth > 0:` early return, add:
```python
    if _busy:
        msg = "Finish the %s dialog first" % _busy
        log.report("warning", msg)
        return SafeResult(False, error=msg)
```
and replace the two lines computing `broken_before`/`problems` inside `run_safely` with calls to
`snapshot_broken(doc)` and `problems(doc, broken_before, touched)`.

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_safe.py` → Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/core/safe.py tests/headless/test_safe.py && git commit -m "InCad 1d-1: guard problems() and busy flag"
```

---

### Task 3: Extrude and Revolve kinds (model side)

**Files:**
- Create: `InCad/incad/features/__init__.py`, `InCad/incad/features/common.py`, `InCad/incad/features/extrude.py`,
  `InCad/incad/features/revolve.py`, `tests/headless/test_extrude.py`, `tests/headless/test_revolve.py`

**Interfaces:**
- Produces (`incad.features.common`): `Field(key, label, kind, choices=(), default=None, show_if=None)` (kinds
  `value_length`, `value_angle`, `choice`, `bool`, `pick`); `closed_profile(sketch) -> bool`;
  `unconsumed_closed_sketches(body) -> [sketch]`; `consumers(sketch) -> [feature]`.
- Produces (each kind module): `TITLE`, `ICON`, `TYPES` (FreeCAD TypeIds it edits), `FIELDS`,
  `defaults(doc, body, profile) -> values`, `create(doc, body, profile, values) -> feature`,
  `read(doc, feature) -> values`, `update(doc, feature, values) -> feature` (may return a replacement),
  `profile_of(feature) -> sketch`. Values: plain dict `{key: str|bool}`; value fields hold the text shown in the
  dialog. `incad.features.KINDS` = list of modules; `kind_for(feature) -> module|None`.
- Extrude values: `operation` (join/cut/intersect/new_solid), `extent` (distance/to_next/through_all/to),
  `direction` (default/flip/symmetric/two_sides), `distance`, `distance2`, `taper`, `to_face` (`"Obj:FaceN"`).
- Revolve values: `operation` (join/cut), `axis` (`V_Axis`/`H_Axis`), `extent` (full/angle/two_angles),
  `angle`, `angle2`, `flip`.

- [ ] **Step 1: Write the failing tests**

`tests/headless/test_extrude.py`:
```python
import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import extrude, kind_for
from incad.features.common import closed_profile, unconsumed_closed_sketches
from headless import util


class ExtrudeTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("E")
        self.body = document.make_part(self.doc)
        self.sk = util.add_rect_sketch(self.body)  # 20 x 10 on XY
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **changes):
        values = extrude.defaults(self.doc, self.body, self.sk)
        values.update(changes)
        f = extrude.create(self.doc, self.body, self.sk, values)
        self.doc.recompute()
        return f

    def test_profile_helpers(self):
        self.assertTrue(closed_profile(self.sk))
        self.assertEqual(unconsumed_closed_sketches(self.body), [self.sk])

    def test_defaults_and_join(self):
        v = extrude.defaults(self.doc, self.body, self.sk)
        self.assertEqual((v["operation"], v["extent"], v["direction"], v["distance"]), ("join", "distance", "default", "10 mm"))
        f = self.make()
        self.assertEqual(f.TypeId, "PartDesign::Pad")
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 10, places=3)
        self.assertEqual(model.bound_parameter(f, "Length"), "d0")
        self.assertIs(kind_for(f), extrude)
        self.assertEqual(unconsumed_closed_sketches(self.body), [])

    def test_read_back(self):
        f = self.make(distance="25 mm", direction="symmetric", taper="5")
        v = extrude.read(self.doc, f)
        self.assertEqual((v["distance"], v["direction"], v["taper"], v["operation"]), ("25 mm", "symmetric", "5 °", "join"))

    def test_update_values_and_formulas(self):
        f = self.make()
        document.set_parameter(self.doc, "Width", "40 mm")
        f = extrude.update(self.doc, f, dict(extrude.read(self.doc, f), distance="Width / 2"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Length.Value, 20)
        self.assertEqual(extrude.read(self.doc, f)["distance"], "Width / 2")

    def test_join_to_cut_keeps_parameter_and_place(self):
        base = self.make(distance="10 mm")
        top = [i + 1 for i, fc in enumerate(base.Shape.Faces) if abs(fc.CenterOfMass.z - 10) < 1e-6][0]
        sk2 = self.body.newObject("Sketcher::SketchObject", "Hole")
        sk2.AttachmentSupport = [(base, "Face%d" % top)]
        sk2.MapMode = "FlatFace"
        sk2.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        f = extrude.create(self.doc, self.body, sk2, dict(extrude.defaults(self.doc, self.body, sk2), distance="3 mm"))
        self.doc.recompute()
        name = model.bound_parameter(f, "Length")
        g = extrude.update(self.doc, f, dict(extrude.read(self.doc, f), operation="cut"))
        self.doc.recompute()
        self.assertEqual(g.TypeId, "PartDesign::Pocket")
        self.assertEqual(model.bound_parameter(g, "Length"), name)
        self.assertIs(self.body.Tip, g)
        self.assertLess(g.Shape.Volume, base.Shape.Volume)

    def test_through_all_cut(self):
        base = self.make(distance="10 mm")
        sk2 = util.add_rect_sketch(self.body, w=4, h=4, name="Cutter")
        self.doc.recompute()
        f = extrude.create(self.doc, self.body, sk2, dict(extrude.defaults(self.doc, self.body, sk2),
                                                          operation="cut", extent="through_all", direction="symmetric"))
        self.doc.recompute()
        self.assertEqual((f.TypeId, f.Type), ("PartDesign::Pocket", "ThroughAll"))
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 10 - 4 * 4 * 10, places=3)

    def test_two_sides(self):
        f = self.make(direction="two_sides", distance="10 mm", distance2="5 mm")
        self.assertEqual(f.SideType, "Two sides")
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 15, places=3)

    def test_new_solid_moves_the_sketch(self):
        f = self.make(operation="new_solid")
        self.assertEqual(len(document.bodies(self.doc)), 2)
        self.assertIsNot(f.getParentGeoFeatureGroup(), self.body)
        self.assertIs(self.sk.getParentGeoFeatureGroup(), f.getParentGeoFeatureGroup())

    def test_intersect(self):
        self.make(distance="10 mm")
        sk2 = util.add_rect_sketch(self.body, w=5, h=5, name="Cross")
        self.doc.recompute()
        f = extrude.create(self.doc, self.body, sk2, dict(extrude.defaults(self.doc, self.body, sk2),
                                                          operation="intersect", distance="30 mm"))
        self.doc.recompute()
        self.assertEqual(f.TypeId, "PartDesign::Boolean")
        self.assertAlmostEqual(self.body.Shape.Volume, 5 * 5 * 10, places=3)

    def test_default_operation_is_cut_inside_material(self):
        self.make(distance="10 mm")
        mid = self.body.newObject("Sketcher::SketchObject", "Mid")
        mid.AttachmentSupport = [(util.xy_plane(self.body), "")]
        mid.MapMode = "FlatFace"
        mid.AttachmentOffset = App.Placement(App.Vector(0, 0, 5), App.Rotation())
        mid.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        self.assertEqual(extrude.defaults(self.doc, self.body, mid)["operation"], "cut")
```

`tests/headless/test_revolve.py`:
```python
import math
import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import kind_for, revolve
from headless import util


class RevolveTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("R")
        self.body = document.make_part(self.doc)
        sk = self.body.newObject("Sketcher::SketchObject", "Profile")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        pts = [(2, 0), (6, 0), (6, 4), (2, 4)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)))
        self.sk = sk
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_full_revolve(self):
        v = revolve.defaults(self.doc, self.body, self.sk)
        self.assertEqual((v["operation"], v["axis"], v["extent"]), ("join", "V_Axis", "full"))
        f = revolve.create(self.doc, self.body, self.sk, v)
        self.doc.recompute()
        self.assertEqual(f.TypeId, "PartDesign::Revolution")
        self.assertAlmostEqual(f.Shape.Volume, math.pi * (6 ** 2 - 2 ** 2) * 4, places=2)
        self.assertIs(kind_for(f), revolve)

    def test_angle_parameter(self):
        f = revolve.create(self.doc, self.body, self.sk,
                           dict(revolve.defaults(self.doc, self.body, self.sk), extent="angle", angle="90"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Angle.Value, 90)
        self.assertEqual(revolve.read(self.doc, f)["angle"], "90 °")
        name = model.bound_parameter(f, "Angle")
        self.assertIsNotNone(name)
        f = revolve.update(self.doc, f, dict(revolve.read(self.doc, f), angle="180"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Angle.Value, 180)
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_headless.sh test_extrude.py`, `tests/run_headless.sh test_revolve.py` → Expected: `No module named 'incad.features'`.

- [ ] **Step 3: Implement**

`InCad/incad/features/__init__.py`:
```python
"""Feature kinds: pure model modules (FIELDS, defaults, create, read, update) that the feature dialog drives."""
from incad.features import extrude, revolve

KINDS = [extrude, revolve]


def kind_for(feature):
    for kind in KINDS:
        if feature is not None and feature.TypeId in kind.TYPES:
            return kind
    return None
```

`InCad/incad/features/common.py`:
```python
"""Helpers shared by feature kinds."""
from dataclasses import dataclass

from incad.core import model, sketch


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str                # value_length | value_angle | choice | bool | pick
    choices: tuple = ()      # ((value, label), …) for choice
    default: object = None
    show_if: tuple = None    # (other key, (values…)): shown only when that field has one of the values


def closed_profile(sk):
    try:
        return any(w.isClosed() for w in sk.Shape.Wires)
    except Exception:
        return False


def consumers(sk):
    return [o for o in sk.InList if getattr(o, "Profile", None) is not None and _profile(o) is sk]


def _profile(feature):
    prof = getattr(feature, "Profile", None)
    if isinstance(prof, (tuple, list)):
        prof = prof[0] if prof else None
    return prof


def unconsumed_closed_sketches(body):
    return [o for o in body.Group if sketch.is_sketch(o) and closed_profile(o) and not consumers(o)]


def value_param(doc, feature, prop, text, unit_kind):
    """Bind feature.prop to a model parameter holding `text` (create one if the property has none yet)."""
    name = model.bound_parameter(feature, prop)
    if name is None:
        name = model.new_feature_parameter(doc, text, unit_kind)
        model.bind(feature, prop, name)
    elif model.parameter_text(doc, name) != text:
        model.set_model_parameter(doc, name, text)
    return name


def value_text(doc, feature, prop):
    name = model.bound_parameter(feature, prop)
    return model.parameter_text(doc, name) if name else ""


def profile_of(feature):
    return _profile(feature)
```

`InCad/incad/features/extrude.py`:
```python
"""Extrude (Inventor) = PartDesign Pad (Join) / Pocket (Cut); Intersect = a second body + Boolean Common;
New Solid = the profile sketch moved into a new body."""
import FreeCAD as App

from incad.core import document
from incad.features.common import Field, profile_of, value_param, value_text

TITLE = "Extrude"
ICON = "extrude"
TYPES = ("PartDesign::Pad", "PartDesign::Pocket")
FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut"), ("intersect", "Intersect"),
                                               ("new_solid", "New Solid")), "join"),
    Field("extent", "Extents", "choice", (("distance", "Distance"), ("to_next", "To Next"),
                                          ("through_all", "Through All"), ("to", "To")), "distance"),
    Field("to_face", "Face", "pick", show_if=("extent", ("to",))),
    Field("distance", "Distance", "value_length", default="10 mm", show_if=("extent", ("distance",))),
    Field("direction", "Direction", "choice", (("default", "→"), ("flip", "←"), ("symmetric", "⇆"),
                                               ("two_sides", "⇄ 2")), "default"),
    Field("distance2", "Distance 2", "value_length", default="5 mm", show_if=("direction", ("two_sides",))),
    Field("taper", "Taper", "value_angle", default="0 °"),
)
_TYPE = {"distance": "Length", "to_next": "UpToFirst", "to": "UpToFace"}


def _normal(sk):
    return sk.Placement.Rotation.multVec(App.Vector(0, 0, 1))


def default_operation(body, sk):
    """Cut when the profile lies inside the material (Inventor pre-selects Cut there), otherwise Join."""
    shape = body.Shape
    if shape.isNull() or shape.Volume <= 0:
        return "join"
    try:
        centre = sk.Shape.BoundBox.Center
        return "cut" if shape.isInside(centre + _normal(sk) * 0.01, 1e-6, True) else "join"
    except Exception:
        return "join"


def defaults(doc, body, profile):
    values = {f.key: f.default for f in FIELDS}
    values["operation"] = default_operation(body, profile)
    values["to_face"] = ""
    return values


def _feature_type(operation):
    return "PartDesign::Pocket" if operation == "cut" else "PartDesign::Pad"


def _apply(doc, f, values):
    cut = f.TypeId == "PartDesign::Pocket"
    extent = values.get("extent", "distance")
    f.Type = ("ThroughAll" if cut else "UpToLast") if extent == "through_all" else _TYPE.get(extent, "Length")
    if extent == "to" and values.get("to_face"):
        obj_name, face = values["to_face"].split(":")
        f.UpToFace = (doc.getObject(obj_name), [face])
    direction = values.get("direction", "default")
    f.SideType = {"symmetric": "Symmetric", "two_sides": "Two sides"}.get(direction, "One side")
    f.Reversed = direction == "flip"
    value_param(doc, f, "Length", values.get("distance") or "10 mm", "length")
    if direction == "two_sides":
        value_param(doc, f, "Length2", values.get("distance2") or "5 mm", "length")
    value_param(doc, f, "TaperAngle", values.get("taper") or "0 °", "angle")


def create(doc, body, profile, values):
    operation = values.get("operation", "join")
    target = body
    if operation in ("new_solid", "intersect"):
        target = document.new_solid(doc)
        body.removeObject(profile)
        target.addObject(profile)
    f = target.newObject(_feature_type("cut" if operation == "cut" else "join"), "Extrude")
    f.Profile = profile
    _apply(doc, f, values)
    if operation == "intersect":
        doc.recompute()
        common = body.newObject("PartDesign::Boolean", "Intersect")
        common.Type = "Common"
        common.addObjects([target])
        return common
    return f


def _pad_of(feature):
    if feature.TypeId == "PartDesign::Boolean":
        tool = feature.Group[0] if feature.Group else None
        return tool.Tip if tool is not None else None
    return feature


def read(doc, feature):
    if feature.TypeId == "PartDesign::Boolean":
        values = read(doc, _pad_of(feature))
        values["operation"] = "intersect"
        return values
    f = feature
    operation = "cut" if f.TypeId == "PartDesign::Pocket" else "join"
    body = f.getParentGeoFeatureGroup()
    if operation == "join" and body is not None and document.primary_body(doc) is not body:
        operation = "new_solid"
    extent = {"Length": "distance", "UpToFirst": "to_next", "UpToFace": "to", "ThroughAll": "through_all",
              "UpToLast": "through_all"}.get(f.Type, "distance")
    direction = {"Symmetric": "symmetric", "Two sides": "two_sides"}.get(f.SideType, "flip" if f.Reversed else "default")
    to_face = ""
    if f.UpToFace and f.UpToFace[0] is not None and f.UpToFace[1]:
        to_face = "%s:%s" % (f.UpToFace[0].Name, f.UpToFace[1][0])
    return {"operation": operation, "extent": extent, "direction": direction, "to_face": to_face,
            "distance": value_text(doc, f, "Length") or "10 mm",
            "distance2": value_text(doc, f, "Length2") or "5 mm",
            "taper": value_text(doc, f, "TaperAngle") or "0 °"}


def update(doc, feature, values):
    """Apply dialog values. Join<->Cut replaces Pad/Pocket in place, keeping its parameters."""
    f = _pad_of(feature)
    wanted = values.get("operation", "join")
    if wanted in ("join", "cut") and f.TypeId != _feature_type(wanted) and feature.TypeId != "PartDesign::Boolean":
        f = _replace(doc, f, _feature_type(wanted))
    _apply(doc, f, values)
    return feature if feature.TypeId == "PartDesign::Boolean" else f


def _replace(doc, old, type_id):
    body = old.getParentGeoFeatureGroup()
    profile = profile_of(old)
    bindings = {p: e for p, e in old.ExpressionEngine}
    was_tip = body.Tip is old
    index = body.Group.index(old)
    after = body.Group[index - 1] if index > 0 else None
    label = old.Label
    body.removeObject(old)
    doc.removeObject(old.Name)
    new = doc.addObject(type_id, "Extrude")
    body.insertObject(new, after, True) if after is not None else body.insertObject(new, body.Group[0] if body.Group else None, False)
    new.Label = label
    new.Profile = profile
    for path, expr in bindings.items():
        new.setExpression(path.lstrip("."), expr)
    if was_tip:
        body.Tip = new
    return new
```

`InCad/incad/features/revolve.py`:
```python
"""Revolve (Inventor) = PartDesign Revolution (Join) / Groove (Cut) around a sketch axis."""
from incad.features.common import Field, profile_of, value_param, value_text

TITLE = "Revolve"
ICON = "revolve"
TYPES = ("PartDesign::Revolution", "PartDesign::Groove")
FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut")), "join"),
    Field("axis", "Axis", "choice", (("V_Axis", "Sketch vertical"), ("H_Axis", "Sketch horizontal")), "V_Axis"),
    Field("extent", "Extents", "choice", (("full", "Full"), ("angle", "Angle"), ("two_angles", "Two angles")), "full"),
    Field("angle", "Angle", "value_angle", default="90 °", show_if=("extent", ("angle", "two_angles"))),
    Field("angle2", "Angle 2", "value_angle", default="90 °", show_if=("extent", ("two_angles",))),
    Field("flip", "Flip", "bool", default=False, show_if=("extent", ("angle",))),
)


def defaults(doc, body, profile):
    return {f.key: f.default for f in FIELDS}


def _type(operation):
    return "PartDesign::Groove" if operation == "cut" else "PartDesign::Revolution"


def _apply(doc, f, values):
    f.ReferenceAxis = (profile_of(f), [values.get("axis", "V_Axis")])
    extent = values.get("extent", "full")
    f.Type = "TwoAngles" if extent == "two_angles" else "Angle"
    f.Reversed = bool(values.get("flip")) and extent == "angle"
    if extent == "full":
        value_param(doc, f, "Angle", "360 °", "angle")
    else:
        value_param(doc, f, "Angle", values.get("angle") or "90 °", "angle")
    if extent == "two_angles":
        value_param(doc, f, "Angle2", values.get("angle2") or "90 °", "angle")


def create(doc, body, profile, values):
    f = body.newObject(_type(values.get("operation", "join")), "Revolve")
    f.Profile = profile
    _apply(doc, f, values)
    return f


def read(doc, f):
    angle = value_text(doc, f, "Angle") or "90 °"
    extent = "two_angles" if f.Type == "TwoAngles" else ("full" if abs(f.Angle.Value - 360) < 1e-9 else "angle")
    axis = f.ReferenceAxis[1][0] if f.ReferenceAxis and f.ReferenceAxis[1] else "V_Axis"
    return {"operation": "cut" if f.TypeId == "PartDesign::Groove" else "join", "axis": axis, "extent": extent,
            "angle": angle, "angle2": value_text(doc, f, "Angle2") or "90 °", "flip": bool(f.Reversed)}


def update(doc, f, values):
    if f.TypeId != _type(values.get("operation", "join")):
        from incad.features import extrude
        f = extrude._replace(doc, f, _type(values.get("operation", "join")))
    _apply(doc, f, values)
    return f
```

- [ ] **Step 4: Run to verify they pass**

Run: `tests/run_headless.sh test_extrude.py`, `tests/run_headless.sh test_revolve.py` → Expected: all OK. Where a
FreeCAD detail differs (e.g. `insertObject` argument order, Pad `UpToLast` for Through All), check it in a probe
and fix the module; the tests stay.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/features tests/headless/test_extrude.py tests/headless/test_revolve.py && git commit -m "InCad 1d-1: Extrude and Revolve kinds"
```

---

### Task 4: Feature dialog widget

**Files:**
- Create: `InCad/incad/ui/feature_dialog.py`, `tests/widgets/test_feature_dialog.py`

**Interfaces:**
- Consumes: `features.common.Field`.
- Produces: `ValueField(QLineEdit)` with `insert(name)`; `FeatureDialog(title, icon, fields, values, theme="light",
  parent=None)`: signals `changed(dict)`, `accepted()`, `applied()`, `cancelled()`, `pickRequested(str key)`;
  `values() -> dict`, `set_values(dict)` (no signal), `set_error(text)` (empty = no error; OK/Apply disabled
  while an error is shown), `set_pick_text(key, text)`, `set_param_name(key, name)`, `focused_value_field()`,
  `field(key)`, `set_choice_enabled(key, value, enabled)`. Enter in a value field = OK; Esc = Cancel. Rows whose
  `show_if` does not match are hidden.

- [ ] **Step 1: Write the failing test**

`tests/widgets/test_feature_dialog.py`:
```python
import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.features.common import Field
from incad.ui.feature_dialog import FeatureDialog

FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut")), "join"),
    Field("extent", "Extents", "choice", (("distance", "Distance"), ("to", "To")), "distance"),
    Field("to_face", "Face", "pick", show_if=("extent", ("to",))),
    Field("distance", "Distance", "value_length", default="10 mm", show_if=("extent", ("distance",))),
    Field("flip", "Flip", "bool", default=False),
)


class FeatureDialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Extrude", "incad", FIELDS,
                               {"operation": "join", "extent": "distance", "to_face": "", "distance": "10 mm",
                                "flip": False})
        self.seen = []
        self.d.changed.connect(lambda v: self.seen.append(dict(v)))
        self.d.show()

    def tearDown(self):
        self.d.close()

    def test_values_round_trip(self):
        self.assertEqual(self.d.values(), {"operation": "join", "extent": "distance", "to_face": "",
                                           "distance": "10 mm", "flip": False})

    def test_choice_change_emits(self):
        self.d.field("operation").button("cut").click()
        self.assertEqual(self.seen[-1]["operation"], "cut")

    def test_value_edit_emits(self):
        self.d.field("distance").setText("25 mm")
        self.d.field("distance").editingFinished.emit()
        self.assertEqual(self.seen[-1]["distance"], "25 mm")

    def test_show_if_hides_rows(self):
        self.assertTrue(self.d.row_visible("distance"))
        self.assertFalse(self.d.row_visible("to_face"))
        self.d.field("extent").button("to").click()
        self.assertFalse(self.d.row_visible("distance"))
        self.assertTrue(self.d.row_visible("to_face"))

    def test_error_disables_ok(self):
        self.d.set_error("Pad: length is zero")
        self.assertFalse(self.d.ok_button.isEnabled())
        self.assertIn("zero", self.d.error_text())
        self.d.set_error("")
        self.assertTrue(self.d.ok_button.isEnabled())

    def test_buttons_and_keys(self):
        from PySide6.QtTest import QTest
        got = []
        self.d.accepted.connect(lambda: got.append("ok"))
        self.d.cancelled.connect(lambda: got.append("cancel"))
        self.d.applied.connect(lambda: got.append("apply"))
        self.d.apply_button.click()
        QTest.keyClick(self.d.field("distance"), QtCore.Qt.Key_Return)
        QTest.keyClick(self.d.field("distance"), QtCore.Qt.Key_Escape)
        self.assertEqual(got, ["apply", "ok", "cancel"])

    def test_insert_into_focused_field(self):
        f = self.d.field("distance")
        f.setFocus()
        f.selectAll()
        self.assertIs(self.d.focused_value_field(), f) if f.hasFocus() else None
        f.insert("d3")
        self.assertEqual(f.text(), "d3")

    def test_param_name_and_pick_text(self):
        self.d.set_param_name("distance", "d4")
        self.assertIn("d4", self.d.label_text("distance"))
        self.d.set_pick_text("to_face", "Pad · Face6")
        self.assertEqual(self.d.pick_text("to_face"), "Pad · Face6")
        picks = []
        self.d.pickRequested.connect(picks.append)
        self.d.field("to_face").click()
        self.assertEqual(picks, ["to_face"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `tests/run_widgets.sh test_feature_dialog.py` → Expected: `No module named 'incad.ui.feature_dialog'`.

- [ ] **Step 3: Implement**

`InCad/incad/ui/feature_dialog.py`:
```python
"""Floating feature dialog (Inventor style): fields built from the feature kind's FIELDS, live changes, an error
line, OK / Apply / Cancel. Value fields accept units, parameter names and formulas; clicking a dimension or a
parameter while one has focus inserts the name."""
from incad.qt import QtCore, QtWidgets, Signal
from incad.ui import theme as themes


class ValueField(QtWidgets.QLineEdit):
    def insert(self, name):
        super().insert(name)
        self.setFocus()


class ChoiceField(QtWidgets.QWidget):
    changed = Signal()

    def __init__(self, choices, parent=None):
        super().__init__(parent)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for value, label in choices:
            b = QtWidgets.QToolButton(self)
            b.setText(label)
            b.setCheckable(True)
            b.setObjectName("InCadSegment")
            self._group.addButton(b)
            row.addWidget(b)
            self._buttons[value] = b
            b.clicked.connect(lambda _=False: self.changed.emit())

    def button(self, value):
        return self._buttons[value]

    def value(self):
        for v, b in self._buttons.items():
            if b.isChecked():
                return v
        return None

    def set_value(self, value):
        if value in self._buttons:
            self._buttons[value].setChecked(True)


class FeatureDialog(QtWidgets.QFrame):
    changed = Signal(dict)
    accepted = Signal()
    applied = Signal()
    cancelled = Signal()
    pickRequested = Signal(str)

    def __init__(self, title, icon, fields, values, theme="light", parent=None):
        super().__init__(parent)
        self.setObjectName("InCadFeatureDialog")
        self._fields = {f.key: f for f in fields}
        self._widgets, self._labels, self._rows = {}, {}, {}
        self._loading = False
        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(10, 8, 10, 8)
        head = QtWidgets.QHBoxLayout()
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(themes.icon(icon, theme).pixmap(18, 18))
        head.addWidget(icon_label)
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("InCadDialogTitle")
        head.addWidget(title_label, 1)
        col.addLayout(head)
        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(8)
        for r, f in enumerate(fields):
            label = QtWidgets.QLabel(f.label)
            widget = self._make(f)
            form.addWidget(label, r, 0)
            form.addWidget(widget, r, 1)
            self._labels[f.key], self._widgets[f.key], self._rows[f.key] = label, widget, (label, widget)
        col.addLayout(form)
        self._error = QtWidgets.QLabel("")
        self._error.setObjectName("InCadDialogError")
        self._error.setWordWrap(True)
        self._error.hide()
        col.addWidget(self._error)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.apply_button = QtWidgets.QPushButton("Apply +")
        self.ok_button = QtWidgets.QPushButton("OK")
        self.ok_button.setDefault(True)
        for b in (self.cancel_button, self.apply_button, self.ok_button):
            buttons.addWidget(b)
        self.cancel_button.clicked.connect(self.cancelled.emit)
        self.apply_button.clicked.connect(self.applied.emit)
        self.ok_button.clicked.connect(self.accepted.emit)
        col.addLayout(buttons)
        p = themes.PALETTES[theme]
        self.setStyleSheet(
            "QFrame#InCadFeatureDialog {{ background: {panel}; border: 1px solid {border}; border-radius: 9px; }}"
            " QLabel {{ color: {text}; }} QLabel#InCadDialogTitle {{ font-weight: 600; }}"
            " QLabel#InCadDialogError {{ color: {error}; }}"
            " QLineEdit {{ background: {panel_alt}; color: {text}; border: 1px solid {border}; border-radius: 4px;"
            " padding: 2px 4px; }} QToolButton#InCadSegment {{ background: {panel_alt}; color: {text};"
            " border: 1px solid {border}; padding: 2px 8px; }} QToolButton#InCadSegment:checked {{"
            " background: {accent}; color: {selection_text}; }}".format(**p))
        self.set_values(values)

    # ----- building -----
    def _make(self, f):
        if f.kind in ("value_length", "value_angle"):
            w = ValueField(self)
            w.setMinimumWidth(130)
            w.editingFinished.connect(self._emit)
            w.returnPressed.connect(self.accepted.emit)
            w.installEventFilter(self)
            return w
        if f.kind == "choice":
            w = ChoiceField(f.choices, self)
            w.changed.connect(self._emit)
            return w
        if f.kind == "bool":
            w = QtWidgets.QCheckBox(self)
            w.toggled.connect(lambda _=False: self._emit())
            return w
        w = QtWidgets.QPushButton("Select…", self)
        w.setObjectName("InCadPick")
        w.clicked.connect(lambda _=False, k=f.key: self.pickRequested.emit(k))
        return w

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Escape:
            self.cancelled.emit()
            return True
        return False

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)

    # ----- values -----
    def values(self):
        out = {}
        for key, f in self._fields.items():
            w = self._widgets[key]
            if f.kind in ("value_length", "value_angle"):
                out[key] = w.text().strip()
            elif f.kind == "choice":
                out[key] = w.value()
            elif f.kind == "bool":
                out[key] = w.isChecked()
            else:
                out[key] = w.property("pick") or ""
        return out

    def set_values(self, values):
        self._loading = True
        try:
            for key, value in values.items():
                f, w = self._fields.get(key), self._widgets.get(key)
                if f is None:
                    continue
                if f.kind in ("value_length", "value_angle"):
                    w.setText(str(value))
                elif f.kind == "choice":
                    w.set_value(value)
                elif f.kind == "bool":
                    w.setChecked(bool(value))
                else:
                    w.setProperty("pick", value or "")
                    if not value:
                        w.setText("Select…")
        finally:
            self._loading = False
        self._update_visibility()

    def _emit(self):
        self._update_visibility()
        if not self._loading:
            self.changed.emit(self.values())

    def _update_visibility(self):
        values = self.values()
        for key, f in self._fields.items():
            shown = f.show_if is None or values.get(f.show_if[0]) in f.show_if[1]
            for w in self._rows[key]:
                w.setVisible(shown)

    # ----- helpers for the session and tests -----
    def field(self, key):
        return self._widgets[key]

    def row_visible(self, key):
        return not self._rows[key][1].isHidden()

    def label_text(self, key):
        return self._labels[key].text()

    def set_param_name(self, key, name):
        f = self._fields[key]
        self._labels[key].setText("%s  (%s)" % (f.label, name) if name else f.label)

    def set_pick_text(self, key, text):
        self._widgets[key].setText(text or "Select…")

    def pick_text(self, key):
        return self._widgets[key].text()

    def set_choice_enabled(self, key, value, enabled):
        self._widgets[key].button(value).setEnabled(enabled)

    def set_error(self, text):
        self._error.setText(text)
        self._error.setVisible(bool(text))
        self.ok_button.setEnabled(not text)
        self.apply_button.setEnabled(not text)

    def error_text(self):
        return self._error.text()

    def focused_value_field(self):
        for key, f in self._fields.items():
            w = self._widgets[key]
            if f.kind in ("value_length", "value_angle") and w.hasFocus():
                return w
        return getattr(self, "_last_value_field", None)
```
In `_make` for value fields also remember the last focused field: add
`w.installEventFilter(self)` (already) and in `eventFilter` add, before the Esc check:
```python
        if event.type() == QtCore.QEvent.FocusIn and isinstance(obj, ValueField):
            self._last_value_field = obj
```

- [ ] **Step 4: Run to verify it passes**

Run: `tests/run_widgets.sh test_feature_dialog.py` → Expected: 8 tests `OK`.

- [ ] **Step 5: Commit**

```bash
git add InCad/incad/ui/feature_dialog.py tests/widgets/test_feature_dialog.py && git commit -m "InCad 1d-1: feature dialog widget"
```

---

### Task 5: Commands, icons, layouts

**Files:**
- Modify: `tools/make_icons.py`, `InCad/incad/actions.py`, `InCad/incad/ui/ribbon_layout.py`,
  `InCad/incad/ui/marking_layout.py`, `tests/widgets/test_actions.py`, `tests/widgets/test_marking_layout.py`

**Interfaces:**
- Produces: commands `feature.extrude` (E, context part), `feature.revolve` (R, context part); `actions.start_feature(kind_name)`
  and `edit_feature` dispatch call `shell.start_feature(kind_module)` / `shell.edit_feature(feature)` (Task 6);
  icons `extrude`, `revolve`; ribbon 3D Model ▸ Create [Extrude, Revolve]; marking menu: part S = Extrude, face
  S = Extrude (zoom_selection moves to the face list), part list gains Zoom All.

- [ ] **Step 1: Write the failing tests**

In `tests/widgets/test_actions.py` change the end of `EXPECTED` to
`"sketch.start", "sketch.finish", "feature.extrude", "feature.revolve"} | set(actions.SKETCHER)` and append to
`ActionsTest`:
```python
    def test_feature_shortcuts(self):
        r = Registry()
        actions.register_all(r)
        self.assertEqual((r.get("feature.extrude").shortcut, r.get("feature.revolve").shortcut), ("E", "R"))
        self.assertEqual(r.get("feature.extrude").contexts, frozenset({"part"}))
```
In `tests/widgets/test_marking_layout.py` add to `test_contexts`:
```python
        self.assertEqual(marking_layout.LAYOUT["part"]["S"], "feature.extrude")
        self.assertEqual(marking_layout.LAYOUT["face"]["S"], "feature.extrude")
```

- [ ] **Step 2: Run to verify they fail**

Run: `tests/run_widgets.sh test_actions.py`, `tests/run_widgets.sh test_marking_layout.py` → Expected: failures.

- [ ] **Step 3: Implement**

`tools/make_icons.py` — add to `ICONS`:
```python
    "extrude": ('<path d="M6 22 L6 12 L16 8 L26 11 L26 21 L14 25 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M6 12 L14 15 L26 11 M14 15 L14 25" fill="none" stroke="{S}" stroke-width="1.2"/>'
                '<path d="M20 9 V2" stroke="{A}" stroke-width="2.2"/><path d="M17 5 L20 1 L23 5" fill="none" '
                'stroke="{A}" stroke-width="2.2" stroke-linejoin="round"/>'),
    "revolve": ('<ellipse cx="16" cy="9" rx="10" ry="3.5" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M6 9 V23 A10 3.5 0 0 0 26 23 V9" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M16 3 V29" stroke="{A}" stroke-width="1.6" stroke-dasharray="3 2"/>'),
```
Run `python3 tools/make_icons.py` → `wrote 65 icons per theme`.

`InCad/incad/actions.py` — add before `def _std(`:
```python
def start_feature(kind_name):
    from incad import features
    from incad.ui import shell
    kind = {k.__name__.rsplit(".", 1)[-1]: k for k in features.KINDS}[kind_name]
    shell.start_feature(kind)
```
in `edit_feature`, replace the `else:` branch with:
```python
    else:
        from incad import features
        from incad.ui import shell
        if features.kind_for(obj) is None:
            log.report("info", "Editing this feature arrives with the next feature tools (plan 1d-2)")
        else:
            shell.edit_feature(obj)
```
and add to the `commands()` list (before the `] + [Command(...SKETCHER…)]` part):
```python
        Command(id="feature.extrude", label="Extrude", icon="extrude", handler=lambda: start_feature("extrude"),
                shortcut="E", contexts=frozenset({"part"}), tooltip="Extrude a sketch profile"),
        Command(id="feature.revolve", label="Revolve", icon="revolve", handler=lambda: start_feature("revolve"),
                shortcut="R", contexts=frozenset({"part"}), tooltip="Revolve a sketch profile around an axis"),
```

`InCad/incad/ui/ribbon_layout.py` — part ▸ "3D Model":
`["3D Model", [["Sketch", ["sketch.start"]], ["Create", ["feature.extrude", "feature.revolve"]]]],`

`InCad/incad/ui/marking_layout.py` — part: `"S": "feature.extrude"` and `"list": ["view.zoom_all", "view.home",
"view.freecad"]`; face: `"S": "feature.extrude"` and `"list": ["view.zoom_selection"]`.

- [ ] **Step 4: Run to verify they pass**

Run the Step 2 commands plus `tests/run_widgets.sh test_icons.py` → Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add tools InCad tests && git commit -m "InCad 1d-1: Extrude/Revolve commands, icons, ribbon and marking menu"
```

---

### Task 6: Feature session and shell wiring

**Files:**
- Create: `InCad/incad/ui/feature_session.py`, `tests/gui/test_features.py`
- Modify: `InCad/incad/ui/shell.py`

**Interfaces:**
- Produces (`incad.ui.feature_session.FeatureSession(kind, doc, body, profile=None, feature=None, theme, parent,
  on_close)`): `start() -> bool`, `dialog`, `feature`, `ok()`, `apply()`, `cancel()`, `insert(name)`.
- Produces (`incad.ui.shell`): `Shell.feature_session`; module `start_feature(kind)`, `edit_feature(feature)`.
  Profile choice: selected sketch → sketch being edited (finished first) → the only unconsumed closed sketch → pick
  mode (status prompt, Esc cancels).

- [ ] **Step 1: Write the failing GUI tests**

`tests/gui/test_features.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, model, prefs, safe  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def type_into(key, text):
    w = dialog().field(key)
    w.setText(text)
    w.editingFinished.emit()
    harness.pump(500)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    ST["sk"] = util.add_rect_sketch(body())
    doc().recompute()
    harness.pump(300)


def test_1_extrude_picks_the_only_profile_and_previews():
    commands.REGISTRY.run("feature.extrude")
    harness.pump(800)
    assert dialog() is not None and dialog().isVisible()
    f = s().feature_session.feature
    assert f is not None and f.TypeId == "PartDesign::Pad" and abs(f.Shape.Volume - 2000) < 1e-6
    assert safe.busy() == "Extrude"


def test_2_ok_commits_one_undo_step():
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(600)
    assert s().feature_session is None and safe.busy() is None
    assert "Extrude" in doc().UndoNames[:1], doc().UndoNames
    pad = body().Tip
    ST["pad"] = pad.Name
    assert model.bound_parameter(pad, "Length") is not None


def test_3_edit_feature_changes_the_distance():
    pad = doc().getObject(ST["pad"])
    shell.edit_feature(pad)
    harness.pump(600)
    type_into("distance", "25 mm")
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(600)
    assert abs(doc().getObject(ST["pad"]).Length.Value - 25) < 1e-6


def test_4_cancel_restores_after_previews():
    names = list(doc().UndoNames)
    shell.edit_feature(doc().getObject(ST["pad"]))
    harness.pump(600)
    type_into("distance", "50 mm")
    dialog().field("operation").button("cut").click()
    harness.pump(600)
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)
    pad = doc().getObject(ST["pad"])
    assert pad is not None and pad.TypeId == "PartDesign::Pad" and abs(pad.Length.Value - 25) < 1e-6
    assert list(doc().UndoNames) == names, (doc().UndoNames, names)


def test_5_invalid_value_disables_ok():
    shell.edit_feature(doc().getObject(ST["pad"]))
    harness.pump(600)
    type_into("distance", "Nope * 2")
    assert not dialog().ok_button.isEnabled() and dialog().error_text()
    type_into("distance", "0")
    assert not dialog().ok_button.isEnabled()
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)


def test_6_cut_through_all_on_top():
    pad = doc().getObject(ST["pad"])
    top = [i + 1 for i, fc in enumerate(pad.Shape.Faces) if abs(fc.CenterOfMass.z - 25) < 1e-6][0]
    sk = body().newObject("Sketcher::SketchObject", "Cutter")
    sk.AttachmentSupport = [(pad, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
    doc().recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(800)
    dialog().field("operation").button("cut").click()
    dialog().field("extent").button("through_all").click()
    harness.pump(600)
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(600)
    tip = body().Tip
    assert tip.TypeId == "PartDesign::Pocket", tip.TypeId
    assert body().Shape.Volume < 20 * 10 * 25 - 1


def test_7_new_solid_and_cancel_moves_sketch_back():
    sk = util.add_rect_sketch(body(), w=5, h=5, name="Other")
    doc().recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(800)
    dialog().field("operation").button("new_solid").click()
    harness.pump(600)
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)
    assert len(document.bodies(doc())) == 1
    assert doc().getObject(sk.Name).getParentGeoFeatureGroup() is body()


def test_8_revolve():
    sk = body().newObject("Sketcher::SketchObject", "RevProfile")
    sk.AttachmentSupport = [(util.xy_plane(body()), "")]
    sk.MapMode = "FlatFace"
    pts = [(30, 0), (34, 0), (34, 4), (30, 4)]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)))
    doc().recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.revolve")
    harness.pump(800)
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(600)
    assert body().Tip.TypeId == "PartDesign::Revolution"


def test_9_parameter_click_inserts_into_the_focused_field():
    document.set_parameter(doc(), "Width", "30 mm")
    shell.edit_feature(doc().getObject(ST["pad"]))
    harness.pump(600)
    f = dialog().field("distance")
    f.setFocus()
    f.selectAll()
    harness.pump(100)
    s().browser.parameterClicked.emit("Width")
    harness.pump(100)
    assert f.text() == "Width", f.text()
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)


def test_10_busy_blocks_other_changes_and_is_cleared():
    shell.edit_feature(doc().getObject(ST["pad"]))
    harness.pump(600)
    s().browser.parameterSet.emit("Gap", "1 mm")
    harness.pump(400)
    assert "Gap" not in [p[0] for p in document.list_parameters(doc())]
    assert "dialog" in s().status.texts()["message"].lower(), s().status.texts()
    QTest.keyClick(dialog().field("distance"), QtCore.Qt.Key_Escape)
    harness.pump(600)
    assert safe.busy() is None and s().feature_session is None


def test_11_leaving_incad_closes_the_dialog():
    shell.edit_feature(doc().getObject(ST["pad"]))
    harness.pump(600)
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert safe.busy() is None
    assert abs(doc().getObject(ST["pad"]).Length.Value - 25) < 1e-6


harness.run([test_0_setup, test_1_extrude_picks_the_only_profile_and_previews, test_2_ok_commits_one_undo_step,
             test_3_edit_feature_changes_the_distance, test_4_cancel_restores_after_previews,
             test_5_invalid_value_disables_ok, test_6_cut_through_all_on_top,
             test_7_new_solid_and_cancel_moves_sketch_back, test_8_revolve,
             test_9_parameter_click_inserts_into_the_focused_field, test_10_busy_blocks_other_changes_and_is_cleared,
             test_11_leaving_incad_closes_the_dialog])
```

- [ ] **Step 2: Run to verify they fail**

Announce the FreeCAD window. Run: `tests/run_gui.sh tests/gui/test_features.py` → Expected: failures from test_1.

- [ ] **Step 3: Implement the session**

`InCad/incad/ui/feature_session.py`:
```python
"""One feature dialog: one undo transaction around create/edit + live previews; OK commits, Cancel aborts."""
from incad.core import log, model, safe
from incad.qt import QtCore
from incad.ui.feature_dialog import FeatureDialog


class FeatureSession(QtCore.QObject):
    def __init__(self, kind, doc, body, profile=None, feature=None, theme="light", parent=None, on_close=None):
        super().__init__(parent)
        self.kind, self.doc, self.body, self.profile = kind, doc, body, profile
        self.feature = feature
        self.creating = feature is None
        self._theme, self._parent, self._on_close = theme, parent, on_close
        self.dialog = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._preview)
        self._pending = None
        self._closed = False

    def start(self):
        doc = self.doc
        if not doc.UndoMode:
            doc.UndoMode = 1
        if doc.HasPendingTransaction:
            doc.commitTransaction()
        self._broken = safe.snapshot_broken(doc)
        doc.openTransaction(self.kind.TITLE)
        safe.set_busy(self.kind.TITLE)
        try:
            if self.creating:
                values = self.kind.defaults(doc, self.body, self.profile)
                self.feature = self.kind.create(doc, self.body, self.profile, values)
            else:
                values = self.kind.read(doc, self.feature)
            doc.recompute()
        except Exception as e:
            log.report("error", "%s could not start: %s" % (self.kind.TITLE, e))
            self._finish(commit=False)
            return False
        self.dialog = FeatureDialog(self.kind.TITLE, self.kind.ICON, self.kind.FIELDS, values, self._theme, self._parent)
        if not self.creating:
            for value in ("intersect", "new_solid"):
                if "operation" in self.dialog._widgets and value in self.dialog.field("operation")._buttons:
                    self.dialog.set_choice_enabled("operation", value, False)
        self.dialog.changed.connect(self._changed)
        self.dialog.accepted.connect(self.ok)
        self.dialog.applied.connect(self.apply)
        self.dialog.cancelled.connect(self.cancel)
        self._label_params()
        self.dialog.move(16, 16)
        self.dialog.show()
        self.dialog.raise_()
        self._check()
        return True

    def _label_params(self):
        for f in self.kind.FIELDS:
            if f.kind.startswith("value"):
                prop = getattr(self.kind, "PROPS", {}).get(f.key)
                if prop and self.feature is not None:
                    target = self.kind._pad_of(self.feature) if hasattr(self.kind, "_pad_of") else self.feature
                    self.dialog.set_param_name(f.key, model.bound_parameter(target, prop) if target else None)

    def _changed(self, values):
        self._pending = values
        self._timer.start()

    def _preview(self):
        if self._pending is None or self._closed:
            return
        values, self._pending = self._pending, None
        try:
            self.feature = self.kind.update(self.doc, self.feature, values)
            self.doc.recompute()
        except Exception as e:
            self.dialog.set_error(str(e))
            return
        self._check()
        self._label_params()

    def _check(self):
        found = safe.problems(self.doc, self._broken, {o.Name for o in self.doc.Objects})
        self.dialog.set_error("; ".join(found))

    def insert(self, name):
        field = self.dialog.focused_value_field() if self.dialog is not None else None
        if field is not None:
            field.insert(name)
            return True
        return False

    def ok(self):
        if self._pending is not None:
            self._timer.stop()
            self._preview()
        if self.dialog is not None and self.dialog.error_text():
            return
        self._finish(commit=True)

    def apply(self):
        kind = self.kind
        self.ok()
        if self._closed:
            from incad.ui import shell
            QtCore.QTimer.singleShot(0, lambda: shell.start_feature(kind))

    def cancel(self):
        self._timer.stop()
        self._finish(commit=False)

    def _finish(self, commit):
        if self._closed:
            return
        self._closed = True
        try:
            if commit:
                self.doc.commitTransaction()
            else:
                self.doc.abortTransaction()
                self.doc.recompute()
        except Exception as e:
            log.report("warning", "Could not close the %s step cleanly: %s" % (self.kind.TITLE, e))
        safe.set_busy(None)
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self._on_close is not None:
            self._on_close(self)
```
Add to `InCad/incad/features/extrude.py`: `PROPS = {"distance": "Length", "distance2": "Length2", "taper": "TaperAngle"}`
and to `revolve.py`: `PROPS = {"angle": "Angle", "angle2": "Angle2"}` and `def _pad_of(f): return f`.

- [ ] **Step 4: Wire it into the shell**

In `InCad/incad/ui/shell.py`:
1. Import `from incad.ui.feature_session import FeatureSession`; `__init__`: `self.feature_session = None`,
   `self._profile_pick = None`.
2. `_teardown()` start: `self._close_feature_session(cancel=True)` and `self._cancel_profile_pick()`.
3. Add methods:
```python
    # ----- features -----
    def _close_feature_session(self, cancel):
        fs = self.feature_session
        if fs is not None:
            fs.cancel() if cancel else fs.ok()
        self.feature_session = None

    def _session_closed(self, fs):
        if self.feature_session is fs:
            self.feature_session = None
        self.schedule_refresh()

    def _profile_for(self, doc, body):
        import FreeCADGui as Gui
        from incad.core import sketch
        from incad.features.common import closed_profile, unconsumed_closed_sketches
        for sel in Gui.Selection.getSelectionEx(doc.Name):
            if sketch.is_sketch(sel.Object) and closed_profile(sel.Object):
                return sel.Object
        editing = self.sketches.editing()
        if editing is not None and closed_profile(editing):
            self.sketches.finish()
            return editing
        candidates = unconsumed_closed_sketches(body)
        return candidates[0] if len(candidates) == 1 else None

    def start_feature(self, kind):
        from incad.core import document
        doc = self._doc()
        if not document.is_incad_part(doc):
            raise ValueError("Create or open an InCad part first")
        if self.feature_session is not None:
            raise ValueError("Finish the %s dialog first" % self.feature_session.kind.TITLE)
        body = document.primary_body(doc)
        profile = self._profile_for(doc, body)
        if profile is None:
            self._begin_profile_pick(kind)
            return
        self._open_session(kind, doc, body, profile=profile)

    def edit_feature(self, feature):
        from incad import features
        kind = features.kind_for(feature)
        if kind is None:
            raise ValueError("%s cannot be edited yet" % feature.Label)
        if self.feature_session is not None:
            raise ValueError("Finish the %s dialog first" % self.feature_session.kind.TITLE)
        self._open_session(kind, feature.Document, feature.getParentGeoFeatureGroup(), feature=feature)

    def _open_session(self, kind, doc, body, profile=None, feature=None):
        parent = self._mdi().viewport() if self._mdi() is not None else self.mw
        fs = FeatureSession(kind, doc, body, profile=profile, feature=feature, theme=self.theme, parent=parent,
                            on_close=self._session_closed)
        self.feature_session = fs
        if not fs.start():
            self.feature_session = None
        self.schedule_refresh()

    def _begin_profile_pick(self, kind):
        import FreeCADGui as Gui
        self._cancel_profile_pick()
        self._profile_pick = _ProfilePicker(self, kind)
        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self._profile_pick)
        self.status.set_prompt("Select a sketch to %s (Esc cancels)" % kind.TITLE.lower())
        log.report("info", "Select a sketch with a closed profile")

    def _cancel_profile_pick(self):
        import FreeCADGui as Gui
        if self._profile_pick is not None:
            try:
                Gui.Selection.removeObserver(self._profile_pick)
            except Exception:
                pass
            self._profile_pick = None
            self.schedule_refresh()
```
and a module-level helper class above `class Shell`:
```python
class _ProfilePicker:
    """Waits for the user to pick a sketch with a closed profile, then starts the feature."""

    def __init__(self, shell, kind):
        self.shell, self.kind = shell, kind

    def addSelection(self, doc_name, obj_name, sub, pnt):
        import FreeCAD as App
        from incad.core import sketch
        from incad.features.common import closed_profile
        obj = App.getDocument(doc_name).getObject(obj_name)
        if sketch.is_sketch(obj) and closed_profile(obj):
            shell, kind = self.shell, self.kind
            QtCore.QTimer.singleShot(0, lambda: (shell._cancel_profile_pick(), shell.start_feature(kind)))
```
4. Insert target: replace `_on_parameter_clicked` body with
```python
        if self.value_box is not None:
            self.value_box.insert(name)
        elif self.feature_session is not None:
            self.feature_session.insert(name)
```
and in `_click_hook` replace `if self.value_box is None: return False` with
```python
        if self.value_box is None and self.feature_session is None:
            return False
```
and `self.value_box.insert(name)` with
```python
        if self.value_box is not None:
            self.value_box.insert(name)
        elif not self.feature_session.insert(name):
            return False
```
5. Esc during profile pick: in `_refresh()` where `_esc` is enabled, use
`act.setEnabled(self.sketches.picking or self._profile_pick is not None)`, and connect `_esc.triggered` to a new
method `_on_escape` that calls `self.sketches.cancel_pick()` and `self._cancel_profile_pick()`.
6. Module functions:
```python
def start_feature(kind):
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    _shell.start_feature(kind)


def edit_feature(feature):
    if _shell is None or not _shell.active:
        raise ValueError("InCad is not active")
    _shell.edit_feature(feature)
```

- [ ] **Step 5: Run the GUI tests until they pass**

Announce the FreeCAD window. Run: `tests/run_gui.sh tests/gui/test_features.py` → Expected: `12 passed, 0 failed`.

- [ ] **Step 6: Run every suite and commit**

Run: `tests/run_all.sh` → Expected: `ALL SUITES PASSED`.
```bash
git add InCad tests && git commit -m "InCad 1d-1: feature sessions — live preview, OK/Apply/Cancel, edit feature, profile pick"
```

---

### Task 7: Look check and docs

- [ ] **Step 1:** Probe screenshots (not committed): an Extrude dialog over a part in light and dark, with an error
shown; check placement (top-left of the 3D view, not under the ViewCube/strip), readability, segment buttons.
Fix with a test first where possible.
- [ ] **Step 2:** README — add:
```markdown
## Features
- E Extrude, R Revolve (also on the ribbon and the right-click menu). The only finished sketch is picked
  automatically; otherwise select one. The preview updates as you type; OK, Apply + (one more), Cancel/Esc.
- Values accept units, names and formulas (Width/2, d3*2); click a dimension or a parameter to insert its name.
- Every value becomes a named parameter (d0, d1 …) in the Parameters panel. Double-click a feature to edit it.
```
- [ ] **Step 3:** `tests/run_all.sh` → `ALL SUITES PASSED`; commit README.
