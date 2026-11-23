"""Boolean acceptance reference for charger power-up and fault re-arming."""
from itertools import product


def step(armed, low_seen_ready, request, ready):
    """Accept an ARM high only after observing ARM low in a ready state."""
    if not ready:
        return False, False
    return armed or (low_seen_ready and request), not request


def main():
    checked = 0
    for armed, low_seen, request, rails, references, sense, protection in product(
        (False, True), repeat=7
    ):
        ready = rails and references and sense and protection
        result, qualified = step(armed, low_seen, request, ready)
        if not ready:
            assert (result, qualified) == (False, False)
        else:
            assert qualified == (not request)
            if not armed:
                assert result == (low_seen and request)
        checked += 1

    tests = (
        ("held high at startup", [(True, False), (True, True), (True, True),
                                  (False, True), (True, True)],
         [False, False, False, False, True]),
        ("edge coincident with readiness", [(False, False), (True, True),
                                            (False, True), (True, True)],
         [False, False, False, True]),
        ("fault with request held high", [(False, True), (True, True), (True, False),
                                          (True, True), (False, True), (True, True)],
         [False, True, False, False, False, True]),
        ("arm pulse wholly during fault", [(False, False), (True, False), (False, False),
                                          (False, True), (True, True)],
         [False, False, False, False, True]),
    )
    for name, sequence, expected in tests:
        armed, low_seen = False, False
        observed = []
        for request, ready in sequence:
            armed, low_seen = step(armed, low_seen, request, ready)
            observed.append(armed)
        assert observed == expected, name
    print(f"{checked} digital combinations and {len(tests)} startup/fault sequences passed")


if __name__ == "__main__":
    main()
