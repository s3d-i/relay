import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from research_relay.__main__ import main
from research_relay.state import git, runtime_dir


ROOT = Path(__file__).resolve().parents[1]


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="relay-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve() / "code with spaces"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Relay Test")
        git(self.repo, "config", "user.email", "relay-test@example.invalid")
        git(self.repo, "commit", "--allow-empty", "-m", "code baseline")
        self.runtime = runtime_dir(self.repo)

    def cli(self, *args):
        """(exit code, parsed JSON from stdout, or from stderr on failure)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in args])
        text = out.getvalue() or err.getvalue()
        return code, json.loads(text) if text.strip() else None
