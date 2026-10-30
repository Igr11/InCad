"""⚙ ▸ Report a Bug (the user: straight into the Issues on my GitHub, without signing in). The report — what happened,
the steps, the product and its version, the system, the end of the log — becomes an issue of REPO through the GitHub
API, sent with a key that can only open issues there. Before anything leaves, the user's home folder and name are
taken out of every line (paths say ~). The key comes with the build (incad/_report_key.py, written by the dist
scripts from a file on the builder's Mac, never in git: GitHub revokes a key it finds in a public repository); a
checkout without it opens GitHub's New Issue page filled in instead (the reporter signs in there)."""
import base64
import json
import os
import platform
import re
import urllib.error
import urllib.parse
import urllib.request

REPO = "Igr11/ProstoCAD"  # renamed from Igr11/InCad (GitHub keeps the old address for web links)
API = "https://api.github.com/repos/%s/issues" % REPO
NEW_ISSUE = "https://github.com/%s/issues/new" % REPO
LOG_LINES = 150
MAX_BODY = 60000          # GitHub takes 65536 characters
MAX_URL = 7000            # a browser's New Issue link: the log is cut to fit
_MASK = b"InCadReport"    # the key is stored masked, so a plain search of the files does not find it


def product():
    """('InnCad Plus', '0.10.4') or ('InCad', '0.11.4'), as the title strip shows them."""
    import incad
    from incad import host
    name = getattr(host, "app_name", lambda: "InCad")()
    version = getattr(host, "version", lambda: incad.__version__)()
    return name, version


def _user_patterns():
    home = os.path.expanduser("~")
    user = os.path.basename(home.rstrip("/\\")) or ""
    pats = [(re.escape(home), "~")]
    if os.sep == "\\":
        pats.append((re.escape(home.replace("\\", "/")), "~"))
    if len(user) >= 3:
        pats.append((r"(?i)(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(user), "<user>"))
    return pats


def scrub(text):
    """The user's home folder and name out of the text: '/Users/igor/x' -> '~/x'; the name alone -> '<user>'."""
    for pattern, repl in _user_patterns():
        text = re.sub(pattern, repl, text)
    return text


def log_tail(lines=LOG_LINES):
    from incad.core import log
    try:
        with open(log.log_path(), encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


def system_lines():
    out = ["- Product: %s %s" % product(), "- System: %s (%s)" % (platform.platform(), platform.machine()),
           "- Python: %s" % platform.python_version()]
    try:
        import FreeCAD as App
        out.append("- FreeCAD: %s" % ".".join(App.Version()[:3]))
    except Exception:
        pass
    try:
        from incad.qt import QtCore
        out.append("- Qt: %s" % QtCore.qVersion())
    except Exception:
        pass
    return out


def compose(what, steps="", contact="", attach_log=True, log_text=None):
    """(title, body) of the issue, names taken out."""
    what, steps, contact = (what or "").strip(), (steps or "").strip(), (contact or "").strip()
    if not what:
        raise ValueError("Say what happened first")
    name, version = product()
    first = what.splitlines()[0][:80]
    title = "[%s %s] %s" % (name, version, first)
    body = ["### What happened", what]
    if steps:
        body += ["", "### Steps", steps]
    if contact:
        body += ["", "### Contact", contact]
    body += ["", "### System"] + system_lines()
    if attach_log:
        tail = log_tail() if log_text is None else log_text
        if tail.strip():
            body += ["", "### Log (the last %d lines)" % LOG_LINES, "```text", tail.rstrip(), "```"]
    body += ["", "_Sent from %s ▸ ⚙ ▸ Report a Bug._" % name]
    text = scrub("\n".join(body))
    if len(text) > MAX_BODY:
        text = text[:MAX_BODY - 40] + "\n```\n(cut to fit)"
    return scrub(title), text


def key():
    """The sending key the build put in, or None (a checkout: the browser way)."""
    try:
        from incad import _report_key
    except ImportError:
        return None
    raw = base64.b64decode(getattr(_report_key, "KEY", "") or "")
    plain = bytes(b ^ _MASK[i % len(_MASK)] for i, b in enumerate(raw)).decode("ascii", "ignore").strip()
    return plain or None


def masked(plain):
    """The text a build writes into _report_key.py for the key `plain`."""
    raw = plain.strip().encode("ascii")
    return base64.b64encode(bytes(b ^ _MASK[i % len(_MASK)] for i, b in enumerate(raw))).decode("ascii")


def send(title, body, opener=None, token=None):
    """Opens the issue; returns its web address. opener: urlopen's stand-in (tests)."""
    token = token or key()
    if not token:
        raise ValueError("This build cannot send reports by itself")
    req = urllib.request.Request(API, data=json.dumps({"title": title, "body": body}).encode("utf-8"), method="POST",
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "InCad-bug-report",
                                          "Content-Type": "application/json"})
    try:
        if opener is None:
            from incad import host
            ctx = host.ssl_context()
            opener = lambda r, timeout: urllib.request.urlopen(r, timeout=timeout, context=ctx)  # noqa: E731
        with opener(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise ValueError("GitHub refused the report (%d): this build's sending key no longer works" % e.code)
        raise ValueError("GitHub refused the report (%d)" % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise ValueError("Could not reach GitHub: check the Internet connection (%s)" % getattr(e, "reason", e))
    url = data.get("html_url")
    if not url:
        raise ValueError("GitHub did not say where the report went")
    return url


def browser_url(title, body):
    """GitHub's New Issue page with the report filled in (the reporter signs in there); the log cut to fit a link."""
    def url(b):
        return NEW_ISSUE + "?" + urllib.parse.urlencode({"title": title, "body": b})
    out = url(body)
    while len(out) > MAX_URL and "```text" in body:
        head, _, rest = body.partition("```text\n")
        log_lines = rest.split("\n")
        if len(log_lines) <= 12:
            body = head + "(the log is too long for a link: ⚙ ▸ Show Log File, then attach it)\n"
            break
        body = head + "```text\n" + "\n".join(log_lines[len(log_lines) // 3:])
        out = url(body)
    return url(body)
