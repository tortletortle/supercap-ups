import csv
import tempfile
import unittest
from pathlib import Path

from generate_eol_checkpoint_decks import (
    CANDIDATES,
    MODEL_INCLUDE,
    build_manifest_rows,
    render_deck,
    write_matrix,
)


class EolCheckpointDeckTests(unittest.TestCase):
    def test_only_candidates_that_reach_1p2s_are_included(self):
        self.assertEqual(
            CANDIDATES,
            (
                ("2S30F_KAM_HP_40", "eol_2s30f_hp40_1p2s_92pct"),
                ("2S25F_KAM_LR", "eol_2s25f_lr_1p2s_92pct"),
            ),
        )
        with self.assertRaises(ValueError):
            render_deck("2S30F_KAM_HP_44")

    def test_hp40_deck_uses_eol_pack_and_1p2s_checkpoint(self):
        deck, case = render_deck("2S30F_KAM_HP_40")
        self.assertAlmostEqual(case["expected_pack_ocv_v"], 4.3407209, delta=2e-5)
        self.assertAlmostEqual(case["expected_pack_terminal_v"], 2.8734896, delta=2e-5)
        self.assertAlmostEqual(case["expected_input_current_a"], 4.5850977, delta=2e-5)
        self.assertIn("CSTORE PACK_OC 0 10.5 IC=4.34072086033", deck)
        self.assertIn("RESR PACK_OC PACK 0.32", deck)
        self.assertIn("RPATH PACK PACK_IN 0.002", deck)
        self.assertIn("VSENSE PACK_IN VIN 0", deck)
        self.assertIn(".tran 0 40m 0 50n uic", deck)

    def test_lr_deck_uses_eol_pack_and_1p2s_checkpoint(self):
        deck, case = render_deck("2S25F_KAM_LR")
        self.assertAlmostEqual(case["expected_pack_ocv_v"], 4.3353756, delta=2e-5)
        self.assertAlmostEqual(case["expected_pack_terminal_v"], 3.6042895, delta=2e-5)
        self.assertAlmostEqual(case["expected_input_current_a"], 3.6554307, delta=2e-5)
        self.assertIn("CSTORE PACK_OC 0 8.75 IC=4.33537563566", deck)
        self.assertIn("RESR PACK_OC PACK 0.2", deck)

    def test_model_include_resolves_from_checkpoint_directory(self):
        repo_root = Path(__file__).resolve().parents[3]
        checkpoint_dir = Path(__file__).resolve().parent / "checkpoints"
        resolved = (checkpoint_dir / MODEL_INCLUDE).resolve()
        expected = repo_root / "sim" / "tps61088_v1_3" / "model" / "TPS61088_LT.LIB"
        self.assertEqual(resolved, expected)
        self.assertTrue(resolved.is_file())

    def test_generated_decks_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_matrix(out)
            decks = sorted(out.glob("*.cir"))
            self.assertEqual(len(decks), 2)
            with (out / "manifest.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                [row["architecture"] for row in rows],
                ["2S30F_KAM_HP_40", "2S25F_KAM_LR"],
            )
            self.assertTrue(all(row["run_status"] == "not_run" for row in rows))


if __name__ == "__main__":
    unittest.main()
