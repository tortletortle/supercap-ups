import math
import unittest
from dataclasses import replace

from backup_ready_supervisor import (
    BackupInputs,
    BackupReadySupervisor,
    EfuseStatus,
    EfuseVariant,
)


GOOD_470A = EfuseStatus(
    variant=EfuseVariant.TPS259470A,
    input_supply_valid=True,
    logic_supply_valid=True,
    auxoff_high=True,
    flt_high=True,
)
GOOD_474L = EfuseStatus(
    variant=EfuseVariant.TPS259474L,
    input_supply_valid=True,
    logic_supply_valid=True,
    pg_high=True,
)
GOOD = BackupInputs(
    cell_permit=True,
    pack_uv_ok=True,
    boost_enabled=True,
    boost_input_window_ok=True,
    boost_output_window_ok=True,
    efuse_status=GOOD_470A,
    path_proof_ok=True,
    path_proof_age_s=0.01,
    path_proof_max_age_s=0.1,
)


def arm_ready(supervisor=None, inputs=GOOD):
    supervisor = supervisor or BackupReadySupervisor()
    supervisor.update(arm_request=False, inputs=inputs)
    assert supervisor.update(arm_request=True, inputs=inputs)
    return supervisor


class BackupReadySupervisorTests(unittest.TestCase):
    def test_reset_defaults_to_inhibit(self):
        supervisor = BackupReadySupervisor()
        self.assertFalse(supervisor.ready)
        self.assertTrue(supervisor.ov2_inhibit)
        self.assertFalse(supervisor.update(arm_request=True, inputs=GOOD))

    def test_all_required_qualifiers_are_mandatory(self):
        cases = (
            replace(GOOD, cell_permit=False),
            replace(GOOD, pack_uv_ok=False),
            replace(GOOD, boost_enabled=False),
            replace(GOOD, boost_input_window_ok=False),
            replace(GOOD, boost_output_window_ok=False),
            replace(GOOD, path_proof_ok=False),
            replace(GOOD, path_proof_age_s=0.101),
            replace(GOOD, efuse_status=EfuseStatus()),
        )
        for case in cases:
            with self.subTest(case=case):
                supervisor = arm_ready()
                self.assertFalse(supervisor.update(arm_request=True, inputs=case))
                self.assertFalse(supervisor.ready)
                self.assertTrue(supervisor.ov2_inhibit)

    def test_470a_status_is_not_a_power_path_proof(self):
        self.assertTrue(GOOD_470A.status_ok)
        inputs = replace(GOOD, path_proof_ok=False)
        supervisor = arm_ready()
        self.assertFalse(supervisor.update(arm_request=True, inputs=inputs))
        self.assertFalse(supervisor.ready)
        self.assertTrue(supervisor.ov2_inhibit)

    def test_474l_pg_is_not_a_power_path_proof(self):
        # Residual OUT capacitance can keep PGTH above the falling threshold.
        self.assertTrue(GOOD_474L.status_ok)
        inputs = replace(GOOD, efuse_status=GOOD_474L, path_proof_ok=False)
        supervisor = arm_ready()
        self.assertFalse(supervisor.update(arm_request=True, inputs=inputs))
        self.assertFalse(supervisor.ready)
        self.assertTrue(supervisor.ov2_inhibit)

    def test_unpowered_open_drain_status_cannot_qualify(self):
        unpowered_input_470a = replace(GOOD_470A, input_supply_valid=False)
        unpowered_input_474l = replace(GOOD_474L, input_supply_valid=False)
        unpowered_logic_470a = replace(GOOD_470A, logic_supply_valid=False)
        unpowered_logic_474l = replace(GOOD_474L, logic_supply_valid=False)
        for status in (
            unpowered_input_470a,
            unpowered_input_474l,
            unpowered_logic_470a,
            unpowered_logic_474l,
        ):
            with self.subTest(status=status):
                self.assertFalse(status.status_ok)

    def test_470a_active_low_fault_pin_blocks_status(self):
        self.assertFalse(replace(GOOD_470A, flt_high=False).status_ok)
        self.assertFalse(replace(GOOD_470A, auxoff_high=False).status_ok)

    def test_474l_low_pg_blocks_status(self):
        self.assertFalse(replace(GOOD_474L, pg_high=False).status_ok)

    def test_arm_high_at_reset_cannot_arm_after_safety_recovers(self):
        supervisor = BackupReadySupervisor()
        unsafe = replace(GOOD, cell_permit=False)
        self.assertFalse(supervisor.update(arm_request=True, inputs=unsafe))
        # Keeping ARM high while CELL_PERMIT recovers is not a new edge.
        self.assertFalse(supervisor.update(arm_request=True, inputs=GOOD))
        self.assertFalse(supervisor.armed)
        # A sampled low then a new high is required.
        self.assertFalse(supervisor.update(arm_request=False, inputs=GOOD))
        self.assertTrue(supervisor.update(arm_request=True, inputs=GOOD))

    def test_ready_loss_latches_until_safe_low_then_fresh_high(self):
        supervisor = arm_ready()
        faulted = replace(GOOD, boost_output_window_ok=False)
        self.assertFalse(supervisor.update(arm_request=True, inputs=faulted))
        self.assertTrue(supervisor.fault_latched)
        self.assertFalse(supervisor.update(arm_request=True, inputs=GOOD))
        self.assertFalse(supervisor.update(arm_request=False, inputs=GOOD))
        self.assertFalse(supervisor.fault_latched)
        self.assertTrue(supervisor.update(arm_request=True, inputs=GOOD))

    def test_fault_during_unsafe_low_does_not_clear_latch(self):
        supervisor = arm_ready()
        self.assertFalse(
            supervisor.update(arm_request=True, inputs=replace(GOOD, pack_uv_ok=False))
        )
        self.assertTrue(supervisor.fault_latched)
        self.assertFalse(
            supervisor.update(arm_request=False, inputs=replace(GOOD, pack_uv_ok=False))
        )
        self.assertTrue(supervisor.fault_latched)
        # Recovery while ARM is still high cannot re-arm.
        self.assertFalse(supervisor.update(arm_request=True, inputs=GOOD))
        # Low while safe clears the latch; only the next high re-arms.
        self.assertFalse(supervisor.update(arm_request=False, inputs=GOOD))
        self.assertFalse(supervisor.fault_latched)
        self.assertTrue(supervisor.update(arm_request=True, inputs=GOOD))

    def test_startup_waits_for_windows_but_timeout_latches(self):
        supervisor = BackupReadySupervisor()
        waiting = replace(GOOD, boost_output_window_ok=False)
        supervisor.update(arm_request=False, inputs=waiting)
        self.assertFalse(supervisor.update(arm_request=True, inputs=waiting))
        self.assertTrue(supervisor.armed)
        self.assertFalse(supervisor.fault_latched)
        self.assertFalse(
            supervisor.update(arm_request=True, inputs=replace(waiting, startup_timeout=True))
        )
        self.assertTrue(supervisor.fault_latched)

    def test_efuse_fault_event_latches(self):
        supervisor = arm_ready()
        self.assertFalse(
            supervisor.update(arm_request=True, inputs=replace(GOOD, efuse_fault_active=True))
        )
        self.assertTrue(supervisor.fault_latched)

    def test_external_fault_latches(self):
        supervisor = arm_ready()
        self.assertFalse(
            supervisor.update(arm_request=True, inputs=replace(GOOD, external_fault=True))
        )
        self.assertTrue(supervisor.fault_latched)

    def test_qualifier_may_arrive_after_arm_before_startup_timeout(self):
        supervisor = BackupReadySupervisor()
        waiting = replace(GOOD, boost_output_window_ok=False)
        supervisor.update(arm_request=False, inputs=waiting)
        self.assertFalse(supervisor.update(arm_request=True, inputs=waiting))
        self.assertTrue(supervisor.update(arm_request=True, inputs=GOOD))

    def test_path_proof_age_limit_is_inclusive(self):
        at_limit = replace(GOOD, path_proof_age_s=GOOD.path_proof_max_age_s)
        self.assertTrue(at_limit.path_proof_fresh)
        supervisor = arm_ready(inputs=at_limit)
        self.assertTrue(supervisor.ready)

    def test_missing_or_invalid_path_proof_age_fails_closed(self):
        cases = (
            replace(GOOD, path_proof_age_s=None),
            replace(GOOD, path_proof_max_age_s=None),
            replace(GOOD, path_proof_age_s=-0.001),
            replace(GOOD, path_proof_age_s=math.inf),
            replace(GOOD, path_proof_max_age_s=math.nan),
            replace(GOOD, path_proof_max_age_s=0.0),
        )
        for case in cases:
            with self.subTest(case=case):
                self.assertFalse(case.path_proof_fresh)
                supervisor = arm_ready()
                self.assertFalse(supervisor.update(arm_request=True, inputs=case))
                self.assertTrue(supervisor.ov2_inhibit)

    def test_path_proof_expiry_revokes_ready_and_latches(self):
        supervisor = arm_ready()
        stale = replace(GOOD, path_proof_age_s=GOOD.path_proof_max_age_s + 1e-9)
        self.assertFalse(supervisor.update(arm_request=True, inputs=stale))
        self.assertTrue(supervisor.fault_latched)

    def test_ov2_inhibit_is_inverse_of_ready(self):
        supervisor = arm_ready()
        self.assertTrue(supervisor.ready)
        self.assertFalse(supervisor.ov2_inhibit)
        supervisor.update(arm_request=True, inputs=replace(GOOD, cell_permit=False))
        self.assertFalse(supervisor.ready)
        self.assertTrue(supervisor.ov2_inhibit)


if __name__ == "__main__":
    unittest.main(verbosity=2)
