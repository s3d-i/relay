from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research_relay.state import git


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install_skill.py"


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="relay-install-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve() / "project with spaces"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        self.ignore = self.repo / ".gitignore"
        self.target = self.repo / ".agents/skills/research-relay"

    def install(self, *args, expected=0):
        result = subprocess.run([sys.executable, str(INSTALLER), "--repo", str(self.repo), *args],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def is_ignored(self, path):
        result = subprocess.run(["git", "-C", str(self.repo), "check-ignore", "--quiet",
                                 "--no-index", "--", path], capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_install_ignores_only_relay_local_paths(self):
        self.install()
        self.assertEqual(self.target.resolve(), ROOT / "skills/research-relay")
        for path in (".agents/skills/research-relay", ".codex/hooks.json",
                     "artifacts/private/human-inputs/session.md"):
            self.assertTrue(self.is_ignored(path), path)
        for path in (".agents/skills/other/SKILL.md", ".codex/config.toml",
                     "artifacts/result.md", ".gitignore"):
            self.assertFalse(self.is_ignored(path), path)

    def test_preserves_existing_bytes_and_repeat_install_is_idempotent(self):
        original = b"# project rules\r\nbuild/\r\n.agents/skills/research-relay"
        self.ignore.write_bytes(original)
        self.install()
        after = self.ignore.read_bytes()
        self.assertTrue(after.startswith(original + b"\r\n"))
        self.assertEqual(after.count(b".agents/skills/research-relay"), 1)
        self.assertIn(b"/.codex/hooks.json\r\n", after)
        self.install()
        self.assertEqual(self.ignore.read_bytes(), after)

    def test_existing_install_gets_missing_ignore_rules(self):
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(ROOT / "skills/research-relay", target_is_directory=True)
        self.assertIn("Already installed", self.install().stdout)
        self.assertTrue(self.is_ignored(".agents/skills/research-relay"))

    def test_conflicting_skill_does_not_change_gitignore(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text("existing skill")
        self.ignore.write_text("build/\n")
        self.install(expected=2)
        self.assertEqual(self.target.read_text(), "existing skill")
        self.assertEqual(self.ignore.read_text(), "build/\n")

    def test_symlinked_gitignore_is_preserved_before_installing_link(self):
        original = self.repo.parent / "outside-ignore"
        original.write_text("build/\n")
        self.ignore.symlink_to(original)
        self.install(expected=2)
        self.assertEqual(original.read_text(), "build/\n")
        self.assertFalse(self.target.is_symlink())

    def test_uninstall_retains_ignores_and_hook_configuration(self):
        self.install()
        before = self.ignore.read_bytes()
        hooks = self.repo / ".codex/hooks.json"
        hooks.parent.mkdir()
        hooks.write_text("local hooks")
        self.install("--uninstall")
        self.assertFalse(self.target.is_symlink())
        self.assertEqual(self.ignore.read_bytes(), before)
        self.assertEqual(hooks.read_text(), "local hooks")

    def test_already_tracked_local_files_are_reported_and_preserved(self):
        hooks = self.repo / ".codex/hooks.json"
        hooks.parent.mkdir()
        hooks.write_text("tracked hooks")
        git(self.repo, "add", ".codex/hooks.json")
        before = git(self.repo, "ls-files", "--stage")
        self.assertIn("already tracked", self.install().stderr)
        self.assertEqual(git(self.repo, "ls-files", "--stage"), before)
        self.assertEqual(hooks.read_text(), "tracked hooks")
