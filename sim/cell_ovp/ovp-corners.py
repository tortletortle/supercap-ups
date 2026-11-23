"""DC engineering corner budgets, not a transient or semiconductor model."""
from itertools import product

DT = 65
DIFF_RES = 0.001 + 25e-6 * DT
SUP_REF_RES = 0.001 + 15e-6 * DT
SUP_VIN_RES = 0.01 + 100e-6 * DT
OPA_OFF = 0.0005
# Conservative output-referred bias/PCB term. Validate with powered tap emulators.
OPA_OUTPUT_BIAS = 0.003
CMP_OFF = 0.0055
REF_ERROR = 0.005
TOL_SIGNS = (-1, 1)


def cell_trip(ref_values):
    output = []
    for signs in product(TOL_SIGNS, repeat=4):
        rt, rb, rl, rf = [1 + sign * DIFF_RES for sign in signs]
        divider = rb / (rt + rb)
        gain = rf / rl
        a = (1 + gain) * divider
        b = a - gain
        for reference, tap_low, opa_off, cmp_off, bias in product(
            ref_values, (0, 7), (-OPA_OFF, OPA_OFF), (-CMP_OFF, CMP_OFF),
            (-OPA_OUTPUT_BIAS, OPA_OUTPUT_BIAS),
        ):
            output.append((reference + cmp_off - b * tap_low - (1 + gain) * opa_off - bias) / a)
    return min(output), max(output)


def supervisor(rt_nom, rb_nom, tolerance, ref_bounds, bias):
    voltages = []
    for st, sb, si, threshold in product(TOL_SIGNS, TOL_SIGNS, TOL_SIGNS, ref_bounds):
        rt = rt_nom * (1 + st * tolerance)
        rb = rb_nom * (1 + sb * tolerance)
        voltages.append(threshold * (1 + rt / rb) + si * rt * bias)
    return min(voltages), max(voltages)


def main():
    cell_nominal = cell_trip((2.5 - REF_ERROR, 2.5 + REF_ERROR))
    vin_down = supervisor(200e3, 10e3, SUP_VIN_RES, (0.387, 0.4), 25e-9)
    vin_up = supervisor(200e3, 10e3, SUP_VIN_RES, (0.396, 0.404), 25e-9)
    ref_up = supervisor(53.6e3, 10e3, SUP_REF_RES, (0.396, 0.404), 15e-9)
    ref_down = supervisor(53.6e3, 10e3, SUP_REF_RES, (0.387, 0.4), 15e-9)
    reference_fault_max = cell_trip(ref_up)[1]
    print(f'Cell threshold with valid reference    {cell_nominal[0]:.4f} ... {cell_nominal[1]:.4f} V')
    print(f'Main falling clamp assertion          {vin_down[0]:.3f} ... {vin_down[1]:.3f} V')
    print(f'Main rising clamp release             {vin_up[0]:.3f} ... {vin_up[1]:.3f} V')
    print(f'Reference rising clamp assertion      {ref_up[0]:.4f} ... {ref_up[1]:.4f} V')
    print(f'Reference falling clamp release       {ref_down[0]:.4f} ... {ref_down[1]:.4f} V')
    print(f'Assert-on-rise bound with ref-high drift  {reference_fault_max:.4f} V')
    assert cell_nominal[0] > 2.4352
    assert cell_nominal[1] < 2.7
    assert ref_up[0] > 2.5 + REF_ERROR
    assert reference_fault_max < 2.7

if __name__ == '__main__':
    main()
