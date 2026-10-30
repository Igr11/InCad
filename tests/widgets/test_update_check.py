"""⚙ ▸ Check for Updates (incad.core.updates, incad.ui.update_check) without the network: versions compared, the file
for each system picked from a release's assets, the answer box for a newer release, nothing said about an older or
skipped one, and a download with Cancel."""
import os
import tempfile
import unittest
from unittest import mock

from incad.core import prefs, updates
from incad.qt import QtWidgets
from incad.ui import update_check

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

ASSETS = [{"name": "ProstoCAD-0.15.0-macos-arm64.dmg", "browser_download_url": "https://x/dmg", "size": 10},
          {"name": "ProstoCAD-0.15.0-windows-x64.zip", "browser_download_url": "https://x/zip", "size": 11},
          {"name": "ProstoCAD-FreeCAD-0.15.0-2026-10-30-abc-macOS-arm64.zip", "browser_download_url": "https://x/am",
           "size": 12},
          {"name": "ProstoCAD-FreeCAD-0.15.0-2026-10-30-abc-Windows-x64.zip", "browser_download_url": "https://x/aw",
           "size": 13},
          {"name": "SHA256SUMS-0.15.0.txt", "browser_download_url": "https://x/s", "size": 1}]


class UpdatesTest(unittest.TestCase):
    def setUp(self):
        prefs.use_memory_backend()

    def test_versions(self):
        self.assertTrue(updates.newer("0.15.0", "0.14.0"))
        self.assertTrue(updates.newer("v0.14.1", "0.14.0"))
        self.assertTrue(updates.newer("0.14.0.1", "0.14.0"))
        self.assertFalse(updates.newer("0.14.0", "0.14.0"))
        self.assertFalse(updates.newer("0.13.9", "0.14.0"))
        self.assertTrue(updates.newer("0.10.0", "0.9.9"), "numbers, not text")

    def test_the_file_for_each_system(self):
        self.assertEqual(updates.asset_for(ASSETS, "mac", True)[0], "ProstoCAD-0.15.0-macos-arm64.dmg")
        self.assertEqual(updates.asset_for(ASSETS, "windows", True)[0], "ProstoCAD-0.15.0-windows-x64.zip")
        self.assertIn("macOS-arm64.zip", updates.asset_for(ASSETS, "mac", False)[0])
        self.assertIn("Windows-x64.zip", updates.asset_for(ASSETS, "windows", False)[0])
        self.assertIsNone(updates.asset_for(ASSETS[-1:], "mac", True))

    def info(self, version):
        return {"version": version, "page": "https://github.com/x", "asset": ("f.zip", "https://x/f", 3), "notes": ""}

    def test_a_newer_release_offers_the_download(self):
        with mock.patch("incad.host.version", return_value="0.14.0"):
            box = update_check.answer(None, self.info("0.15.0"), None, quiet=True, exec_dialog=False)
        self.assertIsNotNone(box)
        self.assertIn("0.15.0 is out", box.text())
        labels = [b.text() for b in box.buttons()]
        for want in ("Download", "What's New", "Skip This Version", "Later"):
            self.assertIn(want, labels)

    def test_nothing_said_at_start_about_the_same_or_a_skipped_one(self):
        with mock.patch("incad.host.version", return_value="0.15.0"):
            self.assertIsNone(update_check.answer(None, self.info("0.15.0"), None, quiet=True, exec_dialog=False))
        prefs.set_update_skipped("0.16.0")
        with mock.patch("incad.host.version", return_value="0.15.0"):
            self.assertIsNone(update_check.answer(None, self.info("0.16.0"), None, quiet=True, exec_dialog=False))
        self.assertIsNone(update_check.answer(None, None, OSError("offline"), quiet=True, exec_dialog=False))

    def test_once_a_day_and_never_in_tests(self):
        os.environ.pop("INCAD_NO_UPDATE_CHECK", None)
        with mock.patch.dict(os.environ, {"INCAD_GUI_OUT": "x"}):
            self.assertFalse(update_check.at_start(None))
        prefs.set_update_check_at_start(False)
        self.assertFalse(update_check.at_start(None))

    def test_download_and_cancel(self):
        body = b"x" * 1000

        class Resp:
            headers = {"Content-Length": str(len(body))}

            def __init__(self):
                self.pos = 0

            def read(self, n):
                chunk = body[self.pos:self.pos + n]
                self.pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        d = tempfile.mkdtemp()
        dest = os.path.join(d, "f.zip")
        with mock.patch("urllib.request.urlopen", return_value=Resp()):
            self.assertEqual(updates.download("https://x/f", dest, chunk=100), dest)
        self.assertEqual(os.path.getsize(dest), len(body))
        dest2 = os.path.join(d, "g.zip")
        with mock.patch("urllib.request.urlopen", return_value=Resp()):
            self.assertIsNone(updates.download("https://x/g", dest2, progress=lambda done, total: done < 300, chunk=100))
        self.assertFalse(os.path.exists(dest2) or os.path.exists(dest2 + ".part"))


if __name__ == "__main__":
    unittest.main()
