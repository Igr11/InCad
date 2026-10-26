"""⚙ ▸ Report a Bug (incad.core.bugreport, incad.ui.bugreport_dialog): the report with the user's name taken out, the
key masked in the build and read back, sending (a stand-in for the web call: nothing leaves this machine), the
browser's link kept short, the build script that writes the key, the dialog."""
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error

from widgets import qtapp
from incad.core import bugreport

HOME = os.path.expanduser("~")
USER = os.path.basename(HOME)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ReportTest(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("incad._report_key", None)

    def test_names_taken_out(self):
        text = "Opened %s/Documents/part.FCStd for %s; %s" % (HOME, USER, os.path.join(HOME, "x"))
        out = bugreport.scrub(text)
        self.assertNotIn(HOME, out)
        if len(USER) >= 3:
            self.assertNotIn(USER, out)
        self.assertIn("~/Documents/part.FCStd", out)

    def test_compose(self):
        log = "INFO Opened %s/a.FCStd\nERROR Split failed\n" % HOME
        title, body = bugreport.compose("Split leaves the pieces touching\nmore", "1. a box", "me@example.com",
                                        True, log_text=log)
        name, version = bugreport.product()
        self.assertEqual(title, "[%s %s] Split leaves the pieces touching" % (name, version))
        for part in ("### What happened", "### Steps", "### Contact", "### System", "### Log", "ERROR Split failed"):
            self.assertIn(part, body)
        self.assertNotIn(HOME, body)
        _, short = bugreport.compose("x", attach_log=False, log_text=log)
        self.assertNotIn("### Log", short)
        with self.assertRaises(ValueError):
            bugreport.compose("  ")

    def test_key_masked_and_read_back(self):
        self.assertIsNone(bugreport.key() if "incad._report_key" not in sys.modules else None)
        plain = "github_pat_ABCdef123"
        stored = bugreport.masked(plain)
        self.assertNotIn("github_pat", stored)
        sys.modules["incad._report_key"] = types.SimpleNamespace(KEY=stored)
        import incad
        incad._report_key = sys.modules["incad._report_key"]
        try:
            self.assertEqual(bugreport.key(), plain)
        finally:
            del incad._report_key

    def test_send(self):
        seen = {}

        def opener(req, timeout=None):
            seen["url"], seen["headers"] = req.full_url, dict(req.header_items())
            seen["data"] = json.loads(req.data.decode("utf-8"))
            return _Response(json.dumps({"html_url": "https://github.com/Igr11/InCad/issues/7"}).encode())
        url = bugreport.send("T", "B", opener=opener, token="tok")
        self.assertEqual(url, "https://github.com/Igr11/InCad/issues/7")
        self.assertEqual(seen["url"], bugreport.API)
        self.assertEqual(seen["data"], {"title": "T", "body": "B"})
        self.assertEqual(seen["headers"]["Authorization"], "Bearer tok")

    def test_send_refused_says_so(self):
        def refused(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Bad credentials", {}, None)

        def offline(req, timeout=None):
            raise urllib.error.URLError("no route")
        with self.assertRaises(ValueError) as ctx:
            bugreport.send("T", "B", opener=refused, token="tok")
        self.assertIn("key", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            bugreport.send("T", "B", opener=offline, token="tok")
        self.assertIn("Internet", str(ctx.exception))
        if bugreport.key() is None:  # a checkout has no key: it cannot send by itself
            with self.assertRaises(ValueError):
                bugreport.send("T", "B", opener=offline)

    def test_browser_link_fits(self):
        log = "\n".join("line %d %s" % (i, "x" * 60) for i in range(400))
        title, body = bugreport.compose("Something", log_text=log)
        url = bugreport.browser_url(title, body)
        self.assertLessEqual(len(url), bugreport.MAX_URL + 200)
        self.assertTrue(url.startswith(bugreport.NEW_ISSUE + "?"))
        self.assertIn("Something", url)

    def test_build_script_writes_the_key(self):
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with tempfile.TemporaryDirectory() as tmp:
            module = os.path.join(tmp, "InCad")
            os.makedirs(os.path.join(module, "incad", "core"))
            for rel in ("incad/__init__.py", "incad/core/__init__.py", "incad/core/bugreport.py"):
                with open(os.path.join(repo, "InCad", rel)) as src, open(os.path.join(module, rel), "w") as dst:
                    dst.write(src.read())
            key_file = os.path.join(tmp, "token")
            env = dict(os.environ, INCAD_REPORT_KEY_FILE=key_file, PYTHONDONTWRITEBYTECODE="1")
            script = os.path.join(repo, "scripts", "write_report_key.py")
            out = subprocess.run([sys.executable, script, module], env=env, capture_output=True, text=True)
            self.assertIn("NOTE", out.stdout)  # no key file: the browser way
            self.assertFalse(os.path.exists(os.path.join(module, "incad", "_report_key.py")))
            with open(key_file, "w") as f:
                f.write("github_pat_XYZ\n")
            out = subprocess.run([sys.executable, script, module], env=env, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            written = open(os.path.join(module, "incad", "_report_key.py")).read()
            self.assertNotIn("github_pat", written)
            ns = {}
            exec(written, ns)
            sys.modules["incad._report_key"] = types.SimpleNamespace(KEY=ns["KEY"])
            import incad
            incad._report_key = sys.modules["incad._report_key"]
            try:
                self.assertEqual(bugreport.key(), "github_pat_XYZ")
            finally:
                del incad._report_key


class DialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.calls = []

    def dialog(self, result, direct=True):
        from incad.ui.bugreport_dialog import BugReportDialog

        def send(*args):
            self.calls.append(args)
            return result
        return BugReportDialog("InCad 0.11.4", send, "light", None, direct)

    def test_says_what_first(self):
        d = self.dialog((True, "Sent", "https://x/1"))
        d.send_button.click()
        self.assertEqual(self.calls, [])
        self.assertIn("what happened", d.message.text().lower())

    def test_sent_shows_the_link_and_closes(self):
        d = self.dialog((True, "Sent, thank you", "https://github.com/Igr11/InCad/issues/9"))
        d.what.setPlainText("It broke")
        d.steps.setPlainText("1. this")
        d.attach.setChecked(False)
        d.send_button.click()
        self.assertEqual(self.calls, [("It broke", "1. this", "", False)])
        self.assertIn("issues/9", d.message.text())
        self.assertEqual(d.send_button.text(), "Close")
        self.assertFalse(d.what.isEnabled())

    def test_refused_keeps_the_text(self):
        d = self.dialog((False, "Could not reach GitHub", None))
        d.what.setPlainText("It broke")
        d.send_button.click()
        self.assertIn("Could not reach", d.message.text())
        self.assertTrue(d.what.isEnabled())
        self.assertEqual(d.send_button.text(), "Send")

    def test_browser_build_says_so(self):
        d = self.dialog((True, "GitHub's page is open", None), direct=False)
        self.assertEqual(d.send_button.text(), "Open on GitHub")


if __name__ == "__main__":
    unittest.main()
