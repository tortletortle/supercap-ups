import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "hardware" / "ltspice-jlc-qualification"
sys.path.insert(0, str(ROOT))
import package_jlc_import as packager  # noqa: E402


class PackageJlcImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.asc_dir = self.root / "asc"
        self.sym_a = self.root / "sym-a"
        self.sym_b = self.root / "sym-b"
        self.asc_dir.mkdir()
        self.sym_a.mkdir()
        self.sym_b.mkdir()
        self.asc = self.asc_dir / "fixture.asc"
        self.asc.write_text(
            "Version 4\n"
            "SYMBOL res 0 0 R0\n"
            "SYMBOL __block21 200 0 R0\n"
            "TEXT 0 0 Left 2 !.include ../model/device.lib\n"
            "TEXT 0 20 Left 2 !.tran 0 1\n"
            "TEXT 0 40 Left 2 !keep-this-note\n",
            encoding="latin-1",
        )
        (self.asc_dir / "__block21.asy").write_text("Version 4\n", encoding="latin-1")
        (self.sym_a / "res.asy").write_text("Version 4\nresistor\n", encoding="latin-1")
        self.output = self.root / "out" / "fixture.zip"
        self.report = self.root / "out" / "manifest.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *extra):
        argv = [
            "package_jlc_import.py",
            "--asc", str(self.asc),
            "--output", str(self.output),
            "--report", str(self.report),
            *map(str, extra),
        ]
        with patch.object(sys, "argv", argv):
            return packager.main()

    def test_complete_symbol_set_creates_jlc_zip_and_strips_only_sim_directives(self):
        original = self.asc.read_bytes()
        code = self.run_main("--symbol-root", self.sym_a)
        self.assertEqual(code, 0)
        self.assertEqual(self.asc.read_bytes(), original)
        with zipfile.ZipFile(self.output) as zf:
            self.assertEqual(set(zf.namelist()), {"fixture.asc", "res.asy", "__block21.asy"})
            imported = zf.read("fixture.asc").decode("latin-1")
            self.assertNotIn(".include", imported)
            self.assertNotIn(".tran", imported)
            self.assertIn("keep-this-note", imported)
        manifest = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["stripped_simulation_directives"]), 2)
        self.assertTrue(manifest["not_production_ready"])

    def test_missing_symbol_fails_closed(self):
        self.asc.write_text(
            "Version 4\nSYMBOL cap 0 0 R0\nSYMBOL __block21 200 0 R0\n",
            encoding="latin-1",
        )
        code = self.run_main("--symbol-root", self.sym_a)
        self.assertEqual(code, 3)
        self.assertFalse(self.output.exists())

    def test_conflicting_same_name_symbols_fail_closed(self):
        (self.sym_b / "res.asy").write_text("Version 4\ndifferent\n", encoding="latin-1")
        code = self.run_main("--symbol-root", self.sym_a, "--symbol-root", self.sym_b)
        self.assertEqual(code, 3)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
