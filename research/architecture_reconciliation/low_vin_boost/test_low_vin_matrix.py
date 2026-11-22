import csv
import tempfile
import unittest
from pathlib import Path

from generate_low_vin_matrix import (
    INPUT_POINTS_V,
    MODEL_INCLUDE,
    format_vin,
    render_deck,
    write_matrix,
)


class LowVinMatrixTests(unittest.TestCase):
    def test_five_required_input_points(self):
        self.assertEqual(INPUT_POINTS_V, (3.2, 3.6, 4.0, 4.4, 4.8))
        self.assertEqual(
            [format_vin(v) for v in INPUT_POINTS_V],
            ["3p2", "3p6", "4p0", "4p4", "4p8"],
        )

    def test_deck_keeps_same_power_stage_and_fpwm_configuration(self):
        deck = render_deck(3.6)
        self.assertIn(f".include {MODEL_INCLUDE}", deck)
        self.assertIn("V1 source 0 3.6", deck)
        self.assertIn("L1 vin sw 3.3u Rser=.026", deck)
        self.assertIn("RFSW fsw sw 324k", deck)
        self.assertIn("RILIM ilim 0 100k", deck)
        self.assertIn("X1 0 boot comp en fb fsw ilim 0 nc0 nc1 0 ss", deck)
        self.assertIn(".tran 0 40m 0 50n", deck)
        self.assertIn("from 35m to 37m", deck)
        self.assertIn("RISE=6001", deck)
        self.assertIn("RISE=6101", deck)

    def test_all_generated_decks_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_matrix(out)
            decks = sorted(out.glob("*.cir"))
            self.assertEqual(len(decks), 5)
            with (out / "manifest.csv").open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row["run_status"] == "not_run" for row in rows))
            self.assertEqual(
                [row["vin_source_v"] for row in rows],
                ["3.2", "3.6", "4.0", "4.4", "4.8"],
            )

    def test_unknown_input_point_is_rejected(self):
        with self.assertRaises(ValueError):
            render_deck(5.0)


if __name__ == "__main__":
    unittest.main()
