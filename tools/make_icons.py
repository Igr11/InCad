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
    "update": ('<path d="M24.5 16 A8.5 8.5 0 1 1 22 10" fill="none" stroke="{S}" stroke-width="2.4" '
               'stroke-linecap="round"/><path d="M23 4 V10.5 H16.5" fill="none" stroke="{S}" stroke-width="2.4" '
               'stroke-linecap="round" stroke-linejoin="round"/>'),
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
    "line": ('<path d="M5 26 L27 6" stroke="{S}" stroke-width="2.4" stroke-linecap="round"/>'
             '<circle cx="5" cy="26" r="2.6" fill="{A}"/><circle cx="27" cy="6" r="2.6" fill="{A}"/>'),
    "circle": '<circle cx="16" cy="16" r="10" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="16" r="2.2" fill="{A}"/>',
    "arc": ('<path d="M5 24 A13 13 0 0 1 27 24" fill="none" stroke="{S}" stroke-width="2.4"/>'
            '<circle cx="5" cy="24" r="2.4" fill="{A}"/><circle cx="16" cy="11.5" r="2.4" fill="{A}"/>'
            '<circle cx="27" cy="24" r="2.4" fill="{A}"/>'),
    "rectangle": ('<rect x="5" y="8" width="22" height="16" fill="none" stroke="{S}" stroke-width="2.4"/>'
                  '<circle cx="5" cy="24" r="2.4" fill="{A}"/><circle cx="27" cy="8" r="2.4" fill="{A}"/>'),
    "slot": ('<rect x="4" y="10" width="24" height="12" rx="6" fill="none" stroke="{S}" stroke-width="2.4"/>'
             '<circle cx="10" cy="16" r="1.8" fill="{A}"/><circle cx="22" cy="16" r="1.8" fill="{A}"/>'),
    "polygon": ('<path d="M16 4 L26.4 10 L26.4 22 L16 28 L5.6 22 L5.6 10 Z" fill="none" stroke="{S}" stroke-width="2.4" '
                'stroke-linejoin="round"/><circle cx="16" cy="16" r="2" fill="{A}"/>'),
    "spline": ('<path d="M4 24 C10 4 18 30 28 8" fill="none" stroke="{S}" stroke-width="2.4"/>'
               '<circle cx="4" cy="24" r="2.2" fill="{A}"/><circle cx="16" cy="17" r="2.2" fill="{A}"/>'
               '<circle cx="28" cy="8" r="2.2" fill="{A}"/>'),
    "sk_point": '<path d="M16 8 V24 M8 16 H24" stroke="{N}" stroke-width="1.4"/><circle cx="16" cy="16" r="4" fill="{A}"/>',
    "sk_fillet": ('<path d="M6 6 V18 A8 8 0 0 0 14 26 H26" fill="none" stroke="{S}" stroke-width="2.4"/>'
                  '<path d="M6 6 V26 H26" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "sk_chamfer": ('<path d="M6 6 V18 L14 26 H26" fill="none" stroke="{S}" stroke-width="2.4"/>'
                   '<path d="M6 18 V26 H14" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "trim": ('<path d="M4 16 H14" stroke="{S}" stroke-width="2.4"/><path d="M14 16 H28" stroke="{N}" stroke-width="1.6" '
             'stroke-dasharray="2 2"/><path d="M20 6 V26" stroke="{S}" stroke-width="2.4"/>'
             '<path d="M11 9 L17 15 M17 9 L11 15" stroke="{R}" stroke-width="2" stroke-linecap="round"/>'),
    "extend": ('<path d="M4 16 H14" stroke="{S}" stroke-width="2.4"/><path d="M14 16 H22" stroke="{A}" stroke-width="2.4" '
               'stroke-dasharray="3 2"/><path d="M24 6 V26" stroke="{S}" stroke-width="2.4"/>'),
    "offset": ('<path d="M6 26 V12 Q6 6 12 6 H26" fill="none" stroke="{S}" stroke-width="2.4"/>'
               '<path d="M12 26 V16 Q12 12 16 12 H26" fill="none" stroke="{A}" stroke-width="2" stroke-dasharray="3 2"/>'),
    "project": ('<path d="M4 20 L14 25 L28 18 L18 13 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M16 3 V15" stroke="{A}" stroke-width="2.2"/>'
                '<path d="M12 11 L16 16 L20 11" fill="none" stroke="{A}" stroke-width="2.2" stroke-linejoin="round"/>'),
    "construction": ('<path d="M5 26 L27 6" stroke="{S}" stroke-width="2.4" stroke-dasharray="4 3"/>'
                     '<circle cx="16" cy="16" r="9" fill="none" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 3"/>'),
    "mirror": ('<path d="M16 3 V29" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 2"/>'
               '<path d="M4 9 H12 V23 H4 Z" fill="{F}" stroke="{S}" stroke-width="1.8"/>'
               '<path d="M28 9 H20 V23 H28 Z" fill="none" stroke="{A}" stroke-width="1.8"/>'),
    "rect_pattern": ('<g fill="{F}" stroke="{S}" stroke-width="1.6"><rect x="4" y="4" width="9" height="9"/>'
                     '<rect x="19" y="4" width="9" height="9"/><rect x="4" y="19" width="9" height="9"/>'
                     '<rect x="19" y="19" width="9" height="9"/></g>'),
    "dimension": ('<path d="M5 22 H27" stroke="{S}" stroke-width="1.8"/><path d="M5 16 V28 M27 16 V28" stroke="{S}" '
                  'stroke-width="1.6"/><path d="M9 19 L5 22 L9 25 M23 19 L27 22 L23 25" fill="none" stroke="{S}" '
                  'stroke-width="1.8"/><text x="16" y="15" font-family="Helvetica" font-size="10" text-anchor="middle" '
                  'fill="{A}">40</text>'),
    "coincident": ('<path d="M4 26 L16 16 L28 22" fill="none" stroke="{S}" stroke-width="2.2"/>'
                   '<circle cx="16" cy="16" r="4" fill="{A}"/>'),
    "horizontal": ('<path d="M4 18 H28" stroke="{S}" stroke-width="2.6"/><text x="16" y="13" font-family="Helvetica" '
                   'font-size="10" font-weight="bold" text-anchor="middle" fill="{A}">H</text>'),
    "vertical": ('<path d="M14 4 V28" stroke="{S}" stroke-width="2.6"/><text x="19" y="19" font-family="Helvetica" '
                 'font-size="10" font-weight="bold" fill="{A}">V</text>'),
    "parallel": '<path d="M6 24 L20 6 M13 26 L27 8" stroke="{S}" stroke-width="2.4"/>',
    "perpendicular": ('<path d="M6 26 H26 M16 26 V6" stroke="{S}" stroke-width="2.4"/>'
                      '<path d="M16 20 H22 V26" fill="none" stroke="{A}" stroke-width="1.6"/>'),
    "tangent": '<circle cx="14" cy="18" r="8" fill="none" stroke="{S}" stroke-width="2.2"/><path d="M4 10 H28" stroke="{A}" stroke-width="2.2"/>',
    "equal": '<path d="M7 12 H25 M7 20 H25" stroke="{S}" stroke-width="2.6"/>',
    "symmetric": ('<path d="M16 4 V28" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 2"/>'
                  '<circle cx="7" cy="16" r="3" fill="{A}"/><circle cx="25" cy="16" r="3" fill="{A}"/>'
                  '<path d="M10 16 H13 M19 16 H22" stroke="{S}" stroke-width="1.6"/>'),
    "fix": ('<rect x="8" y="14" width="16" height="13" rx="2" fill="{F}" stroke="{S}" stroke-width="1.8"/>'
            '<path d="M11 14 V10 A5 5 0 0 1 21 10 V14" fill="none" stroke="{S}" stroke-width="2.2"/>'),
    "show_dof": ('<path d="M5 26 L16 10 L27 26" fill="none" stroke="{S}" stroke-width="2"/>'
                 '<circle cx="16" cy="10" r="3.5" fill="{R}"/><path d="M16 4 V1 M21 6 L23 4 M11 6 L9 4" stroke="{R}" '
                 'stroke-width="1.6"/>'),
    "visibility": ('<path d="M3 16 C8 8 24 8 29 16 C24 24 8 24 3 16 Z" fill="none" stroke="{S}" stroke-width="2"/><circle cx="16" cy="16" r="4" fill="{S}"/>'),
    "show_all": ('<path d="M3 16 C8 8 24 8 29 16 C24 24 8 24 3 16 Z" fill="none" stroke="{S}" stroke-width="2"/><circle cx="16" cy="16" r="4" fill="{S}"/>'
                 '<path d="M24 23 V31 M20 27 H28" stroke="{A}" stroke-width="2.2" stroke-linecap="round"/>'),
    "hide_all": ('<path d="M3 16 C8 8 24 8 29 16 C24 24 8 24 3 16 Z" fill="none" stroke="{S}" stroke-width="2"/><circle cx="16" cy="16" r="4" fill="{S}"/>'
                 '<path d="M6 26 L26 6" stroke="{R}" stroke-width="2.2" stroke-linecap="round"/>'),
    "stop": ('<circle cx="16" cy="16" r="11" fill="none" stroke="{N}" stroke-width="2"/>'
             '<path d="M11 11 L21 21 M21 11 L11 21" stroke="{N}" stroke-width="2.4" stroke-linecap="round"/>'),
    "finish": ('<circle cx="16" cy="16" r="12" fill="#2ea043"/><path d="M10 16.5 L14.5 21 L23 11.5" fill="none" '
               'stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'),
    "start_sketch": ('<rect x="4" y="9" width="18" height="15" fill="none" stroke="{S}" stroke-width="1.6"/>'
                     '<path d="M4 24 L22 9" stroke="{S}" stroke-width="1.2"/>'
                     '<path d="M25 4 V12 M21 8 H29" stroke="{A}" stroke-width="2.4" stroke-linecap="round"/>'),
    "slice": ('<path d="M4 21 L14 26 L28 18 L18 13 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<path d="M3 15 H29" stroke="{R}" stroke-width="2" stroke-dasharray="4 2"/>'),
    "extrude": ('<path d="M6 22 L6 12 L16 8 L26 11 L26 21 L14 25 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M6 12 L14 15 L26 11 M14 15 L14 25" fill="none" stroke="{S}" stroke-width="1.2"/>'
                '<path d="M20 9 V2" stroke="{A}" stroke-width="2.2"/><path d="M17 5 L20 1 L23 5" fill="none" '
                'stroke="{A}" stroke-width="2.2" stroke-linejoin="round"/>'),
    "revolve": ('<ellipse cx="16" cy="9" rx="10" ry="3.5" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M6 9 V23 A10 3.5 0 0 0 26 23 V9" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M16 3 V29" stroke="{A}" stroke-width="1.6" stroke-dasharray="3 2"/>'),
}

