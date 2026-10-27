"""InCad logging and user-facing messages. No FreeCAD import: usable from widget tests."""
import logging
import os

from incad import host

_logger = None
_reporter = None


def log_path():
    return os.environ.get("INCAD_LOG") or host.log_path()


def logger():
    global _logger
    if _logger is None:
        _logger = logging.getLogger("InCad")
        _logger.setLevel(logging.INFO)
        path = log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(handler)
        _logger.propagate = False
    return _logger


def set_reporter(fn):
    """fn(level, message) shows a message to the user (status bar). None = log only."""
    global _reporter
    _reporter = fn


def report(level, message, detail=""):
    """level: 'info' | 'warning' | 'error'. Always logged; shown to the user when a reporter is set."""
    message = host.brand(message)
    log = logger()
    write = {"info": log.info, "warning": log.warning}.get(level, log.error)
    write(message + ("\n" + detail if detail else ""))
    if _reporter is not None:
        try:
            _reporter(level, message)
        except Exception:
            log.exception("reporter failed")


def catch_uncaught():
    """Python errors that escape into FreeCAD (a button's slot, a timer) go to FreeCAD's Report view only, which is
    not saved: InCad's own are also written here (a dialog whose buttons all stopped working left no trace)."""
    import sys
    import traceback
    previous = sys.excepthook
    if getattr(previous, "_incad", False):
        return

    def hook(kind, value, tb):
        try:
            text = "".join(traceback.format_exception(kind, value, tb))
            if "incad" in text:
                logger().error("Uncaught error\n%s", text)
        except Exception:
            pass
        previous(kind, value, tb)

    hook._incad = True
    sys.excepthook = hook


def _reset_for_tests():
    global _logger, _reporter
    if _logger is not None:
        for h in list(_logger.handlers):
            _logger.removeHandler(h)
            h.close()
    _logger = None
    _reporter = None
