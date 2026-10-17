"""The Windows edition of the user manual (and of the presentation slides): the Mac parts (<!--mac-->...<!--/mac-->)
out, the Windows parts (<!--win ... win-->) in, keys and FreeCAD's menus as Windows has them. One source for both
systems; the Mac edition is the file as it is (a browser shows no comment).

    python3 windows.py <source.html> <out.html>      (fails on a Mac word left in the result)
"""
import re
import sys

SUBS = [
    ("<kbd>⌘</kbd>", "<kbd>Ctrl</kbd>"),
    ("<kbd>⌥</kbd>", "<kbd>Alt</kbd>"),
    ("<kbd>⌫</kbd>", "<kbd>Backspace</kbd>"),
    ("<kbd>⇧</kbd>", "<kbd>Shift</kbd>"),
    ("FreeCAD ▸ Settings…", "Edit ▸ Preferences…"),
    ("FreeCAD ▸ About FreeCAD", "Help ▸ About FreeCAD"),
    ("Match macOS", "Match Windows"),
    ("in the Finder", "in the File Explorer"),
    ("в Finder", "в Проводнике"),
    ("macOS on Apple Silicon", "Windows 10 / 11 (x64)"),
    ("macOS на Apple Silicon", "Windows 10 / 11 (x64)"),
]
LEFTOVERS = re.compile(r"⌘|⌥|⌫|Finder|macOS|~/Library|Apple Silicon|FreeCAD ▸ Settings")


def windows(html):
    html = re.sub(r"<!--mac-->.*?<!--/mac-->\n?", "", html, flags=re.S)
    html = re.sub(r"<!--win\s?(.*?)\s?win-->", r"\1", html, flags=re.S)
    for a, b in SUBS:
        html = html.replace(a, b)
    return html


def main(src, out):
    html = windows(open(src, encoding="utf-8").read())
    text = re.sub(r"<[^>]+>", " ", re.sub(r"<(style|script)\b.*?</\1>", "", html, flags=re.S))
    left = sorted({m.group(0) for m in LEFTOVERS.finditer(text)})
    if left:
        sys.exit("%s: Mac words left for Windows: %s" % (src, ", ".join(left)))
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
