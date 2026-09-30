import json
from pathlib import Path
import subprocess
import unittest

from base import RepoCase
from research_relay import links, notes
from research_relay.state import RelayError, git


class NotesTests(RepoCase):
    def test_isolated_branch_preserves_code_and_existing_notes(self):
        (self.repo / "code.txt").write_text("uncommitted code")
        initial = git(self.repo, "status", "--porcelain")
        result = notes.init(self.repo)
        path = Path(result["notes"])
        self.assertEqual(git(self.repo, "status", "--porcelain"), initial)
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")
        self.assertEqual(git(path, "branch", "--show-current"), "relay-notes")
        self.assertFalse((path / "code.txt").exists())
        (path / "RESEARCH.md").write_text("Existing understanding")
        self.assertFalse(notes.init(self.repo)["entry_created"])
        self.assertEqual((path / "RESEARCH.md").read_text(), "Existing understanding")

    def test_commit_only_explicit_reviewed_files(self):
        path = Path(notes.init(self.repo)["notes"])
        (path / "other.md").write_text("Someone else's draft")
        result = notes.commit(self.repo, ["RESEARCH.md"], "Record question")
        self.assertFalse(result["pushed"])
        self.assertIn("other.md", result["remaining"])
        self.assertEqual(git(path, "show", "--format=", "--name-only", "HEAD"), "RESEARCH.md")
        self.assertEqual(notes.commit(self.repo, ["RESEARCH.md"], "Again")["status"], "unchanged")

    def test_private_inputs_ignored_in_notes_and_code_worktrees(self):
        exclude = self.runtime.parent / "info/exclude"
        existing = exclude.read_text() + "\n# keep this local rule\nlocal-output/"
        exclude.write_text(existing)
        result = notes.init(self.repo)
        path = Path(result["notes"])
        private = Path(result["private_inputs"]) / "s1.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic private prompt and option answer")
        self.assertTrue(result["private_inputs_ignored"])
        self.assertEqual(result["tracked_private_artifacts"], [])
        relative = str(private.relative_to(path))
        for checkout in (path, self.repo):
            ignored = subprocess.run(["git", "-C", str(checkout), "check-ignore", "--", relative],
                                     capture_output=True, text=True, check=True)
            self.assertEqual(ignored.stdout.strip(), relative)
        self.assertNotIn("Synthetic", json.dumps(notes.inspect(self.repo)))
        notes.init(self.repo)
        self.assertEqual(exclude.read_text(), existing + "\n/artifacts/private/\n")
        notes.commit(self.repo, ["RESEARCH.md"], "Record public summary")
        self.assertEqual(git(path, "ls-tree", "-r", "--name-only", "HEAD"), "RESEARCH.md")

    def test_explicit_private_paths_rejected_even_when_ignores_were_removed(self):
        path = Path(notes.init(self.repo)["notes"])
        private = path / notes.PRIVATE_INPUTS / "s1.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic private input")
        exclude = self.runtime.parent / "info/exclude"
        exclude.write_text(exclude.read_text().replace("/artifacts/private/\n", ""))
        self.assertFalse(notes.inspect(self.repo)["private_inputs_ignored"])
        with self.assertRaisesRegex(RelayError, "must never be committed"):
            notes.commit(self.repo, [str(private.relative_to(path))], "Reject private file")
        self.assertTrue(notes.inspect(self.repo)["private_inputs_ignored"])
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), "")

    def test_forced_private_index_entries_block_init_and_commit_without_reset(self):
        path = Path(notes.init(self.repo)["notes"])
        private = path / notes.PRIVATE_INPUTS / "s1.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic forced private input")
        relative = str(private.relative_to(path))
        git(path, "add", "-f", "--", relative)
        self.assertEqual(notes.inspect(self.repo)["tracked_private_artifacts"], [relative])
        with self.assertRaisesRegex(RelayError, "already tracked or staged"):
            notes.init(self.repo)
        with self.assertRaisesRegex(RelayError, "already tracked or staged"):
            notes.commit(self.repo, ["RESEARCH.md"], "Reject staged private input")
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), relative)
        self.assertEqual(private.read_text(), "Synthetic forced private input")

    def test_unrelated_staged_and_invalid_paths_rejected(self):
        path = Path(notes.init(self.repo)["notes"])
        for name in (".", "../outside.md", ":(glob)*", "/etc/passwd", "missing.md"):
            with self.subTest(name=name), self.assertRaises(RelayError):
                notes.commit(self.repo, [name], "reject")
        (path / "other.md").write_text("staged by somebody")
        git(path, "add", "other.md")
        with self.assertRaisesRegex(RelayError, "Unrelated staged"):
            notes.commit(self.repo, ["RESEARCH.md"], "no")
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), "other.md")


