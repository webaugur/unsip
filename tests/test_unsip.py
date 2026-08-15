import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from unsip.cli import main, parse_argv
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


if __name__ == "__main__":
    unittest.main()
