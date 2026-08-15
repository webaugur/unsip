"""unsip: unzip-compatible extractor that fsyncs so disks can keep up."""

from __future__ import annotations

import getopt
import sys
import zipfile
from pathlib import Path

import traceback

from unsip.errors import UnsipError, write_backtrace
from unsip import __version__
from unsip.extract import extract_zip, zip_method

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
  -q       quiet (no per-file lines)
  -v       verbose listing (unzip -v); with -d/-n/-o also print sizes while extracting
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
    dest_set = False
    overwrite = "skip_complete"
    overwrite_set = False
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
            dest_set = True
        elif opt == "-n":
            overwrite = "never"
            overwrite_set = True
        elif opt == "-o":
            overwrite = "always"
            overwrite_set = True
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
            dest_set = True
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
        if verbose:
            print(f"unsip {__version__} of 15 Aug 2026, by David L Norris.")
            print("Info-ZIP compatible flags; fsync-throttled extract.")
            raise SystemExit(0)
        raise UnsipError("missing zip file")
    # unzip -v archive.zip is a verbose listing, not a silent extract
    if verbose and mode == "extract" and not dest_set and not overwrite_set and not junk:
        mode = "list"
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
        print(f"Archive:  {archive}")
        if not verbose:
            for info in zf.infolist():
                print(info.filename)
            return 0
        print(" Length   Method    Size  Cmpr    Date    Time   CRC-32   Name")
        print("--------  ------  ------- ---- ---------- ----- --------  ----")
        nfiles = 0
        usize = csize = 0
        for info in zf.infolist():
            if info.filename.endswith("/"):
                continue
            nfiles += 1
            usize += info.file_size
            csize += info.compress_size
            cmpr = 0
            if info.file_size:
                cmpr = int(round(100 * (1 - info.compress_size / info.file_size)))
            y, mo, d, h, mi, _s = info.date_time
            print(
                f"{info.file_size:8d}  {zip_method(info):6}  {info.compress_size:7d} "
                f"{cmpr:3d}% {mo:02d}-{d:02d}-{y:04d} {h:02d}:{mi:02d} "
                f"{info.CRC:08x}  {info.filename}"
            )
        print("--------          -------  ---                            -------")
        tot = 0
        if usize:
            tot = int(round(100 * (1 - csize / usize)))
        noun = "file" if nfiles == 1 else "files"
        print(f"{usize:8d}          {csize:7d} {tot:3d}%                            {nfiles} {noun}")
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
        print(f"unsip: cannot find zip file {archive}", file=sys.stderr)
        return 9
    try:
        if cfg["mode"] == "list":
            return list_zip(archive, verbose=cfg["verbose"])
        if cfg["mode"] == "test":
            return test_zip(archive, emit)
        if not cfg["quiet"]:
            print(f"Archive:  {archive}")
        chatter = None if cfg["quiet"] else (lambda m: print(m))
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
            chatter=chatter,
            verbose=cfg["verbose"],
        )
    except KeyboardInterrupt:
        print("unsip: interrupted", file=sys.stderr)
        print("  already-written files are kept; re-run the same command to resume", file=sys.stderr)
        return 130
    except UnsipError as exc:
        print(f"unsip: {exc}", file=sys.stderr)
        return 1
    except zipfile.BadZipFile as exc:
        print(f"unsip: archive is damaged or not a zip: {archive}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        from unsip.errors import explain_oserror

        print(explain_oserror(exc, doing="failed", path=archive), file=sys.stderr)
        return 1
    except Exception as exc:
        path = write_backtrace(exc, cfg["dest"])
        print(f"unsip: unexpected error: {exc}", file=sys.stderr)
        print(f"  this is a bug; backtrace written to {path}", file=sys.stderr)
        traceback.print_exc()
        return 1
    return 0
