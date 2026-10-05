"""GUI test harness: runs inside a real FreeCAD window started by tests/run_gui.sh and writes a JSON result."""
import json
import os
import time
import traceback

from PySide import QtCore, QtWidgets


def pump(ms=150):
    """Let Qt process events (including deferred deletes) for about `ms` milliseconds."""
    end = time.time() + ms / 1000.0
    while time.time() < end:
        QtWidgets.QApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        time.sleep(0.01)


def _close_modals():
    for _ in range(5):
        w = QtWidgets.QApplication.activeModalWidget()
        if w is None:
            return
        if hasattr(w, "reject"):
            w.reject()
        else:
            w.close()
        pump(200)


def run(tests, delay_ms=2000):
    """Run test functions in order once FreeCAD is up, write results to $INCAD_GUI_OUT, exit FreeCAD."""
    def go():
        results = []
        _close_modals()
        for t in tests:
            try:
                t()
                results.append({"name": t.__name__, "ok": True, "detail": ""})
            except Exception:
                results.append({"name": t.__name__, "ok": False, "detail": traceback.format_exc()})
            pump()
        with open(os.environ["INCAD_GUI_OUT"], "w") as f:
            json.dump(results, f, indent=1)
        os._exit(0)

    QtCore.QTimer.singleShot(delay_ms, go)
