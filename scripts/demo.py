"""Run a labelled synthetic lifecycle with a real watcher process and Git repository."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_relay import ProcessTests
import unittest

print("SIMULATION ONLY: fixture token events + direct hook calls; no Desktop integration claim.", flush=True)
suite = unittest.TestSuite([ProcessTests("test_threshold_hook_and_stop_process_loop")])
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
