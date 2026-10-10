"""Loft hang guard. OpenCascade can hang, never returning, when it lofts a section of one or two edges into one
of many (BRepFill_CompatibleWires::SameNumberByPolarMethod; the user's FreeCAD froze in a Loft preview on
2026-10-10), and it cannot be interrupted from Python. It depends on the exact geometry, so a risky set of
sections is first lofted in a COPY of the document, in a separate freecadcmd process, with a time limit: the
same PartDesign code on the same sketches. A set that does not finish there is refused instead of freezing."""
import os
import subprocess
import tempfile
import time

FEW, MANY = 2, 32        # risky: a section with FEW edges or less beside one with more than MANY
LOFT_SECONDS = 10.0      # for the loft itself, once the copy is loaded
LOAD_SECONDS = 120.0     # for opening the copy
_cache = {}              # key -> "ok" | "fails" | "hangs"

_SCRIPT = """
import os, FreeCAD as App
a = os.environ["INCAD_LOFT_TRIAL"].split("|")
doc = App.openDocument(a[0])
open(a[1], "w").close()  # loaded: the parent's clock for the loft starts now
body = doc.getObject(a[2])
secs = [doc.getObject(n) for n in a[5:]]
f = body.newObject("PartDesign::AdditiveLoft", "InCadLoftTrial")
f.Profile = secs[0]
f.Sections = secs[1:]
f.Ruled = a[3] == "1"
f.Closed = a[4] == "1"
f.recompute()
print("LOFT_FAILED" if "Invalid" in f.State else "LOFT_FINISHED")
"""


def _outer(shape):
    wires = list(shape.Wires)
    return max(wires, key=lambda w: w.BoundBox.DiagonalLength) if wires else None


def edge_count(shape):
    w = _outer(shape)
    return len(w.Edges) if w is not None else 0


def risky(counts):
    counts = [c for c in counts if c > 0]
    return bool(counts) and min(counts) <= FEW and max(counts) > MANY


def _freecadcmd():
    import FreeCAD as App
    path = os.path.join(App.getHomePath(), "bin", "freecadcmd")
    return path if os.path.exists(path) else None


def trial(body, sections, ruled=False, closed=False):
    """'ok', 'fails' or 'hangs': the loft of these sections tried in a copy of the document (cached)."""
    key = (body.Document.Name, body.Name, tuple(s.Name for s in sections),
           tuple(s.Shape.exportBrepToString() for s in sections), bool(ruled), bool(closed))
    if key in _cache:
        return _cache[key]
    exe = _freecadcmd()
    if exe is None:
        return "ok"  # nothing to try it with: never block the user on the guard itself
    result = "ok"
    with tempfile.TemporaryDirectory() as tmp:
        copy, loaded, script = (os.path.join(tmp, n) for n in ("copy.FCStd", "loaded", "trial.py"))
        body.Document.saveCopy(copy)
        with open(script, "w") as f:
            f.write(_SCRIPT)
        env = dict(os.environ, INCAD_LOFT_TRIAL="|".join(
            [copy, loaded, body.Name, "1" if ruled else "0", "1" if closed else "0"] + [s.Name for s in sections]))
        p = subprocess.Popen([exe, "-u", os.path.join(tmp, "user.cfg"), script], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, env=env)  # its own settings, never the user's
        start, started = time.time(), None
        while p.poll() is None:
            now = time.time()
            if started is None and os.path.exists(loaded):
                started = now
            if (started is not None and now - started > LOFT_SECONDS) or now - start > LOAD_SECONDS + LOFT_SECONDS:
                p.kill()
                p.wait()
                result = "hangs" if started is not None else "ok"  # a copy too slow to load proves nothing
                break
            time.sleep(0.05)
        else:
            out = p.stdout.read() if p.stdout else ""
            result = "ok" if "LOFT_FINISHED" in out else "fails"
    _cache[key] = result
    return result


def check(body, sections, ruled=False, closed=False):
    """Raise ValueError (with the way out) when these section sketches would hang the loft."""
    counts = [edge_count(s.Shape) for s in sections]
    if not risky(counts) or trial(body, sections, ruled, closed) != "hangs":
        return
    few = min(((c, s) for c, s in zip(counts, sections) if c > 0), key=lambda cs: cs[0])
    many = max(zip(counts, sections), key=lambda cs: cs[0])
    raise ValueError("Loft can't join %s (%d edge%s) and %s (%d edges): FreeCAD would hang on it. "
                     "Split %s into 3 or more arcs, or draw %s with fewer edges"
                     % (few[1].Label, few[0], "" if few[0] == 1 else "s", many[1].Label, many[0],
                        few[1].Label, many[1].Label))
