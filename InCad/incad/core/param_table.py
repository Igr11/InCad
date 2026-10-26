"""The Parameters window's table (the ribbon's Parameters button, Inventor's fx Parameters): every parameter of the
document with what uses it, and Delete Unused. Three kinds, as the panel under the browser lists them: sketch
dimensions and feature values (model parameters, named d0, d1…), then the user's own parameters."""
import re

from incad.core import document, model, sketch


def _users(doc, ref_patterns, skip):
    """Labels of the objects whose formulas match one of ref_patterns; `skip` (object, property path) is the
    parameter's own formula; another parameter of the same holder is named by itself (its formula uses it)."""
    patterns = [re.compile(p) for p in ref_patterns]
    out = []
    for obj in doc.Objects:
        for path, expr in getattr(obj, "ExpressionEngine", []) or []:
            if (obj, path.lstrip(".")) == skip:
                continue
            if any(p.search(expr) for p in patterns):
                label = path.lstrip(".") if obj.Name in (document.PARAMS_NAME, model.MODEL_NAME) else obj.Label
                if label.startswith("Constraints."):
                    label = "%s (%s)" % (obj.Label, label[len("Constraints."):])  # a dimension of a sketch
                if label not in out:
                    out.append(label)
    return out


def _bare(holder, name):
    """A name used inside its holder's own formulas ('Width*2' beside Width), or through the holder ('X.Width')."""
    return r"(?:%s\.|(?<![\w.]))%s(?!\w)" % (re.escape(holder), re.escape(name))


def rows(doc):
    """[(kind, name, value, result, used_by)]: kind 'dimension', 'feature' or 'user'; value the formula or the
    value typed; used_by labels (a dimension's first is its sketch)."""
    out = []
    for (name, formula, value), (_, sk, _) in zip(sketch.dimension_parameters(doc), sketch.dimensions(doc)):
        ref = r"(?<![\w.])(?:%s|<<%s>>)\.Constraints\.%s(?!\w)" % (re.escape(sk.Name), re.escape(sk.Label),
                                                                   re.escape(name))
        out.append(("dimension", name, formula or value, value,
                    [sk.Label] + [u for u in _users(doc, [ref], (sk, "Constraints." + name)) if u != sk.Label]))
    holder = model._model_obj(doc)
    for name, formula, value in model.feature_parameters(doc):
        out.append(("feature", name, formula or value, value,
                    _users(doc, [_bare(model.MODEL_NAME, name)], (holder, name))))
    params = document.parameters(doc, create=False)
    for name, formula, value in document.list_parameters(doc):
        out.append(("user", name, formula or value, value,
                    _users(doc, [_bare(document.PARAMS_NAME, name)], (params, name))))
    return out


def unused(doc):
    """Names nothing uses: user parameters and feature values left behind (a sketch dimension is its sketch's)."""
    return [r[1] for r in rows(doc) if r[0] != "dimension" and not r[4]]


def delete_unused(doc):
    """Remove every unused parameter; one freed by another's removal ('B = A*2', B unused, then A) goes too.
    Returns the names removed. Call inside safe.run_safely (one undo step)."""
    removed = []
    while True:
        names = [n for n in unused(doc) if n not in removed]
        if not names:
            return removed
        for name in names:
            if model.is_model_parameter(doc, name):
                model.remove_model_parameter(doc, name)
            else:
                document.remove_parameter(doc, name)
            removed.append(name)
