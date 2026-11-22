import csv
import tempfile
import unittest
from pathlib import Path

from generate_inductor_sweep import (
    INDUCTORS,
    INPUT_POINTS_V,
    MODEL_INCLUDE,
    build_manifest_rows,
    render_deck,
    write_matrix,
)


class InductorSweepTests(unittest.TestCase):
    def test_candidate_data_and_critical_vin_points(self):
        self.assertEqual(INPUT_POINTS_V, (2.8, 3.6))
        self.assertEqual(
            [(x["nominal_uH"], x["min_uH"]) for x in INDUCTORS],
            [(3.3, 2.64), (2.2, 1.76), (1.5, 1.2)],
        )
        self.assertEqual(
            [x["isat_typical_a"] for x in INDUCTORS],
            [9.5, 10.0, 12.5],
        )

    def test_decks_use_minimum_inductance_maximum_dcr_and_fpwm_limit(self):
        deck, metadata = render_deck(INDUCTORS[2], 2.8)
        self.assertIn(".include " + MODEL_INCLUDE, deck)
        self.assertIn("V1 source 0 2.8", deck)
        self.assertIn("L1 vin sw 1.2u Rser=0.0121", deck)
        self.assertIn("RILIM ilim 0 100k", deck)
        self.assertIn("il_avg AVG I(L1)", deck)
        self.assertIn("il_rms RMS I(L1)", deck)
        self.assertEqual(metadata["case_type"], "inductor_stress")
        self.assertEqual(metadata["isat_above_programmed_ilim_typical"], "true")

    def test_baseline_and_2p2uH_do_not_claim_isat_above_typical_limit(self):
        _, baseline = render_deck(INDUCTORS[0], 3.6)
        _, candidate = render_deck(INDUCTORS[1], 3.6)
        self.assertEqual(baseline["isat_above_programmed_ilim_typical"], "false")
        self.assertEqual(candidate["isat_above_programmed_ilim_typical"], "false")

    def test_manifest_has_six_unrun_cases(self):
        rows = build_manifest_rows()
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["run_status"] == "not_run" for row in rows))
        self.assertEqual(
            {row["vin_source_v"] for row in rows},
            {"2.8", "3.6"},
        )

    def test_generated_decks_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_matrix(out)
            decks = sorted(out.glob("*.cir"))
            self.assertEqual(len(decks), 6)
            with (out / "manifest.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 6)
            self.assertEqual(
                {path.stem for path in decks},
                {row["case"] for row in rows},
            )

    def test_model_include_resolves_from_sibling_output_directory(self):
        repo_root = Path(__file__).resolve().parents[3]
        output_dir = Path(__file__).resolve().parent / "inductor_sweep"
        resolved = (output_dir / MODEL_INCLUDE).resolve()
        self.assertEqual(
            resolved,
            repo_root / "sim" / "tps61088_v1_3" / "model" / "TPS61088_LT.LIB",
        )


if __name__ == "__main__":
    unittest.main()
