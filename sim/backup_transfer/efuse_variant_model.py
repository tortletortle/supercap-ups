"""Behavioral model for TPS25947 eFuse variants in the backup path."""
from __future__ import annotations
from dataclasses import dataclass

# TPS25947 Rev C, May 2026.
PG_RISE_MIN_V, PG_RISE_MAX_V = 1.183, 1.223
PG_FALL_MIN_V, PG_FALL_MAX_V = 1.076, 1.116
PG_DEGLITCH_TYP_US = 12.0  # typical only; no maximum specified
R_ILM_1650_OHM = 1650.0
ILIM_1650_MIN_A, ILIM_1650_TYP_A, ILIM_1650_MAX_A = 1.800, 2.028, 2.200


def pg_corner_state(pgth_v: float, *, previous_pg: bool,
                    path_fully_on: bool = True, inrush_complete: bool = True,
                    non_overcurrent_fault: bool = False) -> bool | None:
    """Return guaranteed PG state; None means threshold-corner dependent.

    PGTH must sense eFuse OUT when it qualifies delivered output.
    """
    if not path_fully_on or not inrush_complete or non_overcurrent_fault:
        return False
    if previous_pg:
        if pgth_v < PG_FALL_MIN_V:
            return False
        if pgth_v >= PG_FALL_MAX_V:
            return True
        return None
    if pgth_v > PG_RISE_MAX_V:
        return True
    if pgth_v <= PG_RISE_MIN_V:
        return False
    return None


def internal_latch_474l(event: str) -> bool:
    """Persistent breaker overload/OTP latch; output short does not."""
    return event in {"persistent_overload", "overtemperature"}


def backup_ready_qualified(*, arm_latched: bool, pack_uv_ok: bool,
                           cell_protect_valid: bool, boost_input_window_ok: bool,
                           boost_output_window_ok: bool, efuse_power_valid: bool,
                           pg_valid: bool) -> bool:
    return all((arm_latched, pack_uv_ok, cell_protect_valid,
                boost_input_window_ok, boost_output_window_ok,
                efuse_power_valid, pg_valid))


@dataclass
class BackupReadyLatch:
    """A lost READY after qualification latches until ARM low then high."""
    armed: bool = False
    ready: bool = False
    ready_seen: bool = False
    fault_latched: bool = False
    arm_low_seen: bool = True

    def _trip(self):
        self.ready = False
        self.ready_seen = False
        self.armed = False
        self.fault_latched = True
        self.arm_low_seen = False

    def update(self, *, arm_request: bool, pack_uv_ok: bool,
               cell_protect_valid: bool, boost_input_window_ok: bool,
               boost_output_window_ok: bool, efuse_power_valid: bool,
               pg_valid: bool) -> bool:
        safety_ok = pack_uv_ok and cell_protect_valid
        if not arm_request:
            self.ready = self.ready_seen = self.armed = False
            self.arm_low_seen = True
            if safety_ok:
                self.fault_latched = False
            return False
        if self.fault_latched:
            return False
        if not self.armed:
            if not self.arm_low_seen or not safety_ok:
                return False
            self.armed = True
            self.arm_low_seen = False
        if not safety_ok:
            self._trip()
            return False
        qualified = backup_ready_qualified(
            arm_latched=True, pack_uv_ok=pack_uv_ok,
            cell_protect_valid=cell_protect_valid,
            boost_input_window_ok=boost_input_window_ok,
            boost_output_window_ok=boost_output_window_ok,
            efuse_power_valid=efuse_power_valid, pg_valid=pg_valid)
        if not qualified:
            if self.ready_seen:
                self._trip()
            else:
                self.ready = False
            return False
        self.ready = self.ready_seen = True
        return True
