"""Generates InCad's SVG icons in light and dark variants into InCad/incad/resources/icons/{light,dark}/.
Run: python3 tools/make_icons.py   (any Python 3; no dependencies)"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "InCad", "incad", "resources", "icons")

# S stroke/main, F fill, A accent (orange), N neutral, D datum/origin (amber), R red (End of Part)
PALETTE = {
    "light": dict(S="#0a64d6", F="#9cc6f3", A="#e67e22", N="#555555", D="#c07a00", R="#b00020"),
    "dark": dict(S="#5aa2ff", F="#2a5d99", A="#f39c4a", N="#cccccc", D="#e0a030", R="#ff6b7f"),
}

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">%s</svg>\n'

BLOCK = ('<path d="M4 11 L16 5 L28 11 L16 17 Z" fill="{F}" stroke="{S}" stroke-width="1.5"/>'
         '<path d="M4 11 V21 L16 27 V17 Z" fill="{S}" fill-opacity=".55" stroke="{S}" stroke-width="1.5"/>'
         '<path d="M28 11 V21 L16 27 V17 Z" fill="{S}" stroke="{S}" stroke-width="1.5"/>')
SUN = ('<circle cx="16" cy="16" r="6" fill="{A}"/><path d="M16 3 V6 M16 26 V29 M3 16 H6 M26 16 H29 '
       'M6.8 6.8 L9 9 M23 23 L25.2 25.2 M6.8 25.2 L9 23 M23 9 L25.2 6.8" stroke="{A}" stroke-width="2.2" '
       'stroke-linecap="round"/>')
MOON = '<path d="M20 4 A12 12 0 1 0 28 20 A9 9 0 0 1 20 4 Z" fill="{S}"/>'

FEATURE = ('<path d="M6 22 L6 12 L16 8 L26 11 L26 21 L14 25 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
           '<path d="M6 12 L14 15 L26 11 M14 15 L14 25" fill="none" stroke="{S}" stroke-width="1.2"/>')

ICONS = {
    "incad": BLOCK + '<ellipse cx="16" cy="11" rx="4" ry="2" fill="{N}"/>',
    "part": BLOCK,
    "new": ('<path d="M8 3 H19 L25 9 V29 H8 Z" fill="none" stroke="{N}" stroke-width="1.6"/>'
            '<path d="M19 3 V9 H25" fill="none" stroke="{N}" stroke-width="1.6"/>'
            '<path d="M16.5 14 V24 M11.5 19 H21.5" stroke="{A}" stroke-width="2.4" stroke-linecap="round"/>'),
    "open": ('<path d="M3 9 H12 L14 11 H27 V26 H3 Z" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
             '<path d="M3 14 H29 L26 26 H3 Z" fill="{S}" fill-opacity=".35" stroke="{S}" stroke-width="1.6"/>'),
    "close": '<path d="M9 9 L23 23 M23 9 L9 23" stroke="{N}" stroke-width="2.6" stroke-linecap="round"/>',
    "save": ('<rect x="5" y="5" width="22" height="22" rx="2" fill="none" stroke="{S}" stroke-width="1.8"/>'
             '<rect x="10" y="5" width="12" height="8" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
             '<rect x="9" y="18" width="14" height="9" fill="{S}" fill-opacity=".3"/>'),
    "undo": ('<path d="M12 8 L5 14 L12 20" fill="none" stroke="{S}" stroke-width="2.4" stroke-linecap="round" '
             'stroke-linejoin="round"/><path d="M5 14 H19 A7 7 0 0 1 19 28 H14" fill="none" stroke="{S}" '
             'stroke-width="2.4" stroke-linecap="round"/>'),
    "redo": ('<path d="M20 8 L27 14 L20 20" fill="none" stroke="{S}" stroke-width="2.4" stroke-linecap="round" '
             'stroke-linejoin="round"/><path d="M27 14 H13 A7 7 0 0 0 13 28 H18" fill="none" stroke="{S}" '
             'stroke-width="2.4" stroke-linecap="round"/>'),
    "freecad": ('<path d="M5 11 H25 M20 6 L25 11 L20 16" fill="none" stroke="{S}" stroke-width="2.4" '
                'stroke-linecap="round" stroke-linejoin="round"/><path d="M27 21 H7 M12 16 L7 21 L12 26" '
                'fill="none" stroke="{A}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'),
    "settings": ('<circle cx="16" cy="16" r="10" fill="none" stroke="{N}" stroke-width="5" stroke-dasharray="4 3.85"/>'
                 '<circle cx="16" cy="16" r="7.5" fill="none" stroke="{N}" stroke-width="2.5"/>'
                 '<circle cx="16" cy="16" r="3" fill="{N}"/>'),
    "zoom_all": ('<rect x="8" y="8" width="16" height="16" fill="none" stroke="{N}" stroke-width="1.5" '
                 'stroke-dasharray="3 2"/><path d="M4 10 V4 H10 M22 4 H28 V10 M28 22 V28 H22 M10 28 H4 V22" '
                 'fill="none" stroke="{S}" stroke-width="2.4"/>'),
    "home_view": ('<path d="M4 16 L16 5 L28 16" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/>'
                  '<path d="M8 14 V27 H24 V14" fill="{F}" stroke="{S}" stroke-width="2"/>'
                  '<rect x="13" y="19" width="6" height="8" fill="{S}"/>'),
    "style_shaded": ('<path d="M5 11 L16 5 L27 11 L16 17 Z" fill="{F}" stroke="{N}" stroke-width="1.4"/>'
                     '<path d="M5 11 V22 L16 28 V17 Z" fill="{S}" fill-opacity=".6" stroke="{N}" stroke-width="1.4"/>'
                     '<path d="M27 11 V22 L16 28 V17 Z" fill="{S}" stroke="{N}" stroke-width="1.4"/>'),
    "style_wireframe": ('<path d="M5 11 L16 5 L27 11 L16 17 Z M5 11 V22 L16 28 V17 M27 11 V22 L16 28" fill="none" '
                        'stroke="{S}" stroke-width="1.6"/><path d="M5 22 L16 16 L27 22 M16 5 V16" fill="none" '
                        'stroke="{N}" stroke-width="1" stroke-dasharray="2 2"/>'),
    "parameters": ('<text x="4" y="23" font-family="Georgia, serif" font-style="italic" font-size="18" '
                   'fill="{S}">f</text><text x="13" y="23" font-family="Helvetica" font-size="13" fill="{A}">(x)</text>'),
    "origin": '<path d="M3 9 H12 L14 11 H29 V26 H3 Z" fill="{D}" fill-opacity=".35" stroke="{D}" stroke-width="1.6"/>',
    "plane": '<path d="M3 21 L14 27 L29 18 L18 12 Z" fill="{D}" fill-opacity=".45" stroke="{D}" stroke-width="1.6"/>',
    "axis": '<path d="M5 27 L27 5" stroke="{D}" stroke-width="2.4" stroke-linecap="round"/>',
    "point": '<circle cx="16" cy="16" r="4.5" fill="{D}"/>',
    "sketch": ('<rect x="5" y="9" width="20" height="16" fill="none" stroke="{S}" stroke-width="1.6"/>'
               '<path d="M5 25 L25 9" stroke="{S}" stroke-width="1.2"/><circle cx="25" cy="9" r="3" fill="{A}"/>'),
    "feature": FEATURE,
    "end_of_part": '<rect x="6" y="6" width="20" height="20" rx="2" fill="{R}"/><rect x="11" y="11" width="10" height="10" fill="#ffffff"/>',
    "solids": '<path d="M3 9 H12 L14 11 H29 V26 H3 Z" fill="{F}" stroke="{S}" stroke-width="1.6"/>',
    "look_at": ('<path d="M4 22 L14 27 L28 19 L18 14 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M16 4 V18" stroke="{A}" stroke-width="2.4" stroke-linecap="round"/>'
                '<path d="M11 13 L16 19 L21 13" fill="none" stroke="{A}" stroke-width="2.4" stroke-linecap="round" '
                'stroke-linejoin="round"/>'),
    "zoom_selection": ('<circle cx="13" cy="13" r="8" fill="none" stroke="{S}" stroke-width="2.4"/>'
                       '<path d="M19 19 L27 27" stroke="{S}" stroke-width="3" stroke-linecap="round"/>'
                       '<rect x="9.5" y="9.5" width="7" height="7" fill="{A}"/>'),
    "edit": ('<path d="M6 26 L8 19 L21 6 L26 11 L13 24 Z" fill="{F}" stroke="{S}" stroke-width="1.6" '
             'stroke-linejoin="round"/><path d="M18 9 L23 14" stroke="{S}" stroke-width="1.6"/>'
             '<path d="M6 26 L8 19 L13 24 Z" fill="{A}"/>'),
    "suppress": FEATURE + '<path d="M5 27 L27 5" stroke="{R}" stroke-width="2.6" stroke-linecap="round"/>',
    "rename": ('<rect x="4" y="10" width="24" height="12" rx="2" fill="none" stroke="{N}" stroke-width="1.6"/>'
               '<path d="M9 16 H17" stroke="{S}" stroke-width="2.2" stroke-linecap="round"/>'
               '<path d="M21 7 V25 M19 7 H23 M19 25 H23" stroke="{A}" stroke-width="1.8"/>'),
    "orbit": ('<ellipse cx="16" cy="16" rx="12" ry="5" fill="none" stroke="{S}" stroke-width="2"/>'
              '<path d="M24 9 L28 12 L23 14" fill="none" stroke="{S}" stroke-width="2" stroke-linejoin="round"/>'
              '<circle cx="16" cy="16" r="3.5" fill="{A}"/>'),
    "pan": ('<path d="M16 4 V28 M4 16 H28" stroke="{S}" stroke-width="2.2"/>'
            '<path d="M12 8 L16 4 L20 8 M12 24 L16 28 L20 24 M8 12 L4 16 L8 20 M24 12 L28 16 L24 20" fill="none" '
            'stroke="{S}" stroke-width="2.2" stroke-linejoin="round"/>'),
}

PER_THEME = {"theme_toggle": {"light": MOON, "dark": SUN}}  # shows what a click switches to

ALL_NAMES = sorted(list(ICONS) + list(PER_THEME))


def render(body, theme):
    return SVG % body.format(**PALETTE[theme])


def main():
    for theme in PALETTE:
        folder = os.path.join(OUT, theme)
        os.makedirs(folder, exist_ok=True)
        bodies = dict(ICONS)
        bodies.update({name: variants[theme] for name, variants in PER_THEME.items()})
        for name, body in bodies.items():
            with open(os.path.join(folder, name + ".svg"), "w") as f:
                f.write(render(body, theme))
    print("wrote %d icons per theme to %s" % (len(ALL_NAMES), OUT))


if __name__ == "__main__":
    main()
