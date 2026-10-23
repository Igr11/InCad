"""File tabs (the user: "with many parts, are all tabs reachable?"): with 18 files open the tab bar shows scroll
arrows, the current file's tab is on screen, and each tab's tooltip is its full name (Qt on the Mac neither scrolled
nor shortened them: 5 of 18 were reachable)."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import prefs  # noqa: E402
from incad.qt import QtWidgets  # noqa: E402
from incad.ui import shell  # noqa: E402


def bar():
    return Gui.getMainWindow().findChild(QtWidgets.QMdiArea).findChildren(QtWidgets.QTabBar)[0]


def test_0_many_files():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    for i in range(18):
        App.newDocument("Part_with_a_long_name_%02d" % i)
    shell.instance().schedule_refresh()
    harness.pump(1500)


def test_1_arrows_and_the_current_tab_on_screen():
    b = bar()
    assert b.count() >= 18, b.count()
    assert b.usesScrollButtons(), "no scroll arrows"
    assert [w for w in b.findChildren(QtWidgets.QToolButton) if w.isVisible()], "the arrows do not show"
    cur = b.currentIndex()
    assert b.tabRect(cur).intersects(b.rect()), "the current file's tab is off the bar"
    assert all(b.tabToolTip(i) == b.tabText(i) for i in range(b.count())), "a tab without its full name"


def test_9_cleanup():
    for n in list(App.listDocuments()):
        App.closeDocument(n)
    harness.pump(300)


harness.run([test_0_many_files, test_1_arrows_and_the_current_tab_on_screen, test_9_cleanup])
