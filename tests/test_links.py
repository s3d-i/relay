import contextlib
import io
import json
from pathlib import Path
from unittest.mock import patch

from test_relay import RepositoryCase
from research_relay import links, notes
from research_relay.__main__ import main
from research_relay.state import RelayError, git


class LinkReadingTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.notes = Path(notes.init(self.repo)['notes'])

    def write(self, name, body):
        path = self.notes / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        return path

    def test_follow_deeper_and_lateral_connections_without_entry_membership(self):
        self.write('RESEARCH.md', '[Current question](questions/comparison.md)')
        self.write('questions/comparison.md',
                   'Working interpretation. [Observed conditions](../runs/one/detail.md#conditions)')
        self.write('runs/one/detail.md',
                   '[A challenge to this reading](../../counterexamples/alternative.md)')
        correction = self.write('counterexamples/alternative.md',
                                'This observation weakens [the attribution](../questions/comparison.md#claim).')
        self.write('other-focus.md', 'An unrelated working question.')
        notes.commit(self.repo, ['RESEARCH.md', 'questions/comparison.md', 'runs/one/detail.md'],
                     'Record initial understanding')
        # The correction is still a draft and is not linked from the entrypoint.
        before = git(self.notes, 'status', '--porcelain')
        head = git(self.notes, 'rev-parse', 'HEAD')
        view = links.neighborhood(self.notes, 'questions/comparison.md')
        self.assertEqual({edge['source'] for edge in view['incoming']},
                         {'RESEARCH.md', 'counterexamples/alternative.md'})
        self.assertEqual(view['outgoing'][0]['target'], 'runs/one/detail.md')
        self.assertEqual(view['outgoing'][0]['fragment'], 'conditions')
        deeper = links.neighborhood(self.notes, view['outgoing'][0]['target'])
        self.assertEqual(deeper['outgoing'][0]['target'], 'counterexamples/alternative.md')
        cycle = links.neighborhood(self.notes, deeper['outgoing'][0]['target'])
        self.assertEqual(cycle['outgoing'][0]['target'], 'questions/comparison.md')
        self.assertEqual(git(self.notes, 'status', '--porcelain'), before)
        self.assertEqual(git(self.notes, 'rev-parse', 'HEAD'), head)
        correction.write_text('This challenge was withdrawn; rationale retained here.')
        self.assertEqual(len(links.neighborhood(self.notes, 'questions/comparison.md')['incoming']), 1)

    def test_source_lines_references_anchors_spaces_and_images(self):
        self.write('results/run (a).md', '# Results')
        self.write('results/条件 分析.md', '# 条件')
        self.write('RESEARCH.md', '\n'.join([
            '# Focus',
            '[Earlier result](results/run(a).md#claim "reading context")',
            '[Conditions][setup]',
            '![Figure](figures/result.png)',
            '[Same question](#focus)',
            '[Code](https://example.invalid/repo/blob/abc/file.py#L20)',
            '[setup]: <results/条件 分析.md#条件>',
            '[unused]: not-an-edge.md',
            '[setup][] and [setup]',
            '[Encoded](results/%E6%9D%A1%E4%BB%B6%20%E5%88%86%E6%9E%90.md#%E6%9D%A1%E4%BB%B6)',
            '[Label with `code`](<results/run (a).md>)',
        ]))
        view = links.neighborhood(self.notes)
        out = view['outgoing']
        self.assertEqual([edge['line'] for edge in out], [2, 3, 4, 5, 6, 9, 9, 10, 11])
        self.assertEqual(out[0]['target'], 'results/run(a).md')
        self.assertEqual(out[1]['target'], 'results/条件 分析.md')
        self.assertEqual(out[1]['fragment'], '条件')
        self.assertEqual(out[4]['availability'], 'external-unchecked')
        self.assertEqual(out[7]['target'], out[1]['target'])
        self.assertEqual(out[8]['label'], 'Label with `code`')
        self.assertEqual(out[8]['availability'], 'present')
        self.assertEqual(view['incoming'][0]['href'], '#focus')

    def test_code_samples_comments_and_unused_definitions_are_not_connections(self):
        self.write('RESEARCH.md', '\n'.join([
            '`[Inline](fake.md)`',
            '```markdown', '[Fenced](fake.md)', '```',
            '~~~', '[Also fenced](fake.md)', '~~~',
            '    [Indented code](fake.md)',
            '<!-- [Comment](fake.md) -->',
            '[not-used]: fake.md',
            '[Actual connection](real.md)',
        ]))
        out = links.neighborhood(self.notes)['outgoing']
        self.assertEqual([(edge['target'], edge['line']) for edge in out], [('real.md', 11)])

    def test_private_sources_ignored_even_if_force_tracked_and_never_read_via_symlinks(self):
        private = self.write('artifacts/private/human-inputs/session.md',
                             '[PRIVATE RAW INPUT](../../../RESEARCH.md)')
        git(self.notes, 'add', '-f', 'artifacts/private/human-inputs/session.md')
        (self.notes / 'alias.md').symlink_to(private)
        (self.notes / 'aliases').symlink_to(private.parent, target_is_directory=True)
        self.write('RESEARCH.md', '[Private, local](artifacts/private/human-inputs/session.md#prompt-1)\n'
                   '[Unavailable private source](artifacts/private/human-inputs/elsewhere.md#answer-1)')
        original_read = Path.read_text

        def safe_read(path, *args, **kwargs):
            self.assertFalse(path.resolve().is_relative_to(private.parent))
            return original_read(path, *args, **kwargs)

        with patch.object(Path, 'read_text', safe_read):
            view = links.neighborhood(self.notes)
            for name in ('artifacts/private/human-inputs/session.md', 'alias.md', 'aliases/session.md'):
                with self.subTest(name=name), self.assertRaises(RelayError):
                    links.neighborhood(self.notes, name)
        self.assertEqual(view['incoming'], [])
        self.assertNotIn('PRIVATE RAW INPUT', json.dumps(view))
        self.assertEqual([edge['availability'] for edge in view['outgoing']],
                         ['private-local', 'private-unavailable'])

    def test_unavailable_evidence_is_a_reading_limit_not_a_graph_validation_failure(self):
        self.write('RESEARCH.md', '[Missing observation](runs/missing.md#result)\n'
                   '[Local code](../../../code.py)\n[Machine file](file:///tmp/output.csv)')
        view = links.neighborhood(self.notes)
        self.assertEqual([edge['availability'] for edge in view['outgoing']],
                         ['missing', 'outside-notes-unchecked', 'external-unchecked'])
        missing = links.neighborhood(self.notes, 'runs/missing.md')
        self.assertEqual(missing['query']['availability'], 'missing')
        self.assertEqual(missing['incoming'][0]['source'], 'RESEARCH.md')
        self.assertEqual(missing['outgoing'], [])

    def test_ignored_hidden_large_and_non_text_files_do_not_contribute_backlinks(self):
        self.write('.gitignore', 'scratch/\n')
        self.write('scratch/ignored.md', '[ignored](../RESEARCH.md)')
        self.write('.hidden.md', '[hidden](RESEARCH.md)')
        self.write('oversized.md', 'x' * (1024 * 1024 + 1) + '[large](RESEARCH.md)')
        self.write('bad.md', '').write_bytes(b'\xff')
        self.assertEqual(links.neighborhood(self.notes)['incoming'], [])
        self.assertEqual({row['source'] for row in links.neighborhood(self.notes)['skipped']},
                         {'bad.md', 'oversized.md'})

    def test_cli_queries_one_note_without_writes_or_initializing_missing_notes(self):
        self.write('topic.md', '[Focus](RESEARCH.md#question)')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['notes', '--repo', str(self.repo), 'links', '--path', 'topic.md']), 0)
        self.assertEqual(json.loads(output.getvalue())['outgoing'][0]['target'], 'RESEARCH.md')
        for paths in (['../outside.md'], ['/tmp/outside.md'], ['topic.md', 'RESEARCH.md']):
            args = ['notes', '--repo', str(self.repo), 'links']
            for name in paths:
                args += ['--path', name]
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 2)
        other = self.repo.parent / 'without-notes'
        other.mkdir()
        git(other, 'init')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['notes', '--repo', str(other), 'links']), 2)
        self.assertFalse((other / '.git/research-relay').exists())
