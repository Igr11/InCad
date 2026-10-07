"""Host-side helpers for run_scenario.sh (python3 stdlib only): spot lookup, expectations, memo, keycodes."""
import json
import sys

STATE, MEMO = sys.argv[1], sys.argv[2]
what, args = sys.argv[3], sys.argv[4:]

# macOS virtual keycodes, US layout; "S" prefix = Shift, "C" = Command (tests/real/bin/keys)
KEYS = {"a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12, "w": 13,
        "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25,
        "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "\n": 36, "l": 37,
        "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "\t": 48, " ": 49,
        "`": 50}
SHIFTED = {"+": "=", "*": "8", "(": "9", ")": "0", "_": "-", ":": ";", '"': "'", "<": ",", ">": ".", "?": "/",
           "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "{": "[", "}": "]", "|": "\\",
           "~": "`"}


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def spot(name, s, m):
    name = name.format(m=m)
    for group in ("points", "labels", "ribbon", "tree", "plane_panel"):
        if name in (s.get(group) or {}):
            return s[group][name]
    if name.startswith("label."):
        return (s.get("labels") or {}).get(name[6:])
    if name.startswith("tree."):
        return (s.get("tree") or {}).get(name[5:])
    if name.startswith("ribbon."):
        return (s.get("ribbon") or {}).get(name[7:])
    if name.startswith("menu."):
        return (s.get("menu") or {}).get(name[5:])
    if name.startswith("plane."):
        return (s.get("plane_panel") or {}).get(name[6:])
    if name.startswith("popup.") and s.get("popup"):
        return s["popup"]["buttons"].get(name[6:])
    if name.startswith("dialog.") and s.get("dialog"):
        key = name[7:]
        return s["dialog"].get(key) or s["dialog"].get("buttons", {}).get(key)
    if name.startswith("box.") and s.get("box"):
        return s["box"].get(name[4:])
    if name.startswith("marker.") and s.get("markers"):  # marker.<index> (section by 3 points)
        try:
            return s["markers"][int(name[7:])]
        except (ValueError, IndexError):
            return None
    if name.startswith("area.") and s.get("areas"):  # area.<Name> or area.smallest / area.largest
        key = name[5:]
        if key in s["areas"]:
            return s["areas"][key]
        names = sorted(s["areas"])  # Area1, Area2… are made largest first
        return s["areas"][names[-1] if key == "smallest" else names[0]]
    if name.startswith("section.") and s.get("section"):
        return s["section"].get(name[8:])
    return None


s, m = load(STATE), load(MEMO)
if what == "spot":
    xy = spot(args[0], s, m)
    if not xy:
        sys.exit(1)
    print(xy[0], xy[1])
elif what == "expect":
    try:
        ok = bool(eval(args[0], {"s": s, "m": m}))
    except Exception as e:
        print("  (expect raised: %s)" % e)
        ok = False
    sys.exit(0 if ok else 1)
elif what == "memo":
    key, _, expr = args[0].partition("=")
    try:
        m[key.strip()] = eval(expr, {"s": s, "m": m})
    except Exception as e:
        m[key.strip()] = None
        print("  (memo raised: %s)" % e)
    with open(MEMO, "w") as f:
        json.dump(m, f)
elif what == "fresh":  # wait until FreeCAD's event loop writes the state again (a long compute blocks it)
    import os, time
    for _ in range(300):
        if time.time() - os.path.getmtime(STATE) < 0.4:
            d = load(STATE).get("dialog")
            if not (d and d.get("preview")):  # a scheduled or running preview: FreeCAD's progress bar eats the click
                break
        time.sleep(0.1)
    else:
        print("  (state stale for 30 s: FreeCAD busy?)")
elif what == "error":
    print(s.get("error") or "")
elif what == "brief":
    print({k: s.get(k) for k in ("editing", "dims", "box", "dialog", "menu", "focus", "busy", "tip", "volume",
                                 "front_window", "error")})
elif what == "keycodes":
    out = []
    for ch in args[0]:
        if ch in SHIFTED:
            out.append("S%d" % KEYS[SHIFTED[ch]])
        elif ch.isalpha() and ch.isupper():
            out.append("S%d" % KEYS[ch.lower()])
        elif ch in KEYS:
            out.append(str(KEYS[ch]))
        else:
            sys.exit("no keycode for %r" % ch)
    print(" ".join(out))
