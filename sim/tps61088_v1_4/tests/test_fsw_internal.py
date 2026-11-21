"""Tests for internal FSW timing analysis and LTspice RAW parsing."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
V14_ROOT = HERE.parents[1]
SCRIPTS = V14_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analyze_fsw_internal as fsw
from ltspice_raw import load_raw


class CrossingTests(unittest.TestCase):
    def test_linear_interpolation_and_direction(self):
        t = np.array([0.0, 1.0, 2.0, 3.0])
        y = np.array([0.0, 2.0, 2.0, 0.0])
        rise = fsw.crossings(t, y, 1.0, "rise")
        fall = fsw.crossings(t, y, 1.0, "fall")
        np.testing.assert_allclose(rise, [0.5])
        np.testing.assert_allclose(fall, [2.5])

    def test_hysteresis_suppresses_ringing_retrigger(self):
        t = np.arange(9, dtype=float)
        y = np.array([0.0, 11.0, 12.0, 9.0, 11.0, 5.0, 1.0, 11.0, 12.0])
        accepted, rejected = fsw.hysteretic_rising_crossings(
            t, y, high=10.0, rearm=2.0
        )
        self.assertEqual(len(accepted), 2)
        self.assertEqual(rejected, 1)
        self.assertLess(accepted[0], accepted[1])

    def test_first_between_is_half_open(self):
        events = np.array([1.0, 2.0, 3.0])
        self.assertEqual(fsw.first_between(events, 2.0, 3.0), 2.0)
        self.assertEqual(fsw.first_between(events, 3.0, 4.0), 3.0)
        self.assertIsNone(fsw.first_between(events, 2.0, 2.0))


class RcModelTests(unittest.TestCase):
    def test_piecewise_linear_integrator_matches_constant_input_solution(self):
        rfsw, roff, capacitance = 324e3, 1e6, 23e-12
        duration = 100e-9
        t = np.array([0.0, duration])
        sw = np.array([7.0, 7.0])
        _, cap = fsw.integrate_rc_piecewise_linear(
            t, sw, 0.0, 0.0, duration, rfsw, roff, capacitance
        )
        req = 1.0 / (1.0 / rfsw + 1.0 / roff)
        tau = req * capacitance
        v_inf = 7.0 * req / rfsw
        expected = v_inf * (1.0 - np.exp(-duration / tau))
        self.assertAlmostEqual(float(cap[-1]), float(expected), places=12)

    def test_predicted_threshold_crossing_matches_closed_form(self):
        rfsw, roff, capacitance = 324e3, 1e6, 23e-12
        threshold = 1.5
        t = np.linspace(0.0, 4e-6, 4001)
        sw = np.full_like(t, 7.0)
        pvin = np.full_like(t, threshold)
        cap = np.zeros_like(t)
        predicted = fsw.predict_rc_crossing(
            t, sw, pvin, cap, t[0], t[-1], rfsw, roff, capacitance
        )
        req = 1.0 / (1.0 / rfsw + 1.0 / roff)
        tau = req * capacitance
        v_inf = 7.0 * req / rfsw
        expected = -tau * np.log(1.0 - threshold / v_inf)
        self.assertIsNotNone(predicted)
        self.assertLess(abs(predicted - expected), 2e-9)

    def test_capacitance_estimate_requires_reset_switch_off(self):
        t = np.linspace(0.0, 1e-6, 101)
        cap = np.linspace(0.2, 0.8, len(t))
        capacitance = 23e-12
        current = (np.full_like(t, capacitance * (cap[-1] - cap[0]) / (t[-1] - t[0])) + cap / 1e6)
        mask = np.ones(len(t), dtype=bool)
        gate = np.zeros_like(t)
        estimate, low_fraction = fsw.estimate_capacitance(
            t, cap, current, gate, mask, 1e6
        )
        self.assertEqual(low_fraction, 1.0)
        self.assertAlmostEqual(estimate, capacitance, places=12)
        gate[50] = 1.0
        estimate, low_fraction = fsw.estimate_capacitance(
            t, cap, current, gate, mask, 1e6
        )
        self.assertIsNone(estimate)
        self.assertLess(low_fraction, 1.0)


class RawReaderTests(unittest.TestCase):
    def test_reads_interleaved_double_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "synthetic.raw"
            header = (
                "Title: synthetic\n"
                "Plotname: Transient Analysis\n"
                "Flags: real double\n"
                "No. Variables: 2\n"
                "No. Points: 3\n"
                "Variables:\n"
                "\t0\ttime\ttime\n"
                "\t1\tV(sw)\tvoltage\n"
                "Binary:\n"
            )
            values = np.array(
                [[0.0, 0.0], [1e-6, 5.0], [2e-6, 10.0]], dtype="<f8"
            )
            path.write_bytes(header.encode("utf-16le") + values.tobytes())
            decoded, names, raw = load_raw(path)
            try:
                self.assertIn("Plotname: Transient Analysis", decoded)
                self.assertEqual(names, ["time", "V(sw)"])
                np.testing.assert_allclose(np.asarray(raw), values)
            finally:
                # Windows cannot remove the temporary RAW while it is mapped.
                raw._mmap.close()

    def test_rejects_fastaccess_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fastaccess.raw"
            header = (
                "Title: synthetic\n"
                "Plotname: Transient Analysis\n"
                "Flags: real double fastaccess\n"
                "No. Variables: 1\n"
                "No. Points: 1\n"
                "Variables:\n"
                "\t0\ttime\ttime\n"
                "Binary:\n"
            )
            path.write_bytes(header.encode("utf-16le") + np.array([0.0], dtype="<f8").tobytes())
            with self.assertRaisesRegex(ValueError, "fastaccess"):
                load_raw(path)


class DeckAndComparisonTests(unittest.TestCase):
    def test_50ns_and_25ns_decks_have_identical_electrical_netlists(self):
        diag = V14_ROOT / "diagnostics"
        deck50 = (diag / "freq_vin7_rfsw324k_internal_probe_50ns.cir").read_text(
            encoding="utf-8"
        )
        deck25 = (diag / "freq_vin7_rfsw324k_internal_probe_25ns.cir").read_text(
            encoding="utf-8"
        )

        def normalize(deck):
            lines = [
                line.strip() for line in deck.splitlines()
                if line.strip() and not line.lstrip().startswith("*")
            ]
            return [
                ".tran 0 26m 0 MAXSTEP" if line.lower().startswith(".tran ") else line
                for line in lines
            ]

        self.assertEqual(normalize(deck50), normalize(deck25))

    def test_distribution_comparison_uses_medians(self):
        def stat(median):
            return {
                "count": 10, "min": median - 1, "p05": median - 0.9,
                "median": median, "mean": median, "p95": median + 0.9,
                "max": median + 1, "std": 0.5,
            }

        baseline = {
            "raw_path": "baseline.raw",
            "run_parameters": {"rfsw_ohm": 324e3, "cfsw_f": 23e-12, "roff_ohm": 1e6},
            "cycle_accounting": {"complete_valid_cycles": 10},
            "prescribed_edge_measurement": {"frequency_kHz": 442.0},
            "cycle_statistics": {"cross_to_sw_fall_s": stat(110e-9)},
        }
        current = {
            "raw_path": "fine.raw",
            "run_parameters": {"rfsw_ohm": 324e3, "cfsw_f": 23e-12, "roff_ohm": 1e6},
            "cycle_accounting": {"complete_valid_cycles": 10},
            "prescribed_edge_measurement": {"frequency_kHz": 441.0},
            "cycle_statistics": {"cross_to_sw_fall_s": stat(111e-9)},
        }
        result = fsw.compare_summaries(current, baseline)
        self.assertTrue(result["same_electrical_parameters"])
        self.assertEqual(result["frequency_delta_khz"], -1.0)
        self.assertAlmostEqual(
            result["distribution_deltas"]["cross_to_sw_fall_s"]["median_delta"],
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
