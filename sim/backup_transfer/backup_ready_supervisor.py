"""Fail-safe BACKUP_READY supervisor contract for the 4S supercap UPS.

This is a discrete-time behavioral contract, not a transistor-level or
vendor-macro model. It consumes CELL_PERMIT as an upstream interface and
does not reimplement the cell-protection module.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EfuseVariant(str, Enum):
    TPS259470A = "TPS259470A"
    TPS259474L = "TPS259474L"


@dataclass(frozen=True)
class EfuseStatus:
    """Variant-specific status pins plus validity of their monitor rail.

    470A AUXOFF/FLT and 474L PG are necessary status indications, but neither
    proves that the OUT power path can still deliver load current.
    """

    variant: EfuseVariant = EfuseVariant.TPS259470A
    monitor_power_ok: bool = False
    auxoff_high: bool | None = None
    flt_high: bool | None = None
    pg_high: bool | None = None

    @property
    def status_ok(self) -> bool:
        if not self.monitor_power_ok:
            # Do not interpret a floating open-drain output as READY.
            return False
        if self.variant is EfuseVariant.TPS259470A:
            return self.auxoff_high is True and self.flt_high is True
        if self.variant is EfuseVariant.TPS259474L:
            return self.pg_high is True
        return False


@dataclass(frozen=True)
class BackupInputs:
    """Inputs to the backup-source qualification contract.

    CELL_PERMIT is consumed as one upstream safety interface. This module
    must not bypass or recreate the cell-level protection logic.
    """

    cell_permit: bool = False
    pack_uv_ok: bool = False
    boost_enabled: bool = False
    boost_input_window_ok: bool = False
    boost_output_window_ok: bool = False
    efuse_status: EfuseStatus = EfuseStatus()
    path_proof_ok: bool = False
    path_proof_fresh: bool = False
    efuse_fault_active: bool = False
    external_fault: bool = False
    startup_timeout: bool = False

    @property
    def rearm_safe(self) -> bool:
        """Upstream safety conditions required to clear a latched fault.

        Boost output qualification is intentionally not required here because
        the Boost may need to start after the ARM edge. Safety permits and
        fault inputs must be healthy before re-arming.
        """
        return (
            self.cell_permit
            and self.pack_uv_ok
            and not self.efuse_fault_active
            and not self.external_fault
            and not self.startup_timeout
        )

    @property
    def all_ready_qualifiers(self) -> bool:
        return (
            self.cell_permit
            and self.pack_uv_ok
            and self.boost_enabled
            and self.boost_input_window_ok
            and self.boost_output_window_ok
            and self.efuse_status.status_ok
            and self.path_proof_ok
            and self.path_proof_fresh
            and not self.efuse_fault_active
            and not self.external_fault
            and not self.startup_timeout
        )


@dataclass
class BackupReadySupervisor:
    """ARM-edge-gated BACKUP_READY and fault-latch state machine.

    A sampled ARM low is required after reset and after every trip. An ARM
    high held across reset or fault recovery cannot silently re-arm the path.
    A previously qualified READY loss is latched until ARM is low while the
    upstream safety/fault inputs are healthy, followed by a fresh low-to-high
    ARM transition.
    """

    armed: bool = False
    ready: bool = False
    fault_latched: bool = False
    arm_low_seen: bool = False
    ready_seen: bool = False

    def _trip(self) -> None:
        self.armed = False
        self.ready = False
        self.ready_seen = False
        self.fault_latched = True
        self.arm_low_seen = False

    def update(self, *, arm_request: bool, inputs: BackupInputs) -> bool:
        """Advance the supervisor by one sampled control cycle."""
        if not arm_request:
            self.armed = False
            self.ready = False
            self.ready_seen = False
            self.arm_low_seen = True
            if inputs.rearm_safe:
                self.fault_latched = False
            return False

        # A high level at power-up or after a trip is not a new ARM edge.
        if self.fault_latched:
            return False

        if not self.armed:
            if not self.arm_low_seen:
                return False
            # Consume the observed low. If safety is not ready now, a later
            # recovery while ARM remains high must not create a new edge.
            self.arm_low_seen = False
            if not inputs.rearm_safe:
                return False
            self.armed = True

        # Hard safety/fault events trip even before the first READY assertion.
        if (
            not inputs.cell_permit
            or not inputs.pack_uv_ok
            or inputs.efuse_fault_active
            or inputs.external_fault
            or inputs.startup_timeout
        ):
            self._trip()
            return False

        if inputs.all_ready_qualifiers:
            self.ready = True
            self.ready_seen = True
            return True

        self.ready = False
        # A qualification loss after READY is a latched fault, not a transient
        # condition that may self-clear when residual voltage rebounds.
        if self.ready_seen:
            self._trip()
        return False

    @property
    def ov2_inhibit(self) -> bool:
        """Logical intent: high means TPS2121 IN2 must be denied."""
        return not self.ready
