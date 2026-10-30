"""⚙ menu entries of the 0.15 batch in the real window: Rectangle Diagonals (a new rectangle keeps its diagonals when
on), Check for Updates… and Check for Updates at Start."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import prefs  # noqa: E402
from incad.ui import shell  # noqa: E402


def s():
    return shell.instance()


def actions():
    menu = s()._settings_menu(s().mw)
    return {a.text(): a for a in menu.actions()}


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)


def test_1_the_entries_are_there():
    acts = actions()
    for name in ("Rectangle Diagonals", "Check for Updates…", "Check for Updates at Start"):
        assert name in acts, sorted(acts)
    assert not acts["Rectangle Diagonals"].isChecked(), "off by default"
    assert acts["Check for Updates at Start"].isChecked(), "on by default"


def test_2_the_switches_set_the_preferences():
    acts = actions()
    acts["Rectangle Diagonals"].trigger()
    assert prefs.rectangle_diagonals()
    acts["Check for Updates at Start"].trigger()
    assert not prefs.update_check_at_start()
    acts = actions()
    assert acts["Rectangle Diagonals"].isChecked() and not acts["Check for Updates at Start"].isChecked()
    prefs.set_rectangle_diagonals(False)
    prefs.set_update_check_at_start(True)


harness.run([test_0_setup, test_1_the_entries_are_there, test_2_the_switches_set_the_preferences])
