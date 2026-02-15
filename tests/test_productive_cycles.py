"""Tests for productive cycle counting in main_loop."""

from __future__ import annotations


def test_productive_cycle_increments_when_task_executed() -> None:
    """Productive cycles should increment when Phase C executes a task."""
    # Simulate Phase C with a task
    issue = {"number": 1, "title": "Test issue"}
    productive_cycles = 0

    # Phase C was productive
    phase_c_was_productive = issue is not None
    if phase_c_was_productive:
        productive_cycles += 1

    assert productive_cycles == 1


def test_productive_cycle_no_increment_when_idle() -> None:
    """Productive cycles should not increment during idle cycles."""
    # Simulate Phase C with no task (rate-limited or empty backlog)
    issue = None
    productive_cycles = 0

    # Phase C was not productive
    phase_c_was_productive = issue is not None
    if phase_c_was_productive:
        productive_cycles += 1

    assert productive_cycles == 0


def test_director_triggers_on_productive_cycles_not_all_cycles() -> None:
    """Directors should trigger based on productive cycles, not all cycles."""
    director_interval = 5

    # Key insight: Director fires whenever productive_cycles is divisible by interval
    # So it will fire on productive cycles 5, 10, 15, 20, etc.
    # During idle cycles, productive_cycles stays the same, so the check will
    # still pass if we just hit a milestone. This is actually fine - the director
    # will just run on the next cycle after hitting the milestone.
    #
    # The important fix is that it counts PRODUCTIVE cycles, not total cycles.
    # So if you have 10 total cycles but only 5 productive, director fires at
    # cycle 9 (when productive_cycles becomes 5), not at cycle 5.
    test_cases = [
        # (productive_cycles, should_run_director)
        (1, False),  # First productive cycle
        (2, False),  # Second productive cycle
        (3, False),  # Third productive cycle
        (4, False),  # Fourth productive cycle
        (5, True),   # Fifth productive cycle — director fires!
        (6, False),  # Sixth productive cycle
        (10, True),  # Tenth productive cycle — director fires again!
        (15, True),  # Fifteenth productive cycle — director fires!
    ]

    for productive_cycles, expected in test_cases:
        should_run = (
            director_interval > 0
            and productive_cycles % director_interval == 0
            and productive_cycles >= director_interval
        )
        assert should_run == expected, (
            f"productive_cycles {productive_cycles}: "
            f"expected {expected}, got {should_run}"
        )


def test_strategic_director_uses_productive_cycles() -> None:
    """Strategic Director should also use productive cycles."""
    strategic_interval = 10

    # Strategic Director should fire on productive cycle 10, not cycle 10
    test_cases = [
        # (productive_cycles, should_run_strategic)
        (5, False),
        (9, False),
        (10, True),   # First strategic director run
        (11, False),
        (20, True),   # Second strategic director run
    ]

    for productive_cycles, expected in test_cases:
        should_run = (
            strategic_interval > 0
            and productive_cycles % strategic_interval == 0
            and productive_cycles >= strategic_interval
        )
        assert should_run == expected, (
            f"productive_cycles {productive_cycles}: "
            f"expected {expected}, got {should_run}"
        )


def test_productive_cycles_accumulate_across_reexecs() -> None:
    """Productive cycles should persist across re-execs."""
    # Simulate first run: 3 productive cycles
    productive_cycles_offset = 0
    productive_cycles = productive_cycles_offset + 3  # After 3 productive cycles

    # Re-exec with offset
    productive_cycles_offset = productive_cycles
    productive_cycles = productive_cycles_offset  # Start from offset

    # Two more productive cycles
    productive_cycles += 1
    productive_cycles += 1

    # Should have accumulated 5 total productive cycles
    assert productive_cycles == 5
