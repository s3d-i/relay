"""Small local files and one POSIX lock, shared by every worktree of a repository."""

import contextlib
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile


class RelayError(Exception):
    pass


def git(repo, *args, input=None):
    result = subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(repo), *args],
        input=input, text=True, capture_output=True, timeout=30,
    )
    if result.returncode:
        raise RelayError(result.stderr.strip() or "git failed")
    return result.stdout.strip()


def common_dir(repo):
    repo = Path(repo).resolve()
    path = Path(git(repo, "rev-parse", "--git-common-dir"))
    return (repo / path).resolve()


def runtime_dir(repo):
    return common_dir(repo) / "research-relay"


def read_json(path, default=None):
    try:
        value = json.loads(Path(path).read_text())
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    except FileNotFoundError:
        return default
    except (ValueError, UnicodeError) as exc:
        raise RelayError(f"Invalid JSON file (preserved): {path}") from exc


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".relay-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def lock(path):
    """Never unlink lock files: unlinking a locked inode allows two owners."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        os.close(fd)
