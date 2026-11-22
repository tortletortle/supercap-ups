import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_storage_architectures import DESIGNS, simulate
from simulate_calibrated_hold_up import (
    EXPECTED_CASES,
    EfficiencyMap,
    EfficiencyMapError,
    load_efficiency_map,
    simulate_calibrated_hold_up,
    write_outputs,
)


def constant_map(efficiency=0.92, min_vin=2.0, max_vin=6.0):
    return EfficiencyMap([
        {"case": "low", "vin_v": min_vin, "efficiency": efficiency, "peak_i_a": 3.0, "f_sw_khz": 450.0},
        {"case": "high", "vin_v": max_vin, "efficiency": efficiency, "peak_i_a": 4.0, "f_sw_khz": 500.0},
    ])


def write_analysis_csv(path, failed_case=None, omit_case=None):
    fields = [
        "case", "screen_result", "simulation_complete", "timing_order_ok",
        "deck_hash_ok", "log_hash_ok", "raw_hash_ok", "model_hash_ok",
        "vin_avg_v", "eff_model_pct", "peak_i_a", "avg_vout_v",
        "iout_avg_a", "ripple_mVpp", "f_sw_khz",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for index, case in enumerate(EXPECTED_CASES):
            if case == omit_case:
                continue
            source_v = (2.8, 3.0, 3.2, 3.6, 4.0, 4.4, 4.8)[index]
            writer.writerow({
                "case": case,
                "screen_result": "screen_fail" if case == failed_case else "screen_pass",
                "simulation_complete": "True",
                "timing_order_ok": "True",
                "deck_hash_ok": "True",
                "log_hash_ok": "True",
                "raw_hash_ok": "True",
                "model_hash_ok": "True",
                "vin_avg_v": source_v - 0.005,
                "eff_model_pct": 92.0 + index * 0.1,
                "peak_i_a": 3.0 + index * 0.1,
                "avg_vout_v": 12.0,
                "iout_avg_a": 1.0,
                "ripple_mVpp": 45.0,
                "f_sw_khz": 440.0 + index * 10.0,
            })


class CalibratedHoldUpTests(unittest.TestCase):
    def test_efficiency_and_peak_current_are_interpolated(self):
        mapping = EfficiencyMap([
            {"case": "a", "vin_v": 2.8, "efficiency": 0.90, "peak_i_a": 3.0, "f_sw_khz": 400.0},
            {"case": "b", "vin_v": 3.8, "efficiency": 0.94, "peak_i_a": 5.0, "f_sw_khz": 500.0},
        ])
        self.assertAlmostEqual(mapping.efficiency_at(3.3), 0.92)
        self.assertAlmostEqual(mapping.peak_current_at(3.3), 4.0)

    def test_map_rejects_extrapolation(self):
        mapping = constant_map(min_vin=2.8, max_vin=4.8)
        with self.assertRaises(EfficiencyMapError):
            mapping.efficiency_at(2.79)
        with self.assertRaises(EfficiencyMapError):
            mapping.peak_current_at(4.81)

    def test_constant_map_matches_existing_constant_efficiency_model(self):
        design = DESIGNS["2S30F_KAM_HP_40"]
        mapping = constant_map(efficiency=0.92, min_vin=2.0, max_vin=6.0)
        calibrated = simulate_calibrated_hold_up(
            design, mapping, 0.70, 4.0,
            task_s=1.2, dt_s=1e-5, max_s=3.0,
            path_resistance_ohm=0.0,
        )
        baseline = simulate(
            design, 0.70, 4.0, 0.92,
            dt_s=1e-5, task_s=1.2, max_s=3.0,
            path_efficiency=1.0,
        )
        self.assertTrue(calibrated["task_pass"])
        self.assertAlmostEqual(
            calibrated["hold_verified_s"], baseline["hold_s"], delta=0.002
        )
        self.assertLess(abs(calibrated["energy_balance_error_j"]), 1e-6)

    def test_insufficient_calibration_range_stops_before_task_endpoint(self):
        design = DESIGNS["2S30F_KAM_HP_40"]
        mapping = constant_map(efficiency=0.92, min_vin=3.0, max_vin=5.0)
        result = simulate_calibrated_hold_up(
            design, mapping, 0.70, 4.0,
            task_s=1.2, dt_s=1e-4, max_s=3.0,
        )
        self.assertFalse(result["task_pass"])
        self.assertEqual(result["stop_reason"], "efficiency_map_out_of_range")
        self.assertLess(result["hold_verified_s"], 1.2)

    def test_loader_requires_all_seven_hash_verified_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analysis_summary.csv"
            write_analysis_csv(path, omit_case=EXPECTED_CASES[-1])
            with self.assertRaisesRegex(ValueError, "incomplete"):
                load_efficiency_map(path)

    def test_loader_refuses_any_failed_fixed_vin_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analysis_summary.csv"
            write_analysis_csv(path, failed_case=EXPECTED_CASES[0])
            with self.assertRaisesRegex(ValueError, "screen_fail"):
                load_efficiency_map(path)

    def test_loader_accepts_complete_map_and_records_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analysis_summary.csv"
            write_analysis_csv(path)
            mapping, metadata = load_efficiency_map(path)
            self.assertEqual(len(mapping.points), 7)
            self.assertEqual(metadata["point_count"], 7)
            self.assertEqual(len(metadata["source_csv_sha256"]), 64)
            self.assertAlmostEqual(mapping.min_vin_v, 2.795)
            self.assertAlmostEqual(mapping.max_vin_v, 4.795)
            self.assertAlmostEqual(metadata["min_f_sw_khz"], 440.0)
            self.assertAlmostEqual(metadata["max_f_sw_khz"], 500.0)

    def test_candidate_energy_balance_and_output_files(self):
        mapping = constant_map(efficiency=0.92, min_vin=2.0, max_vin=6.0)
        design = dict(DESIGNS["2S25F_KAM_LR"])
        design["name"] = "2S25F_KAM_LR"
        result = simulate_calibrated_hold_up(
            design, mapping, 0.70, 4.0, task_s=1.2, dt_s=1e-4, max_s=2.0
        )
        self.assertTrue(result["task_pass"])
        self.assertLess(abs(result["energy_balance_error_j"]), 1e-6)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            write_outputs(output, [result], {
                "source_csv": "synthetic.csv",
                "source_csv_sha256": "a" * 64,
                "point_count": 7,
                "min_vin_v": 2.8,
                "max_vin_v": 4.8,
                "min_f_sw_khz": 440.0,
                "max_f_sw_khz": 500.0,
            })
            self.assertTrue((output / "calibrated_hold_up_summary.csv").is_file())
            report = (output / "calibrated_hold_up_report.md").read_text(encoding="utf-8")
            self.assertIn("not a continuous switching-level simulation", report)
            self.assertIn("2S25F_KAM_LR", report)


if __name__ == "__main__":
    unittest.main()
