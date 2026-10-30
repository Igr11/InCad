"""⚙ ▸ Check for Updates in the window (incad.core.updates): the question goes to GitHub in a thread of its own (the
window keeps working), the answer comes back on a timer; a newer release can be downloaded at once into Downloads,
with a progress bar and Cancel; then the Mac disk image is opened, a ZIP shown in its folder, with what to do next.
At start: once a day, quietly — only a newer release, not skipped, says anything."""
import datetime
import os
import subprocess
import threading

from incad import host
from incad.core import log, prefs, updates
from incad.qt import QtCore, QtGui, QtWidgets

TITLE = "Check for Updates"
START_DELAY_MS = 20000  # after start: the window is settled, the first file open


class _Ask:
    """updates.latest() in a thread; done() polled from the window's thread."""
    def __init__(self):
        self.info = self.error = None
        self.finished = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.info = updates.latest()
        except Exception as e:  # no network, GitHub's limit: said only when asked by hand
            self.error = e
        self.finished = True


def check(parent, quiet=False, busy=None):
    """Ask, then answer in the window. quiet: the check at start (only a newer release speaks). busy(): True while a
    dialog is open — the answer waits for it."""
    ask = _Ask()
    timer = QtCore.QTimer(parent)

    def poll():
        if not ask.finished or (busy is not None and busy()):
            return
        timer.stop()
        timer.deleteLater()
        answer(parent, ask.info, ask.error, quiet)

    timer.timeout.connect(poll)
    timer.start(300)
    return ask


def answer(parent, info, error, quiet=False, exec_dialog=True):
    """The answer box (returned for tests when exec_dialog is False)."""
    product = updates.product()
    if error is not None or info is None:
        log.logger().info("Update check: %s", error)
        if not quiet:
            QtWidgets.QMessageBox.information(parent, TITLE, "GitHub could not be reached (%s). Try again later, or "
                                              "look at prostocad.com." % (error or "no answer"))
        return None
    current = host.version()
    if not updates.newer(info["version"], current):
        log.logger().info("Update check: %s %s is the newest", product, current)
        if not quiet:
            QtWidgets.QMessageBox.information(parent, TITLE, "You have the newest %s (%s)." % (product, current))
        return None
    if quiet and prefs.update_skipped() == info["version"]:
        return None
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle(TITLE)
    box.setIcon(QtWidgets.QMessageBox.Information)
    box.setText("%s %s is out — you have %s." % (product, info["version"], current))
    box.setInformativeText("Download it now? It goes into your Downloads folder; you install it when you are ready."
                           if info["asset"] else "Its page has the files.")
    get = box.addButton("Download" if info["asset"] else "Open Page", QtWidgets.QMessageBox.AcceptRole)
    news = box.addButton("What's New", QtWidgets.QMessageBox.HelpRole)
    skip = box.addButton("Skip This Version", QtWidgets.QMessageBox.DestructiveRole) if quiet else None
    box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(get)
    box.setObjectName("InCadUpdateBox")
    if not exec_dialog:
        return box
    box.exec()
    pressed = box.clickedButton()
    if pressed is get:
        if info["asset"]:
            fetch(parent, info)
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(info["page"]))
    elif pressed is news:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(info["page"]))
    elif skip is not None and pressed is skip:
        prefs.set_update_skipped(info["version"])
    return box


def fetch(parent, info):
    """Download the release's file for this system, then open it (a disk image) or show it (a ZIP)."""
    name, url, size = info["asset"]
    dest = os.path.join(updates.downloads_folder(), name)
    if not (os.path.isfile(dest) and size and os.path.getsize(dest) == size):
        dlg = QtWidgets.QProgressDialog("Downloading %s…" % name, "Cancel", 0, 100, parent)
        dlg.setWindowTitle(TITLE)
        dlg.setWindowModality(QtCore.Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)

        def progress(done, total):
            total = total or size
            if total:
                dlg.setValue(min(99, int(100 * done / total)))
            QtWidgets.QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            got = updates.download(url, dest, progress)
        except Exception as e:
            dlg.close()
            log.logger().warning("Update download failed: %s", e)
            QtWidgets.QMessageBox.warning(parent, TITLE, "The download failed (%s). Its page: %s" % (e, info["page"]))
            return None
        dlg.close()
        if got is None:
            return None
    log.logger().info("Update downloaded: %s", dest)
    try:
        if name.lower().endswith(".dmg") and host.MAC:
            subprocess.Popen(["open", dest])  # mounted and shown: the app and Applications side by side
        else:
            host.reveal(dest)
    except Exception:
        pass
    QtWidgets.QMessageBox.information(parent, TITLE, "Downloaded into Downloads: %s.\n\n%s"
                                      % (name, updates.install_hint(name)))
    return dest


def at_start(parent, busy=None):
    """Once a day, a while after start: a quiet check (⚙ ▸ Check for Updates at Start)."""
    if not prefs.update_check_at_start() or os.environ.get("INCAD_GUI_OUT") or os.environ.get("INCAD_NO_UPDATE_CHECK"):
        return False  # tests never ask (a box would wait for a click)
    today = datetime.date.today().isoformat()
    if prefs.update_last_check() == today:
        return False
    prefs.set_update_last_check(today)
    QtCore.QTimer.singleShot(START_DELAY_MS, lambda: check(parent, quiet=True, busy=busy))
    return True
