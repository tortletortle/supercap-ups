import hashlib
import tempfile
import unittest
from pathlib import Path

from analyze_low_vin_results import (
    analyze_case,
    parse_ltspice_log,
    parse_spice_number,
    parse_tran_stop_s,
    write_outputs,
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
pack_ocv_avg: AVG(V(PACK_OC))=4.34 FROM 0.035 TO 0.037
pack_terminal_avg: AVG(V(PACK))=2.87 FROM 0.035 TO 0.037
pack_input_avg: AVG(V(PACK_IN))=2.86 FROM 0.035 TO 0.037
ppack: AVG(V(PACK)*I(VSENSE))=11.48 FROM 0.035 TO 0.037
pack_esr_loss_w: AVG(I(VSENSE)*I(VSENSE)*0.32)=5.12 FROM 0.035 TO 0.037
path_loss_w: AVG(I(VSENSE)*I(VSENSE)*0.002)=0.032 FROM 0.035 TO 0.037
eff_pack: 100*pout/ppack=104.5296
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
            write_outputs(root, [result])
            self.assertTrue((root / "analysis_summary.csv").is_file())
            report = (root / "analysis_report.md").read_text(encoding="utf-8")
            self.assertIn("screen_pass", report)
            self.assertIn("FSW observed", report)

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

    def test_pack_coupled_checkpoint_requires_and_reports_pack_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            deck = case / "case.cir"
            log = case / "case.log"
            raw = case / "case.raw"
            model = root / "model.lib"
            deck.write_text(".tran 0 40m 0 50n uic\n")
            pack_log = (
                GOOD_LOG
                .replace("vin_avg: AVG(V(vin))=3.6", "vin_avg: AVG(V(vin))=2.8608")
                .replace("iin_avg: AVG(-I(V1))=4.0", "iin_avg: AVG(-I(V1))=4.6")
                .replace("pin: AVG(-V(vin)*I(V1))=14.4", "pin: AVG(-V(vin)*I(V1))=13.16")
                .replace("eff: 100*pout/pin=83.3333", "eff: 100*pout/pin=91.1854")
                .replace("ppack: AVG(V(PACK)*I(VSENSE))=11.48", "ppack: AVG(V(PACK)*I(VSENSE))=13.202")
                .replace("pack_esr_loss_w: AVG(I(VSENSE)*I(VSENSE)*0.32)=5.12", "pack_esr_loss_w: AVG(I(VSENSE)*I(VSENSE)*0.32)=6.7712")
                .replace("path_loss_w: AVG(I(VSENSE)*I(VSENSE)*0.002)=0.032", "path_loss_w: AVG(I(VSENSE)*I(VSENSE)*0.002)=0.04232")
                .replace("eff_pack: 100*pout/ppack=104.5296", "eff_pack: 100*pout/ppack=90.8953")
                .replace("pack_input_avg: AVG(V(PACK_IN))=2.86", "pack_input_avg: AVG(V(PACK_IN))=2.8608")
            )
            log.write_text(pack_log)
            raw.write_bytes(b"synthetic raw")
            model.write_text("* synthetic model\n")
            row = {
                "case": "case", "architecture": "2S30F_KAM_HP_40",
                "checkpoint_s": "1.2", "expected_pack_ocv_v": "4.3407",
                "expected_pack_terminal_v": "2.8735",
                "expected_input_current_a": "4.5851", "exit_code": "0",
                "input_deck_sha256": sha(deck), "log_sha256": sha(log),
                "raw_sha256": sha(raw), "model_sha256": sha(model),
            }
            result = analyze_case(row, case, model)
            self.assertEqual(result["screen_result"], "screen_pass")
            self.assertAlmostEqual(result["pack_terminal_delta_v"], -0.0035)
            self.assertAlmostEqual(result["pack_ocv_delta_v"], -0.0007)
            self.assertAlmostEqual(result["input_current_delta_a"], 0.0149)
            self.assertAlmostEqual(result["pack_esr_loss_w"], 6.7712)
            self.assertEqual(result["architecture"], "2S30F_KAM_HP_40")

    def test_prebiased_transfer_reports_droop_without_auto_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            deck = case / "case.cir"
            log = case / "case.log"
            raw = case / "case.raw"
            model = root / "model.lib"
            deck.write_text(".tran 0 40m 0 50n uic\n")
            transfer_log = (
                GOOD_LOG
                + "vout_at_enable: FIND V(VOUT) AT=20u=11.57\n"
                + "vout_pre_enable_min: MIN(V(VOUT))=11.55 FROM 0 TO 20u\n"
                + "vout_first_5ms_min: MIN(V(VOUT))=11.55 FROM 0 TO 5m\n"
                + "vout_global_min: MIN(V(VOUT))=11.50 FROM 0 TO 40m\n"
            )
            log.write_text(transfer_log)
            raw.write_bytes(b"synthetic raw")
            model.write_text("* synthetic model\n")
            row = {
                "case": "case", "case_type": "prebiased_transfer",
                "architecture": "2S25F_KAM_LR", "enable_delay_us": "20",
                "exit_code": "0",
                "input_deck_sha256": sha(deck), "log_sha256": sha(log),
                "raw_sha256": sha(raw), "model_sha256": sha(model),
            }
            result = analyze_case(row, case, model)
            self.assertEqual(result["screen_result"], "transfer_review_required")
            self.assertAlmostEqual(result["vout_pre_enable_min_v"], 11.55)
            self.assertAlmostEqual(result["vout_global_min_v"], 11.50)
            self.assertAlmostEqual(result["vout_global_drop_v"], 0.50)
            self.assertEqual(result["enable_delay_us"], "20")
            self.assertIn("no system minimum-output-voltage", result["screen_reasons"])

    def test_prebiased_transfer_missing_droop_measurement_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            deck = case / "case.cir"
            log = case / "case.log"
            raw = case / "case.raw"
            model = root / "model.lib"
            deck.write_text(".tran 0 40m 0 50n uic\n")
            transfer_log = (
                GOOD_LOG
                + "vout_at_enable: AVG(V(VOUT))=11.9 FROM 19u TO 20u\n"
                + "vout_pre_enable_min: MIN(V(VOUT))=11.8 FROM 0 TO 20u\n"
                + "vout_first_5ms_min: MIN(V(VOUT))=11.5 FROM 0 TO 5m\n"
            )
            log.write_text(transfer_log)
            raw.write_bytes(b"synthetic raw")
            model.write_text("* synthetic model\n")
            row = {
                "case": "case", "case_type": "prebiased_transfer",
                "architecture": "2S25F_KAM_LR", "enable_delay_us": "20",
                "exit_code": "0",
                "input_deck_sha256": sha(deck), "log_sha256": sha(log),
                "raw_sha256": sha(raw), "model_sha256": sha(model),
            }
            result = analyze_case(row, case, model)
            self.assertEqual(result["screen_result"], "measurement_incomplete")
            self.assertIn("vout_global_min", result["missing_measurements"])

    def test_pack_checkpoint_missing_required_pack_measurement_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case = root / "case"
            case.mkdir()
            deck = case / "case.cir"
            log = case / "case.log"
            raw = case / "case.raw"
            model = root / "model.lib"
            deck.write_text(".tran 0 40m 0 50n uic\n")
            log.write_text(GOOD_LOG.replace(
                "pack_terminal_avg: AVG(V(PACK))=2.87 FROM 0.035 TO 0.037\n", ""
            ))
            raw.write_bytes(b"synthetic raw")
            model.write_text("* synthetic model\n")
            row = {
                "case": "case", "architecture": "2S30F_KAM_HP_40",
                "expected_pack_terminal_v": "2.8735", "exit_code": "0",
                "input_deck_sha256": sha(deck), "log_sha256": sha(log),
                "raw_sha256": sha(raw), "model_sha256": sha(model),
            }
            result = analyze_case(row, case, model)
            self.assertEqual(result["screen_result"], "measurement_incomplete")
            self.assertIn("pack_terminal_avg", result["missing_measurements"])

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
