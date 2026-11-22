import unittest

from compare_storage_architectures import (
    DESIGNS,
    minimum_efficiency_for_task,
    pack_equivalent,
    simulate,
)


class ArchitectureModelTests(unittest.TestCase):
    def test_eol_series_equivalents(self):
        c_eq, r_pack = pack_equivalent(DESIGNS["4S10F_HCC"], 0.63, 2.0)
        self.assertAlmostEqual(c_eq, 1.575, places=9)
        self.assertAlmostEqual(r_pack, 0.520, places=9)

        c_eq, r_pack = pack_equivalent(DESIGNS["2S30F_KAM_HP_44"], 0.70, 4.0)
        self.assertAlmostEqual(c_eq, 10.5, places=9)
        self.assertAlmostEqual(r_pack, 0.352, places=9)

        c_eq, r_pack = pack_equivalent(DESIGNS["2S30F_KAM_HP_40"], 0.70, 4.0)
        self.assertAlmostEqual(c_eq, 10.5, places=9)
        self.assertAlmostEqual(r_pack, 0.320, places=9)

        c_eq, r_pack = pack_equivalent(DESIGNS["2S25F_KAM_LR"], 0.70, 4.0)
        self.assertAlmostEqual(c_eq, 8.75, places=9)
        self.assertAlmostEqual(r_pack, 0.200, places=9)

    def test_92_percent_eol_hold_times(self):
        hcc = simulate(DESIGNS["4S10F_HCC"], 0.63, 2.0, 0.92, dt_s=1e-5)
        hp = simulate(DESIGNS["2S30F_KAM_HP_44"], 0.70, 4.0, 0.92, dt_s=1e-5)
        hp40 = simulate(DESIGNS["2S30F_KAM_HP_40"], 0.70, 4.0, 0.92, dt_s=1e-5)
        lr = simulate(DESIGNS["2S25F_KAM_LR"], 0.70, 4.0, 0.92, dt_s=1e-5)

        self.assertAlmostEqual(hcc["hold_s"], 1.32676, delta=0.001)
        self.assertAlmostEqual(hp["hold_s"], 0.94782, delta=0.001)
        self.assertAlmostEqual(hp40["hold_s"], 1.37606, delta=0.001)
        self.assertAlmostEqual(lr["hold_s"], 2.58753, delta=0.001)
        self.assertTrue(hcc["task_pass"])
        self.assertFalse(hp["task_pass"])
        self.assertTrue(hp40["task_pass"])
        self.assertTrue(lr["task_pass"])

    def test_corrected_30f_esr_changes_the_result(self):
        design = DESIGNS["2S30F_KAM_HP_44"]
        corrected = simulate(design, 0.70, 4.0, 0.92, dt_s=1e-5)
        old_esr = dict(design)
        old_esr["cell_dc_esr_ohm"] = 0.035
        old_assumption = simulate(old_esr, 0.70, 4.0, 0.92, dt_s=1e-5)

        self.assertLess(corrected["hold_s"], 1.0)
        self.assertGreater(old_assumption["hold_s"], 1.2)

        lower_esr_variant = simulate(
            DESIGNS["2S30F_KAM_HP_40"], 0.70, 4.0, 0.92, dt_s=1e-5
        )
        self.assertGreater(lower_esr_variant["hold_s"], 1.2)

    def test_25f_minus_10_percent_capacity_sensitivity(self):
        result = simulate(
            DESIGNS["2S25F_KAM_LR"], 0.63, 4.0, 0.92, dt_s=1e-5
        )
        self.assertGreater(result["hold_s"], 1.2)

    def test_energy_balance(self):
        for design_id, design in DESIGNS.items():
            cap_factor = (
                design["capacity_tolerance_min"] * design["life_cap_factor"]
            )
            result = simulate(
                design, cap_factor, design["life_esr_factor"], 0.92, dt_s=1e-5
            )
            self.assertLess(
                abs(result["energy_balance_error_j"]), 1e-4, design_id
            )

    def test_timestep_convergence(self):
        for design_id, design in DESIGNS.items():
            cap_factor = (
                design["capacity_tolerance_min"] * design["life_cap_factor"]
            )
            coarse = simulate(
                design, cap_factor, design["life_esr_factor"], 0.92, dt_s=1e-4
            )
            fine = simulate(
                design, cap_factor, design["life_esr_factor"], 0.92, dt_s=5e-5
            )
            self.assertLess(
                abs(coarse["hold_s"] - fine["hold_s"]), 1.1e-4, design_id
            )

    def test_minimum_efficiency_thresholds(self):
        hcc_eta = minimum_efficiency_for_task(
            DESIGNS["4S10F_HCC"], 0.63, 2.0, 1.2
        )
        hp_eta = minimum_efficiency_for_task(
            DESIGNS["2S30F_KAM_HP_44"], 0.70, 4.0, 1.2
        )
        hp40_eta = minimum_efficiency_for_task(
            DESIGNS["2S30F_KAM_HP_40"], 0.70, 4.0, 1.2
        )
        lr_eta = minimum_efficiency_for_task(
            DESIGNS["2S25F_KAM_LR"], 0.70, 4.0, 1.2
        )

        self.assertAlmostEqual(hcc_eta, 0.8696, delta=0.002)
        self.assertAlmostEqual(hp_eta, 0.9614, delta=0.002)
        self.assertAlmostEqual(hp40_eta, 0.8917, delta=0.002)
        self.assertAlmostEqual(lr_eta, 0.6663, delta=0.002)


if __name__ == "__main__":
    unittest.main()
