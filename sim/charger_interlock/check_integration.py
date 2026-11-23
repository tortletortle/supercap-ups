"""Compare ideal settled outputs for candidate charging permission interfaces."""
from check_policy import step


def main():
    # (ARM request, independent health): fault occurs with ARM held.
    sequence = (
        (False, False), (True, True), (False, True), (True, True),
        (True, False), (True, True), (False, True), (True, True),
    )
    armed, low_seen = False, False
    direct, independent, feedback = [], [], []
    feedback_armed, feedback_low_seen = False, False
    for request, health in sequence:
        # A held bench permission can enable both existing gates on recovery.
        direct.append(request and health)
        armed, low_seen = step(armed, low_seen, request, health)
        independent.append(armed and health)
        # If the latch drives Buck EN and also uses it as its own ready
        # input, the default-disabled state cannot qualify a new request.
        buck_en = feedback_armed and health
        feedback_armed, feedback_low_seen = step(
            feedback_armed, feedback_low_seen, request, buck_en,
        )
        feedback.append(feedback_armed and health)

    assert direct == [False, True, False, True, False, True, False, True]
    assert independent == [False, False, False, True, False, False, False, True]
    assert feedback == [False] * len(sequence)
    print("tick,arm,raw_health,held_bench_permit,independent_latch,en_feedback_latch")
    for tick, row in enumerate(zip(sequence, direct, independent, feedback)):
        (request, health), bench, isolated, loop = row
        print(tick, *map(int, (request, health, bench, isolated, loop)), sep=",")


if __name__ == "__main__":
    main()