class LinkTests(RepoCase):
    def setUp(self):
        super().setUp()
        self.notes = Path(notes.init(self.repo)["notes"])

    def write(self, name, body):
        path = self.notes / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path

    def test_follow_deeper_and_lateral_connections_with_backlinks(self):
        self.write("RESEARCH.md", "[Current question](questions/comparison.md)")
        self.write("questions/comparison.md", "[Observed conditions](../runs/one/detail.md#conditions)")
        self.write("runs/one/detail.md", "[A challenge](../../counterexamples/alternative.md)")
        self.write("counterexamples/alternative.md", "Weakens [the attribution](../questions/comparison.md#claim).")
        notes.commit(self.repo, ["RESEARCH.md", "questions/comparison.md"], "Record initial understanding")
        view = links.neighborhood(self.notes, "questions/comparison.md")
        self.assertEqual({edge["source"] for edge in view["incoming"]},
                         {"RESEARCH.md", "counterexamples/alternative.md"})  # untracked drafts count
        self.assertEqual((view["outgoing"][0]["target"], view["outgoing"][0]["fragment"]),
                         ("runs/one/detail.md", "conditions"))
        deeper = links.neighborhood(self.notes, "runs/one/detail.md")
        self.assertEqual(deeper["outgoing"][0]["target"], "counterexamples/alternative.md")
        self.assertEqual(git(self.notes, "status", "--porcelain"), "?? counterexamples/\n?? runs/")

    def test_source_lines_references_anchors_and_code_samples(self):
        self.write("results/run (a).md", "# Results")
        self.write("results/条件 分析.md", "# 条件")
        self.write("RESEARCH.md", "\n".join([
            "# Focus",
            '[Earlier result](results/run(a).md#claim "reading context")',
            "[Conditions][setup]",
            "[Code](https://example.invalid/repo/blob/abc/file.py#L20)",
            "[setup]: <results/条件 分析.md#条件>",
            "`[Inline](fake.md)`",
            "```markdown", "[Fenced](fake.md)", "```",
            "<!-- [Comment](fake.md) -->",
            "[Label with `code`](<results/run (a).md>)",
        ]))
        out = links.neighborhood(self.notes)["outgoing"]
        self.assertEqual([edge["line"] for edge in out], [2, 3, 4, 11])
        self.assertEqual((out[0]["target"], out[0]["availability"]), ("results/run(a).md", "missing"))
        self.assertEqual((out[1]["target"], out[1]["fragment"]), ("results/条件 分析.md", "条件"))
        self.assertEqual(out[2]["availability"], "external-unchecked")
        self.assertEqual((out[3]["label"], out[3]["availability"]), ("Label with `code`", "present"))

    def test_private_sources_are_never_read_or_queried(self):
        self.write("artifacts/private/human-inputs/session.md", "[PRIVATE RAW INPUT](../../../RESEARCH.md)")
        git(self.notes, "add", "-f", "artifacts/private/human-inputs/session.md")
        self.write("RESEARCH.md", "[Private, local](artifacts/private/human-inputs/session.md#prompt-1)\n"
                   "[Unavailable private source](artifacts/private/human-inputs/elsewhere.md#answer-1)\n"
                   "[Missing observation](runs/missing.md#result)")
        view = links.neighborhood(self.notes)
        self.assertEqual(view["incoming"], [])
        self.assertNotIn("PRIVATE RAW INPUT", json.dumps(view))
        self.assertEqual([edge["availability"] for edge in view["outgoing"]],
                         ["private-local", "private-unavailable", "missing"])
        with self.assertRaises(RelayError):
            links.neighborhood(self.notes, "artifacts/private/human-inputs/session.md")

    def test_cli_queries_one_note_without_writes(self):
        self.write("topic.md", "[Focus](RESEARCH.md#question)")
        code, value = self.cli("notes", "links", "--repo", self.repo, "--path", "topic.md")
        self.assertEqual((code, value["outgoing"][0]["target"]), (0, "RESEARCH.md"))
        self.assertEqual(self.cli("notes", "links", "--repo", self.repo, "--path", "../x.md")[0], 2)
        self.assertEqual(self.cli("notes", "links", "--repo", self.repo, "--path", "a.md", "--path", "b.md")[0], 2)
        other = self.repo.parent / "without-notes"
        other.mkdir()
        git(other, "init")
        self.assertEqual(self.cli("notes", "links", "--repo", other)[0], 2)
        self.assertFalse((other / ".git/research-relay").exists())


if __name__ == "__main__":
    unittest.main()
