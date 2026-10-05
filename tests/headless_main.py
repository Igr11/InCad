"""Runs tests/headless/test_*.py inside freecadcmd. Started by tests/run_headless.sh."""
import os
import sys
import unittest

repo = os.environ["INCAD_REPO"]
sys.path.insert(0, os.path.join(repo, "InCad"))
sys.path.insert(0, os.path.join(repo, "tests"))
suite = unittest.defaultTestLoader.discover(
    os.path.join(repo, "tests", "headless"),
    pattern=os.environ.get("INCAD_TEST_PATTERN", "test_*.py"),
    top_level_dir=os.path.join(repo, "tests"),
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
