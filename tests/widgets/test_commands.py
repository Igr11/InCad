import unittest

from incad.core import log
from incad.core.commands import ANY, Command, Registry


def cmd(i, **kw):
    kw.setdefault("handler", lambda: i)
    return Command(id=i, label=i.title(), icon="incad", **kw)


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.r = Registry()
        self.messages = []
        log.set_reporter(lambda level, msg: self.messages.append((level, msg)))

    def tearDown(self):
        log.set_reporter(None)

    def test_register_and_get(self):
        c = self.r.register(cmd("file.new"))
        self.assertIs(self.r.get("file.new"), c)
        self.assertTrue(self.r.has("file.new"))
        self.assertEqual(self.r.ids(), ["file.new"])

    def test_duplicate_id(self):
        self.r.register(cmd("a"))
        with self.assertRaises(ValueError):
            self.r.register(cmd("a"))

    def test_shortcut_clash_only_in_overlapping_contexts(self):
        self.r.register(cmd("line", shortcut="L", contexts=frozenset({"sketch"})))
        self.r.register(cmd("loft", shortcut="L", contexts=frozenset({"part"})))
        with self.assertRaises(ValueError):
            self.r.register(cmd("look", shortcut="L", contexts=frozenset({ANY})))

    def test_for_context(self):
        self.r.register(cmd("a"))
        self.r.register(cmd("b", contexts=frozenset({"sketch"})))
        self.r.register(cmd("c", contexts=frozenset({"part"})))
        self.assertEqual([c.id for c in self.r.for_context("sketch")], ["a", "b"])

    def test_run_returns_value(self):
        self.r.register(cmd("a", handler=lambda: 42))
        res = self.r.run("a")
        self.assertTrue(res.ok)
        self.assertEqual(res.value, 42)

    def test_run_never_raises(self):
        self.r.register(cmd("bad", handler=lambda: 1 / 0))
        res = self.r.run("bad")
        self.assertFalse(res.ok)
        self.assertEqual(self.messages[-1][0], "error")
        self.assertFalse(self.r.run("missing").ok)

    def test_before_run_hook_runs_first_and_never_blocks(self):
        from incad.core import commands
        order = []
        self.r.register(cmd("a", handler=lambda: order.append("command")))
        commands.set_before_run_hook(lambda: order.append("hook"))
        try:
            self.assertTrue(self.r.run("a").ok)
            self.assertEqual(order, ["hook", "command"], "an active drag ends before any command")

            def boom():
                raise RuntimeError("boom")
            commands.set_before_run_hook(boom)
            self.assertTrue(self.r.run("a").ok, "a failing hook does not stop the command")
        finally:
            commands.set_before_run_hook(None)
