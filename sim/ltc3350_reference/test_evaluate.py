import unittest

from evaluate import (
    Design,
    hold_time_s,
    input_charge_budget,
    required_vcap_v,
    shunt_budget,
    simulate_weak_cell_discharge,
    vcap_window,
    vout_window,
)


class LTC3350CandidateTests(unittest.TestCase):
    def setUp(self):
        self.design = Design()

    def test_vcap_divider_window(self):
        nominal, low, high, _ = vcap_window(self.design)
        self.assertAlmostEqual(nominal, 10.0067796610, places=8)
        self.assertAlmostEqual(low, 9.7823005085, places=8)
        self.assertAlmostEqual(high, 10.2312588136, places=8)

    def test_vout_stays_within_five_percent(self):
        nominal, low, high, _ = vout_window(self.design)
        self.assertAlmostEqual(nominal, 12.0, places=8)
        self.assertGreaterEqual(low, 11.4)
        self.assertLessEqual(high, 12.6)

    def test_worst_case_hold_time_exceeds_1p2s(self):
        _, low, _, _ = vcap_window(self.design)
        self.assertGreater(hold_time_s(low, self.design, 0.80), 1.2)
        self.assertGreater(required_vcap_v(1.2, self.design, 0.80), 9.4)

    def test_shunt_has_current_margin(self):
        _, min_shunt_current, _ = shunt_budget(self.design)
        charge = input_charge_budget(self.design)
        self.assertGreater(min_shunt_current, charge["pack_charge_current_no_load_a"])

    def test_equalized_weak_cell_case(self):
        _, low, _, _ = vcap_window(self.design)
        result = simulate_weak_cell_discharge(
            self.design,
            [6.3, 9.0, 9.0, 9.0],
            [0.1125, 0.075, 0.075, 0.075],
            low,
        )
        self.assertEqual(result["reason"], "pack-cutoff")
        self.assertGreater(result["min_cell_v"], 1.0)
        self.assertGreater(result["time_s"], 1.2)


if __name__ == "__main__":
    unittest.main()
