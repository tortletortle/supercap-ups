"""Unit tests for the read-only FSW pairing-v2 runner."""
import csv
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
V14_ROOT = HERE.parents[1]
sys.path.insert(0, str(V14_ROOT / "scripts"))

import run_fsw_internal_pairing_v2 as runner


class PairingRunnerTests(unittest.TestCase):
    def test_sha256_file_reads_binary_content(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.bin"
            path.write_bytes(b"fsw-probe")
            self.assertEqual(
                runner.sha256_file(path),
                hashlib.sha256(b"fsw-probe").hexdigest(),
            )

    def test_inventory_selects_primary_raw_and_ignores_sidecars(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inventory.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=("max_step_ns", "path", "bytes", "sha256")
                )
                writer.writeheader()
                rows_to_write = (
                    ("50", r"C:\\sim\\probe50.db", "10", "db"),
                    ("50", r"C:\\sim\\probe50.log", "20", "log"),
                    ("50", r"C:\\sim\\probe50.op.raw", "30", "op"),
                    ("50", r"C:\\sim\\freq_vin7_rfsw324k_internal_probe_50ns.raw", "40", "raw50"),
                    ("25", r"C:\\sim\\probe25.db", "11", "db"),
                    ("25", r"C:\\sim\\probe25.op.raw", "31", "op"),
                    ("25", r"C:\\sim\\freq_vin7_rfsw324k_internal_probe_25ns.raw", "41", "raw25"),
                    ("12.5", r"C:\\sim\\other.raw", "50", "other"),
                )
                for step, raw_path, size, digest in rows_to_write:
                    writer.writerow({
                        "max_step_ns": step, "path": raw_path,
                        "bytes": size, "sha256": digest,
                    })
            rows = runner.load_inventory_rows(path)
            self.assertEqual(set(rows), {50, 25})
            self.assertTrue(rows[50]["path"].endswith("50ns.raw"))
            self.assertTrue(rows[25]["path"].endswith("25ns.raw"))

    def test_committed_inventory_resolves_the_two_primary_raw_files(self):
        rows = runner.load_inventory_rows()
        self.assertEqual(set(rows), {50, 25})
        basename50 = rows[50]["path"].replace("\\", "/").rsplit("/", 1)[-1].lower()
        basename25 = rows[25]["path"].replace("\\", "/").rsplit("/", 1)[-1].lower()
        self.assertEqual(
            basename50, "freq_vin7_rfsw324k_internal_probe_50ns.raw"
        )
        self.assertEqual(
            basename25, "freq_vin7_rfsw324k_internal_probe_25ns.raw"
        )

    def test_inventory_rejects_duplicate_primary_raw_for_same_step(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inventory.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=("max_step_ns", "path", "bytes", "sha256")
                )
                writer.writeheader()
                writer.writerow({
                    "max_step_ns": "50", "path": "first.raw", "bytes": "10", "sha256": "a"
                })
                writer.writerow({
                    "max_step_ns": "50", "path": "second.raw", "bytes": "10", "sha256": "a"
                })
                writer.writerow({
                    "max_step_ns": "25", "path": "other25.raw", "bytes": "20", "sha256": "b"
                })
            with self.assertRaisesRegex(ValueError, "Duplicate primary 50 ns RAW"):
                runner.load_inventory_rows(path)

    def test_event_multiplicity_gates_primary_events_but_not_diagnostic_comparator(self):
        names = (
            "pvin_cross",
            "comparator_output_rise",
            "u5_toff_0p5V_rise",
            "gate_l_rise",
            "cap_reset_0p5V_fall",
            "sw_fall_10V",
        )
        summary = {
            "event_multiplicity": {
                name: {"missing_cycles": 0, "multiple_cycles": 0}
                for name in names
            }
        }
        summary["event_multiplicity"]["comparator_output_rise"] = {
            "missing_cycles": 3, "multiple_cycles": 2
        }
        check = runner.event_multiplicity_check(summary)
        self.assertTrue(check["required_events_no_missing_or_multiple"])
        self.assertFalse(check["diagnostic_only"]["comparator_output_rise"]["hard_gate"])

        summary["event_multiplicity"]["u5_toff_0p5V_rise"]["multiple_cycles"] = 1
        self.assertFalse(
            runner.event_multiplicity_check(summary)["required_events_no_missing_or_multiple"]
        )
        summary["event_multiplicity"]["u5_toff_0p5V_rise"]["multiple_cycles"] = 0
        summary["event_multiplicity"]["gate_l_rise"]["missing_cycles"] = 1
        self.assertFalse(
            runner.event_multiplicity_check(summary)["required_events_no_missing_or_multiple"]
        )

    def test_run_configuration_check_rejects_wrong_step_or_parameters(self):
        summary = {
            "analysis_window_s": [0.024, 0.026],
            "run_parameters": {
                "max_step_ns": 50,
                "solver_label": "Gear",
                "rfsw_ohm": 324000.0,
                "cfsw_f": 23e-12,
                "roff_ohm": 1e6,
            },
        }
        self.assertTrue(runner.run_configuration_check(summary, 50)["match"])
        self.assertFalse(runner.run_configuration_check(summary, 25)["match"])
        summary["run_parameters"]["rfsw_ohm"] = 510000.0
        self.assertFalse(runner.run_configuration_check(summary, 50)["match"])

    def test_prescribed_frequency_check_requires_valid_timing_and_frequency(self):
        summary = {
            "prescribed_edge_measurement": {
                "timing_valid": True,
                "frequency_kHz": 442.3,
            }
        }
        self.assertTrue(runner.prescribed_frequency_check(summary)["match"])
        summary["prescribed_edge_measurement"]["timing_valid"] = False
        self.assertFalse(runner.prescribed_frequency_check(summary)["match"])
        summary["prescribed_edge_measurement"]["timing_valid"] = True
        summary["prescribed_edge_measurement"]["frequency_kHz"] = None
        self.assertFalse(runner.prescribed_frequency_check(summary)["match"])

    def test_expected_cycle_accounting_is_exact(self):
        summary = {
            "cycle_accounting": {
                "candidate_cycles": 884,
                "complete_valid_cycles": 883,
                "right_censored_cycles": 1,
                "invalid_cycles": 0,
            }
        }
        check = runner.cycle_accounting_check(summary, 50)
        self.assertTrue(check["match"])
        summary["cycle_accounting"]["invalid_cycles"] = 1
        self.assertFalse(runner.cycle_accounting_check(summary, 50)["match"])

    def test_event_completeness_gates_primary_events_not_diagnostic_comparator(self):
        summary = {
            "cycle_accounting": {"complete_valid_cycles": 2},
            "event_completeness": {
                "pvin_cross_s": 2,
                "comparator_output_rise_s": 0,
                "u5_toff_0p5V_rise_s": 2,
                "gate_l_rise_s": 2,
                "cap_reset_0p5V_fall_s": 2,
                "sw_fall_10V_s": 2,
            },
        }
        check = runner.event_completeness_check(summary)
        self.assertTrue(check["all_required_event_counts_cover_valid_cycles"])
        self.assertEqual(check["diagnostic_only_event_counts"]["comparator_output_rise_s"], 0)
        summary["event_completeness"]["u5_toff_0p5V_rise_s"] = 1
        self.assertFalse(
            runner.event_completeness_check(summary)["all_required_event_counts_cover_valid_cycles"]
        )


if __name__ == "__main__":
    unittest.main()
