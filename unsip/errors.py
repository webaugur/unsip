"""User-facing errors vs unexpected failures that need a backtrace."""

from __future__ import annotations

import errno
import traceback
from datetime import datetime, timezone
from pathlib import Path

_OS = {
    errno.ENOSPC: "no space left on the device",
    errno.EIO: "disk I/O error",
    errno.EROFS: "destination is read-only",
    errno.EACCES: "permission denied",
    errno.EPERM: "operation not permitted",
    errno.ENAMETOOLONG: "file name is too long",
    errno.ENOTDIR: "a path component is not a directory",
    errno.EISDIR: "expected a file, found a directory",
    errno.ENOENT: "no such file or directory",
    errno.EBUSY: "device or resource busy",
    errno.ETXTBSY: "text file busy",
}
if hasattr(errno, "EDQUOT"):
    _OS[errno.EDQUOT] = "disk quota exceeded"
if hasattr(errno, "ESTALE"):
    _OS[errno.ESTALE] = "stale file handle"


class UnsipError(RuntimeError):
    """Expected failure: show the message, no traceback."""


def explain_oserror(exc: OSError, *, doing: str, path: Path | str | None = None) -> str:
    why = _OS.get(exc.errno) or (exc.strerror or exc.__class__.__name__)
    bits = [doing, why]
    if path:
        bits.append(str(path))
    if exc.filename and str(exc.filename) != str(path or ""):
        bits.append(f"({exc.filename})")
    if exc.errno is not None:
        bits.append(f"[errno {exc.errno}]")
    return "; ".join(bits)


def write_backtrace(exc: BaseException, dest: Path | None = None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = dest if dest and dest.is_dir() else Path.cwd()
    path = directory / f"unsip-backtrace-{stamp}.log"
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        path = Path.cwd() / f"unsip-backtrace-{stamp}.log"
        path.write_text(text, encoding="utf-8")
    return path
