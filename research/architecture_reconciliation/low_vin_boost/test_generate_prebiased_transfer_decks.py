import csv
import tempfile
import unittest
from pathlib import Path

from generate_prebiased_transfer_decks import (
    CANDIDATES,
    ENABLE_DELAYS_US,
    MODEL_INCLUDE,
    build_manifest_rows,
    render_deck,
    write_matrix,
)


class PrebiasedTransferDeckTests(unittest.TestCase):
    def test_candidate_and_delay_matrix(self):
        self.assertEqual(len(CANDIDATES), 3)
        self.assertEqual(ENABLE_DELAYS_US, (20, 50, 100))
        with self.assertRaises(ValueError):
            render_deck("4S10F_HCC", 20)
        with self.assertRaises(ValueError):
            render_deck("2S25F_KAM_LR", 10)

    def test_output_bus_is_prebiased_and_load_stays_connected(self):
        deck, metadata = render_deck("2S30F_KAM_HP_40", 20)
        self.assertIn("COUT VOUT 0 47u Rser=0.003 IC=12", deck)
        self.assertIn("CSS SS 0 47n IC=1.5", deck)
        self.assertIn("BLOAD LOAD 0 I=if(V(LOAD)>0.5,1,0)", deck)
        self.assertNotIn("I=if(V(EN)>1.5", deck)
        self.assertIn("PWL(0 0 2e-05 0 2.1e-05 3)", deck)
        self.assertIn(".meas tran vout_at_enable AVG V(VOUT) from 1.9e-05 to 2e-05", deck)
        self.assertIn(".meas tran vout_global_min MIN V(VOUT) from 0 to 40m", deck)
        self.assertEqual(metadata["case_type"], "prebiased_transfer")
        self.assertEqual(metadata["enable_delay_us"], 20)

    def test_eol_pack_values_and_model_include(self):
        deck, metadata = render_deck("2S25F_KAM_LR", 50)
        self.assertAlmostEqual(metadata["initial_pack_ocv_v"], 4.8)
        self.assertAlmostEqual(metadata["Ceq_F"], 8.75)
        self.assertAlmostEqual(metadata["Rpack_ohm"], 0.2)
        self.assertIn("CSTORE PACK_OC 0 8.75 IC=4.8", deck)
        self.assertIn("RESR PACK_OC PACK 0.2", deck)
        self.assertIn("RPATH PACK PACK_IN 0.002", deck)
        self.assertIn(".include " + MODEL_INCLUDE, deck)

    def test_manifest_has_nine_unrun_transfer_cases(self):
        rows = build_manifest_rows()
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row["run_status"] == "not_run" for row in rows))
        self.assertEqual(
            [row["enable_delay_us"] for row in rows[:3]],
            [20, 50, 100],
        )

    def test_generated_decks_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_matrix(out)
            decks = sorted(out.glob("*.cir"))
            self.assertEqual(len(decks), 9)
            with (out / "manifest.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 9)
            self.assertEqual(
                {path.stem for path in decks},
                {row["case"] for row in rows},
            )


if __name__ == "__main__":
    unittest.main()
