"""An on-demand view of explicit Markdown links, not a stored or validated graph."""

import html
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from .notes import is_private_artifact
from .state import RelayError, git


# A reading aid for ordinary single-line inline/reference links and images.
# Deliberately not a CommonMark renderer (HTML links and wiki links are omitted).
DEST = r'''(?:<[^<>\n]*>|(?:\\.|[^\\\s()]|\((?:\\.|[^\\\s()])*\))+)'''
TITLE = r'''(?:\s+(?:"[^"\n]*"|'[^'\n]*'|\([^()\n]*\)))?'''
INLINE = re.compile(r'(?<!\\)\[([^\]\n]*)\]\(\s*(' + DEST + ')' + TITLE + r'\s*\)')
DEFINITION = re.compile(r'^ {0,3}\[([^\]\n]+)\]:[ \t]*(' + DEST + ')' + TITLE + r'[ \t]*$', re.M)
REFERENCE = re.compile(r'(?<!\\)\[([^\]\n]+)\](?:\[([^\]\n]*)\])?')


def _blank(match):
    return re.sub(r'[^\n]', ' ', match.group())


def _prose(text):
    """Mask examples without changing source offsets or line numbers."""
    text = re.sub(r'<!--[\s\S]*?(?:-->|$)', _blank, text)
    lines, fence = [], None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)', line)
        masked = bool(fence or marker or line.startswith(('    ', '\t')))
        if marker:
            run, tail = marker.groups()
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not tail.strip():
                fence = None
        lines.append(re.sub(r'[^\n]', ' ', line) if masked else line)
    return re.sub(r'(?<!`)(`+)(?!`)([\s\S]*?)\1(?!`)', _blank, ''.join(lines))


def _decode(value):
    return html.unescape(re.sub(r'\\([^\w\s])', r'\1', value))


def markdown_links(text):
    """Yield source locations and destinations; never infer a semantic relation."""
    prose = _prose(text)
    references = {}
    for match in DEFINITION.finditer(prose):
        key = ' '.join(match[1].split()).casefold()
        references.setdefault(key, match[2])
    prose = DEFINITION.sub(_blank, prose)
    found = []
    for match in INLINE.finditer(prose):
        found.append((match.start(), text[match.start(1):match.end(1)], match[2]))
    # Do not rediscover inline labels or reference definitions as shortcut links.
    prose = INLINE.sub(_blank, prose)
    for match in REFERENCE.finditer(prose):
        key = ' '.join((match[2] or match[1]).split()).casefold()
        if key in references:
            found.append((match.start(), text[match.start(1):match.end(1)], references[key]))
    for offset, label, destination in sorted(found):
        if destination.startswith('<'):
            destination = destination[1:-1]
        yield {'line': text.count('\n', 0, offset) + 1,
               'label': label, 'href': _decode(destination)}


def _symlink(root, path):
    return any(item.is_symlink() for item in (path, *path.parents)
               if item != root and item.is_relative_to(root))


def _local(root, path):
    # Normalize ../ lexically, without following links into private/outside files.
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        return {'target': str(path), 'availability': 'outside-notes-unchecked'}
    relative = path.relative_to(root)
    value = {'target': relative.as_posix()}
    if _symlink(root, path):
        value['availability'] = 'symlink-unchecked'
    elif is_private_artifact(relative):
        value['availability'] = 'private-local' if path.exists() else 'private-unavailable'
    else:
        value['availability'] = 'present' if path.exists() else 'missing'
    return value


def _target(root, source, href):
    try:
        parts = urlsplit(href)
    except ValueError:
        return {'target': href, 'availability': 'unresolved', 'fragment': ''}
    fragment = unquote(parts.fragment)
    if parts.scheme or parts.netloc:
        return {'target': href, 'availability': 'external-unchecked', 'fragment': fragment}
    path = source.parent / unquote(parts.path) if parts.path else source
    return {**_local(root, path), 'fragment': fragment}


def neighborhood(root, name='RESEARCH.md'):
    """Read visible notes once and return one file's outgoing links and backlinks.

    Includes nested/untracked notes and cycles; no tree depth, kind, or entrypoint
    membership is required. Private, ignored, hidden and symlinked sources are
    never read. Missing destinations are reading context, not validation failures.
    """
    root = Path(root).resolve()
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts or relative.as_posix() == '.':
        raise RelayError('Choose a file relative to the notes worktree.')
    if (is_private_artifact(relative) or any(part.startswith('.') for part in relative.parts)
            or _symlink(root, root / relative)):
        raise RelayError('Link queries do not read private, hidden or symlinked sources.')
    query = _local(root, root / relative)
    outgoing, incoming, skipped = [], [], []
    candidates = git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
    for name in sorted(set(candidates.split('\0')) - {''}):
        relative = Path(name)
        if (relative.suffix.lower() != '.md' or is_private_artifact(relative)
                or any(part.startswith('.') for part in relative.parts)):
            continue
        source = root / relative
        if _symlink(root, source):
            skipped.append({'source': name, 'reason': 'symlink-not-read'})
            continue
        try:
            if source.stat().st_size > 1024 * 1024:
                skipped.append({'source': name, 'reason': 'larger-than-1-MiB'})
                continue
            body = source.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            skipped.append({'source': name, 'reason': 'unreadable'})
            continue
        for link in markdown_links(body):
            edge = {'source': name, **link, **_target(root, source, link['href'])}
            if name == query['target']:
                outgoing.append(edge)
            if edge['target'] == query['target']:
                incoming.append(edge)
    return {'notes': str(root), 'query': query, 'outgoing': outgoing, 'incoming': incoming,
            'skipped': skipped,
            'scope': 'Explicit single-line Markdown inline/reference links in visible notes; '
                     'private/ignored/hidden sources, HTML and wiki links omitted. '
                     'External sources and anchors are not verified. No files are changed.'}
