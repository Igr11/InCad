"""Thread families and size tables (mm, degrees). Pure data: no FreeCAD.

Profile model shared by every family: flank angle (included), radial depth of the external tooth (`depth`) and of
the internal tooth (`depth_int`), and the axial crest flats of the external tooth at the major diameter
(`crest_ext`) and of the internal tooth at the minor diameter (`crest_int`). Taper is the half-angle (NPT)."""
import math
from dataclasses import dataclass

IN = 25.4

STANDARDS = [
    ("iso", "ISO metric"), ("iso_fine", "ISO metric fine"), ("unc", "UNC"), ("unf", "UNF"), ("g", "G / BSP"),
    ("npt", "NPT"), ("tr", "Trapezoidal"), ("acme", "ACME"), ("print", "Print-friendly"), ("custom", "Custom"),
]


@dataclass(frozen=True)
class ThreadSpec:
    std: str
    size: str
    major: float
    pitch: float
    angle: float
    depth: float
    depth_int: float
    crest_ext: float
    crest_int: float
    taper: float = 0.0
    crest_drop: float = 0.0  # external crest below the nominal major (radial), e.g. print-friendly


_ISO = [("M1", 0.25), ("M1.2", 0.25), ("M1.4", 0.3), ("M1.6", 0.35), ("M2", 0.4), ("M2.5", 0.45), ("M3", 0.5),
        ("M3.5", 0.6), ("M4", 0.7), ("M5", 0.8), ("M6", 1.0), ("M8", 1.25), ("M10", 1.5), ("M12", 1.75),
        ("M14", 2.0), ("M16", 2.0), ("M18", 2.5), ("M20", 2.5), ("M22", 2.5), ("M24", 3.0), ("M27", 3.0),
        ("M30", 3.5), ("M33", 3.5), ("M36", 4.0), ("M42", 4.5), ("M48", 5.0), ("M56", 5.5), ("M64", 6.0)]
_ISO_FINE = [(3, 0.35), (4, 0.5), (5, 0.5), (6, 0.75), (8, 1.0), (10, 1.0), (10, 1.25), (12, 1.25), (12, 1.5),
             (14, 1.5), (16, 1.5), (18, 1.5), (20, 1.5), (20, 2.0), (22, 1.5), (24, 2.0), (27, 2.0), (30, 2.0),
             (33, 2.0), (36, 3.0), (42, 3.0), (48, 3.0)]
_UN_NUMBERED = {"#0": 0.060, "#1": 0.073, "#2": 0.086, "#3": 0.099, "#4": 0.112, "#5": 0.125, "#6": 0.138,
                "#8": 0.164, "#10": 0.190, "#12": 0.216}
_UNC = [("#1", 64), ("#2", 56), ("#3", 48), ("#4", 40), ("#5", 40), ("#6", 32), ("#8", 32), ("#10", 24),
        ("#12", 24), ("1/4", 20), ("5/16", 18), ("3/8", 16), ("7/16", 14), ("1/2", 13), ("9/16", 12), ("5/8", 11),
        ("3/4", 10), ("7/8", 9), ("1", 8), ("1-1/8", 7), ("1-1/4", 7), ("1-1/2", 6)]
_UNF = [("#0", 80), ("#1", 72), ("#2", 64), ("#3", 56), ("#4", 48), ("#5", 44), ("#6", 40), ("#8", 36), ("#10", 32),
        ("#12", 28), ("1/4", 28), ("5/16", 24), ("3/8", 24), ("7/16", 20), ("1/2", 20), ("9/16", 18), ("5/8", 18),
        ("3/4", 16), ("7/8", 14), ("1", 12), ("1-1/4", 12), ("1-1/2", 12)]
# G / BSP parallel (ISO 228): (size, TPI, major mm)
_G = [("1/16", 28, 7.723), ("1/8", 28, 9.728), ("1/4", 19, 13.157), ("3/8", 19, 16.662), ("1/2", 14, 20.955),
      ("5/8", 14, 22.911), ("3/4", 14, 26.441), ("7/8", 14, 30.201), ("1", 11, 33.249), ("1-1/4", 11, 41.910),
      ("1-1/2", 11, 47.803), ("2", 11, 59.614)]
# NPT: (size, TPI, pipe OD inch)
_NPT = [("1/16", 27, 0.3125), ("1/8", 27, 0.405), ("1/4", 18, 0.540), ("3/8", 18, 0.675), ("1/2", 14, 0.840),
        ("3/4", 14, 1.050), ("1", 11.5, 1.315), ("1-1/4", 11.5, 1.660), ("1-1/2", 11.5, 1.900), ("2", 11.5, 2.375)]
_TR = [(8, 1.5), (10, 2), (12, 3), (14, 3), (16, 4), (18, 4), (20, 4), (22, 5), (24, 5), (26, 5), (28, 5), (30, 6),
       (32, 6), (36, 6), (40, 7)]
_ACME = [("1/4", 16), ("5/16", 14), ("3/8", 12), ("7/16", 12), ("1/2", 10), ("5/8", 8), ("3/4", 6), ("7/8", 6),
         ("1", 5), ("1-1/4", 5), ("1-1/2", 4), ("2", 4)]


