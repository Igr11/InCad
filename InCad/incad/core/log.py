"""InCad logging and user-facing messages. No FreeCAD import: usable from widget tests."""
import logging
import os

_logger = None
_reporter = None


def log_path():
    return os.environ.get("INCAD_LOG") or os.path.expanduser("~/Library/Logs/InCad.log")


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
    log = logger()
    write = {"info": log.info, "warning": log.warning}.get(level, log.error)
    write(message + ("\n" + detail if detail else ""))
    if _reporter is not None:
        try:
            _reporter(level, message)
        except Exception:
            log.exception("reporter failed")


def _reset_for_tests():
    global _logger, _reporter
    if _logger is not None:
        for h in list(_logger.handlers):
            _logger.removeHandler(h)
            h.close()
    _logger = None
    _reporter = None
