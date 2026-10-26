import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from base import RepoCase
from research_relay import hooks, notes, policy
from research_relay.backends import claude
from research_relay.state import RelayError, git, runtime_dir
from test_hooks import claude_lines


class AttachCase(RepoCase):
    """self.repo is a code project; self.home a separate repository that keeps notes."""

    def setUp(self):
        super().setUp()
        self.home = self.make_repo("notes home", "Home Author")
        git(self.home, "commit", "--allow-empty", "-m", "home baseline")

    def make_repo(self, name, user="Relay Test"):
        # Local identity: a global user.name must not decide test branch names.
        path = self.repo.parent / name
        path.mkdir()
        git(path, "init", "-b", "main")
        git(path, "config", "user.name", user)
        git(path, "config", "user.email", "relay-test@example.invalid")
        return path

    def heads(self, repo):
        return git(repo, "for-each-ref", "--format=%(refname)", "refs/heads").splitlines()

    def empty_commit(self, repo, message):
        return git(repo, "commit-tree", git(repo, "mktree", input=""), "-m", message)


class AttachTests(AttachCase):
    def test_notes_of_an_attached_project_live_in_the_home(self):
        result = notes.attach(self.repo, self.home)
        self.assertEqual((result["home"], result["branch"]), (str(self.home), "Home-Author/relay-notes"))
        pointer = json.loads((self.runtime / notes.POINTER).read_text())
        self.assertEqual(pointer["home"], "../../notes home")  # relative to the project's git common dir
        made = notes.init(self.repo)
        path = Path(made["notes"])
        self.assertEqual(path, runtime_dir(self.home) / "notes")
        self.assertEqual((made["home"], made["attached"], made["branch"]),
                         (str(self.home), True, "Home-Author/relay-notes"))
        self.assertTrue(made["private_inputs_ignored"])
        # Nothing of the notes lands in the code repository.
        self.assertEqual(self.heads(self.repo), ["refs/heads/main"])
        self.assertFalse((self.runtime / "notes").exists())
        self.assertIn("/artifacts/private/", (runtime_dir(self.home).parent / "info/exclude").read_text())
        self.assertNotIn("/artifacts/private/", (self.runtime.parent / "info/exclude").read_text())
        (path / "RESEARCH.md").write_text("[Topic](topic.md)")
        (path / "topic.md").write_text("Back to [the entry](RESEARCH.md)")
        done = notes.commit(self.repo, ["RESEARCH.md", "topic.md"], "Record the entry")
        self.assertEqual(git(self.home, "log", "-1", "--format=%s", "Home-Author/relay-notes"), "Record the entry")
        self.assertEqual(done["notes"], str(path))
        code, value = self.cli("notes", "links", "--repo", self.repo, "--path", "topic.md")
        self.assertEqual((code, value["outgoing"][0]["target"]), (0, "RESEARCH.md"))
        code, value = self.cli("notes", "status", "--repo", self.repo)
        self.assertEqual((code, value["notes"], value["upstream"]), (0, str(path), None))
        # The home itself sees the same notes as its own.
        self.assertEqual(notes.inspect(self.home)["notes"], str(path))
        self.assertFalse(notes.inspect(self.home)["attached"])

    def test_an_explicit_branch_beside_the_homes_own_notes(self):
        own = Path(notes.init(self.home)["notes"])
        branch = "Home-Author/model/relay-notes"
        notes.attach(self.repo, self.home, branch)
        # Other notebooks in the same home are not candidates for this one.
        made = notes.init(self.repo)
        path = Path(made["notes"])
        self.assertEqual(path, runtime_dir(self.home) / "branches" / branch)
        self.assertEqual(made["branch"], branch)
        self.assertEqual(notes.find(self.home), own)  # the home's discovery still finds its own notes
        self.assertEqual(notes.locate(self.repo), path)
        notes.commit(self.repo, ["RESEARCH.md"], "Model notes")
        self.assertEqual(git(self.home, "log", "-1", "--format=%s", branch), "Model notes")
        self.assertNotEqual(git(own, "rev-parse", "HEAD"), git(path, "rev-parse", "HEAD"))
        git(path, "switch", "-c", "Home-Author/other/relay-notes")
        (path / "RESEARCH.md").write_text("Meant for the model notebook")
        with self.assertRaises(RelayError):
            notes.commit(self.repo, ["RESEARCH.md"], "Wrong notebook")
        self.assertEqual(git(self.home, "log", "-1", "--format=%s", "Home-Author/other/relay-notes"), "Model notes")

    def test_several_home_notebooks_and_another_author_name_still_find_the_conventional_one(self):
        own = Path(notes.init(self.home)["notes"])
        notes.attach(self.repo, self.home, "x/relay-notes")
        notes.init(self.repo)
        git(self.home, "config", "user.name", "Someone Else")
        self.assertEqual(notes.find(self.home), own)

    def test_a_remote_copy_of_the_chosen_branch_needs_a_decision(self):
        branch = "Home-Author/model/relay-notes"
        theirs = self.empty_commit(self.home, "Model notes from the other machine")
        git(self.home, "update-ref", "refs/remotes/origin/" + branch, theirs)
        notes.attach(self.repo, self.home, branch)
        self.assertEqual([c["ref"] for c in notes.inspect(self.repo)["candidates"]], ["origin/" + branch])
        with self.assertRaisesRegex(RelayError, "origin/Home-Author/model/relay-notes.*--from"):
            notes.init(self.repo)
        made = notes.init(self.repo, "origin/" + branch)
        self.assertEqual(git(made["notes"], "rev-parse", "HEAD"), theirs)

    def test_attach_refuses_and_changes_nothing(self):
        cases = [((self.repo, None, None), "--to another repository"),
                 ((self.repo, self.home, "main"), "must end in relay-notes"),
                 ((self.repo, self.home, "bad..name/relay-notes"), "Invalid branch name"),
                 ((self.repo, self.repo.parent, None), "not a git repository")]
        for args, message in cases:
            with self.subTest(args=args), self.assertRaisesRegex(RelayError, message):
                notes.attach(*args)
        third = self.make_repo("third")
        notes.attach(third, self.home)
        with self.assertRaisesRegex(RelayError, "keeps its notes in another repository"):
            notes.attach(self.repo, third)
        self.assertFalse((self.runtime / notes.POINTER).exists())

    def test_attach_waits_until_the_projects_own_notes_are_in_the_home(self):
        own = Path(notes.init(self.repo)["notes"])
        notes.commit(self.repo, ["RESEARCH.md"], "Project notes")
        private = own / notes.PRIVATE_INPUTS / "s1.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic private input")
        with self.assertRaisesRegex(RelayError, "notes worktree remains at .*1 private input files.*git worktree remove"):
            notes.attach(self.repo, self.home)
        self.assertFalse((self.runtime / notes.POINTER).exists())
        git(self.repo, "worktree", "remove", "--force", str(own))
        with self.assertRaisesRegex(RelayError, "lacks: Relay-Test/relay-notes .*Nothing was changed"):
            notes.attach(self.repo, self.home)
        # Bring them into the home, as the refusal says; a remote copy elsewhere is only reported.
        git(self.home, "fetch", str(self.repo), "Relay-Test/relay-notes:Home-Author/relay-notes")
        git(self.repo, "remote", "add", "origin", "https://example.invalid/public.git")
        git(self.repo, "update-ref", "refs/remotes/origin/relay-notes", git(self.repo, "rev-parse", "Relay-Test/relay-notes"))
        result = notes.attach(self.repo, self.home)
        report = " ".join(result["left_behind"])
        self.assertIn("already contained in Home-Author/relay-notes", report)
        self.assertIn("origin/relay-notes (https://example.invalid/public.git)", report)
        warnings = self.cli("status", "--repo", self.repo)[1]["warnings"]
        self.assertTrue(any("Remote notes branches remain" in text for text in warnings))
        self.assertEqual(self.heads(self.repo), ["refs/heads/Relay-Test/relay-notes", "refs/heads/main"])

    def test_an_upstream_with_commits_the_home_lacks_blocks_attach(self):
        mine = self.empty_commit(self.repo, "Local notes")
        git(self.home, "fetch", str(self.repo), f"{mine}:refs/heads/Home-Author/relay-notes")
        git(self.repo, "update-ref", "refs/heads/Relay-Test/relay-notes", mine)
        ahead = git(self.repo, "commit-tree", git(self.repo, "mktree", input=""), "-p", mine, "-m", "Pushed elsewhere")
        git(self.repo, "update-ref", "refs/remotes/origin/elsewhere", ahead)
        git(self.repo, "config", "branch.Relay-Test/relay-notes.remote", "origin")
        git(self.repo, "config", "branch.Relay-Test/relay-notes.merge", "refs/heads/elsewhere")
        git(self.repo, "config", "remote.origin.url", "https://example.invalid/x.git")
        git(self.repo, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")
        with self.assertRaisesRegex(RelayError, r"origin/elsewhere \("):
            notes.attach(self.repo, self.home)

    def test_init_still_refuses_a_conventional_directory_it_cannot_use(self):
        stray = self.runtime / "notes"
        stray.mkdir(parents=True)
        (stray / "draft.md").write_text("Someone's draft")
        with self.assertRaisesRegex(RelayError, "Unregistered notes directory"):
            notes.init(self.repo)
        shutil.rmtree(stray)
        path = Path(notes.init(self.repo)["notes"])
        git(path, "checkout", "--detach")
        with self.assertRaisesRegex(RelayError, "Unregistered notes directory"):
            notes.init(self.repo)
        self.assertFalse((self.runtime / "branches").exists())

    def test_a_home_that_pins_its_own_branch_is_still_a_home(self):
        notes.attach(self.home, branch="Home-Author/main/relay-notes")
        result = notes.attach(self.repo, self.home)
        self.assertEqual(result["branch"], "Home-Author/main/relay-notes")
        self.assertEqual(notes.resolve(self.repo), (self.home, "Home-Author/main/relay-notes"))

    def test_moving_to_another_home_waits_for_the_first_homes_notes(self):
        notes.attach(self.repo, self.home)
        path = Path(notes.init(self.repo)["notes"])
        notes.commit(self.repo, ["RESEARCH.md"], "Notes in the first home")
        second = self.make_repo("second home")
        with self.assertRaisesRegex(RelayError, "in .*notes home hold commits .*second home lacks.*notes detach first"):
            notes.attach(self.repo, second)
        (path / "draft.md").write_text("Uncommitted")
        git(second, "fetch", str(self.home), "Home-Author/relay-notes:Relay-Test/relay-notes")
        with self.assertRaisesRegex(RelayError, "notes worktree remains at .*1 changed files"):
            notes.attach(self.repo, second)
        self.assertEqual(notes.resolve(self.repo)[0], self.home)
        (path / "draft.md").unlink()
        result = notes.attach(self.repo, second)
        self.assertEqual((result["home"], result["previous"]["branch"]), (str(second), "Home-Author/relay-notes"))
        self.assertIn("already contained", " ".join(result["left_behind"]))
        # Leaving the first home's notes behind is possible, but only on purpose.
        third = self.make_repo("third home")
        with self.assertRaises(RelayError):
            notes.attach(self.repo, third)
        notes.detach(self.repo)
        self.assertEqual(notes.attach(self.repo, third)["home"], str(third))

    def test_attaching_to_a_linked_worktree_records_the_main_checkout(self):
        task = self.repo.parent / "home task"
        git(self.home, "worktree", "add", str(task), "-b", "task")
        notes.attach(self.repo, task)
        self.assertEqual(json.loads((self.runtime / notes.POINTER).read_text())["home"], "../../notes home")
        git(self.home, "worktree", "remove", str(task))
        self.assertEqual(notes.resolve(self.repo)[0], self.home)

    def test_relative_pointer_holds_when_the_workspace_moves(self):
        notes.attach(self.repo, self.home)
        moved = Path(self.tmp.name).resolve().parent / (Path(self.tmp.name).name + "-moved")
        shutil.copytree(self.tmp.name, moved, symlinks=True)
        self.addCleanup(shutil.rmtree, moved, True)
        home, branch = notes.resolve(moved / self.repo.name)
        self.assertEqual((home, branch), (moved / self.home.name, "Home-Author/relay-notes"))

    def test_detach_and_a_broken_pointer(self):
        notes.attach(self.repo, self.home)
        self.assertEqual(notes.detach(self.repo)["previous"]["branch"], "Home-Author/relay-notes")
        self.assertEqual(notes.resolve(self.repo), (self.repo, None))
        self.assertFalse(notes.detach(self.repo)["detached"])
        notes.attach(self.repo, self.home)
        shutil.rmtree(self.home)
        code, value = self.cli("notes", "status", "--repo", self.repo)
        self.assertEqual(code, 2)
        self.assertIn("is not a repository here", value["error"])
        policy.enable(self.runtime, "autoresearch", "claude", 100000, reserve=10000)
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["active"]), (0, True))  # a notes problem does not hide the policy
        self.assertIn("is not a repository here", value["notes"]["error"])
        self.assertTrue(any("is not a repository here" in text for text in value["warnings"]))
        (self.runtime / notes.POINTER).write_text("{broken")
        self.assertIn("invalid", notes.detach(self.repo)["previous"])
        self.assertFalse((self.runtime / notes.POINTER).exists())

    def test_cli_attach_and_flags_only_for_attach(self):
        code, value = self.cli("notes", "attach", "--repo", self.repo, "--to", self.home)
        self.assertEqual((code, value["branch"]), (0, "Home-Author/relay-notes"))
        self.assertEqual(self.cli("notes", "status", "--repo", self.repo, "--to", self.home)[0], 2)
        code, value = self.cli("notes", "detach", "--repo", self.repo)
        self.assertEqual((code, value["detached"]), (0, True))


