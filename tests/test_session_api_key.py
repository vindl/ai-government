"""Tests for session API key pre-flight check."""

from __future__ import annotations

import pytest
from government.session import check_api_key


def test_check_api_key_exits_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_api_key exits with code 1 when ANTHROPIC_API_KEY is not set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="1"):
        check_api_key()


def test_check_api_key_exits_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_api_key exits with code 1 when ANTHROPIC_API_KEY is empty."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(SystemExit, match="1"):
        check_api_key()


def test_check_api_key_exits_when_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_api_key exits with code 1 when ANTHROPIC_API_KEY is whitespace."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    with pytest.raises(SystemExit, match="1"):
        check_api_key()


def test_check_api_key_passes_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_api_key does not exit when ANTHROPIC_API_KEY is set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    check_api_key()  # should not raise
