"""Static tolerance corners for the precision charger and independent OVP draft."""

from itertools import product

PACK_MAX = 9.4
REQUIRED_OCV = 9.0

# REF5025 high grade 0.05% initial + 3 ppm/°C box method across -40..125 °C.
# Additional 100 ppm is a design allowance for line, aging and thermal hysteresis.
REF_ERROR = 0.00050 + 3e-6 * 165 + 0.00010
# Acceptance limit for chosen matched network: 0.05% initial plus 5 ppm/°C
# with max 100 °C distance from 25 °C. A specific orderable ratio is still needed.
RATIO_ERROR = 0.00050 + 5e-6 * 100
# Include OPA333 input error, bias, and stable resistor-capacitor loop residual.
CV_INPUT_ERROR_V = 0.00015
# TLV9031 offset is ±2 mV; allocate another 1.5 mV for hysteresis/bias/layout.
# The added amount is an engineering allowance requiring measured confirmation.
OVP_INPUT_ERROR_V = 0.00350


def window(top_kohm, input_error):
    ratio = top_kohm / 20.0
    outcomes = [
        (2.5 * (1 + ref_sign * REF_ERROR) + input_sign * input_error)
        * (1 + ratio * (1 + ratio_sign * RATIO_ERROR))
        for ref_sign, input_sign, ratio_sign in product((-1, 1), repeat=3)
    ]
    return min(outcomes), 2.5 * (1 + ratio), max(outcomes)


def main():
    cv_lo, cv_mid, cv_hi = window(52.6, CV_INPUT_ERROR_V)
    ovp_lo, ovp_mid, ovp_hi = window(54.2, OVP_INPUT_ERROR_V)
    print(f"CV  static [V]: {cv_lo:.4f} .. {cv_hi:.4f}, nom {cv_mid:.4f}")
    print(f"OVP static [V]: {ovp_lo:.4f} .. {ovp_hi:.4f}, nom {ovp_mid:.4f}")
    print(f"CV peak to earliest OVP allowance: {(ovp_lo - cv_hi)*1000:.1f} mV")
    print(f"Latest OVP to pack maximum allowance: {(PACK_MAX - ovp_hi)*1000:.1f} mV")
    print(f"Minimum CV to required OCV allowance: {(cv_lo - REQUIRED_OCV)*1000:.1f} mV")


if __name__ == "__main__":
    main()
