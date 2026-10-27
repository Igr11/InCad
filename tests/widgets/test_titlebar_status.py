import unittest

from widgets import qtapp
from incad.core.commands import Command, Registry
from incad.ui.statusbar import StatusBar
from incad.ui.titlebar import TitleStrip


class TitleStripTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.reg = Registry()
        for i in ("file.new", "file.save", "edit.undo", "edit.redo", "edit.update", "view.freecad", "view.theme_toggle"):
            self.reg.register(Command(id=i, label=i, icon="incad", handler=lambda i=i: self.ran.append(i)))
        self.made = []

        def factory(parent):
            from incad.qt import QtWidgets
            m = QtWidgets.QMenu(parent)
            m.addAction("Theme")
            self.made.append(m)
            return m

        self.ts = TitleStrip(self.reg, "light", factory)

    def test_buttons_run_commands(self):
        self.ts.button("file.save").click()
        self.ts.button("view.freecad").click()
        self.assertEqual(self.ran, ["file.save", "view.freecad"])
        self.assertIsNone(self.ts.button("file.open"))

    def test_update_sits_right_after_redo(self):
        """Inventor's Update: next to Redo in the quick-access row, recomputes the model and refreshes InCad."""
        order = [self.ts.button(i) for i in ("edit.undo", "edit.redo", "edit.update")]
        self.assertTrue(all(order))
        xs = [b.geometry().x() for b in order]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual(TitleStrip.QUICK.index("edit.update"), TitleStrip.QUICK.index("edit.redo") + 1)
        self.ts.button("edit.update").click()
        self.assertEqual(self.ran[-1], "edit.update")

    def test_freecad_button_has_text(self):
        self.assertEqual(self.ts.button("view.freecad").text(), "FreeCAD")

    def test_shows_the_version(self):
        """The user: the add-on's version shows somewhere in InCad."""
        import incad
        self.assertEqual(self.ts.version_text(), "ProstoCAD %s" % incad.__version__)  # InCad's name since 0.13

    def test_document_name(self):
        self.ts.set_document_name("Bracket")
        self.assertEqual(self.ts.document_name(), "Bracket")

    def test_settings_menu(self):
        m = self.ts.build_settings_menu()
        self.assertEqual([a.text() for a in m.actions()], ["Theme"])

    def test_theme_switch_keeps_buttons(self):
        self.ts.set_theme("dark")
        self.assertFalse(self.ts.button("file.new").icon().isNull())


class StatusBarTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.sb = StatusBar("light")

    def test_initial(self):
        self.assertEqual(self.sb.texts(), {"prompt": "", "message": "", "units": "", "dof": "", "stats": ""})

    def test_fields(self):
        self.sb.set_prompt("Select a plane")
        self.sb.set_units("in")
        self.sb.set_dof(3)
        self.sb.set_stats(2, 5)
        self.assertEqual(self.sb.texts(), {"prompt": "Select a plane", "message": "", "units": "in · deg",
                                           "dof": "DOF: 3", "stats": "2 solids · 5 features"})
        self.sb.set_dof(0)
        self.assertEqual(self.sb.texts()["dof"], "Fully constrained ✓")
        self.sb.set_stats(1, 1)
        self.assertEqual(self.sb.texts()["stats"], "1 solid · 1 feature")
        self.sb.set_dof(None)
        self.sb.set_stats(None, None)
        self.sb.set_units(None)
        self.assertEqual((self.sb.texts()["dof"], self.sb.texts()["stats"], self.sb.texts()["units"]), ("", "", ""))

    def test_message_and_clear(self):
        self.sb.show_message("error", "Fillet failed")
        self.assertEqual(self.sb.texts()["message"], "Fillet failed")
        self.sb.clear_message()
        self.assertEqual(self.sb.texts()["message"], "")

    def test_dof_click(self):
        from PySide6.QtTest import QTest
        from incad.qt import QtCore
        seen = []
        self.sb.dofClicked.connect(lambda: seen.append(1))
        self.sb.set_dof(3)
        self.sb.show()
        QTest.mouseClick(self.sb._dof, QtCore.Qt.LeftButton)
        self.sb.hide()
        self.assertEqual(seen, [1])
