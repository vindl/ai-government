"""Tests for the circuit breaker in main_loop._check_circuit_breaker."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

scripts_path = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_path))

from government.models.telemetry import CycleTelemetry  # noqa: E402
from main_loop import _check_circuit_breaker  # noqa: E402


def _write_telemetry(path: Path, entries: list[CycleTelemetry]) -> None:
    """Write telemetry entries as JSONL."""
    with path.open("w") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")


def test_trips_on_consecutive_same_errors(tmp_path: Path) -> None:
    """Circuit breaker trips when N consecutive cycles share the same error."""
    tpath = tmp_path / "telemetry.jsonl"
    entries = [
        CycleTelemetry(cycle=i, errors=["SomeError: things broke"])
        for i in range(3)
    ]
    _write_telemetry(tpath, entries)

    with patch("main_loop.TELEMETRY_PATH", tpath), pytest.raises(SystemExit) as exc_info:
        _check_circuit_breaker()
    assert exc_info.value.code == 2


def test_no_trip_on_different_errors(tmp_path: Path) -> None:
    """Circuit breaker does NOT trip when each cycle has a different error."""
    tpath = tmp_path / "telemetry.jsonl"
    entries = [
        CycleTelemetry(cycle=0, errors=["ErrorA: one"]),
        CycleTelemetry(cycle=1, errors=["ErrorB: two"]),
        CycleTelemetry(cycle=2, errors=["ErrorC: three"]),
    ]
    _write_telemetry(tpath, entries)

    with patch("main_loop.TELEMETRY_PATH", tpath):
        _check_circuit_breaker()  # should NOT raise


def test_no_trip_with_success_in_between(tmp_path: Path) -> None:
    """Circuit breaker does NOT trip when a successful cycle breaks the streak."""
    tpath = tmp_path / "telemetry.jsonl"
    entries = [
        CycleTelemetry(cycle=0, errors=["SomeError: things broke"]),
        CycleTelemetry(cycle=1, errors=[]),  # success — no errors
        CycleTelemetry(cycle=2, errors=["SomeError: things broke"]),
    ]
    _write_telemetry(tpath, entries)

    with patch("main_loop.TELEMETRY_PATH", tpath):
        _check_circuit_breaker()  # should NOT raise


def test_no_trip_with_too_few_entries(tmp_path: Path) -> None:
    """Circuit breaker does NOT trip when there are fewer entries than threshold."""
    tpath = tmp_path / "telemetry.jsonl"
    entries = [
        CycleTelemetry(cycle=0, errors=["SomeError: things broke"]),
    ]
    _write_telemetry(tpath, entries)

    with patch("main_loop.TELEMETRY_PATH", tpath):
        _check_circuit_breaker()  # should NOT raise


def test_no_crash_on_corrupt_telemetry(tmp_path: Path) -> None:
    """Circuit breaker does NOT crash when telemetry file is corrupt."""
    tpath = tmp_path / "telemetry.jsonl"
    tpath.write_text("not valid json\n{also bad}\n")

    with patch("main_loop.TELEMETRY_PATH", tpath):
        _check_circuit_breaker()  # should NOT raise
