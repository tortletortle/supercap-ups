"""Regression tests for the V1.4 matrix generator (stdlib only)."""
import csv
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
V14_ROOT = HERE.parents[1]
GENERATOR = V14_ROOT / "scripts" / "build_matrix.py"


def snapshot(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class BuildMatrixTests(unittest.TestCase):
    def run_generator(self, root):
        return subprocess.run(
            [sys.executable, str(GENERATOR), "--root", str(root)],
            check=True, capture_output=True, text=True,
        )

    def test_committed_case_names_and_exact_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nets = root / "netlists"
            nets.mkdir()
            (nets / "README.md").write_text("human-maintained sentinel\n", encoding="utf-8")

            result = self.run_generator(root)
            names = sorted(p.name for p in nets.glob("*.cir"))
            expected_frequency = [
                "freq_vin7_rfsw324k.cir",
                "freq_vin7_rfsw510k.cir",
                "freq_vin9p4_rfsw324k.cir",
                "freq_vin9p4_rfsw517k.cir",
            ]

            self.assertIn("Generated 16 LTspice decks", result.stdout)
            self.assertEqual(len(names), 16)
            self.assertEqual(
                sorted(n for n in names if n.startswith("freq_")),
                expected_frequency,
            )
            self.assertFalse(any("vin7p0" in n for n in names))
            self.assertEqual((nets / "README.md").read_text(encoding="utf-8"),
                             "human-maintained sentinel\n")

    def test_limiter_csv_retains_percentage_column_and_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.run_generator(root)
            with (root / "data" / "ti_ilim_screen.csv").open(
                newline="", encoding="utf-8"
            ) as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(len(rows), 6)
            self.assertIn("minimum_headroom_pct", rows[0])
            self.assertEqual(rows[0]["minimum_headroom_pct"], "210.02")
            self.assertEqual(rows[-1]["minimum_headroom_pct"], "-13.57")

    def test_crosscase_screen_includes_new_full_run_peak(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.run_generator(root)
            with (root / "data" / "ti_ilim_crosscase_screen.csv").open(
                newline="", encoding="utf-8"
            ) as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(len(rows), 6)
            by_r = {int(row["rilim_kohm"]): row for row in rows}
            self.assertEqual(by_r[174]["V1_4_round2_full_run_peak_A"], "3.421604")
            self.assertEqual(by_r[174]["headroom_vs_V1_4_A"], "0.5175")
            self.assertEqual(by_r[174]["headroom_vs_V1_4_pct"], "15.12")
            self.assertEqual(by_r[220]["headroom_vs_V1_4_A"], "-0.9125")
            self.assertEqual(by_r[220]["headroom_vs_V1_4_pct"], "-26.67")
            self.assertIn("MAX_I_L1_0_26ms", by_r[174]["V1_4_round2_peak_source_case"])

    def test_repeated_generation_is_deterministic_and_readme_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nets = root / "netlists"
            nets.mkdir()
            readme = nets / "README.md"
            readme.write_text("# Reviewed README\nDo not replace.\n", encoding="utf-8")

            self.run_generator(root)
            first = snapshot(root)
            self.run_generator(root)
            second = snapshot(root)

            self.assertEqual(first, second)
            self.assertEqual(readme.read_text(encoding="utf-8"),
                             "# Reviewed README\nDo not replace.\n")
            self.assertEqual(len(list(nets.glob("*.cir"))), 16)


if __name__ == "__main__":
    unittest.main()