def _fraction(text):
    """'1-1/4' -> 1.25, '3/8' -> 0.375, '1' -> 1."""
    whole, _, frac = text.partition("-") if "/" in text.partition("-")[2] else ("", "", text)
    value = float(whole) if whole else 0.0
    if "/" in frac:
        a, b = frac.split("/")
        value += float(a) / float(b)
    elif frac:
        value += float(frac)
    return value


def _un_major(name):
    return (_UN_NUMBERED[name] if name in _UN_NUMBERED else _fraction(name)) * IN


def _fmt(x):
    return ("%g" % x)


def sizes(std):
    if std == "iso":
        return [n for n, _ in _ISO]
    if std == "iso_fine":
        return ["M%sx%s" % (_fmt(d), _fmt(p)) for d, p in _ISO_FINE]
    if std == "unc":
        return ["%s-%d" % (n, t) for n, t in _UNC]
    if std == "unf":
        return ["%s-%d" % (n, t) for n, t in _UNF]
    if std == "g":
        return ["G" + n for n, _, _ in _G]
    if std == "npt":
        return [n for n, _, _ in _NPT]
    if std == "tr":
        return ["Tr%sx%s" % (_fmt(d), _fmt(p)) for d, p in _TR]
    if std == "acme":
        return ["%s-%d" % (n, t) for n, t in _ACME]
    if std == "print":
        return [n for n, p in _ISO if p >= 0.5]
    return []


def _sixty(std, size, major, pitch, taper=0.0):
    return ThreadSpec(std, size, major, pitch, 60.0, 0.61343 * pitch, 0.54127 * pitch, pitch / 8.0, pitch / 4.0,
                      taper)


def spec(std, size, custom=None):
    if std == "iso":
        pitch = dict(_ISO)[size]
        return _sixty(std, size, float(size[1:]), pitch)
    if std == "iso_fine":
        d, p = size[1:].split("x")
        return _sixty(std, size, float(d), float(p))
    if std in ("unc", "unf"):
        name, _, tpi = size.rpartition("-")
        return _sixty(std, size, _un_major(name), IN / float(tpi))
    if std == "g":
        tpi, major = {n: (t, m) for n, t, m in _G}[size[1:]]
        p = IN / tpi
        crest = 0.1667 * p  # Whitworth 55°, rounded crests taken as flats
        return ThreadSpec(std, size, major, p, 55.0, 0.640327 * p, 0.640327 * p, crest, crest)
    if std == "npt":
        tpi, od = {n: (t, o) for n, t, o in _NPT}[size]
        e0 = od - (0.05 * od + 1.1) / tpi  # pitch diameter at the small end (inch)
        p = IN / tpi
        flat = 0.038 * p
        return ThreadSpec(std, size, (e0 + 0.8 / tpi) * IN, p, 60.0, 0.8 * p, 0.8 * p, flat, flat,
                          math.degrees(math.atan(1 / 32.0)))
    if std == "tr":
        d, p = (float(v) for v in size[2:].split("x"))
        ac = 0.15 if p <= 1.5 else 0.25 if p <= 5 else 0.5 if p <= 12 else 1.0
        return ThreadSpec(std, size, d, p, 30.0, 0.5 * p + ac, 0.5 * p + ac, 0.366 * p, 0.366 * p)
    if std == "acme":
        name, _, tpi = size.rpartition("-")
        p = IN / float(tpi)
        h = 0.5 * p + 0.254
        return ThreadSpec(std, size, _fraction(name) * IN, p, 29.0, h, h, 0.3707 * p, 0.3707 * p)
    if std == "print":
        p = dict(_ISO)[size]
        # ISO flank lines (same pitch diameter as ISO, so it fits metal ISO parts), external tooth truncated to
        # P/4 flats at crest and root; the nut is the ISO internal profile
        depth = 0.25 * p / math.tan(math.radians(30))
        return ThreadSpec(std, size, float(size[1:]), p, 60.0, depth, 0.54127 * p, p / 4.0, p / 4.0, 0.0,
                          0.10825 * p)
    if std == "custom":
        c = dict(custom or {})
        major, p, angle, depth = (float(c[k]) for k in ("major", "pitch", "angle", "depth"))
        flat = (p - 2 * depth * math.tan(math.radians(angle / 2))) / 2
        if p <= 0 or depth <= 0 or flat < 0:
            raise ValueError("That depth is too large for this pitch and flank angle")
        return ThreadSpec(std, size or "Custom", major, p, angle, depth, depth, flat, flat)
    raise ValueError("Unknown thread standard %r" % std)


def default_clearance(std, other=0.2):
    """Print clearance on the diameter (mm): print-friendly threads get more; `other` for every other standard."""
    return 0.3 if std == "print" else other


def bore_diameter(s, clearance=0.0):
    """Drill size for an internal thread: the internal minor diameter plus the print clearance."""
    return s.major - 2 * s.depth_int + clearance


def suggest(std, diameter, internal, clearance=0.0):
    """The size whose major diameter (shaft) is nearest to `diameter`; for a hole, the size whose major (a hole the
    bolt's size: Ø3 -> M3) or bore diameter (a tap drill: Ø8.5 -> M10) is nearest. Thread fills or bores the
    hole to the bore diameter, so either works."""
    names = sizes(std)
    if not names:
        return ""
    def miss(name):
        s = spec(std, name)
        if not internal:
            return abs(s.major - diameter)
        return min(abs(s.major - diameter), abs(bore_diameter(s, clearance) - diameter))
    return min(names, key=miss)
