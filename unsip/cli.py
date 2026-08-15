"""unsip: unzip-compatible extractor that fsyncs so disks can keep up."""

from __future__ import annotations

import getopt
import sys
import zipfile
from pathlib import Path

from unsip.extract import UnsipError, extract_zip

USAGE = """\
unsip [{flags}] file[.zip] [file(s) ...] [-x xfile(s) ...] [-d exdir]

Throttled unzip. Same flag letters as Info-ZIP unzip. Extra:
  --sync-every BYTES   fsync after this many uncompressed bytes (default 8388608)
  --pause SECONDS      sleep after each sync (default 0.4)

Flags:
  -d DIR   extract into DIR (default: current directory)
  -n       never overwrite existing files
  -o       overwrite files without prompting
  -j       junk paths (write all files into the extract dir)
  -l       list archive contents
  -t       test archive integrity
  -q       quiet
  -v       verbose
  -h       this help
"""


def parse_argv(argv: list[str]) -> dict:
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE, end="")
        raise SystemExit(0)

    shorts = "d:nojlqtvh"
    longs = ["sync-every=", "pause=", "help"]
    try:
        opts, rest = getopt.getopt(argv, shorts, longs)
    except getopt.GetoptError as exc:
        raise UnsipError(str(exc)) from exc

    dest = Path(".")
    overwrite = "skip_complete"
    junk = False
    quiet = False
    verbose = False
    mode = "extract"
    sync_every = 8 * 1024 * 1024
    pause = 0.4
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print(USAGE, end="")
            raise SystemExit(0)
        if opt == "-d":
            dest = Path(arg)
        elif opt == "-n":
            overwrite = "never"
        elif opt == "-o":
            overwrite = "always"
        elif opt == "-j":
            junk = True
        elif opt == "-q":
            quiet = True
        elif opt == "-v":
            verbose = True
        elif opt == "-l":
            mode = "list"
        elif opt == "-t":
            mode = "test"
        elif opt == "--sync-every":
            sync_every = int(arg)
        elif opt == "--pause":
            pause = float(arg)

    include: list[str] = []
    exclude: list[str] = []
    zip_path: Path | None = None
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "-d" and i + 1 < len(rest):
            dest = Path(rest[i + 1])
            i += 2
            continue
        if tok == "-x":
            i += 1
            while i < len(rest) and rest[i] != "-d":
                exclude.append(rest[i])
                i += 1
            continue
        if zip_path is None:
            zip_path = Path(tok)
            if zip_path.suffix == "" and not zip_path.is_file():
                alt = Path(str(zip_path) + ".zip")
                if alt.is_file():
                    zip_path = alt
        else:
            include.append(tok)
        i += 1

    if zip_path is None:
        raise UnsipError("missing zip file")
    return {
        "zip_path": zip_path,
        "dest": dest,
        "overwrite": overwrite,
        "junk": junk,
        "quiet": quiet,
        "verbose": verbose,
        "mode": mode,
        "sync_every": sync_every,
        "pause": pause,
        "include": include or None,
        "exclude": exclude or None,
    }


def _emit(quiet: bool):
    if quiet:
        return lambda _m: None
    return lambda m: print(m, file=sys.stderr)


def list_zip(archive: Path, *, verbose: bool) -> int:
    with zipfile.ZipFile(archive) as zf:
        if verbose:
            print(f"Archive:  {archive}")
        for info in zf.infolist():
            if verbose:
                print(f"{info.file_size:10d}  {info.filename}")
            else:
                print(info.filename)
    return 0


def test_zip(archive: Path, emit) -> int:
    with zipfile.ZipFile(archive) as zf:
        bad = zf.testzip()
    if bad:
        emit(f"bad CRC for {bad}")
        return 1
    emit(f"No errors detected in {archive}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        cfg = parse_argv(args)
    except UnsipError as exc:
        print(f"unsip: {exc}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2
    except SystemExit as exc:
        if exc.code in (None, 0):
            return 0
        raise

    archive = cfg["zip_path"]
    emit = _emit(cfg["quiet"])
    if not archive.is_file():
        print(f"unsip: cannot find {archive}", file=sys.stderr)
        return 9
    try:
        if cfg["mode"] == "list":
            return list_zip(archive, verbose=cfg["verbose"])
        if cfg["mode"] == "test":
            return test_zip(archive, emit)
        extract_zip(
            archive,
            cfg["dest"],
            log=emit,
            sync_every=max(1, cfg["sync_every"]),
            pause=max(0.0, cfg["pause"]),
            overwrite=cfg["overwrite"],
            junk_paths=cfg["junk"],
            include=cfg["include"],
            exclude=cfg["exclude"],
        )
    except (UnsipError, zipfile.BadZipFile, OSError) as exc:
        print(f"unsip: {exc}", file=sys.stderr)
        return 1
    return 0
