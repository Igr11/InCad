import os
import tempfile
import unittest

from incad.core import log


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.environ.get("INCAD_LOG")
        os.environ["INCAD_LOG"] = os.path.join(self.tmp, "sub", "incad.log")
        log._reset_for_tests()

    def tearDown(self):
        log._reset_for_tests()
        if self.old is None:
            os.environ.pop("INCAD_LOG", None)
        else:
            os.environ["INCAD_LOG"] = self.old

    def test_report_writes_log_file(self):
        log.report("error", "Fillet failed", "Traceback: details")
        with open(log.log_path()) as f:
            text = f.read()
        self.assertIn("ERROR Fillet failed", text)
        self.assertIn("Traceback: details", text)

    def test_reporter_receives_level_and_message(self):
        seen = []
        log.set_reporter(lambda level, msg: seen.append((level, msg)))
        log.report("warning", "Careful")
        self.assertEqual(seen, [("warning", "Careful")])

    def test_broken_reporter_does_not_raise(self):
        def bad(level, msg):
            raise RuntimeError("reporter broke")
        log.set_reporter(bad)
        log.report("info", "still fine")
        with open(log.log_path()) as f:
            self.assertIn("reporter failed", f.read())