class AttachHookTests(AttachCase):
    def setUp(self):
        super().setUp()
        policy.enable(self.runtime, "autoresearch", "claude", 100000, reserve=10000)
        self.transcript = self.repo.parent / "transcript.jsonl"
        self.transcript.write_text("".join(json.dumps(line) + "\n" for line in claude_lines(1000)))

    def hook(self, event, **kw):
        out = hooks.handle({"hook_event_name": event, "session_id": "s1", "cwd": str(self.repo.parent),
                            "transcript_path": str(self.transcript), **kw}, claude, str(self.repo))
        return out["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_session_text_names_the_home_and_the_project(self):
        text = self.hook("SessionStart", source="startup")
        self.assertIn(f"relay notes status --repo '{self.repo}'", text)  # quoted: the path has spaces
        self.assertNotIn("chosen with relay notes attach", text)
        notes.attach(self.repo, self.home)
        text = self.hook("SessionStart", source="startup")
        self.assertIn(f"on branch Home-Author/relay-notes of {self.home}", text)
        self.assertIn("This repository is in auto-research mode", text)
        self.assertIn("chosen with relay notes attach", self.hook("SessionStart", source="compact"))
        shutil.rmtree(self.home)
        self.assertIn("not a repository on this machine", self.hook("SessionStart", source="startup"))
        # A missing home costs the session nothing else: the closeout still arrives.
        self.transcript.write_text("".join(json.dumps(line) + "\n" for line in claude_lines(75000)))
        self.assertIn("Begin closeout", self.hook("PostToolUse"))

    def test_a_home_the_hook_cannot_read_still_leaves_the_reminders(self):
        notes.attach(self.repo, self.home)
        self.transcript.write_text("".join(json.dumps(line) + "\n" for line in claude_lines(75000)))
        with patch.object(notes, "where", side_effect=PermissionError(13, "Permission denied")):
            self.assertIn("pointer cannot be read", self.hook("SessionStart", source="startup"))
            text = self.hook("PostToolUse")
        self.assertIn("Begin closeout", text)
        self.assertNotIn("hook failed", text)

    def test_an_open_session_is_told_when_its_notes_move(self):
        self.hook("SessionStart", source="startup")
        self.assertEqual(self.hook("PostToolUse"), "")
        notes.attach(self.repo, self.home)
        text = self.hook("PostToolUse")
        self.assertTrue(text.startswith("research-relay: this repository's notes moved"), text)
        self.assertIn("Home-Author/relay-notes", text)
        self.assertNotIn("now in", text)
        self.assertEqual(self.hook("PostToolUse"), "")
        notes.detach(self.repo)
        self.assertIn("own notes again", self.hook("PostToolUse"))
        self.assertEqual(self.hook("PostToolUse"), "")


if __name__ == "__main__":
    unittest.main()
