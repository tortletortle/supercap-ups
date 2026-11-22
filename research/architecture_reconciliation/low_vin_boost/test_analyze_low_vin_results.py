import hashlib
import tempfile
import unittest
from pathlib import Path

from analyze_low_vin_results import (
    analyze_case,
    parse_ltspice_log,
    parse_spice_number,
    parse_tran_stop_s,
)

GOOD_LOG = """LTspice 26.1.1 for Windows
Direct Newton iteration succeeded in finding operating point.
Total elapsed time: 12.345 seconds.
dd: Emission coefficient, N=0.0001, too small, this might lead to numerical problems.
t_en: V(en)=1.2 AT 0.0001004
t98: V(vout)=11.76 AT 0.0112
t98_delay: t98-t_en=0.0110996
sw_t6001: V(sw)=10 AT 0.0228
sw_t6101: V(sw)=10 AT 0.0230
f_sw_khz: 0.1/(sw_t6101-sw_t6001)=500
vin_avg: AVG(V(vin))=3.6 FROM 0.035 TO 0.037
avg_vout: AVG(V(vout))=12.0 FROM 0.035 TO 0.037
vmin: MIN(V(vout))=11.97 FROM 0.035 TO 0.037
vmax: MAX(V(vout))=12.03 FROM 0.035 TO 0.037
ripple: PP(V(vout))=0.06 FROM 0.035 TO 0.037
peak_i: MAX(I(L1))=5.1 FROM 0.035 TO 0.037
peak_start: MAX(I(L1))=5.4 FROM 0 TO 0.035
iin_avg: AVG(-I(V1))=4.0 FROM 0.035 TO 0.037
iout_avg: AVG(I(VLOAD))=1.0 FROM 0.035 TO 0.037
pin: AVG(-V(vin)*I(V1))=14.4 FROM 0.035 TO 0.037
pout: AVG(V(vout)*I(VLOAD))=12.0 FROM 0.035 TO 0.037
eff: 100*pout/pin=83.3333
"""


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LowVinLogParserTests(unittest.TestCase):
    def test_parse_at_measurements_and_regular_values(self):
        parsed = parse_ltspice_log(GOOD_LOG)
        m = parsed["measurements"]
        self.assertAlmostEqual(m["t_en"], 0.0001004)
        self.assertAlmostEqual(m["t98"], 0.0112)
        self.assertAlmostEqual(m["f_sw_khz"], 500.0)
        self.assertAlmostEqual(m["ripple"], 0.06)
        self.assertEqual(parsed["warning_count"], 1)
        self.assertTrue(parsed["has_elapsed_record"])

    def test_failed_measurement_is_preserved(self):
        parsed = parse_ltspice_log(GOOD_LOG + '\nMeasurement "sw_t6101" FAIL\'ed\n')
        self.assertIn("sw_t6101", parsed["failed_measurements"])
        self.assertNotIn("sw_t6101", parsed["measurements"])

    def test_solver_failure_markers_are_detected(self):
        parsed = parse_ltspice_log(
            GOOD_LOG + "\nFatal Error: timestep too small\nTime step too small\n"
        )
        self.assertTrue(parsed["fatal_error"])
        self.assertTrue(parsed["timestep_too_small"])

    def test_spice_suffixes_and_transient_stop(self):
        self.assertAlmostEqual(parse_spice_number("40m"), 0.04)
        self.assertAlmostEqual(parse_spice_number("3.3u"), 3.3e-6)
        self.assertAlmostEqual(parse_spice_number("324k"), 324000)
        self.assertAlmostEqual(parse_spice_number("1meg"), 1e6)
        self.assertAlmostEqual(parse_tran_stop_s(".tran 0 40m 0 50n"), 0.04)

    def test_good_case_is_only_a_limited_screen_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            deck = case / "case.cir"
            log = case / "case.log"
            raw = case / "case.raw"
            model = root / "model.lib"
            deck.write_text(".tran 0 40m 0 50n\n")
            log.write_text(GOOD_LOG)
            raw.write_bytes(b"synthetic raw")
            model.write_text("* synthetic model\n")
            row = {
                "case": "case", "vin_source_v": "3.6", "exit_code": "0",
                "input_deck_sha256": sha(deck), "log_sha256": sha(log),
                "raw_sha256": sha(raw), "model_sha256": sha(model),
            }
            result = analyze_case(row, case, model)
            self.assertEqual(result["screen_result"], "screen_pass")
            self.assertTrue(result["timing_order_ok"])
            self.assertEqual(result["f_sw_khz"], 500.0)
            self.assertEqual(result["eff_model_pct"], 83.3333)

    def test_output_ripple_failure_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            deck = case / "case.cir"
            log = case / "case.log"
            raw = case / "case.raw"
            model = root / "model.lib"
            deck.write_text(".tran 0 40m 0 50n\n")
            log.write_text(GOOD_LOG.replace("ripple: PP(V(vout))=0.06", "ripple: PP(V(vout))=0.12"))
            raw.write_bytes(b"synthetic raw")
            model.write_text("* synthetic model\n")
            row = {
                "case": "case", "vin_source_v": "3.6", "exit_code": "0",
                "input_deck_sha256": sha(deck), "log_sha256": sha(log),
                "raw_sha256": sha(raw), "model_sha256": sha(model),
            }
            result = analyze_case(row, case, model)
            self.assertEqual(result["screen_result"], "screen_fail")
            self.assertFalse(result["check_ripple_at_most_100mVpp"])

    def test_hash_mismatch_blocks_screen_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            deck = case / "case.cir"
            log = case / "case.log"
            raw = case / "case.raw"
            model = root / "model.lib"
            deck.write_text(".tran 0 40m 0 50n\n")
            log.write_text(GOOD_LOG)
            raw.write_bytes(b"synthetic raw")
            model.write_text("* synthetic model\n")
            row = {
                "case": "case", "vin_source_v": "3.6", "exit_code": "0",
                "input_deck_sha256": "0" * 64, "log_sha256": sha(log),
                "raw_sha256": sha(raw), "model_sha256": sha(model),
            }
            result = analyze_case(row, case, model)
            self.assertEqual(result["screen_result"], "artifact_integrity_failure")
            self.assertFalse(result["deck_hash_ok"])


if __name__ == "__main__":
    unittest.main()
