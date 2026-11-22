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

    def test_inventory_selects_50ns_and_25ns_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inventory.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=("max_step_ns", "path", "bytes", "sha256")
                )
                writer.writeheader()
                writer.writerow({"max_step_ns": "50", "path": "a.raw", "bytes": "10", "sha256": "a"})
                writer.writerow({"max_step_ns": "25", "path": "b.raw", "bytes": "20", "sha256": "b"})
                writer.writerow({"max_step_ns": "12.5", "path": "c.raw", "bytes": "30", "sha256": "c"})
            rows = runner.load_inventory_rows(path)
            self.assertEqual(set(rows), {50, 25})
            self.assertEqual(rows[50]["path"], "a.raw")
            self.assertEqual(rows[25]["path"], "b.raw")

    def test_inventory_rejects_duplicate_step(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inventory.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=("max_step_ns", "path", "bytes", "sha256")
                )
                writer.writeheader()
                for raw_path in ("a.raw", "b.raw"):
                    writer.writerow({
                        "max_step_ns": "50",
                        "path": raw_path,
                        "bytes": "10",
                        "sha256": "a",
                    })
                writer.writerow({
                    "max_step_ns": "25", "path": "c.raw", "bytes": "20", "sha256": "b"
                })
            with self.assertRaisesRegex(ValueError, "Duplicate 50 ns"):
                runner.load_inventory_rows(path)

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

    def test_event_completeness_must_cover_every_valid_cycle(self):
        summary = {
            "cycle_accounting": {"complete_valid_cycles": 2},
            "event_completeness": {
                "pvin_cross_s": 2,
                "comparator_output_rise_s": 2,
                "u5_toff_0p5V_rise_s": 2,
                "gate_l_rise_s": 2,
                "cap_reset_0p5V_fall_s": 2,
                "sw_fall_10V_s": 2,
            },
        }
        self.assertTrue(
            runner.event_completeness_check(summary)["all_event_counts_cover_valid_cycles"]
        )
        summary["event_completeness"]["u5_toff_0p5V_rise_s"] = 1
        self.assertFalse(
            runner.event_completeness_check(summary)["all_event_counts_cover_valid_cycles"]
        )


if __name__ == "__main__":
    unittest.main()
