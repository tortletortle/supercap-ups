import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import gate_and_screen as gate
import generate_rilim_matrix as matrix
import generate_dynamic_cases as dynamic
import run_gated_audit as runner


class GateTests(unittest.TestCase):
    def make_pairing_report(self, frequency_delta=0.6, timing_delta=2.0):
        return {
            "status": gate.PAIRING_OK,
            "checks": {"hash": True, "cycle_accounting": True, "csv": True},
            "analysis": {"50ns": {"prescribed_frequency_measurement": {"frequency_khz": 442.0}}},
            "comparison": {
                "same_electrical_parameters": True,
                "frequency_delta_khz": frequency_delta,
                "distribution_deltas": {
                    field: {"unit": "ns", "median_delta": timing_delta if field == "period_s" else 0.1}
                    for field in gate.KEY_TIMING_FIELDS
                },
            },
        }

    def test_pairing_gate_requires_12p5_for_nonconverged_data(self):
        result = gate.decide_12p5(self.make_pairing_report())
        self.assertTrue(result["run_12p5"])
        self.assertFalse(result["matrix_allowed_before_12p5"])

    def test_pairing_gate_skips_12p5_when_all_thresholds_pass(self):
        result = gate.decide_12p5(self.make_pairing_report(0.1, 0.2))
        self.assertFalse(result["run_12p5"])
        self.assertTrue(result["matrix_allowed_before_12p5"])

    def test_pairing_gate_fails_closed_on_failed_report(self):
        report = self.make_pairing_report()
        report["checks"]["csv"] = False
        with self.assertRaises(gate.GateError):
            gate.decide_12p5(report)

    def test_pairing_gate_fails_closed_on_missing_metric(self):
        report = self.make_pairing_report()
        del report["comparison"]["distribution_deltas"]["period_s"]
        with self.assertRaises(gate.GateError):
            gate.decide_12p5(report)

    def test_fpwm_current_limit_screen(self):
        self.assertAlmostEqual(gate.fpwm_limit_typ_a(160_000), 5.8375, places=6)
        rows = gate.build_rilim_screen_rows()
        by_r = {row["rilim_kohm"]: row for row in rows}
        self.assertEqual(by_r[160]["disposition"], "BEST_OF_TESTED_LOW_MARGIN_NOT_APPROVED")
        self.assertEqual(by_r[174]["disposition"], "INSUFFICIENT_SCREEN_MARGIN")
        sweep = gate.build_parameter_sweep_rows()
        self.assertEqual(len(sweep), 6 * 3 * 3 * 4 * 4 * 6)
        self.assertIn("temperature_c", sweep[0])
        self.assertIn("copper_loss_estimate_w", sweep[0])

    def test_peak_and_rms_current_screen(self):
        result = gate.inductor_current_screen(7.0, 12.6, 1.0, 0.8, 2.31e-6, 400e3)
        self.assertAlmostEqual(result["i_peak_a"], 3.9335016835, places=6)
        self.assertAlmostEqual(result["i_rms_a"], 2.4509642945, places=6)

    def test_frequency_measurement_counts_100_periods(self):
        period_100 = 100.0 / 442_336.492352
        measured_khz = 0.1 / period_100
        self.assertAlmostEqual(measured_khz, 442.336492352, places=6)

    def test_12p5_gate_blocks_invalid_cycles_and_missing_csv(self):
        summary25 = {"prescribed_edge_measurement": {"frequency_kHz": 442.0}}
        summary12 = {
            "cycle_accounting": {"candidate_cycles": 2, "complete_valid_cycles": 0,
                                 "right_censored_cycles": 1, "invalid_cycles": 1},
            "run_parameters": {},
            "prescribed_edge_measurement": {"frequency_kHz": 442.0, "timing_valid": False},
        }
        comparison = {
            "same_electrical_parameters": True,
            "frequency_delta_khz": 0.0,
            "distribution_deltas": {
                field: {"unit": "ns", "median_delta": 0.0}
                for field in gate.KEY_TIMING_FIELDS
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            missing_csv = Path(tmp) / "missing.csv"
            result = gate.assess_12p5(summary25, summary12, comparison, missing_csv)
        self.assertFalse(result["matrix_allowed"])
        self.assertFalse(result["checks"]["no_invalid_cycles"])


class MatrixDeckTests(unittest.TestCase):
    def test_matrix_has_twelve_unique_cases_and_internal_current_probes(self):
        names = set()
        for vin, label in matrix.VIN_CASES:
            for rilim in matrix.RILIM_KOHM:
                name = f"ilim_vin{label}_rilim{rilim}k.cir"
                names.add(name)
                deck = matrix.make_deck(vin, rilim, "../../tps61088_v1_3/model/TPS61088_LT.LIB", 25)
                self.assertIn(f"RILIM ilim 0 {rilim}k", deck)
                self.assertIn("V(X1:CLIMT)", deck)
                self.assertIn("V(X1:ISENSE_A)", deck)
                self.assertIn("RMS I(L1)", deck)
                self.assertIn("vout_min_overcurrent MIN V(vout) FROM 15m TO 16m", deck)
                self.assertIn("f_sw_khz PARAM 0.1/(sw_t6101-sw_t6001)", deck)
                self.assertIn(".tran 0 26m 0 25n", deck)
        self.assertEqual(len(names), 12)

    def test_dynamic_decks_cover_loadstep_overcurrent_short_and_full_vin_scan(self):
        names = set()
        for vin in (7.0, 9.4):
            for rilim in (160, 174):
                for kind in ("loadstep", "overcurrent", "short"):
                    names.add(f"dynamic_vin{dynamic.vin_label(vin)}_rilim{rilim}k_{kind}.cir")
                    deck = dynamic.make_deck(vin, rilim, kind, "../../tps61088_v1_3/model/TPS61088_LT.LIB")
                    self.assertIn("V(X1:CLIMT)", deck)
                    self.assertIn("V(X1:ISENSE_A)", deck)
                    self.assertIn(".tran 0 26m 0 25n", deck)
                    if kind == "overcurrent":
                        self.assertIn("ilim_margin_overcurrent PARAM", deck)
        self.assertEqual(len(names), 12)
        scan_names = {
            f"dynamic_vin{dynamic.vin_label(v)}_rilim{r}k_vinscan.cir"
            for v in (7.0, 7.5, 8.0, 8.5, 9.0, 9.4) for r in (160, 174)
        }
        self.assertEqual(len(scan_names), 12)
        for vin in (7.0, 7.5, 8.0, 8.5, 9.0, 9.4):
            deck = dynamic.make_deck(vin, 160, "vinscan", "../../tps61088_v1_3/model/TPS61088_LT.LIB")
            self.assertIn("BLOAD load 0 I=min(max(V(load)/10,0),1)", deck)

    def test_runner_requires_full_matrix_measurements(self):
        required = runner.required_measurement_fields("RILIM_MATRIX")
        self.assertIn("ilim_threshold_overcurrent", required)
        self.assertIn("peak_switch_sense_overcurrent", required)
        self.assertIn("il_rms", required)
        self.assertIn("vout_after_overcurrent", required)
        self.assertIn("eta_pct", runner.required_measurement_fields("VIN_SCAN"))


if __name__ == "__main__":
    unittest.main()
