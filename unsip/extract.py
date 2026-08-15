"""Extract zip members with periodic fsync so writeback can drain."""

from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path
from typing import Callable

CHUNK = 1024 * 512


class UnsipError(RuntimeError):
    pass


def fmt_bytes(n: int) -> str:
    if n >= 1024 * 1024 * 1024:
        return f"{n / (1024 ** 3):.2f} GiB"
    if n >= 1024 * 1024:
        return f"{n / (1024 ** 2):.1f} MiB"
    if n >= 1024:
        return f"{n / 1024:.0f} KiB"
    return f"{n} B"


def safe_join(dest: Path, name: str) -> Path:
    dest_r = dest.resolve()
    target = (dest / name).resolve()
    if target != dest_r and dest_r not in target.parents:
        raise UnsipError(f"refusing zip path {name}")
    return dest / name


def wanted(name: str, include: list[str] | None, exclude: list[str] | None) -> bool:
    if exclude and any(name == e or name.startswith(e.rstrip("/") + "/") for e in exclude):
        return False
    if not include:
        return True
    return any(name == i or name.startswith(i.rstrip("/") + "/") for i in include)


def extract_zip(
    archive: Path,
    dest: Path,
    *,
    log: Callable[[str], None] | None = None,
    sync_every: int = 8 * 1024 * 1024,
    pause: float = 0.4,
    overwrite: str = "skip_complete",
    junk_paths: bool = False,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    emit = log or (lambda _m: None)
    copied = skipped = 0
    since_sync = 0
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            emit(
                f"extract {len(members)} entries → {dest} "
                f"(sync every {fmt_bytes(sync_every)}, pause {pause}s)"
            )
            for info in members:
                name = info.filename
                if not wanted(name, include, exclude):
                    continue
                if name.endswith("/"):
                    if not junk_paths:
                        safe_join(dest, name).mkdir(parents=True, exist_ok=True)
                    continue
                rel = Path(name).name if junk_paths else name
                out = safe_join(dest, rel)
                out.parent.mkdir(parents=True, exist_ok=True)
                exists = out.is_file()
                same = exists and out.stat().st_size == info.file_size
                if exists and overwrite == "never":
                    skipped += 1
                    continue
                if same and overwrite != "always":
                    skipped += 1
                    continue
                tmp = out.with_name(out.name + ".extract")
                with zf.open(info, "r") as src, tmp.open("wb") as fh:
                    while True:
                        chunk = src.read(CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        since_sync += len(chunk)
                        if since_sync >= sync_every:
                            fh.flush()
                            os.fsync(fh.fileno())
                            os.sync()
                            if pause > 0:
                                time.sleep(pause)
                            since_sync = 0
                    fh.flush()
                    os.fsync(fh.fileno())
                tmp.replace(out)
                copied += 1
                if copied % 200 == 0:
                    emit(f"extract progress {copied} written, {skipped} skipped")
    except zipfile.BadZipFile as exc:
        raise UnsipError(f"not a zip: {archive}: {exc}") from exc
    except OSError as exc:
        raise UnsipError(f"extract failed: {exc}") from exc
    os.sync()
    emit(f"extract done: {copied} written, {skipped} skipped → {dest}")
    return dest
