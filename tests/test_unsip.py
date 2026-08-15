import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import errno

from unsip.cli import main, parse_argv
from unsip.errors import explain_oserror
from unsip.extract import extract_zip


def _zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("dir/a.txt", "hello")
        zf.writestr("b.txt", "world")


class UnsipTests(unittest.TestCase):
    def test_parse_clustered_unzip_flags(self):
        cfg = parse_argv(["-nq", "-d", "/tmp/out", "archive.zip", "dir/a.txt", "-x", "skip.dat"])
        self.assertEqual(cfg["overwrite"], "never")
        self.assertTrue(cfg["quiet"])
        self.assertEqual(cfg["dest"], Path("/tmp/out"))
        self.assertEqual(cfg["include"], ["dir/a.txt"])
        self.assertEqual(cfg["exclude"], ["skip.dat"])

    def test_d_after_zip_name(self):
        cfg = parse_argv(["archive.zip", "-d", "dest"])
        self.assertEqual(cfg["dest"], Path("dest"))
        self.assertEqual(cfg["zip_path"], Path("archive.zip"))

    def test_v_alone_lists_like_unzip(self):
        cfg = parse_argv(["-v", "archive.zip"])
        self.assertEqual(cfg["mode"], "list")
        self.assertTrue(cfg["verbose"])

    def test_v_with_d_extracts(self):
        cfg = parse_argv(["-v", "-d", "dest", "archive.zip"])
        self.assertEqual(cfg["mode"], "extract")
        self.assertTrue(cfg["verbose"])

    def test_extract_skip_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "a.zip"
            _zip(zpath)
            dest = Path(tmp) / "out"
            extract_zip(zpath, dest, pause=0.0, sync_every=64)
            self.assertEqual((dest / "dir" / "a.txt").read_text(), "hello")
            (dest / "dir" / "a.txt").write_text("keep")
            self.assertEqual(main(["-n", "-d", str(dest), str(zpath)]), 0)
            self.assertEqual((dest / "dir" / "a.txt").read_text(), "keep")
            buf = io.StringIO()
            import sys

            old = sys.stdout
            sys.stdout = buf
            try:
                code = main(["-l", str(zpath)])
            finally:
                sys.stdout = old
            self.assertEqual(code, 0)
            self.assertIn("dir/a.txt", buf.getvalue())

            dest2 = Path(tmp) / "out2"
            out = io.StringIO()
            old = sys.stdout
            sys.stdout = out
            try:
                code = main(["-d", str(dest2), str(zpath)])
            finally:
                sys.stdout = old
            self.assertEqual(code, 0)
            text = out.getvalue()
            self.assertIn("Archive:", text)
            self.assertTrue("inflating:" in text or "extracting:" in text)
            self.assertIn("b.txt", text)

    def test_explain_enospc(self):
        err = OSError(errno.ENOSPC, "No space left")
        err.filename = "/disk/full"
        msg = explain_oserror(err, doing="cannot write", path="/disk/full")
        self.assertIn("no space left", msg)
        self.assertIn("/disk/full", msg)

    def test_ctrl_c_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "a.zip"
            _zip(zpath)
            dest = Path(tmp) / "out"
            from unittest.mock import patch

            with patch("unsip.cli.extract_zip", side_effect=KeyboardInterrupt):
                err = io.StringIO()
                import sys

                old = sys.stderr
                sys.stderr = err
                try:
                    code = main(["-d", str(dest), str(zpath)])
                finally:
                    sys.stderr = old
            self.assertEqual(code, 130)
            self.assertIn("interrupted", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())


if __name__ == "__main__":
    unittest.main()
