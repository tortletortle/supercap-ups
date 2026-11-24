import unittest

from model import (
    Scenario,
    analytic_general,
    analytic_hold_time,
    output_operating_point,
    simulate,
)


def base(**kwargs):
    values = {"name": "baseline"}
    values.update(kwargs)
    return Scenario(**values)


class EnergyBudgetTests(unittest.TestCase):
    def test_baseline_exact_reproduction(self):
        s = base()
        analytic = analytic_hold_time(s)
        numeric = simulate(s)
        self.assertAlmostEqual(analytic["hold_s"], 1.3748025771548633, places=10)
        self.assertAlmostEqual(numeric["hold_s"], analytic["hold_s"], delta=1e-8)
        self.assertEqual(numeric["stop_reason"], "BOOST_INPUT_FLOOR")
        self.assertAlmostEqual(numeric["minimum_boost_input_v"], 7.0, places=8)

    def test_joint_degradation_exact_reproduction(self):
        s = base(
            name="joint_degradation",
            cell_caps_f=(10.8,) * 4,
            cell_esrs_ohm=(0.110,) * 4,
            boost_efficiency=0.83,
            input_path_ohm=0.120,
        )
        result = analytic_hold_time(s)
        self.assertAlmostEqual(result["hold_s"], 1.1462287868163392, places=10)
        self.assertLess(result["hold_s"], 1.2)

    def test_1p144457_is_a_different_parameter_combination(self):
        # This is the separate V1.4 sensitivity row: 11.2 F, 106 mOhm,
        # 83% efficiency and 150 mOhm input path, not the 10.8/110/120 case.
        s = base(name="alternate", boost_efficiency=0.83, input_path_ohm=0.150)
        result = analytic_hold_time(s)
        self.assertAlmostEqual(result["hold_s"], 1.1444568315153263, places=9)
        self.assertNotAlmostEqual(result["hold_s"], 1.1462287868163392, places=6)

    def test_weak_cell_cuv_preempts_boost_floor(self):
        s = base(
            name="weak_cell",
            initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
        )
        result = simulate(s)
        self.assertEqual(result["stop_reason"], "CELL_UV")
        self.assertAlmostEqual(result["hold_s"], 1.1359367287290603, places=8)
        self.assertGreater(result["end_state"]["vin_boost_v"], 7.0)
        self.assertGreater(result["end_state"]["pack_terminal_v"], s.pack_uvlo_v)

    def test_protection_delay_is_reported_separately(self):
        s = base(
            name="weak_cell_delay",
            initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
            cell_uv_delay_s=0.00406,
        )
        result = simulate(s)
        self.assertEqual(result["stop_reason"], "CELL_UV_ISOLATION")
        self.assertAlmostEqual(result["threshold_crossing_time_s"], 1.1359367287290603, places=8)
        self.assertAlmostEqual(result["physical_isolation_time_s"], 1.1399967287290602, places=8)
        self.assertGreater(result["minimum_cell_terminal_v"], 1.0)

    def test_joint_degradation_plus_weak_cell_fails_earlier(self):
        s = base(
            name="joint_weak",
            cell_caps_f=(10.8,) * 4,
            cell_esrs_ohm=(0.110,) * 4,
            initial_cells_v=(1.45, 2.5166666666667, 2.5166666666667, 2.5166666666667),
            boost_efficiency=0.83,
            input_path_ohm=0.120,
        )
        result = simulate(s)
        self.assertEqual(result["stop_reason"], "CELL_UV")
        self.assertAlmostEqual(result["hold_s"], 0.9773923320026149, places=7)
        self.assertLess(result["hold_s"], 1.2)

    def test_capacity_mismatch_series_equivalent(self):
        caps = (11.2 / 1.08, 11.2, 11.2, 11.2)
        analytic = analytic_general(caps, (0.106,) * 4, (2.25,) * 4, base())
        numeric = simulate(base(name="mismatch", cell_caps_f=caps))
        self.assertAlmostEqual(numeric["hold_s"], analytic, delta=1e-8)
        self.assertAlmostEqual(numeric["hold_s"], 1.3478456638772025, places=7)

    def test_energy_balance_closes(self):
        result = simulate(base())
        self.assertLess(abs(result["energy_balance_residual_j"]), 1e-7)
        self.assertGreater(result["energies_j"]["load"], 0)

    def test_output_path_and_load_modes_are_not_conflated(self):
        regulated = output_operating_point(base())
        fixed_12v_1a = output_operating_point(base(
            name="fixed", load_mode="boost_fixed_12v_1a"
        ))
        fixed_12v_12w = output_operating_point(base(
            name="constant_power", load_mode="boost_fixed_12v_constant_power"
        ))
        self.assertAlmostEqual(regulated["load_voltage_v"], 12.0, places=12)
        self.assertAlmostEqual(regulated["boost_output_voltage_v"], 12.145, places=12)
        self.assertAlmostEqual(fixed_12v_1a["load_voltage_v"], 11.855, places=12)
        self.assertAlmostEqual(fixed_12v_1a["load_power_w"], 11.855, places=12)
        self.assertAlmostEqual(fixed_12v_12w["load_power_w"], 12.0, places=12)
        self.assertAlmostEqual(fixed_12v_12w["load_voltage_v"], 11.85320425066476, places=10)

    def test_monotonicity_and_input_validation(self):
        t_base = analytic_hold_time(base())["hold_s"]
        t_low_cap = analytic_hold_time(base(cell_caps_f=(10.0,) * 4))["hold_s"]
        t_low_eta = analytic_hold_time(base(boost_efficiency=0.80))["hold_s"]
        t_high_rin = analytic_hold_time(base(input_path_ohm=0.15))["hold_s"]
        self.assertLess(t_low_cap, t_base)
        self.assertLess(t_low_eta, t_base)
        self.assertLess(t_high_rin, t_base)
        with self.assertRaises(ValueError):
            analytic_hold_time(base(boost_efficiency=1.1))


if __name__ == "__main__":
    unittest.main()