PER_THEME = {"theme_toggle": {"light": MOON, "dark": SUN}}  # shows what a click switches to



def render(body, theme):
    return SVG % body.format(**PALETTE[theme])


ICONS.update({
    "hole": ('<path d="M5 12 L16 6 L27 12 L27 22 L16 28 L5 22 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
             '<ellipse cx="16" cy="12" rx="5" ry="2.6" fill="{N}"/><path d="M11 12 V19 M21 12 V19" stroke="{N}" '
             'stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "fillet": ('<path d="M5 27 V14 Q5 6 13 6 H27" fill="none" stroke="{S}" stroke-width="2.4"/>'
               '<path d="M5 27 H27 V6" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "chamfer": ('<path d="M5 27 V13 L12 6 H27" fill="none" stroke="{S}" stroke-width="2.4"/>'
                '<path d="M5 27 H27 V6" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "assembly": ('<path d="M3 14 L10 10 L17 14 L17 22 L10 26 L3 22 Z" fill="{F}" stroke="{S}" stroke-width="1.3"/>'
                 '<path d="M15 9 L22 5 L29 9 L29 17 L22 21 L15 17 Z" fill="{F}" stroke="{A}" stroke-width="1.3"/>'),
    "place": ('<path d="M5 13 L13 9 L21 13 L21 23 L13 27 L5 23 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<path d="M25 3 V13 M20 8 L25 13 L30 8" fill="none" stroke="{A}" stroke-width="2.2"/>'),
    "create_component": ('<path d="M5 13 L13 9 L21 13 L21 23 L13 27 L5 23 Z" fill="none" stroke="{S}" '
                         'stroke-width="1.4" stroke-dasharray="3 2"/><path d="M25 3 V13 M20 8 H30" '
                         'stroke="{A}" stroke-width="2.2"/>'),
    "ground": ('<path d="M16 4 V18" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="6" r="3.5" fill="{A}"/>'
               '<path d="M6 22 H26 M9 26 H23 M12 30 H20" stroke="{S}" stroke-width="2"/>'),
    "mate": ('<rect x="5" y="4" width="22" height="9" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
             '<rect x="9" y="19" width="14" height="9" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
             '<path d="M16 13 V19" stroke="{A}" stroke-width="2.2"/>'),
    "flush": ('<rect x="4" y="6" width="11" height="20" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<rect x="17" y="6" width="11" height="14" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<path d="M2 6 H30" stroke="{A}" stroke-width="2" stroke-dasharray="3 2"/>'),
    "angle_c": ('<path d="M5 27 H28 M5 27 L22 8" stroke="{S}" stroke-width="2.4"/>'
                '<path d="M14 27 A9 9 0 0 0 11 20" fill="none" stroke="{A}" stroke-width="2"/>'),
    "parallel_c": ('<path d="M4 21 L17 5 M11 27 L24 11" stroke="{S}" stroke-width="2.4"/>'
                   '<path d="M21 25 L25 20 M25 28 L29 23" stroke="{A}" stroke-width="2"/>'),
    "perpendicular_c": ('<path d="M4 27 H28 M12 27 V4" stroke="{S}" stroke-width="2.4"/>'
                        '<path d="M12 19 H20 V27" fill="none" stroke="{A}" stroke-width="2"/>'),
    "tangent": ('<circle cx="16" cy="14" r="8" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
                '<path d="M3 22 H29" stroke="{A}" stroke-width="2.4"/>'),
    "insert": ('<rect x="10" y="3" width="12" height="15" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
               '<path d="M4 20 H12 V29 H4 Z M20 20 H28 V29 H20 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
               '<path d="M16 1 V31" stroke="{A}" stroke-width="1.6" stroke-dasharray="3 2"/>'),
    "rigid": ('<rect x="4" y="10" width="12" height="12" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<rect x="16" y="10" width="12" height="12" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<path d="M12 16 H20 M16 12 V20" stroke="{A}" stroke-width="2.4"/>'),
    "rotational": ('<circle cx="16" cy="16" r="5" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
                   '<path d="M6 12 A11 11 0 0 1 24 7" fill="none" stroke="{A}" stroke-width="2.2"/>'
                   '<path d="M24 3 V8 H19" fill="none" stroke="{A}" stroke-width="2"/>'),
    "slider": ('<rect x="3" y="13" width="26" height="6" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
               '<rect x="11" y="9" width="10" height="14" fill="{F}" stroke="{A}" stroke-width="1.8"/>'
               '<path d="M4 6 H12 M20 6 H28" stroke="{A}" stroke-width="1.8"/>'),
    "cylindrical": ('<ellipse cx="16" cy="8" rx="8" ry="3" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                    '<path d="M8 8 V24 A8 3 0 0 0 24 24 V8" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                    '<path d="M16 2 V30" stroke="{A}" stroke-width="1.8" stroke-dasharray="3 2"/>'),
    "ball": ('<circle cx="16" cy="12" r="8" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
             '<path d="M8 22 A10 10 0 0 0 24 22" fill="none" stroke="{A}" stroke-width="2.4"/>'
             '<path d="M16 22 V30" stroke="{S}" stroke-width="2.4"/>'),
    "sweep": ('<path d="M5 26 C5 14 14 8 27 8" fill="none" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 2"/>'
              '<path d="M3 24 C3 11 13 5 27 5 L27 11 C16 11 9 16 9 26 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'),
    "loft": ('<ellipse cx="16" cy="25" rx="11" ry="4" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
             '<path d="M5 25 L11 8 M27 25 L21 8" stroke="{S}" stroke-width="1.4"/>'
             '<ellipse cx="16" cy="8" rx="5" ry="2" fill="{F}" stroke="{A}" stroke-width="1.6"/>'),
    "coil": ('<path d="M6 26 C26 24 26 20 6 18 C26 16 26 12 6 10 C26 8 26 4 6 2" fill="none" stroke="{S}" '
             'stroke-width="2.2"/><path d="M16 1 V31" stroke="{A}" stroke-width="1.4" stroke-dasharray="3 2"/>'),
    "draft": ('<path d="M6 27 L10 6 H22 L26 27 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
              '<path d="M10 6 V27 M22 6 V27" stroke="{A}" stroke-width="1.2" stroke-dasharray="2 2"/>'),
    "material": ('<path d="M16 3 C10 12 7 16 7 20 A9 9 0 0 0 25 20 C25 16 22 12 16 3 Z" fill="{F}" stroke="{S}" '
                 'stroke-width="1.6"/><path d="M12 21 A4 4 0 0 0 16 25" fill="none" stroke="{A}" stroke-width="2"/>'),
    "section": ('<path d="M5 12 L16 6 L27 12 L27 22 L16 28 L5 22 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M2 17 L30 15" stroke="{A}" stroke-width="2.4"/>'),
    "delete": ('<path d="M8 9 H24 L22 28 H10 Z" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
               '<path d="M5 9 H27 M13 5 H19" stroke="{S}" stroke-width="2"/><path d="M13 13 L19 23 M19 13 L13 23" '
               'stroke="{A}" stroke-width="2"/>'),
    'constraints_toggle': '<path d="M4 16 C9 8 23 8 28 16 C23 24 9 24 4 16 Z" fill="none" stroke="{S}" stroke-width="2"/><path d="M13 13 L19 13 M13 19 L19 19" stroke="{A}" stroke-width="2.2"/><path d="M6 27 L26 5" stroke="{S}" stroke-width="2"/>',
    'constraints_window': '<rect x="5" y="5" width="22" height="22" rx="3" fill="{F}" stroke="{S}" stroke-width="1.6"/><path d="M9 11 H23 M9 16 H23 M9 21 H18" stroke="{S}" stroke-width="2"/><circle cx="23" cy="21" r="3" fill="{A}"/>',
    'slot_overall': '<rect x="4" y="10" width="24" height="12" rx="6" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="4" cy="16" r="2.2" fill="{A}"/><circle cx="28" cy="16" r="2.2" fill="{A}"/>',
    'slot_center': '<rect x="4" y="10" width="24" height="12" rx="6" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="16" r="2.2" fill="{A}"/><circle cx="22" cy="16" r="1.8" fill="{A}"/>',
    'rect_center': '<rect x="5" y="8" width="22" height="16" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="16" r="2.4" fill="{A}"/><circle cx="27" cy="8" r="2.4" fill="{A}"/>',
    'rect_3pt': '<path d="M4 20 L18 6 L28 16 L14 30 Z" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/><circle cx="4" cy="20" r="2.4" fill="{A}"/><circle cx="18" cy="6" r="2.4" fill="{A}"/><circle cx="28" cy="16" r="2.4" fill="{A}"/>',
    'rect_center_3pt': '<path d="M4 20 L18 6 L28 16 L14 30 Z" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/><circle cx="16" cy="18" r="2.4" fill="{A}"/><circle cx="18" cy="6" r="2.4" fill="{A}"/><circle cx="28" cy="16" r="2.4" fill="{A}"/>',
    'rect_rounded': '<rect x="5" y="8" width="22" height="16" rx="5" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="5" cy="24" r="2.2" fill="{A}"/><circle cx="27" cy="8" r="2.2" fill="{A}"/>',
    'circle_3pt': '<circle cx="16" cy="16" r="10" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="6" cy="16" r="2.4" fill="{A}"/><circle cx="16" cy="6" r="2.4" fill="{A}"/><circle cx="25" cy="21" r="2.4" fill="{A}"/>',
    'ellipse': '<ellipse cx="16" cy="16" rx="12" ry="7" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="16" r="2.2" fill="{A}"/>',
    'ellipse_3pt': '<ellipse cx="16" cy="16" rx="12" ry="7" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="4" cy="16" r="2.2" fill="{A}"/><circle cx="28" cy="16" r="2.2" fill="{A}"/><circle cx="16" cy="9" r="2.2" fill="{A}"/>',
    'arc_center': '<path d="M5 24 A13 13 0 0 1 27 24" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="24" r="2.4" fill="{A}"/><circle cx="5" cy="24" r="2.2" fill="{A}"/><circle cx="27" cy="24" r="2.2" fill="{A}"/>',
    'arc_ellipse': '<path d="M3 20 A13 8 0 0 1 29 20" fill="none" stroke="{S}" stroke-width="2.4"/><circle cx="16" cy="20" r="2.2" fill="{A}"/>',
    'line_single': '<path d="M5 26 L27 6" stroke="{S}" stroke-width="2.4" stroke-linecap="round"/><circle cx="5" cy="26" r="2.6" fill="{A}"/><circle cx="27" cy="6" r="2.6" fill="{A}"/><text x="25" y="29" font-family="Helvetica" font-size="9" font-weight="bold" text-anchor="middle" fill="{A}">1</text>',
    'triangle': '<path d="M16.0 5.0 L25.5 21.5 L6.5 21.5 Z" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/>',
    'square': '<path d="M23.8 8.2 L23.8 23.8 L8.2 23.8 L8.2 8.2 Z" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/>',
    'pentagon': '<path d="M16.0 5.0 L26.5 12.6 L22.5 24.9 L9.5 24.9 L5.5 12.6 Z" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/>',
    'octagon': '<path d="M20.2 5.8 L26.2 11.8 L26.2 20.2 L20.2 26.2 L11.8 26.2 L5.8 20.2 L5.8 11.8 L11.8 5.8 Z" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/>',
    'polygon_n': '<path d="M16.0 5.0 L24.6 9.1 L26.7 18.4 L20.8 25.9 L11.2 25.9 L5.3 18.4 L7.4 9.1 Z" fill="none" stroke="{S}" stroke-width="2.4" stroke-linejoin="round"/><text x="16" y="20" font-family="Helvetica" font-size="10" font-weight="bold" text-anchor="middle" fill="{A}">N</text>',
    'slot_arc_flat': '<path d="M6 22 A12 12 0 0 1 26 22" fill="none" stroke="{S}" stroke-width="8" opacity=".35"/><path d="M6 22 A12 12 0 0 1 26 22" fill="none" stroke="{S}" stroke-width="2"/><path d="M2 22 H10 M22 22 H30" stroke="{A}" stroke-width="2"/>',
    'slot_arc': '<path d="M6 22 A12 12 0 0 1 26 22" fill="none" stroke="{S}" stroke-width="8" stroke-linecap="round" opacity=".35"/><path d="M6 22 A12 12 0 0 1 26 22" fill="none" stroke="{S}" stroke-width="2"/><circle cx="6" cy="22" r="2" fill="{A}"/><circle cx="26" cy="22" r="2" fill="{A}"/>',
    'spline_cv': '<path d="M4 24 L10 6 L22 28 L28 8" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="2 2"/><path d="M4 24 C10 6 22 28 28 8" fill="none" stroke="{S}" stroke-width="2.4"/><rect x="8" y="4" width="4" height="4" fill="{A}"/><rect x="20" y="26" width="4" height="4" fill="{A}"/>',
    'make_assembly': '<rect x="3" y="14" width="11" height="11" fill="{F}" stroke="{S}" stroke-width="1.6"/><rect x="18" y="7" width="11" height="11" fill="{F}" stroke="{S}" stroke-width="1.6"/><path d="M14 19 H18" stroke="{A}" stroke-width="2.2"/>',
    'move_face': '<rect x="5" y="14" width="22" height="12" fill="{F}" stroke="{S}" stroke-width="1.6"/><rect x="5" y="9" width="22" height="5" fill="none" stroke="{A}" stroke-width="1.6" stroke-dasharray="2 1.5"/><path d="M16 3 V10 M12.5 6 L16 2.5 L19.5 6" stroke="{A}" stroke-width="2" fill="none"/>',
    'split': '<rect x="4" y="8" width="24" height="16" fill="{F}" stroke="{S}" stroke-width="1.6"/><path d="M14 4 C18 12 12 20 16 28" stroke="{A}" stroke-width="2.2" fill="none"/>',
    "combine": ('<path d="M4 12 L14 7 L24 12 L24 24 L14 29 L4 24 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<circle cx="21" cy="11" r="7" fill="none" stroke="{A}" stroke-width="2"/>'
                '<circle cx="21" cy="11" r="4.5" fill="{N}" stroke="{A}" stroke-width="1" stroke-dasharray="2 1.5"/>'),
    "thread": ('<rect x="9" y="4" width="14" height="24" rx="1.5" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
               '<path d="M9 8 L23 11 M9 13 L23 16 M9 18 L23 21 M9 23 L23 26" stroke="{A}" stroke-width="2"/>'),
    "shell": ('<path d="M5 10 V26 H27 V10" fill="none" stroke="{S}" stroke-width="3"/>'
              '<path d="M9 10 V22 H23 V10" fill="{F}" stroke="{S}" stroke-width="1"/>'),
    "rect_pattern3d": ('<g fill="{F}" stroke="{S}" stroke-width="1.3"><path d="M3 9 L9 6 L15 9 L9 12 Z"/>'
                       '<path d="M17 9 L23 6 L29 9 L23 12 Z"/><path d="M3 21 L9 18 L15 21 L9 24 Z"/>'
                       '<path d="M17 21 L23 18 L29 21 L23 24 Z"/></g>'),
    "circ_pattern": ('<circle cx="16" cy="16" r="10" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="3 2"/>'
                     '<g fill="{F}" stroke="{S}" stroke-width="1.3"><circle cx="16" cy="6" r="3"/>'
                     '<circle cx="26" cy="16" r="3"/><circle cx="16" cy="26" r="3"/><circle cx="6" cy="16" r="3"/></g>'),
    "path_pattern": ('<path d="M4 24 C10 6 16 30 22 12 S30 8 30 8" fill="none" stroke="{N}" stroke-width="1.2" stroke-dasharray="3 2"/>'
                     '<g fill="{F}" stroke="{S}" stroke-width="1.3"><circle cx="6" cy="20" r="3"/>'
                     '<circle cx="15" cy="19" r="3"/><circle cx="24" cy="10" r="3"/></g>'),
    "mirror3d": ('<path d="M16 3 V29" stroke="{N}" stroke-width="1.4" stroke-dasharray="3 2"/>'
                 '<path d="M4 10 L10 7 L13 9 V22 L7 25 L4 23 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                 '<path d="M28 10 L22 7 L19 9 V22 L25 25 L28 23 Z" fill="none" stroke="{A}" stroke-width="1.4"/>'),
    "work_plane": '<path d="M3 20 L13 26 L29 17 L19 11 Z" fill="{D}" fill-opacity=".45" stroke="{D}" stroke-width="1.6"/><path d="M24 4 V12 M20 8 H28" stroke="{A}" stroke-width="2.2"/>',
    "work_axis": '<path d="M5 27 L23 9" stroke="{D}" stroke-width="2.4" stroke-linecap="round"/><path d="M24 2 V10 M20 6 H28" stroke="{A}" stroke-width="2.2"/>',
    "work_point": '<circle cx="14" cy="18" r="4.5" fill="{D}"/><path d="M24 4 V12 M20 8 H28" stroke="{A}" stroke-width="2.2"/>',
    "measure": ('<path d="M4 22 L22 4 L28 10 L10 28 Z" fill="{F}" stroke="{S}" stroke-width="1.4"/>'
                '<path d="M9 17 L12 20 M12 14 L14 16 M15 11 L18 14 M18 8 L20 10" stroke="{S}" stroke-width="1.4"/>'),
    "mass": ('<path d="M8 12 H24 L28 28 H4 Z" fill="{F}" stroke="{S}" stroke-width="1.6"/>'
             '<circle cx="16" cy="8" r="3.5" fill="none" stroke="{S}" stroke-width="1.8"/>'
             '<text x="16" y="25" font-family="Helvetica" font-size="9" font-weight="bold" text-anchor="middle" '
             'fill="{A}">kg</text>'),
})
ALL_NAMES = sorted(list(ICONS) + list(PER_THEME))


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
