"""Where the time goes when FreeCAD feels slow (found on Windows). In the log: an InCad call slower than SLOW_MS at
once; and once a minute, when anything was slow, how long InCad's own calls took in all and how long Qt's event loop
stood still (watch_ui), whoever held it: a still loop with little InCad time is FreeCAD or the graphics driver.
No FreeCAD import."""
import contextlib
import functools
import time

from incad.core import log

SLOW_MS = 100          # an InCad call this slow is logged by name
STALL_MS = 250         # the event loop standing still this long counts as a stall
REPORT_S = 60.0        # the summary line, at most this often
_TICK_MS = 100
_totals = {}           # name -> [calls, seconds]
_busy = 0.0            # seconds in outermost timed calls since the last summary
_stalls = [0, 0.0]     # count, seconds
_depth = 0
_since = time.monotonic()
_watch = None


def _done(name, seconds):
    global _busy
    entry = _totals.setdefault(name, [0, 0.0])
    entry[0] += 1
    entry[1] += seconds
    if _depth == 0:
        _busy += seconds
    if seconds * 1000.0 > SLOW_MS:
        log.logger().info("Slow: %s took %.0f ms", name, seconds * 1000.0)


@contextlib.contextmanager
def measure(name):
    global _depth
    start = time.perf_counter()
    _depth += 1
    try:
        yield
    finally:
        _depth -= 1
        _done(name, time.perf_counter() - start)


def timed(name):
    """Decorator: the call is measured under this name (an exception still counts)."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            with measure(name):
                return fn(*args, **kwargs)
        return inner
    return wrap


def summary(now=None):
    """The minute's line (or None when nothing was slow), and a fresh minute."""
    global _busy, _since, _totals, _stalls
    now = time.monotonic() if now is None else now
    span = now - _since
    line = None
    if _busy > 0.5 or _stalls[0]:
        top = sorted(_totals.items(), key=lambda kv: -kv[1][1])[:6]
        line = "Time in the last %.0f s: InCad's own calls %.1f s; event loop stalled %d times, %.1f s; top: %s" % (
            span, _busy, _stalls[0], _stalls[1],
            ", ".join("%s %.2f s/%d" % (name, secs, calls) for name, (calls, secs) in top) or "-")
    _busy, _since, _totals, _stalls = 0.0, now, {}, [0, 0.0]
    return line


def _tick():
    global _last
    now = time.monotonic()
    late = now - _last - _TICK_MS / 1000.0
    _last = now
    if late * 1000.0 > STALL_MS:
        _stalls[0] += 1
        _stalls[1] += late
        if late > 2.0:
            log.logger().info("Event loop stood still %.1f s", late)
    if now - _since >= REPORT_S:
        line = summary(now)
        if line:
            log.logger().info(line)


def watch_ui():
    """Start the stall watch (once): a timer that notices when it fires late."""
    global _watch, _last
    if _watch is not None:
        return
    from incad.qt import QtCore
    _last = time.monotonic()
    _watch = QtCore.QTimer()
    _watch.setInterval(_TICK_MS)
    _watch.timeout.connect(lambda: _safe_tick())
    _watch.start()


def stop():
    """Before FreeCAD quits: the timer must not outlive Python."""
    global _watch
    if _watch is not None:
        _watch.stop()
        try:
            import shiboken6
            shiboken6.delete(_watch)  # now: deferred deletes never run once FreeCAD is quitting
        except Exception:
            pass
        _watch = None


def _safe_tick():
    try:
        _tick()
    except Exception:
        pass
