"""⚙ ▸ Report a Bug in the window: the menu has it, it opens the form (this checkout has no sending key: the form
offers GitHub in the browser; nothing is sent from a test)."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import bugreport, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402


def s():
    return shell.instance()


def test_0_activate():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    assert s().active


def test_1_in_the_settings_menu():
    menu = s()._settings_menu(s().mw)
    texts = [a.text() for a in menu.actions()]
    assert "Report a Bug…" in texts, texts
    assert texts.index("Report a Bug…") == texts.index("Show Log File") + 1, texts


def test_2_opens_the_form():
    d = s().report_bug(exec_dialog=False)
    name, version = bugreport.product()
    assert d.windowTitle() == "Report a Bug"
    assert "%s %s" % (name, version) in d.findChildren(type(d.message))[0].text()
    assert d.send_button.text() == ("Send" if bugreport.key() else "Open on GitHub"), d.send_button.text()
    if os.environ.get("INNCAD_SHOT"):
        d.show()
        harness.pump(300)
        d.grab().save(os.environ["INNCAD_SHOT"])
    d.reject()


harness.run([test_0_activate, test_1_in_the_settings_menu, test_2_opens_the_form])
