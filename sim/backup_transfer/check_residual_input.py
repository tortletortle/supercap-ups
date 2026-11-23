"""Check steady-state source selection after the backup eFuse opens."""

from math import exp, log


def select_source(main_valid, main_preferred, backup_valid):
    if main_valid and (main_preferred or not backup_valid):
        return "MAIN"
    if backup_valid:
        return "BACKUP"
    return "HI_Z"


def main():
    # Illustrative bench values. The unloaded IN2 node decays through R.
    initial_voltage = 12.0
    mux_uv = 2.8
    capacitance = 100e-6
    bleed_resistance = 10_000
    fault_to_main_loss = 1e-3
    time_constant = bleed_resistance * capacitance
    residual_voltage = initial_voltage * exp(-fault_to_main_loss / time_constant)
    decay_to_uv = time_constant * log(initial_voltage / mux_uv)

    # name, main valid, XREF prefers main, IN2 above UV / below OV,
    # independent live backup qualification, expected raw and qualified routes
    cases = (
        ("backup still starting", False, False, False, False, "HI_Z", "HI_Z"),
        ("both supplies ready", True, True, True, True, "MAIN", "MAIN"),
        ("normal main loss", False, False, True, True, "BACKUP", "BACKUP"),
        ("backup fault during main sag", True, False, residual_voltage > mux_uv,
         False, "BACKUP", "MAIN"),
        ("backup fault before hard main loss", False, False, residual_voltage > mux_uv,
         False, "BACKUP", "HI_Z"),
        ("backup requalified with main absent", False, False, True, True, "BACKUP", "BACKUP"),
        ("main recovered", True, True, True, True, "MAIN", "MAIN"),
    )
    print(f"IN2 after 1 ms unloaded: {residual_voltage:.3f} V")
    print(f"Unloaded RC decay to illustrative UV threshold: {decay_to_uv:.3f} s")
    print("scenario,voltage_only_route,qualified_route")
    for name, main_valid, prefer_main, in2_valid, backup_ready, raw, qualified in cases:
        assert select_source(main_valid, prefer_main, in2_valid) == raw, name
        assert select_source(main_valid, prefer_main, in2_valid and backup_ready) == qualified, name
        print(f"{name},{raw},{qualified}")


if __name__ == "__main__":
    main()
