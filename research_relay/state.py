"""Small local files and POSIX locks, shared by every worktree of a repository."""

import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
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


def thread_id(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value
    ):
        raise RelayError("Need an exact Codex thread UUID; do not guess from the newest file.")
    return value


def read_json(path, default=None):
    try:
        value = json.loads(Path(path).read_text())
        if not isinstance(value, dict):
            raise ValueError("expected object")
        return value
    except FileNotFoundError:
        return default
    except (ValueError, UnicodeError) as exc:
        raise RelayError(f"Invalid state file (preserved): {path}") from exc


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
def lock(path, blocking=True):
    """Never unlink lock files: unlinking a locked inode allows two owners."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            raise RelayError("Repository already has an active watcher.") from exc
        yield fd
    finally:
        os.close(fd)


def locked(path):
    """Read-only status checks must work without write access to the Git directory."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(fd)


def marker_path(runtime, identity):
    return Path(runtime) / "threads" / (thread_id(identity) + ".json")


def process_identity(pid):
    """Birth time + executable prevents PID reuse from extending watcher life."""
    if not isinstance(pid, int) or pid <= 1:
        raise RelayError("Invalid host PID.")
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart=", "-o", "comm="],
            capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RelayError("Cannot inspect host process; monitoring unavailable (ps denied/failed).") from exc
    if result.returncode or not result.stdout.strip():
        raise RelayError("Cannot verify host process (exited or process inspection denied).")
    return result.stdout.strip()


def verify_ancestor(pid):
    """When launched inside Codex, the chosen host must own this execution tree."""
    current = os.getpid()
    for _ in range(64):
        if current == pid:
            return
        result = subprocess.run(["ps", "-p", str(current), "-o", "ppid="],
                                capture_output=True, text=True, timeout=3)
        try:
            parent = int(result.stdout.strip())
        except ValueError:
            break
        if parent <= 1 or parent == current:
            break
        current = parent
    raise RelayError("Host PID is not an ancestor of this Codex execution; refusing wrong-instance binding.")
