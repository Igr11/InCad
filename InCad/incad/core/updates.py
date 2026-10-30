"""⚙ ▸ Check for Updates (the user: "an option that finds a newer build and downloads it from the site by itself").
The newest release is asked from GitHub (ProstoCAD's downloads: Igr11/ProstoCAD-releases; the FreeCAD add-on's:
Igr11/ProstoCAD), compared with this build's version, and the file for this system is downloaded into Downloads.
Installing stays the user's step (a running program can't replace itself): the Mac disk image is opened, the Windows
or add-on ZIP shown in its folder. At start it looks once a day, quietly; nothing leaves the computer but the
request for the release list. No FreeCAD import: usable from widget tests."""
import json
import os
import re
import urllib.request

from incad import host

PLUS_REPO = "Igr11/ProstoCAD-releases"
ADDON_REPO = "Igr11/ProstoCAD"
TIMEOUT = 10  # seconds


def standalone():
    return bool(getattr(host, "standalone", lambda: False)())


def repo():
    return PLUS_REPO if standalone() else ADDON_REPO


def product():
    return "ProstoCAD" if standalone() else "ProstoCAD for FreeCAD"


def parts(version):
    """'v0.14.0' -> (0, 14, 0); anything after the numbers (a draft's '-rc1') is left out."""
    nums = re.findall(r"\d+", (version or "").split("-")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def newer(latest, current):
    a, b = parts(latest), parts(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def asset_for(assets, system=None, plus=None):
    """The release file for this system: (name, url, size) or None. ProstoCAD: the .dmg (Mac) or windows-x64.zip;
    the add-on: its macOS-arm64.zip or Windows-x64.zip."""
    system = system or ("windows" if host.WINDOWS else "mac")
    plus = standalone() if plus is None else plus
    if plus:
        want = re.compile(r"^(?!.*FreeCAD).*macos-arm64\.dmg$" if system == "mac"
                          else r"^(?!.*FreeCAD).*windows-x64\.zip$", re.I)
    else:
        want = re.compile(r"FreeCAD.*macos-arm64\.zip$" if system == "mac" else r"FreeCAD.*windows-x64\.zip$", re.I)
    for a in assets or ():
        name = a.get("name") or ""
        if want.search(name):
            return name, a.get("browser_download_url"), int(a.get("size") or 0)
    return None


def latest(timeout=TIMEOUT):
    """{'version', 'page', 'asset': (name, url, size) or None, 'notes'} of the newest published release."""
    req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % repo(),
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "ProstoCAD"})
    with urllib.request.urlopen(req, timeout=timeout, context=host.ssl_context()) as r:
        data = json.loads(r.read().decode("utf-8"))
    return {"version": (data.get("tag_name") or "").lstrip("v"), "page": data.get("html_url") or "",
            "asset": asset_for(data.get("assets")), "notes": data.get("body") or ""}


def downloads_folder():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def download(url, dest, progress=None, chunk=1 << 18):
    """The file at url into dest (a .part file renamed at the end); progress(done, total) after every chunk, a false
    answer stops it (Cancel). Returns dest, or None when stopped."""
    req = urllib.request.Request(url, headers={"User-Agent": "ProstoCAD"})
    part = dest + ".part"
    stopped = False
    with urllib.request.urlopen(req, timeout=TIMEOUT * 3, context=host.ssl_context()) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = r.read(chunk)
            if not block:
                break
            f.write(block)
            done += len(block)
            if progress is not None and progress(done, total) is False:
                stopped = True
                break
    if stopped or (total and done < total):
        try:
            os.remove(part)
        except OSError:
            pass
        return None
    os.replace(part, dest)
    return dest


def install_hint(name):
    """What the user does with the downloaded file."""
    if name.lower().endswith(".dmg"):
        return ("The disk image is open. Quit %s, then drag the new ProstoCAD onto Applications (replace the old "
                "one)." % host.app_name())
    if standalone():
        return ("Quit %s, unzip the new one to a short path with Latin letters only and run ProstoCAD.exe from "
                "it." % host.app_name())
    return "Quit FreeCAD and install it as before: README.txt in the ZIP says how."
