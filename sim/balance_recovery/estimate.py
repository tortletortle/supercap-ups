"""Size a current-limited shunt after one series cell reaches its clamp."""
import argparse


def clamp_recovery(weak_f, strong_f, clamp_v, pack_v, current_a):
    """Return first-clamp pack voltage, remaining charge and steady shunt power."""
    first_clamp_pack = clamp_v * (1 + 3 * weak_f / strong_f)
    if not first_clamp_pack <= pack_v <= 4 * clamp_v:
        raise ValueError("Target must lie between first clamp and four clamped cells")
    remaining_charge = strong_f * (pack_v - clamp_v) / 3 - weak_f * clamp_v
    return first_clamp_pack, remaining_charge / current_a, clamp_v * current_a


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-target", type=float, default=9.35)
    args = parser.parse_args()
    print("weak_F,strong_F,clamp_V,charge_A,first_clamp_pack_V,recovery_s,shunt_W")
    for weak_f, strong_f in ((9, 13), (6.3, 9)):
        for clamp_v in (2.5, 2.6):
            for current_a in (0.025, 0.05, 0.1, 0.5):
                first, seconds, watts = clamp_recovery(
                    weak_f, strong_f, clamp_v, args.pack_target, current_a
                )
                print(
                    f"{weak_f:g},{strong_f:g},{clamp_v:.2f},{current_a:.3f},"
                    f"{first:.4f},{seconds:.3f},{watts:.4f}"
                )


if __name__ == "__main__":
    main()
