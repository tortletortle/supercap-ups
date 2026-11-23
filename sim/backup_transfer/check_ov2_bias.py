"""Static corner checks for the residual-powered OV2 bias candidate."""
from itertools import product

IN2_MIN_FALLING_UV = 2.4
IN2_REVIEW_MAX = 13.2
OV2_RISE_MAX = 1.10
OV2_FALL_MIN = 0.99
OV2_OPERATING_MAX = 5.5
CLAMP_LOW, CLAMP_HIGH = 2.40, 2.60
SHUNT_MIN_CURRENT = 80e-6
SHUNT_MAX_CURRENT = 15e-3


def main():
    # Include provisional budgets for sub-knee shunt current, MOSFET
    # off leakage, and board leakage in addition to TPS2121 pin leakage.
    blocked, qualified, clamp_currents = [], [], []
    for top_scale, bottom_scale, leak in product(
        (0.99, 1.01), (0.99, 1.01), (-10e-6, 10e-6)
    ):
        top, bottom = 10_000 * top_scale, 15_000 * bottom_scale
        blocked.append((IN2_MIN_FALLING_UV / top - leak) / (1 / top + 1 / bottom))
        qualified.append((IN2_REVIEW_MAX / top - leak) / (1 / top + 1 / bottom + 1 / 100))
        for clamp_voltage in (CLAMP_LOW, CLAMP_HIGH):
            clamp_currents.append(
                (IN2_REVIEW_MAX - clamp_voltage) / top - clamp_voltage / bottom - leak
            )

    assert OV2_RISE_MAX / IN2_MIN_FALLING_UV >= OV2_OPERATING_MAX / 12
    assert min(blocked) > OV2_RISE_MAX
    assert max(qualified) < OV2_FALL_MIN
    assert CLAMP_HIGH < OV2_OPERATING_MAX
    assert SHUNT_MIN_CURRENT < min(clamp_currents)
    assert max(clamp_currents) < SHUNT_MAX_CURRENT
    print(f"OV2 at falling UV boundary, minimum: {min(blocked):.3f} V")
    print(f"OV2 qualified, maximum: {max(qualified):.3f} V")
    print(f"Clamp current at {IN2_REVIEW_MAX:g} V: "
          f"{1e3 * min(clamp_currents):.3f}–{1e3 * max(clamp_currents):.3f} mA")


if __name__ == "__main__":
    main()
