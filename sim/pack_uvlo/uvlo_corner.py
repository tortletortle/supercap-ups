"""DC nodal corner estimate for the TPS3700 pack supervisor."""
from itertools import product
from math import inf

RT, RB, RF, RP, RD = 174e3, 10e3, 1.5e6, 100e3, 68e3
NOM = (RT, RB, RF, RP, RD)


def threshold(resistors, sense, i_sense, *, out_low=None, out_leak=0, rload=inf):
    """Solve KCL at UV_SENSE and PACK_UV_OK at the crossing."""
    rt, rb, rf, rp, rd = resistors
    conductance = 1 / rp + 1 / rd + 1 / rf + 1 / rload
    output_slope = 0 if out_low is not None else 1 / (rp * conductance)
    output_offset = out_low if out_low is not None else (sense / rf - out_leak) / conductance
    pack = (sense * (1 / rt + 1 / rb + 1 / rf) - output_offset / rf + i_sense)
    pack /= 1 / rt + output_slope / rf
    return pack, pack * output_slope + output_offset


def released_output(resistors, pack, i_sense, out_leak, rload):
    rt, rb, rf, rp, rd = resistors
    sense_conductance = 1 / rt + 1 / rb + 1 / rf
    output_conductance = 1 / rp + 1 / rd + 1 / rf + 1 / rload
    filtered = (pack / rt - i_sense) / sense_conductance
    return ((pack / rp + filtered / rf - out_leak)
            / (output_conductance - 1 / (rf * rf * sense_conductance)))


def corners():
    for tolerances in product((0.999, 1.001), repeat=5):
        resistors = tuple(value * tolerance for value, tolerance in zip(NOM, tolerances))
        for i_sense, rload, out_leak, vlow, trip_points in product(
            (-25e-9, 25e-9), (10e6, inf), (-400e-9, 400e-9),
            (0, 0.25),
            ((0.396, 0.387), (0.399, 0.387), (0.404, 0.392),
             (0.404, 0.400), (0.400, 0.400), (0.396, 0.396)),
        ):
            vplus, vminus = trip_points
            rise, _ = threshold(resistors, vplus, i_sense, out_low=vlow)
            fall, high = threshold(resistors, vminus, i_sense, out_leak=out_leak, rload=rload)
            at_max = released_output(resistors, 9.4, i_sense, out_leak, rload)
            yield rise, fall, rise - fall, high, at_max


if __name__ == "__main__":
    rise, _ = threshold(NOM, 0.4, 1e-9, out_low=0)
    fall, high = threshold(NOM, 0.3945, 1e-9)
    print(f"Nominal rise {rise:.6f} V; fall {fall:.6f} V; hysteresis {rise - fall:.6f} V")
    print(f"Nominal high just before cutoff {high:.6f} V")
    results = list(corners())
    print(f"Evaluated {len(results)} simultaneous corners")
    for name, column in zip(("rise", "fall", "hysteresis", "high before cutoff", "high at 9.4 V"), zip(*results)):
        print(f"{name}: {min(column):.6f} to {max(column):.6f} V")
    assert all(fall < rise for rise, fall, *_ in results)
    assert all(6.70 <= fall < 7.285256 for _, fall, *_ in results)
    assert all(2.65 < high < at_max < 4 for _, _, _, high, at_max in results)
