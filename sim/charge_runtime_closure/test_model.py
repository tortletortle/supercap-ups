import unittest

from model import (
    PackSpec,
    buck_output_corners_v,
    build_voltage_matrix,
    hold_time_s,
    minimum_initial_ocv_v,
    solve_loaded_state,
    worst_low_cv_if_high_corner_limited_v,
)


class ChargeRuntimeClosureTests(unittest.TestCase):
    def setUp(self):
        self.pack = PackSpec()

    def test_corrected_eol_pack_equivalents(self):
        self.assertAlmostEqual(self.pack.cell_eol_cap_f, 6.3, places=12)
        self.assertAlmostEqual(self.pack.pack_equivalent_cap_f, 1.575, places=12)
        self.assertAlmostEqual(self.pack.cell_eol_dc_esr_ohm, 0.130, places=12)
        self.assertAlmostEqual(self.pack.pack_dc_esr_ohm, 0.520, places=12)

    def test_92_percent_hold_time_matches_architecture_reconciliation(self):
        self.assertAlmostEqual(
            hold_time_s(9.4, 0.92, pack=self.pack),
            1.32675,
            delta=0.001,
        )

    def test_existing_nominal_buck_output_is_insufficient(self):
        # Treating Buck output as pack OCV is deliberately optimistic:
        # the blocking diode and current-sense path are not subtracted here.
        self.assertAlmostEqual(
            hold_time_s(9.059, 0.92, pack=self.pack),
            0.98371,
            delta=0.001,
        )
        self.assertLess(hold_time_s(9.059, 0.92, pack=self.pack), 1.2)

    def test_static_buck_output_corners(self):
        corners = buck_output_corners_v()
        self.assertAlmostEqual(corners["minimum_v"], 8.8147, delta=0.001)
        self.assertAlmostEqual(corners["nominal_v"], 9.0592, delta=0.001)
        self.assertAlmostEqual(corners["maximum_v"], 9.3046, delta=0.001)

        # These are Buck output values. Assuming zero series drop gives an
        # optimistic upper bound on the pack voltage and its hold time.
        self.assertLess(hold_time_s(corners["minimum_v"], 0.92), 0.75)
        self.assertLess(hold_time_s(corners["nominal_v"], 0.92), 1.0)
        self.assertGreater(hold_time_s(corners["maximum_v"], 0.92), 1.2)
        self.assertLess(hold_time_s(corners["maximum_v"], 0.90), 1.2)

    def test_required_initial_ocv_for_1p2s(self):
        expected = {
            0.90: 9.32347,
            0.92: 9.27577,
            0.94: 9.23000,
        }
        for efficiency, target in expected.items():
            with self.subTest(efficiency=efficiency):
                required = minimum_initial_ocv_v(
                    efficiency, pack=self.pack, maximum_pack_voltage_v=9.4
                )
                self.assertIsNotNone(required)
                self.assertAlmostEqual(required, target, delta=0.001)
                self.assertGreaterEqual(
                    hold_time_s(required, efficiency, pack=self.pack), 1.2
                )

    def test_voltage_limit_margin(self):
        required_90 = minimum_initial_ocv_v(0.90, pack=self.pack)
        required_92 = minimum_initial_ocv_v(0.92, pack=self.pack)
        self.assertAlmostEqual(9.4 - required_90, 0.07653, delta=0.001)
        self.assertAlmostEqual(9.4 - required_92, 0.12423, delta=0.001)

    def test_feedback_divider_scaled_to_9p4_still_has_large_low_corner(self):
        worst_low = worst_low_cv_if_high_corner_limited_v()
        self.assertAlmostEqual(worst_low, 8.9051, delta=0.001)
        self.assertLess(worst_low, minimum_initial_ocv_v(0.92, pack=self.pack))

    def test_no_operating_point_and_below_cutoff(self):
        self.assertIsNone(solve_loaded_state(5.0, 0.52, 12.0 / (0.92 * 0.99)))
        state = solve_loaded_state(7.0, 0.52, 12.0 / (0.92 * 0.99))
        self.assertIsNotNone(state)
        self.assertLess(state[1], self.pack.pack_cutoff_v)
        self.assertEqual(hold_time_s(7.0, 0.92, pack=self.pack), 0.0)

    def test_efficiency_and_initial_voltage_monotonicity(self):
        low = hold_time_s(9.2, 0.90, pack=self.pack)
        high = hold_time_s(9.2, 0.94, pack=self.pack)
        self.assertGreater(high, low)
        self.assertGreater(
            hold_time_s(9.3, 0.92, pack=self.pack),
            hold_time_s(9.2, 0.92, pack=self.pack),
        )

    def test_task_is_unreachable_if_maximum_charge_voltage_is_too_low(self):
        self.assertIsNone(
            minimum_initial_ocv_v(
                0.92, pack=self.pack, maximum_pack_voltage_v=9.0
            )
        )

    def test_voltage_matrix_has_all_declared_scenarios(self):
        rows = build_voltage_matrix(pack=self.pack)
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(1 for row in rows if row["pass_1p2s"]), 5)


if __name__ == "__main__":
    unittest.main()
