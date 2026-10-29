"""The start page (the user: "every program shows recent files when it opens, and we have room for it — with
previews"): with no file open the empty window holds the recent files as tiles with their pictures; a click opens
the file and the page goes; it comes back when the last file closes."""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell, start_page  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def test_0_a_saved_part():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_start_")
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    util.add_pad(body, util.add_rect_sketch(body, 30, 20, "Base"), 8)
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    path = os.path.join(ST["dir"], "Bracket.FCStd")
    doc.saveAs(path)
    actions._remember_recent(path)
    ST["path"] = path
    harness.pump(300)


def test_1_no_file_open_shows_the_recent_files():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    harness.pump(1200)
    s().refresh()
    harness.pump(500)
    page = s().start_page
    assert page is not None and page.isVisible(), "the start page with no file open"
    paths = [t.path for t in page.tiles]
    assert paths and paths[0] == ST["path"], paths
    assert not page.tiles[0].icon().isNull(), "the file's picture on its tile"
    assert "Bracket" in page.tiles[0].text(), page.tiles[0].text()
    assert App.ParamGet("User parameter:BaseApp/Preferences/RecentFiles").GetInt("RecentFiles", 4) >= start_page.MOST


def test_2_a_click_opens_it_and_the_page_goes():
    s().start_page.tiles[0].click()
    harness.pump(1500)
    doc = App.ActiveDocument
    assert doc is not None and os.path.abspath(doc.FileName) == os.path.abspath(ST["path"]), doc
    s().refresh()
    harness.pump(300)
    assert not s().start_page.isVisible(), "a file is open: the page goes"


def test_3_back_when_the_last_file_closes():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    harness.pump(1200)
    s().refresh()
    harness.pump(300)
    assert s().start_page.isVisible()


def test_9_cleanup():
    shutil.rmtree(ST["dir"], ignore_errors=True)


harness.run([test_0_a_saved_part, test_1_no_file_open_shows_the_recent_files, test_2_a_click_opens_it_and_the_page_goes,
             test_3_back_when_the_last_file_closes, test_9_cleanup])
