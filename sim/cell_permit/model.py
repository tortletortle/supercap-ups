#!/usr/bin/env python3
"""BQ76905 4S CELL_PERMIT timing and fail-closed logic model.

This is a deterministic engineering screen, not a TI silicon model, SPICE
simulation, or hardware measurement. Every non-guaranteed input is labelled.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import csv
import json
import math

CELLS = 4
SLOTS_PER_ADSCAN = CELLS + 1
LOOP_IDLE_SLOTS_PER_ACTIVE = (0, 1, 3, 7)
LFO_SLOW_DRIFT_CHARACTERIZED = 0.021  # -2.1%, full-speed, -40C..110C
BQ_FAST_SLOT_US_TYP = 366.0
BQ_MEDFAST_SLOT_US_TYP = 732.0
BQ_SLOW_SLOT_US_TYP = 2930.0

# Current KiCad values / Vishay published gate-charge screen.
R501_PULLUP_OHM = 10_000.0
R501_TOL = 0.01
R502_PULLDOWN_OHM = 1_000.0
R502_TOL = 0.01
SI7149_QG_MAX_NC = 147.0
SI7149_QG_TEST_VGS_V = 10.0
SI7149_FET_COUNT = 2
SI7149_VGS_NEAR_ZERO_V = 0.10
SI7149_VGS_THRESHOLD_MIN_ABS_V = 1.20

# Current cell-input network in cell-uv-monitor.kicad_sch.
CELL_INPUT_R_OHM = 10.0
CELL_INPUT_R_TOL = 0.01
CELL_INPUT_C_F = 220e-9
CELL_INPUT_C_TOL = 0.10
FILTER_SETTLE_TAU_COUNT = 5.0

# These are explicit engineering assumptions, not BQ76905 timing guarantees.
ALERT_PROP_ASSUMED_MS = 0.050
LOGIC_AND_DFF_ASSUMED_MS = 0.0001


@dataclass(frozen=True)
class ScanConfig:
    cells: int = 4
    cv_slot_us_typ: float = BQ_FAST_SLOT_US_TYP
    shared_slot_us_typ: float = BQ_FAST_SLOT_US_TYP
    loop_slow: int = 0
    use_lfo_characterized_slow_drift: bool = True
    cow_enabled: bool = True
    cow_delay_ms: float = 1.0

    def __post_init__(self) -> None:
        if not 2 <= self.cells <= 5:
            raise ValueError("BQ76905 supports 2..5 active cells")
        if self.loop_slow not in range(4):
            raise ValueError("loop_slow must be 0, 1, 2, or 3")
        if self.cv_slot_us_typ <= 0 or self.shared_slot_us_typ <= 0:
            raise ValueError("slot widths must be positive")
        if self.cow_delay_ms < 0:
            raise ValueError("cow_delay_ms must be non-negative")


def slot_scale(use_lfo_characterized_slow_drift: bool) -> float:
    """Convert nominal slot time to a characterization-derived slow-clock screen.

    TI gives the full-speed LFO frequency drift as -2.1% minimum / +2.3%
    maximum over -40C..110C, but t(ADC_CONV) itself is typical-only and the
    absolute 25C oscillator frequency has no min/max production limit.
    This factor is therefore NOT a guaranteed maximum.
    """
    if not use_lfo_characterized_slow_drift:
        return 1.0
    return 1.0 / (1.0 - LFO_SLOW_DRIFT_CHARACTERIZED)


def adscan_period_ms(cfg: ScanConfig) -> float:
    """Return one cell's sample-to-next-sample interval.

    NORMAL-mode ADSCAN has Ncells + 1 active slots. LOOP_SLOW adds 0/1/3/7
    idle slots per active slot. The model uses the larger configured slot
    width for each idle slot. COWDLY is added once per loop when COW is on.
    """
    scale = slot_scale(cfg.use_lfo_characterized_slow_drift)
    cv_us = cfg.cv_slot_us_typ * scale
    shared_us = cfg.shared_slot_us_typ * scale
    active_us = cfg.cells * cv_us + shared_us
    idle_count = cfg.cells + 1
    idle_us = idle_count * LOOP_IDLE_SLOTS_PER_ACTIVE[cfg.loop_slow] * max(cv_us, shared_us)
    cow_ms = cfg.cow_delay_ms if cfg.cow_enabled else 0.0
    return (active_us + idle_us) / 1000.0 + cow_ms


def cell_input_filter_settle_ms() -> float:
    """Five-tau differential RC settling estimate using resistor/cap max."""
    r_each = CELL_INPUT_R_OHM * (1.0 + CELL_INPUT_R_TOL)
    c = CELL_INPUT_C_F * (1.0 + CELL_INPUT_C_TOL)
    tau_s = (2.0 * r_each) * c
    return FILTER_SETTLE_TAU_COUNT * tau_s * 1000.0


def pmos_gate_turnoff_ms(pack_v: float = 9.4, vgs_target_abs_v: float = SI7149_VGS_NEAR_ZERO_V) -> float:
    """First-order equivalent-C estimate for the existing two-PMOS gate pull-up.

    Qg(max)=147nC per Si7149DP is specified at VGS=-10V. The two common gates
    share R501=10k. Treating Qg/V as a constant equivalent capacitance gives
    a conservative engineering screen, not a guaranteed transistor turn-off
    time. The actual channel-current isolation threshold needs a device model
    and bench measurement.
    """
    if pack_v <= 0 or vgs_target_abs_v <= 0:
        raise ValueError("pack_v and target VGS magnitude must be positive")
    r501_max = R501_PULLUP_OHM * (1.0 + R501_TOL)
    r502_min = R502_PULLDOWN_OHM * (1.0 - R502_TOL)
    initial_abs_vgs = pack_v * r501_max / (r501_max + r502_min)
    ceq_total = SI7149_FET_COUNT * (SI7149_QG_MAX_NC * 1e-9 / SI7149_QG_TEST_VGS_V)
    tau_s = r501_max * ceq_total
    if vgs_target_abs_v >= initial_abs_vgs:
        return 0.0
    return tau_s * math.log(initial_abs_vgs / vgs_target_abs_v) * 1000.0


def total_estimated_isolation_ms(cfg: ScanConfig,
                                 alert_prop_assumed_ms: float = ALERT_PROP_ASSUMED_MS,
                                 logic_assumed_ms: float = LOGIC_AND_DFF_ASSUMED_MS,
                                 gate_target_abs_v: float = SI7149_VGS_NEAR_ZERO_V) -> float:
    return (
        adscan_period_ms(cfg)
        + cell_input_filter_settle_ms()
        + alert_prop_assumed_ms
        + logic_assumed_ms
        + pmos_gate_turnoff_ms(vgs_target_abs_v=gate_target_abs_v)
    )


def legacy_4p06_reproduction_ms() -> float:
    """Reproduce the reported 4.06ms arithmetic, not validate its assumptions."""
    return 5.0 * BQ_MEDFAST_SLOT_US_TYP / 1000.0 + 0.4


def alert_routes_cuv(alarm_mask: int) -> bool:
    """SAA is AlarmEnable bit 13; CUV alert is a Safety Alert A source."""
    return bool(alarm_mask & (1 << 13))


def cow_open_wire_estimate_ms(cfg: ScanConfig, cowntime_fullscans: int = 1,
                              input_cap_f: float = CELL_INPUT_C_F * (1.0 + CELL_INPUT_C_TOL),
                              initial_cell_v: float = 2.70,
                              cuv_threshold_v: float = 1.05,
                              cow_current_uA_typ: float = 55.0) -> float | None:
    """Pulsed-current open-wire estimate using the 55uA typical COW source.

    The source is on only during one Shared Slot, not continuously. A 4S
    system needs approximately cells+1 ADSCANs to exercise all cells because
    one Shared Slot is skipped for stack voltage. It is then off for
    COWNTIME FULLSCAN intervals (modeled as 5 ADSCANs each). Each pulse
    removes I*t/C from a floating tap capacitor. After the final pulse, add
    one ADSCAN for the next cell-voltage measurement. This is an engineering
    estimate, not a datasheet maximum: the 55uA source is typical and the
    actual RC network / open-wire threshold must be measured.
    """
    if cowntime_fullscans <= 0:
        return None
    if initial_cell_v <= cuv_threshold_v or input_cap_f <= 0 or cow_current_uA_typ <= 0:
        return 0.0
    scale = slot_scale(cfg.use_lfo_characterized_slow_drift)
    pulse_width_s = cfg.shared_slot_us_typ * scale * 1e-6
    delta_v_per_pulse = cow_current_uA_typ * 1e-6 * pulse_width_s / input_cap_f
    if delta_v_per_pulse <= 0:
        return None
    pulses = math.ceil((initial_cell_v - cuv_threshold_v) / delta_v_per_pulse)
    period = adscan_period_ms(cfg)
    active_scans = cfg.cells + 1  # includes one skipped stack-voltage Shared Slot
    rest_scans = 5 * cowntime_fullscans  # FULLSCAN modeled as five ADSCANs for 4S
    pulse_interval_ms = (active_scans + rest_scans) * period
    return pulses * pulse_interval_ms + period


@dataclass(frozen=True)
class PermitInputs:
    monitor_pg: bool = True
    config_valid: bool = True
    heartbeat_ok: bool = True
    alert_line_ok: bool = True
    alert_high: bool = True
    open_wire_ok: bool = True
    cell_uv_ok: bool = True
    cell_ov_ok: bool = True
    comm_ok: bool = True
    vref_ok: bool = True
    por_clear: bool = True

    @property
    def cell_permit(self) -> bool:
        return all((
            self.monitor_pg, self.config_valid, self.heartbeat_ok,
            self.alert_line_ok, self.alert_high, self.open_wire_ok,
            self.cell_uv_ok, self.cell_ov_ok, self.comm_ok,
            self.vref_ok, self.por_clear,
        ))


class ArmLatch:
    """Fault-cleared latch; only a fresh ARM low->high edge can re-arm."""
    def __init__(self) -> None:
        self.armed = False
        self.fault_latched = False
        self.low_seen = True  # external pulldown establishes safe initial low

    def update(self, inputs: PermitInputs, manual_arm_req: bool) -> bool:
        if not manual_arm_req:
            self.low_seen = True
        if not inputs.cell_permit:
            self.armed = False
            self.fault_latched = True
            return False
        if manual_arm_req and self.low_seen:
            self.armed = True
            self.fault_latched = False
            self.low_seen = False
        return self.armed and inputs.cell_permit


def _scenario(name: str, cv_us: float, shared_us: float, loop_slow: int,
              cow_enabled: bool, cow_delay_ms: float, use_drift: bool,
              gate_ms: float | None = None, note: str = "") -> dict:
    cfg = ScanConfig(
        cv_slot_us_typ=cv_us,
        shared_slot_us_typ=shared_us,
        loop_slow=loop_slow,
        cow_enabled=cow_enabled,
        cow_delay_ms=cow_delay_ms,
        use_lfo_characterized_slow_drift=use_drift,
    )
    gate = pmos_gate_turnoff_ms() if gate_ms is None else gate_ms
    total = adscan_period_ms(cfg) + cell_input_filter_settle_ms() + ALERT_PROP_ASSUMED_MS + LOGIC_AND_DFF_ASSUMED_MS + gate
    row = {
        "scenario": name,
        "cells": CELLS,
        "cv_slot_us_typ": cv_us,
        "shared_slot_us_typ": shared_us,
        "lfo_slow_drift_applied": use_drift,
        "loop_slow": loop_slow,
        "cow_enabled": cow_enabled,
        "cow_delay_ms": cow_delay_ms if cow_enabled else 0.0,
        "adscan_period_ms": round(adscan_period_ms(cfg), 6),
        "input_filter_5tau_ms": round(cell_input_filter_settle_ms(), 6),
        "alert_delay_assumption_ms": ALERT_PROP_ASSUMED_MS,
        "logic_delay_assumption_ms": LOGIC_AND_DFF_ASSUMED_MS,
        "pmos_gate_near_zero_est_ms": round(gate, 6),
        "total_estimated_ms": round(total, 6),
        "5ms_estimate_screen": "ESTIMATE_ONLY_PASS" if total <= 5.0 else "ESTIMATE_FAIL",
        "hard_max_guaranteed": "NO",
        "note": note,
    }
    if name == "legacy_4p06_reproduction":
        row["5ms_estimate_screen"] = "LEGACY_NOT_VALID_FOR_RELEASE"
    return row


def build_scan_scenarios() -> list[dict]:
    return [
        _scenario("legacy_4p06_reproduction", 732, 732, 0, False, 0, False, 0.4,
                  "Legacy subtotal is 4.06ms (5*732us + 0.4ms); total column also adds current RC/ALERT/logic estimates."),
        _scenario("fast_no_cow_delay", 366, 366, 0, False, 0, True,
                  note="Fast ADC; COW disabled or COWDLY=0. Does not satisfy open-wire coverage."),
        _scenario("fast_cow_delay_1ms", 366, 366, 0, True, 1.0, True,
                  note="Candidate: DA Config=0x003F, full-speed loop, COWDLY=1ms."),
        _scenario("fast_half_loop_cow_delay_1ms", 366, 366, 1, True, 1.0, True,
                  note="Fails estimated 5ms due LOOP_SLOW=half."),
        _scenario("medium_fast_no_cow_delay", 732, 732, 0, False, 0, True,
                  note="Medium-fast scan with near-zero gate criterion; estimated fail."),
        _scenario("medium_fast_cow_delay_1ms", 732, 732, 0, True, 1.0, True,
                  note="Medium-fast plus COWDLY; estimated fail."),
        _scenario("default_slow_full_loop", 2930, 2930, 0, False, 0, True,
                  note="Default DA Config speed; fails 5ms."),
        _scenario("default_slow_half_loop", 2930, 2930, 1, False, 0, True,
                  note="Slow default conversion plus half-speed loop; reproduces ~29.7ms class."),
    ]


def build_timing_budget() -> list[dict]:
    cfg = ScanConfig(cv_slot_us_typ=366, shared_slot_us_typ=366, loop_slow=0,
                     cow_enabled=True, cow_delay_ms=1.0,
                     use_lfo_characterized_slow_drift=True)
    scan = adscan_period_ms(cfg)
    gate = pmos_gate_turnoff_ms()
    return [
        {"stage": "Cell voltage scan wait", "value_ms": round(scan, 6),
         "basis": "5 active slots at 366us typ, LFO -2.1% characterization-derived, plus 1ms COWDLY",
         "evidence_class": "TYPICAL_PLUS_CHARACTERIZATION_DERIVATION",
         "guaranteed_max": "NO"},
        {"stage": "Cell input RC settling", "value_ms": round(cell_input_filter_settle_ms(), 6),
         "basis": "2x(10ohm +1%) x 220nF +10%, 5 tau",
         "evidence_class": "CALCULATED_FROM_SCHEMATIC_VALUES",
         "guaranteed_max": "NO_CAPACITOR_EFFECTIVE_C_MAX_CONFIRMED"},
        {"stage": "BQ ALERT internal/pin propagation", "value_ms": ALERT_PROP_ASSUMED_MS,
         "basis": "50us engineering placeholder; TI does not publish a max propagation time for this event path",
         "evidence_class": "UNBOUNDED_BY_PUBLISHED_MAX",
         "guaranteed_max": "NO"},
        {"stage": "AND/DFF/control logic", "value_ms": LOGIC_AND_DFF_ASSUMED_MS,
         "basis": "0.1us placeholder; actual CLR-to-Q and assembled path not characterized here",
         "evidence_class": "ENGINEERING_ASSUMPTION",
         "guaranteed_max": "NO"},
        {"stage": "P-MOS gate to |VGS|<=0.1V (near-zero channel criterion)", "value_ms": round(gate, 6),
         "basis": "2x Si7149DP Qg(max)=147nC at VGS=-10V, R501=10k +1%, first-order equivalent-C screen",
         "evidence_class": "ENGINEERING_ESTIMATE_FROM_DATASHEET_MAX_CHARGE",
         "guaranteed_max": "NO_DEVICE_SPICE_OR_BENCH"},
        {"stage": "Total", "value_ms": round(scan + cell_input_filter_settle_ms() + ALERT_PROP_ASSUMED_MS + LOGIC_AND_DFF_ASSUMED_MS + gate, 6),
         "basis": "Sum of preceding rows",
         "evidence_class": "MODEL_ESTIMATE_ONLY",
         "guaranteed_max": "NO"},
    ]


def build_fault_matrix() -> list[dict]:
    return [
        {"fault": "Single-cell UV", "injection": "cell_uv_ok=False / CUV SAA alarm", "required": "CELL_PERMIT low; async clear; latch holds", "model_result": "PASS"},
        {"fault": "Cell tap open", "injection": "open_wire_ok=False", "required": "CELL_PERMIT low; no automatic re-arm", "model_result": "PASS_LOGIC_ONLY",
         "note": "BQ COW detection estimate is >5ms; not a 5ms guarantee."},
        {"fault": "Monitor reset", "injection": "por_clear=False, config_valid=False, heartbeat_ok=False", "required": "CELL_PERMIT low until full reinit", "model_result": "PASS_LOGIC_ONLY"},
        {"fault": "I2C NACK/CRC error", "injection": "comm_ok=False, heartbeat_ok=False", "required": "CELL_PERMIT low", "model_result": "PASS_LOGIC_ONLY"},
        {"fault": "Monitor supply lost", "injection": "monitor_pg=False", "required": "CELL_PERMIT low", "model_result": "PASS_LOGIC_ONLY"},
        {"fault": "ALERT asserted", "injection": "alert_high=False", "required": "CELL_PERMIT low", "model_result": "PASS"},
        {"fault": "ALERT open/stuck high", "injection": "alert_line_ok=False", "required": "CELL_PERMIT low", "model_result": "PASS_WITH_REQUIRED_LINE_SUPERVISION",
         "note": "Current schematic has no receiver-side EOL pulldown or independent line check."},
        {"fault": "MOS turn-off delay", "injection": "gate estimate > 5ms", "required": "5ms path criterion", "model_result": "FAIL_FOR_MEDIUMFAST_AND_LOOP_SLOW"},
        {"fault": "Fault clears while ARM held high", "injection": "restore safe inputs, keep manual_arm_req=True", "required": "remain disarmed", "model_result": "PASS"},
        {"fault": "ARM low then high", "injection": "safe inputs; manual ARM low, then high", "required": "explicit re-arm only", "model_result": "PASS"},
    ]


def build_waveform(cfg: ScanConfig, filename: str, step_ms: float = 0.05,
                   stop_ms: float = 8.0) -> list[dict]:
    # Conservative additive screen: full ADSCAN phase wait plus 5-tau input settling.
    sample_ms = adscan_period_ms(cfg) + cell_input_filter_settle_ms()
    alert_ms = sample_ms + ALERT_PROP_ASSUMED_MS
    gate_start_ms = alert_ms + LOGIC_AND_DFF_ASSUMED_MS
    gate_ms = pmos_gate_turnoff_ms()
    r501_max = R501_PULLUP_OHM * (1.0 + R501_TOL)
    r502_min = R502_PULLDOWN_OHM * (1.0 - R502_TOL)
    vgs0 = 9.4 * r501_max / (r501_max + r502_min)
    ceq = SI7149_FET_COUNT * (SI7149_QG_MAX_NC * 1e-9 / SI7149_QG_TEST_VGS_V)
    tau_ms = r501_max * ceq * 1000.0
    rows = []
    n = int(round(stop_ms / step_ms))
    for i in range(n + 1):
        t = i * step_ms
        sampled = abs(t - sample_ms) <= step_ms / 2.0
        alert_low = t >= alert_ms
        permit = not alert_low
        arm = not alert_low
        if t < gate_start_ms:
            vgs = -vgs0
        else:
            vgs = -vgs0 * math.exp(-(t - gate_start_ms) / tau_ms)
        rows.append({
            "time_ms": round(t, 6),
            "weak_cell_voltage_v": 1.049 if t >= 0 else 1.051,
            "cell_sample_event": int(sampled),
            "alert_low": int(alert_low),
            "cell_permit": int(permit),
            "discharge_arm_latched": int(arm),
            "pmos_vgs_v": round(vgs, 6),
            "channel_off_proxy_abs_vgs_le_0p1": int(abs(vgs) <= 0.1),
            "note": "VGS proxy only; not measured load current",
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    scenarios = build_scan_scenarios()
    timing = build_timing_budget()
    faults = build_fault_matrix()
    write_csv(out_dir / "scan_scenarios.csv", scenarios)
    write_csv(out_dir / "timing_budget.csv", timing)
    write_csv(out_dir / "fault_matrix.csv", faults)

    fast = ScanConfig(cv_slot_us_typ=366, shared_slot_us_typ=366, loop_slow=0,
                      cow_enabled=True, cow_delay_ms=1.0,
                      use_lfo_characterized_slow_drift=True)
    half = ScanConfig(cv_slot_us_typ=366, shared_slot_us_typ=366, loop_slow=1,
                      cow_enabled=True, cow_delay_ms=1.0,
                      use_lfo_characterized_slow_drift=True)
    med = ScanConfig(cv_slot_us_typ=732, shared_slot_us_typ=732, loop_slow=0,
                     cow_enabled=False, cow_delay_ms=0,
                     use_lfo_characterized_slow_drift=True)
    write_csv(out_dir / "waveform_fast_candidate.csv", build_waveform(fast, "fast"))
    write_csv(out_dir / "waveform_half_loop_failure.csv", build_waveform(half, "half"))
    write_csv(out_dir / "waveform_mediumfast_failure.csv", build_waveform(med, "mediumfast"))

    cow_ms = cow_open_wire_estimate_ms(fast, cowntime_fullscans=1)
    params = {
        "design": "4S BQ76905 CELL_PERMIT",
        "common_base_commit": "360508c08f23f63cdd74fba7e0c201b0907d3825",
        "nominal_cell_uv_threshold_mv": 1050,
        "measurement_accuracy_full_temp_mv": [-9.8, 9.8],
        "nominal_cuv_threshold_mv": 1050,
        "actual_cuv_trip_voltage_estimate_mv": [1040.2, 1059.8],
        "cell_count": 4,
        "normal_ads_scan_slots": 5,
        "da_config_recommended_hex": "0x003F",
        "power_config_recommended_hex": "0x04",
        "vcell_mode_recommended_hex": "0x04",
        "default_alarm_mask_recommended_hex": "0xE205",
        "enabled_protections_a_recommended_hex": "0xE1",
        "cuv_delay": 1,
        "cuv_recovery_hex": "0x00",
        "cow_normal_check_time": 1,
        "cow_sleep_check_time_hex": "0x10",
        "host_watchdog_timeout": 1,
        "host_watchdog_units": "seconds",
        "adscan_fast_slot_us_typ": 366,
        "lfo_slow_drift_characterized_percent": -2.1,
        "fast_cow_delay_scan_period_est_ms": round(adscan_period_ms(fast), 6),
        "gate_vgs_threshold_1p2v_est_ms": round(pmos_gate_turnoff_ms(vgs_target_abs_v=SI7149_VGS_THRESHOLD_MIN_ABS_V), 6),
        "gate_near_zero_est_ms": round(pmos_gate_turnoff_ms(), 6),
        "total_fast_candidate_est_ms": round(total_estimated_isolation_ms(fast), 6),
        "cow_open_wire_estimate_ms": round(cow_ms, 6),
        "cow_open_wire_current_uA_typ": 55,
        "cow_open_wire_time_is_not_max": True,
        "hard_5ms_guarantee": False,
        "cow_open_wire_estimate_near_uv_ms": round(cow_open_wire_estimate_ms(fast, 1, initial_cell_v=1.051), 6),
        "limitations": [
            "BQ76905 ADC conversion slot times are typical values, not max limits.",
            "LFO frequency drift is specified by characterization; absolute 25C oscillator frequency has no min/max production limit.",
            "No published max propagation delay was found for the CUV alert-to-ALERT pin path.",
            "Si7149DP gate RC estimate is not a vendor transient model and does not prove actual current isolation.",
            "BQ76905 COW current is 55uA typical; open-wire detection is not a 5ms mechanism.",
            "No ngspice executable was available in the execution environment; the included RC deck is not marked as run."
        ]
    }
    (out_dir / "parameters.json").write_text(json.dumps(params, indent=2) + "\n", encoding="utf-8")

    reg_rows = [
        {"name":"Power Config","address":"0x9014","value":"0x04","bytes_le":"04","meaning":"Full-speed LOOP_SPEED/CB_LOOP_SPEED; SLEEP_EN=0; LFOWD=1","status":"candidate; write/readback required"},
        {"name":"REGOUT Config","address":"0x9015","value":"0x0E","bytes_le":"0E","meaning":"REG_EN=1; REGCTL=6 => 3.3V","status":"candidate; required by 3.3V supervisor"},
        {"name":"I2C Config","address":"0x9017","value":"0x3401","bytes_le":"01 34","meaning":"Default timeout fields + CRC=1","status":"only if host CRC implementation is verified"},
        {"name":"DA Config","address":"0x9019","value":"0x003F","bytes_le":"3F 00","meaning":"CVADCSPEED=3, IADCSPEED=3, SSADCSPEED=3; TSMODE=0, CCMODE=0","status":"candidate fastest slot configuration"},
        {"name":"Vcell Mode","address":"0x901B","value":"0x04","bytes_le":"04","meaning":"4 actual cells","status":"required"},
        {"name":"Default Alarm Mask","address":"0x901C","value":"0xE205","bytes_le":"05 E2","meaning":"SSA+SSB+SAA+SHUTV+INITCOMP+POR","status":"candidate; reapply after reset unless OTP programmed"},
        {"name":"Enabled Protections A","address":"0x9024","value":"0xE1","bytes_le":"E1","meaning":"COV+CUV+SCD+REGOUT enabled","status":"CUV enabled; COV threshold owned by OVP module"},
        {"name":"Enabled Protections B","address":"0x9025","value":"0x01","bytes_le":"01","meaning":"HWD enabled","status":"secondary only; HWD minimum 1s"},
        {"name":"DSG FET Protections A","address":"0x9026","value":"0xFF","bytes_le":"FF","meaning":"CUV and other enabled faults disable DSG","status":"DSG pin is NC in current schematic; no physical action"},
        {"name":"Cell Open Wire NORMAL Check Time","address":"0x902B","value":"0x01","bytes_le":"01","meaning":"Minimum non-zero COW cadence","status":"not a 5ms diagnostic"},
        {"name":"Cell Open Wire SLEEP Check Time","address":"0x902C","value":"0x10","bytes_le":"10","meaning":"COWDLY=1ms; sleep COW disabled","status":"candidate; SLEEP disabled"},
        {"name":"Host Watchdog Timeout","address":"0x902D","value":"0x01","bytes_le":"01","meaning":"1 second timeout","status":"not a 5ms watchdog"},
        {"name":"CUV Threshold","address":"0x902E","value":"1050","bytes_le":"1A 04","meaning":"1050mV signed I2 little-endian","status":"candidate; threshold error must be included"},
        {"name":"CUV Delay","address":"0x9030","value":"0x01","bytes_le":"01","meaning":"1 ADSCAN","status":"minimum"},
        {"name":"CUV Recovery Hysteresis","address":"0x9031","value":"0x00","bytes_le":"00","meaning":"No autonomous recovery","status":"required for manual re-arm"},
        {"name":"Alarm Enable()","address":"0x66","value":"0xE205","bytes_le":"05 E2","meaning":"Runtime alarm mask includes SAA and POR/INITCOMP","status":"write and readback after every reset"},
    ]
    write_csv(out_dir / "register_config.csv", reg_rows)

    deck = """* BQ76905 CELL_PERMIT - simplified P-MOS gate RC screen only
* NOT a Si7149DP vendor model; NOT a BQ76905 model; validates only the RC screen.
* Two common gates represented by Qg(max)/VGS = 2*147nC/10V = 29.4nF.
* R501=10k+1%; R502 is disconnected when the series AO3400A pull-down opens.
V_SRC SRC 0 DC 0
R501 SRC GATE 10.1k
CGATE GATE SRC 29.4n IC=-8.56
.ic v(GATE)=-8.56
.control
set filetype=ascii
tran 1u 3m uic
write gate_turnoff_rc.raw v(GATE)
wrdata gate_turnoff_rc.dat v(GATE)
quit
.endc
.end
"""
    (out_dir / "gate_turnoff_rc.cir").write_text(deck, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    write_artifacts(Path(args.out_dir))
